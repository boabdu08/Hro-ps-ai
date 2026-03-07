import pandas as pd
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense

df = pd.read_csv("clean_data.csv")

features = df[[
    "patients",
    "day_of_week",
    "month",
    "is_weekend",
    "holiday",
    "weather"
]].values

sequence_length = 24

X=[]
y=[]

for i in range(len(features)-sequence_length):

    X.append(features[i:i+sequence_length])
    y.append(features[i+sequence_length][0])

X=np.array(X)
y=np.array(y)

model=Sequential()

model.add(LSTM(64,input_shape=(X.shape[1],X.shape[2])))
model.add(Dense(32))
model.add(Dense(1))

model.compile(
    optimizer="adam",
    loss="mse"
)

model.fit(X,y,epochs=10,batch_size=32)

model.save("hospital_forecast_model.keras")

print("Model retrained successfully")