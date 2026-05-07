# HRO-PS Phase 0 Project Trace

This short internal report documents the architecture traced before export or
training work was started.

## Main entry points and dashboard flow

- `dashboard.py` is the Streamlit entry point. It handles login, theme setup,
  role-based navigation, and dispatches to dashboard sections.
- `dashboard_sections.py` renders Command Center, Forecast, Optimization,
  Operations Center, Simulation, Digital Twin, Department Status, Evaluation,
  and Explainability.
- `staff_sections.py` renders Shifts, Appointments, and OR Bookings directly
  from DB-backed operational tables with CSV bootstrapping intentionally
  disabled for runtime.

## Data and live-operations flow

Data files / database → preprocessing / live operational state → forecasting →
optimization → dashboard tabs → department status / digital twin / evaluation.

- Legacy seed/data files include `clean_data.csv`, `clean_data_1y_labeled.csv`,
  `hospital_patient_flow.csv`, `shifts.csv`, `appointments.csv`, and
  `or_bookings.csv`.
- DB models are defined in `models.py`, including `PatientFlow`, `Appointment`,
  `ORBooking`, `StaffShift`, `StaffMaster`, `StaffSchedule`, and
  `PatientTracking`.
- `db_migrations.py` creates/extends operational tables idempotently because the
  project does not use Alembic yet.
- `ops_live.py` centralizes today/live date logic, shift windows, appointment
  status normalization, and duplicate removal.
- `scheduler.py` can keep live demo operational rows aligned with today/current
  hour and seed minimal patient tracking when DB tables are empty.
- `resource_optimizer.py` consumes the next-hour forecast plus live operational
  state to calculate department allocations, shortages, recommendations, and
  action plans.

## Forecasting/model flow

- The legacy/canonical 24-hour runtime stack is used by Command Center and must
  remain unchanged.
- A separate ops-aware 72-hour stack exists:
  - `forecasting_pipeline.py` builds hourly overall and department-level data.
  - `train_lstm_ops72h.py` trains/saves the LSTM artifacts.
  - `train_arimax_ops72h.py` trains/saves ARIMAX artifacts.
  - `build_hybrid_ops72h.py` selects the best weighted hybrid ensemble.
  - `forecast_inference_ops72h.py` loads the 72-hour artifacts and returns
    overall plus department-level forecasts.

## Phase 0 health findings

- Import/health tests passed with `python -m pytest tests/test_imports.py
  tests/test_health.py -q`.
- Legacy CSV files had no full-row duplicates in the Phase 0 audit.
- `shifts.csv` lacks `shift_start_time` and `shift_end_time`; runtime fills
  these via `ops_live.shift_times_for_type()`.
- `hospital_patient_flow.csv` contains old `Unnamed:*` columns; those are not
  used for the new operational exports.
- API imports `forecast_ops72h`, but the exposed API/dashboard route for the new
  72-hour ops forecast still needs final integration after export/training.

## Cleanup/polishing performed

- Added `operational_data_workflow.py` as a focused, additive export/verification
  workflow. It does not rewrite or replace existing dashboard/runtime code.
- The new workflow documents the current system flow in code comments and uses
  existing helpers from `ops_live.py` for live dates, shift windows, status
  normalization, and safe deduplication.
