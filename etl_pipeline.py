import pandas as pd
from database import SessionLocal
from models import PatientFlow, Appointment, ORBooking


REQUIRED_PATIENT_COLS = ["patients"]
REQUIRED_APPT_COLS = ["department", "patient_count"]
REQUIRED_OR_COLS = ["department", "status"]


def validate_columns(df, required):
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")


def clean_dataframe(df):
    df = df.copy()
    df.fillna(0, inplace=True)
    return df


# =========================
# INGEST PATIENT FLOW
# =========================
def ingest_patient_flow(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_PATIENT_COLS)
    df = clean_dataframe(df)

    db = SessionLocal()
    try:
        for _, row in df.iterrows():
            db.add(PatientFlow(
                patients=float(row["patients"])
            ))
        db.commit()
    finally:
        db.close()


# =========================
# INGEST APPOINTMENTS
# =========================
def ingest_appointments(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_APPT_COLS)
    df = clean_dataframe(df)

    db = SessionLocal()
    try:
        for _, row in df.iterrows():
            db.add(Appointment(
                department=row["department"],
                patient_count=int(row["patient_count"]),
                status="scheduled"
            ))
        db.commit()
    finally:
        db.close()


# =========================
# INGEST OR BOOKINGS
# =========================
def ingest_or(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_OR_COLS)
    df = clean_dataframe(df)

    db = SessionLocal()
    try:
        for _, row in df.iterrows():
            db.add(ORBooking(
                department=row["department"],
                status=row["status"]
            ))
        db.commit()
    finally:
        db.close()