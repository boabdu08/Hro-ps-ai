def optimize_resources(predicted_patients):
    predicted_patients = float(predicted_patients)

    beds_needed = int(predicted_patients * 1.1)
    doctors_needed = max(1, int(predicted_patients / 8))
    nurses_needed = max(1, int(predicted_patients / 4))

    return {
        "beds_needed": beds_needed,
        "doctors_needed": doctors_needed,
        "nurses_needed": nurses_needed
    }