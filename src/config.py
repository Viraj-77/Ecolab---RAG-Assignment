from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
SUPPORTED_PROFILES = {"local", "azure"}
SUPPORTED_VECTOR_STORES = {"chroma"}

DEFAULT_LLM_PROFILE = "local"
DEFAULT_EMBEDDING_PROFILE = "local"

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_LLM_MODEL = "gemma3n:e4b"
DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"

DEFAULT_AZURE_API_VERSION = "2024-12-01-preview"
DEFAULT_AZURE_CHAT_MODEL = "gpt-5.4-nano"
DEFAULT_AZURE_EMBED_MODEL = "text-embedding-3-small"

DEFAULT_VECTOR_STORE = "chroma"
DEFAULT_TOP_K = 5
DEFAULT_CHUNK_TOKENS = 650
DEFAULT_OVERLAP_TOKENS = 100

MIN_TOP_K = 1
MAX_TOP_K = 20

MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 2000

MIN_OVERLAP_TOKENS = 0
MAX_OVERLAP_TOKENS = 500


# ---------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    """
    Read string value from environment.

    Empty strings are treated as missing and replaced with default.
    """
    value = os.getenv(name, default)

    if value is None:
        return default

    value = value.strip()

    return value if value else default


def _env_int(name: str, default: int) -> int:
    """
    Read integer value from environment with safe fallback.
    """
    raw_value = _env(name, str(default))

    try:
        return int(raw_value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer. Got: {raw_value}")


def slug(text: str) -> str:
    """
    Convert model/provider text into a safe Chroma collection-name component.
    """
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip())
    value = value.strip("-").lower()

    return value or "default"


def _is_placeholder(value: str) -> bool:
    """
    Detect placeholder Azure values so the app fails clearly instead of silently.
    """
    lowered = value.strip().lower()

    placeholders = {
        "",
        "replace-with-your-key",
        "your_key",
        "your-real-key",
        "your_real_key",
        "your_chat_deployment_name",
        "your-real-resource",
    }

    if lowered in placeholders:
        return True

    if "your-resource-name" in lowered:
        return True

    if "your-real-resource" in lowered:
        return True

    return False


# ---------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class RuntimeConfig:
    """
    Single runtime configuration for the full RAG stack.

    llm_profile:
        Controls final answer generation.
        local = Ollama
        azure = Azure OpenAI

    embedding_profile:
        Controls PDF/query vector creation.
        local = Ollama embedding model
        azure = Azure OpenAI embedding deployment

    Important:
        Chroma collection name is based on embedding provider + embedding model.
        This prevents mixing Azure 1536-dim embeddings with local 768-dim embeddings.
    """

    llm_profile: str = DEFAULT_LLM_PROFILE
    embedding_profile: str = DEFAULT_EMBEDDING_PROFILE

    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_llm_model: str = DEFAULT_OLLAMA_LLM_MODEL
    ollama_embed_model: str = DEFAULT_OLLAMA_EMBED_MODEL

    azure_api_version: str = DEFAULT_AZURE_API_VERSION
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_chat_model: str = DEFAULT_AZURE_CHAT_MODEL
    azure_embed_model: str = DEFAULT_AZURE_EMBED_MODEL

    vector_store: str = DEFAULT_VECTOR_STORE
    top_k: int = DEFAULT_TOP_K
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS

    @property
    def resolved_llm_model(self) -> str:
        if self.llm_profile == "local":
            return self.ollama_llm_model

        return self.azure_chat_model

    @property
    def resolved_embedding_model(self) -> str:
        if self.embedding_profile == "local":
            return self.ollama_embed_model

        return self.azure_embed_model

    @property
    def chroma_dir(self) -> str:
        return "chroma_db"

    @property
    def collection_name(self) -> str:
        """
        Collection depends on embedding model, chunking config, and vector DB.

        LLM model is intentionally not included because LLM does not affect vector dimensions.
        """
        return (
            "ecolab_"
            f"emb-{slug(self.embedding_profile)}_"
            f"model-{slug(self.resolved_embedding_model)}_"
            f"ct{self.chunk_tokens}_"
            f"ov{self.overlap_tokens}"
        )

    @property
    def uses_local_llm(self) -> bool:
        return self.llm_profile == "local"

    @property
    def uses_azure_llm(self) -> bool:
        return self.llm_profile == "azure"

    @property
    def uses_local_embeddings(self) -> bool:
        return self.embedding_profile == "local"

    @property
    def uses_azure_embeddings(self) -> bool:
        return self.embedding_profile == "azure"

    def validate(self) -> None:
        self._validate_profiles()
        self._validate_models()
        self._validate_vector_store()
        self._validate_retrieval_settings()
        self._validate_azure_settings_when_required()

    def _validate_profiles(self) -> None:
        if self.llm_profile not in SUPPORTED_PROFILES:
            raise ValueError(
                f"llm_profile must be one of {sorted(SUPPORTED_PROFILES)}. "
                f"Got: {self.llm_profile}"
            )

        if self.embedding_profile not in SUPPORTED_PROFILES:
            raise ValueError(
                f"embedding_profile must be one of {sorted(SUPPORTED_PROFILES)}. "
                f"Got: {self.embedding_profile}"
            )

    def _validate_models(self) -> None:
        if self.uses_local_llm and not self.ollama_llm_model:
            raise ValueError("OLLAMA_LLM_MODEL cannot be empty when local LLM is selected.")

        if self.uses_local_embeddings and not self.ollama_embed_model:
            raise ValueError("OLLAMA_EMBED_MODEL cannot be empty when local embeddings are selected.")

        if self.uses_azure_llm and not self.azure_chat_model:
            raise ValueError("AZURE_OPENAI_CHAT_MODEL cannot be empty when Azure LLM is selected.")

        if self.uses_azure_embeddings and not self.azure_embed_model:
            raise ValueError("AZURE_OPENAI_EMBED_MODEL cannot be empty when Azure embeddings are selected.")

    def _validate_vector_store(self) -> None:
        if self.vector_store not in SUPPORTED_VECTOR_STORES:
            raise ValueError(
                f"vector_store must be one of {sorted(SUPPORTED_VECTOR_STORES)}. "
                f"Got: {self.vector_store}"
            )

    def _validate_retrieval_settings(self) -> None:
        if not MIN_TOP_K <= self.top_k <= MAX_TOP_K:
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}.")

        if not MIN_CHUNK_TOKENS <= self.chunk_tokens <= MAX_CHUNK_TOKENS:
            raise ValueError(
                f"chunk_tokens must be between {MIN_CHUNK_TOKENS} and {MAX_CHUNK_TOKENS}."
            )

        if not MIN_OVERLAP_TOKENS <= self.overlap_tokens <= MAX_OVERLAP_TOKENS:
            raise ValueError(
                f"overlap_tokens must be between {MIN_OVERLAP_TOKENS} and {MAX_OVERLAP_TOKENS}."
            )

        if self.chunk_tokens <= self.overlap_tokens:
            raise ValueError("chunk_tokens must be greater than overlap_tokens.")

    def _validate_azure_settings_when_required(self) -> None:
        """
        Only validate Azure credentials when Azure is actually selected.
        This allows local-only mode to run without Azure secrets.
        """
        azure_required = self.uses_azure_llm or self.uses_azure_embeddings

        if not azure_required:
            return

        if _is_placeholder(self.azure_endpoint):
            raise ValueError(
                "Azure is selected, but AZURE_OPENAI_ENDPOINT is missing or still a placeholder."
            )

        if _is_placeholder(self.azure_api_key):
            raise ValueError(
                "Azure is selected, but AZURE_OPENAI_API_KEY is missing or still a placeholder."
            )


# ---------------------------------------------------------------------
# Public config loader
# ---------------------------------------------------------------------
def load_config(
    llm_profile: str | None = None,
    embedding_profile: str | None = None,
    ollama_llm_model: str | None = None,
    ollama_embed_model: str | None = None,
    azure_chat_model: str | None = None,
    azure_embed_model: str | None = None,
    top_k: int | None = None,
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> RuntimeConfig:
    """
    Load runtime config from function overrides first, then .env.

    Streamlit passes overrides from the sidebar.
    CLI scripts usually rely on .env.
    """

    cfg = RuntimeConfig(
        llm_profile=(llm_profile or _env("LLM_PROFILE", DEFAULT_LLM_PROFILE)).lower(),
        embedding_profile=(
            embedding_profile or _env("EMBEDDING_PROFILE", DEFAULT_EMBEDDING_PROFILE)
        ).lower(),

        ollama_base_url=_env("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
        ollama_llm_model=ollama_llm_model or _env(
            "OLLAMA_LLM_MODEL",
            DEFAULT_OLLAMA_LLM_MODEL,
        ),
        ollama_embed_model=ollama_embed_model or _env(
            "OLLAMA_EMBED_MODEL",
            DEFAULT_OLLAMA_EMBED_MODEL,
        ),

        azure_api_version=_env("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_API_VERSION),
        azure_endpoint=_env("AZURE_OPENAI_ENDPOINT", ""),
        azure_api_key=_env("AZURE_OPENAI_API_KEY", ""),
        azure_chat_model=azure_chat_model or _env(
            "AZURE_OPENAI_CHAT_MODEL",
            DEFAULT_AZURE_CHAT_MODEL,
        ),
        azure_embed_model=azure_embed_model or _env(
            "AZURE_OPENAI_EMBED_MODEL",
            DEFAULT_AZURE_EMBED_MODEL,
        ),

        vector_store=_env("VECTOR_STORE", DEFAULT_VECTOR_STORE).lower(),
        top_k=top_k if top_k is not None else _env_int("TOP_K", DEFAULT_TOP_K),
        chunk_tokens=(
            chunk_tokens
            if chunk_tokens is not None
            else _env_int("CHUNK_TOKENS", DEFAULT_CHUNK_TOKENS)
        ),
        overlap_tokens=(
            overlap_tokens
            if overlap_tokens is not None
            else _env_int("OVERLAP_TOKENS", DEFAULT_OVERLAP_TOKENS)
        ),
    )

    cfg.validate()

    return cfg