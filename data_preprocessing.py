import pandas as pd

df = pd.read_csv("hospital_patient_flow.csv")

df["datetime"] = pd.to_datetime(df["datetime"])

df = df.sort_values("datetime")

weather_map = {
    "sunny":0,
    "rainy":1,
    "cold":2,
    "hot":3
}

df["weather"] = df["weather"].map(weather_map)

df = df.dropna()

df.to_csv("clean_data.csv", index=False)

print("Advanced data cleaned")