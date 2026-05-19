"""
Home tab — Hospital AI Command Center.

UI-only premium overview. Reads from:
  - ForecastState artifacts (cached via dashboard_sections)
  - Operational CSVs: department_status, appointments, or_bookings, staff_master
  - No live API calls. No DB queries. No model training.
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
# Paths
# ---------------------------------------------------------------------------

_DEPT_STATUS_PATH = Path("data/updated_exports/department_status_updated.csv")
_APPOINTMENTS_PATH = Path("data/updated_exports/appointments_updated.csv")
_OR_BOOKINGS_PATH = Path("data/updated_exports/or_bookings.csv")
_STAFF_MASTER_PATH = Path("data/updated_exports/staff_master_data.csv")

_DEPT_ORDER = ["ER", "ICU", "General Ward", "Surgery", "Radiology"]


# ---------------------------------------------------------------------------
# Cached CSV loaders — no DB, no API, fast
# ---------------------------------------------------------------------------

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


def _kpi_status_from_pressure(level: str) -> str:
    l = str(level).lower()
    if l in {"high", "critical"}:
        return "critical"
    if l in {"moderate", "warning"}:
        return "warning"
    return "success"


def _alert_counts_from_dept(dept_df: pd.DataFrame) -> tuple[int, int]:
    """Derive (critical, warning) counts from department status CSV — no API call."""
    if dept_df.empty:
        return 0, 0
    if "department_status" in dept_df.columns:
        critical = int((dept_df["department_status"].str.lower() == "critical").sum())
        warning = int((dept_df["department_status"].str.lower() == "warning").sum())
        return critical, warning
    if "pressure_level" in dept_df.columns:
        critical = int((dept_df["pressure_level"].str.lower() == "high").sum())
        warning = int((dept_df["pressure_level"].str.lower() == "moderate").sum())
        return critical, warning
    return 0, 0


def _ordered_dept_df(dept_df: pd.DataFrame) -> pd.DataFrame:
    """Return dept_df with departments in canonical display order."""
    if dept_df.empty or "department" not in dept_df.columns:
        return dept_df
    ordered = [d for d in _DEPT_ORDER if d in dept_df["department"].values]
    other = [d for d in dept_df["department"].values if d not in _DEPT_ORDER]
    cat = pd.Categorical(dept_df["department"], categories=ordered + other, ordered=True)
    return dept_df.assign(department=cat).sort_values("department")


# ---------------------------------------------------------------------------
# Hero strip
# ---------------------------------------------------------------------------

def _render_hero(fs, now: datetime) -> None:
    model = ((fs.selected_model or "Hybrid").title()) if fs else "—"
    risk = str(fs.risk_level or "LOW").upper() if fs else "LOW"
    ts = (fs.forecast_timestamp or now.isoformat()) if fs else now.isoformat()
    is_ready = bool(fs and fs.artifact_freshness.ready)

    risk_rgb = _risk_rgba(risk)
    sys_rgb = "52,211,153" if is_ready else "251,191,36"
    sys_label = "System Online" if is_ready else "Degraded Mode"
    ts_short = (ts[:16].replace("T", " ")) if ts and len(ts) >= 16 else str(ts)
    today_label = now.strftime("%a %d %b %Y · %H:%M")

    st.markdown(
        f"""
        <div style="
          background:linear-gradient(135deg,rgba(59,130,246,0.13) 0%,rgba(20,184,166,0.09) 55%,rgba(99,102,241,0.08) 100%);
          border:1px solid rgba(59,130,246,0.22);
          border-radius:16px;
          padding:22px 26px 18px 26px;
          margin-bottom:20px;
        ">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px;">
            <div>
              <div style="font-size:1.6rem;font-weight:820;letter-spacing:-0.025em;color:var(--text);">
                Hospital AI Command Center
              </div>
              <div style="color:var(--text-2);margin-top:5px;font-size:0.94rem;">
                72-hour patient surge &nbsp;·&nbsp; resource allocation &nbsp;·&nbsp; operational pressure &nbsp;·&nbsp; {today_label}
              </div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px;">
              <span style="
                background:rgba(59,130,246,0.14);color:var(--text);
                border:1px solid rgba(59,130,246,0.26);border-radius:999px;
                padding:4px 13px;font-size:12px;font-weight:750;white-space:nowrap;">
                Model: {model}
              </span>
              <span style="
                background:rgba({risk_rgb},0.14);color:var(--text);
                border:1px solid rgba({risk_rgb},0.28);border-radius:999px;
                padding:4px 13px;font-size:12px;font-weight:750;white-space:nowrap;">
                Risk: {risk}
              </span>
              <span style="
                background:rgba({sys_rgb},0.14);color:var(--text);
                border:1px solid rgba({sys_rgb},0.28);border-radius:999px;
                padding:4px 13px;font-size:12px;font-weight:750;white-space:nowrap;">
                &#9679; {sys_label}
              </span>
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
# KPI Row 1 — Forecast KPIs
# ---------------------------------------------------------------------------

def _render_forecast_kpis(fs, dept_df: pd.DataFrame) -> None:
    section_header("Live Forecast KPIs", "Current operational state from the 72-hour AI forecast")

    cur = _safe_int(fs.current_patients if fs else None)
    nxt = _safe_int(fs.predicted_patients_next_hour if fs else None)
    pk24 = _safe_int(fs.peak_24h if fs else None)
    pk72 = _safe_int(fs.peak_72h if fs else None)
    avg72 = _safe_int(fs.avg_72h if fs else None)
    risk = str(fs.risk_level or "LOW").upper() if fs else "LOW"

    depts_high = 0
    if not dept_df.empty and "pressure_level" in dept_df.columns:
        depts_high = int((dept_df["pressure_level"].str.lower() == "high").sum())
    elif not dept_df.empty and "department_status" in dept_df.columns:
        depts_high = int((dept_df["department_status"].str.lower() == "critical").sum())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        kpi_card("Current Patients", fmt_int(cur), status="info")
    with c2:
        kpi_card("Next-Hour Forecast", fmt_int(nxt), status="info")
    with c3:
        kpi_card("24h Peak", fmt_int(pk24),
                 status="critical" if pk24 >= 120 else ("warning" if pk24 >= 80 else "success"))
    with c4:
        kpi_card("72h Peak", fmt_int(pk72),
                 status="critical" if pk72 >= 120 else ("warning" if pk72 >= 80 else "success"))
    with c5:
        kpi_card("Avg 72h Load", fmt_int(avg72), status="normal")
    with c6:
        kpi_card(
            "Depts Under Pressure", str(depts_high),
            delta=f"{depts_high} high-pressure dept{'s' if depts_high != 1 else ''}",
            status="critical" if depts_high >= 2 else ("warning" if depts_high == 1 else "success"),
        )


# ---------------------------------------------------------------------------
# KPI Row 2 — Resource KPIs
# ---------------------------------------------------------------------------

def _render_resource_kpis(dept_df: pd.DataFrame, appt_df: pd.DataFrame, or_df: pd.DataFrame) -> None:
    section_header("Resource Snapshot", "Beds, staff, and scheduled workload")

    avail_beds = total_beds = avail_docs = avail_nurses = 0
    if not dept_df.empty:
        avail_beds = _safe_sum(dept_df.get("available_beds", pd.Series(dtype=float)))
        total_beds = _safe_sum(dept_df.get("total_beds", pd.Series(dtype=float)))
        avail_docs = _safe_sum(dept_df.get("available_doctors", pd.Series(dtype=float)))
        avail_nurses = _safe_sum(dept_df.get("available_nurses", pd.Series(dtype=float)))

    occupied = total_beds - avail_beds
    occ_pct = f"{int(round(occupied / total_beds * 100))}%" if total_beds > 0 else "—"
    beds_label = f"{avail_beds} / {total_beds}"
    beds_status = "critical" if avail_beds < 10 else ("warning" if avail_beds < 20 else "success")

    # Upcoming appointments (next 7 days)
    today = datetime.now().date()
    appt_count = 0
    if not appt_df.empty:
        if "date" in appt_df.columns and pd.api.types.is_datetime64_any_dtype(appt_df["date"]):
            window = (appt_df["date"].dt.date >= today) & (appt_df["date"].dt.date <= today + timedelta(days=7))
            appt_count = int(window.sum())
        else:
            appt_count = len(appt_df)

    # Scheduled OR bookings
    or_count = 0
    if not or_df.empty:
        if "status" in or_df.columns:
            or_count = int(or_df["status"].str.lower().isin({"scheduled", "booked", "confirmed"}).sum())
        else:
            or_count = len(or_df)

    # Alerts from dept status (no API call)
    critical_n, warning_n = _alert_counts_from_dept(dept_df)
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


# ---------------------------------------------------------------------------
# Chart: 72-hour forecast
# ---------------------------------------------------------------------------

def _render_forecast_chart(fs, horizon: int) -> None:
    section_header(
        f"Patient Demand Forecast — {horizon}h",
        "AI hybrid model prediction with risk threshold bands",
    )
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
    y_max = max(max_v * 1.12, 135)

    tmpl = plotly_template_name()
    fig = go.Figure()

    # Threshold bands
    fig.add_hrect(y0=0, y1=80, fillcolor="rgba(52,211,153,0.06)", line_width=0)
    fig.add_hrect(y0=80, y1=120, fillcolor="rgba(251,191,36,0.07)", line_width=0)
    if y_max > 118:
        fig.add_hrect(y0=120, y1=y_max, fillcolor="rgba(251,113,133,0.07)", line_width=0)
    fig.add_hline(y=80, line_dash="dot", line_color="rgba(251,191,36,0.5)",
                  annotation_text="Monitor (80)", annotation_position="right",
                  annotation_font_size=11)
    fig.add_hline(y=120, line_dash="dot", line_color="rgba(251,113,133,0.55)",
                  annotation_text="Critical (120)", annotation_position="right",
                  annotation_font_size=11)

    # Optional component model lines
    for col, label, color in [
        ("lstm_pred", "LSTM", "rgba(45,212,191,0.55)"),
        ("arimax_pred", "ARIMAX", "rgba(129,140,248,0.50)"),
    ]:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            if not vals.isna().all():
                fig.add_trace(go.Scatter(
                    x=df["datetime"], y=vals,
                    mode="lines", name=label,
                    line=dict(color=color, width=1.5, dash="dot"),
                    hovertemplate=f"{label}: %{{y:.0f}}<extra></extra>",
                ))

    # Hybrid forecast — filled area
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=hybrid,
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.10)",
        mode="lines",
        name="Hybrid Forecast",
        line=dict(color="rgba(59,130,246,0.90)", width=2.5),
        hovertemplate="<b>%{y:.0f}</b> patients &nbsp;%{x|%a %H:%M}<extra></extra>",
    ))

    fig.update_layout(
        template=tmpl,
        height=340,
        margin=dict(l=0, r=72, t=14, b=0),
        xaxis_title=None,
        yaxis=dict(title="Patients", range=[0, y_max]),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "fc_chart", str(horizon)))


# ---------------------------------------------------------------------------
# Chart: Department pressure (bar, horizontal-style via vertical bar with color)
# ---------------------------------------------------------------------------

def _render_dept_pressure_chart(dept_df: pd.DataFrame) -> None:
    section_header("Department Pressure", "Occupancy rate and status by department")
    if dept_df.empty:
        empty_state("Department status data not available.")
        return

    df = _ordered_dept_df(dept_df.copy())
    if "department" not in df.columns:
        empty_state("Department column missing.")
        return

    metric_col = "occupancy_rate" if "occupancy_rate" in df.columns else "current_patients"
    pressure_col = "pressure_level" if "pressure_level" in df.columns else "department_status"

    df["_color"] = df[pressure_col].apply(_pressure_color) if pressure_col in df.columns else "#94A3B8"

    y_vals = df[metric_col] * 100 if metric_col == "occupancy_rate" else df[metric_col]
    y_vals = pd.to_numeric(y_vals, errors="coerce").fillna(0)
    text_vals = y_vals.apply(
        lambda v: f"{v:.0f}%" if metric_col == "occupancy_rate" else f"{int(v)}"
    )
    hover = (
        "%{x}<br>Occupancy: %{y:.1f}%<extra></extra>"
        if metric_col == "occupancy_rate"
        else "%{x}<br>Patients: %{y:.0f}<extra></extra>"
    )
    y_label = "Occupancy (%)" if metric_col == "occupancy_rate" else "Current Patients"
    y_max = 115 if metric_col == "occupancy_rate" else None

    tmpl = plotly_template_name()
    fig = go.Figure(go.Bar(
        x=df["department"].astype(str),
        y=y_vals,
        marker_color=df["_color"],
        text=text_vals,
        textposition="outside",
        hovertemplate=hover,
    ))
    if metric_col == "occupancy_rate":
        fig.add_hline(y=85, line_dash="dash", line_color="rgba(251,191,36,0.65)",
                      annotation_text="85% threshold", annotation_font_size=11)
    fig.update_layout(
        template=tmpl,
        height=340,
        margin=dict(l=0, r=24, t=14, b=0),
        xaxis_title=None,
        yaxis=dict(title=y_label, range=[0, y_max] if y_max else None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "dept_pressure"))


# ---------------------------------------------------------------------------
# Table: Department status grid
# ---------------------------------------------------------------------------

def _render_dept_status_grid(dept_df: pd.DataFrame) -> None:
    section_header("Department Status", "Beds, doctors, nurses — shortages highlighted")
    if dept_df.empty:
        empty_state("No department data.")
        return

    df = _ordered_dept_df(dept_df.copy())
    want = [
        "department", "current_patients", "available_beds", "bed_shortage",
        "doctor_shortage", "nurse_shortage", "pressure_level", "department_status",
    ]
    cols = [c for c in want if c in df.columns]
    display = df[cols].rename(columns={
        "department": "Dept",
        "current_patients": "Patients",
        "available_beds": "Free Beds",
        "bed_shortage": "Bed Gap",
        "doctor_shortage": "Dr Gap",
        "nurse_shortage": "RN Gap",
        "pressure_level": "Pressure",
        "department_status": "Status",
    })
    st.dataframe(display, use_container_width=True, hide_index=True,
                 key=scoped_key("home", "dept_table"))


# ---------------------------------------------------------------------------
# Chart: Resource shortage by department
# ---------------------------------------------------------------------------

def _render_shortage_chart(dept_df: pd.DataFrame) -> None:
    section_header("Resource Shortage Ranking", "Staff and bed gaps by department")
    if dept_df.empty:
        empty_state("No resource data.")
        return

    df = _ordered_dept_df(dept_df.copy())
    shortage_cols = [c for c in ["bed_shortage", "doctor_shortage", "nurse_shortage"] if c in df.columns]
    if not shortage_cols or "department" not in df.columns:
        empty_state("Shortage columns not available in data.")
        return

    melt = df[["department"] + shortage_cols].melt(
        id_vars="department", var_name="Resource", value_name="Shortage"
    )
    melt["Resource"] = (
        melt["Resource"]
        .str.replace("_shortage", "", regex=False)
        .str.title()
    )
    melt["Shortage"] = pd.to_numeric(melt["Shortage"], errors="coerce").fillna(0).clip(lower=0)

    color_map = {"Bed": "#60A5FA", "Doctor": "#34D399", "Nurse": "#FBBF24"}
    tmpl = plotly_template_name()
    fig = px.bar(
        melt, x="department", y="Shortage", color="Resource",
        barmode="group",
        color_discrete_map=color_map,
        template=tmpl,
        labels={"department": "", "Shortage": "Units short"},
    )
    fig.update_layout(
        height=280,
        margin=dict(l=0, r=10, t=14, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    title_text=""),
    )
    st.plotly_chart(fig, use_container_width=True, key=scoped_key("home", "shortage_chart"))


# ---------------------------------------------------------------------------
# Snapshot: Upcoming Appointments
# ---------------------------------------------------------------------------

def _render_appt_snapshot(appt_df: pd.DataFrame) -> None:
    section_header("Upcoming Appointments", "Next 7 days — top scheduled slots")
    if appt_df.empty:
        empty_state("No appointment data available.")
        return

    today = datetime.now().date()
    df = appt_df.copy()
    if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
        window = (df["date"].dt.date >= today) & (df["date"].dt.date <= today + timedelta(days=7))
        filtered = df[window]
        df = filtered if not filtered.empty else df
    if "date" in df.columns:
        df = df.sort_values("date")
    df = df.head(5)

    show = [c for c in ["department", "doctor", "date", "time_slot", "patient_count", "status"] if c in df.columns]
    if "date" in show and pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(df[show], use_container_width=True, hide_index=True,
                 key=scoped_key("home", "appt_table"))


# ---------------------------------------------------------------------------
# Snapshot: OR Bookings
# ---------------------------------------------------------------------------

def _render_or_snapshot(or_df: pd.DataFrame) -> None:
    section_header("OR Bookings Snapshot", "Upcoming scheduled procedures")
    if or_df.empty:
        empty_state("No OR booking data available.")
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
    st.dataframe(df[show], use_container_width=True, hide_index=True,
                 key=scoped_key("home", "or_table"))


# ---------------------------------------------------------------------------
# Footer: Model accuracy + navigation hint
# ---------------------------------------------------------------------------

def _render_footer(fs) -> None:
    mae_s = rmse_s = mape_s = "—"
    model_name = (fs.selected_model or "Hybrid") if fs else "Hybrid"
    weights = (fs.model_weights or {}) if fs else {}
    lstm_w = weights.get("lstm", weights.get("LSTM", 0.80))
    arimax_w = weights.get("arimax", weights.get("ARIMAX", 0.20))

    # Try ForecastState metrics first (already loaded), fall back to cached metrics df
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
            try:
                mae_s = fmt_mae_rmse(float(row.get("MAE", row.get("mae", 0))))
            except Exception:
                pass
            try:
                rmse_s = fmt_mae_rmse(float(row.get("RMSE", row.get("rmse", 0))))
            except Exception:
                pass
            try:
                mape_s = fmt_mape(float(row.get("MAPE", row.get("mape", 0))))
            except Exception:
                pass

    st.markdown("---")
    st.caption(
        f"Forecast accuracy — {model_name}: "
        f"MAE {mae_s} pts · RMSE {rmse_s} pts · "
        f"MAPE {mape_s} (caution — not primary metric) · "
        f"Blend weights: LSTM {lstm_w:.0%} / ARIMAX {arimax_w:.0%}"
    )
    st.caption(
        "Use the detailed tabs for: Forecast · Digital Twin · Optimization · "
        "Shifts · Appointments · OR Bookings · Evaluation · Explainability · "
        "Approvals · Audit · Messages · Notifications"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_home() -> None:
    """Render the Home tab — Hospital AI Command Center overview."""

    now = datetime.now()

    # Load ForecastState (cached, reads 4 small CSVs)
    with st.spinner("Loading system overview..."):
        try:
            fs = _cached_artifact_forecast_state()
        except Exception:
            fs = None

    # Load operational CSVs (all cached, small files, no API)
    dept_df = _home_dept_status()
    appt_df = _home_appointments()
    or_df = _home_or_bookings()

    # --- Display options (collapsed by default) ---
    with st.expander("Display options", expanded=False):
        ctl_l, ctl_r = st.columns(2)
        with ctl_l:
            horizon = st.selectbox(
                "Forecast horizon",
                [24, 48, 72],
                index=2,
                key=scoped_key("home", "horizon"),
                help="How many hours of the 72-hour forecast to show in the chart",
            )
        with ctl_r:
            dept_options = ["All departments"]
            if not dept_df.empty and "department" in dept_df.columns:
                dept_options += sorted(dept_df["department"].dropna().unique().tolist())
            selected_dept = st.selectbox(
                "Department filter",
                dept_options,
                key=scoped_key("home", "dept_filter"),
                help="Filter department charts and tables to a single department",
            )

    # Apply department filter
    view_dept_df = dept_df
    if selected_dept != "All departments" and not dept_df.empty and "department" in dept_df.columns:
        view_dept_df = dept_df[dept_df["department"] == selected_dept].copy()

    # ── Hero strip ──────────────────────────────────────────────────────────
    _render_hero(fs, now)

    # ── KPI Row 1: Forecast ──────────────────────────────────────────────
    _render_forecast_kpis(fs, dept_df)
    st.markdown("")

    # ── KPI Row 2: Resources ─────────────────────────────────────────────
    _render_resource_kpis(dept_df, appt_df, or_df)
    st.markdown("")

    # ── Charts: Forecast (wide) + Dept pressure (narrower) ──────────────
    ch_l, ch_r = st.columns([6, 4], gap="medium")
    with ch_l:
        _render_forecast_chart(fs, horizon)
    with ch_r:
        _render_dept_pressure_chart(view_dept_df)

    st.markdown("")

    # ── Operational grid: Dept table + Shortage chart ────────────────────
    g1, g2 = st.columns([5, 5], gap="medium")
    with g1:
        _render_dept_status_grid(view_dept_df)
    with g2:
        _render_shortage_chart(view_dept_df)

    st.markdown("")

    # ── Snapshots: Appointments + OR bookings ─────────────────────────────
    s1, s2 = st.columns(2, gap="medium")
    with s1:
        _render_appt_snapshot(appt_df)
    with s2:
        _render_or_snapshot(or_df)

    # ── Footer: accuracy + navigation ─────────────────────────────────────
    _render_footer(fs)
