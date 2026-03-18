import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import (
    explain_prediction,
    get_feature_config,
    get_latest_sequence,
    get_optimization,
    get_prediction,
    get_system_status,
    simulate,
)
from evaluation_service import build_detailed_predictions_dataframe, build_metrics_dataframe
from forecast_runtime import generate_multistep_forecast
from ui_components import alert_box, empty_state, kpi_card, modern_table, section_header


def _load_runtime_dataframe():
    for path in ["engineered_data.csv", "clean_data.csv"]:
        if os.path.exists(path):
            df = pd.read_csv(path)
            if "patients" in df.columns:
                return df
    return pd.DataFrame()


def _load_runtime_sequence(df: pd.DataFrame):
    latest_sequence = get_latest_sequence()
    feature_config = get_feature_config() or {}
    feature_columns = feature_config.get("feature_columns", [])
    sequence_length = int(feature_config.get("sequence_length", 24))

    if latest_sequence is not None:
        arr = np.array(latest_sequence, dtype=float)
        expected_shape = (sequence_length, len(feature_columns))
        if arr.shape == expected_shape:
            return arr, feature_columns, sequence_length

    if df.empty or not feature_columns:
        return None, feature_columns, sequence_length

    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        return None, feature_columns, sequence_length

    df = df.copy()
    for col in feature_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=feature_columns).reset_index(drop=True)

    if len(df) < sequence_length:
        return None, feature_columns, sequence_length

    return df[feature_columns].tail(sequence_length).values.astype(float), feature_columns, sequence_length


def get_live_context():
    df = _load_runtime_dataframe()
    last_sequence, feature_columns, sequence_length = _load_runtime_sequence(df)

    if last_sequence is None:
        return {"ready": False, "reason": "Latest model input sequence could not be loaded.", "df": df}

    result = get_prediction(last_sequence)
    if not result:
        return {"ready": False, "reason": "Prediction API is not reachable.", "df": df}

    patients_idx = feature_columns.index("patients") if "patients" in feature_columns else 0
    current_patients = int(last_sequence[-1][patients_idx])
    prediction = float(result["predicted_patients_next_hour"])
    optimization = get_optimization(prediction) or {}
    forecast_values = generate_multistep_forecast(last_sequence=last_sequence, predict_fn=get_prediction, steps=24)
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
    section_header("🏥 Hospital Overview", "Live system summary, pressure status, and AI forecast snapshot.")
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    result = ctx["prediction_result"]
    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Current Patients", ctx["current_patients"], status="normal")
    with c2:
        kpi_card("Next Hour Forecast", int(ctx["prediction"]), status="normal")
    with c3:
        kpi_card(
            "Beds Needed",
            int(summary.get("beds_needed_total", result["recommended_resources"]["beds_needed"])),
            status="warning",
        )
    with c4:
        emergency_level = result.get("emergency_level", "LOW")
        status = "critical" if emergency_level == "HIGH" else "warning" if emergency_level == "MEDIUM" else "normal"
        kpi_card("Emergency Level", emergency_level, status=status)

    emergency_level = result.get("emergency_level", "LOW")
    if emergency_level == "HIGH":
        alert_box("🚨 Critical alert: high emergency load expected. Immediate capacity review recommended.", "critical")
    elif emergency_level == "MEDIUM":
        alert_box("⚠️ Moderate emergency pressure detected. Monitor staffing and bed usage closely.", "warning")
    else:
        alert_box("✅ System stable. No major emergency pressure detected.", "success")

    st.markdown("### Resource Snapshot")
    s1, s2, s3 = st.columns(3)
    s1.metric("Beds Needed", int(result["recommended_resources"]["beds_needed"]))
    s2.metric("Doctors Needed", int(result["recommended_resources"]["doctors_needed"]))
    s3.metric("Nurses Needed", int(result["recommended_resources"].get("nurses_needed", 0)))

    allocations = optimization.get("department_allocations", [])
    if allocations:
        st.markdown("### Top Priority Departments")
        alloc_df = pd.DataFrame(allocations).head(5)
        show_cols = [c for c in ["department", "predicted_patients", "status", "priority_score"] if c in alloc_df.columns]
        modern_table(alloc_df[show_cols])


def show_forecast():
    section_header("📈 Forecast & Demand Analysis", "Historical flow, 24-hour AI forecast, and actual vs predicted view.")
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    df = ctx["df"]
    predictions = ctx["forecast_values"]
    if len(predictions) == 0:
        empty_state("Forecast unavailable.")
        return

    forecast_df = pd.DataFrame({"hour": range(1, len(predictions) + 1), "forecast": predictions})

    col1, col2 = st.columns(2)
    with col1:
        if not df.empty:
            hist_df = df.copy().reset_index(drop=True)
            hist_df["time_index"] = hist_df.index
            fig_hist = px.line(hist_df, x="time_index", y="patients", title="Historical Patients")
            fig_hist.update_layout(height=350, xaxis_title="Time Index", yaxis_title="Patients")
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            empty_state("Historical data unavailable.")

    with col2:
        fig_forecast = px.line(forecast_df, x="hour", y="forecast", markers=True, title="24-Hour AI Forecast")
        fig_forecast.update_layout(height=350, xaxis_title="Next Hours", yaxis_title="Predicted Patients")
        st.plotly_chart(fig_forecast, use_container_width=True)

    if not df.empty:
        actual = df["patients"].tail(len(predictions)).values.astype(float)
        forecast_vals = np.array(predictions, dtype=float)
        min_len = min(len(actual), len(forecast_vals))
        compare_df = pd.DataFrame({
            "time_index": list(range(min_len)),
            "Actual": actual[:min_len],
            "Forecast": forecast_vals[:min_len],
        })
        fig_compare = px.line(compare_df, x="time_index", y=["Actual", "Forecast"], title="Actual vs Forecast")
        fig_compare.update_layout(height=350, xaxis_title="Time Window", yaxis_title="Patients")
        st.plotly_chart(fig_compare, use_container_width=True)


def show_optimization():
    section_header("🧩 Advanced Resource Optimization Center", "Department allocations, shortage ranking, and AI-generated recommendations.")
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    optimization = ctx["optimization"]
    summary = optimization.get("summary", {})
    allocations = optimization.get("department_allocations", [])
    recommendations = optimization.get("recommendations", [])
    actions = optimization.get("actions", [])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beds Needed Total", int(summary.get("beds_needed_total", 0)))
    c2.metric("Doctors Needed Total", int(summary.get("doctors_needed_total", 0)))
    c3.metric("Nurses Needed Total", int(summary.get("nurses_needed_total", 0)))
    c4.metric("Top Priority Dept", str(summary.get("top_priority_department", "-")))

    if allocations:
        alloc_df = pd.DataFrame(allocations)
        modern_table(alloc_df)

        if "priority_score" in alloc_df.columns and "department" in alloc_df.columns:
            fig_priority = px.bar(
                alloc_df,
                x="department",
                y="priority_score",
                color="status" if "status" in alloc_df.columns else None,
                title="Priority Score by Department",
            )
            fig_priority.update_layout(height=400)
            st.plotly_chart(fig_priority, use_container_width=True)

        shortage_cols = ["department", "bed_shortage", "doctor_shortage", "nurse_shortage"]
        if all(col in alloc_df.columns for col in shortage_cols):
            shortage_df = alloc_df[shortage_cols].copy()
            fig_shortage = px.bar(
                shortage_df,
                x="department",
                y=["bed_shortage", "doctor_shortage", "nurse_shortage"],
                barmode="group",
                title="Shortage Overview by Department",
            )
            fig_shortage.update_layout(height=420)
            st.plotly_chart(fig_shortage, use_container_width=True)
    else:
        empty_state("No optimization data available.")

    st.markdown("### Recommendations")
    if recommendations:
        for rec in recommendations:
            st.info(rec)
    else:
        empty_state("No recommendations available.")

    st.markdown("### Suggested Actions")
    if actions:
        modern_table(pd.DataFrame(actions))
    else:
        empty_state("No explicit actions generated.")


def show_operations_center():
    section_header("⚙️ Operations Center", "Operational planning, simulation, and department capacity views.")
    ctx = get_live_context()
    if not ctx["ready"]:
        empty_state(ctx["reason"])
        return

    prediction = ctx["prediction"]
    c1, c2, c3 = st.columns(3)
    demand = c1.slider("Demand Increase %", 0, 100, 20, key="ops_demand")
    beds = c2.slider("Available Beds", 50, 300, 120, key="ops_beds")
    doctors = c3.slider("Available Doctors", 5, 50, 15, key="ops_doctors")

    sim = simulate(prediction, beds, doctors, demand)
    if sim:
        s1, s2, s3 = st.columns(3)
        s1.metric("Simulated Patients", int(sim["simulated_patients"]))
        s2.metric("Emergency Level", sim["emergency_level"])
        s3.metric("Doctor Shortage", int(sim["doctor_shortage"]))

        left, right = st.columns(2)
        with left:
            st.write("#### Bed Allocation")
            st.json(sim["bed_allocation"])
        with right:
            st.write("#### Recommended Resources")
            st.json(sim["recommended_resources"])

    hospital_map = pd.DataFrame({
        "Department": ["ER", "ICU", "General Ward", "Surgery", "Radiology"],
        "Capacity": [30, 20, 80, 10, 15],
        "Occupied": [
            int(prediction * 0.30),
            int(prediction * 0.10),
            int(prediction * 0.45),
            int(prediction * 0.10),
            int(prediction * 0.05),
        ],
    })
    hospital_map["Available"] = hospital_map["Capacity"] - hospital_map["Occupied"]

    modern_table(hospital_map)
    fig_dept = px.bar(
        hospital_map,
        x="Department",
        y=["Capacity", "Occupied", "Available"],
        barmode="group",
        title="Department Capacity Overview",
    )
    fig_dept.update_layout(height=400)
    st.plotly_chart(fig_dept, use_container_width=True)


def show_evaluation_panel():
    section_header("📏 Forecast Evaluation Panel", "Model comparison using saved v2 outputs.")

    split = st.radio("Evaluation Split", ["test", "validation"], horizontal=True, key="eval_split_selector")
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
    st.plotly_chart(fig_metrics, use_container_width=True)

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
        st.plotly_chart(fig_compare, use_container_width=True)

        modern_table(clean_df.tail(50))
    else:
        empty_state("Detailed evaluation outputs are not available yet.")


def show_explainability_panel():
    section_header("🔬 Explainable AI Panel")
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
    fig = px.bar(impact_df, x="feature", y="impact", title="Feature Impact on Prediction")
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)
    modern_table(impact_df.sort_values(by="abs_impact", ascending=False))


def show_simulation():
    show_operations_center()


def show_digital_twin():
    show_operations_center()


def show_department_status():
    show_operations_center()