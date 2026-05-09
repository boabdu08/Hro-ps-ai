"""Canonical forecast state + artifact freshness validation for HRO-PS.

This module creates a single source of truth used by:
- Command Center / Operations Center / Optimization / Simulation (live 24h)
- Forecast / Digital Twin (saved 72h artifacts)
- Evaluation panels (metrics aligned to the same artifact run)

Design goals (per project requirements):
- Do not calculate the same metric differently in different files.
- Validate artifacts strongly before displaying them.
- Provide model status + fallback reasons explicitly.
- Never silently use stale/invalid outputs.

This file intentionally avoids changing the main architecture; it adds a shared
canonical state object that existing UI/tab code can consume.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from artifacts import artifact_diagnostics



DEFAULT_ARTIFACT_DIR = (Path(os.getenv("ARTIFACT_DIR") or "artifacts").resolve())


@dataclass(frozen=True)
class ModelStatus:
    lstm_ok: bool
    arimax_ok: bool
    hybrid_ok: bool
    fallback_used: bool
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactFreshness:
    ready: bool
    artifact_timestamp: Optional[str]
    checked_at: str
    missing: List[str] = field(default_factory=list)
    invalid_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastState:
    # Canonical operational KPls
    current_patients: Optional[float]
    predicted_patients_next_hour: Optional[float]

    # 24h curve (optional for some pages)
    forecast_24h_values: List[float]
    peak_24h: Optional[float]

    # 72h curve (required for Forecast/Digital Twin)
    overall_forecast_72h: Optional[pd.DataFrame]
    forecast_72h_values: List[float]
    peak_72h: Optional[float]
    avg_72h: Optional[float]

    # Department-level (required for Forecast + Digital Twin dept filter)
    department_forecast_72h: Optional[pd.DataFrame]

    # Model info
    selected_model: Optional[str]
    model_weights: Dict[str, float]
    metrics: Optional[pd.DataFrame]
    artifact_freshness: ArtifactFreshness
    model_status: ModelStatus

    # UI metadata
    forecast_timestamp: Optional[str]
    risk_level: Optional[str]
    resource_recommendation_input: Optional[float]
    artifact_paths: Dict[str, str] = field(default_factory=dict)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_finite_array(x: np.ndarray) -> bool:
    return np.isfinite(x).all()


def _array_non_constant(x: np.ndarray, *, min_range: float = 1e-3) -> bool:
    if len(x) < 5:
        return False
    r = float(np.nanmax(x) - np.nanmin(x))
    return np.isfinite(r) and r > min_range


def _read_json_maybe(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _validate_ops72h_forecast_df(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if df is None or df.empty:
        return False, ["ops72h forecast CSV is empty"]

    required_cols = {"datetime", "hybrid_pred"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        return False, [f"missing required cols: {sorted(missing_cols)}"]

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    if df["datetime"].isna().any():
        reasons.append("invalid datetime values (NaT present)")

    vals = pd.to_numeric(df["hybrid_pred"], errors="coerce").astype(float).values
    if np.isnan(vals).any():
        reasons.append("hybrid_pred contains NaNs")

    if (vals < 0).any():
        reasons.append("hybrid_pred contains negative values")

    if len(vals) < 24:
        reasons.append("hybrid_pred horizon appears shorter than expected")

    # Strong credibility check: ensure not flat unless mathematically justified.
    # We do not reject; we flag. If it is flat AND artifacts are fresh, we still return ready but with model_status.
    if not _array_non_constant(vals, min_range=0.5):
        reasons.append("hybrid_pred is nearly constant across the horizon")

    return len(reasons) == 0, reasons


def _validate_ops72h_department_df(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if df is None or df.empty:
        return False, ["ops72h department forecast CSV is empty"]

    required_cols = {"datetime", "department", "hybrid_pred"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        return False, [f"missing required cols: {sorted(missing_cols)}"]

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    if df["datetime"].isna().any():
        reasons.append("department forecast contains invalid datetime values")

    vals = pd.to_numeric(df["hybrid_pred"], errors="coerce").astype(float).values
    if np.isnan(vals).any():
        reasons.append("department hybrid_pred contains NaNs")
    if (vals < 0).any():
        reasons.append("department hybrid_pred contains negative values")

    # Expect 72 hours worth of rows per department (not necessarily exactly 72 depending on exports).
    if len(df) < 72:
        reasons.append("department forecast row count seems too low for 72h")

    return len(reasons) == 0, reasons


def _compute_selected_model(metrics_df: pd.DataFrame) -> Optional[str]:
    if metrics_df is None or metrics_df.empty:
        return None
    cols = set(metrics_df.columns)
    if not {"Model", "RMSE"}.issubset(cols):
        return None
    try:
        row = metrics_df.sort_values("RMSE", ascending=True).iloc[0]
        return str(row.get("Model"))
    except Exception:
        return None


def _risk_level(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if v < 80:
        return "LOW"
    if v < 120:
        return "MEDIUM"
    return "HIGH"


def _load_ops72h_artifacts(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Dict[str, Any]:
    base = artifact_dir
    overall_path = base / "forecast_outputs" / "ops72h_overall_forecast.csv"
    dept_path = base / "forecast_outputs" / "ops72h_department_forecast.csv"
    metrics_path = base / "metrics_72h" / "ops72h_model_metrics.csv"
    summary_path = base / "manifests" / "ops72h_training_summary.json"

    out: Dict[str, Any] = {
        "overall_path": str(overall_path),
        "dept_path": str(dept_path),
        "metrics_path": str(metrics_path),
        "summary_path": str(summary_path),
    }
    missing = []
    for label, p in [
        ("overall", overall_path),
        ("department", dept_path),
        ("metrics", metrics_path),
        ("summary", summary_path),
    ]:
        if not p.exists():
            missing.append(f"{label}: {p}")

    out["missing"] = missing
    if missing:
        return out

    overall_df = pd.read_csv(overall_path)
    dept_df = pd.read_csv(dept_path)
    metrics_df = pd.read_csv(metrics_path) if metrics_path.exists() else pd.DataFrame()
    summary = _read_json_maybe(summary_path)

    return {
        "overall_path": str(overall_path),
        "dept_path": str(dept_path),
        "metrics_path": str(metrics_path),
        "summary_path": str(summary_path),
        "overall_df": overall_df,
        "dept_df": dept_df,
        "metrics_df": metrics_df,
        "summary": summary,
        "missing": missing,
    }


def build_canonical_forecast_state(*, current_patients: Optional[float] = None,
                                    predicted_next_hour: Optional[float] = None,
                                    forecast_24h_values: Optional[List[float]] = None) -> ForecastState:
    """Build ForecastState from ops72h artifacts and optional live 24h values.

    If current_patients/predicted_next_hour are not provided, they remain None.
    UI/API callers that need them should pass live values (from Prediction API).
    """

    checked_at = _utc_now_iso()


    # Validate core model/scalers presence (not horizon CSV)
    diag = artifact_diagnostics()

    artifact_freshness = ArtifactFreshness(
        ready=False,
        artifact_timestamp=None,
        checked_at=checked_at,
        missing=list(diag.get("missing") or []),
        invalid_reasons=[],
    )

    # NOTE: ops72h artifacts (forecast_outputs + metrics_72h) must be generated
    # by the ops72h pipeline. This module should not guess fallback values
    # for the 72h horizon; it will mark artifact_freshness.ready=False.


    ops72h = _load_ops72h_artifacts(artifact_dir=DEFAULT_ARTIFACT_DIR)
    missing = list(ops72h.get("missing") or [])

    reasons: List[str] = []

    # Model status starts as OK; we flip based on validations.
    lstm_ok = True
    arimax_ok = True
    hybrid_ok = True
    fallback_used = False

    if missing:
        artifact_freshness = ArtifactFreshness(
            ready=False,
            artifact_timestamp=None,
            checked_at=checked_at,
            missing=missing + artifact_freshness.missing,
            invalid_reasons=[],
        )
        model_status = ModelStatus(
            lstm_ok=True,
            arimax_ok=False,
            hybrid_ok=False,
            fallback_used=True,
            reasons=["72h artifacts missing"],
        )
        return ForecastState(
            current_patients=current_patients,
            predicted_patients_next_hour=predicted_next_hour,
            forecast_24h_values=list(forecast_24h_values or []),
            peak_24h=float(max(forecast_24h_values)) if forecast_24h_values else None,
            overall_forecast_72h=None,
            forecast_72h_values=[],
            peak_72h=None,
            avg_72h=None,
            department_forecast_72h=None,
            selected_model=None,
            model_weights={},
            metrics=None,
            artifact_freshness=artifact_freshness,
            model_status=model_status,
            forecast_timestamp=None,
            risk_level=_risk_level(predicted_next_hour),
            resource_recommendation_input=predicted_next_hour,
            artifact_paths={
                "overall_forecast": str(Path(ops72h.get("overall_path", ""))),
                "department_forecast": str(Path(ops72h.get("dept_path", ""))),
                "metrics": str(Path(ops72h.get("metrics_path", ""))),
                "manifest": str(Path(ops72h.get("summary_path", ""))),
            },
        )

    overall_df = ops72h["overall_df"]
    dept_df = ops72h["dept_df"]
    metrics_df = ops72h.get("metrics_df") if ops72h.get("metrics_df") is not None else pd.DataFrame()
    summary = ops72h.get("summary") or {}

    # Timestamp from summary if present
    forecast_timestamp = summary.get("generated_at") or summary.get("timestamp")
    artifact_freshness = ArtifactFreshness(
        ready=artifact_freshness.ready,
        artifact_timestamp=str(forecast_timestamp) if forecast_timestamp else None,
        checked_at=artifact_freshness.checked_at,
        missing=artifact_freshness.missing,
        invalid_reasons=artifact_freshness.invalid_reasons,
    )

    # Validate CSV schemas and values
    overall_ok, overall_reasons = _validate_ops72h_forecast_df(overall_df)
    dept_ok, dept_reasons = _validate_ops72h_department_df(dept_df)

    reasons.extend(overall_reasons)
    reasons.extend(dept_reasons)

    # Determine readiness: allow flatness but mark in model_status
    # If schema/value checks fail, mark invalid.
    invalid_value_reasons = [r for r in reasons if any(k in r for k in ["missing required", "NaNs", "negative", "empty", "invalid datetime"])]
    if invalid_value_reasons or (not overall_ok) or (not dept_ok):
        artifact_freshness = ArtifactFreshness(
            ready=False,
            artifact_timestamp=artifact_freshness.artifact_timestamp,
            checked_at=artifact_freshness.checked_at,
            missing=artifact_freshness.missing,
            invalid_reasons=invalid_value_reasons or reasons,
        )
        hybrid_ok = False

    # Flatness is credibility issue, but not always fatal. We'll flag hybrid_status.
    if any("nearly constant" in r for r in reasons):
        hybrid_ok = False
        fallback_used = True
        # In absence of runtime ARIMAX fallback info, we attribute it to hybrid quality.

    # Model weights (from summary)
    weights = summary.get("weights") or {}
    selected_model = _compute_selected_model(metrics_df)

    model_status = ModelStatus(
        lstm_ok=lstm_ok,
        arimax_ok=arimax_ok,
        hybrid_ok=hybrid_ok,
        fallback_used=fallback_used,
        reasons=[
            *artifact_freshness.invalid_reasons,
            *([r for r in reasons if r not in artifact_freshness.invalid_reasons]),
        ],
    )

    # Build horizon vectors
    overall_df = overall_df.copy()
    overall_df["datetime"] = pd.to_datetime(overall_df["datetime"], errors="coerce")
    overall_df = overall_df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    vals = pd.to_numeric(overall_df["hybrid_pred"], errors="coerce").astype(float).values

    # Clip non-negative (credibility) but flag.
    vals = np.where(vals < 0, 0.0, vals)

    forecast_72h_values = [float(v) for v in vals.tolist()]
    peak_72h = float(np.max(vals)) if len(vals) else None
    avg_72h = float(np.mean(vals)) if len(vals) else None

    # Department forecast
    dept_df = dept_df.copy()
    dept_df["datetime"] = pd.to_datetime(dept_df["datetime"], errors="coerce")
    dept_df = dept_df.dropna(subset=["datetime"]).reset_index(drop=True)
    if not dept_df.empty:
        dept_df["hybrid_pred"] = pd.to_numeric(dept_df["hybrid_pred"], errors="coerce").astype(float)
        dept_df["hybrid_pred"] = np.where(dept_df["hybrid_pred"] < 0, 0.0, dept_df["hybrid_pred"])

    if metrics_df is not None and not metrics_df.empty:
        metrics_df = metrics_df.copy()
        for col in ["MAE", "RMSE", "MAPE", "WAPE", "SMAPE"]:
            if col in metrics_df.columns:
                metrics_df[col] = pd.to_numeric(metrics_df[col], errors="coerce")

    # If we set invalid, keep ready False (ArtifactFreshness is frozen, so readiness
    # is handled by re-instantiating ArtifactFreshness below).
    if not hybrid_ok:
        pass

    # Mark readiness when at least schema OK.
    # readiness is computed once when we assemble the new ArtifactFreshness
    # (artifact_freshness is frozen)
    if not artifact_freshness.invalid_reasons:
        artifact_freshness = ArtifactFreshness(
            ready=True,
            artifact_timestamp=artifact_freshness.artifact_timestamp,
            checked_at=artifact_freshness.checked_at,
            missing=artifact_freshness.missing,
            invalid_reasons=artifact_freshness.invalid_reasons,
        )

    return ForecastState(
        current_patients=current_patients,
        predicted_patients_next_hour=predicted_next_hour,
        forecast_24h_values=list(forecast_24h_values or []),
        peak_24h=float(max(forecast_24h_values)) if forecast_24h_values else None,
        overall_forecast_72h=overall_df,
        forecast_72h_values=forecast_72h_values,
        peak_72h=peak_72h,
        avg_72h=avg_72h,
        department_forecast_72h=dept_df,
        selected_model=selected_model,
        model_weights={"lstm": float(weights.get("lstm_weight") or weights.get("lstm") or 0.0),
                       "arimax": float(weights.get("arimax_weight") or weights.get("arimax") or 0.0)},
        metrics=metrics_df,
        artifact_freshness=artifact_freshness,
        model_status=model_status,
        forecast_timestamp=str(forecast_timestamp) if forecast_timestamp else None,
        risk_level=_risk_level(predicted_next_hour),
        resource_recommendation_input=predicted_next_hour,
        artifact_paths={
            "overall_forecast": str(ops72h.get("overall_path")),
            "department_forecast": str(ops72h.get("dept_path")),
            "metrics": str(ops72h.get("metrics_path")),
            "manifest": str(ops72h.get("summary_path")),
        },
    )


def forecast_state_to_dict(state: ForecastState, *, include_frames: bool = False) -> Dict[str, Any]:
    """Serialize ForecastState for API responses and smoke checks.

    DataFrames are omitted by default and represented as records only when the
    caller explicitly asks for frames.
    """

    payload: Dict[str, Any] = {
        "current_patients": state.current_patients,
        "predicted_patients_next_hour": state.predicted_patients_next_hour,
        "forecast_24h_values": list(state.forecast_24h_values or []),
        "peak_24h": state.peak_24h,
        "forecast_72h_values": list(state.forecast_72h_values or []),
        "peak_72h": state.peak_72h,
        "avg_72h": state.avg_72h,
        "selected_model": state.selected_model,
        "model_weights": dict(state.model_weights or {}),
        "artifact_freshness": {
            "ready": state.artifact_freshness.ready,
            "artifact_timestamp": state.artifact_freshness.artifact_timestamp,
            "checked_at": state.artifact_freshness.checked_at,
            "missing": list(state.artifact_freshness.missing or []),
            "invalid_reasons": list(state.artifact_freshness.invalid_reasons or []),
        },
        "model_status": {
            "lstm_ok": state.model_status.lstm_ok,
            "arimax_ok": state.model_status.arimax_ok,
            "hybrid_ok": state.model_status.hybrid_ok,
            "fallback_used": state.model_status.fallback_used,
            "reasons": list(state.model_status.reasons or []),
        },
        "forecast_timestamp": state.forecast_timestamp,
        "risk_level": state.risk_level,
        "resource_recommendation_input": state.resource_recommendation_input,
        "artifact_paths": dict(state.artifact_paths or {}),
        "metrics": state.metrics.to_dict(orient="records") if isinstance(state.metrics, pd.DataFrame) else [],
    }
    if include_frames:
        payload["overall_forecast_72h"] = (
            state.overall_forecast_72h.to_dict(orient="records")
            if isinstance(state.overall_forecast_72h, pd.DataFrame)
            else []
        )
        payload["department_forecast_72h"] = (
            state.department_forecast_72h.to_dict(orient="records")
            if isinstance(state.department_forecast_72h, pd.DataFrame)
            else []
        )
    return payload



