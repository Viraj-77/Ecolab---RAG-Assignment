import tiktoken
from src.llm_client import PROFILE

_enc = tiktoken.get_encoding("cl100k_base")

# nomic-embed-text default Ollama context is 2048 tokens (BERT tokenizer ≠ cl100k);
# 400 cl100k tokens gives a comfortable margin. Cloud embedder handles 800 fine.
CHUNK_TOKENS = 384 if PROFILE == "local" else 800
OVERLAP_TOKENS = 48 if PROFILE == "local" else 100
MAX_CHARS_LOCAL = 1500


def split_text(text: str, chunk_size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]: #name says it all
    #split the tnput data into overlapping i.e 12.5 % tokens into chunks
    tokens = _enc.encode(text) #convert the input into  list of token IDs 
    chunks = [] #store chunks 
    start = 0 #index in ciurrent chunk in token list
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(_enc.decode(tokens[start:end]))
        start += chunk_size - overlap
    return chunks


def chunk_document(doc: dict) -> list[dict]:
    raw_chunks = split_text(doc["text"])
    if PROFILE == "local":
        raw_chunks = [c[:MAX_CHARS_LOCAL] for c in raw_chunks]
    return [
        {"source": doc["source"], "chunk_id": i, "text": chunk}
        for i, chunk in enumerate(raw_chunks)
    ]