import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from src.chromadb_setup import get_collection

load_dotenv()
#again taken from .md file from teams
client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint="https://cds-ds-openai-001-x.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

TOP_K = 4  #number of chunks to pull per query

def retrieve(query: str) -> list[dict]:
    #embed the query, then find the closest chunks in the vector store
    vec = client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    ).data[0].embedding

    results = get_collection().query(
        query_embeddings=[vec],
        n_results=TOP_K,
        include=["documents", "metadatas"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]

    return [
        {"text": doc, "source": meta.get("source", "unknown")}
        for doc, meta in zip(docs, metas)
    ]