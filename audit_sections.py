import pandas as pd
import streamlit as st

from database import SessionLocal
from models import AuditEvent, Tenant
from settings import get_settings
from ui_components import alert_box, empty_state, page_header, section_header, status_badge


EXPECTED_COLS = ["audit_id", "timestamp", "action", "actor", "target", "status", "details"]


def _clean(value, default="—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _friendly_action(action: str) -> str:
    return _clean(action).replace("_", " ").title()


def _infer_module(action: str, target: str, details: str) -> str:
    text = f"{action} {target} {details}".lower()
    if "recommend" in text or "approval" in text or "approve" in text or "reject" in text:
        return "Approvals"
    if "alert" in text or "notification" in text:
        return "Alerts / Notifications"
    if "message" in text:
        return "Messages"
    if "appointment" in text or "or:" in text or "staff_shift" in text:
        return "Operations"
    return "System"


def _infer_department(text: str) -> str:
    body = _clean(text, "").lower()
    for dept in ["ICU", "ER", "General Ward", "Surgery", "Radiology"]:
        if dept.lower() in body:
            return dept
    return "All Departments"


def _status_tone(status: str) -> str:
    value = _clean(status, "").lower()
    if value == "success":
        return "success"
    if value in {"failed", "error"}:
        return "critical"
    if value in {"pending", "warning"}:
        return "warning"
    return "neutral"


def _display_audit_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    display = df.copy()
    display["module"] = display.apply(
        lambda r: _infer_module(r.get("action", ""), r.get("target", ""), r.get("details", "")),
        axis=1,
    )
    display["department"] = display.apply(
        lambda r: _infer_department(f"{r.get('target', '')} {r.get('details', '')}"),
        axis=1,
    )
    display["action"] = display["action"].map(_friendly_action)
    return display.rename(
        columns={
            "timestamp": "Timestamp",
            "actor": "User",
            "action": "Action",
            "module": "Module",
            "department": "Department",
            "details": "Details",
            "status": "Status",
            "target": "Target",
            "audit_id": "Audit ID",
        }
    )[["Timestamp", "User", "Action", "Module", "Department", "Status", "Target", "Details", "Audit ID"]]


def _get_default_tenant_id(db) -> int:
    settings = get_settings()
    slug = str(settings.default_tenant_slug or "demo-hospital").strip() or "demo-hospital"
    row = db.query(Tenant).filter(Tenant.slug == slug).first()
    if row is None:
        row = Tenant(name="Demo Hospital", slug=slug)
        db.add(row)
        db.commit()
        db.refresh(row)
    return int(row.id)


@st.cache_data(ttl=30, show_spinner=False)
def load_audit_log():
    db = SessionLocal()
    try:
        tenant_id = _get_default_tenant_id(db)
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == int(tenant_id))
            .order_by(AuditEvent.id.desc())
            .all()
        )
        data = [
            {
                "audit_id": str(row.audit_id or "").strip(),
                "timestamp": str(row.timestamp or "").strip(),
                "action": str(row.action or "").strip(),
                "actor": str(row.actor or "").strip(),
                "target": str(row.target or "").strip(),
                "status": str(row.status or "").strip(),
                "details": str(row.details or "").strip(),
            }
            for row in rows
        ]
        return pd.DataFrame(data, columns=EXPECTED_COLS)
    finally:
        db.close()


def show_audit_summary():
    page_header("Audit", "Operational traceability — approvals, resets, and workflow events.")
    alert_box("Audit trail records operational decisions and user actions for accountability.", level="info")
    df = load_audit_log()
    if df.empty:
        empty_state("No audit records available. Operational decisions will appear here after user actions are recorded.")
        return
    total = len(df)
    success = len(df[df["status"].str.lower() == "success"])
    failed = len(df[df["status"].str.lower() == "failed"])
    approve_actions = len(df[df["action"].str.contains("approve", case=False, na=False)])
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        status_badge(f"Events: {total}", "info")
    with c2:
        status_badge(f"Success: {success}", "success" if success else "neutral")
    with c3:
        status_badge(f"Failed: {failed}", "critical" if failed else "neutral")
    with c4:
        status_badge(f"Approvals: {approve_actions}", "warning" if approve_actions else "neutral")


def show_audit_table():
    section_header("Event log", "Readable operational action history")
    df = load_audit_log()
    if df.empty:
        empty_state("No audit log records available. Operational decisions will appear here after user actions are recorded.")
        return
    sorted_df = df.sort_values(by="timestamp", ascending=False)
    display_df = _display_audit_df(sorted_df)
    _ROW_LIMIT = 200
    if len(display_df) > _ROW_LIMIT:
        st.caption(f"Showing the {_ROW_LIMIT} most recent events. Download below for the full log ({len(display_df)} total).")
        st.dataframe(display_df.head(_ROW_LIMIT), use_container_width=True, hide_index=True)
        st.download_button(
            "Download full audit log (CSV)",
            data=sorted_df.to_csv(index=False).encode("utf-8"),
            file_name="audit_log_full.csv",
            mime="text/csv",
            key="audit_full_download",
        )
    else:
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def show_execution_trace():
    section_header("Execution trace", "A compact timeline of recommendation and decision actions")
    df = load_audit_log()
    if df.empty:
        empty_state("No execution trace available. Approval and decision actions will appear here once recorded.")
        return
    execution_df = df[df["action"].str.contains("approve|reject|reset|sync", case=False, na=False)].copy()
    if execution_df.empty:
        empty_state("No execution-related audit events yet.")
        return
    execution_df = execution_df.sort_values(by="timestamp", ascending=False)
    for _, row in execution_df.iterrows():
        status = str(row["status"]).lower()
        module = _infer_module(row["action"], row["target"], row["details"])
        department = _infer_department(f"{row['target']} {row['details']}")
        with st.container(border=True):
            h1, h2 = st.columns([0.78, 0.22])
            with h1:
                st.markdown(f"#### {_friendly_action(row['action'])}")
                st.caption(f"Timestamp: {row['timestamp']} • Audit ID: {row['audit_id']}")
            with h2:
                status_badge(status.upper(), _status_tone(status))
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("User")
                st.write(_clean(row["actor"]))
            with c2:
                st.caption("Module")
                st.write(module)
            with c3:
                st.caption("Department")
                st.write(department)
            st.write(f"**Target:** {_clean(row['target'])}")
            st.write(f"**Details:** {_clean(row['details'])}")

