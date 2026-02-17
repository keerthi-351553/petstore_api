import streamlit as st
import requests

st.title("🐾 LangGraph + Groq Petstore Agent")

query = st.text_input("Ask in natural language")

if st.button("Submit"):

    res = requests.post(
        "http://localhost:8000/query",
        params={"query": query}
    )

    data = res.json()

    st.subheader("Execution Result")
    st.json(data)
