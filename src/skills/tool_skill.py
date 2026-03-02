import time
import logging
from src.skills.base import Skill
from src.nodes.tool_nodes import tool_node

logger = logging.getLogger(__name__)

class APICallSkill(Skill):
    def __init__(self,base_url: str, metrics):
        super().__init__("api_call", "Executes API", metrics)
        self.base_url = base_url

    def _run(self, state):
        return tool_node(state, self.base_url)