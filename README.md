# HRO-PS AI Hospital Resource Optimization and Patient Surge Forecasting System

HRO-PS is an **AI-powered hospital resource optimization prototype** built for a graduation demo. It combines patient-surge forecasting, operational dashboards, resource optimization, what-if simulation, and in-app communication foundations.

> **Project status:** graduation-demo ready prototype.  
> **Not production hospital SaaS yet:** the system still needs real hospital integration, clinical/operations validation, security/compliance hardening, production migrations, observability, and tenant-isolation testing before real-world use.

## Demo data and privacy

- This project uses **realistic demo/synthetic operational data** for hospital operations scenarios.
- **No real patient data is used.**
- Demo data exists to show the product workflow safely without exposing protected health information.
- Forecast/model artifacts are pre-generated for the demo; the app should **not train models on startup**.

## Main features

- **72-hour patient surge forecasting** using saved forecast artifacts.
- **LSTM / ARIMAX / Hybrid model outputs** for model comparison and operational recommendation.
- **Evaluation tab** reading real `artifacts/metrics_72h` metrics, with MAE/RMSE emphasized and MAPE treated as a caution metric.
- **Forecast tab** reading saved 72-hour overall and department forecast outputs.
- **Digital Twin** view using saved forecast artifacts to explore the next 72 hours.
- **Resource Optimization** for beds, doctors, nurses, shortages, department pressure, and recommended actions.
- **CSV-driven What-if Scenarios** for dynamic patient surge and resource pressure simulation.
- **Staff Scheduling** views for realistic staff coverage.
- **Appointments** and **OR Bookings** operational views.
- **Department Status** based on optimizer outputs and live operational context.
- **Explainability / Model Feature Sensitivity** for readable model-input interpretation.
- **In-app alerts/messages foundation** for operational coordination, acknowledgments, and audit visibility.

## System architecture

```
Synthetic / Demo Hospital Data (17,520 hourly rows, 2024–2025)
        │
        ▼
Feature Engineering (61 operational + temporal columns)
        │
        ├──► LSTM (weight 0.80)  ← Best model by test RMSE (9.579)
        │       Captures non-linear surge spikes, shift transitions, emergency events
        │
        └──► ARIMAX (weight 0.20)
                Captures linear trend and 24-hour periodicity via lag_24 + hour features
                (0 convergence warnings after 2026-05-18 improvement; 7-variable exog set)
        │
        ▼
Constrained Hybrid Blend  (LSTM 0.80 / ARIMAX 0.20 — retrain 2026-05-18)
  MAE 8.3 | RMSE 10.2 | MAPE 6.1%   ← comparison model; LSTM alone: RMSE 9.579
  Unconstrained weight search finds LSTM=0.95/ARIMAX=0.05 ("LSTM-only"),
  confirming LSTM dominance; constrained blend keeps both models represented.
        │
        ▼
ForecastState  ← canonical, frozen source of truth
        │         All tabs and all API endpoints read from the same object.
        │         This makes it architecturally impossible for Command Center,
        │         Forecast, Digital Twin, Optimization, and Evaluation to
        │         show different values for the same metric.
        │         selected_model = LSTM  (lowest test RMSE in this training run)
        │
        ├──► FastAPI (46 endpoints)
        │       /forecast_state  /optimize  /explain  /health/full
        │       PostgreSQL (21 tenant-scoped tables, bcrypt + JWT auth)
        │
        └──► Streamlit Dashboard (13 tabs, 3 role views)
                Command Center → Forecast → Digital Twin
                Optimization (scipy MILP) → What-if Simulation → Evaluation
                Explainability → Shifts → Appointments → OR Bookings
                Notifications → Messages → Approvals → Audit
```

The key architectural invariant is that **ForecastState is the single canonical source of truth**. All 13 dashboard tabs and all forecast/evaluation/optimization API responses derive their values from the same ForecastState instance. Cross-tab consistency is verified by a dedicated smoke test on every run.

## Technology stack

- **Python 3.11** deployment runtime (`runtime.txt`).
- **Streamlit** dashboard (`dashboard.py`).
- **FastAPI** backend (`main:app`, implemented in `api.py`).
- **SQLAlchemy + PostgreSQL** for DB-backed runtime data.
- **Pandas / NumPy / Plotly** for data processing and visualization.
- **scikit-learn / statsmodels / TensorFlow / joblib** for ML artifacts and model inference/training scripts.

## Required artifacts for the demo

The dashboard and API expect saved artifacts to exist before startup. Do **not** retrain during deployment startup.

### 72-hour forecast dashboard artifacts

- `artifacts/forecast_outputs/ops72h_overall_forecast.csv`
- `artifacts/forecast_outputs/ops72h_department_forecast.csv`
- `artifacts/metrics_72h/ops72h_model_metrics.csv`
- `artifacts/manifests/ops72h_training_summary.json`

### 72-hour evaluation artifacts

- `artifacts/metrics_72h/lstm_ops72h_metrics.json`
- `artifacts/metrics_72h/arimax_ops72h_metrics.json`
- `artifacts/metrics_72h/hybrid_ops72h_metrics.json`

### Legacy/runtime inference artifacts used by existing API paths

- `hospital_forecast_model.keras`
- `arimax_model.pkl`
- `x_scaler.pkl`
- `y_scaler.pkl`
- `hybrid_config.json`

## Local run instructions

### 1) Clone the repository

```bash
git clone https://github.com/boabdu08/Hro-ps-ai.git
cd hro-ps-ai
```

### 2) Use Python 3.11

The deployment runtime is Python 3.11. Local Python 3.13 may work for some flows, but Python 3.11 is the safest version for dependency compatibility.

### 3) Configure environment

Copy `.env.example` to `.env` and set values as needed:

```bash
cp .env.example .env
```

Important variables:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `API_BASE_URL`
- `CORS_ORIGINS`
- `DEFAULT_TENANT_SLUG`
- `ARTIFACT_DIR`

### 4) Recommended local run commands on Windows

```powershell
./scripts/seed.ps1
./scripts/run_api.ps1
./scripts/run_dashboard.ps1

# optional always-on pipeline / demo worker
./scripts/run_worker.ps1
```

If PowerShell blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -Command "& ./scripts/run_dashboard.ps1"
```

### 5) Manual commands

API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Dashboard:

```bash
streamlit run dashboard.py
```

## Run validation checks

Compile selected runtime files:

```bash
python -m compileall dashboard.py dashboard_sections.py staff_sections.py api.py api_client.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py -q
```

Run tests:

```bash
python -m pytest -q
```

## Deployment notes

- Streamlit entry point: `dashboard.py`.
- FastAPI entry point: `main:app`.
- Use Python 3.11.
- Use real deployment secrets; do not use the demo JWT secret in production.
- Ensure all required artifacts are included in the deployed filesystem or mounted storage.
- Do not run training scripts during dashboard/API startup.
- Free-tier deployments may sleep and may have ephemeral storage.
- Hugging Face Spaces can be used for a simple Streamlit showcase, but the full system is better suited to API + worker + DB deployment on Render/Railway/Neon/Streamlit Cloud.

See `DEPLOYMENT_GUIDE.md` for detailed deployment-readiness notes.

## Graduation demo positioning

Recommended positioning:

> HRO-PS is a functional AI-powered hospital operations decision-support prototype using realistic demo data. It demonstrates forecasting, evaluation, optimization, simulation, and communication workflows, but it is not yet clinically validated production software.

## Future SaaS roadmap

Post-graduation SaaS work includes:

- production-grade multi-tenant isolation,
- real authentication/account lifecycle and hospital SSO,
- staff accounts and permissions,
- real hospital integration via EHR/ADT/FHIR/HL7 and scheduling systems,
- real-time ingestion with retries, deduplication, and monitoring,
- Alembic/versioned database migrations,
- immutable audit logs and compliance controls,
- security hardening and secrets rotation,
- observability, backups, rollback, and uptime monitoring,
- model drift monitoring and retraining governance,
- formal optimization constraints and KPI validation,
- billing/subscription and admin controls.
