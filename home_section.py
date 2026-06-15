"""
Home tab — Hospital AI Command Center.

UI-only premium overview. Reads from:
  - get_live_context() (cached by sidebar, reused here; API with artifact fallback)
  - ForecastState artifacts (cached via dashboard_sections)
  - patient_flow_hourly_updated.csv (weekly congestion heatmap)
  - department_status_updated.csv (dept KPIs, pressure chart)
  - staff_master_data.csv (staff coverage chart)
  - appointments_updated.csv (workload chart)
  - or_bookings.csv (OR utilization chart)

No model training. No DB queries. No new API calls beyond sidebar cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard_sections import _cached_artifact_forecast_state, _cached_metrics_df
from ui_components import (
    empty_state,
    fmt_int,
    fmt_mae_rmse,
    fmt_mape,
    kpi_card,
    plotly_template_name,
    scoped_key,
    section_header,
)


# ---------------------------------------------------------------------------
# Home -> tab navigation (launchpad).
#
# Streamlit detail: we set st.session_state["nav_target"] in an on_click
# CALLBACK (callbacks run before widgets are instantiated next run), so the
# sidebar radio in dashboard.sidebar_navigation() can consume it without the
# "cannot be modified after the widget is instantiated" exception.
# ---------------------------------------------------------------------------

# Mirror of dashboard.sidebar_navigation page lists (used only to hide buttons
# that don't exist for the current role — keeps navigation honest).
_ROLE_PAGES = {
    "admin": {"Home", "Command Center", "Forecast", "Optimization", "Operations Center",
              "Shifts", "Appointments", "OR Bookings", "Notifications", "Messages",
              "Approvals", "Evaluation", "Explainability", "Audit"},
    "doctor": {"Home", "Overview", "Forecast", "My Shifts", "Appointments",
               "OR Bookings", "Notifications", "Messages"},
    "nurse": {"Home", "Overview", "My Shifts", "Appointments", "Department",
              "Notifications", "Messages"},
}


def _nav_to(target: str) -> None:
    st.session_state["nav_target"] = target


def _nav_button(label: str, target: str, role: str, key: str, *, type: str = "secondary") -> bool:
    """Render a button that navigates to `target` if the role has that page."""
    if target not in _ROLE_PAGES.get(role, set()):
        return False
    st.button(
        label,
        key=scoped_key("home", "nav", key, role),
        on_click=_nav_to,
        args=(target,),
        use_container_width=True,
        type=type,
    )
    return True


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PATIENT_FLOW_PATH = Path("data/updated_exports/patient_flow_hourly_updated.csv")
_DEPT_STATUS_PATH = Path("data/updated_exports/department_status_updated.csv")
_APPOINTMENTS_PATH = Path("data/updated_exports/appointments_updated.csv")
_OR_BOOKINGS_PATH = Path("data/updated_exports/or_bookings.csv")
_STAFF_MASTER_PATH = Path("data/updated_exports/staff_master_data.csv")

_DEPT_ORDER = ["ER", "ICU", "General Ward", "Surgery", "Radiology"]
_DAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}


# ---------------------------------------------------------------------------
# Cached data loaders — TTL matched to how often each source changes
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _home_heatmap_df() -> pd.DataFrame:
    """Weekly avg patient load by day-of-week × hour (TTL=1h, historical data)."""
    if not _PATIENT_FLOW_PATH.exists():
        return pd.DataFrame()
    try:
        cols = ["day_of_week", "hour", "patients"]
        df = pd.read_csv(_PATIENT_FLOW_PATH, usecols=cols)
        pivot = (
            df.groupby(["day_of_week", "hour"])["patients"]
            .mean()
            .unstack("hour")
        )
        pivot.index = [_DAY_NAMES.get(int(d), str(d)) for d in pivot.index]
        # Standard Mon→Sun order
        ordered = [d for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] if d in pivot.index]
        return pivot.loc[ordered].round(1)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _home_dept_status() -> pd.DataFrame:
    if not _DEPT_STATUS_PATH.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(_DEPT_STATUS_PATH)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _home_appointments() -> pd.DataFrame:
    if not _APPOINTMENTS_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(_APPOINTMENTS_PATH)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _home_or_bookings() -> pd.DataFrame:
    if not _OR_BOOKINGS_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(_OR_BOOKINGS_PATH)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _home_staff_master() -> pd.DataFrame:
    if not _STAFF_MASTER_PATH.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(_STAFF_MASTER_PATH)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Live KPI resolver: sidebar already called get_live_context() (cached TTL=30s).
# Calling it here reuses that cache — no extra API calls made.
# ---------------------------------------------------------------------------

def _resolve_live_kpis(fs) -> tuple[Optional[float], Optional[float], Optional[float], bool]:
    """Return (current_patients, next_hr_forecast, peak_24h, api_offline).

    Priority:
    1. get_live_context() cache (API online)
    2. patient_flow CSV last row (current_patients fallback)
    3. ForecastState 72h artifact (next_hr, peak_24h fallback)
    """
    cur = fs.current_patients if fs else None
    nxt = fs.predicted_patients_next_hour if fs else None
    pk24 = fs.peak_24h if fs else None
    api_offline = True

    # 1) Try live context (already cached by sidebar; no new API calls if cache is warm)
    try:
        from dashboard_sections import get_live_context
        ctx = get_live_context()
        if ctx and ctx.get("ready"):
            cur = float(ctx.get("current_patients") or cur or 0)
            nxt = float(ctx.get("prediction") or nxt or 0)
            pk24 = float(ctx.get("peak") or pk24 or 0)
            api_offline = False
    except Exception:
        pass

    # 2) Fallback: patient_flow CSV for current_patients
    if cur is None or cur == 0:
        try:
            pf = pd.read_csv(_PATIENT_FLOW_PATH, usecols=["patients"])
            if not pf.empty:
                cur = float(pf["patients"].iloc[-1])
        except Exception:
            pass

    # 3) Fallback: derive next_hr and peak_24h from 72h artifact
    vals72 = list(fs.forecast_72h_values) if fs and fs.forecast_72h_values else []
    if (nxt is None or nxt == 0) and vals72:
        nxt = float(vals72[0])
    if (pk24 is None or pk24 == 0) and len(vals72) >= 24:
        pk24 = float(max(vals72[:24]))
    elif (pk24 is None or pk24 == 0) and vals72:
        pk24 = float(max(vals72))

    return cur, nxt, pk24, api_offline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(v, default: int = 0) -> int:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return int(round(float(v)))
    except Exception:
        return default


def _safe_sum(col) -> int:
    try:
        return int(pd.to_numeric(col, errors="coerce").fillna(0).sum())
    except Exception:
        return 0


def _risk_rgba(risk: str) -> str:
    return {
        "HIGH": "251,113,133",
        "MEDIUM": "251,191,36",
        "LOW": "52,211,153",
    }.get(str(risk).upper(), "148,163,184")


def _pressure_color(level: str) -> str:
    l = str(level).lower()
    if l in {"high", "critical"}:
        return "#FB7185"
    if l in {"moderate", "warning"}:
        return "#FBBF24"
    if l in {"low", "stable"}:
        return "#34D399"
    return "#94A3B8"


def _ordered_dept(dept_df: pd.DataFrame) -> pd.DataFrame:
    if dept_df.empty or "department" not in dept_df.columns:
        return dept_df
    ordered = [d for d in _DEPT_ORDER if d in dept_df["department"].values]
    rest = [d for d in dept_df["department"].values if d not in _DEPT_ORDER]
    return dept_df.assign(
        department=pd.Categorical(dept_df["department"], categories=ordered + rest, ordered=True)
    ).sort_values("department")


def _alert_counts(dept_df: pd.DataFrame) -> tuple[int, int]:
    if dept_df.empty:
        return 0, 0
    if "department_status" in dept_df.columns:
        crit = int((dept_df["department_status"].str.lower() == "critical").sum())
        warn = int((dept_df["department_status"].str.lower() == "warning").sum())
        return crit, warn
    if "pressure_level" in dept_df.columns:
        crit = int((dept_df["pressure_level"].str.lower() == "high").sum())
        warn = int((dept_df["pressure_level"].str.lower() == "moderate").sum())
        return crit, warn
    return 0, 0


# ---------------------------------------------------------------------------
# Section: Hero strip
# ---------------------------------------------------------------------------

def _render_hero(fs, now: datetime, api_offline: bool) -> None:
    model = ((fs.selected_model or "Hybrid").upper()) if fs else "—"
    risk = str(fs.risk_level or "LOW").upper() if fs else "LOW"
    ts = (fs.forecast_timestamp or now.isoformat()) if fs else now.isoformat()
    is_ready = bool(fs and fs.artifact_freshness.ready)

    risk_rgb = _risk_rgba(risk)
    sys_rgb = "52,211,153" if is_ready else "251,191,36"
    sys_label = "System Online" if is_ready else "Degraded"
    api_rgb = "148,163,184" if api_offline else "52,211,153"
    api_label = "Artifact Mode" if api_offline else "Live API"
    ts_short = (ts[:16].replace("T", " ")) if ts and len(ts) >= 16 else str(ts)
    today_label = now.strftime("%a %d %b %Y · %H:%M")

    st.markdown(
        f"""
        <div style="
          background:linear-gradient(135deg,rgba(59,130,246,0.13) 0%,rgba(20,184,166,0.09) 55%,rgba(99,102,241,0.08) 100%);
          border:1px solid rgba(59,130,246,0.22); border-radius:16px;
          padding:20px 26px 16px 26px; margin-bottom:18px;
        ">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="font-size:1.55rem;font-weight:820;letter-spacing:-0.025em;color:var(--text);">
                Hospital AI Command Center
              </div>
              <div style="color:var(--text-2);margin-top:4px;font-size:0.93rem;">
                72-hour surge &nbsp;·&nbsp; resource allocation &nbsp;·&nbsp; operational pressure &nbsp;·&nbsp; {today_label}
              </div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-top:3px;">
              <span title="Best model by test RMSE on the held-out split. The deployed operational forecaster is the Hybrid (LSTM 0.80 / ARIMAX 0.20) — see the Evaluation tab."
                style="background:rgba(59,130,246,0.14);color:var(--text);
                border:1px solid rgba(59,130,246,0.26);border-radius:999px;
                padding:4px 12px;font-size:12px;font-weight:750;white-space:nowrap;cursor:help;">Best model: {model}</span>
              <span style="background:rgba({risk_rgb},0.14);color:var(--text);
                border:1px solid rgba({risk_rgb},0.28);border-radius:999px;
                padding:4px 12px;font-size:12px;font-weight:750;white-space:nowrap;">Risk: {risk}</span>
              <span style="background:rgba({sys_rgb},0.14);color:var(--text);
                border:1px solid rgba({sys_rgb},0.28);border-radius:999px;
                padding:4px 12px;font-size:12px;font-weight:750;white-space:nowrap;">&#9679; {sys_label}</span>
              <span style="background:rgba({api_rgb},0.10);color:var(--text);
                border:1px solid rgba({api_rgb},0.22);border-radius:999px;
                padding:4px 12px;font-size:12px;font-weight:750;white-space:nowrap;">&#9675; {api_label}</span>
              <span style="color:var(--text-3);font-size:11px;white-space:nowrap;margin-left:2px;">
                Forecast: {ts_short}
              </span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# KPI Row 1 — Forecast
# ---------------------------------------------------------------------------

def _render_forecast_kpis(
    fs,
    cur: Optional[float],
    nxt: Optional[float],
    pk24: Optional[float],
    api_offline: bool,
    dept_df: pd.DataFrame,
) -> None:
    label_sfx = " *" if api_offline else ""
    section_header(
        "Live Forecast KPIs",
        "AI-derived patient demand" + (" · * artifact-mode values" if api_offline else " · live values"),
    )

    pk72 = _safe_int(fs.peak_72h if fs else None)
    avg72 = _safe_int(fs.avg_72h if fs else None)

    depts_high = 0
    if not dept_df.empty and "pressure_level" in dept_df.columns:
        depts_high = int((dept_df["pressure_level"].str.lower() == "high").sum())
    elif not dept_df.empty and "department_status" in dept_df.columns:
        depts_high = int((dept_df["department_status"].str.lower() == "critical").sum())

    cur_v = _safe_int(cur)
    nxt_v = _safe_int(nxt)
    pk24_v = _safe_int(pk24)

    cur_disp = fmt_int(cur_v) if cur_v else "—"
    nxt_disp = fmt_int(nxt_v) if nxt_v else "—"
    pk24_disp = fmt_int(pk24_v) + label_sfx if pk24_v else "—"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        kpi_card("Current Patients", cur_disp + label_sfx, status="info")
    with c2:
        kpi_card("Next-Hour Forecast", nxt_disp + label_sfx, status="info")
    with c3:
        kpi_card("24h Peak", pk24_disp,
                 status="critical" if pk24_v >= 120 else ("warning" if pk24_v >= 80 else "success"))
    with c4:
        kpi_card("72h Peak", fmt_int(pk72),
                 status="critical" if pk72 >= 120 else ("warning" if pk72 >= 80 else "success"))
    with c5:
        kpi_card("Avg 72h Load", fmt_int(avg72), status="normal")
    with c6:
        kpi_card(
            "Depts Under Pressure", str(depts_high),
            delta=f"{depts_high} dept{'s' if depts_high != 1 else ''} at high pressure",
            status="critical" if depts_high >= 2 else ("warning" if depts_high == 1 else "success"),
        )


# ---------------------------------------------------------------------------
# KPI Row 2 — Resources
# ---------------------------------------------------------------------------

def _render_resource_kpis(dept_df: pd.DataFrame, appt_df: pd.DataFrame, or_df: pd.DataFrame) -> None:
    section_header("Resource Snapshot", "Beds, staff, and scheduled workload at a glance")

    avail_beds = total_beds = avail_docs = avail_nurses = 0
    if not dept_df.empty:
        avail_beds = _safe_sum(dept_df.get("available_beds", pd.Series(dtype=float)))
        total_beds = _safe_sum(dept_df.get("total_beds", pd.Series(dtype=float)))
        avail_docs = _safe_sum(dept_df.get("available_doctors", pd.Series(dtype=float)))
        avail_nurses = _safe_sum(dept_df.get("available_nurses", pd.Series(dtype=float)))

    occ_pct = f"{int(round((total_beds - avail_beds) / total_beds * 100))}%" if total_beds > 0 else "—"
    beds_label = f"{avail_beds} / {total_beds}"
    beds_status = "critical" if avail_beds < 10 else ("warning" if avail_beds < 20 else "success")

    # Appointments (next 7 days)
    today = datetime.now().date()
    appt_count = 0
    if not appt_df.empty:
        if "date" in appt_df.columns and pd.api.types.is_datetime64_any_dtype(appt_df["date"]):
            w = (appt_df["date"].dt.date >= today) & (appt_df["date"].dt.date <= today + timedelta(days=7))
            appt_count = int(w.sum())
        else:
            appt_count = len(appt_df)

    # OR bookings
    or_count = 0
    if not or_df.empty:
        if "status" in or_df.columns:
            or_count = int(or_df["status"].str.lower().isin({"scheduled", "booked", "confirmed"}).sum())
        else:
            or_count = len(or_df)

    critical_n, warning_n = _alert_counts(dept_df)
    total_alerts = critical_n + warning_n

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        kpi_card("Available Beds", beds_label, delta=f"Occupancy {occ_pct}", status=beds_status)
    with c2:
        kpi_card("Avail. Doctors", fmt_int(avail_docs), status="normal")
    with c3:
        kpi_card("Avail. Nurses", fmt_int(avail_nurses), status="normal")
    with c4:
        kpi_card("Appts (7-day)", fmt_int(appt_count), status="info")
    with c5:
        kpi_card("OR Bookings", fmt_int(or_count), status="info")
    with c6:
        kpi_card(
            "Active Alerts", str(total_alerts),
            delta=f"{critical_n} Critical · {warning_n} Warning",
            status="critical" if critical_n > 0 else ("warning" if warning_n > 0 else "success"),
        )
    st.caption(
        "Bed/staff counts = currently **staffed and open** resources from the live department-status "
        "snapshot. The Optimization tab plans against the larger *configured physical capacity* "
        "(≈293 beds incl. overflow/hallway bays), which is why its totals are higher."
    )


# ---------------------------------------------------------------------------
# Chart 1: 72-hour AI forecast
# ---------------------------------------------------------------------------

def _render_forecast_chart(fs, horizon: int) -> None:
    section_header(f"{horizon}h AI Patient Forecast", "Hybrid model prediction · risk threshold bands")
    if fs is None or fs.overall_forecast_72h is None or fs.overall_forecast_72h.empty:
        empty_state("72-hour forecast artifact not available.")
        return

    df = fs.overall_forecast_72h.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).head(horizon)
    if df.empty:
        empty_state("No forecast rows to display.")
        return

    hybrid = pd.to_numeric(df.get("hybrid_pred", pd.Series(dtype=float)), errors="coerce")
    max_v = float(hybrid.max()) if not hybrid.isna().all() else 150
    y_max = max(max_v * 1.10, 135)

    tmpl = plotly_template_name()
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=80, fillcolor="rgba(52,211,153,0.05)", line_width=0)
    fig.add_hrect(y0=80, y1=120, fillcolor="rgba(251,191,36,0.06)", line_width=0)
    if y_max > 115:
        fig.add_hrect(y0=120, y1=y_max, fillcolor="rgba(251,113,133,0.06)", line_width=0)
    fig.add_hline(y=80, line_dash="dot", line_color="rgba(251,191,36,0.55)",
                  annotation_text="Monitor (80)", annotation_position="right", annotation_font_size=10)
    fig.add_hline(y=120, line_dash="dot", line_color="rgba(251,113,133,0.60)",
                  annotation_text="Critical (120)", annotation_position="right", annotation_font_size=10)

    for col, label, color in [
        ("lstm_pred", "LSTM", "rgba(45,212,191,0.50)"),
        ("arimax_pred", "ARIMAX", "rgba(129,140,248,0.45)"),
    ]:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            if not vals.isna().all():
                fig.add_trace(go.Scatter(
                    x=df["datetime"], y=vals, mode="lines", name=label,
                    line=dict(color=color, width=1.5, dash="dot"),
                    hovertemplate=f"{label}: %{{y:.0f}}<extra></extra>",
                ))

    fig.add_trace(go.Scatter(
        x=df["datetime"], y=hybrid,
        fill="tozeroy", fillcolor="rgba(59,130,246,0.10)",
        mode="lines", name="Hybrid",
        line=dict(color="rgba(59,130,246,0.90)", width=2.5),
        hovertemplate="<b>%{y:.0f}</b> pts &nbsp;%{x|%a %H:%M}<extra></extra>",
    ))
    fig.update_layout(
        template=tmpl, height=310,
        margin=dict(l=0, r=70, t=12, b=0),
        yaxis=dict(title="Patients", range=[0, y_max]),
        xaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "fc", str(horizon)))


# ---------------------------------------------------------------------------
# Chart 2: Weekly congestion heatmap
# ---------------------------------------------------------------------------

def _render_heatmap() -> None:
    section_header("Weekly Congestion Heatmap", "Average patient load by day and hour")
    pivot = _home_heatmap_df()
    if pivot.empty:
        empty_state("Patient flow data not available for heatmap.")
        return

    tmpl = plotly_template_name()
    z = pivot.values
    x_labels = [str(h) + ":00" if h % 4 == 0 else "" for h in range(24)]
    x_hover = [f"{h:02d}:00" for h in range(24)]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=list(range(24)),
        y=pivot.index.tolist(),
        colorscale="YlOrRd",
        hovertemplate="<b>%{y} %{text}</b><br>Avg patients: %{z:.0f}<extra></extra>",
        text=[[x_hover[h] for h in range(24)] for _ in range(len(pivot))],
        colorbar=dict(title="Avg pts", thickness=14),
        zmin=float(z.min()),
        zmax=float(z.max()),
    ))
    fig.update_layout(
        template=tmpl, height=310,
        margin=dict(l=10, r=10, t=12, b=30),
        xaxis=dict(
            title="Hour of day",
            tickvals=list(range(0, 24, 4)),
            ticktext=[f"{h:02d}:00" for h in range(0, 24, 4)],
        ),
        yaxis_title=None,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "heatmap"))
    st.caption("Darker cells indicate higher average patient load. Based on 17,520 hours of operational data.")


# ---------------------------------------------------------------------------
# Chart 3: Department pressure bar
# ---------------------------------------------------------------------------

def _render_dept_pressure(dept_df: pd.DataFrame) -> None:
    section_header("Dept Pressure", "Occupancy by department")
    if dept_df.empty:
        empty_state("No dept data.")
        return

    df = _ordered_dept(dept_df.copy())
    metric_col = "occupancy_rate" if "occupancy_rate" in df.columns else "current_patients"
    pressure_col = "pressure_level" if "pressure_level" in df.columns else "department_status"
    df["_color"] = df[pressure_col].apply(_pressure_color) if pressure_col in df.columns else "#94A3B8"
    y_vals = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)
    if metric_col == "occupancy_rate":
        y_vals = y_vals * 100
    text_vals = y_vals.apply(lambda v: f"{v:.0f}%") if metric_col == "occupancy_rate" else y_vals.apply(lambda v: f"{int(v)}")

    tmpl = plotly_template_name()
    fig = go.Figure(go.Bar(
        x=df["department"].astype(str), y=y_vals,
        marker_color=df["_color"], text=text_vals, textposition="outside",
        hovertemplate="%{x}: %{y:.1f}" + ("%" if metric_col == "occupancy_rate" else "") + "<extra></extra>",
    ))
    if metric_col == "occupancy_rate":
        fig.add_hline(y=85, line_dash="dot", line_color="rgba(251,191,36,0.6)",
                      annotation_text="85%", annotation_font_size=10)
    fig.update_layout(
        template=tmpl, height=265,
        margin=dict(l=0, r=20, t=12, b=0),
        yaxis=dict(title="Occupancy (%)" if metric_col == "occupancy_rate" else "Patients",
                   range=[0, 115 if metric_col == "occupancy_rate" else None]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "dept_occ"))


# ---------------------------------------------------------------------------
# Chart 4: Bed occupancy stacked bar (occupied vs available)
# ---------------------------------------------------------------------------

def _render_bed_occupancy(dept_df: pd.DataFrame) -> None:
    section_header("Bed Occupancy", "Occupied vs available beds")
    if dept_df.empty or "occupied_beds" not in dept_df.columns:
        empty_state("Bed data not available.")
        return

    df = _ordered_dept(dept_df.copy())
    tmpl = plotly_template_name()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Occupied", x=df["department"].astype(str),
        y=pd.to_numeric(df.get("occupied_beds", 0), errors="coerce").fillna(0),
        marker_color="rgba(251,113,133,0.80)",
        hovertemplate="%{x}: %{y:.0f} occupied<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Available", x=df["department"].astype(str),
        y=pd.to_numeric(df.get("available_beds", 0), errors="coerce").fillna(0),
        marker_color="rgba(52,211,153,0.72)",
        hovertemplate="%{x}: %{y:.0f} available<extra></extra>",
    ))
    fig.update_layout(
        template=tmpl, height=265, barmode="stack",
        margin=dict(l=0, r=10, t=12, b=0),
        xaxis_title=None, yaxis_title="Beds",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, title_text=""),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "bed_occ"))


# ---------------------------------------------------------------------------
# Chart 5: Staff coverage (doctors + nurses per department)
# ---------------------------------------------------------------------------

def _render_staff_coverage() -> None:
    section_header("Staff Coverage", "Doctors and nurses by department")
    staff_df = _home_staff_master()
    if staff_df.empty or "department" not in staff_df.columns or "role" not in staff_df.columns:
        empty_state("Staff data not available.")
        return

    summary = (
        staff_df.groupby(["department", "role"]).size()
        .unstack("role", fill_value=0)
        .reset_index()
    )
    summary = summary.rename(columns={"doctor": "Doctors", "nurse": "Nurses"})
    # Ensure Doctors/Nurses columns exist
    for col in ["Doctors", "Nurses"]:
        if col not in summary.columns:
            # Try case-insensitive match
            match = [c for c in summary.columns if c.lower() == col.lower()]
            if match:
                summary = summary.rename(columns={match[0]: col})
            else:
                summary[col] = 0

    if "department" not in summary.columns:
        empty_state("Department column missing.")
        return

    ordered_depts = [d for d in _DEPT_ORDER if d in summary["department"].values]
    rest = [d for d in summary["department"].values if d not in _DEPT_ORDER]
    summary["department"] = pd.Categorical(summary["department"], categories=ordered_depts + rest, ordered=True)
    summary = summary.sort_values("department")

    tmpl = plotly_template_name()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Doctors", x=summary["department"].astype(str),
        y=pd.to_numeric(summary.get("Doctors", 0), errors="coerce").fillna(0),
        marker_color="rgba(52,211,153,0.80)",
        hovertemplate="%{x}: %{y:.0f} doctors<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Nurses", x=summary["department"].astype(str),
        y=pd.to_numeric(summary.get("Nurses", 0), errors="coerce").fillna(0),
        marker_color="rgba(96,165,250,0.75)",
        hovertemplate="%{x}: %{y:.0f} nurses<extra></extra>",
    ))
    fig.update_layout(
        template=tmpl, height=265, barmode="group",
        margin=dict(l=0, r=10, t=12, b=0),
        xaxis_title=None, yaxis_title="Staff count",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, title_text=""),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "staff_cov"))


# ---------------------------------------------------------------------------
# Chart 6: Appointments workload by department
# ---------------------------------------------------------------------------

def _render_appt_workload(appt_df: pd.DataFrame) -> None:
    section_header("Appt Workload", "Patient volume by department")
    if appt_df.empty or "department" not in appt_df.columns:
        empty_state("Appointment data not available.")
        return

    dept_load = (
        appt_df.groupby("department")["patient_count"]
        .sum()
        .reset_index()
        .rename(columns={"patient_count": "Total Patients"})
    )
    dept_load["Total Patients"] = pd.to_numeric(dept_load["Total Patients"], errors="coerce").fillna(0)

    ordered = [d for d in _DEPT_ORDER if d in dept_load["department"].values]
    rest = [d for d in dept_load["department"].values if d not in _DEPT_ORDER]
    dept_load["department"] = pd.Categorical(dept_load["department"], categories=ordered + rest, ordered=True)
    dept_load = dept_load.sort_values("department")

    tmpl = plotly_template_name()
    fig = go.Figure(go.Bar(
        x=dept_load["department"].astype(str),
        y=dept_load["Total Patients"],
        marker_color="rgba(99,102,241,0.75)",
        text=dept_load["Total Patients"].apply(lambda v: f"{int(v)}"),
        textposition="outside",
        hovertemplate="%{x}: %{y:.0f} patient visits<extra></extra>",
    ))
    fig.update_layout(
        template=tmpl, height=265,
        margin=dict(l=0, r=10, t=12, b=0),
        xaxis_title=None, yaxis_title="Total patients",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "appt_wkld"))


# ---------------------------------------------------------------------------
# Chart 7: OR room utilization
# ---------------------------------------------------------------------------

def _render_or_utilization(or_df: pd.DataFrame) -> None:
    section_header("OR Utilization", "Bookings and duration by room")
    if or_df.empty or "room" not in or_df.columns:
        empty_state("OR data not available.")
        return

    has_dur = "procedure_duration_minutes" in or_df.columns
    if has_dur:
        agg = (
            or_df.groupby("room")
            .agg(bookings=("room", "count"),
                 duration=("procedure_duration_minutes", "sum"))
            .reset_index()
        )
        agg["duration"] = pd.to_numeric(agg["duration"], errors="coerce").fillna(0)
        room_capacity_min = 12 * 60
        agg["utilization_pct"] = (agg["duration"] / room_capacity_min * 100).clip(upper=100).round(1)
        y_col, y_label = "utilization_pct", "Utilization (%)"
        text_col = agg["utilization_pct"].apply(lambda v: f"{v:.0f}%")
        hover = "%{x}: %{y:.0f}% utilized<extra></extra>"
        y_range = [0, 108]
    else:
        agg = or_df.groupby("room").size().reset_index(name="bookings")
        y_col, y_label = "bookings", "Bookings"
        text_col = agg["bookings"].astype(str)
        hover = "%{x}: %{y:.0f} bookings<extra></extra>"
        y_range = None

    tmpl = plotly_template_name()
    fig = go.Figure(go.Bar(
        x=agg["room"].astype(str), y=agg[y_col],
        marker_color="rgba(251,191,36,0.78)",
        text=text_col, textposition="outside",
        hovertemplate=hover,
    ))
    fig.update_layout(
        template=tmpl, height=265,
        margin=dict(l=0, r=10, t=12, b=0),
        xaxis_title=None, yaxis=dict(title=y_label, range=y_range),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "or_util"))


# ---------------------------------------------------------------------------
# Chart 8: Alerts/pressure breakdown (horizontal status bar)
# ---------------------------------------------------------------------------

def _render_alerts_breakdown(dept_df: pd.DataFrame) -> None:
    section_header("Pressure Breakdown", "Dept status distribution")
    if dept_df.empty:
        empty_state("No dept data.")
        return

    status_col = "department_status" if "department_status" in dept_df.columns else "pressure_level"
    if status_col not in dept_df.columns:
        empty_state("Status column missing.")
        return

    counts = dept_df[status_col].value_counts().reset_index()
    counts.columns = ["Status", "Count"]

    color_map = {
        "Critical": "#FB7185", "Warning": "#FBBF24", "Stable": "#34D399",
        "High": "#FB7185", "Moderate": "#FBBF24", "Low": "#34D399",
    }
    counts["Color"] = counts["Status"].map(color_map).fillna("#94A3B8")
    counts["Label"] = counts.apply(lambda r: f"{r.Status} ({int(r.Count)})", axis=1)

    tmpl = plotly_template_name()
    fig = go.Figure(go.Bar(
        x=counts["Count"], y=counts["Status"],
        orientation="h",
        marker_color=counts["Color"],
        text=counts["Label"], textposition="inside",
        hovertemplate="%{y}: %{x} dept(s)<extra></extra>",
    ))
    fig.update_layout(
        template=tmpl, height=265,
        margin=dict(l=0, r=10, t=12, b=0),
        xaxis=dict(title="Departments", dtick=1),
        yaxis_title=None,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "alerts_brkdwn"))


# ---------------------------------------------------------------------------
# Compact tables
# ---------------------------------------------------------------------------

def _render_dept_table(dept_df: pd.DataFrame) -> None:
    section_header("Dept Status", "Beds · staff · shortages")
    if dept_df.empty:
        empty_state("No dept data.")
        return
    df = _ordered_dept(dept_df.copy())
    want = ["department", "current_patients", "available_beds", "bed_shortage",
            "doctor_shortage", "nurse_shortage", "pressure_level", "department_status"]
    cols = [c for c in want if c in df.columns]
    display = df[cols].rename(columns={
        "department": "Dept", "current_patients": "Patients",
        "available_beds": "Free Beds", "bed_shortage": "Bed Gap",
        "doctor_shortage": "Dr Gap", "nurse_shortage": "RN Gap",
        "pressure_level": "Pressure", "department_status": "Status",
    })
    st.dataframe(display, use_container_width=True, hide_index=True, key=scoped_key("home", "dept_tbl"))


def _render_appt_snapshot(appt_df: pd.DataFrame) -> None:
    section_header("Upcoming Appointments", "Next 7 days — top 5")
    if appt_df.empty:
        empty_state("No appointment data.")
        return
    today = datetime.now().date()
    df = appt_df.copy()
    if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
        w = (df["date"].dt.date >= today) & (df["date"].dt.date <= today + timedelta(days=7))
        filtered = df[w]
        df = filtered if not filtered.empty else appt_df.copy()
    if "date" in df.columns:
        df = df.sort_values("date")
    df = df.head(5)
    show = [c for c in ["department", "doctor", "date", "time_slot", "patient_count", "status"] if c in df.columns]
    if "date" in show and pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(df[show], use_container_width=True, hide_index=True, key=scoped_key("home", "appt_tbl"))


def _render_or_snapshot(or_df: pd.DataFrame) -> None:
    section_header("OR Bookings", "Upcoming scheduled — top 5")
    if or_df.empty:
        empty_state("No OR data.")
        return
    df = or_df.copy()
    if "status" in df.columns:
        sched = df[df["status"].str.lower().isin({"scheduled", "booked", "confirmed"})]
        df = sched if not sched.empty else df
    if "date" in df.columns:
        df = df.sort_values("date")
    df = df.head(5)
    show = [c for c in ["room", "doctor", "department", "date", "time_slot", "procedure", "status"] if c in df.columns]
    if "date" in show and pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(df[show], use_container_width=True, hide_index=True, key=scoped_key("home", "or_tbl"))


def _render_mgmt_actions(dept_df: pd.DataFrame, api_offline: bool) -> None:
    section_header("Recommended Actions", "AI-derived management priorities")
    actions = []
    if not dept_df.empty:
        for _, row in dept_df.iterrows():
            dept = str(row.get("department", ""))
            pressure = str(row.get("pressure_level", row.get("department_status", ""))).lower()
            bed_gap = int(pd.to_numeric(row.get("bed_shortage", 0), errors="coerce") or 0)
            doc_gap = int(pd.to_numeric(row.get("doctor_shortage", 0), errors="coerce") or 0)
            rn_gap = int(pd.to_numeric(row.get("nurse_shortage", 0), errors="coerce") or 0)
            if pressure in {"high", "critical"}:
                actions.append(("critical", f"🔴 {dept}: Activate surge protocol — critical pressure level"))
            if bed_gap > 0:
                actions.append(("warning", f"🟡 {dept}: Arrange {bed_gap} additional bed(s) or expedite discharges"))
            if doc_gap > 0:
                actions.append(("warning", f"🟡 {dept}: Assign {doc_gap} additional doctor(s) to coverage"))
            if rn_gap > 0:
                actions.append(("warning", f"🟡 {dept}: Assign {rn_gap} additional nurse(s) to coverage"))

    if api_offline:
        actions.append(("info", "ℹ️ Live predictions unavailable — start API server for real-time AI forecasting"))

    if not actions:
        actions.append(("success", "✅ All departments within normal operational parameters"))

    for severity, msg in actions[:6]:
        color = {"critical": "#FB7185", "warning": "#FBBF24", "success": "#34D399", "info": "#60A5FA"}.get(severity, "#94A3B8")
        st.markdown(
            f"<div style='padding:8px 14px;border-left:4px solid {color};border-radius:6px;"
            f"background:rgba(255,255,255,0.04);margin-bottom:6px;font-size:0.9rem;color:var(--text);'>{msg}</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

def _render_footer(fs) -> None:
    mae_s = rmse_s = mape_s = "—"
    model_name = (fs.selected_model or "Hybrid") if fs else "Hybrid"
    weights = (fs.model_weights or {}) if fs else {}
    lstm_w = weights.get("lstm", weights.get("LSTM", 0.80))
    arimax_w = weights.get("arimax", weights.get("ARIMAX", 0.20))

    metrics_df: Optional[pd.DataFrame] = None
    if fs and isinstance(getattr(fs, "metrics", None), pd.DataFrame) and not fs.metrics.empty:
        metrics_df = fs.metrics
    else:
        try:
            metrics_df = _cached_metrics_df()
        except Exception:
            pass

    if metrics_df is not None and not metrics_df.empty and "Model" in metrics_df.columns:
        mask = metrics_df["Model"].str.lower() == "hybrid"
        if mask.any():
            row = metrics_df[mask].iloc[0]
            for k, s_var in [("MAE", "mae_s"), ("RMSE", "rmse_s"), ("MAPE", "mape_s")]:
                try:
                    v = float(row.get(k, row.get(k.lower(), 0)))
                    if k == "MAPE":
                        locals()[s_var]  # just access to silence linter
                    fmt_fn = fmt_mape if k == "MAPE" else fmt_mae_rmse
                    val = fmt_fn(v)
                    if k == "MAE":
                        mae_s = val
                    elif k == "RMSE":
                        rmse_s = val
                    else:
                        mape_s = val
                except Exception:
                    pass

    st.markdown("---")
    st.caption(
        f"Forecast accuracy — {model_name}: MAE {mae_s} pts · RMSE {rmse_s} pts · "
        f"MAPE {mape_s} (caution — not primary metric) · "
        f"Blend: LSTM {lstm_w:.0%} / ARIMAX {arimax_w:.0%}"
    )
    st.caption(
        "Navigate to: Forecast · Digital Twin · Optimization · Shifts · Appointments · "
        "OR Bookings · Evaluation · Explainability · Approvals · Audit · Messages · Notifications"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _render_ops_briefing(fs, dept_df: pd.DataFrame, now: datetime) -> None:
    """Daily Ops Briefing — deterministic template over real state (no LLM).

    Every number traces to ForecastState, the department-status snapshot, or
    the census projection (labelled as a projection).
    """

    try:
        from ops_insights import build_briefing, project_census, saturation_label
    except Exception:
        return

    vals72 = list(fs.forecast_72h_values) if fs and fs.forecast_72h_values else []
    nxt = float(fs.predicted_patients_next_hour) if fs and fs.predicted_patients_next_hour else None
    risk = str(fs.risk_level or "LOW") if fs else "LOW"
    peak72 = float(fs.peak_72h) if fs and fs.peak_72h else None
    peak_off = int(vals72.index(max(vals72))) if vals72 else None

    staffed = occupied = 0
    top_dept = None
    bed_short = 0
    if not dept_df.empty:
        staffed = int(_safe_sum(dept_df.get("total_beds", pd.Series(dtype=float))))
        occupied = int(_safe_sum(dept_df.get("occupied_beds", pd.Series(dtype=float))))
        bed_short = int(_safe_sum(dept_df.get("bed_shortage", pd.Series(dtype=float))))
        if "pressure_level" in dept_df.columns:
            ranked = dept_df.sort_values("bed_shortage", ascending=False) if "bed_shortage" in dept_df.columns else dept_df
            top_dept = str(ranked.iloc[0]["department"]) if not ranked.empty else None

    hours_to_sat = None
    if vals72 and staffed > 0:
        proj = project_census(vals72, staffed_beds=staffed, initial_census=occupied)
        hours_to_sat = proj.hours_to_saturation

    critical_n, warning_n = _alert_counts(dept_df)
    lines = build_briefing(
        now=now, predicted_next_hour=nxt, peak_72h=peak72, peak_hour_offset=peak_off,
        risk_level=risk, critical_alerts=critical_n, warning_alerts=warning_n,
        top_pressure_department=top_dept, total_bed_shortage=bed_short,
        hours_to_saturation=hours_to_sat, staffed_beds=staffed or None,
    )
    if not lines:
        return

    with st.container(border=True):
        st.markdown("**📋 Daily Ops Briefing** &nbsp; " + now.strftime("%a %d %b · %H:%M"))
        for line in lines:
            st.markdown(f"- {line}")
        st.caption(
            f"Auto-generated from ForecastState + department snapshot + census projection "
            f"({saturation_label(hours_to_sat)} to saturation). Template-based — every number "
            "is traceable; synthetic demo data."
        )


def _render_demo_freshness_chip(appt_df: pd.DataFrame, now: datetime) -> None:
    """Warn when the demo display data window has drifted away from today
    (the cause of the historical 'Appts (7-day) = 0' bug)."""

    if appt_df.empty or "date" not in appt_df.columns:
        return
    dates = pd.to_datetime(appt_df["date"], errors="coerce").dropna()
    if dates.empty:
        return
    dmin, dmax = dates.min().date(), dates.max().date()
    if not (dmin <= now.date() <= dmax):
        st.warning(
            f"Demo display data covers {dmin} → {dmax}, but today is {now.date()}. "
            "Run `python scripts/refresh_demo_dates.py --db` to re-anchor the demo window.",
            icon="📅",
        )


def show_home(role: str = "admin") -> None:
    """Render the Home tab — Hospital AI Command Center launchpad."""
    role = str(role or "admin").lower()
    now = datetime.now()

    # Load ForecastState (cached, reads 4 small CSVs)
    with st.spinner("Loading system overview..."):
        try:
            fs = _cached_artifact_forecast_state()
        except Exception:
            fs = None

    # Resolve live KPIs (tries cached live_context, falls back to artifacts)
    cur, nxt, pk24, api_offline = _resolve_live_kpis(fs)

    # Load operational CSVs (all cached, fast)
    dept_df = _home_dept_status()
    appt_df = _home_appointments()
    or_df = _home_or_bookings()

    # --- Display options (collapsed) ---
    with st.expander("Display options", expanded=False):
        ctl_l, ctl_r = st.columns(2)
        with ctl_l:
            horizon = st.selectbox(
                "Forecast horizon",
                [24, 48, 72], index=2,
                key=scoped_key("home", "horizon"),
                help="Hours of the 72-hour forecast to display",
            )
        with ctl_r:
            dept_opts = ["All departments"]
            if not dept_df.empty and "department" in dept_df.columns:
                dept_opts += sorted(dept_df["department"].dropna().unique().tolist())
            sel_dept = st.selectbox(
                "Department filter", dept_opts,
                key=scoped_key("home", "dept_filter"),
            )
    view_dept = dept_df
    if sel_dept != "All departments" and not dept_df.empty and "department" in dept_df.columns:
        view_dept = dept_df[dept_df["department"] == sel_dept].copy()

    # ── Hero ────────────────────────────────────────────────────────────────
    _render_hero(fs, now, api_offline)

    # ── Demo data freshness + Daily Ops Briefing ─────────────────────────────
    _render_demo_freshness_chip(appt_df, now)
    _render_ops_briefing(fs, dept_df, now)

    # ── Quick navigation launchpad ───────────────────────────────────────────
    section_header("Quick navigation", "Jump straight to the workspace you need")
    nav_specs = [
        ("📈 Forecast →", "Forecast", "forecast"),
        ("🛠️ Optimization →", "Optimization", "optimization"),
        ("🗓️ Appointments →", "Appointments", "appointments"),
        ("🔔 Notifications →", "Notifications", "notifications"),
        ("💬 Messages →", "Messages", "messages"),
    ]
    visible = [s for s in nav_specs if s[1] in _ROLE_PAGES.get(role, set())]
    if visible:
        cols = st.columns(len(visible))
        for col, (label, target, key) in zip(cols, visible):
            with col:
                _nav_button(label, target, role, key)
    st.markdown("")

    # ── KPI Row 1: Forecast ──────────────────────────────────────────────────
    _render_forecast_kpis(fs, cur, nxt, pk24, api_offline, dept_df)
    st.markdown("")

    # ── KPI Row 2: Resources ─────────────────────────────────────────────────
    _render_resource_kpis(dept_df, appt_df, or_df)
    st.markdown("")

    # ── Row A: Main forecast chart + Congestion heatmap ─────────────────────
    ra_l, ra_r = st.columns([6, 6], gap="medium")
    with ra_l:
        _render_forecast_chart(fs, horizon)
    with ra_r:
        _render_heatmap()

    st.markdown("")

    # ── Row B: Dept pressure · Bed occupancy · Alerts breakdown ─────────────
    rb1, rb2, rb3 = st.columns([4, 4, 4], gap="medium")
    with rb1:
        _render_dept_pressure(view_dept)
    with rb2:
        _render_bed_occupancy(view_dept)
    with rb3:
        _render_alerts_breakdown(view_dept)

    st.markdown("")

    # ── Row C: Staff coverage · Appt workload · OR utilization ──────────────
    rc1, rc2, rc3 = st.columns([4, 4, 4], gap="medium")
    with rc1:
        _render_staff_coverage()
    with rc2:
        _render_appt_workload(appt_df)
    with rc3:
        _render_or_utilization(or_df)

    st.markdown("")

    # ── Row D: Compact tables + Management actions ────────────────────────────
    with st.expander("Operational Details — Dept Table · Appointments · OR Bookings", expanded=True):
        rd1, rd2, rd3 = st.columns([4, 4, 4], gap="medium")
        with rd1:
            _render_dept_table(view_dept)
            # Department detail lives in different pages per role.
            _dept_target = "Department" if role == "nurse" else ("Operations Center" if role == "admin" else None)
            if _dept_target:
                _nav_button("Open department view →", _dept_target, role, "dept_full")
        with rd2:
            _render_appt_snapshot(appt_df)
            _nav_button("Open Appointments →", "Appointments", role, "appt_full")
        with rd3:
            _render_or_snapshot(or_df)
            _nav_button("Open OR Bookings →", "OR Bookings", role, "or_full")

    st.markdown("")

    # ── Management actions ───────────────────────────────────────────────────
    _render_mgmt_actions(dept_df, api_offline)

    # ── Footer ───────────────────────────────────────────────────────────────
    _render_footer(fs)
