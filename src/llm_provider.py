from __future__ import annotations

import logging
import time
from typing import Any

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
LOCAL_TEMPERATURE = 0.1
AZURE_TEMPERATURE = 0.1

LOCAL_MAX_RETRIES = 2
AZURE_MAX_RETRIES = 3

RETRY_SLEEP_SECONDS = 3


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class LLMProviderError(RuntimeError):
    """Raised when LLM response generation fails."""


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
            raise LLMProviderError(
                "Azure credentials missing. Check AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )

        _azure_clients[cache_key] = AzureOpenAI(
            api_version=cfg.azure_api_version,
            azure_endpoint=cfg.azure_endpoint,
            api_key=cfg.azure_api_key,
        )

        logger.info("Azure OpenAI client initialized.")

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

        logger.info("Ollama client initialized at %s", cfg.ollama_base_url)

    return _ollama_clients[cache_key]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _sleep_before_retry(attempt: int) -> None:
    time.sleep(RETRY_SLEEP_SECONDS * attempt)


def _is_tool_support_error(error: Exception) -> bool:
    """
    Detect Ollama/local model error when tools are unsupported.
    """
    message = str(error).lower()

    tool_error_signals = [
        "does not support tools",
        "tools not supported",
        "tool calling is not supported",
        "invalid_request_error",
    ]

    return any(signal in message for signal in tool_error_signals)


def _build_local_kwargs(
    messages: list[dict[str, Any]],
    cfg: RuntimeConfig,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": cfg.ollama_llm_model,
        "messages": messages,
        "temperature": LOCAL_TEMPERATURE,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return kwargs


def _build_azure_kwargs(
    messages: list[dict[str, Any]],
    cfg: RuntimeConfig,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": cfg.azure_chat_model,
        "messages": messages,
        "temperature": AZURE_TEMPERATURE,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return kwargs


# ---------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------
def _local_chat_completion(
    messages: list[dict[str, Any]],
    cfg: RuntimeConfig,
    tools: list[dict[str, Any]] | None = None,
):
    """
    Local chat completion using Ollama OpenAI-compatible endpoint.

    Note:
    Your current model `gemma3n:e4b` may not support tool calling.
    If tools fail, we retry once without tools.
    """
    client = _ollama_client(cfg)
    kwargs = _build_local_kwargs(messages=messages, cfg=cfg, tools=tools)

    for attempt in range(1, LOCAL_MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)

        except Exception as exc:
            if tools and _is_tool_support_error(exc):
                logger.warning(
                    "Local model `%s` does not support tools. Retrying without tools.",
                    cfg.ollama_llm_model,
                )

                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)

                return client.chat.completions.create(**kwargs)

            logger.warning(
                "Local Ollama chat failed on attempt %s/%s: %s",
                attempt,
                LOCAL_MAX_RETRIES,
                exc,
            )

            if attempt == LOCAL_MAX_RETRIES:
                raise LLMProviderError(
                    f"Local Ollama chat failed after {LOCAL_MAX_RETRIES} attempts."
                ) from exc

            _sleep_before_retry(attempt)

    raise LLMProviderError("Local Ollama chat failed unexpectedly.")


def _azure_chat_completion(
    messages: list[dict[str, Any]],
    cfg: RuntimeConfig,
    tools: list[dict[str, Any]] | None = None,
):
    """
    Azure OpenAI chat completion.
    """
    client = _azure_client(cfg)
    kwargs = _build_azure_kwargs(messages=messages, cfg=cfg, tools=tools)

    for attempt in range(1, AZURE_MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)

        except Exception as exc:
            logger.warning(
                "Azure chat failed on attempt %s/%s: %s",
                attempt,
                AZURE_MAX_RETRIES,
                exc,
            )

            if attempt == AZURE_MAX_RETRIES:
                raise LLMProviderError(
                    f"Azure chat failed after {AZURE_MAX_RETRIES} attempts."
                ) from exc

            _sleep_before_retry(attempt)

    raise LLMProviderError("Azure chat failed unexpectedly.")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def chat_completion(
    messages: list[dict[str, Any]],
    cfg: RuntimeConfig,
    tools: list[dict[str, Any]] | None = None,
):
    """
    Generate chat completion using active LLM provider.

    Local:
        Ollama + gemma3n:e4b

    Azure:
        Azure OpenAI + gpt-5.4-nano deployment
    """
    if not messages:
        raise LLMProviderError("messages cannot be empty.")

    if cfg.uses_local_llm:
        logger.info("Calling local LLM | model=%s", cfg.ollama_llm_model)

        return _local_chat_completion(
            messages=messages,
            cfg=cfg,
            tools=tools,
        )

    logger.info("Calling Azure LLM | deployment=%s", cfg.azure_chat_model)

    return _azure_chat_completion(
        messages=messages,
        cfg=cfg,
        tools=tools,
    )