from langgraph.graph import StateGraph, END

from src.states.states import MultiAgentState
from src.nodes.multi_planner_node   import multi_planner_node
from src.nodes.task_dispatcher_node import task_dispatcher_node
from src.nodes.multi_responder_node import multi_responder_node


def multi_router_node(state: dict) -> dict:
    """
    Routes between multi-agent skills.
    Mirrors your existing skill_router_node pattern.
    """
    if state.get("error"):
        state["next_skill"] = None
        return state

    # Step 1: no plan yet → plan
    if not state.get("task_queue"):
        state["next_skill"] = "multi_planner"
        return state

    # Step 2: planned but not dispatched → dispatch
    if not state.get("sub_task_results"):
        state["next_skill"] = "task_dispatcher"
        return state

    # Step 3: dispatcher finished, needs response
    if state.get("next_skill") == "multi_responder":
        return state

    # Step 4: no final answer yet → respond
    if not state.get("final_answer"):
        state["next_skill"] = "multi_responder"
        return state

    # Done
    state["next_skill"] = None
    return state


def build_multi_agent_graph():
    """
    Build and return the compiled multi-agent LangGraph.
    Call this once per request (same pattern as your build_graph()).
    """
    workflow = StateGraph(MultiAgentState)

    workflow.add_node("multi_router",    multi_router_node)
    workflow.add_node("multi_planner",   multi_planner_node)
    workflow.add_node("task_dispatcher", task_dispatcher_node)
    workflow.add_node("multi_responder", multi_responder_node)

    workflow.set_entry_point("multi_router")

    workflow.add_conditional_edges(
        "multi_router",
        lambda state: state.get("next_skill"),
        {
            "multi_planner":   "multi_planner",
            "task_dispatcher": "task_dispatcher",
            "multi_responder": "multi_responder",
            None:              END,
        }
    )

    for node in ["multi_planner", "task_dispatcher", "multi_responder"]:
        workflow.add_edge(node, "multi_router")

    return workflow.compile()