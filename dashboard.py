from datetime import datetime

import os

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
    inject_page_context,
    page_header,
    scoped_key,
    set_theme_mode,
    sidebar_status_card,
)
from api_client import get_unread_notification_count

st.set_page_config(page_title="HRO Command Center", layout="wide")


def _get_query_param(name: str) -> str | None:
    """Best-effort getter for query params across Streamlit versions."""

    try:
        value = st.query_params.get(name)
        if isinstance(value, list):
            return value[0] if value else None
        return str(value) if value is not None else None
    except Exception:
        try:
            qp = st.experimental_get_query_params()
            value = qp.get(name)
            return value[0] if isinstance(value, list) and value else None
        except Exception:
            return None


def _set_query_params(**kwargs: str) -> None:
    """Best-effort setter for query params across Streamlit versions."""

    try:
        for k, v in kwargs.items():
            st.query_params[k] = v
    except Exception:
        try:
            st.experimental_set_query_params(**kwargs)
        except Exception:
            return


def _sync_theme_local_storage(theme: str) -> None:
    """Persist theme preference in localStorage.

    Streamlit doesn't expose localStorage to Python directly, but we can keep
    theme in sync via:
      - query param ?theme=
      - a tiny JS snippet that reads/writes localStorage and reloads once
    """

    safe_theme = "dark" if str(theme).lower() == "dark" else "light"
    components.html(
        f"""
        <script>
        (function() {{
          const root = (function() {{
            try {{ return window.parent || window; }} catch (e) {{ return window; }}
          }})();
          const key = 'hro_theme';
          const url = new URL(root.location.href);
          const urlTheme = url.searchParams.get('theme');
          const stored = root.localStorage.getItem(key);

          // If the URL doesn't have theme but localStorage does, promote it into the URL.
          if ((!urlTheme || urlTheme === '') && stored && (stored === 'light' || stored === 'dark')) {{
            url.searchParams.set('theme', stored);
            root.location.replace(url.toString());
            return;
          }}

          // Keep localStorage aligned with the app's chosen theme.
          root.localStorage.setItem(key, '{safe_theme}');
        }})();
        </script>
        """,
        height=0,
    )


def _inject_dynamic_import_recovery() -> None:
    """Mitigate stale Streamlit chunk cache issues.

    In some deployments (especially reverse proxies / CDNs / aggressive browser
    caches), Streamlit's lazily loaded JS chunks (/static/js/index.<hash>.js)
    can get out of sync with the base HTML.

    Symptom:
      TypeError: Failed to fetch dynamically imported module

    This recovery script:
      - listens for that specific error
      - performs a one-time cache-bust reload by adding/updating ?_cb=<ts>

    It is intentionally conservative (one reload max per page load).
    """

    components.html(
        """
        <script>
        (function() {
          try {
            const root = (function() {
              try { return window.parent || window; } catch (e) { return window; }
            })();

            const KEY = 'hro_import_recovery_attempted';
            const attempted = root.sessionStorage.getItem(KEY);

            function shouldRecover(msg) {
              if (!msg) return false;
              const t = String(msg);
              return (
                t.includes('Failed to fetch dynamically imported module') ||
                t.includes('Importing a module script failed')
              );
            }

            function recoverOnce() {
              if (attempted === '1') return;
              root.sessionStorage.setItem(KEY, '1');
              const url = new URL(root.location.href);
              url.searchParams.set('_cb', String(Date.now()));
              // Replace (not assign) so back button doesn't loop.
              root.location.replace(url.toString());
            }

            root.addEventListener('error', function(e) {
              // error.message is often the relevant string; for module errors it may be generic.
              if (shouldRecover(e && e.message)) recoverOnce();
            }, true);

            root.addEventListener('unhandledrejection', function(e) {
              const reason = e && e.reason;
              const msg = (reason && (reason.message || reason.toString && reason.toString())) || '';
              if (shouldRecover(msg)) recoverOnce();
            });
          } catch (err) {
            // Never break the app for recovery logic.
          }
        })();
        </script>
        """,
        height=0,
    )


def _init_theme_from_url() -> None:
    url_theme = (_get_query_param("theme") or "").strip().lower()
    if url_theme in {"light", "dark"}:
        set_theme_mode(url_theme)


_init_theme_from_url()
inject_base_styles()
_sync_theme_local_storage(get_theme_mode())
_inject_dynamic_import_recovery()

if "user" not in st.session_state:
    st.session_state.user = None

if "token" not in st.session_state:
    st.session_state.token = ""


def login_view():
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
                set_theme_mode(desired_mode)
                _set_query_params(theme=desired_mode)
                st.rerun()
            st.caption(f"{datetime.now().strftime('%a %d %b • %H:%M')} • UI {UI_BUILD_ID}")


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

    # UI-only page scoping so we can apply Command Center polish without
    # changing architecture, routing, or component hierarchy.
    inject_page_context(page)

    if role == "admin":
        if page == "Command Center":
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
