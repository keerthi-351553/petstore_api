import json
from src.llms.groq import get_llm
from src.states.petstate import PetState
from src.tools.petstore_tools import call_petstore_api
from src.states.response_state import Plan

llm = get_llm()

def planner_node(state: PetState):
    structured_llm = llm.with_structured_output(Plan)
    prompt = f"""
You are an API planner for Swagger Petstore.

Important:
- NEVER modify numeric IDs from the user.
- Use exact values from the user query.
- Treat IDs as strings.
- Do NOT round or approximate large numbers.

Available endpoints:
GET /pet/findByStatus?status=available
GET /pet/{{petId}}
POST /pet
PUT /pet
DELETE /pet/{{petId}}

User query:
"{state['user_query']}"
"""
    plan_obj = structured_llm.invoke(prompt)

    # Convert Pydantic object → dict
    state["plan"] = plan_obj.model_dump()
    return state

def tool_node(state):
    plan = state["plan"]
    path = plan["path"]

    if "{" in path and "}" in path:
        for key, value in plan.get("payload", {}).items():
            path = path.replace(f"{{{key}}}", str(value))

    result = call_petstore_api(
        method=plan["method"],
        path=path,
        payload=plan.get("payload")
    )

    state["api_response"] = result
    return state


def response_node(state):

    prompt = f"""
User asked:
{state['user_query']}

API result:
{state['api_response']}

Provide a clean natural language answer.
"""

    response = llm.invoke(prompt)

    state["final_answer"] = response.content
    return state
