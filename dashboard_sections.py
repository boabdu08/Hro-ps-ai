from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from feature_spec import FEATURE_COLUMNS as LOCAL_FEATURE_COLUMNS, SEQUENCE_LENGTH as LOCAL_SEQUENCE_LENGTH

from api_client import (
    explain_prediction,
    get_feature_config,
    get_patient_flow_history,
    get_latest_sequence,
    get_optimization,
    get_prediction,
    simulate,
)

from forecast_state import ForecastState, build_canonical_forecast_state


from evaluation_service import build_detailed_predictions_dataframe, build_metrics_dataframe
from forecast_runtime import generate_multistep_forecast
from ui_components import (
    alert_box,
    empty_state,
    fmt_int,
    fmt_mae_rmse,
    fmt_mape,
    fmt_patients,
    fmt_trend,
    fmt_weight,
    kpi_card,
    modern_table,
    page_header,
    scoped_key,
    section_header,
    status_badge,
)


OPS72H_OVERALL_FORECAST_PATH = Path("artifacts") / "forecast_outputs" / "ops72h_overall_forecast.csv"
OPS72H_DEPARTMENT_FORECAST_PATH = Path("artifacts") / "forecast_outputs" / "ops72h_department_forecast.csv"
OPS72H_MODEL_METRICS_PATH = Path("artifacts") / "metrics_72h" / "ops72h_model_metrics.csv"
OPS72H_TRAINING_SUMMARY_PATH = Path("artifacts") / "manifests" / "ops72h_training_summary.json"


COUNT_DISPLAY_HINTS = (
    "patient",
    "patients",
    "bed",
    "beds",
    "doctor",
    "doctors",
    "nurse",
    "nurses",
    "staff",
    "shift",
    "shortage",
    "gap",
    "required",
    "available",
    "forecast",
    "prediction",
    "predicted",
    "actual",
    "hybrid_pred",
    "lstm_pred",
    "arimax_pred",
)


def _display_number(value, decimals: int = 2, signed: bool = False) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        pattern = f"{{:{'+' if signed else ''}.{int(decimals)}f}}"
        return pattern.format(float(value))
    except Exception:
        return str(value)


def _round_display_dataframe(df: pd.DataFrame, *, metric_decimals: int = 2) -> pd.DataFrame:
    """Return a display-only rounded copy; never mutate raw artifacts/API data."""

    out = df.copy()
    for col in out.columns:
        low = str(col).lower()
        if pd.api.types.is_numeric_dtype(out[col]):
            if low in {"mae", "rmse"} or "score" in low or "impact" in low:
                out[col] = out[col].round(metric_decimals)
            elif "mape" in low:
                out[col] = out[col].round(2)
            elif "weight" in low or "multiplier" in low:
                out[col] = out[col].round(2)
            elif any(hint in low for hint in COUNT_DISPLAY_HINTS):
                out[col] = out[col].round(0).astype("Int64")
            else:
                out[col] = out[col].round(metric_decimals)
    return out


def _stable_tail_note(values, *, label: str, tail_hours: int = 12, threshold: float = 0.5) -> str | None:
    try:
        arr = np.array(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        if len(arr) < max(4, tail_hours):
            return None
        tail = arr[-tail_hours:]
        tail_range = float(np.nanmax(tail) - np.nanmin(tail))
        if tail_range <= threshold:
            return (
                f"{label} stabilizes in the final {tail_hours} hours (range ≈ {tail_range:.1f} patients). "
                "This reflects the saved forecast artifact converging to a stable baseline, not an inactive dashboard."
            )
    except Exception:
        return None
    return None


def _model_name(value) -> str:
    text = str(value or "").strip()
    return text.upper() if text.lower() in {"lstm", "arimax"} else text.title() if text else "-"


def _friendly_feature_label(feature: str) -> str:
    name = str(feature or "")
    direct = {
        "is_weekend": "Weekend effect",
        "trend_feature": "Recent trend",
        "holiday": "Holiday effect",
        "month": "Season/month effect",
        "day_of_week": "Day-of-week pattern",
        "hour_sin": "Time-of-day pattern",
        "hour_cos": "Time-of-day pattern",
    }
    if name in direct:
        return direct[name]
    if name.startswith("patients_roll_mean_"):
        return "Recent average patient load"
    if name.startswith("patients_lag_"):
        return "Previous patient load"
    if name.startswith("patients_diff_"):
        return "Recent change in patient load"
    if name.startswith("patients_roll_std_"):
        return "Recent volatility in patient load"
    return name.replace("_", " ").strip().title() or "Feature"


def _feature_meaning(feature: str, direction: str) -> str:
    label = _friendly_feature_label(feature).lower()
    if "patient load" in label:
        base = "Recent/previous patient volumes are influencing the next forecast."
    elif "weekend" in label:
        base = "Weekend calendar patterns are influencing demand."
    elif "holiday" in label:
        base = "Holiday effects are influencing expected arrivals."
    elif "time-of-day" in label:
        base = "Hourly arrival patterns are influencing expected demand."
    elif "trend" in label:
        base = "The recent direction of demand is influencing the forecast."
    else:
        base = "This model input is influencing the forecast."
    return f"{base} Direction: {direction.lower()}."


def _build_scenario_summary_report(scenario_df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if scenario_df.empty:
        empty = pd.DataFrame([{"Metric": "Total scenarios", "Value": 0}])
        return empty, "Total scenarios: 0"

    priority = scenario_df.get("Priority Level", pd.Series(dtype=str)).astype(str)
    critical_high = int(priority.str.contains("Critical|High", case=False, na=False).sum())
    areas = scenario_df.get("Affected Department / Area", pd.Series(dtype=str)).astype(str)
    actions = scenario_df.get("Model Recommended Action", pd.Series(dtype=str)).astype(str)

    top_areas = areas.value_counts().head(5)
    top_actions = actions.str.split(".").str[0].str.strip().replace("", np.nan).dropna().value_counts().head(5)
    summary_rows = [
        {"Metric": "Total scenarios", "Value": int(len(scenario_df))},
        {"Metric": "Critical/high priority scenarios", "Value": critical_high},
        {"Metric": "Top affected departments/areas", "Value": "; ".join([f"{k} ({v})" for k, v in top_areas.items()]) or "-"},
        {"Metric": "Most common recommended actions", "Value": "; ".join([f"{k} ({v})" for k, v in top_actions.items()]) or "-"},
    ]
    report_df = pd.DataFrame(summary_rows)
    report_text = "\n".join([f"{row['Metric']}: {row['Value']}" for row in summary_rows])
    return report_df, report_text


def _forecast_state_summary(state: ForecastState) -> dict:
    return {
        "forecast_horizon_hours": 72,
        "generated_at": state.forecast_timestamp,
        "best_model": state.selected_model,
        "weights": dict(state.model_weights or {}),
        "artifact_freshness": {
            "ready": state.artifact_freshness.ready,
            "artifact_timestamp": state.artifact_freshness.artifact_timestamp,
            "checked_at": state.artifact_freshness.checked_at,
            "missing": list(state.artifact_freshness.missing or []),
            "invalid_reasons": list(state.artifact_freshness.invalid_reasons or []),
        },
        "model_status": {
            "lstm_ok": state.model_status.lstm_ok,
            "arimax_ok": state.model_status.arimax_ok,
            "hybrid_ok": state.model_status.hybrid_ok,
            "fallback_used": state.model_status.fallback_used,
            "reasons": list(state.model_status.reasons or []),
        },
        "artifact_paths": dict(state.artifact_paths or {}),
    }


def command_center_source_values(state: ForecastState) -> dict:
    """Canonical values used by Command Center KPIs."""

    return {
        "source": "ForecastState",
        "current_patients": state.current_patients,
        "predicted_patients_next_hour": state.predicted_patients_next_hour,
        "peak_24h": state.peak_24h,
        "peak_72h": state.peak_72h,
        "avg_72h": state.avg_72h,
        "risk_level": state.risk_level,
        "artifact_timestamp": state.artifact_freshness.artifact_timestamp or state.forecast_timestamp,
    }


def forecast_tab_source_values(state: ForecastState) -> dict:
    """Canonical values used by the Forecast tab."""

    return {
        "source": "ForecastState",
        "predicted_patients_next_hour": state.predicted_patients_next_hour,
        "forecast_72h_values": list(state.forecast_72h_values or []),
        "peak_72h": state.peak_72h,
        "avg_72h": state.avg_72h,
        "metrics": state.metrics.copy() if isinstance(state.metrics, pd.DataFrame) else pd.DataFrame(),
    }


def digital_twin_source_series(state: ForecastState) -> list[float]:
    """Canonical 72h series used by the Digital Twin all-hospital view."""

    return list(state.forecast_72h_values or [])


def optimization_source_input(state: ForecastState) -> float | None:
    """Canonical optimization input: the same next-hour forecast in ForecastState."""

    return state.resource_recommendation_input or state.predicted_patients_next_hour


def evaluation_source_metrics(state: ForecastState) -> pd.DataFrame:
    """Canonical metrics table used by Evaluation and API evaluation endpoints."""

    return state.metrics.copy() if isinstance(state.metrics, pd.DataFrame) else pd.DataFrame()


def _load_ops72h_outputs(state: ForecastState | None = None) -> dict:
    """Load saved 72-hour forecast artifacts for Forecast and Digital Twin tabs.

    REFACTORED: we delegate to the canonical ForecastState builder.
    This ensures all tabs use the same validation + status + metrics.
    """


    state = state or build_canonical_forecast_state()
    missing = list(state.artifact_freshness.missing or [])
    invalid = list(state.artifact_freshness.invalid_reasons or [])
    if not state.artifact_freshness.ready:
        return {"ready": False, "missing": missing, "error": "; ".join(invalid), "state": state}

    overall_df = state.overall_forecast_72h.copy() if isinstance(state.overall_forecast_72h, pd.DataFrame) else pd.DataFrame()
    department_df = state.department_forecast_72h.copy() if isinstance(state.department_forecast_72h, pd.DataFrame) else pd.DataFrame()
    metrics_df = state.metrics.copy() if isinstance(state.metrics, pd.DataFrame) else pd.DataFrame()

    if overall_df.empty or not state.forecast_72h_values:
        return {"ready": False, "missing": [], "error": "ForecastState has no 72h overall forecast rows", "state": state}

    return {
        "ready": True,
        "state": state,
        "overall": overall_df.dropna(subset=["datetime", "hybrid_pred"]).reset_index(drop=True),
        "department": department_df.dropna(subset=["datetime", "department", "hybrid_pred"]).reset_index(drop=True),
        "metrics": metrics_df,
        "summary": _forecast_state_summary(state),
    }


def _dashboard_forecast_state_from_live_context() -> ForecastState:
    """Return the same ForecastState shape used by Command Center.

    In a healthy live dashboard session this comes from get_live_context(), which
    includes current patients, next-hour prediction, 24h forecast, 72h artifact
    series, metrics, risk, and artifact timestamp. If the prediction API is not
    reachable, artifact-only tabs still render from the canonical loader but make
    the missing live values explicit.
    """

    try:
        ctx = get_live_context()
        if isinstance(ctx, dict) and ctx.get("ready") and isinstance(ctx.get("forecast_state"), ForecastState):
            return ctx["forecast_state"]
    except Exception:
        pass
    return build_canonical_forecast_state()


def _show_ops72h_missing_state(bundle: dict) -> None:
    missing = bundle.get("missing") or []
    if missing:
        st.warning("72-hour forecast outputs are not available yet. Generate them before using this tab.")
        for item in missing:
            st.caption(item)
    else:
        st.warning(f"72-hour forecast outputs could not be loaded: {bundle.get('error', 'unknown error')}")


def _load_runtime_dataframe():
    # DB-first runtime: dashboard should not read CSV files.
    # Fetch historical rows from API for charting.
    data = get_patient_flow_history(limit=1000) or {}
    rows = data.get("rows", []) if isinstance(data, dict) else []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Ensure numeric
    if "patients" in df.columns:
        df["patients"] = pd.to_numeric(df["patients"], errors="coerce")
    return df.dropna(subset=["patients"]).reset_index(drop=True)


def _build_engineered_frame_from_base(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Legacy helper (no longer used in DB-first runtime)."""

    if df.empty:
        return pd.DataFrame()

    base_cols = [c for c in ["patients", "day_of_week", "month", "is_weekend", "holiday", "weather"] if c in df.columns]
    if "patients" not in base_cols:
        return pd.DataFrame()

    base_df = df.copy().reset_index(drop=True)
    for col in base_cols:
        base_df[col] = pd.to_numeric(base_df[col], errors="coerce")
    base_df = base_df.dropna(subset=["patients"]).reset_index(drop=True)
    if base_df.empty:
        return pd.DataFrame()

    # Ensure base numeric columns exist.
    for col in ["day_of_week", "month", "is_weekend", "holiday", "weather"]:
        if col not in base_df.columns:
            base_df[col] = 0.0
        base_df[col] = pd.to_numeric(base_df[col], errors="coerce").fillna(0.0)

    # Use row index to synthesize hour signal (same approach as API fallback builder)
    base_df["hour"] = base_df.index % 24
    base_df["hour_sin"] = np.sin(2 * np.pi * base_df["hour"] / 24.0)
    base_df["hour_cos"] = np.cos(2 * np.pi * base_df["hour"] / 24.0)

    patients = base_df["patients"].astype(float)
    for lag in [1, 2, 3, 6, 12, 24]:
        base_df[f"patients_lag_{lag}"] = patients.shift(lag)

    shifted = patients.shift(1)
    for window in [3, 6, 12, 24]:
        base_df[f"patients_roll_mean_{window}"] = shifted.rolling(window, min_periods=1).mean()
        base_df[f"patients_roll_std_{window}"] = shifted.rolling(window, min_periods=2).std()

    base_df["patients_diff_1"] = patients.diff(1)
    base_df["patients_diff_24"] = patients.diff(24)
    base_df["trend_feature"] = (
        np.arange(len(base_df), dtype=float) / float(len(base_df) - 1)
        if len(base_df) > 1 else 0.0
    )

    for col in [c for c in base_df.columns if c.startswith("patients_roll_std_")]:
        base_df[col] = base_df[col].fillna(0.0)

    base_df = base_df.bfill().ffill().fillna(0.0)

    # Ensure we can slice exactly the same columns the API expects.
    missing = [c for c in feature_columns if c not in base_df.columns]
    if missing:
        return pd.DataFrame()

    return base_df


def _load_runtime_sequence(df: pd.DataFrame):
    latest_sequence = get_latest_sequence()
    feature_config = get_feature_config() or {}
    feature_columns = feature_config.get("feature_columns") or list(LOCAL_FEATURE_COLUMNS)
    sequence_length = int(feature_config.get("sequence_length") or LOCAL_SEQUENCE_LENGTH)

    if latest_sequence is not None:
        arr = np.array(latest_sequence, dtype=float)
        expected_shape = (sequence_length, len(feature_columns))
        if arr.shape == expected_shape:
            return arr, feature_columns, sequence_length

        # API reachable but returned unexpected payload.
        st.warning(
            f"Latest sequence received from API but shape was {arr.shape} (expected {expected_shape})."
        )

    # DB-first: do not fallback to CSV.
    return None, feature_columns, sequence_length


def get_live_context():
    df = _load_runtime_dataframe()
    last_sequence, feature_columns, sequence_length = _load_runtime_sequence(df)

    if last_sequence is None:
        return {
            "ready": False,
            "reason": (
                "Latest model input sequence could not be loaded. "
                "Seed Postgres patient_flow data (run seed_from_csv.py or use POST /upload/patient_flow), "
                "then try again."
            ),
            "df": df,
        }

    result = get_prediction(last_sequence)
    if not result:
        return {
            "ready": False,
            "reason": (
                "Prediction API is not reachable or returned an error. "
                "Make sure uvicorn is running and API_BASE_URL is correct."
            ),
            "df": df,
        }

    if "predicted_patients_next_hour" not in result:
        return {
            "ready": False,
            "reason": f"Prediction API response missing 'predicted_patients_next_hour': keys={list(result.keys())}",
            "df": df,
        }

    patients_idx = feature_columns.index("patients") if "patients" in feature_columns else 0
    current_patients = int(last_sequence[-1][patients_idx])

    prediction = float(result["predicted_patients_next_hour"])
    forecast_values = generate_multistep_forecast(
        last_sequence=last_sequence,
        predict_fn=get_prediction,
        steps=24,
    )
    peak = float(max(forecast_values)) if forecast_values else prediction
    forecast_state = build_canonical_forecast_state(
        current_patients=float(current_patients),
        predicted_next_hour=float(prediction),
        forecast_24h_values=[float(v) for v in forecast_values],
    )
    optimization_input = float(forecast_state.resource_recommendation_input or prediction)
    optimization = get_optimization(optimization_input) or {}

    return {
        "ready": True,
        "df": df,
        "last_sequence": last_sequence,
        "feature_columns": feature_columns,
        "sequence_length": sequence_length,
        "prediction_result": result,
        "prediction": float(forecast_state.predicted_patients_next_hour or prediction),
        "current_patients": float(forecast_state.current_patients or current_patients),
        "optimization": optimization,
        "optimization_input": optimization_input,
        "peak": float(forecast_state.peak_24h or peak),
        "forecast_values": list(forecast_state.forecast_24h_values or forecast_values),
        "forecast_state": forecast_state,
    }


def show_overview():
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    result = ctx["prediction_result"]
    forecast_state = ctx["forecast_state"]
    source_values = command_center_source_values(forecast_state)
    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})

    # ------------------------------------------------------------
    # SUMMARY (3-second understanding)
    # ------------------------------------------------------------
    section_header("Summary", "Current load, short-horizon forecast, and capacity signal")

    # KPI row: 4–6 top metrics
    emergency_level = forecast_state.risk_level or result.get("emergency_level", "LOW")
    risk_status = "critical" if emergency_level == "HIGH" else "warning" if emergency_level == "MEDIUM" else "success"
    beds_needed_total = int(summary.get("beds_needed_total", result["recommended_resources"]["beds_needed"]))
    doctors_needed_total = int(summary.get("doctors_needed_total", result["recommended_resources"]["doctors_needed"]))

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        kpi_card("Total patients", fmt_patients(source_values["current_patients"]), status="info")
    with k2:
        kpi_card("Next-hour forecast", fmt_patients(source_values["predicted_patients_next_hour"]), status="normal")
    with k3:
        kpi_card("24h peak", fmt_patients(source_values["peak_24h"]), status="warning" if float(source_values["peak_24h"] or 0) >= 120 else "normal")
    with k4:
        kpi_card("Beds needed", beds_needed_total, delta="system-wide", status="warning")
    with k5:
        kpi_card("Risk signal", emergency_level, delta="pressure", status=risk_status)

    f1, f2, f3 = st.columns(3)
    with f1:
        kpi_card("72h peak", fmt_patients(source_values["peak_72h"]), status="warning" if float(source_values["peak_72h"] or 0) >= 120 else "normal")
    with f2:
        kpi_card("72h average", fmt_patients(source_values["avg_72h"]), status="normal")
    with f3:
        artifact_time = source_values["artifact_timestamp"] or "-"
        kpi_card("Artifact timestamp", artifact_time, status="info")
    st.caption("Command Center KPIs are sourced from the canonical ForecastState used by Forecast, Digital Twin, Optimization, Evaluation, and API runtime.")

    # Decision banner
    if emergency_level == "HIGH":
        alert_box(
            "Emergency surge risk is HIGH. Review department shortages and initiate surge coverage.",
            "critical",
        )
    elif emergency_level == "MEDIUM":
        alert_box(
            "Moderate pressure expected. Prepare backup coverage and monitor bed utilization.",
            "warning",
        )
    else:
        alert_box(
            "System stable. Continue standard operations; keep an eye on forecast trend.",
            "success",
        )

    # ------------------------------------------------------------
    # CORE ANALYTICS (main story)
    # ------------------------------------------------------------
    section_header("Core analytics", "Trend + forecast quality at a glance")
    left, right = st.columns(2)

    forecast_values = list(ctx.get("forecast_values") or [])

    with left:
        with st.container(border=True):
            section_header("24-hour demand outlook", "Expected arrivals over the next day")
            if forecast_values:
                forecast_df = pd.DataFrame({
                    "hour": list(range(1, len(forecast_values) + 1)),
                    "forecast": forecast_values,
                })
                fig = px.area(forecast_df, x="hour", y="forecast", title="")
                fig.update_layout(
                    height=330,
                    xaxis_title="Hours ahead",
                    yaxis_title="Predicted patients",
                    margin=dict(l=8, r=8, t=8, b=8),
                )
                st.plotly_chart(fig, use_container_width=True, key=scoped_key("overview", "core_forecast_24h"))
            else:
                empty_state("Forecast values unavailable.")

    with right:
        with st.container(border=True):
            section_header("Actual vs forecast (recent window)", "Are we tracking reality?")
            if not ctx["df"].empty and forecast_values:
                df = ctx["df"].copy().reset_index(drop=True)
                actual = df["patients"].tail(len(forecast_values)).values.astype(float)
                forecast_vals = np.array(forecast_values, dtype=float)
                min_len = int(min(len(actual), len(forecast_vals)))
                compare_df = pd.DataFrame({
                    "time_index": list(range(min_len)),
                    "Actual": actual[:min_len],
                    "Forecast": forecast_vals[:min_len],
                })
                fig_compare = px.line(compare_df, x="time_index", y=["Actual", "Forecast"], title="")
                fig_compare.update_layout(height=330, xaxis_title="Recent window", yaxis_title="Patients")
                st.plotly_chart(fig_compare, use_container_width=True, key=scoped_key("overview", "core_actual_vs_forecast"))
            else:
                empty_state("Need historical data to compare actual vs forecast.")

    # ------------------------------------------------------------
    # ACTION (interactive control + before/after)
    # ------------------------------------------------------------
    section_header("Action", "Run a quick what-if simulation and see expected impact")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        demand = c1.slider("Demand increase (%)", 0, 100, 20, key=scoped_key("overview_action", "demand"))
        beds = c2.slider("Available beds", 50, 300, 120, key=scoped_key("overview_action", "beds"))
        doctors = c3.slider("Available doctors", 5, 50, 15, key=scoped_key("overview_action", "doctors"))

        sim = simulate(float(ctx["prediction"]), beds, doctors, demand)
        if sim:
            before, after = st.columns(2)
            with before:
                section_header("Current state", "Baseline forecast + resources")
                kpi_card("Forecast", int(ctx["prediction"]), status="info")
                kpi_card("Beds needed", beds_needed_total, status="warning")
                kpi_card("Doctors needed", doctors_needed_total, status="normal")

            with after:
                section_header("Simulated state", "Your scenario")
                kpi_card("Simulated patients", int(sim.get("simulated_patients") or 0), status="info")
                level = str(sim.get("emergency_level", "LOW"))
                lvl_status = "critical" if level == "HIGH" else "warning" if level == "MEDIUM" else "success"
                kpi_card("Emergency signal", level, status=lvl_status)
                shortage = int(sim.get("doctor_shortage") or 0)
                kpi_card("Doctor shortage", shortage, status="warning" if shortage > 0 else "success")

            if int(sim.get("doctor_shortage") or 0) == 0:
                st.success("Scenario looks feasible: no doctor shortage detected for your inputs.")
            else:
                st.warning("Scenario indicates a staffing shortage. Consider increasing doctor availability.")

    # ------------------------------------------------------------
    # INSIGHTS (rankings + copilot)
    # ------------------------------------------------------------
    section_header("Insights", "Where pressure concentrates + what to do next")
    i_left, i_right = st.columns([1.25, 1])

    allocations = optimization.get("department_allocations", [])
    with i_left:
        with st.container(border=True):
            section_header("Department pressure (top 5)", "Focus areas based on modeled shortages")
            if allocations:
                alloc_df = pd.DataFrame(allocations)
                if "priority_score" in alloc_df.columns:
                    alloc_df = alloc_df.sort_values(by="priority_score", ascending=False)
                show_cols = [c for c in ["department", "status", "priority_score", "bed_shortage", "doctor_shortage", "nurse_shortage"] if c in alloc_df.columns]
                modern_table(alloc_df.head(5)[show_cols] if show_cols else alloc_df.head(5), key=scoped_key("overview", "insights_pressure_top5"))
            else:
                empty_state("No department allocation data available.")

    with i_right:
        with st.container(border=True):
            section_header("AI Copilot", "Quick recommendations (from existing optimizer output)")
            recs = list(optimization.get("recommendations", []) or [])
            if recs:
                for rec in recs[:5]:
                    alert_box(str(rec), "info")
            else:
                empty_state("No recommendations currently available.")

            st.caption("Need details? Open Optimization → Action plan, or Notifications → Alerts.")


def show_forecast():
    page_header(
        "Forecasting",
        "Demand outlook across the next 72 hours — trends, peaks, and actual vs predicted.",
    )

    state = _dashboard_forecast_state_from_live_context()
    ops72h = _load_ops72h_outputs(state)
    if not ops72h.get("ready"):
        _show_ops72h_missing_state(ops72h)
        return

    overall_df = ops72h["overall"].copy()
    department_df = ops72h["department"].copy()
    metrics_df = ops72h["metrics"].copy()
    summary = ops72h["summary"] or {}
    state = ops72h.get("state") or state
    source_values = forecast_tab_source_values(state)

    if overall_df.empty:
        empty_state("72-hour overall forecast file is empty.")
        return

    overall_df = overall_df.sort_values("datetime").reset_index(drop=True)
    overall_df["hour_ahead"] = np.arange(1, len(overall_df) + 1)
    predictions = list(source_values["forecast_72h_values"]) or overall_df["hybrid_pred"].astype(float).tolist()

    best_model = _model_name(summary.get("best_model") or "")
    if not best_model and not metrics_df.empty and "RMSE" in metrics_df.columns and "Model" in metrics_df.columns:
        best_model = _model_name(metrics_df.sort_values("RMSE", ascending=True).iloc[0]["Model"])
    weights = summary.get("weights") or {}
    hybrid_row = pd.DataFrame()
    if not metrics_df.empty and "Model" in metrics_df.columns:
        hybrid_row = metrics_df[metrics_df["Model"].astype(str).str.lower() == "hybrid"].head(1)

    # Summary KPIs
    peak = float(max(predictions))
    next_hour = float(source_values["predicted_patients_next_hour"] if source_values["predicted_patients_next_hour"] is not None else predictions[0])
    avg_72h = float(source_values["avg_72h"] if source_values["avg_72h"] is not None else np.mean(predictions))
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        # Best-model correctness/presentation: use RMSE-basis and explain in-text below.
        kpi_card(
            "Operational recommendation",
            best_model or "-",
            status="success" if best_model == "Hybrid" else "info",
        )
    with k2:
        kpi_card("Next hour", fmt_patients(next_hour), status="info")
    with k3:
        kpi_card("72h peak", fmt_patients(peak), status="warning" if peak >= 100 else "normal")
    with k4:
        trend = float(predictions[-1] - predictions[0])
        kpi_card(
            "Trend",
            fmt_trend(trend),
            delta="end − start",
            status="warning" if trend > 5 else "success" if trend < -5 else "normal",
        )
    with k5:
        kpi_card("72h average", fmt_patients(avg_72h), status="normal")
    st.caption("Forecast tab is rendering from the same canonical ForecastState object shape used by Command Center; the 72h series is ForecastState.forecast_72h_values.")

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        kpi_card("LSTM weight", fmt_weight(weights.get("lstm", 0.0)), status="info")
    with m2:
        kpi_card("ARIMAX weight", fmt_weight(weights.get("arimax", 0.0)), status="info")
    if not hybrid_row.empty:
        row = hybrid_row.iloc[0]
        # MAE/RMSE should be primary; keep MAPE as caution via label below.
        with m3:
            kpi_card("Hybrid MAE", fmt_mae_rmse(row.get("MAE", 0.0)), status="normal")
        with m4:
            kpi_card("Hybrid RMSE", fmt_mae_rmse(row.get("RMSE", 0.0)), status="success")
        with m5:
            kpi_card("MAPE (caution)", fmt_mape(row.get("MAPE", 0.0)), status="warning")

    # Lightweight, honest explanations to prevent “model is broken” impressions.
    # (No data changes; display-only notes.)
    best_rmse_text = ""
    if not metrics_df.empty and {"Model", "RMSE"}.issubset(metrics_df.columns):
        best_row = metrics_df.sort_values("RMSE", ascending=True).iloc[0]
        best_rmse_text = f" Lowest RMSE: {_model_name(best_row.get('Model'))} ({fmt_mae_rmse(best_row.get('RMSE'))})."
    alert_box(
        "Hybrid is highlighted as the operational recommendation when it has the lowest RMSE, because RMSE summarizes absolute forecast error in patient-count units more directly than MAPE." + best_rmse_text,
        "success" if best_model == "Hybrid" else "info",
    )

    # ARIMAX “flatness” / early stabilization hint: base on loaded artifact variability.
    # If curves are nearly constant, explain that it may be an artifact/model limitation.
    try:
        if "arimax_pred" in overall_df.columns:
            arimax_vals = overall_df["arimax_pred"].astype(float).values
            arimax_range = float(np.nanmax(arimax_vals) - np.nanmin(arimax_vals))
            if arimax_range < 0.5:
                st.info(
                    "ARIMAX output appears nearly constant across this saved 72h horizon. This is likely an artifact of the saved ARIMAX forecast behavior (not a display bug)."
                )
    except Exception:
        pass

    # Trend explanation (negative/positive)
    st.caption(
        "Trend is the final forecast minus the first forecast. Negative means demand is expected to ease across the horizon; positive means pressure increases."
    )
    stable_note = _stable_tail_note(predictions, label="The overall Hybrid forecast")
    if stable_note:
        st.info(stable_note)


    section_header("72-hour overall hospital forecast", "Saved Hybrid forecast output from artifacts/forecast_outputs")
    col1, col2 = st.columns(2)

    with col1:
        y_cols = [c for c in ["lstm_pred", "arimax_pred", "hybrid_pred"] if c in overall_df.columns]
        overall_chart_df = overall_df.copy()
        for col in y_cols:
            overall_chart_df[col] = pd.to_numeric(overall_chart_df[col], errors="coerce").round(0)
        fig_forecast = px.line(
            overall_chart_df,
            x="datetime",
            y=y_cols or "hybrid_pred",
            markers=True,
            title="72-hour overall forecast (patient counts)",
        )
        fig_forecast.update_layout(height=380, xaxis_title="Forecast time", yaxis_title="Predicted patients")
        fig_forecast.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.0f} patients<extra></extra>")
        st.plotly_chart(fig_forecast, use_container_width=True, key=scoped_key("forecast", "ops72h_overall_curve"))

    with col2:
        display_cols = [c for c in ["hour_ahead", "datetime", "lstm_pred", "arimax_pred", "hybrid_pred"] if c in overall_df.columns]
        modern_table(_round_display_dataframe(overall_df[display_cols].head(72)), key=scoped_key("forecast", "ops72h_overall_table"))

    section_header("Department-level 72-hour forecast", "Hybrid forecast distributed by department")
    if department_df.empty:
        empty_state("Department-level forecast output is empty.")
    else:
        department_df = department_df.sort_values(["department", "datetime"]).reset_index(drop=True)
        dept_options = sorted([str(d) for d in department_df["department"].dropna().unique().tolist()])
        selected_depts = st.multiselect(
            "Departments",
            dept_options,
            default=dept_options[: min(5, len(dept_options))],
            key=scoped_key("forecast", "ops72h_department_filter"),
        )
        plot_dept_df = department_df[department_df["department"].astype(str).isin(selected_depts)] if selected_depts else department_df
        dept_chart_df = plot_dept_df.copy()
        dept_chart_df["hybrid_pred"] = pd.to_numeric(dept_chart_df["hybrid_pred"], errors="coerce").round(0)
        fig_dept = px.line(
            dept_chart_df,
            x="datetime",
            y="hybrid_pred",
            color="department",
            title="Department-level Hybrid forecast (patient counts)",
        )
        fig_dept.update_layout(height=420, xaxis_title="Forecast time", yaxis_title="Predicted patients")
        fig_dept.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.0f} patients<extra></extra>")
        st.plotly_chart(fig_dept, use_container_width=True, key=scoped_key("forecast", "ops72h_department_curve"))
        dept_flat_notes = []
        for dept_name, group in plot_dept_df.groupby("department"):
            note = _stable_tail_note(group["hybrid_pred"].astype(float).tolist(), label=f"{dept_name}")
            if note:
                dept_flat_notes.append(note)
        if dept_flat_notes:
            st.info(" ".join(dept_flat_notes[:3]))
        modern_table(_round_display_dataframe(department_df.head(200)), key=scoped_key("forecast", "ops72h_department_table"))

    section_header("Model comparison", "Metrics from artifacts/metrics/ops72h_model_metrics.csv")
    if metrics_df.empty:
        empty_state("Model metrics output is empty.")
    else:
        display_metrics = _round_display_dataframe(metrics_df)
        modern_table(display_metrics, key=scoped_key("forecast", "ops72h_metrics_table"))
        metric_cols = [c for c in ["MAE", "RMSE", "MAPE"] if c in metrics_df.columns]
        if "Model" in metrics_df.columns and metric_cols:
            primary_cols = [c for c in ["MAE", "RMSE"] if c in metrics_df.columns]
            fig_metrics = px.bar(metrics_df, x="Model", y=primary_cols, barmode="group", title="Primary model comparison: MAE/RMSE")
            fig_metrics.update_layout(height=360, yaxis_title="Error in patient-count units")
            st.plotly_chart(fig_metrics, use_container_width=True, key=scoped_key("forecast", "ops72h_metrics_chart"))
            if "MAPE" in metrics_df.columns:
                st.caption("MAPE is retained in the table as a secondary caution metric because it can look very high when actual patient counts are low or near zero.")

    with st.expander("Training summary"):
        st.json(summary)


def show_optimization():
    page_header(
        "Optimization",
        "AI-powered resource optimization — allocations, shortages, and recommended actions.",
    )

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    forecast_state = ctx["forecast_state"]
    canonical_input = optimization_source_input(forecast_state)
    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})
    allocations = optimization.get("department_allocations", [])
    recommendations = optimization.get("recommendations", [])
    actions = optimization.get("actions", [])

    objective = summary.get("objective")
    top_dept = str(summary.get("top_priority_department", "-") or "-")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Beds needed", int(summary.get("beds_needed_total", 0)), status="warning")
    with c2:
        kpi_card("Doctors needed", int(summary.get("doctors_needed_total", 0)), status="normal")
    with c3:
        kpi_card("Nurses needed", int(summary.get("nurses_needed_total", 0)), status="normal")
    with c4:
        kpi_card("Top priority", top_dept, delta=f"Objective: {objective}" if objective is not None else None, status="info")

    st.caption(
        f"Optimization input is ForecastState.predicted_patients_next_hour = {fmt_patients(canonical_input)}; recommendations and allocations are generated from that same value."
    )

    left, right = st.columns([1.35, 1])
    with left:
        with st.container(border=True):
            section_header("Department allocations")
            if allocations:
                alloc_df = pd.DataFrame(allocations)
                show_cols = [
                    c
                    for c in [
                        "department",
                        "predicted_patients",
                        "status",
                        "beds_required",
                        "bed_shortage",
                        "doctors_required",
                        "doctor_shortage",
                        "nurses_required",
                        "nurse_shortage",
                        "priority_score",
                    ]
                    if c in alloc_df.columns
                ]
                modern_table(alloc_df[show_cols] if show_cols else alloc_df, key=scoped_key("optimization", "alloc_table"))
            else:
                empty_state("No optimization allocations available.")

        if allocations:
            alloc_df = pd.DataFrame(allocations)
            with st.container(border=True):
                section_header("Pressure ranking")
                if "priority_score" in alloc_df.columns and "department" in alloc_df.columns:
                    fig_priority = px.bar(
                        alloc_df,
                        x="department",
                        y="priority_score",
                        color="status" if "status" in alloc_df.columns else None,
                        title="",
                    )
                    fig_priority.update_layout(height=360, yaxis_title="Priority score", xaxis_title="")
                    st.plotly_chart(fig_priority, use_container_width=True, key=scoped_key("optimization", "pressure_ranking"))

            shortage_cols = ["department", "bed_shortage", "doctor_shortage", "nurse_shortage"]
            if all(col in alloc_df.columns for col in shortage_cols):
                with st.container(border=True):
                    section_header("Shortages by department")
                    shortage_df = alloc_df[shortage_cols].copy()
                    fig_shortage = px.bar(
                        shortage_df,
                        x="department",
                        y=["bed_shortage", "doctor_shortage", "nurse_shortage"],
                        barmode="group",
                        title="",
                    )
                    fig_shortage.update_layout(height=380, xaxis_title="")
                    st.plotly_chart(fig_shortage, use_container_width=True, key=scoped_key("optimization", "shortages"))

    with right:
        with st.container(border=True):
            section_header("Recommendations")
            if recommendations:
                for rec in recommendations:
                    alert_box(str(rec), level="info")
            else:
                empty_state("No recommendations available.")

        with st.container(border=True):
            section_header("Action plan")
            if actions:
                modern_table(pd.DataFrame(actions), key=scoped_key("optimization", "actions_table"))
            else:
                empty_state("No explicit actions generated.")


def _build_capacity_from_allocations(allocations: list[dict]) -> pd.DataFrame:
    """Build a capacity/coverage view from real optimizer output.

    This replaces the old deterministic "demo capacity map".

    We interpret:
      - beds_required as the modeled requirement for next-hour load
      - bed_shortage as the deficit against available beds

    Derived fields:
      - beds_available_est = max(0, beds_required - bed_shortage)

    The goal is to show *real, API-backed* content everywhere (no placeholders).
    """

    if not allocations:
        return pd.DataFrame()

    df = pd.DataFrame(allocations)
    if df.empty or "department" not in df.columns:
        return pd.DataFrame()

    # Normalize numeric fields.
    for col in ["predicted_patients", "beds_required", "bed_shortage"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    df["beds_available_est"] = (df["beds_required"] - df["bed_shortage"]).clip(lower=0)

    out_cols = [
        c
        for c in [
            "department",
            "status",
            "predicted_patients",
            "beds_required",
            "beds_available_est",
            "bed_shortage",
            "doctor_shortage",
            "nurse_shortage",
            "priority_score",
        ]
        if c in df.columns
    ]
    return df[out_cols].sort_values(by="priority_score", ascending=False) if "priority_score" in df.columns else df[out_cols]


def _load_what_if_scenarios() -> pd.DataFrame | None:
    """Load expanded what-if scenario dataset.

    Returns None when CSV is missing/invalid so callers can fall back to the
    legacy hardcoded scenario generator.
    """

    path = Path("data") / "updated_exports" / "what_if_scenarios.csv"
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path)
    except Exception:
        return None

    return df


def _validate_what_if_scenarios(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty:
        return False

    required_cols = {
        "scenario_id",
        "scenario_name",
        "scenario_category",
        "department",
        "time_window",
        "demand_multiplier",
        "arrival_increase_percent",
        "bed_capacity_change_percent",
        "doctor_availability_change_percent",
        "nurse_availability_change_percent",
        "or_booking_change_percent",
        "appointment_change_percent",
        "discharge_delay_hours",
        "severity_level",
        "probability_level",
        "operational_risk",
        "affected_resources",
        "expected_system_response",
        "recommended_action",
        "escalation_required",
        "notes",
    }
    if not required_cols.issubset(set(df.columns)):
        return False

    if len(df) < 40:
        return False

    # scenario_id uniqueness
    if "scenario_id" not in df.columns:
        return False
    try:
        if not df["scenario_id"].is_unique:
            return False
    except Exception:
        return False

    # severity/probability/risk values are expected to be categorical
    severity_allowed = {"Low", "Medium", "High", "Critical"}
    if not set(df["severity_level"].dropna().astype(str).unique().tolist()).issubset(severity_allowed):
        return False

    prob_allowed = {"Rare", "Unlikely", "Possible", "Likely", "Very Likely", "VeryLikely"}
    if not set(df["probability_level"].dropna().astype(str).unique().tolist()).intersection(prob_allowed):
        return False

    risk_allowed = {"Low", "Moderate", "High", "Critical"}
    if not set(df["operational_risk"].dropna().astype(str).unique().tolist()).issubset(risk_allowed):
        return False

    # escalation_required
    esc_allowed = {"Yes", "No"}
    if not set(df["escalation_required"].dropna().astype(str).unique().tolist()).issubset(esc_allowed):
        return False

    # basic numeric conversion checks for the dynamic impact fields
    numeric_cols = [
        "demand_multiplier",
        "arrival_increase_percent",
        "bed_capacity_change_percent",
        "doctor_availability_change_percent",
        "nurse_availability_change_percent",
        "or_booking_change_percent",
        "appointment_change_percent",
        "discharge_delay_hours",
    ]
    for c in numeric_cols:
        if c not in df.columns:
            return False
        df[c] = pd.to_numeric(df[c], errors="coerce")
        if df[c].isna().all():
            return False

    return True


def _build_simulation_scenario_analysis(
    *,
    prediction: float,
    demand_increase_pct: float,
    available_beds: int,
    available_doctors: int,
    sim: dict | None,
    capacity_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build an expanded rule-based what-if table for the Simulation tab.

    The Simulation tab exposes demand, beds, doctors, simulation output, and
    optimizer-derived capacity signals. It does not expose exact live nurse pool,
    ICU capacity, OR room slots, appointment-room capacity, or absentee rosters.
    For those unavailable inputs, this function uses conservative proxy estimates
    and labels them as estimates in the table rather than pretending exact data is
    available.
    """

    demand_pct = float(demand_increase_pct or 0.0)
    simulated_patients = float((sim or {}).get("simulated_patients") or prediction * (1.0 + demand_pct / 100.0))
    recommended = (sim or {}).get("recommended_resources") or {}

    required_beds = int(recommended.get("beds_needed") or np.ceil(simulated_patients))
    required_doctors = int(recommended.get("doctors_needed") or np.ceil(simulated_patients / 10.0))
    required_nurses = int(recommended.get("nurses_needed") or np.ceil(simulated_patients / 6.0))
    available_beds = int(available_beds)
    available_doctors = int(available_doctors)

    bed_shortage = max(required_beds - available_beds, 0)
    doctor_shortage = max(required_doctors - available_doctors, 0)

    cap = capacity_df.copy() if isinstance(capacity_df, pd.DataFrame) else pd.DataFrame()
    for col in ["bed_shortage", "doctor_shortage", "nurse_shortage", "priority_score", "predicted_patients", "beds_required", "beds_available_est"]:
        if col in cap.columns:
            cap[col] = pd.to_numeric(cap[col], errors="coerce").fillna(0)

    capacity_nurse_shortage = int(cap["nurse_shortage"].sum()) if "nurse_shortage" in cap.columns and not cap.empty else 0
    # Estimated available nurses because the Simulation controls do not include a nurse slider.
    estimated_available_nurses = max(required_nurses - capacity_nurse_shortage, int(np.ceil(available_doctors * 2.5)), 0)
    nurse_shortage = max(required_nurses - estimated_available_nurses, capacity_nurse_shortage, 0)

    high_demand = demand_pct >= 20.0
    moderate_demand = demand_pct >= 10.0
    multiple_shortages = sum([bed_shortage > 0, doctor_shortage > 0, nurse_shortage > 0]) >= 2
    stable_operation = not high_demand and bed_shortage == 0 and doctor_shortage == 0 and nurse_shortage == 0
    high_capacity_low_demand = demand_pct <= 5 and available_beds >= required_beds + 20 and available_doctors >= required_doctors + 3
    forecast_pressure_no_shortage = moderate_demand and bed_shortage == 0 and doctor_shortage == 0

    current_month = pd.Timestamp.now().month
    season_name = "winter" if current_month in {12, 1, 2} else "spring" if current_month in {3, 4, 5} else "summer" if current_month in {6, 7, 8} else "autumn"

    def dept_rows(name: str) -> pd.DataFrame:
        if cap.empty or "department" not in cap.columns:
            return pd.DataFrame()
        return cap[cap["department"].astype(str).str.contains(name, case=False, na=False)]

    def dept_gap(name: str) -> int:
        rows = dept_rows(name)
        if rows.empty:
            return 0
        total = 0
        for c in ["bed_shortage", "doctor_shortage", "nurse_shortage"]:
            if c in rows.columns:
                total += int(rows[c].sum())
        return total

    er_gap = dept_gap("ER|Emergency")
    icu_gap = dept_gap("ICU")
    ward_gap = dept_gap("Ward|General")
    waiting_estimate = max(int(np.ceil(simulated_patients - prediction)), 0)
    waiting_threshold = max(10, int(np.ceil(simulated_patients * 0.10)))

    if not cap.empty and "department" in cap.columns:
        gap_cols = [c for c in ["bed_shortage", "doctor_shortage", "nurse_shortage"] if c in cap.columns]
        if gap_cols:
            cap["total_gap"] = cap[gap_cols].sum(axis=1)
            top_gap_row = cap.sort_values("total_gap", ascending=False).head(1)
        else:
            top_gap_row = pd.DataFrame()
    else:
        top_gap_row = pd.DataFrame()
    top_dept = str(top_gap_row.iloc[0]["department"]) if not top_gap_row.empty and float(top_gap_row.iloc[0].get("total_gap", 0)) > 0 else "No single department"
    top_dept_gap = int(top_gap_row.iloc[0].get("total_gap", 0)) if not top_gap_row.empty else 0

    # Safe proxies for operational signals not exposed by Simulation controls.
    estimated_or_bookings = max(0, int(np.ceil(simulated_patients / 18.0)))
    estimated_or_slots = max(2, int(np.floor(available_doctors / 4.0)))
    or_gap = max(estimated_or_bookings - estimated_or_slots, 0)
    estimated_appointments = max(0, int(np.ceil(simulated_patients * 0.35)))
    estimated_appointment_capacity = max(available_doctors * 3, 1)
    appointment_gap = max(estimated_appointments - estimated_appointment_capacity, 0)
    estimated_absent_staff = max(0, int(np.ceil((doctor_shortage + nurse_shortage) * 0.30)))
    night_required_staff = max(1, int(np.ceil((required_doctors + required_nurses) * 0.35)))
    night_available_staff = max(1, int(np.ceil((available_doctors + estimated_available_nurses) * 0.25)))
    night_gap = max(night_required_staff - night_available_staff, 0)
    discharge_delay_gap = max(bed_shortage, int(np.ceil(waiting_estimate * 0.25)) if waiting_estimate > waiting_threshold else 0)
    resource_conflict = (bed_shortage > 0 and doctor_shortage == 0 and nurse_shortage == 0) or (bed_shortage == 0 and (doctor_shortage > 0 or nurse_shortage > 0))

    def priority_label(level: str) -> str:
        return {"Critical": "🔴 Critical", "High": "🟠 High", "Medium": "🟡 Medium", "Low": "🟢 Low"}.get(level, level)

    def row(
        scenario: str,
        trigger: str,
        situation: str,
        available: str,
        required: str,
        gap: str,
        action: str,
        decision: str,
        priority: str,
        area: str,
        outcome: str,
    ) -> dict:
        return {
            "Scenario": scenario,
            "Trigger / Condition": trigger,
            "Current Situation": situation,
            "Available Resources": available,
            "Required Resources": required,
            "Shortage / Gap": gap,
            "Model Recommended Action": action,
            "Operational Decision": decision,
            "Priority Level": priority_label(priority),
            "Affected Department / Area": area,
            "Expected Outcome": outcome,
        }

    # CSV mode: try to load expanded scenarios from data/updated_exports/what_if_scenarios.csv.
    # If the CSV fails validation, fall back to the legacy hardcoded rows.
    csv_df = _load_what_if_scenarios()
    csv_mode_valid = _validate_what_if_scenarios(csv_df)

    ui_cols = [
        "Scenario",
        "Trigger / Condition",
        "Current Situation",
        "Available Resources",
        "Required Resources",
        "Shortage / Gap",
        "Model Recommended Action",
        "Operational Decision",
        "Priority Level",
        "Affected Department / Area",
        "Expected Outcome",
    ]

    if csv_mode_valid:
        def _csv_priority(base_level: str, bed_gap: int, doc_gap: int, nurse_gap: int) -> str:
            gaps = sum([bed_gap > 0, doc_gap > 0, nurse_gap > 0])
            level = str(base_level or "Low")
            if gaps >= 2 and level in {"Low", "Medium"}:
                return "High"
            if gaps >= 3 and level != "Critical":
                return "Critical"
            if (bed_gap >= 10 or doc_gap >= 5 or nurse_gap >= 5) and level in {"Low", "Medium"}:
                return "High"
            return level

        out_rows: list[dict] = []

        # Baseline requirements from the live Simulation controls.
        baseline_required_beds = required_beds
        baseline_required_doctors = required_doctors
        baseline_required_nurses = required_nurses

        for _, r in csv_df.iterrows():
            scenario_name = str(r.get("scenario_name"))
            scenario_category = str(r.get("scenario_category"))
            department = str(r.get("department"))
            time_window = str(r.get("time_window"))

            demand_multiplier = float(r.get("demand_multiplier") or 1.0)
            arrival_increase_percent = float(r.get("arrival_increase_percent") or 0.0)
            bed_capacity_change_percent = float(r.get("bed_capacity_change_percent") or 0.0)
            doctor_availability_change_percent = float(r.get("doctor_availability_change_percent") or 0.0)
            nurse_availability_change_percent = float(r.get("nurse_availability_change_percent") or 0.0)
            appointment_change_percent = float(r.get("appointment_change_percent") or 0.0)
            or_booking_change_percent = float(r.get("or_booking_change_percent") or 0.0)
            discharge_delay_hours = float(r.get("discharge_delay_hours") or 0.0)

            severity_level = str(r.get("severity_level") or "Low")
            probability_level = str(r.get("probability_level") or "Possible")
            operational_risk = str(r.get("operational_risk") or "Moderate")
            affected_resources = str(r.get("affected_resources") or "")
            expected_system_response = str(r.get("expected_system_response") or "")
            recommended_action = str(r.get("recommended_action") or "")
            escalation_required = str(r.get("escalation_required") or "No")
            notes = str(r.get("notes") or "")

            # Dynamic calculation drivers (demand/beds/doctors + discharge delay).
            demand_scaled = simulated_patients * float(demand_multiplier)
            demand_scaled *= (1.0 + float(arrival_increase_percent) / 100.0)
            demand_scaled = max(demand_scaled, 0.0)

            # Scale baseline requirements with demand.
            demand_ratio = demand_scaled / max(simulated_patients, 1e-9)
            required_beds_csv = int(np.ceil(baseline_required_beds * demand_ratio))
            required_doctors_csv = int(np.ceil(baseline_required_doctors * demand_ratio))
            required_nurses_csv = int(np.ceil(baseline_required_nurses * demand_ratio))

            # Delayed discharge increases bed pressure.
            discharge_delay_penalty = int(np.ceil(max(discharge_delay_hours, 0.0) / 2.0))
            required_beds_csv += discharge_delay_penalty

            available_beds_csv = int(max(0, np.floor(available_beds * (1.0 + bed_capacity_change_percent / 100.0))))
            available_doctors_csv = int(max(0, np.floor(available_doctors * (1.0 + doctor_availability_change_percent / 100.0))))
            estimated_available_nurses_csv = int(max(0, np.floor(estimated_available_nurses * (1.0 + nurse_availability_change_percent / 100.0))))

            bed_shortage_csv = max(required_beds_csv - available_beds_csv, 0)
            doctor_shortage_csv = max(required_doctors_csv - available_doctors_csv, 0)
            nurse_shortage_csv = max(required_nurses_csv - estimated_available_nurses_csv, 0)

            # Wording dynamics.
            mixed_crisis = ("mixed" in scenario_category.lower()) or severity_level == "Critical"
            delayed_discharge_strong = discharge_delay_penalty >= 6

            trigger = f"{scenario_category}: x{demand_multiplier:.2f} demand; arrival +{arrival_increase_percent:.0f}% during {time_window}."
            current_situation = (
                f"Baseline simulated patients ≈ {simulated_patients:.0f}; scenario-adjusted demand ≈ {demand_scaled:.0f}. "
                f"Discharge delay proxy adds {discharge_delay_penalty} bed-pressure units."
            )

            available_resources = (
                f"Beds available: {available_beds_csv}; Doctors available: {available_doctors_csv}; "
                f"Nurses available: ~{estimated_available_nurses_csv}."
            )
            required_resources = (
                f"Beds required: {required_beds_csv}; Doctors required: {required_doctors_csv}; Nurses required: {required_nurses_csv}."
            )
            shortage_gap = f"Bed gap: {bed_shortage_csv}; Doctor gap: {doctor_shortage_csv}; Nurse gap: {nurse_shortage_csv}."

            # Stronger decision language when mixed crisis or multiple shortages.
            decision_bits = []
            if bed_shortage_csv > 0:
                decision_bits.append(f"Open overflow beds + accelerate discharge (gap beds={bed_shortage_csv}).")
            if doctor_shortage_csv > 0:
                decision_bits.append(f"Call on-call doctors / reschedule non-urgent (gap doctors={doctor_shortage_csv}).")
            if nurse_shortage_csv > 0:
                decision_bits.append(f"Activate nursing backup / redistribute (gap nurses={nurse_shortage_csv}).")
            if not decision_bits:
                decision_bits.append("Maintain standard operations; monitor capacity trend.")

            operational_decision = " ".join(decision_bits)
            if mixed_crisis:
                operational_decision = "Initiate multi-resource command huddle. " + operational_decision
            if delayed_discharge_strong and bed_shortage_csv > 0:
                operational_decision = "Discharge acceleration priority due to delayed turnover. " + operational_decision

            model_recommended_action = recommended_action.strip()
            if (bed_shortage_csv + doctor_shortage_csv + nurse_shortage_csv) > 0:
                model_recommended_action += f" (Targets: beds {bed_shortage_csv}, doctors {doctor_shortage_csv}, nurses {nurse_shortage_csv})."

            # Priority level based on CSV severity + computed gaps.
            csv_priority_base = _csv_priority(severity_level, bed_shortage_csv, doctor_shortage_csv, nurse_shortage_csv)
            priority_level = priority_label(csv_priority_base)

            affected_area = f"{department} ({affected_resources})".strip() if affected_resources else department

            expected_outcome = expected_system_response.strip() if expected_system_response else ""
            if delayed_discharge_strong:
                expected_outcome = (expected_outcome + " Discharge delays amplify bed crowding; prioritize turnaround.").strip()
            if notes:
                expected_outcome = (expected_outcome + f" Notes: {notes}").strip()

            out_rows.append({
                "Scenario": scenario_name,
                "Trigger / Condition": trigger,
                "Current Situation": current_situation,
                "Available Resources": available_resources,
                "Required Resources": required_resources,
                "Shortage / Gap": shortage_gap,
                "Model Recommended Action": model_recommended_action,
                "Operational Decision": operational_decision,
                "Priority Level": priority_level,
                "Affected Department / Area": affected_area,
                "Expected Outcome": expected_outcome,
            })

        out = pd.DataFrame(out_rows)
        return out[ui_cols].copy()

    # Legacy fallback below (hardcoded scenarios).
    rows = [
        row(
            "Emergency demand surge",
            f"Demand increased by {demand_pct:.0f}% and simulated patients = {simulated_patients:.0f}.",
            "Emergency surge threshold reached." if high_demand else "Demand is below the emergency surge threshold.",
            f"Doctors: {available_doctors}; beds: {available_beds}; nurses: ~{estimated_available_nurses} estimated.",
            f"Doctors: {required_doctors}; beds: {required_beds}; nurses: {required_nurses}.",
            f"Doctors: {doctor_shortage}; beds: {bed_shortage}; nurses: {nurse_shortage}.",
            f"Activate emergency staff, open {max(bed_shortage, 10) if high_demand else 0} overflow beds if surge persists, and prioritize urgent patients.",
            "Start surge protocol now." if high_demand or multiple_shortages else "Keep surge team on standby.",
            "Critical" if multiple_shortages and high_demand else "High" if high_demand else "Low",
            "ER / Triage / Admissions",
            "Reduced waiting time and faster emergency throughput.",
        ),

        row(
            "Bed shortage",
            f"Available beds = {available_beds}; required beds = {required_beds}.",
            "Admissions exceed safe bed capacity." if bed_shortage > 0 else "Bed capacity is sufficient for the current scenario.",
            f"Beds available: {available_beds}.",
            f"Beds required: {required_beds}.",
            f"Bed shortage: {bed_shortage}.",
            f"Open {bed_shortage} overflow beds, speed up discharge review, reassign beds, and transfer stable patients." if bed_shortage > 0 else "Maintain current bed plan and review occupancy hourly.",
            "Escalate bed management." if bed_shortage > 0 else "No bed escalation required.",
            "Critical" if bed_shortage >= 10 else "High" if bed_shortage > 0 else "Low",
            "Admissions / General Ward / Bed Management",
            "Lower admission delays and reduced department overcrowding.",
        ),
        row(
            "Doctor shortage",
            f"Available doctors = {available_doctors}; required doctors = {required_doctors}.",
            "Physician coverage is below simulated need." if doctor_shortage > 0 else "Doctor coverage is sufficient for simulated demand.",
            f"Doctors available: {available_doctors}.",
            f"Doctors required: {required_doctors}.",
            f"Doctor shortage: {doctor_shortage}.",
            f"Call {doctor_shortage} on-call doctors, move doctors from stable departments, and reschedule non-urgent appointments." if doctor_shortage > 0 else "Keep current physician roster and monitor queue growth.",
            "Activate on-call physician pool." if doctor_shortage > 0 else "No doctor reallocation required.",
            "High" if doctor_shortage > 0 else "Low",
            "ER / Clinics / Consultation Areas",
            "Shorter consultation queues and faster patient processing.",
        ),
        row(
            "Nurse shortage",
            f"Estimated available nurses = {estimated_available_nurses}; required nurses = {required_nurses}.",
            "Nurse coverage is below estimated need." if nurse_shortage > 0 else "Nurse coverage appears adequate using available signals.",
            f"Nurses available: ~{estimated_available_nurses} estimated.",
            f"Nurses required: {required_nurses}.",
            f"Nurse shortage: {nurse_shortage}.",
            f"Call {nurse_shortage} backup nurses, redistribute nurses, and extend coverage for ER/ICU/General Ward." if nurse_shortage > 0 else "Keep backup nurse roster ready and maintain current coverage.",
            "Activate nursing backup roster." if nurse_shortage > 0 else "No nursing escalation required.",
            "High" if nurse_shortage > 0 else "Low",
            "Nursing / ER / ICU / General Ward",
            "Improved bedside coverage and response time.",
        ),
        row(
            "ICU pressure",
            f"ICU shortage signal = {icu_gap}; simulated patients = {simulated_patients:.0f}.",
            "ICU demand is approaching or exceeding capacity." if icu_gap > 0 or high_demand else "No ICU capacity breach detected from available signals.",
            f"ICU capacity signal gap: {icu_gap}; hospital beds available: {available_beds}.",
            "Reserve ICU beds for critical cases; exact ICU bed count unavailable in Simulation tab.",
            f"ICU gap signal: {icu_gap}.",
            "Reserve ICU beds for critical cases, transfer stable ICU patients when clinically safe, and prepare escalation." if icu_gap > 0 or high_demand else "Maintain ICU watch list and preserve escalation readiness.",
            "Trigger ICU escalation huddle." if icu_gap > 0 else "Continue ICU monitoring.",
            "Critical" if icu_gap > 0 else "Medium" if high_demand else "Low",
            "ICU / Critical Care",
            "Critical care capacity protected for urgent patients.",
        ),
        row(
            "ER overcrowding",
            f"Demand increase = {demand_pct:.0f}%; ER gap signal = {er_gap}; waiting estimate = {waiting_estimate}.",
            "ER demand exceeds expected capacity." if high_demand or er_gap > 0 or waiting_estimate > waiting_threshold else "ER pressure remains manageable.",
            f"Doctors: {available_doctors}; nurses: ~{estimated_available_nurses}; ER gap signal: {er_gap}.",
            f"Doctors: {required_doctors}; nurses: {required_nurses}; waiting threshold: {waiting_threshold}.",
            f"ER gap: {er_gap}; estimated waiting excess: {max(waiting_estimate - waiting_threshold, 0)}.",
            "Open fast-track triage, add ER staff, and redirect low-acuity cases to clinics." if high_demand or er_gap > 0 else "Maintain current ER flow and keep fast-track option ready.",
            "Open ER fast-track lane." if high_demand or er_gap > 0 else "No ER escalation required.",
            "Critical" if er_gap > 0 and high_demand else "High" if high_demand or er_gap > 0 else "Low",
            "ER / Triage",
            "Lower ER waiting time and improved triage throughput.",
        ),
        row(
            "General Ward overcrowding",
            f"General Ward gap signal = {ward_gap}; bed shortage = {bed_shortage}.",
            "Ward occupancy is high and admissions are increasing." if ward_gap > 0 or bed_shortage > 0 else "Ward pressure is within manageable limits.",
            f"Beds available: {available_beds}; ward gap signal: {ward_gap}.",
            f"Beds required: {required_beds}; nurses required: {required_nurses}.",
            f"Ward gap: {ward_gap}; hospital bed shortage: {bed_shortage}.",
            "Prepare discharge list, transfer stable patients, and delay non-urgent admissions." if ward_gap > 0 or bed_shortage > 0 else "Maintain normal ward admission plan.",
            "Start ward decompression plan." if ward_gap > 0 or bed_shortage > 0 else "Continue routine ward operations.",
            "High" if ward_gap > 0 or bed_shortage > 0 else "Low",
            "General Ward / Admissions",
            "Reduced overcrowding and better admission flow.",
        ),
        row(
            "OR overload",
            f"Estimated OR bookings = {estimated_or_bookings}; estimated OR slots = {estimated_or_slots}.",
            "OR bookings exceed available room/time slots." if or_gap > 0 else "Estimated OR load fits current room/time capacity.",
            f"OR slots: ~{estimated_or_slots} estimated from doctor availability.",
            f"OR demand: ~{estimated_or_bookings} estimated cases.",
            f"OR slot gap: {or_gap} estimated.",
            f"Prioritize emergency surgeries, reschedule {or_gap} elective cases, and extend OR hours if possible." if or_gap > 0 else "Keep current OR schedule and reserve emergency slot buffer.",
            "Reprioritize OR list." if or_gap > 0 else "No OR rescheduling required.",
            "High" if or_gap > 0 else "Medium",
            "Operating Rooms / Surgery / Anesthesia",
            "Emergency procedures protected while elective backlog is controlled.",
        ),
        row(
            "Appointment overload",
            f"Estimated appointments = {estimated_appointments}; estimated capacity = {estimated_appointment_capacity}.",
            "Clinic appointments exceed doctor availability." if appointment_gap > 0 else "Clinic appointment volume is within estimated doctor capacity.",
            f"Appointment capacity: ~{estimated_appointment_capacity} visits.",
            f"Appointment load: ~{estimated_appointments} visits.",
            f"Appointment gap: {appointment_gap} estimated.",
            f"Open extra slots, redistribute appointments, and reschedule {appointment_gap} low-priority visits after 4 PM." if appointment_gap > 0 else "Maintain appointment schedule and keep overflow slots available.",
            "Open clinic overflow schedule." if appointment_gap > 0 else "No appointment rescheduling required.",
            "High" if appointment_gap > 0 else "Low",
            "Outpatient Clinics / Scheduling",
            "Reduced waiting time and fewer same-day scheduling conflicts.",
        ),
        row(
            "Staff absenteeism",
            f"Estimated absent/unavailable staff = {estimated_absent_staff} based on shortage pressure.",
            "Some staff are absent or unavailable." if estimated_absent_staff > 0 else "No absenteeism pressure inferred from current simulation.",
            f"Doctors: {available_doctors}; nurses: ~{estimated_available_nurses} estimated.",
            f"Doctors: {required_doctors}; nurses: {required_nurses}.",
            f"Estimated unavailable staff impact: {estimated_absent_staff}.",
            f"Activate backup roster for {estimated_absent_staff} staff and redistribute available staff to ER/ICU/Ward." if estimated_absent_staff > 0 else "Keep backup roster ready; no activation required.",
            "Activate backup roster." if estimated_absent_staff > 0 else "Maintain current roster.",
            "High" if estimated_absent_staff > 0 else "Low",
            "Staffing Office / All Departments",
            "Coverage restored in high-priority areas.",
        ),
        row(
            "Night shift shortage",
            f"Estimated night required staff = {night_required_staff}; estimated night available staff = {night_available_staff}.",
            "Night shift staff coverage is below required level." if night_gap > 0 else "Estimated night coverage is adequate.",
            f"Night staff available: ~{night_available_staff} estimated.",
            f"Night staff required: ~{night_required_staff} estimated.",
            f"Night shift gap: {night_gap} estimated.",
            f"Move {night_gap} staff from evening backup pool or call night-shift reserve staff." if night_gap > 0 else "Maintain current night-shift plan.",
            "Call night-shift reserve." if night_gap > 0 else "No night-shift escalation required.",
            "High" if night_gap > 0 else "Low",
            "Night Shift / Staffing Office",
            "Safer overnight coverage and reduced response delays.",
        ),
        row(
            "Seasonal demand increase",
            f"Current season = {season_name}; demand increase slider = {demand_pct:.0f}%.",
            "Seasonal pattern indicates higher demand." if moderate_demand else "Seasonal demand pressure is not elevated by current inputs.",
            f"Beds: {available_beds}; doctors: {available_doctors}; nurses: ~{estimated_available_nurses} estimated.",
            f"Beds: {required_beds}; doctors: {required_doctors}; nurses: {required_nurses}.",
            f"Resource gap: beds {bed_shortage}, doctors {doctor_shortage}, nurses {nurse_shortage}.",
            "Prepare staff schedules and bed capacity in advance based on seasonal forecast." if moderate_demand else "Keep seasonal watch and maintain standard staffing.",
            "Pre-plan seasonal capacity." if moderate_demand else "Continue standard seasonal monitoring.",
            "Medium" if moderate_demand else "Low",
            "Hospital Operations / Workforce Planning",
            "Better preparedness for predictable demand variation.",
        ),
        row(
            "Sudden discharge delay",
            f"Bed shortage = {bed_shortage}; estimated waiting patients = {waiting_estimate}.",
            "Patients remain inside hospital longer than expected." if discharge_delay_gap > 0 else "No discharge-delay pressure inferred from current simulation.",
            f"Beds available: {available_beds}; estimated waiting patients: {waiting_estimate}.",
            f"Beds required: {required_beds}; discharge gap target: {discharge_delay_gap}.",
            f"Discharge/bed gap: {discharge_delay_gap}.",
            f"Accelerate discharge approvals for {discharge_delay_gap} stable patients and coordinate billing/clearance." if discharge_delay_gap > 0 else "Continue routine discharge review.",
            "Start discharge acceleration round." if discharge_delay_gap > 0 else "No discharge escalation required.",
            "High" if discharge_delay_gap > 0 else "Low",
            "Discharge Team / Ward / Billing",
            "Faster bed turnover and fewer blocked admissions.",
        ),
        row(
            "High waiting patients",
            f"Estimated waiting patients = {waiting_estimate}; safe threshold = {waiting_threshold}.",
            "Waiting patients exceed safe threshold." if waiting_estimate > waiting_threshold else "Waiting estimate is within safe threshold.",
            f"Doctors: {available_doctors}; consultation capacity proxy: {estimated_appointment_capacity}.",
            f"Doctors needed: {required_doctors}; waiting threshold: {waiting_threshold}.",
            f"Waiting gap: {max(waiting_estimate - waiting_threshold, 0)}.",
            "Increase triage speed, add consultation rooms, and assign extra doctors." if waiting_estimate > waiting_threshold else "Maintain current queue monitoring.",
            "Open additional consultation capacity." if waiting_estimate > waiting_threshold else "No queue escalation required.",
            "High" if waiting_estimate > waiting_threshold else "Low",
            "Waiting Area / Triage / Clinics",
            "Shorter waiting queue and faster patient routing.",
        ),
        row(
            "Low bed occupancy / stable operation",
            "Forecasted demand is within available capacity." if stable_operation else "One or more shortage or surge conditions are active.",
            "No major operational risk." if stable_operation else "Current simulation shows operational pressure.",
            f"Beds: {available_beds}; doctors: {available_doctors}; nurses: ~{estimated_available_nurses} estimated.",
            f"Beds: {required_beds}; doctors: {required_doctors}; nurses: {required_nurses}.",
            f"Beds {bed_shortage}; doctors {doctor_shortage}; nurses {nurse_shortage}.",
            "Maintain current plan and continue monitoring demand." if stable_operation else "Resolve active shortage scenarios before returning to stable plan.",
            "Maintain current plan." if stable_operation else "Do not declare stable operation yet.",
            "Low" if stable_operation else "Medium",
            "Hospital-wide Operations",
            "Stable service levels maintained." if stable_operation else "Risk reduced after targeted interventions.",
        ),
        row(
            "Department-specific shortage",
            f"Largest department gap = {top_dept_gap} in {top_dept}.",
            "A specific department has shortage despite hospital-wide resources." if top_dept_gap > 0 else "No department-specific shortage detected from available signals.",
            "Hospital-wide resources may be available but unevenly distributed.",
            f"Department gap to cover: {top_dept_gap} resource units.",
            f"{top_dept} gap: {top_dept_gap}.",
            f"Transfer staff/resources into {top_dept} based on priority and reduce lower-pressure coverage temporarily." if top_dept_gap > 0 else "Keep department allocations unchanged.",
            "Rebalance resources between departments." if top_dept_gap > 0 else "No department transfer required.",
            "High" if top_dept_gap > 0 else "Low",
            top_dept,
            "Department pressure reduced without unnecessary hospital-wide escalation.",
        ),
        row(
            "High forecast but enough current capacity",
            f"Demand increase = {demand_pct:.0f}%; shortages: beds {bed_shortage}, doctors {doctor_shortage}.",
            "Current state is stable, but forecast shows pressure in next hours." if forecast_pressure_no_shortage else "No early forecast pressure requiring pre-activation.",
            f"Beds: {available_beds}; doctors: {available_doctors}; nurses: ~{estimated_available_nurses} estimated.",
            f"Beds: {required_beds}; doctors: {required_doctors}; nurses: {required_nurses}.",
            "No current shortage, but demand trend is elevated." if forecast_pressure_no_shortage else "No pre-shortage gap detected.",
            "Prepare resources before shortage happens: notify staffing, reserve overflow beds, and pre-check discharge list." if forecast_pressure_no_shortage else "Continue normal readiness checks.",
            "Pre-activate readiness plan." if forecast_pressure_no_shortage else "No pre-activation required.",
            "Medium" if forecast_pressure_no_shortage else "Low",
            "Operations Planning / Bed Management",
            "Shortage prevented before patient flow deteriorates.",
        ),
        row(
            "High resource availability but low demand",
            f"Demand increase = {demand_pct:.0f}%; bed surplus = {max(available_beds - required_beds, 0)}; doctor surplus = {max(available_doctors - required_doctors, 0)}.",
            "More staff/beds than needed." if high_capacity_low_demand else "No major excess capacity detected.",
            f"Beds: {available_beds}; doctors: {available_doctors}; nurses: ~{estimated_available_nurses} estimated.",
            f"Beds needed: {required_beds}; doctors needed: {required_doctors}; nurses needed: {required_nurses}.",
            f"Surplus beds: {max(available_beds - required_beds, 0)}; surplus doctors: {max(available_doctors - required_doctors, 0)}.",
            "Keep reserve capacity, avoid unnecessary overtime, and reassign staff to backlog or preventive tasks." if high_capacity_low_demand else "Maintain balanced staffing.",
            "Avoid overtime expansion; keep reserve capacity." if high_capacity_low_demand else "No resource reduction required.",
            "Low",
            "Hospital-wide Operations / Staffing",
            "Cost controlled while preserving readiness.",
        ),
        row(
            "Multiple simultaneous shortages",
            f"Shortage flags: beds={bed_shortage > 0}, doctors={doctor_shortage > 0}, nurses={nurse_shortage > 0}; demand increase={demand_pct:.0f}%.",
            "Demand surge plus multiple shortages detected." if multiple_shortages else "Multiple shortage condition is not active.",
            f"Beds {available_beds}; doctors {available_doctors}; nurses ~{estimated_available_nurses} estimated.",
            f"Beds {required_beds}; doctors {required_doctors}; nurses {required_nurses}.",
            f"Beds {bed_shortage}; doctors {doctor_shortage}; nurses {nurse_shortage}.",
            "Activate emergency operation plan, open command huddle, prioritize ER/ICU, and suspend non-urgent activity." if multiple_shortages else "Track individual shortage scenarios separately.",
            "Activate emergency operations plan." if multiple_shortages else "No multi-shortage activation required.",
            "Critical" if multiple_shortages else "Low",
            "Hospital-wide / Command Team",
            "Critical services protected during compound pressure.",
        ),
        row(
            "Critical resource conflict",
            f"Beds shortage={bed_shortage}; doctor shortage={doctor_shortage}; nurse shortage={nurse_shortage}.",
            "One resource is the bottleneck while another is sufficient." if resource_conflict else "No single-resource conflict detected.",
            f"Beds {available_beds}; doctors {available_doctors}; nurses ~{estimated_available_nurses} estimated.",
            f"Beds {required_beds}; doctors {required_doctors}; nurses {required_nurses}.",
            f"Bottleneck: {'beds' if bed_shortage > 0 else 'staff' if doctor_shortage > 0 or nurse_shortage > 0 else 'none'}.",
            "If beds are the bottleneck, open overflow/discharge beds; if staff are the bottleneck, call backup staff before adding beds." if resource_conflict else "Keep resource balance unchanged.",
            "Resolve bottleneck before expanding other resources." if resource_conflict else "No bottleneck action required.",
            "High" if resource_conflict else "Low",
            "Bed Management / Staffing Office",
            "Action targets the true limiting resource.",
        ),
    ]

    priority_rank = {"🔴 Critical": 0, "🟠 High": 1, "🟡 Medium": 2, "🟢 Low": 3}
    out = pd.DataFrame(rows)
    out["_priority_rank"] = out["Priority Level"].map(priority_rank).fillna(99)
    return out.sort_values(["_priority_rank", "Scenario"]).drop(columns=["_priority_rank"]).reset_index(drop=True)


def render_operations(*, key_prefix: str = "ops"):
    """Operations tab: live overview (no what-if controls)."""

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    key_prefix = str(key_prefix or "ops").strip() or "ops"

    result = ctx["prediction_result"]
    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})
    allocations = optimization.get("department_allocations", [])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Current patients", int(ctx["current_patients"]), status="info")
    with c2:
        kpi_card("Next-hour forecast", int(ctx["prediction"]), status="normal")
    with c3:
        emergency_level = str(result.get("emergency_level", "LOW"))
        status = "critical" if emergency_level == "HIGH" else "warning" if emergency_level == "MEDIUM" else "success"
        kpi_card("Emergency signal", emergency_level, status=status)
    with c4:
        beds_needed = int(summary.get("beds_needed_total", result["recommended_resources"]["beds_needed"]))
        kpi_card("Beds needed", beds_needed, status="warning" if beds_needed >= 100 else "normal")

    left, right = st.columns([1.35, 1])
    with left:
        with st.container(border=True):
            section_header("Department allocations", "Live optimization snapshot")
            if allocations:
                alloc_df = pd.DataFrame(allocations)
                show_cols = [
                    c
                    for c in [
                        "department",
                        "status",
                        "priority_score",
                        "bed_shortage",
                        "doctor_shortage",
                        "nurse_shortage",
                    ]
                    if c in alloc_df.columns
                ]
                modern_table(
                    alloc_df[show_cols] if show_cols else alloc_df,
                    key=scoped_key(key_prefix, "alloc_table"),
                )
            else:
                empty_state("No optimization allocations available.")

        if allocations:
            alloc_df = pd.DataFrame(allocations)
            with st.container(border=True):
                section_header("Pressure ranking")
                if "priority_score" in alloc_df.columns and "department" in alloc_df.columns:
                    fig_priority = px.bar(
                        alloc_df,
                        x="department",
                        y="priority_score",
                        color="status" if "status" in alloc_df.columns else None,
                        title="",
                    )
                    fig_priority.update_layout(height=360, yaxis_title="Priority score", xaxis_title="")
                    st.plotly_chart(
                        fig_priority,
                        use_container_width=True,
                        key=scoped_key(key_prefix, "pressure_ranking"),
                    )

    with right:
        with st.container(border=True):
            section_header("24-hour peak")
            peak = float(ctx.get("peak") or ctx["prediction"])
            kpi_card("Peak forecast", int(peak), status="warning" if peak >= 120 else "normal")
            st.caption("Open Forecast page for the full 24-hour curve.")

        with st.container(border=True):
            section_header("Capacity context", "Derived from the latest optimization run")
            capacity_df = _build_capacity_from_allocations(list(allocations or []))
            if capacity_df.empty:
                empty_state("Capacity context not available.")
            else:
                modern_table(capacity_df, key=scoped_key(key_prefix, "capacity_table"))


def render_simulation(*, key_prefix: str = "sim"):
    """Simulation tab: what-if sliders + scenario outputs."""

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    prediction = float(ctx["prediction"])
    key_prefix = str(key_prefix or "sim").strip() or "sim"

    with st.container(border=True):
        section_header("Scenario controls")
        c1, c2, c3 = st.columns(3)
        demand = c1.slider("Demand increase (%)", 0, 100, 20, key=scoped_key(key_prefix, "demand"))
        beds = c2.slider("Available beds", 50, 300, 120, key=scoped_key(key_prefix, "beds"))
        doctors = c3.slider("Available doctors", 5, 50, 15, key=scoped_key(key_prefix, "doctors"))

    sim = simulate(prediction, beds, doctors, demand)
    if sim:
        s1, s2, s3 = st.columns(3)
        with s1:
            kpi_card("Simulated patients", fmt_patients(sim["simulated_patients"]), status="info")
        with s2:
            level = str(sim.get("emergency_level", "LOW"))
            status = "critical" if level == "HIGH" else "warning" if level == "MEDIUM" else "success"
            kpi_card("Emergency signal", level, status=status)
        with s3:
            shortage = int(sim.get("doctor_shortage") or 0)
            kpi_card("Doctor shortage", fmt_int(shortage), status="warning" if shortage > 0 else "success")

        left, right = st.columns(2)
        with left:
            with st.container(border=True):
                section_header("Bed allocation")
                st.json(sim["bed_allocation"])
        with right:
            with st.container(border=True):
                section_header("Recommended resources")
                st.json(sim["recommended_resources"])

    # Capacity view derived from allocations.
    optimization = ctx.get("optimization") or {}
    allocations = optimization.get("department_allocations", [])
    capacity_df = _build_capacity_from_allocations(list(allocations or []))

    scenario_df = _build_simulation_scenario_analysis(
        prediction=prediction,
        demand_increase_pct=float(demand),
        available_beds=int(beds),
        available_doctors=int(doctors),
        sim=sim if isinstance(sim, dict) else None,
        capacity_df=capacity_df,
    )
    with st.container(border=True):
        section_header(
            "What-if Scenario Analysis",
            "This table shows simulated hospital scenarios, expected shortages, required resources, and recommended operational decisions.",
        )
        summary_report_df, summary_report_text = _build_scenario_summary_report(scenario_df)
        total_scenarios = int(len(scenario_df))
        critical_high = int(summary_report_df.loc[summary_report_df["Metric"] == "Critical/high priority scenarios", "Value"].iloc[0]) if not summary_report_df.empty else 0
        top_area = str(summary_report_df.loc[summary_report_df["Metric"] == "Top affected departments/areas", "Value"].iloc[0]) if not summary_report_df.empty else "-"

        w1, w2, w3 = st.columns(3)
        with w1:
            kpi_card("Total scenarios", fmt_int(total_scenarios), status="info")
        with w2:
            kpi_card("Critical/high priority", fmt_int(critical_high), status="warning" if critical_high else "success")
        with w3:
            kpi_card("Full table columns", fmt_int(len(scenario_df.columns)), delta="CSV-driven UI", status="info")

        section_header("Scenario summary report", "Compact operational view from the dynamic scenario outputs")
        modern_table(summary_report_df, key=scoped_key(key_prefix, "scenario_summary_report"))
        st.caption(f"Top affected areas: {top_area}")
        c_download_1, c_download_2 = st.columns(2)
        with c_download_1:
            st.download_button(
                "Download full scenario table (CSV)",
                data=scenario_df.to_csv(index=False).encode("utf-8"),
                file_name="what_if_scenario_analysis.csv",
                mime="text/csv",
                key=scoped_key(key_prefix, "scenario_full_csv_download"),
            )
        with c_download_2:
            st.download_button(
                "Download summary report (text)",
                data=summary_report_text.encode("utf-8"),
                file_name="what_if_scenario_summary.txt",
                mime="text/plain",
                key=scoped_key(key_prefix, "scenario_summary_text_download"),
            )

        compact_cols = [c for c in ["Scenario", "Priority Level", "Affected Department / Area", "Shortage / Gap", "Operational Decision"] if c in scenario_df.columns]
        section_header("Compact scenario view", "Top priority scenarios first")
        modern_table(scenario_df[compact_cols].head(12) if compact_cols else scenario_df.head(12), key=scoped_key(key_prefix, "scenario_compact_table"))

        with st.expander("Show full 11-column scenario table", expanded=False):
            st.caption("The full table preserves the existing CSV-driven dynamic logic and all 11 UI columns.")
            modern_table(scenario_df, key=scoped_key(key_prefix, "scenario_analysis_table"))

    with st.container(border=True):
        section_header("Capacity context", "Derived from the latest optimization run")
        if capacity_df.empty:
            empty_state("Capacity context not available.")
        else:
            modern_table(_round_display_dataframe(capacity_df), key=scoped_key(key_prefix, "capacity_table"))

    if not capacity_df.empty:
        # Visualize requirement vs availability estimate.
        chart_df = capacity_df.copy()
        # Align naming in chart.
        if "beds_available_est" in chart_df.columns:
            fig_dept = px.bar(
                chart_df,
                x="department",
                y=[c for c in ["beds_required", "beds_available_est", "bed_shortage"] if c in chart_df.columns],
                barmode="group",
                title="",
            )
            fig_dept.update_layout(height=380, xaxis_title="")
            with st.container(border=True):
                section_header("Beds requirement vs availability")
                st.plotly_chart(fig_dept, use_container_width=True, key=scoped_key(key_prefix, "fig_dept"))


def render_digital_twin(*, key_prefix: str = "twin"):
    """Digital twin tab: system mirror + multistep forecast probe."""

    key_prefix = str(key_prefix or "twin").strip() or "twin"

    state = _dashboard_forecast_state_from_live_context()
    ops72h = _load_ops72h_outputs(state)
    if not ops72h.get("ready"):
        _show_ops72h_missing_state(ops72h)
        return

    overall_df = ops72h["overall"].copy().sort_values("datetime").reset_index(drop=True)
    department_df = ops72h["department"].copy().sort_values(["department", "datetime"]).reset_index(drop=True)
    summary = ops72h["summary"] or {}
    state = ops72h.get("state") or state

    if overall_df.empty:
        empty_state("72-hour overall forecast output is empty.")
        return

    forecast_values = digital_twin_source_series(state) or overall_df["hybrid_pred"].astype(float).tolist()
    dept_options = ["All"]
    if not department_df.empty and "department" in department_df.columns:
        dept_options += sorted([str(d) for d in department_df["department"].dropna().unique().tolist()])

    selected_dept = st.selectbox(
        "View forecast",
        dept_options,
        index=0,
        key=scoped_key(key_prefix, "dept_selector"),
        help="All = saved overall Hybrid forecast. Per-department uses the saved 72h department forecast output.",
    )

    if selected_dept == "All":
        plot_df = overall_df[["datetime", "hybrid_pred"]].copy()
        series_name = "Overall Hybrid forecast"
    else:
        plot_df = department_df[department_df["department"].astype(str) == str(selected_dept)][["datetime", "hybrid_pred"]].copy()
        series_name = f"{selected_dept} Hybrid forecast"
    if plot_df.empty:
        empty_state("Selected 72-hour forecast view is empty.")
        return

    plot_values = plot_df["hybrid_pred"].astype(float).tolist()

    horizon = st.select_slider(
        "Twin horizon (hours ahead)",
        options=list(range(1, len(plot_values) + 1)),
        value=1,
        key=scoped_key(key_prefix, "horizon"),
    )
    predicted_at_h = float(plot_values[int(horizon) - 1])
    st.caption(
        f"Current view: {series_name}. The +{horizon}h KPI, chart, and table below are all based on this selected department/view and saved 72-hour horizon."
    )

    weights = summary.get("weights") or {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Best model", _model_name(summary.get("best_model") or "Hybrid"), status="success")
    with c2:
        kpi_card(f"+{horizon}h", fmt_patients(predicted_at_h), status="normal")
    with c3:
        peak = float(max(plot_values))
        kpi_card("72h peak", fmt_patients(peak), status="warning" if peak >= 120 else "normal")
    with c4:
        kpi_card("Weights", f"LSTM {fmt_weight(weights.get('lstm', 0.0))} / ARIMAX {fmt_weight(weights.get('arimax', 0.0))}", status="info")

    twin_df = pd.DataFrame({
        "hour": list(range(1, len(plot_values) + 1)),
        "datetime": plot_df["datetime"].values,
        series_name: plot_values,
    })
    twin_chart_df = twin_df.copy()
    twin_chart_df[series_name] = pd.to_numeric(twin_chart_df[series_name], errors="coerce").round(0)
    fig = px.area(twin_chart_df, x="datetime", y=series_name, title=f"Digital Twin forecast: {series_name}")
    fig.update_traces(
        line=dict(color="rgba(99,102,241,0.95)", width=3),
        fillcolor="rgba(99,102,241,0.16)",
    )
    fig.update_layout(height=320, xaxis_title="Forecast time", yaxis_title="Predicted patients", margin=dict(l=10, r=10, t=10, b=10))
    fig.update_traces(hovertemplate="%{x}<br>%{y:.0f} patients<extra></extra>")
    st.plotly_chart(fig, use_container_width=True, key=scoped_key(key_prefix, "forecast_curve"))

    display_twin_df = _round_display_dataframe(twin_df)
    display_twin_df["Selected horizon"] = ["◀ selected" if int(h) == int(horizon) else "" for h in display_twin_df["hour"]]
    modern_table(display_twin_df, key=scoped_key(key_prefix, "forecast_table"))

    stable_note = _stable_tail_note(plot_values, label=series_name)
    if stable_note:
        st.info(stable_note)

    # Peak pressure across the full 72-hour window (multi-step)
    if plot_values:
        peak_h = int(np.argmax(np.array(plot_values, dtype=float)) + 1)
        st.caption(f"Peak within 72h occurs at +{peak_h}h (based on the saved Hybrid forecast output).")


def render_department_status(*, key_prefix: str = "dept"):
    """Department status tab: per-department breakdown from optimization allocations."""

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    key_prefix = str(key_prefix or "dept").strip() or "dept"
    optimization = ctx["optimization"]
    allocations = optimization.get("department_allocations", [])
    if not allocations:
        empty_state("No department allocation data available.")
        return

    alloc_df = pd.DataFrame(allocations)
    if "department" not in alloc_df.columns:
        modern_table(alloc_df, key=scoped_key(key_prefix, "alloc_table"))
        return

    departments = [str(d) for d in alloc_df["department"].dropna().unique().tolist()]
    departments = sorted(departments)
    selected = st.selectbox(
        "Department",
        departments,
        index=0,
        key=scoped_key(key_prefix, "department_selector"),
    )
    row = alloc_df[alloc_df["department"] == selected].head(1)
    if row.empty:
        empty_state("Department not found.")
        return

    r = row.iloc[0].to_dict()

    # Refactored: drive Department Status from optimization results.
    # Flow: current hospital state (available via optimizer inputs) + forecast (optimizer's modeled demand)
    # -> required resources -> shortages = needed - available.
    def _n(x):
        try:
            return float(pd.to_numeric(x, errors="coerce"))
        except Exception:
            return 0.0

    beds_needed = int(_n(r.get("beds_required")))
    doctors_needed = int(_n(r.get("doctors_required")))
    nurses_needed = int(_n(r.get("nurses_required")))

    bed_shortage = int(max(0, _n(r.get("bed_shortage"))))
    doctor_shortage = int(max(0, _n(r.get("doctor_shortage"))))
    nurse_shortage = int(max(0, _n(r.get("nurse_shortage"))))

    # Available = needed - shortage (best-effort; true availability is internal to the optimizer).
    # Note: `effective_beds_capacity` is computed by the optimizer using PatientTracking
    # occupancy; we keep this fallback for backward compatibility.
    beds_available = int(max(0, beds_needed - bed_shortage))
    doctors_available = int(max(0, doctors_needed - doctor_shortage))
    nurses_available = int(max(0, nurses_needed - nurse_shortage))

    # Pressure/status derived from real shortage magnitudes.
    total_shortage = bed_shortage * 3 + doctor_shortage * 2 + nurse_shortage * 2
    if bed_shortage > 0 or doctor_shortage > 0 or nurse_shortage > 0:
        computed_status = "warning" if total_shortage < 10 else "critical"
    else:
        computed_status = "stable"

    c1, c2, c3 = st.columns(3)
    with c1:
        status_color = "success" if computed_status == "stable" else "warning" if computed_status == "warning" else "critical"
        kpi_card("Status", computed_status.upper(), status=status_color)
    with c2:
        kpi_card("Pressure score", int(total_shortage), status="warning" if computed_status != "stable" else "success")
    with c3:
        kpi_card("Priority", f"{_n(r.get('priority_score')):.1f}" if r.get("priority_score") is not None else "-", status="info")

    section_header("Resources", "Needed vs available vs shortage (optimization-driven)")
    r1, r2, r3 = st.columns(3)
    with r1:
        with st.container(border=True):
            st.subheader("Beds")
            st.metric("Needed", beds_needed)
            st.metric("Available", beds_available)
            st.metric("Shortage", bed_shortage)
    with r2:
        with st.container(border=True):
            st.subheader("Doctors")
            st.metric("Needed", doctors_needed)
            st.metric("Available", doctors_available)
            st.metric("Shortage", doctor_shortage)
    with r3:
        with st.container(border=True):
            st.subheader("Nurses")
            st.metric("Needed", nurses_needed)
            st.metric("Available", nurses_available)
            st.metric("Shortage", nurse_shortage)

    # Keep the table grounded in optimizer output, but include required fields when present.
    show_cols = [
        c
        for c in [
            "department",
            "status",
            "priority_score",
            "current_patients",
            "waiting_patients",
            "occupied_beds",
            "beds_required",
            "effective_beds_capacity",
            "bed_shortage",
            "doctors_required",
            "doctor_shortage",
            "nurses_required",
            "nurse_shortage",
        ]
        if c in alloc_df.columns
    ]
    with st.container(border=True):
        section_header("All departments")
        modern_table(alloc_df[show_cols] if show_cols else alloc_df, key=scoped_key(key_prefix, "alloc_table"))

    shortage_cols = ["bed_shortage", "doctor_shortage", "nurse_shortage"]
    if all(c in alloc_df.columns for c in shortage_cols):
        chart_df = alloc_df[["department"] + shortage_cols].copy()
        fig = px.bar(chart_df, x="department", y=shortage_cols, barmode="group", title="")
        fig.update_layout(height=380, xaxis_title="")
        st.plotly_chart(fig, use_container_width=True, key=scoped_key(key_prefix, "shortages_chart"))


def show_operations_center(*, key_prefix: str = "ops"):
    page_header(
        "Operations Center",
        "Live overview: demand signals, allocations, and capacity context.",
    )
    render_operations(key_prefix=key_prefix)


def show_evaluation_panel():
    page_header("Evaluation", "Model comparison with MAE/RMSE as primary decision metrics and MAPE shown as a caution metric.")

    state = _dashboard_forecast_state_from_live_context()
    split = st.radio(
        "Evaluation Split",
        ["test", "validation"],
        horizontal=True,
        key="eval_split_selector",
    )

    eval_df = evaluation_source_metrics(state) if split == "test" else build_metrics_dataframe(split=split)
    detailed_df = build_detailed_predictions_dataframe(split=split)

    if eval_df.empty:
        empty_state("Evaluation files not found. Run the v2 training pipeline first.")
        return

    st.caption("Evaluation test metrics are sourced from the same canonical ForecastState metrics table used by Forecast and API artifact status.")

    display_eval_df = _round_display_dataframe(eval_df)
    modern_table(display_eval_df, key=scoped_key("evaluation", "metrics_table"))

    best_model_row = eval_df.sort_values("RMSE", ascending=True).iloc[0]
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        kpi_card("Best model by RMSE", _model_name(best_model_row.get("Model")), status="success")
    with e2:
        kpi_card("Primary: RMSE", fmt_mae_rmse(best_model_row.get("RMSE")), status="success")
    with e3:
        kpi_card("Primary: MAE", fmt_mae_rmse(best_model_row.get("MAE")), status="normal")
    with e4:
        kpi_card("Secondary: MAPE", fmt_mape(best_model_row.get("MAPE")), status="warning")

    alert_box(
        f"Best model is selected using the lowest RMSE: {_model_name(best_model_row.get('Model'))}. RMSE and MAE are emphasized because they are errors in patient-count units.",
        "success",
    )

    # Notes about metric interpretation (important for operational throughput experiments)
    st.warning(
        "MAPE is still visible, but it is a secondary caution metric. It can become visually very high when actual patient counts are low or near zero, even when absolute patient-count error is more manageable."
    )
    st.caption(
        "ARIMAX may produce convergence warnings during training; this is a training limitation and is reported as such (not hidden)."
    )


    primary_cols = [c for c in ["MAE", "RMSE"] if c in eval_df.columns]
    fig_metrics = px.bar(
        eval_df,
        x="Model",
        y=primary_cols,
        barmode="group",
        title="Primary forecast error metrics: MAE/RMSE",
    )
    fig_metrics.update_layout(height=420, yaxis_title="Error in patient-count units")
    st.plotly_chart(fig_metrics, use_container_width=True, key=scoped_key("evaluation", "metrics"))

    if "MAPE" in eval_df.columns:
        fig_mape = px.bar(eval_df, x="Model", y="MAPE", title="Secondary caution metric: MAPE")
        fig_mape.update_layout(height=300, yaxis_title="MAPE (%)")
        st.plotly_chart(fig_mape, use_container_width=True, key=scoped_key("evaluation", "mape_secondary"))

    required_cols = ["time_index", "actual", "lstm_pred", "arimax_pred", "hybrid_pred"]
    if not detailed_df.empty and all(col in detailed_df.columns for col in required_cols):
        clean_df = detailed_df[required_cols].copy()

        for col in required_cols:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

        clean_df = clean_df.dropna(subset=["actual", "lstm_pred", "arimax_pred", "hybrid_pred"])

        if clean_df.empty:
            empty_state("Detailed evaluation outputs are empty after cleaning.")
            return

        plot_df = clean_df.melt(
            id_vars="time_index",
            value_vars=["actual", "lstm_pred", "arimax_pred", "hybrid_pred"],
            var_name="series",
            value_name="value",
        )

        plot_df["value"] = pd.to_numeric(plot_df["value"], errors="coerce").round(0)
        fig_compare = px.line(
            plot_df,
            x="time_index",
            y="value",
            color="series",
            title="Actual vs forecasted patient flow (rounded patient counts)",
        )
        fig_compare.update_layout(height=450, yaxis_title="Patients", xaxis_title="Time index")
        fig_compare.update_traces(hovertemplate="Time %{x}<br>%{fullData.name}: %{y:.0f} patients<extra></extra>")
        st.plotly_chart(fig_compare, use_container_width=True, key=scoped_key("evaluation", "actual_vs_models"))

        modern_table(_round_display_dataframe(clean_df.tail(50)), key=scoped_key("evaluation", "tail_table"))
    else:
        empty_state("Detailed evaluation outputs are not available yet.")


def show_explainability_panel():
    page_header("Model Feature Sensitivity", "Readable explanation of which inputs increase or reduce forecast pressure.")

    # Small operational narrative (rule-based) so operators can map the model sensitivity
    # to day-to-day pressure drivers. This never overwrites model-based outputs.
    st.subheader("How to read this")
    st.caption(
        "Positive impact increases forecast pressure. Negative impact reduces forecast pressure. "
        "This is model feature sensitivity from the existing explainability service; it is not labeled as SHAP."
    )


    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    explanation = explain_prediction(ctx["last_sequence"])
    if explanation is None or "feature_impacts" not in explanation:
        empty_state("Explainability service unavailable.")
        return

    base_prediction = explanation["base_prediction"]
    impacts = explanation["feature_impacts"]

    kpi_card("Base prediction", fmt_patients(base_prediction), delta="patients", status="info")

    impact_df = pd.DataFrame(impacts)
    if impact_df.empty:
        empty_state("No explainability impacts available.")
        return

    impact_df["impact"] = pd.to_numeric(impact_df["impact"], errors="coerce").fillna(0.0)
    impact_df["abs_impact"] = impact_df["impact"].abs()
    impact_df["Feature"] = impact_df["feature"].apply(_friendly_feature_label)
    impact_df["Direction"] = np.where(impact_df["impact"] >= 0, "Increases forecast pressure", "Reduces forecast pressure")
    impact_df["Impact"] = impact_df["impact"].round(2)
    impact_df["Plain-English meaning"] = impact_df.apply(lambda r: _feature_meaning(str(r.get("feature")), str(r.get("Direction"))), axis=1)
    top_df = impact_df.sort_values(by="abs_impact", ascending=False).head(12).copy()

    inc_df = top_df[top_df["impact"] >= 0].sort_values("impact", ascending=True)
    red_df = top_df[top_df["impact"] < 0].sort_values("impact", ascending=True)
    c_inc, c_red = st.columns(2)
    with c_inc:
        section_header("Pressure-increasing drivers", "Positive impact")
        if inc_df.empty:
            empty_state("No positive drivers in the top features.")
        else:
            fig_inc = px.bar(
                inc_df,
                x="Impact",
                y="Feature",
                orientation="h",
                title="Top pressure-increasing features",
            )
            fig_inc.update_layout(height=380, xaxis_title="Impact", yaxis_title="")
            fig_inc.update_traces(hovertemplate="%{y}<br>Impact: %{x:.2f}<extra></extra>")
            st.plotly_chart(fig_inc, use_container_width=True, key=scoped_key("explainability", "feature_impacts_positive"))
    with c_red:
        section_header("Pressure-reducing drivers", "Negative impact")
        if red_df.empty:
            empty_state("No negative drivers in the top features.")
        else:
            fig_red = px.bar(
                red_df,
                x="Impact",
                y="Feature",
                orientation="h",
                title="Top pressure-reducing features",
            )
            fig_red.update_layout(height=380, xaxis_title="Impact", yaxis_title="")
            fig_red.update_traces(hovertemplate="%{y}<br>Impact: %{x:.2f}<extra></extra>")
            st.plotly_chart(fig_red, use_container_width=True, key=scoped_key("explainability", "feature_impacts_negative"))

    table_cols = ["Feature", "Direction", "Impact", "Plain-English meaning"]
    modern_table(top_df[table_cols], key=scoped_key("explainability", "impact_table"))


def show_simulation():
    page_header(
        "Simulation",
        "What-if analysis: simulate demand shocks and visualize capacity impact.",
    )
    render_simulation(key_prefix="sim")


def show_digital_twin():
    page_header(
        "Digital Twin",
        "System mirror: probe multistep forecasts and peak pressure ahead.",
    )
    render_digital_twin(key_prefix="twin")


def show_department_status():
    page_header(
        "Department Status",
        "Department-by-department shortages and priority breakdown.",
    )
    render_department_status(key_prefix="dept")
