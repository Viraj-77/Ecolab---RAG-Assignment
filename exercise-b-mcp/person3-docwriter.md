# Person 3 — The Doc Writer

## Your job in one sentence
You write all the documents the grader reads — the README, the design docs, and the traces — using Person 2's test output as your raw material.

## What you're writing
The assignment requires these 6 documents:
1. `README.md` — the main submission doc
2. `docs/baseline-n-tool.md` — the "before" token count
3. `docs/proxy-design.md` — why the proxy was designed this way
4. `docs/sandbox-choice.md` — why RestrictedPython was chosen
5. `docs/trace-self-correcting.md` — one error → retry → success trace
6. `docs/trace-workflow.md` — a multi-step workflow trace with token numbers

## What the server uses
- **Python 3.11**
- **Pydantic v2** for data models
- **`mcp` Python SDK** for the MCP server
- **`RestrictedPython`** for the sandbox
- **`mcp-server/radar_working.json`** — the working copy the server reads/writes (copied from `docs/config.json` on first run; the original is never touched)

You do NOT write code. You do NOT run the server. You take what Person 1 built and Person 2 tested, and turn it into documents.

---

## Before Person 2 is done — things you can do NOW

---

### Task A — Write the N-tool baseline (do this first, no server needed)

This is the "before" picture — what the server would have looked like with one tool per operation.

Give this to Claude Code:
```
I am writing docs/baseline-n-tool.md for a Python tech radar MCP server exercise.

Imagine a naive MCP server that has one tool per operation.
Write out 7 tools with their name, description, and parameters:
1. add_technology
2. remove_technology
3. assign (assign a tech to a team with a ring value)
4. move (change a tech's ring for a team)
5. remove_assignment
6. list_assignments (list all assignments for a team)
7. validate (check if a pending change is valid)

Format each tool as a JSON schema block (name, description, parameters object with types).
Then count the total tokens across all 7 tool schemas using tiktoken with cl100k_base encoding.

Write the result to docs/baseline-n-tool.md in this format:
- Brief intro explaining this is the naive "before" baseline
- Each tool's schema
- Total token count at the bottom labeled: "BEFORE token count: X tokens"
```

---

### Task B — Draft the proxy design doc (after Person 1 commits types.py)

Give this to Claude Code:
```
Read mcp-server/src/types.py and mcp-server/src/proxy.py (if it exists yet, otherwise just types.py).

Write docs/proxy-design.md — a one-page explanation of why the RadarProxy was designed the way it was.
Cover these four points:

1. Why a proxy class instead of putting logic directly in the tool definitions?

2. Why Pydantic v2 models for the DSL instead of JSON Schema or plain text descriptions?

3. Why split into search() and execute() instead of one tool?

4. Why does the server use radar_working.json instead of writing directly to docs/config.json?
   (The original docs/config.json is the source of truth / reference — the server works on a safe copy.
    This prevents accidental corruption of the live radar during development and testing.)

Keep it to one page. Write for a technical reviewer who will grade this submission.
```

---

### Task C — Write the sandbox choice doc (after Person 1 commits sandbox.py)

Give this to Claude Code:
```
Read mcp-server/src/sandbox.py.

Write docs/sandbox-choice.md — one paragraph defending the use of RestrictedPython.
Cover:
1. What RestrictedPython gives us (blocks dangerous builtins like open, exec, import)
2. Why it fits this use case (local file editing, no credentials, no network calls needed)
3. What isolated-vm or subprocess sandboxing would add (OS-level isolation)
4. Why RestrictedPython is sufficient here but would need upgrading if this server touched real APIs or credentials

One paragraph, plain language, no filler.
```

---

## After Person 2 says "raw-traces.txt is committed"

Now you can write the remaining docs.

---

### Task D — Write the self-correcting trace doc

Give this to Claude Code:
```
Read docs/raw-traces.txt.

Find one of the misuse test sections (non-existent tech, duplicate assignment, or ADOPT→HOLD skip) where:
1. Bad Python code was sent to the execute tool
2. The server returned a structured error with suggestions (not a raw crash)

Format this as docs/trace-self-correcting.md with these sections:
## What the model tried to do
[one sentence]

## The bad code it sent
[the Python code block]

## The error the server returned
[exact error message]

## The corrected code (retry)
[write the fixed code based on the error message's suggestion]

## The successful result
[what would come back after the fix]

If raw-traces.txt does not include a retry, write the corrected code yourself based on the error message.
```

---

### Task E — Write the workflow trace doc

Give this to Claude Code:
```
Read docs/raw-traces.txt.

Find the workflow test section (add technology + assign in one execute() call).

Write docs/trace-workflow.md with these sections:

## The scenario
[what the model was trying to do — add a tech and assign it to a team]

## The single execute() call
[the Python code block from the test]

## The result
[what came back]

## Token comparison

| Approach | Steps | Estimated tokens |
|---|---|---|
| N-tool (naive) | 3 separate tool calls | ~[estimate: 3 × average call cost] |
| Code Mode | 1 execute() call | ~[count the code + result] |

Use tiktoken cl100k_base to count the execute() code and result.

## Conclusion
[one sentence on the saving]
```

To count tokens, give this separately to Claude Code:
```
Using tiktoken cl100k_base, count the tokens in this text:
[paste the execute() code here]

Also count:
[paste the result here]

Give me: code tokens, result tokens, total.
```

---

### Task F — Write the final README.md (do this last)

Give this to Claude Code:
```
Write README.md for a Python MCP server submission. Use this exact structure:

## Variant
Variant 2 — Domain-Specific Constrained Metamodel.
[One paragraph: the tech radar has a fixed schema with constrained types and strict validation rules.
Token cost is dominated by schema bloat in the naive approach, not result verbosity.
This makes it V2, not V1 (no large API surface) or V3 (results are small).]

## Proxy Interface
[Paste the Python class interface from mcp-server/src/proxy.py — method signatures only, no implementation]

## Working Copy Design
The server never writes to docs/config.json.
On first run it copies docs/config.json → mcp-server/radar_working.json.
All reads and writes go to radar_working.json.
This keeps the original radar data safe during development and testing.

## Setup

### Prerequisites
- Python 3.11
- Clone this repo

### Install dependencies
cd mcp-server
pip install -e .

### Run the server
python src/server.py

### Connect to Claude Code
[Ask Claude Code: "How do I add a local stdio Python MCP server to Claude Code's MCP config?" — paste the answer]

### Connect to MCP Inspector
[Ask Claude Code: "How do I connect MCP Inspector to a Python stdio MCP server?" — paste the answer]

## Token Measurements

| Measurement | Tokens |
|---|---|
| N-tool baseline (7 tools) | [number from docs/baseline-n-tool.md] |
| Code Mode (search + execute) | [count from src/server.py tool descriptions using tiktoken] |
| Reduction | [difference] |

Tiktoken snippet:
[paste the Python snippet used to count]

## Evaluation Scorecard

| Dimension | Before | After | Score (0–3) |
|---|---|---|---|
| Tool count | 7 | 2 | 3 |
| Bootstrap token cost | [before] tokens | [after] tokens | [score] |
| Metamodel location | In every tool schema | Pydantic types once in description | 3 |
| Credential exposure | N/A | N/A (local file) | 2 |
| Multi-step workflows | N round-trips | Single execute() | 3 |
| Validation error quality | Raw crash | Structured with alternatives | 3 |
| Result verbosity control | Full JSON dump | Model-written projection | 2 |
| **Total** | | | **/21** |

Fill in the actual numbers. Aim for 14–17 honestly. Do not fake a 21.
```

---

## File checklist — you own all of these

- `[ ]` `docs/baseline-n-tool.md` — done early, no server needed
- `[ ]` `docs/proxy-design.md` — done after types.py is committed
- `[ ]` `docs/sandbox-choice.md` — done after sandbox.py is committed
- `[ ]` `docs/trace-self-correcting.md` — done after raw-traces.txt is committed
- `[ ]` `docs/trace-workflow.md` — done after raw-traces.txt is committed
- `[ ]` `README.md` — done last (needs token numbers from all other docs)

---

## Signals you are waiting for

| Who | What they say | What you do next |
|---|---|---|
| Person 1 | "types.py committed" | Start Task B (proxy-design.md) |
| Person 1 | "sandbox.py committed" | Start Task C (sandbox-choice.md) |
| Person 2 | "raw-traces.txt committed" | Start Tasks D, E, then F (README last) |
