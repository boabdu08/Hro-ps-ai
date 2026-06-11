"""Regression test: /predict must never return a negative patient count.

Out-of-distribution input sequences can push the regression below zero; the
endpoint clamps to 0 to match the artifact pipeline's no-negative-forecast rule.
"""

import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("APP_ENV", "test")


class TestPredictClamp:
    def test_negative_prediction_clamped_to_zero(self, monkeypatch):
        import api

        fake_state = SimpleNamespace(predicted_patients_next_hour=-591.97, risk_level="LOW")
        fake_result = {"hybrid_prediction": -591.97, "lstm_prediction": -600.0,
                       "arimax_prediction": -560.0, "lstm_weight": 0.8, "arimax_weight": 0.2}
        monkeypatch.setattr(api, "_build_state_from_sequence", lambda seq: (fake_state, fake_result))
        monkeypatch.setattr(api, "forecast_state_to_dict", lambda state, include_frames=False: {})

        seq = np.zeros((api.SEQUENCE_LENGTH, api.FEATURE_COUNT))
        payload = api.PredictRequest(sequence=seq.tolist())
        out = api.predict(payload, _token={"role": "admin"})

        assert out["predicted_patients_next_hour"] == 0.0
        resources = out["recommended_resources"]
        assert resources["beds_needed"] >= 0
        assert resources["doctors_needed"] >= 1
        assert resources["nurses_needed"] >= 1

    def test_positive_prediction_passes_through(self, monkeypatch):
        import api

        fake_state = SimpleNamespace(predicted_patients_next_hour=101.0, risk_level="MEDIUM")
        fake_result = {"hybrid_prediction": 101.0, "lstm_prediction": 102.0,
                       "arimax_prediction": 97.0, "lstm_weight": 0.8, "arimax_weight": 0.2}
        monkeypatch.setattr(api, "_build_state_from_sequence", lambda seq: (fake_state, fake_result))
        monkeypatch.setattr(api, "forecast_state_to_dict", lambda state, include_frames=False: {})

        seq = np.zeros((api.SEQUENCE_LENGTH, api.FEATURE_COUNT))
        out = api.predict(api.PredictRequest(sequence=seq.tolist()), _token={"role": "admin"})
        assert out["predicted_patients_next_hour"] == pytest.approx(101.0)
