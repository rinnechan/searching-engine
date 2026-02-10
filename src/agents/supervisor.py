import os
import re
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

class TriagePlan(BaseModel):
    # I put this as triage plan because I used to implement parralel workers, but then changed to single worker due to hardware limitations. 
    search_query: str = Field(description="One targeted, specific search query focusing on a unique technical characteristic or specific HS heading. Avoid broad queries.")

class AuditReview(BaseModel):
    status: Literal["APPROVED", "REVISE"] = Field(description="Decision to finish or retry")
    critique: str = Field(description="Reasoning for the decision")


def load_prompt(filename: str) -> str:
    path = os.path.join("prompts", filename)
    if not os.path.exists(path):
        return f"Error: {filename} not found."
    with open(path, "r") as f:
        return f.read()

# Graph nodes
def supervisor_node(state: AuditorState):
    llm = llm_factory().with_structured_output(TriagePlan)
    strategy_content = load_prompt("strategy.md")

    # Use critique from previous attempt if any
    critique_context = ""
    if state.get("critique"):
        critique_context = f"\n\nIMPORTANT - PREVIOUS ATTEMPT FAILED:\nCritique: {state['critique']}\nADJUSTMENT REQUIRED: Be more specific than the last attempt."

    filled_prompt = f"""
    {strategy_content}
    
    --- CURRENT CONTEXT ---
    User Query: {state['query']}
    {critique_context}
    
    TASK: Generate ONE single, highly specific search query. 
    Focus on the unique technical characteristic or specific HS heading.
    """
    
    plan = llm.invoke(filled_prompt)
    
    print(f"--- SUPERVISOR PLAN ---\nQuery Breakdown: {plan}")
    logger.info(f"Supervisor Plan generated: {plan}")

    return {"sub_tasks": [plan.search_query], "status": "PLANNING"}


def supervisor_review_node(state: AuditorState):
    # Inspect worker output for quality and relevance

    worker_results = state.get("worker_results", [])
    if not worker_results:
        logger.warning("Supervisor Review: No worker results to inspect.")
        return {"status": "REVISE", "critique": "No worker results found."}

    latest_result = worker_results[-1]
    query = state.get("query", "")

    # Check raw evidence quality
    retrieval_ctx = state.get("retrieval_context", [])
    raw_evidence = retrieval_ctx[-2] if len(retrieval_ctx) >= 2 else ""

    if not raw_evidence or raw_evidence.strip() == "":
        logger.warning("Supervisor Review: Empty evidence retrieved.")
        return {
            "status": "REVISE",
            "critique": f"No evidence was retrieved from the tariff schedule for '{query}'. Try searching with just the core product noun (e.g., 'headphone' instead of 'wireless headphone')."
        }

    # Check if evidence contains any HS codes at all
    evidence_codes = re.findall(r'\b\d{4}\.\d{2}(?:\.\d{2})?\b', raw_evidence)
    if not evidence_codes:
        logger.warning("Supervisor Review: Evidence contains no HS codes.")
        return {
            "status": "REVISE",
            "critique": f"Retrieved evidence contains no HS codes — likely irrelevant chunks. Try a more specific tariff-related query like 'HS heading for {query}'."
        }

    # Check code depth in worker's analysis
    eight_digit = re.findall(r'\b(\d{4}\.\d{2}\.\d{2})\b', latest_result)
    six_digit = re.findall(r'\b(\d{4}\.\d{2})\b', latest_result)

    if eight_digit:
        # Check if hallucinated code exists in evidence
        codes_in_evidence = set(re.findall(r'\b(\d{4}\.\d{2}\.\d{2})\b', raw_evidence))
        matched = [c for c in eight_digit if c in codes_in_evidence]
        if matched:
            logger.info(f"Supervisor Review: PASSED — 8-digit code(s) {matched} found and verified in evidence.")
            return {"status": "APPROVED"}
        else:
            logger.warning(f"Supervisor Review: Worker cited {eight_digit} but evidence only contains {codes_in_evidence}.")
            return {
                "status": "REVISE",
                "critique": f"Worker proposed code(s) {eight_digit} but these don't appear in the raw evidence. The evidence contains: {list(codes_in_evidence)[:5]}. Re-search using one of these codes or the heading they fall under."
            }
    elif six_digit:
        heading = six_digit[0]
        logger.warning(f"Supervisor Review: Only 6-digit heading {heading} found. Sending worker back.")
        return {
            "status": "REVISE",
            "critique": f"Only found 6-digit heading {heading}. Search specifically for '8-digit national tariff lines under heading {heading}' to find the exact sub-item code."
        }
    else:
        logger.warning("Supervisor Review: No HS codes found in worker output.")
        return {
            "status": "REVISE",
            "critique": f"No HS codes found in worker results. Try a broader search with the core product noun from '{query}'."
        }


def supervisor_review_router(state: AuditorState):
    # Let supervisor decide if it can trust the worker's output or not

    status = state.get("status", "APPROVED")
    step_count = state.get("step_count", 0)

    if status == "REVISE" and step_count < 3:
        logger.info(f"Supervisor sending worker back for deeper search. Attempt: {step_count + 1}")
        return "pacer"
    
    return "aggregator"


def aggregator_node(state: AuditorState):
    # Synthesize worker findings into final code decision

    llm = llm_factory()

    # Load the synthesis prompt template
    try:
        synthesis_template = load_prompt("final_synthesis.md")
    except:
        synthesis_template = "Evaluate and classify based on the evidence."

    worker_results = state.get("worker_results", [])
    latest_result = worker_results[-1] if worker_results else ""

    retrieval_ctx = state.get("retrieval_context", [])
    raw_evidence = retrieval_ctx[-2] if len(retrieval_ctx) >= 2 else ""

    if not latest_result:
        logger.warning("Aggregator: No worker results to evaluate.")
        return {"final_hscode": "INSUFFICIENT DATA - MANUAL REVIEW REQUIRED", "final_confidence": "LOW"}

    worker_8digit = re.findall(r'\b(\d{4}\.\d{2}\.\d{2})\b', latest_result)
    worker_code = worker_8digit[0] if worker_8digit else "N/A"

    filled_prompt = f"""
{synthesis_template}

--- INPUT DATA ---
User Query: {state['query']}

Worker's Proposed 8-digit Code: {worker_code}

Worker's Analysis:
{latest_result}

Raw Retrieved Evidence (from STCCED tariff schedule):
{raw_evidence}

REMINDER: Your FINAL_CODE line MUST contain a full 8-digit code (XXXX.XX.XX). Use the worker's proposed code '{worker_code}' if it appears in the raw evidence. If not, find the correct 8-digit code from the evidence.
"""

    response = llm.invoke(filled_prompt)
    content = response.content

    confidence = "LOW"
    for level in ["HIGH", "MEDIUM", "LOW"]:
        if level in content.upper():
            confidence = level
            break

    logger.info(f"Aggregator: Judged evidence with confidence={confidence}")

    verification_claims = ""
    if "---VERIFICATION_CLAIMS---" in content and "---END_VERIFICATION_CLAIMS---" in content:
        start = content.index("---VERIFICATION_CLAIMS---") + len("---VERIFICATION_CLAIMS---")
        end = content.index("---END_VERIFICATION_CLAIMS---")
        verification_claims = content[start:end].strip()
    else:
        verification_claims = content
        logger.warning("Aggregator: No VERIFICATION_CLAIMS section found, using full output.")

    return {"final_hscode": content, "final_confidence": confidence, "verification_claims": verification_claims}


def supervisor_post_aggregator_node(state: AuditorState):
    # Extract final code from aggregator output and verify against evidence
    final_output = state.get("final_hscode", "")
    if not final_output:
        logger.warning("Supervisor Post-Aggregator: No aggregator output.")
        return {"status": "REVISE", "critique": "Aggregator produced no output."}

    final_code_match = re.search(r'FINAL_CODE:\s*(\d{4}\.\d{2}\.\d{2})', final_output)
    if not final_code_match:
        logger.warning("Supervisor Post-Aggregator: No FINAL_CODE found in aggregator output.")
        return {"status": "REVISE", "critique": "Aggregator did not produce a valid 8-digit FINAL_CODE."}

    final_code = final_code_match.group(1)

    retrieval_ctx = state.get("retrieval_context", [])
    raw_evidence = retrieval_ctx[-2] if len(retrieval_ctx) >= 2 else ""
    codes_in_evidence = set(re.findall(r'\b(\d{4}\.\d{2}\.\d{2})\b', raw_evidence))

    if final_code in codes_in_evidence:
        logger.info(f"Supervisor Post-Aggregator: PASSED — {final_code} verified in evidence.")
        return {"status": "APPROVED"}
    else:
        logger.warning(f"Supervisor Post-Aggregator: FAILED — {final_code} NOT in evidence. Evidence has: {codes_in_evidence}")
        return {
            "status": "REVISE",
            "critique": f"Aggregator hallucinated code {final_code} which does not exist in the retrieved evidence. Evidence contains: {list(codes_in_evidence)[:5]}. Re-search and use only codes from the evidence."
        }


def supervisor_post_aggregator_router(state: AuditorState):
    # Let supervisor decide if it can trust the aggregator's output or not
    status = state.get("status", "APPROVED")
    step_count = state.get("step_count", 0)

    if status == "REVISE" and step_count < 3:
        logger.info(f"Supervisor rejecting aggregator output. Attempt: {step_count + 1}")
        return "pacer"
    
    return "auditor"

def route_to_workers(state: AuditorState):
    return [Send("worker_node", {"query": task}) for task in state["sub_tasks"]]