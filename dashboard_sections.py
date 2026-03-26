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
from evaluation_service import build_detailed_predictions_dataframe, build_metrics_dataframe
from forecast_runtime import generate_multistep_forecast
from ui_components import (
    alert_box,
    empty_state,
    kpi_card,
    modern_table,
    page_header,
    scoped_key,
    section_header,
    status_badge,
)


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
    optimization = get_optimization(prediction) or {}
    forecast_values = generate_multistep_forecast(
        last_sequence=last_sequence,
        predict_fn=get_prediction,
        steps=24,
    )
    peak = float(max(forecast_values)) if forecast_values else prediction

    return {
        "ready": True,
        "df": df,
        "last_sequence": last_sequence,
        "feature_columns": feature_columns,
        "sequence_length": sequence_length,
        "prediction_result": result,
        "prediction": prediction,
        "current_patients": current_patients,
        "optimization": optimization,
        "peak": peak,
        "forecast_values": forecast_values,
    }


def show_overview():
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    result = ctx["prediction_result"]
    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})

    # ------------------------------------------------------------
    # SUMMARY (3-second understanding)
    # ------------------------------------------------------------
    section_header("Summary", "Current load, short-horizon forecast, and capacity signal")

    # KPI row: 4–6 top metrics
    emergency_level = result.get("emergency_level", "LOW")
    risk_status = "critical" if emergency_level == "HIGH" else "warning" if emergency_level == "MEDIUM" else "success"
    beds_needed_total = int(summary.get("beds_needed_total", result["recommended_resources"]["beds_needed"]))
    doctors_needed_total = int(summary.get("doctors_needed_total", result["recommended_resources"]["doctors_needed"]))

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        kpi_card("Total patients", ctx["current_patients"], status="info")
    with k2:
        kpi_card("Next-hour forecast", int(ctx["prediction"]), status="normal")
    with k3:
        kpi_card("24h peak", int(ctx.get("peak") or ctx["prediction"]), status="warning" if float(ctx.get("peak") or 0) >= 120 else "normal")
    with k4:
        kpi_card("Beds needed", beds_needed_total, delta="system-wide", status="warning")
    with k5:
        kpi_card("Risk signal", emergency_level, delta="pressure", status=risk_status)

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
        "Demand outlook across the next 24 hours — trends, peaks, and actual vs predicted.",
    )

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    df = ctx["df"]
    predictions = ctx["forecast_values"]

    if len(predictions) == 0:
        empty_state("Forecast unavailable.")
        return

    forecast_df = pd.DataFrame({
        "hour": range(1, len(predictions) + 1),
        "forecast": predictions,
    })

    # Summary KPIs
    peak = float(max(predictions))
    next_hour = float(predictions[0])
    avg_24h = float(np.mean(predictions))
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Next hour", int(next_hour), status="info")
    with k2:
        kpi_card("24h peak", int(peak), status="warning" if peak >= 100 else "normal")
    with k3:
        kpi_card("24h average", int(avg_24h), status="normal")
    with k4:
        trend = float(predictions[-1] - predictions[0])
        kpi_card("Trend", f"{trend:+.1f}", delta="end − start", status="warning" if trend > 5 else "success" if trend < -5 else "normal")

    section_header("Forecast charts")
    col1, col2 = st.columns(2)

    with col1:
        if not df.empty:
            hist_df = df.copy().reset_index(drop=True)
            hist_df["time_index"] = hist_df.index

            fig_hist = px.line(
                hist_df,
                x="time_index",
                y="patients",
                title="Historical Patients",
            )
            fig_hist.update_layout(height=350, xaxis_title="Time", yaxis_title="Patients")
            st.plotly_chart(fig_hist, use_container_width=True, key=scoped_key("forecast", "hist_patients"))
        else:
            empty_state("Historical data unavailable.")

    with col2:
        fig_forecast = px.line(
            forecast_df,
            x="hour",
            y="forecast",
            markers=True,
            title="24-Hour AI Forecast",
        )
        fig_forecast.update_layout(height=350, xaxis_title="Next hours", yaxis_title="Predicted patients")
        st.plotly_chart(fig_forecast, use_container_width=True, key=scoped_key("forecast", "forecast_24h"))

    if not df.empty:
        actual = df["patients"].tail(len(predictions)).values.astype(float)
        forecast_vals = np.array(predictions, dtype=float)

        min_len = min(len(actual), len(forecast_vals))
        compare_df = pd.DataFrame({
            "time_index": list(range(min_len)),
            "Actual": actual[:min_len],
            "Forecast": forecast_vals[:min_len],
        })

        fig_compare = px.line(
            compare_df,
            x="time_index",
            y=["Actual", "Forecast"],
            title="Actual vs Forecast",
        )
        fig_compare.update_layout(height=350, xaxis_title="Window", yaxis_title="Patients")
        st.plotly_chart(fig_compare, use_container_width=True, key=scoped_key("forecast", "actual_vs_forecast"))


def show_optimization():
    page_header(
        "Optimization",
        "AI-powered resource optimization — allocations, shortages, and recommended actions.",
    )

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

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
            kpi_card("Simulated patients", int(sim["simulated_patients"]), status="info")
        with s2:
            level = str(sim.get("emergency_level", "LOW"))
            status = "critical" if level == "HIGH" else "warning" if level == "MEDIUM" else "success"
            kpi_card("Emergency signal", level, status=status)
        with s3:
            shortage = int(sim.get("doctor_shortage") or 0)
            kpi_card("Doctor shortage", shortage, status="warning" if shortage > 0 else "success")

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
    with st.container(border=True):
        section_header("Capacity context", "Derived from the latest optimization run")
        if capacity_df.empty:
            empty_state("Capacity context not available.")
        else:
            modern_table(capacity_df, key=scoped_key(key_prefix, "capacity_table"))

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

    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    key_prefix = str(key_prefix or "twin").strip() or "twin"
    forecast_values = list(ctx.get("forecast_values") or [])
    if not forecast_values:
        empty_state("Forecast values unavailable.")
        return

    horizon = st.select_slider(
        "Twin horizon (hours ahead)",
        options=list(range(1, len(forecast_values) + 1)),
        value=1,
        key=scoped_key(key_prefix, "horizon"),
    )
    predicted_at_h = float(forecast_values[int(horizon) - 1])

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Now", int(ctx["current_patients"]), status="info")
    with c2:
        kpi_card(f"+{horizon}h", int(predicted_at_h), status="normal")
    with c3:
        peak = float(max(forecast_values))
        kpi_card("24h peak", int(peak), status="warning" if peak >= 120 else "normal")

    twin_df = pd.DataFrame({
        "hour": list(range(1, len(forecast_values) + 1)),
        "forecast": forecast_values,
    })
    fig = px.area(twin_df, x="hour", y="forecast", title="")
    fig.update_traces(
        line=dict(color="rgba(91,92,255,0.95)", width=3),
        fillcolor="rgba(91,92,255,0.14)",
    )
    fig.update_layout(height=320, xaxis_title="Next hours", yaxis_title="Predicted patients", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True, key=scoped_key(key_prefix, "forecast_curve"))


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
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Status", str(r.get("status", "-")).upper(), status="warning" if str(r.get("status", "")).lower() in {"warning", "critical"} else "success")
    with c2:
        kpi_card("Bed shortage", int(r.get("bed_shortage") or 0), status="warning" if int(r.get("bed_shortage") or 0) > 0 else "success")
    with c3:
        kpi_card("Doctor shortage", int(r.get("doctor_shortage") or 0), status="warning" if int(r.get("doctor_shortage") or 0) > 0 else "success")
    with c4:
        kpi_card("Nurse shortage", int(r.get("nurse_shortage") or 0), status="warning" if int(r.get("nurse_shortage") or 0) > 0 else "success")

    show_cols = [c for c in ["department", "status", "priority_score", "bed_shortage", "doctor_shortage", "nurse_shortage"] if c in alloc_df.columns]
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
    page_header("Evaluation", "Model comparison and offline metrics (v2 outputs).")

    split = st.radio(
        "Evaluation Split",
        ["test", "validation"],
        horizontal=True,
        key="eval_split_selector",
    )

    eval_df = build_metrics_dataframe(split=split)
    detailed_df = build_detailed_predictions_dataframe(split=split)

    if eval_df.empty:
        empty_state("Evaluation files not found. Run the v2 training pipeline first.")
        return

    modern_table(eval_df.round(4))

    best_model_row = eval_df.sort_values("RMSE", ascending=True).iloc[0]
    st.success(
        f"Best model currently: {best_model_row['Model']} | "
        f"RMSE = {best_model_row['RMSE']:.4f}, "
        f"MAE = {best_model_row['MAE']:.4f}, "
        f"MAPE = {best_model_row['MAPE']:.2f}%"
    )

    fig_metrics = px.bar(
        eval_df,
        x="Model",
        y=["MAE", "RMSE", "MAPE"],
        barmode="group",
        title="Forecast Error Metrics",
    )
    fig_metrics.update_layout(height=420)
    st.plotly_chart(fig_metrics, use_container_width=True, key=scoped_key("evaluation", "metrics"))

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

        fig_compare = px.line(
            plot_df,
            x="time_index",
            y="value",
            color="series",
            title="Actual vs Forecasted Patient Flow",
        )
        fig_compare.update_layout(height=450)
        st.plotly_chart(fig_compare, use_container_width=True, key=scoped_key("evaluation", "actual_vs_models"))

        modern_table(clean_df.tail(50), key=scoped_key("evaluation", "tail_table"))
    else:
        empty_state("Detailed evaluation outputs are not available yet.")


def show_explainability_panel():
    page_header("Explainability", "Feature sensitivity analysis for the current forecast input.")

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

    st.metric("Base Prediction", int(base_prediction))

    impact_df = pd.DataFrame(impacts)
    if impact_df.empty:
        empty_state("No explainability impacts available.")
        return

    impact_df["abs_impact"] = impact_df["impact"].abs()

    fig = px.bar(
        impact_df,
        x="feature",
        y="impact",
        title="Feature Impact on Prediction",
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("explainability", "feature_impacts"))

    modern_table(impact_df.sort_values(by="abs_impact", ascending=False), key=scoped_key("explainability", "impact_table"))


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