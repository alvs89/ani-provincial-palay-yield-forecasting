from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import bounds as geometry_bounds
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
REFERENCE_DIR = ROOT / "data" / "reference"
HISTORY_PATH = DATA_DIR / "palay_history.csv"
DEFAULT_OUTPUT = DATA_DIR / "province_quarter_satellite.csv"
BOUNDARY_PATH = REFERENCE_DIR / "ph_provincial_boundaries_denr_simplified.geojson"

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
DENR_BOUNDARY_API = (
    "https://fmbfsd.denr.gov.ph/server/rest/services/Hosted/"
    "Provincial_Boundary/FeatureServer/0/query"
)
PHILIPPINES_BBOX = "116,4,127,21"

MODIS_COLLECTION = "modis-13A1-061"
LAND_COVER_COLLECTION = "esa-cci-lc"
NDVI_ASSET = "500m_16_days_NDVI"
EVI_ASSET = "500m_16_days_EVI"
RELIABILITY_ASSET = "500m_16_days_pixel_reliability"
LAND_COVER_ASSET = "lccs_class"

# ESA CCI LCCS classes used as the agricultural-land mask.
# 10-12: rainfed cropland variants
# 20: irrigated or post-flooding cropland
# 30: >50% cropland / natural-vegetation mosaic
CROPLAND_CLASSES = np.array([10, 11, 12, 20, 30], dtype=np.uint8)

# Dataset naming aliases between ANI and the current DENR province layer.
BOUNDARY_ALIASES = {
    "Davao de Oro (Compostela Valley)": "DAVAO DE ORO",
    "Samar": "SAMAR (WESTERN SAMAR)",
}


class SasSigner:
    """Obtain one SAS token per storage container and reuse it."""

    def __init__(self) -> None:
        self.tokens: dict[tuple[str, str], str] = {}

    def sign(self, href: str) -> str:
        parts = urlsplit(href)
        path_parts = parts.path.split("/")
        container = "/".join(path_parts[:2])
        key = (parts.netloc, container)
        token = self.tokens.get(key)

        if token is None:
            for attempt in range(8):
                response = requests.get(
                    PC_SIGN,
                    params={"href": href},
                    timeout=30,
                )
                if response.status_code == 429:
                    time.sleep(min(2**attempt, 30))
                    continue
                response.raise_for_status()
                token = urlsplit(response.json()["href"]).query
                self.tokens[key] = token
                break
            else:
                raise RuntimeError(f"Could not obtain an access token for {href}")

        query = parts.query
        if query and token:
            query += "&"
        query += token or ""
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
        )


def download_boundaries() -> dict[str, Any]:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    if not BOUNDARY_PATH.is_file():
        response = requests.get(
            DENR_BOUNDARY_API,
            params={
                "where": "1=1",
                "outFields": "province,province_,region",
                "f": "geojson",
                "outSR": 4326,
                "returnGeometry": "true",
                "maxAllowableOffset": 0.001,
                "geometryPrecision": 5,
            },
            timeout=120,
        )
        response.raise_for_status()
        BOUNDARY_PATH.write_bytes(response.content)

    return json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))


def load_province_geometries() -> tuple[list[str], dict[str, dict[str, Any]]]:
    history = pd.read_csv(HISTORY_PATH)
    provinces = sorted(history["Province"].dropna().unique().tolist())
    boundary = download_boundaries()
    by_name = {
        str(feature["properties"]["province"]).strip().upper(): feature["geometry"]
        for feature in boundary["features"]
        if feature["properties"].get("province")
    }

    geometries: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for province in provinces:
        source_name = BOUNDARY_ALIASES.get(province, province.upper())
        geometry = by_name.get(source_name.upper())
        if geometry is None:
            missing.append(province)
        else:
            geometries[province] = geometry

    if missing:
        raise RuntimeError(
            "No administrative boundary is available for: "
            + ", ".join(sorted(missing))
        )

    return provinces, geometries


def quarter_for_item(item: dict[str, Any]) -> int | None:
    props = item["properties"]
    start = datetime.fromisoformat(
        props["start_datetime"].replace("Z", "+00:00")
    )
    end = datetime.fromisoformat(
        props["end_datetime"].replace("Z", "+00:00")
    )
    start_quarter = (start.month - 1) // 3 + 1
    end_quarter = (end.month - 1) // 3 + 1
    if start_quarter != end_quarter:
        # Exclude composites that cross quarter boundaries so no pixels from
        # a later quarter enter a preceding-quarter feature.
        return None
    return start_quarter


def stac_search(
    collection: str,
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{PC_STAC}/search",
        params={
            "collections": collection,
            "bbox": PHILIPPINES_BBOX,
            "datetime": f"{start_date}/{end_date}",
            "limit": limit,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("features", [])


def land_cover_item(year: int) -> dict[str, Any]:
    items = stac_search(
        LAND_COVER_COLLECTION,
        f"{year}-01-01",
        f"{year}-12-31",
        limit=10,
    )
    if not items:
        raise RuntimeError(f"No ESA CCI land-cover item is available for {year}.")
    return items[0]


def modis_items(year: int) -> list[dict[str, Any]]:
    items = stac_search(
        MODIS_COLLECTION,
        f"{year}-01-01",
        f"{year}-12-31",
    )
    # Use Terra MOD13A1 only. Aqua begins later, so mixing platforms would
    # change temporal sampling across the historical series.
    terra = [
        item
        for item in items
        if item["id"].startswith("MOD13A1.")
        and quarter_for_item(item) is not None
    ]
    if not terra:
        raise RuntimeError(f"No usable Terra MOD13A1 items found for {year}.")
    return terra


def grid_context(
    sample_item: dict[str, Any],
    signed_sample_href: str,
    provinces: list[str],
    geometries: dict[str, dict[str, Any]],
    province_ids: dict[str, int],
    scale_factor: int,
) -> dict[str, Any] | None:
    with rasterio.open(signed_sample_href) as src:
        tile_bounds = src.bounds
        transformed: dict[str, dict[str, Any]] = {}
        candidate_bounds = []

        for province, geometry in geometries.items():
            geom = transform_geom(
                "EPSG:4326",
                src.crs,
                geometry,
                precision=1,
            )
            bounds = geometry_bounds(geom)
            if (
                bounds[2] <= tile_bounds.left
                or bounds[0] >= tile_bounds.right
                or bounds[3] <= tile_bounds.bottom
                or bounds[1] >= tile_bounds.top
            ):
                continue
            transformed[province] = geom
            candidate_bounds.append(bounds)

        if not candidate_bounds:
            return None

        left = max(tile_bounds.left, min(v[0] for v in candidate_bounds))
        bottom = max(tile_bounds.bottom, min(v[1] for v in candidate_bounds))
        right = min(tile_bounds.right, max(v[2] for v in candidate_bounds))
        top = min(tile_bounds.top, max(v[3] for v in candidate_bounds))

        window = from_bounds(
            left,
            bottom,
            right,
            top,
            src.transform,
        ).round_offsets().round_lengths()
        window = window.intersection(
            Window(0, 0, src.width, src.height)
        )

        out_height = max(1, int(math.ceil(window.height / scale_factor)))
        out_width = max(1, int(math.ceil(window.width / scale_factor)))
        out_shape = (out_height, out_width)
        base_transform = src.window_transform(window)
        transform = base_transform * rasterio.Affine.scale(
            window.width / out_width,
            window.height / out_height,
        )

        shapes = [
            (geometry, province_ids[province])
            for province, geometry in transformed.items()
        ]

        labels = rasterize(
            shapes,
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype="uint16",
        )

        return {
            "crs": src.crs,
            "window": window,
            "shape": out_shape,
            "transform": transform,
            "labels": labels,
            "provinces": transformed,
        }


def cropland_mask(
    signed_land_cover_href: str,
    context: dict[str, Any],
) -> np.ndarray:
    with rasterio.open(signed_land_cover_href) as src:
        with WarpedVRT(
            src,
            crs=context["crs"],
            transform=context["transform"],
            width=context["shape"][1],
            height=context["shape"][0],
            resampling=Resampling.nearest,
        ) as vrt:
            land_cover = vrt.read(1)
    return np.isin(land_cover, CROPLAND_CLASSES)


def item_statistics(
    item: dict[str, Any],
    context: dict[str, Any],
    crop_mask: np.ndarray,
    signer: SasSigner,
    province_count: int,
) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    quarter = quarter_for_item(item)
    if quarter is None:
        raise ValueError("Quarter-crossing composites must be filtered earlier.")

    hrefs = {
        key: signer.sign(item["assets"][key]["href"])
        for key in (NDVI_ASSET, EVI_ASSET, RELIABILITY_ASSET)
    }
    window = context["window"]
    shape = context["shape"]

    with rasterio.open(hrefs[NDVI_ASSET]) as src:
        ndvi = src.read(
            1,
            window=window,
            out_shape=shape,
            resampling=Resampling.average,
        )
    with rasterio.open(hrefs[EVI_ASSET]) as src:
        evi = src.read(
            1,
            window=window,
            out_shape=shape,
            resampling=Resampling.average,
        )
    with rasterio.open(hrefs[RELIABILITY_ASSET]) as src:
        reliability = src.read(
            1,
            window=window,
            out_shape=shape,
            resampling=Resampling.nearest,
        )

    labels = context["labels"]
    valid_base = (
        (labels > 0)
        & crop_mask
        & (reliability >= 0)
        & (reliability <= 1)
    )
    valid_ndvi = valid_base & (ndvi >= -2000) & (ndvi <= 10000)
    valid_evi = valid_base & (evi >= -2000) & (evi <= 10000)

    minlength = province_count + 1
    ndvi_count = np.bincount(
        labels[valid_ndvi],
        minlength=minlength,
    )
    ndvi_sum = np.bincount(
        labels[valid_ndvi],
        weights=ndvi[valid_ndvi],
        minlength=minlength,
    )
    evi_count = np.bincount(
        labels[valid_evi],
        minlength=minlength,
    )
    evi_sum = np.bincount(
        labels[valid_evi],
        weights=evi[valid_evi],
        minlength=minlength,
    )
    return quarter, ndvi_sum, ndvi_count, evi_sum, evi_count


def extract_year(
    year: int,
    scale_factor: int,
    item_workers: int,
    provinces: list[str],
    geometries: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    signer = SasSigner()
    province_ids = {
        province: index + 1
        for index, province in enumerate(provinces)
    }
    reverse_ids = {
        value: key
        for key, value in province_ids.items()
    }

    # Always use land-cover information that predates the vegetation year.
    # ESA CCI COG coverage on Planetary Computer currently ends in 2020.
    mask_year = min(year - 1, 2020)
    land_item = land_cover_item(mask_year)
    signed_land_cover = signer.sign(
        land_item["assets"][LAND_COVER_ASSET]["href"]
    )

    items = modis_items(year)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        props = item["properties"]
        grouped[
            (
                int(props["modis:horizontal-tile"]),
                int(props["modis:vertical-tile"]),
            )
        ].append(item)

    # [ndvi_sum, ndvi_count, evi_sum, evi_count, tile-composite contributions]
    accumulated: dict[
        tuple[str, int, int],
        list[float | int],
    ] = defaultdict(lambda: [0.0, 0, 0.0, 0, 0])

    for tile, tile_items in sorted(grouped.items()):
        sample = tile_items[0]
        signed_sample = signer.sign(
            sample["assets"][NDVI_ASSET]["href"]
        )
        context = grid_context(
            sample,
            signed_sample,
            provinces,
            geometries,
            province_ids,
            scale_factor,
        )
        if context is None:
            continue
        crop_mask = cropland_mask(
            signed_land_cover,
            context,
        )

        with ThreadPoolExecutor(max_workers=item_workers) as executor:
            futures = [
                executor.submit(
                    item_statistics,
                    item,
                    context,
                    crop_mask,
                    signer,
                    len(provinces),
                )
                for item in tile_items
            ]
            for future in as_completed(futures):
                (
                    quarter,
                    ndvi_sum,
                    ndvi_count,
                    evi_sum,
                    evi_count,
                ) = future.result()

                for province_id in range(1, len(provinces) + 1):
                    if not ndvi_count[province_id] and not evi_count[province_id]:
                        continue
                    province = reverse_ids[province_id]
                    key = (province, year, quarter)
                    values = accumulated[key]
                    values[0] += float(ndvi_sum[province_id])
                    values[1] += int(ndvi_count[province_id])
                    values[2] += float(evi_sum[province_id])
                    values[3] += int(evi_count[province_id])
                    values[4] += 1

    rows: list[dict[str, Any]] = []
    for (province, record_year, quarter), values in sorted(accumulated.items()):
        ndvi_sum, ndvi_count, evi_sum, evi_count, tile_composites = values
        if ndvi_count == 0 or evi_count == 0:
            continue
        rows.append(
            {
                "Province": province,
                "Year": record_year,
                "Quarter": quarter,
                "Cropland_NDVI_Mean": ndvi_sum / ndvi_count * 0.0001,
                "Cropland_EVI_Mean": evi_sum / evi_count * 0.0001,
                "Valid_Pixel_Observations": int(
                    min(ndvi_count, evi_count)
                ),
                "Tile_Composite_Contributions": int(tile_composites),
                "Land_Cover_Mask_Year": mask_year,
                "Satellite_Grid_Resolution_m": 500 * scale_factor,
                "Boundary_Context": "Province boundary",
            }
        )

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build quarterly cropland-masked MODIS NDVI/EVI summaries for ANI."
        )
    )
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument(
        "--scale-factor",
        type=int,
        default=1,
        help="Spatial aggregation factor for the native 500 m MODIS grid.",
    )
    parser.add_argument(
        "--item-workers",
        type=int,
        default=4,
        help="Concurrent MODIS composite reads per tile.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data" / "cache" / "satellite_vegetation_years",
        help="Per-year extraction cache used to resume interrupted runs.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild cached yearly extracts instead of reusing them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year < 2000:
        raise ValueError("MOD13A1 coverage begins in 2000.")
    if args.end_year < args.start_year:
        raise ValueError("end-year must be >= start-year.")
    if args.scale_factor < 1:
        raise ValueError("scale-factor must be >= 1.")

    provinces, geometries = load_province_geometries()
    frames = []
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    for year in range(args.start_year, args.end_year + 1):
        cache_path = args.cache_dir / (
            f"province_quarter_satellite_{year}_"
            f"{500 * args.scale_factor}m.csv"
        )
        if cache_path.is_file() and not args.refresh:
            frame = pd.read_csv(cache_path).rename(
                columns={
                    "Composite_Observations": "Tile_Composite_Contributions"
                }
            )
            frames.append(frame)
            print(
                f"{year}: {len(frame)} province-quarter rows "
                f"(cached)",
                flush=True,
            )
            continue

        started = time.time()
        frame = extract_year(
            year,
            args.scale_factor,
            args.item_workers,
            provinces,
            geometries,
        )
        frame.to_csv(cache_path, index=False)
        frames.append(frame)
        print(
            f"{year}: {len(frame)} province-quarter rows "
            f"({time.time() - started:.1f}s)",
            flush=True,
        )

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(
        ["Province", "Year", "Quarter"]
    ).reset_index(drop=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    expected = len(provinces) * 4 * (
        args.end_year - args.start_year + 1
    )
    print(f"Saved: {args.output}")
    print(f"Rows: {len(result)} / {expected}")
    print(
        "NDVI range: "
        f"{result['Cropland_NDVI_Mean'].min():.4f} to "
        f"{result['Cropland_NDVI_Mean'].max():.4f}"
    )
    print(
        "EVI range: "
        f"{result['Cropland_EVI_Mean'].min():.4f} to "
        f"{result['Cropland_EVI_Mean'].max():.4f}"
    )


if __name__ == "__main__":
    main()
