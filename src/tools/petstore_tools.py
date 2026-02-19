import requests

def call_tool_api(method, path, payload=None, base_url=None):
    if not base_url:
        raise ValueError("No base URL provided")

    url = f"{base_url}{path}"

    response = requests.request(method=method, url=url, params=payload if method=="GET" else None, json=payload if method!="GET" else None)

    try:
        return response.json()
    except Exception:
        return response.text


