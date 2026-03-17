import streamlit as st

import time
from staff_sections import _load_shifts_df


# =========================
# KPI CARD
# =========================
def kpi_card(title, value, delta=None, status="normal"):
    color = {
        "normal": "#1f2937",
        "warning": "#f59e0b",
        "critical": "#ef4444"
    }.get(status, "#1f2937")

    st.markdown(f"""
    <div style="
        background-color:{color};
        padding:20px;
        border-radius:12px;
        color:white;
    ">
        <h4>{title}</h4>
        <h2>{value}</h2>
        <p>{delta if delta else ""}</p>
    </div>
    """, unsafe_allow_html=True)


# =========================
# SECTION HEADER
# =========================
def section_header(title):
    st.markdown(f"""
    <h2 style="margin-top:20px; margin-bottom:10px;">
        {title}
    </h2>
    """, unsafe_allow_html=True)


# =========================
# ALERT BOX
# =========================
def alert_box(message, level="info"):
    colors = {
        "info": "#3b82f6",
        "warning": "#f59e0b",
        "critical": "#ef4444"
    }

    st.markdown(f"""
    <div style="
        background-color:{colors[level]};
        padding:15px;
        border-radius:10px;
        color:white;
        margin-bottom:10px;
    ">
        {message}
    </div>
    """, unsafe_allow_html=True)

def show_my_shifts(user_name):
    st.markdown("## 🗓️ My Shifts")

    my_shifts = _load_shifts_df()
    my_shifts = my_shifts[my_shifts["assigned_to"] == user_name]
    if my_shifts.empty:
        st.info("No shifts assigned.")
        return
    st.dataframe(my_shifts[["shift_type", "department", "start_time", "end_time"]], use_container_width=True, hide_index=True)

def show_all_shifts():
    st.markdown("## 👥 All Staff Shifts")

    df = _load_shifts_df()

    if df.empty:
        st.info("No shifts available.")
        return

    keep_cols = [
        "assigned_to",
        "shift_type",
        "department",
        "start_time",
        "end_time",
    ]

    available_cols = [c for c in keep_cols if c in df.columns]
    df = df[available_cols].copy()

    st.dataframe(df, use_container_width=True, hide_index=True)

def show_or_bookings():
    st.markdown("## 🏥 Operating Room Bookings")

    df = _load_shifts_df()

    if df.empty:
        st.info("No OR bookings available.")
        return

    keep_cols = [
        "or_number",
        "procedure",
        "scheduled_time",
        "duration",
        "surgeon",
        "status"
    ]

    available_cols = [c for c in keep_cols if c in df.columns]
    df = df[available_cols].copy()

    st.dataframe(df, use_container_width=True, hide_index=True)

def show_appointment_bookings():
    st.markdown("## 📅 Appointment Bookings")

    df = _load_shifts_df()

    if df.empty:
        st.info("No appointment bookings available.")
        return

    keep_cols = [
        "appointment_id",
        "department",
        "doctor",
        "date",
        "time_slot",
        "patient_count",
        "status"
    ]

    available_cols = [c for c in keep_cols if c in df.columns]
    df = df[available_cols].copy()

    st.dataframe(df, use_container_width=True, hide_index=True)



# =========================
# SIDEBAR ITEM
# =========================
def sidebar_item(label, icon, selected=False):
    bg = "#1f2937" if selected else "transparent"

    st.markdown(f"""
    <div style="
        padding:10px;
        margin-bottom:5px;
        border-radius:8px;
        background:{bg};
        cursor:pointer;
    ">
        {icon} {label}
    </div>
    """, unsafe_allow_html=True)


# =========================
# BADGE
# =========================
def badge(text, color="red"):
    st.markdown(f"""
    <span style="
        background:{color};
        padding:3px 8px;
        border-radius:10px;
        color:white;
        font-size:12px;
    ">
        {text}
    </span>
    """, unsafe_allow_html=True)


# =========================
# MODERN TABLE
# =========================
def modern_table(df):
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

# =========================
# ALERT BOX
def alert_box(message, level="info"):
    colors = {
        "info": "#3b82f6",
        "warning": "#f59e0b",
        "critical": "#ef4444"
    }

    st.markdown(f"""
    <div style="
        background-color:{colors[level]};
        padding:15px;
        border-radius:10px;
        color:white;
        margin-bottom:10px;
    ">
        {message}
    </div>
    """, unsafe_allow_html=True)

def show_notifications_panel(user):
    st.markdown("## 🔔 Alerts")

    alerts = [
        {"msg": "ICU overload", "level": "critical"},
        {"msg": "Doctor shortage", "level": "warning"}
    ]

    for a in alerts:
        alert_box(a["msg"], a["level"]) 
def highlight_rows(df):
    return df.style.applymap(
        lambda v: "background-color: red" if "critical" in str(v).lower() else ""
    )

def _load_shifts_df():
    from database import SessionLocal
    from models import StaffShift

    db = SessionLocal()
    try:
        rows = db.query(StaffShift).all()
        data = [
            {
                "staff_username": r.staff_username,
                "shift_type": r.shift_type,
                "department": r.department,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "or_number": r.or_number,   }]
        



# =========================
# LOADING SPINNER
# =========================
def loading(message="Loading..."):
    with st.spinner(message):
        time.sleep(1)


# =========================
# SUCCESS TOAST
# =========================
def success_toast(msg):
    st.markdown(f"""
    <div style="
        background:#10b981;
        padding:10px;
        border-radius:8px;
        color:white;
        margin-bottom:10px;
    ">
        ✅ {msg}
    </div>
    """, unsafe_allow_html=True)


# =========================
# ERROR TOAST
# =========================
def error_toast(msg):
    st.markdown(f"""
    <div style="
        background:#ef4444;
        padding:10px;
        border-radius:8px;
        color:white;
        margin-bottom:10px;
    ">
        ❌ {msg}
    </div>
    """, unsafe_allow_html=True)


# =========================
# EMPTY STATE
# =========================
def empty_state(message="No data available"):
    st.markdown(f"""
    <div style="
        text-align:center;
        padding:40px;
        color:#9ca3af;
    ">
        <h3>📭</h3>
        <p>{message}</p>
    </div>
    """, unsafe_allow_html=True)


# =========================
# SKELETON LOADER
# =========================
def skeleton():
    st.markdown("""
    <div style="
        background:#1f2937;
        height:100px;
        border-radius:10px;
        margin-bottom:10px;
        animation:pulse 1.5s infinite;
    "></div>

    <style>
    @keyframes pulse {
        0% {opacity:0.5;}
        50% {opacity:1;}
        100% {opacity:0.5;}
    }
    </style>
    """, unsafe_allow_html=True)

def load_audit_log():
    from database import SessionLocal
    from models import AuditLog

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).all()

        EXPECTED_COLS = [
            "timestamp",
            "user",
            "action",
            "target",
            "status",
            "details",
        ]

        data = [
            {
                "timestamp": str(row.timestamp or "").strip(),
                "user": str(row.user or "").strip(),
                "action": str(row.action or "").strip(),
                "target": str(row.target or "").strip(),
                "status": str(row.status or "").strip(),
                "details": str(row.details or "").strip(),
            }
            for row in rows
        ]
        return pd.DataFrame(data, columns=EXPECTED_COLS)
    finally:        db.close()

def animated_kpi(title, value):
    st.markdown(f"""
    <div style="
        background:#111827;
        padding:20px;
        border-radius:12px;
        color:white;
        transition:0.3s;
    ">
        <h4>{title}</h4>
        <h2>{value}</h2>
    </div>
    """, unsafe_allow_html=True)

def _normalize(val):
    if val is None:
        return ""
    return str(val).strip()

def _safe_int(val, default=0):
    try:
        if val is None:
            return default
        return int(val)
    except Exception:
        return default
    
def modern_table(df):
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

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

try:
    result = run_model()
except Exception as e:
    error_toast("Model failed to run")