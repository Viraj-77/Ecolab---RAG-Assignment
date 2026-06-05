"""End-to-end happy-path test for the orchestrator.

Boots registry + rag-agent + mcp-agent + orchestrator, fires three requests:
  1. A read ("What is the Tech Radar?") — should hit rag-agent.
  2. An explicit write (action=add_technology) — should hit mcp-agent.
  3. A retry-with-idempotency check — fires the same explicit envelope twice
     directly at the rag-agent and asserts the cached reply is returned.

Exits 0 on success. Useful as a Person 3 regression check before chaos.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_URL = "http://localhost:8001"
REGISTRY_URL = "http://localhost:8000"
RAG_URL = "http://localhost:8002"
MCP_URL = "http://localhost:8003"

SERVICES = [
    ("registry", "registry.main:app", 8000),
    ("rag-agent", "agents.rag_agent.main:app", 8002),
    ("mcp-agent", "agents.mcp_agent.main:app", 8003),
    ("orchestrator", "orchestrator.main:app", 8001),
]


def _port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _spawn(name: str, app_path: str, port: int) -> subprocess.Popen:
    log_path = REPO_ROOT / "logs" / f"e2e-{name}.log"
    log_path.parent.mkdir(exist_ok=True)
    log_file = log_path.open("w")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", app_path,
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


async def _wait_healthy(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() < deadline:
            try:
                r = await client.get(f"{url}/health")
                if r.status_code == 200:
                    return
            except Exception as e:
                last = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"{url} not healthy: {last}")


async def _post_request(text: str, action: str | None = None,
                        params: dict | None = None) -> dict:
    body: dict = {"text": text}
    if action:
        body["action"] = action
        body["params"] = params or {}
    timeout = float(os.environ.get("E2E_HTTP_TIMEOUT", "120"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{ORCH_URL}/request", json=body)
        r.raise_for_status()
        return r.json()


async def _idempotency_check() -> bool:
    """Fire the same envelope twice at the rag-agent; reply payload must be
    byte-identical (the second call should be served from the LRU)."""
    from envelope import Envelope

    env = Envelope(
        sender="e2e",
        recipient="rag-agent",
        capability="answer-from-corpus",
        payload={"question": "idempotency probe"},
    )
    async with httpx.AsyncClient(timeout=float(os.environ.get("E2E_HTTP_TIMEOUT", "120"))) as client:
        r1 = await client.post(f"{RAG_URL}/invoke", json=env.model_dump())
        r1.raise_for_status()
        r2 = await client.post(f"{RAG_URL}/invoke", json=env.model_dump())
        r2.raise_for_status()
    p1 = r1.json()["payload"]
    p2 = r2.json()["payload"]
    return p1 == p2


async def _go() -> int:
    for url in (REGISTRY_URL, RAG_URL, MCP_URL, ORCH_URL):
        await _wait_healthy(url)
    await asyncio.sleep(0.5)

    print("\n→ READ request")
    read = await _post_request("What is the Tech Radar?")
    print(json.dumps(read, indent=2)[:400])
    assert read["status"] == "completed", read
    assert read["capability"] == "answer-from-corpus", read

    print("\n→ WRITE request (explicit action)")
    write = await _post_request(
        "add gemma3 to TRIAL",
        action="add_technology",
        params={
            "id": "gemma3-orchestrator-e2e",
            "label": "Gemma 3 (e2e probe)",
            "quadrant": 0,
            "link": "https://example.invalid/gemma",
        },
    )
    print(json.dumps(write, indent=2)[:400])
    # If the tech already exists from an earlier run the proxy returns ok=False;
    # both states are valid for this assertion — the workflow completes either way.
    assert write["status"] == "completed", write
    assert write["capability"] == "propose-radar-change", write

    print("\n→ idempotency probe at rag-agent")
    same = await _idempotency_check()
    print("payloads match:", same)
    assert same, "rag-agent did not dedupe identical idempotency_key"

    print("\nE2E PASS — orchestrator routes read/write and idempotency holds")
    return 0


def main() -> int:
    for name, _, port in SERVICES:
        if not _port_free(port):
            print(f"port {port} ({name}) busy — run scripts/free-ports.sh", file=sys.stderr)
            return 2
    procs: list[subprocess.Popen] = []
    try:
        for name, app_path, port in SERVICES:
            print(f"→ launching {name} on :{port}")
            procs.append(_spawn(name, app_path, port))
        return asyncio.run(_go())
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
