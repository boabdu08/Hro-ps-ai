def optimize_resources(predicted_patients):

    beds_needed = int(predicted_patients * 1.1)

    doctors_needed = int(predicted_patients / 8)

    nurses_needed = int(predicted_patients / 4)

    return {
        "beds": beds_needed,
        "doctors": doctors_needed,
        "nurses": nurses_needed
    }