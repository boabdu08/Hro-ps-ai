"""Operational live-state utilities.

These helpers centralize time-aware logic used across:
- Shifts (StaffShift / StaffSchedule)
- Appointments
- OR Bookings
- Patient Tracking
- Optimizer inputs / Department Status

Design goals:
- Keep existing architecture (DB-first, Streamlit reads DB directly)
- Avoid UI-side random/static values
- Provide an hourly simulation path when real integrations are not connected
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Tuple

import pandas as pd


SHIFT_WINDOWS = {
    "Morning": (time(8, 0), time(16, 0)),
    "Evening": (time(16, 0), time(0, 0)),
    "Night": (time(0, 0), time(8, 0)),
}


APPOINTMENT_STATUS_MAP = {
    # Legacy/old -> new canonical
    "open": "Scheduled",
    "busy": "Scheduled",
    "restricted intake": "Reschedule Required",
    "review required": "Reschedule Required",
    "reschedule suggested": "Reschedule Required",
    "reschedule required": "Reschedule Required",
    "scheduled": "Scheduled",
    "checked in": "Checked In",
    "waiting": "Waiting",
    "in consultation": "In Consultation",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "no show": "No Show",
    "noshow": "No Show",
}


def today_str(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.date().strftime("%Y-%m-%d")


def hour_bucket(now: datetime | None = None) -> datetime:
    """Round down to the hour (used for 'hourly live' state)."""

    now = now or datetime.now()
    return now.replace(minute=0, second=0, microsecond=0)


def parse_hhmm(value: str) -> time | None:
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except Exception:
            continue
    return None


def shift_times_for_type(shift_type: str) -> Tuple[str, str]:
    stype = str(shift_type or "").strip().title()
    start, end = SHIFT_WINDOWS.get(stype, (time(8, 0), time(16, 0)))
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def is_time_in_shift(*, now: datetime, shift_type: str) -> bool:
    stype = str(shift_type or "").strip().title()
    start, end = SHIFT_WINDOWS.get(stype, (time(8, 0), time(16, 0)))
    t = now.time()

    # Window that crosses midnight (Evening: 16->00)
    if end == time(0, 0) and start != time(0, 0):
        return t >= start or t < end
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def current_shift_type(now: datetime | None = None) -> str:
    now = now or datetime.now()
    for stype, (start, end) in SHIFT_WINDOWS.items():
        # Reuse same midnight-cross logic.
        if is_time_in_shift(now=now, shift_type=stype):
            return stype
    return "Morning"


def normalize_appointment_status(status: str) -> str:
    raw = str(status or "").strip()
    if not raw:
        return "Scheduled"
    key = raw.lower()
    return APPOINTMENT_STATUS_MAP.get(key, raw)


def dedupe_keep_latest(
    df: pd.DataFrame,
    *,
    logical_keys: list[str],
    latest_by: str | None = None,
) -> pd.DataFrame:
    """Remove duplicate rows and keep the latest record.

    If latest_by is None, we keep the last row in the existing order.
    """

    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    for k in logical_keys:
        if k not in out.columns:
            out[k] = ""

    # Prefer deterministic "latest" behavior:
    # - if the caller provides latest_by and it exists -> sort by it
    # - else if an auto-increment id exists -> use it
    # - else keep existing order
    if latest_by is None and "id" in out.columns:
        latest_by = "id"

    if latest_by and latest_by in out.columns:
        # Try to sort by the latest_by column (string compare is OK for ISO dates,
        # numeric compare is OK for autoincrement ids).
        out = out.sort_values(by=latest_by, ascending=True, kind="mergesort")

    # Drop duplicates keeping the last (latest) record.
    out = out.drop_duplicates(subset=logical_keys, keep="last").reset_index(drop=True)
    return out


@dataclass
class LiveState:
    now: datetime
    today: str
    current_shift: str


def build_live_state(now: datetime | None = None) -> LiveState:
    now = now or datetime.now()
    return LiveState(now=now, today=today_str(now), current_shift=current_shift_type(now))
