from src.llm_client import get_embed_client, EMBED_MODEL
from src.chromadb_setup import get_collection

client = get_embed_client()

TOP_K = 4

def retrieve(query: str) -> list[dict]:
    vec = client.embeddings.create(
        model=EMBED_MODEL,
        input=query,
    ).data[0].embedding

    results = get_collection().query(
        query_embeddings=[vec],
        n_results=TOP_K,
        include=["documents", "metadatas"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]

    return [
        {"text": doc, "source": meta.get("source", "unknown")}
        for doc, meta in zip(docs, metas)
    ]
