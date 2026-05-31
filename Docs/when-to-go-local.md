# When to Go Local — Decision Document

**Scope:** one-page recommendation, written for a peer architect, on whether to deploy this RAG agent on a local Gemma 3n + Ollama stack instead of the Azure OpenAI baseline. Grounded in the 24-query comparison run in [`local-mode-comparison.md`](./local-mode-comparison.md).

## Recommended scenario for "go local"

**Plant-floor SOP retrieval on an air-gapped Windows tablet at a customer food-processing site, used by Ecolab field service technicians during sanitation rounds.**

- Customer sites frequently restrict outbound traffic from operator floor — anything that needs Azure cannot be relied on.
- The information needed is **almost entirely document-grounded** (CIP procedures, sanitizer dilution charts, allergen-changeover SOPs, regulatory references). Live external lookups are a small minority of queries.
- Single-user, infrequent — interactive latency in the 5–10 s range is acceptable when the alternative is "tech walks back to the truck to use a phone."

This is **not** a recommendation for the broader Ecolab assistant deployment, internal employee tools, or anything customer-facing on the web — there, cloud wins on most named axes.

## Named axes (lifted from the comparison run)

| Axis | Local (`gemma3n:e4b`) | Cloud (`gpt-5.4-nano`) | Load-bearing for the recommendation? |
|---|---|---|---|
| **Privacy / data residency** | Fully on-device. No customer doc ever leaves the tablet. | Customer SOPs traverse Azure. | **YES — load-bearing** |
| **Offline capability** | Works with WiFi disabled. | Hard-fails. | **YES — load-bearing** |
| **Pure-RAG correctness** | 1.67 / 2 mean | 2.00 / 2 mean | Acceptable gap — local gives complete-or-partial-but-not-wrong; partial still gets the tech to the right page |
| **Function calling / live data** | Structurally zero (Ollama refuses tools on `gemma3n`) | 17/18 correct decisions | Accepted — SOPs don't need live USGS data |
| **Adversarial / prompt-injection robustness** | 5/6 (leaked partial system prompt on Q22) | 6/6 | Tolerable in a controlled tablet UI; still flagged |
| **Latency p50 / p95** | 6.46 / 11.37 s | 6.11 / 9.52 s | Closer than expected; acceptable |

## One axis where I'd want more data before committing

**Retrieval quality on the actual SOP corpus, not the generic water-management corpus used in this run.** Q13/Q17/Q18 all looked like retrieval misses, not generation failures — `nomic-embed-text` at 768-dim with 1500-char chunks didn't put the right passage in top-4 for some questions. SOPs are highly structured (numbered steps, rigid templates) which may either help retrieval (high lexical signal) or hurt it (passage embeddings that look uniformly similar). I'd want to:

1. Re-index a representative slice of real SOPs.
2. Re-run a 30–50 query SOP-specific eval.

If retrieval recall on SOP-grounded queries falls below ~80% on top-4, the recommendation flips to "ship a hybrid: local for full offline mode, cloud for online mode, env-var-switched at startup based on connectivity check."

## Summary

- **Recommend local** for the air-gapped field-tech SOP-retrieval scenario — privacy and offline are load-bearing, the quality gap is acceptable for the in-scope workload.
- **Do not recommend** local for the general Ecolab assistant, customer-facing chat, or anything that needs live data or strong tool calling. Cloud wins on those axes by a large enough margin that ignoring it would be advocacy, not analysis.
- **One open question**: retrieval quality on real SOPs. The cost of getting it wrong (techs miss safety-critical steps) is high enough that I would not ship without that follow-up evaluation.
