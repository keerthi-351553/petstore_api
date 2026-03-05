# src/nodes/task_dispatcher_node.py
"""
For each sub-task it:
  1. Respects depends_on — waits until the dependency's result is available
  2. Enriches the task description with the dependency's output (so the
     downstream sub-agent has concrete IDs / values to work with)
  3. Builds a fresh scoped single-agent graph (via build_sub_agent_graph)
     using only the endpoints assigned to this sub-task
  4. Invokes the graph and captures the result

Fully generic — no hardcoded domain knowledge.
"""

from src.states.states import SubTaskResult
from src.graphs.sub_agent_graphs import build_sub_agent_graph


def _find_result(results: list, agent_id: str) -> str | None:
    for r in results:
        if r["agent_id"] == agent_id:
            return r["final_answer"]
    return None


def _sort_by_dependency(task_queue: list) -> list:
    """Topological sort — tasks with no dependency come first."""
    ordered   = []
    remaining = list(task_queue)

    for _ in range(len(remaining) + 1):
        if not remaining:
            break
        for task in remaining[:]:
            dep = task.get("depends_on")
            if dep is None or any(t["agent_id"] == dep for t in ordered):
                ordered.append(task)
                remaining.remove(task)

    # Append anything left (circular / unresolvable) at the end
    ordered.extend(remaining)
    return ordered


def task_dispatcher_node(state: dict) -> dict:
    task_queue   : list = state.get("task_queue", [])
    completed    : list = list(state.get("sub_task_results", []))
    openapi_spec : str  = state["openapi_spec"]
    base_url     : str  = state["base_url"]

    ordered_tasks = _sort_by_dependency(task_queue)

    for task in ordered_tasks:
        agent_id    = task["agent_id"]
        description = task["task_description"]
        endpoints   = task.get("endpoints", [])

        # Inject dependency output into the prompt so sub-agent has
        # the concrete data (IDs, names, etc.) it needs
        dep = task.get("depends_on")
        if dep:
            dep_output = _find_result(completed, dep)
            if dep_output:
                description = (
                    f"{description}\n\n"
                    f"--- Output from {dep} (use this context) ---\n"
                    f"{dep_output}"
                )

        print(f"\n  [Dispatcher] ▶ {agent_id} | endpoints: {endpoints}")
        print(f"               task: {description[:90]}...")

        # Build a scoped graph — reuses your existing skills
        graph = build_sub_agent_graph(
            endpoints    = endpoints,
            openapi_spec = openapi_spec,
            base_url     = base_url,
        )

        sub_state = graph.invoke({
            "user_query":   description,
            "openapi_spec": openapi_spec,
        })

        result: SubTaskResult = {
            "agent_id":         agent_id,
            "task_description": task["task_description"],
            "final_answer":     sub_state.get("final_answer", "No answer produced."),
            "api_response":     sub_state.get("api_response"),
        }

        completed.append(result)
        print(f"  [Dispatcher] ◀ {agent_id} done: {result['final_answer'][:80]}...")

    state["sub_task_results"] = completed
    state["next_skill"]       = "multi_responder"
    return state