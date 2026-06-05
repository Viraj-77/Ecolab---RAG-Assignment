from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from src.config import RuntimeConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------
# Client cache
# ---------------------------------------------------------------------
_chroma_clients: dict[str, chromadb.PersistentClient] = {}


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class VectorStoreError(RuntimeError):
    """Raised when ChromaDB setup or access fails."""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _get_chroma_path(cfg: RuntimeConfig) -> Path:
    """
    Return persistent ChromaDB directory path.
    """
    chroma_path = PROJECT_ROOT / cfg.chroma_dir
    chroma_path.mkdir(parents=True, exist_ok=True)

    return chroma_path


def _collection_metadata(cfg: RuntimeConfig) -> dict[str, str | int | float | bool]:
    """
    Metadata attached to the Chroma collection.

    Important:
    The collection is tied to the embedding profile/model and chunking settings.
    This prevents silent mixing of Azure 1536-dim vectors and local 768-dim vectors.
    """
    return {
        "hnsw:space": "cosine",
        "embedding_profile": cfg.embedding_profile,
        "embedding_model": cfg.resolved_embedding_model,
        "chunk_tokens": cfg.chunk_tokens,
        "overlap_tokens": cfg.overlap_tokens,
        "vector_store": cfg.vector_store,
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def get_client(cfg: RuntimeConfig) -> chromadb.PersistentClient:
    """
    Create or reuse a persistent ChromaDB client.
    """
    chroma_path = _get_chroma_path(cfg)
    cache_key = str(chroma_path.resolve())

    if cache_key not in _chroma_clients:
        try:
            _chroma_clients[cache_key] = chromadb.PersistentClient(
                path=cache_key,
            )

            logger.info("ChromaDB client initialized at %s", cache_key)

        except Exception as exc:
            logger.exception("Failed to initialize ChromaDB client")
            raise VectorStoreError(
                f"Failed to initialize ChromaDB at {cache_key}: {exc}"
            ) from exc

    return _chroma_clients[cache_key]


def get_collection(cfg: RuntimeConfig) -> Collection:
    """
    Get or create the active ChromaDB collection.

    Collection name depends on:
    - embedding provider
    - embedding model
    - chunk size
    - overlap

    LLM model is not included because LLM does not affect vector dimensions.
    """
    try:
        client = get_client(cfg)

        collection = client.get_or_create_collection(
            name=cfg.collection_name,
            metadata=_collection_metadata(cfg),
        )

        logger.info(
            "Using Chroma collection | name=%s | embedding=%s:%s",
            cfg.collection_name,
            cfg.embedding_profile,
            cfg.resolved_embedding_model,
        )

        return collection

    except Exception as exc:
        logger.exception("Failed to get/create Chroma collection: %s", cfg.collection_name)
        raise VectorStoreError(
            f"Failed to get/create Chroma collection `{cfg.collection_name}`: {exc}"
        ) from exc


def reset_collection(cfg: RuntimeConfig) -> Collection:
    """
    Delete and recreate the active collection.

    Use this whenever:
    - embedding model changes
    - chunk size changes
    - overlap changes
    - PDF corpus changes and you want a clean rebuild
    """
    try:
        client = get_client(cfg)

        try:
            client.delete_collection(cfg.collection_name)
            logger.info("Deleted existing Chroma collection: %s", cfg.collection_name)

        except Exception:
            logger.info(
                "No existing Chroma collection to delete: %s",
                cfg.collection_name,
            )

        return get_collection(cfg)

    except Exception as exc:
        logger.exception("Failed to reset Chroma collection: %s", cfg.collection_name)
        raise VectorStoreError(
            f"Failed to reset Chroma collection `{cfg.collection_name}`: {exc}"
        ) from exc


def collection_count(cfg: RuntimeConfig) -> int:
    """
    Return vector count in active collection.
    """
    try:
        return get_collection(cfg).count()
    except Exception as exc:
        raise VectorStoreError(f"Failed to count Chroma collection: {exc}") from exc