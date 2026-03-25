from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
import bcrypt


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in your environment (or docker-compose)."
        )
    return value.strip()


from settings import get_settings

_settings = get_settings()

SECRET_KEY = (_settings.jwt_secret_key or os.getenv("JWT_SECRET_KEY", "")).strip()
# Dev-friendly: allow running locally with a safe-ish default while still
# requiring a real secret in production.
if not SECRET_KEY:
    if str(_settings.app_env).lower() in {"dev", "local", "test"}:
        SECRET_KEY = "dev-unsafe-secret-change-me"
    else:
        raise RuntimeError(
            "JWT_SECRET_KEY is required. Refusing to start with an unsafe default secret."
        )

ALGORITHM = (_settings.jwt_algorithm or os.getenv("JWT_ALGORITHM", "HS256")).strip() or "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    _settings.access_token_expire_minutes or os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60") or "60"
)

def hash_password(password: str) -> str:
    """Hash a password using the `bcrypt` package (not passlib).

    Rationale: passlib<2 has known incompatibilities with newer `bcrypt` builds.
    Using bcrypt directly keeps the login flow working on this repo's runtime.
    """

    if password is None:
        return ""
    pw = str(password).encode("utf-8")
    # bcrypt only uses the first 72 bytes; keep behaviour explicit.
    pw = pw[:72]
    hashed = bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or "$" not in str(hashed_password):
        return False
    try:
        pw = str(plain_password).encode("utf-8")[:72]
        hpw = str(hashed_password).encode("utf-8")
        return bool(bcrypt.checkpw(pw, hpw))
    except Exception:
        return False


def create_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError("Invalid token") from e


def bearer_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    if parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
