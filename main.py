from fastapi import FastAPI, UploadFile, Form
import requests
import json, yaml
from src.graphs.pet_graph import build_graph
from urllib.parse import urlparse
app = FastAPI(title="LangGraph Agent with Dynamic Spec")

# Store spec + base URL in app state
app.state.openapi_spec = None
app.state.base_url = None

def parse_base_url(spec_str: str, spec_source_url: str = None) -> str:
    try:
        spec = json.loads(spec_str)
    except json.JSONDecodeError:
        spec = yaml.safe_load(spec_str)

    if "servers" in spec and spec["servers"]:
        url = spec["servers"][0].get("url", "")
        if url.startswith("/"):
            if spec_source_url:
                parsed = urlparse(spec_source_url)
                return f"{parsed.scheme}://{parsed.netloc}{url}"
            return f"http://localhost{url}"
        return url

    # Swagger 2.0 fallback
    host = spec.get("host", "")
    schemes = spec.get("schemes", ["https"])
    base_path = spec.get("basePath", "")
    scheme = schemes[0] if schemes else "https"
    return f"{scheme}://{host}{base_path}"

@app.post("/load_spec")
async def load_spec(file: UploadFile = None, url: str = Form(None)):
    """
    Load an OpenAPI spec either from an uploaded file or a URL.
    Stores the spec content and base URL in app.state.
    """
    if file:
        content = await file.read()
        app.state.openapi_spec = content.decode("utf-8")
        app.state.base_url = parse_base_url(app.state.openapi_spec, spec_source_url=url)
        return {"message": "Spec loaded successfully from file", "base_url": app.state.base_url}

    elif url:
        res = requests.get(url)
        if res.status_code == 200:
            app.state.openapi_spec = res.text
            app.state.base_url = parse_base_url(app.state.openapi_spec, spec_source_url=url)
            return {"message": "Spec loaded successfully from URL", "base_url": app.state.base_url}
        else:
            return {"error": f"Failed to fetch spec from URL (status {res.status_code})"}

    return {"error": "No spec provided"}


@app.get("/current_spec")
def get_current_spec():
    """
    Retrieve the currently loaded OpenAPI spec and base URL.
    """
    if not app.state.openapi_spec:
        return {"error": "No spec loaded"}
    return {"base_url": app.state.base_url, "spec": app.state.openapi_spec}


@app.post("/query")
def query_agent(query: str):
    """
    Query endpoint that uses the loaded spec.
    """
    try:
        if not app.state.openapi_spec or not app.state.base_url:
            return {"error": "No OpenAPI spec loaded. Please upload or provide a URL first."}

        # Build graph dynamically using the loaded spec
        graph = build_graph(app.state.openapi_spec)
        result = graph.invoke({
            "user_query": query,
            "base_url": app.state.base_url,  # pass base_url into state
            "openapi_spec": app.state.openapi_spec
        })

        # ✅ Strip out openapi_spec before sending response to user
        if "openapi_spec" in result:
            del result["openapi_spec"]

        safe_result = json.loads(json.dumps(result, default=str))
        return safe_result
    except Exception as e:
        print("error",e)
        return {
            "error": "Internal server error",
            "details": str(e)
        }
