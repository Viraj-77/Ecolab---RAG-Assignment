# When to Go Local — Decision Document

## Recommended Scenario

I recommend local RAG for an Ecolab-adjacent plant-floor SOP and sustainability-document assistant used by field technicians or plant operators.

In this scenario, technicians need to search approved internal PDFs such as SOPs, sustainability guidelines, safety notes, water-treatment procedures, and water-neutrality documents at customer sites where internet connectivity may be unreliable and customer documents should remain on-device.

This is not a recommendation to use local models everywhere. It is specifically for private, offline, document-grounded retrieval.

---

## Profiles Compared

| Profile | LLM | Embedding | Vector DB |
|---|---|---|---|
| Local | Ollama `gemma3n:e4b` | Ollama `nomic-embed-text` | ChromaDB |
| Azure | Azure `gpt-5.4-nano` | Azure `text-embedding-3-small` | ChromaDB |

---

## Axes Scored

The comparison used these axes:

1. Answer correctness
2. Citation quality
3. Refusal correctness
4. Tool-calling reliability
5. Latency p50 and p95
6. Token throughput
7. Privacy posture
8. Offline capability
9. Cost per 1k requests
10. JSON/tool reliability

The local Ollama output generation rate was measured at **46.79 tokens/s**.

---

## Where Local Won

Local mode won on:

- Offline capability
- Privacy posture
- No per-request LLM API cost
- Keeping sensitive documents on-device
- Good enough document-grounded Q&A

These wins are load-bearing for plant-floor and customer-site environments because connectivity may be restricted, customer documents may be sensitive, and field users may need access even when cloud services are unavailable.

---

## Where Local Lost

Local mode lost on:

- Tool-calling reliability
- Strict JSON output
- Complex reasoning
- Latency consistency
- Long-context synthesis

The selected local model `gemma3n:e4b` did not support OpenAI-style tool calling through Ollama. This is acceptable for the recommended local use case because the main task is offline document Q&A, not live API orchestration.

---

## Where Azure Won

Azure mode performed better for:

- Tool calling
- Live USGS water-quality queries
- Structured output
- Complex reasoning
- Instruction following
- More reliable response formatting

Azure is better when the assistant needs live tools, strong reasoning, strict JSON, or production-grade function-calling reliability.

---

## Recommendation

Use local mode for offline/private document retrieval at plant-floor or customer-site environments.

Use Azure mode for connected environments where tool calling, live data, structured output, and higher reasoning quality are required.

The recommended architecture is a profile-switchable RAG system:

```text
Local mode → offline document Q&A
Azure mode → connected, tool-heavy workflows