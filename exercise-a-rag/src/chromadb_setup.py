import pathlib
import chromadb
from src.llm_client import PROFILE


CHROMA_DIR = str(pathlib.Path(__file__).parent.parent / "chroma_db")

COLLECTION_NAME = f"ecolab_corpus_{PROFILE}"


def get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
