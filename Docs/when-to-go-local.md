# When to Go Local — Decision Document

**Author:** K, Ajay Kumar · **Date:** 2026-06-03  
**Audience:** Peer architect / bootcamp lead  
**Scenario under analysis:** Plant-floor SOP retrieval assistant for an Ecolab water treatment facility in an air-gapped or intermittently-connected industrial environment

---

## The Scenario

Ecolab field technicians at a water treatment plant need to look up standard operating procedures (SOPs), chemical dosing tables, and alarm response guides while on the plant floor. The plant has:

- **Intermittent or no internet connectivity** (common in older industrial facilities with OT/IT segmentation).
- **Privacy and data sovereignty constraints** — SOPs often contain proprietary process details Ecolab does not want leaving the facility network.
- **Real-time sensor data** available on the plant LAN (OT historian or SCADA API), but not via public internet.
- **Ruggedized tablets or panel PCs** (Intel NUC or similar) with 16+ GB RAM but no dedicated GPU.

The agent must answer questions like: *"What is the chlorine dosing protocol for high-turbidity inflow above 5 NTU?"* or *"What alarm response does SOP-42 prescribe for dissolved oxygen below 3 mg/L?"*

---

## Named Axes Scored

| Axis | Local (gemma3n:e4b) | Cloud (gpt-5.4-nano) | Load-bearing? |
|---|---|---|---|
| **Offline capability** | ✅ Fully offline after initial pull | ❌ Network required for every call | **Yes — defining constraint** |
| **Data privacy / sovereignty** | ✅ Nothing leaves the device | ❌ Query + corpus excerpts sent to Azure | **Yes — OT security policy** |
| **Latency p50** | ⚠️ 11 s (CPU, no GPU) | ✅ 1.6 s | No — tolerable for SOP lookup |
| **Output quality (RAG)** | 3.4/4 | 3.8/4 | No — delta acceptable for factual SOP queries |
| **Tool call reliability** | ✅ 10/10 (prompt-based JSON) | ✅ 10/10 (native API) | Neutral — both work |
| **Prompt injection resistance** | ❌ Failed adv-02 | ✅ Passed all adversarial | **Yes — safety concern** |
| **Context window** | ⚠️ ~8k tokens (Q4_K_M effective) | ✅ 128k tokens | Partial — SOPs are typically short (<2k tokens) |
| **Cost per 1,000 requests** | ~$0 (inference hardware amortized) | ~$0.15 (gpt-5.4-nano at $0.15/1M out) | No — cost not load-bearing at this scale |
| **Setup complexity** | ⚠️ Ollama + model pull required | ✅ API key + endpoint | No — one-time setup |
| **Hardware dependency** | ⚠️ Requires ≥16 GB RAM | ✅ No local compute required | Partial — most industrial PCs meet this |

---

## Recommendation: **Go local for this scenario**

The two load-bearing axes — **offline capability** and **data privacy** — both favour local, and neither can be compensated by any cloud feature.

The plant operates behind an OT/IT firewall where outbound HTTPS to Azure is blocked on the OT segment by design. A cloud RAG agent either fails completely during network brownouts or requires a network hole that violates the facility's security architecture. The local agent runs on the panel PC and answers from the indexed SOP corpus whether or not the WAN is up.

Privacy is equally load-bearing: SOPs contain proprietary chemical concentrations, equipment vendor details, and process timing that Ecolab classifies as confidential IP. Sending those in every API request — even to Ecolab's own Azure tenant — creates a data residency and logging risk that legal will not accept without additional contracts and encryption controls. Local inference eliminates the risk at the source.

---

## What Local Loses — Accepted Trade-offs

**Latency (11 s p50):** SOP lookup on a plant floor is not a real-time operation. A technician pulling up an alarm response procedure can wait 10–15 seconds. This is not acceptable for a streaming dashboard but is fine for a text query interface. *Accepted.*

**Prompt injection safety (adv-02 failure):** The local model failed a direct injection attack. For an internal SOP assistant where the only user population is authenticated plant personnel, the attack surface is lower than a public-facing product. However, this must be mitigated: validate that model responses never echo raw user input verbatim, and add a thin post-processing check that strips any line not present in the SOP corpus. *Accepted with mitigation.*

**Smaller context window:** Full SOP documents can be long. At 128-token chunks with 4 retrieved chunks, the model gets ~512 tokens of context per query. Longer SOPs may require increasing k to 8 or using a multi-turn retrieval pattern. *Accepted with configuration adjustment.*

---

## Where Local Won and That Win Was Load-Bearing

**Offline reliability:** During a network outage at a water treatment plant, operators cannot safely halt operations to wait for connectivity. The local agent answered 20/20 test queries from corpus alone with no network dependency. For this scenario, uptime during outages is not negotiable.

**Zero-exfiltration by construction:** Unlike a cloud solution where network audits and DLP rules need to be maintained, the local agent provably does not transmit corpus data. For facilities under CFATS, SOC 2 supply-chain audit, or Ecolab customer NDA requirements, this is a structural advantage, not a configuration.

---

## One Axis Where I Would Want More Data Before Committing

**Latency on actual plant hardware.** The 11 s p50 was measured on an Apple M1 Pro with Metal (GPU) acceleration. Intel NUC-class hardware (Core i7, no discrete GPU, 16 GB DDR4) runs `gemma3n:e4b` purely on CPU — early benchmarks suggest 30–45 s p50 on comparable x86 hardware. At 40 s, the SOP assistant becomes frustrating to use during an active alarm. Before committing to this architecture I would want:

1. A 30-query latency benchmark on the actual panel PC model deployed at the target facility.
2. If p50 exceeds 30 s, evaluate whether `gemma3:1b` (lower quality but 4–5× faster) meets the minimum quality bar for factual SOP lookup. The quality regression is real (~15% lower correctness in internal sweep) but may be acceptable if latency drops to under 10 s.

---

*This document covers one specific Ecolab scenario. Other scenarios (field-tech tablet with LTE but no GPU → different trade-off; cloud-connected lab with no OT constraints → cloud wins) would change the scoring on offline and privacy axes and likely reverse the recommendation.*
