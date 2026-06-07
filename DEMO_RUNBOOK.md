# HRO-PS Graduation Demo Runbook

## 1. Demo Purpose

This runbook guides a 5-7 minute graduation demo of **HRO-PS: Hospital Resource Optimization and Patient Surge Forecasting System**.

The demo goal is to show that HRO-PS can help hospital operations teams:

- monitor current patient pressure,
- forecast short-term surge risk,
- compare AI forecast models,
- explore future operational pressure through a digital twin,
- generate resource recommendations,
- test what-if scenarios,
- coordinate alerts, approvals, and audit workflows.

## 2. System Positioning

Use this wording at the start:

> HRO-PS is a graduation-demo prototype for AI-powered hospital operations decision support. It uses realistic synthetic/demo data, not real patient data. The system demonstrates forecasting, optimization, simulation, evaluation, and coordination workflows. It is not production hospital SaaS yet; real deployment would require hospital integration, clinical/operations validation, security, compliance, monitoring, and tenant isolation hardening.

Important points:

- This is a **functional prototype**, not a static mockup.
- It uses **realistic synthetic/demo data**.
- It uses **no real patient data**.
- It does **not** claim clinical decision authority.
- It is **not production SaaS yet**.
- Models and artifacts are pre-generated; the app should not train on startup.

## 3. Login Details

Tenant:

```text
demo-hospital
```

Admin:

```text
Username: admin1
Password: 123456
```

Doctor:

```text
Username: doctor1
Password: 123456
```

Nurse:

```text
Username: nurse1
Password: 123456
```

Recommended live demo login: **admin1 / 123456**.

## 4. Demo Story Flow

Recommended timing:

- Command Center: 60 seconds
- Forecast: 60 seconds
- Digital Twin: 45 seconds
- Optimization: 60 seconds
- What-if Scenarios: 45 seconds
- Evaluation: 45 seconds
- Explainability: 30 seconds
- Staff / Appointments / OR Bookings: 45 seconds
- Notifications / Messages / Approvals / Audit: 60 seconds

## 5. Step-by-Step Demo Script

### Step 1: Command Center

What to click:

- Log in as admin.
- Open **Command Center**.

What to show:

- Current patients.
- Next-hour forecast.
- 24h peak.
- 72h peak.
- 72h average.
- Risk signal.
- Artifact timestamp.
- Department pressure summary.

What to say:

> This is the main operational view. It summarizes the current hospital load, the next-hour patient forecast, the 24-hour and 72-hour pressure outlook, and the current risk signal. The important engineering point is that these values come from the canonical ForecastState, so the same forecast values are reused across Forecast, Digital Twin, Optimization, Evaluation, and API responses.

Value to hospital operations:

- Gives leadership a fast pressure snapshot.
- Helps detect surge risk before departments become overloaded.
- Reduces confusion from disconnected dashboards.

Fallback explanation if asked:

> If a model output is invalid or too flat, HRO-PS does not silently display it as reliable. It marks the model status and uses a labeled safe fallback so the dashboard remains honest.

### Step 2: Forecast

What to click:

- Open **Forecast**.

What to show:

- 72-hour overall forecast chart.
- LSTM / ARIMAX / Hybrid lines if available.
- Department forecast chart.
- Model comparison metrics.
- Training/artifact summary.

What to say:

> This tab shows the 72-hour patient surge forecast. The system compares LSTM, ARIMAX, and Hybrid outputs, but it validates them before display. The Forecast tab uses the same 72-hour series as the Command Center and Digital Twin, so the numbers stay consistent.

Value to hospital operations:

- Supports proactive bed and staff planning.
- Shows when patient pressure may rise or ease.
- Lets departments understand expected demand.

Fallback explanation if asked:

> In the current artifact run, the system detected invalid LSTM behavior and near-flat ARIMAX behavior, so the manifest records that a time-aware fallback was used. This is safer than showing a misleading flat or broken model output.

### Step 3: Digital Twin

What to click:

- Open **Operations Center**.
- Select **Digital Twin** tab.
- Move the horizon slider.
- Try department selection if available.

What to show:

- +1h or selected horizon forecast.
- 72h peak.
- Forecast curve.
- Department-level pressure.

What to say:

> The Digital Twin lets us probe the future state of the hospital over the next 72 hours. It is not using a separate static sequence; it reads the same ForecastState 72-hour forecast used by the Forecast tab.

Value to hospital operations:

- Helps answer “what will pressure look like in 6, 12, 24, or 72 hours?”
- Makes future pressure visible before operational bottlenecks happen.

Fallback explanation if asked:

> If the curve stabilizes, the dashboard explains whether this is from the saved forecast artifact or a fallback status. It does not pretend every model output is perfect.

### Step 4: Optimization

What to click:

- Open **Optimization**.

What to show:

- Beds needed.
- Doctors needed.
- Nurses needed.
- Top priority department.
- Department allocation table.
- Pressure ranking chart.
- Shortage chart.
- Recommendations and action plan.

What to say:

> Optimization converts the forecast into operational recommendations. It uses the same next-hour forecast from ForecastState as its input, then estimates beds, doctors, nurses, shortages, and department priority scores.

Value to hospital operations:

- Turns prediction into action.
- Helps prioritize departments with the highest pressure.
- Supports transparent resource planning.

Fallback explanation if asked:

> Recommendations are generated from forecast pressure and resource availability. They are not manually hardcoded for visual effect.

### Step 5: What-if Scenarios

What to click:

- Open **Operations Center**.
- Select **Simulation** or **What-if Scenarios**.
- Adjust demand/resource sliders.
- Select scenario filters if available.

What to show:

- Simulated patients.
- Emergency signal.
- Bed allocation.
- Doctor shortage.
- Scenario summary.
- Scenario charts/tables.

What to say:

> This section lets hospital managers test operational stress scenarios, such as increased demand or reduced resource availability. The sliders affect the simulated patient load, emergency level, shortages, and resource recommendations.

Value to hospital operations:

- Supports planning before emergencies.
- Helps compare possible operational responses.
- Makes surge planning interactive.

Fallback explanation if asked:

> Scenario data is demo data, not a real hospital emergency feed. It is used to demonstrate the decision workflow safely.

### Step 6: Evaluation

What to click:

- Open **Evaluation**.

What to show:

- Model metrics table.
- MAE/RMSE chart.
- MAPE as caution metric.
- Actual vs forecast chart if available.
- Best model by stable criteria.

What to say:

> Evaluation explains how model quality is assessed. We emphasize MAE and RMSE because they measure error in patient-count units. MAPE is shown as a caution metric because it can become misleading when actual values are small.

Value to hospital operations:

- Builds trust in the forecast.
- Shows error in understandable units.
- Avoids blind reliance on one metric.

Fallback explanation if asked:

> If model quality checks fail, the system records quality flags. This is important because operations teams need honest model status, not just a polished chart.

### Step 7: Explainability

**Important:** The Explainability tab requires the FastAPI service (`uvicorn`) to be running and reachable at `API_BASE_URL`. If the API is offline, the tab displays an empty state: *"Explainability service unavailable."* Always start the API before the dashboard, and confirm `/health` returns OK before presenting this tab.

What to click:

- Open **Explainability**.

What to show:

- Forecast context card (day, hour, shift, weekend/holiday status, current patients).
- Base prediction (sensitivity baseline).
- Active pressure-increasing drivers chart.
- Active pressure-reducing drivers chart.
- Feature contribution table (active drivers only).
- Context indicators expander (inactive or background features).

What to say:

> Explainability explains what inputs are actively driving the current forecast. Features that are inactive — like 'Weekend effect' on a weekday — are moved to the 'Context indicators' section so they don't mislead the viewer. The main charts show only features that are genuinely contributing to today's pressure level.

Value to hospital operations:

- Improves trust.
- Helps users understand why pressure is increasing or decreasing right now.
- Prevents confusion from showing irrelevant calendar features as "top drivers."
- Supports model review and accountability.

Fallback explanation if asked about weekend/holiday features not appearing:

> Calendar features like weekend effect and holiday effect are only shown as active drivers when they are actually on — that is, when is_weekend or is_holiday equals 1 in the current input. If today is a weekday, the model still contains this feature, but it is correctly classified as inactive for today's forecast context.

Fallback explanation if the tab shows empty state:

> The Explainability tab requires the API service to be running. Start uvicorn and reload the dashboard. This is not a model failure — it means the live inference endpoint is temporarily unavailable.

### Step 8: Staff / Appointments / OR Bookings

What to click:

- Open **Shifts**.
- Open **Appointments**.
- Open **OR Bookings**.

What to show:

- Staff schedule.
- Appointment loads.
- OR booking status.
- Department context.

What to say:

> HRO-PS connects forecasting with operational context. Patient demand alone is not enough; staffing, appointments, and OR activity also affect department pressure.

Value to hospital operations:

- Gives context behind shortages.
- Helps managers understand why one department is higher priority.
- Supports planning across hospital workflows.

Fallback explanation if asked:

> These are demo operational records. In a real SaaS version, these would come from hospital scheduling, ADT, EHR, or bed-management systems.

### Step 9: Notifications / Messages / Approvals / Audit

What to click:

- Open **Notifications**.
- Open **Messages**.
- Open **Approvals**.
- Open **Audit**.

What to show:

- Alerts/notifications.
- Message workflow.
- Approval panel.
- Audit summary/table.

What to say:

> Forecasting and optimization are not enough by themselves. Hospitals also need coordination, approvals, and audit visibility. This demo includes an internal workflow foundation for communicating recommendations and tracking actions.

Value to hospital operations:

- Makes recommendations actionable.
- Adds accountability.
- Supports operational governance.

Fallback explanation if asked:

> This is intentionally internal-only for the demo. It does not include Gmail, OAuth, SMS, or external notification providers yet.

## 6. Key Technical Explanation

### 72-Hour Forecasting

HRO-PS forecasts patient demand over the next 72 hours. The forecast is used by:

- Command Center KPIs,
- Forecast charts,
- Digital Twin horizon view,
- Optimization inputs,
- Evaluation display,
- API artifact status.

### LSTM / ARIMAX / Hybrid

- **LSTM** captures nonlinear temporal patterns in patient flow.
- **ARIMAX** provides statistical time-series forecasting with exogenous variables.
- **Hybrid** combines model outputs when they pass validation.

If a model output is invalid, flat, negative, NaN, stale, or unstable, it should not be blindly trusted.

### ForecastState Consistency

`ForecastState` is the canonical source of truth for:

- current patients,
- next-hour forecast,
- 24h peak,
- 72h peak,
- 72h average,
- selected/best model,
- model status,
- artifact timestamp,
- metrics,
- resource recommendation input.

This prevents different tabs from showing different values for the same concept.

### MAE / RMSE / MAPE

- **MAE**: average absolute error in patient-count units.
- **RMSE**: error in patient-count units, with larger errors penalized more.
- **MAPE**: percentage error, useful sometimes but misleading when actual values are near zero.

Recommended wording:

> We use MAE and RMSE as primary metrics because hospital operators understand errors in patient counts. MAPE is shown carefully as a caution metric.

### ARIMAX / LSTM Fallback Explanation

Recommended wording:

> In this prototype, model outputs are validated before they are used. If LSTM produces invalid values or ARIMAX becomes suspiciously flat, the system uses a labeled time-aware fallback based on historical patterns. This is not hiding the model problem; it makes the limitation visible while keeping the demo operational.

### Why No Real Patient Data Is Used

Recommended wording:

> Real patient data requires privacy, security, compliance, consent, hospital approvals, and integration agreements. For a graduation project, realistic synthetic/demo data is safer and appropriate for demonstrating the system workflow.

### Why Not Production SaaS Yet

Before production use, HRO-PS would need:

- clinical/operations validation,
- real hospital integration,
- security hardening,
- compliance review,
- tenant isolation testing,
- production authentication,
- immutable audit logs,
- monitoring and backups,
- model governance and drift monitoring.

## 7. Jury Q&A

### 1. Is this using real patient data?

No. It uses realistic synthetic/demo operational data. This protects privacy and allows the project to be demonstrated safely without exposing real patient records.

### 2. Is this production-ready?

No. It is a graduation-demo prototype. It demonstrates the workflow and technical feasibility, but real deployment would require hospital integration, compliance, security, monitoring, validation, and governance.

### 3. Why did you use AI for this problem?

Hospital pressure changes over time and depends on patient flow, staffing, appointments, and department load. AI forecasting helps estimate near-future pressure so managers can act earlier.

### 4. What is the main value of the system?

It connects forecasting to operational decisions: predicted demand, department pressure, resource shortages, recommendations, and coordination workflows.

### 5. What is ForecastState?

ForecastState is the canonical runtime object that keeps forecast values consistent across dashboard tabs and API responses. It prevents Command Center, Forecast, Digital Twin, Optimization, and Evaluation from calculating the same metric differently.

### 6. Why do you show MAE and RMSE?

They show forecast error in patient-count units. That is easier for hospital operators to understand than only percentage-based metrics.

### 7. Why can MAPE be misleading?

MAPE divides by actual values. If actual patient counts are low or near zero, the percentage can become very large even when the absolute error is operationally manageable.

### 8. Why was fallback used?

The system detected invalid or low-quality model output. Instead of showing a misleading forecast, it used a labeled time-aware fallback and recorded the reasons in the model status/manifest.

### 9. Does fallback mean the project failed?

No. It means the system has quality control. A reliable decision-support system should detect bad model output and avoid presenting it as trustworthy.

### 10. How does optimization work?

The optimizer uses the forecasted patient load and operational context to estimate beds, doctors, nurses, shortages, and department priority scores. Recommendations are generated from these calculated pressures.

### 11. What does the Digital Twin add?

It lets users explore future hospital pressure across the 72-hour horizon and inspect how demand changes by time and department.

### 12. Can this connect to a real hospital system?

Not yet in this demo version. A SaaS version would need HL7/FHIR/ADT or hospital system integrations, secure ingestion, validation, monitoring, and compliance controls.

### 13. Why not add Gmail, SMS, or OAuth now?

Those are production integration features. For the graduation demo, the system keeps communication internal and stable to avoid unnecessary risk.

### 14. What is the biggest limitation?

The biggest limitation is that the project uses demo data and pre-generated artifacts. Real-world accuracy would require real hospital data, validation, monitoring, and model governance.

### 15. What would you improve next?

The next major step is a pilot-ready SaaS MVP with real hospital data ingestion, stronger authentication, tenant isolation, monitoring, and model lifecycle management.

### 16. Why is the ARIMAX weight only 0.2 in the Hybrid model?

The hybrid weights were chosen by a constrained grid search over LSTM/ARIMAX blending weights from 0.20 to 0.80 in 0.05 steps. The minimum validation RMSE was at LSTM = 0.80 / ARIMAX = 0.20 (hybrid validation RMSE 9.43 vs LSTM-alone 8.42 at validation).

On the held-out test set, LSTM alone achieves RMSE 9.58 and the hybrid achieves RMSE 10.22. LSTM is therefore the most accurate individual model by test RMSE — the manifest correctly records `best_model = LSTM`.

We deploy the 0.80/0.20 hybrid rather than pure LSTM because of **operational robustness**: when LSTM encounters out-of-distribution surge patterns it has not seen during training, its predictions can become volatile. The ARIMAX component (a linear SARIMAX with lag, seasonal, and exogenous regressors) provides a stable linear baseline that anchors the hybrid and prevents extreme forecast swings during unusual events. The slight accuracy trade-off (RMSE 10.22 vs 9.58) is acceptable in a 24/7 hospital context where prediction stability matters as much as average error.

In short: the 0.2 weight is a robustness choice, not a claim that ARIMAX alone is competitive. LSTM dominates because hourly hospital demand has strong non-linear behaviour (surge spikes, shift transitions, emergency events) that ARIMA cannot model well.

### 17. Why keep ARIMAX if LSTM is more accurate?

Because ensemble methods trade a small accuracy loss for stability, and that trade-off is valuable in safety-critical operational contexts. LSTM's strength (non-linear pattern learning) is also its weakness: it can overfit to training patterns and produce unstable forecasts on novel input distributions. The ARIMAX component anchors the hybrid with interpretable linear trend and seasonality, reducing forecast volatility when LSTM predictions become unstable. We would drop ARIMAX entirely only if its weight converged to zero during unconstrained optimisation — the unconstrained optimum is LSTM=0.95/ARIMAX=0.05, confirming ARIMAX still contributes. We constrain the minimum ARIMAX weight to 0.20 as a design floor to guarantee this robustness property.

## 8. Emergency Backup Plan

### If Internet Fails

Prepare screenshots before the discussion:

- Login page.
- Command Center.
- Forecast.
- Digital Twin.
- Optimization.
- Simulation / What-if Scenarios.
- Evaluation.
- Explainability.
- Staff schedule.
- Appointments.
- OR Bookings.
- Notifications / Messages.
- Approvals.
- Audit.

Suggested backup folder:

```text
demo_backup_screenshots/
```

### Local Run Commands

Start API:

```powershell
uvicorn main:app --reload
```

Start dashboard:

```powershell
streamlit run dashboard.py
```

If using separate terminals, start the API first, then the dashboard.

### Smoke Test Commands

ForecastState and cross-tab consistency smoke:

```powershell
python scripts\smoke_forecast_state.py
```

Project tests:

```powershell
python -m pytest -q
```

Optional compile check:

```powershell
python -m compileall dashboard.py dashboard_sections.py staff_sections.py api.py api_client.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py forecast_state.py forecast_inference_ops72h.py generate_ops72h_outputs.py -q
```

## 9. Final Checklist Before Discussion

### API / Backend

- [ ] API starts successfully.
- [ ] `/health` works.
- [ ] `/health/db` works.
- [ ] `/artifacts/manifest` works.
- [ ] `/forecast` or `/forecast_state` works.
- [ ] `/evaluation` works.

### Dashboard

- [ ] Dashboard opens.
- [ ] Login works with `admin1 / 123456`.
- [ ] Tenant is set to `demo-hospital`.
- [ ] Command Center loads.
- [ ] Forecast tab loads.
- [ ] Digital Twin loads.
- [ ] Optimization loads.
- [ ] Simulation / What-if Scenarios loads.
- [ ] Evaluation loads.
- [ ] Explainability loads.
- [ ] Staff / Appointments / OR Bookings load.
- [ ] Notifications / Messages / Approvals / Audit load.

### Artifacts

- [ ] `artifacts/forecast_outputs/ops72h_overall_forecast.csv` exists.
- [ ] `artifacts/forecast_outputs/ops72h_department_forecast.csv` exists.
- [ ] `artifacts/metrics_72h/ops72h_model_metrics.csv` exists.
- [ ] `artifacts/manifests/ops72h_training_summary.json` exists.
- [ ] Smoke test confirms 72 forecast rows.
- [ ] Smoke test confirms dashboard source consistency.

### Presentation

- [ ] Demo credentials ready.
- [ ] Demo script open.
- [ ] Screenshots saved.
- [ ] Internet backup ready.
- [ ] Local run commands ready.
- [ ] Clear explanation prepared for fallback/model limitations.
- [ ] Clear explanation prepared for no real patient data.
- [ ] Clear explanation prepared for not production SaaS yet.

## 10. Closing Statement

Recommended closing:

> HRO-PS demonstrates how AI forecasting can be connected to real operational decision workflows in a hospital setting. The strongest part of the project is not only the forecast chart, but the full loop: forecast, validate, optimize, simulate, explain, communicate, approve, and audit. This is a graduation-demo prototype, and the next step after graduation would be transforming it into a secure, validated SaaS product with real hospital integrations.
