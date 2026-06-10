"""Constraint-aware resource optimizer.

This module consumes forecast outputs (predicted patient load) + current
operational state (appointments, OR, staff shifts) and produces:
- department allocations
- actionable plans (with entity IDs where possible)
- summary objective score proxies (wait time / overcrowding / utilization)

NOTE: This is a first production-grade step *without external solvers*.
Constraints are enforced by explicit feasibility rules (cannot move more staff
than exist, etc.).
"""

import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from database import SessionLocal
from models import Appointment, ORBooking, PatientTracking, StaffShift

from ops_live import build_live_state, is_time_in_shift


DEPARTMENT_CONFIG = {
    "ER": {
        "share": 0.30,
        "beds_capacity": 80,       # includes hallway/overflow bays; ER throughput ~66 of 220 census
        "doctors_capacity": 10,
        "nurses_capacity": 20,
        "doctor_ratio": 6,         # 1 doctor per N patients
        "nurse_ratio": 3,          # 1 nurse per N patients
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.92,
    },
    "ICU": {
        "share": 0.10,
        "beds_capacity": 28,       # ICU is low-volume, high-acuity; ~22 of 220 census
        "doctors_capacity": 8,
        "nurses_capacity": 20,
        "doctor_ratio": 3,         # intensivists per patient
        "nurse_ratio": 2,          # 1:2 ICU standard
        "warning_occupancy": 0.75, # ICU warns earlier than general wards
        "critical_occupancy": 0.88,
    },
    "General Ward": {
        "share": 0.45,
        "beds_capacity": 130,      # largest volume; ~99 of 220 census
        "doctors_capacity": 12,
        "nurses_capacity": 30,
        "doctor_ratio": 10,        # ward physicians cover larger panels
        "nurse_ratio": 6,          # standard ward ratio
        "warning_occupancy": 0.82,
        "critical_occupancy": 0.93,
    },
    "Surgery": {
        "share": 0.10,
        "beds_capacity": 35,       # pre-op + post-op + theatre bays; ~22 of 220 census
        "doctors_capacity": 8,
        "nurses_capacity": 15,
        "doctor_ratio": 4,         # surgeons + anaesthesia per active case
        "nurse_ratio": 3,          # scrub + circulating nurses
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.93,
    },
    "Radiology": {
        "share": 0.05,
        "beds_capacity": 20,       # imaging slots/procedure bays; ~11 of 220 census
        "doctors_capacity": 4,
        "nurses_capacity": 6,
        "doctor_ratio": 8,         # radiologists cover batches of studies
        "nurse_ratio": 8,          # contrast/procedure support
        "warning_occupancy": 0.80,
        "critical_occupancy": 0.92,
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


def _load_operational_state(*, tenant_id: int | None = None) -> Dict[str, Dict[str, float]]:
    db = SessionLocal()
    try:
        # NOTE: This function drives live Department Status and Optimization inputs.
        # We filter to *today/current hour* to reflect real operational state.
        live = build_live_state()
        today = live.today
        now = live.now

        state = {
            dept: {
                "appointments_load": 0,
                "or_pending_count": 0,
                "doctor_staff_count": 0,
                "nurse_staff_count": 0,
                # Patient tracking signals
                "current_patients": 0,
                "waiting_patients": 0,
                "occupied_beds": 0,
            }
            for dept in DEPARTMENT_CONFIG
        }

        q_appt = db.query(Appointment)
        if tenant_id is not None:
            q_appt = q_appt.filter(Appointment.tenant_id == int(tenant_id))
        # Live mode: only today's appointments
        q_appt = q_appt.filter(Appointment.date == today)
        for row in q_appt.all():
            dept = str(row.department or "").strip()
            if dept in state:
                state[dept]["appointments_load"] += _safe_int(row.patient_count, 0)

        q_or = db.query(ORBooking)
        if tenant_id is not None:
            q_or = q_or.filter(ORBooking.tenant_id == int(tenant_id))
        # Live mode: only today's OR bookings
        q_or = q_or.filter(ORBooking.date == today)
        for row in q_or.all():
            dept = str(row.department or "").strip()
            if dept in state and str(row.status or "").strip().lower() in ["pending", "scheduled", "priority review"]:
                state[dept]["or_pending_count"] += 1

        q_shifts = db.query(StaffShift)
        if tenant_id is not None:
            q_shifts = q_shifts.filter(StaffShift.tenant_id == int(tenant_id))
        # Live mode: only today's shift schedule and only staff whose shift is active now.
        q_shifts = q_shifts.filter(StaffShift.shift_date == today)
        for row in q_shifts.all():
            dept = str(row.department or "").strip()
            if dept not in state:
                continue
            # IMPORTANT: status semantics updated per requirements.
            # Only count staff that are operationally available now.
            status = str(row.status or "").strip().lower()
            if status in {"absent", "on leave", "off", "cancelled", "cancelled shift"}:
                continue
            # Filter to current shift window (Morning/Evening/Night)
            if not is_time_in_shift(now=now, shift_type=str(row.shift_type or "")):
                continue
            role = str(row.role or "").strip().lower()
            if role == "doctor":
                state[dept]["doctor_staff_count"] += 1
            elif role == "nurse":
                state[dept]["nurse_staff_count"] += 1

        # Patient tracking (live occupancy)
        q_pt = db.query(PatientTracking)
        if tenant_id is not None:
            q_pt = q_pt.filter(PatientTracking.tenant_id == int(tenant_id))
        for row in q_pt.all():
            dept = str(row.department or "").strip()
            if dept not in state:
                continue

            current_status = str(row.current_status or "").strip().lower()
            admission_status = str(row.admission_status or "").strip().lower()
            bed_id = str(row.assigned_bed_id or "").strip()

            if current_status == "inside_hospital":
                state[dept]["current_patients"] += 1
                if admission_status == "waiting":
                    state[dept]["waiting_patients"] += 1
                if bed_id:
                    state[dept]["occupied_beds"] += 1

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


def _solve_integer_resource_allocation(df: pd.DataFrame) -> dict:
    """Run a small MIP to allocate scarce beds/doctors/nurses by priority.

    Objective: maximize priority-weighted assigned resources, with integer
    variables and total availability constraints for each resource class.
    """

    if df.empty:
        return {"solver": "scipy.optimize.milp", "status": "empty", "allocations": []}

    resource_specs = [
        ("beds", "beds_required", "effective_beds_capacity", 3.0),
        ("doctors", "doctors_required", "effective_doctors_capacity", 2.5),
        ("nurses", "nurses_required", "effective_nurses_capacity", 2.0),
    ]
    rows = []
    for resource, required_col, available_col, resource_weight in resource_specs:
        required = df[required_col].astype(float).clip(lower=0).to_numpy()
        available_total = float(df[available_col].astype(float).clip(lower=0).sum())
        upper = required.copy()
        if len(required) == 0 or available_total <= 0 or upper.sum() <= 0:
            assigned = np.zeros(len(df), dtype=int)
            status = "no_available_capacity"
        else:
            priority = df["priority_score"].astype(float).clip(lower=0).to_numpy()
            c = -(priority + 1.0) * resource_weight
            constraints = LinearConstraint(np.ones((1, len(required))), lb=0, ub=available_total)
            result = milp(
                c=c,
                integrality=np.ones(len(required)),
                bounds=Bounds(lb=np.zeros(len(required)), ub=upper),
                constraints=constraints,
                options={"time_limit": 5},
            )
            if result.success and result.x is not None:
                assigned = np.floor(np.clip(result.x, 0, upper)).astype(int)
                status = "optimal" if int(result.status) == 0 else "feasible"
            else:
                # Safe deterministic fallback for the allocation plan only; the UI still
                # exposes the solver status so a failed MIP is not hidden.
                assigned = np.zeros(len(df), dtype=int)
                remaining = int(available_total)
                for idx in np.argsort(-priority):
                    take = min(int(upper[idx]), remaining)
                    assigned[idx] = take
                    remaining -= take
                    if remaining <= 0:
                        break
                status = f"fallback_greedy:{getattr(result, 'message', 'solver_failed')}"
        for i, department in enumerate(df["department"].tolist()):
            rows.append(
                {
                    "department": department,
                    "resource": resource,
                    "required": int(required[i]),
                    "mip_assigned": int(assigned[i]),
                    "mip_gap": int(max(0, int(required[i]) - int(assigned[i]))),
                    "solver_status": status,
                }
            )
    return {"solver": "scipy.optimize.milp", "status": "ran", "allocations": rows}


def _load_entities(*, tenant_id: int | None = None):
    """Load entities used for actionable plans."""

    db = SessionLocal()
    try:
        q_appts = db.query(Appointment)
        q_or = db.query(ORBooking)
        q_shifts = db.query(StaffShift)

        if tenant_id is not None:
            q_appts = q_appts.filter(Appointment.tenant_id == int(tenant_id))
            q_or = q_or.filter(ORBooking.tenant_id == int(tenant_id))
            q_shifts = q_shifts.filter(StaffShift.tenant_id == int(tenant_id))

        appts = q_appts.all()
        or_rows = q_or.all()
        shifts = q_shifts.all()
        return appts, or_rows, shifts
    finally:
        db.close()


def _shift_is_active(row: StaffShift) -> bool:
    status = str(row.status or "").strip().lower()
    return status not in {"off", "cancelled", "cancelled shift"}


def _build_staff_transfer_plan(
    df: pd.DataFrame,
    shifts: List[StaffShift],
    role: str,
) -> List[dict]:
    """Constraint-based reallocation: move staff from surplus to shortage.

    Constraints:
    - cannot move more staff than exist in a department
    - only move within same role
    """

    shortage_col = "doctor_shortage" if role == "doctor" else "nurse_shortage"
    staff_col = "doctor_staff_count" if role == "doctor" else "nurse_staff_count"

    deficits = (
        df[df[shortage_col] > 0]
        .sort_values(by=shortage_col, ascending=False)
        [["department", shortage_col]]
        .to_dict("records")
    )

    # Surplus = current staff - required staff (proxy: capacity/required). We use shortage<0 as surplus.
    # Since df contains only shortage>=0, approximate surplus from (staff_count - required).
    required_col = "doctors_required" if role == "doctor" else "nurses_required"
    surplus_rows = []
    for _, row in df.iterrows():
        surplus = int(_safe_int(row.get(staff_col, 0)) - _safe_int(row.get(required_col, 0)))
        if surplus > 0:
            surplus_rows.append({"department": row["department"], "surplus": surplus})
    surplus_rows.sort(key=lambda x: x["surplus"], reverse=True)

    # Index shifts by dept+role
    shifts_by_dept: Dict[str, List[StaffShift]] = {}
    for s in shifts:
        if str(s.role or "").strip().lower() != role:
            continue
        dept = str(s.department or "").strip()
        if dept not in shifts_by_dept:
            shifts_by_dept[dept] = []
        if _shift_is_active(s):
            shifts_by_dept[dept].append(s)

    actions: List[dict] = []
    for deficit in deficits:
        to_dept = deficit["department"]
        remaining = int(deficit[shortage_col])
        if remaining <= 0:
            continue

        for donor in surplus_rows:
            if remaining <= 0:
                break
            from_dept = donor["department"]
            if donor["surplus"] <= 0:
                continue
            if from_dept == to_dept:
                continue

            available_shifts = shifts_by_dept.get(from_dept, [])
            if not available_shifts:
                continue

            move = min(remaining, donor["surplus"], len(available_shifts))
            picked = available_shifts[:move]
            shifts_by_dept[from_dept] = available_shifts[move:]

            donor["surplus"] -= move
            remaining -= move

            actions.append(
                {
                    "type": "staff_reassign",
                    "role": role,
                    "from_department": from_dept,
                    "to_department": to_dept,
                    "count": int(move),
                    "shift_ids": [int(s.id) for s in picked if s.id is not None],
                    "staff_usernames": [str(s.staff_username or "").strip() for s in picked],
                }
            )

    return actions


def _select_appointment_reschedules(
    appts: List[Appointment],
    department: str,
    limit: int = 3,
) -> List[dict]:
    candidates = [
        a
        for a in appts
        if str(a.department or "").strip() == department
        and str(a.status or "").strip().lower()
        in {"scheduled", "review required", "reschedule suggested", "open", "busy", ""}
    ]
    candidates.sort(key=lambda a: _safe_int(a.patient_count, 0), reverse=True)
    picked = candidates[:limit]
    return [
        {
            "appointment_db_id": int(a.id) if a.id is not None else None,
            "appointment_id": str(a.appointment_id or "").strip(),
            "department": str(a.department or "").strip(),
            "time_slot": str(a.time_slot or "").strip(),
            "patient_count": _safe_int(a.patient_count, 0),
        }
        for a in picked
    ]


def _select_or_escalations(or_rows: List[ORBooking], department: str, limit: int = 3) -> List[dict]:
    candidates = [
        r
        for r in or_rows
        if str(r.department or "").strip() == department
        and str(r.status or "").strip().lower() in {"pending", "scheduled", "priority review"}
    ]
    picked = candidates[:limit]
    return [
        {
            "or_db_id": int(r.id) if r.id is not None else None,
            "booking_id": str(r.booking_id or "").strip(),
            "room": str(r.room or "").strip(),
            "time_slot": str(r.time_slot or "").strip(),
            "procedure": str(r.procedure or "").strip(),
            "status": str(r.status or "").strip(),
        }
        for r in picked
    ]


def optimize_resources(predicted_patients: float, *, tenant_id: int | None = None):
    """Run the full HRO-PS resource optimisation pipeline.

    Purpose:    Translate a patient-demand forecast into concrete, department-level
                resource allocations (beds, doctors, nurses) using MILP, and produce
                actionable recommendations for the Approvals workflow.
    Source:     Called by the FastAPI /optimize endpoint (triggered by the dashboard
                Optimization tab or the hourly scheduler) with the ForecastState
                predicted_patients_next_hour value.
    Destination: Returns a structured dict consumed by the dashboard Optimization tab
                (KPI cards, allocation table, shortage chart) and by sync_recommendations()
                which seeds the Approvals tab recommendation queue.

    Key labels:
        *_required  = Needed (what the forecast load demands, ×1.10 safety buffer).
        *_shortage  = Shortage (Needed minus currently available — the MILP deficit to cover).
    """
    predicted_patients = float(predicted_patients)
    operational_state = _load_operational_state(tenant_id=tenant_id)
    appts, or_rows, shifts = _load_entities(tenant_id=tenant_id)

    department_rows = []
    for department, cfg in DEPARTMENT_CONFIG.items():
        state = operational_state.get(department, {})
        appointments_load = _safe_int(state.get("appointments_load", 0))
        or_pending_count = _safe_int(state.get("or_pending_count", 0))
        doctor_staff_count = _safe_int(state.get("doctor_staff_count", 0))
        nurse_staff_count = _safe_int(state.get("nurse_staff_count", 0))
        current_patients = _safe_int(state.get("current_patients", 0))
        waiting_patients = _safe_int(state.get("waiting_patients", 0))
        occupied_beds = _safe_int(state.get("occupied_beds", 0))

        pressure_modifier = _compute_pressure_modifier(appointments_load, or_pending_count)
        department_patients_base = predicted_patients * cfg["share"]
        department_patients = department_patients_base * pressure_modifier

        # Demand model: beds include 10% buffer; staff use department-specific ratios.
        beds_required = _safe_ceil(department_patients * 1.10)
        doctors_required = max(1, _safe_ceil(department_patients / cfg.get("doctor_ratio", 8)))
        nurses_required = max(1, _safe_ceil(department_patients / cfg.get("nurse_ratio", 4)))

        # Live bed capacity: occupied beds reduce available beds.
        # Note: cfg["beds_capacity"] is the physical capacity; PatientTracking determines occupancy.
        effective_bed_capacity = max(0, int(cfg["beds_capacity"]) - int(occupied_beds))
        effective_doctor_capacity = min(cfg["doctors_capacity"], doctor_staff_count) if doctor_staff_count > 0 else 0
        effective_nurse_capacity = min(cfg["nurses_capacity"], nurse_staff_count) if nurse_staff_count > 0 else 0

        bed_shortage = max(0, beds_required - effective_bed_capacity)
        doctor_shortage = max(0, doctors_required - effective_doctor_capacity)
        nurse_shortage = max(0, nurses_required - effective_nurse_capacity)

        status = _department_status(
            required_beds=beds_required,
            beds_capacity=cfg["beds_capacity"],
            warning_ratio=cfg["warning_occupancy"],
            critical_ratio=cfg["critical_occupancy"],
        )

        department_rows.append(
            {
                "department": department,
                "predicted_patients": round(department_patients, 2),
                "base_predicted_patients": round(department_patients_base, 2),
                "pressure_modifier": round(pressure_modifier, 3),
                "appointments_load": appointments_load,
                "or_pending_count": or_pending_count,
                # Real-state signals (computed from PatientTracking + schedule)
                "current_patients": current_patients,
                "waiting_patients": waiting_patients,
                "occupied_beds": occupied_beds,
                "beds_capacity": cfg["beds_capacity"],
                "doctors_capacity": cfg["doctors_capacity"],
                "nurses_capacity": cfg["nurses_capacity"],
                "effective_beds_capacity": effective_bed_capacity,
                "effective_doctors_capacity": effective_doctor_capacity,
                "effective_nurses_capacity": effective_nurse_capacity,
                "doctor_staff_count": doctor_staff_count,
                "nurse_staff_count": nurse_staff_count,
                "beds_required": beds_required,
                "doctors_required": doctors_required,
                "nurses_required": nurses_required,
                "bed_shortage": bed_shortage,
                "doctor_shortage": doctor_shortage,
                "nurse_shortage": nurse_shortage,
                "status": status,
            }
        )

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

    # Constraint-based plans
    staff_actions = []
    staff_actions.extend(_build_staff_transfer_plan(df, shifts, role="doctor"))
    staff_actions.extend(_build_staff_transfer_plan(df, shifts, role="nurse"))

    appointment_actions = []
    or_actions = []
    for _, row in df.iterrows():
        dept = row["department"]
        if int(row.get("appointments_load", 0)) >= 20 or int(row.get("bed_shortage", 0)) > 0:
            picked = _select_appointment_reschedules(appts, dept, limit=3)
            if picked:
                appointment_actions.append(
                    {
                        "type": "appointments_reschedule",
                        "department": dept,
                        "appointments": picked,
                        "reason": "Reduce waiting time / bed pressure",
                    }
                )

        if int(row.get("or_pending_count", 0)) >= 2 or dept == "Surgery":
            picked_or = _select_or_escalations(or_rows, dept, limit=3)
            if picked_or:
                or_actions.append(
                    {
                        "type": "or_escalate",
                        "department": dept,
                        "bookings": picked_or,
                        "reason": "Reduce OR backlog and protect emergency capacity",
                    }
                )

    # Objective proxies (until we integrate real wait-time models)
    overcrowding_score = float(df["bed_shortage"].sum())
    wait_time_proxy = float(df["doctor_shortage"].sum() * 2.0 + df["nurse_shortage"].sum() * 1.0)
    utilization_proxy = float(
        np.mean(
            [
                min(2.0, float(r["beds_required"]) / float(max(1, r["beds_capacity"])))
                for _, r in df.iterrows()
            ]
        )
    )
    objective = float(overcrowding_score * 3.0 + wait_time_proxy * 2.0 + utilization_proxy)

    recommendations = _build_recommendations(df)
    mip_result = _solve_integer_resource_allocation(df)

    actions = []
    actions.extend(staff_actions)
    actions.extend(appointment_actions)
    actions.extend(or_actions)

    return {
        "summary": {
            "predicted_patients_total": round(predicted_patients, 2),
            "beds_needed_total": int(df["beds_required"].sum()),
            "doctors_needed_total": int(df["doctors_required"].sum()),
            "nurses_needed_total": int(df["nurses_required"].sum()),
            "top_priority_department": df.iloc[0]["department"] if not df.empty else None,
            "objective": round(objective, 3),
            "wait_time_proxy": round(wait_time_proxy, 3),
            "overcrowding_score": round(overcrowding_score, 3),
            "utilization_proxy": round(utilization_proxy, 3),
            "optimization_method": "Mixed Integer Programming (scipy.optimize.milp) with deterministic fallback if solver fails",
            "mip_status": mip_result.get("status"),
        },
        "department_allocations": df.to_dict(orient="records"),
        "recommendations": recommendations,
        "actions": actions,
        "mip_allocation": mip_result.get("allocations", []),
    }
