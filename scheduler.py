"""Always-on background pipeline.

This is designed to run as a *separate worker* in production (Render/Railway),
so we avoid duplicate schedulers when the API scales horizontally.

Pipeline loop:
1) Generate/ingest new patient flow rows
2) Forecast next hour
3) Run optimization
4) Generate alerts/notifications
5) Persist a PipelineRun record
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import numpy as np

from database import session_scope
from forecast_features import build_latest_sequence_from_rows
from forecast_inference import predict_hybrid as _predict_hybrid
from resource_optimizer import optimize_resources
from settings import get_settings

from models import Alert, Notification, OptimizationRun, PatientFlow, PipelineRun, Tenant, User

from ops_live import build_live_state, shift_times_for_type


logger = logging.getLogger(__name__)


def _normalize_text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def _get_or_create_default_tenant_id(db) -> int:
    settings = get_settings()
    slug = _normalize_text(settings.default_tenant_slug, "demo-hospital")
    row = db.query(Tenant).filter(Tenant.slug == slug).first()
    if row is None:
        row = Tenant(name="Demo Hospital", slug=slug)
        db.add(row)
        db.commit()
        db.refresh(row)
    return int(row.id)


def _insert_synthetic_patient_flow(db, tenant_id: int) -> dict:
    # Import here to keep module import fast.
    from synthetic_data import SyntheticParams, generate_patient_flow

    settings = get_settings()
    params = SyntheticParams(emergency_rate=float(settings.synthetic_emergency_rate))
    row = generate_patient_flow(datetime.now(), params)

    db.add(
        PatientFlow(
            tenant_id=int(tenant_id),
            datetime=row["datetime"],
            patients=float(row["patients"]),
            day_of_week=int(row["day_of_week"]),
            month=int(row["month"]),
            is_weekend=int(row["is_weekend"]),
            holiday=int(row["holiday"]),
            weather=float(row["weather"]),
        )
    )
    db.commit()
    return row


def _ensure_hourly_ops_demo_data(db, tenant_id: int) -> dict:
    """Hourly live-ops simulator.

    For demo mode (no real hospital integration yet), we keep operational tables
    aligned with *today/current hour* so Shifts/Appointments/OR/Department Status
    look live.

    IMPORTANT: We keep this idempotent and lightweight:
    - Do NOT delete existing rows (avoid breaking audits)
    - Insert only if table is empty for today
    """

    live = build_live_state()
    today = live.today

    # Ensure operational rows that exist in DB appear as "today" for live demo.
    # We do not delete historical rows; this is a view-level behavior elsewhere,
    # but the optimizer filters by date. So we need at least one matching record.
    try:
        from models import Appointment, ORBooking, StaffShift

        # Only apply when tables have rows but none for today.
        any_shift = db.query(StaffShift).filter(StaffShift.tenant_id == int(tenant_id)).first()
        if any_shift is not None:
            today_count = (
                db.query(StaffShift)
                .filter(StaffShift.tenant_id == int(tenant_id), StaffShift.shift_date == today)
                .count()
            )
            if int(today_count or 0) == 0:
                # Reuse latest shift rows by copying (keeps history intact).
                latest = (
                    db.query(StaffShift)
                    .filter(StaffShift.tenant_id == int(tenant_id))
                    .order_by(StaffShift.id.desc())
                    .limit(20)
                    .all()
                )
                for s in latest:
                    start, end = shift_times_for_type(str(s.shift_type or ""))
                    db.add(
                        StaffShift(
                            tenant_id=int(tenant_id),
                            staff_username=s.staff_username,
                            name=s.name,
                            role=s.role,
                            department=s.department,
                            shift_date=today,
                            shift_type=s.shift_type,
                            shift_start_time=start,
                            shift_end_time=end,
                            status=s.status,
                        )
                    )
                db.commit()

        any_appt = db.query(Appointment).filter(Appointment.tenant_id == int(tenant_id)).first()
        if any_appt is not None:
            today_count = (
                db.query(Appointment)
                .filter(Appointment.tenant_id == int(tenant_id), Appointment.date == today)
                .count()
            )
            if int(today_count or 0) == 0:
                latest = (
                    db.query(Appointment)
                    .filter(Appointment.tenant_id == int(tenant_id))
                    .order_by(Appointment.id.desc())
                    .limit(20)
                    .all()
                )
                for a in latest:
                    db.add(
                        Appointment(
                            tenant_id=int(tenant_id),
                            appointment_id=a.appointment_id,
                            department=a.department,
                            doctor=a.doctor,
                            date=today,
                            time_slot=a.time_slot,
                            patient_count=a.patient_count,
                            status=a.status,
                        )
                    )
                db.commit()

        any_or = db.query(ORBooking).filter(ORBooking.tenant_id == int(tenant_id)).first()
        if any_or is not None:
            today_count = (
                db.query(ORBooking)
                .filter(ORBooking.tenant_id == int(tenant_id), ORBooking.date == today)
                .count()
            )
            if int(today_count or 0) == 0:
                latest = (
                    db.query(ORBooking)
                    .filter(ORBooking.tenant_id == int(tenant_id))
                    .order_by(ORBooking.id.desc())
                    .limit(20)
                    .all()
                )
                for r in latest:
                    db.add(
                        ORBooking(
                            tenant_id=int(tenant_id),
                            booking_id=r.booking_id,
                            room=r.room,
                            doctor=r.doctor,
                            department=r.department,
                            date=today,
                            time_slot=r.time_slot,
                            procedure=r.procedure,
                            status=r.status,
                        )
                    )
                db.commit()
    except Exception:
        db.rollback()

    # Staff shifts: ensure shift_start/end fields are populated (existing rows may be missing).
    # We do a small update-in-place on today's shifts.
    try:
        from models import StaffShift

        shifts = (
            db.query(StaffShift)
            .filter(StaffShift.tenant_id == int(tenant_id), StaffShift.shift_date == today)
            .all()
        )
        for s in shifts:
            if (not getattr(s, "shift_start_time", None)) or (not getattr(s, "shift_end_time", None)):
                start, end = shift_times_for_type(str(s.shift_type or ""))
                s.shift_start_time = start
                s.shift_end_time = end
        db.commit()
    except Exception:
        db.rollback()

    # Patient tracking: if empty, seed a minimal live state.
    # This enables realistic bed occupancy calculations.
    seeded = {"today": today, "patient_tracking_seeded": False}
    try:
        from models import PatientTracking

        count_today = (
            db.query(PatientTracking)
            .filter(PatientTracking.tenant_id == int(tenant_id))
            .count()
        )
        if int(count_today or 0) == 0:
            now_str = live.now.strftime("%Y-%m-%d %H:%M:%S")
            demo_rows = [
                # ER: mix of waiting + admitted
                {
                    "patient_id": "P-ER-001",
                    "patient_name_or_anonymized_id": "ER-001",
                    "entry_datetime": now_str,
                    "entry_method": "emergency",
                    "department": "ER",
                    "assigned_bed_id": "ER-B01",
                    "admission_status": "admitted",
                    "length_of_stay_hours": 2.0,
                    "payment_status": "pending",
                    "current_status": "inside_hospital",
                },
                {
                    "patient_id": "P-ER-002",
                    "patient_name_or_anonymized_id": "ER-002",
                    "entry_datetime": now_str,
                    "entry_method": "walk-in",
                    "department": "ER",
                    "assigned_bed_id": "",
                    "admission_status": "waiting",
                    "length_of_stay_hours": 0.5,
                    "payment_status": "pending",
                    "current_status": "inside_hospital",
                },
                # ICU
                {
                    "patient_id": "P-ICU-001",
                    "patient_name_or_anonymized_id": "ICU-001",
                    "entry_datetime": now_str,
                    "entry_method": "referral",
                    "department": "ICU",
                    "assigned_bed_id": "ICU-B03",
                    "admission_status": "admitted",
                    "length_of_stay_hours": 12.0,
                    "payment_status": "unpaid",
                    "current_status": "inside_hospital",
                },
                # General Ward
                {
                    "patient_id": "P-GW-001",
                    "patient_name_or_anonymized_id": "GW-001",
                    "entry_datetime": now_str,
                    "entry_method": "appointment",
                    "department": "General Ward",
                    "assigned_bed_id": "GW-B12",
                    "admission_status": "admitted",
                    "length_of_stay_hours": 24.0,
                    "payment_status": "pending",
                    "current_status": "inside_hospital",
                },
            ]

            for r in demo_rows:
                db.add(
                    PatientTracking(
                        tenant_id=int(tenant_id),
                        patient_id=r.get("patient_id"),
                        patient_name_or_anonymized_id=r.get("patient_name_or_anonymized_id"),
                        national_id_or_card_id_optional=r.get("national_id_or_card_id_optional"),
                        entry_datetime=r.get("entry_datetime"),
                        entry_method=r.get("entry_method"),
                        department=r.get("department"),
                        assigned_bed_id=r.get("assigned_bed_id"),
                        admission_status=r.get("admission_status"),
                        length_of_stay_hours=float(r.get("length_of_stay_hours") or 0.0),
                        discharge_datetime=r.get("discharge_datetime"),
                        payment_status=r.get("payment_status"),
                        current_status=r.get("current_status"),
                        notes=r.get("notes"),
                    )
                )

            db.commit()
            seeded["patient_tracking_seeded"] = True
    except Exception:
        db.rollback()

    return seeded


def _build_sequence_from_db_rows(rows: list[PatientFlow]) -> np.ndarray:
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
    seq = build_latest_sequence_from_rows(payload_rows)
    return np.array(seq, dtype=float)


def _forecast_next_hour(sequence: np.ndarray) -> float:
    result = _predict_hybrid(sequence)
    return float(result["hybrid_prediction"])


def _persist_optimization_run(db, tenant_id: int, predicted_patients: float) -> dict:
    result = optimize_resources(predicted_patients, tenant_id=int(tenant_id))
    summary = result.get("summary", {}) if isinstance(result, dict) else {}

    run = OptimizationRun(
        tenant_id=int(tenant_id),
        run_id=_new_id("OPT"),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        predicted_patients=float(predicted_patients),
        objective=float(summary.get("objective")) if summary.get("objective") is not None else None,
        summary_json=json.dumps(summary, ensure_ascii=False),
        allocations_json=json.dumps(result.get("department_allocations", []), ensure_ascii=False),
        actions_json=json.dumps(result.get("actions", []), ensure_ascii=False),
        recommendations_json=json.dumps(result.get("recommendations", []), ensure_ascii=False),
    )
    db.add(run)
    db.commit()
    return result


def _create_simple_alerts(db, tenant_id: int, predicted_patients: float, opt_result: dict) -> None:
    """Minimal alerting for production demo.

    Later phases will unify this with the API alert service + preferences.
    """

    # Trigger forecast alert
    if predicted_patients >= 140:
        title = "Forecast surge detected"
        message = f"Predicted next hour patients: {int(predicted_patients)}"
        alert = Alert(
            tenant_id=int(tenant_id),
            alert_id=_new_id("ALERT"),
            title=title,
            message=message,
            alert_type="forecast_alert",
            priority="high" if predicted_patients < 170 else "critical",
            source="scheduler",
            related_department=None,
            is_active=True,
            is_acknowledged=False,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        # Notify admins
        admins = db.query(User).filter(User.tenant_id == int(tenant_id), User.role.ilike("admin")).all()
        for a in admins:
            db.add(
                Notification(
                    tenant_id=int(tenant_id),
                    notification_id=_new_id("NTF"),
                    user_id=int(a.id),
                    alert_id=int(alert.id),
                    channel="in_app",
                    title=title,
                    body=message,
                    status="delivered",
                    delivered_at=datetime.now(),
                )
            )
        db.commit()

    # Trigger optimization alert when top dept is warning/critical
    try:
        allocations = opt_result.get("department_allocations", []) if isinstance(opt_result, dict) else []
        if allocations:
            top = allocations[0]
            status = _normalize_text(top.get("status"), "stable").lower()
            dept = _normalize_text(top.get("department"))
            if status in {"warning", "critical"}:
                title = f"Optimizer: {status} pressure"
                message = f"Top dept={dept or '-'} | bed_shortage={int(top.get('bed_shortage') or 0)} | doctor_shortage={int(top.get('doctor_shortage') or 0)} | nurse_shortage={int(top.get('nurse_shortage') or 0)}"
                alert = Alert(
                    tenant_id=int(tenant_id),
                    alert_id=_new_id("ALERT"),
                    title=title,
                    message=message,
                    alert_type="optimization_alert",
                    priority="high" if status == "warning" else "critical",
                    source="scheduler",
                    related_department=dept or None,
                    is_active=True,
                    is_acknowledged=False,
                )
                db.add(alert)
                db.commit()
    except Exception:
        logger.exception("Failed to create optimization alert")


def run_pipeline_once() -> dict:
    settings = get_settings()

    with session_scope(commit=False) as db:
        tenant_id = _get_or_create_default_tenant_id(db)
        run = PipelineRun(
            tenant_id=int(tenant_id),
            run_id=_new_id("PIPE"),
            started_at=datetime.now(),
            status="running",
            step="start",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        info: dict = {"pipeline_run_id": run.run_id, "tenant_id": int(tenant_id)}

        # Step 1: data
        if settings.synthetic_data_enabled:
            run.step = "synthetic_data"
            db.commit()
            info["synthetic_row"] = _insert_synthetic_patient_flow(db, tenant_id)

        # Step 1b: operational demo data (hourly live state)
        run.step = "ops_demo_state"
        db.commit()
        info["ops_demo_state"] = _ensure_hourly_ops_demo_data(db, tenant_id)

        # Step 2: forecast
        run.step = "forecast"
        db.commit()
        from feature_spec import SEQUENCE_LENGTH

        rows = (
            db.query(PatientFlow)
            .filter(PatientFlow.tenant_id == int(tenant_id))
            .order_by(PatientFlow.id.desc())
            .limit(int(SEQUENCE_LENGTH))
            .all()
        )
        rows = list(reversed(rows))
        if len(rows) < int(SEQUENCE_LENGTH):
            raise RuntimeError(f"Need at least {SEQUENCE_LENGTH} patient_flow rows to forecast")

        seq = _build_sequence_from_db_rows(rows)
        pred = _forecast_next_hour(seq)
        info["predicted_patients_next_hour"] = float(pred)

        # Step 3: optimization
        run.step = "optimization"
        db.commit()
        opt_result = _persist_optimization_run(db, tenant_id=tenant_id, predicted_patients=pred)
        info["optimization_summary"] = (opt_result or {}).get("summary", {})

        # Step 4: alerts
        run.step = "alerts"
        db.commit()
        _create_simple_alerts(db, tenant_id=tenant_id, predicted_patients=float(pred), opt_result=opt_result or {})

        run.step = "done"
        run.status = "ok"
        run.completed_at = datetime.now()
        run.details_json = json.dumps(info, ensure_ascii=False)
        db.commit()

        return info


async def scheduler_loop() -> None:
    settings = get_settings()
    interval = int(settings.scheduler_interval_seconds)
    logger.info("Scheduler loop starting (interval=%ss)", interval)
    while True:
        try:
            out = run_pipeline_once()
            logger.info("Pipeline run ok: %s", out.get("pipeline_run_id"))
        except Exception as e:
            logger.exception("Pipeline run failed: %s", e)
        await asyncio.sleep(interval)
