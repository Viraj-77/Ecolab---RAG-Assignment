import os
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

load_dotenv()

LLM_PROFILE = os.environ.get("LLM_PROFILE", "cloud").lower()

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "gemma3n:e4b"
OLLAMA_EMBED_MODEL = "nomic-embed-text"

CLOUD_CHAT_MODEL = "gpt-5.4-nano"
CLOUD_EMBED_MODEL = "text-embedding-3-small"


def get_chat_client():
    if LLM_PROFILE == "local":
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    return AzureOpenAI(
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://cds-ds-openai-001-x.openai.azure.com/"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
    )


def get_embed_client():
    if LLM_PROFILE == "local":
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    return AzureOpenAI(
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://cds-ds-openai-001-x.openai.azure.com/"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
    )


def get_chat_model() -> str:
    return OLLAMA_MODEL if LLM_PROFILE == "local" else CLOUD_CHAT_MODEL


def get_embed_model() -> str:
    return OLLAMA_EMBED_MODEL if LLM_PROFILE == "local" else CLOUD_EMBED_MODEL
