"""Generate data/HRO_PS_DATA_AUDIT_NOTEBOOK.ipynb"""
import json, os

cells = []

def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}

def code(src, outputs=None):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": outputs or [],
        "source": src.strip().splitlines(True),
    }

# Title
cells.append(md("""# HRO-PS AI — Data Audit Notebook
**Project:** Hospital Resource Optimization and Patient Surge Forecasting System
**Audit date:** 2026-05-17
**Scope:** All synthetic demo datasets — row counts, nulls, duplicates, range checks, cross-table relationship integrity.
**All data is synthetic/demo — no real patient information.**
"""))

# Setup
cells.append(md("## 0. Setup"))
cells.append(code("""
import pandas as pd
import numpy as np
import os

pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 120)
print("Libraries loaded. Working directory:", os.getcwd())
"""))

# Load files
cells.append(md("## 1. Load all datasets"))
cells.append(code("""
clean_df      = pd.read_csv("clean_data(AutoRecovered).csv")
staff_master  = pd.read_csv("data/updated_exports/staff_master_data.csv")
staff_sched   = pd.read_csv("data/updated_exports/staff_schedule.csv")
appointments  = pd.read_csv("data/updated_exports/appointments_updated.csv")
or_bookings   = pd.read_csv("data/updated_exports/or_bookings.csv")
patient_track = pd.read_csv("data/updated_exports/patient_tracking.csv")
dept_status   = pd.read_csv("data/updated_exports/department_status_updated.csv")
what_if       = pd.read_csv("data/updated_exports/what_if_scenarios.csv")
shifts        = pd.read_csv("shifts.csv")
users         = pd.read_csv("users.csv")
data_dict     = pd.read_csv("data/updated_exports/data_dictionary.csv")

datasets = {
    "clean_data": clean_df,
    "staff_master": staff_master,
    "staff_schedule": staff_sched,
    "appointments": appointments,
    "or_bookings": or_bookings,
    "patient_tracking": patient_track,
    "department_status": dept_status,
    "what_if_scenarios": what_if,
    "shifts": shifts,
    "users": users,
}

for name, df in datasets.items():
    print(f"{name:30s} rows={len(df):6d}  cols={len(df.columns):3d}  nulls={df.isnull().sum().sum()}")
"""))

# Section 2: Patient flow audit
cells.append(md("## 2. Patient Flow (Training Data) Audit"))
cells.append(code("""
df = clean_df.copy()
print("Shape:", df.shape)
print("\\nDate range:", df["datetime"].min(), "to", df["datetime"].max())
print("\\nPatient stats:")
print(df["patients"].describe())
print("\\nWeekday vs weekend mean patients:")
print(df.groupby("is_weekend")["patients"].mean().rename({0: "Weekday", 1: "Weekend"}))
print("\\nHourly mean (selected hours):")
print(df.groupby("hour")["patients"].mean()[[0, 6, 12, 18, 23]].round(1))
print("\\nSeasonality check (mean by season):")
print(df.groupby("season")["patients"].mean().round(1))
print("\\nNull counts (should all be 0):")
nulls = df.isnull().sum()
print(nulls[nulls > 0] if nulls.any() else "No nulls found.")
print("\\nNegative/zero patients (should be 0):")
bad = df[df["patients"] <= 0]
print(len(bad), "rows" if len(bad) else "None")
print("\\nDuplicated timestamps (should be 0):")
print(df["datetime"].duplicated().sum(), "duplicates")
"""))

# Section 3: Staff master
cells.append(md("## 3. Staff Master Data Audit"))
cells.append(code("""
df = staff_master.copy()
print("Shape:", df.shape)
print("\\nRole distribution:")
print(df["role"].value_counts())
print("\\nDepartment distribution:")
print(df["department"].value_counts())
print("\\nDuplicate staff_id (should be 0):")
print(df["staff_id"].duplicated().sum())
print("\\nNull counts:")
print(df.isnull().sum())
print("\\nExperience range:", df["years_experience"].min(), "-", df["years_experience"].max())
"""))

# Section 4: Staff schedule
cells.append(md("## 4. Staff Schedule Audit"))
cells.append(code("""
df = staff_sched.copy()
print("Shape:", df.shape)
print("\\nUsername format sample (should be lowercase stf-XXXX):")
print(df["staff_username"].head(10).tolist())
print("\\nShift type distribution:")
print(df["shift_type"].value_counts())
print("\\nDepartment distribution:")
print(df["department"].value_counts())
print("\\nCross-reference: schedule staff_id in master staff_id")
schedule_ids = set(df["staff_id"].str.upper())
master_ids   = set(staff_master["staff_id"].str.upper())
missing = schedule_ids - master_ids
print(f"Missing from master: {len(missing)} (should be 0)")
if missing:
    print("  Missing:", missing)
"""))

# Section 5: Shifts (DB seed)
cells.append(md("## 5. Shifts CSV (DB Seed Source) Audit"))
cells.append(code("""
df = shifts.copy()
print("Shape:", df.shape)
print("\\nColumns:", list(df.columns))
print("\\nstaff_username case check (should all be lowercase):")
uppercase = df["staff_username"].str.contains("[A-Z]", regex=True, na=False).sum()
print(f"Uppercase staff_username: {uppercase} (should be 0)")
print("\\nShift type distribution:")
print(df["shift_type"].value_counts())
print("\\nNull counts:")
print(df.isnull().sum())
"""))

# Section 6: Appointments
cells.append(md("## 6. Appointments Audit"))
cells.append(code("""
df = appointments.copy()
print("Shape:", df.shape)
print("\\nDuplicate appointment_id (should be 0):")
print(df["appointment_id"].duplicated().sum())
print("\\nStatus distribution:")
print(df["status"].value_counts())
print("\\nDepartment distribution:")
print(df["department"].value_counts())
print("\\nPatient count stats:")
print(df["patient_count"].describe())
print("\\nNull counts (should all be 0):")
print(df.isnull().sum())
print("\\nDoctor names not in staff_master (name mismatch is expected):")
apt_doctors  = set(df["doctor"].dropna())
master_names = set(staff_master["staff_name"].str.strip())
missing = apt_doctors - master_names
print(f"{len(missing)} unmatched doctor names")
"""))

# Section 7: OR Bookings
cells.append(md("## 7. OR Bookings Audit"))
cells.append(code("""
df = or_bookings.copy()
print("Shape:", df.shape)
print("\\nDuplicate booking_id (should be 0):")
print(df["booking_id"].duplicated().sum())
print("\\nRoom distribution:")
print(df["room"].value_counts())
print("\\nStatus distribution:")
print(df["status"].value_counts())
print("\\nProcedure type distribution:")
print(df["procedure_type"].value_counts())
print("\\nDuration stats (minutes):")
print(df["procedure_duration_minutes"].describe())
print("\\nNull counts:")
nulls = df.isnull().sum()
print(nulls[nulls > 0] if nulls.any() else "No nulls found.")
"""))

# Section 8: Patient tracking
cells.append(md("## 8. Patient Tracking Audit"))
cells.append(code("""
df = patient_track.copy()
print("Shape:", df.shape)
print("\\nAdmission status distribution:")
print(df["admission_status"].value_counts())
print("\\nCurrent status distribution:")
print(df["current_status"].value_counts())
print("\\nLogic check: discharged patients must have discharge_datetime")
discharged_no_dt = len(df[(df["current_status"].str.lower() == "discharged") & (df["discharge_datetime"].isna())])
print(f"Violations: {discharged_no_dt} (should be 0)")

print("\\nLogic check: waiting patients must have no bed assigned")
waiting_with_bed = len(df[(df["admission_status"].str.lower() == "waiting") & (df["assigned_bed_id"].notna())])
print(f"Violations: {waiting_with_bed} (should be 0)")

print("\\nNational ID (should be 100% null for privacy):")
print(f"Null: {df['national_id_or_card_id_optional'].isna().sum()} / {len(df)}")
"""))

# Section 9: Department status
cells.append(md("## 9. Department Status Audit"))
cells.append(code("""
df = dept_status.copy()
print("Shape:", df.shape)
print("\\nDepartment overview:")
print(df[["department", "total_beds", "occupied_beds", "available_beds", "occupancy_rate", "pressure_level"]].to_string(index=False))
print("\\nBed math check: occupied + available == total")
bed_ok = (df["occupied_beds"] + df["available_beds"]) == df["total_beds"]
print("All departments correct:", bed_ok.all())
if not bed_ok.all():
    print("Failures:", df[~bed_ok]["department"].tolist())
print("\\nStaff shortages:")
print(df[["department", "doctor_shortage", "nurse_shortage", "bed_shortage"]].to_string(index=False))
"""))

# Section 10: What-if scenarios
cells.append(md("## 10. What-If Scenarios Audit"))
cells.append(code("""
df = what_if.copy()
print("Shape:", df.shape)
print("\\nScenario category distribution:")
print(df["scenario_category"].value_counts())
print("\\nSeverity distribution:")
print(df["severity_level"].value_counts())
print("\\nDuplicate scenario_id (should be 0):")
print(df["scenario_id"].duplicated().sum())
print("\\nDemand multiplier range:", df["demand_multiplier"].min(), "-", df["demand_multiplier"].max())
print("\\nNull counts:")
nulls = df.isnull().sum()
print(nulls[nulls > 0] if nulls.any() else "No nulls found.")
"""))

# Section 11: Users
cells.append(md("## 11. Users (Login Accounts) Audit"))
cells.append(code("""
df = users.copy()
print("Shape:", df.shape)
print("\\nRole distribution:")
print(df["role"].value_counts())
print("\\nDepartment distribution:")
print(df["department"].value_counts())
print("\\nDuplicate usernames (should be 0):")
print(df["username"].duplicated().sum())
print("\\nUser list (passwords redacted):")
print(df[["username", "name", "role", "department"]].to_string(index=False))
"""))

# Section 12: Cross-table relationships
cells.append(md("## 12. Cross-Table Relationship Integrity"))
cells.append(code("""
print("=== Relationship Integrity Summary ===\\n")

# 1. Schedule staff_id -> master
schedule_ids = set(staff_sched["staff_id"].str.upper())
master_ids   = set(staff_master["staff_id"].str.upper())
missing = schedule_ids - master_ids
print(f"[{'PASS' if not missing else 'FAIL'}] staff_schedule.staff_id -> staff_master.staff_id: {len(missing)} missing")

# 2. shifts.staff_username lowercase check
uppercase_count = shifts["staff_username"].str.contains("[A-Z]", regex=True, na=False).sum()
print(f"[{'PASS' if uppercase_count == 0 else 'FAIL'}] shifts.staff_username all lowercase: {uppercase_count} uppercase found")

# 3. users.username uniqueness
dup_users = users["username"].duplicated().sum()
print(f"[{'PASS' if dup_users == 0 else 'FAIL'}] users.username unique: {dup_users} duplicates")

# 4. Bed math
bed_ok = ((dept_status["occupied_beds"] + dept_status["available_beds"]) == dept_status["total_beds"]).all()
print(f"[{'PASS' if bed_ok else 'FAIL'}] dept_status bed math (occ+avail==total): {'all correct' if bed_ok else 'ERROR'}")

# 5. Patient tracking logic
discharged_no_dt = len(patient_track[(patient_track["current_status"].str.lower() == "discharged") & (patient_track["discharge_datetime"].isna())])
print(f"[{'PASS' if discharged_no_dt == 0 else 'FAIL'}] patient_tracking: discharged have discharge_datetime: {discharged_no_dt} violations")

waiting_with_bed = len(patient_track[(patient_track["admission_status"].str.lower() == "waiting") & (patient_track["assigned_bed_id"].notna())])
print(f"[{'PASS' if waiting_with_bed == 0 else 'FAIL'}] patient_tracking: waiting patients have no bed: {waiting_with_bed} violations")

# 6. Appointment duplicate IDs
dup_apt = appointments["appointment_id"].duplicated().sum()
print(f"[{'PASS' if dup_apt == 0 else 'FAIL'}] appointments.appointment_id unique: {dup_apt} duplicates")

# 7. OR booking duplicate IDs
dup_or = or_bookings["booking_id"].duplicated().sum()
print(f"[{'PASS' if dup_or == 0 else 'FAIL'}] or_bookings.booking_id unique: {dup_or} duplicates")

# 8. Training data completeness
null_patients = clean_df["patients"].isnull().sum()
print(f"[{'PASS' if null_patients == 0 else 'FAIL'}] clean_data.patients has no nulls: {null_patients} nulls")

neg_patients = (clean_df["patients"] <= 0).sum()
print(f"[{'PASS' if neg_patients == 0 else 'FAIL'}] clean_data.patients all positive: {neg_patients} zero/negative")

dup_ts = clean_df["datetime"].duplicated().sum()
print(f"[{'PASS' if dup_ts == 0 else 'FAIL'}] clean_data.datetime no duplicates: {dup_ts} duplicates")

print(f"\\nData dictionary: {len(data_dict)} column definitions across {data_dict['dataset'].nunique()} datasets")
"""))

# Section 13: Summary
cells.append(md("## 13. Audit Summary"))
cells.append(code("""
summary = {
    "clean_data rows": len(clean_df),
    "clean_data columns": len(clean_df.columns),
    "staff_master records": len(staff_master),
    "staff_schedule records": len(staff_sched),
    "appointments records": len(appointments),
    "or_bookings records": len(or_bookings),
    "patient_tracking records": len(patient_track),
    "department_status records": len(dept_status),
    "what_if_scenarios records": len(what_if),
    "shifts records (DB seed)": len(shifts),
    "user accounts": len(users),
    "data dictionary entries": len(data_dict),
}
for k, v in summary.items():
    print(f"  {k:40s}: {v}")
print("\\nAudit completed. All checks above should show [PASS].")
print("Any [FAIL] indicates a data issue that must be investigated.")
"""))

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "cells": cells,
}

out = "data/HRO_PS_DATA_AUDIT_NOTEBOOK.ipynb"
os.makedirs("data", exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"Notebook written: {out} ({os.path.getsize(out)//1024} KB, {len(cells)} cells)")
