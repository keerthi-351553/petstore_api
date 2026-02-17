# 🐾 Petstore LangGraph Agent (Groq + Swagger API)

AI agent that converts natural language into real-time API calls against the Swagger Petstore API using LangGraph and Groq LLM.

---

## 🚀 Features

- Natural language → API execution
- Structured LLM output (Pydantic)
- Supports GET, POST, PUT, DELETE
- Automatic path parameter injection
- FastAPI backend
- Streamlit UI

---

## 🏗 Architecture

User → Streamlit UI → FastAPI → LangGraph  
→ Planner Node (Groq + Structured Output)  
→ Tool Node (Swagger API Call)  
→ Response Node → User

---
# ⚙️ Project Setup

## 1. Clone the Repository

```bash
git clone <your-repo-url>
cd petstore
```

---

## 2. Create Virtual Environment

### Windows
```bash
python -m venv .venv
.venv\Scripts\activate
```

### Mac / Linux
```bash
python -m venv .venv
source .venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file in the project root and add:

```
GROQ_API_KEY=your_groq_api_key
```

---

## 5. Run Backend (FastAPI)

```bash
uvicorn main:app --reload
```

Backend runs at:

```
http://127.0.0.1:8000
```

Test endpoint:

```
http://127.0.0.1:8000/query?query=get%20me%20123
```

---

## 6. Run Streamlit UI (Optional)

```bash
streamlit run ./src/ui/streamlit_ui.py
```

---

## 7. Sample Queries

```
Add a dog named dommy
Get me 123
Update the name to doggy for 123
Delete pet


