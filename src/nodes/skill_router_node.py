def skill_router_node(state):

    if state.get("error"):
        state["next_skill"] = None
        return state

    # 1️⃣ If no plan → run planner
    if "plan" not in state:
        state["next_skill"] = "planner"
        return state

    # 2️⃣ If plan exists but no api_response → call API
    if "api_response" not in state:
        state["next_skill"] = "api_call"
        return state

    # 3️⃣ If api_response exists but no final_answer → respond
    if "final_answer" not in state:
        state["next_skill"] = "responder"
        return state

    # 4️⃣ All done → terminate
    state["next_skill"] = None
    return state