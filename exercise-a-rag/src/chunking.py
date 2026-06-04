import tiktoken

_enc = tiktoken.get_encoding("cl100k_base") #c1100k is a tokenizer called to break down text into tokens and it has rules on how to do it  
#_enc is a variable we declared to store rules

CHUNK_TOKENS = 800   # 600 works/chunk
OVERLAP_TOKENS = 100  # 12.5% overlap 


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


def chunk_document(doc: dict) -> list[dict]: #takes data in dict and returns chunks in list add id along with source and text
  
    raw_chunks = split_text(doc["text"])
    return [
        {"source": doc["source"], "chunk_id": i, "text": chunk}
        for i, chunk in enumerate(raw_chunks)
    ]