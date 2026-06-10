"""Deployment readiness checks (Hugging Face Spaces / any PaaS).

Asserts that everything inference needs at runtime is committed and loadable
WITHOUT training: model artifacts, forecast outputs, entrypoints, and that the
Space bootstrap (app.py) is import-safe (no side effects on import).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REQUIRED_ARTIFACTS = [
    "artifacts/models_72h/lstm_ops72h.keras",
    "artifacts/models_72h/lstm_x_scaler.pkl",
    "artifacts/models_72h/lstm_y_scaler.pkl",
    "artifacts/models_72h/lstm_feature_config.json",
    "artifacts/models_72h/hybrid_config.json",
    "artifacts/forecast_outputs/ops72h_overall_forecast.csv",
    "artifacts/forecast_outputs/ops72h_department_forecast.csv",
    "artifacts/metrics_72h/ops72h_model_metrics.csv",
]

ENTRYPOINTS = ["app.py", "main.py", "dashboard.py", "requirements.txt", "README_HF_SPACE.md"]


class TestArtifactsPresent:
    @pytest.mark.parametrize("relpath", REQUIRED_ARTIFACTS)
    def test_required_artifact_exists(self, relpath):
        assert Path(relpath).exists(), f"Missing deployment artifact: {relpath}"

    @pytest.mark.parametrize("relpath", REQUIRED_ARTIFACTS)
    def test_required_artifact_git_tracked(self, relpath):
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relpath],
            capture_output=True, text=True,
        )
        assert out.returncode == 0, f"Artifact not committed to git: {relpath}"


class TestEntrypoints:
    @pytest.mark.parametrize("name", ENTRYPOINTS)
    def test_entrypoint_exists(self, name):
        assert Path(name).exists(), f"Missing deployment file: {name}"

    def test_app_import_is_side_effect_free(self):
        """`import app` must not start servers or train models."""

        code = (
            "import os; os.environ['APP_ENV']='test'; "
            "import app; "
            "import threading; "
            "names=[t.name for t in threading.enumerate()]; "
            "assert 'hro-ps-api' not in names, 'API thread started on import!'"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr

    def test_space_card_has_required_yaml(self):
        text = Path("README_HF_SPACE.md").read_text(encoding="utf-8")
        assert "sdk: streamlit" in text
        assert "app_file: app.py" in text

    def test_no_hardcoded_secrets_in_entrypoints(self):
        for name in ("app.py", "main.py", "auth.py"):
            text = Path(name).read_text(encoding="utf-8")
            # The only permitted literal is the documented dev fallback.
            assert "JWT_SECRET_KEY = \"" not in text.replace("'", '"'), name


class TestNoTrainingOnStartup:
    def test_inference_modules_never_import_training_scripts(self):
        for mod in ("forecast_inference.py", "forecast_inference_ops72h.py", "forecast_state.py"):
            text = Path(mod).read_text(encoding="utf-8")
            for trainer in ("train_lstm", "train_arimax", "build_hybrid", "model.fit("):
                assert trainer not in text, f"{mod} references training: {trainer}"
