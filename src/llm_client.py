import os
import requests
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

load_dotenv()

PROFILE = os.environ.get("LLM_PROFILE", "local").lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_NATIVE_URL = OLLAMA_BASE_URL.rstrip("/").removesuffix("/v1")

if PROFILE == "cloud":
    CHAT_MODEL = "gpt-5.4-nano"
    EMBED_MODEL = "text-embedding-3-small"
    EMBED_DIM = 1536
elif PROFILE == "local":
    CHAT_MODEL = os.environ.get("LOCAL_LLM_MODEL", "gemma3n:e4b")
    EMBED_MODEL = os.environ.get("LOCAL_EMBED_MODEL", "nomic-embed-text")
    EMBED_DIM = 768
else:
    raise ValueError(f"unknown LLM_PROFILE={PROFILE!r}; expected 'local' or 'cloud'")


def _cloud_client():
    return AzureOpenAI(
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
    )


def _local_client():
    return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def get_chat_client():
    return _cloud_client() if PROFILE == "cloud" else _local_client()


class _OllamaEmbedShim:
    """Wraps Ollama's native /api/embed so it returns a shape the calling code expects.
    The OpenAI-compat /v1/embeddings endpoint imposes a small context window that
    rejects normal RAG chunks; the native endpoint accepts options like num_ctx and
    handles longer inputs reliably."""

    def __init__(self, base_url):
        self.base_url = base_url

    class _Embeddings:
        def __init__(self, base_url):
            self.base_url = base_url

        def create(self, model, input):
            inputs = input if isinstance(input, list) else [input]
            data = []
            for text in inputs:
                r = requests.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model, "input": text, "options": {"num_ctx": 8192}},
                    timeout=120,
                )
                r.raise_for_status()
                emb = r.json()["embeddings"][0]
                data.append(type("E", (), {"embedding": emb})())
            return type("R", (), {"data": data})()

    @property
    def embeddings(self):
        return self._Embeddings(self.base_url)


def get_embed_client():
    if PROFILE == "cloud":
        return _cloud_client()
    return _OllamaEmbedShim(OLLAMA_NATIVE_URL)
