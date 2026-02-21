# graphs/dynamic_graph.py
from langgraph.graph import StateGraph, END
from prance import ResolvingParser
from src.states.states import AgentState
from src.nodes.planner_nodes import planner_node
from src.nodes.tool_nodes import tool_node
from src.nodes.response_nodes import response_node

def extract_endpoints(spec_str: str):
    parser = ResolvingParser(spec_string=spec_str)
    spec = parser.specification
    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method in methods.keys():
            endpoints.append(f"{method.upper()} {path}")
    return endpoints

def build_graph(openapi_spec: str):
    endpoints = extract_endpoints(openapi_spec)
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", lambda state: planner_node(state, endpoints), )
    workflow.add_node("tool", tool_node)
    workflow.add_node("responder", response_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "tool")
    workflow.add_edge("tool", "responder")
    workflow.add_edge("responder", END)

    return workflow.compile()