from __future__ import annotations

import logging
import re
from typing import Any

import tiktoken

from src.config import RuntimeConfig, load_config


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------
ENCODING_NAME = "cl100k_base"
_encoder = tiktoken.get_encoding(ENCODING_NAME)


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
MIN_CHUNK_CHAR_LENGTH = 40
DEFAULT_CHUNK_TOKENS = 650
DEFAULT_OVERLAP_TOKENS = 100


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class ChunkingError(RuntimeError):
    """Raised when document chunking fails."""


# ---------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------
def token_count(text: str) -> int:
    """
    Count tokens using cl100k_base tokenizer.

    This is approximate for all models but good enough for chunk control.
    """
    if not text:
        return 0

    return len(_encoder.encode(text))


def _decode_tokens(tokens: list[int]) -> str:
    return _encoder.decode(tokens).strip()


def _tail_overlap(text: str, overlap_tokens: int) -> str:
    """
    Return last N tokens of a chunk to preserve context in next chunk.
    """
    if overlap_tokens <= 0:
        return ""

    tokens = _encoder.encode(text or "")

    if not tokens:
        return ""

    return _decode_tokens(tokens[-overlap_tokens:])


# ---------------------------------------------------------------------
# Text splitting helpers
# ---------------------------------------------------------------------
def _split_by_paragraphs(text: str) -> list[str]:
    """
    Prefer paragraph boundaries because they preserve meaning.
    """
    paragraphs = [
        block.strip()
        for block in re.split(r"\n\s*\n", text)
        if block and block.strip()
    ]

    if len(paragraphs) > 1:
        return paragraphs

    return []


def _split_by_sentences(text: str) -> list[str]:
    """
    Fallback for PDFs where paragraphs are lost during extraction.
    """
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)

    return [
        sentence.strip()
        for sentence in sentences
        if sentence and sentence.strip()
    ]


def _get_semantic_blocks(text: str) -> list[str]:
    """
    Get semantic blocks using paragraph-first logic.

    If PDF extraction gives one giant paragraph, fall back to sentence splits.
    """
    paragraphs = _split_by_paragraphs(text)

    if paragraphs:
        return paragraphs

    sentences = _split_by_sentences(text)

    if sentences:
        return sentences

    return [text.strip()] if text.strip() else []


def _split_large_block(
    block: str,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """
    Split a very large paragraph/table/block by token sliding window.
    """
    tokens = _encoder.encode(block)

    if not tokens:
        return []

    step = max(1, chunk_tokens - overlap_tokens)

    chunks: list[str] = []

    for start in range(0, len(tokens), step):
        part_tokens = tokens[start : start + chunk_tokens]
        part = _decode_tokens(part_tokens)

        if part:
            chunks.append(part)

    return chunks


def _normalize_for_duplicate_check(text: str) -> str:
    """
    Normalize chunk text for duplicate removal.
    """
    normalized = re.sub(r"\s+", " ", text)
    normalized = normalized.strip().lower()

    return normalized


def _remove_tiny_and_duplicate_chunks(chunks: list[str]) -> list[str]:
    """
    Remove very small chunks and exact duplicates.
    """
    final_chunks: list[str] = []
    seen: set[str] = set()

    for chunk in chunks:
        chunk = chunk.strip()

        if len(chunk) < MIN_CHUNK_CHAR_LENGTH:
            continue

        normalized = _normalize_for_duplicate_check(chunk)

        if normalized in seen:
            continue

        seen.add(normalized)
        final_chunks.append(chunk)

    return final_chunks


# ---------------------------------------------------------------------
# Public chunking functions
# ---------------------------------------------------------------------
def split_text_semantic(
    text: str,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """
    Token-aware semantic chunking with overlap.

    Strategy:
    1. Prefer paragraph boundaries.
    2. If paragraph structure is weak, use sentence-level blocks.
    3. If a block is too large, split it by token window.
    4. Add overlap between chunks to avoid losing definitions/formulas.
    5. Remove tiny and exact duplicate chunks.

    This is better than fixed character chunking because it keeps related ideas
    together while still controlling token cost.
    """
    if not text or not text.strip():
        return []

    if chunk_tokens <= 0:
        raise ChunkingError("chunk_tokens must be greater than 0.")

    if overlap_tokens < 0:
        raise ChunkingError("overlap_tokens cannot be negative.")

    if chunk_tokens <= overlap_tokens:
        raise ChunkingError("chunk_tokens must be greater than overlap_tokens.")

    blocks = _get_semantic_blocks(text)

    chunks: list[str] = []
    current_chunk = ""

    for block in blocks:
        block = block.strip()

        if not block:
            continue

        block_token_count = token_count(block)

        # Very large paragraph/table/formula block.
        if block_token_count > chunk_tokens:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""

            large_block_chunks = _split_large_block(
                block=block,
                chunk_tokens=chunk_tokens,
                overlap_tokens=overlap_tokens,
            )

            chunks.extend(large_block_chunks)
            continue

        candidate = (
            f"{current_chunk}\n\n{block}".strip()
            if current_chunk
            else block
        )

        if token_count(candidate) <= chunk_tokens:
            current_chunk = candidate
            continue

        # Current chunk is full. Save and start next with overlap.
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            overlap_text = _tail_overlap(current_chunk, overlap_tokens)
            current_chunk = (
                f"{overlap_text}\n\n{block}".strip()
                if overlap_text
                else block
            )
        else:
            current_chunk = block

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    final_chunks = _remove_tiny_and_duplicate_chunks(chunks)

    logger.info(
        "Chunking complete | raw_chunks=%s | final_chunks=%s | chunk_tokens=%s | overlap=%s",
        len(chunks),
        len(final_chunks),
        chunk_tokens,
        overlap_tokens,
    )

    return final_chunks


def chunk_document(
    doc: dict[str, Any],
    cfg: RuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Chunk a single document/page record.

    Input doc:
    {
        "source": file name,
        "page": page number,
        "text": cleaned text,
        "file_type": pdf/txt/md
    }

    Output chunk:
    {
        source,
        page,
        chunk_id,
        text,
        token_count,
        char_count,
        file_type
    }
    """
    cfg = cfg or load_config()

    source = doc.get("source", "unknown")
    page = int(doc.get("page", 0) or 0)
    text = doc.get("text", "")
    file_type = doc.get("file_type", "unknown")

    if not text or not str(text).strip():
        return []

    raw_chunks = split_text_semantic(
        text=str(text),
        chunk_tokens=cfg.chunk_tokens,
        overlap_tokens=cfg.overlap_tokens,
    )

    chunks: list[dict[str, Any]] = []

    for index, chunk_text in enumerate(raw_chunks):
        chunks.append(
            {
                "source": source,
                "page": page,
                "chunk_id": index,
                "text": chunk_text,
                "token_count": token_count(chunk_text),
                "char_count": len(chunk_text),
                "file_type": file_type,
            }
        )

    return chunks


def chunk_documents(
    docs: list[dict[str, Any]],
    cfg: RuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Chunk multiple documents/pages.
    """
    cfg = cfg or load_config()
    all_chunks: list[dict[str, Any]] = []

    for doc in docs:
        try:
            all_chunks.extend(chunk_document(doc, cfg))
        except Exception as exc:
            logger.exception(
                "Failed to chunk document source=%s page=%s",
                doc.get("source", "unknown"),
                doc.get("page", "?"),
            )
            raise ChunkingError(
                f"Failed to chunk document {doc.get('source', 'unknown')} page {doc.get('page', '?')}"
            ) from exc

    logger.info("Total chunks created: %s", len(all_chunks))

    return all_chunks