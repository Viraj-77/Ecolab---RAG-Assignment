import time
from src.llm_client import get_embed_client, EMBED_MODEL, PROFILE
from src.document_loading import load_all_documents
from src.chunking import chunk_document
from src.chromadb_setup import get_collection

client = get_embed_client()


def embed(texts):
    embeddings = []
    batch_size = 16 if PROFILE == "cloud" else 1

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            res = client.embeddings.create(model=EMBED_MODEL, input=batch)
            embeddings += [d.embedding for d in res.data]
            if PROFILE == "cloud":
                time.sleep(1)
        except Exception as e:
            print(f"batch {i} failed, retrying in 10s:", e)
            time.sleep(10)
            res = client.embeddings.create(model=EMBED_MODEL, input=batch)
            embeddings += [d.embedding for d in res.data]

    return embeddings


def ingest():
    docs = load_all_documents()
    if not docs:
        print("no documents found")
        return

    chunks = []
    for doc in docs:
        chunks += chunk_document(doc)

    col = get_collection()
    already_indexed = set(col.get()["ids"])
    new_chunks = [c for c in chunks if f"{c['source']}_{c['chunk_id']}" not in already_indexed]

    if not new_chunks:
        print("nothing new to index")
        return

    texts = [c["text"] for c in new_chunks]
    ids = [f"{c['source']}_{c['chunk_id']}" for c in new_chunks]
    metas = [{"source": c["source"]} for c in new_chunks]

    col.add(ids=ids, embeddings=embed(texts), documents=texts, metadatas=metas)
    print(f"indexing done — profile={PROFILE}, collection={col.name}, chunks={len(new_chunks)}")


if __name__ == "__main__":
    ingest()
