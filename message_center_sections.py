import streamlit as st
import re

from api_client import (
    acknowledge_message_api,
    archive_message_api,
    get_message_templates,
    get_messages,
    get_unread_message_count,
    send_message_api,
    send_quick_reply_api,
)
from ui_components import alert_box, empty_state, page_header, section_header, status_badge

TARGET_ROLE_OPTIONS = ["doctor", "nurse", "all"]
TARGET_DEPARTMENT_OPTIONS = [
    "All Departments",
    "ER",
    "ICU",
    "General Ward",
    "Surgery",
    "Radiology",
]
PRIORITY_OPTIONS = ["normal", "high", "critical"]


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(text or "")))


def _render_text_body(text: str):
    body = _clean_text(text)
    if not body:
        return
    if _contains_arabic(body):
        st.markdown(
            f"<div dir='rtl' style='text-align:right; line-height:1.8'>{_escape_html(body)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.write(body)


def _status_tone(status: str) -> str:
    value = str(status or "").strip().lower()
    if value in {"unread", "critical"}:
        return "critical"
    if value in {"high", "attention", "archived"}:
        return "warning"
    if value in {"read", "sent", "updated", "resolved"}:
        return "success"
    return "neutral"


def _priority_badge(priority: str):
    value = str(priority).strip().lower()
    if value == "critical":
        status_badge("CRITICAL", "critical")
    elif value == "high":
        status_badge("HIGH", "warning")
    else:
        status_badge("NORMAL", "info")


def _safe_templates_response():
    response = get_message_templates() or {}
    return {
        "admin_templates": response.get("admin_templates", []),
        "staff_quick_replies": response.get("staff_quick_replies", []),
    }


def _safe_messages_response(
    role=None,
    department=None,
    limit=50,
    unread_only=False,
    include_archived=False,
    sender_name=None,
):
    response = get_messages(
        role=role,
        department=department,
        limit=limit,
        unread_only=unread_only,
        include_archived=include_archived,
        sender_name=sender_name,
    ) or {}

    return {
        "messages": response.get("messages", []),
        "quick_replies": response.get("quick_replies", []),
    }


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _message_preview(text: str, length: int = 140) -> str:
    body = _clean_text(text)
    if len(body) <= length:
        return body
    return body[: length - 1].rstrip() + "…"


def _message_status(msg: dict) -> str:
    if bool(msg.get("archived")) or bool(msg.get("user_archived")):
        return "Archived"
    return "Read" if bool(msg.get("is_read", False)) else "Unread"


def _message_sender_recipient(msg: dict) -> tuple[str, str]:
    sender = _clean_text(msg.get("sender_name")) or "Unknown sender"
    sender_role = _clean_text(msg.get("sender_role"))
    recipient_role = _clean_text(msg.get("target_role")) or "all"
    recipient_department = _clean_text(msg.get("target_department")) or "All Departments"
    sender_label = f"{sender} ({sender_role})" if sender_role else sender
    recipient_label = f"{recipient_role.title()} • {recipient_department}"
    return sender_label, recipient_label


def _render_message_card(
    msg: dict,
    *,
    key_prefix: str,
    quick_replies: list[str] | None = None,
    user_name: str | None = None,
    allow_reply: bool = False,
    allow_actions: bool = True,
):
    message_id = _clean_text(msg.get("message_id"))
    title = _clean_text(msg.get("title")) or "Untitled message"
    priority = _clean_text(msg.get("priority")) or "normal"
    category = _clean_text(msg.get("category")) or _clean_text(msg.get("message_type")) or "coordination"
    created = _clean_text(msg.get("created_at")) or _clean_text(msg.get("timestamp")) or "—"
    status = _message_status(msg)
    sender, recipient = _message_sender_recipient(msg)
    department = _clean_text(msg.get("target_department")) or "All Departments"
    role = _clean_text(msg.get("target_role")) or "all"

    with st.container(border=True):
        c_title, c_priority, c_status = st.columns([0.60, 0.18, 0.22])
        with c_title:
            st.markdown(f"#### {title}")
            st.caption(f"{category.title()} • Created: {created}")
        with c_priority:
            _priority_badge(priority)
        with c_status:
            status_badge(status.upper(), _status_tone(status))

        _render_text_body(_message_preview(msg.get("message", "")))
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.caption("Sender")
            st.write(sender)
        with m2:
            st.caption("Recipient")
            st.write(recipient)
        with m3:
            st.caption("Department / role")
            st.write(f"{department} / {role}")
        with m4:
            st.caption("Read state")
            st.write(status)

        _reply_block(msg)

        if allow_reply and message_id:
            existing_reply = _clean_text(msg.get("reply", ""))
            if not existing_reply:
                with st.expander("Reply / coordination update", expanded=False):
                    replies = quick_replies or []
                    if replies:
                        cols = st.columns(min(4, len(replies)))
                        for q_idx, reply in enumerate(replies):
                            with cols[q_idx % len(cols)]:
                                if st.button(reply, key=f"quick_reply_{key_prefix}_{message_id}_{q_idx}"):
                                    result = send_quick_reply_api(
                                        message_id=message_id,
                                        reply_text=reply,
                                        replied_by=user_name or "Staff User",
                                    )
                                    if result and result.get("status") == "updated":
                                        st.success("Reply sent successfully.")
                                        st.rerun()
                                    else:
                                        st.error("Failed to send reply.")

                    custom_reply = st.text_input("Custom reply", key=f"custom_reply_input_{key_prefix}_{message_id}")
                    if st.button("Send custom reply", key=f"send_custom_reply_{key_prefix}_{message_id}"):
                        if not custom_reply.strip():
                            st.warning("Please enter a reply first.")
                        else:
                            result = send_quick_reply_api(
                                message_id=message_id,
                                reply_text=custom_reply.strip(),
                                replied_by=user_name or "Staff User",
                            )
                            if result and result.get("status") == "updated":
                                st.success("Custom reply sent successfully.")
                                st.rerun()
                            else:
                                st.error("Failed to send reply.")

        if allow_actions and message_id:
            a1, a2, a3 = st.columns([1, 1, 2])
            with a1:
                _render_ack_button(message_id, bool(msg.get("is_read", False)), f"{key_prefix}_{message_id}")
            with a2:
                if status != "Archived":
                    _render_archive_button(message_id, f"{key_prefix}_{message_id}")
                else:
                    st.caption("Already archived.")
            with a3:
                with st.expander("View full message", expanded=False):
                    _render_text_body(msg.get("message", ""))
                    st.caption(f"Message ID: {message_id}")


def _reply_block(msg: dict):
    reply = _clean_text(msg.get("reply", ""))
    reply_by = _clean_text(msg.get("reply_by", ""))
    reply_timestamp = _clean_text(msg.get("reply_timestamp", ""))

    if not reply:
        return

    if _contains_arabic(reply):
        st.markdown(
            f"<div dir='rtl' style='text-align:right; padding:0.75rem; border-radius:0.5rem; background:rgba(34,197,94,0.14); line-height:1.8'><strong>Reply:</strong> {_escape_html(reply)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.success(f"Reply: {reply}")

    meta = []
    if reply_by:
        meta.append(f"By: {reply_by}")
    if reply_timestamp:
        meta.append(f"At: {reply_timestamp}")

    if meta:
        st.caption(" | ".join(meta))


def _render_archive_button(message_id: str, key_suffix: str):
    if st.button("Archive", key=f"archive_{key_suffix}"):
        result = archive_message_api(message_id)
        if result and result.get("status") == "archived":
            st.success("Message archived.")
            st.rerun()
        else:
            st.error("Failed to archive message.")


def _render_ack_button(message_id: str, is_read: bool, key_suffix: str):
    if bool(is_read):
        return

    if st.button("Mark as Read", key=f"ack_{key_suffix}"):
        result = acknowledge_message_api(message_id)
        if result and result.get("status") == "acknowledged":
            st.success("Marked as read (for you only).")
            st.rerun()
        else:
            st.error("Failed to mark message as read.")


def show_admin_message_center(sender_name: str, sender_role: str):
    page_header("Messages", "Operational messaging to coordinate staff across departments.")
    alert_box(
        "This message center is for in-app coordination only. External email/SMS delivery is a future SaaS feature.",
        level="info",
    )
    st.caption("Arabic supported: Arabic message bodies and replies render right-to-left in the message cards.")
    data = _safe_templates_response()
    templates = data["admin_templates"]

    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        selected_target_role = st.selectbox(
            "Target Role",
            TARGET_ROLE_OPTIONS,
            index=2,
            key="admin_target_role",
        )
    with top_col2:
        selected_target_department = st.selectbox(
            "Target Department",
            TARGET_DEPARTMENT_OPTIONS,
            index=0,
            key="admin_target_department",
        )
    with top_col3:
        selected_priority = st.selectbox(
            "Priority",
            PRIORITY_OPTIONS,
            index=1,
            key="admin_message_priority",
        )

    section_header("Quick templates", "Demo-safe in-app templates for common hospital coordination moments.")
    if not templates:
        empty_state("No quick templates available.")
    else:
        for idx, template in enumerate(templates):
            title = template.get("title", "Untitled Template")
            message = template.get("message", "")
            category = template.get("category", "general")

            with st.container(border=True):
                t1, t2 = st.columns([0.78, 0.22])
                with t1:
                    st.markdown(f"#### {title}")
                    st.write(message)
                    st.caption(
                        f"Category: {category} • Default role: {template.get('target_role', 'all')} • "
                        f"Default department: {template.get('target_department', 'All Departments')}"
                    )
                with t2:
                    _priority_badge(template.get("priority", selected_priority))
                    if st.button(f"Send template", key=f"send_template_{idx}"):
                        result = send_message_api(
                            sender_name=sender_name,
                            sender_role=sender_role,
                            target_role=selected_target_role,
                            target_department=selected_target_department,
                            category=category,
                            title=title,
                            message=message,
                            priority=selected_priority,
                        )
                        if result and result.get("status") == "sent":
                            st.success("Template message sent successfully.")
                            st.rerun()
                        else:
                            st.error("Failed to send template message.")

    section_header("Compose", "Send an internal coordination update to a role or department.")
    custom_title = st.text_input("Custom Title", key="admin_custom_title")
    custom_type = st.selectbox(
        "Message Type",
        ["custom", "emergency", "coverage", "shift", "capacity"],
        key="admin_custom_type",
    )
    custom_message = st.text_area("Custom Message", key="admin_custom_message")

    if st.button("Send Custom Message", key="send_custom_admin_message"):
        if not custom_title.strip() or not custom_message.strip():
            st.warning("Please enter both title and message.")
        else:
            result = send_message_api(
                sender_name=sender_name,
                sender_role=sender_role,
                target_role=selected_target_role,
                target_department=selected_target_department,
                category=custom_type,
                title=custom_title.strip(),
                message=custom_message.strip(),
                priority=selected_priority,
            )
            if result and result.get("status") == "sent":
                st.success("Custom message sent successfully.")
                st.rerun()
            else:
                st.error("Failed to send custom message.")

    section_header("Sent messages", "Inbox-style view of active coordination messages you sent.")
    unread_meta = get_unread_message_count() or {}
    if isinstance(unread_meta, dict) and "unread_count" in unread_meta:
        st.caption(f"Your unread (personal) inbox count: {int(unread_meta.get('unread_count') or 0)}")

    sent_messages = _safe_messages_response(
        sender_name=sender_name,
        include_archived=False,
        limit=50,
    )["messages"]

    if not sent_messages:
        empty_state("No active sent messages.")
    else:
        for msg in sent_messages:
            _render_message_card(msg, key_prefix="admin_sent")

    section_header("Archived", "Messages hidden from your active coordination queue.")
    archived_messages = _safe_messages_response(
        sender_name=sender_name,
        include_archived=True,
        limit=50,
    )["messages"]

    if not archived_messages:
        empty_state("No archived sent messages.")
    else:
        for msg in archived_messages:
            _render_message_card(msg, key_prefix="admin_archived", allow_actions=False)


def show_staff_message_center(user_name: str, role: str, department: str):
    page_header("Messages", "Your inbox for operational updates, alerts, and quick replies.")
    alert_box(
        "This message center is for in-app coordination only. External email/SMS delivery is a future SaaS feature.",
        level="info",
    )
    st.caption("Arabic supported: Arabic message bodies and replies render right-to-left in the message cards.")

    section_header("Send update to Admin", "Share a staffing, patient-flow, or department coordination update.")
    with st.expander("Compose a quick update", expanded=False):
        staff_title = st.text_input("Title", key="staff_to_admin_title")
        staff_message = st.text_area("Message", key="staff_to_admin_message")
        staff_priority = st.selectbox("Priority", ["normal", "high", "critical"], index=0, key="staff_to_admin_priority")
        if st.button("Send to Admin", key="staff_send_to_admin"):
            if not staff_title.strip() or not staff_message.strip():
                st.warning("Please enter both title and message.")
            else:
                result = send_message_api(
                    sender_role=role,
                    sender_name=user_name,
                    target_role="admin",
                    target_department="All Departments",
                    priority=staff_priority,
                    category="staff_update",
                    title=staff_title.strip(),
                    message=staff_message.strip(),
                )
                if result and result.get("status") == "sent":
                    st.success("Message sent to admin.")
                    st.rerun()
                else:
                    st.error("Failed to send message to admin.")

    tab_inbox, tab_archive = st.tabs(["Inbox", "Archive"])

    with tab_inbox:
        data = _safe_messages_response(
            role=role,
            department=department,
            limit=100,
            unread_only=False,
            include_archived=False,
        )
        messages = data["messages"]
        quick_replies = data["quick_replies"]

        unread_meta = get_unread_message_count() or {}
        if isinstance(unread_meta, dict) and "unread_count" in unread_meta:
            count = int(unread_meta.get("unread_count") or 0)
            status_badge(f"Unread: {count}", "critical" if count else "success")

        if not messages:
            empty_state("No messages available. Coordination updates will appear here when sent by the operations team.")
        else:
            for msg in messages:
                _render_message_card(
                    msg,
                    key_prefix="staff_inbox",
                    quick_replies=quick_replies,
                    user_name=user_name,
                    allow_reply=True,
                )

    with tab_archive:
        archived_messages = _safe_messages_response(
            role=role,
            department=department,
            limit=100,
            unread_only=False,
            include_archived=True,
        )["messages"]

        if not archived_messages:
            empty_state("No archived messages.")
        else:
            for msg in archived_messages:
                _render_message_card(msg, key_prefix="staff_archive", allow_actions=False)


def show_message_center(user: dict):
    role = str(user.get("role", "")).lower()

    if role == "admin":
        show_admin_message_center(
            sender_name=user.get("name", "Hospital Admin"),
            sender_role=role,
        )
    else:
        show_staff_message_center(
            user_name=user.get("name", "Staff User"),
            role=role,
            department=user.get("department", "All Departments"),
        )
