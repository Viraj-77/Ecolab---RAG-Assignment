"""MCP agent — A2A wrapper around exercise-b-mcp.

Capability: ``propose-radar-change``.
Port: 8003.

The agent talks to the vendored ``RadarProxy`` directly (in-process), which
is the same surface the MCP stdio server exposes via ``execute()``. The
A2A payload is structured — ``{"action": "add_technology", ...}`` — rather
than free-form Python code, because envelopes are typed and the
sandboxing concern from Exercise B doesn't apply when the caller is
another trusted agent in the same A2A mesh.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI

# Make the vendored mcp-server package importable as `src`.
_MCP_ROOT = Path(__file__).resolve().parents[2] / "exercise-b-mcp" / "mcp-server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))

REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:8000")
AGENT_NAME = "mcp-agent"
AGENT_PORT = int(os.environ.get("MCP_AGENT_PORT", "8003"))
AGENT_ENDPOINT = os.environ.get("MCP_AGENT_ENDPOINT", f"http://localhost:{AGENT_PORT}/invoke")
AGENT_HEALTH = os.environ.get("MCP_AGENT_HEALTH", f"http://localhost:{AGENT_PORT}/health")
CAPABILITIES = ["propose-radar-change"]

from envelope import Envelope  # noqa: E402
from agents.lifecycle import IdempotencyLRU, make_lifespan  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_idempotency = IdempotencyLRU(max_size=1000)


def _try_load_radar():
    """Best-effort import of the vendored RadarProxy."""
    try:
        from src.proxy import RadarProxy  # type: ignore
        return RadarProxy
    except Exception as e:
        logger.warning("RadarProxy unavailable, mcp-agent will reply with stubs: %s", e)
        return None


_RadarProxy = _try_load_radar()


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


# Allowed structured actions -> proxy method name.
# Read methods are exposed too so the orchestrator can ground a write
# (e.g. "what's already in the radar?") without a separate RAG call.
_READ_ACTIONS = {
    "list_technologies": "list_technologies",
    "list_teams": "list_teams",
    "list_assignments": "list_assignments",
    "get_assignment": "get_assignment",
}
_WRITE_ACTIONS = {
    "add_technology": "add_technology",
    "assign": "assign",
    "move": "move",
    "remove_assignment": "remove_assignment",
}


def _apply_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if _RadarProxy is None:
        return {
            "ok": False,
            "stub": True,
            "action": action,
            "note": "RadarProxy not importable — running in stub mode",
        }
    proxy = _RadarProxy()
    try:
        if action in _READ_ACTIONS:
            method = getattr(proxy, _READ_ACTIONS[action])
            result = method(**params)
            return {"ok": True, "action": action, "result": _serialize(result)}
        if action in _WRITE_ACTIONS:
            method = getattr(proxy, _WRITE_ACTIONS[action])
            result = method(**params)
            if proxy.is_dirty:
                proxy.commit(message=f"a2a:{action}")
            return {
                "ok": True,
                "action": action,
                "committed": True,
                "result": _serialize(result),
            }
        return {
            "ok": False,
            "action": action,
            "error": (
                f"unknown action '{action}'. "
                f"Allowed: {sorted(list(_READ_ACTIONS) + list(_WRITE_ACTIONS))}"
            ),
        }
    except ValueError as e:
        # The proxy raises ValueError with a descriptive, model-friendly message.
        return {"ok": False, "action": action, "error": str(e)}
    except TypeError as e:
        return {"ok": False, "action": action, "error": f"bad params: {e}"}


app = FastAPI(
    title="MCP agent (A2A wrapper for exercise-b-mcp)",
    lifespan=make_lifespan(
        registry_url=REGISTRY_URL,
        name=AGENT_NAME,
        capabilities=CAPABILITIES,
        endpoint=AGENT_ENDPOINT,
        health_url=AGENT_HEALTH,
    ),
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "capabilities": CAPABILITIES,
        "radar_backend": "live" if _RadarProxy is not None else "stub",
    }


@app.post("/invoke")
async def invoke(envelope: Envelope) -> Envelope:
    cached = await _idempotency.get(envelope.idempotency_key)
    if cached is not None:
        logger.info(
            "idempotency hit corr=%s key=%s",
            envelope.correlation_id,
            envelope.idempotency_key,
        )
        return Envelope(**cached)

    started = time.time()
    payload = envelope.payload or {}
    action = str(payload.get("action", "")).strip()
    params = payload.get("params") or {}
    if not action:
        reply_payload = {
            "ok": False,
            "error": "payload.action is required (e.g. 'add_technology')",
        }
    elif not isinstance(params, dict):
        reply_payload = {"ok": False, "error": "payload.params must be an object"}
    else:
        reply_payload = _apply_action(action, params)
        reply_payload["elapsed_ms"] = int((time.time() - started) * 1000)

    reply = envelope.reply(reply_payload, sender=AGENT_NAME)
    await _idempotency.put(envelope.idempotency_key, reply.model_dump())
    return reply


__all__ = ["app"]
