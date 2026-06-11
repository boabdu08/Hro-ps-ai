"""Refresh demo display dates: shift dated display CSVs forward in whole weeks.

Purpose:     The demo display CSVs under data/updated_exports/ were generated
             around a fixed anchor week (2026-05-16..29). Once real "today"
             moves past that window, every "next 7 days" widget (e.g. the Home
             "Appts (7-day)" KPI) correctly counts ZERO. This script shifts the
             *date columns only* forward by whole weeks so today falls inside
             the data window again — weekday alignment preserved, all other
             values untouched.
Source:      Run manually before demo day:  python scripts/refresh_demo_dates.py
Destination: data/updated_exports/appointments_updated.csv, or_bookings.csv,
             staff_schedule.csv (date columns rewritten in place).

Safety:
* NEVER touches artifacts/, training CSVs, or anything canonical-metric related.
* Idempotent — if today is already inside a file's date window, it is skipped.
* Whole-week shifts only, so Mon stays Mon (weekday-dependent demo narratives hold).
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = REPO_ROOT / "data" / "updated_exports"

# file -> date columns to shift (date-only columns; times/values untouched)
TARGETS: dict[str, list[str]] = {
    "appointments_updated.csv": ["date"],
    "or_bookings.csv": ["booking_date", "date"],
    "staff_schedule.csv": ["shift_date"],
}

FORBIDDEN_PARTS = ("artifacts", "clean_data")  # hard guard: never touch these


def _weeks_to_shift(dmin: date, dmax: date, today: date) -> int:
    """Whole weeks to add (can be negative) so today lies within [dmin', dmax'].

    Largest whole-week shift keeping dmin' <= today; if the window is shorter
    than a week and today still overshoots dmax', nudge forward until covered.
    """

    if dmin <= today <= dmax:
        return 0
    weeks = math.floor((today - dmin).days / 7.0)
    while dmax + pd.Timedelta(weeks=weeks).to_pytimedelta() < today:
        weeks += 1
    return weeks


def refresh_file(path: Path, date_cols: list[str], today: date) -> str:
    if any(part in str(path).lower() for part in FORBIDDEN_PARTS):
        raise RuntimeError(f"Refusing to touch forbidden path: {path}")
    if not path.exists():
        return f"SKIP {path.name}: not found"

    df = pd.read_csv(path)
    present = [c for c in date_cols if c in df.columns]
    if not present:
        return f"SKIP {path.name}: no date columns {date_cols} present"

    # Use the union of all date columns to compute one consistent shift.
    all_dates = pd.concat(
        [pd.to_datetime(df[c], errors="coerce", format="%Y-%m-%d") for c in present]
    ).dropna()
    if all_dates.empty:
        return f"SKIP {path.name}: no parseable dates"

    dmin, dmax = all_dates.min().date(), all_dates.max().date()
    weeks = _weeks_to_shift(dmin, dmax, today)
    if weeks == 0:
        return f"OK   {path.name}: today {today} already within {dmin}..{dmax} — no shift"

    offset = pd.Timedelta(weeks=weeks)
    for c in present:
        parsed = pd.to_datetime(df[c], errors="coerce", format="%Y-%m-%d")
        shifted = (parsed + offset).dt.strftime("%Y-%m-%d")
        # Only overwrite rows that parsed; leave malformed cells untouched.
        df[c] = shifted.where(parsed.notna(), df[c])

    df.to_csv(path, index=False)
    return (
        f"SHIFT {path.name}: +{weeks} week(s); {dmin}..{dmax} -> "
        f"{(pd.Timestamp(dmin) + offset).date()}..{(pd.Timestamp(dmax) + offset).date()}"
    )


def refresh_db_dates(today: date | None = None, session=None) -> list[str]:
    """Shift the DB date columns the optimizer's live filters use.

    resource_optimizer.py filters Appointment.date / ORBooking.date /
    StaffShift.shift_date to *today* — stale seeded dates make the live
    operational state empty. Same whole-week shift, same idempotency.
    Dates are stored as 'YYYY-MM-DD' strings.
    """

    import sys as _sys

    _sys.path.insert(0, str(REPO_ROOT))
    from database import SessionLocal
    from models import Appointment, ORBooking, StaffShift

    today = today or datetime.now().date()
    own_session = session is None
    db = session or SessionLocal()
    lines: list[str] = []
    try:
        for model, col in ((Appointment, "date"), (ORBooking, "date"), (StaffShift, "shift_date")):
            rows = db.query(model).all()
            parsed = []
            for r in rows:
                raw = str(getattr(r, col) or "")[:10]
                try:
                    parsed.append((r, datetime.strptime(raw, "%Y-%m-%d").date()))
                except ValueError:
                    continue
            if not parsed:
                lines.append(f"SKIP DB {model.__tablename__}.{col}: no parseable dates")
                continue
            dmin = min(d for _, d in parsed)
            dmax = max(d for _, d in parsed)
            # The optimizer filters these columns with `== today`, so the most
            # recent rows must land exactly ON today: anchor dmax to today
            # (exact-day shift; weekday alignment only matters for display CSVs).
            offset_days = (today - dmax).days
            if offset_days == 0:
                lines.append(f"OK   DB {model.__tablename__}.{col}: latest rows already on {today}")
                continue
            offset = pd.Timedelta(days=offset_days).to_pytimedelta()
            for r, d in parsed:
                setattr(r, col, (d + offset).strftime("%Y-%m-%d"))
            db.commit()
            lines.append(
                f"SHIFT DB {model.__tablename__}.{col}: {len(parsed)} rows {offset_days:+d} d; "
                f"{dmin}..{dmax} -> {dmin + offset}..{dmax + offset}"
            )
    finally:
        if own_session:
            db.close()
    return lines


def main(today: date | None = None, include_db: bool = False) -> list[str]:
    today = today or datetime.now().date()
    lines = [refresh_file(EXPORT_DIR / fname, cols, today) for fname, cols in TARGETS.items()]
    if include_db:
        lines += refresh_db_dates(today)
    for line in lines:
        print(line)
    return lines


if __name__ == "__main__":
    results = main(include_db="--db" in sys.argv)
    sys.exit(0 if all(not r.startswith("ERR") for r in results) else 1)
