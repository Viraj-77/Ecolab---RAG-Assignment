from src.client_factory import get_embed_client, get_embed_model, LLM_PROFILE
from src.chromadb_setup import get_collection, COLLECTION_CLOUD, COLLECTION_LOCAL

TOP_K = 4  # nomic-embed-text clusters differently; same k works well


def retrieve(query: str) -> list[dict]:
    collection_name = COLLECTION_LOCAL if LLM_PROFILE == "local" else COLLECTION_CLOUD
    embed_client = get_embed_client()
    embed_model = get_embed_model()

    vec = embed_client.embeddings.create(
        model=embed_model,
        input=query,
    ).data[0].embedding

    results = get_collection(collection_name).query(
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
