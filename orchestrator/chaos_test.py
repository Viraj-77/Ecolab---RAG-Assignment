"""P3.4 chaos test — kill the RAG agent while requests are in flight,
observe what the system does, dump the timeline.

We exercise BOTH failure paths:

(A) graceful death: SIGTERM lets the agent's lifespan run, so it
    deregisters from the registry. The next orchestrator lookup gets an
    empty list and the workflow fast-fails with status=failed and a
    machine-readable error. No retry budget consumed.

(B) sudden death: SIGKILL — the agent has no chance to deregister.
    The registry still lists it for up to TTL seconds. The orchestrator
    looks it up, picks the dead endpoint, hits ConnectionError, retries
    with the same idempotency_key up to MAX_ATTEMPTS, and poisons the
    workflow. Retry budget exhausted, dead-letter row written.

The structured timeline for the SIGKILL path is dumped to
``logs/chaos-trace.txt`` so docs/failure-modes.md can quote it.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
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
    log_path = REPO_ROOT / "logs" / f"chaos-{name}.log"
    log_path.parent.mkdir(exist_ok=True)
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", app_path,
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1",
             "ORCH_CALL_TIMEOUT": "1.5"},  # short timeout so chaos finishes fast
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
            await asyncio.sleep(0.4)
    raise RuntimeError(f"{url} not healthy: {last}")


async def _run() -> dict:
    for url in (REGISTRY_URL, RAG_URL, MCP_URL, ORCH_URL):
        await _wait_healthy(url)
    await asyncio.sleep(0.5)

    print("\n=== chaos test: kill rag-agent mid-flow ===\n")

    # 1. Sanity: a normal read works.
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{ORCH_URL}/request",
                              json={"text": "What is the radar?"})
        baseline = r.json()
    print(f"[baseline] status={baseline['status']} cap={baseline['capability']}")
    assert baseline["status"] == "completed"

    return baseline


def main() -> int:
    for name, _, port in SERVICES:
        if not _port_free(port):
            print(f"port {port} ({name}) busy — run scripts/free-ports.sh", file=sys.stderr)
            return 2

    procs: dict[str, subprocess.Popen] = {}
    chaos_correlation: str | None = None
    try:
        for name, app_path, port in SERVICES:
            print(f"→ launching {name} on :{port}")
            procs[name] = _spawn(name, app_path, port)

        baseline = asyncio.run(_run())

        # ---------- (A) graceful kill: SIGTERM ----------
        print("\n[chaos A] SIGTERM rag-agent (graceful)")
        procs["rag-agent"].send_signal(signal.SIGTERM)
        try:
            procs["rag-agent"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            procs["rag-agent"].kill()
        time.sleep(1.0)  # let the deregister POST land

        async def _fire(text: str) -> dict:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{ORCH_URL}/request", json={"text": text})
                return r.json()

        graceful = asyncio.run(_fire("Explain what just happened."))
        print(f"\n[chaos A] response: status={graceful['status']} "
              f"error={graceful.get('error')}")
        assert graceful["status"] == "failed", graceful
        assert "no agent" in (graceful.get("error") or "").lower(), graceful

        # ---------- (B) sudden death: respawn + SIGKILL, exercise retry/poison ----------
        print("\n[chaos B] respawning rag-agent so we can SIGKILL it")
        procs["rag-agent"] = _spawn("rag-agent", "agents.rag_agent.main:app", 8002)
        asyncio.run(_wait_healthy(RAG_URL))
        print("[chaos B] rag-agent back up — SIGKILL")
        procs["rag-agent"].send_signal(signal.SIGKILL)
        # SIGKILL leaves the registry's record intact (no graceful deregister).
        # Fire IMMEDIATELY so we hit the dead endpoint before TTL sweeps it.
        chaos_resp = asyncio.run(_fire("Tell me about the radar history."))
        chaos_correlation = chaos_resp["correlation_id"]
        print(f"\n[chaos B] orchestrator response after SIGKILL:")
        print(json.dumps(chaos_resp, indent=2))

        # 4. Inspect the workflow row + poison table.
        async def _post_mortem() -> dict:
            async with httpx.AsyncClient(timeout=5.0) as client:
                wf = (await client.get(
                    f"{ORCH_URL}/workflows/{chaos_correlation}"
                )).json()
                poison = (await client.get(f"{ORCH_URL}/poison")).json()
                return {"workflow": wf, "poison": poison}

        post = asyncio.run(_post_mortem())
        print("\n[chaos] workflow row:")
        print(json.dumps(post["workflow"], indent=2)[:600])
        print(f"\n[chaos] poison table size: {len(post['poison'])}")

        # 5. Assertions: the workflow must NOT have silently completed.
        #    With SIGKILL we expect status=poisoned (retry budget exhausted)
        #    in the common case. If the registry's TTL sweeper happened to
        #    evict the dead agent first we see status=failed, which is also
        #    correct behavior — the assertion accepts either.
        assert chaos_resp["status"] in {"poisoned", "failed"}, chaos_resp
        assert post["workflow"]["status"] in {"poisoned", "failed"}, post["workflow"]
        if chaos_resp["status"] == "poisoned":
            assert len(post["poison"]) >= 1, "expected poison row"

        # 6. Dump the structured timeline to a file the docs can quote.
        from observability.query import render_timeline  # type: ignore

        trace_file = REPO_ROOT / "logs" / "chaos-trace.txt"
        with trace_file.open("w") as f:
            old = sys.stdout
            sys.stdout = f
            try:
                render_timeline(chaos_correlation)
            finally:
                sys.stdout = old
        print(f"\n[chaos] structured timeline written to {trace_file}")
        print("\nCHAOS PASS — orchestrator surfaced the failure (no silent loss)")
        return 0
    finally:
        for p in procs.values():
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs.values():
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
