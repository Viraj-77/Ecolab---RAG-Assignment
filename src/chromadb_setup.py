import pathlib
import chromadb

CHROMA_DIR = str(pathlib.Path(__file__).parent.parent / "chroma_db")

# Separate collection per embedding model to prevent dimension mismatch.
# cloud: text-embedding-3-small (1536-dim)
# local: nomic-embed-text (768-dim)
COLLECTION_CLOUD = "ecolab_corpus"
COLLECTION_LOCAL = "ecolab_corpus_local"


def get_collection(name: str = COLLECTION_CLOUD) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
