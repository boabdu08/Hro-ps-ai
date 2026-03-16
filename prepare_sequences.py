import json
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

# ========================================
# CONFIG
# ========================================
DATA_FILE = "clean_data.csv"
SEQUENCE_LENGTH = 24

FEATURE_COLUMNS = [
    "patients",
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather"
]
TARGET_COLUMN = "patients"

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# Output files
SEQUENCES_FILE = "prepared_sequences.npz"
X_SCALER_FILE = "x_scaler.pkl"
Y_SCALER_FILE = "y_scaler.pkl"
SPLIT_INFO_FILE = "split_info.json"


# ========================================
# LOAD + CLEAN
# ========================================
df = pd.read_csv(DATA_FILE)

missing_cols = [c for c in FEATURE_COLUMNS if c not in df.columns]
if missing_cols:
    raise ValueError(f"Missing required columns: {missing_cols}")

# Sort by datetime if available
if "datetime" in df.columns:
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.sort_values("datetime").reset_index(drop=True)

# Keep only needed features
df = df[FEATURE_COLUMNS + (["datetime"] if "datetime" in df.columns else [])].copy()

# Force numeric conversion on features
for col in FEATURE_COLUMNS:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Drop invalid rows
df = df.dropna().reset_index(drop=True)

if len(df) <= SEQUENCE_LENGTH + 10:
    raise ValueError("Not enough valid rows after cleaning to build sequences.")

feature_values = df[FEATURE_COLUMNS].values.astype(float)

# ========================================
# BUILD SEQUENCES
# ========================================
X = []
y = []
target_row_indices = []

for i in range(len(feature_values) - SEQUENCE_LENGTH):
    X.append(feature_values[i:i + SEQUENCE_LENGTH])
    y.append(feature_values[i + SEQUENCE_LENGTH][0])  # patients target
    target_row_indices.append(i + SEQUENCE_LENGTH)

X = np.array(X, dtype=np.float32)
y = np.array(y, dtype=np.float32).reshape(-1, 1)
target_row_indices = np.array(target_row_indices, dtype=np.int32)

total_sequences = len(X)
if total_sequences < 50:
    raise ValueError(f"Too few sequences generated: {total_sequences}")

# ========================================
# CHRONOLOGICAL SPLIT
# ========================================
train_end = int(total_sequences * TRAIN_RATIO)
val_end = int(total_sequences * (TRAIN_RATIO + VAL_RATIO))

X_train_raw = X[:train_end]
y_train_raw = y[:train_end]

X_val_raw = X[train_end:val_end]
y_val_raw = y[train_end:val_end]

X_test_raw = X[val_end:]
y_test_raw = y[val_end:]

target_rows_train = target_row_indices[:train_end]
target_rows_val = target_row_indices[train_end:val_end]
target_rows_test = target_row_indices[val_end:]

if len(X_train_raw) == 0 or len(X_val_raw) == 0 or len(X_test_raw) == 0:
    raise ValueError("One of the splits is empty. Check dataset size and split ratios.")

# ========================================
# SCALE FEATURES + TARGET
# ========================================
x_scaler = MinMaxScaler()
y_scaler = MinMaxScaler()

# Fit x scaler on TRAIN ONLY
x_scaler.fit(X_train_raw.reshape(-1, X_train_raw.shape[-1]))

def scale_sequences(x_data, scaler):
    n_samples, seq_len, n_features = x_data.shape
    flat = x_data.reshape(-1, n_features)
    scaled_flat = scaler.transform(flat)
    return scaled_flat.reshape(n_samples, seq_len, n_features).astype(np.float32)

X_train = scale_sequences(X_train_raw, x_scaler)
X_val = scale_sequences(X_val_raw, x_scaler)
X_test = scale_sequences(X_test_raw, x_scaler)

# Fit y scaler on TRAIN ONLY
y_scaler.fit(y_train_raw)

y_train = y_scaler.transform(y_train_raw).astype(np.float32)
y_val = y_scaler.transform(y_val_raw).astype(np.float32)
y_test = y_scaler.transform(y_test_raw).astype(np.float32)

# ========================================
# SAVE OUTPUTS
# ========================================
np.savez(
    SEQUENCES_FILE,
    X_train=X_train,
    y_train=y_train,
    X_val=X_val,
    y_val=y_val,
    X_test=X_test,
    y_test=y_test,
    y_train_raw=y_train_raw,
    y_val_raw=y_val_raw,
    y_test_raw=y_test_raw,
    target_rows_train=target_rows_train,
    target_rows_val=target_rows_val,
    target_rows_test=target_rows_test
)

joblib.dump(x_scaler, X_SCALER_FILE)
joblib.dump(y_scaler, Y_SCALER_FILE)

split_info = {
    "sequence_length": SEQUENCE_LENGTH,
    "feature_columns": FEATURE_COLUMNS,
    "target_column": TARGET_COLUMN,
    "train_ratio": TRAIN_RATIO,
    "val_ratio": VAL_RATIO,
    "test_ratio": TEST_RATIO,
    "total_rows_after_cleaning": int(len(df)),
    "total_sequences": int(total_sequences),
    "train_sequences": int(len(X_train)),
    "val_sequences": int(len(X_val)),
    "test_sequences": int(len(X_test)),
    "train_end_sequence_index": int(train_end),
    "val_end_sequence_index": int(val_end)
}

with open(SPLIT_INFO_FILE, "w", encoding="utf-8") as f:
    json.dump(split_info, f, indent=2)

print("✅ Multi-feature sequences prepared successfully.")
print(f"Train: {X_train.shape}, {y_train.shape}")
print(f"Val:   {X_val.shape}, {y_val.shape}")
print(f"Test:  {X_test.shape}, {y_test.shape}")
print(f"Saved: {SEQUENCES_FILE}, {X_SCALER_FILE}, {Y_SCALER_FILE}, {SPLIT_INFO_FILE}")