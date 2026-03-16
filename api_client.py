import requests

API_BASE_URL = "http://127.0.0.1:8000"


def get_prediction(sequence):
    url = f"{API_BASE_URL}/predict"
    payload = {"sequence": sequence.tolist()}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Prediction API error:", e)
        return None


def simulate(predicted_patients, beds_available, doctors_available, demand_increase):
    url = f"{API_BASE_URL}/simulate"

    payload = {
        "predicted_patients": float(predicted_patients),
        "beds_available": int(beds_available),
        "doctors_available": int(doctors_available),
        "demand_increase_percent": float(demand_increase),
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Simulation API error:", e)
        return None


def explain_prediction(sequence):
    url = f"{API_BASE_URL}/explain"
    payload = {"sequence": sequence.tolist()}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Explain API error:", e)
        return None


def get_system_status():
    url = f"{API_BASE_URL}/status"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Status API error:", e)
        return None


def login_user_api(username, password):
    url = f"{API_BASE_URL}/auth/login"

    try:
        response = requests.post(
            url,
            json={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Login API error:", e)
        return None