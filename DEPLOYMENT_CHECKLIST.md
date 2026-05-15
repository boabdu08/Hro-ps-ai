# HRO-PS Deployment Smoke Checklist

Use this checklist before the graduation-demo deployment attempt.

## Startup

- [ ] API starts with `uvicorn main:app --reload`.
- [ ] Dashboard starts with `streamlit run dashboard.py`.
- [ ] Login works for tenant `demo-hospital` and admin `admin1 / 123456`.
- [ ] No training, retraining, or data regeneration runs on startup.

## Forecast Artifacts

- [ ] `clean_data(AutoRecovered).csv` exists and has exactly 17,520 rows.
- [ ] `clean_data(AutoRecovered).csv` date range is `2024-01-01 00:00:00` to `2025-12-31 23:00:00`.
- [ ] LSTM/ARIMAX metrics JSON files record `clean_data(AutoRecovered).csv` as the training source.
- [ ] `artifacts/forecast_outputs/ops72h_overall_forecast.csv` exists and has 72 rows.
- [ ] `artifacts/forecast_outputs/ops72h_department_forecast.csv` exists and has 360 rows.
- [ ] `artifacts/metrics_72h/ops72h_model_metrics.csv` exists and has LSTM, ARIMAX, Hybrid rows.
- [ ] `artifacts/manifests/ops72h_training_summary.json` exists.
- [ ] ForecastState smoke confirms 72-hour series is non-flat.
- [ ] Hybrid weights are both active: LSTM and ARIMAX between 0.2 and 0.8.

## Dashboard Pages

- [ ] Command Center loads KPIs from ForecastState.
- [ ] Forecast loads the same 72-hour series and model metrics.
- [ ] Digital Twin uses the same 72-hour ForecastState series.
- [ ] Optimization uses `ForecastState.predicted_patients_next_hour`.
- [ ] Evaluation uses the canonical metrics table.
- [ ] Operations Center shows all departments: ER, General Ward, ICU, Surgery, Radiology.
- [ ] Shifts shows all departments and Morning, Evening, Night, Emergency Backup.
- [ ] Appointments shows non-uniform department load.
- [ ] OR Bookings shows meaningful room utilization or booking counts.
- [ ] Notifications mark Warning alerts as Monitor, Critical alerts as Required.
- [ ] Messages render Arabic text right-to-left.
- [ ] Approvals show pending items and processed decision history.
- [ ] Audit shows event logs and export works.

## Chart Checks

- [ ] Forecast chart has clear x/y labels and non-flat Hybrid output.
- [ ] Department forecast chart renders selected departments, including ICU.
- [ ] Digital Twin y-axis starts at zero.
- [ ] Evaluation MAE/RMSE bars are proportional and labeled.
- [ ] MAPE chart is clearly labeled as a caution metric.
- [ ] Optimization pressure ranking includes all departments.
- [ ] Shortage charts include a legend.
- [ ] Shift chart labels are readable.
- [ ] OR chart has readable room labels and useful values.

## Dark Mode

- [ ] Command Center text and cards readable.
- [ ] Forecast charts and tables readable.
- [ ] Digital Twin chart readable.
- [ ] Optimization cards/charts/tables readable.
- [ ] Evaluation charts readable.
- [ ] Explainability table readable.
- [ ] Messages, Notifications, Approvals, Audit readable.

## Data Relationship Checks

- [ ] All `staff_schedule.staff_id` values exist in staff master.
- [ ] Appointment doctors exist in staff master.
- [ ] OR booking doctors exist in staff master.
- [ ] No duplicate IDs in staff, appointments, OR bookings, tracking, scenarios.
- [ ] No negative patient/resource values in required operational files.
- [ ] No impossible single-hour patient spikes above 3x the rolling 24-hour average.

## Commands

```powershell
python scripts\smoke_forecast_state.py
python -m pytest -q
python -m compileall dashboard.py dashboard_sections.py staff_sections.py notification_sections.py message_center_sections.py approval_sections.py audit_sections.py api.py api_client.py database.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py forecast_state.py forecast_inference_ops72h.py generate_ops72h_outputs.py -q
```

---

## Overhaul Verification (2026-05-16)

Current validation state after senior overhaul pass:

| Check | Result |
|---|---|
| `compileall` (all root .py files) | PASS |
| `pytest` (87 tests) | 87 passed, 0 failed |
| `smoke_forecast_state.py` | PASSED |
| `what_if_scenarios.csv` row count ≥ 40 | PASS (42 rows) |
| `what_if_scenarios.csv` schema (21 cols) | PASS |
| DEPARTMENT_CONFIG capacities calibrated | PASS |
| Department-specific staff ratios | PASS |
| UI_BUILD_ID current | PASS (2026-05-16-overhaul) |
| FastAPI lifespan pattern (not deprecated) | PASS |
| `/health/full` endpoint | PASS |

### Data Integrity Quick Check

```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/updated_exports/what_if_scenarios.csv')
assert len(df) >= 40, f'Only {len(df)} rows'
assert 'scenario_id' in df.columns
print(f'what_if_scenarios: {len(df)} rows, {len(df.columns)} columns - OK')
"
```

### Pre-Demo Final Check Command

```powershell
$env:PYTHONPATH = "D:\hro-ps-ai"
python scripts\smoke_forecast_state.py
python -m pytest tests\ -q
```
