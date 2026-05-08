# HRO-PS TODO — Documentation + Deployment Readiness Freeze

Feature development is frozen for the graduation demo. Do **not** add Gmail/OAuth, retrain models, regenerate data, change model artifacts, or refactor architecture before the demo unless a blocking deployment bug is found.

## Completed demo milestones

- [x] Operational data export pipeline completed.
- [x] Realistic operational demo data generated.
- [x] 72-hour forecast artifacts generated.
- [x] LSTM / ARIMAX / Hybrid outputs available.
- [x] Evaluation tab reads real `metrics_72h` artifacts.
- [x] Forecast tab reads real 72-hour forecast artifacts.
- [x] Digital Twin reads real 72-hour forecast artifacts.
- [x] What-if scenarios are CSV-driven and dynamic.
- [x] Simulation scenario table uses expanded what-if scenarios.
- [x] Staff scheduling, appointments, and OR booking demo views are available.
- [x] Dashboard correction/polish phase completed.
- [x] FastAPI warnings reviewed as deprecation warnings, not breaking errors.
- [x] `py_compile`, `compileall`, `pytest`, and dashboard smoke-test checklist completed previously.

## Before deployment demo

- [ ] Verify deployment install commands for API and dashboard requirement files.
- [ ] Confirm required forecast/evaluation/model artifacts are present in deployment.
- [ ] Confirm Streamlit starts from `dashboard.py` without training or data regeneration.
- [ ] Confirm FastAPI starts from `main:app` with production env vars.
- [ ] Set real deployment secrets (`JWT_SECRET_KEY`, `DATABASE_URL`, `API_BASE_URL`, `CORS_ORIGINS`).
- [ ] Run deployed smoke test: login, Command Center, Forecast, Evaluation, Digital Twin, Simulation, Staff, Appointments, OR, Notifications/Messages/Audit.
- [ ] Prepare a scripted graduation demo path.

## Nice-to-have before graduation if time remains

- [ ] Add screenshots or GIFs to README.
- [ ] Add a concise model-card slide/document.
- [ ] Add a visible “Demo Mode / No real patient data” UI note if safe.
- [ ] Add a short guided demo checklist for presenters.
- [ ] Move overly technical artifact/path wording into expanders where practical.

## Post-graduation SaaS roadmap

- [ ] Production multi-tenant isolation tests across all endpoints.
- [ ] Real authentication lifecycle, staff account management, and hospital SSO/OIDC/SAML.
- [ ] Alembic/versioned database migrations.
- [ ] Real hospital integration: EHR/ADT/FHIR/HL7, bed board, OR/scheduling systems.
- [ ] Real-time ingestion pipeline with retries, dedupe, idempotency, and monitoring.
- [ ] Formal optimization objective/constraints validated with hospital KPIs.
- [ ] Model monitoring, drift detection, retraining governance, and rollback.
- [ ] Immutable audit logs, compliance policies, backups, and observability.
- [ ] External email/SMS/push notifications with provider abstraction and escalation rules.
- [ ] Billing/subscriptions, tenant admin controls, and plan-based feature flags.
