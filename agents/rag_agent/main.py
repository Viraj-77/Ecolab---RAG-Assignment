"""RAG agent — A2A wrapper around exercise-a-rag.

Capability: ``answer-from-corpus``.
Port: 8002.

The vendored ``exercise-a-rag`` is imported lazily; if its dependencies
(Azure OpenAI key, ChromaDB index) aren't available the agent stays up
and replies with a clearly marked stub. That keeps the A2A plumbing
runnable on a fresh laptop without forcing teammates to provision the
RAG backend before they can exercise the protocol.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI

# Make the vendored exercise-a-rag importable as `src.rag_pipeline`.
_RAG_ROOT = Path(__file__).resolve().parents[2] / "exercise-a-rag"
if str(_RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(_RAG_ROOT))

# Allow the orchestrator/tests to override the registry URL via env.
REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:8000")
AGENT_NAME = "rag-agent"
AGENT_PORT = int(os.environ.get("RAG_AGENT_PORT", "8002"))
AGENT_ENDPOINT = os.environ.get("RAG_AGENT_ENDPOINT", f"http://localhost:{AGENT_PORT}/invoke")
AGENT_HEALTH = os.environ.get("RAG_AGENT_HEALTH", f"http://localhost:{AGENT_PORT}/health")
CAPABILITIES = ["answer-from-corpus"]

from envelope import Envelope  # noqa: E402  (sys.path modified above)
from agents.lifecycle import IdempotencyLRU, make_lifespan  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_idempotency = IdempotencyLRU(max_size=1000)


def _try_load_rag():
    """Best-effort import of the vendored RAG pipeline.

    Returns ``(chat_callable, memory)`` or ``(None, None)`` if the backend
    cannot be initialised on this machine.
    """
    try:
        # These imports require AZURE_OPENAI_API_KEY and a local Chroma index.
        from src.rag_pipeline import chat, SYSTEM_PROMPT  # type: ignore
        from src.conversational_memory import ConversationMemory  # type: ignore

        memory = ConversationMemory(SYSTEM_PROMPT)
        return chat, memory
    except Exception as e:
        logger.warning("RAG backend unavailable, agent will reply with stub answers: %s", e)
        return None, None


_chat, _memory = _try_load_rag()


def _stub_answer(question: str) -> str:
    return (
        "[rag-agent stub] No live RAG backend available in this environment "
        "(Azure OpenAI / ChromaDB not configured). Question received: "
        f"{question!r}"
    )


def _answer_from_corpus(question: str) -> dict[str, Any]:
    started = time.time()
    if _chat is None or _memory is None:
        text = _stub_answer(question)
        backend = "stub"
    else:
        try:
            text = _chat(_memory, question)
            backend = "exercise-a-rag"
        except Exception as e:
            logger.exception("RAG backend raised — falling back to stub")
            text = f"[rag-agent error] {e}"
            backend = "error"
    return {
        "answer": text,
        "backend": backend,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


app = FastAPI(
    title="RAG agent (A2A wrapper for exercise-a-rag)",
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
        "rag_backend": "live" if _chat is not None else "stub",
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

    question = str(envelope.payload.get("question", "")).strip()
    if not question:
        reply_payload = {
            "ok": False,
            "error": "payload.question is required",
        }
    else:
        result = _answer_from_corpus(question)
        reply_payload = {"ok": True, **result}

    reply = envelope.reply(reply_payload, sender=AGENT_NAME)
    await _idempotency.put(envelope.idempotency_key, reply.model_dump())
    return reply


__all__ = ["app"]
