"""FastAPI entrypoint for production deployments.

This repo historically used `api.py` as the module that defines `app = FastAPI()`.
Most PaaS platforms (Render/Railway/AWS App Runner) expect a stable `main:app`.

We keep `api.py` as the real implementation and re-export the app here.
"""

from api import app  # noqa: F401
