"""Generate saved 72-hour forecast and consolidated metrics outputs.

Run after `train_lstm_ops72h.py`, `train_arimax_ops72h.py`, and
`build_hybrid_ops72h.py`. The dashboard/API can read these stable files without
changing the Command Center 24h forecast path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from forecast_inference_ops72h import forecast_ops72h


FORECAST_DIR = Path("artifacts") / "forecast_outputs"
METRICS_DIR = Path("artifacts") / "metrics"
FORECAST_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    fc = forecast_ops72h(horizon_hours=72)
    overall_path = FORECAST_DIR / "ops72h_overall_forecast.csv"
    dept_path = FORECAST_DIR / "ops72h_department_forecast.csv"
    fc.overall.to_csv(overall_path, index=False)
    fc.by_department.to_csv(dept_path, index=False)

    hybrid_metrics = _read_json(Path("artifacts") / "metrics_72h" / "hybrid_ops72h_metrics.json")
    lstm_metrics = _read_json(Path("artifacts") / "metrics_72h" / "lstm_ops72h_metrics.json")
    arimax_metrics = _read_json(Path("artifacts") / "metrics_72h" / "arimax_ops72h_metrics.json")

    test_metrics = hybrid_metrics.get("test", {}) if isinstance(hybrid_metrics, dict) else {}
    rows = []
    if "LSTM" in test_metrics:
        rows.append({"Model": "LSTM", **test_metrics["LSTM"]})
    elif lstm_metrics.get("test"):
        rows.append({"Model": "LSTM", **lstm_metrics["test"]})
    if "ARIMAX" in test_metrics:
        rows.append({"Model": "ARIMAX", **test_metrics["ARIMAX"]})
    elif arimax_metrics.get("test"):
        rows.append({"Model": "ARIMAX", **arimax_metrics["test"]})
    if "Hybrid" in test_metrics:
        rows.append({"Model": "Hybrid", **test_metrics["Hybrid"]})

    metrics_df = pd.DataFrame(rows)
    best_model = None
    if not metrics_df.empty and "RMSE" in metrics_df.columns:
        best_model = str(metrics_df.sort_values("RMSE", ascending=True).iloc[0]["Model"])
    metrics_df.to_csv(METRICS_DIR / "ops72h_model_metrics.csv", index=False)

    summary = {
        "forecast_horizon_hours": 72,
        "generated_at": fc.generated_at,
        "overall_forecast_path": str(overall_path),
        "department_forecast_path": str(dept_path),
        "metrics_csv_path": str(METRICS_DIR / "ops72h_model_metrics.csv"),
        "best_model": best_model,
        "weights": fc.weights,
        "hybrid_config": hybrid_metrics,
    }
    (METRICS_DIR / "ops72h_training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved overall forecast:", overall_path)
    print("Saved department forecast:", dept_path)
    print("Saved metrics:", METRICS_DIR / "ops72h_model_metrics.csv")
    print("Best model:", best_model)


if __name__ == "__main__":
    main()