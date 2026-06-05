# 💧 Ecolab Water Intelligence RAG

A Streamlit-based Retrieval-Augmented Generation (RAG) application for **water neutrality / water sustainability documents**. The project supports both **Local Ollama mode** and **Azure OpenAI mode**, so the same RAG pipeline can be tested for offline privacy, speed, answer quality, and deployment readiness.

---

## 1. Project Objective

The objective of this project is to build a practical RAG system that can:

- Upload and process water-related PDF reports.
- Clean, chunk, and embed document text.
- Store embeddings in a local Chroma vector database.
- Retrieve relevant chunks for user questions.
- Generate grounded answers with citations.
- Switch runtime between:
  - **Local mode:** Ollama LLM + local embedding model.
  - **Azure mode:** Azure OpenAI LLM + Azure embedding deployment.
- Compare Local vs Azure performance using speed, answer quality, privacy, offline use, tool reliability, and cost control.

---

## 2. Current Output Screenshots

### Local Ollama RAG Answer

![Local mode RAG answer](docs/images/local-rag-output.png)

### Azure RAG Answer

![Azure mode RAG answer](docs/images/azure-rag-output.png)

### Local vs Azure Performance Dashboard

![Performance dashboard speed trend](docs/images/performance-dashboard-1.png)

### Business Metrics and Decision Table

![Metrics and decision table](docs/images/performance-dashboard-2.png)

---

## 3. Key Features

### Runtime Selection

The sidebar allows switching between:

- LLM provider: `local` or `azure`
- Embedding provider: `local` or `azure`
- Local Ollama model: `gemma3n:e4b`
- Local embedding model: `nomic-embed-text`
- Azure chat deployment: `gpt-4-nano`
- Azure embedding deployment: `text-embedding-3-small`

### RAG Pipeline

The application follows this flow:

1. Load PDF documents.
2. Clean extracted text.
3. Split text into chunks.
4. Generate embeddings.
5. Store vectors in ChromaDB.
6. Retrieve top-k relevant chunks.
7. Build prompt with retrieved context.
8. Generate grounded answer with citations.
9. Show retrieved chunks and runtime details.

### Performance Dashboard

The dashboard compares Local Ollama and Azure Cloud on:

- Average response latency.
- p50 and p95 latency.
- Answer quality.
- Tool reliability.
- Privacy.
- Offline use.
- Cost control.
- Overall business score.

Current observed summary:

| Runtime | Business Score | Avg Latency | Strength |
|---|---:|---:|---|
| Azure Cloud | 71.4 / 100 | 3.80 s | Faster and reliable for production use |
| Local Ollama | 68.5 / 100 | 9.95 s | Better for privacy, offline use, and cost control |

**Conclusion:** Azure is better for speed and production reliability, while Local Ollama is better for private/offline document Q&A. Keeping both profiles gives the best deployment flexibility.


## 5 Project Status

- Local Ollama RAG working.
- Azure RAG working.
- Runtime selection added.
- Water neutrality report indexed.
- Query answering with citations working.
- Performance dashboard created.
- Local vs Azure business metrics compared.
- README and screenshots added for project submission.

---

## 14. Final Business Conclusion

Local mode is useful when privacy, offline access, and cost control are important. Azure mode is useful when faster response time, reliability, and production deployment are important. The recommended architecture is a dual-runtime RAG system where the user can switch between Local Ollama and Azure OpenAI based on business needs.
