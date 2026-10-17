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
PROVENANCE_PATH = DATA_DIR / "data_provenance.json"

PSA_API = (
    "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2M/NFG/"
    "0032M4AFN01.px"
)
PSA_SOURCE_URL = (
    "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/"
    "DB__2M__NFG/0032M4AFN01.px/"
)
PAGASA_URL = "https://www.pagasa.dost.gov.ph/ten-day-regional-agri-weather"


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
    page = response.text

    plain = _strip_html(page)
    dekad_match = re.search(
        r"DEKAD\s+NO\.\s*(\d+)\s+([0-9]{1,2}\s*-\s*[0-9]{1,2}\s+"
        r"[A-Z]+\s+20\d{2})",
        plain,
        flags=re.I,
    )

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



def update_provenance(prices: pd.DataFrame, pagasa: dict) -> None:
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prices = update_psa_farmgate_prices()
    pagasa = update_pagasa_agri_weather()
    update_provenance(prices, pagasa)
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


if __name__ == "__main__":
    main()
