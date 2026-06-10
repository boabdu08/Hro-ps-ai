"""Patient-flow simulation: admission -> length-of-stay -> discharge.

Purpose:     The forecasting models predict *arrivals* (patients/hour). This module
             turns an arrival forecast into a *census* (occupied beds over time) by
             modelling length-of-stay (LOS) and discharge, so the dashboard can show
             projected bed occupancy and discharge pressure, not just arrivals.
Source:      Called with an hourly arrivals series (e.g. ForecastState.forecast_72h
             values) plus per-department LOS parameters.
Destination: Returns a deterministic census/occupancy DataFrame consumed by the
             Digital Twin / Simulation tabs and the optimizer's occupancy inputs.

Design notes
------------
* Deterministic by default (seeded) so results are reproducible for the demo and
  for tests. No training, no external services.
* Discrete hourly simulation. Each admitted cohort is discharged after a
  length-of-stay drawn from a clipped log-normal (mean = ``mean_los_hours``).
* This is an operational queueing approximation, NOT a clinical model. It is
  explicitly disclosed as such wherever surfaced in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


# Default length-of-stay (hours) per department. Calibrated to the 5-department
# demo hospital; overridable per tenant. These are operational assumptions, not
# measured clinical values.
DEFAULT_LOS_HOURS: Dict[str, float] = {
    "ER": 6.0,
    "ICU": 96.0,
    "General Ward": 72.0,
    "Surgery": 48.0,
    "Radiology": 3.0,
}


@dataclass
class FlowSimConfig:
    mean_los_hours: float = 48.0
    los_cv: float = 0.5            # coefficient of variation of LOS (spread)
    initial_census: int = 0
    bed_capacity: Optional[int] = None
    seed: int = 42
    max_los_hours: float = 24 * 14  # clip extreme stays at 14 days

    def __post_init__(self) -> None:
        if self.mean_los_hours <= 0:
            raise ValueError("mean_los_hours must be > 0")
        if self.los_cv < 0:
            raise ValueError("los_cv must be >= 0")


@dataclass
class FlowSimResult:
    census: List[float] = field(default_factory=list)        # occupied beds per hour
    admissions: List[float] = field(default_factory=list)    # arrivals admitted per hour
    discharges: List[float] = field(default_factory=list)    # discharges per hour
    overflow: List[float] = field(default_factory=list)      # admissions over capacity
    peak_census: float = 0.0
    mean_census: float = 0.0
    total_overflow: float = 0.0

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "hour": list(range(len(self.census))),
                "admissions": self.admissions,
                "discharges": self.discharges,
                "census": self.census,
                "overflow": self.overflow,
            }
        )


def _lognormal_los_hours(rng: np.random.Generator, cfg: FlowSimConfig, n: int) -> np.ndarray:
    """Draw ``n`` length-of-stay samples (hours) from a clipped log-normal.

    The log-normal mean is matched to ``cfg.mean_los_hours`` given ``cfg.los_cv``.
    """
    if n <= 0:
        return np.array([], dtype=float)
    if cfg.los_cv == 0:
        return np.full(n, float(cfg.mean_los_hours))
    sigma = np.sqrt(np.log(1.0 + cfg.los_cv ** 2))
    mu = np.log(cfg.mean_los_hours) - 0.5 * sigma ** 2
    draws = rng.lognormal(mean=mu, sigma=sigma, size=n)
    return np.clip(draws, 1.0, cfg.max_los_hours)


def simulate_patient_flow(
    arrivals: Sequence[float],
    config: Optional[FlowSimConfig] = None,
) -> FlowSimResult:
    """Simulate admission->discharge dynamics over an hourly arrivals series.

    Args:
        arrivals: hourly arrival counts (e.g. forecast values). Negative values
            are treated as 0.
        config: simulation parameters (LOS, capacity, seed).

    Returns:
        FlowSimResult with per-hour census/admissions/discharges/overflow.
    """
    cfg = config or FlowSimConfig()
    rng = np.random.default_rng(cfg.seed)

    arrivals = [max(0.0, float(a)) for a in arrivals]
    horizon = len(arrivals)
    if horizon == 0:
        return FlowSimResult()

    # discharge_schedule[h] = number of patients leaving at hour h.
    discharge_schedule = np.zeros(horizon + int(cfg.max_los_hours) + 2, dtype=float)

    # Seed the initial census as a cohort already present; spread their remaining
    # stay across the LOS distribution so they discharge gradually.
    if cfg.initial_census > 0:
        los = _lognormal_los_hours(rng, cfg, int(cfg.initial_census))
        for stay in los:
            # remaining stay uniformly between 0 and full LOS
            remaining = int(rng.integers(0, max(1, int(stay)) + 1))
            idx = min(remaining, len(discharge_schedule) - 1)
            discharge_schedule[idx] += 1.0

    census = 0.0 + float(cfg.initial_census)
    out_census: List[float] = []
    out_admissions: List[float] = []
    out_discharges: List[float] = []
    out_overflow: List[float] = []

    cap = cfg.bed_capacity

    for h in range(horizon):
        # 1) discharges first (beds free up at the top of the hour)
        leaving = float(discharge_schedule[h])
        leaving = min(leaving, census)
        census -= leaving

        # 2) admissions (rounded; arrivals are a rate)
        admit = float(np.round(arrivals[h]))
        overflow = 0.0
        if cap is not None and census + admit > cap:
            overflow = (census + admit) - cap
            admit = max(0.0, cap - census)

        census += admit

        # 3) schedule discharges for admitted cohort
        if admit > 0:
            los = _lognormal_los_hours(rng, cfg, int(admit))
            for stay in los:
                dh = h + max(1, int(round(stay)))
                if dh < len(discharge_schedule):
                    discharge_schedule[dh] += 1.0

        out_census.append(round(census, 2))
        out_admissions.append(round(admit, 2))
        out_discharges.append(round(leaving, 2))
        out_overflow.append(round(overflow, 2))

    return FlowSimResult(
        census=out_census,
        admissions=out_admissions,
        discharges=out_discharges,
        overflow=out_overflow,
        peak_census=float(max(out_census)) if out_census else 0.0,
        mean_census=float(np.mean(out_census)) if out_census else 0.0,
        total_overflow=float(np.sum(out_overflow)),
    )


def simulate_by_department(
    department_arrivals: Dict[str, Sequence[float]],
    los_hours: Optional[Dict[str, float]] = None,
    bed_capacity: Optional[Dict[str, int]] = None,
    seed: int = 42,
) -> Dict[str, FlowSimResult]:
    """Run :func:`simulate_patient_flow` per department.

    Args:
        department_arrivals: mapping department -> hourly arrivals series.
        los_hours: optional mapping department -> mean LOS hours (defaults to
            DEFAULT_LOS_HOURS, then 48h).
        bed_capacity: optional mapping department -> bed capacity.
        seed: base RNG seed (offset per department for independence).
    """
    los_hours = los_hours or DEFAULT_LOS_HOURS
    results: Dict[str, FlowSimResult] = {}
    for i, (dept, arrivals) in enumerate(sorted(department_arrivals.items())):
        cap = None if bed_capacity is None else bed_capacity.get(dept)
        cfg = FlowSimConfig(
            mean_los_hours=float(los_hours.get(dept, 48.0)),
            bed_capacity=cap,
            seed=seed + i,
        )
        results[dept] = simulate_patient_flow(arrivals, cfg)
    return results
