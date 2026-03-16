from typing import List
import json

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from tensorflow.keras.models import load_model

from database import get_db
from models import User, PatientFlow
from schemas import LoginRequest

app = FastAPI(title="Hospital AI API")


# ========================================
# LOAD MODELS + ARTIFACTS
# ========================================
lstm_model = load_model("hospital_forecast_model.keras", compile=False)
arimax_model = joblib.load("arimax_model.pkl")
x_scaler = joblib.load("x_scaler.pkl")
y_scaler = joblib.load("y_scaler.pkl")

with open("hybrid_config.json", "r", encoding="utf-8") as f:
    hybrid_config = json.load(f)

HYBRID_LSTM_WEIGHT = float(hybrid_config.get("lstm_weight", 0.95))
HYBRID_ARIMAX_WEIGHT = float(hybrid_config.get("arimax_weight", 0.05))

FEATURE_NAMES = [
    "patients",
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather",
]

ADMIN_MESSAGE_TEMPLATES = [
    {
        "category": "emergency",
        "title": "Emergency Surge Alert",
        "message": "Emergency surge alert: all available staff should review current assignments and prepare for overflow response."
    },
    {
        "category": "coverage",
        "title": "Doctor Coverage Request",
        "message": "Urgent coverage needed: an additional doctor is required to cover the current shift immediately."
    },
    {
        "category": "coverage",
        "title": "Nurse Coverage Request",
        "message": "Urgent coverage needed: an additional nurse is required to support the active department."
    },
    {
        "category": "shift",
        "title": "Shift Change Notice",
        "message": "Shift update notice: please review your latest assignment and acknowledge the change."
    },
    {
        "category": "capacity",
        "title": "Bed Shortage Warning",
        "message": "Capacity warning: bed pressure is increasing. Review admissions and discharge flow immediately."
    },
]

STAFF_QUICK_REPLIES = [
    "تم",
    "تم التنفيذ",
    "وصل",
    "جاري التنفيذ",
    "نحتاج دعم دكاترة",
    "نحتاج دعم تمريض",
    "يوجد عجز",
    "لا أستطيع التغطية الآن",
]


# ========================================
# REQUEST MODELS
# ========================================
class PredictRequest(BaseModel):
    sequence: List[List[float]]


class SimulateRequest(BaseModel):
    predicted_patients: float
    beds_available: int
    doctors_available: int
    demand_increase_percent: float = 0


class ExplainRequest(BaseModel):
    sequence: List[List[float]]


# ========================================
# HELPERS
# ========================================
def validate_sequence_shape(arr: np.ndarray):
    return arr.shape == (24, 6)


def scale_sequence(sequence_array: np.ndarray):
    flat = sequence_array.reshape(-1, sequence_array.shape[-1])
    scaled_flat = x_scaler.transform(flat)
    return scaled_flat.reshape(sequence_array.shape).astype(np.float32)


def inverse_scale_target(pred_scaled: float):
    value = np.array([[pred_scaled]], dtype=np.float32)
    return float(y_scaler.inverse_transform(value)[0][0])


def get_next_exog_from_sequence(sequence_array: np.ndarray):
    last_row = sequence_array[-1]
    exog = np.array(
        [[last_row[1], last_row[2], last_row[3], last_row[4], last_row[5]]],
        dtype=float
    )
    return exog


def predict_lstm(sequence_array: np.ndarray):
    scaled_sequence = scale_sequence(sequence_array)
    x_input = np.array([scaled_sequence], dtype=np.float32)

    pred_scaled = float(lstm_model.predict(x_input, verbose=0)[0][0])
    pred_original = inverse_scale_target(pred_scaled)
    return pred_original


def predict_arimax(sequence_array: np.ndarray):
    next_exog = get_next_exog_from_sequence(sequence_array)
    forecast = arimax_model.forecast(steps=1, exog=next_exog)
    return float(forecast.iloc[0] if hasattr(forecast, "iloc") else forecast[0])


def predict_hybrid(sequence_array: np.ndarray):
    lstm_pred = predict_lstm(sequence_array)
    arimax_pred = predict_arimax(sequence_array)

    hybrid_prediction = (
        HYBRID_LSTM_WEIGHT * lstm_pred
        + HYBRID_ARIMAX_WEIGHT * arimax_pred
    )

    return {
        "lstm_prediction": lstm_pred,
        "arimax_prediction": arimax_pred,
        "hybrid_prediction": hybrid_prediction,
        "lstm_weight": HYBRID_LSTM_WEIGHT,
        "arimax_weight": HYBRID_ARIMAX_WEIGHT,
    }


def optimize_resources(predicted_patients: float):
    beds_needed = int(np.ceil(predicted_patients * 1.1))
    doctors_needed = max(1, int(np.ceil(predicted_patients / 8)))
    nurses_needed = max(1, int(np.ceil(predicted_patients / 4)))

    return {
        "beds_needed": beds_needed,
        "doctors_needed": doctors_needed,
        "nurses_needed": nurses_needed,
    }


def predict_emergency_load(predicted_patients: float):
    if predicted_patients < 80:
        return "LOW"
    elif predicted_patients < 120:
        return "MEDIUM"
    return "HIGH"


def allocate_beds(predicted_patients: int, available_beds: int):
    if predicted_patients <= available_beds:
        return {
            "status": "OK",
            "beds_used": predicted_patients,
            "beds_remaining": available_beds - predicted_patients,
            "shortage": 0,
        }

    shortage = predicted_patients - available_beds
    return {
        "status": "SHORTAGE",
        "beds_used": available_beds,
        "beds_remaining": 0,
        "shortage": shortage,
    }


def explain_feature_importance(sequence_array: np.ndarray):
    base_result = predict_hybrid(sequence_array)
    base_pred = float(base_result["hybrid_prediction"])

    impacts = []

    for i, feature_name in enumerate(FEATURE_NAMES):
        modified = sequence_array.copy()

        if feature_name == "patients":
            modified[-1, i] = modified[-1, i] * 1.10
        elif feature_name in ["day_of_week", "month", "weather"]:
            modified[-1, i] = modified[-1, i] + 1
        else:
            modified[-1, i] = 1 - modified[-1, i]

        new_result = predict_hybrid(modified)
        new_pred = float(new_result["hybrid_prediction"])
        impact = new_pred - base_pred

        impacts.append({
            "feature": feature_name,
            "impact": impact,
        })

    impacts = sorted(impacts, key=lambda x: abs(x["impact"]), reverse=True)

    return {
        "base_prediction": base_pred,
        "feature_impacts": impacts,
    }


# ========================================
# ROUTES
# ========================================
@app.get("/")
def home():
    return {"message": "Hospital AI API is running"}


@app.get("/status")
def system_status():
    return {
        "system": "Hospital AI",
        "model": "Hybrid Forecast (LSTM + ARIMAX)",
        "status": "running",
        "hybrid_weights": {
            "lstm": HYBRID_LSTM_WEIGHT,
            "arimax": HYBRID_ARIMAX_WEIGHT,
        },
    }


@app.get("/message_templates")
def get_message_templates():
    return {
        "admin_templates": ADMIN_MESSAGE_TEMPLATES,
        "staff_quick_replies": STAFF_QUICK_REPLIES,
    }


@app.post("/predict")
def predict(data: PredictRequest):
    arr = np.array(data.sequence, dtype=float)

    if not validate_sequence_shape(arr):
        raise HTTPException(status_code=400, detail="Input must be shape (24, 6)")

    pred_result = predict_hybrid(arr)
    hybrid_pred = float(pred_result["hybrid_prediction"])

    resources = optimize_resources(hybrid_pred)
    emergency = predict_emergency_load(hybrid_pred)

    return {
        "predicted_patients_next_hour": hybrid_pred,
        "lstm_prediction": pred_result["lstm_prediction"],
        "arimax_prediction": pred_result["arimax_prediction"],
        "hybrid_prediction": hybrid_pred,
        "hybrid_weights": {
            "lstm": pred_result["lstm_weight"],
            "arimax": pred_result["arimax_weight"],
        },
        "emergency_level": emergency,
        "recommended_resources": resources,
    }


@app.post("/simulate")
def simulate(data: SimulateRequest):
    simulated_patients = data.predicted_patients * (
        1 + data.demand_increase_percent / 100
    )

    resources = optimize_resources(simulated_patients)
    bed_result = allocate_beds(int(np.ceil(simulated_patients)), data.beds_available)
    emergency = predict_emergency_load(simulated_patients)

    doctor_shortage = max(0, resources["doctors_needed"] - data.doctors_available)

    return {
        "simulated_patients": float(simulated_patients),
        "emergency_level": emergency,
        "bed_allocation": bed_result,
        "recommended_resources": resources,
        "doctor_shortage": doctor_shortage,
    }


@app.post("/explain")
def explain(data: ExplainRequest):
    arr = np.array(data.sequence, dtype=float)

    if not validate_sequence_shape(arr):
        raise HTTPException(status_code=400, detail="Input must be shape (24, 6)")

    return explain_feature_importance(arr)


@app.post("/auth/login")
def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user or user.password != payload.password:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "department": user.department,
    }


@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()

    return [
        {
            "username": u.username,
            "name": u.name,
            "role": u.role,
            "department": u.department,
        }
        for u in users
    ]


@app.get("/patient_flow/latest")
def get_latest_patient_flow(db: Session = Depends(get_db)):
    rows = (
        db.query(PatientFlow)
        .order_by(PatientFlow.id.desc())
        .limit(24)
        .all()
    )

    if len(rows) < 24:
        raise HTTPException(status_code=404, detail="Not enough patient flow rows found")

    rows = list(reversed(rows))

    sequence = []
    for r in rows:
        sequence.append([
            r.patients,
            r.day_of_week,
            r.month,
            r.is_weekend,
            r.holiday,
            r.weather,
        ])

    return {"sequence": sequence}