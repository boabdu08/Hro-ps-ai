# HF_PREFLIGHT_AND_UPGRADES_PROMPT — Space deployment pre-flight + creative upgrade pass

Execute all phases end to end. Report per phase and per file. Demo is days away:
everything must be additive, test-backed, and honest.

---

## HARD GUARDRAILS (unchanged, non-negotiable)

1. **Never change canonical numbers/claims.** Dataset 17,520×61 · LSTM 7.65/9.58/5.52% ·
   ARIMAX 15.63/19.33/12.33% · Hybrid 0.80/0.20 → 8.31/10.22/6.07% (deployed) · 72-h ·
   48 endpoints · 21 tables · 13 tabs. Test count may only grow (currently 255).
2. **No retraining, no fabricated data.** Every UI number comes from real artifacts/data or
   is explicitly labelled a demo assumption / simulation.
3. **All tests stay green**, including `tests/test_import_performance.py` — no new feature
   may make `import api` / `import dashboard_sections` pull heavy libs eagerly.
4. **Never rewrite the GitHub origin history.** Any LFS work happens on a separate
   Space remote / fresh clone, never on `origin/main`.
5. Gate after every phase: `pytest -q` → `compileall` (venv-excluded) → `smoke_forecast_state.py`.

---

## Phase A — Hugging Face Space pre-flight (find every failure BEFORE the user creates the Space)

**A1. Large-file / LFS audit (known blocker — verify and solve).**
`artifacts/models_72h/arimax_ops72h.pkl` is 56 MB and git-tracked; HF rejects files >10 MB
without Git LFS, and there is no `.gitattributes`. Do:
- List every git-tracked file >10 MB (`git ls-files | size check`).
- Create `.gitattributes` with LFS rules for the offending patterns (e.g.
  `artifacts/models_72h/*.pkl filter=lfs diff=lfs merge=lfs -text`).
- Because the file is already in history, document BOTH paths in the deploy guide and
  recommend the safe one: push to the Space from a **fresh single-commit snapshot**
  (orphan branch or new clone with `git lfs migrate import` run there) — never rewrite origin.
- If `git lfs` is not installed locally, detect that and put the install step in the guide.

**A2. Python 3.11 wheel check.** The Space runtime is 3.11 (`runtime.txt`); local dev is 3.13.
Verify every pin in `requirements.txt` resolves to a **wheel** for `cp311` / `manylinux`
(e.g. `pip download --only-binary=:all: --python-version 311 --platform manylinux2014_x86_64
--dest tmp_wheelcheck --no-deps -r requirements.txt`, then clean up). Fix any pin that would
force a source build on the Space. Also confirm dev-only packages (pytest/black/flake8) are
acceptable or split a `requirements-space.txt` if install time is a concern — README_HF_SPACE
must match whatever you decide.

**A3. Space cold-boot simulation (local).** Build `scripts/preflight_hf_space.py`:
- Runs `streamlit run app.py` headless in a sanitized env (fresh temp sqlite `DATABASE_URL`,
  no `API_TOKEN`, a dummy `JWT_SECRET_KEY`) to mimic a brand-new Space container.
- Asserts within a 120 s budget: dashboard serves HTTP 200 → internal API `/health` ok →
  `auth/login admin1/123456` succeeds (dev seeding) → `/forecast_state` returns data.
- Prints PASS/FAIL per step; clean teardown (no orphaned processes on :8501/:7861).
Run it now and fix whatever it finds (this is the whole point of the pre-flight).

**A4. Write `DEPLOY_HF_SPACE.md`** — exact copy-paste steps for the user:
create the Space (Streamlit SDK), `git lfs install`, add the `space` remote, the snapshot
push commands from A1, set `JWT_SECRET_KEY` in Space secrets, first-boot expectations
(cold TF load ~30 s on first predict), and a verification checklist. Where the user's HF
login/token is required, STOP and print the exact command for them — do not ask for secrets.

---

## Phase B — Creative upgrade pass (propose, rank, implement the safe winners)

Propose **at least 12 enhancements** — the 10 seeds below plus your OWN new ideas (be
creative; new modules from the previous passes are tested but invisible in the UI, which is
wasted jury value). Rank all by Impact × Effort × Risk in the report, then **implement the
top ~5–7 that are additive and demo-safe**. Defer anything that changes existing behaviour.

Seeds (all build on already-tested modules — surfacing them is low-risk):
1. **Daily Ops Briefing** — template-based natural-language summary card on Home, generated
   deterministically from ForecastState + alerts + optimizer state ("Peak of ~218 expected
   Fri 14:00; ICU projected over 90% occupancy; 2 critical alerts open; recommended +6 beds
   in ER"). No LLM, fully honest, every number traceable.
2. **Scenario Player** — dropdown in the Simulation tab wiring `production_scenarios.py`
   (baseline/surge/holiday/COVID-ramp/mass-casualty/infeasible × hospital profiles) to charts:
   demand vs census vs capacity, optimizer deltas. Clearly labelled "synthetic stress input".
3. **Model Health panel** — admin Evaluation tab card surfacing `drift_detection.py`:
   PSI status chip (stable/moderate/major), rolling MAE vs canonical 8.31 baseline, verdict.
4. **Census & Occupancy projection** — Digital Twin chart from `patient_flow_sim.py`
   (projected occupied beds + overflow from the 72-h forecast, per department toggle).
5. **Time-to-saturation KPI** — single number: hours until projected census exceeds staffed
   beds (∞/"not within 72 h" when safe). Derives from #4; very operational, jury-friendly.
6. **Confidence-aware recommendations** — optimizer outputs shown with ranges using the
   existing empirical bands ("Beds needed: 120 (range 110–135 @80%)").
7. **80%/95% band toggle** on the Forecast chart (artifact already has both bands).
8. **One-click Ops Report export** — downloadable HTML (or PDF if a pure-python lib with a
   cp311 wheel) bundling briefing + KPIs + forecast chart + recommendations; honest footer
   ("synthetic demo data").
9. **Live demo ticker** — opt-in toggle using `stream_simulator.py` to advance the demo
   hour-by-hour so the dashboard visibly "moves" during the defense (labelled SIMULATION).
10. **Guided demo mode** — sidebar expander with the 7-minute demo script (from
    DEMO_RUNBOOK.md) as step-by-step talking points with deep links to the right tabs.

Implementation rules: each shipped feature gets tests (unit-level where UI-bound, AppTest
where feasible); update `scripts/drive_all_pages.py` if pages/widgets change; no new heavy
deps without a cp311 wheel + import-perf tests staying green; every new surface labelled
honestly (synthetic data / simulation / demo assumption).

---

## Phase C — Validate, document, commit

1. Full gate: `pytest -q` (≥255 + new tests, all green), `compileall` (venv-excluded), smoke,
   `scripts/drive_all_pages.py` (all pages × roles must still pass), import-perf tests green,
   re-run `scripts/preflight_hf_space.py` one final time.
2. Write **`UPGRADE_REPORT.md`**: Phase A findings & fixes (incl. the LFS story), full ranked
   backlog with verdicts (shipped / deferred + why), file → what → why → test for every
   change, new test count, demo-day checklist update.
3. Sync any doc-cited number that changed (test count, tab/page count if a new page was
   added — thesis/README/ARCHITECTURE/FINAL_FILES, recompile thesis DOCX as before).
4. Commit locally with a descriptive message. Do not push — the user pushes manually.
