#!/usr/bin/env python3
"""
ANI Nueva Ecija pilot extractor
--------------------------------
Purpose:
1) Pull recent NASA POWER daily weather for a representative Nueva Ecija point.
2) Compute recent 10-day and 30-day conditions.
3) Compare rainfall with the same calendar windows from 2001-2025.
4) Optionally cross-check recent rainfall using CHIRPS v3 preliminary pentads.

IMPORTANT:
- This is a PILOT using a representative province point (15.5833 N, 121.0000 E).
- It is NOT yet the final province-area-weighted weather method.
- PAGASA forecast/hazard variables remain a separate live decision layer.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

LAT = 15.5833
LON = 121.0000
PROVINCE = "Nueva Ecija"

NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_PARAMETERS = ["PRECTOTCORR", "T2M", "RH2M", "WS2M"]

CHIRPS_PENTAD_BASE = (
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/"
    "prelim/pentads/global/tifs"
)

OUTDIR = Path("data/pilot")
OUTDIR.mkdir(parents=True, exist_ok=True)


def safe_get(url, params=None, timeout=90, attempts=4):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers={"User-Agent": "ANI-academic-pilot/1.0"},
            )
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Request failed after {attempts} attempts: {last}")


def fetch_nasa(start: date, end: date) -> pd.DataFrame:
    params = {
        "parameters": ",".join(NASA_PARAMETERS),
        "community": "AG",
        "longitude": LON,
        "latitude": LAT,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    payload = safe_get(NASA_URL, params=params).json()
    block = payload["properties"]["parameter"]

    dates = sorted(set().union(*(v.keys() for v in block.values())))
    rows = []
    for ds in dates:
        row = {"date": pd.to_datetime(ds, format="%Y%m%d")}
        for p in NASA_PARAMETERS:
            value = block.get(p, {}).get(ds)
            if value is None or value <= -900:
                value = math.nan
            row[p] = value
        rows.append(row)

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def valid_latest_date(df: pd.DataFrame) -> pd.Timestamp:
    req = ["PRECTOTCORR", "T2M", "RH2M", "WS2M"]
    ok = df.dropna(subset=req)
    if ok.empty:
        raise RuntimeError("NASA returned no complete recent daily observations.")
    return ok["date"].max()


def summarize_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    x = df[(df["date"] >= start) & (df["date"] <= end)].copy()
    expected = (end - start).days + 1
    if len(x.dropna(subset=["PRECTOTCORR"])) < max(1, expected - 1):
        raise RuntimeError(
            f"Too many missing rainfall values for {start.date()} to {end.date()}."
        )
    return {
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "days_expected": expected,
        "days_available": int(x["PRECTOTCORR"].notna().sum()),
        "rainfall_mm": round(float(x["PRECTOTCORR"].sum()), 2),
        "mean_temperature_c": round(float(x["T2M"].mean()), 2),
        "mean_rh_pct": round(float(x["RH2M"].mean()), 2),
        "mean_wind_m_s": round(float(x["WS2M"].mean()), 2),
    }


def same_month_day(year: int, month: int, day: int) -> date:
    day = min(day, monthrange(year, month)[1])
    return date(year, month, day)


def historical_window_stats(latest: pd.Timestamp, years=range(2001, 2026)):
    records = []

    for year in years:
        hist_end = same_month_day(year, latest.month, latest.day)
        hist_start = hist_end - timedelta(days=29)
        df = fetch_nasa(hist_start, hist_end)

        ts_end = pd.Timestamp(hist_end)
        ten_start = ts_end - pd.Timedelta(days=9)
        thirty_start = ts_end - pd.Timedelta(days=29)

        ten = df[(df["date"] >= ten_start) & (df["date"] <= ts_end)]
        thirty = df[(df["date"] >= thirty_start) & (df["date"] <= ts_end)]

        if ten["PRECTOTCORR"].notna().sum() >= 9 and thirty["PRECTOTCORR"].notna().sum() >= 28:
            records.append(
                {
                    "year": year,
                    "rainfall_10d_mm": float(ten["PRECTOTCORR"].sum()),
                    "rainfall_30d_mm": float(thirty["PRECTOTCORR"].sum()),
                }
            )

        print(f"Historical NASA window: {year}", flush=True)

    hist = pd.DataFrame(records)
    if hist.empty:
        raise RuntimeError("Could not build historical NASA rainfall baseline.")

    return hist


def pct_anomaly(value, baseline):
    if baseline is None or pd.isna(baseline) or baseline == 0:
        return None
    return round((value - baseline) / baseline * 100.0, 1)


def pentad_for_day(d: date):
    # CHIRPS pentads: 1=1-5, 2=6-10, 3=11-15, 4=16-20, 5=21-25, 6=26-end
    p = min(((d.day - 1) // 5) + 1, 6)
    start_day = [1, 6, 11, 16, 21, 26][p - 1]
    if p < 6:
        end_day = start_day + 4
    else:
        end_day = monthrange(d.year, d.month)[1]
    return p, date(d.year, d.month, start_day), date(d.year, d.month, end_day)


def completed_pentads_ending_on_or_before(end_date: date, count=6):
    found = []
    cursor = end_date
    seen = set()

    while len(found) < count:
        p, ps, pe = pentad_for_day(cursor)
        key = (pe.year, pe.month, p)
        if pe <= end_date and key not in seen:
            seen.add(key)
            found.append((p, ps, pe))
        cursor -= timedelta(days=1)

    return sorted(found, key=lambda x: x[2])


def chirps_point_value(year, month, pentad):
    try:
        import rasterio
        from rasterio.io import MemoryFile
    except ImportError:
        raise RuntimeError(
            "CHIRPS extraction requires rasterio. Install with: pip install rasterio"
        )

    filename = f"chirps-v3.0.{year}.{month:02d}.{pentad}.tif"
    url = f"{CHIRPS_PENTAD_BASE}/{filename}"
    response = safe_get(url, timeout=120)

    with MemoryFile(response.content) as mem:
        with mem.open() as src:
            value = float(next(src.sample([(LON, LAT)]))[0])
            nodata = src.nodata

    if (nodata is not None and value == nodata) or value <= -900:
        return math.nan
    return value


def fetch_chirps_recent(end_date: date):
    pentads = completed_pentads_ending_on_or_before(end_date, count=6)
    rows = []

    for p, ps, pe in pentads:
        print(f"CHIRPS v3 pentad: {ps} to {pe}", flush=True)
        val = chirps_point_value(pe.year, pe.month, p)
        rows.append(
            {
                "pentad_start": ps.isoformat(),
                "pentad_end": pe.isoformat(),
                "rainfall_mm": val,
            }
        )

    df = pd.DataFrame(rows)
    last2 = df.tail(2)
    last6 = df.tail(6)

    return df, {
        "period_10d_approx_start": last2.iloc[0]["pentad_start"],
        "period_10d_approx_end": last2.iloc[-1]["pentad_end"],
        "rainfall_10d_approx_mm": round(float(last2["rainfall_mm"].sum()), 2),
        "period_30d_approx_start": last6.iloc[0]["pentad_start"],
        "period_30d_approx_end": last6.iloc[-1]["pentad_end"],
        "rainfall_30d_approx_mm": round(float(last6["rainfall_mm"].sum()), 2),
        "note": "CHIRPS values are sums of the latest six completed preliminary pentads; period length may differ slightly from exactly 30 days at month boundaries.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--end",
        help="Preferred recent end date YYYY-MM-DD. Default: yesterday.",
    )
    parser.add_argument(
        "--skip-chirps",
        action="store_true",
        help="Run NASA only.",
    )
    args = parser.parse_args()

    preferred_end = (
        datetime.strptime(args.end, "%Y-%m-%d").date()
        if args.end
        else date.today() - timedelta(days=1)
    )

    # Fetch enough recent NASA days to tolerate normal NRT latency.
    recent_start = preferred_end - timedelta(days=44)
    print(f"Fetching NASA POWER {recent_start} to {preferred_end}...", flush=True)
    recent_df = fetch_nasa(recent_start, preferred_end)
    latest = valid_latest_date(recent_df)

    ten_start = latest - pd.Timedelta(days=9)
    thirty_start = latest - pd.Timedelta(days=29)

    recent_10 = summarize_window(recent_df, ten_start, latest)
    recent_30 = summarize_window(recent_df, thirty_start, latest)

    print("Building 2001-2025 same-calendar historical rainfall baseline...", flush=True)
    hist = historical_window_stats(latest)
    baseline_10 = float(hist["rainfall_10d_mm"].mean())
    baseline_30 = float(hist["rainfall_30d_mm"].mean())

    result = {
        "province": PROVINCE,
        "method": "representative province point pilot",
        "latitude": LAT,
        "longitude": LON,
        "latest_complete_nasa_date": latest.date().isoformat(),
        "nasa_recent_10d": recent_10,
        "nasa_recent_30d": recent_30,
        "nasa_2001_2025_same_calendar_baseline": {
            "years_used": int(len(hist)),
            "mean_rainfall_10d_mm": round(baseline_10, 2),
            "mean_rainfall_30d_mm": round(baseline_30, 2),
        },
        "nasa_rainfall_anomaly": {
            "rainfall_10d_anomaly_pct": pct_anomaly(
                recent_10["rainfall_mm"], baseline_10
            ),
            "rainfall_30d_anomaly_pct": pct_anomaly(
                recent_30["rainfall_mm"], baseline_30
            ),
        },
        "limitations": [
            "Pilot uses one representative Nueva Ecija point rather than province-area-weighted grids.",
            "NASA rainfall anomaly is observational context, not a planting recommendation threshold.",
            "Current/future PAGASA conditions must be merged separately in the decision-support layer.",
            "CHIRPS preliminary values should later be replaced by final values when available for historical archives.",
        ],
    }

    recent_df.to_csv(OUTDIR / "nueva_ecija_nasa_recent_daily.csv", index=False)
    hist.to_csv(OUTDIR / "nueva_ecija_nasa_historical_windows_2001_2025.csv", index=False)

    if not args.skip_chirps:
        try:
            chirps_df, chirps_summary = fetch_chirps_recent(latest.date())
            chirps_df.to_csv(
                OUTDIR / "nueva_ecija_chirps_v3_recent_pentads.csv", index=False
            )
            result["chirps_v3_recent"] = chirps_summary
        except Exception as exc:
            result["chirps_v3_recent"] = {
                "status": "not completed",
                "error": str(exc),
            }

    with open(OUTDIR / "nueva_ecija_pilot_conditions.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    flat = {
        "Province": PROVINCE,
        "Latitude": LAT,
        "Longitude": LON,
        "Latest_NASA_Date": result["latest_complete_nasa_date"],
        "Recent_Rainfall_10d_mm": recent_10["rainfall_mm"],
        "Recent_Rainfall_30d_mm": recent_30["rainfall_mm"],
        "Rainfall_10d_Climatology_mm": round(baseline_10, 2),
        "Rainfall_30d_Climatology_mm": round(baseline_30, 2),
        "Rainfall_10d_Anomaly_pct": result["nasa_rainfall_anomaly"]["rainfall_10d_anomaly_pct"],
        "Rainfall_30d_Anomaly_pct": result["nasa_rainfall_anomaly"]["rainfall_30d_anomaly_pct"],
        "Recent_Mean_Temperature_10d_C": recent_10["mean_temperature_c"],
        "Recent_Mean_RH_10d_pct": recent_10["mean_rh_pct"],
        "Recent_Mean_Wind_10d_m_s": recent_10["mean_wind_m_s"],
    }

    if isinstance(result.get("chirps_v3_recent"), dict):
        flat["CHIRPS_Rainfall_10d_Approx_mm"] = result["chirps_v3_recent"].get(
            "rainfall_10d_approx_mm"
        )
        flat["CHIRPS_Rainfall_30d_Approx_mm"] = result["chirps_v3_recent"].get(
            "rainfall_30d_approx_mm"
        )

    pd.DataFrame([flat]).to_csv(
        OUTDIR / "nueva_ecija_pilot_feature_row.csv", index=False
    )

    print("\n=== ANI Nueva Ecija pilot result ===")
    print(json.dumps(result, indent=2))
    print(f"\nSaved outputs under: {OUTDIR.resolve()}")


if __name__ == "__main__":
    main()
