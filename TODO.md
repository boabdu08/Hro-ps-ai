# TODO (Scenario + Dashboard Improvements)

## Phase 1 — Inspect existing scenario logic
- [x] Locate current What-if Scenarios table/module.
- [x] Identify where scenarios are loaded/displayed/used.
- [x] Inspect scenario CSV/JSON if present.

## Phase 2 — Expand scenario dataset
- [x] Review current scenario columns and quality.
- [x] Produce richer scenario dataset (40–80+ scenarios).
- [x] Add professional columns (severity/probability/impact/action).
- [x] Export updated scenarios to agreed path.

## Phase 3 — Improve operational UI tabs
- [ ] Inspect current implementations for: Shifts, Appointments, OR Bookings, Explainability, Evaluation.

## Phase 4 — Update evaluation/forecast/digital twin presentation
- [x] Ensure Evaluation tab loads real artifacts and avoids fake values (includes MAPE + ARIMAX limitation notes).
- [x] Ensure Forecast tab plots LSTM/ARIMAX/Hybrid and highlights best (incl. hybrid weights display path).
- [x] Ensure Digital Twin tab reads department-level artifacts and handles 216 rows.

## Phase 5 — Make operational demo data look realistic
- [ ] Replace small demo CSV exports for staff/shifts/appointments/or bookings with medium-hospital sized data.
- [ ] Keep required columns and keep dates synced to today.

## Phase 6 — Validation
- [x] Run `python -m compileall ...`.
- [x] Run `pytest -q`.
- [x] Smoke check dashboard tabs for missing/empty data handling.

## Phase 7 — Scenario UI integration (Simulation)
- [x] CSV-driven Simulation scenario analysis loads when `data/updated_exports/what_if_scenarios.csv` passes validation and preserves the 11 required UI columns, with fallback preserved.

