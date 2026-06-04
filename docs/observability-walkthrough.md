# Observability walkthrough — answering "why did X call Y?"

The rubric: pick a real `correlation_id`, walk through the logs, answer
*"why did X call Y?"* in under 30 seconds without re-running the workflow.

This doc does that twice — once on a happy-path write, once on a chaos run
that ended in poison. Both correlation ids are real and were captured
during `python -m orchestrator.e2e_test` and `python -m orchestrator.chaos_test`
respectively. The raw events live in `observability/logs.ndjson`; the
formatted timelines below were produced by `python -m observability.query <id>`.

## How to reproduce

```bash
python -m observability.query --list           # see recent correlation ids
python -m observability.query <correlation_id> # render the timeline
python -m observability.query --tail           # last 20 events of any kind
```

The query helper sorts by `ts`, so causal order = timeline order.
Every log line carries `correlation_id`, `causation_id`, `sender`,
`recipient`, `capability`, `event` — the field set agreed in the message
envelope plus an `event` discriminator.

## Walkthrough 1 — happy-path write

**Correlation id:** `6a2c3f8b-7cee-42ba-be24-aac869eed91e`
**User request:** `add gemma3 to TRIAL` (with explicit `action=add_technology`)

```
11:51:13.446            user → orchestrator    user_request_received  user_request=add gemma3 to TRIAL explicit_action=add_technology
11:51:13.447    orchestrator → -               intent_classified  chosen_capability=propose-radar-change method=explicit_action user_request=add gemma3 to TRIAL action=add_technology
11:51:13.457    orchestrator → propose-radar-change  envelope_dispatched [propose-radar-change]  idempotency_key=1e24a75a-... endpoint=http://localhost:8003/invoke
11:51:13.461    orchestrator → propose-radar-change  dispatch_attempt [propose-radar-change]  attempt=1 endpoint=http://localhost:8003/invoke idempotency_key=1e24a75a-...
11:51:13.469       mcp-agent → orchestrator    reply_received [propose-radar-change]  ok=True
11:51:13.471    orchestrator → -               workflow_completed [propose-radar-change]  elapsed_ms=25
```

### Why did orchestrator call mcp-agent?

Read line 2: `intent_classified ... method=explicit_action chosen_capability=propose-radar-change`.
The user request carried an explicit `action=add_technology`, so the
classifier short-circuited the keyword pass and routed to the
`propose-radar-change` capability. Line 3 (`envelope_dispatched`) shows the
registry lookup resolved that capability to `http://localhost:8003/invoke`,
which is the mcp-agent's endpoint. **Total time spent answering the
question: ~10 seconds.**

### Why did mcp-agent reply with `ok=True`?

Line 5 (`reply_received`) carries `ok=True`; full reply payload is
preserved on the workflow row in SQLite (`final_response_json`) and on
the inbound envelope log entry. The MCP agent's own log line for this
correlation_id (in `logs/e2e-mcp-agent.log`) shows the action committed
to `radar_working.json` — that's outside the structured event log on
purpose: business-state changes belong to the agent's storage, the event
log only records the A2A interaction.

## Walkthrough 2 — chaos: rag-agent SIGKILL'd mid-workflow

**Correlation id:** `eb765228-e881-4db2-85f0-8455ae8d48ed`
**User request:** `Tell me about the radar history.`

```
11:55:52.333            user → orchestrator    user_request_received  user_request=Tell me about the radar history.
11:55:52.335    orchestrator → -               intent_classified  chosen_capability=answer-from-corpus method=keyword matched_keywords=["tell me", "history"] reasoning=keyword-only path; no LLM call needed
11:55:52.341    orchestrator → answer-from-corpus  envelope_dispatched [answer-from-corpus]  idempotency_key=0159cc26-... endpoint=http://localhost:8002/invoke
11:55:52.345    orchestrator → answer-from-corpus  dispatch_attempt [answer-from-corpus]  attempt=1 endpoint=http://localhost:8002/invoke idempotency_key=0159cc26-...
11:55:52.346    orchestrator → answer-from-corpus  dispatch_http_error [answer-from-corpus]  attempt=1 error=All connection attempts failed
11:55:52.597    orchestrator → answer-from-corpus  dispatch_attempt [answer-from-corpus]  attempt=2 endpoint=http://localhost:8002/invoke idempotency_key=0159cc26-...
11:55:52.603    orchestrator → answer-from-corpus  dispatch_http_error [answer-from-corpus]  attempt=2 error=All connection attempts failed
11:55:53.105    orchestrator → answer-from-corpus  dispatch_attempt [answer-from-corpus]  attempt=3 endpoint=http://localhost:8002/invoke idempotency_key=0159cc26-...
11:55:53.112    orchestrator → answer-from-corpus  dispatch_http_error [answer-from-corpus]  attempt=3 error=All connection attempts failed
11:55:53.868    orchestrator → answer-from-corpus  workflow_poisoned [answer-from-corpus]  error=All connection attempts failed elapsed_ms=1535
```

### Why did orchestrator call rag-agent (a dead one)?

Read line 2 first: `method=keyword matched_keywords=["tell me", "history"]`.
The user input contained both `"tell me"` and `"history"`, both in the
classifier's READ_KEYWORDS list, so the keyword pass deterministically
chose `answer-from-corpus`. No LLM was involved (the `reasoning`
field literally says "keyword-only path; no LLM call needed").

Line 3 (`envelope_dispatched`) shows the registry returned the rag-agent
endpoint. The agent had been SIGKILL'd a moment before so the registry's
TTL hadn't yet evicted it — that's the window the orchestrator hit.
**The "why" is captured in two adjacent log lines:** the classifier's
keyword match and the registry's stale endpoint.

### Why did the orchestrator give up after exactly three attempts?

Lines 4, 6, 8 are `dispatch_attempt attempt=1/2/3` — all three reuse the
**same** `idempotency_key=0159cc26-...`, which is exactly what the rubric
calls out under "Idempotency? It worked once." After the third connection
failure the orchestrator emits `workflow_poisoned` (line 10) and writes a
row to the `poison` table. The retry budget (`MAX_ATTEMPTS=3` in
`orchestrator/main.py`) is the upper bound, not a target — the loop
short-circuits as soon as a reply lands.

### What does the user see?

```json
{
  "correlation_id": "eb765228-e881-4db2-85f0-8455ae8d48ed",
  "status": "poisoned",
  "capability": "answer-from-corpus",
  "error": "All connection attempts failed"
}
```

That's the full HTTP body of the orchestrator's `/request` response. A
second user request would generate a *new* correlation_id and a new
idempotency_key, so re-issuing the same prompt is safe — there is no
silent re-dispatch of poisoned envelopes. (Replaying poisoned envelopes
would require a separate operator action, which is the right default —
poison is a signal, not a bug to mask.)

## What we deliberately do *not* log

- **Envelope payloads.** Payloads can carry user PII (names in questions,
  emails in tickets). The structured log records `ok` / `chosen_capability`
  / `idempotency_key` — the shape — but not the body. Agents persist their
  own answers separately so a forensic replay still has the data.
- **Stack traces of expected failures.** A `dispatch_http_error` line
  carries the error message, not the traceback. Tracebacks for *unexpected*
  failures still go to stderr via the standard logger (configured in
  `observability/logger.py:configure_root`).

## How this would scale

The single ndjson file is fine for laptop-scale (~6 events per workflow,
hundreds of workflows per session). For a real fleet:

- Replace the file sink with an OpenTelemetry exporter (`event` becomes
  the span name, `correlation_id` becomes the trace_id, `causation_id`
  becomes the parent span_id).
- The query helper would become "open the trace by id in Tempo/Jaeger" —
  which is essentially what we did manually for these two walkthroughs.

The structured-fields contract above is the same in either world — that
is the point of the envelope discipline.
