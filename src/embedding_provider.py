from __future__ import annotations

import logging
import time
from typing import Iterable

import requests
from openai import AzureOpenAI, OpenAI

from src.config import RuntimeConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Client cache
# ---------------------------------------------------------------------
_azure_clients: dict[str, AzureOpenAI] = {}
_ollama_clients: dict[str, OpenAI] = {}


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
AZURE_BATCH_SIZE = 16
OLLAMA_BATCH_SIZE = 32

AZURE_MAX_RETRIES = 3
OLLAMA_MAX_RETRIES = 2

RETRY_SLEEP_SECONDS = 5
OLLAMA_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------
# Custom errors
# ---------------------------------------------------------------------
class EmbeddingProviderError(RuntimeError):
    """Raised when embedding generation fails."""


# ---------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------
def _azure_client(cfg: RuntimeConfig) -> AzureOpenAI:
    """
    Create/reuse Azure OpenAI client.
    """
    cache_key = f"{cfg.azure_endpoint}|{cfg.azure_api_version}"

    if cache_key not in _azure_clients:
        if not cfg.azure_endpoint or not cfg.azure_api_key:
            raise EmbeddingProviderError(
                "Azure credentials missing. Check AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )

        _azure_clients[cache_key] = AzureOpenAI(
            api_version=cfg.azure_api_version,
            azure_endpoint=cfg.azure_endpoint,
            api_key=cfg.azure_api_key,
        )

    return _azure_clients[cache_key]


def _ollama_client(cfg: RuntimeConfig) -> OpenAI:
    """
    Create/reuse Ollama OpenAI-compatible client.
    """
    cache_key = cfg.ollama_base_url

    if cache_key not in _ollama_clients:
        _ollama_clients[cache_key] = OpenAI(
            base_url=f"{cfg.ollama_base_url}/v1",
            api_key="ollama",
        )

    return _ollama_clients[cache_key]


# ---------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------
def _batch(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _validate_texts(texts: list[str]) -> list[str]:
    """
    Remove empty strings and normalize text input.
    """
    cleaned_texts = []

    for text in texts:
        if text is None:
            continue

        value = str(text).strip()

        if value:
            cleaned_texts.append(value)

    return cleaned_texts


def _sleep_before_retry(attempt: int) -> None:
    sleep_time = RETRY_SLEEP_SECONDS * attempt
    time.sleep(sleep_time)


def _validate_embeddings(
    embeddings: list[list[float]],
    expected_count: int,
    provider_name: str,
) -> None:
    if len(embeddings) != expected_count:
        raise EmbeddingProviderError(
            f"{provider_name} returned {len(embeddings)} embeddings for {expected_count} texts."
        )

    for index, vector in enumerate(embeddings):
        if not isinstance(vector, list) or not vector:
            raise EmbeddingProviderError(
                f"{provider_name} returned invalid embedding at index {index}."
            )


# ---------------------------------------------------------------------
# OpenAI-compatible embedding call
# ---------------------------------------------------------------------
def _embed_with_openai_client(
    client: AzureOpenAI | OpenAI,
    model: str,
    texts: list[str],
    batch_size: int,
    provider_name: str,
    max_retries: int,
) -> list[list[float]]:
    """
    Works for:
    - AzureOpenAI embeddings
    - Ollama OpenAI-compatible /v1/embeddings
    """
    all_embeddings: list[list[float]] = []

    for batch_no, batch in enumerate(_batch(texts, batch_size), start=1):
        for attempt in range(1, max_retries + 1):
            try:
                response = client.embeddings.create(
                    model=model,
                    input=batch,
                )

                batch_embeddings = [item.embedding for item in response.data]

                _validate_embeddings(
                    embeddings=batch_embeddings,
                    expected_count=len(batch),
                    provider_name=provider_name,
                )

                all_embeddings.extend(batch_embeddings)
                break

            except Exception as exc:
                logger.warning(
                    "%s embedding batch %s failed on attempt %s/%s: %s",
                    provider_name,
                    batch_no,
                    attempt,
                    max_retries,
                    exc,
                )

                if attempt == max_retries:
                    raise EmbeddingProviderError(
                        f"{provider_name} embedding failed after {max_retries} attempts."
                    ) from exc

                _sleep_before_retry(attempt)

    return all_embeddings


# ---------------------------------------------------------------------
# Ollama native REST fallback
# ---------------------------------------------------------------------
def _embed_ollama_native_batch(cfg: RuntimeConfig, texts: list[str]) -> list[list[float]]:
    """
    Native Ollama embedding API.

    Uses:
    POST /api/embed

    This endpoint supports batch input for nomic-embed-text.
    """
    response = requests.post(
        f"{cfg.ollama_base_url}/api/embed",
        json={
            "model": cfg.ollama_embed_model,
            "input": texts,
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    data = response.json()

    embeddings = data.get("embeddings")

    if not embeddings:
        raise EmbeddingProviderError(
            f"Ollama /api/embed response did not contain embeddings. Keys: {list(data.keys())}"
        )

    _validate_embeddings(
        embeddings=embeddings,
        expected_count=len(texts),
        provider_name="Ollama native /api/embed",
    )

    return embeddings


def _embed_ollama_native_single(cfg: RuntimeConfig, texts: list[str]) -> list[list[float]]:
    """
    Last fallback for older Ollama versions.

    Uses:
    POST /api/embeddings

    This endpoint usually supports one prompt at a time.
    """
    embeddings: list[list[float]] = []

    for index, text in enumerate(texts, start=1):
        response = requests.post(
            f"{cfg.ollama_base_url}/api/embeddings",
            json={
                "model": cfg.ollama_embed_model,
                "prompt": text,
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )

        response.raise_for_status()
        data = response.json()

        vector = data.get("embedding")

        if not vector:
            raise EmbeddingProviderError(
                f"Ollama /api/embeddings returned no embedding for text index {index}."
            )

        embeddings.append(vector)

    _validate_embeddings(
        embeddings=embeddings,
        expected_count=len(texts),
        provider_name="Ollama native /api/embeddings",
    )

    return embeddings


def _embed_ollama_rest(cfg: RuntimeConfig, texts: list[str]) -> list[list[float]]:
    """
    Fallback path when Ollama OpenAI-compatible embeddings fail.
    """
    try:
        return _embed_ollama_native_batch(cfg, texts)

    except Exception as batch_exc:
        logger.warning(
            "Ollama /api/embed batch failed. Trying /api/embeddings one-by-one: %s",
            batch_exc,
        )

        try:
            return _embed_ollama_native_single(cfg, texts)

        except Exception as single_exc:
            raise EmbeddingProviderError(
                "Ollama native embedding failed using both /api/embed and /api/embeddings."
            ) from single_exc


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def embed_texts(texts: list[str], cfg: RuntimeConfig) -> list[list[float]]:
    """
    Generate embeddings using selected provider.

    Local:
        Ollama + nomic-embed-text

    Azure:
        Azure OpenAI + text-embedding-3-small deployment
    """
    cleaned_texts = _validate_texts(texts)

    if not cleaned_texts:
        return []

    if cfg.uses_azure_embeddings:
        logger.info(
            "Generating Azure embeddings | model=%s | texts=%s",
            cfg.azure_embed_model,
            len(cleaned_texts),
        )

        client = _azure_client(cfg)

        return _embed_with_openai_client(
            client=client,
            model=cfg.azure_embed_model,
            texts=cleaned_texts,
            batch_size=AZURE_BATCH_SIZE,
            provider_name="Azure OpenAI",
            max_retries=AZURE_MAX_RETRIES,
        )

    logger.info(
        "Generating Ollama embeddings | model=%s | texts=%s",
        cfg.ollama_embed_model,
        len(cleaned_texts),
    )

    client = _ollama_client(cfg)

    try:
        return _embed_with_openai_client(
            client=client,
            model=cfg.ollama_embed_model,
            texts=cleaned_texts,
            batch_size=OLLAMA_BATCH_SIZE,
            provider_name="Ollama OpenAI-compatible",
            max_retries=OLLAMA_MAX_RETRIES,
        )

    except Exception as exc:
        logger.warning(
            "Ollama OpenAI-compatible embedding failed. Trying native Ollama API: %s",
            exc,
        )

        return _embed_ollama_rest(cfg, cleaned_texts)


def embed_query(query: str, cfg: RuntimeConfig) -> list[float]:
    """
    Embed a single user query.
    """
    query = query.strip()

    if not query:
        raise EmbeddingProviderError("Query cannot be empty.")

    embeddings = embed_texts([query], cfg)

    if not embeddings:
        raise EmbeddingProviderError("No query embedding was generated.")

    return embeddings[0]


def embedding_dim(cfg: RuntimeConfig) -> int:
    """
    Return embedding dimension for the active embedding provider.

    Expected:
    - nomic-embed-text: 768
    - text-embedding-3-small: commonly 1536
    """
    sample_vector = embed_query("dimension check", cfg)

    return len(sample_vector)