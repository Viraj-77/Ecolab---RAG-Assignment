from __future__ import annotations

import logging
import re
from typing import Any

from src.chromadb_setup import get_collection
from src.config import RuntimeConfig, load_config
from src.embedding_provider import embed_query


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
DEFAULT_VECTOR_MULTIPLIER = 3
DEFAULT_KEYWORD_SCAN_LIMIT = 10_000

ACRONYM_BOOST = 8.0
EXACT_TERM_BOOST = 4.0
NORMAL_TERM_BOOST = 1.0
PHRASE_BOOST = 6.0

STOPWORDS = {
    "what",
    "which",
    "when",
    "where",
    "why",
    "how",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "on",
    "and",
    "or",
    "with",
    "from",
    "by",
    "as",
    "this",
    "that",
    "give",
    "tell",
    "explain",
    "define",
    "meaning",
    "full",
    "form",
}


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class RetrievalError(RuntimeError):
    """Raised when retrieval fails."""


# ---------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------
def _normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_query_terms(query: str) -> list[str]:
    """
    Extract useful keyword terms from query.

    Keeps terms like:
    - NMCG
    - 3M-7R
    - CGWA
    - water-neutrality
    """
    raw_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", query or "")

    terms: list[str] = []
    seen: set[str] = set()

    for term in raw_terms:
        cleaned = term.strip().lower()

        if not cleaned:
            continue

        if cleaned in STOPWORDS:
            continue

        if len(cleaned) < 2:
            continue

        if cleaned not in seen:
            seen.add(cleaned)
            terms.append(cleaned)

    return terms


def _extract_acronyms(query: str) -> list[str]:
    """
    Extract acronym-like terms.

    Examples:
    - NMCG
    - CGWA
    - 3M-7R
    - SDG
    """
    raw_terms = re.findall(r"\b[A-Z0-9][A-Z0-9_-]{1,}\b", query or "")

    acronyms: list[str] = []
    seen: set[str] = set()

    for term in raw_terms:
        cleaned = term.strip().lower()

        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            acronyms.append(cleaned)

    return acronyms


def _chunk_key(chunk: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(chunk.get("source", "unknown")),
        str(chunk.get("page", "?")),
        str(chunk.get("chunk_id", "?")),
    )


def _make_chunk(
    *,
    rank: int,
    text: str,
    metadata: dict[str, Any],
    distance: float | None = None,
    vector_score: float = 0.0,
    keyword_score: float = 0.0,
    search_mode: str = "vector",
) -> dict[str, Any]:
    return {
        "rank": rank,
        "text": text,
        "source": metadata.get("source", "unknown"),
        "page": metadata.get("page", "?"),
        "chunk_id": metadata.get("chunk_id", "?"),
        "token_count": metadata.get("token_count", "?"),
        "file_type": metadata.get("file_type", "unknown"),
        "distance": float(distance) if distance is not None else 999.0,
        "vector_score": float(vector_score),
        "keyword_score": float(keyword_score),
        "combined_score": float(vector_score + keyword_score),
        "search_mode": search_mode,
    }


# ---------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------
def vector_search(query: str, cfg: RuntimeConfig, n_results: int | None = None) -> list[dict[str, Any]]:
    """
    Semantic search using selected embedding provider.
    """
    collection = get_collection(cfg)

    if collection.count() == 0:
        logger.warning("Vector collection is empty: %s", cfg.collection_name)
        return []

    n_results = n_results or min(cfg.top_k * DEFAULT_VECTOR_MULTIPLIER, collection.count())

    query_vector = embed_query(query, cfg)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks: list[dict[str, Any]] = []

    for index, (doc, meta, distance) in enumerate(zip(docs, metas, distances), start=1):
        # Chroma cosine distance: lower is better.
        vector_score = 1.0 / (1.0 + float(distance))

        chunks.append(
            _make_chunk(
                rank=index,
                text=doc,
                metadata=meta or {},
                distance=float(distance),
                vector_score=vector_score,
                keyword_score=0.0,
                search_mode="vector",
            )
        )

    return chunks


# ---------------------------------------------------------------------
# Keyword search
# ---------------------------------------------------------------------
def _score_keyword_match(
    query: str,
    doc_text: str,
    query_terms: list[str],
    acronyms: list[str],
) -> float:
    normalized_doc = _normalize_text(doc_text)
    normalized_query = _normalize_text(query)

    score = 0.0

    # Phrase match helps queries like "water neutrality" or "3m-7r approach".
    if normalized_query and len(normalized_query) >= 4 and normalized_query in normalized_doc:
        score += PHRASE_BOOST

    for term in query_terms:
        if not term:
            continue

        # Exact word/symbol match.
        if re.search(rf"(?<![a-zA-Z0-9]){re.escape(term)}(?![a-zA-Z0-9])", normalized_doc):
            score += EXACT_TERM_BOOST
        elif term in normalized_doc:
            score += NORMAL_TERM_BOOST

    for acronym in acronyms:
        if re.search(rf"(?<![a-zA-Z0-9]){re.escape(acronym)}(?![a-zA-Z0-9])", normalized_doc):
            score += ACRONYM_BOOST

    return score


def keyword_search(
    query: str,
    cfg: RuntimeConfig,
    max_results: int | None = None,
    scan_limit: int = DEFAULT_KEYWORD_SCAN_LIMIT,
) -> list[dict[str, Any]]:
    """
    Exact keyword fallback for acronyms and short terms.

    Why needed:
    Embedding search often misses short acronym queries like:
    - "full form of NMCG"
    - "What is CGWA?"
    - "3M-7R approach"
    """
    collection = get_collection(cfg)

    if collection.count() == 0:
        return []

    max_results = max_results or cfg.top_k

    query_terms = _extract_query_terms(query)
    acronyms = _extract_acronyms(query)

    if not query_terms and not acronyms:
        return []

    try:
        data = collection.get(
            include=["documents", "metadatas"],
            limit=min(scan_limit, collection.count()),
        )
    except TypeError:
        # Older Chroma versions may not support limit.
        data = collection.get(include=["documents", "metadatas"])

    docs = data.get("documents", [])
    metas = data.get("metadatas", [])

    hits: list[dict[str, Any]] = []

    for doc, meta in zip(docs, metas):
        if not doc:
            continue

        score = _score_keyword_match(
            query=query,
            doc_text=doc,
            query_terms=query_terms,
            acronyms=acronyms,
        )

        if score <= 0:
            continue

        hits.append(
            _make_chunk(
                rank=0,
                text=doc,
                metadata=meta or {},
                distance=0.0,
                vector_score=0.0,
                keyword_score=score,
                search_mode="keyword",
            )
        )

    hits.sort(key=lambda item: item["keyword_score"], reverse=True)

    return hits[:max_results]


# ---------------------------------------------------------------------
# Hybrid merge and rerank
# ---------------------------------------------------------------------
def _merge_chunks(
    vector_chunks: list[dict[str, Any]],
    keyword_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge vector + keyword results.

    If same chunk appears in both, combine scores and mark as hybrid.
    """
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}

    for chunk in vector_chunks:
        key = _chunk_key(chunk)
        merged[key] = chunk

    for chunk in keyword_chunks:
        key = _chunk_key(chunk)

        if key in merged:
            existing = merged[key]
            existing["keyword_score"] += chunk["keyword_score"]
            existing["combined_score"] = existing["vector_score"] + existing["keyword_score"]
            existing["search_mode"] = "hybrid"
        else:
            chunk["combined_score"] = chunk["vector_score"] + chunk["keyword_score"]
            merged[key] = chunk

    return list(merged.values())


def _rerank_chunks(chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """
    Re-rank merged chunks.

    Priority:
    1. Higher combined score
    2. Better vector distance
    """
    ranked = sorted(
        chunks,
        key=lambda item: (
            item.get("combined_score", 0.0),
            -item.get("distance", 999.0),
        ),
        reverse=True,
    )

    final_chunks = ranked[:top_k]

    for index, chunk in enumerate(final_chunks, start=1):
        chunk["rank"] = index

    return final_chunks


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def retrieve(query: str, cfg: RuntimeConfig | None = None) -> list[dict[str, Any]]:
    """
    Retrieve top chunks for a query using hybrid search.

    Steps:
    1. Vector search for semantic similarity.
    2. Keyword search for acronyms/exact terms.
    3. Merge duplicate chunks.
    4. Re-rank and return top-k.

    Returns chunks with:
    - text
    - source
    - page
    - distance
    - search_mode
    - vector_score
    - keyword_score
    """
    cfg = cfg or load_config()

    query = (query or "").strip()

    if not query:
        raise RetrievalError("Query cannot be empty.")

    try:
        vector_chunks = vector_search(
            query=query,
            cfg=cfg,
            n_results=cfg.top_k * DEFAULT_VECTOR_MULTIPLIER,
        )

        keyword_chunks = keyword_search(
            query=query,
            cfg=cfg,
            max_results=cfg.top_k,
        )

        merged_chunks = _merge_chunks(
            vector_chunks=vector_chunks,
            keyword_chunks=keyword_chunks,
        )

        final_chunks = _rerank_chunks(
            chunks=merged_chunks,
            top_k=cfg.top_k,
        )

        logger.info(
            "Retrieval complete | query=%s | vector=%s | keyword=%s | final=%s",
            query[:80],
            len(vector_chunks),
            len(keyword_chunks),
            len(final_chunks),
        )

        return final_chunks

    except Exception as exc:
        logger.exception("Retrieval failed for query: %s", query)
        raise RetrievalError(f"Retrieval failed: {exc}") from exc