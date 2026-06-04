"""Shared agent lifecycle: registry registration, heartbeat, and idempotency LRU.

Person 2 — used by both rag_agent and mcp_agent so the lifecycle plumbing is
implemented once and the agent modules stay focused on business logic.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 10.0
REGISTRY_TIMEOUT_SECONDS = 3.0


class IdempotencyLRU:
    """Bounded LRU cache keyed by ``idempotency_key`` -> cached reply payload.

    The receiver returns the cached envelope if it already processed an
    envelope with the same ``idempotency_key`` — this is the dedupe story
    for the at-least-once retry behavior in ``envelope/client.py``.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._max_size = max_size
        self._cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    async def put(self, key: str, value: dict[str, Any]) -> None:
        async with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)


async def _register(
    registry_url: str,
    name: str,
    capabilities: list[str],
    endpoint: str,
    health_url: str,
) -> None:
    async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{registry_url}/register",
            json={
                "name": name,
                "capabilities": capabilities,
                "endpoint": endpoint,
                "health_url": health_url,
            },
        )
        resp.raise_for_status()
    logger.info("registered %s with capabilities=%s", name, capabilities)


async def _deregister(registry_url: str, name: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_SECONDS) as client:
            await client.delete(f"{registry_url}/deregister/{name}")
        logger.info("deregistered %s", name)
    except Exception as e:
        logger.warning("deregister failed for %s: %s", name, e)


async def _heartbeat_loop(registry_url: str, name: str) -> None:
    while True:
        try:
            async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_SECONDS) as client:
                await client.put(f"{registry_url}/heartbeat/{name}")
        except Exception as e:
            logger.debug("heartbeat for %s failed: %s", name, e)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


def make_lifespan(
    *,
    registry_url: str,
    name: str,
    capabilities: list[str],
    endpoint: str,
    health_url: str,
):
    """Build a FastAPI lifespan that registers, heartbeats, and deregisters."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await _register(registry_url, name, capabilities, endpoint, health_url)
        except Exception as e:
            logger.warning("startup registration failed: %s — agent will keep retrying via heartbeat", e)
        hb_task = asyncio.create_task(_heartbeat_loop(registry_url, name))
        try:
            yield
        finally:
            hb_task.cancel()
            await _deregister(registry_url, name)

    return lifespan


__all__ = ["IdempotencyLRU", "make_lifespan"]
