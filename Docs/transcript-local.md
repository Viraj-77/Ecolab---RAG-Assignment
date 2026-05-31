# Example Transcript — Local Profile (Q16, combined)

**Profile**: `LLM_PROFILE=local`
**Model**: `gemma3n:e4b` via Ollama
**Embedder**: `nomic-embed-text` (768-dim)
**Collection**: `ecolab_corpus_local` (1742 chunks)
**Tools enabled**: `False` (gemma3n:e4b does not support tools at the Ollama API layer)
**Wall-clock latency**: 11.17 s
**Output tokens**: 276 (24.7 tok/s)

---

### User

> Explain what turbidity tells us about water quality (per the documents) and pull current turbidity values for California to illustrate.

### Retrieval (top-4 from `ecolab_corpus_local`)

Chunks surfaced from `pdf1.pdf` and the framework PDF — all on turbidity definitions, distribution-system causes, NTU thresholds, and consumer acceptability. (No California-specific live data is in the corpus, by design — that's the tool's job.)

### Tool call

**None.** Tools are not passed to the model on this profile. The agent is RAG-only and instructed to refuse questions that require live data.

### Assistant (final answer)

> According to the provided documents, turbidity describes the cloudiness of water caused by suspended particles like clay, silt, chemical precipitates, organic particles, and organisms.
>
> Here's what turbidity tells us about water quality:
>
> * **Poor source water quality and inadequate treatment** can cause high turbidity.
> * **Disturbance of sediments and biofilms** within the distribution system or the ingress of dirty water during breaks can also increase turbidity.
> * **High turbidity** can lead to staining of materials, fittings, and clothes, and it can interfere with the effectiveness of treatment processes.
> * **Visible turbidity** reduces the acceptability of drinking water, as consumers often associate it with a lack of safety.
> * Large municipal supplies should consistently produce water with no visible turbidity and be able to achieve a maximum of 0.5 NTU before disinfection, with an average of 0.2 NTU or less. However, smaller supplies may not be able to meet these levels.
> * While most particles contributing to turbidity have no health significance, turbidity can indicate the presence of hazardous chemical and microbial contaminants.
> * Any unexpected increase in turbidity should be investigated as it could reflect significant faults or breaches in distribution systems.
>
> The provided documents do not contain current turbidity values for California. Therefore, I cannot fulfill the request to pull those values.

### Notes (manual scoring)

- **Correctness**: 1 — strong on the corpus half, missing the live half (structural).
- **Citation**: 1 — clearly grounded in the framework / WHO guidance language.
- **Tool decision**: 0 — expected a tool call; structurally cannot fire.
- **Style**: long, cautious, ends with an explicit refusal of the live-data half.
