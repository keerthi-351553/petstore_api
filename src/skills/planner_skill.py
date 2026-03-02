from src.skills.base import Skill
from src.nodes.planner_nodes import planner_node

class PlannerSkill(Skill):
    def __init__(self, endpoints, metrics):
        super().__init__("planner", "Creates API plan", metrics)
        self.endpoints = endpoints

    def _run(self, state):
        return planner_node(state, self.endpoints)