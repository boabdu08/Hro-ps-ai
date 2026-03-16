import json
import os
import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.optimizers import Adam

# ========================================
# CONFIG
# ========================================
SEQUENCES_FILE = "prepared_sequences.npz"
X_SCALER_FILE = "x_scaler.pkl"
Y_SCALER_FILE = "y_scaler.pkl"

LSTM_MODEL_FILE = "hospital_forecast_model.keras"
LSTM_METRICS_FILE = "lstm_metrics.json"
LSTM_EVAL_OUTPUT_FILE = "lstm_eval_outputs.npz"

ARIMAX_EVAL_OUTPUT_FILE = "arimax_eval_outputs.npz"
HYBRID_CONFIG_FILE = "hybrid_config.json"
HYBRID_EVAL_OUTPUT_FILE = "hybrid_eval_outputs.npz"

EPOCHS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.001


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
# LOAD PREPARED DATA
# ========================================
if not os.path.exists(SEQUENCES_FILE):
    raise FileNotFoundError(f"{SEQUENCES_FILE} not found. Run prepare_sequences.py first.")

data = np.load(SEQUENCES_FILE)

X_train = data["X_train"]
y_train = data["y_train"]
X_val = data["X_val"]
y_val = data["y_val"]
X_test = data["X_test"]
y_test = data["y_test"]

y_scaler = joblib.load(Y_SCALER_FILE)

print("Loaded prepared sequences.")
print("X_train:", X_train.shape, "y_train:", y_train.shape)
print("X_val:", X_val.shape, "y_val:", y_val.shape)
print("X_test:", X_test.shape, "y_test:", y_test.shape)

# ========================================
# BUILD MODEL
# ========================================
model = Sequential([
    Input(shape=(X_train.shape[1], X_train.shape[2])),
    LSTM(64, return_sequences=True),
    Dropout(0.2),
    LSTM(32),
    Dense(16, activation="relu"),
    Dense(1)
])

model.compile(
    optimizer=Adam(learning_rate=LEARNING_RATE),
    loss="mse"
)

callbacks = [
    EarlyStopping(
        monitor="val_loss",
        patience=10,
        restore_best_weights=True
    ),
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=5,
        min_lr=1e-5
    ),
    ModelCheckpoint(
        filepath=LSTM_MODEL_FILE,
        monitor="val_loss",
        save_best_only=True
    )
]

# ========================================
# TRAIN
# ========================================
history = model.fit(
    X_train,
    y_train,
    validation_data=(X_val, y_val),
    epochs=EPOCHS,
    batch_size=BATCH_SIZE,
    callbacks=callbacks,
    verbose=1
)

# Load best saved model
model = load_model(LSTM_MODEL_FILE, compile=False)

# ========================================
# EVALUATE LSTM
# ========================================
val_pred_scaled = model.predict(X_val, verbose=0)
test_pred_scaled = model.predict(X_test, verbose=0)

val_pred = y_scaler.inverse_transform(val_pred_scaled).flatten()
test_pred = y_scaler.inverse_transform(test_pred_scaled).flatten()

val_actual = y_scaler.inverse_transform(y_val).flatten()
test_actual = y_scaler.inverse_transform(y_test).flatten()

val_metrics = compute_metrics(val_actual, val_pred)
test_metrics = compute_metrics(test_actual, test_pred)

lstm_metrics_payload = {
    "model": "LSTM",
    "validation": val_metrics,
    "test": test_metrics,
    "history": {
        "final_train_loss": float(history.history["loss"][-1]),
        "final_val_loss": float(history.history["val_loss"][-1]),
        "best_val_loss": float(min(history.history["val_loss"]))
    }
}

with open(LSTM_METRICS_FILE, "w", encoding="utf-8") as f:
    json.dump(lstm_metrics_payload, f, indent=2)

np.savez(
    LSTM_EVAL_OUTPUT_FILE,
    val_actual=val_actual.astype(np.float32),
    val_pred=val_pred.astype(np.float32),
    test_actual=test_actual.astype(np.float32),
    test_pred=test_pred.astype(np.float32)
)

print("LSTM Validation metrics:", val_metrics)
print("LSTM Test metrics:", test_metrics)
print(f"✅ LSTM model saved to {LSTM_MODEL_FILE}")
print(f"✅ LSTM metrics saved to {LSTM_METRICS_FILE}")
print(f"✅ LSTM evaluation outputs saved to {LSTM_EVAL_OUTPUT_FILE}")

# ========================================
# HYBRID WEIGHT SEARCH
# ========================================
if os.path.exists(ARIMAX_EVAL_OUTPUT_FILE):
    arimax_data = np.load(ARIMAX_EVAL_OUTPUT_FILE)

    arimax_val_actual = arimax_data["val_actual"].flatten()
    arimax_val_pred = arimax_data["val_pred"].flatten()

    arimax_test_actual = arimax_data["test_actual"].flatten()
    arimax_test_pred = arimax_data["test_pred"].flatten()

    # Align lengths if needed
    val_len = min(len(val_actual), len(arimax_val_actual), len(val_pred), len(arimax_val_pred))
    test_len = min(len(test_actual), len(arimax_test_actual), len(test_pred), len(arimax_test_pred))

    val_actual_h = val_actual[:val_len]
    lstm_val_pred_h = val_pred[:val_len]
    arimax_val_pred_h = arimax_val_pred[:val_len]

    test_actual_h = test_actual[:test_len]
    lstm_test_pred_h = test_pred[:test_len]
    arimax_test_pred_h = arimax_test_pred[:test_len]

    best_weight = None
    best_rmse = float("inf")
    best_val_pred = None

    # Grid search
    for w_lstm in np.arange(0.0, 1.01, 0.05):
        w_arimax = 1.0 - w_lstm
        hybrid_val_pred = (w_lstm * lstm_val_pred_h) + (w_arimax * arimax_val_pred_h)

        rmse = np.sqrt(mean_squared_error(val_actual_h, hybrid_val_pred))

        if rmse < best_rmse:
            best_rmse = rmse
            best_weight = (float(w_lstm), float(w_arimax))
            best_val_pred = hybrid_val_pred

    best_lstm_weight, best_arimax_weight = best_weight

    hybrid_test_pred = (
        best_lstm_weight * lstm_test_pred_h
        + best_arimax_weight * arimax_test_pred_h
    )

    hybrid_val_metrics = compute_metrics(val_actual_h, best_val_pred)
    hybrid_test_metrics = compute_metrics(test_actual_h, hybrid_test_pred)

    hybrid_config = {
        "hybrid_strategy": "validation_optimized_weighted_average",
        "lstm_weight": best_lstm_weight,
        "arimax_weight": best_arimax_weight,
        "validation": hybrid_val_metrics,
        "test": hybrid_test_metrics
    }

    with open(HYBRID_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(hybrid_config, f, indent=2)

    np.savez(
        HYBRID_EVAL_OUTPUT_FILE,
        val_actual=val_actual_h.astype(np.float32),
        val_pred=best_val_pred.astype(np.float32),
        test_actual=test_actual_h.astype(np.float32),
        test_pred=hybrid_test_pred.astype(np.float32)
    )

    print("✅ Hybrid config saved to", HYBRID_CONFIG_FILE)
    print("Hybrid validation metrics:", hybrid_val_metrics)
    print("Hybrid test metrics:", hybrid_test_metrics)
    print("Best weights -> LSTM:", best_lstm_weight, "| ARIMAX:", best_arimax_weight)

else:
    print(f"⚠ {ARIMAX_EVAL_OUTPUT_FILE} not found. Hybrid optimization skipped.")