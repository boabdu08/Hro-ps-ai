import math
from typing import Dict, List

import pandas as pd

from database import SessionLocal
from models import Appointment, ORBooking, StaffShift


DEPARTMENT_CONFIG = {
    "ER": {
        "share": 0.30,
        "beds_capacity": 30,
        "doctors_capacity": 6,
        "nurses_capacity": 12,
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.95,
    },
    "ICU": {
        "share": 0.10,
        "beds_capacity": 20,
        "doctors_capacity": 5,
        "nurses_capacity": 10,
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.95,
    },
    "General Ward": {
        "share": 0.45,
        "beds_capacity": 80,
        "doctors_capacity": 8,
        "nurses_capacity": 18,
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.95,
    },
    "Surgery": {
        "share": 0.10,
        "beds_capacity": 10,
        "doctors_capacity": 4,
        "nurses_capacity": 8,
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.95,
    },
    "Radiology": {
        "share": 0.05,
        "beds_capacity": 15,
        "doctors_capacity": 3,
        "nurses_capacity": 5,
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.95,
    },
}


def _safe_ceil(value):
    return int(math.ceil(float(value)))


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _department_status(required_beds, beds_capacity, warning_ratio, critical_ratio):
    if beds_capacity <= 0:
        return "critical"
    occupancy = required_beds / beds_capacity
    if occupancy >= critical_ratio:
        return "critical"
    if occupancy >= warning_ratio:
        return "warning"
    return "stable"


def _load_operational_state() -> Dict[str, Dict[str, float]]:
    db = SessionLocal()
    try:
        state = {
            dept: {
                "appointments_load": 0,
                "or_pending_count": 0,
                "doctor_staff_count": 0,
                "nurse_staff_count": 0,
            }
            for dept in DEPARTMENT_CONFIG
        }

        for row in db.query(Appointment).all():
            dept = str(row.department or "").strip()
            if dept in state:
                state[dept]["appointments_load"] += _safe_int(row.patient_count, 0)

        for row in db.query(ORBooking).all():
            dept = str(row.department or "").strip()
            if dept in state and str(row.status or "").strip().lower() in ["pending", "scheduled", "priority review"]:
                state[dept]["or_pending_count"] += 1

        for row in db.query(StaffShift).all():
            dept = str(row.department or "").strip()
            if dept not in state:
                continue
            status = str(row.status or "").strip().lower()
            if status in ["off", "cancelled", "cancelled shift"]:
                continue
            role = str(row.role or "").strip().lower()
            if role == "doctor":
                state[dept]["doctor_staff_count"] += 1
            elif role == "nurse":
                state[dept]["nurse_staff_count"] += 1

        return state
    finally:
        db.close()


def _compute_pressure_modifier(appointments_load: int, or_pending_count: int) -> float:
    appt_modifier = min(0.25, appointments_load / 400.0)
    or_modifier = min(0.20, or_pending_count * 0.03)
    return 1.0 + appt_modifier + or_modifier


def _build_recommendations(df: pd.DataFrame) -> List[str]:
    recommendations: List[str] = []

    critical_df = df[df["status"] == "critical"]
    warning_df = df[df["status"] == "warning"]

    if not critical_df.empty:
        top_critical = critical_df.sort_values(by="priority_score", ascending=False).iloc[0]
        recommendations.append(
            f"Critical pressure in {top_critical['department']}. Activate overflow capacity and intervene immediately."
        )

    if not warning_df.empty:
        departments = ", ".join(warning_df["department"].tolist())
        recommendations.append(
            f"Warning pressure detected in: {departments}. Prepare reserve staff coverage and monitor intake closely."
        )

    for shortage_col, label in [("bed_shortage", "beds"), ("doctor_shortage", "doctors"), ("nurse_shortage", "nurses")]:
        shortage_df = df[df[shortage_col] > 0]
        if not shortage_df.empty:
            dept = shortage_df.sort_values(by=shortage_col, ascending=False).iloc[0]
            recommendations.append(
                f"Reallocate {label} toward {dept['department']} (shortage = {int(dept[shortage_col])})."
            )

    high_appt_df = df[df["appointments_load"] >= 20]
    if not high_appt_df.empty:
        dept = high_appt_df.sort_values(by="appointments_load", ascending=False).iloc[0]
        recommendations.append(
            f"High appointment pressure in {dept['department']}. Review scheduling and reschedule lower-priority slots."
        )

    high_or_df = df[df["or_pending_count"] >= 2]
    if not high_or_df.empty:
        dept = high_or_df.sort_values(by="or_pending_count", ascending=False).iloc[0]
        recommendations.append(
            f"OR pressure rising in {dept['department']}. Escalate pending OR bookings for prioritization review."
        )

    if not recommendations:
        recommendations.append("All departments are operating within safe resource thresholds.")

    return recommendations


def optimize_resources(predicted_patients):
    predicted_patients = float(predicted_patients)
    operational_state = _load_operational_state()

    department_rows = []
    for department, cfg in DEPARTMENT_CONFIG.items():
        state = operational_state.get(department, {})
        appointments_load = _safe_int(state.get("appointments_load", 0))
        or_pending_count = _safe_int(state.get("or_pending_count", 0))
        doctor_staff_count = _safe_int(state.get("doctor_staff_count", 0))
        nurse_staff_count = _safe_int(state.get("nurse_staff_count", 0))

        pressure_modifier = _compute_pressure_modifier(appointments_load, or_pending_count)
        department_patients_base = predicted_patients * cfg["share"]
        department_patients = department_patients_base * pressure_modifier

        beds_required = _safe_ceil(department_patients * 1.10)
        doctors_required = max(1, _safe_ceil(department_patients / 8))
        nurses_required = max(1, _safe_ceil(department_patients / 4))

        effective_doctor_capacity = max(cfg["doctors_capacity"], doctor_staff_count)
        effective_nurse_capacity = max(cfg["nurses_capacity"], nurse_staff_count)

        bed_shortage = max(0, beds_required - cfg["beds_capacity"])
        doctor_shortage = max(0, doctors_required - effective_doctor_capacity)
        nurse_shortage = max(0, nurses_required - effective_nurse_capacity)

        status = _department_status(
            required_beds=beds_required,
            beds_capacity=cfg["beds_capacity"],
            warning_ratio=cfg["warning_occupancy"],
            critical_ratio=cfg["critical_occupancy"],
        )

        department_rows.append({
            "department": department,
            "predicted_patients": round(department_patients, 2),
            "base_predicted_patients": round(department_patients_base, 2),
            "pressure_modifier": round(pressure_modifier, 3),
            "appointments_load": appointments_load,
            "or_pending_count": or_pending_count,
            "beds_capacity": cfg["beds_capacity"],
            "doctors_capacity": effective_doctor_capacity,
            "nurses_capacity": effective_nurse_capacity,
            "beds_required": beds_required,
            "doctors_required": doctors_required,
            "nurses_required": nurses_required,
            "bed_shortage": bed_shortage,
            "doctor_shortage": doctor_shortage,
            "nurse_shortage": nurse_shortage,
            "status": status,
        })

    df = pd.DataFrame(department_rows)
    df["priority_score"] = (
        df["bed_shortage"] * 3.0
        + df["doctor_shortage"] * 2.5
        + df["nurse_shortage"] * 2.0
        + df["appointments_load"] * 0.10
        + df["or_pending_count"] * 2.5
        + df["predicted_patients"] * 0.05
    )
    df = df.sort_values(by="priority_score", ascending=False).reset_index(drop=True)

    recommendations = _build_recommendations(df)
    actions = []
    for _, row in df.iterrows():
        if row["doctor_shortage"] > 0:
            actions.append({"type": "staff", "department": row["department"], "action": f"Assign backup doctors to {row['department']}"})
        if row["nurse_shortage"] > 0:
            actions.append({"type": "staff", "department": row["department"], "action": f"Assign backup nurses to {row['department']}"})
        if row["appointments_load"] >= 20:
            actions.append({"type": "appointments", "department": row["department"], "action": f"Review and reschedule overloaded appointments in {row['department']}"})
        if row["or_pending_count"] >= 2:
            actions.append({"type": "or", "department": row["department"], "action": f"Escalate pending OR bookings in {row['department']}"})

    return {
        "summary": {
            "predicted_patients_total": round(predicted_patients, 2),
            "beds_needed_total": int(df["beds_required"].sum()),
            "doctors_needed_total": int(df["doctors_required"].sum()),
            "nurses_needed_total": int(df["nurses_required"].sum()),
            "top_priority_department": df.iloc[0]["department"] if not df.empty else None,
        },
        "department_allocations": df.to_dict(orient="records"),
        "recommendations": recommendations,
        "actions": actions,
    }

