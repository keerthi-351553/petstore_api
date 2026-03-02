import time
from collections import defaultdict

class SkillMetrics:
    def __init__(self):
        self.data = defaultdict(list)

    def record(self, skill_name, success: bool, duration: float, error: str = None):
        self.data[skill_name].append({
            "success": success,
            "duration": duration,
            "error": error
        })

    def get_score(self, skill_name):
        history = self.data.get(skill_name, [])
        if not history:
            return 0.0
        successes = sum(1 for h in history if h["success"])
        return successes / len(history)