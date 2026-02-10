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
    query_axis = state.get("query")
    raw_evidence = query_stcced(query_axis)
    
    # Limit evidence length to avoid token overages
    char_limit = 5000
    if len(raw_evidence) > char_limit:
        logger.warning(f"Evidence for {query_axis} truncated from {len(raw_evidence)} to {char_limit} chars.")
        safe_evidence = raw_evidence[:char_limit] + "\n...[TRUNCATED FOR TOKEN LIMITS]..."
    else:
        safe_evidence = raw_evidence
    
    CLASSIFICATION_RULES = """CLASSIFICATION RULES:
1. Identify the core product noun (e.g., 'wireless headphone' → core noun is 'headphone').
2. ALWAYS prefer the code whose description EXPLICITLY NAMES the core product noun.
   Example: If you see '8518.30.10 - Headphones' AND '8518.30.59 - Other', PICK 8518.30.10 because it names 'Headphones'.
3. NEVER pick 'Other' or 'Other NMB' codes when a code that names the product exists in the evidence.
4. Modifiers like 'wireless', 'Bluetooth', 'industrial' do NOT change classification — the tariff line does NOT need to say 'wireless'. A line saying 'Headphones' covers ALL headphones (wired, wireless, etc.) unless a separate 'wireless' line exists.
5. Any codes found in the evidence are REAL tariff lines, not examples.
6. NEVER paraphrase or summarize tariff text. Copy it EXACTLY, character for character."""

    analysis_prompt = f"""
    You are a Tariff Classification Expert. Your job is to find the correct HS code from the evidence below.
    
    PRODUCT TO CLASSIFY: {query_axis}
    
    RAW EVIDENCE FROM TARIFF SCHEDULE:
    {safe_evidence}
    
    {CLASSIFICATION_RULES}
    
    STEP 1 — LIST ALL CODES: Copy every line from the evidence that contains an HS code (format: XXXX.XX or XXXX.XX.XX).
    For each line, copy the ENTIRE line exactly as it appears — code, description, unit, everything. Do NOT summarize or skip any lines.
    
    STEP 2 — PICK THE BEST MATCH:
    Look at all codes from Step 1. Which code's description EXPLICITLY NAMES the core product noun?
    - ONLY pick "Other" if NO code in Step 1 names the core product
    
    - **Found Code**: [the 8-digit code whose description names the core product]
    - **Exact Tariff Line**: [copy-paste the FULL line from Step 1, character for character]
    - **Type**: [National Tariff Line (8-digit) OR Heading (6-digit)]
    - **Reasoning**: [Why this code's description matches the core product noun. If you picked an 'Other' code, explain why no code names the product.]
    
    IMPORTANT: The "Exact Tariff Line" MUST be copied from the evidence verbatim. If you cannot find it, say "NOT FOUND IN EVIDENCE".
    """
    
    response = worker_llm.invoke(analysis_prompt)
    
    # Extract token usage from response metadata if available
    usage = getattr(response, "usage_metadata", None) or {}
    tokens = usage.get("total_tokens", 0)
    
    return {"worker_results": [f"Findings for {query_axis}:\n{response.content}"], "total_tokens": tokens, "retrieval_context": [safe_evidence, CLASSIFICATION_RULES]}