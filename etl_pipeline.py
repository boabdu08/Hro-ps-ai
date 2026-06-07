import io
from typing import Optional

import pandas as pd

from database import SessionLocal
from models import Appointment, ORBooking, PatientFlow, Tenant
from settings import get_settings

REQUIRED_PATIENT_COLS = ["patients"]
REQUIRED_APPT_COLS = ["department", "patient_count"]
REQUIRED_OR_COLS = ["department", "status"]

# 10 MB upload guard — block obvious abuse before hitting pd.read_csv
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def validate_columns(df, required):
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")


def clean_dataframe(df):
    df = df.copy()
    df.fillna(0, inplace=True)
    return df


def _validate_upload(file) -> bytes:
    """Read file bytes and enforce size limit before parsing."""
    raw = file.read() if hasattr(file, "read") else file
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise ValueError(
            f"Upload exceeds 10 MB limit ({len(raw):,} bytes). "
            "Split the file or contact an administrator."
        )
    return raw


def _get_or_create_default_tenant_id(db) -> int:
    """Resolve the default tenant_id by slug (fallback for legacy callers)."""
    settings = get_settings()
    slug = (settings.default_tenant_slug or "demo-hospital").strip() or "demo-hospital"
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if tenant is None:
        tenant = Tenant(name="Demo Hospital", slug=slug)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return int(tenant.id)


def _resolve_tenant_id(db, tenant_id: Optional[int]) -> int:
    """Use the caller-supplied tenant_id when available, else fall back to default."""
    if tenant_id is not None:
        return int(tenant_id)
    return _get_or_create_default_tenant_id(db)


def ingest_patient_flow(file, tenant_id: Optional[int] = None):
    raw = _validate_upload(file)
    df = pd.read_csv(io.BytesIO(raw))
    validate_columns(df, REQUIRED_PATIENT_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tid = _resolve_tenant_id(db, tenant_id)
        for _, row in df.iterrows():
            db.add(PatientFlow(
                tenant_id=tid,
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


def ingest_appointments(file, tenant_id: Optional[int] = None):
    raw = _validate_upload(file)
    df = pd.read_csv(io.BytesIO(raw))
    validate_columns(df, REQUIRED_APPT_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tid = _resolve_tenant_id(db, tenant_id)
        for _, row in df.iterrows():
            db.add(Appointment(
                tenant_id=tid,
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


def ingest_or(file, tenant_id: Optional[int] = None):
    raw = _validate_upload(file)
    df = pd.read_csv(io.BytesIO(raw))
    validate_columns(df, REQUIRED_OR_COLS)
    df = clean_dataframe(df)
    db = SessionLocal()
    try:
        tid = _resolve_tenant_id(db, tenant_id)
        for _, row in df.iterrows():
            db.add(ORBooking(
                tenant_id=tid,
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
