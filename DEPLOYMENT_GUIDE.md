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

These root-level files are **separate** from the 72-hour forecast dashboard artifacts above. They serve different runtime paths:

| Artifact set | Used by | Purpose |
|---|---|---|
| `artifacts/models_72h/` + `artifacts/forecast_outputs/` | Dashboard (ForecastState), `/health/full` | Pre-computed 72h forecast shown in all dashboard tabs |
| Root `hospital_forecast_model.keras`, `arimax_model.pkl`, etc. | `forecast_inference.py` → `/predict`, `/explain` API endpoints | Live per-request model inference |

If the root artifacts are missing, the `/predict` and `/explain` endpoints will fail to load and return 500 errors. The dashboard will still work from the pre-computed 72h CSV artifacts. If the 72h artifacts are missing, the dashboard tabs will show a missing-artifact error and `/health/full` will report `"artifacts":"missing"`.

Both sets must be present for full functionality.

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

- **DB:** Neon (recommended) or Supabase / Render Postgres
- **API:** Render web service — `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Dashboard:** Streamlit Cloud or Render web service — `streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
- **Worker:** Render worker — `python worker.py` — deploy **after** the API is healthy

This repo includes `render.yaml` with API, dashboard, and worker services configured.

### Deployment order (important)

Deploy in this order to avoid startup failures:

1. **Provision the Neon database** and copy the connection string.
2. **Deploy the API** (`hro-ps-api`). Set `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS`.
3. **Seed the database**: after the API is up, run `python seed_from_csv.py` once (or `SEED_FORCE=true python seed_from_csv.py` if re-seeding). The API lifespan also seeds 7 baseline demo users on startup automatically.
4. **Deploy the dashboard** (`hro-ps-dashboard`). Set `API_BASE_URL` to the Render API public URL.
5. **Deploy the worker** (`hro-ps-worker`) last — it depends on the API and DB being ready.

> Do **not** deploy the worker before the API. The worker requires the DB schema and API stack to exist first.

### Required env vars

**API service** (`hro-ps-api`):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon connection string with `?sslmode=require` |
| `JWT_SECRET_KEY` | Strong random secret (never the demo value) |
| `JWT_ALGORITHM` | `HS256` |
| `CORS_ORIGINS` | Dashboard URL(s), comma-separated |
| `DEFAULT_TENANT_SLUG` | `demo-hospital` |
| `ARTIFACT_DIR` | `.` (artifacts in repo root) |
| `APP_ENV` | `prod` |

**Dashboard service** (`hro-ps-dashboard`):

| Variable | Value |
|---|---|
| `API_BASE_URL` | Public Render API URL |
| `DATABASE_URL` | Same Neon connection string |
| `DEFAULT_TENANT_SLUG` | `demo-hospital` |
| `ARTIFACT_DIR` | `.` |
| `APP_ENV` | `prod` |

### Artifact deployment note

The `.gitignore` now has explicit exception rules so that required deployment artifacts are committed to git:

```
!artifacts/models_72h/*.keras
!artifacts/models_72h/*.pkl
!artifacts/forecast_outputs/*.csv
!artifacts/metrics_72h/*.csv
!artifacts/metrics_72h/*.json
!artifacts/manifests/*.json
```

Without these exceptions, Render deployments will fail `/health/full` checks because model files will not be present on the cloud filesystem. Verify that `git status` does not show the artifact files as untracked before pushing.

### ARIMAX large file warning

`artifacts/models_72h/arimax_ops72h.pkl` is **53.5 MB**. GitHub's soft warning threshold is 50 MB; the hard push limit is 100 MB. This file is below the hard limit and can be committed and pushed without Git LFS. However:

- GitHub will display a warning when you push: *"File exceeds recommended size (53.5 MB)."* This is cosmetic and does not block the push.
- The root-level `arimax_model.pkl` is 27.6 MB and is below both thresholds — no warning expected.
- Do **not** use `git lfs track *.pkl` unless you have confirmed Git LFS is installed on Render. Render's free tier does not support Git LFS by default, and tracking with LFS without Render LFS support will cause the pkl file to be replaced by a pointer file at deploy time, which will break the API.
- If the 53.5 MB warning blocks your push (it should not), use `git push --no-verify` is **not recommended**; instead, verify you are pushing to a repo where this file was already committed and the remote already has it.

**Recommended action:** Push as-is. Accept the GitHub size warning. Both pkl files are required for full `/predict` and `/explain` functionality and are already committed.

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
   - `GET /health` → `{"status":"ok"}`
   - `GET /health/db` → `{"status":"ok"}`
   - `GET /health/full` → `{"api":"ok","database":"ok","artifacts":"ok","forecast_ready":true}` — this is the canonical deployment gate; if any value is not `ok`/`true`, the deployment is not ready for demo
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
