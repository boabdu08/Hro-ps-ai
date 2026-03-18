import pandas as pd
import streamlit as st

from api_client import get_messages
from ui_components import badge, empty_state, section_header


def _fetch_messages(role=None, department=None, limit=50, unread_only=False):
    response = get_messages(role=role, department=department, limit=limit, unread_only=unread_only)
    if not response:
        return []
    messages = response.get("messages", [])
    return [msg for msg in messages if isinstance(msg, dict)]


def get_unread_count(messages):
    return len([m for m in messages if str(m.get("acknowledged", "no")).lower() == "no"])


def _render_reply(msg: dict):
    reply = str(msg.get("reply", "")).strip()
    reply_by = str(msg.get("reply_by", "")).strip()
    reply_timestamp = str(msg.get("reply_timestamp", "")).strip()
    if not reply:
        return
    st.success(f"Reply: {reply}")
    meta = []
    if reply_by:
        meta.append(f"By: {reply_by}")
    if reply_timestamp:
        meta.append(f"At: {reply_timestamp}")
    if meta:
        st.caption(" | ".join(meta))


def show_alert_center(role=None, department=None):
    section_header("🚨 Alert Center")
    messages = _fetch_messages(role=role, department=department, limit=50)
    if not messages:
        empty_state("No active alerts or messages.")
        return

    unread = get_unread_count(messages)
    badge(f"Unread: {unread}", "#ef4444" if unread else "#10b981")
    alert_messages = [msg for msg in messages if str(msg.get("priority", "")).lower() in ["critical", "high"]]
    if not alert_messages:
        empty_state("No critical or high-priority alerts.")
        return

    for msg in alert_messages:
        st.markdown(f"### {msg.get('title', 'Untitled Alert')}")
        priority = str(msg.get("priority", "normal")).lower()
        if priority == "critical":
            badge("Critical", "#ef4444")
        else:
            badge("High", "#f59e0b")
        st.write(msg.get("message", ""))
        st.caption(f"From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | Time: {msg.get('timestamp', '')}")
        _render_reply(msg)
        st.markdown("---")


def show_staff_decision_feed(role, department=None):
    section_header("📢 Staff Decision Feed")
    messages = _fetch_messages(role=role, department=department, limit=50)
    if not messages:
        empty_state("No decisions available yet.")
        return

    decision_messages = [
        msg for msg in messages if str(msg.get("category", "")).lower() in ["emergency", "coverage", "shift", "capacity", "custom"]
    ]
    if not decision_messages:
        empty_state("No operational decisions available yet.")
        return

    for msg in decision_messages:
        st.markdown(f"### {msg.get('title', 'Untitled')}")
        priority = str(msg.get("priority", "normal")).lower()
        body = msg.get("message", "")
        if priority == "critical":
            st.error(f"🚨 {body}")
        elif priority == "high":
            st.warning(f"⚠️ {body}")
        else:
            st.info(f"📌 {body}")
        st.caption(f"From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | Time: {msg.get('timestamp', '')}")
        _render_reply(msg)
        st.markdown("---")


def show_admin_decision_history():
    section_header("🗂 Decision History")
    messages = _fetch_messages(limit=100)
    if not messages:
        empty_state("No decision history available.")
        return

    df = pd.DataFrame(messages)
    keep_cols = [
        "message_id", "timestamp", "sender_name", "sender_role", "target_role", "target_department",
        "priority", "category", "title", "message", "status", "reply", "reply_by", "reply_timestamp", "acknowledged",
    ]
    available_cols = [c for c in keep_cols if c in df.columns]
    st.dataframe(df[available_cols].copy(), use_container_width=True, hide_index=True)


def show_department_notice_board(department):
    section_header(f"📍 Department Notice Board — {department}")
    messages = _fetch_messages(department=department, limit=50)
    if not messages:
        empty_state("No department notices available.")
        return

    filtered = []
    for msg in messages:
        target_department = str(msg.get("target_department", "")).strip().lower()
        if target_department in [str(department).strip().lower(), "all departments", "all"]:
            filtered.append(msg)

    if not filtered:
        empty_state("No department-specific notices currently available.")
        return

    for msg in filtered:
        st.markdown(f"### {msg.get('title', 'Untitled')}")
        st.info(msg.get("message", ""))
        st.caption(f"From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | Time: {msg.get('timestamp', '')}")
        _render_reply(msg)
        st.markdown("---")


def show_notifications_panel(user: dict):
    role = str(user.get("role", "")).lower()
    department = user.get("department", "All Departments")
    show_alert_center(role=role, department=department)
    st.markdown("---")
    show_staff_decision_feed(role=role, department=department)
    st.markdown("---")
    show_department_notice_board(department)

