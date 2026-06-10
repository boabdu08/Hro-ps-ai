---
title: HRO-PS Hospital Resource Optimization
emoji: 🏥
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: "1.54.0"
app_file: app.py
pinned: false
license: mit
---

# HRO-PS — Hospital Resource Optimization & Patient-Flow Forecasting

> Use this file as the Space's `README.md` when creating the Hugging Face Space
> (the YAML header above is the Space card configuration).

AI-assisted hospital operations dashboard: 72-hour patient-demand forecasting
(Hybrid LSTM + ARIMAX), MILP resource optimization across 5 departments, and a
human-in-the-loop approvals workflow.

## What runs in this Space

| Component | Detail |
|---|---|
| Dashboard | Streamlit, 13 tabs, 3 role-based views (entry: `app.py` → `dashboard.py`) |
| API | FastAPI (48 endpoints) started in-process on an internal port |
| Models | **Pre-generated artifacts** — no training on startup |
| Forecast | 72-h horizon, Hybrid LSTM 0.80 / ARIMAX 0.20 |
| Optimizer | `scipy.optimize.milp` with deterministic greedy fallback |

## Required Space secrets (Settings → Variables and secrets)

| Name | Required | Example / note |
|---|---|---|
| `JWT_SECRET_KEY` | yes | long random string — never hard-coded |
| `DATABASE_URL` | no | defaults to `sqlite:///./hf_demo.db` for the demo; set a Postgres URL for persistence |
| `APP_ENV` | no | `dev` (default) seeds demo users on startup |

Demo login: `admin1` / `123456` (tenant `demo-hospital`, auto-seeded).

## Honest-data disclosure

All data is **synthetic** (17,520 hourly rows, 2024–2025, 5 departments).
No real patient data is used. Model metrics shown in the app are computed on a
held-out test split: LSTM MAE 7.65 / RMSE 9.58 / MAPE 5.52% (best individual
model); deployed Hybrid 8.31 / 10.22 / 6.07% (chosen for operational
robustness, not raw accuracy).
