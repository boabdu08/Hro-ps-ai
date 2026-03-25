"""Centralized environment configuration.

Goals:
- Work locally via optional `.env` file (developer convenience)
- Work in cloud (Render/Streamlit) via real environment variables
- Keep imports side-effect free and easy to test

Note: we intentionally avoid adding new dependencies (like python-dotenv) to
keep the repo lightweight. The `.env` loader here is minimal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str | Path = ".env") -> None:
    """Load key=value pairs into os.environ if not already set.

    This is a minimal parser:
    - ignores blank lines and comments (#)
    - supports KEY=VALUE (VALUE may be quoted)
    """

    p = Path(path)
    if not p.exists() or not p.is_file():
        return

    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if not key:
                continue
            # Never override real env vars.
            os.environ.setdefault(key, value)
    except Exception:
        # Do not crash on .env parsing issues.
        return


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    api_base_url: str

    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

    artifact_dir: str
    tenant_mode_enabled: bool
    default_tenant_slug: str

    # Background pipeline (for always-on cloud)
    scheduler_run_in_api: bool
    scheduler_interval_seconds: int
    synthetic_data_enabled: bool
    synthetic_emergency_rate: float


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def get_settings() -> Settings:
    # Local dev: allow `.env` file.
    _load_dotenv(".env")

    app_env = (os.getenv("APP_ENV") or "dev").strip().lower()

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    api_base_url = (os.getenv("API_BASE_URL") or "http://127.0.0.1:8000").strip() or "http://127.0.0.1:8000"

    jwt_secret_key = (os.getenv("JWT_SECRET_KEY") or "").strip()
    jwt_algorithm = (os.getenv("JWT_ALGORITHM") or "HS256").strip() or "HS256"
    access_token_expire_minutes = _int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 60)

    artifact_dir = (os.getenv("ARTIFACT_DIR") or ".").strip() or "."

    tenant_mode_enabled = _bool_env("TENANT_MODE_ENABLED", True)
    default_tenant_slug = (os.getenv("DEFAULT_TENANT_SLUG") or "demo-hospital").strip() or "demo-hospital"

    scheduler_run_in_api = _bool_env("SCHEDULER_RUN_IN_API", False)
    scheduler_interval_seconds = _int_env("SCHEDULER_INTERVAL_SECONDS", 300)
    synthetic_data_enabled = _bool_env("SYNTHETIC_DATA_ENABLED", True)
    try:
        synthetic_emergency_rate = float((os.getenv("SYNTHETIC_EMERGENCY_RATE") or "0.03").strip() or "0.03")
    except Exception:
        synthetic_emergency_rate = 0.03

    return Settings(
        app_env=app_env,
        database_url=database_url,
        api_base_url=api_base_url,
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=jwt_algorithm,
        access_token_expire_minutes=access_token_expire_minutes,
        artifact_dir=artifact_dir,
        tenant_mode_enabled=tenant_mode_enabled,
        default_tenant_slug=default_tenant_slug,

        scheduler_run_in_api=scheduler_run_in_api,
        scheduler_interval_seconds=scheduler_interval_seconds,
        synthetic_data_enabled=synthetic_data_enabled,
        synthetic_emergency_rate=synthetic_emergency_rate,
    )
