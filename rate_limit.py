"""In-process sliding-window rate limiter for sensitive endpoints.

Purpose:     Throttle brute-force-able endpoints (/auth/login) and heavy
             endpoints (/upload/*) without adding an external dependency or a
             Redis instance — appropriate for the single-instance demo/Space
             deployment this project targets.
Source:      FastAPI dependencies created via build_rate_limiter(); keyed by
             client IP + endpoint scope.
Destination: Raises HTTP 429 when the per-window budget is exhausted.

Limitations (documented, acceptable for single-instance deployments):
* State is per-process — multiple workers/replicas each get their own budget.
  For multi-instance production use a shared store (Redis) instead.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from fastapi import HTTPException, Request

_LOCK = threading.Lock()
_BUCKETS: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

# Defaults chosen to never bother a human demo user while still stopping
# scripted brute force: 10 login attempts / 60 s, 20 uploads / 300 s per IP.
LOGIN_LIMIT = (10, 60.0)
UPLOAD_LIMIT = (20, 300.0)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def check_rate(scope: str, key: str, max_requests: int, window_seconds: float) -> bool:
    """Record one hit and return True when within budget, False when exceeded."""

    now = time.monotonic()
    bucket_key = (scope, key)
    with _LOCK:
        bucket = _BUCKETS[bucket_key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        return True


def reset_all() -> None:
    """Clear all buckets (test helper)."""

    with _LOCK:
        _BUCKETS.clear()


def build_rate_limiter(scope: str, max_requests: int, window_seconds: float) -> Callable:
    """Build a FastAPI dependency enforcing the limit per client IP."""

    def _dep(request: Request) -> None:
        ip = _client_ip(request)
        if not check_rate(scope, ip, max_requests, window_seconds):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {scope}. Try again later.",
                headers={"Retry-After": str(int(window_seconds))},
            )

    return _dep


login_rate_limiter = build_rate_limiter("login", *LOGIN_LIMIT)
upload_rate_limiter = build_rate_limiter("upload", *UPLOAD_LIMIT)
