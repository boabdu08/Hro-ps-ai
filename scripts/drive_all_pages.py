"""Phase 3 driver: visit every dashboard page for every role via AppTest.

Requires the API to be live on :8000. Prints PASS/FAIL per role/page with the
first exception found. Not a pytest module (run directly).
"""

import os
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("APP_ENV", "dev")
B = "http://127.0.0.1:8000"

# AppTest.from_file resolves relative paths against THIS file's directory —
# use the absolute repo-root path so the driver works from scripts/.
REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = str(REPO_ROOT / "dashboard.py")
sys.path.insert(0, str(REPO_ROOT))

ROLE_PAGES = {
    "admin": ["Home", "Command Center", "Forecast", "Optimization", "Operations Center",
              "Shifts", "Appointments", "OR Bookings", "Notifications", "Messages",
              "Approvals", "Evaluation", "Explainability", "Audit"],
    "doctor": ["Home", "Overview", "Forecast", "My Shifts", "Appointments",
               "OR Bookings", "Notifications", "Messages"],
    "nurse": ["Home", "Overview", "My Shifts", "Appointments", "Department",
              "Notifications", "Messages"],
}
CREDS = {"admin": "admin1", "doctor": "doctor1", "nurse": "nurse1"}


def login(role):
    r = requests.post(f"{B}/auth/login", json={"username": CREDS[role], "password": "123456",
                                               "tenant": "demo-hospital"}, timeout=30)
    r.raise_for_status()
    return r.json()


def drive(role):
    from streamlit.testing.v1 import AppTest

    auth = login(role)
    failures = []
    for page in ROLE_PAGES[role]:
        t0 = time.time()
        try:
            at = AppTest.from_file(DASHBOARD, default_timeout=180)
            at.session_state["user"] = auth["user"]
            at.session_state["token"] = auth["access_token"]
            os.environ["API_TOKEN"] = auth["access_token"]
            at.run()
            radios = at.sidebar.radio
            if not radios:
                raise RuntimeError("no sidebar navigation radio found (login page shown?)")
            radios[0].set_value(page).run()
            exc = list(at.exception)
            if exc:
                failures.append((page, exc[0].value))
                print(f"  FAIL {role}/{page}: {exc[0].value}")
            else:
                print(f"  pass {role}/{page} ({time.time()-t0:.0f}s)")
        except Exception as e:
            failures.append((page, str(e)))
            print(f"  FAIL {role}/{page}: {e}")
    return failures


if __name__ == "__main__":
    all_failures = {}
    for role in ROLE_PAGES:
        print(f"=== {role} ===")
        f = drive(role)
        if f:
            all_failures[role] = f
    print("\n==== SUMMARY ====")
    if not all_failures:
        print("ALL PAGES PASS for all roles")
    else:
        for role, fails in all_failures.items():
            for page, err in fails:
                print(f"{role}/{page}: {str(err)[:300]}")
    sys.exit(1 if all_failures else 0)
