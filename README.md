# Ecolab Water Intelligence RAG Agent

**Authors:** K, Ajay Kumar and C, Vijay Vittal and Viraj D Talati  
**Cohort:** MTech-Interns-2026 LLM Capability build office

## Overview
This project is an AI Agent with Retrieval-Augmented Generation (RAG) and function calling, built to answer questions related to Ecolab's domain (water treatment, hygiene, and sustainability). It retrieves relevant chunks from indexed public documents and dynamically calls the USGS Water Quality Portal API for live water quality measurements.

Two profiles are supported via a single environment variable:

| Profile | LLM | Embedder | Collection |
|---|---|---|---|
| `cloud` (default) | `gpt-5.4-nano` via Azure OpenAI | `text-embedding-3-small` (1536-dim) | `ecolab_corpus` |
| `local` | `gemma3n:e4b` via Ollama | `nomic-embed-text` (768-dim) | `ecolab_corpus_local` |

Only the client construction changes between profiles — the retrieval, tool-call, and chat logic is identical.

## Tech Stack & Rationale
* **Language:** Python 3.11+
* **LLM & Tool Calling:** `openai` SDK — pointed at Azure OpenAI (cloud) or `http://localhost:11434/v1` (local)
* **Embeddings:** Azure `text-embedding-3-small` (cloud) or Ollama `nomic-embed-text` (local)
* **Vector Store:** `chromadb` — two persistent collections, one per embedding model, to prevent dimension mismatch
* **Dependency Management:** `uv`
* **Chat Interface:** `streamlit`
* **Other:** `pypdf`, `requests` (USGS API), `python-dotenv`, `tiktoken`

---

## Setup — Cloud Profile

### 1. Install Dependencies
```bash
uv sync
```

### 2. Environment Variables
```bash
cp .env.example .env
```
Populate `.env`:
```
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://cds-ds-openai-001-x.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

### 3. Index Documents
```bash
LLM_PROFILE=cloud uv run python -m src.index_documents
```

### 4. Run
```bash
LLM_PROFILE=cloud uv run streamlit run app.py
```

---

## Setup — Local Profile (Ollama + Gemma 3n E4B)

**Prerequisites:** macOS or Linux, ≥16 GB RAM.

### 1. Install Ollama (macOS)
```bash
brew install ollama
brew services start ollama
ollama --version
```

### 2. Pull models (~8 GB total, one time)
```bash
ollama pull gemma3n:e4b
ollama pull nomic-embed-text
```
Verify Ollama is running: `curl http://localhost:11434/api/tags`

### 3. Index Documents (local embeddings into fresh collection)
```bash
LLM_PROFILE=local uv run python -m src.index_documents
```
This creates `chroma_db/ecolab_corpus_local` with 768-dim nomic-embed-text vectors.  
**Do not mix** this collection with the cloud collection — different dimensions produce silent garbage retrieval.

### 4. Run
```bash
LLM_PROFILE=local uv run streamlit run app.py
```

Expected startup: Ollama loads `gemma3n:e4b` in ~5 s on M1/M2. First query: 10–15 s (model warmup).

### Hardware this was tested on
- **Machine:** Apple M1 Pro, 16 GB RAM, macOS Sequoia 15.3
- **Ollama version:** 0.24.0
- **Model tag:** `gemma3n:e4b` (Q4\_K\_M, 7.5 GB)
- **Embed model:** `nomic-embed-text` (F16, 274 MB)
- **Latency p50:** 11 s · **p95:** 27 s (Metal-accelerated; pure CPU would be ~3× slower)

---

## LLM_PROFILE Switch

```bash
# Cloud
LLM_PROFILE=cloud uv run streamlit run app.py

# Local (no network required after model pull)
LLM_PROFILE=local uv run streamlit run app.py
```

`LLM_PROFILE` defaults to `cloud` if unset. The switch is read once at import time in `src/client_factory.py`. No other files change.

### What changes between profiles

| Component | cloud | local |
|---|---|---|
| `src/client_factory.py` | `AzureOpenAI(...)` | `OpenAI(base_url="http://localhost:11434/v1")` |
| Chat model | `gpt-5.4-nano` | `gemma3n:e4b` |
| Embed model | `text-embedding-3-small` | `nomic-embed-text` |
| ChromaDB collection | `ecolab_corpus` (1536-dim) | `ecolab_corpus_local` (768-dim) |
| Tool calling | Native OpenAI `tools=` API | Prompt-based JSON parsing |

### Why tool calling differs

`gemma3n:e4b` on Ollama 0.24.0 does not support the `tools=` parameter in the OpenAI-compat API. The local pipeline uses a system-prompt instruction that asks the model to emit `TOOL_CALL: {...}` JSON, which `rag_pipeline._chat_local()` parses and executes. This achieved 10/10 correct invocations across the test set.

---

## How to Run the Comparison Benchmark
```bash
LLM_PROFILE=local  uv run python scripts/comparison_run.py
LLM_PROFILE=cloud  uv run python scripts/comparison_run.py   # requires .env
```
Results are saved to `scripts/results_{profile}.json`. See `docs/local-mode-comparison.md` for the full analysis.

## How to Test It
1. **RAG-only:** "What is the water neutrality framework described in the Ecolab documents?"
2. **Tool-only:** "What is the current pH reading in Minnesota right now?"
3. **Combined:** "What does Ecolab say about acceptable pH ranges, and what are the current readings in Minnesota?"
4. **Adversarial:** "What is the best recipe for chocolate cake?" (should be refused)
