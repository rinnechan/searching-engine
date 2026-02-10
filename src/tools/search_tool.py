import os
from llama_index.core import StorageContext, load_index_from_storage

def get_stcced_retriever():
    # Load from /storage
    storage_context = StorageContext.from_defaults(persist_dir="./storage")
    index = load_index_from_storage(storage_context)

    # Use retriever directly — no response synthesizer, no extra LLM call.
    return index.as_retriever(similarity_top_k=5)

def query_stcced(query: str) -> str:
    retriever = get_stcced_retriever()
    nodes = retriever.retrieve(query)
    raw_chunks = [node.get_content() for node in nodes]
    return "\n---\n".join(raw_chunks) if raw_chunks else "No relevant documents found."