# Claude Code — HRO‑PS Final Re‑Eval, Finalize, Enhance & Report

> Open the `hro-ps-ai` repo in VS Code; allow access to `D:\Hro new dashboard`. Paste the block below.
> This is a near‑submission enhancement pass. **Do not destabilize the project.** Keep all 128 tests green (add more), never fabricate results, and treat the implemented code as the source of truth.

## HARD GUARDRAILS (read first)
1. **Canonical numbers are frozen unless you deliberately regenerate.** The thesis, paper, poster, and deck all cite: dataset 17,520×61 / 2 yrs / 5 depts; LSTM **7.65 / 9.58 / 5.52%** (best); ARIMAX **15.63 / 19.33 / 12.33%**; Hybrid 0.80/0.20 **8.31 / 10.22 / 6.07%** (deployed); 72‑h horizon; 48 endpoints; 128 tests. If any change alters these artifacts/metrics, **STOP, report it, and update ALL of `D:\Hro new dashboard\HRO-PS_Thesis_REVISED.md`, `HRO-PS_Paper_REVISED.md`, the poster and `HRO-PS_Presentation_FINAL_v3.pptx` consistently** — never leave docs out of sync. Prefer **additive** evaluation (new metrics alongside, not replacing).
2. **Never claim "removing ARIMAX raises RMSE."** Truth: LSTM alone (9.58) is more accurate than the Hybrid (10.22); the Hybrid is deployed for *robustness*. Fix any note/doc that still says otherwise (incl. the `HRO-PS_Presentation_FINAL_v3.pptx` speaker note containing "10.95"/"Removing ARIMAX").
3. **No fabricated data or results.** Synthetic data stays disclosed. Any new number must be computed and shown honestly.
4. After every change: `python -m pytest -q`, `python -m compileall .`, `python scripts/smoke_forecast_state.py` — all must pass before moving on.

## Phase 1 — Quick re‑evaluation
Re‑run the test suite, smoke test, and compileall; re‑score the project /10 on Technical, AI, Dashboard/UX, Documentation, Innovation, Academic, Production‑readiness. Report the score and the **delta vs the previous 8.6/10**. List concretely what is already complete vs what remains.

## Phase 2 — Finalize pending work & fill gaps
Implement and verify (each with a test or a documented check):
- **Deployment finalization (Hugging Face Spaces):** commit the LSTM `.keras` artifact (and any small artifacts needed for inference); add/verify `app.py`/entrypoint, pinned `requirements.txt`, `README`/Space card, secrets via env (no hard‑coded keys), and a smoke check that the app loads with pre‑generated artifacts (no training on startup).
- **Dual model‑path consistency:** make `/predict` and `/explain` use the same 72‑h models/feature set the dashboard uses (or, if infeasible, clearly document the difference in‑code and in the Explainability tab). Re‑run tests.
- **Security hardening:** input validation (Pydantic) on every request body/query; auth on every protected endpoint (verify, add tests for 401/403); rate‑limiting on auth/upload; file‑upload type/size checks; move JWT secret to env with a startup check; replace deprecated `datetime.utcnow()` (or switch `python‑jose` → `PyJWT`); add security headers/CORS review.
- **Multi‑tenant isolation:** confirm every query on a tenant‑scoped table is filtered by `tenant_id`; add a regression test proving tenant A cannot read tenant B's rows.
- **Model‑level evaluation (additive):** generate and save LSTM training/validation loss curves, residual diagnostics, a rolling‑origin (walk‑forward) backtest, and **per‑department** error metrics; add forecast **uncertainty/prediction bands** to the Forecast tab. Report the numbers honestly; if they don't change the headline test metrics, leave the canonical numbers intact and add these as supplementary evidence.
- **Out‑of‑distribution / production test harness (supervisor M9):** build a small harness that feeds production‑style scenarios (parameterised by a real hospital's bed/doctor counts, e.g. Cleopatra) plus edge cases (surge, holiday, COVID‑style crisis, mass‑casualty, infeasible demand) through the trained model and asserts the forecast→optimization linkage behaves; wire representative cases into the test suite.
- **Pending features:** finish or cleanly scope **per‑department forecasting** and **patient‑flow simulation (admission→discharge)**; if not fully implemented, leave a working stub + a clear "future work" note rather than a half‑broken feature.
- **CI:** add a GitHub Actions workflow running `pytest`, `compileall`, and the smoke test on push.
- **Docs:** add a top‑level `README.md` (how to run API + dashboard + tests + deploy), and a short Architecture/Decision note; keep the Deployment/Integration guide (required data, CSV/SQL/Excel, per‑hospital retraining) current.

## Phase 3 — Propose & implement WIDER, stronger updates
Produce a ranked **enhancement backlog** (Impact × Effort × Risk) — examples to consider, choose the strongest: per‑hospital config/onboarding wizard; richer optimizer (skill‑mix/shift constraints); confidence‑aware recommendations; anomaly/drift detection on incoming data; role‑aware notifications/escalation policies; a public Kaggle/hypothetical‑hospital validation track; SHAP/permutation importance for the LSTM; modularising the monolith files (`api.py`, `dashboard_sections.py`) into routers/modules; performance (caching, bulk DB inserts). 
**Implement the safe, high‑value, low‑risk items now (with tests).** For large/risky ones, scaffold + write a concrete plan instead of half‑implementing. Keep tests green throughout.

## Phase 4 — Re‑validate & sync
Re‑run `pytest` + `compileall` + smoke test. If any enhancement changed a canonical artifact/metric, recompile the affected `.docx`/`.pptx` and update every document so all numbers match (Guardrail 1). Commit with a clear conventional message.

## Report — write `ENHANCEMENT_REPORT.md`
Include: (1) new /10 scores + delta vs 8.6; (2) every change — file, what, why, test result; (3) the enhancement backlog with Done / Deferred (+ reason) per item; (4) any canonical‑number changes and the docs you re‑synced; (5) new/residual risks; (6) updated `FINAL_FILES.md`. End with a one‑paragraph verdict on submission/defense readiness.

> Reminder (manual, not your job): the team must still paraphrase the paper and run Turnitin + AI‑detection before journal submission. You may produce a paraphrased *draft variant* of the paper to speed that up, clearly labelled, but do not claim the check is done.
