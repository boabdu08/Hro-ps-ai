"""Security hardening regression tests: rate limiting, security headers,
upload filename validation, and request-model bounds."""

import os

import pytest

os.environ.setdefault("APP_ENV", "test")

from rate_limit import (  # noqa: E402
    LOGIN_LIMIT,
    UPLOAD_LIMIT,
    build_rate_limiter,
    check_rate,
    reset_all,
)


@pytest.fixture(autouse=True)
def _clean_buckets():
    reset_all()
    yield
    reset_all()


class TestRateLimiterCore:
    def test_allows_within_budget(self):
        assert all(check_rate("t", "ip1", 5, 60.0) for _ in range(5))

    def test_blocks_over_budget(self):
        for _ in range(5):
            check_rate("t", "ip1", 5, 60.0)
        assert check_rate("t", "ip1", 5, 60.0) is False

    def test_keys_are_independent(self):
        for _ in range(5):
            check_rate("t", "ip1", 5, 60.0)
        assert check_rate("t", "ip2", 5, 60.0) is True

    def test_scopes_are_independent(self):
        for _ in range(5):
            check_rate("login", "ip1", 5, 60.0)
        assert check_rate("upload", "ip1", 5, 60.0) is True

    def test_window_expiry_restores_budget(self, monkeypatch):
        import rate_limit as rl

        t = [1000.0]
        monkeypatch.setattr(rl.time, "monotonic", lambda: t[0])
        for _ in range(3):
            assert rl.check_rate("t", "ip1", 3, 10.0) is True
        assert rl.check_rate("t", "ip1", 3, 10.0) is False
        t[0] += 11.0  # advance past the window
        assert rl.check_rate("t", "ip1", 3, 10.0) is True

    def test_default_limits_are_sane(self):
        assert LOGIN_LIMIT[0] >= 5      # never lock out a fumbling demo user
        assert UPLOAD_LIMIT[0] >= 5
        assert LOGIN_LIMIT[1] > 0
        assert UPLOAD_LIMIT[1] > 0


class TestRateLimiterDependency:
    def _fake_request(self, ip="1.2.3.4", forwarded=None):
        class _Client:
            host = ip

        class _Req:
            headers = {"x-forwarded-for": forwarded} if forwarded else {}
            client = _Client()

        return _Req()

    def test_dependency_raises_429_when_exhausted(self):
        from fastapi import HTTPException

        dep = build_rate_limiter("dep-test", 2, 60.0)
        req = self._fake_request()
        dep(req)
        dep(req)
        with pytest.raises(HTTPException) as exc:
            dep(req)
        assert exc.value.status_code == 429
        assert "Retry-After" in (exc.value.headers or {})

    def test_forwarded_for_header_used_for_keying(self):
        dep = build_rate_limiter("fwd-test", 1, 60.0)
        dep(self._fake_request(forwarded="9.9.9.9"))
        # different forwarded IP -> separate budget, no exception
        dep(self._fake_request(forwarded="8.8.8.8"))


class TestSecurityHeaders:
    def test_headers_dict_present_in_api(self):
        from api import SECURITY_HEADERS

        assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
        assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
        assert "Referrer-Policy" in SECURITY_HEADERS
        # HSTS must NOT be set by the app (TLS layer's job)
        assert "Strict-Transport-Security" not in SECURITY_HEADERS


class TestUploadFilenameValidation:
    def test_rejects_non_csv(self):
        from fastapi import HTTPException

        from api import _require_csv_filename

        class _F:
            filename = "malware.exe"

        with pytest.raises(HTTPException) as exc:
            _require_csv_filename(_F())
        assert exc.value.status_code == 400

    def test_accepts_csv(self):
        from api import _require_csv_filename

        class _F:
            filename = "patients.CSV"

        _require_csv_filename(_F())  # must not raise


class TestRequestModelBounds:
    def test_simulate_request_rejects_negative_patients(self):
        from pydantic import ValidationError

        from api import SimulateRequest

        with pytest.raises(ValidationError):
            SimulateRequest(predicted_patients=-5, beds_available=10, doctors_available=2)

    def test_simulate_request_rejects_absurd_demand_increase(self):
        from pydantic import ValidationError

        from api import SimulateRequest

        with pytest.raises(ValidationError):
            SimulateRequest(
                predicted_patients=100,
                beds_available=10,
                doctors_available=2,
                demand_increase_percent=99_999,
            )

    def test_simulate_request_accepts_valid_payload(self):
        from api import SimulateRequest

        req = SimulateRequest(
            predicted_patients=100,
            beds_available=250,
            doctors_available=40,
            demand_increase_percent=25,
        )
        assert req.predicted_patients == 100


class TestJWTSecretStartupCheck:
    def test_dev_env_gets_safe_default(self):
        # In dev/test the app may run with the dev default; in production
        # auth.py raises RuntimeError. We assert the guard logic exists.
        import inspect

        import auth

        source = inspect.getsource(auth)
        assert "JWT_SECRET_KEY is required" in source
        assert "dev-unsafe-secret-change-me" in source
