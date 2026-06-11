"""Operational insight builders — pure, deterministic, UI-framework-free.

Purpose:     Turn already-tested artifacts/modules (ForecastState values,
             patient_flow_sim, drift_detection, uncertainty bands) into
             jury-readable insights: a daily ops briefing, census/saturation
             projections, and a model-health verdict.
Source:      Called by Home / Digital Twin / Evaluation dashboard sections.
Destination: Plain dicts/strings — trivially unit-testable, no Streamlit here.

Honesty rules: every number is computed from real inputs passed in; nothing is
invented. Where a simulation is involved (census projection) the wording says
"projected"/"simulation". No heavy imports (keeps import-perf tests green).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from patient_flow_sim import FlowSimConfig, simulate_patient_flow

SUPP_EVAL_PATH = Path("artifacts/metrics_72h/supplementary/supplementary_evaluation.json")


# ---------------------------------------------------------------------------
# Census projection + time-to-saturation (Digital Twin)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CensusProjection:
    census: List[float]
    overflow: List[float]
    staffed_beds: int
    initial_census: int
    hours_to_saturation: Optional[int]   # None -> not within the horizon
    peak_census: float
    peak_hour: int


def project_census(
    forecast_values: Sequence[float],
    staffed_beds: int,
    initial_census: int,
    mean_los_hours: float = 24.0,
    seed: int = 42,
) -> CensusProjection:
    """Project occupied beds from an arrivals forecast (queueing simulation).

    `hours_to_saturation` = first hour the UNCAPPED projected census exceeds
    staffed_beds (the operational question is "when do we run out", so the
    simulation must be allowed to exceed capacity rather than be clamped at it).
    """

    if staffed_beds <= 0:
        raise ValueError("staffed_beds must be > 0")
    arrivals = [max(0.0, float(v)) for v in forecast_values]

    flow = simulate_patient_flow(
        arrivals,
        FlowSimConfig(
            mean_los_hours=mean_los_hours,
            initial_census=max(0, int(initial_census)),
            bed_capacity=None,          # uncapped: we WANT to see the breach
            seed=seed,
        ),
    )
    census = list(flow.census)
    overflow = [round(max(0.0, c - staffed_beds), 1) for c in census]

    hours_to_sat: Optional[int] = None
    for h, c in enumerate(census):
        if c > staffed_beds:
            hours_to_sat = h
            break

    peak_hour = int(np.argmax(census)) if census else 0
    return CensusProjection(
        census=census,
        overflow=overflow,
        staffed_beds=int(staffed_beds),
        initial_census=int(initial_census),
        hours_to_saturation=hours_to_sat,
        peak_census=float(max(census)) if census else 0.0,
        peak_hour=peak_hour,
    )


def saturation_label(hours: Optional[int]) -> str:
    """KPI text for time-to-saturation."""

    if hours is None:
        return "Not within 72 h"
    if hours == 0:
        return "Already at capacity"
    return f"~{hours} h"


# ---------------------------------------------------------------------------
# Daily Ops Briefing (Home)
# ---------------------------------------------------------------------------

def build_briefing(
    *,
    now: datetime,
    predicted_next_hour: Optional[float],
    peak_72h: Optional[float],
    peak_hour_offset: Optional[int],
    risk_level: str,
    critical_alerts: int,
    warning_alerts: int,
    top_pressure_department: Optional[str],
    total_bed_shortage: int,
    hours_to_saturation: Optional[int],
    staffed_beds: Optional[int] = None,
) -> List[str]:
    """Deterministic, template-based briefing lines. Every number is an input —
    nothing is generated or estimated here."""

    lines: List[str] = []

    if predicted_next_hour is not None:
        lines.append(f"Next hour: ~{predicted_next_hour:.0f} patients expected (risk {risk_level.upper()}).")

    if peak_72h is not None and peak_hour_offset is not None:
        peak_time = now + timedelta(hours=int(peak_hour_offset))
        lines.append(
            f"72-h peak: ~{peak_72h:.0f} patients around {peak_time.strftime('%a %H:00')} "
            f"(hour +{int(peak_hour_offset)})."
        )

    if hours_to_saturation is not None:
        beds_txt = f" of {staffed_beds} staffed beds" if staffed_beds else ""
        lines.append(
            f"Capacity: projected census exceeds staffed beds{beds_txt} in ~{hours_to_saturation} h "
            "— review discharge pipeline and overflow plan."
        )
    elif staffed_beds:
        lines.append(f"Capacity: projected census stays within {staffed_beds} staffed beds for the next 72 h.")

    if critical_alerts or warning_alerts:
        lines.append(f"Alerts: {critical_alerts} critical, {warning_alerts} warning currently active.")
    else:
        lines.append("Alerts: none active.")

    if top_pressure_department:
        shortage_txt = (
            f" (total bed shortage {total_bed_shortage})" if total_bed_shortage > 0 else ""
        )
        lines.append(f"Optimizer: highest pressure in {top_pressure_department}{shortage_txt}.")

    return lines


# ---------------------------------------------------------------------------
# Model Health (Evaluation, admin)
# ---------------------------------------------------------------------------

def model_health(
    reference_series: Sequence[float],
    recent_series: Sequence[float],
    rolling_abs_errors: Optional[Sequence[float]] = None,
) -> Dict:
    """Wrap drift_detection into a UI-ready verdict dict.

    Inputs are real series chosen by the caller (e.g. prior-30-days reference
    vs latest-7-days window of the operational dataset; |pred-actual| from the
    saved test outputs). This function adds no data of its own.
    """

    from drift_detection import detect_drift

    report = detect_drift(reference_series, recent_series, rolling_abs_errors=rolling_abs_errors)
    status_chip = {
        "stable": ("STABLE", "success"),
        "moderate": ("MODERATE SHIFT", "warning"),
        "major": ("MAJOR SHIFT", "error"),
    }[report.psi_status]

    return {
        "psi": report.psi,
        "psi_status": report.psi_status,
        "chip_label": status_chip[0],
        "chip_tone": status_chip[1],
        "mean_shift_z": report.mean_shift_z,
        "rolling_mae": report.rolling_mae,
        "mae_ratio": report.mae_ratio,
        "performance_status": report.performance_status,
        "drifted": report.drifted,
        "notes": list(report.notes),
    }


# ---------------------------------------------------------------------------
# Uncertainty bands accessor (Forecast band toggle)
# ---------------------------------------------------------------------------

def load_bands() -> Optional[Dict]:
    """Both 80% and 95% empirical bands from the supplementary artifact."""

    if not SUPP_EVAL_PATH.exists():
        return None
    try:
        payload = json.loads(SUPP_EVAL_PATH.read_text(encoding="utf-8"))
        return payload.get("uncertainty_bands")
    except Exception:
        return None
