from typing import Dict, Any
from pydantic import BaseModel

class Plan(BaseModel):
    method: str
    path: str
    payload: Dict[str, Any]
