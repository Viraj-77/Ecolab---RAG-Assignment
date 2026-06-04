"""P2.3 smoke test — boots registry + rag-agent + mcp-agent, round-trips one
envelope to each, asserts the registry shows both agents.

Usage (from repo root):
    python -m agents.smoke_test

Exits 0 on success, non-zero on any failed assertion. Prints a compact log
of what was sent and what came back so a teammate can verify visually.
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
REGISTRY_URL = "http://localhost:8000"
RAG_URL = "http://localhost:8002"
MCP_URL = "http://localhost:8003"

SERVICES = [
    ("registry", "registry.main:app", 8000),
    ("rag-agent", "agents.rag_agent.main:app", 8002),
    ("mcp-agent", "agents.mcp_agent.main:app", 8003),
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
    log_path = REPO_ROOT / "logs" / f"smoke-{name}.log"
    log_path.parent.mkdir(exist_ok=True)
    log_file = log_path.open("w")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            app_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc


async def _wait_healthy(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(f"{url}/health")
                if resp.status_code == 200:
                    return
            except Exception as e:
                last_err = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"service at {url} did not become healthy: {last_err}")


async def _smoke_rag() -> dict:
    from envelope import Envelope  # local import after spawning

    env = Envelope(
        sender="smoke-test",
        recipient="rag-agent",
        capability="answer-from-corpus",
        payload={"question": "What is the Tech Radar?"},
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{RAG_URL}/invoke", json=env.model_dump())
        resp.raise_for_status()
        return resp.json()


async def _smoke_mcp() -> dict:
    from envelope import Envelope

    env = Envelope(
        sender="smoke-test",
        recipient="mcp-agent",
        capability="propose-radar-change",
        payload={"action": "list_technologies", "params": {}},
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{MCP_URL}/invoke", json=env.model_dump())
        resp.raise_for_status()
        return resp.json()


async def _check_registry_lists_both() -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{REGISTRY_URL}/agents")
        resp.raise_for_status()
        return resp.json()


async def _run_assertions() -> int:
    print("→ checking registry lists both agents")
    agents = await _check_registry_lists_both()
    names = {a["name"] for a in agents}
    assert "rag-agent" in names, f"rag-agent not registered. Got: {names}"
    assert "mcp-agent" in names, f"mcp-agent not registered. Got: {names}"
    print(f"  ok — registry sees {sorted(names)}")

    print("→ round-tripping envelope to rag-agent")
    rag_reply = await _smoke_rag()
    print("  reply:", json.dumps(rag_reply, indent=2)[:500])
    assert rag_reply["sender"] == "rag-agent"
    assert rag_reply["capability"] == "answer-from-corpus"
    assert "ok" in rag_reply["payload"]
    assert rag_reply["causation_id"] is not None

    print("→ round-tripping envelope to mcp-agent")
    mcp_reply = await _smoke_mcp()
    print("  reply:", json.dumps(mcp_reply, indent=2)[:500])
    assert mcp_reply["sender"] == "mcp-agent"
    assert mcp_reply["capability"] == "propose-radar-change"
    assert "ok" in mcp_reply["payload"]
    assert mcp_reply["causation_id"] is not None

    print("\nSMOKE PASS — registry + rag-agent + mcp-agent round-trip works")
    return 0


def main() -> int:
    for name, _, port in SERVICES:
        if not _port_free(port):
            print(
                f"port {port} ({name}) is in use — run scripts/free-ports.sh and retry",
                file=sys.stderr,
            )
            return 2

    procs: list[subprocess.Popen] = []
    try:
        for name, app_path, port in SERVICES:
            print(f"→ launching {name} on :{port}")
            procs.append(_spawn(name, app_path, port))

        async def _go() -> int:
            for url in (REGISTRY_URL, RAG_URL, MCP_URL):
                await _wait_healthy(url)
            # heartbeat needs a moment to land before the registry sweep is
            # populated; the registration POST is synchronous so this is
            # really just a paranoia delay.
            await asyncio.sleep(0.5)
            return await _run_assertions()

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
