"""Data / forecast drift detection for incoming operational data.

Purpose:     Detect when live data drifts away from the training distribution
             (input drift) or when rolling forecast error degrades (performance
             drift), so admins are alerted *before* the model silently goes stale.
Source:      Called by the scheduler or on-demand from the dashboard with a
             recent window of hourly patient counts (and optionally rolling
             absolute errors).
Destination: DriftReport consumed by the dashboard (admin badge) and usable by
             create_alert_and_notify() to raise a forecast_alert.

Methods (deliberately simple, dependency-free, and explainable to a jury):
* Input drift  — Population Stability Index (PSI) between a reference window
  (training distribution) and the live window, plus mean/std z-shift.
* Performance drift — rolling MAE compared against the canonical test MAE
  baseline; flags when the ratio exceeds a threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

# Canonical deployed-model test MAE (Hybrid 0.80/0.20) — see
# artifacts/metrics_72h/ops72h_model_metrics.csv. Used as the performance
# baseline; do not change without regenerating artifacts.
CANONICAL_TEST_MAE = 8.31

# PSI interpretation thresholds (industry-standard credit-risk convention).
PSI_STABLE = 0.10      # < 0.10 -> no significant shift
PSI_MODERATE = 0.25    # 0.10–0.25 -> moderate shift, monitor
# > 0.25 -> major shift, investigate/retrain


@dataclass
class DriftReport:
    psi: float
    psi_status: str                 # "stable" | "moderate" | "major"
    mean_shift_z: float             # |live mean - ref mean| / ref std
    rolling_mae: Optional[float]
    mae_ratio: Optional[float]      # rolling_mae / canonical test MAE
    performance_status: str         # "ok" | "degraded" | "unknown"
    drifted: bool                   # overall verdict
    notes: List[str] = field(default_factory=list)


def population_stability_index(
    reference: Sequence[float],
    live: Sequence[float],
    bins: int = 10,
) -> float:
    """PSI between a reference and a live sample.

    Bins are quantile-based on the reference so each reference bin holds ~equal
    mass; empty proportions are floored to avoid log(0).
    """

    ref = np.asarray(list(reference), dtype=float)
    cur = np.asarray(list(live), dtype=float)
    if ref.size < bins or cur.size == 0:
        raise ValueError(f"Need >= {bins} reference points and >= 1 live point")

    edges = np.quantile(ref, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    # Collapse duplicate edges (constant stretches in reference data).
    edges = np.unique(edges)
    if len(edges) < 3:
        return 0.0

    ref_counts, _ = np.histogram(ref, bins=edges)
    cur_counts, _ = np.histogram(cur, bins=edges)

    ref_pct = np.clip(ref_counts / ref_counts.sum(), 1e-6, None)
    cur_pct = np.clip(cur_counts / cur_counts.sum(), 1e-6, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def detect_drift(
    reference: Sequence[float],
    live: Sequence[float],
    rolling_abs_errors: Optional[Sequence[float]] = None,
    mae_degradation_ratio: float = 2.0,
    bins: int = 10,
) -> DriftReport:
    """Run input + performance drift checks and return a combined verdict.

    Args:
        reference: training-era hourly patient counts (e.g. last 30 days of
            the training dataset).
        live: recent live hourly patient counts.
        rolling_abs_errors: optional recent |forecast - actual| values; when
            provided, performance drift is evaluated against CANONICAL_TEST_MAE.
        mae_degradation_ratio: rolling MAE above (ratio x canonical MAE)
            flags performance degradation. Default 2.0x.
        bins: PSI quantile bins.
    """

    notes: List[str] = []

    psi = population_stability_index(reference, live, bins=bins)
    if psi < PSI_STABLE:
        psi_status = "stable"
    elif psi < PSI_MODERATE:
        psi_status = "moderate"
        notes.append(f"PSI {psi:.3f} indicates a moderate input shift — monitor.")
    else:
        psi_status = "major"
        notes.append(f"PSI {psi:.3f} indicates a major input shift — investigate/retrain.")

    ref = np.asarray(list(reference), dtype=float)
    cur = np.asarray(list(live), dtype=float)
    ref_std = float(ref.std()) or 1.0
    mean_shift_z = abs(float(cur.mean()) - float(ref.mean())) / ref_std
    if mean_shift_z > 2.0:
        notes.append(f"Live mean shifted {mean_shift_z:.1f} sigma from training mean.")

    rolling_mae: Optional[float] = None
    mae_ratio: Optional[float] = None
    performance_status = "unknown"
    if rolling_abs_errors is not None and len(rolling_abs_errors) > 0:
        rolling_mae = float(np.mean(np.abs(np.asarray(list(rolling_abs_errors), dtype=float))))
        mae_ratio = rolling_mae / CANONICAL_TEST_MAE
        if mae_ratio > mae_degradation_ratio:
            performance_status = "degraded"
            notes.append(
                f"Rolling MAE {rolling_mae:.2f} is {mae_ratio:.1f}x the canonical "
                f"test MAE ({CANONICAL_TEST_MAE}) — performance degradation."
            )
        else:
            performance_status = "ok"

    drifted = psi_status == "major" or performance_status == "degraded" or mean_shift_z > 3.0

    return DriftReport(
        psi=round(psi, 4),
        psi_status=psi_status,
        mean_shift_z=round(mean_shift_z, 3),
        rolling_mae=None if rolling_mae is None else round(rolling_mae, 3),
        mae_ratio=None if mae_ratio is None else round(mae_ratio, 3),
        performance_status=performance_status,
        drifted=drifted,
        notes=notes,
    )
