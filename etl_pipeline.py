import pandas as pd

from database import SessionLocal
from models import Appointment, ORBooking, PatientFlow, Tenant
from settings import get_settings

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


def _get_or_create_default_tenant_id(db) -> int:
    """Resolve tenant_id for ingestion.

    Ingestion endpoints are admin-only, but they must still attach rows to a
    tenant to keep the runtime DB-first dashboard working.

    Historically some ingestion code inserted rows with tenant_id=None when the
    tenants table wasn't seeded yet. That breaks /patient_flow/latest which is
    tenant-scoped.
    """

    settings = get_settings()
    slug = (settings.default_tenant_slug or "demo-hospital").strip() or "demo-hospital"
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if tenant is None:
        tenant = Tenant(name="Demo Hospital", slug=slug)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return int(tenant.id)


def ingest_patient_flow(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_PATIENT_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tenant_id = _get_or_create_default_tenant_id(db)
        for _, row in df.iterrows():
            db.add(PatientFlow(
                tenant_id=int(tenant_id),
                datetime=str(row.get("datetime", "")) if row.get("datetime", "") != "" else None,
                patients=float(row["patients"]),
                day_of_week=int(row.get("day_of_week", 0)) if str(row.get("day_of_week", "")).strip() != "" else None,
                month=int(row.get("month", 0)) if str(row.get("month", "")).strip() != "" else None,
                is_weekend=int(row.get("is_weekend", 0)) if str(row.get("is_weekend", "")).strip() != "" else None,
                holiday=int(row.get("holiday", 0)) if str(row.get("holiday", "")).strip() != "" else None,
                weather=float(row.get("weather", 0)) if str(row.get("weather", "")).strip() != "" else None,
            ))
        db.commit()
    finally:
        db.close()


def ingest_appointments(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_APPT_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tenant_id = _get_or_create_default_tenant_id(db)
        for _, row in df.iterrows():
            db.add(Appointment(
                tenant_id=int(tenant_id),
                appointment_id=str(row.get("appointment_id", "")).strip(),
                department=str(row["department"]).strip(),
                doctor=str(row.get("doctor", "")).strip(),
                date=str(row.get("date", "")).strip(),
                time_slot=str(row.get("time_slot", "")).strip(),
                patient_count=int(row["patient_count"]),
                status=str(row.get("status", "scheduled")).strip() or "scheduled",
            ))
        db.commit()
    finally:
        db.close()


def ingest_or(file):
    df = pd.read_csv(file)
    validate_columns(df, REQUIRED_OR_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tenant_id = _get_or_create_default_tenant_id(db)
        for _, row in df.iterrows():
            db.add(ORBooking(
                tenant_id=int(tenant_id),
                booking_id=str(row.get("booking_id", "")).strip(),
                room=str(row.get("room", "")).strip(),
                doctor=str(row.get("doctor", "")).strip(),
                department=str(row["department"]).strip(),
                date=str(row.get("date", "")).strip(),
                time_slot=str(row.get("time_slot", "")).strip(),
                procedure=str(row.get("procedure", "")).strip(),
                status=str(row["status"]).strip(),
            ))
        db.commit()
    finally:
        db.close()



