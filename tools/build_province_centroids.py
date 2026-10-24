from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from tools.build_satellite_vegetation import (
    REFERENCE_DIR,
    load_province_geometries,
)

OUT = REFERENCE_DIR / "province_centroids.csv"


def ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    if len(ring) < 3:
        return 0.0, 0.0, 0.0
    area2 = 0.0
    cx6a = 0.0
    cy6a = 0.0
    pts = ring if ring[0] == ring[-1] else ring + [ring[0]]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx6a += (x0 + x1) * cross
        cy6a += (y0 + y1) * cross
    if abs(area2) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    area = area2 / 2.0
    cx = cx6a / (3.0 * area2)
    cy = cy6a / (3.0 * area2)
    return cx, cy, abs(area)


def geometry_centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polygons = coords if gtype == "MultiPolygon" else [coords]
    weighted_x = 0.0
    weighted_y = 0.0
    total_area = 0.0
    fallback: list[tuple[float, float]] = []
    for polygon in polygons:
        if not polygon:
            continue
        outer = polygon[0]
        cx, cy, area = ring_centroid(outer)
        fallback.extend((float(x), float(y)) for x, y in outer)
        if area > 0:
            weighted_x += cx * area
            weighted_y += cy * area
            total_area += area
    if total_area > 0:
        return weighted_y / total_area, weighted_x / total_area
    if fallback:
        xs = [p[0] for p in fallback]
        ys = [p[1] for p in fallback]
        return sum(ys) / len(ys), sum(xs) / len(xs)
    raise ValueError("Geometry has no usable coordinates.")


def main() -> None:
    provinces, geometries = load_province_geometries()
    rows = []
    for province in provinces:
        latitude, longitude = geometry_centroid(geometries[province])
        rows.append(
            {
                "Province": province,
                "Latitude": round(latitude, 6),
                "Longitude": round(longitude, 6),
                "Method": "DENR provincial boundary geometric centroid",
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Saved {len(rows)} province representative coordinates to {OUT}")


if __name__ == "__main__":
    main()
