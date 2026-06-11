# HRO-PS — Final Submission File Inventory

**Date:** 2026-06-10  
**Pass:** FINAL_SUBMISSION_PROMPT.md (Phases A–E) + FINAL_ENHANCEMENT_PROMPT.md (Phases 1–4)  
**State:** **255 tests passing** · Smoke PASSED · compileall clean · canonical metrics unchanged

---

## Submission-Ready Deliverables

### Documents and Decks  (`D:\Hro new dashboard\`)

| File | Size | Description |
|------|------|-------------|
| `HRO-PS_Thesis_REVISED.docx` | 9,815 KB | **PRIMARY THESIS** — 8 chapters, 35 embedded figures, commercial-products table (Table 2.2), testing table (Table 5.3), Hugging Face deployment. Recompiled 2026-06-11 with updated 255-test coverage statement. |
| `HRO-PS_Thesis_REVISED.md` | 100 KB | Thesis source markdown (edit this, recompile to DOCX). |
| `HRO-PS_Paper_REVISED.docx` | 3,188 KB | **RESEARCH PAPER** — 10 pages, journal structure, 5 dashboard screenshots + 3 diagrams embedded. ⚠️ Requires paraphrase + Turnitin + AI-detection before journal submission. |
| `HRO-PS_Paper_REVISED.md` | 31 KB | Paper source markdown. |
| `HRO-PS_Presentation_FINAL_v3.pptx` | 41,880 KB | **PRESENTATION** — 31 slides: commercial benchmark (new), model-evaluation (new), Why-LSTM/ARIMAX, Hybrid architecture, RAG loop, Risk & Crisis framing. Deployment = Hugging Face. Speaker notes on S03/S08/S13/S14. |
| `HRO-PS_Poster_FINAL_v2.pptx` | 2,957 KB | **POSTER** — A0 format, canonical metrics in both tables, 6 embedded figures/screenshots, KPI cards show real model metrics (not fabricated surgery stats). |
| `HRO-PS_Supervisor_Compliance_and_Changes.md` | 8 KB | All 32 supervisor instructions with ✅/🟡/🔴→✅ status. |

---

### Code Repository (`D:\hro-ps-ai\`)

**Core application files:**

| File | Size | Description |
|------|------|-------------|
| `api.py` | 81 KB | FastAPI: 48 endpoints, RBAC, MILP optimizer, ALERT_ROUTING_TABLE, Purpose/Source/Destination docstrings. |
| `dashboard.py` | 17 KB | Streamlit entry point: login, sidebar, 13-tab routing. |
| `dashboard_sections.py` | 143 KB | All 13 tab renderers: Forecast, Optimization (Needed/Shortage labels), Digital Twin, Explainability, Simulation, etc. |
| `forecast_state.py` | 19 KB | ForecastState frozen dataclass — canonical single source of truth. |
| `resource_optimizer.py` | 26 KB | MILP resource allocation via `scipy.optimize.milp`; Purpose/Source/Destination docstring. |
| `approval_sections.py` | 27 KB | Recommendation approval/rejection with RAG re-validation badge after apply. |
| `notification_sections.py` | 19 KB | Alert + notification center; admin alert-routing table expander. |
| `api_client.py` | 8 KB | Streamlit-side REST client; includes `get_alert_routing_table()`. |
| `feature_spec.py` | <1 KB | Canonical 26-feature columns shared by training, inference, and roll-forward. |
| `forecast_features.py` | 8 KB | Feature engineering: lags, rolling stats, `trend_feature` (formula documented). |
| `auth.py` | 2 KB | bcrypt/HS256 JWT; `require_role`/`require_admin_or_staff` decorators. |
| `models.py` | 19 KB | 21 SQLAlchemy models, all tenant-scoped with `tenant_id` FK. |

**Training and artifact pipeline:**

| File | Description |
|------|-------------|
| `train_lstm_ops72h.py` | LSTM (128→64→32→1) training on 17,520×61 dataset, 24-h lookback, 72-h horizon. |
| `train_arimax_ops72h.py` | SARIMAX(1,1,1) with 9 exogenous features; 72-h horizon. |
| `build_hybrid_ops72h.py` | Constrained grid search α∈[0.20,0.80]; selects 0.80/0.20 by validation RMSE. |
| `generate_ops72h_outputs.py` | Pre-generates all forecast CSVs + metrics JSON into `artifacts/`. |
| `forecast_features.py` | Feature engineering with `trend_feature` formula documented. |

**Tests:**

| File | Tests | Description |
|------|-------|-------------|
| `tests/test_auth_and_rbac.py` | 20 | bcrypt, JWT round-trip, tenant claims, RBAC gates. |
| `tests/test_data_integrity.py` | 44 | 17,520 rows, canonical metrics, no negative forecasts, artifact presence. |
| `tests/test_optimizer.py` | 39 | MILP allocation, shortage computation, department config. |
| `tests/test_evaluation.py` | 21 | Evaluation service metrics. |
| `tests/test_deployment_readiness.py` | 25 | Artifacts exist AND are git-tracked; app.py import-safe; no training on startup; no hard-coded secrets. |
| `tests/test_patient_flow_sim.py` | 18 | Census simulation: LOS dynamics, capacity caps, overflow, determinism. |
| `tests/test_production_scenarios.py` | 18 | M9 OOD harness: 6 scenarios × hospital profiles; forecast→optimizer linkage. |
| `tests/test_security_hardening.py` | 15 | Rate limiter, security headers, CSV-only uploads, Pydantic bounds, JWT secret guard. |
| `tests/test_supplementary_eval.py` | 14 | Supplementary artifacts well-formed; hybrid metrics reproduce canonical 8.31/10.22/6.07. |
| `tests/test_drift_detection.py` | 11 | PSI input drift + rolling-MAE performance drift. |
| `tests/test_tenant_isolation.py` | 6 | Tenant A cannot read tenant B (users, alerts, notifications, patient flow). |
| `tests/test_demo_date_refresh.py` | 10 | Appts(7-day)=0 bug: whole-week date-shift logic + KPI window against refreshed data. |
| `tests/test_import_performance.py` | 8 | `import api`/`dashboard_sections` must not pull TF/shap/sklearn/scipy eagerly. |
| `tests/test_predict_clamp.py` | 2 | /predict never returns negative patient counts. |
| `tests/test_forecast_state_wiring.py` | 1 | Cross-tab ForecastState consistency. |
| `tests/test_health.py` | 1 | Health endpoint response. |
| `tests/test_imports.py` | 2 | API + dashboard import-safety. |
| **Total** | **255** | All passing. No mocks on forecast artifacts. |

**Enhancement-pass additions (2026-06-10):**

| File | Description |
|------|-------------|
| `patient_flow_sim.py` | Admission→LOS→discharge census simulation (log-normal LOS, capacity, overflow). |
| `production_scenarios.py` | M9 OOD harness: surge/holiday/COVID/mass-casualty/infeasible × 3 hospital profiles. |
| `drift_detection.py` | PSI input drift + rolling-MAE performance drift vs canonical baseline. |
| `rate_limit.py` | Sliding-window rate limiter (login 10/min, upload 20/5 min per IP). |
| `generate_supplementary_eval.py` | Regenerates `artifacts/metrics_72h/supplementary/` (loss curves, residuals, folds, per-dept, bands). |
| `app.py` | Hugging Face Spaces single-container bootstrap (API thread + dashboard). |
| `README_HF_SPACE.md` | Space card (YAML config + secrets table + honest-data disclosure). |
| `ARCHITECTURE.md` | One-page architecture/decision note (10 decisions with trade-offs). |
| `artifacts/metrics_72h/supplementary/` | Supplementary evaluation: `supplementary_evaluation.json` + `lstm_loss_curves.csv`. |

**Deliverable reports (this repo):**

| File | Description |
|------|-------------|
| `SUPERVISOR_COMPLIANCE_CODE.md` | Phase A: code-side evidence for all 🟡 supervisor items. |
| `DEFENSE_READINESS.md` | Phase E: graduation-committee simulation scores + Q&A prep. |
| `ENHANCEMENT_REPORT.md` | Enhancement pass: new scores (8.9/10, +0.3), backlog Done/Deferred, risks, verdict. |
| `CODE_IMPROVEMENTS.md` | All code changes with severity, evidence, and test counts. |
| `AUDIT_REPORT.md` | Full audit findings (H/M/L severity), fixes applied, items left open. |
| `FINAL_FILES.md` | This file — submission inventory. |

**Phase 10 scripts (one-time document build tools):**

| File | Description |
|------|-------------|
| `update_pptx_v2.py` | Phase 10 presentation sync (previous session). |
| `update_poster_v2.py` | Phase 10 poster rebuild: canonical metrics, 6 figures. |
| `insert_figures_v2.py` | Thesis/paper figure injection from `*(diagram)*`/`*(screenshot)*` markers. |
| `remap_screenshots.py` | Screenshot content-based renaming (PDF → verified tab names). |
| `update_presentation_final.py` | Phase D: commercial-products + model-eval slides, HF deployment. |

---

## Canonical Numbers (quick reference)

| Metric | Value |
|--------|-------|
| Training dataset | 17,520 hourly rows × 61 cols, 2024–2025 synthetic |
| Departments | 5: ER, ICU, General Ward, Surgery, Radiology |
| LSTM sequence lookback | 24 hours |
| LSTM test: MAE / RMSE / MAPE | **7.65 / 9.58 / 5.52%** — best individual model |
| ARIMAX test: MAE / RMSE / MAPE | 15.63 / 19.33 / 12.33% — baseline |
| Hybrid 0.80/0.20 test: MAE / RMSE / MAPE | **8.31 / 10.22 / 6.07%** — deployed |
| Weight selection | Constrained grid search α∈[0.20,0.80], 13 combinations |
| Forecast horizon | 72 hours |
| API endpoints | 48 (FastAPI) |
| Database tables | 21 (all tenant-scoped) |
| Dashboard tabs | 13 (3 role-based views) |
| Tests | **255 passing** |
| Deployment | Hugging Face Spaces (GitHub-linked) |
| Industrial reference | Al-Demerdash Hospital, Ain Shams University (site visit; no real patient data) |

---

## Outstanding Manual Tasks (cannot be automated)

| # | Task | Owner | Notes |
|---|------|-------|-------|
| 1 | **Paraphrase paper + run Turnitin + AI-detection** | Team | Supervisor M8/M10 hard requirement before journal submission |
| 2 | Apply College Journal Word template to paper DOCX | Team | Supervisor to provide link |
| 3 | Confirm Al-Demerdash partnership wording with team | Team | Supervisor instruction |
| 4 | ~~Commit LSTM `.keras` artifact~~ **DONE** | — | All model artifacts git-tracked; verified by `tests/test_deployment_readiness.py` |
| 5 | Create the actual Hugging Face Space (push repo, set `JWT_SECRET_KEY` secret, use `README_HF_SPACE.md` as Space README) | Team | ~15 min; bootstrap (`app.py`) is committed and test-verified |
| 6 | Demo rehearsal — full 2-minute script | Team | See `DEFENSE_READINESS.md` recommended script |
