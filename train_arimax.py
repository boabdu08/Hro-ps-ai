import json
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX

# ========================================
# CONFIG
# ========================================
DATA_FILE = "clean_data.csv"
MODEL_FILE = "arimax_model.pkl"
EVAL_OUTPUT_FILE = "arimax_eval_outputs.npz"
METRICS_FILE = "arimax_metrics.json"

SEQUENCE_LENGTH = 24

REQUIRED_COLS = [
    "patients",
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather"
]

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15

ARIMAX_ORDER = (2, 1, 2)
SEASONAL_ORDER = (0, 0, 0, 0)


# ========================================
# METRICS
# ========================================
def calculate_mape(y_true, y_pred):
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)

    mask = y_true != 0
    if mask.sum() == 0:
        return None

    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def compute_metrics(y_true, y_pred):
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = calculate_mape(y_true, y_pred)
    return {"mae": mae, "rmse": rmse, "mape": mape}


# ========================================
# LOAD + CLEAN
# ========================================
df = pd.read_csv(DATA_FILE)

missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
if missing_cols:
    raise ValueError(f"Missing required columns: {missing_cols}")

if "datetime" in df.columns:
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.sort_values("datetime").reset_index(drop=True)

df = df[REQUIRED_COLS].copy()

for col in REQUIRED_COLS:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna().reset_index(drop=True)

if len(df) <= SEQUENCE_LENGTH + 30:
    raise ValueError("Not enough rows for ARIMAX training/evaluation.")

# ========================================
# BUILD SPLITS MATCHING LSTM TARGET ROWS
# ========================================
total_sequences = len(df) - SEQUENCE_LENGTH
train_end_seq = int(total_sequences * TRAIN_RATIO)
val_end_seq = int(total_sequences * (TRAIN_RATIO + VAL_RATIO))

train_end_row = SEQUENCE_LENGTH + train_end_seq
val_end_row = SEQUENCE_LENGTH + val_end_seq

# Train uses all rows up to train_end_row
train_df = df.iloc[:train_end_row].copy()

# Validation target rows
val_df = df.iloc[train_end_row:val_end_row].copy()

# Test target rows
test_df = df.iloc[val_end_row:].copy()

if len(val_df) == 0 or len(test_df) == 0:
    raise ValueError("Validation or test split is empty.")

y_train = train_df["patients"].astype(float)
exog_train = train_df[["day_of_week", "month", "is_weekend", "holiday", "weather"]].astype(float)

y_val = val_df["patients"].astype(float)
exog_val = val_df[["day_of_week", "month", "is_weekend", "holiday", "weather"]].astype(float)

y_test = test_df["patients"].astype(float)
exog_test = test_df[["day_of_week", "month", "is_weekend", "holiday", "weather"]].astype(float)

# ========================================
# TRAIN BASE MODEL ON TRAIN
# ========================================
print("Training ARIMAX on train split...")

train_model = SARIMAX(
    endog=y_train,
    exog=exog_train,
    order=ARIMAX_ORDER,
    seasonal_order=SEASONAL_ORDER,
    enforce_stationarity=False,
    enforce_invertibility=False
)

train_results = train_model.fit(disp=False)

# ========================================
# VALIDATION FORECAST
# ========================================
print("Forecasting validation split...")

val_forecast = train_results.get_forecast(
    steps=len(y_val),
    exog=exog_val
).predicted_mean

# Append validation actuals without refit, then forecast test
results_after_val = train_results.append(
    endog=y_val,
    exog=exog_val,
    refit=False
)

print("Forecasting test split...")

test_forecast = results_after_val.get_forecast(
    steps=len(y_test),
    exog=exog_test
).predicted_mean

# ========================================
# METRICS
# ========================================
val_metrics = compute_metrics(y_val.values, val_forecast.values)
test_metrics = compute_metrics(y_test.values, test_forecast.values)

metrics_payload = {
    "model": "ARIMAX",
    "order": ARIMAX_ORDER,
    "seasonal_order": SEASONAL_ORDER,
    "validation": val_metrics,
    "test": test_metrics
}

with open(METRICS_FILE, "w", encoding="utf-8") as f:
    json.dump(metrics_payload, f, indent=2)

np.savez(
    EVAL_OUTPUT_FILE,
    val_actual=y_val.values.astype(np.float32),
    val_pred=val_forecast.values.astype(np.float32),
    test_actual=y_test.values.astype(np.float32),
    test_pred=test_forecast.values.astype(np.float32)
)

print("Validation metrics:", val_metrics)
print("Test metrics:", test_metrics)

# ========================================
# TRAIN FINAL MODEL ON FULL DATA
# ========================================
print("Training final ARIMAX model on full cleaned dataset...")

y_full = df["patients"].astype(float)
exog_full = df[["day_of_week", "month", "is_weekend", "holiday", "weather"]].astype(float)

final_model = SARIMAX(
    endog=y_full,
    exog=exog_full,
    order=ARIMAX_ORDER,
    seasonal_order=SEASONAL_ORDER,
    enforce_stationarity=False,
    enforce_invertibility=False
)

final_results = final_model.fit(disp=False)
joblib.dump(final_results, MODEL_FILE)

print(f"✅ ARIMAX model saved to {MODEL_FILE}")
print(f"✅ Validation/Test outputs saved to {EVAL_OUTPUT_FILE}")
print(f"✅ Metrics saved to {METRICS_FILE}")