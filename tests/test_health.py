import os

import requests


def test_health_endpoint():
    """Optional smoke test.

    In CI we will start uvicorn in the background and set BASE_URL.
    Locally this test can be skipped by not setting BASE_URL.
    """

    base = os.getenv("BASE_URL", "").strip()
    if not base:
        return

    r = requests.get(f"{base}/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
