"""Build Hybrid forecast combiner (LSTM + ARIMAX) for ops-aware 72h pipeline.

Hybrid formula:
  hybrid = w * lstm + (1-w) * arimax

We search w in [0.0..1.0] step 0.05 and choose the best (lowest validation RMSE).
Outputs:
  - artifacts/models_72h/hybrid_config.json
  - artifacts/metrics_72h/hybrid_ops72h_metrics.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error

from forecasting_pipeline import METRICS_DIR, MODEL_DIR


def mape_safe(y_true, y_pred):
    y_true = np.array(y_true, dtype=float).reshape(-1)
    y_pred = np.array(y_pred, dtype=float).reshape(-1)
    denom = np.where(np.abs(y_true) < 1e-8, 1.0, np.abs(y_true))
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    mape = mape_safe(y_true, y_pred)
    return {"MAE": float(mae), "RMSE": float(rmse), "MAPE": float(mape)}


def _load_npz(path: Path):
    data = np.load(path)
    return np.array(data["y_true"], dtype=float).reshape(-1), np.array(data["y_pred"], dtype=float).reshape(-1)


def find_best_weight(y_true, lstm_pred, arimax_pred):
    best = {"w": 0.5, "rmse": float("inf"), "pred": None}
    for w in np.arange(0.0, 1.0001, 0.05):
        pred = w * lstm_pred + (1.0 - w) * arimax_pred
        rmse = float(mean_squared_error(y_true, pred) ** 0.5)
        if rmse < best["rmse"]:
            best = {"w": float(round(w, 4)), "rmse": rmse, "pred": pred}
    return best["w"], float(round(1.0 - best["w"], 4)), best["pred"]


def main():
    lstm_val = METRICS_DIR / "lstm_ops72h_val_outputs.npz"
    arimax_val = METRICS_DIR / "arimax_ops72h_val_outputs.npz"
    lstm_test = METRICS_DIR / "lstm_ops72h_test_outputs.npz"
    arimax_test = METRICS_DIR / "arimax_ops72h_test_outputs.npz"

    for p in [lstm_val, arimax_val, lstm_test, arimax_test]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required outputs: {p}")

    y_val_true_lstm, y_val_lstm = _load_npz(lstm_val)
    y_val_true_ar, y_val_ar = _load_npz(arimax_val)
    y_test_true_lstm, y_test_lstm = _load_npz(lstm_test)
    y_test_true_ar, y_test_ar = _load_npz(arimax_test)

    # Align lengths (use tail overlap)
    m = min(len(y_val_true_lstm), len(y_val_lstm), len(y_val_true_ar), len(y_val_ar))
    y_val_true = y_val_true_lstm[-m:]
    y_val_lstm = y_val_lstm[-m:]
    y_val_ar = y_val_ar[-m:]

    m2 = min(len(y_test_true_lstm), len(y_test_lstm), len(y_test_true_ar), len(y_test_ar))
    y_test_true = y_test_true_lstm[-m2:]
    y_test_lstm = y_test_lstm[-m2:]
    y_test_ar = y_test_ar[-m2:]

    w_lstm, w_ar, y_val_hybrid = find_best_weight(y_val_true, y_val_lstm, y_val_ar)
    y_test_hybrid = w_lstm * y_test_lstm + w_ar * y_test_ar

    val_metrics = {
        "LSTM": metrics(y_val_true, y_val_lstm),
        "ARIMAX": metrics(y_val_true, y_val_ar),
        "Hybrid": metrics(y_val_true, y_val_hybrid),
    }
    test_metrics = {
        "LSTM": metrics(y_test_true, y_test_lstm),
        "ARIMAX": metrics(y_test_true, y_test_ar),
        "Hybrid": metrics(y_test_true, y_test_hybrid),
    }

    cfg = {
        "lstm_weight": w_lstm,
        "arimax_weight": w_ar,
        "selection_metric": "validation_rmse",
        "validation": val_metrics,
        "test": test_metrics,
        "alignment_note": "Aligned on shortest tail overlap between model outputs.",
    }
    (MODEL_DIR / "hybrid_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (METRICS_DIR / "hybrid_ops72h_metrics.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    print("Best weights:", w_lstm, w_ar)
    print("Hybrid validation metrics:", val_metrics["Hybrid"])
    print("Hybrid test metrics:", test_metrics["Hybrid"])


if __name__ == "__main__":
    main()
