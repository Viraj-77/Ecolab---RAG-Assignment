"""Shared HTTP client for sending envelopes between agents."""
from __future__ import annotations

import httpx

from . import Envelope


class A2AClient:
    """Sends envelopes over HTTP. Retries once on timeout, reusing the idempotency_key."""

    def __init__(self, timeout: float = 5.0, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries

    async def send(self, envelope: Envelope, endpoint: str) -> Envelope:
        """POST envelope to ``endpoint``; return the reply envelope.

        On timeout, retries up to ``max_retries`` times with the SAME envelope (so the
        receiver can dedupe via ``idempotency_key``). Other errors propagate.
        """
        attempts = 0
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while attempts <= self.max_retries:
                try:
                    resp = await client.post(endpoint, json=envelope.model_dump())
                    resp.raise_for_status()
                    return Envelope(**resp.json())
                except httpx.TimeoutException as e:
                    last_exc = e
                    attempts += 1
        assert last_exc is not None
        raise last_exc


__all__ = ["A2AClient"]
