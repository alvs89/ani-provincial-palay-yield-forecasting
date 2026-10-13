#!/usr/bin/env python3
"""ANI Pilot Stage 7 — Site-context capture for Nueva Ecija rainfed rice.

This stage records two inputs that Stage 5 currently lacks:
1) crop establishment method
2) verified local soil series

The Nueva Ecija rainfed-rice suitability codes are based on the
PhilRice Soil Information System provincial suitability table.

Guardrail:
- Suitability is site context, not a planting-date recommendation.
- A province contains multiple soil series; do not guess the field's series.
- If the soil series is unknown, keep it unknown and continue withholding
  the final planting recommendation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
CONFIG_DIR = ROOT / "config"

DEFAULT_CONFIG = CONFIG_DIR / "nueva_ecija_soil_context.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "stage7_site_context.json"

ESTABLISHMENT_METHODS = {
    "dry-direct-seeding": "Dry direct seeding",
    "wet-direct-seeding": "Wet direct seeding",
    "transplanting": "Transplanting",
}

LIMITATION_LABELS = {
    "c": "climate",
    "t": "topography / slope",
    "s": "texture / coarse fragments / soil depth",
    "f": "soil fertility",
    "w": "drainage / flooding",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_suitability_code(code: str | None) -> dict[str, Any]:
    if not code:
        return {
            "rating_code": None,
            "rating_label": "Unknown",
            "limitation_codes": [],
            "limitations": [],
        }

    code = code.strip()
    rating = code[:2] if len(code) >= 2 else code
    suffix = code[2:] if len(code) > 2 else ""

    rating_labels = {
        "S1": "Highly Suitable",
        "S2": "Moderately Suitable",
        "S3": "Marginally Suitable",
        "N1": "Currently Not Suitable",
        "N2": "Permanently Not Suitable",
    }

    limitation_codes = [c for c in suffix if c in LIMITATION_LABELS]
    limitations = [LIMITATION_LABELS[c] for c in limitation_codes]

    return {
        "rating_code": rating,
        "rating_label": rating_labels.get(rating, "Unknown"),
        "limitation_codes": limitation_codes,
        "limitations": limitations,
    }


def build_report(
    config: dict[str, Any],
    establishment_method: str | None,
    soil_series: str | None,
) -> dict[str, Any]:
    soils = config.get("soil_series", {})

    method_available = establishment_method in ESTABLISHMENT_METHODS

    selected_soil: dict[str, Any] | None = None
    normalized_name: str | None = None

    if soil_series:
        for name, info in soils.items():
            if name.lower() == soil_series.strip().lower():
                normalized_name = name
                selected_soil = info
                break

        if selected_soil is None:
            valid = ", ".join(sorted(soils))
            raise ValueError(
                f"Unknown Nueva Ecija soil series: {soil_series!r}. "
                f"Valid configured series: {valid}"
            )

    suitability = parse_suitability_code(
        selected_soil.get("rainfed_rice_suitability")
        if selected_soil
        else None
    )

    runtime_blocks: list[str] = []
    if not method_available:
        runtime_blocks.append("establishment_method")
    if selected_soil is None:
        runtime_blocks.append("soil_series")

    if runtime_blocks:
        site_context_status = "INCOMPLETE"
    else:
        site_context_status = "RECORDED"

    if selected_soil is None:
        interpretation = (
            "Local soil series is not yet verified. Nueva Ecija contains multiple "
            "soil series with materially different rainfed-rice suitability and "
            "limitations, so ANI will not infer one from the province alone."
        )
    else:
        interpretation = (
            f"{normalized_name} is classified by the configured PhilRice-derived "
            f"rainfed-rice context as {suitability['rating_label']} "
            f"({suitability['rating_code']})."
        )
        if suitability["limitations"]:
            interpretation += (
                " Reported limitation categories: "
                + ", ".join(suitability["limitations"])
                + "."
            )

    return {
        "stage": 7,
        "name": "ANI Nueva Ecija Site-Context Capture",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "site_context_status": site_context_status,
        "establishment_method": {
            "code": establishment_method if method_available else None,
            "label": (
                ESTABLISHMENT_METHODS[establishment_method]
                if method_available
                else None
            ),
            "status": "AVAILABLE" if method_available else "MISSING",
        },
        "soil_context": {
            "soil_series": normalized_name,
            "status": "AVAILABLE" if selected_soil else "MISSING",
            "rainfed_rice_suitability": suitability,
            "source_note": (
                selected_soil.get("source_note")
                if selected_soil
                else config.get("source_note")
            ),
        },
        "interpretation": interpretation,
        "runtime_blocks": runtime_blocks,
        "effective_rainfall_ready": False,
        "hydraulic_data_still_needed": [
            "field capacity or equivalent maximum root-zone water storage",
            "wilting point / lower soil-water bound",
            "effective root-zone depth for the selected crop stage",
            "runoff / deep-percolation method or locally validated effective-rainfall method",
        ],
        "stage5_integration": {
            "can_resolve_establishment_method": method_available,
            "can_resolve_soil_series": selected_soil is not None,
            "suggested_arguments": (
                None
                if runtime_blocks
                else (
                    f'--establishment-method {establishment_method} '
                    f'--soil-series "{normalized_name}"'
                )
            ),
            "warning": (
                "These inputs resolve Stage 5 site-context gaps only. "
                "They do not validate the planting thresholds or effective rainfall."
            ),
        },
        "methodology_guardrail": (
            "PhilRice soil suitability provides land/soil context. ANI must not "
            "convert a suitability class alone into a planting-date recommendation."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ANI Stage 7: record establishment method and verified Nueva Ecija "
            "soil-series context."
        )
    )
    parser.add_argument(
        "--establishment-method",
        choices=sorted(ESTABLISHMENT_METHODS),
        default=None,
    )
    parser.add_argument(
        "--soil-series",
        default=None,
        help=(
            "Verified local soil series. Run with --list-soils to see configured choices."
        ),
    )
    parser.add_argument(
        "--list-soils",
        action="store_true",
        help="Print configured Nueva Ecija soil series and rainfed-rice suitability.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config_path = args.config
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    output_path = args.output
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    config = load_json(config_path)

    if args.list_soils:
        print("Configured Nueva Ecija soil series (rainfed rice):")
        for name, info in sorted(config.get("soil_series", {}).items()):
            parsed = parse_suitability_code(info.get("rainfed_rice_suitability"))
            limitations = (
                ", ".join(parsed["limitations"])
                if parsed["limitations"]
                else "none encoded"
            )
            print(
                f"- {name}: {parsed['rating_code']} "
                f"({parsed['rating_label']}) | limitations: {limitations}"
            )
        return

    report = build_report(
        config=config,
        establishment_method=args.establishment_method,
        soil_series=args.soil_series,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== ANI Pilot Stage 7 ===")
    print(f"Site-context status: {report['site_context_status']}")
    print()

    method = report["establishment_method"]
    soil = report["soil_context"]

    print(
        "Establishment method:",
        method["label"] if method["label"] else "MISSING",
    )
    print(
        "Soil series:",
        soil["soil_series"] if soil["soil_series"] else "MISSING",
    )

    if soil["soil_series"]:
        s = soil["rainfed_rice_suitability"]
        print(
            "Rainfed-rice suitability:",
            f"{s['rating_code']} ({s['rating_label']})",
        )
        if s["limitations"]:
            print("Limitation categories:", ", ".join(s["limitations"]))

    print()
    print(report["interpretation"])

    if report["runtime_blocks"]:
        print()
        print("Missing runtime inputs:")
        for item in report["runtime_blocks"]:
            print(f"- {item}")

    print()
    print("Effective rainfall ready:", report["effective_rainfall_ready"])
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
