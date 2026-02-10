import os
import shutil
import time
from dotenv import load_dotenv
from llama_index.core import (
    VectorStoreIndex, 
    SimpleDirectoryReader, 
    StorageContext, 
    load_index_from_storage,
    Settings
)
from llama_index.core.node_parser import SentenceSplitter

# --- New Drivers ---
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

load_dotenv()

# --- Configure Settings ---
RUN_MODE = os.getenv("RUN_MODE", "cloud")
if RUN_MODE == "local":
    # Use Ollama for LLM (llama-index native driver)
    from llama_index.llms.ollama import Ollama as LlamaOllama
    model_name = os.getenv("LOCAL_WORKER_MODEL")
    Settings.llm = LlamaOllama(model=model_name, base_url=os.getenv("OLLAMA_BASE_URL"))
    # Use Ollama embedding
    from llama_index.embeddings.ollama import OllamaEmbedding
    Settings.embed_model = OllamaEmbedding(model_name=os.getenv("LOCAL_EMBEDED_MODEL"), base_url=os.getenv("OLLAMA_BASE_URL"))
else:
    if os.getenv("GOOGLE_API_KEY"):
        # Embedding Model 
        Settings.embed_model = GoogleGenAIEmbedding(
            model_name=os.getenv("CLOUD_EMBEDED_MODEL"),
            api_key=os.getenv("GOOGLE_API_KEY")
        )
        # LLM 
        Settings.llm = GoogleGenAI(
            model=os.getenv("CLOUD_WORKER_MODEL"),
            api_key=os.getenv("GOOGLE_API_KEY")
        )

def parse_document():
    print("Parsing STCCED 2022 PDF... (Using Free Standard Loader)")
    documents = SimpleDirectoryReader(input_files=["./data/stcced2022.pdf"]).load_data()
    return documents

def get_or_create_index():
    # 1. Check existing storage
    if os.path.exists("./storage"):
        print("Loading existing index from disk...")
        try:
            storage_context = StorageContext.from_defaults(persist_dir="./storage")
            index = load_index_from_storage(storage_context)
            return index
        except Exception as e:
            print(f"Index corrupted ({e}). Deleting and rebuilding...")
            shutil.rmtree("./storage")

    # 2. Build New Index
    print("Building new Knowledge Base (Gemini 2.5 Flash Lite)...")
    documents = parse_document()
    
    splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    nodes = splitter.get_nodes_from_documents(documents)
    print(f"Total chunks to process: {len(nodes)}")

    index = VectorStoreIndex([])

    # Insert in batches
    BATCH_SIZE = 35
    for i in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[i : i + BATCH_SIZE]
        
        for attempt in range(3):
            try:
                print(f"  > Processing batch {(i // BATCH_SIZE) + 1} ({len(batch)} items)...")
                index.insert_nodes(batch)
                
                if RUN_MODE != "local":
                    print("    ⏳ Cooldown 240s to fully reset Token Quota...")
                    time.sleep(240) 
                break 
            except Exception as e:
                print(f"    ⚠️ Error: {e}")
                if "429" in str(e) and RUN_MODE != "local":
                    print("    🛑 Rate limit hit. Waiting 7 minutes...")
                    time.sleep(420)
                else:
                    break

    print("✅ Indexing Complete! Saving to disk...")
    index.storage_context.persist(persist_dir="./storage")
    return index

if __name__ == "__main__":
    if not os.path.exists("./data"): os.makedirs("./data")
    index = get_or_create_index()
    print("Knowledge base is ready.")