# Person 2 — The Tester

## Your job in one sentence
You connect to Person 1's server, deliberately try to break it, and save all the output so Person 3 can write the docs.

## What you're doing
- Setting up MCP Inspector (a tool that talks to MCP servers)
- Running test scenarios against the running server (Python 3.11)
- Saving the terminal output into `docs/raw-traces.txt`
- Telling Person 1 about any bugs you find
- Telling Person 3 when your traces are ready

You do NOT write code. You do NOT write docs. Your job is to generate the evidence that the server works.

> **Important**: The server reads from and writes to `mcp-server/radar_working.json` — a working copy of `docs/config.json`. The original `docs/config.json` is never touched.

---

## Before Person 1 is done — things you can do now

### While waiting for the server

Give this to Claude Code:
```
Read docs/config.json and architecture/all_teams.md.
Give me a list of:
1. Five technology ids that exist in the radar (I'll use these in valid test cases)
2. Three technology ids that do NOT exist anywhere (I'll use these to trigger "not found" errors)
3. One example of a team id that has a technology in ring 0 (ADOPT)
4. One example of a team id that has a technology in ring 1 (TRIAL)
5. The id of the default_team

Format as a simple copy-paste list.
```

Save this — you will need it for every test.

---

## When Person 1 says "server is runnable"

### Step 0 — Get the server running locally

```bash
cd mcp-server
pip install -e .
python src/server.py
```

Or with uv:
```bash
cd mcp-server
uv run src/server.py
```

The server should start and wait (no output is normal — it's listening on stdio).

---

### Step 1 — Set up MCP Inspector

Give this to Claude Code:
```
How do I connect MCP Inspector to a local Python MCP server that communicates over stdio?
The server is started with: python mcp-server/src/server.py
Give me the exact steps to install and open MCP Inspector and connect it to this server.
```

---

### Step 2 — Smoke Test 1: Does the server start and show 2 tools?

In MCP Inspector, after connecting:

Give this to Claude Code:
```
I have MCP Inspector connected to the server.
Tell me: how many tools are visible, and what are their names?
Expected answer: exactly 2 tools — "search" and "execute".
```

Save the output.

---

### Step 3 — Smoke Test 2: Basic read works

Give this to Claude Code (through MCP Inspector or Claude Code's MCP tool):
```
Call the search tool with this code:
  result = radar.list_teams()

What comes back? I expect a list of team objects with id and name fields.
Copy the full output.
```

Save the output.

---

### Step 4 — Smoke Test 3: Check working copy is separate from original

Give this to Claude Code:
```
After the server has started, check if the file mcp-server/radar_working.json exists.
If it does, confirm it has the same content as docs/config.json.
This is the working copy the server reads and writes to — the original must never be changed.
```

Save the output.

---

### Step 5 — Misuse Test 1: Assign a tech that doesn't exist

Give this to Claude Code:
```
Call the execute tool with this Python code:
  result = radar.assign('llm-capability-office', 'gpt-5-nano', 1)

Note: 'gpt-5-nano' does NOT exist in the radar.
I expect an error message that:
1. Says the tech was not found
2. Lists some valid tech ids I could use instead
Copy the exact error message that comes back.
```

Save the output.

---

### Step 6 — Misuse Test 2: Assign the same tech twice to the same team

Use the prep list from the start — find a team + tech that already has an assignment.

Give this to Claude Code:
```
Call the execute tool with this Python code:
  result = radar.assign('[team-id]', '[tech-already-assigned-to-that-team]', 2)

Replace with real values from the radar. This tech is already assigned to this team.
I expect an error that says it's already assigned and suggests using radar.move() instead.
Copy the exact error message.
```

Save the output.

---

### Step 7 — Misuse Test 3: Skip from ADOPT directly to HOLD

Find a team + tech where the current ring is 0 (ADOPT).

Give this to Claude Code:
```
Call the execute tool with this Python code:
  result = radar.move('[team-id]', '[tech-currently-in-adopt]', 3)

The tech is currently in ring 0 (ADOPT). Ring 3 is HOLD.
This should be rejected — you can't skip rings.
I expect an error that names which intermediate rings (TRIAL or ASSESS) must be used first.
Copy the exact error message.
```

Save the output.

---

### Step 8 — Workflow Test: Multi-step in a single execute() call

Give this to Claude Code:
```
Call the execute tool with this Python code:

  new_tech = radar.add_technology(
      id='test-smoke-tech',
      label='Smoke Test Technology',
      quadrant=2,
      link='https://example.com/smoke'
  )
  radar.assign('llm-capability-office', new_tech.id, 1, 1)
  radar.commit('test: smoke test add and assign')
  result = radar.get_assignment('llm-capability-office', new_tech.id)

This adds a new technology and assigns it in one call.
Tell me what the result is.
Copy the full output.
```

Save the output.

> ⚠️ This test writes to `mcp-server/radar_working.json`. Tell Person 1 so they can reset if needed:
> `git checkout mcp-server/radar_working.json` or just delete the file (it will be recreated from config.json).

---

### Step 9 — Save all output to docs/raw-traces.txt

Give this to Claude Code:
```
I have collected output from 6 tests. Help me write docs/raw-traces.txt.
Format it with clear section headers like:

=== SMOKE TEST 1: Server starts — 2 tools visible ===
[output]

=== SMOKE TEST 2: search reads teams ===
[output]

=== SMOKE TEST 3: radar_working.json is separate from docs/config.json ===
[output]

=== MISUSE TEST 1: Non-existent tech id ===
[output]

=== MISUSE TEST 2: Duplicate assignment ===
[output]

=== MISUSE TEST 3: ADOPT to HOLD skip ===
[output]

=== WORKFLOW TEST: Add + assign in one execute() call ===
[output]

Write each section header exactly as above so Person 3 can find each one easily.
```

Commit `docs/raw-traces.txt` to the repo.

---

## When you're done

**Tell Person 3**: "raw-traces.txt is committed — start writing docs."

**Tell Person 1** about any bugs with the exact failing input + error you got.

---

## If you find a bug

Message Person 1:
> "Bug in [test name]: I sent [exact code], got [exact error or crash]. Expected: structured error with suggestions."

Wait for the fix, re-run that test, update raw-traces.txt before telling Person 3 you're done.
