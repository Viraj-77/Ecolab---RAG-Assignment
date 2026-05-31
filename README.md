# Ecolab Water Intelligence RAG Agent

**Authors:** Viraj D Talati
**Cohort:** MTech-Interns-2026 LLM Capability build office

## Overview

This project is a Retrieval-Augmented Generation (RAG) agent for the Ecolab domain (water treatment, hygiene, sustainability). It retrieves relevant chunks from indexed PDF documents and — under the cloud profile — calls the USGS Water Quality Portal API for live water-quality measurements via OpenAI tool calling.

The repo now supports **two profiles**, switchable via a single env var, per Exercise A of the Local-RAG take-home:

| Profile | LLM | Embedder | Tool calling |
|---|---|---|---|
| `LLM_PROFILE=cloud` | `gpt-5.4-nano` (Azure OpenAI) | `text-embedding-3-small` (1536-dim) | Full USGS tool loop |
| `LLM_PROFILE=local` | `gemma3n:e4b` (Ollama) | `nomic-embed-text` (768-dim) | Disabled — model lacks tool support |

The cloud/local split is **one env var**, not two parallel codebases. The branching files are `src/llm_client.py`, `src/rag_pipeline.py`, `src/chromadb_setup.py`, and `src/chunking.py`. The agent loop, retrieval logic, and Streamlit UI are profile-agnostic.

## Tech stack

- **Python 3.11+**, dependency-managed by `uv`
- **`openai` SDK** — used for both `AzureOpenAI` (cloud) and the Ollama OpenAI-compat endpoint (local)
- **ChromaDB** — persistent local vector store at `chroma_db/`, separate collection per profile
- **Streamlit** — chat UI (`app.py`)
- **Ollama** — local LLM and embedder runtime (local profile only)
- **`requests`** — USGS API calls
- **`tiktoken`** — token counting in chunking + eval

## Setup

### 1. Install Python deps

```bash
uv sync
```

### 2. Configure `.env`

```ini
# cloud profile
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://cds-ds-openai-001-x.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# profile selection + local profile config
LLM_PROFILE=local                       # or "cloud"
OLLAMA_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=gemma3n:e4b
LOCAL_EMBED_MODEL=nomic-embed-text
```

### 3. (Local profile only) Install Ollama and pull models

```bash
brew install ollama
brew services start ollama        # daemon on :11434
ollama pull gemma3n:e4b           # ~7.5 GB
ollama pull nomic-embed-text      # 137M
```

### 4. Index the corpus

Place PDFs in `Data/`, then run **once per profile** (each profile builds its own collection):

```bash
LLM_PROFILE=cloud uv run python -m src.index_documents   # 836 chunks, 1536-dim
LLM_PROFILE=local uv run python -m src.index_documents   # 1742 chunks, 768-dim
```

A fresh trainee following the steps above should reach a working chat against Ollama in under 15 minutes.

## Running the chat UI

```bash
LLM_PROFILE=local uv run streamlit run app.py
# or
LLM_PROFILE=cloud uv run streamlit run app.py
```

The Streamlit UI prints the active profile in the chat session so you don't lose track of which model is answering.

## Running the evaluation

The 24-query side-by-side benchmark lives in `eval/`:

```bash
LLM_PROFILE=local uv run python -m eval.run_eval   # writes eval/results_local_<ts>.csv
LLM_PROFILE=cloud uv run python -m eval.run_eval   # writes eval/results_cloud_<ts>.csv
```

Manual rubric scoring is in `eval/scored_local.csv` and `eval/scored_cloud.csv`. Aggregates and full diagnosis live in `docs/local-mode-comparison.md`.

## Hardware used for the local-mode runs

- macOS, Apple Silicon
- 16 GB RAM
- `gemma3n:e4b` GGUF Q4_K_M (~7.5 GB on disk) running on CPU/Metal via Ollama
- All eval runs done on this single laptop, single-user

## Deliverables (Exercise A)

| File | What it is |
|---|---|
| [`docs/local-mode-tasks.md`](docs/local-mode-tasks.md) | Ordered task plan for the port |
| [`docs/prompt-set.md`](docs/prompt-set.md) | The 24-query benchmark + rubric |
| [`docs/local-mode-comparison.md`](docs/local-mode-comparison.md) | Side-by-side results, aggregates, diagnosis |
| [`docs/when-to-go-local.md`](docs/when-to-go-local.md) | One-page decision document |
| [`docs/transcript-local.md`](docs/transcript-local.md) / [`docs/transcript-cloud.md`](docs/transcript-cloud.md) | Same combined query end-to-end on each profile |
| [`blockers.md`](blockers.md) | Issues hit during the port and how they were resolved |

## How to test it manually

In the Streamlit UI, try one of each:

1. **RAG-only**: "What is the purpose of a water neutrality framework?" — works on both profiles.
2. **Tool-only**: "What is the latest pH reading from active USGS sites in Minnesota?" — answers fully on cloud; refuses honestly on local.
3. **Combined**: "Explain what turbidity tells us about water quality (per the documents) and pull current turbidity values for California to illustrate." — full RAG + tool synthesis on cloud; corpus-only with explicit refusal of the live half on local. See the transcripts above for the side-by-side.
