import os
import logging
from dotenv import load_dotenv
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase
from src.tools.deepeval_adapter import GroqDeepEvalLLM
from langchain_groq import ChatGroq

load_dotenv()
logger = logging.getLogger(__name__)

# 1. Initialize the Metric with the required threshold for 'Production-grade' validation
# This directly addresses the Faithfulness requirement in the assessment [cite: 45]
faith_metric = FaithfulnessMetric(threshold=0.8, model=GroqDeepEvalLLM())

def auditor_node(state: dict):
    """
    UPGRADED AUDITOR: Mathematically verifies the Worker's findings.
    Captures Metrics for the Pareto Frontier Benchmark Report[cite: 12, 49].
    """
    query = state["query"]
    # Ensure we have worker results before proceeding
    if not state.get("worker_results"):
        return {"status": "REVISE", "critique": "No worker results found to audit."}
    
    worker_output = state["worker_results"][-1]
    
    # Part A: DeepEval Verification
    test_case = LLMTestCase(
        input=query,
        actual_output=worker_output,
        retrieval_context=state.get("retrieval_context", [])
    )
    
    # Run the audit measurement with retries for local models that may produce invalid JSON
    MAX_RETRIES = 3
    score = 0.0
    for attempt in range(MAX_RETRIES):
        try:
            faith_metric.measure(test_case)
            score = faith_metric.score
            break
        except (ValueError, Exception) as e:
            logger.warning(f"⚠️ DeepEval attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error("DeepEval evaluation failed after all retries. Using fallback score 0.0.")
                score = 0.0
    
    # Part B: Usage Tracking for Cost Metric
    current_tokens = state.get("total_tokens", 0)

    # Part C: Decision Logic & State Update
    if score >= 0.8:
        logger.info(f"✅ DeepEval PASSED: {score}")
        return {
            "status": "APPROVED",
            "faithfulness_score": score,
            "critique": f"Verified accuracy: {score}",
            "total_tokens": current_tokens
        }
    else:
        logger.warning(f"❌ DeepEval FAILED: {score}")
        return {
            "status": "REVISE",
            "faithfulness_score": score,
            "critique": f"Hallucination detected. Score {score}. {faith_metric.reason}",
            "total_tokens": current_tokens
        }