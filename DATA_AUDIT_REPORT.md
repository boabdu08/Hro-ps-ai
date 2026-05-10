# HRO-PS Data Audit Report

Generated for the graduation-demo hardening pass.

## Scope

Reviewed project data and artifact files including CSV, JSON, NPZ, PKL, Keras/H5 model artifacts, forecast outputs, metrics, manifests, seed inputs, and updated operational exports.

Reference patterns considered for the next data-enrichment phase:

- MIMIC-style separation of admissions, transfers, patients, and hospital events.
- NHS/HES-style distinction between admissions, outpatient appointments, and bed occupancy.
- WHO/OECD bed-capacity and occupancy indicators.
- Hospital operations norms: weekday pressure, winter flu season peaks, morning arrivals/admissions, evening discharges, department-specific loads, and non-uniform staffing/OR utilization.

Sources reviewed during planning:

- WHO hospital beds indicator.
- WHO Europe bed occupancy indicator.
- NHS England Hospital Episode Statistics and bed availability/occupancy descriptions.

## Files Reviewed

| File | Rows | Columns / Keys | Parser Status |
|---|---:|---|---|
| `data/updated_exports/staff_master_data.csv` | 112 | `staff_id`, `staff_name`, `role`, `department`, `specialty`, `qualification_level`, `available_for_shift`, `max_hours_per_week`, `notes` | OK |
| `data/updated_exports/staff_schedule.csv` | 240 | `staff_id`, `staff_name`, `role`, `department`, `shift_date`, `shift_type`, `shift_start_time`, `shift_end_time`, `status`, `notes` | OK |
| `data/updated_exports/appointments_updated.csv` | 55 | `appointment_id`, `department`, `doctor`, `date`, `time_slot`, `patient_count`, `status` | OK |
| `data/updated_exports/or_bookings.csv` | 9 | `booking_id`, `room`, `doctor`, `department`, `booking_date`, `time_slot`, `procedure`, `status`, `notes` | OK |
| `data/updated_exports/patient_tracking.csv` | 4 | 13 patient-tracking columns | OK |
| `data/updated_exports/department_status_updated.csv` | 5 | 13 department capacity/status columns | OK |
| `data/updated_exports/patient_flow_hourly_updated.csv` | 29,302 | 20 hourly operational columns | OK |
| `data/updated_exports/what_if_scenarios.csv` | 50 | 21 scenario columns | OK |
| `data/updated_exports/export_summary.txt` | 54 lines | text summary | OK |
| `artifacts/forecast_outputs/ops72h_overall_forecast.csv` | 72 | `datetime`, `lstm_pred`, `arimax_pred`, `hybrid_pred`, `lstm_valid`, `arimax_valid`, `validation_note` | OK |
| `artifacts/forecast_outputs/ops72h_department_forecast.csv` | 216 | `datetime`, `department`, `hybrid_pred` | OK |
| `artifacts/metrics_72h/ops72h_model_metrics.csv` | 3 | `Model`, `MAE`, `RMSE`, `MAPE` | OK |
| `artifacts/metrics_72h/lstm_ops72h_metrics.json` | n/a | `model`, `val`, `test`, `feature_cols`, `sequence_length`, `model_path` | OK |
| `artifacts/metrics_72h/arimax_ops72h_metrics.json` | n/a | `model`, `val`, `test`, `exog_cols` | OK |
| `artifacts/metrics_72h/hybrid_ops72h_metrics.json` | n/a | `lstm_weight`, `arimax_weight`, `selection_metric`, `validation`, `test`, `alignment_note` | OK |
| `artifacts/manifests/ops72h_training_summary.json` | n/a | forecast paths, metrics path, best model, weights, hybrid config | OK |
| `hospital_forecast_model.keras` | n/a | binary model artifact | Exists |
| `arimax_model.pkl` | n/a | binary model artifact | Exists |
| `x_scaler.pkl` | n/a | binary scaler artifact | Exists |
| `y_scaler.pkl` | n/a | binary scaler artifact | Exists |
| `hybrid_config.json` | n/a | legacy hybrid config | OK |

Additional legacy/root CSV/JSON/NPZ artifacts were located, including `clean_data.csv`, `appointments.csv`, `or_bookings.csv`, `shifts.csv`, `users.csv`, root-level model metrics, legacy forecast outputs, and sequence arrays. These are retained for backward compatibility but the deployment-facing 72h pipeline should use the canonical `data/updated_exports/` and `artifacts/` layout.

## Quality Checks

### NaN / Null Values

- No parser-blocking NaN issues found in required deployment files.
- Nullable operational fields such as patient discharge time may be empty by design for active patients.

### Negative Values Where Impossible

- `data/updated_exports/what_if_scenarios.csv`
  - Issue: one negative `arrival_increase_percent`.
  - Interpretation: may represent reduced arrivals, but the column name says "increase", so it is semantically confusing.
  - Action in Phase 2: normalize scenario fields and make reductions explicit via capacity/availability change fields or scenario narrative.

### Duplicate IDs

- No duplicate IDs found in required checked columns:
  - `staff_id`
  - `appointment_id`
  - `booking_id`
  - `patient_id`
  - `scenario_id`

### Unrealistic Extreme Spikes

- Current deployment forecast artifact has no invalid 72h spike after the previous fallback fix:
  - overall hybrid min: 70.5
  - overall hybrid max: 116.5
  - range: 46.0
- Historical patient-flow exports still need realism normalization because the timeline has sparse zero sections and isolated live-demo rows.

### Decimal Numbers Where Integers Are Expected

- Forecast values may be decimal because model outputs are continuous.
- UI should round patient counts for display.
- Phase 2 should keep raw model-ready numeric values but produce integer operational counts for arrivals, admissions, discharges, beds, doctors, nurses, appointments, and OR bookings.

### Department Name Consistency

Current canonical department set in runtime optimizer:

- `ER`
- `ICU`
- `General Ward`
- `Surgery`
- `Radiology`

Issues:

- Some updated exports and charts do not cover all departments equally.
- Current 72h department forecast has only `ER`, `General Ward`, and `ICU`.
- Phase 2 must regenerate department-level data so Surgery and Radiology are represented in forecasts and pressure charts.

### Date Synchronization

Issues:

- Current updated operational exports mix a long historical hourly file with live-demo synchronized files.
- Phase 2 requirement is stricter: all time-series data should span `2024-01-01 00:00` to `2025-12-31 23:00` with 17,520 hourly rows.

### Foreign Key / Relationship Checks

| Relationship | Result | Issue |
|---|---|---|
| Every `staff_schedule.staff_id` exists in `staff_master.staff_id` | PASS | None found |
| Every appointment doctor exists in staff master doctors | FAIL | `Dr. Fatima Yasin`, `Dr. Noor Yasin`, `Dr. Youssef Abdullah` missing |
| Every OR booking doctor/surgeon exists in staff master doctors | FAIL | `Dr. Noor Yasin` missing |

Phase 2 must add these doctors to staff master or reassign records to existing doctor staff.

### Uniform / Fake-Looking Distributions

Issues:

- Appointment distribution needs department-specific non-uniform loads.
- OR booking count is too small and visually weak; all-room charts can become "all bars = 1".
- Department forecast currently excludes some departments.

### Fallback / Hardcoded Values

Current model manifest reports:

- LSTM output invalid and replaced by fallback.
- ARIMAX output near-flat and replaced by fallback.
- Hybrid artifact is readable and dynamic, but it is currently fallback-driven.

Phase 3 must retrain on enriched data and produce genuine LSTM/ARIMAX/Hybrid outputs with weights between 0.2 and 0.8 for each model.

## Row-Level Issues Found

Exact row numbers are based on CSV data row index after the header, starting at 2 for the first data row.

| File | Row(s) | Issue |
|---|---:|---|
| `data/updated_exports/what_if_scenarios.csv` | one row identified by numeric scan | Negative `arrival_increase_percent` despite "increase" label |
| `data/updated_exports/appointments_updated.csv` | rows containing listed doctors | Doctor not present in staff master: `Dr. Fatima Yasin`, `Dr. Noor Yasin`, `Dr. Youssef Abdullah` |
| `data/updated_exports/or_bookings.csv` | rows containing listed doctor | Doctor not present in staff master: `Dr. Noor Yasin` |

## Required Fixes For Next Phases

1. Generate a clean 17,520-row hourly patient-flow dataset for 2024-2025.
2. Add required patient-flow columns:
   - `hour`, `day_of_week`, `is_weekend`, `month`, `season`
   - `is_holiday`, `event_flag`, `shift_period`
   - `arrivals`, `admissions`, `discharges`, `waiting_patients`
   - `avg_wait_time_minutes`, `occupancy_rate`
   - `available_beds`, `available_doctors`, `available_nurses`
   - `appointments_count`, `or_bookings_count`
   - `department_pressure_score`, `predicted_patients_next_hour`
3. Regenerate department hourly data for all canonical departments.
4. Expand staff master with `years_experience` and `overtime_hours`.
5. Ensure all schedule staff IDs exist in staff master.
6. Ensure all appointment/OR doctors exist in staff master.
7. Increase OR bookings and include:
   - `procedure_type`
   - `procedure_duration_minutes`
   - `post_op_bed_required`
8. Ensure all departments and all shift types are represented.
9. Regenerate what-if scenarios with complete summaries, affected departments, shortages, and recommended actions.
10. Retrain models and remove fallback-driven hybrid artifact status.

## Audit Status

Current frozen data is usable for a demo, but it does not satisfy the stricter realism and retraining requirements. Phase 2 should replace the sparse/short operational exports with a consistent, reproducible two-year demo dataset.

---

## Post-Fix Data Audit Update

Generated after the data expansion and retraining pass.

Correction: the primary manually checked dataset is `clean_data(AutoRecovered).csv`. A previous expansion had updated `data/updated_exports/*` and `clean_data.csv`, but the exact AutoRecovered file still had 8,760 rows. This pass expanded the exact file directly.

### Main Dataset Correction

| Field | Before | After |
|---|---:|---:|
| File | `clean_data(AutoRecovered).csv` | `clean_data(AutoRecovered).csv` |
| Rows | 8,760 | 17,520 |
| Columns | 23 | 61 |
| Date range | `2025-01-01 00:00:00` to `2025-12-31 23:00:00` | `2024-01-01 00:00:00` to `2025-12-31 23:00:00` |
| Duplicate timestamps | 0 | 0 |
| Missing values | not final-validated | 0 |
| Negative numeric values | not final-validated | 0 |

Preserved original columns:

`datetime`, `patients`, `day_of_week`, `day_of_week_name`, `month`, `is_weekend`, `holiday`, `holiday_name`, `weather`, `weather_type`, `weather_severity`, `hospital capacity`, `is_capped`, `is_emergency`, `emergency_spike`, `is_outbreak`, `outbreak_intensity`, `is_staff_shortage`, `staff_shortage_impact`, `scenario_primary`, `scenario_code`, `y_patients_t_plus_1`, `y_patients_t_plus_24`.

Added operational/modeling columns:

`hour`, `season`, `week_of_year`, `shift_period`, `is_holiday`, `is_holiday_or_event`, `event_flag`, `arrivals`, `admissions`, `discharges`, `transfers`, `emergency_arrivals`, `elective_arrivals`, `waiting_patients`, `avg_wait_time_minutes`, `occupancy_rate`, `bed_occupancy`, `occupied_beds`, `available_beds`, `available_doctors`, `available_nurses`, `staff_on_duty`, `doctor_shortage`, `nurse_shortage`, `bed_shortage`, `appointments_count`, `or_bookings_count`, `delayed_discharge_count`, `department_pressure_score`, `er_pressure_score`, `doctors_available`, `nurses_available`, `lag_1`, `lag_24`, `roll_mean_3`, `roll_mean_6`, `roll_mean_24`, `predicted_patients_next_hour`.

### Files Regenerated / Revalidated

| File | Rows | Columns | Status |
|---|---:|---:|---|
| `data/updated_exports/patient_flow_hourly_updated.csv` | 17,520 | 33 | PASS |
| `data/updated_exports/ops_hourly_overall.csv` | 17,520 | 33 | PASS |
| `data/updated_exports/updated_hospital_data.csv` | 17,520 | 33 | PASS |
| `data/updated_exports/ops_hourly_by_department.csv` | 87,600 | 3 | PASS |
| `data/updated_exports/staff_master_data.csv` | 148 | 11 | PASS |
| `data/updated_exports/staff_schedule.csv` | 1,470 | 11 | PASS |
| `data/updated_exports/appointments_updated.csv` | 153 | 7 | PASS |
| `data/updated_exports/or_bookings.csv` | 150 | 13 | PASS |
| `data/updated_exports/patient_tracking.csv` | 120 | 13 | PASS |
| `data/updated_exports/department_status_updated.csv` | 5 | 13 | PASS |
| `data/updated_exports/what_if_scenarios.csv` | 50 | 26 | PASS |
| `artifacts/forecast_outputs/ops72h_overall_forecast.csv` | 72 | 7 | PASS |
| `artifacts/forecast_outputs/ops72h_department_forecast.csv` | 360 | 3 | PASS |
| `artifacts/metrics_72h/ops72h_model_metrics.csv` | 3 | 4 | PASS |

### Patient Flow Columns Confirmed

The expanded patient-flow file now includes the required operational and modeling fields:

`hour`, `day_of_week`, `is_weekend`, `month`, `season`, `is_holiday`, `event_flag`, `shift_period`, `arrivals`, `admissions`, `discharges`, `waiting_patients`, `avg_wait_time_minutes`, `occupancy_rate`, `available_beds`, `available_doctors`, `available_nurses`, `appointments_count`, `or_bookings_count`, `department_pressure_score`, `predicted_patients_next_hour`.

Additional model features retained: `patients`, `week_number`, `holiday`, `occupied_beds`, `doctors_available`, `nurses_available`, `lag_1`, `lag_24`, `roll_mean_3`, `roll_mean_6`, `roll_mean_24`.

### Relationship Checks After Fix

| Relationship | Result |
|---|---|
| Every `staff_schedule.staff_id` exists in `staff_master.staff_id` | PASS |
| Every appointment doctor exists in staff master doctors | PASS |
| Every OR booking doctor exists in staff master doctors | PASS |
| All canonical departments appear in department time series | PASS |
| All canonical departments appear in staff schedule | PASS |
| Morning, Evening, Night, and Emergency Backup shifts are represented | PASS |

### Realism Checks After Fix

- Patient-flow span: 17,520 hourly rows for a two-year demo series. Leap day is intentionally excluded so the row count matches the requested fixed 17,520-hour training horizon.
- Year two is not a copy of year one; it includes volume drift and seasonal variation.
- Department-level rows: 5 departments x 17,520 hours = 87,600 rows.
- Appointment distribution is non-uniform by design: ER highest, then General Ward, ICU/Surgery, then Radiology.
- OR bookings now include multiple bookings per room, `procedure_type`, `procedure_duration_minutes`, and `post_op_bed_required`.
- What-if scenarios now include affected departments, shortage gaps, expected response, recommended action, priority level, escalation flag, and summary.

### Forecast Artifact Checks After Fix

- Overall 72-hour forecast rows: 72.
- Department forecast rows: 360.
- Departments represented: ER, General Ward, ICU, Surgery, Radiology.
- LSTM status: valid.
- ARIMAX status: valid, with training convergence warnings documented in `MODEL_TRAINING_SUMMARY.md`.
- Hybrid status: valid.
- Hybrid weights: LSTM `0.8`, ARIMAX `0.2`.
- Fallback used in current manifest: `False`.
- ForecastState smoke result: PASSED.

### Remaining Honest Limitations

- The dataset is realistic synthetic/demo data, not real hospital data.
- The two-year row count requirement conflicts with the literal leap-year-inclusive 2024-2025 range; the generator excludes February 29, 2024 to satisfy the exact 17,520-row requirement.
- ARIMAX may still warn during fitting, but output validation prevents invalid or flat forecasts from being promoted silently.
