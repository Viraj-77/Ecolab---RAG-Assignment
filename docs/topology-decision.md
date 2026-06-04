# Topology decision — Orchestration vs Choreography

**Decision:** **Orchestration.** A central conductor (`orchestrator/`, port 8001)
classifies intent, queries the registry by capability, dispatches one envelope
per step, and persists workflow state to SQLite. Agents do not subscribe to
events; they only respond to direct envelopes.

This document defends that pick against the trade-off axes the assignment
calls out (cognitive load, blast radius, debuggability, latency) and against
the "what if the team doubles next year?" stress test.

## What we considered

| Topology | Mechanism | Where state lives |
|---|---|---|
| **Orchestration (chosen)** | `orchestrator/main.py` calls agents directly over HTTP | `orchestrator/state.db` (SQLite) — `workflows` + `poison` tables |
| Choreography | NATS / Redis Streams; agents subscribe to events tagged by capability | The event log itself is the state |

Both are realistic for the Tech Radar Concierge scenario. We rejected
choreography for the bootcamp version because of the trade-offs below — but
the call would change for the larger-team scenario, and we say so explicitly.

## Trade-offs scored

### Cognitive load on a new engineer — **orchestration wins**
A new teammate can answer "what does this system do when a request arrives?"
by reading exactly one file: `orchestrator/main.py`. The flow is linear:
classify → look up endpoint → send envelope → persist reply → return. With
choreography the same answer requires reading every subscribing agent and
reasoning about emergent ordering — the system's behaviour lives between the
files, not inside any one of them.

### Blast radius when one agent fails — **roughly tied; orchestration is more honest**
Killing the rag-agent in our chaos test (see `docs/failure-modes.md`)
produces two visible behaviors: graceful exit → fast `failed`, sudden death
→ retry-with-idempotency loop → `poisoned`. In both cases the orchestrator
is the only process that needs to know *what to do next*, and that decision
is committed to SQLite before the user is told. With choreography the failure
is more diffuse — other subscribers may keep emitting events while the
unhealthy agent is offline, so the work-in-progress backlog grows quietly
in the broker. Orchestration forces the outcome onto a single accountable row.

### Debuggability — **orchestration wins, but only because we built the trace**
The rubric requires *"why did agent X call agent Y?"* to be answerable from
logs alone. With orchestration that question reduces to "what did the
orchestrator decide?" — one process, one classifier, one log line per
decision (see `intent_classified` events). Choreography does not have this
single-decision-point: each event-driven agent independently decides whether
to react, and reconstructing the *causal* chain (vs the temporal one) means
joining across many subscriber logs. We have only six events on a happy-path
write — see `docs/observability-walkthrough.md` for the trace.

### Latency — **choreography would win under load; orchestration is fine here**
Our happy-path write trace shows a 25 ms end-to-end round trip for a single
classify → dispatch → reply (`workflow_completed elapsed_ms=25` in the
observability log). At a bootcamp's request rate this is irrelevant.
Choreography would be faster *under sustained load* because subscribers fan
out work in parallel and the broker is durable — but we don't have sustained
load, and the "async is faster under load" argument needs numbers we don't
have. We mention this here so the reader doesn't accept "synchronous = slow"
on faith.

### What changes if the team doubling next year? — **the answer flips toward choreography**
With 6+ engineers shipping new agents, an orchestrator becomes a
coordination bottleneck: every new capability requires editing
`orchestrator/main.py` (or its classifier). Choreography decouples that:
a new agent declares the events it cares about and ships independently. We
would migrate by:

1. Keeping the registry as-is (capability advertising still matters).
2. Replacing the orchestrator's outbound call with an event publish — agents
   subscribe by capability rather than being directly invoked.
3. Promoting the SQLite `workflows` table into a proper event store (the
   broker's log) so workflow state is materialised on demand rather than
   maintained imperatively.

We would also switch from "fail loudly on orchestrator restart" to "the
event log replays itself" — which is a real upgrade in failure semantics.

## Honest costs we accepted by picking orchestration

1. **The orchestrator is a single process.** If it dies, in-progress
   workflows are marked `failed` on restart (see `_resume_in_progress` in
   `orchestrator/main.py`); we do *not* silently resume. That's a
   deliberate trade — silent resume requires deduplication on every
   downstream agent, which the bootcamp's in-memory LRU does provide, but
   we'd rather show the failure than paper over it.
2. **Adding a new capability requires two edits.** The new agent + a
   classifier or routing rule update on the orchestrator. With
   choreography it would be one.
3. **The registry's TTL window is a real failure mode.** A SIGKILL'd
   agent stays "alive" in the registry for up to 30 s, which is exactly
   the window in which the orchestrator hits a dead endpoint and burns
   its retry budget into the poison table. This is captured by the
   chaos test and *is* the intended behavior — but it's a cost, not a
   freebie.

## TL;DR

For three agents, one workflow shape, and a bootcamp graders' deadline:
**orchestration is the right pick** because it makes the decision flow
explicit, the failure surface honest, and the debugging story
single-process. We would re-evaluate at team size > 6 or capability
count > 8.
