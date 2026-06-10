# Claude Code — HRO‑PS Finalization & 10/10 Hardening Prompt

> Open this repo (`hro-ps-ai`) in VS Code with Claude Code, then paste the prompt block below.
> It is pre‑loaded with the verified ground truth and the known weak points from the documentation audit, so Claude Code starts from our findings instead of re‑deriving them.

---

## PASTE THIS INTO CLAUDE CODE

You are acting as Senior Software Architect, Principal Engineer, Security Auditor, QA Lead, and Graduation Committee Examiner. Your mission is to push the HRO‑PS graduation project from ~8/10 to the highest realistically achievable score before submission and defense. **Do not just review — actively fix, refactor, test, and validate.** The **implementation is the source of truth**; when docs and code disagree, fix code if it is wrong, otherwise update docs. Never invent clinical validation or real‑hospital deployment claims — this is an honest prototype on synthetic data.

### Project context (verified)
HRO‑PS = Hospital Resource Optimization and Patient‑Surge Forecasting system. Python (3.11 deploy / 3.13 dev); FastAPI backend (`api.py`, routers: system, auth, messages, patient_flow, ml, upload, alerts, notifications; ~48 endpoints); Streamlit dashboard (`dashboard.py` + `*_sections.py`); SQLAlchemy + PostgreSQL (21 tenant‑scoped tables, `models.py`); bcrypt + JWT carrying `tenant_id` (`auth.py`). Forecasting: LSTM + ARIMAX + Hybrid (`train_lstm_ops72h.py`, `train_arimax_ops72h.py`, `build_hybrid_ops72h.py`, `forecast_*` , artifacts in `artifacts/`). Optimizer: real MILP via `scipy.optimize.milp` in `resource_optimizer.py`. Architectural keystone: **ForecastState** single source of truth (`forecast_state.py`), verified by `scripts/smoke_forecast_state.py`.

### Canonical numbers (must match everywhere — code, configs, dashboard, and the revised docs)
- Dataset: `clean_data(AutoRecovered).csv` = 17,520 hourly rows × 61 cols, 2024–2025 (Feb 29 2024 excluded), 5 departments (ER, ICU, General Ward, Surgery, Radiology); dept series 87,600 rows.
- LSTM: input seq 24h; LSTM(128)→Dropout0.2→LSTM(64)→Dropout0.2→Dense(32,ReLU)→Dense(1); Adam lr=0.001 + ReduceLROnPlateau; batch 64; best epoch 30.
- ARIMAX: SARIMAX(1,1,1)(0,0,0,0), Powell, maxiter=300, 7 exog (lag_1, lag_24, roll_mean_24, hour, is_weekend, appointments_count, occupied_beds), 0 convergence warnings.
- Hybrid: constrained 0.80 LSTM / 0.20 ARIMAX (validation‑RMSE selected); unconstrained optimum 0.95/0.05.
- Test metrics: LSTM MAE 7.65 / RMSE 9.58 / MAPE 5.52% (best individual); ARIMAX 15.63 / 19.33 / 12.33%; Hybrid 8.31 / 10.22 / 6.07% (deployed for robustness). `best_model = LSTM` in the manifest.
- 72h forecast: 72 overall + 360 dept rows; peak ≈218, avg ≈194; fallback_used=False.

### Ground rules
1. Before changing anything, run the test suite and record the baseline: `pytest -q`. Keep all currently‑passing tests green.
2. Make changes in small commits; after each, re‑run the relevant tests and `python -m compileall .`.
3. Do NOT retrain models on startup or commit huge artifacts; models are pre‑generated.
4. Keep a running CHANGELOG of every fix (file, issue, severity, fix, test result).

### Phase 1 — Full technical audit
Audit frontend, backend, DB, APIs, forecasting engine, hybrid logic, optimizer, auth/authorization, multi‑tenant isolation, dashboard, deployment config, config files, and environment variables. Produce a categorized issue list: bugs, design flaws, security vulns, inconsistencies, dead code, missing validations, logic errors, performance bottlenecks, doc mismatches — each with file:line and severity (Critical/High/Medium/Low).

### Phase 2 — Fix high‑impact issues (in this order)
- **Critical:** security vulns; any endpoint missing authentication or authorization; sensitive‑data exposure; secrets committed to the repo; dangerous configs (debug on, permissive CORS, default JWT secret).
- **High:** forecasting/config inconsistencies; data‑integrity issues; runtime risks; production blockers.
- **Medium:** error handling, logging, reliability, maintainability, UX.
Fix everything that can be safely fixed; for anything risky, leave a clearly‑marked TODO + explanation.

### Phase 3 — Architecture validation (critical for the defense)
- Verify **ForecastState** is the single source of truth: every dashboard tab and every forecast/optimization/evaluation API response must derive values from the same instance. Eliminate any duplicate/ad‑hoc state. Run `scripts/smoke_forecast_state.py`.
- Verify **multi‑tenant isolation rigorously**: the JWT carries `tenant_id`, but confirm that **every** DB query (every model with a `tenant_id` column) is filtered by the caller's tenant — search for queries that could leak across tenants. This is currently only "foundations"; harden it and add a regression test that proves tenant A cannot read tenant B's rows. (If full isolation isn't achievable, make the documentation/presentation say "tenant‑scoped foundations," not "full multi‑tenant SaaS.")

### Phase 4 — Hybrid forecasting verification
Reconcile `hybrid_config.json`, `artifacts/manifests/ops72h_training_summary.json`, `artifacts/metrics_72h/ops72h_model_metrics.csv`, the training/inference code, and the dashboard against the canonical numbers above. Fix any mismatch (e.g., a legacy `hybrid_config.json` weight that differs from 0.80/0.20, or any 0.6/0.4 / 0.7 / 168‑hour / 29,302‑row remnant). Confirm inference uses the same weights and features as training.

### Phase 5 — Security hardening
Authentication on every protected endpoint; authorization/RBAC checks (admin vs doctor vs nurse); session/JWT handling (expiry, secret from env not hard‑coded); input validation (Pydantic schemas on all bodies/queries); file‑upload validation (type/size/path); rate‑limiting where sensible; no secrets in code (move to env, add `.env.example`, ensure `.gitignore`). Add tests for auth failures (401/403).

### Phase 6 — Graduation‑committee simulation
For each, ensure the code + docs give a strong, evidence‑backed answer: Why this architecture? Why Hybrid instead of pure LSTM (robustness/fallback, even though LSTM is most accurate)? Why ARIMAX (interpretable baseline + exogenous regressors)? Why MILP (`scipy.optimize.milp`, integer allocation, priority‑weighted coverage, 5s greedy fallback)? Why ForecastState (cross‑view consistency, smoke‑tested)? Why tenant‑scoping? Strengthen any weak justification in code comments/docstrings and in the docs.

### Phase 7 — Production readiness
Assess readiness for defense, publication, and a hospital pilot. Add a `README` "How to run" (API, dashboard, seed, tests), a `requirements.txt`/lockfile check, `.env.example`, health checks, and a clean `docker-compose` if present. Close as many gaps as is safe.

### Phase 8 — Documentation synchronization
The revised thesis and paper live at:
- `D:\Hro new dashboard\HRO-PS_Thesis_REVISED.md`
- `D:\Hro new dashboard\HRO-PS_Paper_REVISED.md`
- `D:\Hro new dashboard\HRO-PS_Audit_and_Correction_Plan.md` (the change log/audit)
Verify the code matches these (they already use the canonical numbers). Then **compile them to the requested formats** with pandoc, embedding the diagrams in `D:\Hro new dashboard\thesis_figures\*.svg`:
```
pandoc "HRO-PS_Thesis_REVISED.md" -o "HRO-PS_Thesis_REVISED.docx" --toc --toc-depth=3 --number-sections
pandoc "HRO-PS_Paper_REVISED.md"  -o "HRO-PS_Paper_REVISED.docx"  --number-sections
```
(Convert the SVG diagrams to PNG first if pandoc lacks rsvg: `for f in thesis_figures/*.svg; do rsvg-convert "$f" -o "${f%.svg}.png"; done`, then reference the PNGs.)

**Poster & presentation (preserve existing themes):** apply the corrected content in `D:\Hro new dashboard\HRO-PS_Poster_Content.md` and `D:\Hro new dashboard\HRO-PS_Presentation_Content_and_Sync.md` onto the existing decks using python‑pptx — **do not restyle**; only replace outdated text/numbers/figures per the sync checklists in those files, and insert the diagrams + the screenshots you capture in Phase 9. Existing decks: poster `poster msa.pptx` (in the uploads folder) and presentation `Hospital Resource Optimization with AI Final Hro.pptx`. Save revised copies as `HRO-PS_Poster_FINAL.pptx` and `HRO-PS_Presentation_FINAL.pptx`.

### Phase 9 — Evidence collection
Run the API (`uvicorn api:app --port 8000`) and dashboard (`streamlit run dashboard.py`), log in with a demo account (tenant `demo-hospital`, e.g. `admin1` / `123456`), and capture clean screenshots of: Command Center, Forecast (LSTM/ARIMAX/Hybrid), Evaluation (MAE/RMSE/MAPE), Optimization (MILP allocation + solver status), Digital Twin, What‑if, Explainability, Department status, Shifts, Appointments, OR bookings, Notifications/Approvals/Audit, and the Swagger UI. Save them to `D:\Hro new dashboard\thesis_figures\screenshots\` with descriptive names so they can be dropped into the thesis/paper/poster/presentation figure slots.

### Deliverables (write these as markdown files in the repo)
1. `AUDIT_REPORT.md` — issues found, severity, fix applied, remaining risks.
2. `CODE_IMPROVEMENTS.md` — all refactors, bug fixes, security fixes, architecture fixes.
3. `DEFENSE_READINESS.md` — scores: overall /10, technical quality /10, research contribution /10, production readiness /10.
4. `TOP_RISKS.md` — anything still preventing a near‑perfect evaluation.
5. Final verdict: "If submitted today, what would prevent a near‑perfect grade?" with the concrete remaining actions.

Begin with Phase 1 (baseline `pytest`, then the audit) and report the issue list before making large changes.
