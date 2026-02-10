import os
import logging
from dotenv import load_dotenv
from src.tools.search_tool import query_stcced

load_dotenv()
logger = logging.getLogger(__name__)


RUN_MODE = os.getenv("RUN_MODE", "cloud")
if RUN_MODE == "local":
    model_name = os.getenv("LOCAL_WORKER_MODEL")
    from langchain_ollama import ChatOllama
    worker_llm = ChatOllama(model=model_name, base_url=os.getenv("OLLAMA_BASE_URL"))
else:
    model_name = os.getenv("CLOUD_WORKER_MODEL")
    from langchain_google_genai import ChatGoogleGenerativeAI
    worker_llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1)

def worker_node(state: dict):
    """
    The Specialist Worker. 
    Now includes safety truncation to prevent 413/429 errors.
    """
    query_axis = state.get("query")
    
    # 2. Retrieval Step
    # We assume query_stcced returns a string of combined PDF chunks.
    raw_evidence = query_stcced(query_axis)
    
    # We limit to 3,000 characters
    char_limit = 5000
    if len(raw_evidence) > char_limit:
        logger.warning(f"Evidence for {query_axis} truncated from {len(raw_evidence)} to {char_limit} chars.")
        safe_evidence = raw_evidence[:char_limit] + "\n...[TRUNCATED FOR TOKEN LIMITS]..."
    else:
        safe_evidence = raw_evidence
    # --- SAFETY TRUNCATION END ---
    
    CLASSIFICATION_RULES = """CLASSIFICATION RULES:
1. Identify the core product noun (e.g., 'wireless headphone' → core noun is 'headphone').
2. Match the core noun first. If a code explicitly names the core product, use THAT code — do NOT pick 'Other' categories.
3. Only use 'Other' codes if NO code directly names the core product noun.
4. Modifiers like 'wireless', 'Bluetooth', 'industrial' do NOT change classification — they describe features, not different product categories, unless there's actually a different category that matches the exact features.
5. Quote the legal text exactly as written in the evidence.
6. Any codes found in the evidence are REAL tariff lines, not examples."""

    # 3. Reasoning Step
    analysis_prompt = f"""
    You are a Tariff Classification Expert. Your job is to find the correct HS code from the evidence.
    
    PRODUCT TO CLASSIFY: {query_axis}
    RAW EVIDENCE FROM TARIFF SCHEDULE: 
    {safe_evidence}
    
    {CLASSIFICATION_RULES}
    
    OUTPUT FORMAT:
    - **Found Code**: [8-digit or 6-digit code, exactly as shown in the evidence]
    - **Legal Text**: [Direct quote of the line item from the evidence]
    - **Type**: [National Tariff Line OR Heading]
    - **Reasoning**: [Why this code matches the core product noun, referencing the classification rules above]
    """
    
    response = worker_llm.invoke(analysis_prompt)
    
    # Extract token usage from response metadata if available
    usage = getattr(response, "usage_metadata", None) or {}
    tokens = usage.get("total_tokens", 0)
    
    return {"worker_results": [f"Findings for {query_axis}:\n{response.content}"], "total_tokens": tokens, "retrieval_context": [safe_evidence, CLASSIFICATION_RULES]}