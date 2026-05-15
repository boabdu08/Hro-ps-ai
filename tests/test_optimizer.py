"""Tests for resource_optimizer.optimize_resources.

These tests exercise the optimizer logic end-to-end without requiring a
live database — the optimizer falls back to empty DB state gracefully,
which is sufficient to validate structure and positive-integer outputs.
"""

import pytest

from resource_optimizer import optimize_resources, DEPARTMENT_CONFIG


EXPECTED_DEPARTMENTS = {"ER", "ICU", "General Ward", "Surgery", "Radiology"}


def _call_optimizer(predicted_patients: float = 100.0) -> dict:
    """Call optimizer and return result dict."""
    return optimize_resources(predicted_patients)


class TestOptimizerReturnShape:
    def test_returns_dict(self):
        result = _call_optimizer()
        assert isinstance(result, dict)

    def test_has_required_top_level_keys(self):
        result = _call_optimizer()
        for key in ("summary", "department_allocations", "recommendations", "actions"):
            assert key in result, f"Missing top-level key: '{key}'"

    def test_summary_is_dict(self):
        result = _call_optimizer()
        assert isinstance(result["summary"], dict)

    def test_department_allocations_is_list(self):
        result = _call_optimizer()
        assert isinstance(result["department_allocations"], list)

    def test_recommendations_is_list(self):
        result = _call_optimizer()
        assert isinstance(result["recommendations"], list)

    def test_actions_is_list(self):
        result = _call_optimizer()
        assert isinstance(result["actions"], list)


class TestSummaryFields:
    def test_summary_has_beds_needed_total(self):
        result = _call_optimizer(predicted_patients=100)
        assert "beds_needed_total" in result["summary"]

    def test_summary_has_doctors_needed_total(self):
        result = _call_optimizer(predicted_patients=100)
        assert "doctors_needed_total" in result["summary"]

    def test_summary_has_nurses_needed_total(self):
        result = _call_optimizer(predicted_patients=100)
        assert "nurses_needed_total" in result["summary"]

    def test_beds_needed_total_positive(self):
        result = _call_optimizer(predicted_patients=100)
        assert result["summary"]["beds_needed_total"] > 0

    def test_doctors_needed_total_positive(self):
        result = _call_optimizer(predicted_patients=100)
        assert result["summary"]["doctors_needed_total"] > 0

    def test_nurses_needed_total_positive(self):
        result = _call_optimizer(predicted_patients=100)
        assert result["summary"]["nurses_needed_total"] > 0

    def test_beds_needed_total_is_int(self):
        result = _call_optimizer(predicted_patients=100)
        assert isinstance(result["summary"]["beds_needed_total"], int)

    def test_doctors_needed_total_is_int(self):
        result = _call_optimizer(predicted_patients=100)
        assert isinstance(result["summary"]["doctors_needed_total"], int)

    def test_nurses_needed_total_is_int(self):
        result = _call_optimizer(predicted_patients=100)
        assert isinstance(result["summary"]["nurses_needed_total"], int)


class TestDepartmentAllocations:
    def test_exactly_five_departments(self):
        result = _call_optimizer()
        assert len(result["department_allocations"]) == 5

    def test_all_expected_departments_present(self):
        result = _call_optimizer()
        actual_depts = {row["department"] for row in result["department_allocations"]}
        assert actual_depts == EXPECTED_DEPARTMENTS

    def test_each_allocation_has_beds_required(self):
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert "beds_required" in row, f"Missing 'beds_required' in dept row: {row.get('department')}"

    def test_each_allocation_has_doctors_required(self):
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert "doctors_required" in row

    def test_each_allocation_has_nurses_required(self):
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert "nurses_required" in row

    def test_beds_required_positive_for_nonzero_patients(self):
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert row["beds_required"] > 0, f"beds_required <= 0 for {row['department']}"

    def test_priority_score_field_present(self):
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert "priority_score" in row

    def test_status_field_present_and_valid(self):
        valid_statuses = {"stable", "warning", "critical"}
        result = _call_optimizer(predicted_patients=100)
        for row in result["department_allocations"]:
            assert row["status"] in valid_statuses, (
                f"Invalid status '{row['status']}' for dept '{row['department']}'"
            )


class TestMILPAllocation:
    def test_milp_runs_without_crash(self):
        """MILP solver must run without raising an exception."""
        result = _call_optimizer(predicted_patients=120)
        # mip_allocation key must be present (may be empty list if solver skips)
        assert "mip_allocation" in result

    def test_milp_status_in_summary(self):
        result = _call_optimizer(predicted_patients=100)
        assert "mip_status" in result["summary"]

    def test_milp_allocation_is_list(self):
        result = _call_optimizer(predicted_patients=100)
        assert isinstance(result["mip_allocation"], list)

    def test_milp_allocation_entries_have_required_fields(self):
        result = _call_optimizer(predicted_patients=150)
        for entry in result["mip_allocation"]:
            for field in ("department", "resource", "required", "mip_assigned", "mip_gap"):
                assert field in entry, f"MILP allocation entry missing '{field}': {entry}"

    def test_mip_assigned_non_negative(self):
        result = _call_optimizer(predicted_patients=100)
        for entry in result["mip_allocation"]:
            assert entry["mip_assigned"] >= 0

    def test_mip_gap_non_negative(self):
        result = _call_optimizer(predicted_patients=100)
        for entry in result["mip_allocation"]:
            assert entry["mip_gap"] >= 0


class TestScaling:
    def test_higher_patients_increases_beds_needed(self):
        low = optimize_resources(50)["summary"]["beds_needed_total"]
        high = optimize_resources(200)["summary"]["beds_needed_total"]
        assert high > low, "beds_needed_total should increase with more predicted patients"

    def test_higher_patients_increases_doctors_needed(self):
        low = optimize_resources(50)["summary"]["doctors_needed_total"]
        high = optimize_resources(200)["summary"]["doctors_needed_total"]
        assert high > low, "doctors_needed_total should increase with more predicted patients"

    def test_recommendations_not_empty(self):
        result = _call_optimizer(predicted_patients=100)
        assert len(result["recommendations"]) >= 1
