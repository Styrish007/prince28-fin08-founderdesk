import chromadb
from chromadb.config import Settings
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = "schemes"

_client = None
_collection = None

def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        Path(PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
    return _client

def get_collection():
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection

def reset_collection():
    global _collection
    client = get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass
    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    return _collection
