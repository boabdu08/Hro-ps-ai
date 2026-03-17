import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error


def calculate_metrics(actual, predicted):
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))

    mape = np.mean(np.abs((actual - predicted) / actual)) * 100

    return {
        "MAE": round(mae, 3),
        "RMSE": round(rmse, 3),
        "MAPE": round(mape, 2)
    }


def compare_models(actual, lstm, arimax, hybrid):
    return {
        "LSTM": calculate_metrics(actual, lstm),
        "ARIMAX": calculate_metrics(actual, arimax),
        "HYBRID": calculate_metrics(actual, hybrid),
    }