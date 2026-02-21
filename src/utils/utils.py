# utils/utils.py
import json

MAX_ITEMS = 10
MAX_STRING_LENGTH = 300
MAX_TOTAL_CHARS = 8000
MAX_PROMPT_CHARS = 12000
MAX_VALIDATION_ERRORS = 3

def compress_schema(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {}
    return {
        "type": schema.get("type"),
        "required": schema.get("required", []),
        "properties": {
            k: {"type": v.get("type"), "enum": v.get("enum"), "format": v.get("format")}
            for k, v in schema.get("properties", {}).items() if isinstance(v, dict)
        },
    }

def limit_validation_errors(errors):
    return "\n".join([e.message for e in errors[:MAX_VALIDATION_ERRORS]])

def compress_json(data, depth=0):
    if isinstance(data, list):
        return [compress_json(item, depth + 1) for item in data[:MAX_ITEMS]]
    if isinstance(data, dict):
        return {k: compress_json(v, depth + 1) for k, v in data.items()}
    if isinstance(data, str):
        return data[:MAX_STRING_LENGTH] + " ...truncated" if len(data) > MAX_STRING_LENGTH else data
    return data

def enforce_size_limit(obj):
    text = json.dumps(obj)
    return text[:MAX_TOTAL_CHARS] + " ...truncated" if len(text) > MAX_TOTAL_CHARS else text

def ensure_prompt_within_limit(prompt: str):
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too large ({len(prompt)} chars). Compression failed.")