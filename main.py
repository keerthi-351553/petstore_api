# main.py
from fastapi import FastAPI, UploadFile, Form
import requests, json

from src.graphs.graphs import build_graph                        # existing single-agent
from src.graphs.multi_agent_graph import build_multi_agent_graph # multi-agent

app = FastAPI(title="LangGraph Generic OpenAPI Agent")

app.state.openapi_spec = None
app.state.base_url = None


# ── Existing endpoints (UNCHANGED) ──────────────────────────────────────────

@app.post("/load_spec")
async def load_spec(file: UploadFile = None, url: str = Form(None)):
    """Load any OpenAPI spec from a file upload or URL."""
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
    if not app.state.openapi_spec:
        return {"error": "No spec loaded"}
    return {"base_url": app.state.base_url, "spec": app.state.openapi_spec}


@app.post("/query")
def query_agent(query: str, base_url: str):
    """Single-agent query — handles one API call at a time."""
    if not app.state.openapi_spec or not base_url:
        return {"error": "No OpenAPI spec loaded. POST to /load_spec first."}
    try:
        app.state.base_url = base_url
        graph  = build_graph(app.state.openapi_spec, base_url)
        result = graph.invoke({
            "user_query":   query,
            "openapi_spec": app.state.openapi_spec,
        })
        result.pop("openapi_spec", None)
        return json.loads(json.dumps(result, default=str))
    except Exception as e:
        return {"error": "Internal server error", "details": str(e)}


# ── NEW: Multi-agent endpoint ────────────────────────────────────────────────

@app.post("/multi_query")
def multi_query_agent(query: str, base_url: str):
    """
    Multi-agent query — works with ANY loaded OpenAPI spec.

    Automatically:
      1. Analyses your spec's endpoints
      2. Breaks the user query into sub-tasks
      3. Runs each sub-task through a scoped single-agent graph
      4. Chains results between dependent tasks
      5. Returns one synthesised final answer

    Use this when your query spans multiple API operations, e.g.:
      - "Get all items and create a summary report"
      - "Find resource X then update resource Y using X's ID"
      - "Check the status of A and B and tell me which is active"
    """
    if not app.state.openapi_spec or not base_url:
        return {"error": "No OpenAPI spec loaded. POST to /load_spec first."}

    try:
        app.state.base_url = base_url
        graph  = build_multi_agent_graph()
        result = graph.invoke({
            "user_query":   query,
            "openapi_spec": app.state.openapi_spec,
            "base_url":     base_url,
        })
        result.pop("openapi_spec", None)
        return json.loads(json.dumps(result, default=str))
    except Exception as e:
        import traceback
        return {
            "error":   "Multi-agent error",
            "details": str(e),
            "trace":   traceback.format_exc(),
        }