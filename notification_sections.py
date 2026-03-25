import pandas as pd
import streamlit as st

from api_client import (
    ack_alert_api,
    get_alerts,
    get_notification_preferences,
    get_notifications,
    get_unread_notification_count,
    mark_notification_read,
    resolve_alert_api,
    update_notification_preferences,
)
from ui_components import alert_box, empty_state, page_header, section_header, status_badge


def _priority_badge(priority: str):
    prio = str(priority or "").lower()
    if prio == "critical":
        status_badge("CRITICAL", "critical")
    elif prio == "high":
        status_badge("HIGH", "warning")
    elif prio == "medium":
        status_badge("MEDIUM", "info")
    else:
        status_badge("LOW", "neutral")


def _render_preferences():
    page_header("Preferences", "Notification settings for your in-app workflow.")
    pref = (get_notification_preferences() or {}).get("preferences") or {}

    receive_in_app = st.toggle("Receive in-app notifications", value=bool(pref.get("receive_in_app", True)))
    critical_only = st.toggle("Critical only", value=bool(pref.get("critical_only", False)))

    # (Quiet hours are present in the model but optional in UI)
    if st.button("Save preferences"):
        res = update_notification_preferences(
            {
                "receive_in_app": bool(receive_in_app),
                "critical_only": bool(critical_only),
            }
        )
        if res and res.get("status") == "updated":
            st.success("Preferences saved")
        else:
            st.error("Failed to save preferences")


def show_alerts_center(user: dict):
    role = str(user.get("role", "")).lower()
    department = str(user.get("department", "All Departments")).strip()

    page_header("Alerts", "Operational alerts driven by forecast and optimization signals.")
    data = get_alerts(active_only=True, department=None, limit=100) or {}
    alerts = data.get("alerts", []) if isinstance(data, dict) else []

    if not alerts:
        empty_state("No active alerts.")
        return

    # Quick summary
    critical_count = len([a for a in alerts if str(a.get("priority", "")).lower() == "critical"])
    warning_count = len([a for a in alerts if str(a.get("priority", "")).lower() in {"high"}])
    meta1, meta2, meta3 = st.columns(3)
    with meta1:
        status_badge(f"Active alerts: {len(alerts)}", "info")
    with meta2:
        status_badge(f"Critical: {critical_count}", "critical" if critical_count else "neutral")
    with meta3:
        status_badge(f"High: {warning_count}", "warning" if warning_count else "neutral")

    for a in alerts:
        title = str(a.get("title", "Alert"))
        msg = str(a.get("message", ""))
        prio = str(a.get("priority", "medium"))
        dept = a.get("department")
        alert_id = str(a.get("alert_id", ""))
        source = str(a.get("source", "system"))
        created_at = str(a.get("created_at", ""))
        rec = str(a.get("recommendation_summary", "")).strip()

        with st.container(border=True):
            st.markdown(f"#### {title}")
            _priority_badge(prio)
            st.caption(
                (f"Department: {dept} | " if dept else "")
                + f"Source: {source} | Created: {created_at}"
            )
            st.write(msg)
            if rec:
                alert_box(f"Recommendation: {rec}", level="info")

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("Acknowledge", key=f"ack_{alert_id}"):
                    res = ack_alert_api(alert_id)
                    if res and res.get("status") == "acknowledged":
                        st.success("Acknowledged")
                        st.rerun()
                    else:
                        st.error("Ack failed")

            with col2:
                if role == "admin":
                    if st.button("Resolve", key=f"resolve_{alert_id}"):
                        res = resolve_alert_api(alert_id)
                        if res and res.get("status") == "resolved":
                            st.success("Resolved")
                            st.rerun()
                        else:
                            st.error("Resolve failed")
                else:
                    st.empty()

            with col3:
                # Convenience hint
                if dept and str(dept).strip().lower() != department.strip().lower() and role != "admin":
                    st.caption("(You might not normally see other departments; access is filtered server-side.)")


def show_notifications_center(user: dict):
    page_header("Notifications", "Your personal in-app notification inbox.")
    unread_meta = get_unread_notification_count() or {}
    unread_count = int(unread_meta.get("unread_count") or 0)
    status_badge(f"Unread: {unread_count}", "critical" if unread_count else "success")

    unread_only = st.toggle("Show unread only", value=False)
    data = get_notifications(unread_only=unread_only, limit=100) or {}
    rows = data.get("notifications", []) if isinstance(data, dict) else []

    if not rows:
        empty_state("No notifications.")
        return

    df = pd.DataFrame(rows)
    # Sort newest first
    if "created_at" in df.columns:
        df = df.sort_values(by="created_at", ascending=False)

    for n in df.to_dict("records"):
        nid = str(n.get("notification_id", ""))
        title = str(n.get("title", "Notification"))
        body = str(n.get("body", ""))
        created_at = str(n.get("created_at", ""))
        read_at = n.get("read_at")
        status = str(n.get("status", "delivered"))

        with st.container(border=True):
            st.markdown(f"#### {title}")
            st.caption(f"Status: {status} | Created: {created_at}")
            st.write(body)
            if read_at:
                status_badge("READ", "success")
            else:
                status_badge("UNREAD", "critical")

            if not read_at:
                if st.button("Mark as read", key=f"read_{nid}"):
                    res = mark_notification_read(nid)
                    if res and res.get("status") == "read":
                        st.success("Marked as read")
                        st.rerun()
                    else:
                        st.error("Failed")


def show_notifications_panel(user: dict):
    # Main page composition
    show_alerts_center(user)
    st.markdown("---")
    show_notifications_center(user)
    st.markdown("---")
    _render_preferences()
