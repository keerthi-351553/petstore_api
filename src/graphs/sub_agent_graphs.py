# src/graphs/sub_agent_graphs.py
"""
It re-uses your EXISTING skills (PlannerSkill, APICallSkill, ResponseSkill)
and your EXISTING router node exactly as-is.

The only difference from your current build_graph():
  - It receives a pre-filtered list of endpoints (only what this sub-task needs)
  - No hardcoded domain — works with any OpenAPI spec
"""

from langgraph.graph import StateGraph, END

from src.states.states import AgentState
from src.skills.registry import SkillRegistry
from src.skills.planner_skill import PlannerSkill
from src.skills.tool_skill import APICallSkill
from src.skills.response_skill import ResponseSkill
from src.nodes.skill_router_node import skill_router_node
from src.skills.metrics import SkillMetrics


def build_sub_agent_graph(endpoints: list[str], openapi_spec: str, base_url: str):
    """
    Build a single-agent LangGraph scoped to the given endpoint list.

    Args:
        endpoints    : list of "METHOD /path" strings this sub-agent may use
        openapi_spec : full spec string (needed by planner + tool nodes)
        base_url     : API base URL

    Returns:
        Compiled LangGraph ready to invoke with an AgentState.
    """
    metrics  = SkillMetrics()
    registry = SkillRegistry()

    # Reuse your existing skills — just pass the scoped endpoint list
    registry.register(PlannerSkill(endpoints, metrics))
    registry.register(APICallSkill(base_url=base_url, metrics=metrics))
    registry.register(ResponseSkill(metrics))

    workflow = StateGraph(AgentState)
    workflow.add_node("router", skill_router_node)

    for skill_name in registry.list():
        workflow.add_node(
            skill_name,
            lambda state, s=skill_name: registry.get(s).execute(state)
        )

    workflow.set_entry_point("router")

    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("next_skill"),
        {
            **{name: name for name in registry.list()},
            None: END,
        }
    )

    for name in registry.list():
        workflow.add_edge(name, "router")

    return workflow.compile()