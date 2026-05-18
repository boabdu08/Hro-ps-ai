"""ARIMAX/SARIMAX candidate experiment.

Tests multiple SARIMAX configurations on the same train/val/test split,
reports validation and test metrics for each, and picks the best configuration.

Does NOT modify any existing artifact. Run this first, review the results,
then update train_arimax_ops72h.py if a candidate beats the baseline.

Usage:
    python experiment_arimax_candidates.py
"""

from __future__ import annotations

import warnings
import time
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX

from forecasting_pipeline import build_ops_hourly_frame


def mape_safe(y_true, y_pred):
    y_true = np.array(y_true, dtype=float).reshape(-1)
    y_pred = np.array(y_pred, dtype=float).reshape(-1)
    denom = np.where(np.abs(y_true) < 1e-8, 1.0, np.abs(y_true))
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def evaluate(y_true, y_pred):
    y_true = np.array(y_true, dtype=float).reshape(-1)
    y_pred = np.array(y_pred, dtype=float).reshape(-1)
    if not np.isfinite(y_pred).all():
        return None  # NaN/Inf in predictions — convergence failure
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(mean_squared_error(y_true, y_pred) ** 0.5)
    mape = mape_safe(y_true, y_pred)
    return {"MAE": round(mae, 4), "RMSE": round(rmse, 4), "MAPE": round(mape, 4)}


def fit_and_forecast(
    y_train, x_train, y_val, x_val,
    order, seasonal_order, method="powell", maxiter=300,
):
    """Fit SARIMAX on train, forecast val. Returns (val_pred, fit_obj, n_warnings)."""
    n_warnings = 0

    def count_warning(message, category, *args, **kwargs):
        nonlocal n_warnings
        n_warnings += 1

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.showwarning = count_warning
        try:
            model = SARIMAX(
                endog=y_train,
                exog=x_train,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
                trend=None,
            )
            fit = model.fit(method=method, maxiter=maxiter, disp=False)
            val_pred = np.array(fit.forecast(steps=len(x_val), exog=x_val), dtype=float).reshape(-1)
            return val_pred, fit, n_warnings
        except Exception as e:
            return None, None, n_warnings


EXOG_FULL = [
    "hour", "day_of_week", "month", "week_number", "season",
    "is_weekend", "is_holiday", "holiday", "shift_period_code",
    "appointments_count", "or_bookings_count",
    "doctors_available", "nurses_available", "occupied_beds", "waiting_patients",
    "lag_1", "lag_24", "roll_mean_3", "roll_mean_6", "roll_mean_24",
]

# 7-variable reduced set: eliminates multicollinearity without losing key information.
# Keeps direct autoregressive features (lag_1, lag_24), the daily-cycle pattern
# (hour, is_weekend), the smoothed trend (roll_mean_24), and the two most stable
# operational demand drivers (appointments_count, occupied_beds).
EXOG_REDUCED = [
    "lag_1", "lag_24", "roll_mean_24",
    "hour", "is_weekend",
    "appointments_count", "occupied_beds",
]

# 5-variable minimal set: only autoregressive + temporal
EXOG_MINIMAL = [
    "lag_1", "lag_24", "roll_mean_24",
    "hour", "is_weekend",
]

CANDIDATES = [
    # (label, order, seasonal_order, exog_key, method, maxiter)
    # Baseline is SKIPPED (already trained: val RMSE=25.77, test RMSE=20.32, 3 warnings)
    ("C1: (1,1,1)x(0) 7-exog Powell",
     (1,1,1), (0,0,0,0), "reduced", "powell", 300),
    ("C2: (1,1,1)x(1,0,0,24) 7-exog Powell",
     (1,1,1), (1,0,0,24), "reduced", "powell", 300),
    ("C3: (1,1,0)x(1,0,0,24) 7-exog Powell",
     (1,1,0), (1,0,0,24), "reduced", "powell", 300),
    ("C4: (1,1,1)x(1,0,0,24) 5-exog Powell",
     (1,1,1), (1,0,0,24), "minimal", "powell", 300),
    ("C5: (2,1,0)x(1,0,0,24) 7-exog Powell",
     (2,1,0), (1,0,0,24), "reduced", "powell", 300),
]

EXOG_MAP = {"full": EXOG_FULL, "reduced": EXOG_REDUCED, "minimal": EXOG_MINIMAL}


def main():
    print("Loading training data...")
    frame = build_ops_hourly_frame()
    if frame.overall.empty:
        raise RuntimeError("No ops dataset available.")

    df = frame.overall.copy().sort_values("datetime").reset_index(drop=True)
    print(f"Dataset: {len(df)} rows")

    target = "patients"
    all_cols = list(set(EXOG_FULL + EXOG_REDUCED + EXOG_MINIMAL))
    for c in all_cols + [target]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    n = len(df)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    print(f"Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")
    print()

    results = []

    for label, order, seasonal_order, exog_key, method, maxiter in CANDIDATES:
        exog_cols = EXOG_MAP[exog_key]
        # Ensure all columns exist
        for c in exog_cols:
            if c not in train_df.columns:
                train_df[c] = 0.0
                val_df[c] = 0.0
                test_df[c] = 0.0

        x_train = train_df[exog_cols].astype(float)
        y_train = train_df[target].astype(float)
        x_val = val_df[exog_cols].astype(float)
        y_val = val_df[target].astype(float)
        x_test = test_df[exog_cols].astype(float)
        y_test = test_df[target].astype(float)

        print(f"Testing: {label}")
        print(f"  order={order}, seasonal={seasonal_order}, exog={exog_key}({len(exog_cols)} cols), method={method}, maxiter={maxiter}")
        t0 = time.time()

        val_pred, fit_obj, n_warn = fit_and_forecast(
            y_train, x_train, y_val, x_val,
            order, seasonal_order, method=method, maxiter=maxiter,
        )

        elapsed = time.time() - t0

        if val_pred is None or fit_obj is None:
            print(f"  FAILED (fit or forecast error). Elapsed: {elapsed:.1f}s")
            results.append({
                "label": label, "order": order, "seasonal_order": seasonal_order,
                "exog_key": exog_key, "method": method, "maxiter": maxiter,
                "val_metrics": None, "test_metrics": None,
                "n_warnings": n_warn, "elapsed_s": elapsed, "failed": True,
            })
            continue

        val_pred_clipped = np.clip(val_pred, 0, None)
        val_m = evaluate(y_val.values, val_pred_clipped)
        if val_m is None:
            print(f"  Val predictions contain NaN — convergence failure. Skipping test eval.")
            results.append({
                "label": label, "order": order, "seasonal_order": seasonal_order,
                "exog_key": exog_key, "method": method, "maxiter": maxiter,
                "val_metrics": None, "test_metrics": None,
                "n_warnings": n_warn, "elapsed_s": elapsed, "failed": True,
                "fail_reason": "NaN in val predictions",
            })
            continue

        # Also get test metrics by refitting on train+val
        print(f"  Refitting on train+val for test metrics...")
        tv_df = pd.concat([train_df, val_df], axis=0).reset_index(drop=True)
        t1 = time.time()
        test_pred, _, n_warn2 = fit_and_forecast(
            tv_df[target].astype(float), tv_df[exog_cols].astype(float),
            y_test, x_test,
            order, seasonal_order, method=method, maxiter=maxiter,
        )
        elapsed2 = time.time() - t1

        if test_pred is None:
            test_m = None
        else:
            test_m = evaluate(y_test.values, np.clip(test_pred, 0, None))
            # test_m may be None if test_pred contains NaN

        total_warn = n_warn + n_warn2
        print(f"  Val  metrics: {val_m}")
        print(f"  Test metrics: {test_m if test_m else 'NaN/failed'}")
        print(f"  Convergence warnings: {total_warn} | Elapsed: {elapsed:.1f}s + {elapsed2:.1f}s")
        print()

        results.append({
            "label": label, "order": order, "seasonal_order": seasonal_order,
            "exog_key": exog_key, "method": method, "maxiter": maxiter,
            "val_metrics": val_m, "test_metrics": test_m,
            "n_warnings": total_warn, "elapsed_s": elapsed + elapsed2, "failed": False,
        })

    # Summary
    print("=" * 70)
    print("EXPERIMENT SUMMARY")
    print("=" * 70)
    valid = [r for r in results if not r.get("failed") and r["val_metrics"] is not None]
    if not valid:
        print("All candidates failed. Keeping current ARIMAX.")
        return

    best = min(valid, key=lambda r: r["val_metrics"]["RMSE"])
    print(f"\nBest candidate by validation RMSE: {best['label']}")
    print(f"  Val RMSE : {best['val_metrics']['RMSE']:.4f}")
    test_rmse_str = f"{best['test_metrics']['RMSE']:.4f}" if best.get("test_metrics") else "N/A"
    print(f"  Test RMSE: {test_rmse_str}")
    print(f"  Warnings : {best['n_warnings']}")

    baseline = next((r for r in results if "Baseline" in r["label"]), None)
    if baseline and not baseline.get("failed") and baseline["val_metrics"]:
        print(f"\nBaseline val RMSE : {baseline['val_metrics']['RMSE']:.4f}")
        print(f"Baseline test RMSE: {baseline['test_metrics']['RMSE']:.4f}" if baseline["test_metrics"] else "Baseline test RMSE: N/A")
        improvement = baseline["val_metrics"]["RMSE"] - best["val_metrics"]["RMSE"]
        print(f"Val RMSE improvement: {improvement:.4f}")
        if improvement > 0.1:
            print("\n>>> RECOMMENDATION: Update train_arimax_ops72h.py with the best candidate configuration.")
        else:
            print("\n>>> No meaningful improvement found. Keep current ARIMAX configuration.")

    print("\nFull results table:")
    print(f"{'Label':<50} {'Val MAE':>8} {'Val RMSE':>9} {'Test RMSE':>10} {'Warn':>5}")
    print("-" * 90)
    for r in results:
        if r.get("failed"):
            print(f"  {r['label']:<48} {'FAILED':>8}")
        elif r["val_metrics"]:
            tr = r["test_metrics"]["RMSE"] if r["test_metrics"] else float("nan")
            print(f"  {r['label']:<48} {r['val_metrics']['MAE']:>8.4f} {r['val_metrics']['RMSE']:>9.4f} {tr:>10.4f} {r['n_warnings']:>5}")

    # Save experiment results
    out_path = "artifacts/metrics_72h/arimax_experiment_results.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
