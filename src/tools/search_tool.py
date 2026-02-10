import os
from llama_index.core import StorageContext, load_index_from_storage

def get_stcced_query_engine():
    # Load the persisted index from the /storage directory created during ingestion
    storage_context = StorageContext.from_defaults(persist_dir="./storage")
    index = load_index_from_storage(storage_context)
    
    # Configure the engine for recursive retrieval to handle high-ambiguity cases
    return index.as_query_engine(
        similarity_top_k=5,
        streaming=False
    )

def query_stcced(query: str) -> str:
    engine = get_stcced_query_engine()
    response = engine.query(query)
    return str(response)