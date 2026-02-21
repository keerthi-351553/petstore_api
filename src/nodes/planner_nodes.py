from src.states.states import Plan
from src.llms.groq import get_llm

llm = get_llm()

def load_full_spec(spec_str: str):
    import yaml, json
    try:
        return json.loads(spec_str)
    except Exception:
        return yaml.safe_load(spec_str)

def planner_node(state, endpoints):
    """
    Dynamic planner that handles DELETE by attribute.
    """
    full_spec = load_full_spec(state["openapi_spec"])
    structured_llm = llm.with_structured_output(Plan)

    prompt = f"""
You are an API planner.

Return JSON with:
- method (GET, POST, PUT, DELETE)
- path (must match available endpoints exactly)
- payload (JSON object, can be empty {{}})

Available method-path combinations:
{chr(10).join(endpoints)}

User query:
"{state['user_query']}"
"""

    plan_obj = structured_llm.invoke(prompt)
    plan = plan_obj.model_dump()

    # Ensure normalized fields
    if "method" not in plan and "name" in plan:
        plan["method"] = plan.pop("name")
    if "payload" not in plan:
        plan["payload"] = {}

    # ===== Dynamic DELETE handling =====
    path_methods = full_spec["paths"].get(plan["path"], {})
    if plan["method"].upper() == "DELETE" and "delete" not in path_methods:
        # DELETE not allowed, plan GET first
        plan["dynamic_delete"] = True  # marker for tool_node
        plan["method"] = "GET"
        # Keep original filter payload to find resource(s)
        plan["filter_payload"] = plan.get("payload", {})
        plan["payload"] = {}

    state["plan"] = plan
    return state