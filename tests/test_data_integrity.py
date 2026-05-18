"""Data and artifact integrity tests for HRO-PS AI.

These tests validate:
- clean_data(AutoRecovered).csv row count and schema
- Forecast output CSVs have correct horizon dimensions
- Required model artifact files exist in artifacts/models_72h/
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_DATA_PATH = PROJECT_ROOT / "clean_data(AutoRecovered).csv"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
MODELS_72H_DIR = ARTIFACTS_DIR / "models_72h"
FORECAST_OUTPUTS_DIR = ARTIFACTS_DIR / "forecast_outputs"

OVERALL_FORECAST_PATH = FORECAST_OUTPUTS_DIR / "ops72h_overall_forecast.csv"
DEPARTMENT_FORECAST_PATH = FORECAST_OUTPUTS_DIR / "ops72h_department_forecast.csv"

EXPECTED_ROW_COUNT = 17520
REQUIRED_COLUMNS = {"datetime", "patients", "hour", "day_of_week", "month"}
NAN_THRESHOLD = 0.05  # max 5% NaN allowed in key columns

EXPECTED_DEPARTMENTS = {"ER", "ICU", "General Ward", "Surgery", "Radiology"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clean_df() -> pd.DataFrame:
    assert CLEAN_DATA_PATH.exists(), (
        f"clean_data(AutoRecovered).csv not found at {CLEAN_DATA_PATH}"
    )
    return pd.read_csv(CLEAN_DATA_PATH)


@pytest.fixture(scope="module")
def overall_forecast_df() -> pd.DataFrame:
    if not OVERALL_FORECAST_PATH.exists():
        pytest.fail(f"Critical: overall forecast artifact missing at {OVERALL_FORECAST_PATH}. Run generate_ops72h_outputs.py.")
    return pd.read_csv(OVERALL_FORECAST_PATH)


@pytest.fixture(scope="module")
def department_forecast_df() -> pd.DataFrame:
    if not DEPARTMENT_FORECAST_PATH.exists():
        pytest.fail(f"Critical: department forecast artifact missing at {DEPARTMENT_FORECAST_PATH}. Run generate_ops72h_outputs.py.")
    return pd.read_csv(DEPARTMENT_FORECAST_PATH)


# ---------------------------------------------------------------------------
# clean_data(AutoRecovered).csv — row count
# ---------------------------------------------------------------------------

class TestCleanDataRowCount:
    def test_row_count_exactly_17520(self, clean_df):
        """2 years of hourly data = 2 * 365 * 24 = 17520 rows."""
        assert len(clean_df) == EXPECTED_ROW_COUNT, (
            f"Expected {EXPECTED_ROW_COUNT} rows, got {len(clean_df)}"
        )


# ---------------------------------------------------------------------------
# clean_data(AutoRecovered).csv — required columns
# ---------------------------------------------------------------------------

class TestCleanDataSchema:
    def test_required_columns_present(self, clean_df):
        missing = REQUIRED_COLUMNS - set(clean_df.columns)
        assert not missing, f"Required columns missing from clean_data: {missing}"

    def test_datetime_column_present(self, clean_df):
        assert "datetime" in clean_df.columns

    def test_patients_column_present(self, clean_df):
        assert "patients" in clean_df.columns

    def test_hour_column_present(self, clean_df):
        assert "hour" in clean_df.columns

    def test_day_of_week_column_present(self, clean_df):
        assert "day_of_week" in clean_df.columns

    def test_month_column_present(self, clean_df):
        assert "month" in clean_df.columns


# ---------------------------------------------------------------------------
# clean_data(AutoRecovered).csv — value validity
# ---------------------------------------------------------------------------

class TestCleanDataValues:
    def test_patients_all_non_negative(self, clean_df):
        negative_count = (pd.to_numeric(clean_df["patients"], errors="coerce") < 0).sum()
        assert negative_count == 0, (
            f"Found {negative_count} rows with negative 'patients' values"
        )

    def test_patients_no_extreme_negatives(self, clean_df):
        """Belt-and-suspenders: explicitly assert all numeric patients >= 0."""
        vals = pd.to_numeric(clean_df["patients"], errors="coerce").dropna()
        assert (vals >= 0).all(), "All patient counts must be >= 0"

    def test_nan_fraction_datetime_within_threshold(self, clean_df):
        nan_frac = clean_df["datetime"].isna().mean()
        assert nan_frac <= NAN_THRESHOLD, (
            f"'datetime' has {nan_frac:.1%} NaN — exceeds {NAN_THRESHOLD:.0%} threshold"
        )

    def test_nan_fraction_patients_within_threshold(self, clean_df):
        nan_frac = pd.to_numeric(clean_df["patients"], errors="coerce").isna().mean()
        assert nan_frac <= NAN_THRESHOLD, (
            f"'patients' has {nan_frac:.1%} NaN — exceeds {NAN_THRESHOLD:.0%} threshold"
        )

    def test_nan_fraction_hour_within_threshold(self, clean_df):
        nan_frac = pd.to_numeric(clean_df["hour"], errors="coerce").isna().mean()
        assert nan_frac <= NAN_THRESHOLD, (
            f"'hour' has {nan_frac:.1%} NaN — exceeds {NAN_THRESHOLD:.0%} threshold"
        )

    def test_nan_fraction_day_of_week_within_threshold(self, clean_df):
        nan_frac = pd.to_numeric(clean_df["day_of_week"], errors="coerce").isna().mean()
        assert nan_frac <= NAN_THRESHOLD, (
            f"'day_of_week' has {nan_frac:.1%} NaN — exceeds {NAN_THRESHOLD:.0%} threshold"
        )

    def test_nan_fraction_month_within_threshold(self, clean_df):
        nan_frac = pd.to_numeric(clean_df["month"], errors="coerce").isna().mean()
        assert nan_frac <= NAN_THRESHOLD, (
            f"'month' has {nan_frac:.1%} NaN — exceeds {NAN_THRESHOLD:.0%} threshold"
        )


# ---------------------------------------------------------------------------
# Overall 72h forecast — row count
# ---------------------------------------------------------------------------

class TestOverallForecast:
    def test_overall_forecast_has_exactly_72_rows(self, overall_forecast_df):
        assert len(overall_forecast_df) == 72, (
            f"Overall 72h forecast must have exactly 72 rows, got {len(overall_forecast_df)}"
        )

    def test_overall_forecast_has_datetime_column(self, overall_forecast_df):
        assert "datetime" in overall_forecast_df.columns

    def test_overall_forecast_has_hybrid_pred_column(self, overall_forecast_df):
        assert "hybrid_pred" in overall_forecast_df.columns

    def test_overall_forecast_no_negative_predictions(self, overall_forecast_df):
        vals = pd.to_numeric(overall_forecast_df["hybrid_pred"], errors="coerce")
        assert (vals >= 0).all(), "Overall forecast must have no negative predictions"


# ---------------------------------------------------------------------------
# Department 72h forecast — row count (72 × 5 departments = 360)
# ---------------------------------------------------------------------------

class TestDepartmentForecast:
    def test_department_forecast_has_exactly_360_rows(self, department_forecast_df):
        assert len(department_forecast_df) == 360, (
            f"Department forecast must have 360 rows (72h × 5 depts), "
            f"got {len(department_forecast_df)}"
        )

    def test_department_forecast_has_department_column(self, department_forecast_df):
        assert "department" in department_forecast_df.columns

    def test_department_forecast_has_datetime_column(self, department_forecast_df):
        assert "datetime" in department_forecast_df.columns

    def test_department_forecast_has_hybrid_pred_column(self, department_forecast_df):
        assert "hybrid_pred" in department_forecast_df.columns

    def test_all_five_departments_present(self, department_forecast_df):
        actual_depts = set(department_forecast_df["department"].unique())
        missing_depts = EXPECTED_DEPARTMENTS - actual_depts
        assert not missing_depts, (
            f"Missing departments in forecast: {missing_depts}"
        )

    def test_each_department_has_72_rows(self, department_forecast_df):
        counts = department_forecast_df.groupby("department")["datetime"].count()
        bad = {dept: int(count) for dept, count in counts.items() if count != 72}
        assert not bad, (
            f"Departments with != 72 forecast rows: {bad}"
        )

    def test_department_forecast_no_negative_predictions(self, department_forecast_df):
        vals = pd.to_numeric(department_forecast_df["hybrid_pred"], errors="coerce")
        assert (vals >= 0).all(), "Department forecast must have no negative predictions"


# ---------------------------------------------------------------------------
# Model artifact files existence
# ---------------------------------------------------------------------------

class TestCleanDataTemporalIntegrity:
    def test_no_duplicate_timestamps(self, clean_df):
        dup_count = clean_df["datetime"].duplicated().sum()
        assert dup_count == 0, (
            f"clean_data(AutoRecovered).csv has {dup_count} duplicate datetime values"
        )

    def test_datetime_parseable(self, clean_df):
        parsed = pd.to_datetime(clean_df["datetime"], errors="coerce")
        bad_count = parsed.isna().sum()
        assert bad_count == 0, f"{bad_count} datetime values could not be parsed"

    def test_date_range_starts_2024(self, clean_df):
        parsed = pd.to_datetime(clean_df["datetime"], errors="coerce")
        assert parsed.min().year == 2024, (
            f"Expected start year 2024, got {parsed.min().year}"
        )

    def test_date_range_ends_2025(self, clean_df):
        parsed = pd.to_datetime(clean_df["datetime"], errors="coerce")
        assert parsed.max().year == 2025, (
            f"Expected end year 2025, got {parsed.max().year}"
        )


# ---------------------------------------------------------------------------
# what_if_scenarios.csv integrity
# ---------------------------------------------------------------------------

WHAT_IF_PATH = PROJECT_ROOT / "data" / "updated_exports" / "what_if_scenarios.csv"
WHAT_IF_MIN_ROWS = 40
WHAT_IF_EXPECTED_COLS = 21


class TestWhatIfScenarios:
    def test_what_if_csv_exists(self):
        assert WHAT_IF_PATH.exists(), (
            f"what_if_scenarios.csv not found at {WHAT_IF_PATH}"
        )

    def test_what_if_csv_min_rows(self):
        if not WHAT_IF_PATH.exists():
            pytest.skip("what_if_scenarios.csv missing — see test_what_if_csv_exists")
        df = pd.read_csv(WHAT_IF_PATH)
        assert len(df) >= WHAT_IF_MIN_ROWS, (
            f"what_if_scenarios.csv has {len(df)} rows, expected >= {WHAT_IF_MIN_ROWS}"
        )

    def test_what_if_csv_column_count(self):
        if not WHAT_IF_PATH.exists():
            pytest.skip("what_if_scenarios.csv missing")
        df = pd.read_csv(WHAT_IF_PATH)
        assert len(df.columns) == WHAT_IF_EXPECTED_COLS, (
            f"what_if_scenarios.csv has {len(df.columns)} columns, expected {WHAT_IF_EXPECTED_COLS}"
        )

    def test_what_if_scenario_id_present(self):
        if not WHAT_IF_PATH.exists():
            pytest.skip("what_if_scenarios.csv missing")
        df = pd.read_csv(WHAT_IF_PATH)
        assert "scenario_id" in df.columns, "what_if_scenarios.csv must have a 'scenario_id' column"

    def test_what_if_no_duplicate_scenario_ids(self):
        if not WHAT_IF_PATH.exists():
            pytest.skip("what_if_scenarios.csv missing")
        df = pd.read_csv(WHAT_IF_PATH)
        if "scenario_id" not in df.columns:
            pytest.skip("scenario_id column not present")
        dup_count = df["scenario_id"].duplicated().sum()
        assert dup_count == 0, (
            f"what_if_scenarios.csv has {dup_count} duplicate scenario_id values"
        )


# ---------------------------------------------------------------------------
# users.csv integrity
# ---------------------------------------------------------------------------

USERS_CSV_PATH = PROJECT_ROOT / "users.csv"
USERS_MIN_COUNT = 25


class TestUsersCSV:
    def test_users_csv_exists(self):
        assert USERS_CSV_PATH.exists(), (
            f"users.csv not found at {USERS_CSV_PATH}"
        )

    def test_users_csv_min_count(self):
        if not USERS_CSV_PATH.exists():
            pytest.skip("users.csv missing")
        df = pd.read_csv(USERS_CSV_PATH)
        assert len(df) >= USERS_MIN_COUNT, (
            f"users.csv has {len(df)} users, expected >= {USERS_MIN_COUNT}"
        )

    def test_users_no_duplicate_usernames(self):
        if not USERS_CSV_PATH.exists():
            pytest.skip("users.csv missing")
        df = pd.read_csv(USERS_CSV_PATH)
        if "username" not in df.columns:
            pytest.skip("username column not present in users.csv")
        dup_count = df["username"].duplicated().sum()
        assert dup_count == 0, (
            f"users.csv has {dup_count} duplicate username values"
        )

    def test_users_roles_are_valid(self):
        if not USERS_CSV_PATH.exists():
            pytest.skip("users.csv missing")
        df = pd.read_csv(USERS_CSV_PATH)
        if "role" not in df.columns:
            pytest.skip("role column not present in users.csv")
        valid_roles = {"admin", "doctor", "nurse"}
        invalid = set(df["role"].dropna().unique()) - valid_roles
        assert not invalid, f"users.csv has invalid role values: {invalid}"

    def test_demo_users_present(self):
        if not USERS_CSV_PATH.exists():
            pytest.skip("users.csv missing")
        df = pd.read_csv(USERS_CSV_PATH)
        if "username" not in df.columns:
            pytest.skip("username column not present in users.csv")
        required = {"admin1", "doctor1", "nurse1"}
        present = set(df["username"].astype(str))
        missing = required - present
        assert not missing, (
            f"Demo accounts missing from users.csv: {missing}"
        )


class TestModelArtifactFiles:
    def test_models_72h_directory_exists(self):
        assert MODELS_72H_DIR.exists(), (
            f"artifacts/models_72h directory not found at {MODELS_72H_DIR}"
        )

    def test_lstm_keras_file_exists(self):
        lstm_path = MODELS_72H_DIR / "lstm_ops72h.keras"
        assert lstm_path.exists(), (
            f"LSTM model artifact missing: {lstm_path}. "
            "Run train_lstm_ops72h.py to generate it."
        )

    def test_arimax_pkl_file_exists(self):
        arimax_path = MODELS_72H_DIR / "arimax_ops72h.pkl"
        assert arimax_path.exists(), (
            f"ARIMAX model artifact missing: {arimax_path}. "
            "Run train_arimax_ops72h.py to generate it."
        )

    def test_lstm_keras_file_not_empty(self):
        lstm_path = MODELS_72H_DIR / "lstm_ops72h.keras"
        if not lstm_path.exists():
            pytest.skip("lstm_ops72h.keras not found — skipping size check")
        assert lstm_path.stat().st_size > 0, "lstm_ops72h.keras is an empty file"

    def test_arimax_pkl_file_not_empty(self):
        arimax_path = MODELS_72H_DIR / "arimax_ops72h.pkl"
        if not arimax_path.exists():
            pytest.skip("arimax_ops72h.pkl not found — skipping size check")
        assert arimax_path.stat().st_size > 0, "arimax_ops72h.pkl is an empty file"
