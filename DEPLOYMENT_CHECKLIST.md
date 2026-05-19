# HRO-PS Deployment Smoke Checklist

> **Note:** Unchecked boxes (`[ ]`) are intended for **manual live deployment walkthrough** — they cannot be verified without running the full stack. Items marked **(Automated: PASS)** have already been verified by the test suite and smoke scripts as of the 2026-05-18/19 validation run.

---

## Minimum Before Sharing Link

These are the absolute minimum checks before sending the demo URL to anyone.

- [ ] `GET /health/full` returns `{"api":"ok","database":"ok","artifacts":"ok","forecast_ready":true}`
- [ ] Login works for `admin1 / 123456` on tenant `demo-hospital`
- [ ] Command Center tab loads KPIs without error
- [ ] Forecast tab renders 72-hour chart
- [ ] Optimization tab runs and shows department allocation
- [ ] Approvals tab shows pending items
- [ ] Audit tab shows event logs

---

## Section 1 — Local / CI Verified (pre-push)

These items have been confirmed by automated tests and smoke scripts. No manual re-check required unless artifact files change.

- [x] `clean_data(AutoRecovered).csv` exists and has exactly 17,520 rows **(Automated: PASS — test_data_integrity.py)**
- [x] `clean_data(AutoRecovered).csv` date range is `2024-01-01 00:00:00` to `2025-12-31 23:00:00` **(Automated: PASS)**
- [x] LSTM/ARIMAX metrics JSON files record `clean_data(AutoRecovered).csv` as the training source **(Automated: PASS)**
- [x] `artifacts/forecast_outputs/ops72h_overall_forecast.csv` exists and has 72 rows **(Automated: PASS — smoke_forecast_state.py)**
- [x] `artifacts/forecast_outputs/ops72h_department_forecast.csv` exists and has 360 rows **(Automated: PASS)**
- [x] `artifacts/metrics_72h/ops72h_model_metrics.csv` exists with LSTM, ARIMAX, Hybrid rows **(Automated: PASS)**
- [x] `artifacts/manifests/ops72h_training_summary.json` exists **(Automated: PASS)**
- [x] ForecastState smoke confirms 72-hour series is non-flat **(Automated: PASS — smoke_forecast_state.py)**
- [x] Hybrid weights both active: LSTM=0.80, ARIMAX=0.20 **(Automated: PASS)**
- [x] `data/updated_exports/what_if_scenarios.csv` — 42 rows, 21 columns **(Automated: PASS)**
- [x] No negative patient/resource values in operational files **(Automated: PASS — test_data_integrity.py)**
- [x] Python compilation clean — all key .py files **(Automated: PASS — compileall)**
- [x] All tests pass (108 as of 2026-05-19) **(Automated: PASS — pytest)**

---

## Section 2 — Pre-Deployment (before starting cloud deploy)

- [ ] `.gitignore` exceptions are in place — run `git check-ignore -v artifacts/models_72h/lstm_ops72h.keras`; it should print nothing (NOT ignored).
- [ ] `git status` is clean — no untracked or modified files.
- [ ] All required artifact files are committed — run `git ls-files artifacts/` and confirm model/forecast/metrics files are listed.
- [ ] `requirements-api.txt` and `requirements-dashboard.txt` are up to date.
- [ ] `render.yaml` is committed and points to correct entry points.
- [ ] Neon database is provisioned and `DATABASE_URL` connection string is ready.
- [ ] `JWT_SECRET_KEY` is set to a strong random secret (not the demo default).
- [ ] `CORS_ORIGINS` will include the dashboard Render URL.
- [ ] `API_BASE_URL` in the dashboard service env is set to the deployed API URL.

---

## Section 3 — Live Deployment Verification (after cloud deploy)

### Startup

- [ ] API starts; `GET /health` returns 200.
- [ ] `GET /health/full` returns `{"api":"ok","database":"ok","artifacts":"ok","forecast_ready":true}`.
- [ ] Dashboard starts and is reachable at its public URL.
- [ ] Login works for tenant `demo-hospital` with `admin1 / 123456`.
- [ ] No training, retraining, or data regeneration runs on startup.

### Dashboard Pages

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
- [ ] Explainability tab loads with feature impact bars (pressure-increasing and pressure-reducing columns).
- [ ] Explainability tab: base prediction KPI card shows a patient count (not 0 or blank).
- [ ] Explainability tab: plain-English feature meanings are readable in the impact table.
- [ ] Explainability tab: no "unavailable" error shown.
- [ ] Explainability tab: method is labeled as feature sensitivity analysis (not SHAP).
- [ ] What-if Scenarios: scenario table loads and shows ≥ 40 rows.
- [ ] What-if Scenarios: demand/resource sliders affect simulated output.

### Chart Checks

- [ ] Forecast chart has clear x/y labels and non-flat Hybrid output.
- [ ] Department forecast chart renders selected departments, including ICU.
- [ ] Digital Twin y-axis starts at zero.
- [ ] Evaluation MAE/RMSE bars are proportional and labeled.
- [ ] MAPE chart is clearly labeled as a caution metric.
- [ ] Optimization pressure ranking includes all departments.
- [ ] Shortage charts include a legend.
- [ ] Shift chart labels are readable.
- [ ] OR chart has readable room labels and useful values.
- [ ] Feature impact bars have readable feature names and numerical impact values.
- [ ] Positive drivers (left column) and negative drivers (right column) both render in Explainability.

### Dark Mode

- [ ] Command Center text and cards readable.
- [ ] Forecast charts and tables readable.
- [ ] Digital Twin chart readable.
- [ ] Optimization cards/charts/tables readable.
- [ ] Evaluation charts readable.
- [ ] Explainability table readable.
- [ ] Messages, Notifications, Approvals, Audit readable.

### Data Relationship Checks

- [ ] All `staff_schedule.staff_id` values exist in staff master.
- [ ] Appointment doctors exist in staff master.
- [ ] OR booking doctors exist in staff master.
- [ ] No duplicate IDs in staff, appointments, OR bookings, tracking, scenarios.
- [ ] `users.csv` has ≥ 25 accounts covering admin, doctor, and nurse roles.
- [ ] Login works for all named demo accounts (admin1, admin2, ops_manager, doctor1, doctor2, nurse1, nurse2, stf-0001).

---

## Section 4 — Final Jury Demo Preparation

### Cold-Start Preparation (do this 10 minutes before presenting)

Free-tier Render services spin down after inactivity. A cold-start can add 30–90 seconds on the first request and an additional 15–30 seconds for Streamlit's first full render.

- [ ] Open the API health URL (e.g., `https://hro-ps-api.onrender.com/health/full`) at least **10 minutes before the demo** to wake the service.
- [ ] Open the dashboard URL at least **10 minutes before the demo**.
- [ ] Confirm `/health/full` returns `{"api":"ok","database":"ok","artifacts":"ok","forecast_ready":true}`.
- [ ] Navigate to the Command Center tab and wait for the KPIs to populate (first load warms the 600-second ForecastState cache).
- [ ] Keep the browser tabs open and active — do not close or allow them to idle before presenting.
- [ ] **Prepare a screenshots fallback:** capture Command Center, Forecast, Optimization, and Approvals in case the live service becomes unavailable during the demo.

### Jury Demo Walkthrough Order

1. Login as `admin1 / 123456` on tenant `demo-hospital`.
2. Command Center — KPIs, forecast accuracy caption (Hybrid MAE 6.6 | RMSE 8.1 | MAPE 4.9%).
3. Forecast — 72-hour chart, three model comparison, hybrid weights grid-search result.
4. Optimization — run MILP solver, department resource allocation.
5. Approvals — pending AI recommendation, approve, confirm audit entry created.
6. Audit — show the audit log entry for the approval.
7. Explainability — feature sensitivity bars, pressure-increasing and pressure-reducing drivers.
8. Digital Twin — horizon slider (Hour 1 = next hour, Hour 72 = 3 days ahead).
9. Simulation / What-if — 42-scenario library, demand/resource sliders.

---

## Commands

```powershell
python scripts\smoke_forecast_state.py
python -m pytest -q
python -m compileall dashboard.py dashboard_sections.py staff_sections.py notification_sections.py message_center_sections.py approval_sections.py audit_sections.py api.py api_client.py database.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py forecast_state.py forecast_inference_ops72h.py generate_ops72h_outputs.py -q
```

---

## Retrain Verification (2026-05-18 ARIMAX improvement; LSTM unchanged from 2026-05-17)

| Check | Result |
|---|---|
| `compileall` (all key .py files) | PASS |
| `pytest` (87 tests) | 87 passed, 0 failed |
| `smoke_forecast_state.py` | PASSED (fallback_used=False) |
| Dataset rows | 17,520 ✓ |
| Dataset NaN | 0 ✓ |
| LSTM test metrics | MAE=7.645, RMSE=9.579, MAPE=5.52% (unchanged) |
| ARIMAX test metrics | MAE=15.678, RMSE=19.391, MAPE=12.44% (**0 convergence warnings**) |
| Hybrid test metrics | MAE=8.311, RMSE=10.215, MAPE=6.07% (improved from 10.453) |
| Hybrid weights | LSTM=0.80, ARIMAX=0.20 (both models valid) |
| Unconstrained optimum | LSTM=0.95, ARIMAX=0.05 (LSTM-dominant) |
| Best model by test RMSE | **LSTM** (9.579 < Hybrid 10.215) |
| Overall forecast rows | 72 ✓ |
| Department forecast rows | 360 ✓ |
| Forecast NaN/negatives | 0 / 0 ✓ |
| Forecast non-flat | True (smoke: PASSED) ✓ |
| 72h peak | 218.4 patients |
| `what_if_scenarios.csv` row count ≥ 40 | PASS (42 rows) |
| `what_if_scenarios.csv` schema (21 cols) | PASS |

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
