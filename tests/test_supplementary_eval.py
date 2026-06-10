"""Supplementary evaluation artifact tests.

Verifies the additive evaluation artifacts exist, are well-formed, and —
critically — that the reconstructed hybrid test metrics still match the
frozen canonical numbers (MAE 8.31 / RMSE 10.22 / MAPE 6.07).
"""

import json
from pathlib import Path

import pytest

SUPP_DIR = Path("artifacts/metrics_72h/supplementary")
SUPP_JSON = SUPP_DIR / "supplementary_evaluation.json"
LOSS_CSV = SUPP_DIR / "lstm_loss_curves.csv"


@pytest.fixture(scope="module")
def payload():
    if not SUPP_JSON.exists():
        pytest.fail(f"Missing supplementary artifact: {SUPP_JSON} — run generate_supplementary_eval.py")
    return json.loads(SUPP_JSON.read_text(encoding="utf-8"))


class TestCanonicalConsistency:
    def test_hybrid_metrics_match_canonical(self, payload):
        m = payload["hybrid_test_metrics_check"]
        assert m["MAE"] == pytest.approx(8.31, abs=0.01)
        assert m["RMSE"] == pytest.approx(10.22, abs=0.01)
        assert m["MAPE"] == pytest.approx(6.07, abs=0.01)

    def test_artifacts_declare_no_retraining(self, payload):
        assert "no retraining" in payload["generated_from"]


class TestLossCurves:
    def test_loss_csv_exists_with_epochs(self):
        import pandas as pd

        df = pd.read_csv(LOSS_CSV)
        assert list(df.columns) == ["epoch", "loss", "val_loss"]
        assert len(df) >= 10

    def test_training_converged(self):
        import pandas as pd

        df = pd.read_csv(LOSS_CSV)
        # Final loss must be far below initial loss (model actually learned).
        assert df["loss"].iloc[-1] < df["loss"].iloc[0] * 0.5
        assert df["val_loss"].iloc[-1] < df["val_loss"].iloc[0]


class TestResidualDiagnostics:
    def test_required_fields_present(self, payload):
        diag = payload["residual_diagnostics"]
        for key in ("mean_residual", "std_residual", "lag1_autocorrelation",
                    "pct_within_2_rmse", "n"):
            assert key in diag

    def test_residual_sample_size_substantial(self, payload):
        assert payload["residual_diagnostics"]["n"] >= 2000

    def test_95pct_of_errors_within_2_rmse(self, payload):
        # Sanity: roughly Gaussian-ish tail behaviour.
        assert payload["residual_diagnostics"]["pct_within_2_rmse"] >= 90.0


class TestRollingOriginFolds:
    def test_six_folds_present(self, payload):
        folds = payload["rolling_origin_folds"]
        assert len(folds) == 6
        assert all(f["n_hours"] > 100 for f in folds)

    def test_fold_metrics_in_plausible_range(self, payload):
        for f in payload["rolling_origin_folds"]:
            assert 0 < f["MAE"] < 30, f
            assert f["RMSE"] >= f["MAE"], f


class TestPerDepartmentMetrics:
    def test_all_five_departments_scored(self, payload):
        depts = {d["department"] for d in payload["per_department_metrics"]}
        assert depts == {"ER", "ICU", "General Ward", "Surgery", "Radiology"}

    def test_department_shares_sum_to_one(self, payload):
        total = sum(d["share"] for d in payload["per_department_metrics"])
        assert total == pytest.approx(1.0, abs=0.01)

    def test_department_mae_positive_and_bounded(self, payload):
        for d in payload["per_department_metrics"]:
            assert 0 < d["MAE"] < 20, d


class TestUncertaintyBands:
    def test_band_structure(self, payload):
        bands = payload["uncertainty_bands"]
        assert bands["band_80"]["lower_offset"] < 0 < bands["band_80"]["upper_offset"]
        assert bands["band_95"]["lower_offset"] <= bands["band_80"]["lower_offset"]
        assert bands["band_95"]["upper_offset"] >= bands["band_80"]["upper_offset"]

    def test_band_method_is_empirical(self, payload):
        assert "empirical" in payload["uncertainty_bands"]["method"]
