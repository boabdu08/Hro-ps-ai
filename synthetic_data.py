"""Realistic synthetic data generator for always-on demo.

We simulate hourly patient arrivals with:
- time-of-day pattern
- day-of-week pattern
- seasonal/month pattern
- random emergencies (spikes)

This module is dependency-light (stdlib only).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SyntheticParams:
    base: float = 70.0
    daily_amplitude: float = 25.0
    weekend_drop: float = 10.0
    seasonal_amplitude: float = 8.0
    noise_std: float = 6.0
    emergency_rate: float = 0.03
    emergency_spike_min: float = 25.0
    emergency_spike_max: float = 80.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def generate_patient_flow(now: datetime, params: SyntheticParams) -> dict:
    """Return a row-like dict compatible with PatientFlow."""

    hour = now.hour
    dow = now.weekday()  # 0=Mon
    month = now.month

    # Daily cycle: peak around 14:00
    # Shift sine so hour=14 is peak.
    daily = params.daily_amplitude * math.sin(((hour - 8) / 24.0) * 2 * math.pi)

    # Weekend effect
    weekend = 1 if dow >= 5 else 0
    weekend_effect = -params.weekend_drop if weekend else 0.0

    # Seasonality: month cycle
    seasonal = params.seasonal_amplitude * math.sin(((month - 1) / 12.0) * 2 * math.pi)

    # Noise
    noise = random.gauss(0.0, params.noise_std)

    emergency = 1 if random.random() < params.emergency_rate else 0
    spike = random.uniform(params.emergency_spike_min, params.emergency_spike_max) if emergency else 0.0

    patients = params.base + daily + weekend_effect + seasonal + noise + spike
    patients = _clamp(patients, 5.0, 300.0)

    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "patients": float(round(patients, 2)),
        "day_of_week": int(dow),
        "month": int(month),
        "is_weekend": int(weekend),
        "holiday": 0,
        # current model expects numeric weather
        "weather": 0.0,
        "is_emergency": bool(emergency),
        "emergency_spike": float(round(spike, 2)),
    }
