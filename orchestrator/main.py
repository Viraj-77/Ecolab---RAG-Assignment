"""Orchestrator — central conductor for the A2A workflow.

Owns:
- Intent classification (keyword first; LLM fallback when configured).
- Registry-based capability lookup.
- Per-step persistence to SQLite (workflows + poison tables).
- Timeout + retry with idempotency_key reuse.
- Resume of in-progress workflows on restart (best-effort: any workflow
  that was mid-flight when the orchestrator died is marked failed and
  flagged in the resume log; replay is the user's job — see
  docs/failure-modes.md for why we picked "fail loudly" over silent
  resume in the bootcamp version).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from envelope import Envelope
from observability import configure_root, log_event

from .classifier import CAP_MCP, CAP_RAG, classify
from .state import WorkflowStore

REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:8000")
ORCH_NAME = "orchestrator"
ORCH_PORT = int(os.environ.get("ORCH_PORT", "8001"))
ORCH_ENDPOINT = os.environ.get("ORCH_ENDPOINT", f"http://localhost:{ORCH_PORT}/request")
ORCH_HEALTH = os.environ.get("ORCH_HEALTH", f"http://localhost:{ORCH_PORT}/health")

CAPABILITIES = ["orchestrate-radar-request"]

CALL_TIMEOUT_SECONDS = float(os.environ.get("ORCH_CALL_TIMEOUT", "5.0"))
MAX_ATTEMPTS = int(os.environ.get("ORCH_MAX_ATTEMPTS", "3"))  # 1 try + 2 retries
HEARTBEAT_INTERVAL_SECONDS = 10.0
REGISTRY_LOOKUP_TIMEOUT = 3.0

configure_root()
logger = logging.getLogger(__name__)

_store = WorkflowStore()


class RequestBody(BaseModel):
    """User-facing request shape: just a free-text string."""

    text: str
    # Optional structured params for write requests (an action + params dict).
    # When present, the orchestrator skips the keyword classifier — the user
    # is being explicit about what they want. Useful for the chaos/demo
    # scripts and for clients that already know the action shape.
    action: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class RequestResponse(BaseModel):
    correlation_id: str
    status: str
    capability: str
    answer: Optional[Any] = None
    error: Optional[str] = None


# ---------- registry interaction ----------


async def _registry_lookup(capability: str) -> Optional[str]:
    """Return the endpoint URL for the first agent advertising ``capability``."""
    async with httpx.AsyncClient(timeout=REGISTRY_LOOKUP_TIMEOUT) as client:
        resp = await client.get(
            f"{REGISTRY_URL}/agents", params={"capability": capability}
        )
        resp.raise_for_status()
        agents = resp.json()
    if not agents:
        return None
    # Pick the first one — the rubric says "match capabilities, not hardcode";
    # we don't need fancy load balancing for the bootcamp.
    return agents[0]["endpoint"]


async def _register_self() -> None:
    try:
        async with httpx.AsyncClient(timeout=REGISTRY_LOOKUP_TIMEOUT) as client:
            await client.post(
                f"{REGISTRY_URL}/register",
                json={
                    "name": ORCH_NAME,
                    "capabilities": CAPABILITIES,
                    "endpoint": ORCH_ENDPOINT,
                    "health_url": ORCH_HEALTH,
                },
            )
        logger.info("orchestrator registered")
    except Exception as e:
        logger.warning("startup registration failed: %s", e)


async def _deregister_self() -> None:
    try:
        async with httpx.AsyncClient(timeout=REGISTRY_LOOKUP_TIMEOUT) as client:
            await client.delete(f"{REGISTRY_URL}/deregister/{ORCH_NAME}")
    except Exception as e:
        logger.debug("deregister failed: %s", e)


async def _heartbeat_loop() -> None:
    while True:
        try:
            async with httpx.AsyncClient(timeout=REGISTRY_LOOKUP_TIMEOUT) as client:
                await client.put(f"{REGISTRY_URL}/heartbeat/{ORCH_NAME}")
        except Exception as e:
            logger.debug("heartbeat failed: %s", e)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


# ---------- the dispatch loop ----------


async def _send_with_retries(envelope: Envelope, endpoint: str) -> Envelope:
    """POST envelope to endpoint with timeout + retries.

    On HTTPX timeout we retry with the SAME envelope (same idempotency_key)
    so the receiver can dedupe via its LRU cache. After ``MAX_ATTEMPTS``
    timeouts in a row we surface the timeout to the caller — the orchestrator
    handles "now what" (retry budget exceeded → poison).
    """
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT_SECONDS) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                log_event(
                    event="dispatch_attempt",
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.causation_id,
                    sender=envelope.sender,
                    recipient=envelope.recipient,
                    capability=envelope.capability,
                    attempt=attempt,
                    endpoint=endpoint,
                    idempotency_key=envelope.idempotency_key,
                )
                resp = await client.post(endpoint, json=envelope.model_dump())
                resp.raise_for_status()
                return Envelope(**resp.json())
            except httpx.TimeoutException as e:
                last_exc = e
                log_event(
                    event="dispatch_timeout",
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.causation_id,
                    sender=envelope.sender,
                    recipient=envelope.recipient,
                    capability=envelope.capability,
                    attempt=attempt,
                    endpoint=endpoint,
                    idempotency_key=envelope.idempotency_key,
                    timeout_s=CALL_TIMEOUT_SECONDS,
                )
            except httpx.HTTPError as e:
                # Connection errors / 5xx — also retryable; same key.
                last_exc = e
                log_event(
                    event="dispatch_http_error",
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.causation_id,
                    sender=envelope.sender,
                    recipient=envelope.recipient,
                    capability=envelope.capability,
                    attempt=attempt,
                    endpoint=endpoint,
                    error=str(e),
                )
            # exponential-ish backoff between attempts (small, since user is waiting)
            await asyncio.sleep(0.25 * attempt)
    assert last_exc is not None
    raise last_exc


async def _resume_in_progress() -> None:
    """On startup, any workflow still marked in_progress was interrupted.

    We mark them ``failed`` and emit a ``workflow_interrupted`` event. The user
    can replay by issuing the original request again — the agents' idempotency
    LRU is in-memory so it's been wiped too, but the original request text is
    persisted on the workflow row.
    """
    rows = _store.list_in_progress()
    for r in rows:
        cid = r["correlation_id"]
        _store.update(cid, status="failed", step="orchestrator_restart")
        log_event(
            event="workflow_interrupted",
            correlation_id=cid,
            sender=ORCH_NAME,
            previous_status=r["status"],
            previous_step=r["step"],
            user_request=r["user_request"],
            note="orchestrator restarted while workflow was in flight",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(event="orchestrator_starting", sender=ORCH_NAME)
    await _register_self()
    await _resume_in_progress()
    hb_task = asyncio.create_task(_heartbeat_loop())
    try:
        yield
    finally:
        hb_task.cancel()
        await _deregister_self()
        log_event(event="orchestrator_stopping", sender=ORCH_NAME)


app = FastAPI(title="A2A Orchestrator", lifespan=lifespan)


# ---------- HTTP surface ----------


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "agent": ORCH_NAME,
        "capabilities": CAPABILITIES,
        "in_progress_workflows": len(_store.list_in_progress()),
    }


@app.get("/workflows/{correlation_id}")
def get_workflow(correlation_id: str) -> dict:
    row = _store.get(correlation_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown correlation_id")
    return row


@app.get("/workflows")
def list_workflows(limit: int = 25) -> list[dict]:
    return _store.list_recent(limit=limit)


@app.get("/poison")
def list_poison() -> list[dict]:
    return _store.list_poison()


@app.post("/request", response_model=RequestResponse)
async def handle_request(req: RequestBody) -> RequestResponse:
    correlation_id = str(uuid.uuid4())
    started = time.time()

    log_event(
        event="user_request_received",
        correlation_id=correlation_id,
        sender="user",
        recipient=ORCH_NAME,
        user_request=req.text,
        explicit_action=req.action,
    )
    _store.create(correlation_id=correlation_id, user_request=req.text)

    # ---------- intent classification ----------
    if req.action:
        # User was explicit — write request via structured action.
        decision = None
        capability = CAP_MCP
        payload: dict[str, Any] = {"action": req.action, "params": req.params or {}}
        log_event(
            event="intent_classified",
            correlation_id=correlation_id,
            sender=ORCH_NAME,
            chosen_capability=capability,
            method="explicit_action",
            user_request=req.text,
            action=req.action,
        )
    else:
        decision = classify(req.text)
        capability = decision.chosen_capability
        log_event(
            event="intent_classified",
            correlation_id=correlation_id,
            sender=ORCH_NAME,
            **decision.to_log_extras(),
        )
        if capability == CAP_RAG:
            payload = {"question": req.text}
        else:
            # Ambiguous user input wanting a write — without an explicit action
            # we can't responsibly mutate the radar. Send to RAG instead and
            # tell the user how to make the write request explicit.
            log_event(
                event="write_intent_without_action",
                correlation_id=correlation_id,
                sender=ORCH_NAME,
                user_request=req.text,
                note="downgrading to read; client must pass action+params for writes",
            )
            capability = CAP_RAG
            payload = {"question": req.text}

    _store.update(correlation_id, step=f"dispatching:{capability}", status="in_progress")

    # ---------- registry lookup ----------
    try:
        endpoint = await _registry_lookup(capability)
    except Exception as e:
        log_event(
            event="registry_lookup_failed",
            correlation_id=correlation_id,
            sender=ORCH_NAME,
            capability=capability,
            error=str(e),
        )
        _store.update(correlation_id, status="failed", step="registry_lookup_failed")
        return RequestResponse(
            correlation_id=correlation_id,
            status="failed",
            capability=capability,
            error=f"registry lookup failed: {e}",
        )
    if not endpoint:
        log_event(
            event="no_agent_for_capability",
            correlation_id=correlation_id,
            sender=ORCH_NAME,
            capability=capability,
        )
        _store.update(correlation_id, status="failed", step="no_agent_for_capability")
        return RequestResponse(
            correlation_id=correlation_id,
            status="failed",
            capability=capability,
            error=f"no agent advertises capability '{capability}'",
        )

    # ---------- build envelope ----------
    out = Envelope(
        correlation_id=correlation_id,
        sender=ORCH_NAME,
        recipient=capability,  # logical recipient — we resolved a concrete endpoint
        capability=capability,
        payload=payload,
    )
    log_event(
        event="envelope_dispatched",
        correlation_id=correlation_id,
        causation_id=out.causation_id,
        sender=ORCH_NAME,
        recipient=capability,
        capability=capability,
        idempotency_key=out.idempotency_key,
        endpoint=endpoint,
    )

    # ---------- send with retries ----------
    try:
        reply = await _send_with_retries(out, endpoint)
    except Exception as e:
        # Retry budget exhausted or non-retryable error — poison.
        _store.update(
            correlation_id,
            step="poisoned",
            status="poisoned",
            last_envelope=out.model_dump(),
            bump_attempt=True,
        )
        _store.add_poison(
            correlation_id=correlation_id,
            envelope=out.model_dump(),
            reason=f"{type(e).__name__}: {e}",
        )
        log_event(
            event="workflow_poisoned",
            correlation_id=correlation_id,
            sender=ORCH_NAME,
            recipient=capability,
            capability=capability,
            error=str(e),
            elapsed_ms=int((time.time() - started) * 1000),
        )
        return RequestResponse(
            correlation_id=correlation_id,
            status="poisoned",
            capability=capability,
            error=str(e),
        )

    log_event(
        event="reply_received",
        correlation_id=correlation_id,
        causation_id=reply.causation_id,
        sender=reply.sender,
        recipient=ORCH_NAME,
        capability=capability,
        ok=reply.payload.get("ok"),
    )
    _store.update(
        correlation_id,
        step="completed",
        status="completed",
        last_envelope=reply.model_dump(),
        final_response=reply.payload,
    )
    log_event(
        event="workflow_completed",
        correlation_id=correlation_id,
        sender=ORCH_NAME,
        capability=capability,
        elapsed_ms=int((time.time() - started) * 1000),
    )
    return RequestResponse(
        correlation_id=correlation_id,
        status="completed",
        capability=capability,
        answer=reply.payload,
    )


__all__ = ["app"]
