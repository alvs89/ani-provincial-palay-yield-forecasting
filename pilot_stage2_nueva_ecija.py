#!/usr/bin/env python3
"""
ANI Pilot Stage 2 — Nueva Ecija
================================
This stage does TWO things:

1) Exact-period NASA ↔ CHIRPS cross-check
   - Reuses the CHIRPS pentad windows created by Stage 1.
   - Recalculates NASA POWER rainfall over those EXACT SAME dates.
   - This avoids comparing different date windows.

2) PAGASA live/future-data connection test
   - Calls the documented PAGASA 10-day and seasonal endpoints.
   - Saves the raw responses first, without inventing field meanings.
   - This is a connectivity/schema audit before recommendation rules are built.

Run from the ANI project root:
    python pilot_stage2_nueva_ecija.py

Optional:
    python pilot_stage2_nueva_ecija.py --province "Nueva Ecija"

If PAGASA later requires a token:
    set PAGASA_API_TOKEN=your_token_here
    python pilot_stage2_nueva_ecija.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ---------------------------------------------------------------------
# Pilot configuration
# ---------------------------------------------------------------------

DEFAULT_PROVINCE = "Nueva Ecija"
LAT = 15.5833
LON = 121.0000

NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_PARAMS = ["PRECTOTCORR", "T2M", "RH2M", "WS2M"]

PAGASA_BASE = "https://tenday.pagasa.dost.gov.ph/api/v1"

OUTDIR = Path("data/pilot")
OUTDIR.mkdir(parents=True, exist_ok=True)

STAGE1_JSON = OUTDIR / "nueva_ecija_pilot_conditions.json"
STAGE1_CHIRPS = OUTDIR / "nueva_ecija_chirps_v3_recent_pentads.csv"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ANI-academic-pilot/2.0"})


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def safe_get(url: str, params=None, timeout=90, attempts=4):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"GET failed after {attempts} attempts: {url}\n{last}")


def to_iso_date(value) -> str:
    return pd.to_datetime(value).date().isoformat()


def fetch_nasa(start: str, end: str) -> pd.DataFrame:
    params = {
        "parameters": ",".join(NASA_PARAMS),
        "community": "AG",
        "longitude": LON,
        "latitude": LAT,
        "start": pd.to_datetime(start).strftime("%Y%m%d"),
        "end": pd.to_datetime(end).strftime("%Y%m%d"),
        "format": "JSON",
    }
    payload = safe_get(NASA_URL, params=params).json()
    block = payload["properties"]["parameter"]

    dates = sorted(set().union(*(x.keys() for x in block.values())))
    rows = []

    for ds in dates:
        row = {"date": pd.to_datetime(ds, format="%Y%m%d")}
        for p in NASA_PARAMS:
            value = block.get(p, {}).get(ds)
            if value is None or value <= -900:
                value = math.nan
            row[p] = value
        rows.append(row)

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def summarize_nasa(df: pd.DataFrame, start: str, end: str) -> dict[str, Any]:
    s = pd.to_datetime(start)
    e = pd.to_datetime(end)
    x = df[(df["date"] >= s) & (df["date"] <= e)].copy()

    expected = (e - s).days + 1
    available = int(x["PRECTOTCORR"].notna().sum())

    return {
        "start": s.date().isoformat(),
        "end": e.date().isoformat(),
        "days_expected": int(expected),
        "rainfall_days_available": available,
        "rainfall_mm": round(float(x["PRECTOTCORR"].sum()), 2),
        "mean_temperature_c": round(float(x["T2M"].mean()), 2),
        "mean_rh_pct": round(float(x["RH2M"].mean()), 2),
        "mean_wind_m_s": round(float(x["WS2M"].mean()), 2),
    }


def pct_difference(a: float, b: float):
    """
    Symmetric percent difference.
    This is a cross-source agreement indicator, NOT an accuracy score.
    """
    denom = (abs(a) + abs(b)) / 2
    if denom == 0:
        return 0.0
    return round(abs(a - b) / denom * 100, 1)


def relative_difference(nasa: float, chirps: float):
    """
    NASA relative to CHIRPS.
    Positive = NASA wetter; negative = NASA drier.
    """
    if chirps == 0:
        return None
    return round((nasa - chirps) / chirps * 100, 1)


def json_to_flat_csv(payload: Any, path: Path):
    try:
        if isinstance(payload, dict):
            # Common API response wrappers.
            for key in ("data", "results", "result", "forecast", "forecasts"):
                if key in payload and isinstance(payload[key], list):
                    df = pd.json_normalize(payload[key], sep=".")
                    df.to_csv(path, index=False)
                    return
            df = pd.json_normalize(payload, sep=".")
        elif isinstance(payload, list):
            df = pd.json_normalize(payload, sep=".")
        else:
            df = pd.DataFrame([{"value": payload}])
        df.to_csv(path, index=False)
    except Exception as exc:
        pd.DataFrame([{"flatten_error": str(exc)}]).to_csv(path, index=False)


def call_pagasa(endpoint: str, params=None, token=None):
    url = f"{PAGASA_BASE}/{endpoint.lstrip('/')}"
    params = dict(params or {})
    headers = {}

    # Token support is optional because endpoint access can change.
    if token:
        params.setdefault("token", token)
        headers["Authorization"] = f"Bearer {token}"

    r = SESSION.get(url, params=params, headers=headers, timeout=60)

    result = {
        "url": r.url,
        "status_code": r.status_code,
        "content_type": r.headers.get("content-type"),
    }

    try:
        result["payload"] = r.json()
    except Exception:
        result["payload_text"] = r.text[:5000]

    return result


# ---------------------------------------------------------------------
# Stage 2A — exact-period NASA ↔ CHIRPS comparison
# ---------------------------------------------------------------------

def run_aligned_rainfall():
    if not STAGE1_CHIRPS.exists():
        raise FileNotFoundError(
            f"Missing {STAGE1_CHIRPS}. Run pilot_nueva_ecija_conditions.py first."
        )

    chirps = pd.read_csv(STAGE1_CHIRPS)

    required = {"pentad_start", "pentad_end", "rainfall_mm"}
    if not required.issubset(chirps.columns):
        raise RuntimeError(
            f"{STAGE1_CHIRPS} does not contain expected columns: {sorted(required)}"
        )

    chirps = chirps.sort_values("pentad_end").reset_index(drop=True)
    if len(chirps) < 6:
        raise RuntimeError("Need at least 6 CHIRPS pentads from Stage 1.")

    last2 = chirps.tail(2)
    last6 = chirps.tail(6)

    windows = {
        "aligned_10d": {
            "start": to_iso_date(last2.iloc[0]["pentad_start"]),
            "end": to_iso_date(last2.iloc[-1]["pentad_end"]),
            "chirps_rainfall_mm": round(float(last2["rainfall_mm"].sum()), 2),
        },
        "aligned_30d": {
            "start": to_iso_date(last6.iloc[0]["pentad_start"]),
            "end": to_iso_date(last6.iloc[-1]["pentad_end"]),
            "chirps_rainfall_mm": round(float(last6["rainfall_mm"].sum()), 2),
        },
    }

    global_start = windows["aligned_30d"]["start"]
    global_end = windows["aligned_10d"]["end"]

    print(f"Fetching NASA POWER for exact CHIRPS period {global_start} to {global_end}...")
    nasa = fetch_nasa(global_start, global_end)
    nasa.to_csv(OUTDIR / "nueva_ecija_nasa_chirps_aligned_daily.csv", index=False)

    comparison_rows = []

    for label, info in windows.items():
        n = summarize_nasa(nasa, info["start"], info["end"])
        nasa_rain = n["rainfall_mm"]
        chirps_rain = info["chirps_rainfall_mm"]

        info["nasa"] = n
        info["symmetric_percent_difference"] = pct_difference(nasa_rain, chirps_rain)
        info["nasa_relative_to_chirps_pct"] = relative_difference(nasa_rain, chirps_rain)

        comparison_rows.append(
            {
                "Window": label,
                "Start": info["start"],
                "End": info["end"],
                "NASA_Rainfall_mm": nasa_rain,
                "CHIRPS_Rainfall_mm": chirps_rain,
                "Absolute_Difference_mm": round(abs(nasa_rain - chirps_rain), 2),
                "Symmetric_Percent_Difference": info["symmetric_percent_difference"],
                "NASA_Relative_to_CHIRPS_pct": info["nasa_relative_to_chirps_pct"],
                "NASA_Days_Available": n["rainfall_days_available"],
            }
        )

    pd.DataFrame(comparison_rows).to_csv(
        OUTDIR / "nueva_ecija_nasa_chirps_aligned_comparison.csv",
        index=False,
    )

    return windows


# ---------------------------------------------------------------------
# Stage 2B — PAGASA API audit / live future layer
# ---------------------------------------------------------------------

def run_pagasa(province: str):
    token = os.getenv("PAGASA_API_TOKEN")

    tests = {
        "issuance": ("tenday/issuance", {}),
        "location": ("location", {"province": province}),
        "current": ("tenday/current", {"province": province, "page": "none"}),
        "full_10day": ("tenday/full", {"province": province, "page": "none"}),
        "seasonal_province": ("seasonal/province", {"value": "all"}),
    }

    statuses = {}

    for name, (endpoint, params) in tests.items():
        print(f"PAGASA API: {name}...")
        result = call_pagasa(endpoint, params=params, token=token)

        status = result["status_code"]
        statuses[name] = {
            "status_code": status,
            "url": result["url"],
            "content_type": result.get("content_type"),
        }

        raw_path = OUTDIR / f"pagasa_{name}_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        if "payload" in result:
            json_to_flat_csv(
                result["payload"],
                OUTDIR / f"pagasa_{name}_flat.csv",
            )

        print(f"  HTTP {status}")

    return statuses


# ---------------------------------------------------------------------
# Combined Stage 2 result
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--province", default=DEFAULT_PROVINCE)
    args = parser.parse_args()

    print("=== ANI Pilot Stage 2 ===")
    print(f"Province: {args.province}\n")

    aligned = run_aligned_rainfall()
    pagasa = run_pagasa(args.province)

    result = {
        "province": args.province,
        "representative_point": {"latitude": LAT, "longitude": LON},
        "stage": 2,
        "aligned_nasa_chirps": aligned,
        "pagasa_api_audit": pagasa,
        "interpretation_rules_applied": False,
        "recommendation_generated": False,
        "notes": [
            "NASA and CHIRPS rainfall are now compared over identical date windows.",
            "Cross-source difference is not an accuracy score because neither source is treated as ground truth.",
            "PAGASA responses are saved raw before any field is mapped into recommendation variables.",
            "No Favorable/Caution/Unfavorable rule is applied yet.",
            "The next step is to inspect the actual PAGASA response schema and map supported fields.",
        ],
    }

    with open(
        OUTDIR / "nueva_ecija_stage2_combined.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("\n=== Exact-date rainfall cross-check ===")
    for name, x in aligned.items():
        print(
            f"{name}: {x['start']} to {x['end']} | "
            f"NASA={x['nasa']['rainfall_mm']} mm | "
            f"CHIRPS={x['chirps_rainfall_mm']} mm | "
            f"sym. difference={x['symmetric_percent_difference']}%"
        )

    print("\n=== PAGASA connectivity ===")
    for name, x in pagasa.items():
        print(f"{name}: HTTP {x['status_code']}")

    print("\nSaved Stage 2 outputs under:")
    print(OUTDIR.resolve())

    print("\nIMPORTANT:")
    print(
        "Do not interpret the cross-source percent difference as model error. "
        "NASA POWER and CHIRPS are independent gridded rainfall estimates."
    )
    print(
        "Send the terminal output plus pagasa_full_10day_raw.json and "
        "pagasa_seasonal_province_raw.json for the next validation step."
    )


if __name__ == "__main__":
    main()
