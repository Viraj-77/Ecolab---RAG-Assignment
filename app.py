from __future__ import annotations

import logging
import re
from pathlib import Path

import streamlit as st

from src.chromadb_setup import get_collection
from src.config import load_config
from src.conversational_memory import ConversationMemory
from src.index_documents import ingest
from src.rag_pipeline import SYSTEM_PROMPT, chat


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# App constants
# ---------------------------------------------------------------------
APP_TITLE = "Ecolab Water Intelligence RAG"
APP_ICON = "💧"

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "Data"
DATA_DIR.mkdir(exist_ok=True)

LOCAL_LLM_MODELS = [
    "gemma3n:e4b",
    "gemma3:1b",
    "gemma3:4b",
    "gemma3:12b",
]

LOCAL_EMBEDDING_MODELS = [
    "nomic-embed-text",
]

AZURE_CHAT_DEPLOYMENTS = [
    "gpt-5.4-nano",
]

AZURE_EMBEDDING_DEPLOYMENTS = [
    "text-embedding-3-small",
]

ALLOWED_UPLOAD_TYPES = ["pdf"]


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------
def safe_filename(filename: str) -> str:
    """
    Prevent path traversal and unsafe file names.
    """
    name = Path(filename).name
    name = re.sub(r"[^a-zA-Z0-9_. -]", "_", name)
    name = name.strip()

    if not name:
        return "uploaded_file.pdf"

    return name


def reset_chat_state() -> None:
    st.session_state.memory = ConversationMemory(SYSTEM_PROMPT)
    st.session_state.messages = []


def validate_runtime_selection(
    llm_profile: str,
    embedding_profile: str,
    azure_chat_model: str | None,
    azure_embed_model: str | None,
) -> list[str]:
    """
    UI-level warnings only. Real validation still happens inside backend providers.
    """
    warnings: list[str] = []

    if llm_profile == "azure" and not azure_chat_model:
        warnings.append("Azure LLM is selected, but Azure chat deployment is empty.")

    if embedding_profile == "azure" and not azure_embed_model:
        warnings.append("Azure embedding is selected, but Azure embedding deployment is empty.")

    if llm_profile == "local":
        warnings.append(
            "Local Gemma mode is used for answer generation. "
            "Your current gemma3n:e4b model may not support OpenAI-style tools."
        )

    if embedding_profile == "azure":
        warnings.append(
            "Azure embedding selected. Make sure `.env` has real Azure endpoint and API key."
        )

    return warnings


def show_uploaded_documents() -> None:
    files = sorted(DATA_DIR.glob("*"))

    if not files:
        st.info("No documents found in Data/ yet.")
        return

    st.caption("Documents currently available for indexing:")

    for file in files:
        if file.is_file():
            size_mb = file.stat().st_size / (1024 * 1024)
            st.write(f"- `{file.name}` — {size_mb:.2f} MB")


# ---------------------------------------------------------------------
# Streamlit page setup
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Ecolab Local/Cloud RAG",
    page_icon=APP_ICON,
    layout="wide",
)

st.title(f"{APP_ICON} {APP_TITLE}")
st.caption(
    "One RAG pipeline with selectable Azure or Ollama runtime. "
    "Upload PDFs, build vector DB, retrieve top chunks, and generate grounded answers."
)


# ---------------------------------------------------------------------
# Sidebar: runtime selection
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("Runtime Selection")

    llm_profile = st.selectbox(
        "LLM provider",
        options=["local", "azure"],
        index=0,
        key="llm_provider_select",
        help="local = Ollama Gemma. azure = Azure OpenAI chat deployment.",
    )

    embedding_profile = st.selectbox(
        "Embedding provider",
        options=["local", "azure"],
        index=0,
        key="embedding_provider_select",
        help="local = Ollama nomic-embed-text. azure = Azure text-embedding-3-small.",
    )

    st.divider()

    # -------------------------
    # LLM model selection
    # -------------------------
    if llm_profile == "local":
        ollama_llm_model = st.selectbox(
            "Ollama LLM model",
            options=LOCAL_LLM_MODELS,
            index=0,
            key="ollama_llm_model_select",
            help="Use gemma3n:e4b because this is the model currently pulled in your Ollama.",
        )
        azure_chat_model = None

    else:
        azure_chat_model = st.selectbox(
            "Azure Chat deployment",
            options=AZURE_CHAT_DEPLOYMENTS,
            index=0,
            key="azure_chat_model_select",
            help="Azure OpenAI chat deployment name.",
        )
        ollama_llm_model = None

    # -------------------------
    # Embedding model selection
    # -------------------------
    if embedding_profile == "local":
        ollama_embed_model = st.selectbox(
            "Ollama embedding model",
            options=LOCAL_EMBEDDING_MODELS,
            index=0,
            key="ollama_embedding_model_select",
            help="Local embedding model through Ollama.",
        )
        azure_embed_model = None

    else:
        azure_embed_model = st.selectbox(
            "Azure embedding deployment",
            options=AZURE_EMBEDDING_DEPLOYMENTS,
            index=0,
            key="azure_embedding_model_select",
            help="Azure embedding deployment name.",
        )
        ollama_embed_model = None

    st.divider()

    top_k = st.slider(
        "Top-K retrieved chunks",
        min_value=3,
        max_value=10,
        value=5,
        step=1,
        key="top_k_slider",
        help="Higher Top-K gives more context but increases token usage.",
    )

    chunk_tokens = st.slider(
        "Chunk tokens",
        min_value=300,
        max_value=1200,
        value=650,
        step=50,
        key="chunk_tokens_slider",
        help="Chunk size used during indexing.",
    )

    overlap_tokens = st.slider(
        "Overlap tokens",
        min_value=50,
        max_value=250,
        value=100,
        step=25,
        key="overlap_tokens_slider",
        help="Overlap avoids losing context between chunks.",
    )

    cfg = load_config(
        llm_profile=llm_profile,
        embedding_profile=embedding_profile,
        ollama_llm_model=ollama_llm_model,
        ollama_embed_model=ollama_embed_model,
        azure_chat_model=azure_chat_model,
        azure_embed_model=azure_embed_model,
        top_k=top_k,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
    )

    warnings = validate_runtime_selection(
        llm_profile=llm_profile,
        embedding_profile=embedding_profile,
        azure_chat_model=azure_chat_model,
        azure_embed_model=azure_embed_model,
    )

    for warning in warnings:
        st.warning(warning)

    st.divider()

    st.subheader("Selected Stack")

    st.code(
        f"LLM provider       : {cfg.llm_profile}\n"
        f"LLM model          : {cfg.resolved_llm_model}\n"
        f"Embedding provider : {cfg.embedding_profile}\n"
        f"Embedding model    : {cfg.resolved_embedding_model}\n"
        f"Vector DB          : ChromaDB\n"
        f"Collection         : {cfg.collection_name}\n"
        f"Top-K              : {cfg.top_k}\n"
        f"Chunk tokens       : {cfg.chunk_tokens}\n"
        f"Overlap tokens     : {cfg.overlap_tokens}",
        language="text",
    )

    try:
        vector_count = get_collection(cfg).count()
        st.metric("Vectors in selected collection", vector_count)
    except Exception as exc:
        logger.exception("Failed to read selected ChromaDB collection")
        st.warning(f"Could not read vector DB: {exc}")

    st.divider()

    st.subheader("PDF Upload + Indexing")

    uploaded_files = st.file_uploader(
        "Upload PDF files",
        type=ALLOWED_UPLOAD_TYPES,
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files:
        saved_count = 0

        for uploaded_file in uploaded_files:
            filename = safe_filename(uploaded_file.name)
            output_path = DATA_DIR / filename

            try:
                output_path.write_bytes(uploaded_file.getbuffer())
                saved_count += 1
            except Exception as exc:
                logger.exception("Failed to save uploaded file: %s", filename)
                st.error(f"Failed to save `{filename}`: {exc}")

        if saved_count:
            st.success(f"Saved {saved_count} PDF file(s) into `Data/`.")

    with st.expander("Show uploaded documents"):
        show_uploaded_documents()

    st.info(
        "Indexing depends on the selected embedding provider. "
        "Local embedding creates a local Chroma collection. "
        "Azure embedding creates a separate Azure-embedding collection."
    )

    if st.button("Build / Rebuild Vector DB", type="primary", key="build_vector_db_btn"):
        with st.spinner(
            "Extracting text → cleaning → chunking → embedding → storing in ChromaDB..."
        ):
            try:
                count = ingest(cfg, reset=True)
                st.success(f"Indexing complete. Vector count: {count}")
            except Exception as exc:
                logger.exception("Indexing failed")
                st.error(f"Indexing failed: {exc}")

    st.divider()

    if st.button("Reset chat memory", key="reset_chat_btn"):
        reset_chat_state()
        st.rerun()


# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------
config_key = (
    cfg.llm_profile,
    cfg.embedding_profile,
    cfg.resolved_llm_model,
    cfg.resolved_embedding_model,
    cfg.top_k,
    cfg.chunk_tokens,
    cfg.overlap_tokens,
)

if "config_key" not in st.session_state:
    st.session_state.config_key = config_key

if "memory" not in st.session_state:
    st.session_state.memory = ConversationMemory(SYSTEM_PROMPT)

if "messages" not in st.session_state:
    st.session_state.messages = []

if st.session_state.config_key != config_key:
    st.session_state.config_key = config_key
    reset_chat_state()
    st.toast("Runtime changed. Chat memory reset for clean comparison.", icon="🔄")


# ---------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------
left_col, right_col = st.columns([0.72, 0.28])

with right_col:
    st.subheader("Run checklist")

    st.markdown(
        """
        **For local mode**
        1. Ollama running on `localhost:11434`
        2. Model: `gemma3n:e4b`
        3. Embedding: `nomic-embed-text`
        4. Build vector DB using local embedding

        **For Azure mode**
        1. Add real Azure keys in `.env`
        2. Select Azure LLM + Azure embedding
        3. Build vector DB using Azure embedding
        """
    )

    st.subheader("Good test questions")
    st.code(
        "What is water neutrality?\n"
        "Explain the seven principles of water neutrality.\n"
        "What is the role of supply chains in water neutrality?\n"
        "What is 3M-7R approach?",
        language="text",
    )

with left_col:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "Ask about water treatment, SOPs, sustainability, or the uploaded PDF..."
    )

    if user_input:
        st.session_state.messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving context and generating answer..."):
                try:
                    result = chat(
                        memory=st.session_state.memory,
                        user_message=user_input,
                        cfg=cfg,
                    )

                    st.markdown(result.answer)

                    with st.expander("Retrieved chunks and runtime details"):
                        st.write(f"Latency: `{result.latency_sec}` sec")
                        st.write(f"Tools called: `{result.tool_names or 'None'}`")

                        for chunk in result.chunks:
                            st.markdown(
                                f"**S{chunk['rank']}** — "
                                f"`{chunk['source']}`, page `{chunk['page']}`, "
                                f"distance `{chunk['distance']:.4f}`"
                            )

                            preview = chunk["text"][:1200]
                            if len(chunk["text"]) > 1200:
                                preview += "..."

                            st.write(preview)

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": result.answer,
                        }
                    )

                except Exception as exc:
                    logger.exception("Chat request failed")

                    error_msg = (
                        "Something went wrong while generating the answer.\n\n"
                        f"Error: `{exc}`"
                    )

                    st.error(error_msg)

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": error_msg,
                        }
                    )