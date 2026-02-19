import streamlit as st
import requests

st.title("🐾Build & Test with OpenAPI Specs")

uploaded_file = st.file_uploader("Upload OpenAPI spec (JSON/YAML)", type=["json", "yaml", "yml"])
spec_url = st.text_input("Or provide OpenAPI spec URL")

# Send spec to FastAPI backend
if uploaded_file is not None:
    files = {"file": uploaded_file}
    res = requests.post("http://localhost:8000/load_spec", files=files)
    if res.status_code == 200:
        st.success("Spec uploaded successfully")
    else:
        st.error(res.json())

elif spec_url:
    res = requests.post("http://localhost:8000/load_spec", data={"url": spec_url})
    if res.status_code == 200:
        st.success("Spec loaded successfully from URL")
    else:
        st.error(res.json())

query = st.text_input("Ask in natural language")

if st.button("Submit"):
    res = requests.post("http://localhost:8000/query", params={"query": query})
    st.subheader("Execution Result")
    if res.headers.get("content-type", "").startswith("application/json"):
        st.json(res.json())
    else:
        st.error("Backend returned non-JSON response")
        st.text(res.text)

