import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .proxy import RadarProxy
from .sandbox import run_execute, run_search

SEARCH_DESCRIPTION = """\
Read the tech radar. Write Python using the `radar` proxy object.

Available types (from Pydantic models):
  Quadrant: 0=Models, 1=Infrastructure, 2=Frameworks, 3=Techniques
  Ring: 0=ADOPT, 1=TRIAL, 2=ASSESS, 3=HOLD
  Moved: -1=down, 0=unchanged, 1=up

Read methods:
  radar.list_technologies(quadrant=None) -> list of Technology
  radar.list_teams() -> list of Team
  radar.list_assignments(team_id) -> list of Assignment
  radar.get_assignment(team_id, tech_id) -> Assignment or None

This tool is READ-ONLY. Calling write methods raises an error.
Use execute() to make changes.
Assign your result to a variable called `result`.
"""

EXECUTE_DESCRIPTION = """\
Read and write the tech radar. Write Python using the `radar` proxy object.

All read methods from search() are available, plus:
  radar.add_technology(id, label, quadrant, link=None) -> Technology
  radar.assign(team_id, tech_id, ring, moved=0) -> Assignment
  radar.move(team_id, tech_id, new_ring) -> Assignment
  radar.remove_assignment(team_id, tech_id) -> None
  radar.commit(message="") -> saves to radar_working.json (no git push)

Errors include valid alternatives - read them carefully before retrying.
Assign your result to a variable called `result`.
"""

server: Server = Server("radar-mcp")


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


@server.list_tools()
async def list_tools() -> list[Tool]:
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python to run against the radar proxy"}
        },
        "required": ["code"],
    }
    return [
        Tool(name="search", description=SEARCH_DESCRIPTION, inputSchema=schema),
        Tool(name="execute", description=EXECUTE_DESCRIPTION, inputSchema=schema),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    code = arguments.get("code", "")
    try:
        if name == "search":
            proxy = RadarProxy()
            result = run_search(code, proxy)
        elif name == "execute":
            result = run_execute(code)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        payload = _to_jsonable(result)
        return [TextContent(type="text", text=json.dumps(payload, default=str))]
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
