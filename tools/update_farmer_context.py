from __future__ import annotations

import html
import io
import json
from datetime import datetime, timezone
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
HISTORY_PATH = DATA_DIR / "palay_history.csv"
PRICE_PATH = DATA_DIR / "palay_farmgate_prices.csv"
PAGASA_PATH = DATA_DIR / "pagasa_regional_agri_weather.json"
PAGASA_CLIMATE_PATH = DATA_DIR / "pagasa_climate_risk.json"
PROVENANCE_PATH = DATA_DIR / "data_provenance.json"
LONG_TERM_METADATA_PATH = ROOT / "models" / "long_term_projection_metadata.json"

PSA_API = (
    "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2M/NFG/"
    "0032M4AFN01.px"
)
PSA_SOURCE_URL = (
    "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/"
    "DB__2M__NFG/0032M4AFN01.px/"
)
PAGASA_URL = "https://www.pagasa.dost.gov.ph/ten-day-regional-agri-weather"
PAGASA_ENSO_URL = "https://www.pagasa.dost.gov.ph/climate/el-nino-la-nina/advisories"
PAGASA_DROUGHTCASTER_URL = "https://droughtcaster.pagasa.dost.gov.ph/"
PAGASA_DROUGHTCASTER_PROXY = "https://droughtcaster.pagasa.dost.gov.ph/proxy.php"
DROUGHTCASTER_PROVINCE_ALIASES = {
    "Cotabato (North Cotabato)": "Cotabato",
    "Davao de Oro (Compostela Valley)": "Davao de Oro",
    "Tawi-tawi": "Tawi-Tawi",
}


def curl_text(url: str, *, payload: dict | None = None) -> str:
    exe = shutil.which("curl") or shutil.which("curl.exe")
    if not exe:
        raise RuntimeError("curl is required to update PSA OpenSTAT market data.")

    cmd = [
        exe,
        "-sS",
        "-L",
        "--http1.1",
        "--tlsv1.2",
        "--retry",
        "5",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "-A",
        "ANI Provincial Palay Yield Forecasting System",
    ]
    if Path(exe).name.lower() == "curl.exe":
        cmd.append("--ssl-no-revoke")
    temp_path: Path | None = None
    if payload is not None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as tmp:
            json.dump(payload, tmp)
            temp_path = Path(tmp.name)
        cmd += [
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            f"@{temp_path}",
        ]
    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        return proc.stdout
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _clean_geo_label(label: str) -> str:
    cleaned = re.sub(r"^\.+", "", str(label)).strip()
    return re.sub(r"\s+(?:[a-z]/|\d+/)$", "", cleaned, flags=re.I).strip()


def update_psa_farmgate_prices() -> pd.DataFrame:
    history = pd.read_csv(HISTORY_PATH)
    ani_provinces = set(history["Province"].dropna().astype(str).unique())

    metadata = json.loads(curl_text(PSA_API))
    variables = {v["code"]: v for v in metadata["variables"]}
    geo_var = variables["Geolocation"]
    geo_pairs = list(zip(geo_var["values"], geo_var["valueTexts"]))

    selected_geo_codes = [
        code
        for code, label in geo_pairs
        if _clean_geo_label(label) in ani_provinces
    ]
    year_codes = variables["Year"]["values"]
    period_codes = variables["Period"]["values"][:12]

    payload = {
        "query": [
            {
                "code": "Geolocation",
                "selection": {"filter": "item", "values": selected_geo_codes},
            },
            {
                "code": "Commodity",
                "selection": {"filter": "item", "values": ["0", "1"]},
            },
            {
                "code": "Year",
                "selection": {"filter": "item", "values": year_codes},
            },
            {
                "code": "Period",
                "selection": {"filter": "item", "values": period_codes},
            },
        ],
        "response": {"format": "csv"},
    }

    raw = pd.read_csv(io.StringIO(curl_text(PSA_API, payload=payload)))
    raw["Province"] = raw["Geolocation"].map(_clean_geo_label)
    value_columns = [
        c for c in raw.columns if re.match(r"^20\d{2} [A-Za-z]+$", str(c))
    ]
    long = raw.melt(
        id_vars=["Province", "Commodity"],
        value_vars=value_columns,
        var_name="Period",
        value_name="Price_PHP_per_kg",
    )
    parsed = long["Period"].str.extract(r"^(\d{4})\s+(.+)$")
    long["Year"] = parsed[0].astype(int)
    long["Month"] = parsed[1]
    long["Month_Number"] = pd.to_datetime(
        long["Month"], format="%B"
    ).dt.month.astype(int)
    long["Price_PHP_per_kg"] = pd.to_numeric(
        long["Price_PHP_per_kg"], errors="coerce"
    )
    long = long.dropna(subset=["Price_PHP_per_kg"]).copy()
    long["Source"] = "PSA OpenSTAT Farm Price Survey for Palay"
    long["Source_URL"] = PSA_SOURCE_URL
    long = long[
        [
            "Province",
            "Commodity",
            "Year",
            "Month",
            "Month_Number",
            "Price_PHP_per_kg",
            "Source",
            "Source_URL",
        ]
    ].sort_values(["Province", "Commodity", "Year", "Month_Number"])
    long = long.drop_duplicates(
        subset=["Province", "Commodity", "Year", "Month_Number"],
        keep="last",
    )
    long.to_csv(PRICE_PATH, index=False)
    return long


def _strip_html(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    text = re.sub(r"<li[^>]*>", " | ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\ufffd", "-")
    return re.sub(r"\s+", " ", text).strip()


def _range_after(label: str, block: str) -> str | None:
    match = re.search(
        rf"{label}.*?<p[^>]*>(.*?)</p>",
        block,
        flags=re.I | re.S,
    )
    return _strip_html(match.group(1)) if match else None


def _list_after(label: str, block: str) -> list[str]:
    match = re.search(
        rf">{label}</th>.*?<ul[^>]*>(.*?)</ul>",
        block,
        flags=re.I | re.S,
    )
    if not match:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", match.group(1), flags=re.I | re.S)
    return [_strip_html(x) for x in items if _strip_html(x)]


def update_pagasa_agri_weather() -> dict:
    response = requests.get(
        PAGASA_URL,
        headers={"User-Agent": "ANI Provincial Palay Yield Forecasting System"},
        timeout=45,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    page = response.text

    plain = _strip_html(page)
    dekad_match = re.search(
        r"DEKAD\s+NO\.\s*(\d+)\s+([0-9]{1,2}\s*-\s*[0-9]{1,2}\s+"
        r"[A-Z]+\s+20\d{2})",
        plain,
        flags=re.I,
    )

    soil_moisture = {"period": None, "wet": "", "moist": "", "dry": ""}
    soil_period_match = re.search(
        r"ACTUAL SOIL MOISTURE CONDITION\s*\(as of\s*([^)]*)\)",
        plain,
        flags=re.I,
    )
    section_start = page.find("ACTUAL SOIL MOISTURE CONDITION")
    section_end = page.find("Farm Advisories", section_start)
    if section_start >= 0 and section_end > section_start:
        soil_section = page[section_start:section_end]
        cells = [
            _strip_html(cell)
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", soil_section, flags=re.I | re.S)
        ]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 3:
            soil_moisture = {
                "period": soil_period_match.group(1).strip() if soil_period_match else None,
                "wet": cells[-3],
                "moist": cells[-2],
                "dry": cells[-1],
            }

    forecast_match = re.search(
        r"Philippine Agri-Weather Forecast\s+(.*?)\s+ACTUAL SOIL MOISTURE CONDITION",
        plain,
        flags=re.I | re.S,
    )
    national_forecast = forecast_match.group(1).strip() if forecast_match else None
    hazard_keywords = [
        keyword
        for keyword in ["tropical cyclone", "heavy rainfall", "gusty winds", "thunderstorms"]
        if national_forecast and keyword in national_forecast.lower()
    ]

    regions: list[dict] = []
    blocks = re.findall(
        r'<div class="region-list region-details-\d+[^"]*"[^>]*>(.*?)</table>',
        page,
        flags=re.I | re.S,
    )
    for block in blocks:
        name_match = re.search(
            r'<th rowspan="3"[^>]*>(.*?)</th>',
            block,
            flags=re.I | re.S,
        )
        if not name_match:
            continue
        label = _strip_html(name_match.group(1))
        regions.append(
            {
                "regionLabel": label,
                "forecastRainfallMm": _range_after(
                    r"Forecast\s+Rainfall\s*\(mm\)\s*:", block
                ),
                "relativeHumidityPct": _range_after(
                    r"Relative\s+Humidity\s*\(%\)\s*:", block
                ),
                "rainyDaysGt1Mm": _range_after(
                    r"No\.\s+of\s+Rainy\s+Days.*?\(>\s*1\s*mm\)\s*:", block
                ),
                "temperatureC": _range_after(
                    r"Temperature\s*\([^)]*C\)\s*:", block
                ),
                "riceStages": _list_after("RICE", block),
                "farmOperations": _list_after(r"FARM\s*<br\s*/?>\s*OPERATIONS", block),
            }
        )

    result = {
        "source": "DOST-PAGASA 10-Day Regional Agri-Weather Information",
        "retrievedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceUrl": PAGASA_URL,
        "dekadNumber": int(dekad_match.group(1)) if dekad_match else None,
        "forecastPeriod": dekad_match.group(2).title() if dekad_match else None,
        "soilMoisture": soil_moisture,
        "nationalForecastSummary": national_forecast,
        "hazardKeywords": hazard_keywords,
        "regions": regions,
        "note": (
            "Official PAGASA regional agri-weather context. It is separate from "
            "ANI's XGBoost yield estimate and is not used as a model predictor."
        ),
    }
    PAGASA_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result



def _latest_enso_advisory(page: str) -> dict:
    plain = _strip_html(page)
    candidates: list[dict] = []
    patterns = [
        ("El Nino", r"(20\d{2}-\d{2}-\d{2})\s+El\s+Ni.{0,1}o\s+Advisory\s+(?:No\.?|no\.?)\s*(\d+)"),
        ("La Nina", r"(20\d{2}-\d{2}-\d{2})\s+La\s+Ni.{0,1}a\s+Advisory\s+(?:No\.?|no\.?)\s*(\d+)"),
    ]
    for phase, pattern in patterns:
        for match in re.finditer(pattern, plain, flags=re.I):
            candidates.append(
                {
                    "phase": phase,
                    "issuedDate": match.group(1),
                    "advisoryNumber": int(match.group(2)),
                    "title": f"{phase} Advisory No. {int(match.group(2))}",
                }
            )
    if not candidates:
        return {
            "available": False,
            "reason": "No current ENSO advisory could be parsed from the PAGASA advisory page.",
        }
    latest = max(candidates, key=lambda x: x["issuedDate"])
    return {
        "available": True,
        **latest,
        "sourceUrl": PAGASA_ENSO_URL,
        "scope": (
            "National PAGASA ENSO advisory. Local rainfall and agricultural impacts "
            "still depend on province-specific conditions and official local advisories."
        ),
    }


def _drought_map_payload(provinces: list[str]) -> dict:
    joined = "|".join(provinces)
    response = requests.get(
        PAGASA_DROUGHTCASTER_PROXY,
        params={
            "endpoint": "drought-map",
            "cacheOnly": "1",
            "locations": joined,
        },
        headers={"User-Agent": "ANI Provincial Palay Yield Forecasting System"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("PAGASA DroughtCaster returned an unexpected response.")
    return payload


def update_pagasa_climate_risk() -> dict:
    history = pd.read_csv(HISTORY_PATH)
    provinces = sorted(history["Province"].dropna().astype(str).unique().tolist())

    enso_response = requests.get(
        PAGASA_ENSO_URL,
        headers={"User-Agent": "ANI Provincial Palay Yield Forecasting System"},
        timeout=45,
    )
    enso_response.raise_for_status()
    enso_response.encoding = enso_response.apparent_encoding or "utf-8"
    enso = _latest_enso_advisory(enso_response.text)

    drought_requests = [
        DROUGHTCASTER_PROVINCE_ALIASES.get(province, province)
        for province in provinces
    ]
    drought_payload = _drought_map_payload(drought_requests)
    reverse_aliases = {
        source_name: ani_name
        for ani_name, source_name in DROUGHTCASTER_PROVINCE_ALIASES.items()
    }
    province_records: dict[str, dict] = {}
    for item in drought_payload.get("items", []):
        payload = item.get("payload") or {}
        source_province = str(
            payload.get("name") or item.get("location") or ""
        ).strip()
        province = reverse_aliases.get(source_province, source_province)
        if not province:
            continue
        series = [
            x
            for x in (payload.get("data") or [])
            if isinstance(x, dict) and x.get("date") and x.get("type") and x.get("status")
        ]
        assessments = sorted(
            (x for x in series if x.get("type") == "assessment"),
            key=lambda x: x["date"],
        )
        outlook = sorted(
            (x for x in series if x.get("type") == "outlook"),
            key=lambda x: x["date"],
        )
        province_records[province] = {
            "issuedAt": payload.get("issuedAt"),
            "islandGroup": payload.get("islandGroup"),
            "latestAssessment": assessments[-1] if assessments else None,
            "outlook": outlook,
        }

    result = {
        "source": "DOST-PAGASA",
        "retrievedAtUtc": datetime.now(timezone.utc).isoformat(),
        "enso": enso,
        "drought": {
            "source": "DOST-PAGASA PH Meteorological Drought Monitor",
            "sourceUrl": PAGASA_DROUGHTCASTER_URL,
            "definitionsUrl": "https://www.pagasa.dost.gov.ph/climate/climate-advisories",
            "cacheComplete": bool(drought_payload.get("complete")),
            "loadedProvinces": int(drought_payload.get("loaded") or len(province_records)),
            "requestedProvinces": len(provinces),
            "provinces": province_records,
            "classificationNote": (
                "ANI displays PAGASA's published Not affected, Dry condition, Dry spell, "
                "and Drought classifications. ANI does not calculate its own drought class."
            ),
        },
        "modelRelationship": (
            "Official climate-risk context only; it is not an input to the active XGBoost "
            "model and does not alter yield-model eligibility or inference."
        ),
    }
    PAGASA_CLIMATE_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def update_provenance(prices: pd.DataFrame, pagasa: dict, climate: dict) -> None:
    if not PROVENANCE_PATH.is_file():
        return

    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    latest = prices.sort_values(["Year", "Month_Number"]).iloc[-1]
    retrieval_time = datetime.now(timezone.utc).isoformat()

    provenance["palay_market_context"] = {
        "source": "Philippine Statistics Authority (PSA) OpenSTAT Farm Price Survey for Palay",
        "matrix": "0032M4AFN01",
        "source_url": PSA_SOURCE_URL,
        "retrieved_at_utc": retrieval_time,
        "frequency": "Monthly",
        "geographic_scope": (
            "Provincial records available in the PSA matrix and aligned to ANI "
            "canonical province names."
        ),
        "commodity_preference": (
            "Palay [Paddy] Other Variety, dry (conv. to 14% mc)"
        ),
        "integrated_through": {
            "year": int(latest["Year"]),
            "month": int(latest["Month_Number"]),
            "month_name": str(latest["Month"]),
        },
        "rows": int(len(prices)),
        "displayed_context": [
            "latest available farmgate price (PHP/kg)",
            "month-over-month change",
            "year-over-year change",
            "trailing 12-month minimum and maximum",
        ],
        "model_relationship": (
            "Market context only; it is not an input to the active XGBoost model "
            "and does not alter yield-model eligibility or inference."
        ),
        "availability_policy": (
            "Display the latest available provincial record and its explicit "
            "reference period; do not fabricate a value for months or provinces "
            "without a reported observation."
        ),
    }
    provenance["official_agri_weather_context"] = {
        "source": "DOST-PAGASA 10-Day Regional Agri-Weather Information",
        "source_url": PAGASA_URL,
        "retrieved_at_utc": pagasa.get("retrievedAtUtc") or retrieval_time,
        "integrated_forecast_period": pagasa.get("forecastPeriod"),
        "dekad_number": pagasa.get("dekadNumber"),
        "regional_records": len(pagasa.get("regions", [])),
        "displayed_context": [
            "forecast rainfall range",
            "relative humidity range",
            "number of rainy days (>1 mm)",
            "temperature range",
            "soil-moisture condition",
            "national farm-advisory hazard signals",
            "rice stages",
            "farm operations",
        ],
        "scope_note": (
            "Regional official agri-weather context. It is not a field-level "
            "forecast and does not replace official PAGASA warnings or advisories."
        ),
        "model_relationship": (
            "Context only; it is not an input to the active XGBoost model and "
            "does not alter yield-model eligibility or inference."
        ),
        "refresh_method": "python -m tools.update_farmer_context",
    }
    provenance["historical_enso_yield_context"] = {
        "source": "NOAA Climate Prediction Center Relative Oceanic Nino Index (RONI), ERSSTv6",
        "source_url": "https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/",
        "local_dataset": "data/processed/enso_history.csv",
        "refresh_method": "python tools/build_enso_history.py",
        "displayed_context": [
            "representative quarterly RONI value",
            "warm/cold/neutral RONI signal",
            "historical El Nino, La Nina, and Neutral episode grouping",
            "same-quarter median provincial palay yield by historical ENSO episode",
        ],
        "classification_method": (
            "El Nino and La Nina historical episode labels follow NOAA CPC's stated "
            "requirement that the +/-0.5 C RONI threshold persist for at least five "
            "consecutive overlapping seasons. Representative quarterly values use "
            "JFM, AMJ, JAS, and OND."
        ),
        "model_relationship": (
            "Exploratory historical association only; RONI/ENSO is not an input to "
            "the active XGBoost model and does not alter prediction eligibility or inference."
        ),
    }
    long_term_meta = (
        json.loads(LONG_TERM_METADATA_PATH.read_text(encoding="utf-8"))
        if LONG_TERM_METADATA_PATH.is_file()
        else None
    )
    provenance["long_term_climate_projection"] = {
        "source": "NASA NEX-GDDP-CMIP6",
        "source_url": "https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/",
        "projection_horizons_years": [3, 5, 10],
        "scenarios": ["SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5"],
        "climate_models": ["ACCESS-CM2", "GFDL-ESM4", "MPI-ESM1-2-HR"],
        "evaluation": long_term_meta,
        "model_relationship": (
            "Experimental scenario projection only; CMIP6 is separate from "
            "the deployed next-quarter XGBoost model."
        ),
    }
    provenance["official_climate_risk_context"] = {
        "source": "DOST-PAGASA",
        "retrieved_at_utc": climate.get("retrievedAtUtc") or retrieval_time,
        "enso_source_url": PAGASA_ENSO_URL,
        "drought_source_url": PAGASA_DROUGHTCASTER_URL,
        "latest_enso_advisory": climate.get("enso"),
        "drought_provinces_loaded": (
            climate.get("drought", {}).get("loadedProvinces")
        ),
        "displayed_context": [
            "latest PAGASA ENSO advisory",
            "latest provincial drought assessment",
            "published province drought outlook",
        ],
        "scope_note": (
            "Official national/provincial climate-risk context. It is not a field-level "
            "diagnosis and does not replace PAGASA warnings, advisories, or LGU guidance."
        ),
        "model_relationship": (
            "Context only; it is not an input to the active XGBoost model and does not "
            "alter yield-model eligibility or inference."
        ),
        "refresh_method": "python -m tools.update_farmer_context",
    }
    provenance["farmer_interpretation_layers"] = {
        "historical_yield_benchmarks": {
            "basis": (
                "Pre-target PSA agricultural history for the selected ecosystem "
                "and calendar quarter."
            ),
            "outputs": [
                "province same-quarter median",
                "recent five-year same-quarter median",
                "province historical upper quartile",
                "regional same-quarter median",
                "historical percentile",
            ],
            "interpretation": (
                "Historical reference benchmarks only; not a universal or "
                "agronomic optimum."
            ),
        },
        "associated_pre_target_signals": {
            "basis": (
                "Pre-target agricultural, NASA POWER seasonal history, and "
                "available MODIS vegetation context."
            ),
            "outputs": [
                "same-quarter production change",
                "same-quarter harvested-area change",
                "rainfall difference from seasonal median",
                "temperature difference from seasonal median",
                "NDVI difference from seasonal median",
            ],
            "interpretation": (
                "Associated conditions only; the system does not infer that an "
                "individual signal caused a yield change."
            ),
        },
        "xgboost_relationship": (
            "These interpretation layers do not modify the trained feature "
            "vector, model artifact, fixed 2025 evaluation, or prediction output."
        ),
    }
    PROVENANCE_PATH.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

def main() -> None:
    from tools.build_enso_history import main as update_enso_history

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    update_enso_history()
    prices = update_psa_farmgate_prices()
    pagasa = update_pagasa_agri_weather()
    climate = update_pagasa_climate_risk()
    update_provenance(prices, pagasa, climate)
    latest = prices.sort_values(["Year", "Month_Number"]).iloc[-1]
    print(
        f"Saved {len(prices):,} farmgate-price records through "
        f"{latest['Month']} {int(latest['Year'])}: {PRICE_PATH}"
    )
    print(
        f"Saved {len(pagasa['regions'])} PAGASA regional agri-weather records "
        f"for {pagasa.get('forecastPeriod') or 'the current published period'}: "
        f"{PAGASA_PATH}"
    )
    print(
        "Saved PAGASA climate-risk context for "
        f"{climate.get('drought', {}).get('loadedProvinces', 0)} provinces: "
        f"{PAGASA_CLIMATE_PATH}"
    )


if __name__ == "__main__":
    main()
