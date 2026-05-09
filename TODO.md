# TODO — HRO-PS Audit & Forecast Reliability Cleanup

## Step 0 — Repo audit baseline (completed)
- Inspected ops72h training/export/inference pipeline:
  - `forecast_inference_ops72h.py`, `train_lstm_ops72h.py`, `train_arimax_ops72h.py`, `build_hybrid_ops72h.py`, `generate_ops72h_outputs.py`
- Identified root “flat 72h forecast” mechanisms:
  - LSTM/ARIMAX inference keeps exogenous inputs effectively constant across the horizon.
- Identified cross-tab inconsistency root:
  - Command Center uses live 24h pipeline; Forecast/Digital Twin uses saved 72h artifacts.

## Step 1 — Fix artifact freshness validation + unified canonical ForecastState loader (IN PROGRESS)
- Create/strengthen canonical `ForecastState` artifact freshness + validation.
- Provide a shared loader/service used everywhere:
  - Centralize reading ops72h forecast artifacts + metrics.
  - Validate required cols, datetime parsing, horizon length, non-negative, non-NaN, non-flat flags.
  - Expose model/risk/resource/metrics metadata in a single object.

## Step 2 — Fix `forecast_inference_ops72h.py` horizon to be time-aware (APPROVED)
- Remove constant exog repetition across horizon.
- Roll forward future features by hour (hour/day_of_week/is_weekend/seasonality).
- Add safeguards to prevent suspiciously constant output unless justified + flagged.

## Step 3 — Robust Hybrid validation + ARIMAX fallback + manifest (APPROVED)
- Validate LSTM and ARIMAX outputs before combining.
- Detect invalid/flat output, NaNs, negatives, unrealistic spikes, stale timestamps.
- If ARIMAX invalid: reduce weight/exclude and apply safe baseline.
- Store reasons and status in manifest.

## Step 4 — Wire all tabs to unified canonical forecast state (APPROVED)
- Update dashboard sections to use canonical ForecastState for:
  - current patients / next-hour forecast
  - 24h curve + peak
  - 72h curve + peak + average
  - selected model/risk level
  - forecast timestamp + artifact status

## Step 5 — Smoke tests + audit report (required)
- Run smoke checks:
  - Command Center next-hour forecast equals Forecast tab next-hour forecast.
  - Digital Twin uses the same 72-hour series.
  - Optimization uses the same selected forecast value.
  - Evaluation reads metrics from the same model/artifact manifest.
  - No tab uses hardcoded placeholder forecast values.
- Create/update `PROJECT_AUDIT_AND_FIX_REPORT.md` documenting files changed, root cause, and validation results.

