import shap
import pandas as pd
import joblib

def explain_prediction(input_data):

    model = joblib.load("patient_model.pkl")

    explainer = shap.Explainer(model)

    shap_values = explainer(input_data)

    return shap_values