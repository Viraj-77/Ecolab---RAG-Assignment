"""Person 2 test harness — drives the radar MCP server over stdio.

Substitutes for MCP Inspector (no Node available locally). Uses the official
mcp Python SDK to spawn `python -m src.server` as a subprocess, list tools,
and call search/execute. Each test prints a section header so the output can
be sliced into docs/raw-traces.txt.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent
SERVER_DIR = REPO_ROOT / "mcp-server"


def header(label: str) -> None:
    print()
    print(f"=== {label} ===")


def dump(obj) -> None:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    print(json.dumps(obj, indent=2, default=str))


async def call(session: ClientSession, tool: str, code: str) -> str:
    res = await session.call_tool(tool, arguments={"code": code})
    parts = []
    for c in res.content:
        if hasattr(c, "text"):
            parts.append(c.text)
        else:
            parts.append(str(c))
    return "\n".join(parts)


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.server"],
        env={**os.environ, "PYTHONPATH": str(SERVER_DIR)},
        cwd=str(SERVER_DIR),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            header("INIT")
            print(f"server name: {init.serverInfo.name}")
            print(f"server version: {init.serverInfo.version}")
            print(f"protocol version: {init.protocolVersion}")

            # ---- SMOKE TEST 1: list tools ----
            header("SMOKE TEST 1: Server starts — 2 tools visible")
            tools = await session.list_tools()
            for t in tools.tools:
                print(f"- {t.name}")
                print(f"  inputSchema keys: {list(t.inputSchema.get('properties', {}).keys())}")
                # show description first 200 chars
                desc = t.description or ""
                print(f"  description (first 240 chars):\n    " + desc[:240].replace("\n", "\n    "))
            assert {t.name for t in tools.tools} == {"search", "execute"}, "Expected exactly search + execute"
            print("PASS: exactly 2 tools — search + execute")

            # ---- SMOKE TEST 2: search reads teams ----
            header("SMOKE TEST 2: search reads teams")
            print(">> search code:")
            code = "result = radar.list_teams()"
            print(code)
            print(">> response:")
            print(await call(session, "search", code))

            # ---- SMOKE TEST 3: working copy is separate from source ----
            header("SMOKE TEST 3: radar_working.json is separate from ecolab-radar-config.json")
            working = REPO_ROOT / "mcp-server" / "radar_working.json"
            source = REPO_ROOT / "ecolab-radar-config.json"
            print(f"working copy exists: {working.exists()}  ({working})")
            print(f"source exists:       {source.exists()}  ({source})")
            if working.exists():
                src_bytes = source.read_bytes()
                wrk_bytes = working.read_bytes()
                print(f"source size:  {len(src_bytes)} bytes")
                print(f"working size: {len(wrk_bytes)} bytes")
                # Compare content semantically (server load+save reformats JSON)
                src_data = json.loads(src_bytes)
                wrk_data = json.loads(wrk_bytes)
                if src_data == wrk_data:
                    print("PASS: working copy content matches source (semantic equality)")
                else:
                    same_teams = [t["id"] for t in src_data["teams"]] == [t["id"] for t in wrk_data["teams"]]
                    print(f"NOTE: working copy differs from source. teams identical: {same_teams}")

            # ---- MISUSE TEST 1: non-existent tech ----
            header("MISUSE TEST 1: Non-existent tech id")
            code = "result = radar.assign('llm-capability-office', 'gpt-5-nano', 1)"
            print(">> execute code:")
            print(code)
            print(">> response:")
            print(await call(session, "execute", code))

            # ---- MISUSE TEST 2: duplicate assignment ----
            # claude-opus-4-7-azure-ai-foundry is already ADOPT for llm-capability-office
            header("MISUSE TEST 2: Duplicate assignment")
            code = (
                "result = radar.assign("
                "'llm-capability-office', 'claude-opus-4-7-azure-ai-foundry', 2)"
            )
            print(">> execute code:")
            print(code)
            print(">> response:")
            print(await call(session, "execute", code))

            # ---- MISUSE TEST 3: ADOPT -> HOLD skip ----
            # claude-opus-4-7-azure-ai-foundry is in ring 0 (ADOPT) for llm-capability-office.
            header("MISUSE TEST 3: ADOPT to HOLD skip")
            code = (
                "result = radar.move("
                "'llm-capability-office', 'claude-opus-4-7-azure-ai-foundry', 3)"
            )
            print(">> execute code:")
            print(code)
            print(">> response:")
            print(await call(session, "execute", code))

            # ---- WORKFLOW TEST: add + assign + commit + read in one call ----
            header("WORKFLOW TEST: Add + assign in one execute() call")
            code = (
                "new_tech = radar.add_technology(\n"
                "    id='test-smoke-tech',\n"
                "    label='Smoke Test Technology',\n"
                "    quadrant=2,\n"
                "    link='https://example.com/smoke'\n"
                ")\n"
                "radar.assign('llm-capability-office', new_tech.id, 1, 1)\n"
                "radar.commit('test: smoke test add and assign')\n"
                "result = radar.get_assignment('llm-capability-office', new_tech.id)\n"
            )
            print(">> execute code:")
            print(code)
            print(">> response:")
            print(await call(session, "execute", code))


if __name__ == "__main__":
    asyncio.run(main())
