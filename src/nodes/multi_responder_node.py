# src/nodes/multi_responder_node.py
"""
Multi-Responder Node
─────────────────────
Collects all sub_task_results and synthesises one coherent answer.
Fully generic — works with any set of sub-tasks from any API.
"""

import json
from src.llms.groq import get_llm
from src.utils.utils import ensure_prompt_within_limit, enforce_size_limit

llm = get_llm()


def multi_responder_node(state: dict) -> dict:
    results = state.get("sub_task_results", [])

    summaries = [
        {
            "task_id":    r["agent_id"],
            "task":       r["task_description"],
            "answer":     r["final_answer"],
        }
        for r in results
    ]

    safe_summaries = enforce_size_limit(json.dumps(summaries, indent=2))

    prompt = f"""
The user asked: "{state['user_query']}"

To answer this, multiple API sub-tasks were executed. Here are their results:

{safe_summaries}

Write ONE clear, complete, and natural answer to the user's original request.
- Integrate the sub-task results naturally (do not just list them).
- If tasks depended on each other, explain how the data flowed.
- Be concise but complete.
"""

    ensure_prompt_within_limit(prompt)
    response = llm.invoke(prompt)

    state["final_answer"] = response.content
    state["next_skill"]   = None  # signals END
    return state