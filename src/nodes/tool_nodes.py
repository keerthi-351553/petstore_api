# nodes/tool_node.py
import json
from urllib.parse import urljoin, urlparse
from jsonschema import Draft7Validator, RefResolver

from src.llms.groq import get_llm
from src.tools.api_tools import call_tool_api
from src.states.states import Plan
from src.utils.utils import (
    compress_schema,
    limit_validation_errors,
    ensure_prompt_within_limit,
)

llm = get_llm()

def load_full_spec(spec_str: str):
    import yaml, json
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
    resolver = RefResolver.from_schema(full_spec)
    validator = Draft7Validator(schema, resolver=resolver)
    return list(validator.iter_errors(payload))

def fix_payload_with_llm(payload, schema, errors):
    compressed = compress_schema(schema)
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
    response = (
        llm.invoke(prompt))
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
    import re

    # 1️⃣ Try to get ID from payload
    resource_id = plan["payload"].get("id")

    # 2️⃣ If not in payload, try extracting from path (e.g., /Books/111)
    if not resource_id:
        match = re.search(r"/(\d+)(/)?$", plan["path"])
        if match:
            resource_id = match.group(1)

    # 3️⃣ If still not found → error
    if not resource_id:
        raise ValueError("Cannot determine resource ID for PUT")

    # 4️⃣ Build actual resource path
    resource_path = plan["path"]

    if "{id}" in resource_path:
        resource_path = resource_path.replace("{id}", str(resource_id))

    # 5️⃣ Fetch existing resource
    resource_url = urljoin(base_url.rstrip("/") + "/", resource_path.lstrip("/"))
    existing = call_tool_api(method="GET", path=resource_url, payload=None)

    if isinstance(existing, dict):
        merged = existing.copy()
        merged.update(plan["payload"])
        merged["id"] = int(resource_id)  # ensure ID remains
        return merged

    return plan["payload"]

def find_spec_path(full_spec, plan_path):
    """Find the templated path in spec that matches plan_path"""
    for spec_path in full_spec["paths"].keys():
        parts_spec = spec_path.strip("/").split("/")
        parts_plan = plan_path.strip("/").split("/")
        if len(parts_spec) != len(parts_plan):
            continue
        matched = True
        for s, p in zip(parts_spec, parts_plan):
            if s.startswith("{") and s.endswith("}"):
                continue  # path param, skip
            if s != p:
                matched = False
                break
        if matched:
            return spec_path
    raise ValueError(f"Invalid path: {plan_path}")


def tool_node(state):
    plan = state["plan"]
    full_spec = load_full_spec(state["openapi_spec"])
    base_url = state["base_url"].rstrip("/") or "http://localhost"
    
    # ==========================
    # Dynamic DELETE by attribute
    # ==========================
    path_methods = full_spec["paths"].get(plan["path"], {})
    if plan.get("dynamic_delete") or (plan["method"].upper() == "DELETE" and "delete" not in path_methods):
        get_url = urljoin(base_url + "/", plan["path"].lstrip("/"))
        resources = call_tool_api(method="GET", path=get_url, payload=None)
        filter_payload = plan.get("filter_payload", plan.get("payload", {}))
        matches = [r for r in resources if all(r.get(k) == v for k, v in filter_payload.items())]

        deleted = []
        for r in matches:
            del_path = plan["path"]
            for k, v in r.items():
                del_path = del_path.replace(f"{{{k}}}", str(v))
            del_url = urljoin(base_url + "/", del_path.lstrip("/"))
            res = call_tool_api(method="DELETE", path=del_url, payload=None)
            deleted.append(res)
        state["api_response"] = deleted
        return state

    # ==========================
    # PUT/POST/GET logic
    # ==========================
    # 1️⃣ Normalize path for schema lookup
    spec_path = find_spec_path(full_spec, plan["path"])

    # 2️⃣ Validation + repair
    schema = get_request_schema(full_spec, spec_path, plan["method"])
    if schema:
        for _ in range(2):
            errors = validate_payload(plan["payload"], schema, full_spec)
            if not errors:
                break
            plan["payload"] = fix_payload_with_llm(plan["payload"], schema, errors)

    # 3️⃣ Replace path parameters for actual call
    path_with_params = replace_path_params(plan["path"], plan.get("payload", {}))
    full_url = urljoin(base_url + "/", path_with_params.lstrip("/"))

    # 4️⃣ Merge existing resource for PUT
    if plan["method"].upper() == "PUT":
        plan["payload"] = merge_with_existing_resource(base_url, plan)

    # 5️⃣ Call API
    result = call_tool_api(method=plan["method"], path=full_url, payload=plan.get("payload"))
    state["api_response"] = result
    return state