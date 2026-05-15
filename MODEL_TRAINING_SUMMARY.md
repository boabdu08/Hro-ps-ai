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
$env:HRO_OPS72H_LSTM_EPOCHS='12'; $env:HRO_OPS72H_LSTM_BATCH_SIZE='128'; python train_lstm_ops72h.py
python train_arimax_ops72h.py
python build_hybrid_ops72h.py
python generate_ops72h_outputs.py
```

## Final Metrics

| Model | MAE | RMSE | MAPE |
|---|---:|---:|---:|
| LSTM | 7.158200 | 9.005371 | 5.329422 |
| ARIMAX | 7.796137 | 9.317053 | 5.963158 |
| Hybrid | 6.622505 | 8.148527 | 4.912072 |

## Hybrid Weights

Constrained grid search required both models to contribute between 0.2 and 0.8.

- LSTM weight: 0.8
- ARIMAX weight: 0.2
- Selection metric: validation RMSE

This is now a genuine Hybrid model, not LSTM-only or ARIMAX-only.

## Forecast Artifact Status

Generated files:

- `artifacts/forecast_outputs/ops72h_overall_forecast.csv`
- `artifacts/forecast_outputs/ops72h_department_forecast.csv`
- `artifacts/metrics_72h/ops72h_model_metrics.csv`
- `artifacts/manifests/ops72h_training_summary.json`

Forecast quality:

- Overall forecast rows: 72
- Department forecast rows: 360
- Departments: ER, General Ward, ICU, Surgery, Radiology
- LSTM valid: true
- ARIMAX valid: true
- Fallback reasons: none
- Forecast is non-negative and non-flat.

Latest generated 72h output:

- Forecast timestamp: `2026-05-10T10:11:05.448950`
- 72h peak: `252.63652782074715`
- 72h average: `222.9677434709386`
- Constant forecast detected by smoke test: `False`

## Convergence Warnings

ARIMAX emitted statsmodels convergence warnings:

```text
ConvergenceWarning: Maximum Likelihood optimization failed to converge.
```

The ARIMAX output still produced varying validation/test predictions and was retained with transparent documentation. Hybrid validation selected a 0.8 / 0.2 LSTM/ARIMAX blend.

## Known Limitations

- The dataset is synthetic demo data, not real hospital data.
- Metrics are meaningful for the demo distribution but are not clinically validated.
- ARIMAX convergence warnings indicate the statistical fit is imperfect.
- Production deployment would require real hospital data ingestion, model monitoring, drift detection, and formal validation.

---

## Status as of 2026-05-16 Overhaul

No retraining was performed in this pass — existing metrics and artifacts remain valid:

| Model | MAE | RMSE | MAPE | Status |
|---|---:|---:|---:|---|
| LSTM | 7.158 | 9.005 | 5.33% | Valid |
| ARIMAX | 7.796 | 9.317 | 5.96% | Valid (convergence warning documented) |
| **Hybrid** | **6.623** | **8.149** | **4.91%** | **Best — Valid** |

- Hybrid weights confirmed: LSTM=0.80, ARIMAX=0.20
- 72h forecast peak: 252.6, average: 222.9 (non-flat, non-negative)
- ForecastState smoke: PASSED
- Artifact timestamp: 2026-05-10T10:11:05.448950
