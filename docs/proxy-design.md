# Proxy Design — Why `RadarProxy` is shaped this way

The Variant 2 framework asks: *why this proxy, not another?* Below are the
four decisions that drove `mcp-server/src/proxy.py`, each defended against the
obvious alternative.

## 1. Why a proxy class instead of logic in tool definitions?

The naive baseline (see `baseline-n-tool.md`) puts one MCP tool per operation,
and each tool's handler reaches into the radar JSON directly. That spreads the
domain rules — *"a tech may not be assigned twice to a team"*, *"ADOPT requires
a link"*, *"ADOPT↔HOLD must pass through TRIAL or ASSESS"* — across seven
handlers that have no shared call site. Refactoring a rule means hunting
through tool code.

`RadarProxy` collects those rules in one Python class. The two MCP tools
(`search`, `execute`) are thin: they accept a string of Python, hand it to
the sandbox, and let the model script the proxy. The validation, the working
copy, the `is_dirty` bookkeeping all live with the data they protect, not in
the wire layer. When a rule changes (e.g. adding a new ring transition
constraint) we touch one validator and every tool sees it.

## 2. Why Pydantic v2 instead of JSON Schema or plain text?

Pydantic v2 models are simultaneously: (a) the on-disk schema validator for
`radar_working.json`, (b) the runtime type for the proxy methods, (c) the
DSL the model reads in the tool description. JSON Schema gives us only (a),
and at the cost of repeating every enum across every tool that references it
(see the `Ring` repetition in `baseline-n-tool.md`). Plain-text descriptions
give the model the most compact bootstrap but lose the parser — invalid input
to `add_technology` crashes deep inside the proxy instead of at the boundary
with a structured error.

Pydantic also pays the smallest token bill for the metamodel. The Quadrant /
Ring / Moved enums are printed *once* in the `search` tool description as a
plain block:

```
Quadrant: 0=Models, 1=Infrastructure, 2=Frameworks, 3=Techniques
Ring: 0=ADOPT, 1=TRIAL, 2=ASSESS, 3=HOLD
Moved: -1=down, 0=unchanged, 1=up
```

The model reads them from there; the runtime parses them via Pydantic; the
JSON file conforms to them via the same `Radar` model. One source, three
consumers.

## 3. Why split into `search()` and `execute()` instead of one tool?

The split is cheap insurance against accidental mutation during introspection.
The model often writes exploratory code — *"how many techs are in quadrant 0
right now?"* — and a single tool would let it slip a `radar.assign(...)`
into a "read-only" prompt without anyone noticing until commit. Splitting the
sandbox surfaces (`_ReadOnlyRadar` for `search`, full `RadarProxy` for
`execute`) means the proxy *enforces* read-only at the language level: any
write call raises `"search is read-only. '...' is not available. Use
execute() to make changes."`

The cost of the split is one extra tool description (~270 tokens). The
benefit is a hard wall between query-path and write-path, plus a clear
human-readable signal in the trace for which calls intended to mutate.

## 4. Why `radar_working.json` instead of writing to `ecolab-radar-config.json`?

`ecolab-radar-config.json` (path noted in `PLAN.md`; the assignment brief
calls this file `docs/config.json`) is the source-of-truth radar — the file
that other systems may read and that we must never silently corrupt during
development or testing. On first server start, `radar_store.load_radar()`
copies it to `mcp-server/radar_working.json`; from that point on, every read
and every `commit()` goes to the working copy. The original is byte-identical
after a full test pass (verified in `docs/raw-traces.txt`, smoke test 3).

This separation is what lets us run misuse traces, accept dirty intermediate
states, and `rm radar_working.json` to reset — without ever touching the
file other systems depend on. Pushing changes back to the canonical radar is
a deliberate human step (a PR), not a side-effect of running the MCP server.

---

The shape that emerges — read methods + write methods + a single `commit()`
+ a working-copy persistence layer — is exactly what the framework's
`DomainProxy` interface prescribes. The names map to radar concepts
(`add_technology`, `assign`, `move`), validation lives in the proxy, and the
tool layer disappears into a 2-tool surface measured at 485 tokens (vs the
1,300-token N-tool baseline).
