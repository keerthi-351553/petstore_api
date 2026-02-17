import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "llama-3.1-8b-instant"
    PETSTORE_BASE_URL = "https://petstore.swagger.io/v2"
    SPEC_PATH = "src/specs/petstore.json"

settings = Settings()