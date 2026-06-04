# Ecolab Water Intelligence RAG Agent

**Authors:** K, Ajay Kumar and C, Vijay Vittal and Viraj D Talati  
**Cohort:** MTech-Interns-2026 LLM Capability build office

## Overview
This project is an AI Agent with Retrieval-Augmented Generation (RAG) and function calling, built to answer questions related to Ecolab's domain (water treatment, hygiene, and sustainability). It retrieves relevant chunks from indexed public documents and dynamically calls the USGS Water Quality Portal API for live water quality measurements.

## Tech Stack & Rationale
We chose a modern, lightweight tech stack to prioritize understanding the core mechanics of RAG and tool-calling over relying on opaque orchestration frameworks:

* **Language:** Python 3.11+
* **LLM & Tool Calling:** `openai` SDK with `AzureOpenAI` client (Model: `gpt-5.4-nano`)
* **Embeddings:** Azure OpenAI `text-embedding-3-small` (for consistent vector space across documents and queries).
* **Vector Store:** `chromadb` (running fully locally with persistent disk storage).
* **Dependency Management:** `uv` for fast dependency resolution and locking.
* **Chat Interface:** `streamlit` for an interactive, web-based multi-turn chat experience.
* **Other Utilities:** 
  * `pypdf` for parsing document PDFs.
  * `requests` for querying the USGS public API.
  * `python-dotenv` for managing environment variables securely.
  * `tiktoken` for accurate token counting.

## Setup Instructions

### 1. Install Dependencies
Ensure you have Python 3.11+ installed. We use `uv` as our dependency manager. Install dependencies via:
```bash
uv sync
```

### 2. Environment Variables
Copy the provided `.env.example` file to create your own `.env` file:
```bash
cp .env.example .env
```
Populate `.env` with your Azure OpenAI credentials. Make sure you never commit this file.

### 3. Data Ingestion
Place your PDF documents in the `Data/` directory. Then, run the ingestion script to chunk, embed, and index them into ChromaDB:
```bash
python -m src.index_documents
```
*Note: This will store the vector data locally in the `chroma_db/` directory. Do not commit this directory.*

## How to Run the App

Start the Streamlit interface using the following command:
```bash
uv run streamlit run app.py
```
This will open the chat application in your default web browser where you can interact with the agent.

## How to Test It
You can test the agent's capabilities by asking three types of questions in the chat UI:
1. **RAG-only queries:** Ask about general water treatment concepts found in your ingested PDFs.
2. **Tool-only queries:** Ask a specific data question that requires live USGS data (e.g., "What is the current pH reading in minnesota rightnow").
3. **Combined queries:** Ask a question that requires both context from the documents and live USGS data to form a complete answer.
