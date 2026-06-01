# Person 1 — The Builder

## Your job in one sentence
You build the MCP server — the program that lets Claude read and edit the tech radar.

## Tech stack you are using
- **Python 3.11**
- **`mcp` library** — the official Python MCP SDK
- **Pydantic v2** — for data models and validation
- **`RestrictedPython`** — for safe code execution in the sandbox

## What you're building
A Python program that:
- Reads `docs/config.json` once on startup as a **reference copy**
- Creates a **working copy** at `mcp-server/radar_working.json` (this is what the server actually reads and writes — the original `docs/config.json` is never touched)
- Lets Claude add technologies, assign them to teams, move them between rings
- Validates every change (e.g. you can't skip from ADOPT to HOLD in one step)
- Writes changes only to `radar_working.json`

The whole server exposes only **2 tools** to Claude: `search` (read-only) and `execute` (read + write). All the domain logic lives inside a `RadarProxy` class.

---

## Files you will create

```
mcp-server/
├── pyproject.toml         ← Python project config
├── radar_working.json     ← working copy (auto-created from docs/config.json)
└── src/
    ├── types.py           ← Pydantic models (do this first, commit immediately)
    ├── radar_store.py     ← load docs/config.json, save radar_working.json
    ├── validators.py      ← rules that prevent bad edits
    ├── proxy.py           ← the RadarProxy class (main logic)
    ├── sandbox.py         ← safe code runner using RestrictedPython
    └── server.py          ← the MCP server entry point
```

---

## Step-by-step with Claude Code prompts

### Step 1 — Set up the project

Give this to Claude Code:
```
Create a new folder called mcp-server inside this repo.
Inside it, create a pyproject.toml for Python 3.11 with these dependencies:
- mcp (the official Python MCP SDK from Anthropic)
- pydantic (v2)
- RestrictedPython

Also create an empty src/ folder with an __init__.py file.
Do not install anything yet, just create the files.
```

---

### Step 2 — Write the types (do this FIRST, commit immediately)

Give this to Claude Code:
```
In mcp-server/src/types.py, write Pydantic v2 models for the tech radar.

Use these exact definitions:

from pydantic import BaseModel
from typing import Literal, Optional

Quadrant = Literal[0, 1, 2, 3]
# 0 = Models & Providers
# 1 = Infrastructure & Cloud
# 2 = Frameworks & Libraries
# 3 = Techniques & Patterns

Ring = Literal[0, 1, 2, 3]
# 0 = ADOPT, 1 = TRIAL, 2 = ASSESS, 3 = HOLD

Moved = Literal[-1, 0, 1]

class Technology(BaseModel):
    id: str           # kebab-case, unique
    label: str        # human-readable name
    quadrant: Quadrant
    link: Optional[str] = None   # required for ADOPT ring

class Team(BaseModel):
    id: str
    name: str
    date: str         # "YYYY.MM"

class Assignment(BaseModel):
    tech: str         # references Technology.id
    ring: Ring
    moved: Moved

class Radar(BaseModel):
    date: str
    default_team: str
    teams: list[Team]
    technologies: list[Technology]
    assignments: dict[str, list[Assignment]]   # team id → list of assignments
```

**After this step: tell your teammates "types.py is committed" so they can start working.**

---

### Step 3 — Write the radar store

Give this to Claude Code:
```
In mcp-server/src/radar_store.py, write these functions:

1. load_radar() -> Radar
   - Checks if mcp-server/radar_working.json exists
   - If it does NOT exist: copies docs/config.json to mcp-server/radar_working.json, then reads it
   - If it DOES exist: reads mcp-server/radar_working.json directly
   - Returns a Radar Pydantic object

2. save_radar(radar: Radar) -> None
   - Writes the Radar object to mcp-server/radar_working.json as formatted JSON (indent=2)
   - NEVER writes to docs/config.json

The path to docs/config.json must be resolved relative to the repo root (two levels up from mcp-server/src/).
Print a message to stderr when the working copy is first created: "Created radar_working.json from docs/config.json"
```

---

### Step 4 — Write the validators

Give this to Claude Code:
```
In mcp-server/src/validators.py, write these validation functions.
Each must raise a ValueError with a helpful message that tells the caller what to do instead.

1. assert_tech_exists(radar: Radar, tech_id: str) -> None
   - Raises if tech_id is not in radar.technologies
   - Error message: f"Tech '{tech_id}' not found in radar. Did you mean one of: {similar_ids}?"
   - List up to 5 existing ids in the error

2. assert_not_duplicate(radar: Radar, team_id: str, tech_id: str) -> None
   - Raises if the team already has an assignment for that tech
   - Error message must say the current ring name and suggest using radar.move() instead
   - Example: "claude-haiku-4-5-databricks is already assigned to commercial (ring: TRIAL). Use radar.move('commercial', 'claude-haiku-4-5-databricks', 0) to promote it to ADOPT."

3. assert_legal_ring_transition(from_ring: int, to_ring: int) -> None
   - Raises if jumping from ring 0 (ADOPT) directly to ring 3 (HOLD) or vice versa
   - Error message: "Cannot move from ADOPT to HOLD in one step. Allowed intermediate rings: TRIAL (1) or ASSESS (2)."

4. assert_adopt_has_link(tech: Technology, ring: int) -> None
   - Raises if ring is 0 (ADOPT) and tech.link is None
   - Error message: f"Tech '{tech.id}' cannot be set to ADOPT without a link. Add a link field first: e.g. radar.update_technology('{tech.id}', link='https://...')"

5. assert_single_default(radar: Radar) -> None
   - Raises if radar.default_team does not match any team id
   - Error message lists the available team ids
```

---

### Step 5 — Write the proxy

Give this to Claude Code:
```
In mcp-server/src/proxy.py, write a class called RadarProxy.
It loads the radar from radar_store.load_radar() on __init__.

Read methods (safe for both search and execute):
- list_technologies(quadrant: int | None = None) -> list[Technology]
- list_teams() -> list[Team]
- list_assignments(team_id: str) -> list[Assignment]
- get_assignment(team_id: str, tech_id: str) -> Assignment | None

Write methods (only for execute):
- add_technology(id: str, label: str, quadrant: int, link: str | None = None) -> Technology
- assign(team_id: str, tech_id: str, ring: int, moved: int = 0) -> Assignment
- move(team_id: str, tech_id: str, new_ring: int) -> Assignment
- remove_assignment(team_id: str, tech_id: str) -> None

Persistence:
- commit(message: str = "") -> None
  Calls save_radar() to write mcp-server/radar_working.json.
  Prints the message to stderr. Does NOT run git commands.

Every write method must call the relevant validators before making any change.
If a validator raises, re-raise the same ValueError unchanged.

Track whether any writes have happened with a self._dirty flag.
Add a property is_dirty -> bool.
```

---

### Step 6 — Write the sandbox

Give this to Claude Code:
```
In mcp-server/src/sandbox.py, write two functions using RestrictedPython.

1. run_search(code: str, radar_instance: RadarProxy) -> any
   - Creates a restricted execution environment
   - Exposes a read-only view: radar object has only read methods
   - Write methods (assign, move, add_technology, remove_assignment, commit) are NOT available
   - If code tries to call a write method, raises: ValueError("search is read-only. Use execute() to make changes.")
   - Runs the code and returns the value of the last expression or a variable called 'result'

2. run_execute(code: str) -> any
   - Creates a fresh RadarProxy instance
   - Exposes the full proxy as 'radar' in the execution context
   - Runs the code and returns the result
   - After running: if radar.is_dirty is True, auto-calls radar.commit()

Both functions must:
- Set a timeout of 5 seconds
- Catch all exceptions and re-raise as ValueError with the original message preserved
- Never expose Python builtins that could harm the filesystem (open, exec, import, etc.)
```

---

### Step 7 — Write the MCP server entry point

Give this to Claude Code:
```
In mcp-server/src/server.py, create a Python MCP server using the mcp library.
Use stdio transport.

Register exactly 2 tools:

Tool 1: "search"
Description — include this verbatim:
"""
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
Parameter: code (string) — Python to run against the radar proxy

Tool 2: "execute"
Description — include this verbatim:
"""
Read and write the tech radar. Write Python using the `radar` proxy object.

All read methods from search() are available, plus:
  radar.add_technology(id, label, quadrant, link=None) -> Technology
  radar.assign(team_id, tech_id, ring, moved=0) -> Assignment
  radar.move(team_id, tech_id, new_ring) -> Assignment
  radar.remove_assignment(team_id, tech_id) -> None
  radar.commit(message="") -> saves to radar_working.json (no git push)

Errors include valid alternatives — read them carefully before retrying.
Assign your result to a variable called `result`.
"""
Parameter: code (string) — Python to run against the radar proxy

Wire the tools to run_search() and run_execute() from sandbox.py.
Return results as JSON strings. If a ValueError is raised, return the error message as a string (do not crash the server).
```

**After this step: tell your teammates "server is runnable" and give them the run command.**

---

## Run command to share with teammates

```bash
cd mcp-server
pip install -e .
python src/server.py
```

Or with uv (if available):
```bash
cd mcp-server
uv run src/server.py
```

---

## When you're done
- Tell Person 2 the server is running so they can start testing
- Stay available to fix bugs — they will send you the exact failing input
- Make sure `radar_working.json` is in `.gitignore` (it's a working file, not a deliverable)
