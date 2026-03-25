from datetime import datetime

import streamlit as st

import os

from api_client import api_base_url, login_user_api
from approval_sections import show_admin_approval_panel
from audit_sections import show_audit_summary, show_audit_table, show_execution_trace
from dashboard_sections import (
    get_live_context,
    show_department_status,
    show_digital_twin,
    show_evaluation_panel,
    show_explainability_panel,
    show_forecast,
    show_operations_center,
    show_optimization,
    show_overview,
    show_simulation,
)
from message_center_sections import show_message_center
from notification_sections import show_notifications_panel
from staff_sections import (
    show_admin_appointments_overview,
    show_all_shifts,
    show_appointments,
    show_my_shifts,
    show_or_bookings,
)
from ui_components import inject_base_styles, page_header, scoped_key, sidebar_status_card
from api_client import get_unread_notification_count

st.set_page_config(page_title="HRO Command Center", layout="wide")
inject_base_styles()

if "user" not in st.session_state:
    st.session_state.user = None

if "token" not in st.session_state:
    st.session_state.token = ""


def login_view():
    page_header(
        "HRO‑PS Command Center",
        "Premium hospital operations intelligence — forecasting, optimization, alerts, approvals.",
        meta_right=f"API: {api_base_url()}",
    )

    left, right = st.columns([1.05, 1])
    with left:
        st.markdown(
            """
            <div class="hro-surface" style="padding:18px;">
              <div style="font-size:1.05rem; font-weight:800; margin-bottom:6px;">Sign in</div>
              <div style="color:#5B667A; margin-bottom:14px;">Use your hospital account to access your role-based workspace.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # SaaS: select tenant (optional; defaults to DEFAULT_TENANT_SLUG)
        tenant_slug = st.text_input(
            "Tenant (slug)",
            value=os.getenv("DEFAULT_TENANT_SLUG", "demo-hospital"),
            key=scoped_key("login", "tenant_slug"),
        )
        username = st.text_input("Username", key=scoped_key("login", "username"))
        password = st.text_input("Password", type="password", key=scoped_key("login", "password"))

        login_clicked = st.button("Login", type="primary", key=scoped_key("login", "submit"))
    with right:
        st.markdown(
            """
            <div class="hro-surface" style="padding:18px;">
              <div style="font-size:1.05rem; font-weight:800; margin-bottom:10px;">What you can do</div>
              <ul style="margin: 0 0 0 18px; color:#0B1220; opacity:0.92; line-height: 1.75;">
                <li>Forecast patient demand and detect pressure early</li>
                <li>Optimize beds, staffing, and department allocations</li>
                <li>Manage alerts, notifications, and operational messaging</li>
                <li>Approve recommendations with full audit visibility</li>
              </ul>
              <div style="margin-top:14px; color:#5B667A; font-size:0.92rem;">Tip: start with <b>Command Center</b> for a full system snapshot.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if login_clicked:
        # NOTE: login_user_api currently only accepts (username, password);
        # for tenant-aware login we pass tenant_slug through env for now.
        if tenant_slug.strip():
            os.environ["TENANT_SLUG"] = tenant_slug.strip()

        user = login_user_api(username.strip(), password.strip()) if username.strip() and password.strip() else None
        if user and isinstance(user, dict) and user.get("access_token") and user.get("user"):
            st.session_state.user = user["user"]
            st.session_state.token = user["access_token"]
            # Pass token to the API client via env so existing helper functions work.
            os.environ["API_TOKEN"] = st.session_state.token
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")


def show_header(user):
    page_header(
        "HRO‑PS Command Center",
        f"{user.get('name','-')} • {user.get('role','-').title()} • {user.get('department','-')}",
        meta_right=datetime.now().strftime("%a %d %b • %H:%M"),
    )


def sidebar_navigation(role):
    st.sidebar.markdown("### Navigation")

    if role == "admin":
        pages = [
            "Command Center",
            "Forecast",
            "Optimization",
            "Operations Center",
            "Shifts",
            "Appointments",
            "OR Bookings",
            "Notifications",
            "Messages",
            "Approvals",
            "Evaluation",
            "Explainability",
            "Audit",
        ]
    elif role == "doctor":
        pages = [
            "Overview",
            "Forecast",
            "My Shifts",
            "Appointments",
            "OR Bookings",
            "Notifications",
            "Messages",
        ]
    else:
        pages = [
            "Overview",
            "My Shifts",
            "Appointments",
            "Department",
            "Notifications",
            "Messages",
        ]

    # Streamlit warns on empty labels even if collapsed.
    return st.sidebar.radio(
        "Navigation",
        pages,
        label_visibility="collapsed",
        key=scoped_key("sidebar", "navigation", role),
    )


@st.cache_data(ttl=20, show_spinner=False)
def _cached_live_context():
    return get_live_context()


def show_sidebar_context(user):
    ctx = _cached_live_context()

    sidebar_status_card(
        "User Session",
        [
            f"<b>Name:</b> {user.get('name', '-')}",
            f"<b>Role:</b> {user.get('role', '-')}",
            f"<b>Department:</b> {user.get('department', '-')}",
        ],
    )

    # Notification counter (in-app notifications)
    try:
        notif_meta = get_unread_notification_count() or {}
        notif_unread = int(notif_meta.get("unread_count") or 0)
    except Exception:
        notif_unread = 0

    sidebar_status_card(
        "Notifications",
        [f"Unread notifications: <b>{notif_unread}</b>"],
    )

    if ctx.get("ready"):
        result = ctx["prediction_result"]
        sidebar_status_card(
            "Live Summary",
            [
                f"Current Patients: <b>{ctx['current_patients']}</b>",
                f"Next Hour Forecast: <b>{int(ctx['prediction'])}</b>",
                f"Peak Load: <b>{int(ctx['peak'])}</b>",
                f"Emergency: <b>{result.get('emergency_level', 'LOW')}</b>",
            ],
        )
    else:
        sidebar_status_card("System Status", [ctx.get("reason", "Context unavailable")])

    if st.sidebar.button("Logout", key=scoped_key("sidebar", "logout")):
        st.session_state.user = None
        st.session_state.token = ""
        if "API_TOKEN" in os.environ:
            os.environ.pop("API_TOKEN", None)
        if "TENANT_SLUG" in os.environ:
            os.environ.pop("TENANT_SLUG", None)
        st.rerun()


def main_app():
    user = st.session_state.user
    role = str(user["role"]).lower()

    show_header(user)
    show_sidebar_context(user)
    page = sidebar_navigation(role)

    if role == "admin":
        if page == "Command Center":
            show_overview()

        elif page == "Forecast":
            show_forecast()

        elif page == "Optimization":
            show_optimization()

        elif page == "Operations Center":
            st.markdown("## ⚙️ Operations Center")
            tab_ops, tab_sim, tab_twin, tab_dept = st.tabs(
                ["Operations", "Simulation", "Digital Twin", "Department Status"]
            )
            with tab_ops:
                show_operations_center()
            with tab_sim:
                show_simulation()
            with tab_twin:
                show_digital_twin()
            with tab_dept:
                show_department_status()

        elif page == "Shifts":
            show_all_shifts()

        elif page == "Appointments":
            show_admin_appointments_overview()

        elif page == "OR Bookings":
            show_or_bookings("admin")

        elif page == "Notifications":
            show_notifications_panel(user)

        elif page == "Messages":
            show_message_center(user)

        elif page == "Approvals":
            ctx = _cached_live_context()
            if not ctx["ready"]:
                st.error(ctx["reason"])
            else:
                result = ctx["prediction_result"]
                show_admin_approval_panel(
                    peak=int(ctx["peak"]),
                    beds_needed=int(result["recommended_resources"]["beds_needed"]),
                    doctors_needed=int(result["recommended_resources"]["doctors_needed"]),
                    emergency_level=result.get("emergency_level", "LOW"),
                    approver_name=user.get("name", "Admin"),
                )

        elif page == "Evaluation":
            show_evaluation_panel()

        elif page == "Explainability":
            show_explainability_panel()

        elif page == "Audit":
            show_audit_summary()
            st.markdown("---")
            show_audit_table()
            st.markdown("---")
            show_execution_trace()

    elif role == "doctor":
        if page == "Overview":
            show_overview()

        elif page == "Forecast":
            show_forecast()

        elif page == "My Shifts":
            show_my_shifts(user["username"], "doctor")

        elif page == "Appointments":
            show_appointments("doctor", doctor_name=user.get("name"))

        elif page == "OR Bookings":
            show_or_bookings("doctor", doctor_name=user.get("name"))

        elif page == "Notifications":
            show_notifications_panel(user)

        elif page == "Messages":
            show_message_center(user)

    else:
        if page == "Overview":
            show_overview()

        elif page == "My Shifts":
            show_my_shifts(user["username"], "nurse")

        elif page == "Appointments":
            show_appointments("nurse", department=user.get("department"))

        elif page == "Department":
            show_department_status()

        elif page == "Notifications":
            show_notifications_panel(user)

        elif page == "Messages":
            show_message_center(user)


if st.session_state.user is None:
    login_view()
else:
    main_app()
