# Failure modes

This document covers the chaos test we ran (P3.4) and the failure modes the
design anticipates. The structured trace from the chaos run is at
`logs/chaos-trace.txt` (regenerated each time `python -m orchestrator.chaos_test`
is invoked).

## Chaos test — what we killed, what happened

**Run command:** `python -m orchestrator.chaos_test`
**What we kill:** the rag-agent (port 8002), in two phases.

### Phase A — graceful death (SIGTERM)

1. Boot registry + rag-agent + mcp-agent + orchestrator.
2. Verify a normal read request completes (`status=completed`).
3. Send `SIGTERM` to rag-agent. Its FastAPI lifespan runs the shutdown
   path which `DELETE /deregister/rag-agent` against the registry.
4. Send another read request to the orchestrator.

**Outcome:** the orchestrator's registry lookup returns an empty list
for `answer-from-corpus`, the workflow row goes straight to `failed`
with `step=no_agent_for_capability`, and the user gets:

```json
{
  "status": "failed",
  "capability": "answer-from-corpus",
  "error": "no agent advertises capability 'answer-from-corpus'"
}
```

No retry budget is consumed, no poison row is written, latency is
~10 ms. **This is the desired behavior** — when an agent leaves cleanly,
the system fails fast and tells the user precisely what's missing.

### Phase B — sudden death (SIGKILL)

1. Re-spawn rag-agent and wait for it to register.
2. Send `SIGKILL`. The agent has no chance to deregister, so the
   registry still lists `rag-agent` until its 30 s TTL expires.
3. **Immediately** fire another read request through the orchestrator
   (within the TTL window).

**Outcome:** the orchestrator looks up `answer-from-corpus`, gets the
dead endpoint, and dispatches the envelope. Connection refused. It
retries, **reusing the same `idempotency_key`** so a slow-to-die agent
that responds late wouldn't double-process. Three attempts fail in a
row. The orchestrator marks the workflow `poisoned` and writes a row
to the `poison` table.

The structured timeline from that run (excerpt — full version in
`logs/chaos-trace.txt`):

```
dispatch_attempt        attempt=1 idempotency_key=0159cc26-...
dispatch_http_error     attempt=1 error=All connection attempts failed
dispatch_attempt        attempt=2 idempotency_key=0159cc26-...
dispatch_http_error     attempt=2 error=All connection attempts failed
dispatch_attempt        attempt=3 idempotency_key=0159cc26-...
dispatch_http_error     attempt=3 error=All connection attempts failed
workflow_poisoned       elapsed_ms=1535
```

User sees:
```json
{
  "status": "poisoned",
  "error": "All connection attempts failed"
}
```

**Lesson:** the registry's TTL window is the failure surface. SIGKILL'd
agents are still "alive" to the registry for up to 30 s, and that's
exactly when the orchestrator burns retry attempts on a dead host. We
considered making the agent endpoints health-checked before dispatch
but rejected it: the orchestrator would then have to re-implement the
registry's job, and the retry-with-idempotency loop already produces
the right outcome (poison) loudly enough.

## Anticipated failure modes (and how the design handles each)

### 1. Timeout on a downstream agent
- **Mechanism:** `httpx.TimeoutException` inside `_send_with_retries`.
- **Handling:** retry up to `MAX_ATTEMPTS=3` with the *same*
  `idempotency_key`. The receiver dedupes via its in-memory LRU
  (`agents/lifecycle.py:IdempotencyLRU`) so a slow-then-recovering agent
  doesn't double-process.
- **Tunable via env:** `ORCH_CALL_TIMEOUT` (default 5 s),
  `ORCH_MAX_ATTEMPTS` (default 3).

### 2. HTTP error / connection refused
- **Mechanism:** any `httpx.HTTPError` short of timeout (5xx,
  ConnectionError).
- **Handling:** logged as `dispatch_http_error`, retried with the same
  idempotency_key, escalated to poison after the budget. Identical
  semantics to timeouts.

### 3. Retry budget exhausted → poison
- **Mechanism:** `MAX_ATTEMPTS` consecutive failures.
- **Handling:** workflow row → `status=poisoned, step=poisoned`, plus a
  row inserted into the `poison` table with the original envelope JSON
  and the failure reason. Inspectable at `GET /poison`. **No automatic
  replay.** Re-issuing the original user prompt creates a *new*
  workflow with a new correlation_id — the original poisoned envelope
  stays as audit.

### 4. Partial completion (one of two agents fails after the other succeeded)
- **Bootcamp scope:** our happy-path workflows are single-step
  (orchestrator → one agent → reply). Partial completion as the
  rubric describes (A succeeds, B fails) does not arise in the
  Tech Radar Concierge flow because the orchestrator does not chain
  RAG → MCP for one user request — it picks one capability per request.
- **If we extended to chained workflows:** the workflow row's
  `last_envelope_json` field already captures the most recent reply.
  We'd add a `step` enum with `(rag_done, mcp_pending, mcp_done)`,
  resume from the recorded step on retry, and add a compensating-action
  hook keyed by the partially-completed step. **We did not implement
  this** because the rubric says "if you need 5+ agents you're
  over-engineering" — same logic for chained workflows in this scope.

### 5. Poison message / unparseable envelope
- **Mechanism:** an envelope that fails Pydantic validation at the
  agent's `POST /invoke` boundary. FastAPI returns 422.
- **Handling:** the orchestrator treats 422 the same as any other
  HTTP error — three retries with same idempotency_key (which won't
  help, but the symmetry is intentional) and then poison. Manual
  inspection via `GET /poison`.
- **Why no agent-side dead-letter:** the agents are stateless about
  rejected envelopes. Centralising the dead-letter at the orchestrator
  matches the topology decision (single accountable row) and avoids
  three different reject queues.

### 6. Orchestrator restarts mid-flight
- **Mechanism:** Python process dies (Ctrl-C, OOM, deploy).
- **Handling:** on startup, `_resume_in_progress` finds every row with
  `status IN ('pending','in_progress')`, marks them `failed` with
  `step=orchestrator_restart`, and emits a `workflow_interrupted`
  event. **We deliberately do not silently resume.** Reasons:
  - The user's in-flight HTTP `POST /request` already returned an
    error (the connection dropped). Silent resume would race with a
    retried request and trigger two writes for "one" user click.
  - Idempotency LRUs are in-memory, so a resumed envelope would not
    benefit from dedupe across the restart boundary.
  - "Replay is the user's job" produces a new correlation_id, which
    is observably correct.
- **What this costs:** a workflow that crashes mid-write to the radar
  may have committed at the mcp-agent but the orchestrator never saw
  the reply. The radar ends up with the change; the user sees an
  error. This is an **at-most-once user-visible result, at-least-once
  side effect** — same trade-off every workflow engine forces. We
  document it; we do not paper over it.

### 7. Registry crashes
- **Mechanism:** registry process dies.
- **Handling:** orchestrator's lookups raise `httpx.ConnectError`,
  which we catch and surface as `registry_lookup_failed` →
  `status=failed`. Agents' heartbeats fail silently and they stay up.
  When the registry comes back agents do **not** auto-re-register
  (the registration POST happens once at lifespan startup) — they
  rely on the operator to restart them. This is a known gap; in
  production we'd add a periodic "if not in registry, re-register"
  in the heartbeat loop. Bootcamp scope: noted, not implemented.

### 8. Agent registers under a stale endpoint
- **Mechanism:** an agent restarts on a different port but the
  registry still has its old endpoint.
- **Handling:** the new POST `/register` overwrites the record by
  name, so this is self-healing on register. The window is the
  process startup time — sub-second locally.

## What we did not chaos-test (and why)

- **Killing the registry.** Same failure surface as "registry crashes"
  above; nothing new to demonstrate.
- **Killing the orchestrator.** The interesting half (resume on
  restart) is unit-tested by a manual `pkill -9 -f orchestrator.main &&
  pkill && uvicorn ...` cycle; the assertion is that the workflow row
  comes back as `failed` with `step=orchestrator_restart`. This is
  the same code path exercised by `_resume_in_progress` and we did
  not script it because the assertion is on a SQL row, not on
  network behaviour.
- **Network partition between orchestrator and agents.** Locally this
  collapses to "connection refused", which is what Phase B tests. A
  real partition (packet drops, not RST) would show up as timeouts —
  same retry path, same poison outcome.

## TL;DR

The system fails in three observable ways: **fast-fail** (graceful
agent death, registry empty), **retry-then-poison** (sudden agent
death, dead endpoint), and **fail-loud-on-restart** (orchestrator
death, in-progress workflows surfaced not silently resumed). All
three are visible in the structured event log without re-running the
workflow. There is no silent loss path that we know of; if you find
one, the trace will show it.
