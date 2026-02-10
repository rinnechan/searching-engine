import os
import time
import logging
from langgraph.graph import StateGraph, START, END

from src.agents.state import AuditorState
from src.agents.supervisor import supervisor_node, aggregator_node, route_to_workers, supervisor_review_node, supervisor_review_router, supervisor_post_aggregator_node, supervisor_post_aggregator_router
from src.agents.auditor import auditor_node 
from src.agents.worker import worker_node

logger = logging.getLogger(__name__)
RUN_MODE = os.getenv("RUN_MODE", "cloud")

def pacer_node(state: AuditorState):
    # Encounter too many rate-limit so have to put it here. This is a safety node to prevent errors during recursive loops.
    if RUN_MODE != "local":
        logger.info("Pacing: Waiting 10 seconds to respect API rate limits...")
        time.sleep(10)
    else:
        logger.info("Local mode: skipping cooldown.")
    
    current_count = state.get("step_count", 0)
    return {**state, "step_count": current_count + 1}

def router(state: AuditorState):
    # Set up the depth of the recursive loop and the exit condition based on the Auditor's feedback
    status = state.get("status", "APPROVED")
    step_count = state.get("step_count", 0)

    if status == "REVISE" and step_count < 3:
        logger.info(f"RECURSIVE SEARCH: Auditor rejected findings. Attempt: {step_count + 1}")
        return "pacer"
    
    logger.info("FINALIZING: Audit complete.")
    return "end"

# Set up the graph workflow
workflow = StateGraph(AuditorState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("worker_node", worker_node)
workflow.add_node("supervisor_review", supervisor_review_node)
workflow.add_node("aggregator", aggregator_node)
workflow.add_node("supervisor_post_aggregator", supervisor_post_aggregator_node)
workflow.add_node("auditor", auditor_node)
workflow.add_node("pacer", pacer_node)
workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges("supervisor", route_to_workers)
workflow.add_edge("worker_node", "supervisor_review")

workflow.add_conditional_edges(
    "supervisor_review",
    supervisor_review_router,
    {
        "aggregator": "aggregator",
        "pacer": "pacer"
    }
)

workflow.add_edge("aggregator", "supervisor_post_aggregator")

workflow.add_conditional_edges(
    "supervisor_post_aggregator",
    supervisor_post_aggregator_router,
    {
        "auditor": "auditor",
        "pacer": "pacer"
    }
)

workflow.add_conditional_edges(
    "auditor",
    router,
    {
        "pacer": "pacer",
        "end": END
    }
)

workflow.add_edge("pacer", "supervisor")
graph = workflow.compile()