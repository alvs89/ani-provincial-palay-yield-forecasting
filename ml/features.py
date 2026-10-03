from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

CATEGORICAL_FEATURES = ["Province", "Ecosystem", "Target_Quarter"]

NUMERIC_FEATURES = [
    "Yield_Lag1_mt_per_ha",
    "Yield_Lag4_mt_per_ha",
    "Yield_Rolling4_Mean_mt_per_ha",
    "Area_Lag4_ha",
    "Production_Lag4_mt",
    "Rainfall_Lag1_mm",
    "T2M_Lag1_C",
    "RH2M_Lag1_pct",
    "WS2M_Lag1_m_s",
    "Rainfall_Lag4_mm",
    "T2M_Lag4_C",
    "RH2M_Lag4_pct",
    "WS2M_Lag4_m_s",
]

MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "Target_Yield_mt_per_ha"

MIN_PRIOR_QUARTERS = 40
MIN_SAME_QUARTER_OBSERVATIONS = 8


def normalize_ecosystem(value: str) -> str:
    value = value.strip().lower()
    aliases = {
        "irrigated": "Irrigated Palay",
        "irrigated palay": "Irrigated Palay",
        "rainfed": "Rainfed Palay",
        "rainfed palay": "Rainfed Palay",
    }
    if value not in aliases:
        raise ValueError("Ecosystem must be Irrigated or Rainfed.")
    return aliases[value]


def period_key(year: int, quarter: int) -> int:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("Quarter must be 1, 2, 3, or 4.")
    return year * 4 + (quarter - 1)


def period_from_key(key: int) -> tuple[int, int]:
    return key // 4, (key % 4) + 1


def previous_period(year: int, quarter: int, lag: int) -> tuple[int, int]:
    return period_from_key(period_key(year, quarter) - lag)


@dataclass
class FeatureBuildResult:
    eligible: bool
    reason: str | None
    row: dict[str, Any] | None
    prior_total: int
    prior_same_quarter: int


class AniFeatureBuilder:
    def __init__(self, history_df: pd.DataFrame, weather_df: pd.DataFrame):
        self.history = history_df.copy()
        self.weather = weather_df.copy()

        self.history["Period_Key"] = (
            self.history["Year"].astype(int) * 4
            + self.history["Quarter_Number"].astype(int)
            - 1
        )

        self.history_lookup = {
            (r.Province, r.Ecosystem, int(r.Year), int(r.Quarter_Number)): r
            for r in self.history.itertuples(index=False)
        }
        self.weather_lookup = {
            (r.Province, int(r.Year), int(r.Quarter)): r
            for r in self.weather.itertuples(index=False)
        }

    def _history_record(self, province: str, ecosystem: str, year: int, quarter: int):
        return self.history_lookup.get((province, ecosystem, year, quarter))

    def _weather_record(self, province: str, year: int, quarter: int):
        return self.weather_lookup.get((province, year, quarter))

    def build(
        self,
        province: str,
        ecosystem: str,
        target_year: int,
        target_quarter: int,
    ) -> FeatureBuildResult:
        ecosystem = normalize_ecosystem(ecosystem)
        target_key = period_key(target_year, target_quarter)

        prior = self.history[
            (self.history["Province"] == province)
            & (self.history["Ecosystem"] == ecosystem)
            & (self.history["Period_Key"] < target_key)
        ].copy()

        prior_total = int(len(prior))
        prior_same_quarter = int(
            (prior["Quarter_Number"].astype(int) == int(target_quarter)).sum()
        )

        if prior_total < MIN_PRIOR_QUARTERS:
            return FeatureBuildResult(
                False,
                f"Only {prior_total} usable prior quarters are available; at least {MIN_PRIOR_QUARTERS} are required.",
                None,
                prior_total,
                prior_same_quarter,
            )

        if prior_same_quarter < MIN_SAME_QUARTER_OBSERVATIONS:
            return FeatureBuildResult(
                False,
                f"Only {prior_same_quarter} prior Q{target_quarter} observations are available; at least {MIN_SAME_QUARTER_OBSERVATIONS} are required.",
                None,
                prior_total,
                prior_same_quarter,
            )

        lag_records = []
        for lag in (1, 2, 3, 4):
            y, q = previous_period(target_year, target_quarter, lag)
            record = self._history_record(province, ecosystem, y, q)
            if record is None:
                return FeatureBuildResult(
                    False,
                    f"Required historical agricultural record for lag {lag} ({y} Q{q}) is missing.",
                    None,
                    prior_total,
                    prior_same_quarter,
                )
            lag_records.append(record)

        lag1 = lag_records[0]
        lag4 = lag_records[3]

        y1, q1 = previous_period(target_year, target_quarter, 1)
        y4, q4 = previous_period(target_year, target_quarter, 4)
        weather_lag1 = self._weather_record(province, y1, q1)
        weather_lag4 = self._weather_record(province, y4, q4)

        if weather_lag1 is None:
            return FeatureBuildResult(
                False,
                f"Required lag-1 weather record ({y1} Q{q1}) is missing.",
                None,
                prior_total,
                prior_same_quarter,
            )
        if weather_lag4 is None:
            return FeatureBuildResult(
                False,
                f"Required lag-4 weather record ({y4} Q{q4}) is missing.",
                None,
                prior_total,
                prior_same_quarter,
            )

        rolling4 = float(np.mean([float(r.Yield_mt_per_ha) for r in lag_records]))

        row = {
            "Province": province,
            "Ecosystem": ecosystem,
            "Target_Quarter": int(target_quarter),
            "Yield_Lag1_mt_per_ha": float(lag1.Yield_mt_per_ha),
            "Yield_Lag4_mt_per_ha": float(lag4.Yield_mt_per_ha),
            "Yield_Rolling4_Mean_mt_per_ha": rolling4,
            "Area_Lag4_ha": float(lag4.Area_Harvested_ha),
            "Production_Lag4_mt": float(lag4.Production_mt),
            "Rainfall_Lag1_mm": float(weather_lag1.Rainfall_Sum_mm),
            "T2M_Lag1_C": float(weather_lag1.T2M_Mean_C),
            "RH2M_Lag1_pct": float(weather_lag1.RH2M_Mean_pct),
            "WS2M_Lag1_m_s": float(weather_lag1.WS2M_Mean_m_s),
            "Rainfall_Lag4_mm": float(weather_lag4.Rainfall_Sum_mm),
            "T2M_Lag4_C": float(weather_lag4.T2M_Mean_C),
            "RH2M_Lag4_pct": float(weather_lag4.RH2M_Mean_pct),
            "WS2M_Lag4_m_s": float(weather_lag4.WS2M_Mean_m_s),
        }

        return FeatureBuildResult(
            True, None, row, prior_total, prior_same_quarter
        )

    def historical_context(
        self,
        province: str,
        ecosystem: str,
        target_year: int,
        target_quarter: int,
    ) -> dict[str, Any]:
        ecosystem = normalize_ecosystem(ecosystem)
        target_key = period_key(target_year, target_quarter)

        same_quarter = self.history[
            (self.history["Province"] == province)
            & (self.history["Ecosystem"] == ecosystem)
            & (self.history["Quarter_Number"].astype(int) == int(target_quarter))
            & (self.history["Period_Key"] < target_key)
        ]["Yield_mt_per_ha"].astype(float)

        if len(same_quarter) < MIN_SAME_QUARTER_OBSERVATIONS:
            raise ValueError(
                "Not enough prior same-quarter observations to calculate historical context."
            )

        return {
            "historical_median": float(same_quarter.median()),
            "q25": float(same_quarter.quantile(0.25)),
            "q75": float(same_quarter.quantile(0.75)),
            "same_quarter_observations": int(len(same_quarter)),
        }


def historical_status(predicted_yield: float, q25: float, q75: float) -> str:
    if predicted_yield < q25:
        return "Below Typical Historical Range"
    if predicted_yield > q75:
        return "Above Typical Historical Range"
    return "Within Typical Historical Range"
