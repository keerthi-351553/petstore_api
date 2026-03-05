# src/nodes/planner_nodes.py
import json
import yaml
import re
from src.states.states import Plan
from src.llms.groq import get_llm

llm = get_llm()

def load_full_spec(spec_str: str) -> dict:
    try:
        return json.loads(spec_str)
    except Exception:
        return yaml.safe_load(spec_str)


def _extract_path_param_types(full_spec: dict, path: str, method: str) -> dict:
    """Returns {param_name: type} for path parameters from the spec."""
    types = {}
    path_item = full_spec.get("paths", {}).get(path, {})
    params = path_item.get("parameters", []) + \
             path_item.get(method.lower(), {}).get("parameters", [])
    for p in params:
        if p.get("in") == "path":
            types[p["name"]] = p.get("schema", {}).get("type", "string")
    return types


def _looks_like_id(value: str, expected_type: str) -> bool:
    """Returns True if value is a valid literal for the expected param type."""
    if expected_type == "integer":
        return bool(re.match(r"^\d+$", str(value)))
    if expected_type in ("number", "float"):
        return bool(re.match(r"^\d+(\.\d+)?$", str(value)))
    # UUID
    if expected_type == "string":
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        return bool(re.match(uuid_pattern, str(value), re.IGNORECASE))
    return True


def _get_list_endpoint_and_schema(full_spec: dict, detail_path: str) -> tuple[str | None, dict | None, list]:
    """
    Given a detail path like /api/v1/Books/{id}, find:
      - The corresponding list endpoint (e.g. /api/v1/Books)
      - The response schema of that list endpoint
      - The query parameters of that list endpoint

    Does NOT hardcode any field names — derives everything from the spec.
    Returns (list_path, response_schema, query_params).
    """
    # Strip trailing path segments that contain parameters to find the base path
    segments = detail_path.strip("/").split("/")
    # Walk backwards, dropping param segments until we find a list endpoint
    for i in range(len(segments), 0, -1):
        candidate = "/" + "/".join(segments[:i])
        if "{" in candidate:
            continue  # skip paths that still have params
        if candidate not in full_spec.get("paths", {}):
            continue
        if "get" not in full_spec["paths"][candidate]:
            continue

        method_obj  = full_spec["paths"][candidate]["get"]
        query_params = [
            p for p in (
                full_spec["paths"][candidate].get("parameters", []) +
                method_obj.get("parameters", [])
            )
            if p.get("in") == "query"
        ]

        # Extract response schema (200 response)
        responses = method_obj.get("responses", {})
        schema    = None
        for code in ("200", "201", "default"):
            resp = responses.get(code, {})
            content = resp.get("content", {})
            for ct, ct_body in content.items():
                if "json" in ct:
                    schema = ct_body.get("schema", {})
                    break
            if schema:
                break

        return candidate, schema, query_params

    return None, None, []


def _schema_to_field_list(schema: dict | None, full_spec: dict) -> list[str]:
    """
    Recursively resolve a schema (handling $ref, allOf, array items)
    and return the list of field names in the response object.
    """
    if not schema:
        return []

    # Resolve $ref
    if "$ref" in schema:
        ref_path = schema["$ref"].lstrip("#/").split("/")
        node = full_spec
        for part in ref_path:
            node = node.get(part, {})
        return _schema_to_field_list(node, full_spec)

    # Array: inspect items
    if schema.get("type") == "array":
        return _schema_to_field_list(schema.get("items", {}), full_spec)

    # allOf / oneOf / anyOf
    for combiner in ("allOf", "oneOf", "anyOf"):
        if combiner in schema:
            fields = []
            for sub in schema[combiner]:
                fields += _schema_to_field_list(sub, full_spec)
            return fields

    # Object: return property names
    return list(schema.get("properties", {}).keys())


def _ask_llm_for_search_strategy(
    user_value: str,
    list_path: str,
    query_params: list,
    response_fields: list[str],
    user_query: str,
) -> dict:
    """
    Ask the LLM to decide — based on the spec's actual query params and
    response fields — how to search for the resource.

    Returns:
      {
        "strategy": "query_param" | "client_filter",
        "query_param": "<param_name>" or null,   # which query param to use
        "match_field": "<field_name>",            # which response field to match on
      }
    """
    qp_descriptions = [
        f"  - {p['name']} ({p.get('schema', {}).get('type','?')}): {p.get('description','')}"
        for p in query_params
    ] or ["  (none)"]

    prompt = f"""
You are helping resolve a user query against a REST API.

The user is searching for a resource using the value: "{user_value}"
Their full query: "{user_query}"

The list endpoint is: GET {list_path}

Available query parameters on this endpoint:
{chr(10).join(qp_descriptions)}

Fields present in each response record:
{json.dumps(response_fields)}

Decide the best strategy to find the resource:
1. If a query parameter clearly matches what the user is searching by
   (e.g. a "name", "title", "search", or any descriptive param), use it.
2. Otherwise, fetch the full list and filter client-side using the best
   matching response field.

Respond with ONLY a JSON object (no explanation):
{{
  "strategy": "query_param" or "client_filter",
  "query_param": "<param_name>" or null,
  "match_field": "<field_name from response>"
}}
"""

    response = llm.invoke(prompt)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        return json.loads(raw)
    except Exception:
        # Safe fallback — fetch all and let tool_node's LLM figure out matching
        return {
            "strategy":    "client_filter",
            "query_param": None,
            "match_field": response_fields[0] if response_fields else None,
        }


def _detect_name_lookup(state: dict, plan: dict, full_spec: dict) -> dict | None:
    """
    Detects when the user supplied a non-ID value for a path parameter
    (e.g. a name/title instead of an integer ID).

    When detected:
      - Reads the spec to find the list endpoint and its schema
      - Asks the LLM (using spec knowledge only) how to search
      - Rewrites the plan accordingly

    No field names are hardcoded anywhere in this function.
    """
    path       = plan.get("path", "")
    method     = plan.get("method", "GET")
    payload    = plan.get("payload", {})

    path_params = re.findall(r"\{(\w+)\}", path)
    if len(path_params) != 1:
        return None

    param_name = path_params[0]
    user_value = payload.get(param_name, "")
    if not user_value:
        return None

    param_types   = _extract_path_param_types(full_spec, path, method)
    expected_type = param_types.get(param_name, "integer")

    if _looks_like_id(str(user_value), expected_type):
        return None  # Value is already valid — no fix needed

    # ── Value is not a valid ID → need to search by attribute ──────────────
    print(f"\n  [Planner] ⚠️  '{user_value}' is not a valid {expected_type} for {{{param_name}}}.")

    list_path, response_schema, query_params = _get_list_endpoint_and_schema(full_spec, path)

    if not list_path:
        print(f"  [Planner]    No list endpoint found. Passing through as-is.")
        return None

    # Resolve what fields exist in the response records — from the spec
    response_fields = _schema_to_field_list(response_schema, full_spec)
    print(f"  [Planner]    List endpoint: {list_path}")
    print(f"  [Planner]    Response fields from spec: {response_fields}")

    # Ask the LLM to pick strategy using only spec-derived info
    strategy_info = _ask_llm_for_search_strategy(
        user_value      = str(user_value),
        list_path       = list_path,
        query_params    = query_params,
        response_fields = response_fields,
        user_query      = state.get("user_query", ""),
    )
    print(f"  [Planner]    LLM strategy: {strategy_info}")

    modified_plan = dict(plan)
    modified_plan["name_lookup"]     = True
    modified_plan["lookup_value"]    = str(user_value)
    modified_plan["lookup_field"]    = param_name
    modified_plan["match_field"]     = strategy_info.get("match_field")  # from spec, not hardcoded
    modified_plan["original_path"]   = path
    modified_plan["original_method"] = method

    if strategy_info["strategy"] == "query_param" and strategy_info.get("query_param"):
        modified_plan["method"]  = "GET"
        modified_plan["path"]    = list_path
        modified_plan["payload"] = {strategy_info["query_param"]: str(user_value)}
    else:
        modified_plan["method"]        = "GET"
        modified_plan["path"]          = list_path
        modified_plan["payload"]       = {}
        modified_plan["client_filter"] = True

    return modified_plan


def planner_node(state, endpoints):
    full_spec      = load_full_spec(state["openapi_spec"])
    structured_llm = llm.with_structured_output(Plan)

    # Build endpoint descriptions with param types from spec
    endpoint_details = []
    for path, methods in full_spec.get("paths", {}).items():
        for method, details in methods.items():
            if method.lower() in ("parameters", "summary", "description"):
                continue
            summary = details.get("summary", details.get("description", ""))
            params  = details.get("parameters", []) + methods.get("parameters", [])
            param_hints = [
                f"{p['name']}({p.get('in','?')}:{p.get('schema',{}).get('type','?')})"
                for p in params
            ]
            param_str = ", ".join(param_hints) if param_hints else "none"
            endpoint_details.append(f"{method.upper()} {path}  |  params: {param_str}  |  {summary}")

    endpoint_text = "\n".join(endpoint_details)

    prompt = f"""
You are an API planner. Analyse the user query and return a JSON plan.

Return JSON with:
- method  : HTTP method (GET, POST, PUT, DELETE)
- path    : must EXACTLY match one of the available paths (with {{param}} placeholders)
- payload : JSON object using placeholder names as keys.
            IMPORTANT: if a path param is typed 'integer' or 'uuid' but the user
            gave a name or string value, still put it in payload as-is.
            The system will automatically detect and resolve it via the list endpoint.

Available endpoints (path | params | summary):
{endpoint_text}

User query: "{state['user_query']}"
"""

    plan_obj = structured_llm.invoke(prompt)
    plan     = plan_obj.model_dump()

    if "method" not in plan and "name" in plan:
        plan["method"] = plan.pop("name")
    if "payload" not in plan:
        plan["payload"] = {}

    # ── Name-vs-ID fix (spec-driven, no hardcoded field names) ──────────────
    fixed_plan = _detect_name_lookup(state, plan, full_spec)
    if fixed_plan:
        plan = fixed_plan
    else:
        # ── Dynamic DELETE handling (existing logic, preserved) ──────────────
        path_methods = full_spec["paths"].get(plan["path"], {})
        if plan["method"].upper() == "DELETE" and "delete" not in path_methods:
            plan["dynamic_delete"] = True
            plan["method"]         = "GET"
            plan["filter_payload"] = plan.get("payload", {})
            plan["payload"]        = {}

    state["plan"] = plan
    return state