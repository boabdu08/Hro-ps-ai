import os

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "hro_db"

DEFAULT_DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


@lru_cache(maxsize=1)
def get_engine():
    # Production-friendly defaults while keeping local-dev simple.
    # - pool_pre_ping avoids stale connections
    # - pool_recycle helps with network timeouts
    return create_engine(
        DATABASE_URL,
        echo=_env_bool("SQLALCHEMY_ECHO", False),
        pool_pre_ping=True,
        pool_recycle=_env_int("SQLALCHEMY_POOL_RECYCLE", 1800),
        pool_size=_env_int("SQLALCHEMY_POOL_SIZE", 5),
        max_overflow=_env_int("SQLALCHEMY_MAX_OVERFLOW", 10),
    )


# Backwards-compatible exports (other modules import these symbols)
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()