# PROJECT_AUDIT_AND_FIX_REPORT.md

## Summary
HRO-PS now has the live dashboard/API forecast path wired through the canonical `ForecastState` contract. Command Center, Forecast, Digital Twin, Optimization, Evaluation, and forecast/evaluation/artifact API responses use the same canonical state values or explicit helper contracts derived from that state.

## Files Inspected
- `README.md`
- `TODO.md`
- `DEPLOYMENT_GUIDE.md`
- `render.yaml`
- `dashboard.py`
- `dashboard_sections.py`
- `api.py`
- `api_client.py`
- `forecast_state.py`
- `forecast_inference_ops72h.py`
- `generate_ops72h_outputs.py`
- `evaluation_service.py`
- `resource_optimizer.py`
- `scripts/smoke_forecast_state.py`
- `tests/test_imports.py`
- `tests/test_health.py`

## Files Changed
- `forecast_state.py`
- `dashboard_sections.py`
- `api.py`
- `forecast_inference_ops72h.py`
- `scripts/smoke_forecast_state.py`
- `tests/test_forecast_state_wiring.py`
- `README.md`
- `DEPLOYMENT_GUIDE.md`
- `artifacts/forecast_outputs/ops72h_overall_forecast.csv`
- `artifacts/forecast_outputs/ops72h_department_forecast.csv`
- `artifacts/metrics_72h/ops72h_model_metrics.csv`
- `artifacts/manifests/ops72h_training_summary.json`

## Root Causes Found
- Forecast artifacts were technically non-constant but clinically implausible: 71 zero forecast hours followed by one spike. The cause was the fallback repeating a sparse recent 72-hour window after model validation failed.
- ARIMAX exogenous future values were effectively repeated from the last row, making flat ARIMAX behavior likely.
- Evaluation API/dashboard paths still had separate metric-loading calls even though `ForecastState` already carried canonical metrics.
- There was no automated proof that dashboard tab source values were derived from the same `ForecastState`.
- Deployment docs still referenced the legacy consolidated metrics directory instead of the canonical `metrics_72h` and `manifests` layout.

## Forecasting Fixes
- `forecast_inference_ops72h.py`
  - Replaced the sparse-window fallback with a time-aware baseline from comparable historical non-zero hours.
  - Added stricter flat-output detection using a relative dynamic-range threshold.
  - Updated LSTM roll-forward to advance calendar/hour features instead of repeating the last exogenous row.
  - Updated ARIMAX future exogenous generation for known calendar features.
  - Invalid LSTM/ARIMAX outputs are now replaced with a labeled seasonal-naive fallback and captured in the manifest.
- Regenerated ops72h forecast artifacts with the safer fallback.
  - Overall 72h forecast rows: 72.
  - Overall hybrid range: 70.5 to 116.5 patients.
  - Overall hybrid average: 94.47 patients.
  - Department forecast rows: 216 total, 72 rows per department.
  - No negative, NaN, or zero-filled forecast horizon.

## Artifact Validation Fixes
- `forecast_state.py`
  - Requires exactly 72 overall forecast rows.
  - Requires exactly 72 rows per department.
  - Keeps flatness as a quality flag instead of making otherwise readable artifacts disappear.
  - Reads LSTM/ARIMAX validity and fallback reasons from the manifest weights block.
  - Serializes forecast frames with JSON-safe datetime strings for API responses.

## Dashboard Consistency Fixes
- `dashboard_sections.py`
  - Added testable source helpers:
    - `command_center_source_values`
    - `forecast_tab_source_values`
    - `digital_twin_source_series`
    - `optimization_source_input`
    - `evaluation_source_metrics`
  - Command Center KPIs now read through `command_center_source_values(state)`.
  - Forecast tab next-hour, 72h peak, 72h average, 72h series, and metrics read through ForecastState helpers.
  - Digital Twin all-hospital series reads from `ForecastState.forecast_72h_values`.
  - Optimization displays and uses the canonical ForecastState next-hour input.
  - Evaluation test metrics read from `ForecastState.metrics`.

## API Fixes
- `api.py`
  - `/predict` already returns `forecast_state`; retained that canonical response path.
  - `/forecast_state`, `/forecast`, `/status`, and `/artifacts/manifest` use `ForecastState`.
  - `/evaluate` and `/evaluation` now return metrics from the same serialized `ForecastState` payload instead of separately loading old metric tables.
  - `/optimize_resources/{predicted_patients}` tags results with `source=ForecastState`, stores the canonical optimization input, and returns the serialized forecast state used for the run.

## Old Paths Removed
- Deployment docs now point consolidated metrics/manifest paths to:
  - `artifacts/metrics_72h/ops72h_model_metrics.csv`
  - `artifacts/manifests/ops72h_training_summary.json`
- Search check for old non-artifact paths:
  - Command: `rg --pcre2 -n "(?<!artifacts/)forecast_outputs/|(?<!artifacts/)metrics/|forecast_outputs\\|metrics\\" -g "*.py" -g "*.md" -g "*.yaml" -g "*.txt"`
  - Result: no matches.

## Smoke Test Output
- `python generate_ops72h_outputs.py`
  - Saved overall forecast: `artifacts/forecast_outputs/ops72h_overall_forecast.csv`
  - Saved department forecast: `artifacts/forecast_outputs/ops72h_department_forecast.csv`
  - Saved metrics: `artifacts/metrics_72h/ops72h_model_metrics.csv`
  - Saved manifest: `artifacts/manifests/ops72h_training_summary.json`
  - Best model: ARIMAX
- `python scripts/smoke_forecast_state.py`
  - ForecastState ready: True.
  - 72h rows: 72.
  - 72h peak: 116.5.
  - 72h average: 94.47.
  - Constant detected: False.
  - Command Center source: ForecastState.
  - Forecast tab source: ForecastState.
  - Command Center next-hour equals Forecast tab next-hour: 101.0 == 101.0.
  - Digital Twin series count: 72.
  - Optimization input: 101.0.
  - Evaluation metrics rows: 3.
  - Smoke validation: PASSED.
- `python -m pytest -q`
  - Result: 4 passed.
  - Warnings: FastAPI `on_event` deprecation and pytest cache permission warnings for `.pytest_cache`.
- `python -m compileall dashboard.py dashboard_sections.py staff_sections.py api.py api_client.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py forecast_state.py forecast_inference_ops72h.py generate_ops72h_outputs.py -q`
  - Result: passed.
- Direct API canonical smoke:
  - `get_forecast_endpoint(_token={})` returned `source=ForecastState` and 72 forecast values.
  - `get_evaluation(_token={})` returned `source=ForecastState` and 3 metric rows.
  - Result: PASSED.

## Remaining Honest Limitations
- This is still a graduation-demo prototype using realistic demo/synthetic data, not production hospital software.
- The latest regenerated 72h output uses the safe historical fallback because this artifact run detected invalid LSTM output and near-flat ARIMAX output. This is now explicit in the manifest and `ForecastState.model_status`.
- The fallback is realistic and time-aware, but it is not a substitute for clinically validated retraining on real hospital operational feeds.
- Full live dashboard rendering still depends on API authentication, seeded Postgres data, and the local/cloud runtime environment.

## Commands To Run
API:
```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

Dashboard:
```powershell
streamlit run dashboard.py
```

Regenerate 72h forecast artifacts:
```powershell
python generate_ops72h_outputs.py
```

Smoke tests:
```powershell
python scripts\smoke_forecast_state.py
python -m pytest -q
python -m compileall dashboard.py dashboard_sections.py staff_sections.py api.py api_client.py ops_live.py resource_optimizer.py operational_data_workflow.py evaluation_service.py forecast_state.py forecast_inference_ops72h.py generate_ops72h_outputs.py -q
```

## Deployment Readiness Notes
- Canonical runtime layout is now:
  - `data/updated_exports/`
  - `artifacts/forecast_outputs/`
  - `artifacts/metrics_72h/`
  - `artifacts/models_72h/`
  - `artifacts/manifests/`
- Do not present this as production hospital SaaS. It is deployment-ready for a graduation demo after verifying the deployed environment has the same artifacts, dependencies, database seed, and secrets.
