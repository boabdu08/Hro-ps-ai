from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

import pandas as pd

from operational_data_workflow import (
    EXPORT_DIR,
    STAFF_MASTER_COLUMNS,
    STAFF_SCHEDULE_COLUMNS,
    OR_BOOKINGS_COLUMNS,
    today_str,
)


def _today() -> str:
    return today_str()


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

SHIFT_STATUS = ["Assigned", "Available", "Absent", "On Leave"]

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

APPOINTMENT_TYPES = [
    "Consultation",
    "Follow-up",
    "Emergency Follow-up",
    "Diagnostic Review",
    "Pre-op Assessment",
    "Post-op Follow-up",
    "Routine Checkup",
]

APPT_TIME_SLOTS = [
    "08:00-08:30",
    "08:30-09:00",
    "09:00-09:30",
    "09:30-10:00",
    "10:00-10:30",
    "10:30-11:00",
    "11:00-11:30",
    "11:30-12:00",
    "12:00-12:30",
    "12:30-13:00",
    "13:00-13:30",
    "13:30-14:00",
    "14:00-14:30",
    "14:30-15:00",
    "15:00-15:30",
    "15:30-16:00",
]

OR_ROOMS = [f"OR-{i}" for i in range(1, 8)]

OR_STATUSES = [
    "Scheduled",
    "Confirmed",
    "In Progress",
    "Completed",
    "Delayed",
    "Cancelled",
    "Priority Review",
    "Emergency Inserted",
]

OR_PROCEDURES = [
    "Emergency Surgery",
    "Elective Hernia Repair",
    "Appendectomy",
    "Orthopedic repair",
    "Cardiac catheterization",
    "Laparoscopic cholecystectomy",
    "Cataract procedure",
    "Tonsillectomy",
    "Spinal procedure",
    "Wound debridement",
    "Gallbladder surgery",
]

OR_TIME_SLOTS = [
    "08:00-10:30",
    "09:00-11:30",
    "10:00-12:30",
    "11:30-14:00",
    "12:00-14:30",
    "13:00-15:30",
    "14:30-17:00",
    "16:00-18:30",
]

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

FAKE_EMAIL_DOMAINS = ["demo-hospital.org", "hospitalmail.test"]


def _fake_email(first: str, last: str, domain: str) -> str:
    return f"{first}.{last}@{domain}".lower().replace(" ", "")


def _pick(items, k=1):
    if k == 1:
        return random.choice(items)
    return random.sample(items, k)


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


def generate_staff_master() -> pd.DataFrame:
    """Generate medium-hospital staff master data.

    Note: This generator does NOT touch DB.
    Exports are produced via operational_data_workflow.export_updated_operational_data().
    """

    random.seed(42)

    # Target sizes
    doctors = 32
    nurses = 72

    staff_rows = []

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

    # Sprinkle distribution
    doctor_dept_choices = random.choices(doctor_departments, weights=[3, 3, 4, 4, 3, 3, 4, 2], k=doctors)
    nurse_dept_choices = random.choices(nurse_departments, weights=[5, 4, 9, 4, 4, 4, 3, 2, 2, 1, 4], k=nurses)

    def make_person(i: int):
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last = LAST_NAMES[(i * 3) % len(LAST_NAMES)]
        return first, last

    # Doctors
    for i in range(doctors):
        dept = doctor_dept_choices[i]
        first, last = make_person(i)
        role = ROLE_DOCTOR
        staff_id = f"DOC-{i+1:03d}"
        staff_name = f"Dr. {first} {last}"
        specialty = _department_to_specialty(dept)
        qual = QUAL_LEVEL_DOCTOR[i % len(QUAL_LEVEL_DOCTOR)]
        staff_rows.append(
            {
                "staff_id": staff_id,
                "staff_name": staff_name,
                "role": role,
                "department": dept,
                "specialty": specialty,
                "qualification_level": qual,
                "available_for_shift": True,
                "max_hours_per_week": int(random.choice([40, 44, 48])),
                "notes": "demo staff master",
                # email only if UI/schema later supports it; we keep columns fixed.
            }
        )

    # Nurses
    for i in range(nurses):
        dept = nurse_dept_choices[i]
        first, last = make_person(i + doctors)
        role = ROLE_NURSE
        staff_id = f"NUR-{i+1:03d}"
        staff_name = f"Nurse {first} {last}"
        specialty = _department_to_specialty(dept)
        qual = QUAL_LEVEL_NURSE[i % len(QUAL_LEVEL_NURSE)]
        staff_rows.append(
            {
                "staff_id": staff_id,
                "staff_name": staff_name,
                "role": role,
                "department": dept,
                "specialty": specialty,
                "qualification_level": qual,
                "available_for_shift": True,
                "max_hours_per_week": int(random.choice([36, 40, 44, 48])),
                "notes": "demo staff master",
            }
        )

    df = pd.DataFrame(staff_rows)

    # Ensure exact required columns/order
    for col in STAFF_MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[STAFF_MASTER_COLUMNS]

    # De-dupe safety
    df = df.drop_duplicates(subset=["staff_id"], keep="first").reset_index(drop=True)
    return df


def generate_staff_schedule(staff_master: pd.DataFrame, today: str) -> pd.DataFrame:
    random.seed(43)
    staff_rows = []

    # We will create 3 shifts per staff member only for a subset, to keep size realistic.
    # target rough schedule size: 90-140 staff-shift assignments per day.
    doctors = staff_master[staff_master["role"] == ROLE_DOCTOR]
    nurses = staff_master[staff_master["role"] == ROLE_NURSE]

    # ER: strong coverage
    # ICU / General Ward: high nurse coverage
    # Surgery: surgeon/anesthesia availability (doctors)

    def shift_status_for_role(role: str) -> str:
        # Mostly assigned/available, with some absent/on leave.
        if random.random() < (0.06 if role == ROLE_NURSE else 0.03):
            return random.choice(["Absent", "On Leave"])
        return random.choices(["Assigned", "Available"], weights=[0.75, 0.25], k=1)[0]

    # Choose staff for each shift
    for dept in DEPARTMENTS:
        # Determine counts per dept
        if dept == "ER":
            doc_target = 6
            nurse_target = 18
        elif dept == "ICU":
            doc_target = 3
            nurse_target = 16
        elif dept == "General Ward":
            doc_target = 4
            nurse_target = 20
        elif dept == "Surgery":
            doc_target = 6
            nurse_target = 10
        elif dept in {"Cardiology", "Orthopedics", "Pediatrics"}:
            doc_target = 3
            nurse_target = 10
        else:
            doc_target = 1
            nurse_target = 6

        # Filter staff by department
        dept_docs = doctors[doctors["department"] == dept]
        dept_nurs = nurses[nurses["department"] == dept]

        dept_docs_ids = dept_docs["staff_id"].tolist()
        dept_nurs_ids = dept_nurs["staff_id"].tolist()

        for shift_type in SHIFT_TYPES:
            start, end = SHIFT_TIME_MAP[shift_type]

            # Doctors for Surgery/ER/ICU; nurses for everything
            doc_ids = []
            nurse
