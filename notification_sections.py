import streamlit as st
from api_client import get_messages
from ui_components import alert_box
from ui_components import badge
from datetime import datetime
from api_client import login_user   
from dashboard_sections import show_forecast
from staff_sections import show_my_shifts
from approval_sections import show_admin_approval_panel
from audit_sections import show_audit_summary, show_audit_table, show_execution_trace
from message_center_sections import show_message_center
from notification_sections import show_notifications_panel
from ui_components import empty_state
st.markdown("## 🔔 Notifications")
badge("3 New Alerts", "red")
alerts = [
    {"msg": "ICU overload", "level": "critical"},
    {"msg": "Doctor shortage", "level": "warning"},
    {"msg": "New COVID-19 case", "level": "critical"},
]
for a in alerts:
    alert_box(a["msg"], a["level"])


def get_unread_count(messages):
    return len([m for m in messages if m.get("acknowledged") == "no"])
    st.metric("Unread Alerts", get_unread_count(messages))

def _fetch_messages(role=None, department=None, limit=50, unread_only=False):
    response = get_messages(
        role=role,
        department=department,
        limit=limit,
        unread_only=unread_only,
    )

    if not response:
        return []

    messages = response.get("messages", [])
    if not isinstance(messages, list):
        return []

    clean_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            clean_messages.append(msg)

    return clean_messages


def _render_reply(msg: dict):
    reply = str(msg.get("reply", "")).strip()
    reply_by = str(msg.get("reply_by", "")).strip()
    reply_timestamp = str(msg.get("reply_timestamp", "")).strip()

    if not reply:
        return

    st.success(f"Reply: {reply}")

    caption_parts = []
    if reply_by:
        caption_parts.append(f"By: {reply_by}")
    if reply_timestamp:
        caption_parts.append(f"At: {reply_timestamp}")

    if caption_parts:
        st.caption(" | ".join(caption_parts))


def show_alert_center(role=None, department=None):
    st.markdown("## 🚨 Alert Center")

    messages = _fetch_messages(role=role, department=department, limit=50)

    if not messages:
        st.info("No active alerts or messages.")
        return

    alert_messages = [
        msg for msg in messages
        if str(msg.get("priority", "")).lower() in ["critical", "high"]
    ]

    if not alert_messages:
        st.info("No critical or high-priority alerts.")
        return

    for msg in alert_messages:
        title = msg.get("title", "Untitled Alert")
        body = msg.get("message", "")
        priority = str(msg.get("priority", "normal")).lower()
        sender_name = msg.get("sender_name", "")
        sender_role = msg.get("sender_role", "")
        timestamp = msg.get("timestamp", "")

        st.markdown(f"### {title}")

        if priority == "critical":
            st.error("🚨 Critical")
        else:
            st.warning("⚠️ High")

        st.write(body)
        st.caption(f"From: {sender_name} ({sender_role}) | Time: {timestamp}")
        _render_reply(msg)
        st.markdown("---")


def show_staff_decision_feed(role, department=None):
    st.markdown("## 📢 Staff Decision Feed")

    messages = _fetch_messages(role=role, department=department, limit=50)

    if not messages:
        st.info("No decisions available yet.")
        return

    decision_messages = [
        msg
        for msg in messages
        if str(msg.get("category", "")).lower() in ["emergency", "coverage", "shift", "capacity", "custom"]
    ]

    if not decision_messages:
        st.info("No operational decisions available yet.")
        return

    for msg in decision_messages:
        title = msg.get("title", "Untitled")
        body = msg.get("message", "")
        priority = str(msg.get("priority", "normal")).lower()
        sender_name = msg.get("sender_name", "")
        sender_role = msg.get("sender_role", "")
        timestamp = msg.get("timestamp", "")

        st.markdown(f"### {title}")

        if priority == "critical":
            st.error(f"🚨 {body}")
        elif priority == "high":
            st.warning(f"⚠️ {body}")
        else:
            st.info(f"📌 {body}")

        st.caption(f"From: {sender_name} ({sender_role}) | Time: {timestamp}")
        _render_reply(msg)
        st.markdown("---")


def show_admin_decision_history():
    st.markdown("## 🗂 Decision History")

    messages = _fetch_messages(role=None, department=None, limit=100)

    if not messages:
        st.info("No decision history available.")
        return

    import pandas as pd

    df = pd.DataFrame(messages)

    keep_cols = [
        "message_id",
        "timestamp",
        "sender_name",
        "sender_role",
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
    ]

    available_cols = [c for c in keep_cols if c in df.columns]
    df = df[available_cols].copy()

    st.dataframe(df, use_container_width=True, hide_index=True)


def show_department_notice_board(department):
    st.markdown(f"## 📍 Department Notice Board — {department}")

    messages = _fetch_messages(role=None, department=department, limit=50)

    if not messages:
        st.info("No department notices available.")
        return

    filtered = []
    for msg in messages:
        target_department = str(msg.get("target_department", "")).strip().lower()
        if target_department in [str(department).strip().lower(), "all departments", "all"]:
            filtered.append(msg)

    if not filtered:
        st.info("No department-specific notices currently available.")
        return

    for msg in filtered:
        title = msg.get("title", "Untitled")
        body = msg.get("message", "")
        sender_name = msg.get("sender_name", "")
        sender_role = msg.get("sender_role", "")
        timestamp = msg.get("timestamp", "")

        st.markdown(f"### {title}")
        st.info(body)
        st.caption(f"From: {sender_name} ({sender_role}) | Time: {timestamp}")
        _render_reply(msg)
        st.markdown("---")



def show_notifications_panel(user):
    st.markdown("## 🔔 Alerts")

    alerts = [
        {"msg": "ICU overload", "level": "critical"},
        {"msg": "Doctor shortage", "level": "warning"}
    ]

    for a in alerts:
        alert_box(a["msg"], a["level"])

def highlight_rows(df):
    return df.style.applymap(
        lambda v: "background-color: red" if "critical" in str(v).lower() else ""
    )

def load_audit_log():
    from database import SessionLocal
    from models import AuditLog

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).all()

        EXPECTED_COLS = [
            "timestamp",
            "user",
            "action",
            "target",
            "status",
            "details",
        ]

        data = [
            {
                "timestamp": str(row.timestamp or "").strip(),
                "user": str(row.user or "").strip(),
                "action": str(row.action or "").strip(),
                "target": str(row.target or "").strip(),
                "status": str(row.status or "").strip(),
                "details": str(row.details or "").strip(),
            }
            for row in rows
        ]
        return pd.DataFrame(data, columns=EXPECTED_COLS)
    
st.markdown("<br>", unsafe_allow_html=True)



if not alerts:
    empty_state("No alerts right now 🎉")