"""Generate 1-year *labeled* clean_data-style dataset for forecasting.

This repo's canonical pipeline expects a base frame with at least:
  datetime, patients, day_of_week, month, is_weekend, holiday, weather

This script generates hourly data with realistic patterns + edge-case scenarios,
and also adds supervised-learning labels:
  - y_patients_t_plus_1  (next hour)
  - y_patients_t_plus_24 (next-day same hour)

It intentionally generates an *extra 24 hours* past the 1-year window so that
all rows in the output year have both labels available.

Output file default: clean_data_1y_labeled.csv
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd


DOW_IDX_TO_NAME = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


# Weather index MUST correspond to weather_type (as requested)
WEATHER_CODE_TO_TYPE = {
    0: "sunny",
    1: "rainy",
    2: "cold",
    3: "hot",
    4: "dusty",
    5: "windy",
}


@dataclass(frozen=True)
class GeneratorConfig:
    start: datetime
    hours: int = 365 * 24  # exactly 1 year window (non-leap)
    seed: int = 42
    capacity: float = 260.0

    # baseline and noise
    base: float = 82.0
    noise_std: float = 8.0
    ar_strength: float = 0.55  # autocorrelation weight [0..1]

    # cycles
    daily_amplitude: float = 28.0
    evening_bump: float = 14.0
    weekend_drop: float = 9.0
    seasonal_amplitude: float = 10.0

    # events
    emergency_rate: float = 0.025
    emergency_spike_min: float = 25.0
    emergency_spike_max: float = 120.0

    n_outbreaks: int = 3
    outbreak_min_days: int = 7
    outbreak_max_days: int = 14
    outbreak_min_intensity: float = 0.15  # +15%
    outbreak_max_intensity: float = 0.55  # +55%

    n_staff_shortages: int = 4
    staff_shortage_min_days: int = 2
    staff_shortage_max_days: int = 6
    staff_shortage_min_impact: float = 0.08  # -8%
    staff_shortage_max_impact: float = 0.25  # -25%

    heatwave_days: int = 6
    storm_days: int = 4


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _choose_weighted(rng: random.Random, items: List[Tuple[int, float]]) -> int:
    """items = [(value, weight), ...]"""
    total = sum(w for _, w in items)
    r = rng.random() * total
    upto = 0.0
    for val, w in items:
        upto += w
        if upto >= r:
            return val
    return items[-1][0]


def _month_weather_probs(month: int) -> List[Tuple[int, float]]:
    """Return (weather_code, weight) list; roughly: winter colder, summer hotter."""
    # Very rough climatology; tweakable.
    if month in (12, 1, 2):
        return [(2, 0.42), (1, 0.26), (5, 0.12), (0, 0.16), (4, 0.02), (3, 0.02)]
    if month in (3, 4, 11):
        # Transitional seasons: more wind, some dust.
        return [(0, 0.38), (1, 0.22), (5, 0.20), (2, 0.10), (4, 0.06), (3, 0.04)]
    if month in (5, 6, 9, 10):
        return [(0, 0.45), (3, 0.22), (4, 0.14), (5, 0.10), (1, 0.06), (2, 0.03)]
    # (7,8)
    return [(3, 0.46), (0, 0.28), (4, 0.16), (5, 0.06), (1, 0.03), (2, 0.01)]


def _weather_severity_for_type(rng: random.Random, weather_code: int, month: int) -> float:
    """Return a realistic non-negative severity in [0,1].

    Notes:
    - sunny can legitimately be near 0.
    - for non-sunny types we ensure a meaningful non-zero severity.
    """

    w = WEATHER_CODE_TO_TYPE.get(weather_code, "sunny")

    if w == "sunny":
        return float(_clamp(rng.uniform(0.0, 0.35), 0.0, 1.0))

    if w == "rainy":
        sev = rng.uniform(0.15, 0.95)
        # Winter rains tend to be stronger
        if month in (12, 1, 2):
            sev += rng.uniform(0.05, 0.20)
        return float(_clamp(sev, 0.05, 1.0))

    if w == "cold":
        sev = rng.uniform(0.10, 0.85)
        if month in (12, 1, 2):
            sev += rng.uniform(0.10, 0.25)
        return float(_clamp(sev, 0.05, 1.0))

    if w == "hot":
        sev = rng.uniform(0.15, 0.95)
        if month in (7, 8):
            sev += rng.uniform(0.10, 0.25)
        return float(_clamp(sev, 0.05, 1.0))

    if w == "dusty":
        sev = rng.uniform(0.20, 0.95)
        if month in (5, 6, 7, 8, 9):
            sev += rng.uniform(0.05, 0.20)
        return float(_clamp(sev, 0.05, 1.0))

    if w == "windy":
        sev = rng.uniform(0.15, 0.90)
        if month in (3, 4, 11):
            sev += rng.uniform(0.05, 0.15)
        return float(_clamp(sev, 0.05, 1.0))

    return float(_clamp(rng.uniform(0.0, 1.0), 0.0, 1.0))


def _weather_effect(weather_code: int, severity: float) -> float:
    """Translate weather into expected extra arrivals."""
    w = WEATHER_CODE_TO_TYPE.get(weather_code, "sunny")

    # Base effect plus severity-dependent contribution.
    if w == "sunny":
        return 1.0 * severity
    if w == "rainy":
        return 3.0 + 14.0 * severity
    if w == "cold":
        return 2.0 + 10.0 * severity
    if w == "hot":
        return 2.0 + 12.0 * severity
    if w == "dusty":
        return 4.0 + 12.0 * severity
    if w == "windy":
        return 2.0 + 9.0 * severity
    return 0.0


def _fixed_holidays(year: int) -> Dict[datetime.date, str]:
    """A small set of fixed-date holidays for scenario coverage."""
    # Keep it generic (not country-specific). You can customize later.
    fixed = [
        (1, 1, "new_year"),
        (5, 1, "labor_day"),
        (12, 25, "xmas"),
    ]
    return {datetime(year, m, d).date(): name for (m, d, name) in fixed}


def _random_windows(
    rng: random.Random,
    start: datetime,
    total_hours: int,
    n: int,
    min_hours: int,
    max_hours: int,
) -> List[Tuple[int, int]]:
    """Return list of windows as (start_hour_index, end_hour_index) in [0,total)."""
    windows: List[Tuple[int, int]] = []
    if n <= 0:
        return windows

    for _ in range(n):
        length = rng.randint(min_hours, max_hours)
        # avoid choosing start too late
        s = rng.randint(0, max(0, total_hours - length - 1))
        windows.append((s, s + length))

    # Merge overlapping windows for cleanliness.
    windows.sort(key=lambda x: x[0])
    merged: List[Tuple[int, int]] = []
    for s, e in windows:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
    return merged


def _hourly_daily_pattern(hour: int, amplitude: float, evening_bump: float) -> float:
    """A two-peak-ish diurnal pattern using sin + a gaussian bump."""
    # Peak around early afternoon.
    daily = amplitude * math.sin(((hour - 8) / 24.0) * 2.0 * math.pi)
    # Add an evening bump around 19:00.
    bump = evening_bump * math.exp(-0.5 * ((hour - 19) / 2.5) ** 2)
    return daily + bump


def generate_labeled_year(config: GeneratorConfig) -> pd.DataFrame:
    rng = random.Random(config.seed)

    # Generate an extra 24 hours to allow y(t+24) labeling for the final day.
    total_hours = config.hours + 24
    end = config.start + timedelta(hours=total_hours)

    fixed_holidays = _fixed_holidays(config.start.year)

    # Event windows (in hour indices)
    outbreak_windows = _random_windows(
        rng,
        start=config.start,
        total_hours=total_hours,
        n=config.n_outbreaks,
        min_hours=config.outbreak_min_days * 24,
        max_hours=config.outbreak_max_days * 24,
    )
    staff_windows = _random_windows(
        rng,
        start=config.start,
        total_hours=total_hours,
        n=config.n_staff_shortages,
        min_hours=config.staff_shortage_min_days * 24,
        max_hours=config.staff_shortage_max_days * 24,
    )

    # One heatwave + one storm window for coverage.
    heatwave_windows = _random_windows(
        rng,
        start=config.start,
        total_hours=total_hours,
        n=1,
        min_hours=config.heatwave_days * 24,
        max_hours=config.heatwave_days * 24,
    )
    storm_windows = _random_windows(
        rng,
        start=config.start,
        total_hours=total_hours,
        n=1,
        min_hours=config.storm_days * 24,
        max_hours=config.storm_days * 24,
    )

    # Structural break: mid-year baseline drift (e.g., policy change / new unit)
    break_point = int(config.hours * 0.55)
    break_delta = rng.uniform(-12.0, 18.0)

    # Pre-sample intensities so they are stable within windows
    outbreak_intensities = [
        rng.uniform(config.outbreak_min_intensity, config.outbreak_max_intensity)
        for _ in outbreak_windows
    ]
    staff_impacts = [
        rng.uniform(config.staff_shortage_min_impact, config.staff_shortage_max_impact)
        for _ in staff_windows
    ]

    def in_windows(i: int, windows: List[Tuple[int, int]]) -> int:
        for idx, (s, e) in enumerate(windows):
            if s <= i < e:
                return idx
        return -1

    rows: List[dict] = []
    prev_patients = config.base

    # To make holiday coverage larger than the fixed set, add some random holidays.
    # We mark an entire day as holiday with small probability.
    random_holiday_days = set()
    cur_day = config.start.date()
    while cur_day < end.date():
        if rng.random() < 0.035:
            random_holiday_days.add(cur_day)
        cur_day = (datetime.combine(cur_day, datetime.min.time()) + timedelta(days=1)).date()

    for i in range(total_hours):
        dt = config.start + timedelta(hours=i)
        hour = dt.hour
        dow_idx = dt.weekday()  # 0=Mon
        dow_name = DOW_IDX_TO_NAME.get(dow_idx, "Unknown")
        month = dt.month
        is_weekend = 1 if dow_idx >= 5 else 0

        # holiday (binary)
        holiday_name = fixed_holidays.get(dt.date())
        is_holiday = 1 if (holiday_name is not None or dt.date() in random_holiday_days) else 0

        # weather code
        weather_code = _choose_weighted(rng, _month_weather_probs(month))
        weather_severity = _weather_severity_for_type(rng, weather_code, month)

        # Override weather during forced event windows
        if in_windows(i, heatwave_windows) >= 0:
            weather_code = 3  # hot
            weather_severity = rng.uniform(0.80, 1.0)
        elif in_windows(i, storm_windows) >= 0:
            # storms: rainy + windy
            weather_code = 1 if rng.random() < 0.65 else 5
            weather_severity = rng.uniform(0.75, 1.0)

        # Seasonality: month cycle
        seasonal = config.seasonal_amplitude * math.sin(((month - 1) / 12.0) * 2.0 * math.pi)
        daily = _hourly_daily_pattern(hour, config.daily_amplitude, config.evening_bump)
        weekend_effect = -config.weekend_drop if is_weekend else 0.0

        # Weekday profile (Mon often busiest, weekend quieter) for realism.
        weekday_profile = {
            0: 6.0,   # Monday
            1: 3.0,   # Tue
            2: 2.0,   # Wed
            3: 2.0,   # Thu
            4: 4.0,   # Fri
            5: -3.0,  # Sat
            6: -5.0,  # Sun
        }.get(dow_idx, 0.0)

        # holiday effect: fewer scheduled visits but more accidents can happen; net mixed.
        holiday_effect = (-8.0 if is_holiday else 0.0) + (2.5 if (is_holiday and is_weekend) else 0.0)

        # weather effect: depends on type and severity.
        weather_effect = _weather_effect(weather_code, weather_severity)

        # outbreak / staffing
        outbreak_idx = in_windows(i, outbreak_windows)
        staff_idx = in_windows(i, staff_windows)
        outbreak_intensity = outbreak_intensities[outbreak_idx] if outbreak_idx >= 0 else 0.0
        staff_shortage_impact = staff_impacts[staff_idx] if staff_idx >= 0 else 0.0

        # baseline drift after break point
        baseline_shift = break_delta if i >= break_point else 0.0

        # emergencies: short spikes.
        # Make them *more likely* and *larger* during severe weather / outbreaks / holidays.
        emergency_rate = float(config.emergency_rate)
        emergency_rate += 0.035 * float(weather_severity)
        emergency_rate += 0.010 if is_holiday else 0.0
        emergency_rate += 0.020 * float(outbreak_intensity)
        emergency_rate = float(_clamp(emergency_rate, 0.001, 0.25))

        is_emergency = 1 if rng.random() < emergency_rate else 0
        if is_emergency:
            base_spike = rng.uniform(config.emergency_spike_min, config.emergency_spike_max)
            # Severity and outbreak intensify emergencies (accidents, respiratory, etc.)
            spike_multiplier = 1.0 + (1.25 * float(weather_severity)) + (0.75 * float(outbreak_intensity))
            emergency_spike = float(base_spike * spike_multiplier)
        else:
            emergency_spike = 0.0

        # Compose expected value
        expected = (
            config.base
            + baseline_shift
            + daily
            + seasonal
            + weekend_effect
            + weekday_profile
            + holiday_effect
            + weather_effect
        )

        expected *= (1.0 + outbreak_intensity)
        expected *= (1.0 - staff_shortage_impact)
        expected += emergency_spike

        noise = rng.gauss(0.0, config.noise_std)

        # Autocorrelation to make lags meaningful.
        raw_patients = expected + noise
        patients = (config.ar_strength * prev_patients) + ((1.0 - config.ar_strength) * raw_patients)

        # Capacity capping
        capped = 1 if patients > config.capacity else 0
        patients = _clamp(patients, 1.0, config.capacity)

        # Store patient counts as integers rounded UP (ceil), as requested.
        patients_int = int(math.ceil(patients))

        prev_patients = float(patients_int)

        # Primary scenario label (human readable)
        # Priority: capacity_capped > emergency > outbreak > storm/heatwave > holiday > staff shortage > normal
        scenario_primary = "normal"
        if capped:
            scenario_primary = "capacity_capped"
        elif is_emergency:
            scenario_primary = "emergency_spike"
        elif outbreak_idx >= 0:
            scenario_primary = "outbreak_period"
        elif (weather_code != 0) and (weather_severity >= 0.75):
            scenario_primary = "extreme_weather"
        elif is_holiday:
            scenario_primary = "holiday"
        elif staff_idx >= 0:
            scenario_primary = "staff_shortage"

        scenario_code = {
            "normal": 0,
            "holiday": 1,
            "extreme_weather": 2,
            "outbreak_period": 3,
            "staff_shortage": 4,
            "emergency_spike": 5,
            "capacity_capped": 6,
        }[scenario_primary]

        rows.append(
            {
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "patients": int(patients_int),
                # Keep numeric for compatibility with existing pipeline/training.
                "day_of_week": int(dow_idx),
                # Optional human-readable label for debugging/EDA.
                "day_of_week_name": dow_name,
                "month": int(month),
                "is_weekend": int(is_weekend),
                "holiday": int(is_holiday),
                "holiday_name": holiday_name or "random_or_none",
                "weather": int(weather_code),
                "weather_type": WEATHER_CODE_TO_TYPE.get(weather_code, "unknown"),
                "weather_severity": float(round(weather_severity, 3)),
                "capacity": float(config.capacity),
                "is_capped": int(capped),
                "is_emergency": int(is_emergency),
                "emergency_spike": float(round(emergency_spike, 2)),
                "is_outbreak": int(outbreak_idx >= 0),
                "outbreak_intensity": float(round(outbreak_intensity, 3)),
                "is_staff_shortage": int(staff_idx >= 0),
                "staff_shortage_impact": float(round(staff_shortage_impact, 3)),
                "scenario_primary": scenario_primary,
                "scenario_code": int(scenario_code),
            }
        )

    df = pd.DataFrame(rows)

    # Add labels (next hour and next day same hour)
    df["y_patients_t_plus_1"] = df["patients"].shift(-1)
    df["y_patients_t_plus_24"] = df["patients"].shift(-24)

    # Keep only the first config.hours rows (exact 1-year window) where labels are available
    df = df.iloc[: config.hours].copy().reset_index(drop=True)
    if df[["y_patients_t_plus_1", "y_patients_t_plus_24"]].isna().any().any():
        raise RuntimeError("Label generation failed; found NaNs in y columns within 1-year window.")

    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2025-01-01 00:00:00", help="Start datetime (YYYY-mm-dd HH:MM:SS)")
    p.add_argument("--hours", type=int, default=365 * 24, help="Number of hours to output (default 8760)")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--capacity", type=float, default=260.0, help="Capacity cap for patients")
    p.add_argument("--out", default="clean_data_1y_labeled.csv", help="Output CSV path")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.fromisoformat(args.start)
    cfg = GeneratorConfig(start=start, hours=int(args.hours), seed=int(args.seed), capacity=float(args.capacity))

    df = generate_labeled_year(cfg)
    df.to_csv(args.out, index=False)
    # Avoid Unicode issues on Windows cp1252 terminals.
    print(f"Saved {args.out}")
    print(f"Rows: {len(df)} | Columns: {len(df.columns)}")
    print("Scenario distribution (scenario_primary):")
    print(df["scenario_primary"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
