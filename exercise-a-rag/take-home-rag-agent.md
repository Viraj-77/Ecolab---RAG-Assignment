# Take-Home Assignment: AI Agent with RAG and Tool Calling

| | |
|---|---|
| **Author** | Thijs Hakkenberg — AI Innovation & Research |
| **Last Updated** | 2026-04-18 |
| **Version** | 1.0 |
| **Audience** | MTech interns, bootcamp trainees |
| **Related Epic** | [AI Talent Development — 1018669](https://dev.azure.com/Ecolab/LLM-Capability-Build_office/_workitems/edit/1018669) |
| **Tenet** | Education |
| **Status** | Active — Exercise 1 released; Exercises 2–3 planned |

---

## Overview

Ecolab is exploring intelligent agents that assist decision-making in water treatment, hygiene, and sustainability. Your task is to build a **function-calling AI agent** that combines:

- **Retrieval-Augmented Generation (RAG)** over publicly available unstructured data.
- **Structured tool/API calling** against a public API relevant to Ecolab's business domain.
- **A simple chat interface** for natural-language interaction.

This assignment is delivered in **phases**. You will complete them in order; later phases build on earlier ones.

| Phase | Focus | Status |
|---|---|---|
| **Exercise 1** | Python RAG + function-calling agent (local, no frameworks) | **IN SCOPE — start here** |
| Exercise 2 | Deploy on a free hosting platform (Cloudflare, Vercel, Fly.io, …) | Future — released after Exercise 1 feedback |
| Exercise 3 | Production readiness (observability, IaC, architecture diagram, CI/CD) | Future |

## Learning Objectives

By the end of Exercise 1 you will have hands-on understanding of:

1. How an LLM performs **retrieval-augmented generation** — chunking, embedding, vector search, prompt assembly.
2. How **OpenAI function calling** works at the raw-SDK level — tool schemas, the tool-call loop, merging tool results back into the conversation.
3. How an agent decides **when to retrieve, when to call a tool, and when to answer directly**.
4. Idiomatic, modular Python for a small-but-real AI system.

## Prerequisites

- **Python 3.11+** installed locally
- An **Azure OpenAI API key** (provided by your bootcamp lead — do **not** commit it)
- A **public Git repository** on GitHub, GitLab, or Bitbucket that you push to **from day one**. See [*Version Control Expectations*](#version-control-expectations) below — commit history is part of what we evaluate.
- Basic familiarity with REST APIs and terminal use

## Provided Infrastructure — Azure OpenAI

Your bootcamp lead will give you an **API key** for a shared Azure OpenAI endpoint we have provisioned on **Azure AI Foundry**. You do **not** need a personal OpenAI account.

The endpoint is fully compatible with the standard [`openai`](https://pypi.org/project/openai/) Python package — use the `AzureOpenAI` client.

| | |
|---|---|
| Endpoint | `https://cds-ds-openai-001-x.openai.azure.com/` |
| API version | `2024-12-01-preview` |
| Chat deployment | `gpt-5.4-nano` |
| Embedding deployment | `text-embedding-3-small` |
| API key | provided separately (load from `AZURE_OPENAI_API_KEY` env var) |

### Chat / tool calling

```python
import os
from openai import AzureOpenAI

client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint="https://cds-ds-openai-001-x.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

response = client.chat.completions.create(
    model="gpt-5.4-nano",  # pass the deployment name as `model`
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...],           # your function-calling tool schemas
)
```

### Embeddings — option A: Azure OpenAI (provided)

```python
import os
from openai import AzureOpenAI

client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint="https://cds-ds-openai-001-x.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

vector = client.embeddings.create(
    model="text-embedding-3-small",  # deployment name
    input="chunk text here",
).data[0].embedding
```

### Embeddings — option B: local SentenceTransformers

If you prefer to run embeddings locally (no API cost, fully offline after model download):

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # or any model you like
vectors = model.encode(["chunk text here"])
```

Pick **one** embedding approach and use it consistently for both ingestion and query — the embedding vectors must come from the same model.

> **Never commit the API key.** Load it from an environment variable or `.env` file, and ship a `.env.example` with placeholder values.

---

# Exercise 1 — Python RAG + Function-Calling Agent  *(IN SCOPE)*

## Goal

Build a working local agent in Python that:

1. Answers questions using an **unstructured corpus** you have indexed in ChromaDB.
2. Can **call a public API** when the question needs live/structured data.
3. **Combines** RAG context and tool-call results in a coherent response.
4. Supports **multi-turn chat** through a simple interface (CLI **or** Streamlit).

## Required Stack (Pinned)

This exercise is about learning the **primitives**. Orchestration frameworks like LangChain and LlamaIndex are great in production, but they hide the exact mechanics we want you to understand. You will use those later — not now.

| Layer | You MUST use | Not allowed |
|---|---|---|
| Language | Python 3.11+ | — |
| LLM + tool calling | [`openai`](https://pypi.org/project/openai/) SDK pointed at the Azure OpenAI endpoint we provide (via the `AzureOpenAI` client) | LangChain, LlamaIndex, Haystack, AutoGen, CrewAI, any agent framework |
| Vector store | **Any local vector store** — [`chromadb`](https://pypi.org/project/chromadb/) (recommended), [`faiss-cpu`](https://pypi.org/project/faiss-cpu/), [`lancedb`](https://pypi.org/project/lancedb/), or similar. Must run fully on your machine, with persistence on disk. | Managed / cloud vector DBs (Pinecone, Weaviate Cloud, Qdrant Cloud, etc.) |
| Embeddings | **Either** Azure OpenAI embeddings (`text-embedding-3-small`, provided) **or** local [`sentence-transformers`](https://pypi.org/project/sentence-transformers/) — pick one and stick with it | Third-party hosted embedding APIs (Cohere, Voyage, etc.) |
| Dependency manager | [`uv`](https://docs.astral.sh/uv/) **or** [`poetry`](https://python-poetry.org/) (pick one, document it) | Raw `pip` with no lock file |
| Chat interface | CLI **or** [`streamlit`](https://pypi.org/project/streamlit/) (your choice) | — |
| Secrets | [`python-dotenv`](https://pypi.org/project/python-dotenv/) or environment variables | Hard-coded keys |

Small helper libraries are fine — [`requests`](https://pypi.org/project/requests/), [`pydantic`](https://pypi.org/project/pydantic/), [`python-dotenv`](https://pypi.org/project/python-dotenv/), [`rich`](https://pypi.org/project/rich/), [`tiktoken`](https://pypi.org/project/tiktoken/), PDF parsers, etc. The restriction is on **agent/orchestration frameworks**, not on small utilities.

## Functional Requirements

### 1. Ingest an unstructured corpus

- Pick **at least 3–5 public documents** relevant to the Ecolab domain (water treatment, hygiene, sustainability). Examples: EPA environmental reports, WHO sanitation guidelines, scientific papers, public sustainability reports.
- Implement an `ingest.py` (or equivalent) that:
  - Loads the documents (PDF, HTML, or plain text).
  - Splits them into **chunks** with a sensible size and overlap — document your choice.
  - Generates embeddings via Azure OpenAI **or** a local SentenceTransformers model (your choice — see the snippets above).
  - Stores them in a **local, persistent vector store** (ChromaDB, FAISS with on-disk index, LanceDB, etc.) — you should be able to restart the agent without re-ingesting.

### 2. Retrieval

- On each user turn, retrieve the **top-k** most relevant chunks for the user's query.
- Inject them into the LLM prompt as context, clearly separated from the user's question.

### 3. Function / tool calling

- Define **at least one tool** using the OpenAI `tools=[...]` schema that calls a public API.
- Implement the **full tool-call loop**:
  1. Send the conversation + tool definitions to the model.
  2. If the model returns a `tool_call`, execute the actual HTTP request.
  3. Append the tool result to the conversation.
  4. Call the model again to produce the final user-visible answer.
- The agent must **reason about when to use the tool** — not call it on every turn.

### 4. Suggested public APIs (pick one)

| API | What it returns | Docs |
|---|---|---|
| **USGS Water Quality Portal** | Water quality measurements by location/parameter | https://www.waterqualitydata.us/webservices_documentation/ |
| **EPA Facility Registry Service (FRS)** | Regulated facilities, locations, programs | https://www.epa.gov/frs/frs-api |
| **OpenAQ** | Real-time and historical air quality data | https://docs.openaq.org/ |
| **CDC Environmental Public Health Tracking** | Environmental health indicators by US geography | https://ephtracking.cdc.gov/apihelp |

Pick the one that best complements your chosen corpus. You may add more tools if you wish.

### 5. Chat interface

- Multi-turn: the agent maintains conversation history within a single session.
- CLI is perfectly acceptable. Streamlit is also allowed if you prefer a browser UI.
- The interface should be runnable with a single command (e.g. `python chat.py` or `streamlit run app.py`).

## Explicit Non-Goals (do NOT do these)

| ❌ Not in scope | Why |
|---|---|
| Hosting / deployment | Exercise 2 |
| Authentication / user accounts | Exercise 3 territory |
| Persisting chat history across restarts | Keep it simple |
| UI polish beyond basic usability | Focus on the agent, not CSS |
| Multiple agents / agent-to-agent communication | Out of scope |
| Fine-tuning | Out of scope |
| Any framework abstractions (LangChain, LlamaIndex, etc.) | **The whole point is to learn the primitives** |

If you find yourself building a generic framework, stop and simplify.

## Deliverables

1. **A public Git repository** on GitHub, GitLab, or Bitbucket — **not a zip**. You should be committing and pushing from day one; we review commit history as well as final state.
2. **`README.md`** containing:
   - Tech stack and rationale (why you chose each piece within the pinned set).
   - Setup: how to install dependencies, set env vars, ingest the corpus.
   - How to run: one command to start the chat.
   - How to test.
3. **A 1–2 page write-up** (`docs/writeup.md` or similar) covering:
   - Key design decisions (chunking strategy, retrieval-k, prompt structure, when the agent decides to call the tool).
   - Trade-offs you made and why.
   - **How RAG and tool calling are combined** — be explicit about the control flow.
   - Known limitations and what you would do next.
4. **Example conversation transcripts** (2–3 short dialogues) demonstrating:
   - A question answered from RAG alone.
   - A question that triggers a tool call.
   - A question that combines both.

## Evaluation Rubric

| Criterion | What we look for | Weight |
|---|---|---|
| **Functionality** | Agent retrieves and combines data effectively; tool loop works end-to-end; multi-turn chat is coherent | 25% |
| **Code quality & engineering process** | Modular design, clear file/module structure of your own making, documented, typed; no dead code; secrets handled correctly; lockfile committed; **commit history shows incremental, meaningful work** with clear messages from day one | 20% |
| **Reasoning** | Clear judgment about when to retrieve vs call a tool vs answer directly; prompt design reflects intent | 20% |
| **Creativity & business relevance** | Corpus + API choice is thoughtful and connected to Ecolab's domain | 15% |
| **Presentation** | README is clear enough that a stranger can run your agent in under 10 minutes; write-up is concrete | 20% |

Total: **100%**. Passing bar: ≥ 70%.

We want to see **your** design — how you structure modules, name things, and split responsibilities. Don't look for a template to copy.

## Submission

- Share your **public repository URL** with your bootcamp lead. We pull the head of your default branch at the deadline — there is no zip/archive submission.
- Your `README.md` must include your **name** and **cohort identifier** at the top.
- The repository must be public from the start so we can see history — not a single squashed commit dropped in at the end.
- Deadline: communicated separately by your bootcamp lead.

## Version Control Expectations

Commit history is a signal of how you work, so we review it alongside the final code. Concretely:

- **Commit from day one.** Push your `README.md` skeleton and `pyproject.toml` / lockfile early, before any functional code is written.
- **Small, meaningful commits** beat one enormous end-of-project commit. Each commit should express a single idea or change and leave the repo in a working state where reasonable.
- **Clear commit messages.** Use the imperative mood and a concise one-line summary — e.g. `Add PDF loader for EPA report corpus`, `Wire USGS tool into agent loop`, `Fix chunk overlap off-by-one`.
- **Branches** are optional for a solo project; a linear history on `main` is fine.

### Never commit secrets

This is the most common way trainees lose points. Your repository is public, so anything you push is world-readable.

- Add a `.gitignore` **before your first commit**. At minimum, exclude: `.env`, any file containing an API key, local caches (`__pycache__/`, `.venv/`), and vector-store data directories (`chroma_db/`, `*.lance/`, `*.faiss`, etc.).
- Ship a `.env.example` with placeholder values so others know which variables are needed.
- Load the Azure OpenAI key **only** from an environment variable (or `.env` loaded via [`python-dotenv`](https://pypi.org/project/python-dotenv/)). Never hard-code it, never print it, never include it in logs or screenshots.
- If you accidentally commit a secret: **tell your bootcamp lead immediately** so we can rotate the key, then clean your git history. Deleting the file in a later commit does **not** remove it — the secret stays in history and must be purged with `git filter-repo` or by rewriting/rebasing.

---

# Exercise 2 — Hosting & Deployment  *(Future)*

Once Exercise 1 is graded and reviewed, you will extend your local agent into a hosted web service on a **free-tier platform** — candidates include Cloudflare Workers/Pages, Vercel, Fly.io, Railway, or Hugging Face Spaces. You will learn about cold starts, secret management in serverless environments, and the trade-offs between edge and origin compute.

*Exercise 2 brief will be released after Exercise 1 feedback is returned.*

---

# Exercise 3 — Production Readiness  *(Future)*

A production-grade version layers in: **observability** (structured logging, traces, token/latency metrics), **Infrastructure as Code** (Terraform or Docker Compose), a **system architecture diagram**, CI/CD, and basic evaluation harnesses. You will pick a subset to implement, not everything.

*Exercise 3 brief will be released after Exercise 2.*

---

## Appendix

### Grading Criteria Summary

| Criterion | Weight |
|---|---|
| Functionality | 25% |
| Code quality | 20% |
| Reasoning | 20% |
| Creativity & business relevance | 15% |
| Presentation | 20% |

### Resources

**Azure OpenAI**
- Using the `openai` Python SDK with Azure — https://learn.microsoft.com/azure/ai-services/openai/how-to/switching-endpoints
- Function calling guide — https://platform.openai.com/docs/guides/function-calling
- Embeddings guide — https://platform.openai.com/docs/guides/embeddings

**Python packages** (PyPI)
- [`openai`](https://pypi.org/project/openai/)
- [`chromadb`](https://pypi.org/project/chromadb/) — [quickstart](https://docs.trychroma.com/getting-started)
- [`faiss-cpu`](https://pypi.org/project/faiss-cpu/) *(alternative vector store)*
- [`lancedb`](https://pypi.org/project/lancedb/) *(alternative vector store)*
- [`sentence-transformers`](https://pypi.org/project/sentence-transformers/) *(local embeddings option)*
- [`streamlit`](https://pypi.org/project/streamlit/)
- [`python-dotenv`](https://pypi.org/project/python-dotenv/)
- [`requests`](https://pypi.org/project/requests/), [`pydantic`](https://pypi.org/project/pydantic/), [`rich`](https://pypi.org/project/rich/), [`tiktoken`](https://pypi.org/project/tiktoken/)

**Tooling**
- [`uv`](https://docs.astral.sh/uv/)
- [`poetry`](https://python-poetry.org/docs/)

### FAQ / Common Pitfalls

**Q: Can I use LangChain / LlamaIndex "just for the retriever"?**
No. For this exercise, write retrieval yourself — it's a dozen lines of code and you will learn more.

**Q: My chunks are huge and retrieval is noisy.**
Start at ~500–1000 tokens per chunk with ~10–15% overlap and iterate. Document what you tried.

**Q: The model keeps calling the tool when it shouldn't.**
Tighten the tool's `description` field and the system prompt — be explicit about when the tool should and shouldn't be used. Include an example.

**Q: The model never calls the tool.**
Same cause, opposite direction. Make the tool's usefulness explicit in its description, and confirm the tool is actually registered in the `tools=[...]` parameter on every call in the loop.

**Q: Should I evaluate my agent?**
Not formally for Exercise 1. A handful of example transcripts is enough. Formal eval harnesses come in Exercise 3.

**Q: What about safety / prompt injection?**
Be aware of it — your corpus is external data that could contain instructions to the model. A brief mention in your write-up is expected; a full mitigation is not.

**Q: Can I use a different LLM provider or host my own model?**
No — use the Azure OpenAI endpoint we provide so grading stays tractable. You **do** have a choice on embeddings: Azure OpenAI `text-embedding-3-small` or a local SentenceTransformers model. Pick whichever you prefer and document your reasoning.

---

*Questions? Raise them in your bootcamp cohort channel before burning time on the wrong interpretation.*
