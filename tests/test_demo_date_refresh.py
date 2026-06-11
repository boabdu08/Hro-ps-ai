"""Regression tests for the Appts (7-day) = 0 bug and scripts/refresh_demo_dates.py.

The Home KPI filters appointments to [today, today+7]; the demo CSVs are
anchored to a fixed week, so once real time passes the window the KPI showed 0.
The refresh script shifts date columns by whole weeks so today falls inside.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from refresh_demo_dates import TARGETS, _weeks_to_shift  # noqa: E402

EXPORT_DIR = Path("data/updated_exports")


def _kpi_count(dates: pd.Series, today: date) -> int:
    """Exact windowing logic used by home_section.py line ~376."""
    w = (dates.dt.date >= today) & (dates.dt.date <= today + timedelta(days=7))
    return int(w.sum())


class TestWeeksToShift:
    def test_today_inside_window_no_shift(self):
        assert _weeks_to_shift(date(2026, 6, 6), date(2026, 6, 19), date(2026, 6, 11)) == 0

    def test_stale_window_shifts_forward_whole_weeks(self):
        # Original bug: window 2026-05-16..29, today 2026-06-11 -> +3 weeks
        w = _weeks_to_shift(date(2026, 5, 16), date(2026, 5, 29), date(2026, 6, 11))
        assert w == 3
        assert date(2026, 5, 16) + timedelta(weeks=w) <= date(2026, 6, 11) <= date(2026, 5, 29) + timedelta(weeks=w)

    def test_future_window_shifts_backward(self):
        # Overshoot case: window starts after today -> negative whole weeks
        w = _weeks_to_shift(date(2026, 6, 13), date(2026, 6, 26), date(2026, 6, 11))
        assert w == -1

    def test_shift_preserves_weekday(self):
        d = date(2026, 5, 16)  # Saturday
        w = _weeks_to_shift(d, d + timedelta(days=13), date(2026, 6, 11))
        assert (d + timedelta(weeks=w)).weekday() == d.weekday()

    def test_far_stale_window_lands_today_inside(self):
        for days_ago in (30, 90, 365):
            today = date(2026, 6, 11)
            dmin = today - timedelta(days=days_ago)
            dmax = dmin + timedelta(days=13)
            w = _weeks_to_shift(dmin, dmax, today)
            assert dmin + timedelta(weeks=w) <= today <= dmax + timedelta(weeks=w)


class TestKpiWindowAgainstRefreshedData:
    """Apply the shift in-memory so this test never goes stale itself."""

    @pytest.mark.parametrize("fname,col", [("appointments_updated.csv", "date"),
                                           ("or_bookings.csv", "date"),
                                           ("staff_schedule.csv", "shift_date")])
    def test_window_count_positive_after_refresh_logic(self, fname, col):
        path = EXPORT_DIR / fname
        assert path.exists(), f"missing demo CSV: {path}"
        df = pd.read_csv(path)
        dates = pd.to_datetime(df[col], errors="coerce").dropna()
        assert not dates.empty

        today = date.today()
        weeks = _weeks_to_shift(dates.min().date(), dates.max().date(), today)
        shifted = dates + pd.Timedelta(weeks=weeks)
        assert _kpi_count(shifted, today) > 0, (
            f"{fname}: 7-day window empty even after whole-week shift — "
            "the Appts (7-day)=0 bug has regressed"
        )

    def test_targets_never_include_canonical_paths(self):
        for fname in TARGETS:
            assert "artifact" not in fname.lower()
            assert "clean_data" not in fname.lower()


class TestUnitWindowingStraddlingToday:
    def test_fixture_straddling_today(self):
        today = date.today()
        dates = pd.Series(pd.to_datetime([
            today - timedelta(days=3),   # past — excluded
            today,                       # included
            today + timedelta(days=3),   # included
            today + timedelta(days=7),   # boundary — included
            today + timedelta(days=8),   # beyond — excluded
        ]))
        assert _kpi_count(dates, today) == 3
