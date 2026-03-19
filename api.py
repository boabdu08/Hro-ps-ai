from typing import List, Optional
import json
from datetime import datetime, timedelta
import logging

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File, APIRouter, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy import text

from artifacts import artifact_diagnostics, load_manifest
from feature_spec import FEATURE_COLUMNS, ARIMAX_EXOG_COLUMNS, SEQUENCE_LENGTH
from evaluation_service import compare_models
from database import get_db, init_db, engine
from db_migrations import ensure_alerts_notifications, ensure_message_extensions, ensure_multi_tenant, ensure_pipeline_runs
from models import Alert, Notification, NotificationPreference, Tenant, User, PatientFlow, MessageLog, MessageRead, OptimizationRun, PipelineRun
from resource_optimizer import optimize_resources
from schemas import LoginRequest
from etl_pipeline import ingest_patient_flow, ingest_appointments, ingest_or
from auth import create_token, bearer_from_header, decode_token, verify_password
from forecast_inference import load_assets as _load_assets, predict_hybrid as _predict_hybrid
import os

DATABASE_URL = os.getenv("DATABASE_URL")
app = FastAPI(title="Hospital AI API")
logging.basicConfig(level=logging.INFO)

# Routers (keep public URLs stable; we can version later)
system_router = APIRouter(tags=["system"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
messages_router = APIRouter(prefix="/messages", tags=["messages"])
patient_flow_router = APIRouter(prefix="/patient_flow", tags=["patient_flow"])
ml_router = APIRouter(tags=["ml"])
upload_router = APIRouter(prefix="/upload", tags=["upload"])

# Alerts + notifications
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


@app.on_event("startup")
def _startup_create_tables():
    # Safe default for this repo: ensure tables exist at runtime.
    # For production, migrate to Alembic migrations and remove create_all.
    init_db()
    ensure_multi_tenant(engine)
    ensure_message_extensions(engine)
    ensure_alerts_notifications(engine)
    ensure_pipeline_runs(engine)

    # Optional: run scheduler inside API process (dev/single-instance only).
    from settings import get_settings

    if get_settings().scheduler_run_in_api:
        import asyncio
        from scheduler import scheduler_loop

        asyncio.create_task(scheduler_loop())

LEGACY_MESSAGES_FILE = "messages_log.csv"  # import-only (not runtime)
LEGACY_MESSAGE_COLS = [
    "message_id",
    "timestamp",
    "sender_role",
    "sender_name",
    "target_role",
    "target_department",
    "priority",
    "category",
    "title",
    "message",
    "status",
    "reply",
    "reply_by",
    "reply_timestamp",
    "acknowledged",
    "archived",
]

FEATURE_COUNT = len(FEATURE_COLUMNS)


def _get_assets_or_503():
    try:
        return _load_assets()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Forecasting artifacts not ready: {e}")

ADMIN_MESSAGE_TEMPLATES = [
    {
        "category": "emergency",
        "priority": "critical",
        "title": "Emergency Surge Alert",
        "message": "Emergency surge alert: all available staff should review current assignments and prepare for overflow response.",
        "target_role": "all",
        "target_department": "All Departments",
    },
    {
        "category": "coverage",
        "priority": "high",
        "title": "Doctor Coverage Request",
        "message": "Urgent coverage needed: an additional doctor is required to cover the current shift immediately.",
        "target_role": "doctor",
        "target_department": "All Departments",
    },
    {
        "category": "coverage",
        "priority": "high",
        "title": "Nurse Coverage Request",
        "message": "Urgent coverage needed: an additional nurse is required to support the active department.",
        "target_role": "nurse",
        "target_department": "All Departments",
    },
    {
        "category": "shift",
        "priority": "high",
        "title": "Shift Change Notice",
        "message": "Shift update notice: please review your latest assignment and acknowledge the change.",
        "target_role": "all",
        "target_department": "All Departments",
    },
    {
        "category": "capacity",
        "priority": "high",
        "title": "Bed Shortage Warning",
        "message": "Capacity warning: bed pressure is increasing. Review admissions and discharge flow immediately.",
        "target_role": "all",
        "target_department": "All Departments",
    },
]

STAFF_QUICK_REPLIES = [
    "تم",
    "تم التنفيذ",
    "وصلت",
    "جاري التنفيذ",
    "نحتاج دعم دكاترة",
    "نحتاج دعم تمريض",
    "يوجد عجز",
    "لا أستطيع التغطية الآن",
]


class PredictRequest(BaseModel):
    sequence: List[List[float]]


class SimulateRequest(BaseModel):
    predicted_patients: float
    beds_available: int
    doctors_available: int
    demand_increase_percent: float = 0


class ExplainRequest(BaseModel):
    sequence: List[List[float]]


class SendMessageRequest(BaseModel):
    sender_role: str
    sender_name: str
    target_role: str = "all"
    target_department: str = "All Departments"
    # Priority levels (new): low | medium | high | critical
    # Legacy values (supported): normal
    priority: str = "medium"
    # Message types (new): normal | alert | critical | decision
    message_type: str = "normal"
    category: str = "general"
    is_pinned: bool = False
    title: str
    message: str


class ReplyMessageRequest(BaseModel):
    message_id: str
    reply: str
    reply_by: str


class MessageActionRequest(BaseModel):
    message_id: str


class MessageUserActionRequest(BaseModel):
    message_id: str
    # Optional for admin acting on behalf of a user; otherwise inferred from JWT.
    username: Optional[str] = None


class EvaluateRequest(BaseModel):
    actual: List[float]
    lstm: List[float]
    arimax: List[float]
    hybrid: List[float]


class AlertActionRequest(BaseModel):
    alert_id: str


class MarkNotificationReadRequest(BaseModel):
    notification_id: str


class CreateAlertRequest(BaseModel):
    title: str
    message: str
    alert_type: str = "operational_alert"
    priority: str = "medium"
    related_department: Optional[str] = None
    target_role: str = "all"
    target_department: str = "All Departments"


def get_token_payload(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extract and decode JWT from Authorization: Bearer ..."""

    token = bearer_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        return decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(roles: List[str]):
    allowed = {r.lower() for r in roles}

    def _dep(payload: dict = Depends(get_token_payload)) -> dict:
        role = str(payload.get("role", "")).lower()
        if role not in allowed:
            raise HTTPException(status_code=403, detail=f"Forbidden for role={role}")
        return payload

    return _dep


require_admin = require_role(["admin"])
require_staff_or_admin = require_role(["admin", "doctor", "nurse"])


def build_engineered_sequence_from_patient_flow(rows: List[PatientFlow]) -> List[List[float]]:
    """Build engineered sequence from DB rows.

    NOTE: This uses the same deterministic feature engineering from Phase 1.
    """

    from forecast_features import build_latest_sequence_from_rows

    payload_rows = [
        {
            "patients": float(r.patients),
            "day_of_week": float(r.day_of_week or 0),
            "month": float(r.month or 0),
            "is_weekend": float(r.is_weekend or 0),
            "holiday": float(r.holiday or 0),
            "weather": float(r.weather or 0),
            "datetime": getattr(r, "datetime", None),
        }
        for r in rows
    ]

    return build_latest_sequence_from_rows(payload_rows)


def normalize_text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and np.isnan(value):
        return default
    text = str(value).strip()
    if text.lower() == "nan":
        return default
    return text if text else default


def normalize_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in ["true", "1", "yes", "y"]:
        return True
    if text in ["false", "0", "no", "n", ""]:
        return False
    return default


def parse_datetime_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def validate_sequence_shape(arr: np.ndarray):
    return arr.shape == (SEQUENCE_LENGTH, FEATURE_COUNT)


def predict_hybrid(sequence_array: np.ndarray):
    # Delegate to canonical inference module.
    return _predict_hybrid(sequence_array)


def predict_emergency_load(predicted_patients: float):
    if predicted_patients < 80:
        return "LOW"
    if predicted_patients < 120:
        return "MEDIUM"
    return "HIGH"


def allocate_beds(predicted_patients: int, available_beds: int):
    if predicted_patients <= available_beds:
        return {
            "status": "OK",
            "beds_used": predicted_patients,
            "beds_remaining": available_beds - predicted_patients,
            "shortage": 0,
        }

    shortage = predicted_patients - available_beds
    return {
        "status": "SHORTAGE",
        "beds_used": available_beds,
        "beds_remaining": 0,
        "shortage": shortage,
    }


def calculate_recommended_resources(predicted_patients: float):
    return {
        "beds_needed": int(np.ceil(predicted_patients * 1.15)),
        "doctors_needed": max(1, int(np.ceil(predicted_patients / 6.0))),
        "nurses_needed": max(1, int(np.ceil(predicted_patients / 3.5))),
    }


def explain_feature_importance(sequence_array: np.ndarray):
    base_result = predict_hybrid(sequence_array)
    base_pred = float(base_result["hybrid_prediction"])
    impacts = []

    for i, feature_name in enumerate(FEATURE_COLUMNS):
        modified = sequence_array.copy()

        if feature_name == "patients":
            modified[-1, i] = modified[-1, i] * 1.10
        elif feature_name in ["day_of_week", "month", "weather", "hour", "trend_feature"]:
            modified[-1, i] = modified[-1, i] + 1
        elif feature_name in ["is_weekend", "holiday"]:
            modified[-1, i] = 1 - modified[-1, i]
        else:
            modified[-1, i] = modified[-1, i] * 1.05

        new_pred = float(predict_hybrid(modified)["hybrid_prediction"])
        impacts.append({"feature": feature_name, "impact": float(new_pred - base_pred)})

    impacts = sorted(impacts, key=lambda x: abs(x["impact"]), reverse=True)
    return {"base_prediction": float(base_pred), "feature_impacts": impacts}


# (duplicate removed)


def serialize_message_row(row: MessageLog) -> dict:
    return {
        "message_id": normalize_text(row.message_id),
        "timestamp": normalize_text(row.timestamp),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "type": normalize_text(getattr(row, "message_type", "normal"), "normal"),
        "is_pinned": bool(getattr(row, "is_pinned", False)),
        "sender_role": normalize_text(row.sender_role),
        "sender_name": normalize_text(row.sender_name),
        "target_role": normalize_text(row.target_role, "all"),
        "target_department": normalize_text(row.target_department, "All Departments"),
        "priority": normalize_text(row.priority, "normal"),
        "category": normalize_text(row.category, "general"),
        "title": normalize_text(row.title),
        "message": normalize_text(row.message),
        "status": normalize_text(row.status, "sent"),
        "reply": normalize_text(row.reply),
        "reply_by": normalize_text(row.reply_by),
        "reply_timestamp": normalize_text(row.reply_timestamp),
        "acknowledged": normalize_text(row.acknowledged, "no"),
        "archived": bool(row.archived),
    }


def _get_user_by_username_or_401(db: Session, username: str, tenant_id: int | None = None) -> User:
    q = db.query(User).filter(User.username == normalize_text(username))
    if tenant_id is not None:
        q = q.filter(User.tenant_id == int(tenant_id))
    user = q.first()
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def _get_default_tenant_id(db: Session) -> int:
    """Resolve default tenant id from settings/default slug."""

    from settings import get_settings

    slug = get_settings().default_tenant_slug
    row = db.query(Tenant).filter(Tenant.slug == normalize_text(slug)).first()
    if row is None:
        # should not happen because ensure_multi_tenant inserts it, but keep safe.
        row = Tenant(name="Demo Hospital", slug=normalize_text(slug))
        db.add(row)
        db.commit()
        db.refresh(row)
    return int(row.id)


def get_tenant_id(payload: dict, db: Session) -> int:
    """Tenant context for the current request.

    Backwards compatible:
    - if JWT has tenant_id -> use it
    - else use default tenant id
    """

    tid = payload.get("tenant_id")
    if tid is None:
        return _get_default_tenant_id(db)
    try:
        return int(tid)
    except Exception:
        return _get_default_tenant_id(db)


def _get_current_user(db: Session, payload: dict) -> User:
    tid = get_tenant_id(payload, db)
    return _get_user_by_username_or_401(db, normalize_text(payload.get("username")), tenant_id=tid)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def _get_or_create_notification_pref(db: Session, user_id: int, tenant_id: int) -> NotificationPreference:
    row = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == int(user_id), NotificationPreference.tenant_id == int(tenant_id))
        .first()
    )
    if row is None:
        row = NotificationPreference(user_id=int(user_id), tenant_id=int(tenant_id))
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _should_notify_user(pref: NotificationPreference, priority: str, channel: str = "in_app") -> bool:
    prio = normalize_text(priority, "medium").lower()
    if channel == "in_app" and not bool(pref.receive_in_app):
        return False
    if pref.critical_only and prio != "critical":
        return False
    return True


def _users_for_scope(
    db: Session,
    tenant_id: int,
    target_role: Optional[str],
    target_department: Optional[str],
) -> list[User]:
    """Resolve recipients by role + department.

    - role: exact match or "all" => all roles
    - department: exact match (case-insensitive) or "All Departments"/"all" => all departments
    """

    q = db.query(User).filter(User.tenant_id == int(tenant_id))
    role = normalize_text(target_role).lower()
    dept = normalize_text(target_department).lower()

    if role and role not in {"all", "*"}:
        q = q.filter(User.role.ilike(role))
    if dept and dept not in {"all departments", "all", "*"}:
        q = q.filter(User.department.ilike(normalize_text(target_department)))
    return q.all()


def create_alert_and_notify(
    *,
    db: Session,
    tenant_id: int,
    title: str,
    message: str,
    alert_type: str,
    priority: str,
    source: str,
    related_department: Optional[str] = None,
    generated_by_rule: Optional[str] = None,
    recommendation_summary: Optional[str] = None,
    target_role: Optional[str] = None,
    target_department: Optional[str] = None,
    dedupe_window_minutes: int = 30,
) -> Alert:
    """Create an alert (with simple dedupe) and create in-app notifications."""

    now = datetime.now()
    prio = normalize_text(priority, "medium").lower()
    if prio == "normal":
        prio = "medium"
    if prio not in {"low", "medium", "high", "critical"}:
        prio = "medium"

    a_type = normalize_text(alert_type, "operational_alert").lower()
    if a_type not in {
        "capacity_alert",
        "staffing_alert",
        "forecast_alert",
        "optimization_alert",
        "critical_alert",
        "operational_alert",
    }:
        a_type = "operational_alert"

    # Dedupe: same type+dept+title within window and still active.
    window_start = now - timedelta(minutes=int(dedupe_window_minutes))
    existing = (
        db.query(Alert)
        .filter(
            Alert.tenant_id == int(tenant_id),
            Alert.is_active.is_(True),
            Alert.alert_type.ilike(a_type),
            (Alert.related_department.ilike(normalize_text(related_department)) if related_department else True),
            Alert.title.ilike(normalize_text(title)),
            Alert.created_at >= window_start,
        )
        .order_by(Alert.id.desc())
        .first()
    )
    if existing is not None:
        alert = existing
    else:
        alert = Alert(
            tenant_id=int(tenant_id),
            alert_id=_new_id("ALERT"),
            title=normalize_text(title, "Alert"),
            message=normalize_text(message),
            alert_type=a_type,
            priority=prio,
            source=normalize_text(source, "system"),
            related_department=normalize_text(related_department) if related_department else None,
            is_active=True,
            is_acknowledged=False,
            generated_by_rule=normalize_text(generated_by_rule) if generated_by_rule else None,
            recommendation_summary=normalize_text(recommendation_summary) if recommendation_summary else None,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

    # Create notifications for recipients.
    recipients = _users_for_scope(db, tenant_id, target_role, target_department)
    for u in recipients:
        pref = _get_or_create_notification_pref(db, int(u.id), tenant_id=int(tenant_id))
        if not _should_notify_user(pref, prio, channel="in_app"):
            continue

        # Avoid notification spam: if user already has a notification for this alert
        # created recently, don't create another.
        existing_notif = (
            db.query(Notification)
            .filter(
                Notification.tenant_id == int(tenant_id),
                Notification.user_id == int(u.id),
                Notification.alert_id == int(alert.id),
                Notification.created_at >= window_start,
            )
            .first()
        )
        if existing_notif is not None:
            continue

        notif = Notification(
            notification_id=_new_id("NTF"),
            tenant_id=int(tenant_id),
            user_id=int(u.id),
            alert_id=int(alert.id),
            channel="in_app",
            title=normalize_text(title, "Alert"),
            body=normalize_text(message),
            status="delivered",
            delivered_at=now,
        )
        db.add(notif)

    db.commit()
    return alert


def _message_is_auto_archived(row: MessageLog, now: datetime) -> bool:
    """Compute time-based auto-archive.

    Rules:
    - pinned messages: never auto-archive
    - critical messages: never auto-archive
    - others: auto-archive after 8 hours from created_at (fallback: timestamp parse)
    """

    if bool(getattr(row, "is_pinned", False)):
        return False

    msg_type = normalize_text(getattr(row, "message_type", "normal"), "normal").lower()
    prio = normalize_text(getattr(row, "priority", "medium"), "medium").lower()
    if msg_type == "critical" or prio == "critical":
        return False

    created_at = getattr(row, "created_at", None)
    if created_at is None:
        # best-effort parse from legacy timestamp "YYYY-mm-dd HH:MM:SS"
        try:
            created_at = datetime.strptime(normalize_text(row.timestamp), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False

    return now >= created_at + timedelta(hours=8)


def _serialize_message_for_user(row: MessageLog, user_id: int, db: Session, now: datetime) -> dict:
    payload = serialize_message_row(row)

    # Per-user state.
    read_row = (
        db.query(MessageRead)
        .filter(MessageRead.message_id == row.message_id, MessageRead.user_id == int(user_id))
        .first()
    )
    payload["is_read"] = bool(read_row.is_read) if read_row else False
    payload["read_at"] = read_row.read_at.isoformat() if read_row and read_row.read_at else None
    payload["user_archived"] = bool(read_row.is_archived) if read_row else False

    payload["auto_archived"] = _message_is_auto_archived(row, now)
    return payload


def _serialize_joined_message(row: MessageLog, read_row: Optional[MessageRead], now: datetime) -> dict:
    """Serialize when message_reads is already joined (avoids N+1 queries)."""

    payload = serialize_message_row(row)
    payload["is_read"] = bool(read_row.is_read) if read_row else False
    payload["read_at"] = read_row.read_at.isoformat() if read_row and read_row.read_at else None
    payload["user_archived"] = bool(read_row.is_archived) if read_row else False
    payload["auto_archived"] = _message_is_auto_archived(row, now)
    return payload


def bootstrap_messages_from_csv_if_needed(db: Session):
    # DB-first runtime: do not bootstrap from CSV.
    return


@app.middleware("http")
async def log_requests(request, call_next):
    logging.info("%s %s", request.method, request.url)
    response = await call_next(request)
    return response


@system_router.get("/")
def home(_token: dict = Depends(require_staff_or_admin)):
    return {"message": "Hospital AI API is running"}


@system_router.get("/health")
def health(_token: dict = Depends(require_staff_or_admin)):
    return {"status": "ok"}


@system_router.get("/health/db")
def health_db(_token: dict = Depends(require_staff_or_admin)):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db_unhealthy: {e}")


@system_router.get("/status")
def system_status(_token: dict = Depends(require_staff_or_admin)):
    diag = artifact_diagnostics()
    manifest = load_manifest()
    weights = None

    if not diag.get("missing"):
        try:
            assets = _get_assets_or_503()
            weights = {
                "lstm": float(getattr(assets, "lstm_weight", None)),
                "arimax": float(getattr(assets, "arimax_weight", None)),
            }
        except Exception:
            weights = None

    return {
        "system": "Hospital AI",
        "model": "Hybrid Forecast (LSTM + ARIMAX)",
        "status": "running",
        "hybrid_weights": weights or {"lstm": None, "arimax": None},
        "feature_count": FEATURE_COUNT,
        "sequence_length": SEQUENCE_LENGTH,
        "artifacts": diag,
        "artifact_manifest": manifest,
    }


@system_router.get("/pipeline/status")
def pipeline_status(
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """Return latest scheduler pipeline run for the current tenant."""

    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(PipelineRun)
        .filter(PipelineRun.tenant_id == int(tenant_id))
        .order_by(PipelineRun.id.desc())
        .first()
    )
    if row is None:
        return {"tenant_id": int(tenant_id), "latest": None}
    try:
        details = json.loads(row.details_json) if row.details_json else None
    except Exception:
        details = None

    return {
        "tenant_id": int(tenant_id),
        "latest": {
            "run_id": row.run_id,
            "status": row.status,
            "step": row.step,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "details": details,
        },
    }


@system_router.get("/feature_config")
def get_feature_config(_token: dict = Depends(require_staff_or_admin)):
    return {
        "feature_count": FEATURE_COUNT,
        "sequence_length": SEQUENCE_LENGTH,
        "feature_columns": FEATURE_COLUMNS,
        "arimax_exog_columns": ARIMAX_EXOG_COLUMNS,
    }


@system_router.get("/artifacts/manifest")
def get_artifacts_manifest(_token: dict = Depends(require_admin)):
    return load_manifest()


@messages_router.get("/templates")
def get_message_templates(_token: dict = Depends(require_staff_or_admin)):
    return {
        "admin_templates": ADMIN_MESSAGE_TEMPLATES,
        "staff_quick_replies": STAFF_QUICK_REPLIES,
    }


@messages_router.get("")
def get_messages(
    role: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    include_archived: bool = Query(default=False),
    # filters
    message_type: Optional[str] = Query(default=None, alias="type"),
    priority: Optional[str] = Query(default=None),
    pinned_only: bool = Query(default=False),
    sender_name: Optional[str] = Query(default=None),
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    bootstrap_messages_from_csv_if_needed(db)
    query = db.query(MessageLog)

    tenant_id = get_tenant_id(_token, db)

    # Resolve current user for per-user read state.
    current_user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    user_id = int(current_user.id)
    now = datetime.now()

    # Tenant isolation
    query = query.filter(MessageLog.tenant_id == int(tenant_id))

    if role:
        role = normalize_text(role).lower()
        query = query.filter(
            (MessageLog.target_role.ilike(role))
            | (MessageLog.target_role.ilike("all"))
        )

    if department:
        department = normalize_text(department).lower()
        query = query.filter(
            (MessageLog.target_department.ilike(department))
            | (MessageLog.target_department.ilike("all departments"))
            | (MessageLog.target_department.ilike("all"))
        )

    if sender_name:
        query = query.filter(MessageLog.sender_name.ilike(normalize_text(sender_name)))

    if message_type:
        query = query.filter(MessageLog.message_type.ilike(normalize_text(message_type).lower()))

    if priority:
        query = query.filter(MessageLog.priority.ilike(normalize_text(priority).lower()))

    if pinned_only:
        query = query.filter(MessageLog.is_pinned.is_(True))

    # Fetch messages with per-user state via outer join to message_reads.
    rows = (
        query.outerjoin(
            MessageRead,
            and_(MessageRead.message_id == MessageLog.message_id, MessageRead.user_id == user_id),
        )
        .add_entity(MessageRead)
        .order_by(MessageLog.id.desc())
        .limit(limit)
        .all()
    )

    serialized: list[dict] = []
    unread_count = 0
    for msg_row, read_row in rows:
        msg = _serialize_joined_message(msg_row, read_row, now=now)

        # Determine visibility according to lifecycle rules.
        # A message is considered archived for this user if:
        # - user_archived OR
        # - auto_archived (unless critical/pinned) OR
        # - legacy global archived
        is_archived_effective = bool(msg.get("user_archived")) or bool(msg.get("auto_archived")) or bool(msg.get("archived"))
        if not include_archived and is_archived_effective:
            continue
        if include_archived and not is_archived_effective:
            continue

        if unread_only and bool(msg.get("is_read")):
            continue

        if not msg.get("is_read") and not is_archived_effective:
            unread_count += 1

        msg["archived"] = is_archived_effective
        serialized.append(msg)

    return {
        "messages": serialized,
        "quick_replies": STAFF_QUICK_REPLIES,
        "unread_count": int(unread_count),
        "user": {
            "id": int(user_id),
            "username": normalize_text(current_user.username),
            "role": normalize_text(current_user.role),
            "department": normalize_text(current_user.department),
        },
    }


@messages_router.post("/send")
def send_message(
    payload: SendMessageRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    bootstrap_messages_from_csv_if_needed(db)

    # Normalize new enums while keeping backward compatibility.
    raw_priority = normalize_text(payload.priority, "medium").lower()
    if raw_priority == "normal":
        raw_priority = "medium"
    if raw_priority not in {"low", "medium", "high", "critical"}:
        raw_priority = "medium"

    raw_type = normalize_text(payload.message_type, "normal").lower()
    if raw_type not in {"normal", "alert", "critical", "decision"}:
        raw_type = "normal"

    tenant_id = get_tenant_id(_token, db)
    now_str = parse_datetime_now()
    row = MessageLog(
        tenant_id=int(tenant_id),
        message_id=f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        timestamp=now_str,
        created_at=datetime.now(),
        sender_role=normalize_text(payload.sender_role, "admin"),
        sender_name=normalize_text(payload.sender_name, "Unknown Sender"),
        target_role=normalize_text(payload.target_role, "all"),
        target_department=normalize_text(payload.target_department, "All Departments"),
        priority=raw_priority,
        message_type=raw_type,
        is_pinned=bool(payload.is_pinned),
        category=normalize_text(payload.category, "general"),
        title=normalize_text(payload.title, "Untitled Message"),
        message=normalize_text(payload.message),
        status="sent",
        reply="",
        reply_by="",
        reply_timestamp="",
        acknowledged="no",
        archived=False,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "status": "sent",
        "message": "Message sent successfully.",
        "data": serialize_message_row(row),
    }


@messages_router.get("/unread_count")
def get_unread_count(
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """Fast unread counter endpoint for the current user."""

    tenant_id = get_tenant_id(_token, db)
    current_user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    user_id = int(current_user.id)
    now = datetime.now()

    # Fetch recent messages for the user's scope, then compute read state.
    # Keep this efficient: only look at last N rows.
    query = db.query(MessageLog).filter(MessageLog.tenant_id == int(tenant_id))
    role = normalize_text(_token.get("role")).lower()
    department = normalize_text(_token.get("department")).lower()

    if role:
        query = query.filter((MessageLog.target_role.ilike(role)) | (MessageLog.target_role.ilike("all")))
    if department:
        query = query.filter(
            (MessageLog.target_department.ilike(department))
            | (MessageLog.target_department.ilike("all departments"))
            | (MessageLog.target_department.ilike("all"))
        )

    rows = (
        query.outerjoin(
            MessageRead,
            and_(MessageRead.message_id == MessageLog.message_id, MessageRead.user_id == user_id),
        )
        .add_entity(MessageRead)
        .order_by(MessageLog.id.desc())
        .limit(200)
        .all()
    )

    unread = 0
    for msg_row, read_row in rows:
        msg = _serialize_joined_message(msg_row, read_row, now=now)
        archived_effective = bool(msg.get("user_archived")) or bool(msg.get("auto_archived")) or bool(msg.get("archived"))
        if archived_effective:
            continue
        if not msg.get("is_read"):
            unread += 1
    return {"unread_count": int(unread)}


@messages_router.post("/reply")
def reply_to_message(
    payload: ReplyMessageRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    bootstrap_messages_from_csv_if_needed(db)

    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(MessageLog)
        .filter(MessageLog.tenant_id == int(tenant_id), MessageLog.message_id == normalize_text(payload.message_id))
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Message not found.")

    row.reply = normalize_text(payload.reply)
    row.reply_by = normalize_text(payload.reply_by)
    row.reply_timestamp = parse_datetime_now()
    row.status = "updated"
    # Legacy: keep old fields but do NOT use them for per-user state.
    row.acknowledged = "yes"
    # Do not auto-archive globally; per-user archive is handled via MessageRead.

    db.commit()
    db.refresh(row)

    return {
        "status": "updated",
        "message": "Reply saved successfully.",
        "data": serialize_message_row(row),
    }


@messages_router.post("/ack")
def acknowledge_message(
    payload: MessageActionRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    bootstrap_messages_from_csv_if_needed(db)

    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(MessageLog)
        .filter(MessageLog.tenant_id == int(tenant_id), MessageLog.message_id == normalize_text(payload.message_id))
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Message not found.")

    current_user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    user_id = int(current_user.id)

    read_row = (
        db.query(MessageRead)
        .filter(MessageRead.message_id == row.message_id, MessageRead.user_id == user_id)
        .first()
    )
    if read_row is None:
        read_row = MessageRead(tenant_id=int(tenant_id), message_id=row.message_id, user_id=user_id)
        db.add(read_row)

    read_row.is_read = True
    read_row.read_at = datetime.now()
    db.commit()
    db.refresh(read_row)

    return {"status": "acknowledged", "data": _serialize_message_for_user(row, user_id=user_id, db=db, now=datetime.now())}


@messages_router.post("/archive")
def archive_message(
    payload: MessageActionRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    bootstrap_messages_from_csv_if_needed(db)

    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(MessageLog)
        .filter(MessageLog.tenant_id == int(tenant_id), MessageLog.message_id == normalize_text(payload.message_id))
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Message not found.")

    current_user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    user_id = int(current_user.id)

    read_row = (
        db.query(MessageRead)
        .filter(MessageRead.message_id == row.message_id, MessageRead.user_id == user_id)
        .first()
    )
    if read_row is None:
        read_row = MessageRead(tenant_id=int(tenant_id), message_id=row.message_id, user_id=user_id)
        db.add(read_row)

    read_row.is_archived = True
    read_row.archived_at = datetime.now()
    # Archive also implies read for this user.
    read_row.is_read = True
    read_row.read_at = read_row.read_at or datetime.now()

    db.commit()
    db.refresh(read_row)

    return {"status": "archived", "data": _serialize_message_for_user(row, user_id=user_id, db=db, now=datetime.now())}


@messages_router.post("/pin")
def pin_message(
    payload: MessageActionRequest,
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(MessageLog)
        .filter(MessageLog.tenant_id == int(tenant_id), MessageLog.message_id == normalize_text(payload.message_id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    row.is_pinned = True
    db.commit()
    db.refresh(row)
    return {"status": "pinned", "data": serialize_message_row(row)}


@messages_router.post("/unpin")
def unpin_message(
    payload: MessageActionRequest,
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(MessageLog)
        .filter(MessageLog.tenant_id == int(tenant_id), MessageLog.message_id == normalize_text(payload.message_id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    row.is_pinned = False
    db.commit()
    db.refresh(row)
    return {"status": "unpinned", "data": serialize_message_row(row)}


@auth_router.post("/login")
def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    username = normalize_text(payload.username)
    password = normalize_text(payload.password)

    # Resolve tenant context at login time.
    tenant_slug = normalize_text(getattr(payload, "tenant_slug", None) or "")
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=401, detail="Unknown tenant")
        tenant_id = int(tenant.id)
    else:
        tenant_id = _get_default_tenant_id(db)

    user = db.query(User).filter(User.username == username, User.tenant_id == tenant_id).first()
    if user is None or not verify_password(password, normalize_text(user.password)):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_token(
        {
            "sub": normalize_text(user.username),
            "username": normalize_text(user.username),
            "role": normalize_text(user.role),
            "department": normalize_text(user.department),
            "name": normalize_text(user.name),
            "tenant_id": int(tenant_id),
        }
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": normalize_text(user.username),
            "name": normalize_text(user.name),
            "role": normalize_text(user.role),
            "department": normalize_text(user.department),
            "tenant_id": int(tenant_id),
        },
    }


@auth_router.get("/users")
def get_users(_token: dict = Depends(require_admin), db: Session = Depends(get_db)):
    tenant_id = get_tenant_id(_token, db)
    users = db.query(User).filter(User.tenant_id == int(tenant_id)).all()
    return {
        "users": [
            {
                "username": normalize_text(u.username),
                "name": normalize_text(u.name),
                "role": normalize_text(u.role),
                "department": normalize_text(u.department),
            }
            for u in users
        ]
    }


@patient_flow_router.get("/latest")
def get_latest_patient_flow_sequence(
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    rows = (
        db.query(PatientFlow)
        .filter(PatientFlow.tenant_id == int(tenant_id))
        .order_by(PatientFlow.id.desc())
        .limit(SEQUENCE_LENGTH)
        .all()
    )
    if len(rows) < SEQUENCE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {SEQUENCE_LENGTH} patient flow rows in DB.",
        )

    rows = list(reversed(rows))
    return {
        "sequence_length": SEQUENCE_LENGTH,
        "feature_count": FEATURE_COUNT,
        "sequence": build_engineered_sequence_from_patient_flow(rows),
    }


@ml_router.get("/optimize_resources/{predicted_patients}")
def optimize_resources_endpoint(
    predicted_patients: float,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """Run optimization and persist the run for audit + approvals."""

    tenant_id = get_tenant_id(_token, db)
    result = optimize_resources(predicted_patients)
    summary = result.get("summary", {}) if isinstance(result, dict) else {}

    try:
        row = OptimizationRun(
            tenant_id=int(tenant_id),
            run_id=_new_run_id("OPT"),
            timestamp=parse_datetime_now(),
            predicted_patients=float(predicted_patients),
            objective=float(summary.get("objective")) if summary.get("objective") is not None else None,
            summary_json=json.dumps(summary, ensure_ascii=False),
            allocations_json=json.dumps(result.get("department_allocations", []), ensure_ascii=False),
            actions_json=json.dumps(result.get("actions", []), ensure_ascii=False),
            recommendations_json=json.dumps(result.get("recommendations", []), ensure_ascii=False),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        logging.exception("Failed to persist optimization run: %s", e)

    # Minimal auto-alert hook (smallest increment): generate an alert when
    # optimizer detects warning/critical pressure in the top-priority department.
    try:
        allocations = result.get("department_allocations", []) if isinstance(result, dict) else []
        recommendations = result.get("recommendations", []) if isinstance(result, dict) else []
        if allocations:
            top = allocations[0]
            dept = normalize_text(top.get("department"))
            status = normalize_text(top.get("status"), "stable").lower()
            if status in {"warning", "critical"} and dept:
                prio = "critical" if status == "critical" else "high"
                title = f"{status.title()} pressure in {dept}"
                msg = (
                    f"Optimizer detected {status} pressure in {dept}. "
                    f"Bed shortage={int(top.get('bed_shortage') or 0)}, "
                    f"Doctor shortage={int(top.get('doctor_shortage') or 0)}, "
                    f"Nurse shortage={int(top.get('nurse_shortage') or 0)}."
                )
                rec_summary = "; ".join([normalize_text(r) for r in recommendations[:3] if r])

                # Notify admins (global) and the impacted department.
                create_alert_and_notify(
                    db=db,
                    tenant_id=int(tenant_id),
                    title=title,
                    message=msg,
                    alert_type="optimization_alert",
                    priority=prio,
                    source="optimizer",
                    related_department=dept,
                    generated_by_rule="optimizer_top_department",
                    recommendation_summary=rec_summary,
                    target_role="admin",
                    target_department="All Departments",
                )
                create_alert_and_notify(
                    db=db,
                    tenant_id=int(tenant_id),
                    title=title,
                    message=msg,
                    alert_type="optimization_alert",
                    priority=prio,
                    source="optimizer",
                    related_department=dept,
                    generated_by_rule="optimizer_top_department",
                    recommendation_summary=rec_summary,
                    target_role="all",
                    target_department=dept,
                )
    except Exception as e:
        logging.exception("Auto-alert generation failed: %s", e)

    return result


@ml_router.get("/optimization_runs")
def list_optimization_runs(
    limit: int = Query(default=20, ge=1, le=200),
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    rows = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.tenant_id == int(tenant_id))
        .order_by(OptimizationRun.id.desc())
        .limit(limit)
        .all()
    )
    payload = []
    for r in rows:
        payload.append(
            {
                "run_id": normalize_text(r.run_id),
                "timestamp": normalize_text(r.timestamp),
                "predicted_patients": float(r.predicted_patients),
                "objective": float(r.objective) if r.objective is not None else None,
                "summary": json.loads(r.summary_json) if r.summary_json else {},
            }
        )
    return {"runs": payload}


@ml_router.get("/optimization_runs/{run_id}")
def get_optimization_run(
    run_id: str,
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    row = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.tenant_id == int(tenant_id), OptimizationRun.run_id == normalize_text(run_id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return {
        "run_id": normalize_text(row.run_id),
        "timestamp": normalize_text(row.timestamp),
        "predicted_patients": float(row.predicted_patients),
        "objective": float(row.objective) if row.objective is not None else None,
        "summary": json.loads(row.summary_json) if row.summary_json else {},
        "department_allocations": json.loads(row.allocations_json) if row.allocations_json else [],
        "actions": json.loads(row.actions_json) if row.actions_json else [],
        "recommendations": json.loads(row.recommendations_json) if row.recommendations_json else [],
    }


# -----------------------------
# Alerts API
# -----------------------------


@alerts_router.get("")
def list_alerts(
    active_only: bool = Query(default=True),
    department: Optional[str] = Query(default=None),
    alert_type: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    role = normalize_text(_token.get("role")).lower()
    user_department = normalize_text(_token.get("department"))

    tenant_id = get_tenant_id(_token, db)
    q = db.query(Alert).filter(Alert.tenant_id == int(tenant_id))
    if active_only:
        q = q.filter(Alert.is_active.is_(True))
    if alert_type:
        q = q.filter(Alert.alert_type.ilike(normalize_text(alert_type)))
    if priority:
        q = q.filter(Alert.priority.ilike(normalize_text(priority)))

    # Access control: non-admin users see only their department + global (NULL).
    if role != "admin":
        q = q.filter(
            (Alert.related_department.is_(None))
            | (Alert.related_department.ilike(user_department))
        )

    # Optional filter, but don't allow staff to expand scope beyond their dept.
    if department:
        dep = normalize_text(department)
        if role == "admin" or dep.lower() == user_department.lower():
            q = q.filter(Alert.related_department.ilike(dep))

    rows = q.order_by(Alert.id.desc()).limit(limit).all()
    return {
        "alerts": [
            {
                "alert_id": normalize_text(a.alert_id),
                "title": normalize_text(a.title),
                "message": normalize_text(a.message),
                "type": normalize_text(a.alert_type),
                "priority": normalize_text(a.priority),
                "source": normalize_text(a.source),
                "department": normalize_text(a.related_department) if a.related_department else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                "is_active": bool(a.is_active),
                "is_acknowledged": bool(a.is_acknowledged),
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "generated_by_rule": normalize_text(a.generated_by_rule),
                "recommendation_summary": normalize_text(a.recommendation_summary),
            }
            for a in rows
        ]
    }


@alerts_router.post("/create")
def create_alert(
    payload: CreateAlertRequest,
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    alert = create_alert_and_notify(
        db=db,
        tenant_id=int(tenant_id),
        title=payload.title,
        message=payload.message,
        alert_type=payload.alert_type,
        priority=payload.priority,
        source=f"admin:{normalize_text(_token.get('username'))}",
        related_department=payload.related_department,
        generated_by_rule="manual",
        target_role=payload.target_role,
        target_department=payload.target_department,
        dedupe_window_minutes=0,
    )
    return {"status": "created", "alert_id": normalize_text(alert.alert_id)}


@alerts_router.post("/ack")
def acknowledge_alert(
    payload: AlertActionRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    alert = (
        db.query(Alert)
        .filter(Alert.tenant_id == int(tenant_id), Alert.alert_id == normalize_text(payload.alert_id))
        .first()
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)

    # Mark as acknowledged globally for now.
    alert.is_acknowledged = True
    alert.acknowledged_by_user_id = int(user.id)
    alert.acknowledged_at = datetime.now()

    # Mark user's related notifications as read.
    db.query(Notification).filter(
        Notification.tenant_id == int(tenant_id),
        Notification.user_id == int(user.id),
        Notification.alert_id == int(alert.id),
        Notification.read_at.is_(None),
    ).update(
        {"read_at": datetime.now(), "status": "read"},
        synchronize_session=False,
    )

    db.commit()
    return {"status": "acknowledged", "alert_id": normalize_text(alert.alert_id)}


@alerts_router.post("/resolve")
def resolve_alert(
    payload: AlertActionRequest,
    _token: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    alert = (
        db.query(Alert)
        .filter(Alert.tenant_id == int(tenant_id), Alert.alert_id == normalize_text(payload.alert_id))
        .first()
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    alert.is_active = False
    alert.resolved_by_user_id = int(user.id)
    alert.resolved_at = datetime.now()
    db.commit()
    return {"status": "resolved", "alert_id": normalize_text(alert.alert_id)}


# -----------------------------
# Notifications API (in-app)
# -----------------------------


@notifications_router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    q = db.query(Notification).filter(Notification.tenant_id == int(tenant_id), Notification.user_id == int(user.id))
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    rows = q.order_by(Notification.id.desc()).limit(limit).all()

    return {
        "notifications": [
            {
                "notification_id": normalize_text(n.notification_id),
                "title": normalize_text(n.title),
                "body": normalize_text(n.body),
                "channel": normalize_text(n.channel),
                "status": normalize_text(n.status),
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "delivered_at": n.delivered_at.isoformat() if n.delivered_at else None,
                "read_at": n.read_at.isoformat() if n.read_at else None,
                "alert_id": int(n.alert_id) if n.alert_id is not None else None,
                "message_id": normalize_text(n.message_id) if n.message_id else None,
            }
            for n in rows
        ]
    }


@notifications_router.get("/unread_count")
def notification_unread_count(
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    unread = (
        db.query(Notification)
        .filter(Notification.tenant_id == int(tenant_id), Notification.user_id == int(user.id), Notification.read_at.is_(None))
        .count()
    )
    return {"unread_count": int(unread)}


@notifications_router.post("/read")
def mark_notification_read(
    payload: MarkNotificationReadRequest,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    row = (
        db.query(Notification)
        .filter(
            Notification.notification_id == normalize_text(payload.notification_id),
            Notification.tenant_id == int(tenant_id),
            Notification.user_id == int(user.id),
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read_at = row.read_at or datetime.now()
    row.status = "read"
    db.commit()
    return {"status": "read", "notification_id": normalize_text(row.notification_id)}


@notifications_router.get("/preferences")
def get_notification_preferences(
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    pref = _get_or_create_notification_pref(db, int(user.id), tenant_id=int(tenant_id))
    return {
        "preferences": {
            "receive_in_app": bool(pref.receive_in_app),
            "receive_email": bool(pref.receive_email),
            "receive_sms": bool(pref.receive_sms),
            "receive_push": bool(pref.receive_push),
            "critical_only": bool(pref.critical_only),
            "quiet_hours_start": normalize_text(pref.quiet_hours_start),
            "quiet_hours_end": normalize_text(pref.quiet_hours_end),
        }
    }


@notifications_router.post("/preferences")
def update_notification_preferences(
    payload: dict,
    _token: dict = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    tenant_id = get_tenant_id(_token, db)
    user = _get_user_by_username_or_401(db, normalize_text(_token.get("username")), tenant_id=tenant_id)
    pref = _get_or_create_notification_pref(db, int(user.id), tenant_id=int(tenant_id))

    for key in [
        "receive_in_app",
        "receive_email",
        "receive_sms",
        "receive_push",
        "critical_only",
    ]:
        if key in payload:
            setattr(pref, key, bool(payload.get(key)))
    for key in ["quiet_hours_start", "quiet_hours_end"]:
        if key in payload:
            setattr(pref, key, normalize_text(payload.get(key)) or None)

    db.commit()
    db.refresh(pref)
    return {"status": "updated"}


@ml_router.post("/predict")
def predict(
    payload: PredictRequest,
    _token: dict = Depends(require_staff_or_admin),
):
    sequence_array = np.array(payload.sequence, dtype=float)

    if not validate_sequence_shape(sequence_array):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid sequence shape. Expected "
                f"({SEQUENCE_LENGTH}, {FEATURE_COUNT}), got {sequence_array.shape}."
            ),
        )

    result = predict_hybrid(sequence_array)
    predicted_patients = float(result["hybrid_prediction"])

    return {
        "predicted_patients_next_hour": predicted_patients,
        "emergency_level": predict_emergency_load(predicted_patients),
        "recommended_resources": calculate_recommended_resources(predicted_patients),
        **result,
    }


@ml_router.post("/simulate")
def simulate(
    payload: SimulateRequest,
    _token: dict = Depends(require_staff_or_admin),
):
    adjusted_patients = float(payload.predicted_patients) * (
        1.0 + float(payload.demand_increase_percent) / 100.0
    )

    recommended_resources = calculate_recommended_resources(adjusted_patients)
    bed_allocation = allocate_beds(int(np.ceil(adjusted_patients)), int(payload.beds_available))
    doctor_shortage = max(
        0,
        int(recommended_resources["doctors_needed"]) - int(payload.doctors_available),
    )

    return {
        "simulated_patients": float(round(adjusted_patients, 2)),
        "demand_increase_percent": float(payload.demand_increase_percent),
        "emergency_level": predict_emergency_load(adjusted_patients),
        "bed_allocation": bed_allocation,
        "recommended_resources": recommended_resources,
        "doctor_shortage": int(doctor_shortage),
    }


@ml_router.post("/explain")
def explain(
    payload: ExplainRequest,
    _token: dict = Depends(require_staff_or_admin),
):
    sequence_array = np.array(payload.sequence, dtype=float)

    if not validate_sequence_shape(sequence_array):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid sequence shape. Expected "
                f"({SEQUENCE_LENGTH}, {FEATURE_COUNT}), got {sequence_array.shape}."
            ),
        )

    return explain_feature_importance(sequence_array)


@ml_router.post("/evaluate")
def evaluate(
    payload: EvaluateRequest,
    _token: dict = Depends(require_admin),
):
    return compare_models(
        actual=payload.actual,
        lstm=payload.lstm,
        arimax=payload.arimax,
        hybrid=payload.hybrid,
    )


@upload_router.post("/patient_flow")
def upload_patient_flow(
    file: UploadFile = File(...),
    _token: dict = Depends(require_admin),
):
    ingest_patient_flow(file.file)
    return {"status": "patient flow uploaded"}


@upload_router.post("/appointments")
def upload_appointments(
    file: UploadFile = File(...),
    _token: dict = Depends(require_admin),
):
    ingest_appointments(file.file)
    return {"status": "appointments uploaded"}


@upload_router.post("/or")
def upload_or(
    file: UploadFile = File(...),
    _token: dict = Depends(require_admin),
):
    ingest_or(file.file)
    return {"status": "or bookings uploaded"}


# Backwards-compatible aliases (keep existing dashboard client paths working)
# - Old: GET /message_templates  -> New: GET /messages/templates
@system_router.get("/message_templates", include_in_schema=False)
def _legacy_message_templates(_token: dict = Depends(require_staff_or_admin)):
    return {
        "admin_templates": ADMIN_MESSAGE_TEMPLATES,
        "staff_quick_replies": STAFF_QUICK_REPLIES,
    }


# - Old: GET /users -> New: GET /auth/users
@system_router.get("/users", include_in_schema=False)
def _legacy_users(_token: dict = Depends(require_admin), db: Session = Depends(get_db)):
    # Mirror /auth/users payload.
    users = db.query(User).all()
    return {
        "users": [
            {
                "username": normalize_text(u.username),
                "name": normalize_text(u.name),
                "role": normalize_text(u.role),
                "department": normalize_text(u.department),
            }
            for u in users
        ]
    }


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(messages_router)
app.include_router(patient_flow_router)
app.include_router(ml_router)
app.include_router(upload_router)

# New routers
app.include_router(alerts_router)
app.include_router(notifications_router)