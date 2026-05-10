"""Inference helpers for the ops-aware 72-hour forecasting pipeline.

This module is intentionally separate from existing `forecast_inference.py` to
avoid breaking the legacy 24h Command Center forecast pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from forecasting_pipeline import MODEL_DIR, build_ops_hourly_frame


@dataclass
class Ops72hForecast:
    generated_at: str
    horizon_hours: int
    overall: pd.DataFrame
    by_department: pd.DataFrame
    weights: dict


def _load_lstm_artifacts():
    from tensorflow.keras.models import load_model

    model_path = MODEL_DIR / "lstm_ops72h.keras"
    x_scaler_path = MODEL_DIR / "lstm_x_scaler.pkl"
    y_scaler_path = MODEL_DIR / "lstm_y_scaler.pkl"
    cfg_path = MODEL_DIR / "lstm_feature_config.json"

    if not model_path.exists() or not x_scaler_path.exists() or not y_scaler_path.exists() or not cfg_path.exists():
        return None

    model = load_model(str(model_path), compile=False)
    x_scaler = joblib.load(x_scaler_path)
    y_scaler = joblib.load(y_scaler_path)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    feature_cols = list(cfg.get("feature_cols") or [])
    seq_len = int(cfg.get("sequence_length") or 24)
    return model, x_scaler, y_scaler, feature_cols, seq_len


def _load_arimax_model():
    p = MODEL_DIR / "arimax_ops72h.pkl"
    return None if not p.exists() else joblib.load(p)


def _load_hybrid_cfg():
    p = MODEL_DIR / "hybrid_config.json"
    if not p.exists():
        return {"lstm_weight": 0.85, "arimax_weight": 0.15}
    return json.loads(p.read_text(encoding="utf-8"))


def _seasonal_naive_fallback(df_hist: pd.DataFrame, horizon: int) -> np.ndarray:
    """Safe time-aware fallback from comparable historical non-zero hours.

    The operational exports can contain long zero-filled gaps after continuous
    hourly reindexing. Repeating the last 72 raw rows can therefore create an
    unrealistic "all zeros then one spike" forecast. This fallback uses real
    historical patient counts, but prefers non-zero observations for the same
    hour/day pattern and falls back to robust medians when sparse.
    """

    hist = df_hist.copy().sort_values("datetime").reset_index(drop=True)
    hist["datetime"] = pd.to_datetime(hist.get("datetime"), errors="coerce")
    hist["patients"] = pd.to_numeric(hist.get("patients"), errors="coerce")
    hist = hist.dropna(subset=["datetime", "patients"])
    if hist.empty:
        return np.zeros(horizon, dtype=float)

    hist = hist[hist["patients"] >= 0].copy()
    hist["hour"] = hist["datetime"].dt.hour
    hist["day_of_week"] = hist["datetime"].dt.dayofweek
    last_dt = hist["datetime"].max()
    recent_cutoff = last_dt - pd.Timedelta(days=90)
    recent = hist[hist["datetime"] >= recent_cutoff].copy()
    positive_recent = recent[recent["patients"] > 0].copy()
    positive_all = hist[hist["patients"] > 0].copy()

    # Require enough recent positives to represent a daily cycle. If today's
    # exports only have a few live non-zero rows, use the broader historical
    # demo pattern instead of a single repeated value.
    baseline_pool = positive_recent if len(positive_recent) >= 24 else positive_all
    if baseline_pool.empty:
        baseline_pool = recent if not recent.empty else hist

    global_median = float(baseline_pool["patients"].median())
    if not np.isfinite(global_median):
        global_median = 0.0

    # Modest trend adjustment from recent non-zero demand, capped so fallback
    # remains a baseline rather than an invented surge.
    recent_pos = positive_recent.sort_values("datetime")
    trend_factor = 1.0
    if len(recent_pos) >= 48:
        tail = recent_pos.tail(24)["patients"].median()
        prev = recent_pos.iloc[-48:-24]["patients"].median()
        if np.isfinite(tail) and np.isfinite(prev) and prev > 0:
            trend_factor = float(np.clip(tail / prev, 0.85, 1.15))

    out = []
    for i in range(horizon):
        future_dt = last_dt + pd.Timedelta(hours=i + 1)
        hour = int(future_dt.hour)
        dow = int(future_dt.dayofweek)

        pool = baseline_pool[
            (baseline_pool["hour"] == hour)
            & (baseline_pool["day_of_week"] == dow)
        ]
        if len(pool) < 3:
            pool = baseline_pool[baseline_pool["hour"] == hour]
        if len(pool) < 3:
            value = global_median
        else:
            value = float(pool["patients"].median())

        out.append(max(0.0, value * trend_factor))

    out = np.array(out, dtype=float)
    if len(out) >= 24 and float(np.nanmax(out) - np.nanmin(out)) < 0.5:
        hourly = baseline_pool.groupby("hour")["patients"].median()
        if len(hourly) > 1:
            for i in range(horizon):
                future_hour = int((last_dt + pd.Timedelta(hours=i + 1)).hour)
                out[i] = float(hourly.get(future_hour, global_median))
    return np.clip(out, 0.0, None)


def _validate_forecast_vector(name: str, values: np.ndarray, df_hist: pd.DataFrame) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    arr = np.array(values, dtype=float).reshape(-1)
    if len(arr) == 0:
        return False, [f"{name} output is empty"]
    if not np.isfinite(arr).all():
        reasons.append(f"{name} output contains NaN/Inf")
    if (arr < 0).any():
        reasons.append(f"{name} output contains negative values")
    if len(arr) >= 6:
        arr_range = float(np.nanmax(arr) - np.nanmin(arr))
        arr_mean = float(np.nanmean(np.abs(arr)))
        min_dynamic_range = max(0.5, arr_mean * 0.05)
        if arr_range < min_dynamic_range:
            reasons.append(f"{name} output is nearly flat")

    hist_vals = pd.to_numeric(df_hist.get("patients"), errors="coerce").dropna().astype(float).values
    if len(hist_vals):
        hist_max = float(np.nanmax(hist_vals))
        hist_p99 = float(np.nanpercentile(hist_vals, 99))
        upper = max(hist_max * 3.0, hist_p99 * 3.0, 50.0)
        if float(np.nanmax(arr)) > upper:
            reasons.append(f"{name} output exceeds safe historical range")
    return len(reasons) == 0, reasons


def _safe_model_output(name: str, values: np.ndarray, df_hist: pd.DataFrame, horizon: int) -> tuple[np.ndarray, bool, list[str]]:
    ok, reasons = _validate_forecast_vector(name, values, df_hist)
    if ok:
        return np.clip(np.array(values, dtype=float).reshape(-1)[:horizon], 0.0, None), True, []
    fallback = _seasonal_naive_fallback(df_hist, horizon)
    return fallback, False, reasons + [f"{name} replaced by seasonal-naive fallback"]


def _predict_lstm_next_hours(df_hist: pd.DataFrame, horizon: int) -> np.ndarray:
    loaded = _load_lstm_artifacts()
    if loaded is None:
        return np.zeros(horizon, dtype=float)
    model, x_scaler, y_scaler, feature_cols, seq_len = loaded

    hist = df_hist.copy().sort_values("datetime").reset_index(drop=True)
    for c in feature_cols:
        if c not in hist.columns:
            hist[c] = 0.0
        hist[c] = pd.to_numeric(hist[c], errors="coerce").fillna(0.0)

    # Use last seq_len rows as seed.
    x_hist = x_scaler.transform(hist[feature_cols].values.astype(np.float32))
    if len(x_hist) < seq_len:
        # Pad with zeros if needed.
        pad = np.zeros((seq_len - len(x_hist), x_hist.shape[1]), dtype=np.float32)
        x_hist = np.vstack([pad, x_hist])
    seed = x_hist[-seq_len:].copy()

    last_dt = pd.to_datetime(hist["datetime"].iloc[-1]) if "datetime" in hist.columns else pd.Timestamp.now()
    preds = []
    rolling = seed
    for step in range(horizon):
        x_in = rolling.reshape(1, rolling.shape[0], rolling.shape[1])
        y_s = model.predict(x_in, verbose=0).reshape(-1, 1)
        y = float(y_scaler.inverse_transform(y_s)[0, 0])
        preds.append(y)

        # Roll window with time-aware future calendar features. We keep the
        # autoregressive patient signal but update hour/day/weekend seasonality
        # so the LSTM is not fed an artificial constant horizon.
        future_dt = last_dt + pd.Timedelta(hours=step + 1)
        next_row = rolling[-1].copy()
        if "patients" in feature_cols:
            idx = feature_cols.index("patients")
            next_row[idx] = y_scaler.transform(np.array([[y]], dtype=np.float32))[0, 0]
        raw_updates = {
            "hour": float(future_dt.hour),
            "day_of_week": float(future_dt.dayofweek),
            "month": float(future_dt.month),
            "is_weekend": float(future_dt.dayofweek >= 5),
            "is_holiday": 0.0,
            "holiday": 0.0,
            "shift_period_code": 1.0 if 7 <= future_dt.hour <= 14 else 2.0 if 15 <= future_dt.hour <= 22 else 0.0,
            "hour_sin": float(np.sin(2 * np.pi * future_dt.hour / 24.0)),
            "hour_cos": float(np.cos(2 * np.pi * future_dt.hour / 24.0)),
        }
        for col, value in raw_updates.items():
            if col in feature_cols:
                idx = feature_cols.index(col)
                try:
                    temp = np.zeros((1, len(feature_cols)), dtype=np.float32)
                    temp[0, idx] = float(value)
                    next_row[idx] = x_scaler.transform(temp)[0, idx]
                except Exception:
                    next_row[idx] = float(value)
        rolling = np.vstack([rolling[1:], next_row])

    return np.array(preds, dtype=float)


def _predict_arimax_next_hours(df_hist: pd.DataFrame, horizon: int) -> np.ndarray:
    model = _load_arimax_model()
    if model is None:
        return np.zeros(horizon, dtype=float)

    # The ARIMAX model was trained with a fixed set of exogenous columns.
    exog_cols = list(getattr(model.model, "exog_names", []) or [])
    # statsmodels includes intercept in exog_names sometimes; ignore if not in df.
    exog_cols = [c for c in exog_cols if c in df_hist.columns]

    hist = df_hist.copy().sort_values("datetime").reset_index(drop=True)
    for c in exog_cols:
        hist[c] = pd.to_numeric(hist[c], errors="coerce").fillna(0.0)

    last_dt = pd.to_datetime(hist["datetime"].iloc[-1]) if "datetime" in hist.columns else pd.Timestamp.now()

    # Build time-aware future exogenous values where the trained columns are
    # known calendar features. Unknown exogenous columns fall back to the last
    # observed value, which is safer than dropping the model input shape.
    if exog_cols:
        last = hist[exog_cols].iloc[-1:].values.astype(float)
        exog_future = np.repeat(last, repeats=horizon, axis=0)
        for i in range(horizon):
            future_dt = last_dt + pd.Timedelta(hours=i + 1)
            updates = {
                "hour": float(future_dt.hour),
                "day_of_week": float(future_dt.dayofweek),
                "month": float(future_dt.month),
                "is_weekend": float(future_dt.dayofweek >= 5),
                "is_holiday": 0.0,
                "holiday": 0.0,
                "shift_period_code": 1.0 if 7 <= future_dt.hour <= 14 else 2.0 if 15 <= future_dt.hour <= 22 else 0.0,
                "hour_sin": float(np.sin(2 * np.pi * future_dt.hour / 24.0)),
                "hour_cos": float(np.cos(2 * np.pi * future_dt.hour / 24.0)),
            }
            for col, value in updates.items():
                if col in exog_cols:
                    exog_future[i, exog_cols.index(col)] = float(value)
    else:
        exog_future = None

    pred = model.forecast(steps=horizon, exog=exog_future)
    return np.array(pred, dtype=float).reshape(-1)


def forecast_ops72h(*, tenant_id: int | None = None, horizon_hours: int = 72) -> Ops72hForecast:
    horizon_hours = int(horizon_hours)
    if horizon_hours <= 0:
        horizon_hours = 72

    frame = build_ops_hourly_frame(tenant_id=tenant_id)
    if frame.overall.empty:
        raise RuntimeError("No ops dataset available")

    hist = frame.overall.copy().sort_values("datetime").reset_index(drop=True)
    last_dt = pd.to_datetime(hist["datetime"].iloc[-1])
    future_index = pd.date_range(start=last_dt + pd.Timedelta(hours=1), periods=horizon_hours, freq="h")

    raw_lstm_pred = _predict_lstm_next_hours(hist, horizon_hours)
    raw_arimax_pred = _predict_arimax_next_hours(hist, horizon_hours)
    lstm_pred, lstm_ok, lstm_reasons = _safe_model_output("LSTM", raw_lstm_pred, hist, horizon_hours)
    arimax_pred, arimax_ok, arimax_reasons = _safe_model_output("ARIMAX", raw_arimax_pred, hist, horizon_hours)
    cfg = _load_hybrid_cfg()
    w_lstm = float(cfg.get("lstm_weight", 0.85))
    w_ar = float(cfg.get("arimax_weight", 0.15))
    if not lstm_ok and arimax_ok:
        w_lstm, w_ar = 0.0, 1.0
    elif lstm_ok and not arimax_ok:
        w_lstm, w_ar = 1.0, 0.0
    elif not lstm_ok and not arimax_ok:
        # Both model outputs were invalid; use the time-aware fallback once.
        w_lstm, w_ar = 1.0, 0.0
        lstm_pred = _seasonal_naive_fallback(hist, horizon_hours)
        arimax_pred = lstm_pred.copy()
    else:
        total = max(w_lstm + w_ar, 1e-9)
        w_lstm, w_ar = w_lstm / total, w_ar / total
    hybrid = np.clip(w_lstm * lstm_pred + w_ar * arimax_pred, 0.0, None)

    overall = pd.DataFrame(
        {
            "datetime": future_index,
            "lstm_pred": np.clip(lstm_pred, 0.0, None),
            "arimax_pred": np.clip(arimax_pred, 0.0, None),
            "hybrid_pred": hybrid,
        }
    )
    overall["lstm_valid"] = bool(lstm_ok)
    overall["arimax_valid"] = bool(arimax_ok)
    overall["validation_note"] = "; ".join(lstm_reasons + arimax_reasons) or "OK"

    # Department-level forecast: distribute overall hybrid forecast by latest dept shares
    by_department = pd.DataFrame()
    if not frame.by_department.empty:
        # Share based on last 24h of patient_tracking derived department series.
        recent = frame.by_department.copy()
        recent["datetime"] = pd.to_datetime(recent["datetime"], errors="coerce")
        recent = recent.dropna(subset=["datetime"]).sort_values("datetime")
        cutoff = recent["datetime"].max() - pd.Timedelta(hours=24)
        recent = recent[recent["datetime"] >= cutoff]
        shares = recent.groupby("department")["patients"].sum()
        shares = shares / float(shares.sum()) if float(shares.sum()) > 0 else shares
        share_map = {str(k): float(v) for k, v in shares.to_dict().items()}
    else:
        share_map = {"ER": 0.30, "ICU": 0.10, "General Ward": 0.45, "Surgery": 0.10, "Radiology": 0.05}

    rows = []
    for dept, share in share_map.items():
        for i, dt in enumerate(future_index):
            rows.append(
                {
                    "datetime": dt,
                    "department": dept,
            "hybrid_pred": max(0.0, float(hybrid[i]) * float(share)),
                }
            )
    by_department = pd.DataFrame(rows)

    return Ops72hForecast(
        generated_at=datetime.now().isoformat(),
        horizon_hours=horizon_hours,
        overall=overall,
        by_department=by_department,
        weights={
            "lstm": w_lstm,
            "arimax": w_ar,
            "lstm_valid": bool(lstm_ok),
            "arimax_valid": bool(arimax_ok),
            "fallback_reasons": lstm_reasons + arimax_reasons,
        },
    )
