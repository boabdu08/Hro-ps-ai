"""Tests for ops_insights — briefing, census projection, saturation, model health."""

from datetime import datetime

import pytest

from ops_insights import (
    CensusProjection,
    build_briefing,
    load_bands,
    model_health,
    project_census,
    saturation_label,
)

NOW = datetime(2026, 6, 12, 9, 0)


class TestCensusProjection:
    def test_returns_full_horizon(self):
        proj = project_census([100.0] * 72, staffed_beds=172, initial_census=129)
        assert isinstance(proj, CensusProjection)
        assert len(proj.census) == 72
        assert len(proj.overflow) == 72

    def test_high_demand_saturates(self):
        # 100 arrivals/h with 24h LOS against 172 staffed beds must breach quickly.
        proj = project_census([100.0] * 72, staffed_beds=172, initial_census=129)
        assert proj.hours_to_saturation is not None
        assert proj.hours_to_saturation < 24
        assert proj.peak_census > 172

    def test_low_demand_never_saturates(self):
        proj = project_census([2.0] * 72, staffed_beds=172, initial_census=20, mean_los_hours=6.0)
        assert proj.hours_to_saturation is None
        assert max(proj.overflow) == 0.0

    def test_overflow_consistent_with_census(self):
        proj = project_census([80.0] * 72, staffed_beds=100, initial_census=90)
        for c, o in zip(proj.census, proj.overflow):
            assert o == pytest.approx(max(0.0, c - 100), abs=0.11)

    def test_deterministic(self):
        a = project_census([50.0] * 48, staffed_beds=150, initial_census=100)
        b = project_census([50.0] * 48, staffed_beds=150, initial_census=100)
        assert a.census == b.census

    def test_rejects_zero_beds(self):
        with pytest.raises(ValueError):
            project_census([10.0] * 24, staffed_beds=0, initial_census=0)


class TestSaturationLabel:
    def test_none_means_safe(self):
        assert saturation_label(None) == "Not within 72 h"

    def test_zero_means_now(self):
        assert saturation_label(0) == "Already at capacity"

    def test_hours_formatted(self):
        assert saturation_label(17) == "~17 h"


class TestBriefing:
    def _full(self, **over):
        kw = dict(
            now=NOW, predicted_next_hour=101.0, peak_72h=218.4, peak_hour_offset=29,
            risk_level="medium", critical_alerts=2, warning_alerts=3,
            top_pressure_department="ER", total_bed_shortage=6,
            hours_to_saturation=17, staffed_beds=172,
        )
        kw.update(over)
        return build_briefing(**kw)

    def test_every_input_number_appears(self):
        text = " ".join(self._full())
        for token in ("101", "218", "+29", "2 critical", "3 warning", "ER", "17 h", "172"):
            assert token in text, token

    def test_no_saturation_message_when_safe(self):
        text = " ".join(self._full(hours_to_saturation=None))
        assert "stays within 172 staffed beds" in text
        assert "exceeds staffed beds" not in text

    def test_no_alerts_line(self):
        text = " ".join(self._full(critical_alerts=0, warning_alerts=0))
        assert "none active" in text

    def test_deterministic(self):
        assert self._full() == self._full()

    def test_handles_missing_forecast(self):
        lines = self._full(predicted_next_hour=None, peak_72h=None, peak_hour_offset=None)
        assert lines  # still produces alert/capacity lines
        assert all("None" not in l for l in lines)


class TestModelHealth:
    def test_stable_series_verdict(self):
        import numpy as np

        rng = np.random.default_rng(1)
        ref = list(rng.normal(190, 20, 720))
        live = list(rng.normal(190, 20, 168))
        out = model_health(ref, live, rolling_abs_errors=[8.0] * 72)
        assert out["chip_label"] == "STABLE"
        assert out["performance_status"] == "ok"
        assert out["drifted"] is False

    def test_shifted_series_flags(self):
        import numpy as np

        rng = np.random.default_rng(2)
        ref = list(rng.normal(190, 20, 720))
        live = list(rng.normal(320, 20, 168))
        out = model_health(ref, live)
        assert out["chip_label"] == "MAJOR SHIFT"
        assert out["drifted"] is True


class TestLoadBands:
    def test_bands_artifact_has_both_levels(self):
        bands = load_bands()
        assert bands is not None, "supplementary artifact missing"
        assert "band_80" in bands and "band_95" in bands
