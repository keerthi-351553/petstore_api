from src.skills.base import Skill
from src.nodes.response_nodes import response_node

class ResponseSkill(Skill):
    def __init__(self, metrics):
        super().__init__("responder", "Generates final answer", metrics)

    def _run(self, state):
        return response_node(state)