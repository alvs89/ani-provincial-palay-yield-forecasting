from datetime import date
import math
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import (
    app,
    classify_environmental_freshness,
    classify_target_period,
)
from ml.features import normalize_province_name

ROOT = Path(__file__).resolve().parent
client = TestClient(app)

# Backend service and metadata
health = client.get("/health")
assert health.status_code == 200, health.text
meta_response = client.get("/meta")
assert meta_response.status_code == 200, meta_response.text
meta = meta_response.json()
assert "model" in meta

latest_ag = meta["latest_agricultural_period"]
latest_weather = meta["latest_weather_period"]
model_meta = meta["model"]

assert (latest_ag["year"], latest_ag["quarter"]) == (2026, 2), latest_ag
assert latest_ag.get("status") == "Preliminary", latest_ag
assert (latest_weather["year"], latest_weather["quarter"]) == (2026, 2), latest_weather
assert (
    model_meta.get("trained_through_year"),
    model_meta.get("trained_through_quarter"),
) == (2026, 1), model_meta
assert model_meta.get("scikit_learn_version") == "1.7.2", model_meta
print(
    "PASS Backend: /health and /meta return 200; integrated agricultural and "
    "weather coverage reaches Q2 2026; deployment training cutoff is Q1 2026."
)

# Fixed research/evaluation dataset remains through 2025.
provenance = __import__("json").loads(
    (ROOT / "data" / "processed" / "data_provenance.json").read_text(
        encoding="utf-8"
    )
)
assert provenance["agricultural_data"]["production_matrix"] == "2E4EVCP0"
assert provenance["agricultural_data"]["area_harvested_matrix"] == "2E4EAHC0"
assert provenance["agricultural_data"]["source_status_by_2026_quarter"]["Q2"] == "Preliminary"

history = pd.read_csv(ROOT / "data" / "processed" / "palay_history.csv")
weather = pd.read_csv(
    ROOT / "data" / "processed" / "province_quarter_weather.csv"
)
deployment_ready = pd.read_csv(
    ROOT / "data" / "processed" / "forecast_ready.csv"
)
source_records = pd.read_csv(
    ROOT / "data" / "processed" / "psa_2026_q1_q2_source_records.csv"
)
assert len(history) == 15122
assert history.duplicated(
    ["Province", "Ecosystem", "Year", "Quarter_Number"]
).sum() == 0
usable = history["Area_Harvested_ha"] > 0
yield_difference = (
    history.loc[usable, "Production_mt"]
    / history.loc[usable, "Area_Harvested_ha"]
    - history.loc[usable, "Yield_mt_per_ha"]
).abs()
assert (yield_difference <= 0.01).all()
assert len(weather) == 8692
assert weather.duplicated(["Province", "Year", "Quarter"]).sum() == 0
assert weather[
    ["Rainfall_Sum_mm", "T2M_Mean_C", "RH2M_Mean_pct", "WS2M_Mean_m_s"]
].isna().sum().sum() == 0
assert len(deployment_ready) == 12864
assert deployment_ready.isna().sum().sum() == 0
assert source_records["PSA_Data_Status"].value_counts().to_dict() == {
    "Published": 142,
    "Preliminary": 141,
}
print(
    "PASS Data integrity: integrated agricultural, weather, model-ready, "
    "and source-status records are internally consistent."
)

satellite = pd.read_csv(
    ROOT / "data" / "processed" / "province_quarter_satellite.csv"
)
assert len(satellite) == 8692
assert satellite["Province"].nunique() == 82
assert satellite.duplicated(["Province", "Year", "Quarter"]).sum() == 0
assert satellite["Cropland_NDVI_Mean"].between(-1.0, 1.0).all()
assert satellite["Cropland_EVI_Mean"].between(-1.0, 1.0).all()
satellite_period_keys = set(
    (
        satellite["Year"].astype(int) * 4
        + satellite["Quarter"].astype(int)
        - 1
    ).tolist()
)
satellite_min = min(satellite_period_keys)
satellite_max = max(satellite_period_keys)
assert (satellite_min // 4, satellite_min % 4 + 1) == (2000, 1)
assert (satellite_max // 4, satellite_max % 4 + 1) == (2026, 3)
satellite_missing_periods = {
    (period_key // 4, period_key % 4 + 1)
    for period_key in range(satellite_min, satellite_max + 1)
    if period_key not in satellite_period_keys
}
assert satellite_missing_periods == {(2025, 3)}
assert meta["latest_satellite_period"] == {"year": 2026, "quarter": 3}
assert (
    meta["satellite_vegetation"]["deployment_decision"]
    == "retain_current_deployed_feature_set"
)

satellite_summary = __import__("json").loads(
    (
        ROOT
        / "outputs"
        / "satellite_evaluation"
        / "summary.json"
    ).read_text(encoding="utf-8")
)
assert satellite_summary["promote_to_deployment"] is False
assert (
    satellite_summary["deployment_decision"]
    == "retain_current_deployed_feature_set"
)
assert math.isclose(
    satellite_summary["holdout_2025"]["satellite_augmented_model"]["mae"],
    0.22495718193715053,
)
assert math.isclose(
    satellite_summary["holdout_2025"]["selected_feature_complete_case"][
        "coverage_pct"
    ],
    74.75538160469667,
)
assert not any(
    str(feature).startswith("Cropland_")
    for feature in model_meta.get("features", [])
)
assert (
    provenance["satellite_vegetation_data"]["deployment_use"]
    .startswith("Evaluated satellite vegetation dataset")
)
historical_satellite = client.get(
    "/historical",
    params={"province": "Abra", "ecosystem": "Irrigated"},
)
assert historical_satellite.status_code == 200, historical_satellite.text
historical_satellite_rows = historical_satellite.json()["records"]
q2_2026_satellite = next(
    row
    for row in historical_satellite_rows
    if row["year"] == 2026 and row["quarter"] == 2
)
q3_2025_satellite = next(
    row
    for row in historical_satellite_rows
    if row["year"] == 2025 and row["quarter"] == 3
)
assert 0 <= q2_2026_satellite["croplandNdvi"] <= 1
assert 0 <= q2_2026_satellite["croplandEvi"] <= 1
assert q2_2026_satellite["satelliteValidPixelObservations"] > 0
assert q3_2025_satellite["croplandNdvi"] is None
assert q3_2025_satellite["croplandEvi"] is None
print(
    "PASS Satellite vegetation: 82-province MODIS NDVI/EVI coverage is "
    "internally consistent, the Q3 2025 access-platform gap is explicit, "
    "historical endpoints expose satellite context, and satellite predictors "
    "remain outside the active model because the promotion criteria were not met."
)

research = pd.read_csv(
    ROOT / "data" / "processed" / "forecast_ready_research_2001_2025.csv"
)
assert int(research["Target_Year"].max()) == 2025
assert len(research) == 12592
evaluation = model_meta["evaluation"]
assert evaluation["evaluation_period"] == "2025 holdout"
assert evaluation["eligible_rows"] == 511
assert math.isclose(evaluation["xgboost"]["mae"], 0.22322921736778986)
assert math.isclose(evaluation["xgboost"]["rmse"], 0.3077063812294472)
assert math.isclose(evaluation["xgboost"]["r2"], 0.8602508673547016)
print(
    "PASS Evaluation: fixed 2001-2025 research data and 2025 chronological "
    "holdout metrics remain unchanged."
)

# Q3 2026 can use Q2 2026 lagged inputs without including Q2 in model fitting.
prediction = client.post(
    "/predict",
    json={
        "province": "Abra",
        "ecosystem": "Irrigated",
        "target_year": 2026,
        "target_quarter": 3,
    },
)
assert prediction.status_code == 200, prediction.text
prediction_payload = prediction.json()
assert prediction_payload["eligible"] is True, prediction_payload
predicted_yield = prediction_payload.get("predictedYield")
assert isinstance(predicted_yield, (int, float)) and not isinstance(
    predicted_yield, bool
)
assert math.isfinite(predicted_yield), predicted_yield
assert prediction_payload.get("previousQuarterAgriculturalStatus") == "Preliminary"
for field in (
    "temporalStatus",
    "resultType",
    "targetPeriodStart",
    "targetPeriodEnd",
    "referenceDate",
    "referenceTimezone",
):
    assert field in prediction_payload, f"Missing prediction field: {field}"
    assert isinstance(prediction_payload[field], str), (
        field,
        prediction_payload[field],
    )
assert prediction_payload["referenceTimezone"] == "Asia/Manila"
assert date.fromisoformat(prediction_payload["referenceDate"])

unsupported = client.post(
    "/predict",
    json={
        "province": "Abra",
        "ecosystem": "Irrigated",
        "target_year": 2026,
        "target_quarter": 4,
    },
)
assert unsupported.status_code == 200, unsupported.text
unsupported_payload = unsupported.json()
assert unsupported_payload["eligible"] is False, unsupported_payload
assert (
    "Required historical agricultural record for lag 1 (2026 Q3) is missing"
    in unsupported_payload["reason"]
), unsupported_payload
print(
    "PASS Model prediction: Q3 2026 is numeric and eligible where required "
    "inputs exist; Q4 is withheld because Q3 agricultural Lag 1 is unavailable."
)

# Deterministic Manila quarterly temporal classification
reference_date = date(2026, 10, 13)
expected_temporal = {
    (2026, 1): ("RETROSPECTIVE_ESTIMATE", "Retrospective Estimate"),
    (2026, 3): ("RETROSPECTIVE_ESTIMATE", "Retrospective Estimate"),
    (2026, 4): ("CURRENT_QUARTER_ESTIMATE", "Current-Quarter Estimate"),
    (2027, 1): ("PROSPECTIVE_FORECAST", "Prospective Forecast"),
}
for (year, quarter), (status, result_type) in expected_temporal.items():
    classified = classify_target_period(year, quarter, reference_date)
    assert classified["temporalStatus"] == status, classified
    assert classified["resultType"] == result_type, classified
    assert classified["referenceTimezone"] == "Asia/Manila", classified
print(
    "PASS Temporal classification: explicit 2026-10-13 quarter cases and "
    "Asia/Manila timezone match."
)

# Deterministic freshness classification for an in-memory environmental report
report = {
    "context": {
        "forecast_window": {
            "start": "2026-10-14",
            "end": "2026-10-23",
        }
    }
}
for check_date, expected_status in (
    (date(2026, 10, 13), "UPCOMING"),
    (date(2026, 10, 18), "CURRENT"),
    (date(2026, 10, 24), "EXPIRED"),
):
    freshness = classify_environmental_freshness(report, check_date)
    assert freshness["status"] == expected_status, freshness
    current_for_decision_support = freshness["status"] in {
        "UPCOMING",
        "CURRENT",
    }
    assert current_for_decision_support is (expected_status != "EXPIRED")
for invalid_report in (
    {},
    {
        "context": {
            "forecast_window": {
                "start": "not-a-date",
                "end": "2026-10-23",
            }
        }
    },
):
    assert (
        classify_environmental_freshness(invalid_report, reference_date)[
            "status"
        ]
        == "UNKNOWN"
    )
print(
    "PASS Environmental freshness: upcoming, current, expired, and unknown "
    "windows match."
)

# Province aliases normalize while canonical identifiers pass through unchanged
province_names = {
    "Cotabato": "Cotabato (North Cotabato)",
    "Davao de Oro": "Davao de Oro (Compostela Valley)",
    "Tawi-Tawi": "Tawi-tawi",
}
for supplied, canonical in province_names.items():
    assert normalize_province_name(supplied) == canonical
    assert normalize_province_name(canonical) == canonical
print("PASS Province normalization: aliases and canonical names match.")

# Current province-region display follows the latest integrated administrative context.
assert (
    meta["province_regions"]["Negros Occidental"] == "NEGROS ISLAND REGION"
)
assert meta["province_regions"]["Negros Oriental"] == "NEGROS ISLAND REGION"
assert meta["province_regions"]["Siquijor"] == "NEGROS ISLAND REGION"
assert meta["province_regions"]["Sulu"] == "REGION IX (ZAMBOANGA PENINSULA)"
print(
    "PASS Region mapping: current NIR and Sulu administrative assignments "
    "match the integrated 2026 PSA context."
)

# Public availability confirms Q3 2026 eligibility where all required lags exist.
for province in (
    "Cotabato (North Cotabato)",
    "Davao de Oro (Compostela Valley)",
):
    response = client.get(
        "/forecast-availability",
        params={"province": province, "ecosystem": "Irrigated"},
    )
    assert response.status_code == 200, response.text
    targets = response.json()["availableTargets"]
    assert any(
        target["year"] == 2026 and target["quarter"] == 3
        for target in targets
    ), (province, targets)

tawi = client.get(
    "/forecast-availability",
    params={"province": "Tawi-tawi", "ecosystem": "Irrigated"},
)
assert tawi.status_code == 200, tawi.text
assert not any(
    target["year"] == 2026 and target["quarter"] == 3
    for target in tawi.json()["availableTargets"]
)
print(
    "PASS Forecast eligibility: canonical province cases expose Q3 2026 where "
    "eligible; Tawi-tawi remains unavailable under the same rules."
)

print("ANI integration verification passed.")
