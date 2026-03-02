# graphs/graphs.py
from langgraph.graph import StateGraph, END
from prance import ResolvingParser
from src.states.states import AgentState
from src.skills.registry import SkillRegistry
from src.skills.planner_skill import PlannerSkill
from src.skills.tool_skill import APICallSkill
from src.skills.response_skill import ResponseSkill
from src.nodes.skill_router_node import skill_router_node
from src.skills.metrics import SkillMetrics

def extract_endpoints(spec_str: str):
    parser = ResolvingParser(spec_string=spec_str)
    spec = parser.specification
    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method in methods.keys():
            endpoints.append(f"{method.upper()} {path}")
    return endpoints

def build_graph(openapi_spec: str, base_url: str):
    endpoints = extract_endpoints(openapi_spec)

    metrics = SkillMetrics()  # ✅ Create once

    registry = SkillRegistry()

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
        lambda state: state.get("next_skill"),  # safer than state["next_skill"]
        {
            **{name: name for name in registry.list()},
            None: END,  # 🔥 required for clean termination
        }
    )


    for name in registry.list():
        workflow.add_edge(name, "router")

    return workflow.compile()