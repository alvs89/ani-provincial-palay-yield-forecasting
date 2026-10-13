#!/usr/bin/env python3
"""ANI Pilot Stage 6 — FAO-56 ET₀ and water-balance evidence layer.

Purpose
-------
Stage 6 adds a defensible atmospheric water-demand signal to ANI using
Open-Meteo's daily FAO-56 reference evapotranspiration (ET₀).

Important methodological guardrail
----------------------------------
This script DOES NOT assume that forecast rainfall equals effective rainfall.
FAO defines effective rainfall as the portion of rainfall retained in the crop
root zone after losses such as runoff and deep percolation. Without a validated
soil/runoff/root-zone method, effective rainfall remains unavailable.

The default outputs therefore include:
- total forecast rainfall
- total FAO-56 ET₀
- climatic water balance = rainfall - ET₀
- rainfall / ET₀ ratio
- daily rainfall and ET₀
- effective rainfall = null unless a provisional, user-supplied fraction is used

The user-supplied effective-rainfall fraction is intentionally marked
PROVISIONAL and must not be described as locally validated.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
PILOT_DATA_DIR = ROOT / "data" / "pilot"

DEFAULT_STAGE4 = OUTPUT_DIR / "stage4_condition_interpretation.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "stage6_water_balance.json"
DEFAULT_RAW = PILOT_DATA_DIR / "nueva_ecija_stage6_openmeteo_raw.json"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Same representative point currently used by ANI Stage 3.
DEFAULT_LAT = 15.5833
DEFAULT_LON = 121.0000
DEFAULT_TIMEZONE = "Asia/Manila"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ANI-CS406-academic-project/6.0"})


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_json(
    url: str,
    params: dict[str, Any],
    timeout: int = 60,
    attempts: int = 4,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            response = SESSION.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(min(2 ** (attempt + 1), 8))

    raise RuntimeError(f"Open-Meteo request failed after {attempts} attempts: {last_error}")


def resolve_window(stage4: dict[str, Any]) -> tuple[str, str]:
    window = stage4.get("forecast_window") or {}
    start = window.get("start")
    end = window.get("end")

    if not start or not end:
        raise ValueError(
            "Stage 4 JSON does not contain forecast_window.start and forecast_window.end."
        )

    # Validate ISO dates.
    date.fromisoformat(start)
    date.fromisoformat(end)

    if date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("Forecast end date occurs before forecast start date.")

    return start, end


def fetch_open_meteo(
    latitude: float,
    longitude: float,
    timezone: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(
            [
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "temperature_2m_mean",
                "temperature_2m_max",
                "temperature_2m_min",
                "shortwave_radiation_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
            ]
        ),
    }
    return get_json(OPEN_METEO_URL, params=params)


def _series(raw: dict[str, Any], key: str) -> list[Any]:
    daily = raw.get("daily")
    if not isinstance(daily, dict):
        raise ValueError("Open-Meteo response does not contain a daily object.")

    values = daily.get(key)
    if not isinstance(values, list):
        raise ValueError(f"Open-Meteo response is missing daily.{key}.")

    return values


def _number(value: Any, field: str, day: str) -> float:
    if value is None:
        raise ValueError(f"Missing {field} for {day}.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} value for {day}: {value!r}") from exc


def build_daily_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    dates = _series(raw, "time")
    precipitation = _series(raw, "precipitation_sum")
    et0 = _series(raw, "et0_fao_evapotranspiration")

    optional_keys = [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "shortwave_radiation_sum",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
    ]
    optional = {
        key: raw.get("daily", {}).get(key, [None] * len(dates))
        for key in optional_keys
    }

    if not (len(dates) == len(precipitation) == len(et0)):
        raise ValueError("Open-Meteo daily arrays have inconsistent lengths.")

    rows: list[dict[str, Any]] = []

    for i, day in enumerate(dates):
        p = _number(precipitation[i], "precipitation_sum", str(day))
        e = _number(et0[i], "et0_fao_evapotranspiration", str(day))

        row = {
            "date": str(day),
            "precipitation_mm": round(p, 3),
            "et0_fao56_mm": round(e, 3),
            "climatic_water_balance_mm": round(p - e, 3),
        }

        for key in optional_keys:
            values = optional[key]
            value = values[i] if isinstance(values, list) and i < len(values) else None
            row[key] = None if value is None else round(float(value), 3)

        rows.append(row)

    return rows


def classify_climatic_balance(total_p: float, total_et0: float) -> str:
    """Descriptive climate signal only — not a planting recommendation."""
    if total_et0 <= 0:
        return "UNAVAILABLE"

    ratio = total_p / total_et0

    if ratio >= 1.0:
        return "RAINFALL_MEETS_OR_EXCEEDS_REFERENCE_ET0"
    if ratio >= 0.75:
        return "RAINFALL_MODERATELY_BELOW_REFERENCE_ET0"
    return "RAINFALL_WELL_BELOW_REFERENCE_ET0"


def build_report(
    stage4: dict[str, Any],
    raw: dict[str, Any],
    effective_rainfall_fraction: float | None,
    crop_coefficient: float | None,
) -> dict[str, Any]:
    daily_rows = build_daily_rows(raw)

    total_p = round(sum(row["precipitation_mm"] for row in daily_rows), 3)
    total_et0 = round(sum(row["et0_fao56_mm"] for row in daily_rows), 3)
    climate_balance = round(total_p - total_et0, 3)
    ratio = None if total_et0 == 0 else round(total_p / total_et0, 3)

    if effective_rainfall_fraction is None:
        peff = None
        peff_status = "WITHHELD_NO_VALIDATED_SOIL_RUNOFF_MODEL"
        peff_method = None
        peff_note = (
            "Effective rainfall is not calculated by default because rainfall retained "
            "in the root zone depends on runoff, deep percolation, soil properties, "
            "root-zone depth, antecedent moisture, and local conditions."
        )
    else:
        if not 0 <= effective_rainfall_fraction <= 1:
            raise ValueError("--effective-rainfall-fraction must be between 0 and 1.")
        peff = round(total_p * effective_rainfall_fraction, 3)
        peff_status = "PROVISIONAL_USER_SUPPLIED_FRACTION"
        peff_method = "P_eff = forecast rainfall × user-supplied fraction"
        peff_note = (
            "This is a scenario value only. The supplied fraction has not been validated "
            "by this script and must not be represented as a locally validated agronomic rule."
        )

    if crop_coefficient is None:
        etc_total = None
        crop_balance = None
        kc_status = "NOT_CALCULATED_NO_CROP_COEFFICIENT"
    else:
        if crop_coefficient <= 0:
            raise ValueError("--kc must be greater than 0.")
        etc_total = round(total_et0 * crop_coefficient, 3)
        crop_balance = None if peff is None else round(peff - etc_total, 3)
        kc_status = "PROVISIONAL_USER_SUPPLIED_KC"

    return {
        "stage": 6,
        "name": "ANI FAO-56 ET0 and Water-Balance Evidence Layer",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "location": stage4.get("location", "Nueva Ecija"),
        "ecosystem": stage4.get("ecosystem"),
        "water_source": stage4.get("water_source"),
        "forecast_window": stage4.get("forecast_window"),
        "representative_point": {
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
            "elevation_m": raw.get("elevation"),
            "timezone": raw.get("timezone"),
        },
        "water_balance": {
            "forecast_rainfall_mm": total_p,
            "reference_et0_fao56_mm": total_et0,
            "climatic_water_balance_p_minus_et0_mm": climate_balance,
            "rainfall_to_et0_ratio": ratio,
            "climatic_balance_signal": classify_climatic_balance(total_p, total_et0),
        },
        "effective_rainfall": {
            "effective_rainfall_mm": peff,
            "status": peff_status,
            "method": peff_method,
            "note": peff_note,
        },
        "crop_water_demand": {
            "kc": crop_coefficient,
            "status": kc_status,
            "estimated_etc_mm": etc_total,
            "provisional_effective_rainfall_minus_etc_mm": crop_balance,
            "note": (
                "ETc = Kc × ET0 is only calculated when a crop coefficient is explicitly "
                "supplied. Rice Kc varies with growth stage and management."
            ),
        },
        "daily": daily_rows,
        "methodology": {
            "et0": (
                "Daily ET0 is obtained from Open-Meteo's et0_fao_evapotranspiration "
                "variable, documented as FAO-56 Penman-Monteith reference evapotranspiration."
            ),
            "climatic_water_balance": (
                "P - ET0 is an atmospheric/climatic context indicator. It is not equivalent "
                "to soil water balance, effective rainfall, or crop-specific water sufficiency."
            ),
            "effective_rainfall_guardrail": (
                "ANI does not equate precipitation with effective rainfall. A validated "
                "soil/runoff/root-zone method is required before effective rainfall can be "
                "treated as an agronomic decision input."
            ),
        },
        "stage5_integration": {
            "can_supply_effective_rainfall_now": peff is not None,
            "safe_to_treat_as_validated": False,
            "suggested_stage5_argument": (
                None if peff is None else f"--effective-rainfall-mm {peff:.3f}"
            ),
            "warning": (
                "Even when a provisional effective-rainfall fraction is supplied, Stage 5 "
                "must continue withholding a final recommendation while the ruleset remains UNVALIDATED."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ANI Stage 6: fetch daily FAO-56 ET0 and calculate a forecast-window "
            "climatic water balance without assuming rainfall is fully effective."
        )
    )
    parser.add_argument(
        "--stage4",
        type=Path,
        default=DEFAULT_STAGE4,
        help="Stage 4 JSON. Default: outputs/stage4_condition_interpretation.json",
    )
    parser.add_argument("--latitude", type=float, default=DEFAULT_LAT)
    parser.add_argument("--longitude", type=float, default=DEFAULT_LON)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument(
        "--effective-rainfall-fraction",
        type=float,
        default=None,
        help=(
            "Optional provisional fraction from 0 to 1. Do not use unless you have a "
            "documented local/validated basis. Omit by default."
        ),
    )
    parser.add_argument(
        "--kc",
        type=float,
        default=None,
        help=(
            "Optional provisional crop coefficient. ETc=Kc*ET0 will only be shown if supplied."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON. Default: outputs/stage6_water_balance.json",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=DEFAULT_RAW,
        help="Raw Open-Meteo response JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    stage4_path = args.stage4
    if not stage4_path.is_absolute():
        stage4_path = ROOT / stage4_path

    output_path = args.output
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    raw_path = args.raw_output
    if not raw_path.is_absolute():
        raw_path = ROOT / raw_path

    stage4 = load_json(stage4_path)
    start_date, end_date = resolve_window(stage4)

    print("=== ANI Pilot Stage 6 ===")
    print(
        f"{stage4.get('location', 'Nueva Ecija')} {stage4.get('ecosystem', '')} | "
        f"window: {start_date} to {end_date}"
    )
    print("Fetching daily precipitation and FAO-56 ET0 from Open-Meteo...")

    raw = fetch_open_meteo(
        latitude=args.latitude,
        longitude=args.longitude,
        timezone=args.timezone,
        start_date=start_date,
        end_date=end_date,
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    report = build_report(
        stage4=stage4,
        raw=raw,
        effective_rainfall_fraction=args.effective_rainfall_fraction,
        crop_coefficient=args.kc,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    wb = report["water_balance"]
    peff = report["effective_rainfall"]

    print()
    print(f"Forecast rainfall: {wb['forecast_rainfall_mm']} mm")
    print(f"FAO-56 reference ET0: {wb['reference_et0_fao56_mm']} mm")
    print(
        "Climatic water balance (P - ET0): "
        f"{wb['climatic_water_balance_p_minus_et0_mm']} mm"
    )
    print(f"Rainfall / ET0 ratio: {wb['rainfall_to_et0_ratio']}")
    print(f"Climate signal: {wb['climatic_balance_signal']}")
    print()
    print(f"Effective rainfall status: {peff['status']}")
    print(f"Effective rainfall: {peff['effective_rainfall_mm']}")
    print()
    print(f"Saved report: {output_path}")
    print(f"Saved raw Open-Meteo response: {raw_path}")

    if peff["effective_rainfall_mm"] is None:
        print()
        print(
            "Stage 6 intentionally did NOT manufacture effective rainfall. "
            "Next requirement: local soil/runoff/root-zone calibration."
        )
    else:
        print()
        print(
            "A provisional effective-rainfall scenario was calculated. "
            "It is NOT locally validated and must not unlock a final planting recommendation."
        )


if __name__ == "__main__":
    main()
