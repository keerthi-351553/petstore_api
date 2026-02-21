from fastapi import FastAPI, UploadFile, Form
import requests, json
from src.graphs.graphs import build_graph

app = FastAPI(title="LangGraph Dynamic OpenAPI Agent")

# Store spec + base URL in app state
app.state.openapi_spec = None
app.state.base_url = None

@app.post("/load_spec")
async def load_spec(file: UploadFile = None, url: str = Form(None)):
    """Load OpenAPI spec from file or URL"""
    if file:
        content = await file.read()
        app.state.openapi_spec = content.decode("utf-8")
    elif url:
        res = requests.get(url)
        if res.status_code != 200:
            return {"error": f"Failed to fetch spec (status {res.status_code})"}
        app.state.openapi_spec = res.text
    else:
        return {"error": "No spec provided"}
    return {"message": "Spec loaded successfully"}


@app.get("/current_spec")
def get_current_spec():
    """Retrieve current spec"""
    if not app.state.openapi_spec:
        return {"error": "No spec loaded"}
    return {"base_url": app.state.base_url, "spec": app.state.openapi_spec}


@app.post("/query")
def query_agent(query: str, base_url: str):
    """Process user query dynamically using LangGraph workflow"""
    if not app.state.openapi_spec or not base_url:
        return {"error": "No OpenAPI spec loaded. Please upload or provide a URL first."}

    try:
        app.state.base_url = base_url
        graph = build_graph(app.state.openapi_spec)

        result = graph.invoke({
            "user_query": query,
            "openapi_spec": app.state.openapi_spec,
            "base_url": base_url
        })

        # remove spec from response
        if "openapi_spec" in result:
            del result["openapi_spec"]
        return json.loads(json.dumps(result, default=str))
    except Exception as e:
        return {"error": "Internal server error", "details": str(e)}