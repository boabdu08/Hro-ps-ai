import streamlit as st
import pandas as pd
import numpy as np

from api_client import get_prediction
from dashboard_sections import (
    show_top_kpis,
    show_forecast_panel,
    show_capacity_panel,
    show_digital_twin_panel,
    show_operations_panel,
    show_hospital_map_panel,
    show_heatmap
)

st.set_page_config(page_title="Hospital AI Command Center", layout="wide")

st.title("🏥 Hospital AI Command Center")

# =========================
# Load data
# =========================
df = pd.read_csv("clean_data.csv")

required_cols = ["patients", "day_of_week", "month", "is_weekend", "holiday", "weather"]

missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

features = df[required_cols].values.astype(float)

if len(features) < 24:
    st.error("Need at least 24 rows of data")
    st.stop()

last_sequence = features[-24:]

# =========================
# API prediction
# =========================
result = get_prediction(last_sequence)

if result is None:
    st.error("API not reachable. Make sure FastAPI is running on http://127.0.0.1:8000")
    st.stop()

prediction = result["predicted_patients_next_hour"]
recommended = result["recommended_resources"]
emergency_level = result["emergency_level"]

beds_needed = recommended["beds_needed"]
doctors_needed = recommended["doctors_needed"]
nurses_needed = recommended.get("nurses_needed", 0)

# =========================
# Rolling forecast to estimate peak
# =========================
predictions = []
sequence = last_sequence.copy()

for _ in range(24):
    res = get_prediction(sequence)

    if res is None:
        break

    pred = res["predicted_patients_next_hour"]
    predictions.append(pred)

    new_row = sequence[-1].copy()
    new_row[0] = pred
    sequence = np.vstack([sequence[1:], new_row])

if len(predictions) == 0:
    st.error("Forecast failed")
    st.stop()

peak = float(np.max(predictions))

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("🧭 Command Sidebar")

    st.markdown("### System Status")
    st.success("API Connected")
    st.info("Dashboard Active")

    st.markdown("### Dataset Info")
    st.write(f"Rows: {len(df)}")
    st.write(f"Columns: {len(df.columns)}")

    st.markdown("### Live Summary")
    st.metric("Current Patients", int(df["patients"].iloc[-1]))
    st.metric("Next Hour Forecast", int(prediction))
    st.metric("Peak Load", int(peak))

    st.markdown("### Capacity Snapshot")
    st.write(f"Beds Needed: **{beds_needed}**")
    st.write(f"Doctors Needed: **{doctors_needed}**")
    st.write(f"Nurses Needed: **{nurses_needed}**")

    st.markdown("### Emergency")
    if emergency_level == "HIGH":
        st.error("High")
    elif emergency_level == "MEDIUM":
        st.warning("Medium")
    else:
        st.success("Low")

# =========================
# Top KPIs
# =========================
show_top_kpis(
    current_patients=int(df["patients"].iloc[-1]),
    prediction=int(prediction),
    peak=int(peak),
    emergency_level=emergency_level,
    beds=beds_needed,
    doctors=doctors_needed
)

st.markdown("---")

# =========================
# Tabs Layout
# =========================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📈 Forecast",
    "🧠 Simulation",
    "⚙️ Operations",
    "🏥 Departments"
])

# -------------------------
# TAB 1: OVERVIEW
# -------------------------
with tab1:
    st.subheader("System Overview")

    show_capacity_panel(recommended, emergency_level)

# -------------------------
# TAB 2: FORECAST
# -------------------------
with tab2:
    st.subheader("Forecast & Demand Monitoring")

    forecast_df, forecast_values = show_forecast_panel(df, last_sequence)

    st.markdown("---")
    show_heatmap(df)

# -------------------------
# TAB 3: SIMULATION
# -------------------------
with tab3:
    st.subheader("Digital Twin & Scenario Planning")

    show_digital_twin_panel(prediction)

# -------------------------
# TAB 4: OPERATIONS
# -------------------------
with tab4:
    st.subheader("Hospital Operations Center")

    show_operations_panel(prediction)

# -------------------------
# TAB 5: DEPARTMENTS
# -------------------------
with tab5:
    st.subheader("Department Capacity & Status")

    show_hospital_map_panel(prediction)