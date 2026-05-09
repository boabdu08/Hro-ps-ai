# HRO-PS Deployment Readiness Guide

This guide is for a **graduation demo deployment** of HRO-PS. The project is demo-ready, but it is **not production hospital SaaS yet**. Do not deploy with real patient data until security, compliance, tenant isolation, real hospital integration, and clinical/operations validation are completed.

## Deployment status and constraints

- Use **Python 3.11** (`runtime.txt`).
- Streamlit entry point: `dashboard.py`.
- FastAPI entry point: `main:app`.
- Do **not** train models on startup.
- Do **not** regenerate demo data on startup unless intentionally running a seed/demo script.
- Do **not** implement Gmail/OAuth as part of the graduation deployment freeze.
- Demo data is realistic/synthetic. **No real patient data is used.**
- Free-tier services may sleep and may use ephemeral storage.

## Required artifacts

The deployment must include the saved artifacts used by dashboard/API runtime paths.

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

If any required artifact is missing, the related tab/API route may show a missing-artifact state or fail inference.

## Environment variables

Required/recommended variables:

- `APP_ENV=prod` for cloud deployment.
- `DATABASE_URL` = Postgres connection string, usually with `sslmode=require` for Neon/Supabase.
- `JWT_SECRET_KEY` = strong secret; never use the demo value in public deployment.
- `JWT_ALGORITHM=HS256`.
- `API_BASE_URL` = public FastAPI URL used by the dashboard.
- `CORS_ORIGINS` = comma-separated dashboard origins allowed by the API.
- `DEFAULT_TENANT_SLUG=demo-hospital` for the graduation demo tenant.
- `TENANT_MODE_ENABLED=true`.
- `ARTIFACT_DIR=.` unless artifacts are mounted elsewhere.

Worker-specific variables if running the worker:

- `SCHEDULER_INTERVAL_SECONDS=300`
- `SYNTHETIC_DATA_ENABLED=true` for demo mode only
- `SYNTHETIC_EMERGENCY_RATE=0.03`

## Requirement files

- Full local/demo install: `requirements.txt`
- API deployment install: `requirements-api.txt`
- Dashboard deployment install: `requirements-dashboard.txt`

Before deployment, verify the target platform installs the intended file and can import the target entry point.

## Recommended full architecture

- **API:** Render or Railway web service running `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Worker:** Render/Railway worker running `python worker.py`
- **DB:** Neon/Supabase/Postgres
- **Dashboard:** Streamlit Cloud or Render running `streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`

This repo includes `render.yaml` with API, dashboard, and worker services.

## Streamlit Cloud deployment

1. Connect the GitHub repo.
2. Set app file to `dashboard.py`.
3. Configure secrets/environment variables:
   - `API_BASE_URL`
   - `DEFAULT_TENANT_SLUG`
   - `TENANT_MODE_ENABLED`
   - DB variables if using dashboard sections that read the DB directly.
4. Confirm artifacts required by Forecast/Digital Twin/Evaluation exist in the deployed app filesystem.

## Hugging Face Spaces notes

Hugging Face Spaces can work as a **simple Streamlit showcase**, but it is not ideal for the full API + worker + DB architecture.

If using Hugging Face:

- Use `dashboard.py` as the Streamlit entry point.
- Ensure the Space installs dashboard dependencies.
- Set `API_BASE_URL` as a Space secret/variable if the dashboard calls an external API.
- Include required forecast/evaluation artifacts in the repo or mounted storage.
- Do not train on Space startup.
- Be aware that free Spaces can sleep and local storage can be ephemeral.

If the Hugging Face deployment becomes unstable, prefer Streamlit Cloud/Render for the dashboard and Render/Railway for the API/worker.

## Verification checklist

After deployment, verify:

1. API health:
   - `GET /health`
   - `GET /health/db`
2. Login:
   - `POST /auth/login`
3. Dashboard pages:
   - Command Center
   - Forecast
   - Digital Twin
   - Evaluation
   - Simulation / What-if Scenarios
   - Optimization
   - Staff Scheduling
   - Appointments
   - OR Bookings
   - Notifications / Messages / Audit
4. Confirm no model training starts during API/dashboard startup.
5. Confirm artifacts are readable in the deployed environment.
6. Confirm worker writes data only if intentionally enabled.

## Production SaaS warning

Before real SaaS launch, complete:

- tenant isolation tests,
- production migrations,
- secure account lifecycle and SSO,
- real hospital integrations,
- compliance/security review,
- audit/retention policies,
- monitoring/observability,
- backups and rollback,
- model drift/retraining governance,
- validated optimization constraints.
