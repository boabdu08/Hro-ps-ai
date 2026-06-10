"""Tests for drift_detection — PSI input drift + rolling-MAE performance drift."""

import numpy as np
import pytest

from drift_detection import (
    CANONICAL_TEST_MAE,
    DriftReport,
    detect_drift,
    population_stability_index,
)


RNG = np.random.default_rng(123)
REFERENCE = list(RNG.normal(loc=190.0, scale=20.0, size=720))  # 30 days hourly


class TestPSI:
    def test_identical_distributions_near_zero(self):
        psi = population_stability_index(REFERENCE, REFERENCE)
        assert psi < 0.01

    def test_same_distribution_sample_is_stable(self):
        live = list(RNG.normal(loc=190.0, scale=20.0, size=168))
        psi = population_stability_index(REFERENCE, live)
        assert psi < 0.10

    def test_shifted_distribution_is_flagged(self):
        live = list(RNG.normal(loc=280.0, scale=20.0, size=168))  # +4.5 sigma shift
        psi = population_stability_index(REFERENCE, live)
        assert psi > 0.25

    def test_requires_enough_reference_points(self):
        with pytest.raises(ValueError):
            population_stability_index([1.0, 2.0], [1.0])

    def test_constant_reference_does_not_crash(self):
        psi = population_stability_index([100.0] * 50, [100.0] * 10)
        assert psi == 0.0


class TestDetectDrift:
    def test_stable_input_no_errors(self):
        live = list(RNG.normal(loc=190.0, scale=20.0, size=168))
        report = detect_drift(REFERENCE, live)
        assert isinstance(report, DriftReport)
        assert report.psi_status == "stable"
        assert report.performance_status == "unknown"
        assert report.drifted is False

    def test_major_input_shift_sets_drifted(self):
        live = list(RNG.normal(loc=300.0, scale=20.0, size=168))
        report = detect_drift(REFERENCE, live)
        assert report.psi_status == "major"
        assert report.drifted is True
        assert any("major input shift" in n for n in report.notes)

    def test_performance_ok_when_rolling_mae_near_canonical(self):
        live = list(RNG.normal(loc=190.0, scale=20.0, size=168))
        errors = list(np.abs(RNG.normal(loc=0.0, scale=CANONICAL_TEST_MAE, size=72)))
        report = detect_drift(REFERENCE, live, rolling_abs_errors=errors)
        assert report.performance_status == "ok"
        assert report.rolling_mae is not None
        assert report.mae_ratio is not None

    def test_performance_degraded_when_mae_exceeds_2x(self):
        live = list(RNG.normal(loc=190.0, scale=20.0, size=168))
        errors = [CANONICAL_TEST_MAE * 3.0] * 72  # 3x canonical MAE
        report = detect_drift(REFERENCE, live, rolling_abs_errors=errors)
        assert report.performance_status == "degraded"
        assert report.drifted is True

    def test_mean_shift_z_computed(self):
        live = list(RNG.normal(loc=250.0, scale=20.0, size=168))  # 3 sigma shift
        report = detect_drift(REFERENCE, live)
        assert report.mean_shift_z > 2.0

    def test_custom_degradation_ratio(self):
        live = list(RNG.normal(loc=190.0, scale=20.0, size=168))
        errors = [CANONICAL_TEST_MAE * 1.5] * 72
        strict = detect_drift(REFERENCE, live, rolling_abs_errors=errors, mae_degradation_ratio=1.2)
        lenient = detect_drift(REFERENCE, live, rolling_abs_errors=errors, mae_degradation_ratio=2.0)
        assert strict.performance_status == "degraded"
        assert lenient.performance_status == "ok"
