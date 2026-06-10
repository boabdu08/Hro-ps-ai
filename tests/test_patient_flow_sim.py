"""Tests for patient_flow_sim — admission -> LOS -> discharge census simulation."""

import numpy as np
import pytest

from patient_flow_sim import (
    DEFAULT_LOS_HOURS,
    FlowSimConfig,
    FlowSimResult,
    simulate_by_department,
    simulate_patient_flow,
)


class TestConfigValidation:
    def test_rejects_zero_los(self):
        with pytest.raises(ValueError):
            FlowSimConfig(mean_los_hours=0)

    def test_rejects_negative_cv(self):
        with pytest.raises(ValueError):
            FlowSimConfig(los_cv=-0.1)

    def test_default_los_covers_all_departments(self):
        assert set(DEFAULT_LOS_HOURS) == {"ER", "ICU", "General Ward", "Surgery", "Radiology"}
        assert all(v > 0 for v in DEFAULT_LOS_HOURS.values())


class TestSimulationBasics:
    def test_empty_arrivals_returns_empty_result(self):
        result = simulate_patient_flow([])
        assert isinstance(result, FlowSimResult)
        assert result.census == []
        assert result.peak_census == 0.0

    def test_output_lengths_match_horizon(self):
        arrivals = [10.0] * 72
        result = simulate_patient_flow(arrivals)
        assert len(result.census) == 72
        assert len(result.admissions) == 72
        assert len(result.discharges) == 72
        assert len(result.overflow) == 72

    def test_census_never_negative(self):
        arrivals = [5.0, 0.0, 0.0, 20.0, 0.0] * 10
        result = simulate_patient_flow(arrivals)
        assert all(c >= 0 for c in result.census)

    def test_negative_arrivals_treated_as_zero(self):
        result = simulate_patient_flow([-5.0] * 24)
        assert result.peak_census == 0.0
        assert result.total_overflow == 0.0

    def test_deterministic_with_same_seed(self):
        arrivals = list(np.linspace(5, 25, 48))
        r1 = simulate_patient_flow(arrivals, FlowSimConfig(seed=7))
        r2 = simulate_patient_flow(arrivals, FlowSimConfig(seed=7))
        assert r1.census == r2.census
        assert r1.discharges == r2.discharges

    def test_census_accumulates_with_long_los(self):
        # 10 arrivals/hour with a 96h LOS: census must keep growing over 24h
        # because nobody is discharged within the window.
        cfg = FlowSimConfig(mean_los_hours=96.0, los_cv=0.0)
        result = simulate_patient_flow([10.0] * 24, cfg)
        assert result.census[-1] > result.census[0]
        assert result.census[-1] == pytest.approx(240.0, abs=1.0)

    def test_short_los_reaches_steady_state(self):
        # 10/hour with deterministic 5h LOS -> census stabilises near 50.
        cfg = FlowSimConfig(mean_los_hours=5.0, los_cv=0.0)
        result = simulate_patient_flow([10.0] * 72, cfg)
        assert result.census[-1] == pytest.approx(50.0, abs=5.0)

    def test_to_frame_columns(self):
        df = simulate_patient_flow([3.0] * 12).to_frame()
        assert list(df.columns) == ["hour", "admissions", "discharges", "census", "overflow"]
        assert len(df) == 12


class TestCapacityAndOverflow:
    def test_capacity_caps_census(self):
        cfg = FlowSimConfig(mean_los_hours=96.0, los_cv=0.0, bed_capacity=40)
        result = simulate_patient_flow([10.0] * 24, cfg)
        assert max(result.census) <= 40.0

    def test_overflow_recorded_when_demand_exceeds_capacity(self):
        cfg = FlowSimConfig(mean_los_hours=96.0, los_cv=0.0, bed_capacity=40)
        result = simulate_patient_flow([10.0] * 24, cfg)
        assert result.total_overflow > 0

    def test_no_overflow_without_capacity_limit(self):
        result = simulate_patient_flow([50.0] * 24, FlowSimConfig(mean_los_hours=96.0))
        assert result.total_overflow == 0.0

    def test_initial_census_respected(self):
        cfg = FlowSimConfig(initial_census=30, mean_los_hours=48.0)
        result = simulate_patient_flow([0.0] * 6, cfg)
        # With zero arrivals, census starts at/below 30 and never rises.
        assert result.census[0] <= 30.0
        assert all(result.census[i] >= result.census[i + 1] for i in range(len(result.census) - 1))


class TestDepartmentSimulation:
    def test_runs_per_department(self):
        arrivals = {"ER": [20.0] * 24, "ICU": [3.0] * 24}
        results = simulate_by_department(arrivals)
        assert set(results) == {"ER", "ICU"}
        assert all(isinstance(r, FlowSimResult) for r in results.values())

    def test_icu_census_higher_relative_to_arrivals_than_er(self):
        # ICU LOS (96h) >> ER LOS (6h): same arrivals should accumulate a much
        # larger ICU census than ER census.
        arrivals = {"ER": [5.0] * 72, "ICU": [5.0] * 72}
        results = simulate_by_department(arrivals)
        assert results["ICU"].peak_census > results["ER"].peak_census

    def test_capacity_mapping_applied(self):
        arrivals = {"ICU": [10.0] * 48}
        results = simulate_by_department(arrivals, bed_capacity={"ICU": 28})
        assert max(results["ICU"].census) <= 28.0
        assert results["ICU"].total_overflow > 0
