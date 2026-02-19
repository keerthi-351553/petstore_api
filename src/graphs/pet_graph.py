from langgraph.graph import StateGraph, END
from src.states.petstate import PetState
from src.nodes.pet_nodes import planner_node, tool_node, response_node
import json
from prance import ResolvingParser


def extract_endpoints(spec_str: str):
    """
    Parse the OpenAPI spec string and return available endpoints + methods.
    """
    parser = ResolvingParser(spec_string=spec_str)
    spec = parser.specification

    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method in methods.keys():
            endpoints.append(f"{method.upper()} {path}")
    return endpoints


def build_graph(openapi_spec: str):
    """
    Build the LangGraph workflow using the uploaded OpenAPI spec.
    """
    # Extract endpoints dynamically
    endpoints = extract_endpoints(openapi_spec)

    workflow = StateGraph(PetState)

    # Add nodes
    workflow.add_node("planner", lambda state: planner_node(state, endpoints))
    workflow.add_node("tool", tool_node)
    workflow.add_node("responder", response_node)

    # Define flow
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "tool")
    workflow.add_edge("tool", "responder")
    workflow.add_edge("responder", END)

    return workflow.compile()
