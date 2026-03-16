import pandas as pd
import streamlit as st

from api_client import (
    get_message_templates,
    get_messages,
    send_message_api,
    reply_to_message_api,
)


def _render_priority_badge(priority: str):
    priority = str(priority).lower()

    if priority == "critical":
        st.error("🚨 Critical")
    elif priority == "high":
        st.warning("⚠️ High")
    else:
        st.info("ℹ️ Normal")


def show_admin_message_center(sender_name, sender_role="admin"):
    st.markdown("## 💬 Admin Quick Messages Center")

    templates_data = get_message_templates()

    if templates_data is None:
        st.warning("Message template service unavailable.")
        return

    templates = templates_data.get("admin_templates", [])

    st.write("### Quick Message Shortcuts")

    if not templates:
        st.info("No admin templates available.")
    else:
        for idx, template in enumerate(templates):
            with st.container():
                c1, c2 = st.columns([4, 1])

                with c1:
                    st.markdown(f"**{template['title']}**")
                    st.caption(
                        f"Category: {template['category']} | "
                        f"Target Role: {template['target_role']} | "
                        f"Target Department: {template['target_department']}"
                    )
                    st.write(template["message"])

                with c2:
                    if st.button(
                        f"Send {idx + 1}",
                        key=f"admin_template_send_{idx}"
                    ):
                        result = send_message_api(
                            sender_role=sender_role,
                            sender_name=sender_name,
                            title=template["title"],
                            message=template["message"],
                            target_role=template["target_role"],
                            target_department=template["target_department"],
                            priority=template["priority"],
                            category=template["category"],
                        )
                        if result:
                            st.success("Message sent successfully.")
                            st.rerun()
                        else:
                            st.error("Failed to send message.")

                st.markdown("---")

    st.write("### Custom Broadcast Message")

    with st.form("custom_admin_message_form"):
        title = st.text_input("Message Title")
        message = st.text_area("Message Content")
        target_role = st.selectbox(
            "Target Role",
            ["all", "doctor", "nurse"]
        )
        target_department = st.selectbox(
            "Target Department",
            ["All Departments", "ER", "ICU", "General Ward", "Surgery", "Radiology"]
        )
        priority = st.selectbox(
            "Priority",
            ["normal", "high", "critical"]
        )
        category = st.selectbox(
            "Category",
            ["general", "emergency", "coverage", "shift", "capacity"]
        )

        submitted = st.form_submit_button("Send Custom Message")

        if submitted:
            if not title.strip() or not message.strip():
                st.error("Title and message are required.")
            else:
                result = send_message_api(
                    sender_role=sender_role,
                    sender_name=sender_name,
                    title=title.strip(),
                    message=message.strip(),
                    target_role=target_role,
                    target_department=target_department,
                    priority=priority,
                    category=category,
                )
                if result:
                    st.success("Custom message sent successfully.")
                    st.rerun()
                else:
                    st.error("Failed to send custom message.")

    st.markdown("---")
    st.write("### Recent Sent Messages")

    sent_messages = get_messages(limit=30)
    sent_messages = [
        msg for msg in sent_messages
        if str(msg.get("sender_role", "")).lower() == "admin"
    ]

    if not sent_messages:
        st.info("No messages have been sent yet.")
        return

    for msg in sent_messages:
        with st.container():
            st.markdown(f"**{msg.get('title', '-') }**")
            st.write(msg.get("message", ""))

            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption(f"To Role: {msg.get('target_role', '-')}")
            with c2:
                st.caption(f"To Department: {msg.get('target_department', '-')}")
            with c3:
                st.caption(f"Time: {msg.get('timestamp', '-')}")

            if str(msg.get("reply", "")).strip():
                st.success(
                    f"Reply from {msg.get('reply_by', '-')} "
                    f"at {msg.get('reply_timestamp', '-')}: {msg.get('reply', '')}"
                )

            st.markdown("---")


def show_staff_message_center(user_name, user_role, department):
    st.markdown("## 💬 Staff Message Inbox & Quick Replies")

    templates_data = get_message_templates()
    quick_replies = []
    if templates_data is not None:
        quick_replies = templates_data.get("staff_quick_replies", [])

    inbox_messages = get_messages(
        role=user_role,
        department=department,
        limit=50
    )

    if not inbox_messages:
        st.info("No messages available in your inbox.")
        return

    for idx, msg in enumerate(inbox_messages):
        with st.container():
            st.markdown(f"**{msg.get('title', '-') }**")
            _render_priority_badge(msg.get("priority", "normal"))
            st.write(msg.get("message", ""))

            st.caption(
                f"From: {msg.get('sender_name', '-')} "
                f"({msg.get('sender_role', '-')}) | "
                f"Time: {msg.get('timestamp', '-')}"
            )

            if str(msg.get("reply", "")).strip():
                st.success(
                    f"Your latest reply status: {msg.get('reply', '')} "
                    f"| By: {msg.get('reply_by', '-')}"
                )

            st.write("#### Quick Replies")
            if quick_replies:
                cols = st.columns(4)
                for q_idx, reply_text in enumerate(quick_replies):
                    with cols[q_idx % 4]:
                        if st.button(
                            reply_text,
                            key=f"quick_reply_{idx}_{q_idx}_{msg.get('message_id', '')}"
                        ):
                            result = reply_to_message_api(
                                message_id=msg["message_id"],
                                reply=reply_text,
                                reply_by=user_name,
                            )
                            if result:
                                st.success("Reply sent.")
                                st.rerun()
                            else:
                                st.error("Failed to send reply.")

            custom_reply = st.text_input(
                "Custom Reply",
                key=f"custom_reply_input_{msg.get('message_id', idx)}"
            )

            if st.button(
                "Send Custom Reply",
                key=f"custom_reply_btn_{msg.get('message_id', idx)}"
            ):
                if not custom_reply.strip():
                    st.error("Reply cannot be empty.")
                else:
                    result = reply_to_message_api(
                        message_id=msg["message_id"],
                        reply=custom_reply.strip(),
                        reply_by=user_name,
                    )
                    if result:
                        st.success("Custom reply sent.")
                        st.rerun()
                    else:
                        st.error("Failed to send custom reply.")

            st.markdown("---")