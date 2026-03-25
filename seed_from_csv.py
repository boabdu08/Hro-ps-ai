import os
import pandas as pd
from sqlalchemy import text
from database import engine, SessionLocal, Base
from settings import get_settings
from auth import hash_password, verify_password
from models import (
    PatientFlow,
    Appointment,
    ORBooking,
    StaffShift,
    Tenant,
    User,
    RecommendationRecord,
    AuditEvent,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()


def _get_or_create_default_tenant_id() -> int:
    settings = get_settings()
    slug = settings.default_tenant_slug
    row = db.query(Tenant).filter(Tenant.slug == slug).first()
    if row is None:
        row = Tenant(name="Demo Hospital", slug=slug)
        db.add(row)
        db.commit()
        db.refresh(row)
    return int(row.id)


def _should_skip_table(table_name: str) -> bool:
    """Idempotent seeding guard.

    Default behavior: if a table already has rows, skip seeding it.
    Override by setting env SEED_FORCE=true.
    """

    force = str(os.getenv("SEED_FORCE", "")).strip().lower() in {"1", "true", "yes", "y", "on"}
    if force:
        return False

    try:
        # Use a cheap COUNT(*) to detect existing data.
        count = db.execute(text(f"SELECT COUNT(1) FROM {table_name}")).scalar()  # type: ignore[arg-type]
        return int(count or 0) > 0
    except Exception:
        # If we can't determine, do not skip.
        return False


def safe_value(value):
    if pd.isna(value):
        return None
    return value


def seed_patients_flow():
    try:
        tenant_id = _get_or_create_default_tenant_id()
        if _should_skip_table("patients_flow"):
            print("patients_flow already has rows; skipping (set SEED_FORCE=true to override).")
            return
        df = pd.read_csv("clean_data.csv")
        for _, row in df.iterrows():
            record = PatientFlow(
                tenant_id=int(tenant_id),
                datetime=safe_value(row.get("datetime")),
                patients=safe_value(row.get("patients")),
                day_of_week=safe_value(row.get("day_of_week")),
                month=safe_value(row.get("month")),
                is_weekend=safe_value(row.get("is_weekend")),
                holiday=safe_value(row.get("holiday")),
                weather=safe_value(row.get("weather")),
            )
            db.add(record)
        db.commit()
        print("patients_flow seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding patients_flow:", e)


def seed_appointments():
    try:
        tenant_id = _get_or_create_default_tenant_id()
        if _should_skip_table("appointments"):
            print("appointments already has rows; skipping (set SEED_FORCE=true to override).")
            return
        df = pd.read_csv("appointments.csv")
        for _, row in df.iterrows():
            record = Appointment(
                tenant_id=int(tenant_id),
                appointment_id=safe_value(row.get("appointment_id")),
                department=safe_value(row.get("department")),
                doctor=safe_value(row.get("doctor")),
                date=safe_value(row.get("date")),
                time_slot=safe_value(row.get("time_slot")),
                patient_count=safe_value(row.get("patient_count")),
                status=safe_value(row.get("status")),
            )
            db.add(record)
        db.commit()
        print("appointments seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding appointments:", e)


def seed_or_bookings():
    try:
        tenant_id = _get_or_create_default_tenant_id()
        if _should_skip_table("or_bookings"):
            print("or_bookings already has rows; skipping (set SEED_FORCE=true to override).")
            return
        df = pd.read_csv("or_bookings.csv")
        for _, row in df.iterrows():
            record = ORBooking(
                tenant_id=int(tenant_id),
                booking_id=safe_value(row.get("booking_id")),
                room=safe_value(row.get("room")),
                doctor=safe_value(row.get("doctor")),
                department=safe_value(row.get("department")),
                date=safe_value(row.get("date")),
                time_slot=safe_value(row.get("time_slot")),
                procedure=safe_value(row.get("procedure")),
                status=safe_value(row.get("status")),
            )
            db.add(record)
        db.commit()
        print("or_bookings seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding or_bookings:", e)


def seed_staff_shifts():
    try:
        tenant_id = _get_or_create_default_tenant_id()
        if _should_skip_table("staff_shifts"):
            print("staff_shifts already has rows; skipping (set SEED_FORCE=true to override).")
            return
        df = pd.read_csv("shifts.csv")
        for _, row in df.iterrows():
            record = StaffShift(
                tenant_id=int(tenant_id),
                staff_username=safe_value(row.get("staff_username")),
                name=safe_value(row.get("name")),
                role=safe_value(row.get("role")),
                department=safe_value(row.get("department")),
                shift_date=safe_value(row.get("shift_date")),
                shift_type=safe_value(row.get("shift_type")),
                status=safe_value(row.get("status")),
            )
            db.add(record)
        db.commit()
        print("staff_shifts seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding staff_shifts:", e)


def seed_users():
    try:
        tenant_id = _get_or_create_default_tenant_id()
        # idempotent: skip usernames that already exist for this tenant.
        existing = {
            str(u.username).strip()
            for u in db.query(User).filter(User.tenant_id == int(tenant_id)).all()
            if u.username
        }
        df = pd.read_csv("users.csv")
        for _, row in df.iterrows():
            username = str(safe_value(row.get("username")) or "").strip()
            if not username or username in existing:
                continue

            raw_password = str(safe_value(row.get("password")) or "").strip()
            hashed = hash_password(raw_password) if raw_password else ""
            record = User(
                tenant_id=int(tenant_id),
                username=username,
                name=safe_value(row.get("name")),
                role=safe_value(row.get("role")),
                department=safe_value(row.get("department")),
                password=hashed,
            )
            db.add(record)
        db.commit()
        print("users seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding users:", e)


def ensure_demo_auth_users():
    """Ensure demo tenant + baseline demo users exist with bcrypt passwords.

    This hardens local-dev and fresh deployments even if users.csv changes.
    Default password (required by task): 123456.
    """

    tenant_id = _get_or_create_default_tenant_id()
    desired = [
        {"username": "admin1", "name": "Hospital Admin", "role": "admin", "department": "Management"},
        {"username": "doctor1", "name": "Dr. Ahmed", "role": "doctor", "department": "ER"},
        {"username": "nurse1", "name": "Nurse Mona", "role": "nurse", "department": "General Ward"},
    ]

    pwd = "123456"
    hashed = hash_password(pwd)

    existing = {u.username: u for u in db.query(User).filter(User.tenant_id == int(tenant_id)).all()}
    changed = 0
    for u in desired:
        row = existing.get(u["username"])
        if row is None:
            db.add(
                User(
                    tenant_id=int(tenant_id),
                    username=u["username"],
                    name=u["name"],
                    role=u["role"],
                    department=u["department"],
                    password=hashed,
                )
            )
            changed += 1
        else:
            # Ensure password matches expected demo password (123456), and is hashed.
            if (not row.password) or ("$" not in str(row.password)) or (not verify_password(pwd, str(row.password))):
                row.password = hashed
                changed += 1
            row.name = row.name or u["name"]
            row.role = row.role or u["role"]
            row.department = row.department or u["department"]

    if changed:
        db.commit()
        print(f"demo auth users ensured/updated: {changed}")


def seed_recommendation_log():
    try:
        if not os.path.exists("recommendation_log.csv"):
            print("recommendation_log.csv not found. Skipping recommendation log seeding.")
            return

        tenant_id = _get_or_create_default_tenant_id()
        df = pd.read_csv("recommendation_log.csv")
        if df.empty:
            print("recommendation_log.csv is empty. Skipping recommendation log seeding.")
            return

        existing_ids = {
            str(r.recommendation_id).strip()
            for r in db.query(RecommendationRecord)
            .filter(RecommendationRecord.tenant_id == int(tenant_id))
            .all()
            if r.recommendation_id
        }

        # Repo schema stores recommendations in RecommendationRecord.
        # CSV columns vary by version; we map to the closest supported fields.
        for _, row in df.iterrows():
            rec_id = str(safe_value(row.get("recommendation_id") or "")).strip()
            if not rec_id or rec_id in existing_ids:
                continue
            record = RecommendationRecord(
                tenant_id=int(tenant_id),
                recommendation_id=rec_id,
                timestamp=str(safe_value(row.get("timestamp") or "")).strip() or None,
                rec_type=str(safe_value(row.get("type") or row.get("rec_type") or "general")).strip() or "general",
                message=str(safe_value(row.get("message") or row.get("recommendation") or "")).strip() or "",
                status=str(safe_value(row.get("status") or "pending")).strip() or "pending",
                approved_by=str(safe_value(row.get("approved_by") or row.get("approver") or "")).strip() or "",
                execution_status=str(safe_value(row.get("execution_status") or "")).strip() or "",
                execution_note=str(safe_value(row.get("execution_note") or "")).strip() or "",
                affected_entities=str(safe_value(row.get("affected_files") or row.get("affected_entities") or "")).strip() or "",
            )
            db.add(record)

        db.commit()
        print("recommendation_log seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding recommendation_log:", e)


def seed_audit_log():
    try:
        if not os.path.exists("audit_log.csv"):
            print("audit_log.csv not found. Skipping audit log seeding.")
            return

        tenant_id = _get_or_create_default_tenant_id()
        df = pd.read_csv("audit_log.csv")
        # Repo schema stores audit events in AuditEvent.
        for _, row in df.iterrows():
            audit_id = str(safe_value(row.get("audit_id") or "")).strip()
            if not audit_id:
                continue
            record = AuditEvent(
                tenant_id=int(tenant_id),
                audit_id=audit_id,
                timestamp=str(safe_value(row.get("timestamp") or "")).strip() or None,
                action=str(safe_value(row.get("action") or "")).strip() or "",
                actor=str(safe_value(row.get("actor") or "")).strip() or "",
                target=str(safe_value(row.get("target") or "")).strip() or "",
                status=str(safe_value(row.get("status") or "")).strip() or "",
                details=str(safe_value(row.get("details") or "")).strip() or "",
            )
            db.add(record)
        db.commit()
        print("audit_log seeded successfully.")
    except Exception as e:
        db.rollback()
        print("Error seeding audit_log:", e)


if __name__ == "__main__":
    try:
        seed_patients_flow()
        seed_appointments()
        seed_or_bookings()
        seed_staff_shifts()
        seed_users()
        ensure_demo_auth_users()
        seed_recommendation_log()
        seed_audit_log()
        print("CSV to PostgreSQL seeding completed.")
    finally:
        db.close()