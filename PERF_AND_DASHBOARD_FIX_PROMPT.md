# PERF_AND_DASHBOARD_FIX_PROMPT — Startup speed, Appts KPI bug, full runtime eval & fix

Execute all phases end to end. Report per phase and per file. This is days before the
graduation demo: prefer minimal, surgical, test-backed changes.

---

## HARD GUARDRAILS (same as previous passes — non-negotiable)

1. **Never change canonical numbers or claims.** Dataset 17,520×61 · LSTM test 7.65/9.58/5.52% ·
   ARIMAX 15.63/19.33/12.33% · Hybrid 0.80/0.20 → 8.31/10.22/6.07% (deployed) · 72-h horizon ·
   48 endpoints · 21 tables · 13 tabs. Test count may only GROW (currently 235).
2. **No retraining. No new model runs.** Never touch `artifacts/`, `clean_data*.csv`,
   training CSVs, or anything the metrics were computed from.
3. **All tests stay green.** Every fix gets a regression test where feasible.
4. **No fabrication.** If a number is shown in the UI it must come from real data or be
   labelled as a demo assumption.
5. Validation gate after every phase: `python -m pytest -q` → `python -m compileall . -q` →
   `python scripts/smoke_forecast_state.py`. All three must pass before moving on.

---

## Phase 0 — Baseline measurements (record, don't fix yet)

1. Disk: free space on D:; list every virtualenv dir in the repo (`.venv*`, `venv`, `env`)
   with size in GB.
2. Import profile: `python -X importtime -c "import api" 2> tmp_importtime_api.log` and
   `python -X importtime -c "import dashboard" 2> tmp_importtime_dash.log`. Report the top
   10 cumulative offenders for each.
3. Cold-start timings: seconds until `uvicorn main:app` answers `GET /health`, and seconds
   until `streamlit run dashboard.py --server.headless true` serves the login page.
4. Baseline validation trio (pytest / compileall / smoke) must pass before any change.

---

## Phase 1 — Startup performance + disk (the user recreated 3 venvs; startup is very slow)

1. **Consolidate to ONE Python environment** (user has pre-approved deleting the extras):
   - Decide which interpreter actually runs the project (the test suite currently runs on
     system Python 3.13 with user-site packages). Keep exactly one environment that can run
     API + dashboard + tests; update `scripts/run_api.ps1`, `scripts/run_dashboard.ps1`, and
     the README quickstart to reference it explicitly.
   - Delete the redundant venvs with `Remove-Item -Recurse -Force` (PowerShell delete frees
     space immediately — no Recycle Bin). Also run `pip cache purge` and delete stale junk:
     `tmp_git_status.txt`, `tmp_streamlit_index.js`, `clean_data(AutoRecovered).csv` (verify
     untracked/unreferenced first), old `__pycache__` dirs.
   - Report GB freed and final free-disk number. (Low disk is itself a major slowness cause.)
2. **Lazy-load heavy imports.** TensorFlow is already lazy in `forecast_inference*.py` —
   verify nothing else pulls it (or `statsmodels`, `sklearn`, `shap`) at module import time
   through the chains `api.py → forecast_inference_ops72h → forecasting_pipeline` and
   `dashboard.py → dashboard_sections → evaluation_service / forecast_runtime`. Defer any
   eager heavy import into the function that needs it. Do NOT restructure architecture —
   import deferral only.
3. **Add a regression test** (`tests/test_import_performance.py`): after `import api` and
   `import dashboard_sections`, assert `"tensorflow" not in sys.modules` and
   `"shap" not in sys.modules` (use a subprocess so test order can't pollute it).
4. **Add `scripts/run_all.ps1`**: starts the API (background) waits for `/health`, then starts
   the dashboard — one command for demo day.
5. Re-measure the Phase 0 timings and report before → after.

---

## Phase 2 — Fix "Appts (7-day) = 0" (root cause already diagnosed — verify, then fix)

**Verified root cause:** `home_section.py` → `_home_appointments()` reads
`data/updated_exports/appointments_updated.csv` (dates clustered around the demo anchor
~2026-05-18..25) and the KPI at line ~371 filters `[datetime.now().date(), +7 days]`.
Real "today" (June 2026) is past every appointment date → count 0. OR Bookings shows 102
because that KPI counts by *status*, not date. Classic stale-demo-data / mixed-time-anchor bug.

1. Implement **`scripts/refresh_demo_dates.py`** (recommended fix):
   - Shifts the *date columns only* of display CSVs in `data/updated_exports/`
     (`appointments_updated.csv`, `or_bookings.csv`, `staff_schedule.csv`, and any other
     dated display CSV) forward in **whole weeks** so weekday alignment is preserved and
     "today" falls inside the data window. Values/rows otherwise unchanged.
   - NEVER touches `artifacts/`, training data, or anything canonical-metric related.
   - Idempotent (running twice is safe), prints what it shifted, documented in README
     ("run before demo day").
   - Run it now so the dashboard is correct immediately.
2. **Audit every other widget for the same today-vs-anchor bug** — shifts "this week",
   OR bookings date windows, any "next 24h/7d" filter in `home_section.py`,
   `staff_sections.py`, `dashboard_sections.py` — and fix consistently (same anchor logic).
3. **Regression test**: Appts-window logic returns > 0 against the refreshed data, and/or a
   unit test of the windowing with a fixture whose dates straddle "today".

---

## Phase 3 — Quick eval: run everything, fix every error found

1. **API**: start `uvicorn main:app`. Verify `/health`, login (demo `admin1`/`123456`),
   then exercise the main endpoints (predict, 72h forecast, optimization, alerts,
   notifications, appointments, shifts, messages). Fix any traceback / 500 / validation
   error found. Watch the server log while doing Phase 3.2 and fix anything it prints.
2. **Dashboard**: with the API up, drive the app programmatically with
   `streamlit.testing.v1.AppTest` (`AppTest.from_file("dashboard.py")`) — log in and visit
   every page for each role (admin, doctor, nurse). Assert no exceptions per page. Fix
   everything found. Also run it live once and confirm the sidebar **System Status** shows
   online (the bug in the screenshot — "Prediction API is not reachable… make sure uvicorn is
   running and API_BASE_URL is correct" — must not appear while uvicorn IS running; if it
   does, debug `api_client.py` base-URL/env handling).
3. **Consistency checks** (verify; fix or caption only if actually wrong — do not change
   canonical claims):
   - Header badge says "Model: LSTM" — confirm intended (legacy next-hour path) vs the
     deployed Hybrid naming used elsewhere; align the label or add a tooltip if misleading.
   - Home "Available Beds 43/172" vs optimizer's ~293 total beds — if these are different
     scopes, add a clarifying caption; if it's a data bug, fix the source.
4. Anything found that is too risky to fix now: list it in the report with the reason
   instead of fixing silently.

---

## Phase 4 — Validate, document, commit

1. Full gate: `pytest -q` (≥235, all green, plus the new tests), `compileall`, smoke.
2. Write **`PERF_FIX_REPORT.md`**: baseline vs after startup seconds, GB freed, root causes,
   every file changed (file → what → why → test), errors found & fixed in Phase 3, deferred
   items. If any doc-cited number changed (e.g. test count), sync README/ARCHITECTURE/
   FINAL_FILES exactly as in previous passes.
3. Commit with a descriptive message. Do not push (the user pushes manually).
