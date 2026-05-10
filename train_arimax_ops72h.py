"""Train ARIMAX (SARIMAX) for ops-aware 72-hour forecasting.

Uses updated hospital operational features (appointments/or/staff/beds) from
`forecasting_pipeline.build_ops_hourly_frame()`.

Artifacts are written under:
  - artifacts/models_72h/
  - artifacts/metrics_72h/
"""

from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX

from forecasting_pipeline import METRICS_DIR, MODEL_DIR, build_ops_hourly_frame, save_ops_hourly_dataset


def mape_safe(y_true, y_pred):
    y_true = np.array(y_true, dtype=float).reshape(-1)
    y_pred = np.array(y_pred, dtype=float).reshape(-1)
    denom = np.where(np.abs(y_true) < 1e-8, 1.0, np.abs(y_true))
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def evaluate(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    mape = mape_safe(y_true, y_pred)
    return {"MAE": float(mae), "RMSE": float(rmse), "MAPE": float(mape)}


def fit_model(y: pd.Series, exog: pd.DataFrame):
    model = SARIMAX(
        endog=y,
        exog=exog,
        order=(1, 1, 1),
        seasonal_order=(0, 0, 0, 0),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    return model.fit(disp=False)


def main():
    frame = build_ops_hourly_frame()
    if frame.overall.empty:
        raise RuntimeError("No ops dataset available. Seed PatientFlow (hourly) first.")
    save_ops_hourly_dataset(frame)

    df = frame.overall.copy().sort_values("datetime").reset_index(drop=True)
    training_source = str(frame.overall.attrs.get("source_path", "unknown"))
    max_rows = int(os.getenv("HRO_OPS72H_ARIMAX_MAX_ROWS", "0"))
    if max_rows > 0 and len(df) > max_rows:
        # SARIMAX fitting can be slow on very long hourly histories. Use the
        # most recent window by default for practical retraining while still
        # preserving all exported datasets for review and downstream analysis.
        df = df.tail(max_rows).reset_index(drop=True)
    target = "patients"
    exog_cols = [
        "hour",
        "day_of_week",
        "month",
        "week_number",
        "season",
        "is_weekend",
        "is_holiday",
        "holiday",
        "shift_period_code",
        "appointments_count",
        "or_bookings_count",
        "doctors_available",
        "nurses_available",
        "occupied_beds",
        "waiting_patients",
        "lag_1",
        "lag_24",
        "roll_mean_3",
        "roll_mean_6",
        "roll_mean_24",
    ]

    for c in [target] + exog_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    n = len(df)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    y_train = train_df[target].astype(float)
    x_train = train_df[exog_cols].astype(float)
    y_val = val_df[target].astype(float)
    x_val = val_df[exog_cols].astype(float)
    y_test = test_df[target].astype(float)
    x_test = test_df[exog_cols].astype(float)

    print("Training ARIMAX on train split...")
    train_fit = fit_model(y_train, x_train)
    val_pred = np.array(train_fit.forecast(steps=len(x_val), exog=x_val), dtype=float).reshape(-1)
    val_metrics = evaluate(y_val.values, val_pred)

    print("Re-fitting ARIMAX on train+val...")
    train_val = pd.concat([train_df, val_df], axis=0).reset_index(drop=True)
    fit_tv = fit_model(train_val[target].astype(float), train_val[exog_cols].astype(float))
    test_pred = np.array(fit_tv.forecast(steps=len(x_test), exog=x_test), dtype=float).reshape(-1)
    test_metrics = evaluate(y_test.values, test_pred)

    # Final model on full data
    final_fit = fit_model(df[target].astype(float), df[exog_cols].astype(float))
    model_path = MODEL_DIR / "arimax_ops72h.pkl"
    joblib.dump(final_fit, model_path)

    (METRICS_DIR / "arimax_ops72h_metrics.json").write_text(
        json.dumps({"model": "ARIMAX", "training_source": training_source, "val": val_metrics, "test": test_metrics, "exog_cols": exog_cols}, indent=2),
        encoding="utf-8",
    )
    np.savez_compressed(METRICS_DIR / "arimax_ops72h_val_outputs.npz", y_true=y_val.values.astype(float), y_pred=val_pred.astype(float))
    np.savez_compressed(METRICS_DIR / "arimax_ops72h_test_outputs.npz", y_true=y_test.values.astype(float), y_pred=test_pred.astype(float))

    print("Saved:", model_path)
    print("Val metrics:", val_metrics)
    print("Test metrics:", test_metrics)


if __name__ == "__main__":
    main()
