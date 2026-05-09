# PROJECT_AUDIT_AND_FIX_REPORT.md

## Summary
This report tracks the root cause of cross-tab forecast inconsistencies and documents the canonical forecast-state fix implementation.

## Current Status
Pending implementation of Step 1 (artifact freshness validation + unified canonical ForecastState loader) and wiring.

## Root Cause (from repo audit)
- Command Center and live Operations pages were using the **live 24-hour prediction path**.
- Forecast and Digital Twin pages were using **saved 72-hour forecast artifacts** from CSV exports.
- This caused cross-tab value drift (next-hour forecast, peaks, and selected/best model) even when the UI labels implied they were comparable.

## Files Affected (planned)
- `forecast_state.py`
- `dashboard_sections.py`
- `api.py`
- `api_client.py`
- `evaluation_service.py` (if API/state integration requires it)
- Possibly other UI sections that compute peaks/next-hour independently.

## Validation Plan (smoke checks)
After wiring, the following must be true:
1. Command Center next-hour forecast equals Forecast tab next-hour forecast.
2. Digital Twin uses the same 72-hour series.
3. Optimization uses the same selected forecast value.
4. Evaluation reads metrics from the same model/artifact manifest.
5. No tab uses hardcoded placeholder forecast values.

## Notes
Run `python -m pytest -q` and manual smoke test in UI/APIs after changes.

