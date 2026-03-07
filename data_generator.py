import pandas as pd
import random
from datetime import datetime, timedelta

start_date = datetime(2023,1,1)

data = []

weather_types = ["sunny","rainy","cold","hot"]

for i in range(3000):

    date = start_date + timedelta(hours=i)

    patients = random.randint(20,90)

    day_of_week = date.weekday()
    month = date.month

    weekend = 1 if day_of_week >= 5 else 0

    holiday = 1 if random.random() < 0.03 else 0

    weather = random.choice(weather_types)

    data.append({
        "datetime": date,
        "patients": patients,
        "day_of_week": day_of_week,
        "month": month,
        "is_weekend": weekend,
        "holiday": holiday,
        "weather": weather
    })

df = pd.DataFrame(data)

df.to_csv("hospital_patient_flow.csv", index=False)

print("Advanced dataset generated")