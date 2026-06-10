"""Hugging Face Spaces entrypoint (Streamlit SDK).

Purpose:     Single-process bootstrap for a Streamlit Space: starts the FastAPI
             backend on an internal port in a background thread, points the
             dashboard's API client at it, then runs the Streamlit dashboard.
Source:      `streamlit run app.py` (the default command for a Streamlit Space).
Destination: The full HRO-PS dashboard served on the Space's public port, with
             the API private to the container.

Hard requirements honoured:
* No training on startup — models and forecasts are pre-generated artifacts
  committed to the repo (artifacts/models_72h, artifacts/forecast_outputs).
* No hard-coded secrets — JWT_SECRET_KEY and DATABASE_URL come from Space
  secrets (Settings -> Variables and secrets). For a demo Space without a
  managed Postgres, set DATABASE_URL to sqlite:///./hf_demo.db.

Local check (no Space needed):
    python -c "import app"            # must not raise, must not train
"""

from __future__ import annotations

import os
import threading
import time

# Internal API port (not exposed by the Space; only the dashboard is public).
_API_PORT = int(os.getenv("INTERNAL_API_PORT", "7861"))

# Default env for a self-contained Space. Real deployments override these via
# Space secrets; setdefault never overwrites configured values.
os.environ.setdefault("APP_ENV", os.getenv("APP_ENV", "dev"))
os.environ.setdefault("API_BASE_URL", f"http://127.0.0.1:{_API_PORT}")
os.environ.setdefault("DATABASE_URL", "sqlite:///./hf_demo.db")


def _start_api_once() -> None:
    """Start uvicorn in a daemon thread (idempotent across Streamlit reruns)."""

    import uvicorn

    from main import app as fastapi_app

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=_API_PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def _ensure_api_running() -> None:
    import requests

    base = os.environ["API_BASE_URL"]
    try:
        requests.get(f"{base}/health", timeout=1)
        return  # already up (Streamlit rerun)
    except Exception:
        pass

    thread = threading.Thread(target=_start_api_once, name="hro-ps-api", daemon=True)
    thread.start()

    for _ in range(60):  # wait up to ~30 s for cold start
        try:
            requests.get(f"{base}/health", timeout=1)
            return
        except Exception:
            time.sleep(0.5)


def main() -> None:
    _ensure_api_running()

    # Run the existing dashboard script in this Streamlit session.
    import runpy

    runpy.run_path("dashboard.py", run_name="__main__")


# Only bootstrap when executed by Streamlit — a plain `import app` (used by the
# deployment smoke check) must stay side-effect free.
if __name__ == "__main__" or os.getenv("STREAMLIT_SERVER_PORT") or "streamlit" in os.getenv("_", "").lower():
    main()
