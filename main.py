from fastapi import FastAPI
from src.graphs.pet_graph import build_graph

app = FastAPI(title="LangGraph Petstore Agent")

graph = build_graph()

@app.post("/query")
def query_agent(query: str):

    result = graph.invoke({
        "user_query": query
    })

    return result
