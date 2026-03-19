import requests

import os

from settings import get_settings


def _auth_headers() -> dict:
    token = os.getenv("API_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}

_settings = get_settings()
API_BASE_URL = (
    (_settings.api_base_url or "").strip()
    or os.getenv("API_BASE_URL", "http://127.0.0.1:8000").strip()
    or "http://127.0.0.1:8000"
)


def _safe_get(url, params=None, timeout=20):
    try:
        response = requests.get(url, params=params, timeout=timeout, headers=_auth_headers())
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # Streamlit will surface None; keep stdout logs for terminal/dev.
        print(f"GET API error [{url}]: {e}")
        return None


def _safe_post(url, payload=None, timeout=20):
    try:
        response = requests.post(url, json=payload, timeout=timeout, headers=_auth_headers())
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"POST API error [{url}]: {e}")
        return None


def api_base_url() -> str:
    return API_BASE_URL


def login_user_api(username, password):
    url = f"{API_BASE_URL}/auth/login"
    payload = {"username": username, "password": password}

    # SaaS: allow optional tenant selection (dashboard sets TENANT_SLUG env var).
    tenant_slug = os.getenv("TENANT_SLUG", "").strip()
    if tenant_slug:
        payload["tenant_slug"] = tenant_slug
    return _safe_post(url, payload=payload, timeout=10)


def get_system_status():
    return _safe_get(f"{API_BASE_URL}/status", timeout=10)


def get_feature_config():
    return _safe_get(f"{API_BASE_URL}/feature_config", timeout=10)


def get_latest_sequence():
    data = _safe_get(f"{API_BASE_URL}/patient_flow/latest", timeout=15)
    if not data:
        return None
    return data.get("sequence")


def get_prediction(sequence):
    payload = {"sequence": sequence.tolist() if hasattr(sequence, "tolist") else sequence}
    return _safe_post(f"{API_BASE_URL}/predict", payload=payload, timeout=25)


def simulate(predicted_patients, beds_available, doctors_available, demand_increase):
    payload = {
        "predicted_patients": float(predicted_patients),
        "beds_available": int(beds_available),
        "doctors_available": int(doctors_available),
        "demand_increase_percent": float(demand_increase),
    }
    return _safe_post(f"{API_BASE_URL}/simulate", payload=payload, timeout=25)


def explain_prediction(sequence):
    payload = {"sequence": sequence.tolist() if hasattr(sequence, "tolist") else sequence}
    return _safe_post(f"{API_BASE_URL}/explain", payload=payload, timeout=25)


def get_optimization(predicted_patients):
    return _safe_get(f"{API_BASE_URL}/optimize_resources/{predicted_patients}", timeout=20)


def get_message_templates():
    # prefer stable new route; keep backwards compatibility in API too
    return _safe_get(f"{API_BASE_URL}/messages/templates", timeout=10)


def get_messages(
    role=None,
    department=None,
    limit=50,
    unread_only=False,
    include_archived=False,
    sender_name=None,
    message_type=None,
    priority=None,
    pinned_only=False,
):
    params = {
        "limit": int(limit),
        "unread_only": bool(unread_only),
        "include_archived": bool(include_archived),
    }

    if role:
        params["role"] = role
    if department:
        params["department"] = department
    if sender_name:
        params["sender_name"] = sender_name

    if message_type:
        params["type"] = message_type
    if priority:
        params["priority"] = priority
    if pinned_only:
        params["pinned_only"] = bool(pinned_only)

    return _safe_get(f"{API_BASE_URL}/messages", params=params, timeout=20)


def get_unread_message_count():
    return _safe_get(f"{API_BASE_URL}/messages/unread_count", timeout=10)


def send_message_api(
    sender_role,
    sender_name,
    title,
    message,
    target_role="all",
    target_department="All Departments",
    priority="normal",
    category="general",
    message_type="normal",
    is_pinned=False,
):
    payload = {
        "sender_role": sender_role,
        "sender_name": sender_name,
        "target_role": target_role,
        "target_department": target_department,
        "priority": priority,
        "message_type": message_type,
        "is_pinned": bool(is_pinned),
        "category": category,
        "title": title,
        "message": message,
    }
    return _safe_post(f"{API_BASE_URL}/messages/send", payload=payload, timeout=20)


def send_quick_reply_api(message_id, reply_text, replied_by):
    payload = {
        "message_id": message_id,
        "reply": reply_text,
        "reply_by": replied_by,
    }
    return _safe_post(f"{API_BASE_URL}/messages/reply", payload=payload, timeout=20)


def acknowledge_message_api(message_id):
    return _safe_post(
        f"{API_BASE_URL}/messages/ack",
        payload={"message_id": message_id},
        timeout=20,
    )


def archive_message_api(message_id):
    return _safe_post(
        f"{API_BASE_URL}/messages/archive",
        payload={"message_id": message_id},
        timeout=20,
    )


def evaluate_model(actual, lstm, arimax, hybrid):
    payload = {
        "actual": actual,
        "lstm": lstm,
        "arimax": arimax,
        "hybrid": hybrid,
    }
    return _safe_post(f"{API_BASE_URL}/evaluate", payload=payload, timeout=25)


def get_optimization_runs(limit: int = 20):
    return _safe_get(f"{API_BASE_URL}/optimization_runs", params={"limit": int(limit)}, timeout=15)


def get_optimization_run(run_id: str):
    return _safe_get(f"{API_BASE_URL}/optimization_runs/{run_id}", timeout=15)


# ---------------------
# Alerts + Notifications
# ---------------------


def get_alerts(active_only: bool = True, department: str | None = None, limit: int = 50):
    params = {"active_only": bool(active_only), "limit": int(limit)}
    if department:
        params["department"] = department
    return _safe_get(f"{API_BASE_URL}/alerts", params=params, timeout=15)


def create_alert_api(
    title: str,
    message: str,
    alert_type: str = "operational_alert",
    priority: str = "medium",
    related_department: str | None = None,
    target_role: str = "all",
    target_department: str = "All Departments",
):
    payload = {
        "title": title,
        "message": message,
        "alert_type": alert_type,
        "priority": priority,
        "related_department": related_department,
        "target_role": target_role,
        "target_department": target_department,
    }
    return _safe_post(f"{API_BASE_URL}/alerts/create", payload=payload, timeout=15)


def ack_alert_api(alert_id: str):
    return _safe_post(f"{API_BASE_URL}/alerts/ack", payload={"alert_id": alert_id}, timeout=15)


def resolve_alert_api(alert_id: str):
    return _safe_post(f"{API_BASE_URL}/alerts/resolve", payload={"alert_id": alert_id}, timeout=15)


def get_notifications(unread_only: bool = False, limit: int = 50):
    return _safe_get(
        f"{API_BASE_URL}/notifications",
        params={"unread_only": bool(unread_only), "limit": int(limit)},
        timeout=15,
    )


def get_unread_notification_count():
    return _safe_get(f"{API_BASE_URL}/notifications/unread_count", timeout=10)


def mark_notification_read(notification_id: str):
    return _safe_post(
        f"{API_BASE_URL}/notifications/read",
        payload={"notification_id": notification_id},
        timeout=15,
    )


def get_notification_preferences():
    return _safe_get(f"{API_BASE_URL}/notifications/preferences", timeout=10)


def update_notification_preferences(payload: dict):
    return _safe_post(f"{API_BASE_URL}/notifications/preferences", payload=payload, timeout=15)