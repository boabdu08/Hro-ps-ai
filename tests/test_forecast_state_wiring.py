import pandas as pd

from dashboard_sections import (
    command_center_source_values,
    digital_twin_source_series,
    evaluation_source_metrics,
    forecast_tab_source_values,
    optimization_source_input,
)
from forecast_state import build_canonical_forecast_state


def test_forecast_state_cross_tab_source_contract():
    state = build_canonical_forecast_state(
        current_patients=96.0,
        predicted_next_hour=101.0,
        forecast_24h_values=[101.0 + (i % 6) for i in range(24)],
    )

    command_values = command_center_source_values(state)
    forecast_values = forecast_tab_source_values(state)

    assert len(state.forecast_72h_values) == 72
    assert command_values["source"] == "ForecastState"
    assert forecast_values["source"] == "ForecastState"
    assert command_values["predicted_patients_next_hour"] == forecast_values["predicted_patients_next_hour"]
    assert digital_twin_source_series(state) == state.forecast_72h_values
    assert optimization_source_input(state) == state.predicted_patients_next_hour

    metrics = evaluation_source_metrics(state)
    assert isinstance(metrics, pd.DataFrame)
    assert metrics.equals(state.metrics)
