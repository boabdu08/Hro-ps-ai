"""Operational data verification and export workflow for HRO-PS.

This module is intentionally additive and conservative. It does not replace the
existing DB-first dashboard/runtime architecture. Instead, it provides a single
place to:

1. Verify the updated hospital operational data structure requested for review.
2. Build safe live/demo fallback tables when DB operational tables are empty or
   unavailable in a local environment.
3. Export review-ready CSVs under ``data/updated_exports/`` before any model
   training is run.

System flow documented during Phase 0:

Data files / database
    -> operational live-state normalization (ops_live.py, scheduler.py,
       staff_sections.py, resource_optimizer.py)
    -> hourly forecasting features (forecasting_pipeline.py)
    -> LSTM / ARIMAX / Hybrid 72h artifacts (train_*_ops72h.py,
       build_hybrid_ops72h.py, forecast_inference_ops72h.py)
    -> dashboard tabs (dashboard.py, dashboard_sections.py, staff_sections.py)
    -> department status / digital twin / evaluation outputs.

The Command Center's existing 24-hour forecast path is intentionally untouched.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd

from ops_live import SHIFT_WINDOWS, dedupe_keep_latest, normalize_appointment_status, shift_times_for_type, today_str


EXPORT_DIR = Path("data") / "updated_exports"

STAFF_MASTER_COLUMNS = [
    "staff_id",
    "staff_name",
    "role",
    "department",
    "specialty",
    "qualification_level",
    "available_for_shift",
    "max_hours_per_week",
    "notes",
]

STAFF_SCHEDULE_COLUMNS = [
    "staff_id",
    "staff_name",
    "role",
    "department",
    "shift_date",
    "shift_type",
    "shift_start_time",
    "shift_end_time",
    "status",
    "notes",
]

OR_BOOKINGS_COLUMNS = [
    "booking_id",
    "room",
    "doctor",
    "department",
    "booking_date",
    "time_slot",
    "procedure",
    "status",
    "notes",
]

PATIENT_TRACKING_COLUMNS = [
    "patient_id",
    "patient_name_or_anonymized_id",
    "national_id_or_card_id_optional",
    "entry_datetime",
    "entry_method",
    "department",
    "assigned_bed_id",
    "admission_status",
    "length_of_stay_hours",
    "discharge_datetime",
    "payment_status",
    "current_status",
    "notes",
]

APPOINTMENT_STATUSES = [
    "Scheduled",
    "Checked In",
    "Waiting",
    "In Consultation",
    "Completed",
    "Cancelled",
    "No Show",
    "Reschedule Required",
]

DEPARTMENTS = ["ER", "ICU", "General Ward", "Surgery", "Radiology"]


@dataclass
class WorkflowResult:
    tables: Dict[str, pd.DataFrame]
    created_files: Dict[str, Path] = field(default_factory=dict)
    duplicates_removed: Dict[str, int] = field(default_factory=dict)
    dates_updated_to_today: bool = False
    demo_fallback_generated: bool = False
    newly_added_columns: Dict[str, list[str]] = field(default_factory=dict)
    required_column_report: Dict[str, Dict[str, list[str]]] = field(default_factory=dict)


def _read_csv_if_exists(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _ensure_columns(df: pd.DataFrame, columns: Iterable[str], defaults: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    defaults = defaults or {}
    out = df.copy() if df is not None else pd.DataFrame()
    added: list[str] = []
    for col in columns:
        if col not in out.columns:
            out[col] = defaults.get(col, "")
            added.append(col)
    return out[list(columns)], added


def _normalize_shift_type(value: str) -> str:
    raw = str(value or "").strip().title()
    return raw if raw in SHIFT_WINDOWS else "Morning"


def _load_staff_schedule(today: str) -> tuple[pd.DataFrame, int, list[str], bool]:
    """Build updated staff_schedule from DB when available, otherwise shifts.csv."""

    source_used_db = False
    rows = []
    try:
        from database import SessionLocal
        from models import StaffSchedule, StaffShift

        db = SessionLocal()
        try:
            schedule_rows = db.query(StaffSchedule).all()
            if schedule_rows:
                source_used_db = True
                for r in schedule_rows:
                    rows.append(
                        {
                            "staff_id": getattr(r, "staff_id", "") or "",
                            "staff_name": getattr(r, "staff_name", "") or "",
                            "role": getattr(r, "role", "") or "",
                            "department": getattr(r, "department", "") or "",
                            "shift_date": getattr(r, "shift_date", "") or "",
                            "shift_type": getattr(r, "shift_type", "") or "",
                            "shift_start_time": getattr(r, "shift_start_time", "") or "",
                            "shift_end_time": getattr(r, "shift_end_time", "") or "",
                            "status": getattr(r, "status", "") or "Assigned",
                            "notes": getattr(r, "notes", "") or "",
                        }
                    )
            else:
                shift_rows = db.query(StaffShift).all()
                if shift_rows:
                    source_used_db = True
                    for r in shift_rows:
                        rows.append(
                            {
                                "staff_id": getattr(r, "staff_username", "") or "",
                                "staff_name": getattr(r, "name", "") or "",
                                "role": getattr(r, "role", "") or "",
                                "department": getattr(r, "department", "") or "",
                                "shift_date": getattr(r, "shift_date", "") or "",
                                "shift_type": getattr(r, "shift_type", "") or "",
                                "shift_start_time": getattr(r, "shift_start_time", "") or "",
                                "shift_end_time": getattr(r, "shift_end_time", "") or "",
                                "status": getattr(r, "status", "") or "Assigned",
                                "notes": "generated from legacy staff_shifts table",
                            }
                        )
        finally:
            db.close()
    except Exception:
        rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        raw = _read_csv_if_exists("shifts.csv")
        if not raw.empty:
            df = pd.DataFrame(
                {
                    "staff_id": raw.get("staff_username", ""),
                    "staff_name": raw.get("name", ""),
                    "role": raw.get("role", ""),
                    "department": raw.get("department", ""),
                    "shift_date": raw.get("shift_date", ""),
                    "shift_type": raw.get("shift_type", ""),
                    "shift_start_time": raw.get("shift_start_time", ""),
                    "shift_end_time": raw.get("shift_end_time", ""),
                    "status": raw.get("status", "Assigned"),
                    "notes": "generated from shifts.csv fallback",
                }
            )

    if df.empty:
        # Final safe fallback: enough coverage for all departments/roles/shifts.
        demo = []
        for dept in DEPARTMENTS:
            for role in ["doctor", "nurse"]:
                for i, shift in enumerate(["Morning", "Evening", "Night"], start=1):
                    demo.append(
                        {
                            "staff_id": f"{role[:1].upper()}-{dept.replace(' ', '')}-{i:02d}",
                            "staff_name": f"Demo {role.title()} {dept} {i}",
                            "role": role,
                            "department": dept,
                            "shift_date": today,
                            "shift_type": shift,
                            "status": "Assigned",
                            "notes": "demo fallback generated because no staff schedule source was available",
                        }
                    )
        df = pd.DataFrame(demo)

    before = len(df)
    df, added = _ensure_columns(df, STAFF_SCHEDULE_COLUMNS)
    df["shift_type"] = df["shift_type"].apply(_normalize_shift_type)
    df["shift_date"] = today
    times = df["shift_type"].apply(lambda x: pd.Series(shift_times_for_type(x)))
    df["shift_start_time"] = times[0]
    df["shift_end_time"] = times[1]
    df = dedupe_keep_latest(df, logical_keys=["staff_id", "department", "shift_date", "shift_type"])
    return df, before - len(df), added, not source_used_db


def _build_staff_master(staff_schedule: pd.DataFrame) -> tuple[pd.DataFrame, int, list[str]]:
    master = staff_schedule[["staff_id", "staff_name", "role", "department"]].copy()
    master["specialty"] = master["department"].replace({"ER": "Emergency Medicine", "ICU": "Critical Care"})
    master["qualification_level"] = np.where(master["role"].str.lower().eq("doctor"), "Senior", "Registered")
    master["available_for_shift"] = True
    master["max_hours_per_week"] = 48
    master["notes"] = "derived from current staff schedule"
    before = len(master)
    master = dedupe_keep_latest(master, logical_keys=["staff_id"])
    master, added = _ensure_columns(master, STAFF_MASTER_COLUMNS)
    return master, before - len(master), added


def _load_appointments(today: str) -> tuple[pd.DataFrame, int, list[str], bool]:
    source_used_db = False
    rows = []
    try:
        from database import SessionLocal
        from models import Appointment

        db = SessionLocal()
        try:
            for r in db.query(Appointment).all():
                source_used_db = True
                rows.append(
                    {
                        "appointment_id": getattr(r, "appointment_id", "") or "",
                        "department": getattr(r, "department", "") or "",
                        "doctor": getattr(r, "doctor", "") or "",
                        "date": getattr(r, "date", "") or "",
                        "time_slot": getattr(r, "time_slot", "") or "",
                        "patient_count": getattr(r, "patient_count", 0) or 0,
                        "status": getattr(r, "status", "") or "Scheduled",
                    }
                )
        finally:
            db.close()
    except Exception:
        rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        df = _read_csv_if_exists("appointments.csv")

    if df.empty:
        df = pd.DataFrame(
            [
                {
                    "appointment_id": f"APT-{i+1:03d}",
                    "department": dept,
                    "doctor": f"Dr. Demo {dept}",
                    "date": today,
                    "time_slot": slot,
                    "patient_count": count,
                    "status": status,
                }
                for i, (dept, slot, count, status) in enumerate(
                    zip(DEPARTMENTS, ["08:00-10:00", "10:00-12:00", "12:00-14:00", "14:00-16:00", "16:00-18:00"], [18, 8, 22, 7, 5], APPOINTMENT_STATUSES)
                )
            ]
        )

    before = len(df)
    df, added = _ensure_columns(
        df,
        ["appointment_id", "department", "doctor", "date", "time_slot", "patient_count", "status"],
        {"status": "Scheduled", "patient_count": 0},
    )
    df["date"] = today
    df["patient_count"] = pd.to_numeric(df["patient_count"], errors="coerce").fillna(0).astype(int)
    df["status"] = df["status"].apply(normalize_appointment_status)
    df.loc[~df["status"].isin(APPOINTMENT_STATUSES), "status"] = "Scheduled"
    df = dedupe_keep_latest(df, logical_keys=["appointment_id"])
    df = dedupe_keep_latest(df, logical_keys=["department", "doctor", "date", "time_slot"])
    return df, before - len(df), added, not source_used_db


def _load_or_bookings(today: str) -> tuple[pd.DataFrame, int, list[str], bool]:
    source_used_db = False
    rows = []
    try:
        from database import SessionLocal
        from models import ORBooking

        db = SessionLocal()
        try:
            for r in db.query(ORBooking).all():
                source_used_db = True
                rows.append(
                    {
                        "booking_id": getattr(r, "booking_id", "") or "",
                        "room": getattr(r, "room", "") or "",
                        "doctor": getattr(r, "doctor", "") or "",
                        "department": getattr(r, "department", "") or "",
                        "booking_date": getattr(r, "date", "") or "",
                        "time_slot": getattr(r, "time_slot", "") or "",
                        "procedure": getattr(r, "procedure", "") or "",
                        "status": getattr(r, "status", "") or "Scheduled",
                        "notes": "",
                    }
                )
        finally:
            db.close()
    except Exception:
        rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        raw = _read_csv_if_exists("or_bookings.csv")
        if not raw.empty:
            df = raw.rename(columns={"date": "booking_date"})

    if df.empty:
        df = pd.DataFrame(
            [
                {
                    "booking_id": f"OR-{i+1:03d}",
                    "room": f"OR-{i+1}",
                    "doctor": f"Dr. Surgery {i+1}",
                    "department": "Surgery" if i < 2 else "ER",
                    "booking_date": today,
                    "time_slot": slot,
                    "procedure": proc,
                    "status": "Scheduled",
                    "notes": "demo fallback generated because no OR booking source was available",
                }
                for i, (slot, proc) in enumerate([("08:00-10:00", "Appendectomy"), ("10:00-12:00", "Orthopedic repair"), ("13:00-15:00", "Emergency procedure")])
            ]
        )

    before = len(df)
    df, added = _ensure_columns(df, OR_BOOKINGS_COLUMNS, {"status": "Scheduled"})
    df["booking_date"] = today
    df = dedupe_keep_latest(df, logical_keys=["booking_id"])
    df = dedupe_keep_latest(df, logical_keys=["room", "booking_date", "time_slot", "procedure"])
    return df, before - len(df), added, not source_used_db


def _load_patient_tracking(today: str) -> tuple[pd.DataFrame, int, list[str], bool]:
    source_used_db = False
    rows = []
    try:
        from database import SessionLocal
        from models import PatientTracking

        db = SessionLocal()
        try:
            for r in db.query(PatientTracking).all():
                source_used_db = True
                rows.append({col: getattr(r, col, "") for col in PATIENT_TRACKING_COLUMNS})
        finally:
            db.close()
    except Exception:
        rows = []

    df = pd.DataFrame(rows)
    if df.empty:
        # Derive a realistic patient-tracking fallback from the latest hospital flow.
        flow = _read_csv_if_exists("clean_data.csv")
        if flow.empty:
            flow = _read_csv_if_exists("hospital_patient_flow.csv")
        base_count = int(pd.to_numeric(flow.get("patients", pd.Series([25])), errors="coerce").dropna().tail(1).iloc[0]) if not flow.empty else 25
        n = max(20, min(base_count, 80))
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        rows = []
        for i in range(n):
            dept = DEPARTMENTS[i % len(DEPARTMENTS)]
            entry = now - timedelta(hours=int(i % 36))
            admitted = i % 5 != 0
            discharged = i % 7 == 0
            discharge = entry + timedelta(hours=6 + (i % 24)) if discharged else None
            rows.append(
                {
                    "patient_id": f"P-{today.replace('-', '')}-{i+1:04d}",
                    "patient_name_or_anonymized_id": f"ANON-{i+1:04d}",
                    "national_id_or_card_id_optional": "",
                    "entry_datetime": entry.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_method": ["walk-in", "appointment", "emergency", "referral"][i % 4],
                    "department": dept,
                    "assigned_bed_id": f"{dept[:2].upper()}-B{i+1:03d}" if admitted and not discharged else "",
                    "admission_status": "discharged" if discharged else "admitted" if admitted else "waiting",
                    "length_of_stay_hours": round(((discharge or now) - entry).total_seconds() / 3600.0, 2),
                    "discharge_datetime": discharge.strftime("%Y-%m-%d %H:%M:%S") if discharge else "",
                    "payment_status": ["paid", "pending", "unpaid"][i % 3],
                    "current_status": "discharged" if discharged else "inside_hospital",
                    "notes": "demo fallback generated from patient-flow signal",
                }
            )
        df = pd.DataFrame(rows)

    before = len(df)
    df, added = _ensure_columns(df, PATIENT_TRACKING_COLUMNS)
    df = dedupe_keep_latest(df, logical_keys=["patient_id"])
    return df, before - len(df), added, not source_used_db


def _build_patient_flow_hourly(patient_tracking: pd.DataFrame) -> pd.DataFrame:
    # Prefer the already-prepared ops-aware hourly dataset when it exists. This
    # keeps the export suitable for model training even if live PatientTracking
    # only contains a sparse current-state snapshot.
    existing_ops = _read_csv_if_exists(Path("artifacts") / "datasets" / "ops_hourly_overall.csv")
    if not existing_ops.empty and "datetime" in existing_ops.columns and "patients" in existing_ops.columns:
        existing_ops["datetime"] = pd.to_datetime(existing_ops["datetime"], errors="coerce")
        existing_ops = existing_ops.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
        return existing_ops

    pt = patient_tracking.copy()
    pt["entry_datetime"] = pd.to_datetime(pt["entry_datetime"], errors="coerce")
    pt = pt.dropna(subset=["entry_datetime"])
    if pt.empty:
        clean = _read_csv_if_exists("clean_data.csv")
        if clean.empty:
            return pd.DataFrame(columns=["datetime", "patients", "arrivals", "hour", "day_of_week", "month", "week_number", "season", "is_weekend", "holiday"])
        clean["datetime"] = pd.to_datetime(clean["datetime"], errors="coerce")
        clean = clean.dropna(subset=["datetime"]).sort_values("datetime").tail(24 * 90)
        clean["datetime"] = clean["datetime"].dt.floor("h")
        return clean[[c for c in ["datetime", "patients", "day_of_week", "month", "is_weekend", "holiday"] if c in clean.columns]].copy()

    hourly = pt.assign(datetime=pt["entry_datetime"].dt.floor("h")).groupby("datetime").size().reset_index(name="arrivals")

    # Sparse live snapshots are useful for operations but not enough for model
    # training. If fewer than 7 days of hourly rows are available, fall back to
    # the richer historical clean dataset and preserve the required schema.
    if len(hourly) < 24 * 7:
        clean = _read_csv_if_exists("clean_data.csv")
        if not clean.empty and "datetime" in clean.columns and "patients" in clean.columns:
            clean["datetime"] = pd.to_datetime(clean["datetime"], errors="coerce")
            clean = clean.dropna(subset=["datetime"]).sort_values("datetime").copy()
            clean["datetime"] = clean["datetime"].dt.floor("h")
            clean = clean.drop_duplicates(subset=["datetime"], keep="last")
            clean["hour"] = clean["datetime"].dt.hour
            clean["day_of_week"] = clean["datetime"].dt.dayofweek
            clean["month"] = clean["datetime"].dt.month
            clean["week_number"] = clean["datetime"].dt.isocalendar().week.astype(int)
            clean["season"] = ((clean["month"] % 12) // 3).astype(int)
            clean["is_weekend"] = (clean["day_of_week"] >= 5).astype(int)
            clean["holiday"] = pd.to_numeric(clean.get("holiday", 0), errors="coerce").fillna(0).astype(int)
            clean["arrivals"] = pd.to_numeric(clean["patients"], errors="coerce").fillna(0.0)
            return clean[["datetime", "arrivals", "patients", "hour", "day_of_week", "month", "week_number", "season", "is_weekend", "holiday"]].reset_index(drop=True)

    idx = pd.date_range(hourly["datetime"].min(), hourly["datetime"].max(), freq="h")
    hourly = hourly.set_index("datetime").reindex(idx).fillna(0).rename_axis("datetime").reset_index()
    hourly["patients"] = hourly["arrivals"].astype(float)
    hourly["hour"] = hourly["datetime"].dt.hour
    hourly["day_of_week"] = hourly["datetime"].dt.dayofweek
    hourly["month"] = hourly["datetime"].dt.month
    hourly["week_number"] = hourly["datetime"].dt.isocalendar().week.astype(int)
    hourly["season"] = ((hourly["month"] % 12) // 3).astype(int)
    hourly["is_weekend"] = (hourly["day_of_week"] >= 5).astype(int)
    hourly["holiday"] = 0
    return hourly


def _build_department_status(patient_tracking: pd.DataFrame, staff_schedule: pd.DataFrame) -> pd.DataFrame:
    rows = []
    active = patient_tracking[patient_tracking["current_status"].astype(str).str.lower().eq("inside_hospital")].copy()
    current_shift = "Morning"
    now_t = datetime.now().time()
    if now_t >= datetime.strptime("16:00", "%H:%M").time():
        current_shift = "Evening"
    elif now_t < datetime.strptime("08:00", "%H:%M").time():
        current_shift = "Night"

    for dept in DEPARTMENTS:
        dept_patients = active[active["department"].astype(str).eq(dept)]
        current_patients = int(len(dept_patients))
        occupied_beds = int(dept_patients["assigned_bed_id"].astype(str).str.strip().ne("").sum())
        capacity = {"ER": 30, "ICU": 20, "General Ward": 80, "Surgery": 10, "Radiology": 15}.get(dept, 20)
        available_beds = max(0, capacity - occupied_beds)
        needed_beds = int(np.ceil(current_patients * 0.75))
        bed_shortage = max(0, needed_beds - available_beds)

        sched_dept = staff_schedule[
            staff_schedule["department"].astype(str).eq(dept)
            & staff_schedule["shift_type"].astype(str).eq(current_shift)
            & ~staff_schedule["status"].astype(str).str.lower().isin(["absent", "on leave", "off", "cancelled"])
        ]
        available_doctors = int(sched_dept["role"].astype(str).str.lower().eq("doctor").sum())
        available_nurses = int(sched_dept["role"].astype(str).str.lower().eq("nurse").sum())
        needed_doctors = max(1, int(np.ceil(current_patients / 12.0)))
        needed_nurses = max(1, int(np.ceil(current_patients / 6.0)))
        doctor_shortage = max(0, needed_doctors - available_doctors)
        nurse_shortage = max(0, needed_nurses - available_nurses)
        shortage_score = bed_shortage * 3 + doctor_shortage * 2 + nurse_shortage * 2
        status = "Critical" if shortage_score >= 10 else "Warning" if shortage_score > 0 else "Stable"
        rows.append(
            {
                "department": dept,
                "current_patients": current_patients,
                "occupied_beds": occupied_beds,
                "available_beds": available_beds,
                "needed_beds": needed_beds,
                "bed_shortage": bed_shortage,
                "available_doctors": available_doctors,
                "needed_doctors": needed_doctors,
                "doctor_shortage": doctor_shortage,
                "available_nurses": available_nurses,
                "needed_nurses": needed_nurses,
                "nurse_shortage": nurse_shortage,
                "department_status": status,
            }
        )
    return pd.DataFrame(rows)


def build_updated_operational_tables() -> WorkflowResult:
    today = today_str()
    result = WorkflowResult(tables={}, dates_updated_to_today=True)

    staff_schedule, dup, added, demo = _load_staff_schedule(today)
    result.tables["staff_schedule"] = staff_schedule
    result.duplicates_removed["staff_schedule"] = dup
    result.newly_added_columns["staff_schedule"] = added
    result.demo_fallback_generated = result.demo_fallback_generated or demo

    staff_master, dup, added = _build_staff_master(staff_schedule)
    result.tables["staff_master_data"] = staff_master
    result.duplicates_removed["staff_master_data"] = dup
    result.newly_added_columns["staff_master_data"] = added

    appointments, dup, added, demo = _load_appointments(today)
    result.tables["appointments_updated"] = appointments
    result.duplicates_removed["appointments_updated"] = dup
    result.newly_added_columns["appointments_updated"] = added
    result.demo_fallback_generated = result.demo_fallback_generated or demo

    or_bookings, dup, added, demo = _load_or_bookings(today)
    result.tables["or_bookings"] = or_bookings
    result.duplicates_removed["or_bookings"] = dup
    result.newly_added_columns["or_bookings"] = added
    result.demo_fallback_generated = result.demo_fallback_generated or demo

    patient_tracking, dup, added, demo = _load_patient_tracking(today)
    result.tables["patient_tracking"] = patient_tracking
    result.duplicates_removed["patient_tracking"] = dup
    result.newly_added_columns["patient_tracking"] = added
    result.demo_fallback_generated = result.demo_fallback_generated or demo

    result.tables["department_status_updated"] = _build_department_status(patient_tracking, staff_schedule)
    result.tables["patient_flow_hourly_updated"] = _build_patient_flow_hourly(patient_tracking)

    # Main updated dataset: hourly flow enriched with department status rollups.
    flow = result.tables["patient_flow_hourly_updated"].copy()
    dept_status = result.tables["department_status_updated"].copy()
    if not flow.empty:
        for col in ["current_patients", "occupied_beds", "available_beds", "bed_shortage", "doctor_shortage", "nurse_shortage"]:
            flow[f"total_{col}"] = float(pd.to_numeric(dept_status.get(col, pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    result.tables["updated_hospital_data"] = flow

    required = {
        "staff_master_data": STAFF_MASTER_COLUMNS,
        "staff_schedule": STAFF_SCHEDULE_COLUMNS,
        "or_bookings": OR_BOOKINGS_COLUMNS,
        "patient_tracking": PATIENT_TRACKING_COLUMNS,
        "appointments_updated": ["appointment_id", "department", "doctor", "date", "time_slot", "patient_count", "status"],
        "department_status_updated": [
            "current_patients",
            "occupied_beds",
            "available_beds",
            "needed_beds",
            "bed_shortage",
            "available_doctors",
            "needed_doctors",
            "doctor_shortage",
            "available_nurses",
            "needed_nurses",
            "nurse_shortage",
            "department_status",
        ],
        "patient_flow_hourly_updated": ["datetime", "patients"],
    }
    for table, cols in required.items():
        df = result.tables.get(table, pd.DataFrame())
        present = [c for c in cols if c in df.columns]
        missing = [c for c in cols if c not in df.columns]
        result.required_column_report[table] = {"present": present, "missing": missing}
    return result


def export_updated_operational_data(export_dir: Path = EXPORT_DIR) -> WorkflowResult:
    """Create review-ready CSV exports and a human-readable summary file."""

    export_dir.mkdir(parents=True, exist_ok=True)
    result = build_updated_operational_tables()

    export_map = {
        "updated_hospital_data": "updated_hospital_data.csv",
        "staff_master_data": "staff_master_data.csv",
        "staff_schedule": "staff_schedule.csv",
        "or_bookings": "or_bookings.csv",
        "patient_tracking": "patient_tracking.csv",
        "appointments_updated": "appointments_updated.csv",
        "department_status_updated": "department_status_updated.csv",
        "patient_flow_hourly_updated": "patient_flow_hourly_updated.csv",
    }
    for table, filename in export_map.items():
        path = export_dir / filename
        result.tables[table].to_csv(path, index=False)
        result.created_files[table] = path

    for name in ["ops_hourly_overall.csv", "ops_hourly_by_department.csv"]:
        src = Path("artifacts") / "datasets" / name
        if src.exists():
            dest = export_dir / name
            shutil.copyfile(src, dest)
            result.created_files[name.replace(".csv", "")] = dest

    lines = []
    lines.append("HRO-PS updated operational data export summary")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("CSV files created:")
    for key, path in result.created_files.items():
        df = pd.read_csv(path) if path.exists() else pd.DataFrame()
        lines.append(f"- {key}: {path.as_posix()} | rows={len(df)} | columns={len(df.columns)}")
    lines.append("")
    lines.append("Newly added columns:")
    for table, cols in result.newly_added_columns.items():
        lines.append(f"- {table}: {cols if cols else 'None'}")
    lines.append("")
    lines.append("Duplicate removal:")
    for table, count in result.duplicates_removed.items():
        lines.append(f"- {table}: removed {int(count)} duplicate rows")
    lines.append("")
    lines.append(f"Dates updated to today's date: {'Yes' if result.dates_updated_to_today else 'No'}")
    lines.append(f"Demo/fallback data generated: {'Yes' if result.demo_fallback_generated else 'No'}")
    lines.append("")
    lines.append("Required table/column checks:")
    for table, report in result.required_column_report.items():
        exists = table in result.tables and not result.tables[table].empty
        lines.append(f"- {table}: exists={'Yes' if exists else 'No'}")
        lines.append(f"  present: {report['present']}")
        lines.append(f"  missing: {report['missing'] if report['missing'] else 'None'}")

    summary_path = export_dir / "export_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result.created_files["export_summary"] = summary_path
    return result


if __name__ == "__main__":
    res = export_updated_operational_data()
    print("Data export completed")
    for key, path in res.created_files.items():
        print(f"{key}: {path}")
    print("Data ready for training:", all(not r["missing"] for r in res.required_column_report.values()))