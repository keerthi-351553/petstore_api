# src/nodes/multi_planner_node.py
"""
Steps:
  1. Parse the spec → extract all available METHOD /path strings
  2. Ask the LLM to group those endpoints into logical sub-tasks
     that together satisfy the user's request
  3. For each sub-task, record which endpoints it needs and whether
     it depends on a prior sub-task's output

The LLM decides grouping — it might produce 1 task or 5, depending
on what the spec offers and what the user asked for.
"""

import json
from src.llms.groq import get_llm
from src.utils.utils import ensure_prompt_within_limit

llm = get_llm()


def _parse_spec(spec_str: str) -> dict:
    import yaml
    try:
        return json.loads(spec_str)
    except Exception:
        return yaml.safe_load(spec_str)


def _extract_all_endpoints(spec: dict) -> list[str]:
    """Return every METHOD /path in the spec as a flat list."""
    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method in methods.keys():
            if method.lower() not in ("parameters", "summary", "description"):
                endpoints.append(f"{method.upper()} {path}")
    return endpoints


def _extract_endpoint_summaries(spec: dict) -> list[str]:
    """Return METHOD /path – summary lines to give the LLM richer context."""
    lines = []
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method.lower() in ("parameters", "summary", "description"):
                continue
            summary = details.get("summary", details.get("description", ""))
            line = f"{method.upper()} {path}"
            if summary:
                line += f"  →  {summary}"
            lines.append(line)
    return lines


def multi_planner_node(state: dict) -> dict:
    """
    Decomposes the user query into SubTasks driven purely by the
    loaded OpenAPI spec — no hardcoded domain knowledge.
    """
    spec          = _parse_spec(state["openapi_spec"])
    all_endpoints = _extract_all_endpoints(spec)
    endpoint_docs = _extract_endpoint_summaries(spec)

    endpoints_text = "\n".join(endpoint_docs)

    prompt = f"""
You are a task planner for a generic REST API agent.

The loaded API has these endpoints:
{endpoints_text}

The user wants: "{state['user_query']}"

Your job:
1. Decide how many sub-tasks are needed to fully satisfy the request.
2. Assign each sub-task a unique agent_id like "task_0", "task_1", etc.
3. For each sub-task, list only the specific endpoints it needs.
4. If a sub-task needs data from a previous sub-task (e.g. needs an ID that
   the earlier task will retrieve), set depends_on to that task's agent_id.
   Otherwise set depends_on to null.

Rules:
- Only use endpoints from the list above — never invent paths.
- If the whole request can be handled by ONE API call, return a single sub-task.
- Keep task_description specific and actionable.
- Do NOT hardcode any domain names like "pet", "store", "user" — 
  reason only from the endpoint paths and summaries given above.

Respond with ONLY a JSON array, no explanation:
[
  {{
    "agent_id": "task_0",
    "task_description": "...",
    "endpoints": ["GET /some/path", "POST /other/path"],
    "depends_on": null
  }},
  {{
    "agent_id": "task_1",
    "task_description": "... using the result from task_0 ...",
    "endpoints": ["POST /another/path"],
    "depends_on": "task_0"
  }}
]
"""

    ensure_prompt_within_limit(prompt)
    response = llm.invoke(prompt)
    raw = response.content.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        task_queue = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: single task with all endpoints
        task_queue = [{
            "agent_id":        "task_0",
            "task_description": state["user_query"],
            "endpoints":        all_endpoints,
            "depends_on":       None,
        }]

    print(f"\n[MultiPlanner] Created {len(task_queue)} sub-task(s):")
    for t in task_queue:
        dep = f" (depends on {t['depends_on']})" if t.get("depends_on") else ""
        print(f"  • {t['agent_id']}{dep}: {t['task_description'][:70]}")

    state["task_queue"]       = task_queue
    state["sub_task_results"] = []
    state["next_skill"]       = "task_dispatcher"
    return state