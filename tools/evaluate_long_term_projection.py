from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "models" / "long_term_projection_metadata.json"
HISTORY = ROOT / "data" / "processed" / "palay_history.csv"
WEATHER = ROOT / "data" / "processed" / "province_quarter_weather.csv"
CLIMATE_COLS = [
    "Rainfall_Sum_mm",
    "T2M_Mean_C",
    "RH2M_Mean_pct",
    "WS2M_Mean_m_s",
]
K = 5


def main() -> None:
    history = pd.read_csv(HISTORY)
    weather = pd.read_csv(WEATHER)
    history["Ecosystem"] = history["Ecosystem"].str.replace(
        " Palay", "", regex=False
    )
    data = history.merge(
        weather,
        left_on=["Province", "Year", "Quarter_Number"],
        right_on=["Province", "Year", "Quarter"],
        how="inner",
    )
    data = data[
        (data["Year"] >= 2001)
        & (data["Year"] <= 2025)
        & data["Yield_mt_per_ha"].notna()
    ].copy()

    predictions = []
    actuals = []
    naive_predictions = []
    naive_actuals = []

    keys = ["Province", "Ecosystem", "Quarter_Number"]
    for _, group in data.groupby(keys, sort=False):
        train = group[group["Year"] <= 2020].dropna(
            subset=CLIMATE_COLS + ["Yield_mt_per_ha"]
        )
        test = group[(group["Year"] >= 2021) & (group["Year"] <= 2025)].dropna(
            subset=CLIMATE_COLS + ["Yield_mt_per_ha"]
        )
        if len(train) < K or test.empty:
            continue

        climate = train[CLIMATE_COLS].to_numpy(dtype=float)
        yields = train["Yield_mt_per_ha"].to_numpy(dtype=float)
        med = np.median(climate, axis=0)
        mad = np.median(np.abs(climate - med), axis=0)
        mad[mad == 0] = 1.0

        year_to_yield = {
            int(row.Year): float(row.Yield_mt_per_ha)
            for _, row in group.iterrows()
        }
        for _, row in test.iterrows():
            target = row[CLIMATE_COLS].to_numpy(dtype=float)
            distance = np.sqrt(np.sum(((climate - target) / mad) ** 2, axis=1))
            idx = np.argsort(distance)[:K]
            weights = 1.0 / (distance[idx] + 0.5)
            predictions.append(float(np.average(yields[idx], weights=weights)))
            actuals.append(float(row["Yield_mt_per_ha"]))

            previous = year_to_yield.get(int(row["Year"]) - 1)
            if previous is not None:
                naive_predictions.append(previous)
                naive_actuals.append(float(row["Yield_mt_per_ha"]))

    analog = {
        "period": "2021-2025 chronological check",
        "training_period": "2001-2020",
        "eligible_rows": len(actuals),
        "mae": float(mean_absolute_error(actuals, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(actuals, predictions))),
        "r2": float(r2_score(actuals, predictions)),
    }
    naive = {
        "definition": "previous-year same-quarter yield",
        "eligible_rows": len(naive_actuals),
        "mae": float(mean_absolute_error(naive_actuals, naive_predictions)),
        "rmse": float(np.sqrt(mean_squared_error(naive_actuals, naive_predictions))),
        "r2": float(r2_score(naive_actuals, naive_predictions)),
    }
    metadata = {
        "name": "ANI Experimental Long-Term Climate-Analog Projection",
        "version": "ANI-LTP-CLIMATE-ANALOG-v1",
        "method": (
            "Five nearest historical climate analogs within the same province, "
            "ecosystem, and calendar quarter. Distances use median-absolute-"
            "deviation scaling across rainfall, mean temperature, relative "
            "humidity, and wind speed."
        ),
        "validation": analog,
        "seasonal_naive_comparison": naive,
        "deployment_status": "Experimental scenario projection only",
        "validation_interpretation": (
            "The climate-analog method is less accurate than ANI's short-term "
            "previous-year seasonal baseline on the 2021-2025 check. It is "
            "therefore not presented as a replacement for the validated "
            "next-quarter XGBoost forecast. Its purpose is conditional long-term "
            "scenario exploration when future lagged agricultural inputs do not exist."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
