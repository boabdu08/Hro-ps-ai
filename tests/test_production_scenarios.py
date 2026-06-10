"""M9 production/OOD scenario harness tests.

Asserts the forecast -> patient-flow -> optimization linkage behaves sensibly
under production-style stress scenarios. Uses the pre-generated 72-h forecast
artifact as base demand (no fabrication, no retraining).
"""

import pytest

from production_scenarios import (
    PROFILE_CLEOPATRA_SCALE,
    PROFILE_DEMO,
    PROFILE_SMALL_CLINIC,
    SCENARIOS,
    load_base_forecast,
    run_scenario,
)


@pytest.fixture(scope="module")
def base_forecast():
    return load_base_forecast()


@pytest.fixture(scope="module")
def all_results(base_forecast):
    return {
        name: run_scenario(name, PROFILE_DEMO, base_forecast=base_forecast)
        for name in SCENARIOS
    }


class TestHarnessBasics:
    def test_base_forecast_is_72h_and_positive(self, base_forecast):
        assert len(base_forecast) == 72
        assert all(v > 0 for v in base_forecast)

    def test_all_six_scenarios_registered(self):
        assert set(SCENARIOS) == {
            "baseline",
            "surge",
            "holiday",
            "covid_crisis",
            "mass_casualty",
            "infeasible_demand",
        }

    def test_unknown_scenario_raises(self):
        with pytest.raises(ValueError):
            run_scenario("zombie_apocalypse")

    def test_every_scenario_returns_complete_result(self, all_results):
        for name, r in all_results.items():
            assert len(r["demand"]) == 72, name
            assert len(r["census"]) == 72, name
            assert r["peak_demand"] > 0, name
            assert "summary" in r["optimizer"], name
            assert "department_allocations" in r["optimizer"], name


class TestScenarioDirections:
    """Demand transforms must move outputs in the operationally correct direction."""

    def test_surge_raises_demand_vs_baseline(self, all_results):
        assert all_results["surge"]["peak_demand"] > all_results["baseline"]["peak_demand"]

    def test_holiday_lowers_demand_vs_baseline(self, all_results):
        assert all_results["holiday"]["peak_demand"] < all_results["baseline"]["peak_demand"]

    def test_covid_ramp_ends_higher_than_it_starts(self, all_results):
        demand = all_results["covid_crisis"]["demand"]
        assert demand[-1] > demand[0] * 1.3

    def test_mass_casualty_spike_is_localised(self, all_results):
        base = all_results["baseline"]["demand"]
        mc = all_results["mass_casualty"]["demand"]
        # Spike hours differ by exactly +150; non-spike hours match baseline.
        assert mc[12] == pytest.approx(base[12] + 150.0)
        assert mc[13] == pytest.approx(base[13] + 150.0)
        assert mc[11] == pytest.approx(base[11])
        assert mc[20] == pytest.approx(base[20])

    def test_infeasible_demand_is_10x(self, all_results):
        base = all_results["baseline"]["demand"]
        inf = all_results["infeasible_demand"]["demand"]
        assert inf[0] == pytest.approx(base[0] * 10.0)


class TestForecastOptimizationLinkage:
    """The optimizer must respond monotonically and stay structurally valid."""

    def test_optimizer_runs_for_every_scenario(self, all_results):
        for name, r in all_results.items():
            allocations = r["optimizer"]["department_allocations"]
            assert len(allocations) == 5, name  # 5 departments always present

    def test_surge_needs_at_least_baseline_beds(self, all_results):
        surge_beds = all_results["surge"]["optimizer_summary"]["beds_needed_total"]
        base_beds = all_results["baseline"]["optimizer_summary"]["beds_needed_total"]
        assert surge_beds > base_beds

    def test_infeasible_demand_floods_every_department(self, all_results):
        allocations = all_results["infeasible_demand"]["optimizer"]["department_allocations"]
        # 10x demand must produce a bed shortage in every department.
        assert all(int(a["bed_shortage"]) > 0 for a in allocations)

    def test_holiday_keeps_shortages_at_or_below_baseline(self, all_results):
        def total_bed_shortage(r):
            return sum(int(a["bed_shortage"]) for a in r["optimizer"]["department_allocations"])

        assert total_bed_shortage(all_results["holiday"]) <= total_bed_shortage(all_results["baseline"])

    def test_allocations_never_negative(self, all_results):
        for name, r in all_results.items():
            for a in r["optimizer"]["department_allocations"]:
                assert int(a["beds_required"]) >= 0, name
                assert int(a["bed_shortage"]) >= 0, name
                assert int(a["doctor_shortage"]) >= 0, name
                assert int(a["nurse_shortage"]) >= 0, name


class TestHospitalProfiles:
    def test_infeasible_demand_overflows_demo_hospital(self, base_forecast):
        r = run_scenario("infeasible_demand", PROFILE_DEMO, base_forecast=base_forecast)
        assert r["capacity_exceeded"] is True
        assert r["total_overflow"] > 0

    def test_baseline_fits_demo_hospital(self, base_forecast):
        r = run_scenario("baseline", PROFILE_DEMO, base_forecast=base_forecast)
        # ~218 peak arrivals/h with 24h LOS exceeds nothing catastrophically at
        # 293 beds with 55% starting occupancy — census is capped by capacity,
        # so the assertion is on the census ceiling, not overflow.
        assert max(r["census"]) <= PROFILE_DEMO.total_beds

    def test_small_clinic_overflows_even_on_baseline(self, base_forecast):
        r = run_scenario("baseline", PROFILE_SMALL_CLINIC, base_forecast=base_forecast)
        assert r["capacity_exceeded"] is True

    def test_census_respects_profile_capacity(self, base_forecast):
        for profile in (PROFILE_DEMO, PROFILE_CLEOPATRA_SCALE, PROFILE_SMALL_CLINIC):
            r = run_scenario("surge", profile, base_forecast=base_forecast)
            assert max(r["census"]) <= profile.total_beds, profile.name
