import time
import logging

logger = logging.getLogger(__name__)

class Skill:
    def __init__(self, name: str, description: str, metrics=None):
        self.name = name
        self.description = description
        self.metrics = metrics

    def execute(self, state):
        start_time = time.time()

        try:
            result = self._run(state)
            duration = time.time() - start_time

            if self.metrics:
                self.metrics.record(self.name, True, duration)

            return result

        except Exception as e:
            duration = time.time() - start_time

            logger.exception(f"{self.name} failed")

            if self.metrics:
                self.metrics.record(self.name, False, duration, str(e))

            state["error"] = {
                "error": {...},
                "next_skill": None
            }

            return state

    def _run(self, state):
        raise NotImplementedError