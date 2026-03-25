# Backend/Application Foundation Audit

## Scope reviewed
- `api.py`
- `database.py`
- `models.py`
- `schemas.py`
- `auth.py`
- `settings.py`
- `db_migrations.py`
- `worker.py`
- `scheduler.py`
- `etl_pipeline.py`
- `create_tables.py`
- `test_db.py`
- `docker-compose.yml`
- `Dockerfile`
- `render.yaml`
- `DEPLOYMENT_GUIDE.md`
- `MASTER_ROADMAP.md`

## Current architecture
- The backend is a single FastAPI application in `api.py`.
- Persistence is handled with SQLAlchemy in `database.py` and ORM entities in `models.py`.
- Authentication is JWT-based in `auth.py`, with role checks implemented inside `api.py`.
- Background processing exists via `scheduler.py`, with `worker.py` as a separate entrypoint to run the scheduler loop.
- ETL ingestion is synchronous and CSV-based in `etl_pipeline.py`.
- Deployment targets are documented as Render + Postgres + optional worker, with local Docker support in `docker-compose.yml`.

## Module / boundary inventory
- `api.py`: HTTP boundary, auth enforcement, orchestration, DB reads/writes, startup initialization, health/status, messages, alerts, notifications, patient flow, prediction, simulation, explanation, evaluation, optimization, upload.
- `database.py`: engine/session/base creation, request DB dependency, `create_all()` bootstrap.
- `models.py`: tenant, user, patient flow, appointments, OR bookings, staff shifts, messages, per-user message state, recommendations, audit events, optimization runs, alerts, notification preferences, notifications, pipeline runs.
- `schemas.py`: very small request/response schema layer; only login/user models in reviewed scope.
- `auth.py`: password hashing/verification and JWT encode/decode helpers.
- `db_migrations.py`: startup-time idempotent SQL patches for message, tenant, alerts/notifications, and pipeline tables.
- `scheduler.py`: recurring pipeline that generates synthetic rows, forecasts, optimizes, raises alerts, and records `PipelineRun`.
- `worker.py`: production worker wrapper over `scheduler_loop()`.
- `etl_pipeline.py`: CSV ingestion directly into DB.
- Infra files define container/runtime startup, but deployment docs and manifests are not fully aligned with actual API behavior.

## Data flow observed
1. API startup in `api.py` calls `init_db()` then startup migration helpers from `db_migrations.py`.
2. Auth flow:
   - `POST /auth/login` checks `users` table and returns JWT.
   - Protected routes decode bearer token and enforce role lists in `api.py`.
3. Forecast/optimization flow:
   - `GET /patient_flow/latest` pulls last `SEQUENCE_LENGTH` rows from `patients_flow`.
   - `POST /predict` accepts explicit sequence payload.
   - `GET /optimize_resources/{predicted_patients}` runs optimizer and persists `OptimizationRun`.
4. Alert/notification flow:
   - optimizer endpoint or scheduler creates `Alert` rows and `Notification` rows.
   - users query notifications and mark them read.
5. Background pipeline:
   - `worker.py` runs `scheduler_loop()`.
   - `scheduler.py` optionally generates synthetic data, forecasts next hour, runs optimization, creates alerts, writes `PipelineRun`.
6. Upload flow:
   - upload endpoints pass file handles to `etl_pipeline.py`, which parses CSV and inserts rows.

## Config / env handling
- Central settings are in `settings.py` with a minimal `.env` loader.
- `database.py` reads from `get_settings().database_url`, then `os.getenv("DATABASE_URL")`, else falls back to a hardcoded local Postgres DSN.
- `auth.py` reads JWT config from settings/env, but also falls back to `dev-unsafe-secret-change-me`.
- Scheduler behavior is environment-driven: `SCHEDULER_RUN_IN_API`, `SCHEDULER_INTERVAL_SECONDS`, `SYNTHETIC_DATA_ENABLED`, `SYNTHETIC_EMERGENCY_RATE`.
- Deployment manifests supply some of these values, but not consistently across files.

## Auth and access control
- JWT bearer auth is implemented in `auth.py` and consumed in `api.py`.
- Roles are enforced by simple role-name checks in `require_role(...)`.
- Tenant context is derived from JWT `tenant_id`, else default tenant fallback in `api.py`.
- Password verification supports both bcrypt hashes and plaintext fallback:
  - `auth.py -> verify_password()` returns `plain_password == hashed_password` if bcrypt verification fails.
- There is no reviewed rate limiting, lockout, or brute-force protection.
- Health endpoints in `api.py` require auth, including `/health` and `/health/db`.

## Database design
- `models.py` shows a row-based multi-tenant design with `tenant_id` on most domain tables.
- Many `tenant_id` columns are `nullable=True`, not enforced non-null.
- Several payload-style fields are stored as `Text` JSON strings, especially in `OptimizationRun` and `PipelineRun.details_json`.
- Messages and notifications have separate lifecycle tables (`MessageLog`, `MessageRead`, `Notification`, `NotificationPreference`).
- There is an `AuditEvent` model, but no reviewed code writes to it.
- `PatientFlow.datetime` and several schedule/date fields are stored as `String`, not typed dates/timestamps.

## Migrations / schema evolution
- `database.py -> init_db()` still runs `Base.metadata.create_all(bind=engine)`.
- `api.py` startup also runs `ensure_multi_tenant`, `ensure_message_extensions`, `ensure_alerts_notifications`, and `ensure_pipeline_runs`.
- `db_migrations.py` uses raw SQL `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE`, and backfill updates.
- This is explicitly acknowledged in code/docs as a stopgap, not a full migration system.

## Logging / error handling / observability
- Logging is mostly `logging.basicConfig(level=logging.INFO)` and basic `logger.exception(...)`.
- `api.py` has a request middleware that logs method and URL only.
- There are no structured logs, request IDs, metrics, tracing, or centralized exception handlers in reviewed files.
- Error handling is mixed:
  - user-facing validation often raises `HTTPException`
  - some persistence failures are swallowed after `rollback()` plus log, e.g. optimization-run persistence in `api.py`
  - scheduler loop catches exceptions and logs them, but failed runs are not marked failed in `pipeline_runs`

## Production / deployment readiness
- There is a workable baseline for API + Postgres + worker deployment.
- `render.yaml` defines separate web and worker services.
- `docker-compose.yml` defines `db`, `api`, and `dashboard`; it does not run the worker.
- `Dockerfile` is generic and defaults to API.
- Docs acknowledge lack of Alembic and need for public health endpoints.
- Current readiness is partial rather than production-hardened.

## Critical issues and root causes

### 1) Public health check configuration is broken
- Files: `api.py`, `render.yaml`, `DEPLOYMENT_GUIDE.md`
- Root cause:
  - `api.py` protects `/health` and `/health/db` with `require_staff_or_admin`.
  - `render.yaml` sets `healthCheckPath: /health`.
  - `DEPLOYMENT_GUIDE.md` also recommends `/health`.
- Why it matters:
  - managed platform health checks are typically unauthenticated, so deployment health probing can fail.
- Exact issue:
  - deployment config points to an endpoint that requires Bearer auth.

### 2) JWT secret defaults are unsafe in running environments
- Files: `auth.py`, `settings.py`
- Root cause:
  - both files allow fallback to `dev-unsafe-secret-change-me` if `JWT_SECRET_KEY` is absent.
- Why it matters:
  - tokens become forgeable if production is misconfigured or secret injection fails.
- Exact issue:
  - no hard fail for missing secret in production path.

### 3) Password verification silently falls back to plaintext comparison
- File: `auth.py`
- Root cause:
  - `verify_password()` catches all exceptions from bcrypt verification and then compares raw password to stored value.
- Why it matters:
  - this tolerates plaintext password storage and can hide hashing/configuration problems instead of failing closed.
- Exact issue:
  - authentication logic degrades to insecure plaintext auth on hash verification errors.

### 4) Scheduler failures do not reliably update `pipeline_runs` as failed
- File: `scheduler.py`
- Root cause:
  - `run_pipeline_once()` creates a `PipelineRun` with status `running`, but if any later step raises, the outer `scheduler_loop()` logs the exception and sleeps.
  - There is no guaranteed failure-state update on the `PipelineRun` record.
- Why it matters:
  - `/pipeline/status` can show stale/running records instead of real failure states, reducing operational visibility.
- Exact issue:
  - run-level failure persistence is missing.

### 5) Startup schema management is split between `create_all()` and ad hoc SQL migrations
- Files: `database.py`, `api.py`, `db_migrations.py`, `create_tables.py`
- Root cause:
  - tables are created by ORM metadata and then mutated by custom raw SQL patch functions on startup.
- Why it matters:
  - schema drift risk is high, especially for existing DBs, index/constraint parity, and repeatable deployments.
- Exact issue:
  - no single authoritative migration mechanism.

### 6) Migration helpers are inconsistent with ORM tenant/index design
- Files: `models.py`, `db_migrations.py`
- Root cause:
  - ORM models define tenant-aware constraints/indexes such as:
    - `MessageRead`: unique on `(tenant_id, message_id, user_id)`
    - `NotificationPreference`: unique on `user_id` plus tenant index
    - multiple tenant-aware indexes on alerts/notifications
  - migration SQL creates older/global forms, e.g.:
    - `message_reads` unique only on `(message_id, user_id)`
    - `notification_preferences` unique only on `user_id`
    - alerts/notifications creation omits `tenant_id`, later `ensure_multi_tenant()` adds nullable `tenant_id`
- Why it matters:
  - actual DB shape for upgraded instances may not match model intent, especially for multi-tenant correctness.
- Exact issue:
  - startup SQL does not fully mirror `models.py`.

### 7) Multi-tenant enforcement is incomplete at schema level
- Files: `models.py`, `db_migrations.py`, `api.py`
- Root cause:
  - most `tenant_id` fields are nullable and migration code intentionally avoids adding FK constraints for tenant backfills.
- Why it matters:
  - application-level filtering exists, but DB-level isolation/integrity is weak.
- Exact issue:
  - tenant scoping is largely conventional rather than enforced by non-null/FK/compound uniqueness everywhere.

### 8) ETL writes may create tenant-less rows if default tenant is absent
- File: `etl_pipeline.py`
- Root cause:
  - ingestion resolves the default tenant by slug, but if not found, writes rows with `tenant_id = None`.
  - unlike API startup helpers, ETL itself does not ensure tenant creation first.
- Why it matters:
  - imported data can bypass tenant isolation assumptions.
- Exact issue:
  - ETL depends on prior startup migration side effects.

### 9) Local test utility bypasses real configuration
- File: `test_db.py`
- Root cause:
  - hardcoded `DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/hro_db"`.
- Why it matters:
  - test script does not validate deployed/runtime config and can mislead operators.
- Exact issue:
  - config divergence from `settings.py` / `.env` / containerized environments.

## Broken import / runtime risks observed

### 10) Duplicate scheduler risk is explicitly possible
- Files: `api.py`, `worker.py`, `scheduler.py`, `render.yaml`, `DEPLOYMENT_GUIDE.md`
- Root cause:
  - `api.py` can launch `scheduler_loop()` internally when `SCHEDULER_RUN_IN_API=true`.
  - `worker.py` independently runs the same loop.
- Why it matters:
  - if both are enabled in one environment, duplicate pipeline executions and duplicate alerts/optimization runs will occur.
- Exact issue:
  - concurrency separation relies entirely on environment discipline.

### 11) Upload endpoints do not wrap ETL parse/DB errors into API-friendly responses
- Files: `api.py`, `etl_pipeline.py`
- Root cause:
  - upload routes call ingestion functions directly with no local error mapping.
  - ingestion functions can raise pandas parsing/value conversion exceptions.
- Why it matters:
  - callers may receive generic 500 errors with inconsistent failure semantics.
- Exact issue:
  - no endpoint-level validation/error translation around ETL.

### 12) Legacy compatibility route leaks cross-tenant users
- File: `api.py`
- Root cause:
  - legacy `GET /users` route (`_legacy_users`) returns `db.query(User).all()` without tenant filter, unlike `/auth/users`.
- Why it matters:
  - admin in one tenant can see users across tenants through the legacy alias.
- Exact issue:
  - tenant scoping missing on backward-compatible endpoint.

## Documentation / deployment drift
- `MASTER_ROADMAP.md` correctly flags missing Alembic, public health checks, stronger enforcement, and monitoring.
- `DEPLOYMENT_GUIDE.md` states health endpoints “currently require auth,” which matches code, but still recommends them operationally.
- `docker-compose.yml` includes dashboard but not worker, while Render config includes worker.
- `render.yaml` and docs assume the API health check path is usable as-is, but code contradicts that for unauthenticated probes.

## Overall assessment
- The project already has a meaningful backend foundation: FastAPI app, SQLAlchemy persistence, JWT auth, worker-based scheduler, tenant-aware domain models, and deployment manifests.
- The main weaknesses are not missing scaffolding but correctness and hardening gaps:
  - insecure auth fallback behavior
  - health/deployment mismatch
  - migration/schema drift
  - incomplete tenant enforcement
  - weak observability and failure-state recording
  - a concrete tenant leak in legacy `/users`

## Highest-priority fixes from reviewed files
1. Fix public health-check mismatch (`api.py`, `render.yaml`, `DEPLOYMENT_GUIDE.md`).
2. Remove insecure secret/password fallback behavior (`auth.py`, `settings.py`).
3. Correct tenant leak in legacy `/users` alias (`api.py`).
4. Persist pipeline failures explicitly in `scheduler.py`.
5. Replace mixed startup schema patching with one authoritative migration path (`database.py`, `db_migrations.py`, `create_tables.py`).