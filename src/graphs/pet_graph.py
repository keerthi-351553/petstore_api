from langgraph.graph import StateGraph, END
from src.states.petstate import PetState
from src.nodes.pet_nodes import planner_node, tool_node, response_node

def build_graph():

    workflow = StateGraph(PetState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("responder", response_node)

    workflow.set_entry_point("planner")

    workflow.add_edge("planner", "tool")
    workflow.add_edge("tool", "responder")
    workflow.add_edge("responder", END)

    return workflow.compile()
