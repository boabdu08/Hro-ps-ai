import streamlit as st

from api_client import (
    acknowledge_message_api,
    archive_message_api,
    get_message_templates,
    get_messages,
    get_unread_message_count,
    send_message_api,
    send_quick_reply_api,
)
from ui_components import badge, empty_state, section_header

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


def _priority_badge(priority: str):
    value = str(priority).strip().lower()
    if value == "critical":
        badge("Critical", "#ef4444")
    elif value == "high":
        badge("High", "#f59e0b")
    else:
        badge("Normal", "#2563eb")


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


def _reply_block(msg: dict):
    reply = _clean_text(msg.get("reply", ""))
    reply_by = _clean_text(msg.get("reply_by", ""))
    reply_timestamp = _clean_text(msg.get("reply_timestamp", ""))

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
    section_header("💬 Admin Messaging Hub", "Send quick operational messages to hospital staff.")
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

    st.markdown("### Quick Message Shortcuts")
    if not templates:
        empty_state("No quick templates available.")
    else:
        for idx, template in enumerate(templates):
            title = template.get("title", "Untitled Template")
            message = template.get("message", "")
            category = template.get("category", "general")

            st.markdown(f"**{title}**")
            _priority_badge(template.get("priority", selected_priority))
            st.write(message)
            st.caption(
                f"Category: {category} | Default Role: {template.get('target_role', 'all')} | "
                f"Default Department: {template.get('target_department', 'All Departments')}"
            )

            if st.button(f"Send Template {idx + 1}", key=f"send_template_{idx}"):
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

            st.markdown("---")

    st.markdown("### Send Custom Message")
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

    st.markdown("### Active Sent Messages")
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
        for i, msg in enumerate(sent_messages):
            message_id = msg.get("message_id", "")

            st.markdown(f"**{msg.get('title', 'Untitled')}**")
            _priority_badge(msg.get("priority", "normal"))
            st.write(msg.get("message", ""))
            st.caption(
                f"Target Role: {msg.get('target_role', 'all')} | "
                f"Target Department: {msg.get('target_department', 'All Departments')} | "
                f"Status: {msg.get('status', '')} | Time: {msg.get('timestamp', '')}"
            )

            _reply_block(msg)

            c1, c2 = st.columns(2)
            with c1:
                _render_ack_button(message_id, bool(msg.get("is_read", False)), f"admin_sent_{message_id}")
            with c2:
                _render_archive_button(message_id, f"admin_sent_{message_id}")

            if i < len(sent_messages) - 1:
                st.markdown("---")

    st.markdown("### Archived Sent Messages")
    archived_messages = _safe_messages_response(
        sender_name=sender_name,
        include_archived=True,
        limit=50,
    )["messages"]

    if not archived_messages:
        empty_state("No archived sent messages.")
    else:
        for i, msg in enumerate(archived_messages):
            st.markdown(f"**{msg.get('title', 'Untitled')}**")
            _priority_badge(msg.get("priority", "normal"))
            st.write(msg.get("message", ""))
            _reply_block(msg)
            st.caption(
                f"[Archived] Target Role: {msg.get('target_role', 'all')} | "
                f"Target Department: {msg.get('target_department', 'All Departments')} | "
                f"Time: {msg.get('timestamp', '')}"
            )
            if i < len(archived_messages) - 1:
                st.markdown("---")


def show_staff_message_center(user_name: str, role: str, department: str):
    section_header("💬 Staff Message Center", "Respond quickly to admin alerts and operational messages.")

    st.markdown("### Send Message to Admin")
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
            st.caption(f"Unread for you: {int(unread_meta.get('unread_count') or 0)}")

        if not messages:
            empty_state("No messages available.")
        else:
            for idx, msg in enumerate(messages):
                message_id = msg.get("message_id", "")

                st.markdown(f"### {msg.get('title', 'Untitled Message')}")
                _priority_badge(msg.get("priority", "normal"))
                st.write(msg.get("message", ""))
                st.caption(
                    f"From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | "
                    f"Time: {msg.get('timestamp', '')}"
                )

                reply_value = _clean_text(msg.get("reply", ""))
                is_read = bool(msg.get("is_read", False))

                if reply_value:
                    _reply_block(msg)
                else:
                    st.markdown("#### Quick Replies")
                    if quick_replies:
                        cols = st.columns(4)
                        for q_idx, reply in enumerate(quick_replies):
                            with cols[q_idx % 4]:
                                if st.button(reply, key=f"quick_reply_{message_id}_{q_idx}"):
                                    result = send_quick_reply_api(
                                        message_id=message_id,
                                        reply_text=reply,
                                        replied_by=user_name,
                                    )
                                    if result and result.get("status") == "updated":
                                        st.success("Reply sent successfully.")
                                        st.rerun()
                                    else:
                                        st.error("Failed to send reply.")

                    custom_reply = st.text_input("Custom Reply", key=f"custom_reply_input_{message_id}")
                    if st.button("Send Custom Reply", key=f"send_custom_reply_{message_id}"):
                        if not custom_reply.strip():
                            st.warning("Please enter a reply first.")
                        else:
                            result = send_quick_reply_api(
                                message_id=message_id,
                                reply_text=custom_reply.strip(),
                                replied_by=user_name,
                            )
                            if result and result.get("status") == "updated":
                                st.success("Custom reply sent successfully.")
                                st.rerun()
                            else:
                                st.error("Failed to send reply.")

                c1, c2 = st.columns(2)
                with c1:
                    _render_ack_button(message_id, is_read, f"staff_{message_id}")
                with c2:
                    _render_archive_button(message_id, f"staff_{message_id}")

                if idx < len(messages) - 1:
                    st.markdown("---")

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
            for idx, msg in enumerate(archived_messages):
                st.markdown(f"### {msg.get('title', 'Untitled Message')}")
                _priority_badge(msg.get("priority", "normal"))
                st.write(msg.get("message", ""))
                _reply_block(msg)
                st.caption(
                    f"[Archived] From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | "
                    f"Time: {msg.get('timestamp', '')}"
                )

                if idx < len(archived_messages) - 1:
                    st.markdown("---")


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