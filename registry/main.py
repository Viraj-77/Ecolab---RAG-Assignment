"""Agent registry — register/deregister/query-by-capability/health + TTL heartbeat."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

HEARTBEAT_TTL_SECONDS = 30.0
SWEEP_INTERVAL_SECONDS = 10.0


class AgentRecord(BaseModel):
    name: str
    capabilities: list[str]
    endpoint: str
    health_url: str
    last_heartbeat: float = Field(default_factory=time.time)


class RegisterRequest(BaseModel):
    name: str
    capabilities: list[str]
    endpoint: str
    health_url: str


_agents: dict[str, AgentRecord] = {}
_sweeper_task: Optional[asyncio.Task] = None


async def _sweep_loop() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        cutoff = time.time() - HEARTBEAT_TTL_SECONDS
        stale = [n for n, r in _agents.items() if r.last_heartbeat < cutoff]
        for name in stale:
            _agents.pop(name, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sweeper_task
    _sweeper_task = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        _sweeper_task.cancel()


app = FastAPI(title="A2A Agent Registry", lifespan=lifespan)


@app.post("/register")
def register(req: RegisterRequest) -> AgentRecord:
    record = AgentRecord(**req.model_dump())
    _agents[req.name] = record
    return record


@app.delete("/deregister/{name}")
def deregister(name: str) -> dict:
    if name not in _agents:
        raise HTTPException(status_code=404, detail=f"agent '{name}' not registered")
    _agents.pop(name)
    return {"deregistered": name}


@app.put("/heartbeat/{name}")
def heartbeat(name: str) -> dict:
    if name not in _agents:
        raise HTTPException(status_code=404, detail=f"agent '{name}' not registered")
    _agents[name].last_heartbeat = time.time()
    return {"name": name, "ts": _agents[name].last_heartbeat}


@app.get("/agents")
def list_agents(capability: Optional[str] = None) -> list[AgentRecord]:
    if capability is None:
        return list(_agents.values())
    return [r for r in _agents.values() if capability in r.capabilities]


@app.get("/health")
def health() -> dict:
    now = time.time()
    return {
        "status": "ok",
        "agent_count": len(_agents),
        "agents": [
            {
                "name": r.name,
                "capabilities": r.capabilities,
                "stale_seconds": round(now - r.last_heartbeat, 2),
                "alive": (now - r.last_heartbeat) < HEARTBEAT_TTL_SECONDS,
            }
            for r in _agents.values()
        ],
    }
