import requests
from config import settings

def call_petstore_api(method, path, payload=None):
    url = f"{settings.PETSTORE_BASE_URL}{path}"

    response = requests.request(
        method=method,
        url=url,
        json=payload
    )
    print("res-->",response.json())

    try:
        return response.json()
    except:
        return response.text
