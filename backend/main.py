from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ml.features import (
    AniFeatureBuilder,
    MODEL_FEATURES,
    historical_status,
    normalize_ecosystem,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models"

HISTORY_PATH = DATA_DIR / "palay_history.csv"
WEATHER_PATH = DATA_DIR / "province_quarter_weather.csv"
MODEL_PATH = MODEL_DIR / "ani_xgboost_pipeline.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"

if not MODEL_PATH.exists():
    raise RuntimeError(
        f"Model file not found at {MODEL_PATH}. Run `python -m ml.train_model` first."
    )

history_df = pd.read_csv(HISTORY_PATH)
weather_df = pd.read_csv(WEATHER_PATH)
pipeline = joblib.load(MODEL_PATH)
metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
builder = AniFeatureBuilder(history_df, weather_df)

# Stable province -> region mapping from the processed agricultural dataset.
province_region = (
    history_df[["Province", "Region_Context"]]
    .drop_duplicates(subset=["Province"])
    .set_index("Province")["Region_Context"]
    .to_dict()
)

app = FastAPI(
    title="ANI Provincial Palay Yield Forecasting API",
    version=metadata.get("model_version", "0.1"),
    description=(
        "Backend API for the ANI academic machine-learning prototype. "
        "Forecasts are analytical estimates and are not official PSA crop forecasts."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ForecastRequest(BaseModel):
    province: str
    ecosystem: str
    target_year: int = Field(ge=2001, le=2100)
    target_quarter: int = Field(ge=1, le=4)


def _period_key(year: int, quarter: int) -> int:
    return year * 4 + quarter - 1


def _latest_period() -> tuple[int, int]:
    idx = (
        history_df["Year"].astype(int) * 4
        + history_df["Quarter_Number"].astype(int)
        - 1
    ).max()
    return int(idx // 4), int(idx % 4 + 1)


def _next_period(year: int, quarter: int) -> tuple[int, int]:
    idx = _period_key(year, quarter) + 1
    return int(idx // 4), int(idx % 4 + 1)


def _extra_context(
    province: str,
    ecosystem: str,
    target_year: int,
    target_quarter: int,
    feature_row: dict[str, Any],
) -> dict[str, Any]:
    eco = normalize_ecosystem(ecosystem)
    target_idx = _period_key(target_year, target_quarter)
    prior = history_df[
        (history_df["Province"] == province)
        & (history_df["Ecosystem"] == eco)
        & (
            history_df["Year"].astype(int) * 4
            + history_df["Quarter_Number"].astype(int)
            - 1
            < target_idx
        )
    ].copy()

    same_q = prior[
        prior["Quarter_Number"].astype(int) == int(target_quarter)
    ].sort_values("Year")

    lag8 = same_q[same_q["Year"].astype(int) == target_year - 2]
    lag4 = same_q[same_q["Year"].astype(int) == target_year - 1]

    def pct_change(new: float, old: float) -> float:
        if old == 0:
            return 0.0
        return (new - old) / old * 100.0

    prod_trend = 0.0
    area_trend = 0.0
    if not lag8.empty and not lag4.empty:
        prod_trend = pct_change(
            float(lag4.iloc[0]["Production_mt"]),
            float(lag8.iloc[0]["Production_mt"]),
        )
        area_trend = pct_change(
            float(lag4.iloc[0]["Area_Harvested_ha"]),
            float(lag8.iloc[0]["Area_Harvested_ha"]),
        )

    return {
        "previous_comparable_yield": float(feature_row["Yield_Lag4_mt_per_ha"]),
        "recent_yield_average": float(
            feature_row["Yield_Rolling4_Mean_mt_per_ha"]
        ),
        "lagged_production_trend": float(prod_trend),
        "lagged_area_trend": float(area_trend),
        "rainfall_indicator": (
            f'{feature_row["Rainfall_Lag1_mm"]:.1f} mm previous-quarter rainfall'
        ),
        "temperature_indicator": (
            f'{feature_row["T2M_Lag1_C"]:.1f} °C previous-quarter mean temperature'
        ),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_version": metadata.get("model_version"),
        "training_rows": metadata.get("training_rows"),
    }


@app.get("/meta")
def meta() -> dict[str, Any]:
    latest_year, latest_quarter = _latest_period()
    next_year, next_quarter = _next_period(latest_year, latest_quarter)

    return {
        "model": metadata,
        "provinces": sorted(history_df["Province"].dropna().unique().tolist()),
        "ecosystems": ["Irrigated", "Rainfed"],
        "latest_agricultural_period": {
            "year": latest_year,
            "quarter": latest_quarter,
        },
        "suggested_next_target": {
            "year": next_year,
            "quarter": next_quarter,
        },
        "province_regions": province_region,
    }


@app.get("/forecast-availability")
def forecast_availability(
    province: str = Query(...),
    ecosystem: str = Query(...),
) -> dict[str, Any]:
    """List future periods whose required lagged inputs currently exist."""
    if province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found in ANI data.")

    try:
        eco = normalize_ecosystem(ecosystem)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    latest_year, latest_quarter = _latest_period()
    first_idx = _period_key(latest_year, latest_quarter) + 1
    available = []
    # Look up to four years ahead. A period is offered only when the same
    # feature builder used by /predict confirms all required lags are present.
    for period_idx in range(first_idx, first_idx + 16):
        year, quarter = period_idx // 4, period_idx % 4 + 1
        result = builder.build(province, eco, year, quarter)
        if result.eligible:
            available.append({
                "year": year,
                "quarter": quarter,
                "priorQuarters": result.prior_total,
                "sameQuarterObservations": result.prior_same_quarter,
            })

    return {
        "province": province,
        "ecosystem": eco.replace(" Palay", ""),
        "latestAgriculturalPeriod": {
            "year": latest_year,
            "quarter": latest_quarter,
        },
        "availableTargets": available,
    }


@app.post("/predict")
def predict(request: ForecastRequest) -> dict[str, Any]:
    if request.province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found in ANI data.")

    try:
        ecosystem = normalize_ecosystem(request.ecosystem)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = builder.build(
        request.province,
        ecosystem,
        request.target_year,
        request.target_quarter,
    )

    if not result.eligible or result.row is None:
        return {
            "eligible": False,
            "message": (
                "Forecast unavailable — insufficient historical data or required "
                "lagged inputs are not yet available."
            ),
            "reason": result.reason,
            "province": request.province,
            "ecosystem": ecosystem.replace(" Palay", ""),
            "targetYear": request.target_year,
            "targetQuarter": request.target_quarter,
            "priorQuarters": result.prior_total,
            "sameQuarterObservations": result.prior_same_quarter,
        }

    feature_frame = pd.DataFrame([result.row], columns=MODEL_FEATURES)
    predicted = float(pipeline.predict(feature_frame)[0])

    context = builder.historical_context(
        request.province,
        ecosystem,
        request.target_year,
        request.target_quarter,
    )
    status = historical_status(predicted, context["q25"], context["q75"])
    diff_pct = (
        (predicted - context["historical_median"])
        / context["historical_median"]
        * 100.0
    )
    extra = _extra_context(
        request.province,
        ecosystem,
        request.target_year,
        request.target_quarter,
        result.row,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    forecast_id = (
        f"ANI-FC-{request.target_year}-Q{request.target_quarter}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )

    return {
        "eligible": True,
        "forecastId": forecast_id,
        "province": request.province,
        "region": province_region[request.province],
        "ecosystem": ecosystem.replace(" Palay", ""),
        "targetYear": request.target_year,
        "targetQuarter": request.target_quarter,
        "predictedYield": round(predicted, 3),
        "unit": "t/ha",
        "historicalMedian": round(context["historical_median"], 3),
        "q25": round(context["q25"], 3),
        "q75": round(context["q75"], 3),
        "historicalStatus": status,
        "percentDifferenceFromMedian": round(diff_pct, 1),
        # Compatibility fields for the current frontend result layout.
        "historicalAverage": round(context["historical_median"], 3),
        "historicalMin": round(context["q25"], 3),
        "historicalMax": round(context["q75"], 3),
        "previousComparableYield": round(
            extra["previous_comparable_yield"], 3
        ),
        "recentYieldAverage": round(extra["recent_yield_average"], 3),
        "laggedProductionTrend": round(extra["lagged_production_trend"], 1),
        "laggedAreaTrend": round(extra["lagged_area_trend"], 1),
        "rainfallIndicator": extra["rainfall_indicator"],
        "temperatureIndicator": extra["temperature_indicator"],
        "percentDifferenceFromAverage": round(diff_pct, 1),
        "dataPointsUsed": result.prior_total,
        "sameQuarterObservations": result.prior_same_quarter,
        "modelName": metadata.get("model_name"),
        "modelVersion": metadata.get("model_version"),
        "modelMode": "Trained XGBoost",
        "generatedAt": generated_at,
        "disclaimer": (
            "ANI is an ML-based analytical estimate and does not replace official "
            "PSA crop statistics or field-based agricultural assessment."
        ),
    }


@app.get("/historical")
def historical(
    province: str = Query(...),
    ecosystem: str = Query(...),
) -> dict[str, Any]:
    if province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found.")

    try:
        eco = normalize_ecosystem(ecosystem)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    records = history_df[
        (history_df["Province"] == province)
        & (history_df["Ecosystem"] == eco)
    ].copy()

    weather = weather_df[weather_df["Province"] == province].copy()

    merged = records.merge(
        weather,
        left_on=["Province", "Year", "Quarter_Number"],
        right_on=["Province", "Year", "Quarter"],
        how="left",
    ).sort_values(["Year", "Quarter_Number"])

    output = []
    for row in merged.itertuples(index=False):
        output.append(
            {
                "id": f"{province}-{eco}-{int(row.Year)}-Q{int(row.Quarter_Number)}",
                "province": province,
                "region": province_region[province],
                "year": int(row.Year),
                "quarter": int(row.Quarter_Number),
                "ecosystem": eco.replace(" Palay", ""),
                "productionVolume": float(row.Production_mt),
                "areaHarvested": float(row.Area_Harvested_ha),
                "yield": float(row.Yield_mt_per_ha),
                "rainfall": (
                    None if pd.isna(row.Rainfall_Sum_mm)
                    else float(row.Rainfall_Sum_mm)
                ),
                "avgTemperature": (
                    None if pd.isna(row.T2M_Mean_C)
                    else float(row.T2M_Mean_C)
                ),
                "relativeHumidity": (
                    None if pd.isna(row.RH2M_Mean_pct)
                    else float(row.RH2M_Mean_pct)
                ),
                "windSpeed": (
                    None if pd.isna(row.WS2M_Mean_m_s)
                    else float(row.WS2M_Mean_m_s)
                ),
            }
        )

    return {"records": output}


@app.get("/historical/all")
def historical_all() -> dict[str, Any]:
    merged = history_df.merge(
        weather_df,
        left_on=["Province", "Year", "Quarter_Number"],
        right_on=["Province", "Year", "Quarter"],
        how="left",
    ).sort_values(["Province", "Ecosystem", "Year", "Quarter_Number"])

    records = []
    for row in merged.itertuples(index=False):
        records.append(
            {
                "id": (
                    f"{row.Province}-{row.Ecosystem}-"
                    f"{int(row.Year)}-Q{int(row.Quarter_Number)}"
                ),
                "province": row.Province,
                "region": row.Region_Context,
                "year": int(row.Year),
                "quarter": int(row.Quarter_Number),
                "ecosystem": str(row.Ecosystem).replace(" Palay", ""),
                "productionVolume": float(row.Production_mt),
                "areaHarvested": float(row.Area_Harvested_ha),
                "yield": float(row.Yield_mt_per_ha),
                "rainfall": (
                    None if pd.isna(row.Rainfall_Sum_mm)
                    else float(row.Rainfall_Sum_mm)
                ),
                "avgTemperature": (
                    None if pd.isna(row.T2M_Mean_C)
                    else float(row.T2M_Mean_C)
                ),
                "relativeHumidity": (
                    None if pd.isna(row.RH2M_Mean_pct)
                    else float(row.RH2M_Mean_pct)
                ),
                "windSpeed": (
                    None if pd.isna(row.WS2M_Mean_m_s)
                    else float(row.WS2M_Mean_m_s)
                ),
            }
        )

    return {
        "records": records,
        "province_regions": province_region,
        "record_count": len(records),
    }


@app.get("/model-info")
def model_info() -> dict[str, Any]:
    return metadata
