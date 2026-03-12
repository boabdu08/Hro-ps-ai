import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from api_client import get_prediction, simulate


def show_top_kpis(current_patients, prediction, peak, emergency_level, beds, doctors):
    st.subheader("📌 System Overview")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Current Patients", int(current_patients))
    c2.metric("Next Hour", int(prediction))
    c3.metric("Peak Load", int(peak))
    c4.metric("Emergency", emergency_level)
    c5.metric("Beds Needed", int(beds))
    c6.metric("Doctors Needed", int(doctors))


def show_forecast_panel(df, last_sequence):
    st.subheader("📈 Forecast Center")

    col1, col2 = st.columns(2)

    with col1:
        st.write("### Historical Patient Flow")
        st.line_chart(df["patients"])

    predictions = []
    sequence = last_sequence.copy()

    for _ in range(24):
        result = get_prediction(sequence)

        if result is None:
            break

        pred = result["predicted_patients_next_hour"]
        predictions.append(pred)

        new_row = sequence[-1].copy()
        new_row[0] = pred
        sequence = np.vstack([sequence[1:], new_row])

    if len(predictions) == 0:
        st.warning("Forecast unavailable")
        return None, []

    forecast_df = pd.DataFrame({
        "hour": range(1, len(predictions) + 1),
        "forecast": predictions
    })

    with col2:
        st.write("### 24-Hour Forecast")
        st.line_chart(forecast_df.set_index("hour"))

    st.write("### Actual vs Forecast")
    actual = df["patients"].tail(len(predictions)).values
    min_len = min(len(actual), len(predictions))

    compare_df = pd.DataFrame({
        "Actual": actual[:min_len],
        "Forecast": predictions[:min_len]
    })

    st.line_chart(compare_df)

    return forecast_df, predictions


def show_capacity_panel(resources, emergency_level):
    st.subheader("🚨 Capacity & Alerts")

    col1, col2 = st.columns(2)

    with col1:
        beds_needed = resources.get("beds_needed", 0)
        capacity = 120
        occupancy = (beds_needed / capacity) * 100 if capacity > 0 else 0

        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=occupancy,
            title={"text": "Bed Occupancy %"},
            gauge={
                "axis": {"range": [0, 100]},
                "steps": [
                    {"range": [0, 60], "color": "lightgray"},
                    {"range": [60, 80], "color": "gray"},
                    {"range": [80, 100], "color": "darkgray"}
                ]
            }
        ))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if emergency_level == "HIGH":
            st.error("High emergency load detected")
        elif emergency_level == "MEDIUM":
            st.warning("Moderate emergency pressure")
        else:
            st.success("Emergency load is stable")

        if resources.get("beds_needed", 0) > 120:
            st.error("Bed shortage expected")

        if resources.get("doctors_needed", 0) > 15:
            st.warning("Doctor shortage expected")


def show_digital_twin_panel(prediction):
    st.subheader("🧠 Digital Twin Simulation")

    c1, c2, c3 = st.columns(3)

    demand = c1.slider("Demand Increase %", 0, 100, 20)
    beds = c2.slider("Available Beds", 50, 300, 120)
    doctors = c3.slider("Available Doctors", 5, 50, 15)

    sim = simulate(prediction, beds, doctors, demand)

    if sim:
        s1, s2, s3 = st.columns(3)
        s1.metric("Simulated Patients", int(sim["simulated_patients"]))
        s2.metric("Emergency Level", sim["emergency_level"])
        s3.metric("Doctor Shortage", int(sim["doctor_shortage"]))

        st.write("### Bed Allocation")
        st.json(sim["bed_allocation"])

        st.write("### Recommended Resources")
        st.json(sim["recommended_resources"])


def show_operations_panel(prediction):
    st.subheader("⚙️ Operations Center")

    col1, col2 = st.columns(2)

    with col1:
        st.write("### Operating Room Scheduling")
        surgeries = st.slider("Expected Surgeries", 0, 100, 20)
        rooms = st.slider("Operating Rooms", 1, 10, 4)

        schedule = pd.DataFrame({
            "Room": [f"OR-{i+1}" for i in range(rooms)],
            "Surgeries": [surgeries // rooms + (1 if i < surgeries % rooms else 0) for i in range(rooms)]
        })

        st.dataframe(schedule, use_container_width=True)

    with col2:
        st.write("### Resource Optimizer")

        doctors = max(1, int(prediction / 8))
        nurses = max(1, int(prediction / 4))
        beds = int(prediction * 1.1)

        opt_df = pd.DataFrame({
            "Resource": ["Doctors", "Nurses", "Beds"],
            "Recommended": [doctors, nurses, beds]
        })

        st.table(opt_df)


def show_hospital_map_panel(prediction):
    st.subheader("🏥 Department Status")

    hospital_map = pd.DataFrame({
        "Department": ["ER", "ICU", "General Ward", "Surgery", "Radiology"],
        "Capacity": [30, 20, 80, 10, 15],
        "Occupied": [
            int(prediction * 0.30),
            int(prediction * 0.10),
            int(prediction * 0.45),
            int(prediction * 0.10),
            int(prediction * 0.05)
        ]
    })

    hospital_map["Available"] = hospital_map["Capacity"] - hospital_map["Occupied"]

    st.dataframe(hospital_map, use_container_width=True)


def show_heatmap(df):
    st.subheader("🔥 Weekly Patient Heatmap")

    heatmap_data = pd.pivot_table(
        df,
        values="patients",
        index="day_of_week",
        columns="month",
        aggfunc="mean"
    )

    fig = px.imshow(
        heatmap_data,
        labels=dict(x="Month", y="Day of Week", color="Patients"),
        aspect="auto"
    )

    st.plotly_chart(fig, use_container_width=True)