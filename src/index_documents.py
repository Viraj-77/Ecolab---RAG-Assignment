import os
import time
from dotenv import load_dotenv
from openai import AzureOpenAI
from src.document_loading import load_all_documents
from src.chunking import chunk_document
from src.chromadb_setup import get_collection

load_dotenv()

#taken from .md file from teams
client = AzureOpenAI(
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)


def embed(texts):
    #we send text in batch of 16 cause api hits rate limit
    embeddings = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + 16]  #take the next 16 texts
        try:
            res = client.embeddings.create(model="text-embedding-3-small", input=batch)  #converting text to vectors
            embeddings += [d.embedding for d in res.data]  #pull the vectors out of the response
            time.sleep(1)
        except Exception as e:
            print("batch failed, retrying in 10s:", e)
            time.sleep(10)
            res = client.embeddings.create(model="text-embedding-3-small", input=batch)
            embeddings += [d.embedding for d in res.data]

    return embeddings


def ingest():
    #load all pdfs from our folder
    docs = load_all_documents()
    if not docs:
        print("no documents found")
        return

    #split each pdf into chunks
    chunks = []
    for doc in docs:
        chunks += chunk_document(doc)

    #check whats already in chromadb so we dont reindex stuff
    col = get_collection()
    already_indexed = set(col.get()["ids"])  #set of chunk IDs already stored
    new_chunks = [c for c in chunks if f"{c['source']}_{c['chunk_id']}" not in already_indexed]

    if not new_chunks:
        print("nothing new to index")
        return

    #pull out the text, ids, and metadata for the new chunks
    texts = [c["text"] for c in new_chunks]
    ids = [f"{c['source']}_{c['chunk_id']}" for c in new_chunks]
    metas = [{"source": c["source"]} for c in new_chunks]

    #embed the texts and store everything in chromadb
    col.add(ids=ids, embeddings=embed(texts), documents=texts, metadatas=metas)
    print("indexing done")


if __name__ == "__main__":
    ingest()