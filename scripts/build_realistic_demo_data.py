from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "data" / "updated_exports"
ARTIFACT_DATA_DIR = ROOT / "artifacts" / "datasets"
MAIN_DATASET_PATH = ROOT / "clean_data(AutoRecovered).csv"

DEPARTMENTS = ["ER", "General Ward", "ICU", "Surgery", "Radiology"]
DEPT_SHARES = {
    "ER": 0.30,
    "General Ward": 0.28,
    "ICU": 0.15,
    "Surgery": 0.15,
    "Radiology": 0.12,
}
DEPT_CAPACITY = {
    "ER": {"beds": 46, "doctors": 10, "nurses": 22},
    "General Ward": {"beds": 92, "doctors": 12, "nurses": 30},
    "ICU": {"beds": 28, "doctors": 8, "nurses": 22},
    "Surgery": {"beds": 34, "doctors": 10, "nurses": 18},
    "Radiology": {"beds": 18, "doctors": 6, "nurses": 10},
}
SHIFT_PERIODS = {
    "Night": range(0, 7),
    "Morning": range(7, 15),
    "Evening": range(15, 23),
}
SHIFT_TIMES = {
    "Morning": ("07:00", "15:00"),
    "Evening": ("15:00", "23:00"),
    "Night": ("23:00", "07:00"),
    "Emergency Backup": ("00:00", "23:59"),
}


@dataclass(frozen=True)
class StaffMember:
    staff_id: str
    staff_name: str
    role: str
    department: str
    specialty: str
    qualification_level: str
    years_experience: int
    overtime_hours: int


def _season(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    return "Autumn"


def _season_factor(month: int) -> float:
    if month in (12, 1, 2):
        return 1.18
    if month in (3, 4, 5):
        return 1.02
    if month in (6, 7, 8):
        return 0.92
    return 1.05


def _hour_factor(hour: int) -> float:
    if 8 <= hour <= 12:
        return 1.22
    if 13 <= hour <= 16:
        return 1.10
    if 17 <= hour <= 20:
        return 1.02
    if 0 <= hour <= 5:
        return 0.72
    return 0.92


def _shift_period(hour: int) -> str:
    if hour in SHIFT_PERIODS["Morning"]:
        return "Morning"
    if hour in SHIFT_PERIODS["Evening"]:
        return "Evening"
    return "Night"


def _holiday_flag(ts: pd.Timestamp) -> int:
    fixed = {(1, 1), (4, 25), (5, 1), (7, 23), (10, 6), (12, 25)}
    return int((ts.month, ts.day) in fixed)


def build_patient_flow() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(4208)
    index = pd.date_range("2024-01-01 00:00", "2025-12-31 23:00", freq="h")
    # Demo requirement is exactly 2 * 8760 rows. The literal range includes
    # leap day 2024, so we exclude Feb 29 to keep the requested 17,520 rows.
    index = index[~((index.month == 2) & (index.day == 29))]
    total_beds = sum(v["beds"] for v in DEPT_CAPACITY.values())
    total_doctors = sum(v["doctors"] for v in DEPT_CAPACITY.values())
    total_nurses = sum(v["nurses"] for v in DEPT_CAPACITY.values())

    rows = []
    dept_rows = []
    previous_patients = 112
    for i, ts in enumerate(index):
        year_growth = 1.0 if ts.year == 2024 else 1.075
        weekday_factor = 1.10 if ts.dayofweek < 5 else 0.86
        base = 118.0 * year_growth * weekday_factor * _season_factor(ts.month) * _hour_factor(ts.hour)
        weekly_wave = 7.0 * np.sin(2 * np.pi * (ts.dayofyear / 7.0))
        annual_wave = 11.0 * np.cos(2 * np.pi * ((ts.dayofyear - 20) / 365.25))
        noise = rng.normal(0, 4.0)
        patients = max(38, base + weekly_wave + annual_wave + noise)

        rolling_anchor = max(60, previous_patients)
        patients = min(patients, rolling_anchor * 1.35)
        previous_patients = int(round(0.72 * previous_patients + 0.28 * patients))
        patients_i = int(round(patients))

        arrivals = max(6, int(round(patients_i * (0.18 + (0.05 if 8 <= ts.hour <= 12 else 0.0)) + rng.normal(0, 2))))
        admissions = max(3, int(round(arrivals * (0.36 + (0.07 if ts.dayofweek < 5 else -0.02)))))
        discharges = max(2, int(round(patients_i * (0.10 + (0.07 if 16 <= ts.hour <= 20 else 0.0)) + rng.normal(0, 2))))
        appointments_count = max(0, int(round((20 if ts.dayofweek < 5 and 8 <= ts.hour <= 16 else 4) * year_growth + rng.normal(0, 2))))
        or_bookings_count = max(0, int(round((4 if ts.dayofweek < 5 and 7 <= ts.hour <= 17 else 1) + rng.normal(0, 1))))
        occupancy_rate = float(np.clip(patients_i / total_beds, 0.58, 0.92))
        occupied_beds = int(round(occupancy_rate * total_beds))
        available_beds = max(0, total_beds - occupied_beds)
        available_doctors = max(4, int(round(total_doctors * (0.78 if _shift_period(ts.hour) == "Night" else 0.92))))
        available_nurses = max(8, int(round(total_nurses * (0.80 if _shift_period(ts.hour) == "Night" else 0.94))))
        waiting_patients = max(0, int(round(arrivals * (0.18 + max(0, occupancy_rate - 0.78)) + rng.normal(0, 1))))
        avg_wait_time = int(round(18 + waiting_patients * 2.8 + max(0, occupancy_rate - 0.80) * 80))
        pressure = round((occupancy_rate * 60) + (waiting_patients * 1.6) + (appointments_count * 0.25), 2)

        rows.append(
            {
                "datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "patients": patients_i,
                "hour": ts.hour,
                "day_of_week": ts.dayofweek,
                "is_weekend": int(ts.dayofweek >= 5),
                "month": ts.month,
                "week_number": int(ts.isocalendar().week),
                "season": _season(ts.month),
                "is_holiday": _holiday_flag(ts),
                "holiday": _holiday_flag(ts),
                "event_flag": int(_holiday_flag(ts) or (ts.month in (1, 2) and ts.dayofweek == 0)),
                "shift_period": _shift_period(ts.hour),
                "arrivals": arrivals,
                "admissions": admissions,
                "discharges": discharges,
                "waiting_patients": waiting_patients,
                "avg_wait_time_minutes": avg_wait_time,
                "occupancy_rate": round(occupancy_rate, 3),
                "occupied_beds": occupied_beds,
                "available_beds": available_beds,
                "available_doctors": available_doctors,
                "available_nurses": available_nurses,
                "doctors_available": available_doctors,
                "nurses_available": available_nurses,
                "appointments_count": appointments_count,
                "or_bookings_count": or_bookings_count,
                "department_pressure_score": pressure,
            }
        )

        for dept, share in DEPT_SHARES.items():
            dept_noise = rng.normal(0, 0.015)
            dept_patients = max(1, int(round(patients_i * max(0.05, share + dept_noise))))
            dept_rows.append(
                {
                    "datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "department": dept,
                    "patients": dept_patients,
                }
            )

    df = pd.DataFrame(rows)
    df["lag_1"] = df["patients"].shift(1).bfill().astype(int)
    df["lag_24"] = df["patients"].shift(24).bfill().astype(int)
    df["roll_mean_3"] = df["patients"].shift(1).rolling(3, min_periods=1).mean().bfill().round(2)
    df["roll_mean_6"] = df["patients"].shift(1).rolling(6, min_periods=1).mean().bfill().round(2)
    df["roll_mean_24"] = df["patients"].shift(1).rolling(24, min_periods=1).mean().bfill().round(2)
    df["predicted_patients_next_hour"] = df["patients"].shift(-1).ffill().round().astype(int)
    return df, pd.DataFrame(dept_rows)


def build_main_clean_dataset(flow: pd.DataFrame) -> pd.DataFrame:
    """Build the exact main dataset file while preserving its original schema.

    `clean_data(AutoRecovered).csv` is the manually reviewed source file, so it
    receives the full 17,520-row expansion directly. Existing columns are kept
    and richer operational features are added without changing downstream
    compatibility.
    """

    out = flow.copy()
    dt = pd.to_datetime(out["datetime"], errors="coerce")
    out["day_of_week_name"] = dt.dt.day_name()
    out["holiday_name"] = np.where(out["holiday"].astype(int) == 1, "Hospital calendar event", "No Holiday")
    out["weather"] = np.select(
        [out["season"].eq("Winter"), out["season"].eq("Summer")],
        [2, 1],
        default=0,
    ).astype(int)
    out["weather_type"] = np.select(
        [out["season"].eq("Winter"), out["season"].eq("Summer")],
        ["Cold/Flu Season", "Heat"],
        default="Normal",
    )
    out["weather_severity"] = np.select(
        [out["event_flag"].astype(int).eq(1), out["season"].eq("Winter")],
        [2, 1],
        default=0,
    ).astype(int)
    out["hospital capacity"] = int(sum(v["beds"] for v in DEPT_CAPACITY.values()))
    out["is_capped"] = (out["occupancy_rate"].astype(float) >= 0.90).astype(int)
    out["is_emergency"] = (out["department_pressure_score"].astype(float) >= 70).astype(int)
    out["emergency_spike"] = np.maximum(0, out["arrivals"].astype(int) - out["arrivals"].rolling(24, min_periods=1).mean()).round().astype(int)
    out["is_outbreak"] = ((out["season"].eq("Winter")) & (out["event_flag"].astype(int).eq(1))).astype(int)
    out["outbreak_intensity"] = np.where(out["is_outbreak"].eq(1), 2, np.where(out["season"].eq("Winter"), 1, 0)).astype(int)
    out["staff_on_duty"] = out["available_doctors"].astype(int) + out["available_nurses"].astype(int)
    out["doctor_shortage"] = np.maximum(0, np.ceil(out["patients"].astype(float) / 8).astype(int) - out["available_doctors"].astype(int))
    out["nurse_shortage"] = np.maximum(0, np.ceil(out["patients"].astype(float) / 4).astype(int) - out["available_nurses"].astype(int))
    out["bed_shortage"] = np.maximum(0, np.ceil(out["patients"].astype(float) * 1.05).astype(int) - out["available_beds"].astype(int))
    out["is_staff_shortage"] = ((out["doctor_shortage"] + out["nurse_shortage"]) > 0).astype(int)
    out["staff_shortage_impact"] = (out["doctor_shortage"] * 2 + out["nurse_shortage"]).astype(int)
    out["scenario_primary"] = np.select(
        [out["is_emergency"].eq(1), out["is_staff_shortage"].eq(1), out["is_outbreak"].eq(1)],
        ["Emergency Surge", "Staff Shortage", "Outbreak Watch"],
        default="Normal Operations",
    )
    scenario_map = {"Normal Operations": 0, "Emergency Surge": 1, "Staff Shortage": 2, "Outbreak Watch": 3}
    out["scenario_code"] = pd.Series(out["scenario_primary"]).map(scenario_map).fillna(0).astype(int)
    out["y_patients_t_plus_1"] = out["patients"].shift(-1).ffill().round().astype(int)
    out["y_patients_t_plus_24"] = out["patients"].shift(-24).ffill().round().astype(int)

    out["week_of_year"] = out["week_number"].astype(int)
    out["is_holiday_or_event"] = ((out["is_holiday"].astype(int) == 1) | (out["event_flag"].astype(int) == 1)).astype(int)
    out["transfers"] = np.maximum(0, (out["admissions"].astype(int) * 0.08).round().astype(int))
    out["emergency_arrivals"] = np.maximum(0, (out["arrivals"].astype(int) * np.where(out["hour"].between(18, 23), 0.48, 0.38)).round().astype(int))
    out["elective_arrivals"] = np.maximum(0, out["arrivals"].astype(int) - out["emergency_arrivals"].astype(int))
    out["bed_occupancy"] = out["occupancy_rate"]
    out["er_pressure_score"] = (out["department_pressure_score"].astype(float) * 1.12).round(2)
    out["delayed_discharge_count"] = np.maximum(0, (out["waiting_patients"].astype(int) * np.where(out["hour"].between(16, 20), 0.18, 0.08)).round().astype(int))

    original_cols = [
        "datetime",
        "patients",
        "day_of_week",
        "day_of_week_name",
        "month",
        "is_weekend",
        "holiday",
        "holiday_name",
        "weather",
        "weather_type",
        "weather_severity",
        "hospital capacity",
        "is_capped",
        "is_emergency",
        "emergency_spike",
        "is_outbreak",
        "outbreak_intensity",
        "is_staff_shortage",
        "staff_shortage_impact",
        "scenario_primary",
        "scenario_code",
        "y_patients_t_plus_1",
        "y_patients_t_plus_24",
    ]
    added_cols = [
        "hour",
        "season",
        "week_of_year",
        "shift_period",
        "is_holiday",
        "is_holiday_or_event",
        "event_flag",
        "arrivals",
        "admissions",
        "discharges",
        "transfers",
        "emergency_arrivals",
        "elective_arrivals",
        "waiting_patients",
        "avg_wait_time_minutes",
        "occupancy_rate",
        "bed_occupancy",
        "occupied_beds",
        "available_beds",
        "available_doctors",
        "available_nurses",
        "staff_on_duty",
        "doctor_shortage",
        "nurse_shortage",
        "bed_shortage",
        "appointments_count",
        "or_bookings_count",
        "delayed_discharge_count",
        "department_pressure_score",
        "er_pressure_score",
        "doctors_available",
        "nurses_available",
        "lag_1",
        "lag_24",
        "roll_mean_3",
        "roll_mean_6",
        "roll_mean_24",
        "predicted_patients_next_hour",
    ]
    return out[original_cols + [c for c in added_cols if c not in original_cols]]


def build_staff() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(931)
    first = ["Ahmed", "Mona", "Youssef", "Fatima", "Noor", "Omar", "Sara", "Hassan", "Laila", "Karim", "Nadine", "Mostafa"]
    last = ["Ali", "Hassan", "Yasin", "Abdullah", "Mahmoud", "Ibrahim", "Said", "Fouad", "Nasser", "Samir"]
    staff: list[StaffMember] = []
    idx = 1
    for dept in DEPARTMENTS:
        cfg = DEPT_CAPACITY[dept]
        for role, count in [("doctor", cfg["doctors"]), ("nurse", cfg["nurses"])]:
            for _ in range(count):
                name = f"{'Dr.' if role == 'doctor' else 'Nurse'} {rng.choice(first)} {rng.choice(last)}"
                staff.append(
                    StaffMember(
                        staff_id=f"STF-{idx:04d}",
                        staff_name=name,
                        role=role,
                        department=dept,
                        specialty=dept if role == "doctor" else "Clinical Nursing",
                        qualification_level=rng.choice(["Junior", "Senior", "Consultant"] if role == "doctor" else ["RN", "Senior RN", "Charge Nurse"]).item(),
                        years_experience=int(rng.integers(2, 24)),
                        overtime_hours=int(rng.integers(0, 18)),
                    )
                )
                idx += 1
    staff_df = pd.DataFrame([s.__dict__ | {"available_for_shift": "Yes", "max_hours_per_week": 48, "notes": "Synthetic demo staff"} for s in staff])

    schedule_rows = []
    demo_week = pd.date_range("2025-12-25", periods=14, freq="D")
    for day in demo_week:
        for dept in DEPARTMENTS:
            dept_staff = [s for s in staff if s.department == dept]
            doctors = [s for s in dept_staff if s.role == "doctor"]
            nurses = [s for s in dept_staff if s.role == "nurse"]
            for shift in ["Morning", "Evening", "Night", "Emergency Backup"]:
                doc_count = 2 if shift != "Emergency Backup" else 1
                nurse_count = 4 if shift != "Emergency Backup" else 2
                selected = list(rng.choice(doctors, size=min(doc_count, len(doctors)), replace=False)) + list(rng.choice(nurses, size=min(nurse_count, len(nurses)), replace=False))
                for member in selected:
                    start, end = SHIFT_TIMES[shift]
                    schedule_rows.append(
                        {
                            "staff_id": member.staff_id,
                            "staff_name": member.staff_name,
                            "staff_username": member.staff_id.lower(),
                            "role": member.role,
                            "department": dept,
                            "shift_date": day.strftime("%Y-%m-%d"),
                            "shift_type": shift,
                            "shift_start_time": start,
                            "shift_end_time": end,
                            "status": "Assigned",
                            "notes": "Synthetic demo schedule",
                        }
                    )
    return staff_df, pd.DataFrame(schedule_rows)


def _doctor_by_dept(staff_df: pd.DataFrame) -> dict[str, list[str]]:
    return {
        dept: staff_df[(staff_df["department"] == dept) & (staff_df["role"] == "doctor")]["staff_name"].tolist()
        for dept in DEPARTMENTS
    }


def build_appointments(staff_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(1204)
    doctors = _doctor_by_dept(staff_df)
    rows = []
    shares = {"ER": 0.25, "General Ward": 0.20, "ICU": 0.15, "Surgery": 0.15, "Radiology": 0.10}
    total = 180
    dates = pd.date_range("2025-12-25", periods=14, freq="D")
    slots = ["08:00-10:00", "10:00-12:00", "12:00-14:00", "14:00-16:00", "16:00-18:00"]
    idx = 1
    for dept, share in shares.items():
        count = int(round(total * share))
        for _ in range(count):
            day = rng.choice(dates)
            rows.append(
                {
                    "appointment_id": f"APT-{idx:04d}",
                    "department": dept,
                    "doctor": rng.choice(doctors[dept]).item(),
                    "date": pd.Timestamp(day).strftime("%Y-%m-%d"),
                    "time_slot": rng.choice(slots).item(),
                    "patient_count": int(rng.integers(3, 14)),
                    "status": rng.choice(["Scheduled", "Open", "Busy", "Review Required"], p=[0.58, 0.18, 0.14, 0.10]).item(),
                }
            )
            idx += 1
    return pd.DataFrame(rows)


def build_or_bookings(staff_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(771)
    doctors = _doctor_by_dept(staff_df)
    procedure_map = {
        "Appendectomy": ("General Surgery", 90, True),
        "Trauma Repair": ("Emergency Surgery", 120, True),
        "Orthopedic Fixation": ("Orthopedic", 150, True),
        "Cardiac Cath": ("Cardiology", 110, True),
        "Diagnostic Imaging Sedation": ("Radiology", 60, False),
    }
    rows = []
    dates = pd.date_range("2025-12-25", periods=14, freq="D")
    rooms = ["OR-1", "OR-2", "OR-3", "OR-4"]
    idx = 1
    for day in dates:
        for room in rooms:
            starts = [7, 10, 13, 16]
            for start_hour in starts:
                if rng.random() < 0.72:
                    procedure = rng.choice(list(procedure_map.keys())).item()
                    p_type, duration, post_op = procedure_map[procedure]
                    dept = "Surgery" if "Surgery" in p_type or procedure in {"Appendectomy", "Trauma Repair", "Orthopedic Fixation"} else "Radiology"
                    end_hour = min(23, start_hour + max(1, int(np.ceil(duration / 60))))
                    rows.append(
                        {
                            "booking_id": f"OR-{idx:04d}",
                            "room": room,
                            "doctor": rng.choice(doctors[dept]).item(),
                            "department": dept,
                            "booking_date": day.strftime("%Y-%m-%d"),
                            "date": day.strftime("%Y-%m-%d"),
                            "time_slot": f"{start_hour:02d}:00-{end_hour:02d}:00",
                            "procedure": procedure,
                            "procedure_type": p_type,
                            "procedure_duration_minutes": duration + int(rng.integers(-15, 31)),
                            "post_op_bed_required": bool(post_op),
                            "status": rng.choice(["Scheduled", "Pending", "Priority Review"], p=[0.70, 0.20, 0.10]).item(),
                            "notes": "Synthetic demo OR booking",
                        }
                    )
                    idx += 1
    return pd.DataFrame(rows)


def build_patient_tracking(flow_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(432)
    rows = []
    latest = pd.Timestamp("2025-12-31 08:00")
    for i in range(120):
        dept = rng.choice(DEPARTMENTS, p=[0.32, 0.28, 0.15, 0.15, 0.10]).item()
        entry = latest + pd.Timedelta(hours=int(rng.integers(0, 16)))
        los = int(rng.integers(4, 96))
        discharged = rng.random() < 0.42
        rows.append(
            {
                "patient_id": f"PT-{i+1:04d}",
                "patient_name_or_anonymized_id": f"ANON-{i+1:04d}",
                "national_id_or_card_id_optional": "",
                "entry_datetime": entry.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_method": rng.choice(["ER", "Referral", "Scheduled", "Transfer"], p=[0.42, 0.24, 0.24, 0.10]).item(),
                "department": dept,
                "assigned_bed_id": f"{dept[:2].upper()}-{int(rng.integers(1, DEPT_CAPACITY[dept]['beds']+1)):03d}" if rng.random() > 0.18 else "",
                "admission_status": rng.choice(["admitted", "waiting", "observation"], p=[0.68, 0.18, 0.14]).item(),
                "length_of_stay_hours": los,
                "discharge_datetime": (entry + pd.Timedelta(hours=los)).strftime("%Y-%m-%d %H:%M:%S") if discharged else "",
                "payment_status": rng.choice(["covered", "pending", "self-pay"], p=[0.74, 0.18, 0.08]).item(),
                "current_status": "discharged" if discharged else "inside_hospital",
                "notes": "Synthetic demo patient tracking",
            }
        )
    return pd.DataFrame(rows)


def build_department_status(flow_df: pd.DataFrame) -> pd.DataFrame:
    latest_patients = int(flow_df["patients"].iloc[-1])
    rows = []
    for dept, share in DEPT_SHARES.items():
        cfg = DEPT_CAPACITY[dept]
        current = int(round(latest_patients * share))
        occupied = min(cfg["beds"], int(round(current * 0.82)))
        available_beds = max(0, cfg["beds"] - occupied)
        needed_beds = int(round(current * 1.10))
        needed_doctors = max(1, int(np.ceil(current / 8)))
        needed_nurses = max(1, int(np.ceil(current / 4)))
        rows.append(
            {
                "department": dept,
                "current_patients": current,
                "occupied_beds": occupied,
                "available_beds": available_beds,
                "needed_beds": needed_beds,
                "bed_shortage": max(0, needed_beds - available_beds),
                "available_doctors": cfg["doctors"],
                "needed_doctors": needed_doctors,
                "doctor_shortage": max(0, needed_doctors - cfg["doctors"]),
                "available_nurses": cfg["nurses"],
                "needed_nurses": needed_nurses,
                "nurse_shortage": max(0, needed_nurses - cfg["nurses"]),
                "department_status": "Critical" if needed_beds > cfg["beds"] else "Warning" if needed_beds > cfg["beds"] * 0.85 else "Stable",
            }
        )
    return pd.DataFrame(rows)


def build_what_if() -> pd.DataFrame:
    rows = []
    categories = ["Surge", "Staffing", "Bed Capacity", "OR Pressure", "Discharge Delay"]
    for i in range(50):
        dept = DEPARTMENTS[i % len(DEPARTMENTS)]
        category = categories[i % len(categories)]
        severity = ["Low", "Medium", "High", "Critical"][i % 4]
        demand = round(1.05 + (i % 8) * 0.05, 2)
        bed_change = 5 * (i % 4)
        doc_change = 5 * ((i + 1) % 4)
        nurse_change = 5 * ((i + 2) % 4)
        shortage_gap = int(max(0, (demand - 1.0) * 24 + bed_change / 5))
        rows.append(
            {
                "scenario_id": f"SCN-{i+1:03d}",
                "scenario_name": f"{dept} {category} Scenario {i+1}",
                "scenario_category": category,
                "department": dept,
                "time_window": ["Next 6h", "Next 12h", "Next 24h", "Next 72h"][i % 4],
                "demand_multiplier": demand,
                "arrival_increase_percent": round((demand - 1.0) * 100, 1),
                "bed_capacity_change_percent": bed_change,
                "doctor_availability_change_percent": doc_change,
                "nurse_availability_change_percent": nurse_change,
                "or_booking_change_percent": 10 if category == "OR Pressure" else 0,
                "appointment_change_percent": 12 if category == "Surge" else 3,
                "discharge_delay_hours": [0, 2, 4, 6][i % 4],
                "severity_level": severity,
                "probability_level": ["Rare", "Unlikely", "Possible", "Likely", "Very Likely"][i % 5],
                "operational_risk": "Critical" if severity == "Critical" else "High" if severity == "High" else "Moderate" if severity == "Medium" else "Low",
                "affected_resources": "beds, doctors, nurses",
                "affected_departments": dept,
                "shortage_gap": shortage_gap,
                "expected_system_response": f"Monitor {dept} pressure and compare shortages against available resources.",
                "recommended_action": f"Prepare {dept} reserve coverage; expected shortage gap {shortage_gap}.",
                "model_recommended_action": f"Reallocate staff and beds toward {dept} if pressure exceeds threshold.",
                "priority_level": "Critical" if severity == "Critical" else "High" if severity == "High" else "Medium",
                "escalation_required": "Yes" if severity == "Critical" else "No",
                "scenario_summary": f"{category} in {dept}: demand x{demand}, shortage gap {shortage_gap}, action: reserve resources.",
                "notes": "Synthetic what-if scenario for demo workflow.",
            }
        )
    return pd.DataFrame(rows)


def save_outputs() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    flow, by_dept = build_patient_flow()
    main_clean = build_main_clean_dataset(flow)
    staff, schedule = build_staff()
    appointments = build_appointments(staff)
    or_bookings = build_or_bookings(staff)
    tracking = build_patient_tracking(flow)
    dept_status = build_department_status(flow)
    what_if = build_what_if()

    flow.to_csv(EXPORT_DIR / "patient_flow_hourly_updated.csv", index=False)
    flow.to_csv(EXPORT_DIR / "ops_hourly_overall.csv", index=False)
    flow.to_csv(EXPORT_DIR / "updated_hospital_data.csv", index=False)
    by_dept.to_csv(EXPORT_DIR / "ops_hourly_by_department.csv", index=False)
    main_clean.to_csv(MAIN_DATASET_PATH, index=False)
    staff.to_csv(EXPORT_DIR / "staff_master_data.csv", index=False)
    schedule.to_csv(EXPORT_DIR / "staff_schedule.csv", index=False)
    appointments.to_csv(EXPORT_DIR / "appointments_updated.csv", index=False)
    or_bookings.to_csv(EXPORT_DIR / "or_bookings.csv", index=False)
    tracking.to_csv(EXPORT_DIR / "patient_tracking.csv", index=False)
    dept_status.to_csv(EXPORT_DIR / "department_status_updated.csv", index=False)
    what_if.to_csv(EXPORT_DIR / "what_if_scenarios.csv", index=False)

    # Mirror model-training datasets.
    flow.to_csv(ARTIFACT_DATA_DIR / "ops_hourly_overall.csv", index=False)
    by_dept.to_csv(ARTIFACT_DATA_DIR / "ops_hourly_by_department.csv", index=False)

    # Root seed compatibility for DB-backed runtime sections.
    try:
        main_clean.to_csv(ROOT / "clean_data.csv", index=False)
    except PermissionError:
        print("Warning: clean_data.csv is locked; primary clean_data(AutoRecovered).csv was still updated.")
    appointments.rename(columns={"booking_date": "date"}).to_csv(ROOT / "appointments.csv", index=False)
    or_bookings.to_csv(ROOT / "or_bookings.csv", index=False)
    schedule.rename(columns={"staff_id": "staff_username", "staff_name": "name"}).to_csv(ROOT / "shifts.csv", index=False)

    summary = [
        "HRO-PS realistic demo data export summary",
        "Generated by scripts/build_realistic_demo_data.py",
        "Date range: 2024-01-01 00:00 to 2025-12-31 23:00",
        "",
        f"patient_flow_hourly_updated rows={len(flow)} columns={len(flow.columns)}",
        f"clean_data(AutoRecovered).csv rows={len(main_clean)} columns={len(main_clean.columns)}",
        f"ops_hourly_by_department rows={len(by_dept)} departments={', '.join(DEPARTMENTS)}",
        f"staff_master_data rows={len(staff)}",
        f"staff_schedule rows={len(schedule)}",
        f"appointments_updated rows={len(appointments)}",
        f"or_bookings rows={len(or_bookings)}",
        f"patient_tracking rows={len(tracking)}",
        f"department_status_updated rows={len(dept_status)}",
        f"what_if_scenarios rows={len(what_if)}",
        "",
        "No real patient data is used. This is synthetic demo data.",
    ]
    (EXPORT_DIR / "export_summary.txt").write_text("\n".join(summary), encoding="utf-8")


if __name__ == "__main__":
    save_outputs()
    print("Realistic demo data generated.")
