import time
from src.client_factory import get_embed_client, get_embed_model, LLM_PROFILE
from src.document_loading import load_all_documents
from src.chunking import chunk_document, split_text
from src.chromadb_setup import get_collection, COLLECTION_CLOUD, COLLECTION_LOCAL

# nomic-embed-text uses a word-piece tokenizer where a single period is one token.
# A 300-cl100k-token TOC line full of dots can exceed 2000 nomic tokens.
# 128 cl100k tokens worst-case ≈ 512 nomic tokens — safely under the 512-token limit.
LOCAL_CHUNK_TOKENS = 128
LOCAL_OVERLAP_TOKENS = 20


def embed(texts: list[str]) -> list[list[float]]:
    client = get_embed_client()
    model = get_embed_model()
    embeddings = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            res = client.embeddings.create(model=model, input=batch)
            embeddings += [d.embedding for d in res.data]
            if LLM_PROFILE == "cloud":
                time.sleep(1)  # cloud rate-limit guard; local Ollama doesn't need it
        except Exception as e:
            print("batch failed, retrying in 10s:", e)
            time.sleep(10)
            res = client.embeddings.create(model=model, input=batch)
            embeddings += [d.embedding for d in res.data]

    return embeddings


def ingest():
    collection_name = COLLECTION_LOCAL if LLM_PROFILE == "local" else COLLECTION_CLOUD
    print(f"Profile: {LLM_PROFILE} → collection: {collection_name}, model: {get_embed_model()}")

    docs = load_all_documents()
    if not docs:
        print("no documents found")
        return

    chunks = []
    for doc in docs:
        if LLM_PROFILE == "local":
            raw = split_text(doc["text"], chunk_size=LOCAL_CHUNK_TOKENS, overlap=LOCAL_OVERLAP_TOKENS)
            chunks += [{"source": doc["source"], "chunk_id": i, "text": t} for i, t in enumerate(raw)]
        else:
            chunks += chunk_document(doc)

    col = get_collection(collection_name)
    already_indexed = set(col.get()["ids"])
    new_chunks = [c for c in chunks if f"{c['source']}_{c['chunk_id']}" not in already_indexed]

    if not new_chunks:
        print("nothing new to index")
        return

    texts = [c["text"] for c in new_chunks]
    ids = [f"{c['source']}_{c['chunk_id']}" for c in new_chunks]
    metas = [{"source": c["source"]} for c in new_chunks]

    col.add(ids=ids, embeddings=embed(texts), documents=texts, metadatas=metas)
    print(f"indexed {len(new_chunks)} chunks into '{collection_name}'")


if __name__ == "__main__":
    ingest()
