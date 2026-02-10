import operator
from typing import Annotated, List, TypedDict
from pydantic import BaseModel, Field

class AuditorState(TypedDict):
    query: str
    worker_results: Annotated[List[str], operator.add]
    sub_tasks: List[str]
    final_hscode: str
    final_confidence: str
    verification_claims: str
    step_count: Annotated[int, operator.add]
    faithfulness_score: float
    status: str
    critique: str
    total_tokens: int
    retrieval_context: Annotated[List[str], operator.add]

class WorkerInput(TypedDict):
    query: str