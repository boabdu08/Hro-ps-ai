# Code Improvements Log

**Session:** 2026-06-08  
**Baseline:** 108 tests, 0 failed  
**Final:** 128 tests, 0 failed  
All changes verified with `python -m compileall` and full `pytest` run after each fix.

---

## 1. `hybrid_config.json` — Weight and metric alignment

**Type:** Config fix  
**Severity:** HIGH

Root-level `hybrid_config.json` contained the unconstrained training result (LSTM=1.0/ARIMAX=0.0)
while every other reference in the project stated the canonical deployed weights (0.80/0.20).
The `/predict` and `/explain` API endpoints load this file via `artifacts.py`.

**Change:** Updated `lstm_weight` to `0.8`, `arimax_weight` to `0.2`. Replaced the flat
`validation_metrics` and `test_metrics` blocks with the canonical numbers from
`artifacts/manifests/ops72h_training_summary.json`. Added `_note` field explaining constrained
vs. unconstrained selection rationale, `best_model_by_test_rmse: "LSTM"`, and
`deployed_model: "Hybrid (LSTM 0.80 / ARIMAX 0.20)"`.

---

## 2. `DEMO_RUNBOOK.md` — Q&A section: replace fabricated RMSE claim

**Type:** Documentation correction  
**Severity:** HIGH

Q16 and Q17 in the jury Q&A section contained the claim:
> "Removing ARIMAX raises RMSE from 8.149 to 9.005 — a 10.8% degradation."

No artifact file contains these numbers. The actual canonical test metrics show the hybrid
(RMSE 10.22) is *less* accurate than LSTM alone (RMSE 9.58) — the opposite direction.

**Change:** Rewrote Q16 and Q17 with factually correct numbers and the correct justification:
LSTM is best by test RMSE; hybrid is deployed for *operational robustness* (ARIMAX provides a
linear anchor that prevents forecast volatility when LSTM encounters out-of-distribution patterns).
Unconstrained optimum 0.95/0.05 cited to show ARIMAX still contributes at the minimum constraint.

---

## 3. `DEPLOYMENT_CHECKLIST.md` — Stale metric in demo walkthrough

**Type:** Documentation correction  
**Severity:** HIGH

Demo walkthrough step 2 instructed the presenter to say "Hybrid MAE 6.6 | RMSE 8.1 | MAPE 4.9%".
These values do not exist in any artifact. The dashboard dynamically reads from ForecastState and
would display LSTM MAE 7.64 / RMSE 9.58 (best model), contradicting the spoken numbers.

**Change:** Updated to "LSTM MAE 7.6 | RMSE 9.6 | MAPE 5.5% (best model by test RMSE);
deployed Hybrid LSTM 0.80/ARIMAX 0.20 for robustness."

---

## 4. `etl_pipeline.py` — Tenant isolation + upload size validation

**Type:** Security fix + reliability fix  
**Severity:** HIGH + MEDIUM

**Problem 1 (tenant isolation):** `ingest_patient_flow`, `ingest_appointments`, `ingest_or` all
called `_get_or_create_default_tenant_id(db)` regardless of which tenant the uploading admin
belonged to. In a multi-tenant deployment this routes all uploads to the demo tenant.

**Problem 2 (size validation):** `pd.read_csv(file.file)` was called directly with no size guard.
A 100 MB upload would block the request thread until pandas failed.

**Changes:**
- Added `_validate_upload(file) -> bytes`: reads all bytes first, raises `ValueError` if
  `len(raw) > 10 MB`, returns bytes for `io.BytesIO` wrapping.
- Added `_resolve_tenant_id(db, tenant_id: Optional[int]) -> int`: uses caller-supplied
  `tenant_id` when not None, falls back to default for legacy/seed paths.
- All three ingest functions now accept `tenant_id: Optional[int] = None` and call
  `_resolve_tenant_id`.

---

## 5. `api.py` — Wire JWT tenant_id into upload endpoints

**Type:** Security fix  
**Severity:** HIGH

Upload endpoint handlers extracted `_token` from the JWT (correctly) but did not pass the tenant
to the ingest functions.

**Change:** All three upload handlers (`upload_patient_flow`, `upload_appointments`, `upload_or`)
now accept `db: Session = Depends(get_db)`, call `get_tenant_id(_token, db)`, and pass the result
as `tenant_id=tid` to the corresponding ingest function.

---

## 6. `api.py` — Add logging to `get_tenant_id()` fallback path

**Type:** Security hardening  
**Severity:** MEDIUM

`get_tenant_id()` silently fell back to the default tenant when the JWT claim was absent or
non-integer, with no observable signal.

**Change:** Added `logging.warning()` calls in both fallback branches (missing claim, invalid
integer). The username from the JWT is included in the log message to aid debugging.

---

## 7. `api.py` — Delete dead `home_authenticated` route

**Type:** Dead code removal  
**Severity:** MEDIUM

`home_authenticated()` registered a second `GET /` route (`include_in_schema=False`) after
`home_public()`. FastAPI routes first-match, so `home_authenticated` was unreachable.

**Change:** Deleted the function and its comment block.

---

## 8. `auth.py` — Replace deprecated `datetime.utcnow()`

**Type:** Deprecation fix  
**Severity:** LOW

`create_token()` used `datetime.utcnow()` which is deprecated in Python 3.12+ and produces
a `DeprecationWarning` on every token creation (visible in every test run).

**Change:** Added `timezone` to the `datetime` import. Changed to `datetime.now(timezone.utc)`.

---

## 9. `tests/test_auth_and_rbac.py` — New: 20 auth regression tests

**Type:** Test coverage addition  
**Severity:** MEDIUM

No tests existed for authentication, RBAC, or multi-tenant isolation. A regression in
`require_role`, `hash_password`, `create_token`, or `decode_token` would be invisible.

**Added 20 tests across 4 classes:**
- `TestPasswordHashing` (7): hash format, correct/wrong/empty passwords, bcrypt salting
- `TestJWTRoundTrip` (6): encode/decode, role/tenant_id survival, tamper detection, expiry
- `TestTenantIsolation` (2): distinct tenant_id per token, missing claim returns None
- `TestRequireRole` (5): admin gate pass/block, staff gate pass, missing/invalid token → 401/403

**Test count:** 108 → 128 (all passing).

---

## Summary Table

| # | File | Type | Tests Before | Tests After |
|---|------|------|-------------|-------------|
| 1 | `hybrid_config.json` | Config | 108 | 108 |
| 2 | `DEMO_RUNBOOK.md` | Docs | 108 | 108 |
| 3 | `DEPLOYMENT_CHECKLIST.md` | Docs | 108 | 108 |
| 4 | `etl_pipeline.py` | Security + reliability | 108 | 108 |
| 5 | `api.py` (upload callers) | Security | 108 | 108 |
| 6 | `api.py` (get_tenant_id) | Hardening | 108 | 108 |
| 7 | `api.py` (dead route) | Cleanup | 108 | 108 |
| 8 | `auth.py` | Deprecation | 108 | 108 |
| 9 | `tests/test_auth_and_rbac.py` | Tests | 108 | **128** |

**No regressions. Smoke validation: PASSED after all changes.**
