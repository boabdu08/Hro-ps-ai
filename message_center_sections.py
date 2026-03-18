import streamlit as st

from api_client import get_message_templates, get_messages, send_message_api, send_quick_reply_api
from ui_components import badge, empty_state, section_header

TARGET_ROLE_OPTIONS = ["doctor", "nurse", "all"]
TARGET_DEPARTMENT_OPTIONS = ["All Departments", "ER", "ICU", "General Ward", "Surgery", "Radiology"]
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


def _safe_messages_response(role=None, department=None, limit=50, unread_only=False):
    response = get_messages(role=role, department=department, limit=limit, unread_only=unread_only) or {}
    return {
        "messages": response.get("messages", []),
        "quick_replies": response.get("quick_replies", []),
    }


def _reply_block(msg: dict):
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


def show_admin_message_center(sender_name: str, sender_role: str):
    section_header("💬 Admin Messaging Hub", "Send quick operational messages to hospital staff.")
    data = _safe_templates_response()
    templates = data["admin_templates"]

    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        selected_target_role = st.selectbox("Target Role", TARGET_ROLE_OPTIONS, index=2, key="admin_target_role")
    with top_col2:
        selected_target_department = st.selectbox(
            "Target Department",
            TARGET_DEPARTMENT_OPTIONS,
            index=0,
            key="admin_target_department",
        )
    with top_col3:
        selected_priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=1, key="admin_message_priority")

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
    custom_type = st.selectbox("Message Type", ["custom", "emergency", "coverage", "shift", "capacity"], key="admin_custom_type")
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

    st.markdown("### Recently Sent Messages")
    sent_messages = _safe_messages_response(limit=20)["messages"]
    if not sent_messages:
        empty_state("No sent messages yet.")
        return

    for i, msg in enumerate(sent_messages):
        st.markdown(f"**{msg.get('title', 'Untitled')}**")
        _priority_badge(msg.get("priority", "normal"))
        st.write(msg.get("message", ""))
        st.caption(
            f"Target Role: {msg.get('target_role', 'all')} | "
            f"Target Department: {msg.get('target_department', 'All Departments')} | "
            f"Status: {msg.get('status', '')} | Time: {msg.get('timestamp', '')}"
        )
        _reply_block(msg)
        if i < len(sent_messages) - 1:
            st.markdown("---")


def show_staff_message_center(user_name: str, role: str, department: str):
    section_header("💬 Staff Message Center", "Respond quickly to admin alerts and operational messages.")
    data = _safe_messages_response(role=role, department=department, limit=50)
    messages = data["messages"]
    quick_replies = data["quick_replies"]

    if not messages:
        empty_state("No messages available.")
        return

    for idx, msg in enumerate(messages):
        message_id = msg.get("message_id", "")
        st.markdown(f"### {msg.get('title', 'Untitled Message')}")
        _priority_badge(msg.get("priority", "normal"))
        st.write(msg.get("message", ""))
        st.caption(f"From: {msg.get('sender_name', '')} ({msg.get('sender_role', '')}) | Time: {msg.get('timestamp', '')}")

        reply_value = str(msg.get("reply", "")).strip()
        if reply_value:
            _reply_block(msg)
        else:
            st.markdown("#### Quick Replies")
            if quick_replies:
                cols = st.columns(4)
                for q_idx, reply in enumerate(quick_replies):
                    with cols[q_idx % 4]:
                        if st.button(reply, key=f"quick_reply_{message_id}_{q_idx}"):
                            result = send_quick_reply_api(message_id=message_id, reply_text=reply, replied_by=user_name)
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
                    result = send_quick_reply_api(message_id=message_id, reply_text=custom_reply.strip(), replied_by=user_name)
                    if result and result.get("status") == "updated":
                        st.success("Custom reply sent successfully.")
                        st.rerun()
                    else:
                        st.error("Failed to send reply.")

        if idx < len(messages) - 1:
            st.markdown("---")


def show_message_center(user: dict):
    role = str(user.get("role", "")).lower()
    if role == "admin":
        show_admin_message_center(sender_name=user.get("name", "Admin"), sender_role=role)
    else:
        show_staff_message_center(
            user_name=user.get("name", "Unknown User"),
            role=role,
            department=user.get("department", "All Departments"),
        )

