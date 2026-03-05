# nodes/tool_node.py
import json
import re
from urllib.parse import urljoin
from jsonschema import Draft7Validator, RefResolver

from src.llms.groq import get_llm
from src.tools.api_tools import call_tool_api
from src.utils.utils import (
    compress_schema,
    limit_validation_errors,
    ensure_prompt_within_limit,
    compress_json,
    enforce_size_limit,
)

llm = get_llm()


def load_full_spec(spec_str: str):
    import yaml
    try:
        return json.loads(spec_str)
    except Exception:
        return yaml.safe_load(spec_str)


def get_request_schema(full_spec, path, method):
    if path not in full_spec["paths"]:
        raise ValueError(f"Invalid path: {path}")
    if method.lower() not in full_spec["paths"][path]:
        raise ValueError(f"Method {method} not allowed for {path}")
    method_obj = full_spec["paths"][path][method.lower()]
    if "requestBody" in method_obj:
        content = method_obj["requestBody"]["content"]
        for content_type, body in content.items():
            if "json" in content_type:
                return body["schema"]
    return None


def validate_payload(payload, schema, full_spec):
    resolver  = RefResolver.from_schema(full_spec)
    validator = Draft7Validator(schema, resolver=resolver)
    return list(validator.iter_errors(payload))


def fix_payload_with_llm(payload, schema, errors):
    compressed     = compress_schema(schema)
    error_messages = limit_validation_errors(errors)
    prompt = f"""
Fix this JSON payload to satisfy schema.

Payload:
{json.dumps(payload, indent=2)}

Schema:
{json.dumps(compressed, indent=2)}

Errors:
{error_messages}

Return ONLY valid JSON.
"""
    ensure_prompt_within_limit(prompt)
    response = llm.invoke(prompt)
    try:
        fixed = json.loads(response.content.strip())
        if isinstance(fixed, dict):
            return fixed
    except Exception:
        pass
    return payload


def replace_path_params(path, payload):
    for key, value in payload.items():
        path = path.replace(f"{{{key}}}", str(value))
    return path


def merge_with_existing_resource(base_url, plan):
    resource_id = plan["payload"].get("id")
    if not resource_id:
        match = re.search(r"/(\d+)(/?$)", plan["path"])
        if match:
            resource_id = match.group(1)
    if not resource_id:
        raise ValueError("Cannot determine resource ID for PUT")
    resource_path = plan["path"]
    if "{id}" in resource_path:
        resource_path = resource_path.replace("{id}", str(resource_id))
    resource_url = urljoin(base_url.rstrip("/") + "/", resource_path.lstrip("/"))

    response = call_tool_api(method="GET", path=resource_url, payload=None)

    # call_tool_api wraps responses as {"status_code":..., "success":..., "data":{...}}
    # We must unwrap to get the actual resource object before merging,
    # otherwise the PUT body will contain status_code/success/data fields
    # and the API will NULL out every field it doesn't recognise.
    existing = None
    if isinstance(response, dict):
        if "data" in response and isinstance(response["data"], dict):
            existing = response["data"]          # ← unwrap the real object
        elif response.get("success") is not None:
            # response IS the wrapper but has no "data" key — use as-is minus meta fields
            existing = {k: v for k, v in response.items()
                        if k not in ("status_code", "success")}
        else:
            existing = response                  # already a plain resource dict

    if existing:
        # Only carry user-supplied fields that are actually part of the resource
        # (strip any meta keys that may have leaked into payload)
        meta_keys = {"status_code", "success", "data"}
        clean_updates = {k: v for k, v in plan["payload"].items() if k not in meta_keys}

        merged = existing.copy()
        merged.update(clean_updates)
        try:
            merged["id"] = int(resource_id)
        except (ValueError, TypeError):
            merged["id"] = resource_id
        return merged

    return plan["payload"]


def find_spec_path(full_spec, plan_path):
    for spec_path in full_spec["paths"].keys():
        parts_spec = spec_path.strip("/").split("/")
        parts_plan = plan_path.strip("/").split("/")
        if len(parts_spec) != len(parts_plan):
            continue
        matched = True
        for s, p in zip(parts_spec, parts_plan):
            if s.startswith("{") and s.endswith("}"):
                continue
            if s != p:
                matched = False
                break
        if matched:
            return spec_path
    raise ValueError(f"Invalid path: {plan_path}")


def _unwrap_list(data) -> list:
    """
    Unwrap common API response wrappers to get the actual list.
    Tries data["data"], data["items"], data["results"], etc.
    If data is already a list, returns it directly.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], list):
                return data[key]
    return []


def _find_matching_record(records: list, lookup_value: str, match_field: str | None) -> dict | None:
    """
    Find the record that best matches lookup_value.

    Strategy (fully generic — no hardcoded field names):
      1. If match_field was provided by the planner (from spec schema), try it first
      2. Ask the LLM to identify the best match from the actual records
         The LLM sees real field names and values — no assumptions needed
    """
    if not records:
        return None

    # Step 1: try the spec-derived match_field if provided
    if match_field:
        for record in records:
            if isinstance(record, dict):
                val = str(record.get(match_field, "")).lower()
                if val == lookup_value.lower():
                    return record
        # Partial match fallback
        for record in records:
            if isinstance(record, dict):
                val = str(record.get(match_field, "")).lower()
                if lookup_value.lower() in val:
                    return record

    # Step 2: LLM-based matching — show it a sample of real records
    # and ask which one matches. No field names hardcoded.
    sample     = records[:20]  # limit for token budget
    compressed = enforce_size_limit(json.dumps(compress_json(sample), indent=2))

    prompt = f"""
You are matching a user-supplied value to a record in an API response.

User is looking for: "{lookup_value}"

Here are the records returned by the API:
{compressed}

Which record best matches what the user is looking for?
Consider all fields — name, title, code, slug, label, or any descriptive field.

Respond with ONLY the index (0-based integer) of the best matching record,
or -1 if none match. No explanation.
"""
    ensure_prompt_within_limit(prompt)
    response = llm.invoke(prompt)
    raw = response.content.strip()

    try:
        idx = int(re.search(r"-?\d+", raw).group())
        if 0 <= idx < len(records):
            return records[idx]
    except Exception:
        pass

    return None

# ─────────────────────────────────────────────────────────────────────────────
# Main tool_node
# ─────────────────────────────────────────────────────────────────────────────

def tool_node(state, base_url):
    plan      = state["plan"]
    full_spec = load_full_spec(state["openapi_spec"])

    # ══════════════════════════════════════════════════════════════
    # CASE 1: Name-lookup
    #   Planner detected user gave a non-ID value for a path param.
    #   Steps:
    #     a) Call list/search endpoint (plan already rewrote path/payload)
    #     b) Find matching record — using spec-derived match_field + LLM fallback
    #     c) Extract real ID from matched record
    #     d) Call original endpoint with real ID
    # ══════════════════════════════════════════════════════════════
    if plan.get("name_lookup"):
        lookup_value    = plan["lookup_value"]
        lookup_field    = plan["lookup_field"]   # path param name e.g. "id"
        match_field     = plan.get("match_field")  # spec-derived field to match on
        original_path   = plan["original_path"]
        original_method = plan["original_method"]

        print(f"\n  [ToolNode] 🔍 Name-lookup: '{lookup_value}' | match_field from spec: {match_field}")

        # a) Call list/search endpoint
        list_url = urljoin(base_url.rstrip("/") + "/", plan["path"].lstrip("/"))
        raw_response = call_tool_api(
            method  = "GET",
            path    = list_url,
            payload = plan.get("payload") or None,
        )

        records = _unwrap_list(raw_response.get("data", raw_response))

        # b) Find the matching record
        matched = _find_matching_record(records, lookup_value, match_field)

        if not matched:
            state["api_response"] = {
                "status_code": 404,
                "success":     False,
                "data": {
                    "message": (
                        f"No record found matching '{lookup_value}'. "
                        f"Searched {len(records)} records at {plan['path']}."
                    )
                }
            }
            return state

        # c) Extract the real ID — try the path param name, then "id"
        real_id = matched.get(lookup_field) or matched.get("id")
        print(f"  [ToolNode] ✅ Match found: {lookup_field}={real_id} | record keys: {list(matched.keys())}")

        # d) Call original endpoint with real ID
        resolved_path = replace_path_params(original_path, {lookup_field: real_id})
        final_url     = urljoin(base_url.rstrip("/") + "/", resolved_path.lstrip("/"))

        result = call_tool_api(
            method  = original_method,
            path    = final_url,
            payload = None if original_method.upper() == "GET" else {lookup_field: real_id},
        )
        state["api_response"] = result
        return state

    # ══════════════════════════════════════════════════════════════
    # CASE 2: Dynamic DELETE by attribute
    # ══════════════════════════════════════════════════════════════
    path_methods = full_spec["paths"].get(plan["path"], {})
    if plan.get("dynamic_delete") or (
        plan["method"].upper() == "DELETE" and "delete" not in path_methods
    ):
        get_url        = urljoin(base_url + "/", plan["path"].lstrip("/"))
        resources      = call_tool_api(method="GET", path=get_url, payload=None)
        filter_payload = plan.get("filter_payload", plan.get("payload", {}))
        resource_list  = resources if isinstance(resources, list) else []
        matches        = [
            r for r in resource_list
            if all(r.get(k) == v for k, v in filter_payload.items())
        ]
        deleted = []
        for r in matches:
            del_path = plan["path"]
            for k, v in r.items():
                del_path = del_path.replace(f"{{{k}}}", str(v))
            del_url = urljoin(base_url + "/", del_path.lstrip("/"))
            res = call_tool_api(method="DELETE", path=del_url, payload=None)
            deleted.append(res)
        state["api_response"] = deleted if deleted else [{"deleted": 0}]
        plan["dynamic_delete"] = False
        return state

    # ══════════════════════════════════════════════════════════════
    # CASE 3: Normal GET / POST / PUT
    # ══════════════════════════════════════════════════════════════
    spec_path = find_spec_path(full_spec, plan["path"])

    schema = get_request_schema(full_spec, spec_path, plan["method"])
    if schema:
        for _ in range(2):
            errors = validate_payload(plan["payload"], schema, full_spec)
            if not errors:
                break
            plan["payload"] = fix_payload_with_llm(plan["payload"], schema, errors)

    path_with_params = replace_path_params(plan["path"], plan.get("payload", {}))
    full_url         = urljoin(base_url + "/", path_with_params.lstrip("/"))

    if plan["method"].upper() == "PUT":
        plan["payload"] = merge_with_existing_resource(base_url, plan)

    result = call_tool_api(method=plan["method"], path=full_url, payload=plan.get("payload"))
    state["api_response"] = result
    return state