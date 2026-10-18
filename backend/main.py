from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
    normalize_province_name,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models"

HISTORY_PATH = DATA_DIR / "palay_history.csv"
WEATHER_PATH = DATA_DIR / "province_quarter_weather.csv"
SATELLITE_PATH = DATA_DIR / "province_quarter_satellite.csv"
MARKET_PATH = DATA_DIR / "palay_farmgate_prices.csv"
PAGASA_AGRI_WEATHER_PATH = DATA_DIR / "pagasa_regional_agri_weather.json"
PAGASA_CLIMATE_RISK_PATH = DATA_DIR / "pagasa_climate_risk.json"
AGRICULTURAL_SOURCE_PATH = DATA_DIR / "psa_2026_q1_q2_source_records.csv"
MODEL_PATH = MODEL_DIR / "ani_xgboost_pipeline.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"
ENVIRONMENTAL_DECISION_SUPPORT_PATH = ROOT / "outputs" / "environmental_decision_support.json"
SATELLITE_EVALUATION_PATH = (
    ROOT / "outputs" / "satellite_evaluation" / "summary.json"
)

if not MODEL_PATH.exists():
    raise RuntimeError(
        f"Model file not found at {MODEL_PATH}. Run `python -m ml.train_model` first."
    )

history_df = pd.read_csv(HISTORY_PATH)
weather_df = pd.read_csv(WEATHER_PATH)
satellite_df = (
    pd.read_csv(SATELLITE_PATH)
    if SATELLITE_PATH.is_file()
    else pd.DataFrame()
)
market_df = (
    pd.read_csv(MARKET_PATH)
    if MARKET_PATH.is_file()
    else pd.DataFrame()
)
pagasa_agri_weather = (
    json.loads(PAGASA_AGRI_WEATHER_PATH.read_text(encoding="utf-8"))
    if PAGASA_AGRI_WEATHER_PATH.is_file()
    else None
)
pagasa_climate_risk = (
    json.loads(PAGASA_CLIMATE_RISK_PATH.read_text(encoding="utf-8"))
    if PAGASA_CLIMATE_RISK_PATH.is_file()
    else None
)
satellite_evaluation = (
    json.loads(SATELLITE_EVALUATION_PATH.read_text(encoding="utf-8"))
    if SATELLITE_EVALUATION_PATH.is_file()
    else None
)
agricultural_source_df = (
    pd.read_csv(AGRICULTURAL_SOURCE_PATH)
    if AGRICULTURAL_SOURCE_PATH.is_file()
    else pd.DataFrame()
)
pipeline = joblib.load(MODEL_PATH)
metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
builder = AniFeatureBuilder(history_df, weather_df)

# Province -> region mapping follows the most recent integrated agricultural record
# so administrative changes are reflected in the current interface.
province_region = (
    history_df.sort_values(["Year", "Quarter_Number"])
    [["Province", "Region_Context"]]
    .drop_duplicates(subset=["Province"], keep="last")
    .set_index("Province")["Region_Context"]
    .to_dict()
)

# Current PSA administrative context that may not appear in usable yield rows
# when the latest province-quarter has no reportable harvested-area observation.
province_region.update(
    {
        "Negros Occidental": "NEGROS ISLAND REGION",
        "Negros Oriental": "NEGROS ISLAND REGION",
        "Siquijor": "NEGROS ISLAND REGION",
        "Sulu": "REGION IX (ZAMBOANGA PENINSULA)",
    }
)

app = FastAPI(
    title="ANI Provincial Palay Yield Forecasting API",
    version=metadata.get("model_version", "0.1"),
    description=(
        "Backend API for the ANI Provincial Palay Yield Forecasting System. "
        "Model results are analytical estimates and are not official PSA crop statistics."
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

PHILIPPINE_TIMEZONE_NAME = "Asia/Manila"
PHILIPPINE_TIMEZONE = ZoneInfo(PHILIPPINE_TIMEZONE_NAME)
TEMPORAL_RESULT_TYPES = {
    "PROSPECTIVE_FORECAST": "Prospective Forecast",
    "CURRENT_QUARTER_ESTIMATE": "Current-Quarter Estimate",
    "RETROSPECTIVE_ESTIMATE": "Retrospective Estimate",
}
MIN_SATELLITE_SEASONAL_OBSERVATIONS = 5
SATELLITE_CONTEXT_SOURCE = "NASA MODIS/Terra MOD13A1 Collection 6.1"


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


def _latest_weather_period() -> tuple[int, int]:
    idx = (
        weather_df["Year"].astype(int) * 4
        + weather_df["Quarter"].astype(int)
        - 1
    ).max()
    return int(idx // 4), int(idx % 4 + 1)


def _latest_satellite_period() -> tuple[int, int] | None:
    if satellite_df.empty:
        return None
    idx = (
        satellite_df["Year"].astype(int) * 4
        + satellite_df["Quarter"].astype(int)
        - 1
    ).max()
    return int(idx // 4), int(idx % 4 + 1)



def _latest_market_period() -> tuple[int, int] | None:
    if market_df.empty:
        return None
    ordered = market_df.sort_values(["Year", "Month_Number"])
    row = ordered.iloc[-1]
    return int(row["Year"]), int(row["Month_Number"])


def _historical_benchmark_context(
    province: str,
    ecosystem: str,
    target_year: int,
    target_quarter: int,
    predicted_yield: float,
) -> dict[str, Any]:
    eco = normalize_ecosystem(ecosystem)
    target_idx = _period_key(target_year, target_quarter)
    province_prior = history_df[
        (history_df["Province"] == province)
        & (history_df["Ecosystem"] == eco)
        & (history_df["Quarter_Number"].astype(int) == int(target_quarter))
        & (
            history_df["Year"].astype(int) * 4
            + history_df["Quarter_Number"].astype(int)
            - 1
            < target_idx
        )
    ].copy()
    values = province_prior["Yield_mt_per_ha"].astype(float)

    current_region = province_region.get(province)
    region_provinces = [
        p for p, r in province_region.items() if r == current_region
    ]
    region_prior = history_df[
        history_df["Province"].isin(region_provinces)
        & (history_df["Ecosystem"] == eco)
        & (history_df["Quarter_Number"].astype(int) == int(target_quarter))
        & (
            history_df["Year"].astype(int) * 4
            + history_df["Quarter_Number"].astype(int)
            - 1
            < target_idx
        )
    ]["Yield_mt_per_ha"].astype(float)

    recent = province_prior[
        province_prior["Year"].astype(int) >= int(target_year) - 5
    ]["Yield_mt_per_ha"].astype(float)

    province_median = float(values.median()) if not values.empty else None
    upper_quartile = float(values.quantile(0.75)) if not values.empty else None
    regional_median = (
        float(region_prior.median()) if not region_prior.empty else None
    )
    recent_median = float(recent.median()) if not recent.empty else None
    percentile = (
        float((values <= predicted_yield).mean() * 100.0)
        if not values.empty
        else None
    )
    regional_diff = (
        (predicted_yield - regional_median) / regional_median * 100.0
        if regional_median not in {None, 0}
        else None
    )

    return {
        "provinceSameQuarterMedian": (
            round(province_median, 3) if province_median is not None else None
        ),
        "provinceRecentFiveYearSameQuarterMedian": (
            round(recent_median, 3) if recent_median is not None else None
        ),
        "provinceUpperQuartileBenchmark": (
            round(upper_quartile, 3) if upper_quartile is not None else None
        ),
        "attainableHistoricalBenchmark": (
            round(upper_quartile, 3) if upper_quartile is not None else None
        ),
        "gapFromAttainableBenchmarkMtHa": (
            round(predicted_yield - upper_quartile, 3)
            if upper_quartile is not None
            else None
        ),
        "gapFromAttainableBenchmarkPct": (
            round((predicted_yield - upper_quartile) / upper_quartile * 100.0, 1)
            if upper_quartile not in {None, 0}
            else None
        ),
        "regionalSameQuarterMedian": (
            round(regional_median, 3) if regional_median is not None else None
        ),
        "differenceFromRegionalMedianPct": (
            round(regional_diff, 1) if regional_diff is not None else None
        ),
        "historicalPercentile": (
            round(percentile, 1) if percentile is not None else None
        ),
        "provinceSameQuarterObservations": int(len(values)),
        "regionalSameQuarterObservations": int(len(region_prior)),
        "region": current_region,
        "benchmarkType": "Historical high-yield benchmark (75th percentile), not an agronomic optimum",
        "source": "Processed PSA OpenSTAT palay production and harvested-area history",
        "affectsYieldEstimate": False,
    }


def _associated_signals_context(
    province: str,
    target_year: int,
    target_quarter: int,
    feature_row: dict[str, Any],
    extra: dict[str, Any],
    satellite: dict[str, Any],
) -> dict[str, Any]:
    target_idx = _period_key(target_year, target_quarter)
    reference_idx = target_idx - 1
    reference_year = int(reference_idx // 4)
    reference_quarter = int(reference_idx % 4 + 1)
    historical_weather = weather_df[
        (weather_df["Province"] == province)
        & (weather_df["Quarter"].astype(int) == reference_quarter)
        & (
            weather_df["Year"].astype(int) * 4
            + weather_df["Quarter"].astype(int)
            - 1
            < reference_idx
        )
    ]

    def median(column: str) -> float | None:
        x = pd.to_numeric(historical_weather[column], errors="coerce").dropna()
        return float(x.median()) if not x.empty else None

    def pct(value: float, baseline: float | None) -> float | None:
        if baseline in {None, 0}:
            return None
        return (float(value) - float(baseline)) / float(baseline) * 100.0

    rainfall = float(feature_row["Rainfall_Lag1_mm"])
    temperature = float(feature_row["T2M_Lag1_C"])
    rh = float(feature_row["RH2M_Lag1_pct"])
    wind = float(feature_row["WS2M_Lag1_m_s"])
    rainfall_median = median("Rainfall_Sum_mm")
    temp_median = median("T2M_Mean_C")
    rh_median = median("RH2M_Mean_pct")
    wind_median = median("WS2M_Mean_m_s")

    return {
        "referencePeriod": f"Q{reference_quarter} {reference_year}",
        "sameQuarterProductionChangePct": round(
            float(extra["lagged_production_trend"]), 1
        ),
        "sameQuarterHarvestedAreaChangePct": round(
            float(extra["lagged_area_trend"]), 1
        ),
        "rainfall": {
            "valueMm": round(rainfall, 1),
            "seasonalMedianMm": (
                round(rainfall_median, 1) if rainfall_median is not None else None
            ),
            "differenceFromSeasonalMedianPct": (
                round(pct(rainfall, rainfall_median), 1)
                if pct(rainfall, rainfall_median) is not None
                else None
            ),
        },
        "temperature": {
            "valueC": round(temperature, 1),
            "seasonalMedianC": (
                round(temp_median, 1) if temp_median is not None else None
            ),
            "differenceFromSeasonalMedianC": (
                round(temperature - temp_median, 1)
                if temp_median is not None
                else None
            ),
        },
        "relativeHumidity": {
            "valuePct": round(rh, 1),
            "seasonalMedianPct": round(rh_median, 1) if rh_median is not None else None,
        },
        "windSpeed": {
            "valueMS": round(wind, 1),
            "seasonalMedianMS": (
                round(wind_median, 1) if wind_median is not None else None
            ),
        },
        "satelliteNdviDifferenceFromSeasonalMedianPct": (
            satellite.get("ndviPercentDifferenceFromMedian")
            if satellite.get("comparisonAvailable")
            else None
        ),
        "interpretationGuardrail": (
            "These are associated pre-target conditions and historical changes. "
            "They do not establish that any one factor caused the yield outcome."
        ),
        "affectsYieldEstimate": False,
    }



def _yield_pattern_context(
    province: str,
    ecosystem: str,
    target_year: int,
    target_quarter: int,
    predicted_yield: float,
) -> dict[str, Any]:
    """Summarize pre-target historical patterns without changing model inference."""
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
    prior["Yield_mt_per_ha"] = pd.to_numeric(
        prior["Yield_mt_per_ha"], errors="coerce"
    )
    prior = prior.dropna(subset=["Yield_mt_per_ha"])

    same_q = prior[
        prior["Quarter_Number"].astype(int) == int(target_quarter)
    ].sort_values("Year")

    def trend_pct_per_year(frame: pd.DataFrame) -> float | None:
        if len(frame) < 6:
            return None
        x = frame["Year"].astype(float)
        y = frame["Yield_mt_per_ha"].astype(float)
        x_centered = x - x.mean()
        denom = float((x_centered**2).sum())
        mean_y = float(y.mean())
        if denom <= 0 or mean_y == 0:
            return None
        slope = float((x_centered * (y - y.mean())).sum() / denom)
        return slope / mean_y * 100.0

    long_term_trend = trend_pct_per_year(same_q)

    recent_change = None
    if len(same_q) >= 6:
        recent3 = float(same_q.tail(3)["Yield_mt_per_ha"].median())
        previous3 = float(same_q.tail(6).head(3)["Yield_mt_per_ha"].median())
        if previous3 != 0:
            recent_change = (recent3 - previous3) / previous3 * 100.0

    seasonal_medians = (
        prior.groupby("Quarter_Number")["Yield_mt_per_ha"].median().dropna()
    )
    seasonal_rank = None
    target_typical = None
    if int(target_quarter) in seasonal_medians.index and not seasonal_medians.empty:
        target_typical = float(seasonal_medians.loc[int(target_quarter)])
        ordered = seasonal_medians.sort_values(ascending=False)
        seasonal_rank = int(list(ordered.index).index(int(target_quarter)) + 1)

    percentile = (
        float((same_q["Yield_mt_per_ha"] <= predicted_yield).mean() * 100.0)
        if not same_q.empty
        else None
    )
    if percentile is None:
        anomaly = "Insufficient history"
    elif percentile <= 10:
        anomaly = "Unusually Low vs Historical Same-Quarter Values"
    elif percentile <= 25:
        anomaly = "Below Typical Same-Quarter Range"
    elif percentile < 75:
        anomaly = "Within Typical Same-Quarter Range"
    elif percentile < 90:
        anomaly = "Above Typical Same-Quarter Range"
    else:
        anomaly = "Unusually High vs Historical Same-Quarter Values"

    if long_term_trend is None:
        trend_direction = "Insufficient history"
    elif abs(long_term_trend) < 0.5:
        trend_direction = "Broadly Stable"
    elif long_term_trend > 0:
        trend_direction = "Long-Term Increase"
    else:
        trend_direction = "Long-Term Decline"

    return {
        "available": not same_q.empty,
        "sameQuarterObservations": int(len(same_q)),
        "longTermSameQuarterTrendPctPerYear": (
            round(long_term_trend, 2) if long_term_trend is not None else None
        ),
        "longTermTrendDirection": trend_direction,
        "recentThreeVsPreviousThreePct": (
            round(recent_change, 1) if recent_change is not None else None
        ),
        "historicalPercentile": (
            round(percentile, 1) if percentile is not None else None
        ),
        "anomalyStatus": anomaly,
        "targetQuarterHistoricalMedian": (
            round(target_typical, 3) if target_typical is not None else None
        ),
        "seasonalQuarterRank": seasonal_rank,
        "seasonalQuarterCount": int(len(seasonal_medians)),
        "interpretation": (
            "Patterns are calculated only from observations available before the "
            "target period. They describe historical behavior and do not establish "
            "the causes of a yield change."
        ),
        "affectsYieldEstimate": False,
    }


def _vegetation_yield_relationship(
    province: str,
    ecosystem: str,
    target_year: int,
    target_quarter: int,
) -> dict[str, Any]:
    """Exploratory province-level cropland vegetation/yield associations."""
    base = {
        "available": False,
        "source": SATELLITE_CONTEXT_SOURCE,
        "affectsYieldEstimate": False,
        "analysisType": "Exploratory association; not causal",
    }
    if satellite_df.empty:
        return {**base, "reason": "Satellite vegetation data are unavailable."}

    eco = normalize_ecosystem(ecosystem)
    target_idx = _period_key(target_year, target_quarter)
    yields = history_df[
        (history_df["Province"] == province)
        & (history_df["Ecosystem"] == eco)
        & (
            history_df["Year"].astype(int) * 4
            + history_df["Quarter_Number"].astype(int)
            - 1
            < target_idx
        )
    ][["Year", "Quarter_Number", "Yield_mt_per_ha"]].copy()
    sats = satellite_df[
        (satellite_df["Province"] == province)
        & (
            satellite_df["Year"].astype(int) * 4
            + satellite_df["Quarter"].astype(int)
            - 1
            < target_idx
        )
    ][["Year", "Quarter", "Cropland_NDVI_Mean", "Cropland_EVI_Mean"]].copy()

    merged = yields.merge(
        sats,
        left_on=["Year", "Quarter_Number"],
        right_on=["Year", "Quarter"],
        how="inner",
    )
    for col in ["Yield_mt_per_ha", "Cropland_NDVI_Mean", "Cropland_EVI_Mean"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.dropna(
        subset=["Yield_mt_per_ha", "Cropland_NDVI_Mean", "Cropland_EVI_Mean"]
    )
    if len(merged) < 12:
        return {
            **base,
            "reason": "Fewer than 12 matched historical vegetation-yield observations are available.",
            "matchedObservations": int(len(merged)),
        }

    def correlation(x: pd.Series, y: pd.Series) -> float | None:
        if x.nunique() < 2 or y.nunique() < 2:
            return None
        value = x.corr(y)
        return float(value) if pd.notna(value) else None

    def seasonal_adjusted_corr(column: str) -> float | None:
        work = merged[["Quarter_Number", "Yield_mt_per_ha", column]].copy()
        yield_anomaly = work["Yield_mt_per_ha"] - work.groupby(
            "Quarter_Number"
        )["Yield_mt_per_ha"].transform("median")
        veg_anomaly = work[column] - work.groupby(
            "Quarter_Number"
        )[column].transform("median")
        return correlation(yield_anomaly, veg_anomaly)

    def describe(r: float | None) -> str:
        if r is None:
            return "Unavailable"
        a = abs(r)
        strength = (
            "Very weak" if a < 0.20 else
            "Weak" if a < 0.40 else
            "Moderate" if a < 0.60 else
            "Strong" if a < 0.80 else
            "Very strong"
        )
        direction = "positive" if r > 0 else "negative" if r < 0 else "neutral"
        return f"{strength} {direction} association"

    ndvi_raw = correlation(merged["Yield_mt_per_ha"], merged["Cropland_NDVI_Mean"])
    evi_raw = correlation(merged["Yield_mt_per_ha"], merged["Cropland_EVI_Mean"])
    ndvi_seasonal = seasonal_adjusted_corr("Cropland_NDVI_Mean")
    evi_seasonal = seasonal_adjusted_corr("Cropland_EVI_Mean")

    return {
        **base,
        "available": True,
        "matchedObservations": int(len(merged)),
        "ndviPearson": round(ndvi_raw, 3) if ndvi_raw is not None else None,
        "eviPearson": round(evi_raw, 3) if evi_raw is not None else None,
        "ndviSeasonallyAdjustedCorrelation": (
            round(ndvi_seasonal, 3) if ndvi_seasonal is not None else None
        ),
        "eviSeasonallyAdjustedCorrelation": (
            round(evi_seasonal, 3) if evi_seasonal is not None else None
        ),
        "ndviInterpretation": describe(ndvi_seasonal),
        "eviInterpretation": describe(evi_seasonal),
        "guardrail": (
            "MODIS indicators are province-level cropland summaries, not rice-only "
            "field measurements. Correlation can show association but cannot prove "
            "that vegetation conditions caused a yield change."
        ),
    }


def _farmer_guidance_context(
    associated: dict[str, Any],
    benchmark: dict[str, Any],
    agri_weather: dict[str, Any],
    climate_risk: dict[str, Any],
) -> dict[str, Any]:
    """Generate transparent monitoring guidance, not agronomic prescriptions."""
    items: list[dict[str, str]] = []

    rain_diff = (associated.get("rainfall") or {}).get(
        "differenceFromSeasonalMedianPct"
    )
    temp_diff = (associated.get("temperature") or {}).get(
        "differenceFromSeasonalMedianC"
    )
    ndvi_diff = associated.get("satelliteNdviDifferenceFromSeasonalMedianPct")
    percentile = benchmark.get("historicalPercentile")

    if rain_diff is not None and float(rain_diff) <= -20:
        items.append({
            "title": "Review water availability",
            "detail": (
                "Pre-target rainfall was notably below its seasonal median. "
                "Check current PAGASA rainfall information and local irrigation "
                "availability before water-sensitive farm operations."
            ),
            "basis": "ANI historical rainfall signal + official PAGASA context",
        })
    elif rain_diff is not None and float(rain_diff) >= 30:
        items.append({
            "title": "Monitor excess-rainfall impacts",
            "detail": (
                "Pre-target rainfall was well above its seasonal median. Review "
                "drainage, field access, and current PAGASA rainfall advisories."
            ),
            "basis": "ANI historical rainfall signal + official PAGASA context",
        })

    if temp_diff is not None and float(temp_diff) >= 1.0:
        items.append({
            "title": "Monitor warmer-than-usual conditions",
            "detail": (
                "Pre-target temperature was above its seasonal median. Pay extra "
                "attention to crop stage, water condition, and current PAGASA "
                "temperature guidance."
            ),
            "basis": "ANI temperature signal + official PAGASA context",
        })

    if ndvi_diff is not None and float(ndvi_diff) <= -7.5:
        items.append({
            "title": "Inspect possible vegetation stress",
            "detail": (
                "Province-level cropland greenness was below its seasonal median. "
                "Use field inspection to check whether rice areas show stress, pest, "
                "water, or management issues; the satellite signal is not a diagnosis."
            ),
            "basis": "MODIS cropland vegetation context",
        })

    if percentile is not None and float(percentile) <= 25:
        items.append({
            "title": "Review the low historical position",
            "detail": (
                "The estimate is in the lower part of this province's same-quarter "
                "history. Compare current field conditions with recent better-performing "
                "same-season years before deciding on interventions."
            ),
            "basis": "PSA historical yield benchmark",
        })

    if agri_weather.get("available") and agri_weather.get("farmOperations"):
        operations = ", ".join(agri_weather.get("farmOperations", [])[:5])
        items.append({
            "title": "Check current PAGASA farm-operation guidance",
            "detail": f"Current regional PAGASA guidance highlights: {operations}.",
            "basis": "DOST-PAGASA 10-Day Regional Agri-Weather Information",
        })

    if climate_risk.get("available"):
        drought = climate_risk.get("droughtAssessment") or {}
        status = str(drought.get("status") or "").strip()
        if status and status.lower() not in {"normal", "no drought", "none", "not affected", "not affected by drought"}:
            items.append({
                "title": "Review official climate-risk status",
                "detail": (
                    f"PAGASA's latest provincial drought assessment reports: {status}. "
                    "Use the official drought outlook together with short-term weather "
                    "information for planning."
                ),
                "basis": "DOST-PAGASA climate-risk context",
            })

    if not items:
        items.append({
            "title": "Continue routine monitoring",
            "detail": (
                "ANI did not detect a large pre-target deviation among the currently "
                "integrated signals. Continue checking field conditions and the latest "
                "official PAGASA advisories."
            ),
            "basis": "ANI contextual screening + official PAGASA context",
        })

    return {
        "available": True,
        "items": items[:5],
        "guardrail": (
            "These are monitoring and planning prompts, not field-specific agronomic "
            "prescriptions. Verify conditions locally and follow official/local "
            "agricultural guidance before acting."
        ),
        "affectsYieldEstimate": False,
    }



def _market_context(province: str) -> dict[str, Any]:
    base = {
        "available": False,
        "source": "PSA OpenSTAT Farm Price Survey for Palay",
        "sourceUrl": (
            "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/"
            "DB__2M__NFG/0032M4AFN01.px/"
        ),
        "affectsYieldEstimate": False,
    }
    if market_df.empty:
        return {**base, "reason": "Farmgate-price data are unavailable."}

    rows = market_df[market_df["Province"] == province].copy()
    if rows.empty:
        return {
            **base,
            "reason": "No provincial palay farmgate-price record is available.",
        }

    preferred = "Palay [Paddy] Other Variety, dry (conv. to 14% mc)"
    selected = rows[rows["Commodity"] == preferred].copy()
    if selected.empty:
        selected = rows.copy()

    selected = selected.sort_values(["Year", "Month_Number"])
    latest = selected.iloc[-1]
    latest_key = int(latest["Year"]) * 12 + int(latest["Month_Number"])
    integrated_period = _latest_market_period()
    integrated_key = (
        integrated_period[0] * 12 + integrated_period[1]
        if integrated_period
        else latest_key
    )
    months_behind = max(0, integrated_key - latest_key)
    previous = selected[
        selected["Year"].astype(int) * 12
        + selected["Month_Number"].astype(int)
        == latest_key - 1
    ]
    year_ago = selected[
        selected["Year"].astype(int) * 12
        + selected["Month_Number"].astype(int)
        == latest_key - 12
    ]
    trailing = selected[
        (selected["Year"].astype(int) * 12 + selected["Month_Number"].astype(int))
        >= latest_key - 11
    ]

    price = float(latest["Price_PHP_per_kg"])

    def change(frame: pd.DataFrame) -> float | None:
        if frame.empty:
            return None
        old = float(frame.iloc[-1]["Price_PHP_per_kg"])
        if old == 0:
            return None
        return (price - old) / old * 100.0

    return {
        **base,
        "available": True,
        "commodity": str(latest["Commodity"]),
        "period": f"{latest['Month']} {int(latest['Year'])}",
        "latestIntegratedPeriod": (
            f"{pd.Timestamp(year=integrated_period[0], month=integrated_period[1], day=1).strftime('%B')} "
            f"{integrated_period[0]}"
            if integrated_period
            else None
        ),
        "monthsBehindLatestIntegratedPeriod": int(months_behind),
        "dataFreshness": (
            "Latest Integrated Period"
            if months_behind == 0
            else "Earlier Available Provincial Record"
        ),
        "pricePhpPerKg": round(price, 2),
        "monthOverMonthChangePct": (
            round(change(previous), 1) if change(previous) is not None else None
        ),
        "yearOverYearChangePct": (
            round(change(year_ago), 1) if change(year_ago) is not None else None
        ),
        "trailing12MonthMinPhpPerKg": (
            round(float(trailing["Price_PHP_per_kg"].min()), 2)
            if not trailing.empty
            else None
        ),
        "trailing12MonthMaxPhpPerKg": (
            round(float(trailing["Price_PHP_per_kg"].max()), 2)
            if not trailing.empty
            else None
        ),
        "definition": (
            "Farmgate price is the price received by farmers at the first point "
            "of sale, net of marketing costs paid by the farmer."
        ),
        "note": "Latest PSA OpenSTAT values may be preliminary or revised.",
    }


def _pagasa_region_label(province: str, region: str) -> str | None:
    if region == "NEGROS ISLAND REGION":
        if province == "Negros Occidental":
            return "Region 6 Western Visayas"
        if province in {"Negros Oriental", "Siquijor"}:
            return "Region 7 Central Visayas"
    mapping = {
        "CORDILLERA ADMINISTRATIVE REGION (CAR)": "CAR (Cordillera Administrative Region)",
        "REGION I (ILOCOS REGION)": "Region 1 Ilocos Region",
        "REGION II (CAGAYAN VALLEY)": "Region 2 Cagayan Valley",
        "REGION III (CENTRAL LUZON)": "Region 3 Central Luzon",
        "REGION IV-A (CALABARZON)": "Region 4A CALABARZON",
        "MIMAROPA REGION": "Region 4B MIMAROPA",
        "REGION V (BICOL REGION)": "Region 5 Bicol Region",
        "REGION VI (WESTERN VISAYAS)": "Region 6 Western Visayas",
        "REGION VII (CENTRAL VISAYAS)": "Region 7 Central Visayas",
        "REGION VIII (EASTERN VISAYAS)": "Region 8 Eastern Visayas",
        "REGION IX (ZAMBOANGA PENINSULA)": "Region 9 Zamboanga Peninsula",
        "REGION X (NORTHERN MINDANAO)": "Region 10 Northern Mindanao",
        "REGION XI (DAVAO REGION)": "Region 11 Davao Region",
        "REGION XII (SOCCSKSARGEN)": "Region 12 SOCCSKSARGEN",
        "REGION XIII (CARAGA)": "Region 13 CARAGA",
        "BANGSAMORO AUTONOMOUS REGION IN MUSLIM MINDANAO (BARMM)": (
            "BARMM (Bangsamoro Autonomous Region in Muslim Mindanao)"
        ),
        "BANGSAMORO AUTONOMOUS REGION IN MUSLIM MINDANAO (BARMM)d/": (
            "BARMM (Bangsamoro Autonomous Region in Muslim Mindanao)"
        ),
    }
    return mapping.get(region)


def _official_agri_weather_context(province: str) -> dict[str, Any]:
    base = {
        "available": False,
        "source": "DOST-PAGASA 10-Day Regional Agri-Weather Information",
        "sourceUrl": "https://www.pagasa.dost.gov.ph/ten-day-regional-agri-weather",
        "affectsYieldEstimate": False,
    }
    if not isinstance(pagasa_agri_weather, dict):
        return {**base, "reason": "Official agri-weather context is unavailable."}

    region = province_region.get(province)
    label = _pagasa_region_label(province, region)
    if not label:
        return {
            **base,
            "reason": "No matching PAGASA regional agri-weather grouping is available.",
        }

    record = next(
        (
            x
            for x in pagasa_agri_weather.get("regions", [])
            if x.get("regionLabel") == label
        ),
        None,
    )
    if not record:
        return {
            **base,
            "reason": "The current PAGASA regional agri-weather record is unavailable.",
        }

    return {
        **base,
        "available": True,
        "forecastPeriod": pagasa_agri_weather.get("forecastPeriod"),
        "dekadNumber": pagasa_agri_weather.get("dekadNumber"),
        "regionLabel": label,
        "forecastRainfallMm": record.get("forecastRainfallMm"),
        "relativeHumidityPct": record.get("relativeHumidityPct"),
        "rainyDaysGt1Mm": record.get("rainyDaysGt1Mm"),
        "temperatureC": record.get("temperatureC"),
        "riceStages": record.get("riceStages") or [],
        "farmOperations": record.get("farmOperations") or [],
        "scope": (
            "Official regional 10-day agri-weather context; it does not alter "
            "the ANI XGBoost yield estimate."
        ),
    }


def _official_climate_risk_context(province: str) -> dict[str, Any]:
    base = {
        "available": False,
        "source": "DOST-PAGASA",
        "ensoSourceUrl": (
            "https://www.pagasa.dost.gov.ph/climate/el-nino-la-nina/advisories"
        ),
        "droughtSourceUrl": "https://droughtcaster.pagasa.dost.gov.ph/",
        "definitionsUrl": "https://www.pagasa.dost.gov.ph/climate/climate-advisories",
        "affectsYieldEstimate": False,
    }
    if not isinstance(pagasa_climate_risk, dict):
        return {**base, "reason": "Official PAGASA climate-risk context is unavailable."}

    enso = pagasa_climate_risk.get("enso") or {}
    drought_root = pagasa_climate_risk.get("drought") or {}
    record = (drought_root.get("provinces") or {}).get(province)
    if not enso.get("available") and not record:
        return {
            **base,
            "reason": (
                "No current PAGASA ENSO or provincial drought context is "
                "available for this selection."
            ),
        }

    return {
        **base,
        "available": True,
        "retrievedAtUtc": pagasa_climate_risk.get("retrievedAtUtc"),
        "ensoAdvisory": enso if enso.get("available") else None,
        "droughtAssessment": (
            record.get("latestAssessment") if isinstance(record, dict) else None
        ),
        "droughtOutlook": (
            record.get("outlook") or [] if isinstance(record, dict) else []
        ),
        "droughtIssuedAt": (
            record.get("issuedAt") if isinstance(record, dict) else None
        ),
        "classificationNote": drought_root.get("classificationNote"),
        "scope": (
            "Official PAGASA climate-risk context. Drought categories and ENSO "
            "advisories are displayed as published and are not calculated by ANI."
        ),
    }


def _satellite_vegetation_context(
    province: str,
    target_year: int,
    target_quarter: int,
) -> dict[str, Any]:
    """Summarize pre-target satellite vegetation without affecting inference."""
    reference_idx = _period_key(target_year, target_quarter) - 1
    reference_year = int(reference_idx // 4)
    reference_quarter = int(reference_idx % 4 + 1)

    base = {
        "available": False,
        "comparisonAvailable": False,
        "referenceYear": reference_year,
        "referenceQuarter": reference_quarter,
        "referencePeriod": f"Q{reference_quarter} {reference_year}",
        "source": SATELLITE_CONTEXT_SOURCE,
        "spatialScope": "Province-level cropland summary",
        "affectsYieldEstimate": False,
    }

    if satellite_df.empty:
        return {
            **base,
            "reason": "Satellite vegetation data are unavailable.",
        }

    normalized = normalize_province_name(province)
    reference = satellite_df[
        (satellite_df["Province"] == normalized)
        & (satellite_df["Year"].astype(int) == reference_year)
        & (satellite_df["Quarter"].astype(int) == reference_quarter)
    ]
    if reference.empty:
        return {
            **base,
            "reason": (
                "Satellite vegetation context is unavailable for the required "
                f"pre-target period (Q{reference_quarter} {reference_year})."
            ),
        }

    row = reference.iloc[0]
    ndvi = float(row["Cropland_NDVI_Mean"])
    evi = float(row["Cropland_EVI_Mean"])
    if not (pd.notna(ndvi) and pd.notna(evi)):
        return {
            **base,
            "reason": (
                "Satellite vegetation values are incomplete for the required "
                f"pre-target period (Q{reference_quarter} {reference_year})."
            ),
        }

    current_key = reference_year * 4 + reference_quarter - 1
    historical = satellite_df[
        (satellite_df["Province"] == normalized)
        & (satellite_df["Quarter"].astype(int) == reference_quarter)
        & (
            satellite_df["Year"].astype(int) * 4
            + satellite_df["Quarter"].astype(int)
            - 1
            < current_key
        )
    ][["Cropland_NDVI_Mean", "Cropland_EVI_Mean"]].dropna()

    result: dict[str, Any] = {
        **base,
        "available": True,
        "croplandNdvi": round(ndvi, 4),
        "croplandEvi": round(evi, 4),
        "validPixelObservations": (
            int(row["Valid_Pixel_Observations"])
            if pd.notna(row.get("Valid_Pixel_Observations"))
            else None
        ),
        "historicalSameQuarterObservations": int(len(historical)),
    }

    if len(historical) < MIN_SATELLITE_SEASONAL_OBSERVATIONS:
        return {
            **result,
            "reason": (
                "The satellite observation is available, but there are not "
                "enough earlier same-quarter observations for a seasonal comparison."
            ),
        }

    ndvi_series = historical["Cropland_NDVI_Mean"].astype(float)
    evi_series = historical["Cropland_EVI_Mean"].astype(float)
    ndvi_median = float(ndvi_series.median())
    ndvi_q25 = float(ndvi_series.quantile(0.25))
    ndvi_q75 = float(ndvi_series.quantile(0.75))
    evi_median = float(evi_series.median())

    if ndvi < ndvi_q25:
        vegetation_status = "Below Typical Seasonal Vegetation"
    elif ndvi > ndvi_q75:
        vegetation_status = "Above Typical Seasonal Vegetation"
    else:
        vegetation_status = "Within Typical Seasonal Vegetation"

    def percent_difference(value: float, baseline: float) -> float | None:
        if baseline == 0:
            return None
        return (value - baseline) / baseline * 100.0

    ndvi_difference = percent_difference(ndvi, ndvi_median)
    evi_difference = percent_difference(evi, evi_median)

    return {
        **result,
        "comparisonAvailable": True,
        "vegetationStatus": vegetation_status,
        "ndviHistoricalMedian": round(ndvi_median, 4),
        "ndviQ25": round(ndvi_q25, 4),
        "ndviQ75": round(ndvi_q75, 4),
        "eviHistoricalMedian": round(evi_median, 4),
        "ndviPercentDifferenceFromMedian": (
            round(ndvi_difference, 1)
            if ndvi_difference is not None
            else None
        ),
        "eviPercentDifferenceFromMedian": (
            round(evi_difference, 1)
            if evi_difference is not None
            else None
        ),
        "comparisonBasis": (
            f"Earlier Q{reference_quarter} province-level cropland observations"
        ),
    }


def _agricultural_source_status(
    province: str,
    ecosystem: str,
    year: int,
    quarter: int,
) -> str | None:
    if agricultural_source_df.empty:
        return None
    eco = normalize_ecosystem(ecosystem)
    rows = agricultural_source_df[
        (agricultural_source_df["Province"] == normalize_province_name(province))
        & (agricultural_source_df["Ecosystem"] == eco)
        & (agricultural_source_df["Year"].astype(int) == int(year))
        & (
            agricultural_source_df["Quarter_Number"].astype(int)
            == int(quarter)
        )
    ]["PSA_Data_Status"].dropna()
    statuses = sorted(
        {str(value).strip() for value in rows if str(value).strip()}
    )
    return ", ".join(statuses) if statuses else None


def _latest_agricultural_status() -> str | None:
    if agricultural_source_df.empty:
        return None
    year, quarter = _latest_period()
    rows = agricultural_source_df[
        (agricultural_source_df["Year"].astype(int) == year)
        & (
            agricultural_source_df["Quarter_Number"].astype(int)
            == quarter
        )
    ]["PSA_Data_Status"].dropna()
    statuses = sorted(
        {str(value).strip() for value in rows if str(value).strip()}
    )
    return ", ".join(statuses) if statuses else None


def _next_period(year: int, quarter: int) -> tuple[int, int]:
    idx = _period_key(year, quarter) + 1
    return int(idx // 4), int(idx % 4 + 1)


def philippine_reference_date(reference_date: date | None = None) -> date:
    """Return an explicit reference date or today's date in Asia/Manila."""
    return reference_date or datetime.now(PHILIPPINE_TIMEZONE).date()


def classify_target_period(
    target_year: int,
    target_quarter: int,
    reference_date: date | None = None,
) -> dict[str, str]:
    """Classify a target quarter temporally without evaluating model eligibility."""
    quarter_bounds = {
        1: (1, 3, 31),
        2: (4, 6, 30),
        3: (7, 9, 30),
        4: (10, 12, 31),
    }
    if target_quarter not in quarter_bounds:
        raise ValueError("Quarter must be 1, 2, 3, or 4.")

    start_month, end_month, end_day = quarter_bounds[target_quarter]
    period_start = date(target_year, start_month, 1)
    period_end = date(target_year, end_month, end_day)
    today = philippine_reference_date(reference_date)

    if today < period_start:
        temporal_status = "PROSPECTIVE_FORECAST"
    elif today <= period_end:
        temporal_status = "CURRENT_QUARTER_ESTIMATE"
    else:
        temporal_status = "RETROSPECTIVE_ESTIMATE"

    return {
        "temporalStatus": temporal_status,
        "resultType": TEMPORAL_RESULT_TYPES[temporal_status],
        "targetPeriodStart": period_start.isoformat(),
        "targetPeriodEnd": period_end.isoformat(),
        "referenceDate": today.isoformat(),
        "referenceTimezone": PHILIPPINE_TIMEZONE_NAME,
    }


def classify_environmental_freshness(
    report: dict[str, Any],
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Classify the stored Stage 9 window without recomputing its calculations."""
    today = philippine_reference_date(reference_date)
    window = (report.get("context") or {}).get("forecast_window") or {}
    raw_start = window.get("start")
    raw_end = window.get("end")
    status = "UNKNOWN"
    try:
        window_start = date.fromisoformat(raw_start)
        window_end = date.fromisoformat(raw_end)
        if window_start > window_end:
            raise ValueError("Forecast window starts after it ends.")
        if today < window_start:
            status = "UPCOMING"
        elif today <= window_end:
            status = "CURRENT"
        else:
            status = "EXPIRED"
    except (TypeError, ValueError):
        window_start = None
        window_end = None

    return {
        "status": status,
        "referenceDate": today.isoformat(),
        "referenceTimezone": PHILIPPINE_TIMEZONE_NAME,
        "windowStart": window_start.isoformat() if window_start else None,
        "windowEnd": window_end.isoformat() if window_end else None,
    }


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

    lag1_idx = target_idx - 1
    lag1_year, lag1_quarter = lag1_idx // 4, lag1_idx % 4 + 1
    lag1_status = _agricultural_source_status(
        province,
        eco,
        lag1_year,
        lag1_quarter,
    )

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
        "previous_quarter_rainfall_mm": round(float(feature_row["Rainfall_Lag1_mm"]), 1),
        "previous_quarter_mean_temperature_c": round(float(feature_row["T2M_Lag1_C"]), 1),
        "previous_quarter_agricultural_status": lag1_status,
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


@app.get("/environmental-decision-support")
def environmental_decision_support() -> dict[str, Any]:
    """Return the latest Stage 9 report without recomputing or affecting yield forecasts."""
    if not ENVIRONMENTAL_DECISION_SUPPORT_PATH.is_file():
        return {
            "available": False,
            "message": "Environmental decision-support output has not been generated yet.",
            "freshness": classify_environmental_freshness({}),
            "currentForDecisionSupport": False,
        }

    try:
        report = json.loads(
            ENVIRONMENTAL_DECISION_SUPPORT_PATH.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "message": "Environmental decision-support output could not be read.",
            "freshness": classify_environmental_freshness({}),
            "currentForDecisionSupport": False,
        }

    if not isinstance(report, dict):
        return {
            "available": False,
            "message": "Environmental decision-support output is not a JSON object.",
            "freshness": classify_environmental_freshness({}),
            "currentForDecisionSupport": False,
        }
    freshness = classify_environmental_freshness(report)
    return {
        **report,
        "available": True,
        "freshness": freshness,
        "currentForDecisionSupport": freshness["status"] in {"UPCOMING", "CURRENT"},
    }


@app.get("/meta")
def meta() -> dict[str, Any]:
    latest_year, latest_quarter = _latest_period()
    weather_year, weather_quarter = _latest_weather_period()
    satellite_period = _latest_satellite_period()
    market_period = _latest_market_period()
    next_year, next_quarter = _next_period(latest_year, latest_quarter)

    return {
        "model": metadata,
        "provinces": sorted(history_df["Province"].dropna().unique().tolist()),
        "ecosystems": ["Irrigated", "Rainfed"],
        "latest_agricultural_period": {
            "year": latest_year,
            "quarter": latest_quarter,
            "status": _latest_agricultural_status(),
        },
        "latest_weather_period": {
            "year": weather_year,
            "quarter": weather_quarter,
        },
        "latest_satellite_period": (
            {
                "year": satellite_period[0],
                "quarter": satellite_period[1],
            }
            if satellite_period
            else None
        ),
        "satellite_vegetation": satellite_evaluation,
        "latest_market_period": (
            {"year": market_period[0], "month": market_period[1]}
            if market_period
            else None
        ),
        "official_agri_weather": (
            {
                "source": pagasa_agri_weather.get("source"),
                "forecastPeriod": pagasa_agri_weather.get("forecastPeriod"),
                "dekadNumber": pagasa_agri_weather.get("dekadNumber"),
            }
            if isinstance(pagasa_agri_weather, dict)
            else None
        ),
        "official_climate_risk": (
            {
                "source": pagasa_climate_risk.get("source"),
                "retrievedAtUtc": pagasa_climate_risk.get("retrievedAtUtc"),
                "enso": pagasa_climate_risk.get("enso"),
                "droughtProvincesLoaded": (
                    pagasa_climate_risk.get("drought", {}).get("loadedProvinces")
                ),
            }
            if isinstance(pagasa_climate_risk, dict)
            else None
        ),
        "suggested_next_target": {
            "year": next_year,
            "quarter": next_quarter,
        },
        "province_regions": province_region,
    }


@app.get("/farmer-context")
def farmer_context(province: str = Query(...)) -> dict[str, Any]:
    province = normalize_province_name(province)
    if province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found in ANI data.")
    return {
        "province": province,
        "region": province_region[province],
        "marketContext": _market_context(province),
        "officialAgriWeatherContext": _official_agri_weather_context(province),
        "officialClimateRiskContext": _official_climate_risk_context(province),
    }


@app.get("/forecast-availability")
def forecast_availability(
    province: str = Query(...),
    ecosystem: str = Query(...),
) -> dict[str, Any]:
    """List model-eligible target periods whose required lagged inputs currently exist."""
    province = normalize_province_name(province)
    if province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found in ANI data.")

    try:
        eco = normalize_ecosystem(ecosystem)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    latest_year, latest_quarter = _latest_period()
    first_idx = _period_key(latest_year, latest_quarter) + 1
    reference_date = philippine_reference_date()
    available = []
    nearest_assessment = None
    # Look up to four years ahead. A period is offered only when the same
    # feature builder used by /predict confirms all required lags are present.
    for period_idx in range(first_idx, first_idx + 16):
        year, quarter = period_idx // 4, period_idx % 4 + 1
        result = builder.build(province, eco, year, quarter)
        if nearest_assessment is None:
            nearest_assessment = {
                "year": year,
                "quarter": quarter,
                "eligible": result.eligible,
                "reason": result.reason,
                "priorQuarters": result.prior_total,
                "sameQuarterObservations": result.prior_same_quarter,
            }
        if result.eligible:
            temporal = classify_target_period(year, quarter, reference_date)
            available.append({
                "year": year,
                "quarter": quarter,
                "priorQuarters": result.prior_total,
                "sameQuarterObservations": result.prior_same_quarter,
                "temporalStatus": temporal["temporalStatus"],
                "resultType": temporal["resultType"],
                "targetPeriodStart": temporal["targetPeriodStart"],
                "targetPeriodEnd": temporal["targetPeriodEnd"],
            })

    return {
        "province": province,
        "ecosystem": eco.replace(" Palay", ""),
        "latestAgriculturalPeriod": {
            "year": latest_year,
            "quarter": latest_quarter,
        },
        "referenceDate": reference_date.isoformat(),
        "referenceTimezone": PHILIPPINE_TIMEZONE_NAME,
        "availableTargets": available,
        "nearestTargetAssessment": nearest_assessment,
    }


@app.post("/predict")
def predict(request: ForecastRequest) -> dict[str, Any]:
    province = normalize_province_name(request.province)
    if province not in province_region:
        raise HTTPException(status_code=404, detail="Province not found in ANI data.")

    try:
        ecosystem = normalize_ecosystem(request.ecosystem)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = builder.build(
        province,
        ecosystem,
        request.target_year,
        request.target_quarter,
    )
    generated_at_dt = datetime.now(timezone.utc)
    temporal = classify_target_period(
        request.target_year,
        request.target_quarter,
        generated_at_dt.astimezone(PHILIPPINE_TIMEZONE).date(),
    )

    if not result.eligible or result.row is None:
        return {
            "eligible": False,
            "message": (
                "Yield estimate unavailable — historical data or required "
                "lagged inputs are not yet available."
            ),
            "reason": result.reason,
            "province": province,
            "ecosystem": ecosystem.replace(" Palay", ""),
            "targetYear": request.target_year,
            "targetQuarter": request.target_quarter,
            "priorQuarters": result.prior_total,
            "sameQuarterObservations": result.prior_same_quarter,
            **temporal,
        }

    feature_frame = pd.DataFrame([result.row], columns=MODEL_FEATURES)
    predicted = float(pipeline.predict(feature_frame)[0])

    context = builder.historical_context(
        province,
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
        province,
        ecosystem,
        request.target_year,
        request.target_quarter,
        result.row,
    )
    satellite_context = _satellite_vegetation_context(
        province,
        request.target_year,
        request.target_quarter,
    )
    benchmark_context = _historical_benchmark_context(
        province,
        ecosystem,
        request.target_year,
        request.target_quarter,
        predicted,
    )
    associated_signals = _associated_signals_context(
        province,
        request.target_year,
        request.target_quarter,
        result.row,
        extra,
        satellite_context,
    )
    yield_patterns = _yield_pattern_context(
        province,
        ecosystem,
        request.target_year,
        request.target_quarter,
        predicted,
    )
    vegetation_yield_relationship = _vegetation_yield_relationship(
        province,
        ecosystem,
        request.target_year,
        request.target_quarter,
    )
    official_agri_weather = _official_agri_weather_context(province)
    official_climate_risk = _official_climate_risk_context(province)
    farmer_guidance = _farmer_guidance_context(
        associated_signals,
        benchmark_context,
        official_agri_weather,
        official_climate_risk,
    )

    generated_at = generated_at_dt.isoformat()
    forecast_id = (
        f"ANI-FC-{request.target_year}-Q{request.target_quarter}-"
        f"{generated_at_dt.strftime('%Y%m%d%H%M%S')}"
    )

    return {
        "eligible": True,
        "forecastId": forecast_id,
        "province": province,
        "region": province_region[province],
        "ecosystem": ecosystem.replace(" Palay", ""),
        "targetYear": request.target_year,
        "targetQuarter": request.target_quarter,
        **temporal,
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
        "previousQuarterRainfallMm": extra["previous_quarter_rainfall_mm"],
        "previousQuarterMeanTemperatureC": extra["previous_quarter_mean_temperature_c"],
        "previousQuarterAgriculturalStatus": extra["previous_quarter_agricultural_status"],
        "rainfallIndicator": extra["rainfall_indicator"],
        "temperatureIndicator": extra["temperature_indicator"],
        "satelliteVegetationContext": satellite_context,
        "vegetationYieldRelationship": vegetation_yield_relationship,
        "historicalBenchmarkContext": benchmark_context,
        "yieldPatternContext": yield_patterns,
        "associatedSignalsContext": associated_signals,
        "farmerGuidanceContext": farmer_guidance,
        "marketContext": _market_context(province),
        "officialAgriWeatherContext": official_agri_weather,
        "officialClimateRiskContext": official_climate_risk,
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


def _merge_historical_context(records: pd.DataFrame) -> pd.DataFrame:
    weather = weather_df.rename(columns={"Quarter": "Weather_Quarter"})
    merged = records.merge(
        weather,
        left_on=["Province", "Year", "Quarter_Number"],
        right_on=["Province", "Year", "Weather_Quarter"],
        how="left",
    )

    if not satellite_df.empty:
        satellite = satellite_df.rename(
            columns={"Quarter": "Satellite_Quarter"}
        )
        merged = merged.merge(
            satellite[
                [
                    "Province",
                    "Year",
                    "Satellite_Quarter",
                    "Cropland_NDVI_Mean",
                    "Cropland_EVI_Mean",
                    "Valid_Pixel_Observations",
                ]
            ],
            left_on=["Province", "Year", "Quarter_Number"],
            right_on=["Province", "Year", "Satellite_Quarter"],
            how="left",
        )
        historical_boundary_mismatch = (
            (merged["Province"] == "Maguindanao del Sur")
            & (merged["Year"].astype(int) < 2024)
        )
        merged.loc[
            historical_boundary_mismatch,
            [
                "Cropland_NDVI_Mean",
                "Cropland_EVI_Mean",
                "Valid_Pixel_Observations",
            ],
        ] = pd.NA
    else:
        merged["Cropland_NDVI_Mean"] = pd.NA
        merged["Cropland_EVI_Mean"] = pd.NA
        merged["Valid_Pixel_Observations"] = pd.NA

    return merged


def _historical_output_row(row: Any, region: str) -> dict[str, Any]:
    return {
        "id": (
            f"{row.Province}-{row.Ecosystem}-"
            f"{int(row.Year)}-Q{int(row.Quarter_Number)}"
        ),
        "province": row.Province,
        "region": region,
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
        "croplandNdvi": (
            None if pd.isna(row.Cropland_NDVI_Mean)
            else float(row.Cropland_NDVI_Mean)
        ),
        "croplandEvi": (
            None if pd.isna(row.Cropland_EVI_Mean)
            else float(row.Cropland_EVI_Mean)
        ),
        "satelliteValidPixelObservations": (
            None if pd.isna(row.Valid_Pixel_Observations)
            else int(row.Valid_Pixel_Observations)
        ),
    }


@app.get("/historical")
def historical(
    province: str = Query(...),
    ecosystem: str = Query(...),
) -> dict[str, Any]:
    province = normalize_province_name(province)
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
    merged = _merge_historical_context(records).sort_values(
        ["Year", "Quarter_Number"]
    )
    output = [
        _historical_output_row(row, province_region[province])
        for row in merged.itertuples(index=False)
    ]
    return {"records": output}


@app.get("/historical/all")
def historical_all() -> dict[str, Any]:
    merged = _merge_historical_context(history_df).sort_values(
        ["Province", "Ecosystem", "Year", "Quarter_Number"]
    )
    records = [
        _historical_output_row(row, row.Region_Context)
        for row in merged.itertuples(index=False)
    ]
    return {
        "records": records,
        "province_regions": province_region,
        "record_count": len(records),
    }


@app.get("/model-info")
def model_info() -> dict[str, Any]:
    return metadata
