# Person 1 (Builder) — Plan

Variant 2 (Tech Radar). Build a Python MCP server exposing only `search` and `execute` tools backed by a `RadarProxy`.

## Source-of-truth file
`ecolab-radar-config.json` (repo root) — used as the read-only reference. The server creates `mcp-server/radar_working.json` from it on first run and only ever writes to the working copy.

## Files to build (in order)
1. `mcp-server/pyproject.toml` + `mcp-server/src/__init__.py` — Python 3.11, deps: `mcp`, `pydantic>=2`, `RestrictedPython`.
2. `src/types.py` — Pydantic v2 models: `Quadrant`, `Ring`, `Moved`, `Technology`, `Team`, `Assignment`, `Radar`. **Commit immediately and tell teammates.**
3. `src/radar_store.py` — `load_radar()` (copies `ecolab-radar-config.json` → `radar_working.json` if missing, then reads working copy), `save_radar()` (writes working copy only, never the source).
4. `src/validators.py` — 5 functions, each raising `ValueError` with self-correcting messages:
   - `assert_tech_exists`
   - `assert_not_duplicate`
   - `assert_legal_ring_transition` (no ADOPT↔HOLD direct jump)
   - `assert_adopt_has_link`
   - `assert_single_default`
5. `src/proxy.py` — `RadarProxy` with read methods (`list_technologies`, `list_teams`, `list_assignments`, `get_assignment`), write methods (`add_technology`, `assign`, `move`, `remove_assignment`), `commit(message)`, `is_dirty`.
6. `src/sandbox.py` — `run_search(code, proxy)` (read-only view, blocks writes) and `run_execute(code)` (full proxy, auto-commits if dirty). RestrictedPython, 5s timeout, no `open/exec/import`.
7. `src/server.py` — official `mcp` SDK over stdio, registers exactly two tools `search` and `execute` with the verbatim descriptions from `person1-coder.md`.
8. `.gitignore` — add `radar_working.json`.

## Handoff
- After step 2: notify teammates "types.py committed".
- After step 7: share run command — `cd mcp-server && pip install -e . && python src/server.py`.
