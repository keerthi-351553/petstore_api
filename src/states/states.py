# states/state_models.py
from typing import TypedDict, Optional, Dict, Any
from pydantic import BaseModel

class AgentState(TypedDict):
    user_query: str
    plan: Optional[Dict[str, Any]]
    api_response: Optional[Any]
    final_answer: Optional[str]
    base_url: str = ""
    openapi_spec: str

class Plan(BaseModel):
    method: str
    path: str
    payload: Dict[str, Any]