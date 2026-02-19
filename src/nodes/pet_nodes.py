import json
import yaml
from jsonschema import Draft7Validator

from src.llms.groq import get_llm
from src.states.petstate import PetState
from src.tools.petstore_tools import call_tool_api
from src.states.response_state import Plan

from jsonschema import Draft7Validator, RefResolver

llm = get_llm()


# ---------------------------------------------------------
# Utils
# ---------------------------------------------------------

def load_full_spec(spec_str: str):
    try:
        return json.loads(spec_str)
    except json.JSONDecodeError:
        return yaml.safe_load(spec_str)

def get_request_schema(full_spec, path, method):
    """Extract request body schema dynamically."""
    method_obj = full_spec["paths"][path][method.lower()]

    if "requestBody" in method_obj:
        content = method_obj["requestBody"]["content"]
        if "application/json" in content:
            return content["application/json"]["schema"]

    return None

def validate_payload(payload, schema, full_spec):
    resolver = RefResolver.from_schema(full_spec)

    validator = Draft7Validator(
        schema,
        resolver=resolver
    )

    errors = list(validator.iter_errors(payload))
    return errors

def fix_payload_with_llm(payload, schema, errors):
    """Ask LLM to fix invalid payload generically."""
    error_messages = "\n".join([e.message for e in errors])
    prompt = f"""
The following JSON payload is invalid:

{json.dumps(payload, indent=2)}

It must satisfy this JSON Schema:

{json.dumps(schema, indent=2)}

Validation errors:
{error_messages}

Return ONLY a corrected JSON object.
Do not include explanations.
"""
    response = llm.invoke(prompt)
    try:
        fixed = json.loads(response.content.strip())
        if isinstance(fixed, dict):
            return fixed
    except Exception as e:
        pass
    return payload


def replace_path_params(path, payload):
    """Replace {param} in path using payload values."""
    for key, value in payload.items():
        path = path.replace(f"{{{key}}}", str(value))
    return path


# ---------------------------------------------------------
# Planner Node
# ---------------------------------------------------------

def planner_node(state: PetState, endpoints):
    structured_llm = llm.with_structured_output(Plan)

    prompt = f"""
You are an API planner.

Return a JSON object with:
- method (GET, POST, PUT, DELETE)
- path (exactly matching available endpoints)
- payload (JSON object)

Available endpoints:
{chr(10).join(endpoints)}

User query:
"{state['user_query']}"
"""

    plan_obj = structured_llm.invoke(prompt)
    state["plan"] = plan_obj.model_dump()

    return state


# ---------------------------------------------------------
# Tool Node (GENERIC + SELF-HEALING)
# ---------------------------------------------------------

def tool_node(state: PetState):
    if "plan" not in state:
        raise ValueError("Planner did not produce a plan")

    plan = state["plan"]

    full_spec = load_full_spec(state["openapi_spec"])
    schema = get_request_schema(full_spec, plan["path"], plan["method"])

    # Validate + repair loop
    if schema:
        for _ in range(2):  # max 2 retries
            errors = validate_payload(plan["payload"], schema, full_spec)
            if not errors:
                break

            plan["payload"] = fix_payload_with_llm(
                plan["payload"],
                schema,
                errors
            )
    # Replace path params dynamically
    final_path = replace_path_params(plan["path"], plan.get("payload", {}))

    # Call API
    result = call_tool_api(
        method=plan["method"],
        path=final_path,
        payload=plan.get("payload"),
        base_url=state["base_url"]
    )

    state["api_response"] = result
    return state


# ---------------------------------------------------------
# Response Node
# ---------------------------------------------------------

def response_node(state: PetState):
    prompt = f"""
User asked:
{state['user_query']}

API result:
{state['api_response']}

Provide a clean natural language answer.
If API failed, explain clearly.
"""
    response = llm.invoke(prompt)
    state["final_answer"] = response.content

    return state
