# Take-Home Assignment: Token-Efficient (Code-Mode) MCP Server

| | |
|---|---|
| **Author** | Thijs Hakkenberg — AI Innovation & Research |
| **Last Updated** | 2026-05-20 |
| **Version** | 1.0 |
| **Audience** | MTech interns, bootcamp trainees who have completed [Exercise A — Local RAG](./take-home-local-rag.md) |
| **Related Epic** | [A2A at Scale — 1018668](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018668) · Feature: [MCP Strategy Development — 1018686](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018686) |
| **Tenet** | Education — Experimentation |
| **Status** | Active — Exercise B in the *port → restructure → compose* track |

---

## Overview

Native MCP servers leak tokens. A 2,500-endpoint API exposed as MCP tools costs ~1.17M tokens of bootstrap context — before any reasoning has happened. Even a small domain server, designed naively, repeats the same metamodel across seven tool schemas.

**Code Mode** is a structural rewrite: replace N tools with two (`search` and `execute`) and let the model write code against a server-side proxy. The savings depend on what kind of MCP server you have. The framework you'll work from defines three variants. You'll classify, redesign, and ship one.

| Exercise | Focus | Status |
|---|---|---|
| A — Local RAG | Re-host the cloud RAG agent on Gemma 3n E4B via Ollama | See [`take-home-local-rag.md`](./take-home-local-rag.md) |
| **B — Code-Mode MCP server (this file)** | Token-efficient MCP design across three structural variants | **IN SCOPE — start here** |
| C — A2A multi-agent orchestration | Compose A + B into an A2A system | See [`take-home-a2a-orchestration.md`](./take-home-a2a-orchestration.md) |

You work in **teams of 2–3** for this exercise.

> **The proxy is what you're designing, not the tool schema.** That single sentence is what this exercise is teaching you to internalise.

## Learning Objectives

By the end of Exercise B you can:

1. Read an existing MCP server, **count its bootstrap token cost** with `tiktoken` (cl100k_base), and classify it as **Variant 1 / 2 / 3** using the framework's decision heuristic.
2. Design a **proxy interface in TypeScript** that captures the domain abstraction. The tool schema collapses to almost nothing once the proxy is right.
3. Implement **`search()` + `execute()`** with a sandbox runtime appropriate to your stack (`isolated-vm` / `node:vm` / Python `RestrictedPython` / subprocess) — and *defend* the choice. Security isolation and context isolation are not the same thing.
4. Write **self-correcting validation errors** — every error must tell the model what to try instead. Demonstrate this with a deliberate misuse and the corrected retry.
5. Separate **`query`-path** from **`execute`-path** to prevent accidental mutation during introspection. Show one trace where the split saved you.
6. Measure **before / after** bootstrap token cost and fill in the framework's evaluation scorecard (7 dimensions × 0–3). Score it honestly — the framework is not your friend if you cherry-pick.
7. Defend your DSL choices against alternatives — *why TypeScript types and not JSON Schema; why this proxy shape and not that one.*

## Prerequisites

### Reading (before you write any code — ~1 hour)

- **Required**: the *Token-Efficient MCP Server Design* framework — copy at `/Users/hakketh/Downloads/mcp-codemode-classification-framework (1).md`. Bootcamp leads will commit a versioned copy under `docs/training/bootcamp/reference/` before the assignment is released.
- **Required (skim)**: the Ecolab MCP Strategy at `docs/strategies/mcp-strategy.md` — gives you the deployment-tier model and registry context your server will eventually slot into.
- **Recommended**: the original Cloudflare *Code Mode* write-up that the framework generalises from. A link is in the framework reference.

Do **not** try to memorise the framework's variant tables before opening your editor. Read once, then start measuring tokens — token counts are what tell you which variant you're actually in.

### Tooling

- Node.js 20+ **or** Python 3.11+ (pick one for your server; you can keep your client in any language).
- [`tiktoken`](https://pypi.org/project/tiktoken/) (Python) or [`tiktoken`](https://www.npmjs.com/package/tiktoken) (Node) — for counting bootstrap tokens.
- An MCP host capable of running your server. Claude Code, Cursor, the official MCP inspector, or your own loop from Exercise A all qualify.
- One of: [`isolated-vm`](https://www.npmjs.com/package/isolated-vm), [`node:vm`](https://nodejs.org/api/vm.html), [`RestrictedPython`](https://pypi.org/project/RestrictedPython/), or a subprocess sandbox.

## Provided Infrastructure

You don't need a managed cloud endpoint for this exercise. Your MCP server runs locally; your MCP client (Claude Code, Cursor, or your own loop) connects over stdio or HTTP.

If you pick the **Tech Radar** target, the source-of-truth repo is at `/Users/hakketh/projects/repos/Stack.TechRadar` (the spoke teams' shared radar, deployed to an Azure SWA). Its config schema is documented below.

---

# Exercise B — Pick One Variant, Build One Server

## Goal

Choose **one of the three variants** below, design the proxy, implement `search()` + `execute()`, measure the token gap, and fill in the scorecard. Stretch teams: pick a second variant from a different category.

The deliverable is not "an MCP server that works." It is "an MCP server we can defend against the framework's scorecard, with a measured before/after token delta."

## The Three Variants

### Variant 1 — Large External API Surface

**Archetype**: Cloudflare MCP, Salesforce MCP, ServiceNow MCP, SAP API MCP.

**Suggested targets**:

| Target | Why it fits | Where to find it |
|---|---|---|
| **Databricks REST API** | ~150 endpoints across jobs, clusters, repos, SQL, MLflow. Spec lives in OpenAPI form on the Databricks side. | https://docs.databricks.com/api/workspace/introduction |
| **Azure DevOps REST API** | Several hundred endpoints across work items, repos, pipelines, builds, releases. Familiar from your daily work. | https://learn.microsoft.com/en-us/rest/api/azure/devops/ |
| **Public-data API** — FDA openFDA, EPA Envirofacts, OpenAQ | Hundreds of endpoints. Ecolab-adjacent. No credentials required for read-only. | https://open.fda.gov/apis/, https://www.epa.gov/enviro/web-services |

**What "good" looks like**:

- The full OpenAPI spec lives **on the server**, never in the model context. `search()` lets the model write code that queries the spec as a structured object.
- `execute()` provides an authenticated client proxy. Credentials are injected by the server, never visible to the model.
- The sandbox blocks outbound network access except through the proxy.
- Bootstrap token cost: **≤ 1,000 tokens** (two tool definitions; nothing else).

### Variant 2 — Domain-Specific Constrained Metamodel  *(canonical Ecolab target — Tech Radar)*

**Archetype**: archimate-mcp, Terraform plan MCP, BPMN editor MCP, OpenAPI spec editor MCP.

**Target**: the **Stack.TechRadar** at `/Users/hakketh/projects/repos/Stack.TechRadar`. This is the spoke teams' shared technology radar; you build an MCP server that proposes and applies edits to it.

**The actual metamodel** (from `docs/config.json` in that repo):

```typescript
// 4 quadrants, fixed
type Quadrant = 0 | 1 | 2 | 3
//   0 = Models & Providers
//   1 = Infrastructure & Cloud
//   2 = Frameworks & Libraries
//   3 = Techniques & Patterns

// 4 rings, fixed
type Ring = 0 | 1 | 2 | 3
//   0 = ADOPT, 1 = TRIAL, 2 = ASSESS, 3 = HOLD

// movement annotation since the previous radar
type Moved = -1 | 0 | 1

interface Technology {
  id: string          // kebab-case, unique across the radar
  label: string       // human-readable, ~30 chars
  quadrant: Quadrant
}

interface Team {
  id: string          // e.g. "llm-capability-office"
  name: string
  date: string        // "YYYY.MM"
}

interface Assignment {
  tech: string        // FK to Technology.id
  ring: Ring
  moved: Moved
}

// the radar:
interface Radar {
  date: string        // "YYYY.MM"
  default_team: string
  teams: Team[]
  technologies: Technology[]
  assignments: Record<string /* team id */, Assignment[]>
}
```

**Real validation rules** (these are what your server enforces):

1. `assignments[team][i].tech` must reference an existing `technologies[].id`.
2. A tech may not be assigned twice to the same team.
3. `Moved` is only meaningful relative to the previous radar — your server should know the prior `date`.
4. Some governance rules teams want to encode (defend your choice): e.g. "ADOPT requires a `link` field on the technology" (you may extend the schema), or "demoting from ADOPT to HOLD in one step is forbidden — must pass through ASSESS or TRIAL first."
5. There is **always** exactly one `default_team`.

**What "good" looks like**:

- TypeScript types above (or your improved version) appear **once** in the tool description as the DSL bootstrap. ~300–600 tokens, not repeated per tool.
- The proxy exposes a clean `radar.*` API: `addTechnology`, `assign`, `move`, `removeAssignment`, `listForTeam`, `validate`. Validation runs in the proxy, not in the tool layer.
- Validation errors say *what to try instead* — *"`'gpt-5-nano'` is already assigned to team `'commercial'` (ring TRIAL). Use `radar.move('commercial', 'gpt-5-nano', ADOPT)` to promote it."*
- After applying changes, the proxy `commit(message)` writes back to `docs/config.json` and (optionally) opens a PR — do **not** push to `main` directly during the exercise.

### Variant 3 — Stateful Context-Rich Domain

**Archetype**: Git MCP, filesystem MCP, todo/task MCP, calendar MCP, note-taking MCP.

**Suggested targets**:

| Target | Why it fits | Notes |
|---|---|---|
| A git repo (this one or any other you own) | 10–15 operations; result verbosity dominates token cost (a `read_file` on a 2,000-line file dwarfs the tool definitions). | Wrap `git` shell or `nodegit` / `pygit2`. |
| The LCBO wiki | Pages, links, history, attachments. Result shaping pays off — pages are long. | https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_wiki |
| A personal task list with deadlines & dependencies | Small tool surface, but multi-step workflows (read → transform → write) benefit from batching in code. | Roll your own JSON store. |

**What "good" looks like**:

- Even with a small (5–10) tool surface, wrapping in Code Mode pays off because the model writes code that reads → transforms → writes in a single `execute()` call instead of N round-trips.
- The proxy implements **streaming/pagination** by default rather than dumping full results.
- The proxy exposes a `project()` operator on query results — the model writes a map/filter/reduce in code; only the projection comes back to context.
- If your tool surface is < 5 tools and all simple CRUD, *call out in your write-up that Code Mode overhead may not be worth it here* — that's a valid finding.

## Required Stack (Pinned)

| Layer | You MUST use | Not allowed |
|---|---|---|
| MCP server runtime | Node.js 20+ **or** Python 3.11+ | Anything you can't sandbox |
| Sandbox runtime | `isolated-vm` (Node, security-relevant) **or** `node:vm` (Node, low-risk only) **or** `RestrictedPython` (Python) **or** subprocess+timeout | Letting the model run unrestricted code in your server process |
| MCP transport | Stdio **or** HTTP — pick one and document why | A custom protocol that defeats the point of "MCP server" |
| Token counting | [`tiktoken`](https://pypi.org/project/tiktoken/) cl100k_base | Hand-waving "looks smaller" — show the number |
| Validation | Inside the proxy methods, with self-correcting errors | Validation in the tool schema only |

## Functional Requirements

### 1. Baseline N-tool measurement

Before you write the Code Mode version, design (on paper if needed) what the **naive N-tool** version would look like. List the tools, their parameter schemas, and use `tiktoken` to count the bootstrap tokens you'd ship if you implemented it that way.

This is your **before** number. Without it, your scorecard is unfounded.

### 2. Proxy design

Hand-write the TypeScript interface for your proxy first. Do not start the implementation until the proxy interface fits on one page and the team agrees on it.

The shape that the framework recommends — adapt it to your variant:

```typescript
interface DomainProxy {
  // Reads (available in both query and execute)
  list(options?: ListOptions): CompactEntity[]
  get(id: string): Entity | undefined
  validate(operation: PendingOperation): ValidationResult

  // Writes (execute-only; proxy enforces this via the tool split)
  create(type: EntityType, data: CreateData): Entity
  update(id: string, patch: Patch): Entity
  delete(id: string): void

  // Persistence
  commit(message?: string): void
}
```

### 3. `search()` and `execute()` tools

- `search()` — **read-only**. Runs in a sandbox where the proxy exposes only the read surface. Returns the result of the model's code.
- `execute()` — read **and** write. The proxy in this sandbox can mutate; `commit()` (or `save()`, `publish()`) is the persistence trigger.
- Tool descriptions: ≤ 1,000 tokens combined for V1/V3, ≤ 1,200 for V2 (the DSL block adds ~300–600).

### 4. Self-correcting validation

For your variant, write down **three deliberate misuses** the model could make. Make sure the proxy throws a structured error for each, and the error message names the valid alternatives. Demonstrate one round-trip: (i) model emits broken code, (ii) sandbox throws structured error, (iii) model rewrites code, (iv) succeeds.

### 5. Token measurement

Use `tiktoken` cl100k_base to count:

- Bootstrap token cost of the **N-tool** baseline (paper or implemented).
- Bootstrap token cost of your **Code Mode** server.
- A typical multi-step workflow's runtime token cost in **N-tool** (sum of tool-call + result tokens) vs **Code Mode** (single execute() with code returning a projection).

These numbers go in your README and in your scorecard.

### 6. Evaluation scorecard

Fill in the framework's scorecard table. Score honestly: 0/1/2/3 per dimension, total out of 21. If you score 21, your team is either lying or has miscounted. The expected range for a first build is **12–17**.

| Dimension | Current state | Target state | Score (0–3) |
|---|---|---|---|
| Tool count | ... | ≤ 2–5 | |
| Bootstrap token cost | ... | < 1,000 | |
| Metamodel location | ... | DSL types or server-side | |
| Credential exposure | ... | Server-internal | |
| Multi-step workflows | ... | Single `execute()` | |
| Validation error quality | ... | Includes valid alternatives | |
| Result verbosity control | ... | Model controls projection | |

## Explicit Non-Goals (do NOT do these)

| ❌ Not in scope | Why |
|---|---|
| Production deployment of the MCP server | Local-only is fine for this exercise |
| Authentication of MCP clients | Stub it; the registry/auth story is part of Exercise C |
| Multi-tenant credential isolation | Stretch goal; not required for the base submission |
| Full migration of `Stack.TechRadar` to your server | You apply *proposed* changes locally; do not auto-push to `main` |
| Reimplementing the wrapped API | You wrap; you do not reinvent |
| Re-using LangChain / LlamaIndex / FastMCP magic that hides the proxy/tool split | The whole point is to design the split deliberately |

## Deliverables

1. **A public Git repository** (or a folder in your existing bootcamp repo) containing the MCP server source.
2. **`README.md`** with:
   - Variant chosen and the one-paragraph justification.
   - The proxy interface, written out as TypeScript, on the first page.
   - Setup steps to run the server and connect it to a host (Claude Code / Cursor / MCP Inspector).
   - The before/after token numbers, with the `tiktoken` snippet that produced them.
   - The filled-in evaluation scorecard.
3. **`docs/proxy-design.md`** — one page on *why this proxy shape, not another*. Reference the DSL alternatives you considered (JSON Schema, Pydantic, raw search).
4. **`docs/sandbox-choice.md`** — one paragraph defending your sandbox runtime against the alternatives in the framework's table. Address security isolation explicitly.
5. **One worked trace** showing the self-correcting-validation round-trip. Plain text is fine; copy from your terminal.
6. **One worked trace** showing a multi-step workflow that demonstrates the result-verbosity savings (V3) or the no-schema-bloat win (V1) or the constraint-validation win (V2). Numbers next to the trace.

## Evaluation Rubric

| Criterion | What we look for | Weight |
|---|---|---|
| **Variant classification** | You can defend why this server is V1, V2, or V3 against the decision heuristic — and you measured before claiming. | 10% |
| **Proxy quality** | The proxy interface fits on a page, names map to domain concepts, query/execute split is honest, validation lives in the proxy not the tools. | 25% |
| **Code Mode mechanics** | `search()` and `execute()` work with a real sandbox; credentials never leak to model context; the bootstrap token measurement is reproducible. | 20% |
| **Self-correcting errors** | At least three deliberate-misuse cases produce structured errors with named valid alternatives; one full round-trip is recorded. | 15% |
| **Honest scorecard** | Filled in, defended, total in the 12–17 range; an unrealistic 21 loses points unless every dimension is justified. | 15% |
| **Engineering discipline** | Modular code; types or docstrings; secrets handled; commits readable and incremental; README good enough that a peer can run it in 15 minutes. | 15% |

Total: **100%**. Passing bar: ≥ 70%.

## Submission

- Public repo URL shared with your bootcamp lead. Same rules as the other take-homes — no zip submissions.
- Both `proxy-design.md` and `sandbox-choice.md` live under `docs/`.
- Deadline: communicated separately.

## Version Control Expectations

Same as the other take-homes (commit early, no secrets, small commits, readable messages). Specifically for this exercise:

- **Commit the paper N-tool baseline first.** Even a markdown file with a tool-list is enough — what matters is that the *before* state is in git before the *after* state.
- **Do not commit other people's API specs.** Reference them by URL; if you cache, cache outside the repo.
- For the Tech Radar variant: never push to `main` of `Stack.TechRadar`. Open a PR from a fork or a topic branch — and only after a human review.

---

## Stretch Challenges

1. **Cross-runtime build** — implement the same server in Python (`RestrictedPython`) and Node (`isolated-vm`). Compare ergonomics, security posture, dev-loop speed, and bootstrap token count (the runtimes shouldn't change tokens, but you'd be surprised).
2. **Per-call observability** — emit a structured event per `execute()` (input code, sandbox runtime, time, token deltas, mutations). Answer *"why did the model write that code?"* from the log alone, with no re-run.
3. **Multi-tenant** — same MCP, different credentials per session, audit-trailed. The proxy gets a per-session principal.
4. **Adversarial harness** — write 10 prompts that try to break out of the sandbox or trick the proxy into mutating during a `search()`. Document what each one does and which the design rejects.
5. **Generate the DSL bootstrap automatically** from the canonical types so the description never drifts from the proxy. (Variant 2 only.)
6. **Plug the server into Exercise A** — your local-RAG agent calls the server through the MCP protocol. Note any tool-call drift in the smaller model.

---

## Appendix

### Common Smells (we will call these out)

- **Spec pasted into the tool description.** You've made native MCP worse, not better. Re-read framework Mistake 1.
- **`execute()` returns the raw API response.** You saved tool tokens and lost result-verbosity wins. Re-read Mistake 2.
- **`Error: invalid`.** The model has nothing to recover from. Re-read Mistake 5 and rewrite the error.
- **"It's only 4 tools, who cares about query/execute split."** Wait until your first accidental mutation in a read-only flow. Or: do the split anyway — it's cheap insurance.
- **Scorecard 21/21.** Either you're lying or you've miscounted. Both lose points.
- **"We picked `node:vm` because it was easier."** That's not a defence. *Why is the threat model OK with `node:vm`?* — that's a defence.
- **Tool description is a wall of JSON Schema.** That's a copy-pasted MCP server, not a designed one.

### Resources

**The framework you're working from**
- `/Users/hakketh/Downloads/mcp-codemode-classification-framework (1).md` — required read.

**MCP basics**
- Model Context Protocol spec — https://modelcontextprotocol.io/
- MCP Inspector — https://github.com/modelcontextprotocol/inspector
- Cloudflare's *Code Mode* announcement (the source pattern) — search "Cloudflare Code Mode MCP".

**Sandboxes**
- [`isolated-vm`](https://www.npmjs.com/package/isolated-vm) — V8 isolate, suitable for security-relevant servers.
- [`node:vm`](https://nodejs.org/api/vm.html) — context isolation only; **not** security isolation.
- [`RestrictedPython`](https://pypi.org/project/RestrictedPython/) — Python sandbox; review limits.
- Subprocess + timeout — OS-level isolation; highest overhead.

**Token measurement**
- [`tiktoken`](https://pypi.org/project/tiktoken/) (Python) or [`tiktoken`](https://www.npmjs.com/package/tiktoken) (Node).
- Use `cl100k_base` for OpenAI-family models (Azure OpenAI included).

**Tech Radar (V2 target)**
- Source-of-truth repo: `/Users/hakketh/projects/repos/Stack.TechRadar`
- Live radar (deployed Azure SWA): browse the team selector to see ring/quadrant assignments.
- Schema is in the README of that repo and verbatim above.

**Ecolab MCP context**
- `docs/strategies/mcp-strategy.md` — the deployment-tier model your server eventually fits into.
- `docs/designs/mcp-registry-spec.html` — registry contract for when your server is published.

### FAQ / Common Pitfalls

**Q: I picked Variant 1, but my chosen API only has 30 endpoints. Am I in the wrong variant?**
Probably yes. Re-run the decision heuristic. If schema bloat dominates and the metamodel is loose, you might be V1. If the API has constrained types and rules, you're V2. If most token cost is from results, V3. *Measure first.*

**Q: My DSL block is 1,200 tokens. Is that too much?**
For V2, target ≤ 600. If your block is 1,200, your types are too verbose — strip JSDoc, collapse unions, factor out repeated structures. The model has pretraining knowledge; you don't need to define `string` for it.

**Q: The model keeps trying to write Python in the sandbox even though I said TypeScript.**
Be explicit in `execute()`'s description: *"You will write JavaScript. The proxy `<name>` is the only way to interact with the domain. Do not import Node APIs."* Smaller models drift more (you saw this in Exercise A).

**Q: Should I use `FastMCP` / `mcp-typescript` / similar SDKs?**
Yes for the protocol plumbing. *No* for anything that bundles tool registration in a way that hides the proxy/tool split — you must own that split.

**Q: My tool returns an error and the model just gives up.**
That's the framework's Mistake 5. Your error needs to name the valid alternatives — *"`assignTo('rde', 'gpt-5-nano')` failed: tech `'gpt-5-nano'` not in radar. Use `radar.addTechnology(...)` first, or pick from: gpt-5.4-nano, claude-haiku-4-5-databricks, ..."*

**Q: For the Tech Radar variant, should my server actually edit `docs/config.json`?**
Yes — that's the realistic design. But never auto-push to `main` of the radar repo during the exercise. `commit()` writes the file and opens a PR (or stages a branch) for human review.

**Q: Can I skip the N-tool baseline since "obviously" Code Mode is cheaper?**
No. The before/after delta is half of what you're being evaluated on. A scorecard without the *before* is a brochure.

---

*Questions? Raise them in your bootcamp cohort channel before burning time on the wrong interpretation.*
