# Exercise C — Execution Plan

**Scenario:** Tech Radar Concierge
**Transport:** HTTP/JSON (FastAPI)
**Topology:** Orchestration (central conductor + SQLite-persisted state)
**Language:** Python 3.11+
**Branch:** `Team/ExerciseC-ScenarioA`
**Repo:** https://github.com/Viraj-77/Ecolab---RAG-Assignment

**Source branches to vendor in:**
- Exercise A (local RAG): `local-mode-code-Viraj`
- Exercise B (MCP Variant 2): `Team/ExerciseB-Variant2`

---

## 0. Shared foundations (do together, ~2 hrs, day 1)

- [ ] Confirm capability strings: `answer-from-corpus` (RAG), `propose-radar-change` (MCP).
- [ ] Confirm intent routing: `"explain"` → RAG; `"propose change"` → MCP; orchestrator decides.
- [ ] Agree on local ports: registry `8000`, orchestrator `8001`, RAG agent `8002`, MCP agent `8003`.
- [ ] Vendor Exercise A and B into subdirs (Person 1 does this, see step P1.0).
- [ ] **Commit the envelope module FIRST** before any agent logic ships (assignment's explicit version-control rule).

### Target repo layout

```
/exercise-a-rag/        # vendored from local-mode-code-Viraj (frozen, do not refactor)
/exercise-b-mcp/        # vendored from Team/ExerciseB-Variant2 (frozen, do not refactor)
/envelope/              # shared Pydantic envelope module
/registry/              # FastAPI registry service
/orchestrator/          # FastAPI orchestrator + SQLite state store
/agents/
  /rag-agent/           # A2A wrapper around exercise-a-rag
  /mcp-agent/           # A2A wrapper around exercise-b-mcp
/observability/         # JSON log sink + query helper
/docs/
  topology-decision.md
  observability-walkthrough.md
  failure-modes.md
docker-compose.yml      # or Makefile — one-command boot
README.md
PLAN.md                 # this file
```

---

## Person 1 — Platform & Registry

Owns: vendoring, envelope, registry, transport helpers, one-command boot, top-level README.

### P1.0 — Vendor A and B (do this first, then push so others can pull)
```bash
git checkout Team/ExerciseC-ScenarioA
git fetch origin
git checkout origin/local-mode-code-Viraj -- .
# move whatever was pulled into ./exercise-a-rag/  (adjust paths as needed)
git checkout origin/Team/ExerciseB-Variant2 -- .
# move into ./exercise-b-mcp/
git add exercise-a-rag exercise-b-mcp
git commit -m "vendor exercise A and B into exercise-c workspace"
git push
```

### P1.1 — Envelope module (FIRST commit with real code)
- [x] `envelope/__init__.py` — Pydantic `Envelope` with: `correlation_id`, `causation_id`, `idempotency_key`, `sender`, `recipient`, `capability`, `payload`, `timestamp`.
- [x] One-line docstring per field.
- [x] Helper: `Envelope.reply_to(prev, payload)` that propagates correlation_id and sets causation_id.
- [x] Commit: `feat(envelope): typed message envelope`

### P1.2 — Registry service (`registry/`, port 8000)
- [x] `POST /register` — body: name, capabilities[], endpoint, health_url.
- [x] `DELETE /deregister/:name`.
- [x] `GET /agents?capability=...` — filter by capability.
- [x] `GET /health` — own health + aggregated per-agent.
- [x] Heartbeat: agents PUT `/heartbeat/:name` every 10s; entries TTL after 30s.
- [x] Persist agent table in memory (dict is fine; document the choice).
- [x] Commit: `feat(registry): register/deregister/query/health + TTL`

### P1.3 — Shared HTTP client (`envelope/client.py` or `common/`)
- [x] `send(envelope, endpoint, timeout=5)` — POSTs envelope, returns reply envelope.
- [x] Auto-retry once on timeout, **reuse same idempotency_key**.
- [x] Inject correlation/causation if missing.

### P1.4 — One-command boot
- [x] `docker-compose.yml` OR `Makefile` (`make up`) that starts: registry, orchestrator, rag-agent, mcp-agent.
- [x] `requirements.txt` per service.

### P1.4b — Port helper scripts (`scripts/`)
- [x] `scripts/check-ports.sh` — checks 8000/8001/8002/8003. For each, prints `FREE` or `IN USE by PID <n> (<process name>)`. Exits non-zero if any are taken. Use `lsof -nP -iTCP:<port> -sTCP:LISTEN`.
- [x] `scripts/free-ports.sh` — lists what's on each port, prompts `Kill these? [y/N]`, then `kill <pid>` (SIGTERM, not -9 unless retry needed).
- [x] Make both executable (`chmod +x`). Document in README under "Troubleshooting".
- [x] Wire `check-ports.sh` into the Makefile's `up` target as a precondition.
- [x] Commit: `feat(scripts): port check + free helpers — P1.4b done`

### P1.5 — README.md
- [x] Scenario + why each agent has a unique job (Person 2 contributes their paragraph).
- [x] Envelope spec (paste field defs verbatim, one sentence each).
- [x] Setup: `pip install -r requirements.txt` per service OR `docker compose up`.
- [x] Run: one command.
- [x] Mermaid sequence diagram of happy path.

---

## Person 2 — Agents (RAG + MCP wrappers)

Owns: the two business agents. Wrap A and B; do NOT modify them.

### P2.1 — RAG agent (`agents/rag_agent/`, port 8002)
- [x] FastAPI app. On startup → POST to registry with capability `answer-from-corpus`.
- [x] On shutdown → deregister.
- [x] `POST /invoke` — accepts `Envelope`, extracts `payload.question`, calls into `exercise-a-rag`, returns reply `Envelope`.
- [x] `GET /health`.
- [x] Heartbeat task every 10s.
- [x] Idempotency: in-memory LRU(1000) on `idempotency_key` → cached reply.
- [x] Commit: `feat(rag-agent): A2A wrapper for exercise A`

### P2.2 — MCP agent (`agents/mcp_agent/`, port 8003)
- [x] FastAPI app. Capability `propose-radar-change`.
- [x] `POST /invoke` — accepts `Envelope`, calls into `exercise-b-mcp` (Variant 2 server) to edit the radar.
- [x] Same lifecycle (register/deregister/heartbeat) and idempotency dedupe.
- [x] Commit: `feat(mcp-agent): A2A wrapper for exercise B`

### P2.3 — Smoke test
- [x] Script that boots registry + both agents and round-trips one envelope to each. No orchestrator yet. (`python -m agents.smoke_test`)

### P2.4 — README contribution
- [x] One paragraph: what each agent does that the other can't (composition honesty).

---

## Person 3 — Orchestrator, Observability, Failure Handling

Owns: the brain, the trace, the chaos story, and three docs.

### P3.1 — Orchestrator (`orchestrator/`, port 8001)
- [x] FastAPI + SQLite (`orchestrator/state.db`).
- [x] Table `workflows(correlation_id, step, status, last_envelope_json, created_at, updated_at)`.
- [x] `POST /request` — entry point for user requests. Generates correlation_id.
- [x] Intent classifier: keyword first-pass (`"explain"|"what is"|"why"` → RAG; `"add"|"propose"|"change"` → MCP). If ambiguous, small LLM call. **Log the prompt and the chosen capability.**
- [x] Query registry by capability → pick endpoint → send envelope.
- [x] Persist state at every step; resume on restart.
- [x] Commit: `feat(orchestrator): SQLite-backed workflow engine`

### P3.2 — Failure handling
- [ ] Timeout: 5s per cross-agent call; on expiry, log + retry once with same idempotency_key.
- [ ] Max retries: 2; after that → poison.
- [ ] Dead-letter table `poison(correlation_id, envelope_json, reason, ts)`.
- [ ] Partial completion: workflow status field `pending|in_progress|completed|failed|poisoned`. On orchestrator restart, resume any `in_progress`.

### P3.3 — Observability (`observability/`)
- [ ] Structured JSON logger (`structlog`). Every log line has `correlation_id`, `causation_id`, `sender`, `recipient`, `capability`, `event`.
- [ ] Logs flush to `observability/logs.ndjson`.
- [ ] `observability/query.py CORRELATION_ID` → prints timeline (sorted by ts) for that workflow.
- [ ] LLM-driven decisions log the **full prompt + response** alongside the chosen next step.

### P3.4 — Chaos test
- [ ] Script: start system, fire a request, kill RAG agent mid-flight, observe.
- [ ] Document outcome in `docs/failure-modes.md`.

### P3.5 — Docs
- [ ] `docs/topology-decision.md` — orchestration vs choreography, scored on cognitive load / blast radius / debuggability / latency / team-doubles-next-year.
- [ ] `docs/observability-walkthrough.md` — pick a real correlation_id, walk through logs, answer "why did X call Y" twice.
- [ ] `docs/failure-modes.md` — chaos test + anticipated failure modes.

### P3.6 — Demo recording
- [ ] ~3 min: happy path + chaos path. Host internally; link in README.

---

## Sequencing (so nobody blocks)

| Day | Person 1 | Person 2 | Person 3 |
|---|---|---|---|
| 1 | Vendor A+B, envelope, registry | Stub agents that just register + health | Stub orchestrator that registers + health |
| 2 | HTTP client helper, compose | Wire real A and B logic | Workflow engine + intent classifier |
| 3 | README + diagram | Smoke tests + composition paragraph | Failure handling, observability, chaos, docs, demo |

---

## How a teammate joins / picks up half the work

This section exists so any teammate (and their Claude session) can pick up partway through with **zero ambiguity** about what's done, what's next, and which files are authoritative. Follow it literally.

### Canonical sources of truth (memorize these)

| Thing | Where |
|---|---|
| Repo | https://github.com/Viraj-77/Ecolab---RAG-Assignment |
| Working branch (ALL Exercise C work goes here) | `Team/ExerciseC-ScenarioA` |
| Exercise A source (frozen, vendor only — do NOT pull from here again after P1.0) | branch `local-mode-code-Viraj` |
| Exercise B source (frozen, vendor only — do NOT pull from here again after P1.0) | branch `Team/ExerciseB-Variant2` |
| Plan + progress tracker | `PLAN.md` (this file) — checkboxes are authoritative |
| Conventions reference | `envelope/`, `README.md` |

**Rule:** the only branch anyone commits to is `Team/ExerciseC-ScenarioA`. Never commit to `local-mode-code-Viraj` or `Team/ExerciseB-Variant2`. Never re-vendor A or B after P1.0 is done — the copies under `exercise-a-rag/` and `exercise-b-mcp/` are now the canonical versions.

### Step 1 — First-time clone (run once per machine)

```bash
git clone https://github.com/Viraj-77/Ecolab---RAG-Assignment.git
cd Ecolab---RAG-Assignment
git fetch --all
git checkout Team/ExerciseC-ScenarioA
git pull origin Team/ExerciseC-ScenarioA
```

Verify you have the latest:
```bash
git log --oneline -5            # see the most recent commits
git status                       # should say: nothing to commit, working tree clean
ls                               # should show PLAN.md, envelope/, registry/, etc. depending on progress
```

### Step 2 — Before EVERY work session (even if you cloned 5 minutes ago)

```bash
git checkout Team/ExerciseC-ScenarioA
git pull --rebase origin Team/ExerciseC-ScenarioA
```

If `git pull --rebase` fails because you have uncommitted local changes:
```bash
git stash
git pull --rebase origin Team/ExerciseC-ScenarioA
git stash pop
```

**Never skip this step.** Skipping it is how teammates overwrite each other.

### Step 3 — Figure out what to work on

1. Open `PLAN.md`.
2. Find your assigned Person section (Person 1 / 2 / 3).
3. The first `[ ]` (unchecked box) under your section is your next task. Tasks must be done in order within a section.
4. If your section is fully `[x]`, look across at other sections — help finish whoever's behind, but **announce in your team chat first** so two people don't grab the same task.

### Step 4 — Tell your Claude exactly what to do

Paste this **verbatim** into a fresh Claude Code session, replacing `N` with your person number:

> I am working on Exercise C of the Ecolab A2A bootcamp.
>
> Repo: https://github.com/Viraj-77/Ecolab---RAG-Assignment
> Branch: `Team/ExerciseC-ScenarioA` (the only branch we commit to)
> My role: **Person N**
>
> Before doing anything else:
> 1. Run `git checkout Team/ExerciseC-ScenarioA && git pull --rebase origin Team/ExerciseC-ScenarioA`.
> 2. Read `PLAN.md` end-to-end.
> 3. Read `README.md` if it exists, and skim `envelope/` to learn the conventions already in use.
> 4. Run `git log --oneline -20` to see what teammates have already shipped.
>
> Then:
> - Find the first unchecked `[ ]` task under "Person N" in `PLAN.md`. That is your starting point.
> - Do **not** redo any task that is already `[x]`.
> - Do **not** modify files outside Person N's owned folders unless `PLAN.md` says to (Person 1 owns `envelope/`, `registry/`, compose/Makefile, top-level README; Person 2 owns `agents/`; Person 3 owns `orchestrator/`, `observability/`, `docs/`). The vendored `exercise-a-rag/` and `exercise-b-mcp/` are read-only for everyone.
> - After each completed task: edit `PLAN.md` to tick the box, commit, and push immediately (see the commit/push block in PLAN.md).
> - If `PLAN.md`, the existing code, and your instinct disagree, `PLAN.md` wins — ask me before deviating.

### Step 5 — Commit and push after EVERY completed task

Do not batch. Push as soon as one checkbox is done, so teammates see your work fast and conflicts stay tiny.

```bash
# 1. Tick the box you just finished in PLAN.md (edit the file).
# 2. Stage only the files you touched + PLAN.md:
git add PLAN.md <the/files/you/changed>

# 3. Commit with a clear scope tag:
git commit -m "feat(<scope>): <what you did> — P<N>.<task> done"
# examples:
#   feat(envelope): typed message envelope — P1.1 done
#   feat(registry): register/deregister/query/health + TTL — P1.2 done
#   feat(rag-agent): A2A wrapper for exercise A — P2.1 done

# 4. Push to the shared branch:
git push origin Team/ExerciseC-ScenarioA
```

Tell your team in chat: *"Pushed P1.2. Pull before you start."*

### Step 6 — Handling conflicts

If `git push` is rejected because someone pushed first:

```bash
git pull --rebase origin Team/ExerciseC-ScenarioA
# If conflicts: open the marked files, resolve, then:
git add <conflicted-files>
git rebase --continue
git push origin Team/ExerciseC-ScenarioA
```

Conflict in `PLAN.md` checkboxes? **Keep both ticks** (you each completed something). Conflict in code outside your owned folders? You probably edited something you shouldn't have — revert it with `git checkout --theirs <file>` and let the owner finish their work.

### Step 7 — Sanity checks before you stop for the day

```bash
git status                        # should be clean
git log --oneline origin/Team/ExerciseC-ScenarioA..HEAD   # should be empty (everything pushed)
```

If either shows pending stuff, push or stash before closing your laptop.

### Quick reference card

| Situation | Command |
|---|---|
| Start the day | `git pull --rebase origin Team/ExerciseC-ScenarioA` |
| See teammates' recent work | `git log --oneline -20` |
| Finished a task | tick `PLAN.md`, `git add … && git commit -m "feat(...): … — PN.X done" && git push` |
| Push rejected | `git pull --rebase` → resolve → `git push` |
| Don't know what to do | first unchecked `[ ]` in your Person section in `PLAN.md` |
| Need to see what changed | `git diff origin/Team/ExerciseC-ScenarioA` |
| Accidentally on wrong branch | `git checkout Team/ExerciseC-ScenarioA` (commit or stash first) |

### Anti-patterns that cause file mismatches (don't do these)

- ❌ Committing to `local-mode-code-Viraj` or `Team/ExerciseB-Variant2`. Both are frozen sources.
- ❌ Modifying files inside `exercise-a-rag/` or `exercise-b-mcp/`. Wrap them, don't edit them.
- ❌ Working on `main`. We never touch `main` in this exercise.
- ❌ Long-lived local branches. Push to `Team/ExerciseC-ScenarioA` at least daily.
- ❌ Editing files outside your Person section without coordinating.
- ❌ `git push --force` to the shared branch. Never. If you think you need it, ask the team first.
- ❌ Skipping the PLAN.md tick. Other people (and other Claudes) rely on it to know what's done.

---

## Definition of done (rubric self-check)

- [ ] 3 agents up, registry queryable, scenario runs end-to-end (20%)
- [ ] Envelope consistent everywhere; correlation/causation/idempotency keys actually used (20%)
- [ ] Topology decision documented and defended (15%)
- [ ] "Why did X call Y" answerable from logs alone for any correlation_id (15%)
- [ ] Timeouts + retries-with-idempotency + partial-completion + poison-message all addressed; ≥1 chaos test recorded (15%)
- [ ] Each agent does something the others can't (10%)
- [ ] Modular code, one-command setup, clean commits (5%)
