# Claude Code — HRO‑PS FINAL Submission Pass (Supervisor Compliance + Sync + Compile + Eval)

> Open the `hro-ps-ai` repo in VS Code. Allow access to `D:\Hro new dashboard` (docs/figures live there). Paste the block below.
> The thesis is the SINGLE SOURCE OF TRUTH; align everything to it and to the implemented code. After any code change run `pytest` and keep all tests green. Never overwrite original uploads — write NEW `*_FINAL` / `*_REVISED` files.

## PASTE THIS INTO CLAUDE CODE

Act as Senior Engineer + Academic Reviewer + Graduation Examiner. This is the FINAL pre‑submission pass. Work from `D:\Hro new dashboard\HRO-PS_Supervisor_Compliance_and_Changes.md` (the supervisor‑instruction compliance report) and the verified facts below. Do not fabricate clinical results or "% productivity" numbers.

**Verified facts (must match everywhere):** dataset 17,520 hourly rows × 61 cols, 2 years, 5 departments (ER, ICU, General Ward, Surgery, Radiology); LSTM 24‑h window, best individual model (test MAE 7.65 / RMSE 9.58 / MAPE 5.52%); ARIMAX SARIMAX(1,1,1)+7 exog (15.63/19.33/12.33%); Hybrid 0.80/0.20 deployed (8.31/10.22/6.07%), weight auto‑selected by constrained grid search; 72‑h horizon; MILP optimiser via `scipy.optimize.milp`; ForecastState single source of truth; FastAPI 48 endpoints + PostgreSQL + bcrypt/JWT; Streamlit dashboard; deployment = **Hugging Face Spaces** (GitHub‑linked); industrial reference = **Al‑Demerdash Hospital (Ain Shams)**, synthetic data only.

### Phase A — Supervisor‑compliance verification (code side)
For each 🟡 item in the compliance report, verify in code and fix if reasonable; report status + evidence:
- Alert‑routing table (alert type → recipient) exists & is configurable.
- Optimization labels clearly separate **"Needed"** vs **"Shortage"**.
- Explainability chart: **absolute values, percentage scale, readable**, negative half removed; document the `recent_trend` feature's formula.
- "Apply recommendation → re‑run → Red‑Amber‑Green re‑validates" loop works end‑to‑end.
- Forecast exposes both **24‑h and 24–72‑h** views; department‑specific output.
- Annotate each major action with **Purpose / Source(Trigger) / Destination(Outcome)** (code comments or a docstring table).

### Phase B — Code ↔ thesis 2‑way sync
Everything in the thesis exists in code, and everything in code is documented. Fix mismatches (update code if wrong, else the docs). Re‑run `pytest`, `compileall`, and `scripts/smoke_forecast_state.py`.

### Phase C — Compile the documents (NEW sections/figures included)
Convert SVGs in `D:\Hro new dashboard\thesis_figures\*.svg` to PNG, then:
```
pandoc "D:\Hro new dashboard\HRO-PS_Thesis_REVISED.md" -o "D:\Hro new dashboard\HRO-PS_Thesis_REVISED.docx" --toc --toc-depth=3 --number-sections --resource-path="D:\Hro new dashboard"
pandoc "D:\Hro new dashboard\HRO-PS_Paper_REVISED.md"  -o "D:\Hro new dashboard\HRO-PS_Paper_REVISED.docx"  --number-sections --resource-path="D:\Hro new dashboard"
```
Confirm the thesis includes the new **Commercial products (Table 2.2)** and **Testing & validation (Table 5.3)** sections, and the paper embeds the **5 dashboard screenshots** (file size should grow).

### Phase D — Presentation & poster (apply supervisor items; preserve theme)
Update `HRO-PS_Presentation_FINAL_v2.pptx` (29 slides) and `HRO-PS_Poster_FINAL_v2.pptx` via python‑pptx (iterate shapes AND tables AND notes):
- Add a **commercial‑products / competitive‑benchmark** slide; ensure **Why‑LSTM** and **Why‑ARIMAX** slides; **model‑evaluation** slide (MAE/RMSE/MAPE + curves); Gantt spanning **Grad‑1 + Grad‑2**; reframe opening around **Risk & Crisis Management**; replace any "Proposed"→"Implemented"; deployment = Hugging Face; ensure the model‑comparison table shows the canonical metrics (LSTM best, Hybrid deployed).
- Keep numbers identical to the thesis/paper.

### Phase E — Final evaluation (graduation‑committee simulation)
Score /10: Technical quality · AI component · Dashboard & UX · Documentation · Innovation · Academic quality · Presentation readiness. Give strengths, weaknesses, top risks before submission, and the single biggest blocker to a near‑perfect grade.

### Deliverables (write as markdown in the repo)
`AUDIT_REPORT.md` (refresh), `CODE_IMPROVEMENTS.md` (refresh), `SUPERVISOR_COMPLIANCE_CODE.md` (Phase A results), `DEFENSE_READINESS.md` (Phase E scores), `FINAL_FILES.md` (list every submission‑ready file with a one‑line description). Report what changed per file and any item you could not complete.

> Reminder: paraphrase the paper and run Turnitin + AI‑detection before journal submission (supervisor's hard requirement) — flag this; do not skip it.
