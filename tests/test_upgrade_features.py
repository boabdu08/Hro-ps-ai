"""Tests for the upgrade-pass features' non-UI glue:
scenario player cache function, model-health payload, guided-demo content,
and 3.11-syntax safety of all new/touched modules."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("APP_ENV", "test")


class TestScenarioPlayerGlue:
    def test_cached_scenario_run_shape(self):
        from dashboard_sections import _cached_scenario_run

        # .func bypasses the streamlit cache wrapper outside a session.
        fn = getattr(_cached_scenario_run, "func", None) or getattr(
            _cached_scenario_run, "__wrapped__", _cached_scenario_run
        )
        r = fn("surge", "demo-hospital")
        assert len(r["demand"]) == 72
        assert len(r["census"]) == 72
        assert r["beds"] == 293
        assert r["peak_demand"] > 0
        assert "beds_needed_total" in r["summary"]

    def test_small_clinic_overflows(self):
        from dashboard_sections import _cached_scenario_run

        fn = getattr(_cached_scenario_run, "func", None) or getattr(
            _cached_scenario_run, "__wrapped__", _cached_scenario_run
        )
        r = fn("baseline", "small-clinic")
        assert r["capacity_exceeded"] is True


class TestModelHealthPayload:
    def test_payload_from_real_artifacts(self):
        from dashboard_sections import _model_health_payload

        fn = getattr(_model_health_payload, "func", None) or getattr(
            _model_health_payload, "__wrapped__", _model_health_payload
        )
        health = fn()
        assert health is not None, "artifacts missing for model health"
        assert health["psi_status"] in {"stable", "moderate", "major"}
        assert health["rolling_mae"] is not None and health["rolling_mae"] > 0
        # Rolling MAE comes from the same outputs as the canonical 8.31 — the
        # last-72h window may differ from the full-test mean but must be sane.
        assert 0 < health["rolling_mae"] < 40


class TestGuidedDemoContent:
    def test_seven_steps_present(self):
        from dashboard import _DEMO_SCRIPT_STEPS

        assert len(_DEMO_SCRIPT_STEPS) == 7
        text = " ".join(t + " " + p for t, p in _DEMO_SCRIPT_STEPS)
        # Honest-numbers check: the script cites only canonical claims.
        assert "9.58" in text and "0.80" in text
        assert "10.8%" not in text  # the retired fabricated claim must not return


class TestPython311Syntax:
    """Space runtime is 3.11; local dev is 3.13. Nested same-quote f-strings &
    friends must not creep in. Runs only when a 3.11 interpreter exists."""

    PY311 = Path(r"C:\Users\Ab005\AppData\Local\Programs\Python\Python311\python.exe")
    MODULES = [
        "app.py", "dashboard.py", "dashboard_sections.py", "home_section.py",
        "ops_insights.py", "api.py", "api_client.py", "db_migrations.py",
        "patient_flow_sim.py", "production_scenarios.py", "drift_detection.py",
    ]

    @pytest.mark.skipif(not PY311.exists(), reason="no local Python 3.11")
    def test_runtime_modules_compile_on_311(self):
        out = subprocess.run(
            [str(self.PY311), "-m", "compileall", "-q", *self.MODULES],
            capture_output=True, text=True, timeout=300,
        )
        assert out.returncode == 0, (out.stderr or out.stdout)[-1500:]
