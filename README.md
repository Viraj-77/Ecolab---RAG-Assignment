# Take-Home B — Code-Mode MCP Server (Variant 2: Tech Radar)

A token-efficient MCP server for the Ecolab **Stack.TechRadar**. Replaces the
naive 7-tool surface with two tools — `search` and `execute` — backed by a
Python `RadarProxy` running inside a `RestrictedPython` sandbox.

## Variant chosen

**Variant 2 — Domain-Specific Constrained Metamodel.** The radar has a fixed
metamodel (4 quadrants × 4 rings × `Moved ∈ {-1, 0, 1}`) and hard validation
rules (no duplicate `(team, tech)` assignments, ADOPT requires a `link`, no
direct ADOPT↔HOLD transitions, exactly one `default_team`). A naive N-tool
design repeats the Quadrant/Ring enums in every schema (the schema-bloat
tax); Code Mode prints the metamodel once in a Pydantic-shaped DSL block and
lets the model script the proxy.

## Proxy interface (TypeScript shape — implemented in Python/Pydantic)

```typescript
interface RadarProxy {
  // Reads (available in both search and execute)
  list_technologies(quadrant?: Quadrant): Technology[]
  list_teams(): Team[]
  list_assignments(team_id: string): Assignment[]
  get_assignment(team_id: string, tech_id: string): Assignment | undefined

  // Writes (execute-only; search wraps the proxy in _ReadOnlyRadar)
  add_technology(id: string, label: string, quadrant: Quadrant, link?: string): Technology
  assign(team_id: string, tech_id: string, ring: Ring, moved?: Moved): Assignment
  move(team_id: string, tech_id: string, new_ring: Ring): Assignment
  remove_assignment(team_id: string, tech_id: string): void

  // Persistence
  commit(message?: string): void   // writes radar_working.json; does not push to main
}
```

The Python implementation lives in `mcp-server/src/proxy.py`. The Pydantic
models (`Quadrant`, `Ring`, `Moved`, `Technology`, `Team`, `Assignment`,
`Radar`) are in `mcp-server/src/types.py` and are the single source of truth
for the on-disk schema, the runtime types, and the DSL bootstrap.

## Setup & run

```bash
# 1. Install
cd mcp-server
pip install -e .

# 2. Run the server (stdio MCP transport)
python -m src.server

# 3. Drive it from a host
#    - Claude Code / Cursor: register a stdio MCP server with the command above.
#    - Or run the bundled harness (substitutes for MCP Inspector when Node
#      is unavailable):
cd ..
python test_harness.py
```

The first invocation copies `ecolab-radar-config.json` to
`mcp-server/radar_working.json`. All `commit()` calls write the working copy
only — the source-of-truth file is never modified. To reset, delete the
working copy.

## Token measurement (`tiktoken` cl100k_base)

```bash
cd Deliverables
python3 count_baseline.py    # naive 7-tool surface
python3 count_after.py       # search + execute
python3 count_workflow.py    # multi-step workflow runtime cost
```

| Surface | Bootstrap tokens |
|---|---|
| **N-tool baseline** (`add_technology`, `remove_technology`, `assign`, `move`, `remove_assignment`, `list_assignments`, `validate`) | **1,300** |
| **Code Mode** (`search` + `execute`, DSL block in description) | **485** |
| **Δ** | **−815 tokens (≈ 63% reduction)** |

A representative multi-step workflow (add a tech → assign it → fetch the
assignment) goes from 3 N-tool round-trips to 1 `execute()` call; see
`Deliverables/count_workflow.py` for the runtime delta.

## Evaluation scorecard

| Dimension | Current state | Target state | Score |
|---|---|---|---|
| Tool count | 2 (`search`, `execute`) | ≤ 2–5 | **3** |
| Bootstrap token cost | 485 | < 1,000 | **3** |
| Metamodel location | DSL block + Pydantic on the server | DSL types or server-side | **3** |
| Credential exposure | None held; local file only | Server-internal | **3** |
| Multi-step workflows | One `execute()` runs read→transform→write inline | Single `execute()` | **3** |
| Validation error quality | Structured errors with `get_close_matches` suggestions and recommended next call | Includes valid alternatives | **2** |
| Result verbosity control | Model picks the projection inside the sandbox; only `result` returns | Model controls projection | **2** |

**Total: 19 / 21.** Two `2`s reflect honest gaps: the validation messages
spell out the corrective call for some misuses but not all, and result
projection is available but the description doesn't push the model to use
it on every read. Both are visible in the worked traces.

## Deliverables map

| Spec deliverable | Location |
|---|---|
| MCP server source | `mcp-server/` |
| Proxy interface (this README) | top of this file |
| Setup/run steps | this README |
| Before/after token numbers + tiktoken snippet | `Deliverables/count_baseline.py`, `count_after.py`, `count_workflow.py` |
| Filled scorecard | this README |
| `docs/proxy-design.md` | `Deliverables/proxy-design.md` (also `docs/proxy-design.md`) |
| `docs/sandbox-choice.md` | `Deliverables/sandbox-choice.md` (also `docs/sandbox-choice.md`) |
| Self-correcting validation trace | `Deliverables/trace-self-correcting.md` (also `docs/trace-self-correcting.md`) |
| Multi-step workflow trace | `docs/raw-traces.txt` (workflow W1) + `Deliverables/count_workflow.py` |
| N-tool baseline (BEFORE) | `Deliverables/baseline-n-tool.md` |

## Sandbox choice

`RestrictedPython` with a 5-second `SIGALRM` timeout. `search` runs against
a `_ReadOnlyRadar` wrapper that raises on any write call; `execute` exposes
the full proxy and auto-commits if the proxy is dirty. Full defence in
`Deliverables/sandbox-choice.md`.

## Non-goals (per spec)

No production deploy, no MCP-client auth, no multi-tenant credential
isolation, and `commit()` writes the working copy only — pushes to the
canonical radar repo are a deliberate human PR step.
