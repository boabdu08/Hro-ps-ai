"""Forecasting pipeline using the *updated hospital operational data model*.

Goal (per product requirements):
  - Train & evaluate LSTM, ARIMAX, and Hybrid (weighted ensemble) forecasts
  - Forecast horizon: next 72 hours
  - Outputs: overall hospital forecast + department-level forecast

IMPORTANT ARCHITECTURE NOTE
---------------------------
The project already has a 24-hour roll-forward forecast used by Command Center.
We do NOT change that pipeline or its artifacts.

This module introduces a *separate* 72-hour forecasting dataset + artifacts so
we can safely evolve the forecasting logic without breaking existing tabs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from database import SessionLocal
from models import Appointment, ORBooking, PatientFlow, PatientTracking, StaffShift
from ops_live import is_time_in_shift


# ---------------------------
# Paths / outputs
# ---------------------------


ARTIFACT_DIR = Path("artifacts").resolve()
DATA_DIR = ARTIFACT_DIR / "datasets"
MODEL_DIR = ARTIFACT_DIR / "models_72h"
METRICS_DIR = ARTIFACT_DIR / "metrics_72h"
UPDATED_EXPORT_DIR = Path("data") / "updated_exports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_dt(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    ts = pd.to_datetime(s, errors="coerce")
    return None if pd.isna(ts) else ts


def _hour_floor(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.floor("h")


def _normalize_text(v) -> str:
    return str(v or "").strip()


def _time_slot_to_hour_start(date_str: str, time_slot: str) -> pd.Timestamp | None:
    """Convert a `YYYY-MM-DD` + time_slot like '08:00-10:00' to hourly bucket start."""

    date_str = _normalize_text(date_str)
    time_slot = _normalize_text(time_slot)
    if not date_str or not time_slot or "-" not in time_slot:
        return None
    start = time_slot.split("-")[0].strip()
    try:
        return pd.to_datetime(f"{date_str} {start}", errors="raise").floor("h")
    except Exception:
        return None


def _add_standard_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure training-time features required by the 72h model scripts exist."""

    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    out = out.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    out["patients"] = pd.to_numeric(out.get("patients", 0.0), errors="coerce").fillna(0.0)

    out["hour"] = out["datetime"].dt.hour.astype(int)
    out["day_of_week"] = out["datetime"].dt.dayofweek.astype(int)
    out["month"] = out["datetime"].dt.month.astype(int)
    out["week_number"] = out["datetime"].dt.isocalendar().week.astype(int)
    out["is_weekend"] = (out["day_of_week"] >= 5).astype(int)
    out["season"] = ((out["month"] % 12) // 3).astype(int)
    out["holiday"] = pd.to_numeric(out.get("holiday", 0), errors="coerce").fillna(0).astype(int)

    for col in ["appointments_count", "or_bookings_count", "doctors_available", "nurses_available", "occupied_beds", "waiting_patients"]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    y = out["patients"].astype(float)
    out["lag_1"] = y.shift(1).fillna(0.0)
    out["lag_24"] = y.shift(24).fillna(0.0)
    for w in [3, 6, 24]:
        out[f"roll_mean_{w}"] = y.shift(1).rolling(w, min_periods=1).mean().fillna(0.0)
    return out


def _build_ops_hourly_frame_from_exports() -> OpsHourlyFrame | None:
    """Load Phase-2 exported datasets before falling back to DB tables.

    This keeps training reproducible from the manually reviewable CSVs while the
    existing DB-first runtime remains available as fallback.
    """

    overall_path = UPDATED_EXPORT_DIR / "ops_hourly_overall.csv"
    if not overall_path.exists():
        overall_path = UPDATED_EXPORT_DIR / "patient_flow_hourly_updated.csv"
    if not overall_path.exists():
        return None

    try:
        overall = pd.read_csv(overall_path)
    except Exception:
        return None
    if overall.empty or "datetime" not in overall.columns or "patients" not in overall.columns:
        return None

    overall = _add_standard_time_features(overall)
    if len(overall) < 24 * 14:
        return None

    by_dept_path = UPDATED_EXPORT_DIR / "ops_hourly_by_department.csv"
    if by_dept_path.exists():
        try:
            by_department = pd.read_csv(by_dept_path)
        except Exception:
            by_department = pd.DataFrame()
    else:
        by_department = pd.DataFrame()

    if by_department.empty or not {"datetime", "department", "patients"}.issubset(by_department.columns):
        shares = {"ER": 0.30, "ICU": 0.10, "General Ward": 0.45, "Surgery": 0.10, "Radiology": 0.05}
        by_department = pd.concat(
            [
                pd.DataFrame(
                    {
                        "datetime": overall["datetime"],
                        "department": dept,
                        "patients": overall["patients"].astype(float) * share,
                    }
                )
                for dept, share in shares.items()
            ],
            ignore_index=True,
        )
    else:
        by_department["datetime"] = pd.to_datetime(by_department["datetime"], errors="coerce")
        by_department = by_department.dropna(subset=["datetime"])
        by_department["patients"] = pd.to_numeric(by_department["patients"], errors="coerce").fillna(0.0)

    departments = sorted([str(d) for d in by_department["department"].dropna().unique().tolist()])
    return OpsHourlyFrame(overall=overall.reset_index(drop=True), by_department=by_department.reset_index(drop=True), departments=departments)


@dataclass
class OpsHourlyFrame:
    overall: pd.DataFrame
    by_department: pd.DataFrame
    departments: List[str]


def build_ops_hourly_frame(*, tenant_id: int | None = None) -> OpsHourlyFrame:
    """Build an hourly dataset from updated operational tables.

    Target variable (preferred):
      - demand = PatientFlow.patients per hour (already operational hourly stream)

    Fallback target:
      - arrivals = number of patient entries per hour (PatientTracking.entry_datetime)

    Department targets:
      - arrivals_department = entries per hour per department

    Exogenous variables (hourly):
      - appointments_count (sum of patient_count for appointment slots)
      - or_bookings_count
      - doctors_available_now / nurses_available_now (from StaffShift for current shift)
      - occupied_beds_now / waiting_patients_now (from PatientTracking)

    Output frames have a continuous hourly index.
    """

    exported = _build_ops_hourly_frame_from_exports()
    if exported is not None:
        return exported

    db = SessionLocal()
    try:
        # ---------------------------
        # Target series (overall demand per hour)
        # ---------------------------
        q_pf = db.query(PatientFlow)
        if tenant_id is not None:
            q_pf = q_pf.filter(PatientFlow.tenant_id == int(tenant_id))
        pf_rows = q_pf.order_by(PatientFlow.id.asc()).all()

        pf_payload = []
        for r in pf_rows:
            ts = _safe_dt(getattr(r, "datetime", None))
            if ts is None:
                continue
            pf_payload.append({"datetime": _hour_floor(ts), "demand": float(getattr(r, "patients", 0) or 0)})

        pf_df = pd.DataFrame(pf_payload)

        # PatientTracking (used for department shares + occupancy features)
        q_pt = db.query(PatientTracking)
        if tenant_id is not None:
            q_pt = q_pt.filter(PatientTracking.tenant_id == int(tenant_id))
        pt_rows = q_pt.all()

        pt_payload = []
        for r in pt_rows:
            ts = _safe_dt(getattr(r, "entry_datetime", None))
            if ts is None:
                continue
            dept = _normalize_text(getattr(r, "department", "")) or "Unknown"
            pt_payload.append({"datetime": _hour_floor(ts), "department": dept, "arrivals": 1})
        pt_df = pd.DataFrame(pt_payload)

        if not pf_df.empty:
            overall = (
                pf_df.groupby("datetime")["demand"]
                .sum()
                .reset_index()
                .sort_values("datetime")
                .reset_index(drop=True)
            )
            # Align department targets using observed PatientTracking department shares.
            # If PatientTracking is sparse, we fall back to a stable share map.
            if not pt_df.empty:
                shares = pt_df.groupby("department")["arrivals"].sum()
                shares = shares / float(shares.sum()) if float(shares.sum()) > 0 else shares
                share_map = {str(k): float(v) for k, v in shares.to_dict().items()}
            else:
                share_map = {"ER": 0.30, "ICU": 0.10, "General Ward": 0.45, "Surgery": 0.10, "Radiology": 0.05}

            departments = sorted(list(share_map.keys()))
            panel = []
            for dept in departments:
                panel.append(
                    pd.DataFrame(
                        {
                            "datetime": overall["datetime"],
                            "department": dept,
                            "demand": overall["demand"].astype(float) * float(share_map.get(dept, 0.0)),
                        }
                    )
                )
            by_department = pd.concat(panel, axis=0).reset_index(drop=True) if panel else pd.DataFrame()

            target_col = "demand"
        else:
            # Fallback: use PatientTracking hourly arrivals if PatientFlow isn't available.
            if pt_df.empty:
                return OpsHourlyFrame(overall=pd.DataFrame(), by_department=pd.DataFrame(), departments=[])

            overall = pt_df.groupby("datetime")["arrivals"].sum().reset_index().sort_values("datetime")
            by_department = (
                pt_df.groupby(["datetime", "department"])["arrivals"]
                .sum()
                .reset_index()
                .sort_values(["datetime", "department"])
                .reset_index(drop=True)
            )
            departments = sorted([str(d) for d in by_department["department"].dropna().unique().tolist()])
            target_col = "arrivals"

        # Continuous hourly index
        start = overall["datetime"].min()
        end = overall["datetime"].max()
        # Continuous hourly time index (use lowercase 'h' to avoid pandas deprecation).
        hour_index = pd.date_range(start=start, end=end, freq="h")

        overall = (
            overall.set_index("datetime")
            .reindex(hour_index)
            .fillna(0.0)
            .rename_axis("datetime")
            .reset_index()
        )
        # Keep target column name consistent for training.
        if target_col not in overall.columns:
            overall[target_col] = 0.0

        if not by_department.empty:
            # Ensure continuous panel per department.
            panel = []
            for dept in departments:
                s = by_department[by_department["department"] == dept].set_index("datetime")
                col = "demand" if "demand" in s.columns else "arrivals"
                s = s[col].reindex(hour_index).fillna(0.0)
                panel.append(pd.DataFrame({"datetime": hour_index, "department": dept, "demand": s.values.astype(float)}))
            by_department = pd.concat(panel, axis=0).reset_index(drop=True) if panel else pd.DataFrame()

        # ---------------------------
        # Exogenous hourly features
        # ---------------------------
        # Appointments -> bucketed to slot start hour.
        q_appt = db.query(Appointment)
        if tenant_id is not None:
            q_appt = q_appt.filter(Appointment.tenant_id == int(tenant_id))
        appt_rows = q_appt.all()

        appt_payload = []
        for a in appt_rows:
            hour = _time_slot_to_hour_start(_normalize_text(a.date), _normalize_text(a.time_slot))
            if hour is None:
                continue
            dept = _normalize_text(a.department) or "Unknown"
            appt_payload.append(
                {
                    "datetime": hour,
                    "department": dept,
                    "appointments_count": float(getattr(a, "patient_count", 0) or 0),
                }
            )

        appt_df = pd.DataFrame(appt_payload)
        if not appt_df.empty:
            appt_overall = appt_df.groupby("datetime")["appointments_count"].sum().reindex(hour_index).fillna(0.0)
            appt_by_dept = (
                appt_df.groupby(["datetime", "department"])["appointments_count"].sum().reset_index()
            )
        else:
            appt_overall = pd.Series(0.0, index=hour_index)
            appt_by_dept = pd.DataFrame(columns=["datetime", "department", "appointments_count"])

        # OR bookings -> bucketed to slot start hour.
        q_or = db.query(ORBooking)
        if tenant_id is not None:
            q_or = q_or.filter(ORBooking.tenant_id == int(tenant_id))
        or_rows = q_or.all()

        or_payload = []
        for r in or_rows:
            hour = _time_slot_to_hour_start(_normalize_text(r.date), _normalize_text(r.time_slot))
            if hour is None:
                continue
            dept = _normalize_text(r.department) or "Unknown"
            or_payload.append({"datetime": hour, "department": dept, "or_bookings_count": 1.0})
        or_df = pd.DataFrame(or_payload)
        if not or_df.empty:
            or_overall = or_df.groupby("datetime")["or_bookings_count"].sum().reindex(hour_index).fillna(0.0)
        else:
            or_overall = pd.Series(0.0, index=hour_index)

        # Staffing availability (approx): for each hour, count shifts active at that hour.
        q_shifts = db.query(StaffShift)
        if tenant_id is not None:
            q_shifts = q_shifts.filter(StaffShift.tenant_id == int(tenant_id))
        shift_rows = q_shifts.all()

        # We compute per-hour availability for doctors/nurses by evaluating each shift's type window.
        staffing_by_hour = []
        for ts in hour_index:
            doctors = 0
            nurses = 0
            for s in shift_rows:
                # Only consider shifts for the same date as this timestamp.
                if _normalize_text(getattr(s, "shift_date", "")) != ts.strftime("%Y-%m-%d"):
                    continue
                status = _normalize_text(getattr(s, "status", "Assigned")).lower()
                if status in {"absent", "on leave", "off", "cancelled", "cancelled shift"}:
                    continue
                if not is_time_in_shift(now=ts.to_pydatetime(), shift_type=_normalize_text(getattr(s, "shift_type", ""))):
                    continue
                role = _normalize_text(getattr(s, "role", "")).lower()
                if role == "doctor":
                    doctors += 1
                elif role == "nurse":
                    nurses += 1
            staffing_by_hour.append({"datetime": ts, "doctors_available": float(doctors), "nurses_available": float(nurses)})

        staffing_df = (
            pd.DataFrame(staffing_by_hour)
            .set_index("datetime")
            .reindex(hour_index)
            .fillna(0.0)
            .rename_axis("datetime")
            .reset_index()
        )

        # Bed occupancy / waiting patients snapshot (from PatientTracking):
        # We'll derive an approximate time series by assuming each patient occupies from entry -> discharge.
        occ_events = []
        wait_events = []
        for r in pt_rows:
            entry = _safe_dt(getattr(r, "entry_datetime", None))
            if entry is None:
                continue
            discharge = _safe_dt(getattr(r, "discharge_datetime", None))
            if discharge is None:
                # Still inside hospital => treat end as dataset end.
                discharge = end
            entry_h = _hour_floor(entry)
            discharge_h = _hour_floor(discharge)
            dept = _normalize_text(getattr(r, "department", "")) or "Unknown"
            bed_id = _normalize_text(getattr(r, "assigned_bed_id", ""))
            admission_status = _normalize_text(getattr(r, "admission_status", "")).lower()

            if bed_id:
                occ_events.append({"department": dept, "start": entry_h, "end": discharge_h})
            if admission_status == "waiting":
                wait_events.append({"department": dept, "start": entry_h, "end": discharge_h})

        def _events_to_series(events: list[dict], name: str) -> pd.DataFrame:
            if not events:
                return pd.DataFrame({"datetime": hour_index, name: np.zeros(len(hour_index), dtype=float)})
            counts = pd.Series(0.0, index=hour_index)
            for e in events:
                s = e["start"]
                eend = e["end"]
                if pd.isna(s) or pd.isna(eend):
                    continue
                mask = (hour_index >= s) & (hour_index <= eend)
                counts.loc[mask] += 1.0
            return pd.DataFrame({"datetime": hour_index, name: counts.values})

        occ_df = _events_to_series(occ_events, "occupied_beds")
        wait_df = _events_to_series(wait_events, "waiting_patients")

        # Merge exog into overall
        overall = overall.merge(staffing_df, on="datetime", how="left")
        overall["appointments_count"] = appt_overall.values
        overall["or_bookings_count"] = or_overall.values
        overall = overall.merge(occ_df, on="datetime", how="left")
        overall = overall.merge(wait_df, on="datetime", how="left")
        overall = overall.fillna(0.0)

        # Time features
        overall["hour"] = overall["datetime"].dt.hour.astype(int)
        overall["day_of_week"] = overall["datetime"].dt.dayofweek.astype(int)
        overall["month"] = overall["datetime"].dt.month.astype(int)
        overall["week_number"] = overall["datetime"].dt.isocalendar().week.astype(int)
        overall["is_weekend"] = (overall["day_of_week"] >= 5).astype(int)
        overall["season"] = ((overall["month"] % 12) // 3).astype(int)
        overall["holiday"] = 0  # optional: keep as 0 unless a holiday calendar is introduced.

        # Lag + rolling features on target
        y = overall[target_col].astype(float)
        overall["lag_1"] = y.shift(1).fillna(0.0)
        overall["lag_24"] = y.shift(24).fillna(0.0)
        for w in [3, 6, 24]:
            overall[f"roll_mean_{w}"] = y.shift(1).rolling(w, min_periods=1).mean().fillna(0.0)

        # Rename target to a single canonical name for downstream training scripts.
        overall = overall.rename(columns={target_col: "patients"})
        if not by_department.empty and "demand" in by_department.columns:
            by_department = by_department.rename(columns={"demand": "patients"})

        return OpsHourlyFrame(overall=overall.reset_index(drop=True), by_department=by_department, departments=departments)
    finally:
        db.close()


def save_ops_hourly_dataset(frame: OpsHourlyFrame) -> Dict[str, str]:
    """Persist the prepared dataset for training runs (CSV)."""

    out = {}
    if not frame.overall.empty:
        p = DATA_DIR / "ops_hourly_overall.csv"
        frame.overall.to_csv(p, index=False)
        out["overall"] = str(p)
    if not frame.by_department.empty:
        p = DATA_DIR / "ops_hourly_by_department.csv"
        frame.by_department.to_csv(p, index=False)
        out["by_department"] = str(p)
    return out
