# HRO‑PS — MASTER ROADMAP (Current → Production SaaS → Live Deployment → Real Validation → Launch)

> Guiding principle: **forecasting + optimization are the core product loop**. Everything else (alerts, workflows, SaaS, UI, deployment) exists to make that loop reliable, explainable, and operational.

---

## 🟥 PHASE 0 — CURRENT STATE (Based on audit)

### Objective
Establish an honest baseline and lock the execution order.

### Current completion (rough)
**~55–65%** (prototype is functional; production hardening and SaaS readiness are partially implemented).

### What is already fixed / implemented (strengths)
- **Hybrid forecasting runtime exists** (LSTM + ARIMAX artifacts + inference).
- **Optimization engine exists** (resource optimizer; persists optimization runs).
- **DB-first direction is underway** (tables exist; most features read/write DB).
- **Messaging + notifications + alerts** implemented (v1) and integrated with dashboard.
- **Centralized settings** + `.env.example` added.
- **Tenant foundations**: tenant model + default tenant bootstrap + JWT includes `tenant_id`.

### Key weaknesses
- **Forecast integrity is not fully validated** (feature engineering drift risk, evaluation mismatch risk).
- **Optimization objective/constraints are not formally validated against real KPIs**.
- **Schema/migrations** are still “lightweight helpers” (no Alembic versioning).
- **Background pipeline** not yet production-grade (needs worker separation, observability, idempotency, dedupe).
- **Deployment is not locked** (env vars, secrets, health checks, scaling, costs).

### Critical risks
1) **Forecast drift** (training feature set ≠ runtime feature set).
2) **Optimization produces non-actionable plans** (wrong constraints, unrealistic outputs).
3) **Multi-instance scheduler duplication** if not separated into a single worker.
4) **Operational reliability**: missing monitoring, retry policies, and safe fallbacks.

### Expected output
- A single source of truth roadmap (this document) + a locked critical path.

### Definition of Done
- Roadmap approved and translated into tickets.

---

## 🟧 PHASE 1 — CORE SYSTEM FIXES (Forecast + Optimization + Data Integrity)

### Objective
Make forecasting + optimization **correct, reproducible, and defensible**.

### Key tasks
1) **Forecast integrity fixes**
   - Verify runtime uses *exact* same feature pipeline as training (no hidden transforms).
   - Freeze `FEATURE_COLUMNS` and `feature_engineering_metadata.json` as canonical.
2) **Canonical feature engineering**
   - One canonical function: `raw_rows -> engineered_sequence` used everywhere.
3) **Evaluation alignment**
   - Ensure evaluation scripts use the same inference code.
   - Produce baseline report (MAPE/RMSE/MAE + drift checks).
4) **Optimization upgrade**
   - Formalize objectives: minimize shortages, overtime, cost; maximize SLA.
   - Add constraints: min staffing per dept, max shift changes, bed limits.
5) **Forecast → Optimization linkage**
   - Define exact interface: forecast output → optimizer input (units + horizon).
6) **Remove legacy code paths**
   - Deprecate old feature pipelines / duplicate models.

### Dependencies
- Stable artifacts and correct feature spec.

### Risks
- Hidden feature drift causing silent prediction errors.

### Expected output
- “Forecast + Optimization” loop produces consistent results across API, scripts, dashboard.

### Definition of Done
- Reproducible evaluation report (same inputs → same outputs).
- Optimization outputs pass a scenario test suite.

**Time estimate:** 1–2 weeks.

---

## 🟨 PHASE 2 — SYSTEM ARCHITECTURE CLEANUP

### Objective
Reduce complexity: one runtime path, one data flow.

### Key tasks
- Remove duplicated pipelines and consolidate modules.
- Create `services/` layer (forecast_service, optimization_service, alert_service).
- Standardize return payloads (schemas).
- Add integration tests for API endpoints.

### Dependencies
- Phase 1 canonical pipelines.

### Risks
- Breaking dashboard if endpoints change without compatibility wrappers.

### Expected output
- Clean module boundaries; fewer “script-only” code paths.

### Definition of Done
- API + dashboard run through the same services; unit tests cover core services.

**Time estimate:** 1 week.

---

## 🟩 PHASE 3 — DB-FIRST + API HARDENING

### Objective
DB becomes the source of truth; API becomes safe + predictable.

### Key tasks
- Remove CSV runtime usage completely (CSV only for seeding).
- Improve schema:
  - proper types, indexes, constraints
  - add `forecast_runs`, `kpi_snapshots`
- Add real migrations (Alembic) + version control
- Security hardening:
  - JWT rotation policy
  - password hashing enforcement
  - rate limiting (basic)
- Validation + error handling standards.

### Dependencies
- Phase 1/2 stabilization.

### Risks
- Schema changes without migrations can break prod.

### Expected output
- Strong DB schema + hardened API.

### Definition of Done
- Alembic migrations in place; zero runtime dependency on CSV.

**Time estimate:** 1–2 weeks.

---

## 🟦 PHASE 4 — COMMUNICATION + ALERTS + WORKFLOWS

### Objective
Turn predictions into actions via human workflows.

### Key tasks
- Message system v2 (templates, threading, read/ack per user).
- Smart alerts rules engine:
  - forecast surge
  - bed shortages
  - staffing shortage
- Notification preferences + escalation.
- Role-based workflows:
  - Admin: approve changes
  - Staff: acknowledge + execute
- Audit trail: every decision traceable.

### Dependencies
- Phase 3 hardened data + API.

### Risks
- Alert fatigue; wrong thresholds.

### Expected output
- Reliable operational communication loop.

### Definition of Done
- End-to-end scenario: forecast surge → optimized plan → approvals → staff acknowledgment → audit record.

**Time estimate:** 1–2 weeks.

---

## 🟪 PHASE 5 — FULL SYSTEM INTEGRATION

### Objective
One integrated product loop with KPIs.

### Key tasks
- Forecast → Optimization → Alerts → Approvals → Execution tracking.
- KPI linkage: bed occupancy proxy, waiting time proxy, staffing utilization.
- Unified domain model + consistent naming.
- Dashboard integration with “live mode”.

### Dependencies
- Phase 4 workflows.

### Risks
- KPI definitions not aligned with hospital realities.

### Expected output
- Demonstrable, measurable operational improvement loop.

### Definition of Done
- KPI dashboard shows improvements in simulated scenarios.

**Time estimate:** 1 week.

---

## 🟫 PHASE 6 — MULTI‑TENANT SAAS

### Objective
Sellable SaaS foundation.

### Key tasks
- Tenant isolation enforcement on every endpoint.
- Tenant onboarding:
  - create tenant
  - create admin user
  - seed tenant demo data
- Tenant-specific configs (thresholds, departments, branding).
- Billing/plan placeholders (no full payments yet).

### Dependencies
- Stable schema + migrations.

### Risks
- Data leakage if any query misses tenant filter.

### Expected output
- Two tenants can run in one DB safely.

### Definition of Done
- Automated test proves tenant isolation across major endpoints.

**Time estimate:** 1–2 weeks.

---

## ⚫ PHASE 7 — DEPLOYMENT & 24/7 OPERATION

### Objective
Always-on cloud system.

### Key tasks
- Deploy API to Render/Railway.
- Deploy worker to run scheduler 24/7.
- Deploy Streamlit dashboard to Streamlit Cloud.
- Cloud Postgres on Neon/Supabase.
- Add health checks + structured logging.
- Backups + rollback strategy.

### Dependencies
- Phase 3 (hardening) + Phase 6 (tenant isolation for SaaS).

### Risks
- Free tiers sleep; needs paid plan for true 24/7.

### Expected output
- Public URLs (API + Dashboard) + persistent database.

### Definition of Done
- System runs for 72 hours without manual intervention.

**Time estimate:** 2–4 days.

---

## ⚪ PHASE 8 — DEMO / TEST ENVIRONMENT

### Objective
Reliable demo for stakeholders.

### Key tasks
- Seed data + scenario scripts.
- Test accounts per role.
- Demo playbook (what to click + what to explain).
- Automated API checks (smoke tests).

### Dependencies
- Phase 7 live deployment.

### Risks
- Demo data not realistic → credibility loss.

### Definition of Done
- One-click demo scenario produces clear outputs.

**Time estimate:** 3–5 days.

---

## 🟤 PHASE 9 — FINAL VALIDATION

### Objective
Prove the system works end-to-end.

### Key tasks
- Forecast validation (backtesting + drift checks).
- Optimization validation (scenario suite + constraints).
- End-to-end workflow validation.
- KPI evaluation report.

### Dependencies
- Phase 8 stable demo.

### Definition of Done
- Signed validation report + tracked known limitations.

**Time estimate:** 1–2 weeks.

---

## 🔴 PHASE 10 — PRODUCT LAUNCH READINESS

### Objective
Launch a sellable product.

### Key tasks
- Performance + reliability hardening.
- On-call playbook, runbooks.
- Documentation: admin manual + API docs.
- Packaging: pricing page, pitch deck, case study.

### Dependencies
- Phase 9 validation.

### Definition of Done
- Launch checklist passes; demo stable; onboarding ready.

**Time estimate:** 1 week.

---

## Priority order (must do first)
1) Phase 1 (forecast + optimizer correctness) — **core value**
2) Phase 3 (DB + API hardening) — **reliability**
3) Phase 7 (deployment + scheduler worker) — **always-on**
4) Phase 4/5 (workflows + integration) — **operationalization**
5) Phase 6 (SaaS multi-tenant) — **sellability**

---

## Execution strategy (sequential vs parallel)
- **Sequential (critical path):** Phase 1 → Phase 3 → Phase 7 → Phase 9
- **Parallelizable:**
  - UI improvements (Phase 5) can progress while Phase 3 hardens API.
  - Multi-tenant UX (Phase 6) can start after tenant isolation tests exist.

---

## Rough timeline
Total: **6–10 weeks** depending on depth of validation.

---

## Critical path (blockers)
1) Canonical feature engineering & evaluation alignment (Phase 1)
2) DB migrations + schema hardening (Phase 3)
3) Always-on worker + stable deployment (Phase 7)

---

## Quick wins (high impact / low effort)
- Add smoke tests (login, status, latest sequence, optimize).
- Add pipeline status endpoint + dashboard widget.
- Add better error messages and “data not ready” handling.
