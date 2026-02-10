import os
from typing import List, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langgraph.constants import Send
from src.agents.state import AuditorState
import logging

logger = logging.getLogger(__name__)

load_dotenv()
RUN_MODE = os.getenv("RUN_MODE", "cloud")
if RUN_MODE == "local":
    model_name = os.getenv("LOCAL_GROQ_MODEL")
    from langchain_ollama import ChatOllama
    llm_factory = lambda: ChatOllama(model=model_name, base_url=os.getenv("OLLAMA_BASE_URL"))
else:
    model_name = os.getenv("CLOUD_GROQ_MODEL")
    llm_factory = lambda: ChatGroq(model=model_name, temperature=0, verbose=True)

# --- 1. STRUCTURED OUTPUT SCHEMAS ---

class TriagePlan(BaseModel):
    """
    The 'Sniper' Plan.
    We enforce a single, highly specific search query to save API calls
    and prevent rate-limit crashes.
    """
    search_query: str = Field(description="One targeted, specific search query (e.g., 'HS Code for Wireless Headphones 8518.30')")

class AuditReview(BaseModel):
    """The result of the Auditor's skeptical review."""
    status: Literal["APPROVED", "REVISE"] = Field(description="Decision to finish or retry")
    critique: str = Field(description="Reasoning for the decision")

# --- 2. HELPER FUNCTIONS ---

def load_prompt(filename: str) -> str:
    """
    Loads a markdown prompt template from the prompts directory.
    """
    path = os.path.join("prompts", filename)
    if not os.path.exists(path):
        # Fallback if file is missing (prevents crash during setup)
        return f"Error: {filename} not found."
    with open(path, "r") as f:
        return f.read()

# --- 3. GRAPH NODES ---

def supervisor_node(state: AuditorState):
    """
    NODE: PLANNER
    Reads 'decomposition_strategy.md' and generates ONE specific search task.
    """
    llm = llm_factory().with_structured_output(TriagePlan)
    strategy_content = load_prompt("strategy.md")

    # If this is a retry, inject the previous critique to guide the new plan
    critique_context = ""
    if state.get("critique"):
        critique_context = f"\n\nIMPORTANT - PREVIOUS ATTEMPT FAILED:\nCritique: {state['critique']}\nADJUSTMENT REQUIRED: Be more specific than the last attempt."

    # Inject state variables into the template
    filled_prompt = f"""
    {strategy_content}
    
    --- CURRENT CONTEXT ---
    User Query: {state['query']}
    {critique_context}
    
    TASK: Generate ONE single, highly specific search query. 
    Focus on the unique technical characteristic or specific HS heading.
    """
    
    plan = llm.invoke(filled_prompt)
    
    # We wrap the single query in a list because the State/Router expects a list
    print(f"--- 🧠 SUPERVISOR PLAN ---\nQuery Breakdown: {plan}")
    logger.info(f"Supervisor Plan generated: {plan}")

    return {"sub_tasks": [plan.search_query], "status": "PLANNING"}

import re
from collections import Counter

def aggregator_node(state: AuditorState):
    """
    NODE: AGGREGATOR
    Synthesizes the final report using 'final_synthesis.md' (or default text).
    """
    llm = llm_factory()
    
    # Try to load file, use robust default if missing
    try:
        synthesis_template = load_prompt("final_synthesis.md")
    except:
        synthesis_template = "Summarize the findings and provide the HS Code."

    # Use only the latest worker result (most refined attempt)
    worker_results = state.get("worker_results", [])
    latest_result = worker_results[-1] if worker_results else ""
    
    # Also gather all codes across all attempts to find the most common one
    all_evidence = "\n".join(worker_results)
    all_8digit = re.findall(r'\b(\d{4}\.\d{2}\.\d{2})\b', all_evidence)
    all_6digit = re.findall(r'\b(\d{4}\.\d{2})\b', all_evidence)
    
    # Pick the most frequently occurring 8-digit code (consensus across retries)
    if all_8digit:
        code_counts = Counter(all_8digit)
        extracted_code = code_counts.most_common(1)[0][0]
    elif all_6digit:
        code_counts = Counter(all_6digit)
        extracted_code = code_counts.most_common(1)[0][0]
    else:
        extracted_code = "N/A"
    
    logger.info(f"Aggregator: extracted HS code '{extracted_code}' (most common across {len(worker_results)} attempts)")
    
    filled_prompt = f"""
    {synthesis_template}
    
    --- INPUT DATA ---
    User Query: {state['query']}
    MANDATORY HS CODE (do NOT change this): {extracted_code}
    Verified Evidence (latest attempt):
    {latest_result}
    """
    
    response = llm.invoke(filled_prompt)
    
    # Extract confidence from the response if mentioned
    content = response.content
    confidence = "N/A"
    for level in ["HIGH", "MEDIUM", "LOW"]:
        if level in content.upper():
            confidence = level
            break
    
    return {"final_hscode": content, "final_confidence": confidence}

# --- 4. DYNAMIC ROUTER ---

def route_to_workers(state: AuditorState):
    """
    Fan-out to workers. 
    Since sub_tasks is now a list of 1, this spawns exactly 1 worker.
    """
    return [Send("worker_node", {"query": task}) for task in state["sub_tasks"]]