from __future__ import annotations

import re

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


KNOWN_DEPARTMENTS = ["ER", "ICU", "General Ward", "Surgery", "Radiology"]
SEVERITY_ORDER = ["Critical", "Warning", "Info"]


def _clean(value, default: str = "—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return default
    return text


def _label(value) -> str:
    text = _clean(value, "").replace("_", " ").replace("-", " ").strip()
    return text.title() if text else "—"


def _priority_to_severity(priority: str) -> str:
    value = _clean(priority, "medium").lower()
    if value == "critical":
        return "Critical"
    if value in {"high", "warning"}:
        return "Warning"
    return "Info"


def _severity_tone(severity: str) -> str:
    value = _clean(severity, "Info").lower()
    if value == "critical":
        return "critical"
    if value == "warning":
        return "warning"
    return "info"


def _derive_notification_severity(row: dict) -> str:
    text = " ".join(
        [
            _clean(row.get("title"), ""),
            _clean(row.get("body"), ""),
            _clean(row.get("status"), ""),
        ]
    ).lower()
    if any(token in text for token in ["critical", "emergency", "surge", "severe"]):
        return "Critical"
    if any(token in text for token in ["warning", "high", "attention", "shortage", "review"]):
        return "Warning"
    return "Info"


def _derive_department(row: dict) -> str:
    explicit = row.get("department") or row.get("related_department") or row.get("target_department")
    if explicit:
        return _clean(explicit)
    text = f"{_clean(row.get('title'), '')} {_clean(row.get('body'), '')} {_clean(row.get('message'), '')}".lower()
    for dept in KNOWN_DEPARTMENTS:
        if dept.lower() in text:
            return dept
    return "All Departments"


def _notification_source(row: dict) -> str:
    if row.get("alert_id"):
        return "Alerts"
    if row.get("message_id"):
        return "Messages"
    return "Operations"


def _notification_status(row: dict) -> str:
    status = _clean(row.get("status"), "delivered").lower()
    if status in {"archived", "resolved"}:
        return "Resolved / Archived"
    if row.get("read_at") or status == "read":
        return "Read"
    return "Unread"


def _alert_status(row: dict) -> str:
    if row.get("resolved_at") or row.get("is_active") is False:
        return "Resolved"
    if row.get("is_acknowledged"):
        return "Acknowledged"
    return "Active"


def _render_meta_grid(items: list[tuple[str, str]]):
    cols = st.columns(min(4, max(1, len(items))))
    for idx, (label, value) in enumerate(items):
        with cols[idx % len(cols)]:
            st.caption(label)
            st.write(value)


def _apply_filters(rows: list[dict], *, prefix: str, is_alert: bool = False) -> list[dict]:
    if not rows:
        return rows

    severities = ["All"] + SEVERITY_ORDER
    departments = ["All"] + sorted({_derive_department(r) for r in rows if _derive_department(r)})
    statuses = ["All"] + sorted({_alert_status(r) if is_alert else _notification_status(r) for r in rows})
    sources = ["All"] + sorted(
        {
            _clean(r.get("source"), "Operations") if is_alert else _notification_source(r)
            for r in rows
        }
    )

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        selected_severity = st.selectbox("Severity", severities, key=f"{prefix}_severity")
    with f2:
        selected_department = st.selectbox("Department", departments, key=f"{prefix}_department")
    with f3:
        selected_status = st.selectbox("Status", statuses, key=f"{prefix}_status")
    with f4:
        selected_source = st.selectbox("Source module", sources, key=f"{prefix}_source")

    filtered = []
    for row in rows:
        severity = _priority_to_severity(row.get("priority")) if is_alert else _derive_notification_severity(row)
        department = _derive_department(row)
        status = _alert_status(row) if is_alert else _notification_status(row)
        source = _clean(row.get("source"), "Operations") if is_alert else _notification_source(row)

        if selected_severity != "All" and severity != selected_severity:
            continue
        if selected_department != "All" and department != selected_department:
            continue
        if selected_status != "All" and status != selected_status:
            continue
        if selected_source != "All" and source != selected_source:
            continue
        filtered.append(row)

    return filtered


def _render_preferences():
    page_header("Preferences", "Notification settings for your in-app workflow.")
    alert_box(
        "Notifications are in-app only in this demo. External email/SMS delivery is not implemented.",
        level="info",
    )
    pref = (get_notification_preferences() or {}).get("preferences") or {}

    receive_in_app = st.toggle("Receive in-app notifications", value=bool(pref.get("receive_in_app", True)))
    critical_only = st.toggle("Critical only", value=bool(pref.get("critical_only", False)))

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


def _alert_sort_key(row: dict) -> tuple[int, str]:
    severity = _priority_to_severity(row.get("priority"))
    rank = {"Critical": 0, "Warning": 1, "Info": 2}.get(severity, 3)
    return rank, _clean(row.get("created_at"), "")


def _render_alert_card(alert: dict, *, role: str, user_department: str):
    alert_id = _clean(alert.get("alert_id"), "")
    title = _clean(alert.get("title"), "Operational alert")
    msg = _clean(alert.get("message"), "")
    severity = _priority_to_severity(alert.get("priority"))
    dept = _derive_department(alert)
    source = _clean(alert.get("source"), "Operations")
    created_at = _clean(alert.get("created_at"), "—")
    rec = _clean(alert.get("recommendation_summary"), "")
    status = _alert_status(alert)
    simulation_value = alert.get("is_simulation")
    source_label = ""
    if simulation_value is True:
        source_label = "Simulation alert • "
    elif simulation_value is False:
        source_label = "Real operational alert • "
    affected_resource = " / ".join(
        [part for part in [_clean(alert.get("related_entity_type"), ""), _clean(alert.get("related_entity_id"), "")] if part]
    ) or "Not specified"
    escalation = "Required" if severity in {"Critical", "Warning"} else "Monitor"

    with st.container(border=True):
        head1, head2, head3 = st.columns([0.62, 0.18, 0.20])
        with head1:
            st.markdown(f"#### {title}")
        with head2:
            status_badge(severity.upper(), _severity_tone(severity))
        with head3:
            status_badge(status.upper(), "success" if status == "Resolved" else "warning" if status == "Acknowledged" else _severity_tone(severity))

        st.caption(f"{source_label}Source module: {source} • Created: {created_at}")
        st.write(msg)
        _render_meta_grid(
            [
                ("Department", dept),
                ("Affected resource", affected_resource),
                ("Escalation", escalation),
                ("Alert type", _label(alert.get("type"))),
            ]
        )
        if rec:
            alert_box(f"Recommended action: {rec}", level="info")
        else:
            st.caption("Recommended action: Review the source workflow for next operational steps.")

        action1, action2, action3 = st.columns([1, 1, 2])
        with action1:
            ack_disabled = status in {"Acknowledged", "Resolved"} or not alert_id
            if st.button("Acknowledge", key=f"ack_{alert_id}", disabled=ack_disabled):
                res = ack_alert_api(alert_id)
                if res and res.get("status") == "acknowledged":
                    st.success("Alert acknowledged")
                    st.rerun()
                else:
                    st.error("Acknowledge failed")
            if ack_disabled and status == "Acknowledged":
                st.caption("Already acknowledged.")
        with action2:
            if role == "admin":
                resolve_disabled = status == "Resolved" or not alert_id
                if st.button("Resolve", key=f"resolve_{alert_id}", disabled=resolve_disabled):
                    res = resolve_alert_api(alert_id)
                    if res and res.get("status") == "resolved":
                        st.success("Alert resolved")
                        st.rerun()
                    else:
                        st.error("Resolve failed")
                if resolve_disabled and status == "Resolved":
                    st.caption("Already resolved.")
            else:
                st.caption("Resolve is available to administrators.")
        with action3:
            if dept and dept.lower() != user_department.lower() and role != "admin":
                st.caption("Access is filtered server-side for department visibility.")
            with st.expander("View details", expanded=False):
                st.write(f"**Rule:** {_clean(alert.get('generated_by_rule'), 'Not specified')}")
                st.write(f"**Expires:** {_clean(alert.get('expires_at'), 'No expiry set')}")
                st.write(f"**Acknowledged at:** {_clean(alert.get('acknowledged_at'), 'Not acknowledged')}")
                st.write(f"**Resolved at:** {_clean(alert.get('resolved_at'), 'Not resolved')}")


def show_alerts_center(user: dict):
    role = str(user.get("role", "")).lower()
    department = str(user.get("department", "All Departments")).strip()

    page_header("Alerts", "Operational alerts driven by forecast, simulation, and optimization signals.")
    data = get_alerts(active_only=True, department=None, limit=100) or {}
    alerts = data.get("alerts", []) if isinstance(data, dict) else []

    if not alerts:
        empty_state("No active alerts. Hospital operations are stable.")
        return

    critical_count = len([a for a in alerts if _priority_to_severity(a.get("priority")) == "Critical"])
    warning_count = len([a for a in alerts if _priority_to_severity(a.get("priority")) == "Warning"])
    acknowledged_count = len([a for a in alerts if a.get("is_acknowledged")])
    meta1, meta2, meta3, meta4 = st.columns(4)
    meta1.metric("Active alerts", len(alerts))
    meta2.metric("Critical", critical_count)
    meta3.metric("Warnings", warning_count)
    meta4.metric("Acknowledged", acknowledged_count)

    section_header("Alert filters", "Critical alerts are always sorted first after filters are applied.")
    filtered = _apply_filters(alerts, prefix="alerts", is_alert=True)
    if not filtered:
        empty_state("No alerts match the selected filters.")
        return

    sorted_alerts = sorted(filtered, key=_alert_sort_key)
    for severity in SEVERITY_ORDER:
        severity_rows = [a for a in sorted_alerts if _priority_to_severity(a.get("priority")) == severity]
        if not severity_rows:
            continue
        section_header(f"{severity} alerts")
        for alert in severity_rows:
            _render_alert_card(alert, role=role, user_department=department)


def _notification_recommendation(row: dict) -> str:
    body = _clean(row.get("body"), "")
    match = re.search(r"(recommend(?:ed|ation)?[^.]*\.)", body, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if row.get("alert_id"):
        return "Review the related alert and acknowledge or resolve if action is complete."
    if row.get("message_id"):
        return "Open Messages to coordinate with the sender or recipient."
    return "Not provided"


def _render_notification_card(row: dict):
    notification_id = _clean(row.get("notification_id"), "")
    title = _clean(row.get("title"), "Notification")
    body = _clean(row.get("body"), "")
    created_at = _clean(row.get("created_at"), "—")
    severity = _derive_notification_severity(row)
    status = _notification_status(row)
    department = _derive_department(row)
    source = _notification_source(row)
    recommended_action = _notification_recommendation(row)

    with st.container(border=True):
        h1, h2, h3 = st.columns([0.62, 0.18, 0.20])
        with h1:
            st.markdown(f"#### {title}")
        with h2:
            status_badge(severity.upper(), _severity_tone(severity))
        with h3:
            tone = "critical" if status == "Unread" else "success" if status == "Resolved / Archived" else "neutral"
            status_badge(status.upper(), tone)
        st.write(body)
        _render_meta_grid(
            [
                ("Department", department),
                ("Source module", source),
                ("Created time", created_at),
                ("Recommended action", recommended_action),
            ]
        )
        if status == "Unread" and notification_id:
            if st.button("Mark as read", key=f"read_{notification_id}"):
                res = mark_notification_read(notification_id)
                if res and res.get("status") == "read":
                    st.success("Marked as read")
                    st.rerun()
                else:
                    st.error("Failed to mark notification as read")


def _render_notification_group(title: str, rows: list[dict]):
    section_header(title)
    if not rows:
        empty_state(f"No {title.lower()} notifications.")
        return
    for severity in SEVERITY_ORDER:
        severity_rows = [r for r in rows if _derive_notification_severity(r) == severity]
        if not severity_rows:
            continue
        st.markdown(f"##### {severity}")
        for row in severity_rows:
            _render_notification_card(row)


def show_notifications_center(user: dict):
    page_header("Notifications", "Your personal in-app notification inbox for operational workflow updates.")
    unread_meta = get_unread_notification_count() or {}
    unread_count = int(unread_meta.get("unread_count") or 0)

    data = get_notifications(unread_only=False, limit=100) or {}
    rows = data.get("notifications", []) if isinstance(data, dict) else []

    if not rows:
        status_badge("Unread: 0", "success")
        empty_state("No active notifications. Hospital operations are stable.")
        return

    df = pd.DataFrame(rows)
    if "created_at" in df.columns:
        df = df.sort_values(by="created_at", ascending=False)
    records = df.to_dict("records")

    read_rows = [r for r in records if _notification_status(r) == "Read"]
    critical_count = len([r for r in records if _derive_notification_severity(r) == "Critical"])
    warning_count = len([r for r in records if _derive_notification_severity(r) == "Warning"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Unread", unread_count)
    c2.metric("Read", len(read_rows))
    c3.metric("Critical", critical_count)
    c4.metric("Warnings", warning_count)

    section_header("Notification filters", "Filter by status, severity, department, and source module.")
    filtered = _apply_filters(records, prefix="notifications", is_alert=False)
    if not filtered:
        empty_state("No notifications match the selected filters.")
        return

    filtered_unread = [r for r in filtered if _notification_status(r) == "Unread"]
    filtered_read = [r for r in filtered if _notification_status(r) == "Read"]
    filtered_archived = [r for r in filtered if _notification_status(r) == "Resolved / Archived"]

    tab_unread, tab_read, tab_archived = st.tabs(
        [
            f"Unread ({len(filtered_unread)})",
            f"Read ({len(filtered_read)})",
            f"Resolved / Archived ({len(filtered_archived)})",
        ]
    )
    with tab_unread:
        _render_notification_group("Unread", filtered_unread)
    with tab_read:
        _render_notification_group("Read", filtered_read)
    with tab_archived:
        _render_notification_group("Resolved / Archived", filtered_archived)


def show_notifications_panel(user: dict):
    show_alerts_center(user)
    st.markdown("---")
    show_notifications_center(user)
    st.markdown("---")
    _render_preferences()