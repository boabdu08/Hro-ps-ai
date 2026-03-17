import numpy as np
import joblib
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
import pandas as pd


# =========================
# LOAD MODELS
# =========================
lstm_model = load_model("hospital_forecast_model.keras")
arimax_model = joblib.load("arimax_model.pkl")

x_scaler = joblib.load("x_scaler.pkl")
y_scaler = joblib.load("y_scaler.pkl")


# =========================
# PREPARE INPUT
# =========================
def prepare_input(sequence):
    sequence = np.array(sequence).reshape(1, -1, 1)
    sequence_scaled = x_scaler.transform(sequence.reshape(-1, 1)).reshape(1, -1, 1)
    return sequence_scaled


# =========================
# PREDICT
# =========================
def predict_lstm(sequence):
    seq = prepare_input(sequence)
    pred = lstm_model.predict(seq, verbose=0)
    return y_scaler.inverse_transform(pred)[0][0]


def predict_arimax(sequence):
    return arimax_model.forecast(steps=1)[0]


# =========================
# SMART HYBRID
# =========================
def hybrid_predict(sequence, weight_lstm=0.6):
    lstm_pred = predict_lstm(sequence)
    arimax_pred = predict_arimax(sequence)

    hybrid = (lstm_pred * weight_lstm) + (arimax_pred * (1 - weight_lstm))

    return {
        "lstm": float(lstm_pred),
        "arimax": float(arimax_pred),
        "hybrid": float(hybrid)
    }