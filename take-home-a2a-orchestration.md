# Take-Home Assignment: A2A Multi-Agent Orchestration

| | |
|---|---|
| **Author** | Thijs Hakkenberg — AI Innovation & Research |
| **Last Updated** | 2026-05-20 |
| **Version** | 1.0 |
| **Audience** | MTech interns, bootcamp trainees who have completed [Exercise A — Local RAG](./take-home-local-rag.md) and [Exercise B — Code-Mode MCP](./take-home-codemode-mcp.md) |
| **Related Epic** | [A2A at Scale — 1018668](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018668) · Features: [Eva Everywhere Orchestration POC — 1018682](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018682), [Agent Registry — 1018685](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018685) |
| **Tenet** | Education — Experimentation |
| **Status** | Active — Exercise C in the *port → restructure → compose* track |

---

## Overview

You have a local RAG agent (Exercise A). You have an MCP server with a deliberate proxy design (Exercise B). They are not yet a system — they are two programs that don't know about each other. This exercise is where you make them one.

Two agents that don't know about each other are not a system. **Make them one.**

| Exercise | Focus | Status |
|---|---|---|
| A — Local RAG | Re-host the cloud RAG agent on Gemma 3n E4B via Ollama | See [`take-home-local-rag.md`](./take-home-local-rag.md) |
| B — Code-Mode MCP server | Token-efficient MCP design across three structural variants | See [`take-home-codemode-mcp.md`](./take-home-codemode-mcp.md) |
| **C — A2A multi-agent orchestration (this file)** | Compose A + B into an A2A system with a registry, observability, and failure handling | **IN SCOPE — start here** |

You work in **teams of 2–3** for this exercise. Compose your team's own Exercise A agent and Exercise B server into the system; you do not need a fresh build.

## Learning Objectives

By the end of Exercise C you can:

1. Implement the **A2A protocol minimally** — agent discovery, capability advertising, message envelope, idempotency keys, correlation IDs — and explain each field's job in one sentence. The wire format is yours to design within the constraints below.
2. Stand up an **Agent Registry** modelled on Ecolab's `docs/designs/agent-registry-spec.html`, with at least: register, deregister, query-by-capability, health.
3. Compose **at least three agents** into an end-to-end workflow on an Ecolab-adjacent scenario:
   - one **local-RAG agent** (re-using your Exercise A agent),
   - one **MCP-backed agent** (re-using your Exercise B server),
   - one **orchestrator** (or, if you choose choreography, an event broker).
4. Choose **orchestration** (a central conductor — Durable Functions / Temporal-style) **vs choreography** (agents react to events; no conductor) and defend the choice using the same trade-off discipline as Architecture Exercise 4 — cognitive load, blast radius, debuggability, latency.
5. Wire **observability end-to-end**. Every agent-to-agent message is traceable, and *"why did agent X call agent Y?"* is answerable from logs alone — no re-running.
6. Handle failure honestly: timeouts, retries with idempotency keys, partial completion, poison messages. Document what happens when one agent dies mid-workflow.
7. (Optional) Bootstrap with [`ollama2a`](https://pypi.org/project/ollama2a/) and decide whether its abstractions helped — defend keep / replace / ignore.

## Prerequisites

### Reading (before you write any code — ~1 hour)

- **Required**: `docs/strategies/a2a-strategy.html` — Ecolab A2A strategy. Don't try to implement everything in here; understand the *contract*.
- **Required**: `docs/designs/agent-registry-spec.html` — the registry contract you'll model on.
- **Required**: `docs/designs/observability-contract.md` — the trace fields and message-envelope expectations.
- **Recommended**: `docs/designs/agent-classification-pipeline.md` — auto-registration / governance pipeline for context.

You do **not** need to read the full Eva Everywhere or Agent Control Tower designs. The point of this exercise is to internalise the contract, not to clone a production platform.

### Tooling

- Python 3.11+ **or** Node.js 20+. Mixed-language is allowed across agents (your team's choice; document trade-offs).
- A message transport you can defend: HTTP/JSON-RPC, gRPC, NATS, Redis Streams, Azure Service Bus, or a Python `asyncio.Queue` with persistence — pick one and own the consequences.
- An observability sink: OpenTelemetry collector → Jaeger/Tempo/Grafana (or just structured JSON logs to a file with a small log-viewer notebook). Whatever you use, it must answer the *"why did X call Y"* question without re-running the workflow.
- Optional: [`ollama2a`](https://pypi.org/project/ollama2a/) as a bootstrap library.

## Provided Infrastructure

There is no managed Ecolab A2A infrastructure for this exercise — you build the pieces. When the bootcamp graduates a real Eva integration, the skills you build here transfer to that platform.

For local development, run everything on your laptop. The orchestrator, registry, two business agents, and observability sink can all be processes on `localhost`.

---

# Exercise C — Compose A + B into a Real A2A System

## Goal

Pick an Ecolab-adjacent scenario where the local-RAG agent and the MCP-backed agent each have a job no other agent can do. Stand up a registry, three agents, an orchestrator (or event broker), and observability. Run it end-to-end. Then break it on purpose.

## Suggested Scenarios

Pick one — or invent your own and defend it.

| Scenario | What each agent does | Why it forces composition |
|---|---|---|
| **Tech Radar Concierge** | RAG agent answers natural-language questions about the radar's history & rationale (corpus = past radar snapshots, ADRs, blog posts). MCP-backed agent (your Ex B Variant 2 server) actually edits the radar. Orchestrator routes "explain" vs "propose change" intents. | Read-vs-write split, two distinct capabilities, real artifact (the radar) at the end. |
| **SOP Assistant** | RAG agent retrieves and explains plant-floor SOPs from your Exercise A corpus. MCP-backed agent files an issue / opens a ticket via Exercise B (V1 over Azure DevOps API or V3 over a task-list backend). Orchestrator decides "answer in chat" vs "escalate as ticket". | Realistic field-tech use case; clear escalation seam. |
| **Tech Demand Triage** | RAG agent classifies an inbound request against Ecolab's tech demand process. MCP-backed agent (V1 or V3) creates the corresponding work item. A third "policy" agent vets every cross-agent message before forwarding (compliance pattern). | Three agents with distinct jobs; introduces a non-trivial orchestration topology. |

If you invent your own, the bar is: each agent must do something the others *cannot*, and the workflow must benefit from the composition (i.e. doing it as one monolithic agent would be worse).

## Required Stack (Pinned)

| Layer | You MUST have | Not allowed |
|---|---|---|
| Agents | At least 3, each a separate process | A single Python file with three classes pretending to be agents |
| Registry | A real service with register/deregister/query-by-capability/health | Hardcoded URLs |
| Transport | One transport across all agents (HTTP, gRPC, NATS, Service Bus, etc.) — your choice | Different ad-hoc protocols per pair |
| Message envelope | Includes at minimum: `correlation_id`, `causation_id`, `idempotency_key`, `sender`, `recipient`, `capability`, `payload`, `timestamp` | Bare JSON blobs |
| Observability | Structured logs **or** OTEL traces — answer "why did X call Y" from logs alone | Print-statement debugging |
| Orchestrator OR event broker | A real one. Durable workflow engine, custom orchestrator with persisted state, or an event broker (NATS / Redis Streams / etc.) | A single `if/else` ladder in one process |

You **may** use [`ollama2a`](https://pypi.org/project/ollama2a/) as a starter; if you do, your write-up must answer *did it help, where did it get in the way?*

## Functional Requirements

### 1. Agent Registry

Implement a registry service exposing at least:

- `POST /register` — agent declares: name, capabilities (free-form strings the orchestrator can match against), endpoint, health URL.
- `DELETE /deregister/:name` — graceful shutdown.
- `GET /agents` — list with filter by capability.
- `GET /health` — registry's own health, plus aggregated per-agent.
- A heartbeat / TTL so a crashed agent eventually disappears.

The shape should be recognisable from `docs/designs/agent-registry-spec.html`. You are not required to be wire-compatible with that spec — you are required to be able to defend any deviations.

### 2. Three Agents (minimum)

- **Local-RAG agent** (from Exercise A). Wrapped in an A2A service. Advertises a capability like `"answer-from-corpus"`.
- **MCP-backed agent** (from Exercise B). Wrapped in an A2A service. Advertises a capability like `"propose-radar-change"` or whatever fits your scenario.
- **Orchestrator** — receives the user request, queries the registry, dispatches to one or more business agents, composes the final response.

Each agent registers on startup, deregisters on shutdown, responds to health checks.

### 3. Message Envelope

Define your envelope as a single struct (Pydantic / Zod / TypeScript interface) and use it everywhere. At minimum it includes:

- `correlation_id` — same across all messages in one user request.
- `causation_id` — the message that caused this one.
- `idempotency_key` — the receiver uses this to dedupe retries.
- `sender`, `recipient`, `capability`, `payload`, `timestamp`.

Include the field definitions verbatim in your README and explain each in one sentence.

### 4. Orchestration vs Choreography — Pick One, Defend It

Decide between:

- **Orchestration** — a central conductor maintains workflow state, dispatches each step, retries failed calls. (Examples: Durable Functions, Temporal, your own workflow engine over a database.)
- **Choreography** — agents emit events; other agents react. No central state; the event log *is* the state.

Write a one-paragraph defence in `docs/topology-decision.md` covering: cognitive load on a new engineer, blast radius when one agent fails, debuggability, latency, and how your decision changes if the team shipping next year is twice the size.

### 5. Observability

Implement structured logging or OTEL tracing such that, given a `correlation_id`, you can reconstruct:

- Which agents took part.
- The order of messages.
- Any retries / timeouts / failures.
- For each LLM-driven decision: *the prompt that produced the next-step choice*.

The acceptance test: open a transcript at random, ask *"why did agent X call agent Y?"*, get the answer in under 30 seconds without re-running the workflow.

### 6. Failure Handling

Implement and document:

- **Timeouts** — every cross-agent call has a deadline; document what happens when it expires.
- **Retries with idempotency** — at least one agent retries a downstream call; the receiver dedupes via `idempotency_key`.
- **Partial completion** — what state is the workflow in when agent B succeeds but agent C fails? Recoverable, or compensating action?
- **Poison message** — an envelope that fails repeatedly. Where does it go? (Dead-letter queue? Logged and dropped? Routed to a human?)

Demonstrate at least **one chaos test**: kill one agent mid-workflow, watch the system behave, document the outcome.

## Explicit Non-Goals (do NOT do these)

| ❌ Not in scope | Why |
|---|---|
| Production deployment to Azure / Kubernetes | Local-only is fine; the patterns transfer |
| Building your own LLM-routing platform | Use your Exercise A agent as-is |
| Agent-driven prompt-injection mitigation beyond awareness | Mention threat in write-up; full mitigation is bigger than this exercise |
| Wire-compatible Ecolab Agent Registry implementation | Spec-aligned is enough; full compatibility comes later |
| Dynamic agent code-loading / sandboxing | That's the Code Mode pattern from Exercise B; here you compose, you don't reload |
| More than 5 agents | If you need 5+, you are over-engineering. Three is the bar; four is fine; five is a code smell. |

## Deliverables

1. **A public Git repository** (or folder) containing all services, the registry, the observability stack, and run scripts. One `make up` (or `docker compose up`, or `python orchestrator/run.py`) starts the whole system locally.
2. **`README.md`** with:
   - The chosen scenario and why each agent has a unique job.
   - The message envelope, written out in code, with one-sentence field descriptions.
   - One-command setup; one-command run.
   - A mermaid sequence diagram of the happy-path workflow.
3. **`docs/topology-decision.md`** — one page on orchestration vs choreography, scored against the trade-off axes.
4. **`docs/observability-walkthrough.md`** — pick one real `correlation_id` from a workflow run; walk a reader through the logs/traces and answer *"why did X call Y?"* twice.
5. **`docs/failure-modes.md`** — the chaos test: what you killed, what happened, what you learned. Plus a short list of failure modes you anticipated and how the design handles each.
6. **A short demo recording** (~3 minutes, OBS / QuickTime / Loom) of a happy-path run *and* a chaos run. Internal hosting only — do not commit to the repo.

## Evaluation Rubric

| Criterion | What we look for | Weight |
|---|---|---|
| **System works end-to-end** | Three agents up, registry queryable, the chosen scenario runs to a meaningful output. | 20% |
| **Protocol discipline** | Envelope is consistent; correlation/causation/idempotency keys are populated and used; capabilities are matched, not hardcoded. | 20% |
| **Topology defence** | Orchestration vs choreography choice is named, scored against axes, honest about trade-offs accepted. | 15% |
| **Observability** | "Why did X call Y" is answerable from logs alone for any `correlation_id`. LLM-driven decisions show their prompts. | 15% |
| **Failure handling** | Timeouts, retries-with-idempotency, partial-completion, poison-message all addressed in code or in writing. At least one real chaos test recorded. | 15% |
| **Composition honesty** | Each agent does something the others can't. The system is more than the sum of the parts. | 10% |
| **Engineering discipline** | Modular code; types or docstrings; readable commit history; one-command setup that works on a fresh laptop. | 5% |

Total: **100%**. Passing bar: ≥ 70%.

## Submission

- Public repo URL shared with your bootcamp lead.
- All three docs (`topology-decision.md`, `observability-walkthrough.md`, `failure-modes.md`) under `docs/`.
- Demo link in your README.
- Deadline: communicated separately.

## Version Control Expectations

Standard rules from the prior take-homes apply. Specifically for this one:

- **One commit per agent skeleton** before any of them does anything useful. We want to see the agents register and respond to health checks before any business logic ships.
- **Commit your message envelope as a typed module first.** It will change; that's fine — git history of the envelope's evolution is itself part of what we read.
- **Do not commit logs or traces with PII** — even your test scenarios. If your prompts contain names or emails, scrub before commit.

---

## Stretch Challenges

Pick one or more once your base deliverables are in.

1. **Fully local A2A** — every agent uses your Exercise A local model. Run the same workflow under no-internet conditions and report whether the latency budget still holds.
2. **Hot-swap a model** — swap one agent's underlying model (Gemma 4B → 8B, or local → cloud) without restarting the orchestrator. The registry should re-discover the new endpoint.
3. **Policy-gate agent** — add a fourth agent that vets every cross-agent message before it is forwarded. Inspired by the Ecolab compliance pattern. Define what "vet" means concretely (PII strip, refusal on banned terms, data-class check).
4. **Topology bake-off** — implement the same workflow under both orchestration *and* choreography. Run identical chaos tests. Report which broke first, where, and why.
5. **Replace `ollama2a`** — start with `ollama2a`, then strip it out once you understand what it does. Was it net-positive or net-negative? *Why?*
6. **Schema-enforced envelope** — protobuf or Avro for the envelope, with a versioned registry. Bump a field type and break a downstream agent on purpose; show the version negotiation kicking in.

---

## Appendix

### Common Smells (we will call these out)

- **No registry.** If agents hardcode each other's URLs, it's not A2A — it's RPC.
- **"Idempotency? It worked once."** First retry collapses your design.
- **Untraceable orchestrator decisions.** If the trace doesn't say *why*, observability is theatre.
- **Three agents that all do the same thing.** Composition means each agent has a job no other agent can do.
- **Choreography with no event log.** The whole point is that the event log *is* the state. If it's not durable, you've built ad-hoc coupling, not choreography.
- **Orchestrator with no persisted state.** The whole point is workflow state survives a crash. If your "orchestrator" loses context on restart, it's a router.
- **"Latency is bad because async is bad."** If your numbers contradict this — say so. Async with a real message bus is often *faster* under load.
- **Envelope only on the wire.** If you parse it back into local objects and the rest of your code uses bespoke types, the envelope discipline is cosmetic.

### Resources

**Ecolab A2A & registry**
- `docs/strategies/a2a-strategy.html` — Ecolab A2A strategy.
- `docs/designs/agent-registry-spec.html` — registry contract you model on.
- `docs/designs/observability-contract.md` — trace and envelope expectations.
- `docs/designs/agent-classification-pipeline.md` — auto-registration pipeline.

**A2A protocol references**
- Google's [A2A Protocol](https://github.com/google/A2A) — the public reference protocol.
- Anthropic's MCP — your Exercise B work is what each agent uses internally for capability access.

**Orchestration / choreography building blocks**
- [Temporal](https://temporal.io/) — production-grade orchestration; read the docs even if you don't use it.
- [Azure Durable Functions](https://learn.microsoft.com/en-us/azure/azure-functions/durable/) — pattern reference.
- [NATS](https://nats.io/) / [Redis Streams](https://redis.io/docs/data-types/streams/) — choreography substrate.

**Observability**
- OpenTelemetry — https://opentelemetry.io/
- Tempo + Grafana for trace exploration — sufficient for laptop scale.

**Optional starter library**
- [`ollama2a`](https://pypi.org/project/ollama2a/) — bootstrap A2A on top of Ollama.

### FAQ / Common Pitfalls

**Q: My orchestrator is just a Python function with three `if` branches. Is that enough?**
No. State must survive a process restart, and "what did agent B reply when agent A asked at step 3" must be queryable. A function with `if` branches loses both. Either persist the workflow state to a small SQLite/Redis store, or use a real workflow engine.

**Q: Do I need OpenTelemetry, or are JSON logs OK?**
JSON logs are fine, *if* a `correlation_id` filter rebuilds the timeline and a human can answer "why did X call Y" in under 30 seconds. If your logs need three terminal windows and a spreadsheet, switch to OTEL.

**Q: My local-RAG agent is too slow to drive a real workflow. What do I do?**
Two options: (1) put a smaller / faster local model in front of the RAG agent for routing, escalate only when needed; (2) run the local-RAG step async and surface a "thinking…" message — the orchestrator just needs to handle the eventual reply. *Document which you chose and why.*

**Q: Should choreography agents be able to subscribe to *any* event?**
Practically, yes; architecturally, no — you'll regret it. Constrain subscriptions to declared capabilities, even if your broker doesn't enforce it. Document the rule.

**Q: My MCP server from Exercise B is single-tenant. Can my A2A agents share it?**
Yes for the exercise. In production you'd want a per-session principal (the multi-tenant stretch from Exercise B). For now, share the server and note the gap in your write-up.

**Q: How big is "too big" for the demo?**
If a single user request takes more than ~30 seconds end-to-end on a happy path, your scenario is too big for this exercise — slim it. We're grading the *protocol* and *composition*, not the depth of the business workflow.

**Q: Is `ollama2a` required?**
No. It's a starter; some teams find it useful, others fight it. Either path is fine — what we grade is your reflection on it.

---

*Questions? Raise them in your bootcamp cohort channel before burning time on the wrong interpretation.*
