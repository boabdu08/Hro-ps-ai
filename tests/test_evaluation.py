"""Tests for evaluation_service.build_metrics_dataframe.

These tests validate the DataFrame structure and numerical credibility
of the evaluation metrics produced from the canonical artifacts.
"""

import pytest
import pandas as pd

from evaluation_service import build_metrics_dataframe


EXPECTED_MODELS = {"LSTM", "ARIMAX", "Hybrid"}


def _get_df() -> pd.DataFrame:
    return build_metrics_dataframe(split="test")


class TestDataFrameSchema:
    def test_returns_dataframe(self):
        df = _get_df()
        assert isinstance(df, pd.DataFrame), "build_metrics_dataframe must return a DataFrame"

    def test_not_empty(self):
        df = _get_df()
        assert not df.empty, "Metrics DataFrame must not be empty"

    def test_has_model_column(self):
        df = _get_df()
        assert "Model" in df.columns, "DataFrame must have a 'Model' column"

    def test_has_mae_column(self):
        df = _get_df()
        assert "MAE" in df.columns, "DataFrame must have a 'MAE' column"

    def test_has_rmse_column(self):
        df = _get_df()
        assert "RMSE" in df.columns, "DataFrame must have a 'RMSE' column"

    def test_has_mape_column(self):
        df = _get_df()
        assert "MAPE" in df.columns, "DataFrame must have a 'MAPE' column"

    def test_no_extra_required_columns_missing(self):
        df = _get_df()
        required = {"Model", "MAE", "RMSE", "MAPE"}
        missing = required - set(df.columns)
        assert not missing, f"Missing required columns: {missing}"


class TestModelPresence:
    def test_lstm_present(self):
        df = _get_df()
        assert "LSTM" in df["Model"].values, "LSTM must be present in metrics"

    def test_arimax_present(self):
        df = _get_df()
        assert "ARIMAX" in df["Model"].values, "ARIMAX must be present in metrics"

    def test_hybrid_present(self):
        df = _get_df()
        assert "Hybrid" in df["Model"].values, "Hybrid must be present in metrics"

    def test_three_model_rows(self):
        df = _get_df()
        assert len(df) >= 3, f"Expected at least 3 model rows, got {len(df)}"


class TestMAEValues:
    def _mae(self, model: str) -> float:
        df = _get_df()
        row = df[df["Model"] == model]
        assert not row.empty, f"Model '{model}' not found in metrics"
        return float(row.iloc[0]["MAE"])

    def test_lstm_mae_positive(self):
        assert self._mae("LSTM") > 0.0, "LSTM MAE must be a positive float"

    def test_arimax_mae_positive(self):
        assert self._mae("ARIMAX") > 0.0, "ARIMAX MAE must be a positive float"

    def test_hybrid_mae_positive(self):
        assert self._mae("Hybrid") > 0.0, "Hybrid MAE must be a positive float"

    def test_all_mae_are_floats(self):
        df = _get_df()
        for _, row in df.iterrows():
            assert isinstance(float(row["MAE"]), float), (
                f"MAE for {row['Model']} is not a float: {row['MAE']}"
            )

    def test_hybrid_mae_less_than_lstm_mae(self):
        """Hybrid is expected to be the best model (lowest MAE)."""
        hybrid_mae = self._mae("Hybrid")
        lstm_mae = self._mae("LSTM")
        assert hybrid_mae < lstm_mae, (
            f"Expected Hybrid MAE ({hybrid_mae:.4f}) < LSTM MAE ({lstm_mae:.4f}). "
            "Hybrid should outperform standalone LSTM."
        )


class TestRMSEValues:
    def test_all_rmse_positive(self):
        df = _get_df()
        for _, row in df.iterrows():
            assert float(row["RMSE"]) > 0.0, f"RMSE for {row['Model']} must be positive"

    def test_rmse_greater_than_or_equal_mae(self):
        """RMSE >= MAE is a mathematical property."""
        df = _get_df()
        for _, row in df.iterrows():
            mae = float(row["MAE"])
            rmse = float(row["RMSE"])
            assert rmse >= mae - 1e-6, (
                f"RMSE ({rmse:.4f}) must be >= MAE ({mae:.4f}) for model {row['Model']}"
            )


class TestMAPEValues:
    def test_all_mape_non_negative(self):
        df = _get_df()
        for _, row in df.iterrows():
            assert float(row["MAPE"]) >= 0.0, f"MAPE for {row['Model']} must be non-negative"

    def test_all_mape_below_100_percent(self):
        """MAPE > 100% would indicate catastrophic model failure."""
        df = _get_df()
        for _, row in df.iterrows():
            mape = float(row["MAPE"])
            assert mape < 100.0, (
                f"MAPE for {row['Model']} is {mape:.2f}%, which exceeds 100% — check artifact generation."
            )


class TestValidationSplit:
    def test_validation_split_returns_dataframe(self):
        df = build_metrics_dataframe(split="validation")
        # Validation split may return empty DataFrame if val artifacts are missing;
        # either is acceptable — we just ensure it does not raise.
        assert isinstance(df, pd.DataFrame)
