from __future__ import annotations

import io
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
REFERENCE_DIR = ROOT / "data" / "reference"
CACHE_DIR = ROOT / "data" / "cache" / "cmip6"
CENTROIDS_PATH = REFERENCE_DIR / "province_centroids.csv"
EVALUATION_PATH = ROOT / "models" / "long_term_projection_metadata.json"

NASA_NCCS_BASE = "https://ds.nccs.nasa.gov/thredds"
NASA_SOURCE_URL = "https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/"

SCENARIOS = {
    "ssp126": "SSP1-2.6",
    "ssp245": "SSP2-4.5",
    "ssp370": "SSP3-7.0",
    "ssp585": "SSP5-8.5",
}
GCM_MODELS = (
    "ACCESS-CM2",
    "GFDL-ESM4",
    "MPI-ESM1-2-HR",
)
CMIP_VARIABLES = ("pr", "tasmax", "tasmin", "hurs", "sfcWind")
HISTORICAL_CLIMATE_COLUMNS = (
    "Rainfall_Sum_mm",
    "T2M_Mean_C",
    "RH2M_Mean_pct",
    "WS2M_Mean_m_s",
)
ANALOG_K = 5


def normalize_ecosystem(value: str) -> str:
    value = str(value).strip()
    return value[:-6] if value.endswith(" Palay") else value


def quarter_dates(year: int, quarter: int) -> tuple[date, date]:
    bounds = {
        1: (1, 1, 3, 31),
        2: (4, 1, 6, 30),
        3: (7, 1, 9, 30),
        4: (10, 1, 12, 31),
    }
    if quarter not in bounds:
        raise ValueError("Quarter must be between 1 and 4.")
    sm, sd, em, ed = bounds[quarter]
    return date(year, sm, sd), date(year, em, ed)


class Cmip6Client:
    def __init__(self, centroids_path: Path = CENTROIDS_PATH) -> None:
        if not centroids_path.is_file():
            raise FileNotFoundError(
                f"Province centroid file is missing: {centroids_path}. "
                "Run python -m tools.build_province_centroids."
            )
        self.centroids = pd.read_csv(centroids_path).set_index("Province")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._catalog_cache: dict[tuple[str, str, str, int], str] = {}

    def coordinates(self, province: str) -> tuple[float, float]:
        if province not in self.centroids.index:
            raise KeyError(f"No representative coordinate is available for {province}.")
        row = self.centroids.loc[province]
        return float(row["Latitude"]), float(row["Longitude"])

    def _dataset_path(
        self, model: str, scenario: str, variable: str, year: int
    ) -> str:
        key = (model, scenario, variable, year)
        if key in self._catalog_cache:
            return self._catalog_cache[key]

        catalog_url = (
            f"{NASA_NCCS_BASE}/catalog/AMES/NEX/GDDP-CMIP6/"
            f"{model}/{scenario}/r1i1p1f1/{variable}/catalog.xml"
        )
        response = requests.get(
            catalog_url,
            headers={"User-Agent": "ANI Provincial Palay Yield Forecasting System"},
            timeout=45,
        )
        response.raise_for_status()
        candidates = re.findall(
            rf'urlPath="([^"]*_{year}(?:_v[^"]+)?\.nc)"',
            response.text,
        )
        if not candidates:
            raise RuntimeError(
                f"No NEX-GDDP-CMIP6 {variable} file found for "
                f"{model} {scenario} {year}."
            )
        path = candidates[-1]
        self._catalog_cache[key] = path
        return path

    def _cache_path(
        self,
        model: str,
        scenario: str,
        variable: str,
        year: int,
        quarter: int,
        province: str,
    ) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", province)
        return (
            CACHE_DIR
            / scenario
            / str(year)
            / f"{safe}_Q{quarter}_{model}_{variable}.csv"
        )

    def _fetch_variable(
        self,
        model: str,
        scenario: str,
        variable: str,
        year: int,
        quarter: int,
        latitude: float,
        longitude: float,
        province: str,
    ) -> pd.Series:
        cache_path = self._cache_path(
            model, scenario, variable, year, quarter, province
        )
        if cache_path.is_file():
            frame = pd.read_csv(cache_path)
        else:
            dataset_path = self._dataset_path(model, scenario, variable, year)
            start, end = quarter_dates(year, quarter)
            params = {
                "var": variable,
                "latitude": f"{latitude:.5f}",
                "longitude": f"{longitude:.5f}",
                "time_start": f"{start.isoformat()}T12:00:00Z",
                "time_end": f"{end.isoformat()}T12:00:00Z",
                "accept": "csv",
            }
            url = (
                f"{NASA_NCCS_BASE}/ncss/grid/{dataset_path}?"
                f"{urlencode(params)}"
            )
            response = requests.get(
                url,
                headers={
                    "User-Agent": "ANI Provincial Palay Yield Forecasting System"
                },
                timeout=60,
            )
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(cache_path, index=False)

        value_cols = [
            col for col in frame.columns if col.startswith(f"{variable}[")
        ]
        if not value_cols:
            raise RuntimeError(
                f"NEX-GDDP-CMIP6 response did not contain {variable}."
            )
        values = pd.to_numeric(frame[value_cols[0]], errors="coerce").dropna()
        if values.empty:
            raise RuntimeError(
                f"NEX-GDDP-CMIP6 returned no usable {variable} values."
            )
        return values

    def quarterly_climate(
        self,
        province: str,
        scenario: str,
        year: int,
        quarter: int,
        model: str,
    ) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unsupported CMIP6 scenario: {scenario}")
        latitude, longitude = self.coordinates(province)

        values: dict[str, pd.Series] = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(
                    self._fetch_variable,
                    model,
                    scenario,
                    variable,
                    year,
                    quarter,
                    latitude,
                    longitude,
                    province,
                ): variable
                for variable in CMIP_VARIABLES
            }
            for future in as_completed(futures):
                variable = futures[future]
                values[variable] = future.result()

        rainfall_mm = float((values["pr"] * 86400.0).sum())
        temp_mean_c = float(
            ((values["tasmax"].mean() + values["tasmin"].mean()) / 2.0)
            - 273.15
        )
        humidity_pct = float(values["hurs"].mean())
        wind_m_s = float(values["sfcWind"].mean())

        return {
            "model": model,
            "rainfallMm": rainfall_mm,
            "meanTemperatureC": temp_mean_c,
            "relativeHumidityPct": humidity_pct,
            "windSpeedMS": wind_m_s,
            "gridLatitude": latitude,
            "gridLongitude": longitude,
        }


class LongTermProjector:
    def __init__(
        self,
        history: pd.DataFrame,
        weather: pd.DataFrame,
        client: Cmip6Client | None = None,
    ) -> None:
        hist = history.copy()
        hist["Ecosystem"] = hist["Ecosystem"].map(normalize_ecosystem)
        merged = hist.merge(
            weather,
            left_on=["Province", "Year", "Quarter_Number"],
            right_on=["Province", "Year", "Quarter"],
            how="inner",
        )
        self.data = merged[
            (merged["Year"].astype(int) >= 2001)
            & (merged["Year"].astype(int) <= 2025)
            & merged["Yield_mt_per_ha"].notna()
        ].copy()
        self.client = client or Cmip6Client()
        self.evaluation = (
            json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
            if EVALUATION_PATH.is_file()
            else None
        )

    @staticmethod
    def _climate_vector(record: dict[str, Any]) -> np.ndarray:
        return np.array(
            [
                float(record["rainfallMm"]),
                float(record["meanTemperatureC"]),
                float(record["relativeHumidityPct"]),
                float(record["windSpeedMS"]),
            ],
            dtype=float,
        )

    def _group(
        self, province: str, ecosystem: str, quarter: int
    ) -> pd.DataFrame:
        eco = normalize_ecosystem(ecosystem)
        return self.data[
            (self.data["Province"] == province)
            & (self.data["Ecosystem"] == eco)
            & (self.data["Quarter_Number"].astype(int) == int(quarter))
        ].sort_values("Year")

    def _analog_projection(
        self,
        group: pd.DataFrame,
        climate: dict[str, Any],
    ) -> dict[str, Any]:
        cols = list(HISTORICAL_CLIMATE_COLUMNS)
        sample = group.dropna(subset=cols + ["Yield_mt_per_ha"]).copy()
        if len(sample) < ANALOG_K:
            raise ValueError(
                "At least five historical same-quarter observations are required "
                "for the long-term climate-analog projection."
            )

        median = sample[cols].median().astype(float)
        mad = (sample[cols].astype(float) - median).abs().median()
        mad = mad.replace(0, 1.0).astype(float)
        target = pd.Series(
            {
                "Rainfall_Sum_mm": climate["rainfallMm"],
                "T2M_Mean_C": climate["meanTemperatureC"],
                "RH2M_Mean_pct": climate["relativeHumidityPct"],
                "WS2M_Mean_m_s": climate["windSpeedMS"],
            },
            dtype=float,
        )
        normalized = (sample[cols].astype(float) - target) / mad
        distances = np.sqrt((normalized**2).sum(axis=1).astype(float))
        nearest_idx = distances.nsmallest(min(ANALOG_K, len(sample))).index
        nearest = sample.loc[nearest_idx].copy()
        nearest_dist = distances.loc[nearest_idx].to_numpy(dtype=float)
        yields = nearest["Yield_mt_per_ha"].to_numpy(dtype=float)
        weights = 1.0 / (nearest_dist + 0.5)
        projected = float(np.average(yields, weights=weights))

        return {
            "projectedYieldMtPerHa": projected,
            "analogYieldQ25": float(np.quantile(yields, 0.25)),
            "analogYieldQ75": float(np.quantile(yields, 0.75)),
            "analogYears": [int(v) for v in nearest["Year"].tolist()],
            "analogYields": [round(float(v), 3) for v in yields],
            "analogDistances": [round(float(v), 3) for v in nearest_dist],
        }

    def project(
        self,
        province: str,
        ecosystem: str,
        target_year: int,
        target_quarter: int,
        scenario: str,
    ) -> dict[str, Any]:
        if target_year < 2027 or target_year > 2100:
            raise ValueError("Long-term projection year must be between 2027 and 2100.")
        if target_quarter not in {1, 2, 3, 4}:
            raise ValueError("Target quarter must be between 1 and 4.")
        if scenario not in SCENARIOS:
            raise ValueError("Unsupported CMIP6 scenario.")

        group = self._group(province, ecosystem, target_quarter)
        if len(group) < ANALOG_K:
            raise ValueError(
                "Insufficient same-quarter historical data for this province "
                "and ecosystem."
            )

        model_results: list[dict[str, Any]] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=len(GCM_MODELS)) as pool:
            futures = {
                pool.submit(
                    self.client.quarterly_climate,
                    province,
                    scenario,
                    target_year,
                    target_quarter,
                    model,
                ): model
                for model in GCM_MODELS
            }
            for future in as_completed(futures):
                model = futures[future]
                try:
                    climate = future.result()
                    analog = self._analog_projection(group, climate)
                    model_results.append({**climate, **analog})
                except Exception as exc:
                    errors.append(f"{model}: {exc}")

        if len(model_results) < 2:
            detail = "; ".join(errors) if errors else "No usable GCM results."
            raise RuntimeError(
                "Long-term projection requires at least two usable CMIP6 models. "
                + detail
            )

        model_results.sort(key=lambda row: row["model"])
        projected_values = np.array(
            [row["projectedYieldMtPerHa"] for row in model_results], dtype=float
        )
        lower_values = np.array(
            [row["analogYieldQ25"] for row in model_results], dtype=float
        )
        upper_values = np.array(
            [row["analogYieldQ75"] for row in model_results], dtype=float
        )

        climate_keys = {
            "rainfallMm": "projectedRainfallMm",
            "meanTemperatureC": "projectedMeanTemperatureC",
            "relativeHumidityPct": "projectedRelativeHumidityPct",
            "windSpeedMS": "projectedWindSpeedMS",
        }
        ensemble_climate = {
            out: float(np.median([row[key] for row in model_results]))
            for key, out in climate_keys.items()
        }

        historical_climate = {
            "rainfallMm": float(group["Rainfall_Sum_mm"].median()),
            "meanTemperatureC": float(group["T2M_Mean_C"].median()),
            "relativeHumidityPct": float(group["RH2M_Mean_pct"].median()),
            "windSpeedMS": float(group["WS2M_Mean_m_s"].median()),
        }
        recent = group[group["Year"].astype(int) >= 2016]
        baseline_source = recent if len(recent) >= 5 else group
        baseline_yield = float(baseline_source["Yield_mt_per_ha"].median())
        central = float(np.median(projected_values))
        lower = float(min(projected_values.min(), lower_values.min()))
        upper = float(max(projected_values.max(), upper_values.max()))

        rainfall_change_pct = (
            (ensemble_climate["projectedRainfallMm"] - historical_climate["rainfallMm"])
            / historical_climate["rainfallMm"]
            * 100.0
            if historical_climate["rainfallMm"]
            else None
        )
        temperature_change_c = (
            ensemble_climate["projectedMeanTemperatureC"]
            - historical_climate["meanTemperatureC"]
        )

        return {
            "projectionType": "Experimental Long-Term Yield Projection",
            "province": province,
            "ecosystem": normalize_ecosystem(ecosystem),
            "targetYear": int(target_year),
            "targetQuarter": int(target_quarter),
            "scenario": scenario,
            "scenarioLabel": SCENARIOS[scenario],
            "projectedYieldMtPerHa": round(central, 3),
            "projectedRangeLowMtPerHa": round(lower, 3),
            "projectedRangeHighMtPerHa": round(upper, 3),
            "recentHistoricalBaselineMtPerHa": round(baseline_yield, 3),
            "changeFromRecentBaselinePct": round(
                ((central - baseline_yield) / baseline_yield) * 100.0, 1
            )
            if baseline_yield
            else None,
            **{
                key: round(value, 2)
                for key, value in ensemble_climate.items()
            },
            "rainfallVsHistoricalMedianPct": round(rainfall_change_pct, 1)
            if rainfall_change_pct is not None
            else None,
            "temperatureVsHistoricalMedianC": round(temperature_change_c, 2),
            "historicalClimateBaseline": {
                "rainfallMm": round(historical_climate["rainfallMm"], 2),
                "meanTemperatureC": round(
                    historical_climate["meanTemperatureC"], 2
                ),
                "relativeHumidityPct": round(
                    historical_climate["relativeHumidityPct"], 2
                ),
                "windSpeedMS": round(historical_climate["windSpeedMS"], 2),
            },
            "cmip6ModelsUsed": [row["model"] for row in model_results],
            "modelResults": [
                {
                    "model": row["model"],
                    "projectedYieldMtPerHa": round(
                        row["projectedYieldMtPerHa"], 3
                    ),
                    "analogYears": row["analogYears"],
                    "analogYields": row["analogYields"],
                    "rainfallMm": round(row["rainfallMm"], 2),
                    "meanTemperatureC": round(row["meanTemperatureC"], 2),
                    "relativeHumidityPct": round(
                        row["relativeHumidityPct"], 2
                    ),
                    "windSpeedMS": round(row["windSpeedMS"], 2),
                }
                for row in model_results
            ],
            "evaluation": self.evaluation,
            "source": "NASA NEX-GDDP-CMIP6",
            "sourceUrl": NASA_SOURCE_URL,
            "method": (
                "Each CMIP6 model supplies projected quarterly climate conditions "
                "for a representative provincial point. ANI finds the five most "
                "climatically similar historical observations for the same province, "
                "ecosystem, and quarter, then combines their observed PSA-derived "
                "yields. The central result is the median across available climate "
                "models; the displayed range combines climate-model and historical-"
                "analog spread."
            ),
            "guardrail": (
                "This is an experimental scenario projection, not the validated "
                "next-quarter XGBoost forecast and not an official PSA projection. "
                "It assumes historical climate-yield relationships remain informative "
                "and does not model future changes in varieties, irrigation, inputs, "
                "land use, pests, policy, or farm management."
            ),
            "errors": errors,
        }
