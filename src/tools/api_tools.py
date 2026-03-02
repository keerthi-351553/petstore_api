import requests
from urllib.parse import urljoin

def call_tool_api(method, path, payload=None, base_url=None):
    """Call API with full URL or relative path + base_url"""
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    elif base_url:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    else:
        raise ValueError("No base URL provided")

    response = requests.request(
        method=method,
        url=url,
        params=payload if method.upper() == "GET" else None,
        json=payload if method.upper() != "GET" else None
    )
    result = {
        "status_code": response.status_code,
        "success": response.ok
    }

    try:
        result["data"] = response.json()
    except:
        result["data"] = response.text

    return result
