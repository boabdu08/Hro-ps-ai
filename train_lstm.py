import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense

X = np.load("X.npy")
y = np.load("y.npy")

model = Sequential()

model.add(LSTM(64, input_shape=(X.shape[1], X.shape[2])))

model.add(Dense(32))

model.add(Dense(1))

model.compile(
    optimizer="adam",
    loss="mse"
)

model.fit(
    X,
    y,
    epochs=15,
    batch_size=32
)

model.save("hospital_forecast_model.keras")

print("Advanced model trained")