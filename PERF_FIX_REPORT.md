# PERF_FIX_REPORT — Startup speed, Appts KPI fix, full runtime eval

**Date:** 2026-06-11 · **Pass:** `PERF_AND_DASHBOARD_FIX_PROMPT.md` Phases 0–4
**Final gate:** **255 tests passing** (was 235) · `compileall` CLEAN · smoke PASSED
**Canonical numbers:** untouched (dataset/metrics/horizon/endpoints/tables/tabs unchanged; test count grew, as permitted)

---

## 1. Baseline → After

| Measurement | Baseline (Phase 0) | After (Phase 1) | Change |
|---|---|---|---|
| `import api` (cold cache) | **31.6 s** | **2.1 s** | **15× faster** |
| — `evaluation_service` (chain) | 21.4 s | 0.6 s | sklearn deferred |
| — `sklearn.metrics` | 15.0 s | not imported | lazy |
| — `scipy.stats` | 7.5 s | not imported | lazy |
| `import dashboard` | 18.7 s (10 s is Streamlit itself) | ~12 s cold | heavy libs no longer pulled |
| API cold start → `/health` | 6.7 s | **5.1 s** | −24 % (warm cache; truly cold gains the full import delta) |
| Dashboard cold start → login page | 4.8 s | **2.0 s** | −58 % |
| D: free disk | 511 GB | **514 GB** | **≈3.2 GB freed** |
| Python environments | 3 (5.45 GB) | **1** (`venv`, 2.31 GB) | consolidated |

Root causes of slowness: (1) `evaluation_service.py` eagerly imported `sklearn.metrics` at module level — every API/dashboard start paid the full sklearn+scipy chain; (2) three redundant venvs (also made `compileall .` crawl ~5 GB of site-packages); (3) an **orphaned uvicorn multiprocessing child** from a dead parent was still holding port 8000 (killed; this alone can make "the API" look frozen/stale).

---

## 2. Phase 1 — Startup & disk (file → what → why → test)

| File | What | Why | Test |
|---|---|---|---|
| *(deleted)* `.venv/` (2.37 GB), `.venv311/` (0.77 GB) | Removed; `venv` (Py 3.13.3) is the single canonical env — it runs API + dashboard + tests; `python-pptx` installed into it so deck tooling works | Pre-approved consolidation; ~3.14 GB + pip cache (13 dirs) + 5.7 MB junk freed | Full suite green on `venv` |
| *(deleted)* `tmp_git_status.txt`, `tmp_streamlit_index.js` (git-rm — was tracked junk), `tmp_login.json`, `tmp_tab_distinctness.txt`, `zzz_test_write.txt`, repo `__pycache__` | Stale junk removal | Phase 1 cleanup list | n/a |
| **NOT deleted:** `clean_data(AutoRecovered).csv` | Kept | **Guardrail 2** (never touch `clean_data*.csv`) + it is git-tracked and referenced by `tests/test_data_integrity.py`, `forecasting_pipeline.py`, `dashboard_sections.py` — the prompt's own "verify untracked/unreferenced" check fails | data-integrity tests depend on it |
| `evaluation_service.py` | `sklearn.metrics` import moved inside `calculate_metrics()` | The 15 s offender on every cold start; functions only needed when metrics are recomputed | 255 green + import-perf tests |
| `resource_optimizer.py` | `scipy.optimize` import moved inside `_solve_integer_resource_allocation()` | Same pattern; solver only needed when an optimization runs | 39 optimizer tests green |
| `tests/test_import_performance.py` **(new, 8 tests)** | Subprocess-isolated: after `import api` / `import dashboard_sections`, asserts `tensorflow`, `shap`, `sklearn`, `scipy` are NOT in `sys.modules` | Locks the lazy-import behaviour (prompt asked for TF+shap; sklearn+scipy added since they were the actual offenders) | 8 pass |
| `scripts/run_all.ps1` **(new)** | Starts API in background, waits for `/health` (90 s budget), then dashboard in foreground; reuses an already-running API | One command for demo day | manual run |
| `scripts/run_api.ps1`, `scripts/run_dashboard.ps1` | Now pin `venv\Scripts\python.exe` explicitly (old fallback chain referenced the deleted `.venv311`) | Would have thrown after consolidation | manual run |
| `README.md` | Quickstart: ONE canonical env section, `run_all.ps1`, `refresh_demo_dates.py` pre-demo step | Doc currency | n/a |

---

## 3. Phase 2 — "Appts (7-day) = 0" fix

**Root cause (verified):** `data/updated_exports/appointments_updated.csv` dates spanned 2026-05-16..29; the Home KPI filters `[today, today+7]`; today (2026-06-11) was past the window → 0. OR Bookings showed a count because that KPI counts by *status*, not date.

| File | What | Why | Test |
|---|---|---|---|
| `scripts/refresh_demo_dates.py` **(new)** | Shifts date columns of `appointments_updated.csv`, `or_bookings.csv` (`booking_date`+`date`), `staff_schedule.csv` (`shift_date`) by **whole weeks** (floor-based, bidirectional) so today lands inside the window; weekday alignment preserved; idempotent; hard guard refuses `artifacts/`/`clean_data*` paths. `--db` mode additionally anchors the **DB** columns the optimizer filters with `== today` (`appointments.date`, `or_bookings.date`, `staff_shifts.shift_date`) to today by exact-day shift | The CSV fix repairs the Home KPI; the DB fix repairs the optimizer's live operational state (it filters rows to *today* and was finding zero) | 10 tests + idempotency verified live |
| **Ran it:** CSVs now 2026-06-06..19 (today inside) → **Appts (7-day) KPI = 97** (was 0); DB now has **55 appointments, 9 OR bookings, 20 staff shifts ON today** | | | |
| `tests/test_demo_date_refresh.py` **(new, 10 tests)** | Unit tests of `_weeks_to_shift` (forward/backward/weekday-preserving/far-stale) + the exact home_section windowing logic against the real CSVs **with the shift applied in-memory** (so the test itself never goes stale) + guard that targets never include canonical paths | Regression lock on the bug | 10 pass |

**Anchor audit (other widgets):**
- Home appointment *snapshot* (same 7-day filter) — fixed by the same CSV refresh.
- OR KPI / OR snapshot — status-based, was never broken; dates now current anyway.
- Shifts / Appointments / OR Bookings *tabs* (`staff_sections.py`) — already remap display dates to today ("live demo mode"); unaffected.
- `resource_optimizer.py` live filters (`== today`) — fixed by `--db` mode (above).
- `patient_tracking.csv` (entry dates 2025-12-31) — no today-window consumer found; left untouched.

---

## 4. Phase 3 — Run-everything eval: errors found & fixed

**API (live uvicorn, all 43 routes):** login + 23 endpoint exercises all returned 200 (`/health/full` fully green: api/database/artifacts ok, all 3 models ok); server log clean (only benign TF-on-Windows notices).

| Found | Severity | Fix | Test |
|---|---|---|---|
| `POST /predict` returned **−591.97 patients** for a garbage (out-of-distribution) input sequence; downstream `beds_needed` went negative too | Medium (robustness; jury could see a negative census) | `api.py predict()`: clamp `predicted_patients = max(0.0, ·)` — mirrors the artifact pipeline's no-negative-forecast validation rule | `tests/test_predict_clamp.py` (2) |
| Orphaned uvicorn child process holding :8000 from a previous session | Low (env hygiene) | Killed; documented here — if the API "won't restart", check `Get-NetTCPConnection -LocalPort 8000` | n/a |

**Dashboard (AppTest, every page × every role):** **29 pages across admin (14), doctor (8), nurse (7) — ALL PASS, zero exceptions.** Live `streamlit run` serves HTTP 200 with 0 errors in the log; `get_live_context()` returns `ready=True` with the API up → sidebar **System Status shows online**.

| Found | Severity | Fix | Test |
|---|---|---|---|
| The screenshot bug — "Prediction API is not reachable… make sure uvicorn is running" while uvicorn IS running. Root cause: the **first** `/predict` after API start lazy-loads TensorFlow + model (10–30 s), exceeding the client's 25 s timeout → misleading banner | High (demo-visible) | `api_client.py`: `/predict` timeout 25→90 s with rationale comment; `dashboard_sections.py`: message now shows the actual base URL and explains first-call warm-up + 60-min token expiry | AppTest Command Center passes incl. warm-up path |

**Consistency checks:**

| Item | Verdict | Action |
|---|---|---|
| Header badge "Model: LSTM" | Intended (`ForecastState.selected_model` = best by test RMSE) but ambiguous next to "deployed Hybrid" elsewhere | Relabelled **"Best model: LSTM"** + hover tooltip: "Best model by test RMSE… deployed operational forecaster is the Hybrid (LSTM 0.80/ARIMAX 0.20)" (`home_section.py`) |
| Home "Available Beds 43/172" vs optimizer ≈293 beds | Different scopes, both correct: 172 = currently **staffed/open** beds (live dept-status snapshot); 293 = **configured physical capacity** incl. overflow/hallway bays (optimizer planning ceiling) | Clarifying caption added under the Home KPI row (`home_section.py`) |

**Deferred (too risky now, listed instead of fixed):**
- Streamlit `use_container_width` deprecation warnings (~100 call sites across all section files; removal deadline already passed upstream but only logs warnings). Cosmetic; a mass find-replace days before the demo risks layout regressions. Post-demo task.
- `pd.to_datetime` "could not infer format" warning in `dashboard_sections.py:81` — cosmetic, data loads correctly.
- Full DB reseed via `seed_operational_demo_data_phase5.py` — would also regenerate the display CSVs and operational values; the surgical date-anchor (`--db`) achieves the needed effect with far smaller blast radius.

---

## 5. Phase 4 — Gate, doc sync, commit

- Gate: **255 passed** (235 + 8 import-perf + 10 demo-date + 2 clamp) · `compileall` (repo, venv-excluded) CLEAN · smoke PASSED.
- `tmp_apptest_drive.py` promoted to **`scripts/drive_all_pages.py`** — reusable pre-demo check that visits every page for every role against the live API.
- Doc-cited test count 235→255 synced: `README.md`, `ARCHITECTURE.md` (×2), `FINAL_FILES.md` (header, table, +3 new test rows), `DEFENSE_READINESS.md` (current sections; the explicitly-historical "Previous Scores" block left as a record), thesis MD updated and **DOCX recompiled** (9,815 KB, 35 figures) — same procedure as previous passes.
- Committed locally (not pushed — user pushes manually).

## Demo-day checklist (30 seconds)

```powershell
python scripts/refresh_demo_dates.py --db   # re-anchor demo dates to today
./scripts/run_all.ps1                        # API + dashboard, one command
venv\Scripts\python scripts/drive_all_pages.py   # optional: auto-visit all 29 pages
```
