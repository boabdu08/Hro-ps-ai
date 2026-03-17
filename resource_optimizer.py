import pandas as pd
import numpy as np
from database import SessionLocal
from models import Appointment, ORBooking, StaffShift


DEPARTMENTS = ["ER", "ICU", "General Ward", "Surgery", "Radiology"]


# ==========================================
# LOAD CURRENT STATE
# ==========================================
def load_state(db):
    state = {d: {"patients": 0, "doctors": 0, "nurses": 0} for d in DEPARTMENTS}

    for a in db.query(Appointment).all():
        if a.department in state:
            state[a.department]["patients"] += int(a.patient_count or 0)

    for s in db.query(StaffShift).all():
        if s.department in state:
            if s.role == "doctor":
                state[s.department]["doctors"] += 1
            elif s.role == "nurse":
                state[s.department]["nurses"] += 1

    return state


# ==========================================
# CALCULATE PRESSURE
# ==========================================
def calculate_pressure(state):
    pressure = {}

    for d, data in state.items():
        patients = data["patients"]
        doctors = max(1, data["doctors"])
        nurses = max(1, data["nurses"])

        score = (patients / doctors) * 1.5 + (patients / nurses)

        pressure[d] = score

    return pressure


# ==========================================
# REDISTRIBUTION
# ==========================================
def redistribute_resources(state, pressure):
    actions = []

    sorted_depts = sorted(pressure.items(), key=lambda x: x[1], reverse=True)

    high = sorted_depts[0][0]
    low = sorted_depts[-1][0]

    if pressure[high] > pressure[low] * 1.5:
        actions.append({
            "type": "staff",
            "action": f"Move 1 doctor from {low} to {high}"
        })

        actions.append({
            "type": "staff",
            "action": f"Move 2 nurses from {low} to {high}"
        })

    return actions


# ==========================================
# OR OPTIMIZATION
# ==========================================
def optimize_or(db):
    actions = []

    for booking in db.query(ORBooking).all():
        if booking.status == "pending":
            actions.append({
                "type": "or",
                "action": f"Prioritize OR booking {booking.booking_id}"
            })

    return actions


# ==========================================
# APPOINTMENT OPTIMIZATION
# ==========================================
def optimize_appointments(db):
    actions = []

    for a in db.query(Appointment).all():
        if int(a.patient_count or 0) > 20:
            actions.append({
                "type": "appointments",
                "action": f"Reschedule appointment {a.appointment_id}"
            })

    return actions


# ==========================================
# MAIN OPTIMIZER
# ==========================================
def optimize_resources(predicted_patients):
    db = SessionLocal()

    try:
        state = load_state(db)
        pressure = calculate_pressure(state)

        redistribution = redistribute_resources(state, pressure)
        or_actions = optimize_or(db)
        appt_actions = optimize_appointments(db)

        all_actions = redistribution + or_actions + appt_actions

        return {
            "pressure": pressure,
            "actions": all_actions
        }

    finally:
        db.close()