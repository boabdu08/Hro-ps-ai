import streamlit as st
import pandas as pd
import plotly.express as px


@st.cache_data
def load_shifts():
    return pd.read_csv("shifts.csv")


@st.cache_data
def load_or_bookings():
    return pd.read_csv("or_bookings.csv")


@st.cache_data
def load_appointments():
    return pd.read_csv("appointments.csv")


def show_my_shifts(username, role):
    st.markdown("## 🕒 My Shifts")

    df = load_shifts()
    my_shifts = df[df["staff_username"] == username]

    if my_shifts.empty:
        st.info("No shifts assigned.")
        return

    st.dataframe(my_shifts, use_container_width=True, hide_index=True)

    shift_count = my_shifts.groupby("shift_type").size().reset_index(name="count")

    fig = px.bar(
        shift_count,
        x="shift_type",
        y="count",
        title="My Shift Distribution"
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


def show_all_shifts():
    st.markdown("## 👥 Staff Shift Management")

    df = load_shifts()
    st.dataframe(df, use_container_width=True, hide_index=True)

    summary = df.groupby(["department", "shift_type"]).size().reset_index(name="assigned_staff")

    fig = px.bar(
        summary,
        x="department",
        y="assigned_staff",
        color="shift_type",
        barmode="group",
        title="Shift Allocation by Department"
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


def show_or_bookings(role, doctor_name=None):
    st.markdown("## 🏥 Operating Room Bookings")

    df = load_or_bookings()

    if role == "doctor" and doctor_name:
        df = df[df["doctor"] == doctor_name]

    if df.empty:
        st.info("No OR bookings available.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    booking_summary = df.groupby(["room", "status"]).size().reset_index(name="count")

    fig = px.bar(
        booking_summary,
        x="room",
        y="count",
        color="status",
        barmode="group",
        title="OR Booking Status by Room"
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


def show_appointments(role, department=None, doctor_name=None):
    st.markdown("## 📅 Appointments & Clinic Bookings")

    df = load_appointments()

    if role == "doctor" and doctor_name:
        df = df[df["doctor"] == doctor_name]
    elif role == "nurse" and department:
        df = df[df["department"] == department]

    if df.empty:
        st.info("No appointments available.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    fig = px.bar(
        df,
        x="time_slot",
        y="patient_count",
        color="status",
        title="Patient Load by Appointment Slot"
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


def show_admin_appointments_overview():
    st.markdown("## 📊 Appointment Management Overview")

    df = load_appointments()

    st.dataframe(df, use_container_width=True, hide_index=True)

    summary = df.groupby("department")["patient_count"].sum().reset_index()

    fig = px.pie(
        summary,
        names="department",
        values="patient_count",
        title="Appointments Load by Department"
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)