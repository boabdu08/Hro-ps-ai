# HRO-PS — Architecture & Decision Note

One page. The full README has run instructions; this records *why* the system
is shaped the way it is.

## Data flow

```
CSV (17,520 hourly rows, synthetic, 2024–2025, 5 departments)
  → feature engineering (21-feature ops schema / 26-feature root schema)
  → offline training: LSTM + SARIMAX(1,1,1)   [never at runtime]
  → pre-generated artifacts (models, scalers, 72-h forecast CSVs, metrics)
  → ForecastState (frozen dataclass — single canonical source of truth)
  → FastAPI (48 endpoints) ──► Streamlit dashboard (13 tabs, 3 roles)
                └─► scipy.optimize.milp resource optimizer → Approvals workflow
```

## Key decisions (and the trade-off each one accepts)

| # | Decision | Why | Trade-off accepted |
|---|----------|-----|--------------------|
| 1 | **ForecastState frozen dataclass** as the only forecast source | Makes cross-tab inconsistency architecturally impossible; smoke-tested every CI run | All tabs share staleness: a bad artifact breaks everything visibly (preferred over silent divergence) |
| 2 | **Pre-generated artifacts, no training on startup** | Deterministic demo, fast cold start, works on free-tier hosts | Forecasts are static between regenerations; live retraining is future work |
| 3 | **Hybrid LSTM 0.80 / ARIMAX 0.20 deployed even though LSTM alone tests better** (RMSE 9.58 vs 10.22) | ARIMAX is a linear anchor that damps LSTM volatility on out-of-distribution surges; constrained grid search (α ∈ [0.20, 0.80]) picked the floor | ~0.64 RMSE accuracy cost on the test set — disclosed everywhere, never hidden |
| 4 | **Two model paths** — root 26-feature model for live `/predict`+`/explain`, ops 21-feature pipeline for 72-h dashboard forecasts | The paths were trained on different schemas; unifying requires retraining near submission (high risk, zero demo value) | Documented difference (forecast_inference.py, Explainability tab); both share the 0.80/0.20 weights |
| 5 | **Row-based multi-tenancy** (tenant_id FK on all 21 tables) | Standard SaaS pattern; one DB, simple ops | Isolation depends on query discipline — enforced by regression tests (tests/test_tenant_isolation.py) |
| 6 | **MILP via scipy.optimize.milp + deterministic greedy fallback** | No external solver install; hard constraints (capacity, ratios); <5 s solve | Less expressive than OR-Tools CP-SAT (skill-mix/shift constraints are backlog) |
| 7 | **In-process rate limiter** (rate_limit.py), not Redis | Single-instance demo deployment; zero new infrastructure | Per-process budgets — multi-replica production needs a shared store (documented in-module) |
| 8 | **Empirical residual-quantile uncertainty bands** (not parametric) | Honest about the actual error distribution incl. asymmetry; no distributional assumption | One-step-ahead residuals understate hour-72 uncertainty (disclosed in the UI caption) |
| 9 | **PSI + rolling-MAE drift detection** (drift_detection.py) | Explainable to a jury in one sentence; no labels needed for input drift | Simpler than KS/MMD tests; thresholds are convention (0.10/0.25), not learned |
| 10 | **Patient-flow simulation is an operational queueing approximation** (patient_flow_sim.py: log-normal LOS, hourly discrete steps) | Turns arrival forecasts into census/occupancy projections for capacity planning | Not a clinical model — labelled as such wherever surfaced |

## Quality gates

Every change must pass, in order:
`python -m pytest -q` (255 tests) → `python -m compileall . -q` →
`python scripts/smoke_forecast_state.py` (cross-tab canonical wiring).
CI (.github/workflows/ci.yml) runs all three plus lint and a Docker build.

## Canonical numbers (frozen — regenerate artifacts before changing ANY of these)

Dataset 17,520×61 (2 yrs, 5 depts) · LSTM test 7.65 / 9.58 / 5.52% (best) ·
ARIMAX 15.63 / 19.33 / 12.33% · Hybrid 0.80/0.20 → 8.31 / 10.22 / 6.07%
(deployed) · 72-h horizon · 48 endpoints · 21 tables · 13 tabs · 255 tests.
