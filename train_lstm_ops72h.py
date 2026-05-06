"""Train LSTM (ops-aware) for 72-hour forecasting.

This training script uses the updated operational data model via
`forecasting_pipeline.build_ops_hourly_frame()`.

It outputs artifacts under:
  - artifacts/models_72h/
  - artifacts/metrics_72h/

We keep these separate from the legacy 24h artifacts used by Command Center.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler

from forecasting_pipeline import METRICS_DIR, MODEL_DIR, build_ops_hourly_frame, save_ops_hourly_dataset


def mape_safe(y_true, y_pred):
    y_true = np.array(y_true, dtype=float).reshape(-1)
    y_pred = np.array(y_pred, dtype=float).reshape(-1)
    denom = np.where(np.abs(y_true) < 1e-8, 1.0, np.abs(y_true))
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def evaluate(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    mape = mape_safe(y_true, y_pred)
    return {"MAE": float(mae), "RMSE": float(rmse), "MAPE": float(mape)}


def build_sequences(x: np.ndarray, y: np.ndarray, seq_len: int):
    Xs, ys = [], []
    for i in range(seq_len, len(x)):
        Xs.append(x[i - seq_len : i])
        ys.append(y[i])
    return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def main():
    # Lazy import: keep non-training flows light.
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.optimizers import Adam

    frame = build_ops_hourly_frame()
    if frame.overall.empty:
        raise RuntimeError("No ops dataset available (PatientFlow/PatientTracking empty). Seed the DB first.")

    save_ops_hourly_dataset(frame)

    df = frame.overall.copy()
    df = df.sort_values("datetime").reset_index(drop=True)

    target = "patients"
    feature_cols = [
        # target included as a feature for autoregressive learning
        "patients",
        "hour",
        "day_of_week",
        "month",
        "week_number",
        "season",
        "is_weekend",
        "holiday",
        "appointments_count",
        "or_bookings_count",
        "doctors_available",
        "nurses_available",
        "occupied_beds",
        "waiting_patients",
        "lag_1",
        "lag_24",
        "roll_mean_3",
        "roll_mean_6",
        "roll_mean_24",
    ]
    for c in feature_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Sequence length: keep aligned with existing system (24 hours) unless tuned later.
    seq_len = 24

    n = len(df)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    x_scaler = MinMaxScaler()
    y_scaler = MinMaxScaler()

    x_train = train_df[feature_cols].values.astype(np.float32)
    x_val = val_df[feature_cols].values.astype(np.float32)
    x_test = test_df[feature_cols].values.astype(np.float32)

    y_train = train_df[[target]].values.astype(np.float32)
    y_val = val_df[[target]].values.astype(np.float32)
    y_test = test_df[[target]].values.astype(np.float32)

    x_scaler.fit(x_train)
    y_scaler.fit(y_train)

    x_train_s = x_scaler.transform(x_train)
    x_val_s = x_scaler.transform(x_val)
    x_test_s = x_scaler.transform(x_test)

    y_train_s = y_scaler.transform(y_train)
    y_val_s = y_scaler.transform(y_val)
    y_test_s = y_scaler.transform(y_test)

    X_train, Y_train = build_sequences(x_train_s, y_train_s, seq_len)
    X_val, Y_val = build_sequences(x_val_s, y_val_s, seq_len)
    X_test, Y_test = build_sequences(x_test_s, y_test_s, seq_len)

    if len(X_train) == 0 or len(X_val) == 0:
        raise RuntimeError("Not enough rows to build LSTM sequences for training.")

    def build_model(input_shape):
        model = Sequential(
            [
                LSTM(128, return_sequences=True, input_shape=input_shape),
                Dropout(0.2),
                LSTM(64),
                Dropout(0.2),
                Dense(32, activation="relu"),
                Dense(1),
            ]
        )
        model.compile(optimizer=Adam(learning_rate=0.001), loss="mse")
        return model

    model_path = MODEL_DIR / "lstm_ops72h.keras"
    x_scaler_path = MODEL_DIR / "lstm_x_scaler.pkl"
    y_scaler_path = MODEL_DIR / "lstm_y_scaler.pkl"
    meta_path = MODEL_DIR / "lstm_feature_config.json"

    model = build_model((X_train.shape[1], X_train.shape[2]))
    callbacks = [
        EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-5, verbose=1),
        ModelCheckpoint(filepath=str(model_path), monitor="val_loss", save_best_only=True, verbose=1),
    ]

    history = model.fit(
        X_train,
        Y_train,
        validation_data=(X_val, Y_val),
        epochs=60,
        batch_size=64,
        callbacks=callbacks,
        verbose=1,
    )

    best = load_model(str(model_path), compile=False)
    val_pred_s = best.predict(X_val, verbose=0).reshape(-1, 1)
    test_pred_s = best.predict(X_test, verbose=0).reshape(-1, 1)

    y_val_true = y_scaler.inverse_transform(Y_val.reshape(-1, 1)).reshape(-1)
    y_test_true = y_scaler.inverse_transform(Y_test.reshape(-1, 1)).reshape(-1)
    y_val_pred = y_scaler.inverse_transform(val_pred_s).reshape(-1)
    y_test_pred = y_scaler.inverse_transform(test_pred_s).reshape(-1)

    val_metrics = evaluate(y_val_true, y_val_pred)
    test_metrics = evaluate(y_test_true, y_test_pred)

    joblib.dump(x_scaler, x_scaler_path)
    joblib.dump(y_scaler, y_scaler_path)
    meta_path.write_text(json.dumps({"feature_cols": feature_cols, "sequence_length": seq_len}, indent=2), encoding="utf-8")

    outputs = {
        "model": "LSTM",
        "val": val_metrics,
        "test": test_metrics,
        "feature_cols": feature_cols,
        "sequence_length": seq_len,
        "model_path": str(model_path),
    }
    (METRICS_DIR / "lstm_ops72h_metrics.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    np.savez_compressed(METRICS_DIR / "lstm_ops72h_val_outputs.npz", y_true=y_val_true, y_pred=y_val_pred)
    np.savez_compressed(METRICS_DIR / "lstm_ops72h_test_outputs.npz", y_true=y_test_true, y_pred=y_test_pred)

    print("Saved:", model_path)
    print("Val metrics:", val_metrics)
    print("Test metrics:", test_metrics)


if __name__ == "__main__":
    main()
