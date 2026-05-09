from __future__ import annotations

import math
from dataclasses import asdict

import os
import sys

# Ensure repo root is on sys.path when running via: python scripts/...py
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from forecast_state import build_canonical_forecast_state



def _is_constant(vals: list[float] | None, *, tol: float = 1e-6) -> bool:
    if not vals or len(vals) < 3:
        return False
    finite = [v for v in vals if v is not None and math.isfinite(float(v))]
    if len(finite) < 3:
        return False
    return (max(finite) - min(finite)) <= tol


def main() -> None:
    state = build_canonical_forecast_state()

    print("=== Canonical ForecastState Smoke ===")

    # Artifact freshness
    af = asdict(state.artifact_freshness)
    print("artifact_freshness:")
    for k in ["ready", "checked_at", "artifact_timestamp", "missing", "invalid_reasons"]:
        print(f"  {k}: {af.get(k)}")

    ms = asdict(state.model_status)
    print("model_status:")
    for k in ["lstm_ok", "arimax_ok", "hybrid_ok", "fallback_used", "reasons"]:
        print(f"  {k}: {ms.get(k)}")

    # Core operational KPI
    print("current_patients:", state.current_patients)
    print("predicted_patients_next_hour:", state.predicted_patients_next_hour)
    print("forecast_timestamp:", state.forecast_timestamp)

    # 24h (optional)
    print("24h forecast values count:", len(state.forecast_24h_values or []))
    print("24h peak:", state.peak_24h)

    # 72h
    v72 = state.forecast_72h_values or []
    print("72h forecast values count:", len(v72))
    print("72h peak:", state.peak_72h)
    print("72h avg:", state.avg_72h)
    print("72h constant_detected:", _is_constant(v72))

    # Validation checks
    issues: list[str] = []

    if len(v72) < 72:
        issues.append(f"Expected at least 72 horizon rows, got {len(v72)}")

    for i, v in enumerate(v72):
        if v is None or not math.isfinite(float(v)):
            issues.append(f"Non-finite forecast value at index {i}: {v}")
        if float(v) < 0:
            issues.append(f"Negative forecast value at index {i}: {v}")

    # Department forecast schema quick check
    df = state.department_forecast_72h
    if df is not None:
        if df.empty:
            issues.append("department_forecast_72h is empty")
        else:
            for col in ["datetime", "department", "hybrid_pred"]:
                if col not in df.columns:
                    issues.append(f"department_forecast_72h missing col: {col}")

    if issues:
        print("\nSmoke validation: FAILED")
        for e in issues:
            print(" -", e)
        raise SystemExit(1)

    print("\nSmoke validation: PASSED")


if __name__ == "__main__":
    main()

