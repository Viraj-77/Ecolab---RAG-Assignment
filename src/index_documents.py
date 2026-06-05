from __future__ import annotations

import argparse
import hashlib
import logging
import time
from math import ceil
from typing import Any, Iterable

from src.chromadb_setup import get_collection, reset_collection
from src.chunking import chunk_documents
from src.config import RuntimeConfig, load_config
from src.document_loading import load_all_documents
from src.embedding_provider import embed_texts, embedding_dim


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
DEFAULT_INGEST_BATCH_SIZE = 32


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class IngestionError(RuntimeError):
    """Raised when document ingestion/indexing fails."""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _batch(items: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _safe_metadata_value(value: Any) -> str | int | float | bool:
    """
    Chroma metadata values must be primitive types.
    """
    if isinstance(value, (str, int, float, bool)):
        return value

    if value is None:
        return ""

    return str(value)


def _stable_chunk_id(chunk: dict[str, Any]) -> str:
    """
    Create stable unique ID for a chunk.

    Includes hash of content so re-indexing after chunking changes is safe.
    """
    source = str(chunk.get("source", "unknown"))
    page = str(chunk.get("page", "0"))
    chunk_id = str(chunk.get("chunk_id", "0"))
    text = str(chunk.get("text", ""))

    text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    return f"{source}_p{page}_c{chunk_id}_{text_hash}"


def _chunk_metadata(
    chunk: dict[str, Any],
    cfg: RuntimeConfig,
    dim: int,
) -> dict[str, str | int | float | bool]:
    """
    Metadata stored with each vector.
    """
    metadata = {
        "source": chunk.get("source", "unknown"),
        "page": chunk.get("page", 0),
        "chunk_id": chunk.get("chunk_id", 0),
        "token_count": chunk.get("token_count", 0),
        "char_count": chunk.get("char_count", 0),
        "file_type": chunk.get("file_type", "unknown"),
        "embedding_profile": cfg.embedding_profile,
        "embedding_model": cfg.resolved_embedding_model,
        "embedding_dim": dim,
        "chunk_tokens": cfg.chunk_tokens,
        "overlap_tokens": cfg.overlap_tokens,
    }

    return {
        key: _safe_metadata_value(value)
        for key, value in metadata.items()
    }


def _print_ingestion_header(cfg: RuntimeConfig) -> None:
    print("=" * 80)
    print("RAG INGESTION")
    print("=" * 80)
    print(f"Embedding profile : {cfg.embedding_profile}")
    print(f"Embedding model   : {cfg.resolved_embedding_model}")
    print(f"Vector DB         : ChromaDB")
    print(f"Collection        : {cfg.collection_name}")
    print(f"Chunk tokens      : {cfg.chunk_tokens}")
    print(f"Overlap tokens    : {cfg.overlap_tokens}")
    print(f"Top-K             : {cfg.top_k}")
    print("=" * 80)


def _print_ingestion_summary(
    *,
    total_docs: int,
    total_chunks: int,
    indexed_chunks: int,
    collection_count: int,
    elapsed_sec: float,
) -> None:
    print("=" * 80)
    print("INDEXING COMPLETED")
    print("=" * 80)
    print(f"Loaded document records : {total_docs}")
    print(f"Created chunks          : {total_chunks}")
    print(f"New indexed chunks      : {indexed_chunks}")
    print(f"Total vector count      : {collection_count}")
    print(f"Elapsed time            : {elapsed_sec:.2f} sec")
    print("=" * 80)


# ---------------------------------------------------------------------
# Public ingestion function
# ---------------------------------------------------------------------
def ingest(
    cfg: RuntimeConfig | None = None,
    reset: bool = False,
    batch_size: int = DEFAULT_INGEST_BATCH_SIZE,
) -> int:
    """
    Full indexing flow.

    Steps:
    1. Load documents from Data/
    2. Clean/extract text
    3. Chunk documents
    4. Generate embeddings using selected provider
    5. Store in selected Chroma collection

    Important:
    Chroma collection depends on embedding provider/model.
    This prevents mixing Azure and local embedding dimensions.
    """
    cfg = cfg or load_config()
    start_time = time.perf_counter()

    if batch_size <= 0:
        raise IngestionError("batch_size must be greater than zero.")

    _print_ingestion_header(cfg)

    try:
        dim = embedding_dim(cfg)
    except Exception as exc:
        logger.exception("Embedding dimension check failed")
        raise IngestionError(f"Embedding dimension check failed: {exc}") from exc

    print(f"Embedding dimension check: {dim}")

    docs = load_all_documents()

    if not docs:
        print("No supported documents found in Data/. Add PDF, TXT, or MD files first.")
        return 0

    try:
        chunks = chunk_documents(docs, cfg)
    except Exception as exc:
        logger.exception("Chunking failed")
        raise IngestionError(f"Chunking failed: {exc}") from exc

    if not chunks:
        print("No chunks created. Check document extraction or file content.")
        return 0

    collection = reset_collection(cfg) if reset else get_collection(cfg)

    try:
        existing_ids = set(collection.get(include=[])["ids"])
    except Exception:
        existing_ids = set()

    new_chunks: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk["id"] = _stable_chunk_id(chunk)

        if chunk["id"] not in existing_ids:
            new_chunks.append(chunk)

    if not new_chunks:
        current_count = collection.count()
        print("Nothing new to index.")
        print(f"Current vector count: {current_count}")
        return current_count

    total_batches = ceil(len(new_chunks) / batch_size)
    indexed_count = 0

    for batch_no, batch in enumerate(_batch(new_chunks, batch_size), start=1):
        texts = [str(chunk["text"]) for chunk in batch]
        ids = [str(chunk["id"]) for chunk in batch]
        metadatas = [
            _chunk_metadata(chunk=chunk, cfg=cfg, dim=dim)
            for chunk in batch
        ]

        try:
            vectors = embed_texts(texts, cfg)
        except Exception as exc:
            logger.exception("Embedding generation failed for batch %s", batch_no)
            raise IngestionError(
                f"Embedding generation failed for batch {batch_no}/{total_batches}: {exc}"
            ) from exc

        try:
            collection.add(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception as exc:
            logger.exception("Failed to add vectors to ChromaDB for batch %s", batch_no)
            raise IngestionError(
                f"Failed to store vectors in ChromaDB for batch {batch_no}/{total_batches}: {exc}"
            ) from exc

        indexed_count += len(batch)

        print(
            f"Indexed batch {batch_no}/{total_batches} | "
            f"chunks={len(batch)} | total_indexed={indexed_count}"
        )

    final_count = collection.count()
    elapsed_sec = time.perf_counter() - start_time

    _print_ingestion_summary(
        total_docs=len(docs),
        total_chunks=len(chunks),
        indexed_chunks=indexed_count,
        collection_count=final_count,
        elapsed_sec=elapsed_sec,
    )

    return final_count


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index PDF/TXT/MD documents into ChromaDB for Azure or Ollama RAG."
    )

    parser.add_argument("--llm-profile", choices=["local", "azure"], default=None)
    parser.add_argument("--embedding-profile", choices=["local", "azure"], default=None)

    parser.add_argument("--ollama-llm-model", default=None)
    parser.add_argument("--ollama-embed-model", default=None)

    parser.add_argument("--azure-chat-model", default=None)
    parser.add_argument("--azure-embed-model", default=None)

    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--chunk-tokens", type=int, default=None)
    parser.add_argument("--overlap-tokens", type=int, default=None)

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and rebuild the selected Chroma collection.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_INGEST_BATCH_SIZE,
        help="Embedding/indexing batch size.",
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    cfg = load_config(
        llm_profile=args.llm_profile,
        embedding_profile=args.embedding_profile,
        ollama_llm_model=args.ollama_llm_model,
        ollama_embed_model=args.ollama_embed_model,
        azure_chat_model=args.azure_chat_model,
        azure_embed_model=args.azure_embed_model,
        top_k=args.top_k,
        chunk_tokens=args.chunk_tokens,
        overlap_tokens=args.overlap_tokens,
    )

    ingest(
        cfg=cfg,
        reset=args.reset,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()