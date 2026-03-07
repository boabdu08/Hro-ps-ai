def predict_emergency_load(predicted_patients):

    if predicted_patients < 80:
        return "LOW"

    elif predicted_patients < 120:
        return "MEDIUM"

    else:
        return "HIGH"