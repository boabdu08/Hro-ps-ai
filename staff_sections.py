import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Appointment, ORBooking, StaffShift
from ui_components import empty_state, fmt_int, kpi_card, modern_table, page_header, scoped_key, section_header

from ops_live import build_live_state, dedupe_keep_latest, normalize_appointment_status, shift_times_for_type


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
        df = pd.DataFrame([
            {
                "id": int(row.id) if getattr(row, "id", None) is not None else None,
                "staff_username": _normalize(row.staff_username),
                "name": _normalize(row.name),
                "role": _normalize(row.role),
                "department": _normalize(row.department),
                "shift_date": _normalize(row.shift_date),
                "shift_type": _normalize(row.shift_type),
                "shift_start_time": _normalize(getattr(row, "shift_start_time", "")),
                "shift_end_time": _normalize(getattr(row, "shift_end_time", "")),
                "status": _normalize(row.status),
            }
            for row in rows
        ])
        if df.empty:
            return df

        # --- Live demo behavior ---
        # 1) Remove duplicates (logical keys) and keep latest.
        df = dedupe_keep_latest(
            df,
            logical_keys=["staff_username", "shift_date", "shift_type", "department"],
            latest_by="id",
        )

        # 2) Update dates to today's date for live demo mode.
        live = build_live_state()
        df["shift_date"] = live.today

        # 3) Ensure shift time ranges exist and align to shift_type.
        def _fill_times(row):
            stime = str(row.get("shift_start_time") or "").strip()
            etime = str(row.get("shift_end_time") or "").strip()
            if stime and etime:
                return stime, etime
            return shift_times_for_type(str(row.get("shift_type") or ""))

        times = df.apply(lambda r: _fill_times(r), axis=1, result_type="expand")
        if isinstance(times, pd.DataFrame) and times.shape[1] == 2:
            df["shift_start_time"] = times[0]
            df["shift_end_time"] = times[1]

        # Hide internal id from UI.
        return df.drop(columns=["id"], errors="ignore")
    finally:
        db.close()


def _load_or_df() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_or_from_csv_if_needed(db)
        rows = db.query(ORBooking).all()
        df = pd.DataFrame([
            {
                "id": int(row.id) if getattr(row, "id", None) is not None else None,
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
        if df.empty:
            return df

        # Dedupe: booking_id OR room+date+time_slot+procedure
        df = dedupe_keep_latest(
            df,
            logical_keys=["booking_id"],
            latest_by="id",
        )
        # Some datasets may have empty booking_id; apply a second-pass dedupe.
        df = dedupe_keep_latest(
            df,
            logical_keys=["room", "date", "time_slot", "procedure"],
            latest_by="id",
        )

        # Live demo: always show today's bookings
        live = build_live_state()
        df["date"] = live.today
        return df.drop(columns=["id"], errors="ignore")
    finally:
        db.close()


def _load_appointments_df() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_appointments_from_csv_if_needed(db)
        rows = db.query(Appointment).all()
        df = pd.DataFrame([
            {
                "id": int(row.id) if getattr(row, "id", None) is not None else None,
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
            # Dedupe: appointment_id OR dept+doctor+date+time_slot
            df = dedupe_keep_latest(df, logical_keys=["appointment_id"], latest_by="id")
            df = dedupe_keep_latest(df, logical_keys=["department", "doctor", "date", "time_slot"], latest_by="id")

            # Live demo: update to today's date
            live = build_live_state()
            df["date"] = live.today

            # Normalize appointment statuses to the new meaningful set
            df["status"] = df["status"].apply(normalize_appointment_status)
        return df.drop(columns=["id"], errors="ignore")
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
    page_header("Staffing", "Realistic medium-hospital staff coverage across departments and shift types.")
    df = _load_shifts_df()
    if df.empty:
        empty_state("No shifts available.")
        return
    st.caption("Source: current DB/API `StaffShift` records after live-demo date normalization and deduplication. CSV bootstrapping is intentionally disabled in this runtime.")

    role_series = df["role"].astype(str).str.lower() if "role" in df.columns else pd.Series(dtype=str)
    total_staff = int(df["staff_username"].nunique()) if "staff_username" in df.columns else int(len(df))
    if "staff_username" in df.columns and not role_series.empty:
        doctors = int(df.loc[role_series.str.contains("doctor|physician", case=False, na=False), "staff_username"].nunique())
        nurses = int(df.loc[role_series.str.contains("nurse", case=False, na=False), "staff_username"].nunique())
        total_staff = int(doctors + nurses)
    else:
        doctors = 0
        nurses = 0
    total_shifts = int(len(df))
    departments = int(df["department"].nunique()) if "department" in df.columns else 0

    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        kpi_card("Total staff shown", fmt_int(total_staff), status="info")
    with s2:
        kpi_card("Doctors", fmt_int(doctors), status="normal")
    with s3:
        kpi_card("Nurses", fmt_int(nurses), status="normal")
    with s4:
        kpi_card("Scheduled shifts", fmt_int(total_shifts), status="success")
    with s5:
        kpi_card("Departments covered", fmt_int(departments), status="info")

    modern_table(df, key=scoped_key("shifts", "all", "table"))

    left, right = st.columns(2)
    with left:
        section_header("Shift distribution", "Morning / Evening / Night / Emergency Backup where present")
        if "shift_type" in df.columns:
            shift_order = ["Morning", "Evening", "Night", "Emergency Backup"]
            shift_count = df.groupby("shift_type").size().reindex(shift_order, fill_value=0).reset_index(name="scheduled_shifts")
            fig_shift = px.bar(shift_count, x="shift_type", y="scheduled_shifts", title="Scheduled shifts by shift type")
            fig_shift.update_layout(height=350, xaxis_title="Shift type", yaxis_title="Scheduled shifts", xaxis_tickangle=-15)
            fig_shift.update_traces(hovertemplate="%{x}: %{y:.0f} shifts<extra></extra>")
            st.plotly_chart(fig_shift, use_container_width=True, key=scoped_key("shifts", "all", "shift_distribution"))
    with right:
        section_header("Department coverage", "Shifts by department")
        if "department" in df.columns:
            dept_order = ["ER", "General Ward", "ICU", "Surgery", "Radiology"]
            dept_summary = df.groupby("department").size().reindex(dept_order, fill_value=0).reset_index(name="scheduled_shifts")
            fig_dept = px.bar(dept_summary, x="department", y="scheduled_shifts", title="Scheduled shifts by department")
            fig_dept.update_layout(height=350, xaxis_title="Department", yaxis_title="Scheduled shifts", xaxis_tickangle=-15)
            fig_dept.update_traces(hovertemplate="%{x}: %{y:.0f} shifts<extra></extra>")
            st.plotly_chart(fig_dept, use_container_width=True, key=scoped_key("shifts", "all", "department_coverage"))

    summary = df.groupby(["department", "shift_type"]).size().reset_index(name="assigned_staff")
    fig = px.bar(summary, x="department", y="assigned_staff", color="shift_type", barmode="group", title="Shift allocation by department and type")
    fig.update_layout(height=420, yaxis_title="Assigned staff", xaxis_title="Department", xaxis_tickangle=-15, legend_title_text="Shift type")
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.0f} staff<extra></extra>")
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("shifts", "all", "chart"))


def show_or_bookings(role, doctor_name=None):
    page_header("Operating rooms", "OR schedule, bookings, and status by room.")
    df = _load_or_df()
    if role == "doctor" and doctor_name:
        df = df[df["doctor"] == doctor_name]
    if df.empty:
        empty_state("No OR bookings available.")
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("OR bookings", fmt_int(len(df)), status="info")
    with c2:
        kpi_card("Rooms used", fmt_int(df["room"].nunique() if "room" in df.columns else 0), status="normal")
    with c3:
        kpi_card("Departments", fmt_int(df["department"].nunique() if "department" in df.columns else 0), status="normal")
    with c4:
        scheduled = int(df["status"].astype(str).str.contains("scheduled|booked|confirmed", case=False, na=False).sum()) if "status" in df.columns else 0
        kpi_card("Scheduled/confirmed", fmt_int(scheduled), status="success")
    modern_table(df, key=scoped_key("or_bookings", role, doctor_name or "all", "table"))
    if "procedure_duration_minutes" in df.columns:
        room_df = df.copy()
        room_df["procedure_duration_minutes"] = pd.to_numeric(room_df["procedure_duration_minutes"], errors="coerce").fillna(0)
        room_capacity = 12 * 60
        booking_summary = room_df.groupby("room").agg(
            bookings=("room", "size"),
            booked_minutes=("procedure_duration_minutes", "sum"),
        ).reset_index()
        booking_summary["utilization_percent"] = (booking_summary["booked_minutes"] / room_capacity * 100).clip(upper=100).round(1)
        fig = px.bar(
            booking_summary,
            x="room",
            y="utilization_percent",
            text="bookings",
            title="OR utilization by room",
            labels={"utilization_percent": "Booked utilization (%)", "room": "Operating room"},
        )
        fig.update_traces(texttemplate="%{text} bookings", textposition="outside")
        fig.update_layout(height=380, yaxis_range=[0, 100], xaxis_tickangle=-15)
    else:
        booking_summary = df.groupby(["room", "status"]).size().reset_index(name="count")
        fig = px.bar(booking_summary, x="room", y="count", color="status", barmode="group", title="OR Booking Status by Room")
        fig.update_layout(height=350, xaxis_tickangle=-15)
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
    total_patients = int(pd.to_numeric(df.get("patient_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if "patient_count" in df.columns else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Appointment slots", fmt_int(len(df)), status="info")
    with c2:
        kpi_card("Patients scheduled", fmt_int(total_patients), status="normal")
    with c3:
        kpi_card("Departments", fmt_int(df["department"].nunique() if "department" in df.columns else 0), status="normal")
    with c4:
        kpi_card("Doctors", fmt_int(df["doctor"].nunique() if "doctor" in df.columns else 0), status="success")
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
    total_patients = int(pd.to_numeric(df.get("patient_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if "patient_count" in df.columns else 0
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        kpi_card("Appointment slots", fmt_int(len(df)), status="info")
    with a2:
        kpi_card("Patients scheduled", fmt_int(total_patients), status="normal")
    with a3:
        kpi_card("Departments", fmt_int(df["department"].nunique() if "department" in df.columns else 0), status="normal")
    with a4:
        kpi_card("Doctors", fmt_int(df["doctor"].nunique() if "doctor" in df.columns else 0), status="success")
    modern_table(df, key=scoped_key("appointments", "admin_overview", "table"))
    summary = df.groupby("department")["patient_count"].sum().reset_index()
    fig = px.pie(summary, names="department", values="patient_count", title="Appointments Load by Department")
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("appointments", "admin_overview", "chart"))







