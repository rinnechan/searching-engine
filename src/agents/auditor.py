import os
import re
import logging
from dotenv import load_dotenv
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase
from src.tools.deepeval_adapter import GroqDeepEvalLLM
from langchain_groq import ChatGroq

load_dotenv()
logger = logging.getLogger(__name__)
faith_metric = FaithfulnessMetric(threshold=0.75, model=GroqDeepEvalLLM())

def auditor_node(state: dict):
    # Retrieve necessary information and judge the evidence
    query = state["query"]
    final_output = state.get("final_hscode", "")
    if not final_output:
        return {"status": "REVISE", "critique": "No aggregator output found to audit."}

    claims_to_verify = state.get("verification_claims", "") or final_output
    logger.info(f"Auditor: Claims to verify:\n{claims_to_verify}")
    
    retrieval_ctx = state.get("retrieval_context", [])
    raw_evidence_only = []
    for i in range(0, len(retrieval_ctx), 2):
        if i < len(retrieval_ctx):
            raw_evidence_only.append(retrieval_ctx[i])
    recent_evidence = raw_evidence_only[-1:] if raw_evidence_only else []

    test_case = LLMTestCase(
        input=query,
        actual_output=claims_to_verify,
        retrieval_context=recent_evidence
    )
    
    MAX_RETRIES = 3
    score = 0.0
    for attempt in range(MAX_RETRIES):
        try:
            faith_metric.measure(test_case)
            score = faith_metric.score
            # Log detailed claim
            if hasattr(faith_metric, 'claims') and faith_metric.claims:
                logger.info(f"DeepEval extracted {len(faith_metric.claims)} claims: {faith_metric.claims}")
            if hasattr(faith_metric, 'verdicts') and faith_metric.verdicts:
                for i, verdict in enumerate(faith_metric.verdicts):
                    v = verdict.verdict if hasattr(verdict, 'verdict') else str(verdict)
                    r = verdict.reason if hasattr(verdict, 'reason') else ''
                    logger.info(f"  Claim {i+1}: {v} — {r}")
            if hasattr(faith_metric, 'reason') and faith_metric.reason:
                logger.info(f"DeepEval reason: {faith_metric.reason}")
            break
        except (ValueError, Exception) as e:
            logger.warning(f"DeepEval attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error("DeepEval evaluation failed after all retries. Using fallback score 0.0.")
                score = 0.0
    
    current_tokens = state.get("total_tokens", 0)

    if score >= 0.75:
        logger.info(f"DeepEval PASSED: {score}")
        return {
            "status": "APPROVED",
            "faithfulness_score": score,
            "critique": f"Verified accuracy: {score}",
            "total_tokens": current_tokens
        }
    else:
        logger.warning(f"DeepEval FAILED: {score}")
        return {
            "status": "REVISE",
            "faithfulness_score": score,
            "critique": f"Faithfulness check failed. Score {score}. {faith_metric.reason}",
            "total_tokens": current_tokens
        }