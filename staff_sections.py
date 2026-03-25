import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Appointment, ORBooking, StaffShift
from ui_components import empty_state, modern_table, page_header, scoped_key, section_header


def _normalize(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _bootstrap_shifts_from_csv_if_needed(db: Session):
    # DB-first runtime: do not bootstrap from CSV.
    return


def _bootstrap_or_from_csv_if_needed(db: Session):
    # DB-first runtime: do not bootstrap from CSV.
    return


def _bootstrap_appointments_from_csv_if_needed(db: Session):
    # DB-first runtime: do not bootstrap from CSV.
    return


def _load_shifts_df() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_shifts_from_csv_if_needed(db)
        rows = db.query(StaffShift).all()
        return pd.DataFrame([
            {
                "staff_username": _normalize(row.staff_username),
                "name": _normalize(row.name),
                "role": _normalize(row.role),
                "department": _normalize(row.department),
                "shift_date": _normalize(row.shift_date),
                "shift_type": _normalize(row.shift_type),
                "status": _normalize(row.status),
            }
            for row in rows
        ])
    finally:
        db.close()


def _load_or_df() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_or_from_csv_if_needed(db)
        rows = db.query(ORBooking).all()
        return pd.DataFrame([
            {
                "booking_id": _normalize(row.booking_id),
                "room": _normalize(row.room),
                "doctor": _normalize(row.doctor),
                "department": _normalize(row.department),
                "date": _normalize(row.date),
                "time_slot": _normalize(row.time_slot),
                "procedure": _normalize(row.procedure),
                "status": _normalize(row.status),
            }
            for row in rows
        ])
    finally:
        db.close()


def _load_appointments_df() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_appointments_from_csv_if_needed(db)
        rows = db.query(Appointment).all()
        df = pd.DataFrame([
            {
                "appointment_id": _normalize(row.appointment_id),
                "department": _normalize(row.department),
                "doctor": _normalize(row.doctor),
                "date": _normalize(row.date),
                "time_slot": _normalize(row.time_slot),
                "patient_count": _safe_int(row.patient_count, 0),
                "status": _normalize(row.status),
            }
            for row in rows
        ])
        if not df.empty:
            df["patient_count"] = pd.to_numeric(df["patient_count"], errors="coerce").fillna(0)
        return df
    finally:
        db.close()


def show_my_shifts(username, role):
    page_header("My shifts", "Your upcoming assignments and distribution by shift type.")
    df = _load_shifts_df()
    if df.empty:
        empty_state("No shifts assigned.")
        return
    my_shifts = df[df["staff_username"] == username]
    if my_shifts.empty:
        empty_state("No shifts assigned.")
        return
    modern_table(my_shifts, key=scoped_key("my_shifts", username, role, "table"))
    shift_count = my_shifts.groupby("shift_type").size().reset_index(name="count")
    fig = px.bar(shift_count, x="shift_type", y="count", title="My Shift Distribution")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("my_shifts", username, role, "chart"))


def show_all_shifts():
    page_header("Staffing", "Shift coverage across departments.")
    df = _load_shifts_df()
    if df.empty:
        empty_state("No shifts available.")
        return
    modern_table(df, key=scoped_key("shifts", "all", "table"))
    summary = df.groupby(["department", "shift_type"]).size().reset_index(name="assigned_staff")
    fig = px.bar(summary, x="department", y="assigned_staff", color="shift_type", barmode="group", title="Shift Allocation by Department")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("shifts", "all", "chart"))


def show_or_bookings(role, doctor_name=None):
    page_header("Operating rooms", "OR schedule, bookings, and status by room.")
    df = _load_or_df()
    if role == "doctor" and doctor_name:
        df = df[df["doctor"] == doctor_name]
    if df.empty:
        empty_state("No OR bookings available.")
        return
    modern_table(df, key=scoped_key("or_bookings", role, doctor_name or "all", "table"))
    booking_summary = df.groupby(["room", "status"]).size().reset_index(name="count")
    fig = px.bar(booking_summary, x="room", y="count", color="status", barmode="group", title="OR Booking Status by Room")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("or_bookings", role, doctor_name or "all", "chart"))


def show_appointments(role, department=None, doctor_name=None):
    page_header("Appointments", "Clinic load, appointment slots, and patient volume.")
    df = _load_appointments_df()
    if role == "doctor" and doctor_name:
        df = df[df["doctor"] == doctor_name]
    elif role == "nurse" and department:
        df = df[df["department"] == department]
    if df.empty:
        empty_state("No appointments available.")
        return
    modern_table(df, key=scoped_key("appointments", role, department or "", doctor_name or "", "table"))
    fig = px.bar(df, x="time_slot", y="patient_count", color="status", title="Patient Load by Appointment Slot")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("appointments", role, department or "", doctor_name or "", "chart"))


def show_admin_appointments_overview():
    page_header("Appointments overview", "Aggregate clinic load across departments.")
    df = _load_appointments_df()
    if df.empty:
        empty_state("No appointments available.")
        return
    modern_table(df, key=scoped_key("appointments", "admin_overview", "table"))
    summary = df.groupby("department")["patient_count"].sum().reset_index()
    fig = px.pie(summary, names="department", values="patient_count", title="Appointments Load by Department")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("appointments", "admin_overview", "chart"))




