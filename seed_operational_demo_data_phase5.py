from __future__ import annotations

"""Phase 5 operational demo data seeding.

This file is intentionally self-contained and safe to import/run.
It generates deterministic demo rows for:
- staff master
- staff schedule
- appointments
- OR bookings
Then it inserts them into the operational tables.

It also exports the Phase 5 operational CSVs via operational_data_workflow.

Note: This module does NOT touch training, evaluation, deployment, or any
other subsystem beyond seeding operational tables.
"""

import random
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from database import SessionLocal
from models import Appointment, ORBooking, StaffMaster, StaffSchedule
import operational_data_workflow as od


# -------------------------
# Demo constants
# -------------------------

DEPARTMENTS = [
    "ER",
    "ICU",
    "General Ward",
    "Cardiology",
    "Orthopedics",
    "Pediatrics",
    "Surgery",
    "Radiology",
    "Laboratory",
    "Pharmacy",
    "Outpatient Clinics",
]

ROLE_DOCTOR = "doctor"
ROLE_NURSE = "nurse"

QUAL_LEVEL_DOCTOR = ["Resident", "Senior", "Consultant", "Specialist"]
QUAL_LEVEL_NURSE = ["Registered", "Senior", "Certified"]

SHIFT_TYPES = ["Morning", "Evening", "Night"]
SHIFT_TIME_MAP = {
    "Morning": ("08:00", "16:00"),
    "Evening": ("16:00", "00:00"),
    "Night": ("00:00", "08:00"),
}

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

OR_PROCEDURES = {
    "Surgery": [
        "Emergency Surgery",
        "Elective Hernia Repair",
        "Appendectomy",
        "Orthopedic repair",
        "Wound debridement",
        "Spinal procedure",
    ],
    "Orthopedics": [
        "Orthopedic repair",
        "Spinal procedure",
        "Wound debridement",
    ],
    "Cardiology": [
        "Cardiac catheterization",
    ],
}

FIRST_NAMES = [
    "Ahmed",
    "Sara",
    "Mona",
    "Youssef",
    "Fatima",
    "Omar",
    "Layla",
    "Hassan",
    "Noura",
    "Rami",
    "Leila",
    "Ibrahim",
    "Amal",
    "Karim",
    "Zahra",
    "Samir",
    "Mariam",
    "Fadi",
    "Noor",
    "Huda",
    "Tarek",
    "Rana",
]

LAST_NAMES = [
    "Al-Sayed",
    "Hassan",
    "Karim",
    "Abdullah",
    "Nasser",
    "Khalil",
    "Yasin",
    "Saad",
    "Fares",
    "Othman",
    "Badr",
    "Hamed",
]


# -------------------------
# Internal helpers
# -------------------------


def _department_to_specialty(dept: str) -> str:
    mapping = {
        "ER": "Emergency Medicine",
        "ICU": "Critical Care",
        "General Ward": "Internal Medicine",
        "Cardiology": "Cardiology",
        "Orthopedics": "Orthopedics",
        "Pediatrics": "Pediatrics",
        "Surgery": "General Surgery",
        "Radiology": "Radiology",
        "Laboratory": "Clinical Laboratory",
        "Pharmacy": "Pharmacy",
        "Outpatient Clinics": "Family Medicine",
    }
    return mapping.get(dept, "General Medicine")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_cols(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = ""
    return out[list(columns)]


def _dedupe(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    return df.drop_duplicates(subset=keys, keep="first").reset_index(drop=True)


# -------------------------
# Required functions
# -------------------------


def generate_staff_master(*, doctors: int = 40, nurses: int = 90) -> pd.DataFrame:
    """Generate StaffMaster rows for Phase 5 demo."""

    random.seed(42)
    rows: list[dict] = []

    doctor_departments = [
        "ER",
        "ICU",
        "General Ward",
        "Cardiology",
        "Orthopedics",
        "Pediatrics",
        "Surgery",
        "Outpatient Clinics",
    ]
    doctor_weights = [4, 4, 7, 5, 4, 4, 7, 4]

    nurse_departments = [
        "ER",
        "ICU",
        "General Ward",
        "Cardiology",
        "Orthopedics",
        "Pediatrics",
        "Surgery",
        "Radiology",
        "Laboratory",
        "Pharmacy",
        "Outpatient Clinics",
    ]
    nurse_weights = [7, 6, 16, 5, 6, 6, 4, 3, 3, 2, 5]

    doctor_dept_choices = random.choices(doctor_departments, weights=doctor_weights, k=doctors)
    nurse_dept_choices = random.choices(nurse_departments, weights=nurse_weights, k=nurses)

    def make_person(i: int) -> tuple[str, str]:
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last = LAST_NAMES[(i * 3) % len(LAST_NAMES)]
        return first, last

    for i in range(doctors):
        dept = doctor_dept_choices[i]
        first, last = make_person(i)
        rows.append(
            {
                "staff_id": f"DOC-{i+1:03d}",
                "staff_name": f"Dr. {first} {last}",
                "role": ROLE_DOCTOR,
                "department": dept,
                "specialty": _department_to_specialty(dept),
                "qualification_level": QUAL_LEVEL_DOCTOR[i % len(QUAL_LEVEL_DOCTOR)],
                "available_for_shift": True,
                "max_hours_per_week": int(random.choice([40, 44, 48, 50])),
                "notes": "demo staff master",
            }
        )

    for i in range(nurses):
        dept = nurse_dept_choices[i]
        first, last = make_person(i + doctors)
        rows.append(
            {
                "staff_id": f"NUR-{i+1:03d}",
                "staff_name": f"Nurse {first} {last}",
                "role": ROLE_NURSE,
                "department": dept,
                "specialty": _department_to_specialty(dept),
                "qualification_level": QUAL_LEVEL_NURSE[i % len(QUAL_LEVEL_NURSE)],
                "available_for_shift": True,
                "max_hours_per_week": int(random.choice([36, 40, 44, 48])),
                "notes": "demo staff master",
            }
        )

    df = pd.DataFrame(rows)
    cols = od.STAFF_MASTER_COLUMNS if hasattr(od, "STAFF_MASTER_COLUMNS") else list(df.columns)
    df = _normalize_cols(df, cols)
    df = _dedupe(df, ["staff_id"])
    return df


def generate_staff_schedule(*, staff_master: pd.DataFrame | None = None) -> pd.DataFrame:
    """Generate StaffSchedule rows for Phase 5 demo."""

    random.seed(43)
    today = _today_str()

    if staff_master is None:
        staff_master = generate_staff_master()

    doctors = staff_master[staff_master["role"] == ROLE_DOCTOR].copy()
    nurses = staff_master[staff_master["role"] == ROLE_NURSE].copy()

    dept_targets = {
        "ER": {ROLE_DOCTOR: 4, ROLE_NURSE: 10},
        "ICU": {ROLE_DOCTOR: 2, ROLE_NURSE: 12},
        "General Ward": {ROLE_DOCTOR: 2, ROLE_NURSE: 14},
        "Surgery": {ROLE_DOCTOR: 3, ROLE_NURSE: 6},
        "Cardiology": {ROLE_DOCTOR: 2, ROLE_NURSE: 6},
        "Orthopedics": {ROLE_DOCTOR: 2, ROLE_NURSE: 6},
        "Pediatrics": {ROLE_DOCTOR: 2, ROLE_NURSE: 6},
        "Radiology": {ROLE_DOCTOR: 1, ROLE_NURSE: 3},
        "Laboratory": {ROLE_DOCTOR: 1, ROLE_NURSE: 3},
        "Pharmacy": {ROLE_DOCTOR: 0, ROLE_NURSE: 2},
        "Outpatient Clinics": {ROLE_DOCTOR: 2, ROLE_NURSE: 4},
    }

    def shift_status_for_role(role: str) -> str:
        if random.random() < (0.06 if role == ROLE_NURSE else 0.03):
            return random.choice(["Absent", "On Leave"])
        return random.choices(["Assigned", "Available"], weights=[0.75, 0.25], k=1)[0]

    staff_rows: list[dict] = []

    for dept in DEPARTMENTS:
        target = dept_targets.get(dept, {ROLE_DOCTOR: 1, ROLE_NURSE: 6})

        dept_docs = doctors[doctors["department"].astype(str).eq(dept)]
        dept_nurs = nurses[nurses["department"].astype(str).eq(dept)]

        doc_ids = dept_docs["staff_id"].tolist()
        nurse_ids = dept_nurs["staff_id"].tolist()

        for shift_type in SHIFT_TYPES:
            start, end = SHIFT_TIME_MAP[shift_type]

            doc_k = min(len(doc_ids), target.get(ROLE_DOCTOR, 0))
            nurse_k = min(len(nurse_ids), target.get(ROLE_NURSE, 0))

            chosen_docs = random.sample(doc_ids, k=doc_k) if doc_k > 0 else []
            chosen_nurs = random.sample(nurse_ids, k=nurse_k) if nurse_k > 0 else []

            for sid in chosen_docs:
                person = dept_docs[dept_docs["staff_id"].eq(sid)].iloc[0]
                staff_rows.append(
                    {
                        "staff_id": sid,
                        "staff_name": person["staff_name"],
                        "role": ROLE_DOCTOR,
                        "department": dept,
                        "shift_date": today,
                        "shift_type": shift_type,
                        "shift_start_time": start,
                        "shift_end_time": end,
                        "status": shift_status_for_role(ROLE_DOCTOR),
                        "notes": "demo schedule",
                    }
                )

            for sid in chosen_nurs:
                person = dept_nurs[dept_nurs["staff_id"].eq(sid)].iloc[0]
                staff_rows.append(
                    {
                        "staff_id": sid,
                        "staff_name": person["staff_name"],
                        "role": ROLE_NURSE,
                        "department": dept,
                        "shift_date": today,
                        "shift_type": shift_type,
                        "shift_start_time": start,
                        "shift_end_time": end,
                        "status": shift_status_for_role(ROLE_NURSE),
                        "notes": "demo schedule",
                    }
                )

    df = pd.DataFrame(staff_rows)

    cols = od.STAFF_SCHEDULE_COLUMNS if hasattr(od, "STAFF_SCHEDULE_COLUMNS") else list(df.columns)
    df = _normalize_cols(df, cols)
    df = _dedupe(df, ["staff_id", "department", "shift_date", "shift_type"])
    return df


def generate_appointments(*, staff_master: pd.DataFrame | None = None) -> pd.DataFrame:
    """Generate Appointment rows for Phase 5 demo."""

    random.seed(44)
    today = _today_str()

    if staff_master is None:
        staff_master = generate_staff_master()

    doctor_pool = staff_master[staff_master["role"] == ROLE_DOCTOR].copy()
    if doctor_pool.empty:
        # fallback minimal
        doctor_pool = pd.DataFrame(
            [
                {
                    "staff_id": "DOC-000",
                    "staff_name": "Dr. Demo",
                    "role": ROLE_DOCTOR,
                    "department": "ER",
                }
            ]
        )

    time_slots = [
        "08:00-10:00",
        "10:00-12:00",
        "12:00-14:00",
        "14:00-16:00",
        "16:00-18:00",
    ]

    rows: list[dict] = []
    for i, dept in enumerate(DEPARTMENTS):
        dept_docs = doctor_pool[doctor_pool["department"].astype(str).eq(dept)]
        if dept_docs.empty:
            dept_docs = doctor_pool
        # Assign one doctor name per appointment row.
        for j, slot in enumerate(time_slots):
            doc_person = dept_docs.sample(n=1, random_state=44 + i * 10 + j).iloc[0]
            count = int([18, 8, 22, 7, 5][j])
            status = APPOINTMENT_STATUSES[(i + j) % len(APPOINTMENT_STATUSES)]
            rows.append(
                {
                    "appointment_id": f"APT-{i+1:03d}-{j+1:02d}",
                    "department": dept,
                    "doctor": doc_person["staff_name"],
                    "date": today,
                    "time_slot": slot,
                    "patient_count": count,
                    "status": status,
                }
            )

    df = pd.DataFrame(rows)

    cols = [
        "appointment_id",
        "department",
        "doctor",
        "date",
        "time_slot",
        "patient_count",
        "status",
    ]
    if hasattr(od, "APPOINTMENT_STATUSES"):
        # Let workflow normalize statuses if present; for seeding keep as is.
        pass
    df = _normalize_cols(df, cols)
    df = _dedupe(df, ["appointment_id"])
    return df


def generate_or_bookings(*, staff_master: pd.DataFrame | None = None) -> pd.DataFrame:
    """Generate ORBooking rows for Phase 5 demo."""

    random.seed(45)
    today = _today_str()

    if staff_master is None:
        staff_master = generate_staff_master()

    doctor_pool = staff_master[staff_master["role"] == ROLE_DOCTOR].copy()
    if doctor_pool.empty:
        doctor_pool = pd.DataFrame(
            [
                {
                    "staff_id": "DOC-000",
                    "staff_name": "Dr. Demo",
                    "role": ROLE_DOCTOR,
                    "department": "Surgery",
                }
            ]
        )

    time_slots = ["08:00-10:00", "10:00-12:00", "13:00-15:00"]
    procedures_fallback = ["Appendectomy", "Orthopedic repair", "Emergency procedure"]

    rows: list[dict] = []
    for i, dept in enumerate(["Surgery", "Orthopedics", "Cardiology"]):
        dept_docs = doctor_pool[doctor_pool["department"].astype(str).eq(dept)]
        if dept_docs.empty:
            dept_docs = doctor_pool
        procedures = OR_PROCEDURES.get(dept, procedures_fallback)
        for j, slot in enumerate(time_slots):
            doc_person = dept_docs.sample(n=1, random_state=45 + i * 10 + j).iloc[0]
            proc = procedures[j % len(procedures)]
            rows.append(
                {
                    "or_booking_id": f"OR-{i+1:03d}-{j+1:02d}",
                    "department": dept,
                    "procedure": proc,
                    "surgeon": doc_person["staff_name"],
                    "date": today,
                    "time_slot": slot,
                    "notes": "demo OR booking",
                }
            )

    df = pd.DataFrame(rows)

    # Align to operational workflow schema.
    cols = ["or_booking_id", "department", "procedure", "surgeon", "date", "time_slot", "notes"]
    df = _normalize_cols(df, cols)

    # Map to OR_BOOKINGS_COLUMNS expected by export.
    # export expects: booking_id, room, doctor, department, booking_date, time_slot, procedure, status, notes
    # We keep "status" out of generator; export/workflow will default to Scheduled.
    df = df.rename(
        columns={
            "or_booking_id": "booking_id",
            "surgeon": "doctor",
            "date": "booking_date",
        }
    )
    if "room" not in df.columns:
        df["room"] = df["booking_id"].astype(str)

    # Provide status if workflow checks/needs it.
    if "status" not in df.columns:
        df["status"] = "Scheduled"

    # Ensure final order for our insertion mapping and dedupe keys.
    df = _dedupe(df, ["booking_id"])
    return df


def seed_database(force: bool = True) -> dict:
    """Seed StaffMaster, StaffSchedule, Appointment, ORBooking tables.

    If ORM/DB schema mismatch prevents safe insertion, exports generated data
    to data/updated_exports/* CSV paths as a fallback.
    """

    staff_master_df = generate_staff_master()
    staff_schedule_df = generate_staff_schedule(staff_master=staff_master_df)
    appointments_df = generate_appointments(staff_master=staff_master_df)
    or_bookings_df = generate_or_bookings(staff_master=staff_master_df)

    # Normalize generator columns to model field names.
    staff_master_records = staff_master_df.to_dict(orient="records")
    staff_schedule_records = staff_schedule_df.to_dict(orient="records")
    appointment_records = appointments_df.to_dict(orient="records")
    # ORBooking model expects: booking_id, room, doctor, department, date, time_slot, procedure, status
    # generator produces booking_date; store it into model.date.
    or_records_raw = or_bookings_df.copy()
    if "booking_date" in or_records_raw.columns and "date" not in or_records_raw.columns:
        or_records_raw["date"] = or_records_raw["booking_date"]
    or_records = or_records_raw.to_dict(orient="records")

    db = SessionLocal()
    seeded_via_db = False
    db_error: str | None = None

    try:
        # Ensure tables exist.
        # NOTE: This is dev-friendly create_all; repo already depends on it.
        from database import init_db

        init_db()

        # Basic overwrite behavior.
        if force:
            # Use bulk delete for simplicity.
            db.query(StaffSchedule).delete(synchronize_session=False)
            db.query(Appointment).delete(synchronize_session=False)
            db.query(ORBooking).delete(synchronize_session=False)
            db.query(StaffMaster).delete(synchronize_session=False)

        for rec in staff_master_records:
            db.add(StaffMaster(**rec))

        for rec in staff_schedule_records:
            db.add(StaffSchedule(**rec))

        for rec in appointment_records:
            db.add(Appointment(**rec))

        for rec in or_records:
            # Drop unused keys that may not exist on the ORM model.
            # This avoids unsupported columns without changing the ORM schema.
            allowed = {
                "booking_id",
                "room",
                "doctor",
                "department",
                "date",
                "time_slot",
                "procedure",
                "status",
            }
            rec2 = {k: v for k, v in rec.items() if k in allowed}
            db.add(ORBooking(**rec2))

        db.commit()
        seeded_via_db = True
    except Exception as e:
        db.rollback()
        db_error = f"{type(e).__name__}: {e}"
    finally:
        db.close()

    if not seeded_via_db:
        # Safe fallback: export generated data directly to operational export paths.
        # Do NOT rely on operational_data_workflow for fallback export.
        try:
            out_dir = "data/updated_exports"
            staff_master_df.to_csv(f"{out_dir}/staff_master_data.csv", index=False)
            # staff_schedule generator matches export columns; rename to what export expects.
            staff_schedule_df.to_csv(f"{out_dir}/staff_schedule.csv", index=False)

            # appointments: workflow expects appointments_updated.csv with header names as in workflow.
            appointments_df.to_csv(f"{out_dir}/appointments_updated.csv", index=False)

            # OR: export expects OR bookings CSV named or_bookings.csv
            # Our generator now uses booking_id/room/doctor/booking_date.
            # If booking_date exists, rename to match export.
            or_export_df = or_bookings_df.copy()
            if "booking_date" in or_export_df.columns:
                or_export_df = or_export_df.rename(columns={"booking_date": "booking_date"})
            or_export_df.to_csv(f"{out_dir}/or_bookings.csv", index=False)
        except Exception as e:
            # If fallback fails, surface the DB limitation loudly.
            raise RuntimeError(
                "DB seeding failed and CSV fallback export also failed: "
                f"DB error={db_error}; fallback_error={type(e).__name__}: {e}"
            ) from e

        print("DB seeding limitation detected; used CSV fallback instead.")
        print("DB limitation:", db_error)
        return {
            "seeded_via_db": False,
            "db_error": db_error,
            "counts": {
                "staff": len(staff_master_df),
                "staff_schedule": len(staff_schedule_df),
                "appointments": len(appointments_df),
                "or_bookings": len(or_bookings_df),
            },
        }

    # Count after commit.
    db2 = SessionLocal()
    try:
        staff_count = db2.query(StaffMaster).count()
        schedule_count = db2.query(StaffSchedule).count()
        appt_count = db2.query(Appointment).count()
        or_count = db2.query(ORBooking).count()

        doc_count = (
            db2.query(StaffMaster).filter(StaffMaster.role == "doctor").count()
        )
        nurse_count = (
            db2.query(StaffMaster).filter(StaffMaster.role == "nurse").count()
        )

        return {
            "seeded_via_db": True,
            "db_error": None,
            "counts": {
                "staff": staff_count,
                "doctors": doc_count,
                "nurses": nurse_count,
                "staff_schedule": schedule_count,
                "appointments": appt_count,
                "or_bookings": or_count,
            },
        }
    finally:
        db2.close()


def export_and_seed_phase5(force: bool = True) -> dict:
    """Seed DB (or CSV fallback) then export updated operational CSVs.

    If CSV fallback was used, we do not overwrite the realistic CSVs with
    smaller DB-derived exports.
    """

    seed_result = seed_database(force=force)
    seeded_via_db = bool(seed_result.get("seeded_via_db"))

    counts = seed_result.get("counts", {})

    if seeded_via_db:
        # Export from DB; expected to be complete.
        od.export_updated_operational_data()
    else:
        print("Skipping operational_data_workflow export to avoid overwriting CSV fallback.")

    doctors = counts.get("doctors")
    nurses = counts.get("nurses")
    staff_count = counts.get("staff")

    result = {
        "staff": staff_count,
        "doctors": doctors,
        "nurses": nurses,
        "staff_schedule": counts.get("staff_schedule"),
        "appointments": counts.get("appointments"),
        "or_bookings": counts.get("or_bookings"),
        "seeded_via_db": seeded_via_db,
    }

    print("Phase 5 operational demo seeding summary:")
    print(result)
    return result


if __name__ == "__main__":
    export_and_seed_phase5(force=True)

