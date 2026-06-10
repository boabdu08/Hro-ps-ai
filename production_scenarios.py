"""Out-of-distribution / production scenario harness (supervisor item M9).

Purpose:     Prove the forecast -> optimization linkage behaves sensibly under
             production-style conditions and edge cases, parameterised by a
             configurable hospital profile (bed/doctor/nurse counts).
Source:      Base demand comes from the repo's pre-generated 72-h forecast
             artifact (artifacts/forecast_outputs/ops72h_overall_forecast.csv) —
             a real model output, never fabricated. Scenario transforms are
             applied on top and are clearly labelled as synthetic stress inputs.
Destination: run_scenario() returns a structured result consumed by
             tests/test_production_scenarios.py and available for demo walkthroughs.

NOTE: hospital profiles below are illustrative configurations for stress
testing — they are NOT published statistics of any named institution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from patient_flow_sim import FlowSimConfig, simulate_patient_flow
from resource_optimizer import optimize_resources

FORECAST_CSV = Path("artifacts/forecast_outputs/ops72h_overall_forecast.csv")


@dataclass(frozen=True)
class HospitalProfile:
    """Operational capacity profile used to parameterise scenarios.

    Profiles are illustrative test configurations (sized to typical private /
    public Egyptian hospitals) — not published statistics of real institutions.
    """

    name: str
    total_beds: int
    doctors: int
    nurses: int


# Demo hospital matches resource_optimizer.DEPARTMENT_CONFIG totals (~293 beds).
PROFILE_DEMO = HospitalProfile(name="demo-hospital", total_beds=293, doctors=44, nurses=103)
# "Cleopatra-scale" = mid-size private hospital configuration (illustrative).
PROFILE_CLEOPATRA_SCALE = HospitalProfile(name="cleopatra-scale", total_beds=250, doctors=40, nurses=90)
# Small clinic edge case: capacity far below demo demand.
PROFILE_SMALL_CLINIC = HospitalProfile(name="small-clinic", total_beds=60, doctors=8, nurses=20)


def load_base_forecast() -> List[float]:
    """Load the canonical pre-generated 72-h overall forecast (model output)."""

    df = pd.read_csv(FORECAST_CSV)
    for col in ("hybrid_pred", "forecast_patients", "lstm_pred"):
        if col in df.columns:
            break
    else:
        raise ValueError(f"No known forecast column in {FORECAST_CSV}: {list(df.columns)}")
    values = [float(v) for v in df[col].tolist()]
    if not values:
        raise ValueError(f"No forecast values found in {FORECAST_CSV}")
    return values


# --- Scenario transforms -----------------------------------------------------
# Each transform takes the base hourly demand series and returns a stressed
# series. All transforms are deterministic.

def _surge(base: List[float]) -> List[float]:
    """Sustained surge: +40% demand across the whole horizon."""
    return [v * 1.40 for v in base]


def _holiday(base: List[float]) -> List[float]:
    """Holiday lull: -25% demand (elective activity paused)."""
    return [v * 0.75 for v in base]


def _covid_crisis(base: List[float]) -> List[float]:
    """COVID-style crisis: demand ramps from +10% to +80% over the horizon."""
    n = len(base)
    ramp = np.linspace(1.10, 1.80, n)
    return [v * r for v, r in zip(base, ramp)]


def _mass_casualty(base: List[float]) -> List[float]:
    """Mass-casualty incident: +150 patients/hour spike for 3 hours at hour 12."""
    out = list(base)
    for h in range(12, min(15, len(out))):
        out[h] = out[h] + 150.0
    return out


def _infeasible_demand(base: List[float]) -> List[float]:
    """Infeasible demand: 10x load — guaranteed to exceed any profile capacity."""
    return [v * 10.0 for v in base]


SCENARIOS: Dict[str, Callable[[List[float]], List[float]]] = {
    "baseline": lambda base: list(base),
    "surge": _surge,
    "holiday": _holiday,
    "covid_crisis": _covid_crisis,
    "mass_casualty": _mass_casualty,
    "infeasible_demand": _infeasible_demand,
}


def run_scenario(
    scenario: str,
    profile: HospitalProfile = PROFILE_DEMO,
    base_forecast: Optional[List[float]] = None,
) -> Dict:
    """Run one scenario through the forecast -> flow-sim -> optimizer linkage.

    Returns a dict with:
        demand:           stressed hourly demand series (72 values)
        peak_demand:      max hourly demand
        census:           projected occupied beds (patient_flow_sim, capped at profile beds)
        peak_census:      max projected census
        total_overflow:   patients that could not be placed (capacity exceeded)
        optimizer:        optimize_resources() output at peak demand
        capacity_exceeded: True when peak demand census hits the bed ceiling
    """

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Available: {sorted(SCENARIOS)}")

    base = base_forecast if base_forecast is not None else load_base_forecast()
    demand = SCENARIOS[scenario](base)
    peak_demand = float(max(demand))

    flow = simulate_patient_flow(
        demand,
        FlowSimConfig(
            mean_los_hours=24.0,
            initial_census=int(profile.total_beds * 0.55),
            bed_capacity=profile.total_beds,
            seed=42,
        ),
    )

    optimizer_result = optimize_resources(peak_demand)
    summary = optimizer_result.get("summary", {})

    return {
        "scenario": scenario,
        "profile": profile.name,
        "demand": demand,
        "peak_demand": peak_demand,
        "census": flow.census,
        "peak_census": flow.peak_census,
        "total_overflow": flow.total_overflow,
        "capacity_exceeded": flow.total_overflow > 0,
        "optimizer": optimizer_result,
        "optimizer_summary": summary,
    }


def run_all_scenarios(profile: HospitalProfile = PROFILE_DEMO) -> Dict[str, Dict]:
    """Run every registered scenario against one hospital profile."""

    base = load_base_forecast()
    return {name: run_scenario(name, profile, base_forecast=base) for name in SCENARIOS}


if __name__ == "__main__":
    import json

    results = run_all_scenarios()
    compact = {
        name: {
            "peak_demand": round(r["peak_demand"], 1),
            "peak_census": round(r["peak_census"], 1),
            "total_overflow": round(r["total_overflow"], 1),
            "capacity_exceeded": r["capacity_exceeded"],
            "beds_needed_total": r["optimizer_summary"].get("beds_needed_total"),
            "mip_status": r["optimizer_summary"].get("mip_status"),
        }
        for name, r in results.items()
    }
    print(json.dumps(compact, indent=2))
