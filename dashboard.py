from datetime import datetime

import os
import re

import streamlit as st
import streamlit.components.v1 as components

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
from home_section import show_home
from message_center_sections import show_message_center
from notification_sections import show_notifications_panel
from staff_sections import (
    show_admin_appointments_overview,
    show_all_shifts,
    show_appointments,
    show_my_shifts,
    show_or_bookings,
)
from ui_components import (
    UI_BUILD_ID,
    get_theme_mode,
    inject_base_styles,
    page_header,
    scoped_key,
    set_theme_mode,
    sidebar_status_card,
)
st.set_page_config(page_title="HRO Command Center", layout="wide")


@st.cache_data(ttl=30, show_spinner=False)
def _cached_notif_count():
    from api_client import get_unread_notification_count
    return get_unread_notification_count()


def _inject_runtime_js(page: str) -> None:
    """Single consolidated per-rerun JS injector (ONE iframe instead of three).

    Replaces the old `_sync_theme_local_storage` + `_inject_dynamic_import_recovery`
    + `inject_page_context` trio. Each `components.html` is a real DOM iframe on
    every navigation, so collapsing three into one is a measurable per-rerun win.

    Responsibilities (all idempotent, no full-page reload on theme toggle):
      - set `data-hro-page` + `data-hro-theme` on <html> from the AUTHORITATIVE
        Python theme (never disagrees with the injected CSS variables)
      - mirror the theme into localStorage (best-effort persistence)
      - install the stale-chunk import-recovery listener ONCE per browser session
    """

    theme = "dark" if get_theme_mode() == "dark" else "light"
    safe = str(page or "").strip().lower()
    safe = re.sub(r"[^a-z0-9\-\s]", "", safe)
    safe = re.sub(r"\s+", "-", safe).strip("-")
    if safe in {"command-center", "overview", "operations-center"}:
        safe = "command-center"
    if not safe:
        safe = "unknown"

    components.html(
        f"""
        <script>
        (function() {{
          var root;
          try {{ root = window.parent || window; }} catch (e) {{ root = window; }}
          try {{
            var html = root.document.documentElement;
            html.setAttribute('data-hro-page', '{safe}');
            html.setAttribute('data-hro-theme', '{theme}');
            try {{ root.localStorage.setItem('hro_theme', '{theme}'); }} catch (e) {{}}
          }} catch (e) {{}}

          // Stale-chunk recovery — install listeners only once per session.
          try {{
            if (!root.__hro_recovery_installed) {{
              root.__hro_recovery_installed = true;
              var KEY = 'hro_import_recovery_attempted';
              function shouldRecover(msg) {{
                if (!msg) return false;
                var t = String(msg);
                return t.includes('Failed to fetch dynamically imported module')
                    || t.includes('Importing a module script failed');
              }}
              function recoverOnce() {{
                if (root.sessionStorage.getItem(KEY) === '1') return;
                root.sessionStorage.setItem(KEY, '1');
                var url = new URL(root.location.href);
                url.searchParams.set('_cb', String(Date.now()));
                root.location.replace(url.toString());
              }}
              root.addEventListener('error', function(e) {{
                if (shouldRecover(e && e.message)) recoverOnce();
              }}, true);
              root.addEventListener('unhandledrejection', function(e) {{
                var reason = e && e.reason;
                var msg = (reason && (reason.message || (reason.toString && reason.toString()))) || '';
                if (shouldRecover(msg)) recoverOnce();
              }});
            }}
          }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
    )


inject_base_styles()

if "user" not in st.session_state:
    st.session_state.user = None

if "token" not in st.session_state:
    st.session_state.token = ""


def login_view():
    _inject_runtime_js("login")
    page_header(
        "HRO‑PS Command Center",
        "Premium hospital operations intelligence — forecasting, optimization, alerts, approvals.",
        meta_right=f"UI: {UI_BUILD_ID} • API: {api_base_url()}",
    )

    left, right = st.columns([1.05, 1])
    with left:
        st.markdown(
            """
            <div class="hro-surface" style="padding:18px;">
              <div style="font-size:1.05rem; font-weight:800; margin-bottom:6px;">Sign in</div>
              <div style="color:var(--text-2); margin-bottom:14px;">Use your hospital account to access your role-based workspace.</div>
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
              <ul style="margin: 0 0 0 18px; color:var(--text); opacity:0.92; line-height: 1.75;">
                <li>Forecast patient demand and detect pressure early</li>
                <li>Optimize beds, staffing, and department allocations</li>
                <li>Manage alerts, notifications, and operational messaging</li>
                <li>Approve recommendations with full audit visibility</li>
              </ul>
              <div style="margin-top:14px; color:var(--text-2); font-size:0.92rem;">
                Tip: start with <b>Command Center</b> for a full system snapshot.
              </div>
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
    # System identity header (story-driven). Theme toggle lives top-right.
    with st.container(border=True):
        left, right = st.columns([0.78, 0.22], vertical_alignment="bottom")
        with left:
            st.markdown(
                """
                <div style="font-size:1.35rem; font-weight:820; letter-spacing:-0.02em;">Hospital Resource Optimization</div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                f"Decision dashboard • {user.get('name','-')} • {str(user.get('role','-')).title()} • {user.get('department','-')}"
            )
        with right:
            current_mode = get_theme_mode()
            # Visible build/version indicator so we can verify the right UI is deployed.
            st.markdown(
                f"<div style='display:flex; justify-content:flex-end; margin-bottom:8px;'><span class='hro-badge hro-badge-info'>UI {UI_BUILD_ID}</span></div>",
                unsafe_allow_html=True,
            )
            want_dark = st.toggle(
                "Dark mode",
                value=(current_mode == "dark"),
                help="Light/Dark theme (saved in localStorage).",
                key=scoped_key("header", "theme_toggle"),
            )
            desired_mode = "dark" if want_dark else "light"
            if desired_mode != current_mode:
                # Instant theme switch: update Python state + one cheap rerun.
                # No query-param write and no JS location.replace (the old path
                # forced a full browser reload, which made toggling slow).
                set_theme_mode(desired_mode)
                st.rerun()
            st.caption(f"{datetime.now().strftime('%a %d %b • %H:%M')} • UI {UI_BUILD_ID}")


def sidebar_navigation(role):
    st.sidebar.markdown("### Navigation")

    if role == "admin":
        pages = [
            "Home",
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
            "Home",
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
            "Home",
            "Overview",
            "My Shifts",
            "Appointments",
            "Department",
            "Notifications",
            "Messages",
        ]

    # Consume a navigation request from the Home launchpad. Set BEFORE the radio
    # widget is created (safe), so on_click callbacks on Home can drive the nav.
    nav_key = scoped_key("sidebar", "navigation", role)
    target = st.session_state.pop("nav_target", None)
    if target in pages:
        st.session_state[nav_key] = target

    # Streamlit warns on empty labels even if collapsed.
    return st.sidebar.radio(
        "Navigation",
        pages,
        label_visibility="collapsed",
        key=nav_key,
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

    # Notification counter — cached 30 s to avoid an API hit on every rerun.
    try:
        notif_meta = _cached_notif_count() or {}
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


_DEMO_SCRIPT_STEPS = [
    ("1 · Home", "Open with the Daily Ops Briefing: next-hour load, 72-h peak, capacity outlook — every number traceable to ForecastState."),
    ("2 · Forecast", "Three models compared. LSTM is best on test (RMSE 9.58); the deployed Hybrid 0.80/0.20 trades ~0.6 RMSE for robustness. Toggle the 80%/95% uncertainty band."),
    ("3 · Optimization", "MILP (scipy) allocates beds/doctors/nurses across 5 departments under hard constraints, in under 5 seconds. Note Needed vs Shortage columns."),
    ("4 · Digital Twin", "Probe any hour ahead; show the census projection and the time-to-saturation KPI (queueing simulation, labelled)."),
    ("5 · Simulation", "Run the Scenario Player: surge / mass-casualty / infeasible demand — synthetic stress on the real forecast, optimizer responds live."),
    ("6 · Approvals", "Human-in-the-loop: approve a recommendation, the RAG re-validation badge confirms, audit trail records it."),
    ("7 · Evaluation", "Canonical metrics table + Model Health (drift status). Close: 13 tabs, 48 endpoints, 21 tenant-scoped tables, every test green."),
]


def _render_guided_demo_sidebar(role: str) -> None:
    """Guided demo mode — the 7-step defense script as sidebar talking points."""

    if role != "admin":
        return
    with st.sidebar.expander("🎓 Guided demo (7 min)", expanded=False):
        for title, talking_point in _DEMO_SCRIPT_STEPS:
            st.markdown(f"**{title}** — {talking_point}")
        st.caption("Full script + Q&A: DEMO_RUNBOOK.md · DEFENSE_READINESS.md")


def main_app():
    user = st.session_state.user
    role = str(user["role"]).lower()

    show_header(user)
    show_sidebar_context(user)
    page = sidebar_navigation(role)
    _render_guided_demo_sidebar(role)

    # UI-only page scoping + theme attribute + import recovery, in one iframe.
    _inject_runtime_js(page)

    if role == "admin":
        if page == "Home":
            show_home(role)

        elif page == "Command Center":
            show_overview()

        elif page == "Forecast":
            show_forecast()

        elif page == "Optimization":
            show_optimization()

        elif page == "Operations Center":
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
        if page == "Home":
            show_home(role)

        elif page == "Overview":
            show_overview()

        elif page == "Forecast":
            show_forecast()

        elif page == "My Shifts":
            show_my_shifts(user["username"], "doctor")

        elif page == "Appointments":
            show_appointments("doctor", department=user.get("department"), doctor_name=user.get("name"))

        elif page == "OR Bookings":
            show_or_bookings("doctor", doctor_name=user.get("name"), department=user.get("department"))

        elif page == "Notifications":
            show_notifications_panel(user)

        elif page == "Messages":
            show_message_center(user)

    else:
        if page == "Home":
            show_home(role)

        elif page == "Overview":
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
