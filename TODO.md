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
- [x] Inspect current implementations for: Shifts, Appointments, OR Bookings, Explainability, Evaluation.

## Phase 3 note (operational demo data)
- Shifts/Appointments/OR Bookings are now backed by realistic operational demo data exports (Phase 5), while Explainability/Evaluation were already inspected/improved in Phase 4.


## Phase 4 — Update evaluation/forecast/digital twin presentation
- [x] Ensure Evaluation tab loads real artifacts and avoids fake values (includes MAPE + ARIMAX limitation notes).
- [x] Ensure Forecast tab plots LSTM/ARIMAX/Hybrid and highlights best (incl. hybrid weights display path).
- [x] Ensure Digital Twin tab reads department-level artifacts and handles 216 rows.

## Phase 5 — Make operational demo data look realistic
- [x] Replace small demo CSV exports for staff/shifts/appointments/or bookings with medium-hospital sized data.
- [x] Keep required columns and keep dates synced to today.

### Phase 5 risks / notes
- Staff seed count may differ from exported `staff_master_data.csv` because export rebuilds staff master from scheduled staff and dedupes by `staff_id`.
- Appointment/OR doctor linkage is name-based in CSV exports (not a staff_id foreign key).
- OR bookings = 9 is acceptable for the demo, but can be expanded later if a denser OR schedule is desired.


## Phase 6 — Validation
- [x] Run `python -m compileall ...`.
- [x] Run `pytest -q`.
- [x] Smoke check dashboard tabs for missing/empty data handling.

## Phase 7 — Scenario UI integration (Simulation)
- [x] CSV-driven Simulation scenario analysis loads when `data/updated_exports/what_if_scenarios.csv` passes validation and preserves the 11 required UI columns, with fallback preserved.

