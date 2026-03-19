# HRO‑PS Cloud Deployment Guide (24/7)

## Target architecture
- **API**: Render or Railway (FastAPI + Uvicorn)
- **Worker**: Render Worker / Railway service running `python worker.py`
- **DB**: Neon (Postgres)
- **Dashboard**: Streamlit Cloud

> Note: true 24/7 requires **non-sleeping** plans. Free tiers may sleep.

---

## 1) Create Neon Postgres
1. Create a Neon project + database.
2. Copy connection string.
3. Ensure `sslmode=require` is present.

Example:
```
postgresql+psycopg2://USER:PASSWORD@HOST/DB?sslmode=require
```

---

## 2) Deploy API + Worker on Render
This repo includes `render.yaml` with two services:
- `hro-ps-api` (web)
- `hro-ps-worker` (background scheduler)

### Required env vars (both services)
- `DATABASE_URL` = Neon connection string
- `JWT_SECRET_KEY` = strong secret

### Worker-specific env vars
- `SCHEDULER_INTERVAL_SECONDS` (e.g. `300`)
- `SYNTHETIC_DATA_ENABLED=true`
- `SYNTHETIC_EMERGENCY_RATE=0.03`

---

## 3) Deploy Dashboard on Streamlit Cloud
1. Connect the GitHub repo.
2. Set the app file to `dashboard.py`.

### Streamlit env vars
- `API_BASE_URL` = your Render API URL (e.g. `https://hro-ps-api.onrender.com`)
- (Optional) `DEFAULT_TENANT_SLUG=demo-hospital`

---

## 4) Verify production
1. API health:
   - `GET /health`
   - `GET /health/db`
2. Login:
   - `POST /auth/login`
3. Confirm worker is writing data:
   - patient flow grows in DB
   - optimization_runs grows
   - alerts/notifications appear

---

## Expected public URLs
- API: `https://<your-api>.onrender.com`
- Dashboard: `https://<your-app>.streamlit.app`
