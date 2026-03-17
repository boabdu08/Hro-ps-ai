import streamlit as st
from datetime import datetime

from api_client import login_user
from dashboard_sections import (
    show_overview,
    show_forecast,
    show_optimization,
    show_operations_center,
)
from staff_sections import (
    show_my_shifts,
    show_appointments,
    show_or_bookings,
)
from approval_sections import show_admin_approval_panel
from audit_sections import (
    show_audit_summary,
    show_audit_table,
    show_execution_trace,
)
from message_center_sections import show_message_center
from notification_sections import show_notifications_panel

st.markdown("""
<style>
body {
    background-color: #0f172a;
    color: white;
}
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="HRO Command Center", layout="wide")


# ==========================================
# LOGIN STATE
# ==========================================
if "user" not in st.session_state:
    st.session_state.user = None


def login_view():
    st.title("🏥 HRO — AI Hospital System")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(username, password)
        if user:
            st.session_state.user = user
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")


# ==========================================
# HEADER
# ==========================================
def show_header(user):
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("User", user["name"])
    col2.metric("Role", user["role"])
    col3.metric("Department", user.get("department", "-"))
    col4.metric("Time", datetime.now().strftime("%H:%M:%S"))

    st.markdown("---")
def show_header(user):
    st.markdown(f"""
    <div style="
        display:flex;
        justify-content:space-between;
        background:#111827;
        padding:15px;
        border-radius:10px;
        margin-bottom:20px;
    ">
        <div>👤 {user['name']} ({user['role']})</div>
        <div>🏥 HRO Command Center</div>
        <div>🕒 {datetime.now().strftime("%H:%M")}</div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# SIDEBAR NAV
# ==========================================
def sidebar_navigation(role):
    st.sidebar.title("🧭 Navigation")

    if role == "admin":
        return st.sidebar.radio(
            "Go to",
            [
                "Command Center",
                "Operations",
                "Optimization",
                "Approvals",
                "Messages",
                "Audit",
            ],
        )

    elif role == "doctor":
        return st.sidebar.radio(
            "Go to",
            [
                "Overview",
                "My Shifts",
                "Appointments",
                "OR Bookings",
                "Forecast",
                "Notifications",
            ],
        )

    elif role == "nurse":
        return st.sidebar.radio(
            "Go to",
            [
                "Overview",
                "My Shifts",
                "Appointments",
                "Department",
                "Notifications",
            ],
        )


# ==========================================
# MAIN APP
# ==========================================
def main_app():
    user = st.session_state.user
    role = user["role"]

    show_header(user)

    page = sidebar_navigation(role)

    # ================= ADMIN =================
    if role == "admin":
        if page == "Command Center":
            show_overview()
            show_kpi_cards({
                "patients": int(latest_prediction),
                "beds": int(optimization["summary"]["beds_needed_total"]),
                "doctors": int(optimization["summary"]["doctors_needed_total"]),
                "nurses": int(optimization["summary"]["nurses_needed_total"]),
})
        elif page == "Operations":
            show_operations_center()

        elif page == "Optimization":
            show_optimization()

        elif page == "Approvals":
            show_admin_approval_panel(
                peak=120,
                beds_needed=130,
                doctors_needed=15,
                emergency_level="HIGH",
                approver_name=user["name"],
            )

        elif page == "Messages":
            show_message_center(user)

        elif page == "Audit":
            show_audit_summary()
            show_audit_table()
            show_execution_trace()

    # ================= DOCTOR =================
    elif role == "doctor":
        if page == "Overview":
            show_overview()

        elif page == "My Shifts":
            show_my_shifts(user["username"], "doctor")

        elif page == "Appointments":
            show_appointments("doctor", doctor_name=user["name"])

        elif page == "OR Bookings":
            show_or_bookings("doctor", doctor_name=user["name"])

        elif page == "Forecast":
            show_forecast()

        elif page == "Notifications":
            show_notifications_panel(user)

    # ================= NURSE =================
    elif role == "nurse":
        if page == "Overview":
            show_overview()

        elif page == "My Shifts":
            show_my_shifts(user["username"], "nurse")

        elif page == "Appointments":
            show_appointments("nurse", department=user["department"])

        elif page == "Department":
            show_operations_center()

        elif page == "Notifications":
            show_notifications_panel(user)


# ==========================================
# RUN
# ==========================================
if st.session_state.user is None:
    login_view()
else:
    main_app()