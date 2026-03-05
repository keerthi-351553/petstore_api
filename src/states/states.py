# states/states.py
from typing import TypedDict, Optional, Dict, Any, List
from pydantic import BaseModel

class AgentState(TypedDict):
    user_query: str
    plan: Optional[Dict[str, Any]]
    api_response: Optional[Any]
    final_answer: Optional[str]
    openapi_spec: str

class Plan(BaseModel):
    method: str
    path: str
    payload: Dict[str, Any]

class SubTask(TypedDict):
    """
    One atomic unit of work, derived dynamically from the loaded OpenAPI spec.

    agent_id        : unique label e.g. "task_0", "task_1"
    task_description: plain-English instruction for this sub-task
    endpoints       : the specific METHOD /path strings this sub-task is allowed to use
    depends_on      : agent_id whose result must be available before this runs (or None)
    """
    agent_id: str
    task_description: str
    endpoints: List[str]        # scoped to just what this sub-task needs
    depends_on: Optional[str]


class SubTaskResult(TypedDict):
    """Result produced by running one SubTask through a single-agent graph."""
    agent_id: str
    task_description: str
    final_answer: str
    api_response: Optional[Any]


class MultiAgentState(TypedDict):
    """
    Carried through the multi-agent LangGraph.

    Step 1 – multi_planner   → fills task_queue
    Step 2 – task_dispatcher → fills sub_task_results  (one entry per sub-task)
    Step 3 – multi_responder → fills final_answer
    """
    user_query: str
    openapi_spec: str
    base_url: str

    task_queue: Optional[List[SubTask]]
    sub_task_results: Optional[List[SubTaskResult]]
    final_answer: Optional[str]

    next_skill: Optional[str]
    error: Optional[Dict[str, Any]]
