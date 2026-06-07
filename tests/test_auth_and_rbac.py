"""Auth, RBAC, and multi-tenant isolation regression tests.

Exercises the auth module (auth.py) and the require_role factory (api.py)
directly — no running server required. Proves:
- Password hashing round-trips correctly.
- JWT creation / decode round-trips correctly (create_token / decode_token).
- A token for tenant A carries tenant_id=A, not B.
- require_role raises 403 for wrong role and 401 for missing / invalid token.
- An expired token raises ValueError on decode.
"""

import time
from datetime import datetime, timedelta

import pytest
from jose import jwt

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    SECRET_KEY,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        assert hash_password("secret123") != "secret123"

    def test_correct_password_verifies(self):
        h = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", h) is True

    def test_wrong_password_rejected(self):
        h = hash_password("correct-horse-battery")
        assert verify_password("wrong-password", h) is False

    def test_empty_password_rejected(self):
        h = hash_password("correct-horse-battery")
        assert verify_password("", h) is False

    def test_none_hash_returns_false(self):
        assert verify_password("anything", None) is False
        assert verify_password("anything", "") is False

    def test_hash_is_bcrypt_format(self):
        h = hash_password("test")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_same_password_different_salt_each_call(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True


# ---------------------------------------------------------------------------
# JWT round-trip
# ---------------------------------------------------------------------------

class TestJWTRoundTrip:
    def _make_token(self, username="u", role="admin", tenant_id=1, **extra):
        data = {"sub": username, "username": username, "role": role, "tenant_id": tenant_id}
        data.update(extra)
        return create_token(data)

    def test_token_decodes_correctly(self):
        token = self._make_token(username="alice")
        payload = decode_token(token)
        assert payload["username"] == "alice"

    def test_role_survives_round_trip(self):
        token = self._make_token(role="nurse")
        assert decode_token(token)["role"] == "nurse"

    def test_tenant_id_survives_round_trip(self):
        token = self._make_token(tenant_id=42)
        assert int(decode_token(token)["tenant_id"]) == 42

    def test_tampered_token_raises(self):
        token = self._make_token()
        parts = token.split(".")
        parts[-1] = parts[-1][:-4] + "XXXX"
        with pytest.raises(Exception):
            decode_token(".".join(parts))

    def test_garbage_token_raises(self):
        for bad in ("not.a.jwt", "", "garbage"):
            with pytest.raises(Exception):
                decode_token(bad)

    def test_expired_token_raises(self):
        data = {"sub": "u", "username": "u", "role": "admin", "tenant_id": 1}
        expired = create_token(data, expires_minutes=-1)
        time.sleep(0.05)
        with pytest.raises(Exception):
            decode_token(expired)


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_tokens_carry_distinct_tenants(self):
        tok_a = create_token({"sub": "a", "username": "a", "role": "admin", "tenant_id": 10})
        tok_b = create_token({"sub": "b", "username": "b", "role": "admin", "tenant_id": 20})
        assert int(decode_token(tok_a)["tenant_id"]) == 10
        assert int(decode_token(tok_b)["tenant_id"]) == 20

    def test_token_without_tenant_id_has_no_claim(self):
        tok = create_token({"sub": "legacy", "username": "legacy", "role": "admin"})
        payload = decode_token(tok)
        assert payload.get("tenant_id") is None


# ---------------------------------------------------------------------------
# require_role factory (tested via direct dependency invocation)
# ---------------------------------------------------------------------------

class TestRequireRole:
    """Drive the get_token_payload + require_role pipeline without an HTTP server.

    require_role returns a plain closure; FastAPI normally injects the payload
    via Depends. We replicate that: call get_token_payload() ourselves, then
    pass the result as the positional argument to the closure.
    """

    def _make_bearer(self, role="admin", tenant_id=1):
        tok = create_token({"sub": "u", "username": "u", "role": role, "tenant_id": tenant_id})
        return f"Bearer {tok}"

    def _get_payload(self, bearer):
        from api import get_token_payload
        return get_token_payload(authorization=bearer)

    def test_admin_passes_admin_gate(self):
        from api import require_role
        gate = require_role(["admin"])
        payload = self._get_payload(self._make_bearer(role="admin"))
        result = gate(payload=payload)
        assert result["role"] == "admin"

    def test_nurse_blocked_by_admin_gate(self):
        from fastapi import HTTPException
        from api import require_role
        gate = require_role(["admin"])
        payload = self._get_payload(self._make_bearer(role="nurse"))
        with pytest.raises(HTTPException) as exc:
            gate(payload=payload)
        assert exc.value.status_code == 403

    def test_doctor_passes_staff_or_admin_gate(self):
        from api import require_role
        gate = require_role(["admin", "doctor", "nurse"])
        payload = self._get_payload(self._make_bearer(role="doctor"))
        result = gate(payload=payload)
        assert result["role"] == "doctor"

    def test_missing_auth_header_raises_401(self):
        from fastapi import HTTPException
        from api import get_token_payload
        with pytest.raises(HTTPException) as exc:
            get_token_payload(authorization=None)
        assert exc.value.status_code == 401

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from api import get_token_payload
        with pytest.raises(HTTPException) as exc:
            get_token_payload(authorization="Bearer invalid.garbage.here")
        assert exc.value.status_code == 401
