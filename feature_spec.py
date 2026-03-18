SEQUENCE_LENGTH = 24

# Canonical feature ordering shared by:
# - training prep (prepare_sequences_v2.py)
# - inference feature building (api.py)
# - roll-forward multistep forecasting (forecast_runtime.py)
FEATURE_COLUMNS = [
    "patients",
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather",
    "hour",
    "hour_sin",
    "hour_cos",
    "patients_lag_1",
    "patients_lag_2",
    "patients_lag_3",
    "patients_lag_6",
    "patients_lag_12",
    "patients_lag_24",
    "patients_roll_mean_3",
    "patients_roll_std_3",
    "patients_roll_mean_6",
    "patients_roll_std_6",
    "patients_roll_mean_12",
    "patients_roll_std_12",
    "patients_roll_mean_24",
    "patients_roll_std_24",
    "patients_diff_1",
    "patients_diff_24",
    "trend_feature",
]

ARIMAX_EXOG_COLUMNS = [
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather",
    "hour",
    "hour_sin",
    "hour_cos",
    "trend_feature",
]

