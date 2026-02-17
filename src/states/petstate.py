from typing import TypedDict, Optional, Dict, Any

class PetState(TypedDict):
    user_query: str
    plan: Optional[Dict[str, Any]]
    api_response: Optional[Any]
    final_answer: Optional[str]

from pydantic import BaseModel

class Plan(BaseModel):
    method: str
    path: str
    payload: dict
