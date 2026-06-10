import os
from datetime import datetime, timedelta
from typing import List, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from database import SessionLocal
from settings import get_settings
from models import Appointment, AuditEvent, ORBooking, RecommendationRecord, StaffShift, Tenant
from ui_components import alert_box, empty_state, modern_table, page_header, scoped_key, section_header, status_badge

LEGACY_RECOMMENDATION_FILE = "recommendation_log.csv"  # import-only (not runtime)
REQUIRED_LOG_COLS = [
    "recommendation_id",
    "timestamp",
    "type",
    "message",
    "status",
    "approved_by",
    "execution_status",
    "execution_note",
    "affected_files",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _status_tone(status: str) -> str:
    value = _normalize(status).lower()
    if value == "approved":
        return "success"
    if value == "rejected":
        return "critical"
    if value == "pending":
        return "warning"
    return "neutral"


def _approval_title(rec_type: str) -> str:
    value = _normalize(rec_type, "operational")
    mapping = {
        "staff": "Staffing change approval",
        "beds": "Emergency resource request",
        "capacity": "Department escalation",
        "emergency": "Emergency resource request",
        "or": "OR priority review",
        "appointments": "Department escalation",
        "optimization": "Optimization recommendation approval",
    }
    return mapping.get(value.lower(), f"{value.title()} approval")


def _priority_from_type(rec_type: str, message: str) -> str:
    text = f"{rec_type} {message}".lower()
    if any(term in text for term in ["emergency", "critical", "high", "surge"]):
        return "critical"
    if any(term in text for term in ["beds", "capacity", "doctors", "backup", "review"]):
        return "high"
    return "normal"


def _recommended_decision(row) -> str:
    rec_type = _normalize(row.get("type") if isinstance(row, dict) else row["type"])
    if rec_type.lower() in {"staff", "beds", "capacity", "emergency", "or", "appointments"}:
        return "Approve if operational capacity and manager review align."
    return "Review recommendation details before approving."


def _show_revalidation_status(rec_type: str, department: str):
    """Display RAG re-validation after a recommendation is approved and executed.

    Purpose:    Close the apply→re-run→Red-Amber-Green loop — show the operator
                that the system has checked the post-approval state.
    Source:     Called immediately after approve_recommendation() succeeds.
    Destination: Informational badge on the Approvals tab; logged in the audit trail.
    """
    # Map recommendation type to expected post-approval operational status.
    _RAG = {
        "staff":       ("GREEN",  "success", "Staffing recommendation applied — coverage gap addressed."),
        "beds":        ("AMBER",  "warning", "Bed reallocation applied — monitor occupancy for full GREEN status."),
        "capacity":    ("AMBER",  "warning", "Capacity adjustment applied — review load in next forecast cycle."),
        "emergency":   ("GREEN",  "success", "Emergency escalation applied — priority resources activated."),
        "or":          ("GREEN",  "success", "OR booking priority updated — surgical schedule de-conflicted."),
        "appointments":("AMBER",  "warning", "Appointment rescheduling applied — re-run forecast to confirm GREEN."),
    }
    rag_color, tone, note = _RAG.get(
        _normalize(rec_type).lower(),
        ("AMBER", "warning", "Recommendation applied — re-run the Optimization tab to confirm the updated status."),
    )
    dept_label = f" ({department})" if department and department not in {"All", "—", ""} else ""
    status_badge(f"Re-validation: {rag_color}{dept_label}", tone)
    st.caption(note)


def _render_priority(priority: str):
    value = _normalize(priority, "normal").lower()
    if value == "critical":
        status_badge("CRITICAL", "critical")
    elif value == "high":
        status_badge("HIGH", "warning")
    else:
        status_badge("NORMAL", "info")


def _render_approval_card(row, approver_name: str):
    rec_id = _normalize(row["recommendation_id"])
    rec_type = _normalize(row["type"], "optimization")
    message = _normalize(row["message"])
    department = infer_department_from_message(message)
    priority = _priority_from_type(rec_type, message)

    with st.container(border=True):
        h1, h2, h3 = st.columns([0.58, 0.18, 0.24])
        with h1:
            st.markdown(f"#### {_approval_title(rec_type)}")
            st.caption(f"Request ID: {rec_id} • Created: {_normalize(row['timestamp'], '—')}")
        with h2:
            _render_priority(priority)
        with h3:
            status_badge(_normalize(row["status"], "pending").upper(), _status_tone(row["status"]))

        st.write(message)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.caption("Department")
            st.write(department)
        with c2:
            st.caption("Requested by")
            st.write("Forecast + Optimization")
        with c3:
            st.caption("Recommended decision")
            st.write(_recommended_decision(row))
        with c4:
            st.caption("Reason")
            st.write(_normalize(rec_type).title())

        a1, a2 = st.columns([1, 1])
        with a1:
            if st.button("Approve", key=f"approve_{rec_id}"):
                ok = approve_recommendation(rec_id, approver_name)
                load_recommendations.clear()
                if ok:
                    st.success(f"{rec_id} approved and executed")
                    # RAG re-validation: show updated status after applying recommendation.
                    _show_revalidation_status(rec_type, department)
                else:
                    st.error("Failed to approve recommendation.")
                st.rerun()
        with a2:
            if st.button("Reject", key=f"reject_{rec_id}"):
                ok = reject_recommendation(rec_id, approver_name)
                load_recommendations.clear()
                if ok:
                    st.warning(f"{rec_id} rejected")
                else:
                    st.error("Failed to reject recommendation.")
                st.rerun()


def _new_recommendation_id() -> str:
    return f"REC-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def _new_audit_id() -> str:
    return f"AUD-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def _get_default_tenant_id(db) -> int:
    """Resolve tenant for Streamlit-side DB actions.

    The Streamlit app currently performs some DB writes directly (not via API),
    so it needs an explicit tenant context.
    """

    settings = get_settings()
    slug = str(settings.default_tenant_slug or "demo-hospital").strip() or "demo-hospital"
    row = db.query(Tenant).filter(Tenant.slug == slug).first()
    if row is None:
        row = Tenant(name="Demo Hospital", slug=slug)
        db.add(row)
        db.commit()
        db.refresh(row)
    return int(row.id)


def _record_audit(db: Session, action: str, actor: str, target: str, status: str, details: str):
    tenant_id = _get_default_tenant_id(db)
    db.add(
        AuditEvent(
            tenant_id=int(tenant_id),
            audit_id=_new_audit_id(),
            timestamp=_now(),
            action=_normalize(action),
            actor=_normalize(actor),
            target=_normalize(target),
            status=_normalize(status),
            details=_normalize(details),
        )
    )


def _bootstrap_recommendations_from_csv_if_needed(db: Session):
    # DB-first runtime: do not bootstrap from CSV.
    return


def _recommendation_record_to_dict(row: RecommendationRecord) -> dict:
    return {
        "recommendation_id": _normalize(row.recommendation_id),
        "timestamp": _normalize(row.timestamp),
        "type": _normalize(row.rec_type),
        "message": _normalize(row.message),
        "status": _normalize(row.status),
        "approved_by": _normalize(row.approved_by),
        "execution_status": _normalize(row.execution_status),
        "execution_note": _normalize(row.execution_note),
        "affected_files": _normalize(row.affected_entities),
    }


@st.cache_data(ttl=15, show_spinner=False)
def load_recommendations() -> pd.DataFrame:
    db = SessionLocal()
    try:
        _bootstrap_recommendations_from_csv_if_needed(db)
        tenant_id = _get_default_tenant_id(db)
        rows = (
            db.query(RecommendationRecord)
            .filter(RecommendationRecord.tenant_id == int(tenant_id))
            .order_by(RecommendationRecord.id.desc())
            .all()
        )
        return pd.DataFrame([_recommendation_record_to_dict(row) for row in rows], columns=REQUIRED_LOG_COLS)
    finally:
        db.close()


def reset_recommendations():
    db = SessionLocal()
    try:
        tenant_id = _get_default_tenant_id(db)
        db.query(RecommendationRecord).filter(RecommendationRecord.tenant_id == int(tenant_id)).delete()
        _record_audit(
            db,
            "reset_recommendations",
            "system",
            "recommendation_records",
            "success",
            "Recommendation records were reset.",
        )
        db.commit()
        load_recommendations.clear()
    finally:
        db.close()


def infer_department_from_message(message: str):
    message_lower = str(message).lower()
    if "icu" in message_lower:
        return "ICU"
    if "general ward" in message_lower:
        return "General Ward"
    if "surgery" in message_lower:
        return "Surgery"
    if "radiology" in message_lower:
        return "Radiology"
    return "ER"


def create_recommendation_row(rec_type: str, message: str):
    return {
        "recommendation_id": _new_recommendation_id(),
        "timestamp": _now(),
        "type": rec_type,
        "message": message,
        "status": "pending",
        "approved_by": "",
        "execution_status": "",
        "execution_note": "",
        "affected_files": "",
    }


def generate_ai_recommendations(peak, beds_needed, doctors_needed, emergency_level):
    recommendations = []
    if peak >= 100:
        recommendations.append({
            "type": "capacity",
            "message": f"Peak forecast reached {int(peak)} patients. Recommend opening overflow capacity."
        })
    if beds_needed >= 100:
        recommendations.append({
            "type": "beds",
            "message": f"Beds needed = {beds_needed}. Recommend reallocating beds or delaying non-urgent admissions."
        })
    if doctors_needed >= 12:
        recommendations.append({
            "type": "staff",
            "message": f"Doctors needed = {doctors_needed}. Recommend adding backup doctors to upcoming shifts."
        })
    if emergency_level == "HIGH":
        recommendations.append({
            "type": "emergency",
            "message": "Emergency load is HIGH. Recommend activating emergency surge plan."
        })
    return recommendations


def seed_demo_recommendations():
    db = SessionLocal()
    try:
        _bootstrap_recommendations_from_csv_if_needed(db)
        tenant_id = _get_default_tenant_id(db)
        # Only avoid duplicating *pending* recommendations. Approved/rejected recommendations
        # are part of history and we still want a way to generate new pending work.
        existing_messages = {
            _normalize(row.message)
            for row in db.query(RecommendationRecord)
                .filter(RecommendationRecord.tenant_id == int(tenant_id), RecommendationRecord.status == "pending")
                .all()
        }

        demo_rows = [
            create_recommendation_row("capacity", "Peak forecast reached 135 patients. Recommend opening overflow capacity."),
            create_recommendation_row("beds", "Beds needed = 145. Recommend reallocating beds or delaying non-urgent admissions."),
            create_recommendation_row("staff", "Doctors needed = 18. Recommend adding backup doctors to upcoming shifts."),
            create_recommendation_row("emergency", "Emergency load is HIGH. Recommend activating emergency surge plan."),
        ]

        inserted = 0
        for row in demo_rows:
            if row["message"] in existing_messages:
                continue

            db.add(
                RecommendationRecord(
                    tenant_id=int(tenant_id),
                    recommendation_id=row["recommendation_id"],
                    timestamp=row["timestamp"],
                    rec_type=row["type"],
                    message=row["message"],
                    status=row["status"],
                    approved_by=row["approved_by"],
                    execution_status=row["execution_status"],
                    execution_note=row["execution_note"],
                    affected_entities=row["affected_files"],
                )
            )
            inserted += 1

        _record_audit(
            db,
            "seed_demo_recommendations",
            "system",
            "recommendation_records",
            "success",
            f"Inserted {inserted} demo recommendations.",
        )
        db.commit()
    finally:
        db.close()


def sync_recommendations(peak, beds_needed, doctors_needed, emergency_level):
    # Guard: only sync once per session per unique set of inputs to prevent a
    # DB write on every Streamlit rerun.  Callers that need a forced re-sync
    # (e.g. after optimization changes) should call load_recommendations.clear().
    _sync_key = f"_synced_recs_{peak}_{beds_needed}_{doctors_needed}_{emergency_level}"
    if st.session_state.get(_sync_key):
        return load_recommendations()
    st.session_state[_sync_key] = True

    db = SessionLocal()
    try:
        _bootstrap_recommendations_from_csv_if_needed(db)
        tenant_id = _get_default_tenant_id(db)

        generated = generate_ai_recommendations(peak, beds_needed, doctors_needed, emergency_level)
        pending_messages = {
            _normalize(row.message)
            for row in (
                db.query(RecommendationRecord)
                .filter(RecommendationRecord.tenant_id == int(tenant_id), RecommendationRecord.status == "pending")
                .all()
            )
        }

        inserted = 0
        for rec in generated:
            if rec["message"] in pending_messages:
                continue

            row = create_recommendation_row(rec["type"], rec["message"])
            db.add(
                RecommendationRecord(
                    tenant_id=int(tenant_id),
                    recommendation_id=row["recommendation_id"],
                    timestamp=row["timestamp"],
                    rec_type=row["type"],
                    message=row["message"],
                    status=row["status"],
                    approved_by=row["approved_by"],
                    execution_status=row["execution_status"],
                    execution_note=row["execution_note"],
                    affected_entities=row["affected_files"],
                )
            )
            inserted += 1

        if inserted > 0:
            _record_audit(
                db,
                "sync_recommendations",
                "system",
                "recommendation_records",
                "success",
                f"Inserted {inserted} new AI recommendations.",
            )

        db.commit()
        rows = (
            db.query(RecommendationRecord)
            .filter(RecommendationRecord.tenant_id == int(tenant_id))
            .order_by(RecommendationRecord.id.desc())
            .all()
        )
        return pd.DataFrame([_recommendation_record_to_dict(row) for row in rows], columns=REQUIRED_LOG_COLS)
    finally:
        db.close()


def _decision_history_from_audit() -> pd.DataFrame:
    """Fallback decision history from immutable audit events when records are absent."""

    db = SessionLocal()
    try:
        tenant_id = _get_default_tenant_id(db)
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == int(tenant_id))
            .filter(AuditEvent.action.in_(["approve_recommendation", "reject_recommendation"]))
            .order_by(AuditEvent.id.desc())
            .all()
        )
        data = []
        for row in rows:
            action = _normalize(row.action)
            data.append(
                {
                    "Request ID": _normalize(row.target),
                    "Created time": _normalize(row.timestamp),
                    "Request type": action.replace("_recommendation", ""),
                    "Reason / recommendation": _normalize(row.details),
                    "Status": "approved" if action == "approve_recommendation" else "rejected",
                    "Decision by": _normalize(row.actor),
                    "Execution status": _normalize(row.status),
                    "Execution note": _normalize(row.details),
                    "Affected records": _normalize(row.target),
                }
            )
        return pd.DataFrame(data)
    finally:
        db.close()


def execute_staff_decision(db: Session, message: str) -> Tuple[str, str, str]:
    tenant_id = _get_default_tenant_id(db)
    department = infer_department_from_message(message)
    next_day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    db.add(
        StaffShift(
            tenant_id=int(tenant_id),
            staff_username=f"backup_doctor_{department.lower().replace(' ', '_')}",
            name="Backup Doctor",
            role="doctor",
            department=department,
            shift_date=next_day,
            shift_type="Emergency Backup",
            status="Auto-Assigned",
        )
    )

    return (
        "executed",
        f"Added backup doctor shift in {department} for {next_day}.",
        f"staff_shifts:{department}:{next_day}",
    )


def execute_beds_decision(db: Session, message: str) -> Tuple[str, str, str]:
    tenant_id = _get_default_tenant_id(db)
    appointments = db.query(Appointment).filter(Appointment.tenant_id == int(tenant_id)).all()
    if not appointments:
        return "skipped", "No appointments found to rebalance.", "appointments"

    busiest = max(appointments, key=lambda row: _safe_int(row.patient_count, 0))
    busiest.status = "Review Required"

    return (
        "executed",
        f"Marked appointment slot {busiest.time_slot} in {busiest.department} as Review Required.",
        f"appointments:{_normalize(busiest.appointment_id)}",
    )


def execute_capacity_decision(db: Session, message: str) -> Tuple[str, str, str]:
    tenant_id = _get_default_tenant_id(db)
    appointments = db.query(Appointment).filter(Appointment.tenant_id == int(tenant_id)).all()
    if not appointments:
        return "skipped", "No appointment slots available for capacity reallocation.", "appointments"

    top_two = sorted(appointments, key=lambda row: _safe_int(row.patient_count, 0), reverse=True)[:2]
    if not top_two:
        return "skipped", "No appointment slots available for capacity reallocation.", "appointments"

    affected = []
    for row in top_two:
        row.status = "Reschedule Suggested"
        affected.append(_normalize(row.appointment_id))

    return (
        "executed",
        "Marked top pressure appointment slots as Reschedule Suggested.",
        f"appointments:{', '.join(affected)}",
    )


def execute_emergency_decision(db: Session, message: str) -> Tuple[str, str, str]:
    note_parts: List[str] = []
    affected_entities: List[str] = []

    tenant_id = _get_default_tenant_id(db)
    pending_or_rows = [
        row
        for row in db.query(ORBooking).filter(ORBooking.tenant_id == int(tenant_id)).all()
        if _normalize(row.status).lower() == "pending"
    ]
    if pending_or_rows:
        for row in pending_or_rows:
            row.status = "Priority Review"
            affected_entities.append(f"or:{_normalize(row.booking_id)}")
        note_parts.append("Pending OR bookings escalated to Priority Review")

    appt_rows = db.query(Appointment).filter(Appointment.tenant_id == int(tenant_id)).all()
    if appt_rows:
        busiest = max(appt_rows, key=lambda row: _safe_int(row.patient_count, 0))
        busiest.status = "Restricted Intake"
        affected_entities.append(f"appointments:{_normalize(busiest.appointment_id)}")
        note_parts.append(
            f"Appointment slot {busiest.time_slot} in {busiest.department} set to Restricted Intake"
        )

    if not note_parts:
        return "skipped", "No OR bookings or appointments available for emergency actions.", ""

    return "executed", " | ".join(note_parts), ", ".join(affected_entities)


def execute_decision(db: Session, decision_type: str, message: str):
    if decision_type == "staff":
        return execute_staff_decision(db, message)
    if decision_type == "beds":
        return execute_beds_decision(db, message)
    if decision_type == "capacity":
        return execute_capacity_decision(db, message)
    if decision_type in ["emergency", "or"]:
        return execute_emergency_decision(db, message)
    if decision_type == "appointments":
        return execute_capacity_decision(db, message)
    return "skipped", "No execution rule defined for this recommendation type.", ""


def approve_recommendation(recommendation_id, approver_name):
    db = SessionLocal()
    try:
        _bootstrap_recommendations_from_csv_if_needed(db)
        tenant_id = _get_default_tenant_id(db)
        row = (
            db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.tenant_id == int(tenant_id),
                RecommendationRecord.recommendation_id == recommendation_id,
            )
            .first()
        )
        if row is None:
            return False

        execution_status, execution_note, affected_entities = execute_decision(
            db,
            _normalize(row.rec_type),
            _normalize(row.message),
        )

        row.status = "approved"
        row.approved_by = _normalize(approver_name)
        row.execution_status = _normalize(execution_status)
        row.execution_note = _normalize(execution_note)
        row.affected_entities = _normalize(affected_entities)

        _record_audit(
            db,
            "approve_recommendation",
            _normalize(approver_name),
            recommendation_id,
            "success",
            f"Recommendation approved. Execution status={execution_status}. Affected={affected_entities or 'none'}.",
        )
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print("approve_recommendation error:", e)
        return False
    finally:
        db.close()


def reject_recommendation(recommendation_id, approver_name):
    db = SessionLocal()
    try:
        _bootstrap_recommendations_from_csv_if_needed(db)
        tenant_id = _get_default_tenant_id(db)
        row = (
            db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.tenant_id == int(tenant_id),
                RecommendationRecord.recommendation_id == recommendation_id,
            )
            .first()
        )
        if row is None:
            return False

        row.status = "rejected"
        row.approved_by = _normalize(approver_name)
        row.execution_status = "not_executed"
        row.execution_note = "Recommendation rejected by manager."
        row.affected_entities = ""

        _record_audit(
            db,
            "reject_recommendation",
            _normalize(approver_name),
            recommendation_id,
            "success",
            "Recommendation rejected by manager.",
        )
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print("reject_recommendation error:", e)
        return False
    finally:
        db.close()


def show_admin_approval_panel(peak, beds_needed, doctors_needed, emergency_level, approver_name):
    page_header(
        "Approvals",
        "Review and approve AI-generated operational recommendations with full traceability.",
    )
    alert_box(
        "Approvals turn forecast and optimization recommendations into tracked operational decisions. "
        "Each approval or rejection is recorded in the immutable audit trail.",
        level="info",
    )

    top1, top2, top3 = st.columns(3)
    with top1:
        st.caption("Demo safety")
        st.write("No fake saved data is generated automatically.")
    with top2:
        st.caption("Workflow source")
        st.write("Forecast + Optimization")
    with top3:
        level = str(emergency_level or "LOW")
        tone = "critical" if level == "HIGH" else "warning" if level == "MEDIUM" else "success"
        status_badge(f"Emergency: {level}", tone)

    df = sync_recommendations(peak, beds_needed, doctors_needed, emergency_level)
    if df.empty:
        empty_state("No pending approvals. Recommended actions will appear here when operational decisions require manager review.")
        return

    pending_df = df[df["status"] == "pending"].copy()
    approved_df = df[df["status"] == "approved"].copy()
    rejected_df = df[df["status"] == "rejected"].copy()

    s1, s2, s3 = st.columns(3)
    s1.metric("Pending", len(pending_df))
    s2.metric("Approved", len(approved_df))
    s3.metric("Rejected", len(rejected_df))

    section_header("Pending approvals", "Items requiring manager review and decision tracking")
    if pending_df.empty:
        empty_state("No pending approvals. Recommended actions will appear here when operational decisions require manager review.")
    else:
        pending_df = pending_df.sort_values(by="timestamp", ascending=False)
        for _, row in pending_df.iterrows():
            _render_approval_card(row, approver_name)

    section_header("Decision history", "Approved and rejected recommendations with execution notes")
    history_df = pd.concat([approved_df, rejected_df], ignore_index=True)
    if history_df.empty:
        audit_history_df = _decision_history_from_audit()
        if audit_history_df.empty:
            empty_state("No processed recommendations yet.")
        else:
            st.caption("Decision history recovered from the audit trail.")
            modern_table(audit_history_df, key=scoped_key("approvals", "audit_decision_history"), preview_rows=25)
    else:
        history_df = history_df.sort_values(by="timestamp", ascending=False)
        display_df = history_df.rename(
            columns={
                "recommendation_id": "Request ID",
                "timestamp": "Created time",
                "type": "Request type",
                "message": "Reason / recommendation",
                "status": "Status",
                "approved_by": "Decision by",
                "execution_status": "Execution status",
                "execution_note": "Execution note",
                "affected_files": "Affected records",
            }
        )
        modern_table(display_df, key=scoped_key("approvals", "decision_history"), preview_rows=25)
