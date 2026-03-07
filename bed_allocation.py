def allocate_beds(predicted_patients, available_beds):

    if predicted_patients <= available_beds:
        return {
            "status": "OK",
            "beds_used": predicted_patients,
            "beds_remaining": available_beds - predicted_patients
        }

    else:
        shortage = predicted_patients - available_beds

        return {
            "status": "SHORTAGE",
            "beds_used": available_beds,
            "beds_remaining": 0,
            "shortage": shortage
        }