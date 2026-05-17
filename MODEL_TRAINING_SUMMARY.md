# HRO-PS 72h Model Training Summary

## Training Dataset

- Source: `clean_data(AutoRecovered).csv`
- Confirmed training source recorded in metrics:
  - LSTM: `D:\hro-ps-ai\clean_data(AutoRecovered).csv`
  - ARIMAX: `D:\hro-ps-ai\clean_data(AutoRecovered).csv`
- Department source: `data/updated_exports/ops_hourly_by_department.csv`
- Date range: `2024-01-01 00:00:00` to `2025-12-31 23:00:00`
- Row count: 17,520 hourly rows
- Note: Feb 29, 2024 is excluded so the demo dataset contains exactly two 8,760-hour years as requested.
- Department rows: 87,600 rows, 17,520 rows for each canonical department.

## Features Used

Primary target:

- `patients`

Time/calendar features:

- `hour`
- `day_of_week`
- `month`
- `week_number`
- `season`
- `is_weekend`
- `is_holiday`
- `holiday`
- `shift_period_code`

Operational exogenous features:

- `appointments_count`
- `or_bookings_count`
- `doctors_available`
- `nurses_available`
- `occupied_beds`
- `waiting_patients`

Autoregressive features:

- `lag_1`
- `lag_24`
- `roll_mean_3`
- `roll_mean_6`
- `roll_mean_24`

## Train / Validation / Test Split

The ops72h scripts use chronological splits:

- Train: 70%
- Validation: 15%
- Test: 15%

Approximate split sizes before LSTM sequence construction:

- Train rows: 12,264
- Validation rows: 2,628
- Test rows: 2,628

LSTM uses a 24-hour sequence length, so sequence counts are reduced by 24 within each split.

## Training Commands Run

```powershell
# Retrain 2026-05-17 (full default epochs, both models from clean_data(AutoRecovered).csv)
python train_lstm_ops72h.py
python train_arimax_ops72h.py
python build_hybrid_ops72h.py
python generate_ops72h_outputs.py
```

## Final Metrics (Retrain 2026-05-17)

Test set metrics (15% chronological hold-out):

| Model | MAE | RMSE | MAPE |
|---|---:|---:|---:|
| LSTM | 7.6450 | 9.5789 | 5.52% |
| ARIMAX | 16.4501 | 20.3250 | 12.58% |
| Hybrid (0.8/0.2) | 8.4950 | 10.4532 | 6.13% |

Validation set metrics (used for weight selection):

| Model | MAE | RMSE | MAPE |
|---|---:|---:|---:|
| LSTM | 6.2535 | 8.4197 | 5.61% |
| ARIMAX | 20.6688 | 25.7710 | 22.27% |
| Hybrid (0.8/0.2) | 7.0715 | 9.2289 | 6.98% |

## Hybrid Weights

Constrained grid search (w in [0.20, 0.80], step 0.05) selected the best weights by lowest validation RMSE.

- LSTM weight: 0.80
- ARIMAX weight: 0.20
- Selection metric: validation RMSE
- Both models used: lstm_valid=True, arimax_valid=True, fallback_reasons=[]

**Note:** In this retrain, LSTM alone has lower test MAE (7.645) than the Hybrid (8.495) because ARIMAX convergence was poor (3 MLE convergence warnings). Both models are still included — the weight search found 0.8/0.2 as the best available blend within constraints.

## Forecast Artifact Status

Generated files:

- `artifacts/forecast_outputs/ops72h_overall_forecast.csv`
- `artifacts/forecast_outputs/ops72h_department_forecast.csv`
- `artifacts/metrics_72h/ops72h_model_metrics.csv`
- `artifacts/manifests/ops72h_training_summary.json`

Forecast quality (2026-05-17):

- Overall forecast rows: 72
- Department forecast rows: 360
- Departments: ER, General Ward, ICU, Surgery, Radiology
- NaN values: 0
- Negative predictions: 0
- LSTM valid: True
- ARIMAX valid: True
- Fallback used: False
- Forecast is non-negative and non-flat (hybrid_pred std=20.72).
- 72h peak: 210.37 patients
- 72h average: 186.03 patients
- Constant forecast detected by smoke test: False
- Artifact timestamp: 2026-05-17T16:08:43.214496

## LSTM Training Details (2026-05-17)

- Epochs run: 40 (early stopped at 40, best model at epoch 30)
- Max epochs configured: 60
- Batch size: 64
- Sequence length: 24 hours
- Architecture: LSTM(128) → Dropout(0.2) → LSTM(64) → Dropout(0.2) → Dense(32, relu) → Dense(1)
- Optimizer: Adam lr=0.001 with ReduceLROnPlateau

## Convergence Warnings

ARIMAX emitted 3 statsmodels MLE convergence warnings during training:

```text
ConvergenceWarning: Maximum Likelihood optimization failed to converge.
```

Not hidden. The ARIMAX output is valid (non-flat, non-NaN, non-negative) but less accurate than the previous training run. The convergence issue is a known limitation of SARIMAX (1,1,1) on large datasets with many exogenous variables. A seasonal ARIMAX (1,1,1)(1,0,1,24) would better capture hospital periodicity and is recommended for production.

## Known Limitations

- Dataset is synthetic demo data — not real hospital data.
- Metrics are for the demo distribution only — not clinically validated.
- ARIMAX convergence warnings indicate imperfect statistical fit.
- In this retrain, ARIMAX performed significantly worse than LSTM (test RMSE 20.32 vs 9.58), making the Hybrid slightly worse than LSTM alone.
- Production would require real data, model monitoring, drift detection, and formal clinical validation.

---

## Status as of 2026-05-17 Retrain

Full retrain completed from `clean_data(AutoRecovered).csv`:

| Model | MAE | RMSE | MAPE | Status |
|---|---:|---:|---:|---|
| LSTM | 7.645 | 9.579 | 5.52% | Valid |
| ARIMAX | 16.450 | 20.325 | 12.58% | Valid, 3 convergence warnings |
| **Hybrid** | **8.495** | **10.453** | **6.13%** | **Valid, genuinely blended 0.8/0.2** |

- Hybrid weights: LSTM=0.80, ARIMAX=0.20 (constraint: both must contribute 0.2–0.8)
- 72h forecast peak: 210.4, average: 186.0 (non-flat, non-negative)
- ForecastState smoke: PASSED (fallback_used=False)
- pytest: 87 passed, 0 failed
- compileall: clean
