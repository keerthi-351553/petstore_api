# nodes/response_node.py
from src.llms.groq import get_llm
from src.utils.utils import compress_json, enforce_size_limit, ensure_prompt_within_limit

llm = get_llm()

def response_node(state):
    api_data = state.get("api_response")
    compressed = compress_json(api_data)
    safe_payload = enforce_size_limit(compressed)

    prompt = f"""
User asked:
{state['user_query']}

API result (compressed):
{safe_payload}

Provide a clean natural language answer.
If API failed, explain clearly.
"""
    ensure_prompt_within_limit(prompt)
    response = llm.invoke(prompt)
    state["final_answer"] = response.content
    return state