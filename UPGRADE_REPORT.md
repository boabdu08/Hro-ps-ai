# UPGRADE_REPORT — HF Space pre-flight + creative upgrade pass

**Date:** 2026-06-11 · **Pass:** `HF_PREFLIGHT_AND_UPGRADES_PROMPT.md` Phases A–C
**Final gate:** **277 tests passing** (was 255) · compileall CLEAN · smoke PASSED ·
all 29 pages × 3 roles PASS · pre-flight **ALL PASS (6/6 steps, 10 s)**
**Canonical numbers:** untouched (only the test count grew, as permitted).

---

## Phase A — HF Space pre-flight: findings & fixes

### A1 · Large-file / LFS audit
| Finding | Resolution |
|---|---|
| **Two** git-tracked files exceed HF's 10 MB plain-git limit: `artifacts/models_72h/arimax_ops72h.pkl` (53.5 MB) **and** `arimax_model.pkl` (27.6 MB — the root model `/predict` needs; the prompt only knew about the first) | `.gitattributes` created (LFS rules for `*.pkl/.keras/.h5/.joblib/.npz/.npy`). Because both files are already in plain-git history, the deploy guide mandates the **single-commit orphan-snapshot push** to the Space; the `git lfs migrate import` alternative is documented for a separate clone only. `origin/main` history untouched. |
| git-lfs availability | Already installed (git-lfs/3.7.1) — verified, no install step needed. |

### A2 · Python 3.11 wheel check
`pip download --only-binary=:all: --python-version 311 --platform manylinux2014_x86_64` over
`requirements.txt`: **23/23 pins resolve to wheels, 0 errors** — no source builds on the Space,
no `requirements-space.txt` split needed (dev tools also wheel-clean; install time dominated by
TensorFlow either way, noted in the guide).

### A3 · Cold-boot simulation — `scripts/preflight_hf_space.py` (NEW)
Six steps: Py3.11 syntax sweep → streamlit serves app.py → first-session script run →
internal API `/health` → `admin1/123456` login on fresh SQLite → `/forecast_state` (72 values).
**It caught two Space-fatal bugs that local dev could never see:**

| Bug found by pre-flight | Why local dev never saw it | Fix |
|---|---|---|
| **API startup crash on SQLite**: `db_migrations.py` runs raw Postgres-only DDL (`SERIAL`, `NOW()`) in the FastAPI lifespan; with the Space's default `DATABASE_URL=sqlite:///…` the API died with "Application startup failed" → the Space would render a dashboard with a dead backend | Dev always runs Postgres | All five `ensure_*` helpers now no-op on non-Postgres dialects (`_is_postgres` guard) — `Base.metadata.create_all()` already builds the full schema on SQLite. Verified: API boots + login works on fresh SQLite. |
| **Python 3.12-only syntax** (nested same-quote f-string) in the new Model Health panel — fine on local 3.13, **SyntaxError on the Space's 3.11** | Local venv is 3.13 | Rewritten 3.11-safe; a 3.11 `compileall` sweep over all runtime modules is now pre-flight step 0 **and** a pytest test (`test_upgrade_features.py::TestPython311Syntax`). |

Also hardened `app.py`: repo-root on `sys.path` + absolute `dashboard.py` path (boot no longer
depends on the runner's CWD). Same-class fix in `scripts/drive_all_pages.py` (`AppTest.from_file`
resolves paths relative to the *calling file* — driver broke when promoted into `scripts/`).

### A4 · `DEPLOY_HF_SPACE.md` (NEW)
Copy-paste guide: Space creation, `JWT_SECRET_KEY` secret (exact `secrets.token_urlsafe` command
printed — the user runs `hf auth login` themselves; no secrets handled here), orphan-snapshot
push commands, first-boot expectations (~30 s one-time TF load on first predict), verification
checklist, troubleshooting.

---

## Phase B — ranked backlog (14 proposals) and verdicts

| # | Enhancement | Impact | Effort | Risk | Verdict |
|---|------------|:--:|:--:|:--:|---|
| 1 | Daily Ops Briefing (Home) | High | Low | Low | ✅ **SHIPPED** |
| 2 | Scenario Player (Simulation) | High | Med | Low | ✅ **SHIPPED** |
| 3 | Model Health panel (Evaluation) | High | Low | Low | ✅ **SHIPPED** |
| 4 | Census & occupancy projection (Digital Twin) | High | Med | Low | ✅ **SHIPPED** |
| 5 | Time-to-saturation KPI | High | Low | Low | ✅ **SHIPPED** (with #4) |
| 7 | 80%/95% band toggle (Forecast) | Med | Low | Low | ✅ **SHIPPED** |
| 10 | Guided demo mode (sidebar) | Med | Low | Low | ✅ **SHIPPED** |
| 11 | *(own)* Demo-data freshness chip (Home) | Med | Low | Low | ✅ **SHIPPED** — warns when the demo date window drifts from today (the "Appts=0" bug class), with the exact fix command |
| 6 | Confidence-aware optimizer ranges | Med | Med | **Med** | ❌ Deferred — changes how existing recommendation numbers read days before the demo; bands exist as foundation |
| 8 | One-click Ops Report export (HTML) | Med | Med | Low | ❌ Deferred — new surface to polish/QA; briefing covers the jury value |
| 9 | Live demo ticker (stream_simulator) | Med | Med | **High** | ❌ Deferred — visibly mutating state mid-defense is the riskiest possible demo behaviour |
| 12 | *(own)* API latency badge (sidebar) | Low | Low | Low | ❌ Deferred — nice-to-have, zero jury value |
| 13 | *(own)* One-click demo reset button (admin) | Med | Med | Med | ❌ Deferred — destructive surface near demo day |
| 14 | *(own)* Printable jury one-pager from briefing | Low | Med | Low | ❌ Deferred — overlaps #8 |

**Rule honoured:** everything shipped is additive (new widgets/expanders on existing pages — no
page list changes, no behaviour changes to existing widgets), labelled honestly
(SIMULATION / synthetic stress / latest-available-window), and built on already-tested modules.

## Phase B — file → what → why → test

| File | What | Why | Test |
|---|---|---|---|
| `ops_insights.py` **(NEW)** | Pure, deterministic builders: `build_briefing` (template lines, every number an input), `project_census` + `saturation_label` (uncapped queueing projection → first breach hour), `model_health` (drift_detection → UI verdict dict), `load_bands` (80/95) | All UI features get a framework-free, unit-testable core; no heavy imports (import-perf safe) | `tests/test_ops_insights.py` — **17** |
| `home_section.py` | `_render_ops_briefing` card (ForecastState + dept snapshot + census projection → 5 traceable bullet lines + honesty caption); `_render_demo_freshness_chip` (warns when demo window ∌ today, prints the refresh command) | Seeds #1 and #11 — the strongest "invisible modules made visible" wins | Briefing builder unit-tested; page covered by drive_all_pages |
| `dashboard_sections.py` | `_render_census_projection` (Digital Twin): census vs staffed-beds chart, saturation v-line, 3 KPIs (Time-to-saturation / peak census / staffed beds), SIMULATION caption; Forecast band radio Off/80%/95% (band name + caption follow the choice); `_model_health_payload` (PSI: prior-30-days vs latest-7-days of the real ops dataset; rolling MAE from saved test outputs vs canonical 8.31) + `_render_model_health_panel` on Evaluation; `_cached_scenario_run` + `_render_scenario_player` (6 scenarios × 3 illustrative profiles, demand/census/capacity chart, optimizer summary, SYNTHETIC STRESS caption) | Seeds #4+#5, #7, #3, #2 | `tests/test_upgrade_features.py` — **5** (glue functions + honesty checks); pages via drive_all_pages |
| `dashboard.py` | `_DEMO_SCRIPT_STEPS` (7 steps) + `_render_guided_demo_sidebar` (admin-only expander) | Seed #10 — the 7-minute defense script in the presenter's eyeline | Content test asserts canonical claims present and the retired "10.8%" claim absent |
| `db_migrations.py` | `_is_postgres` guard on all 5 `ensure_*` helpers | Phase A SQLite crash fix | Pre-flight steps 3–6; tenant-isolation suite still green |
| `app.py` | sys.path + absolute-path hardening | Phase A boot robustness | Pre-flight + deployment-readiness suite |
| `scripts/preflight_hf_space.py` **(NEW)** | 6-step cold-boot simulator | The pre-flight itself | Run twice → ALL PASS |
| `scripts/drive_all_pages.py` | Absolute dashboard path | Broke after move to scripts/ (AppTest path semantics) | Re-run: 29/29 pages pass |
| `.gitattributes` **(NEW)**, `DEPLOY_HF_SPACE.md` **(NEW)** | LFS rules; deploy guide | Phase A1/A4 | n/a (docs/config) |

**Test count: 255 → 277** (+17 ops_insights, +5 upgrade features). Import-perf suite green —
no new feature pulls TF/shap/sklearn/scipy at import time.

---

## Phase C — validation & doc sync

| Gate | Result |
|---|---|
| `pytest -q` | **277 passed, 0 failed** |
| `compileall` (venv-excluded) | CLEAN |
| `smoke_forecast_state.py` | PASSED |
| `scripts/drive_all_pages.py` (live API) | 29 pages × 3 roles — **ALL PASS** |
| import-perf tests | green |
| `scripts/preflight_hf_space.py` (final) | **ALL PASS — 6/6 in 10 s** |

Docs synced 255 → 277: README, ARCHITECTURE (×2), FINAL_FILES (header/table/+2 test rows),
DEFENSE_READINESS (current sections), thesis MD + **DOCX recompiled** (9,815 KB, 35 figures).
No tab/page count changed (all features live inside existing pages).

## Demo-day checklist (updated)

```powershell
python scripts/refresh_demo_dates.py --db    # re-anchor demo dates to today
python scripts/preflight_hf_space.py         # 6-step cold-boot check (10 s)
./scripts/run_all.ps1                        # API + dashboard, one command
venv\Scripts\python scripts/drive_all_pages.py   # optional: auto-visit all 29 pages
```
Space deployment: follow `DEPLOY_HF_SPACE.md` (snapshot push — ~15 min including build).
