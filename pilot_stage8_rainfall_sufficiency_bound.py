#!/usr/bin/env python3
"""ANI Pilot Stage 8 — Rainfall sufficiency bound.

This stage derives a conservative, assumption-light bound from Stage 6:

    0 <= effective rainfall <= total rainfall

Therefore, even before estimating runoff or deep percolation, gross rainfall
provides an absolute upper bound on effective rainfall.

For crop-specific demand:
    ETc = Kc * ET0

The break-even Kc under the physically impossible best case that 100% of
rainfall is effective is:

    Kc_break_even = total_rainfall / ET0

If the actual crop-stage Kc is greater than this value, forecast rainfall alone
cannot meet ETc over the window. Soil-water storage, irrigation, groundwater,
or other water sources would be needed to close the gap.

Guardrails:
- P/ET0 is not a planting recommendation.
- This stage does not estimate antecedent soil-water storage.
- This stage does not assume all rainfall is effective.
- Monthly empirical effective-rainfall formulae are intentionally not applied
  to a 10-day forecast window.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"

DEFAULT_STAGE6 = OUTPUT_DIR / "stage6_water_balance.json"
DEFAULT_STAGE7 = OUTPUT_DIR / "stage7_site_context.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "stage8_rainfall_sufficiency_bound.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def build_report(
    stage6: dict[str, Any],
    stage7: dict[str, Any] | None,
    site_verification: str,
    kc: float | None,
) -> dict[str, Any]:
    wb = stage6.get("water_balance") or {}

    p = wb.get("forecast_rainfall_mm")
    et0 = wb.get("reference_et0_fao56_mm")

    if p is None or et0 is None:
        raise ValueError(
            "Stage 6 report is missing forecast_rainfall_mm or reference_et0_fao56_mm."
        )

    p = float(p)
    et0 = float(et0)

    if et0 <= 0:
        raise ValueError("Stage 6 ET0 must be greater than zero.")

    if p < 0:
        raise ValueError("Stage 6 rainfall cannot be negative.")

    gross_rainfall_fraction_of_et0 = p / et0
    break_even_kc = gross_rainfall_fraction_of_et0

    reference_gap_best_case = p - et0

    site = None
    if stage7:
        site = {
            "site_context_status": stage7.get("site_context_status"),
            "establishment_method": stage7.get("establishment_method"),
            "soil_context": stage7.get("soil_context"),
            "verification": site_verification,
            "verification_note": (
                "User has explicitly marked the Stage 7 site inputs as field-verified."
                if site_verification == "verified"
                else (
                    "Stage 7 site inputs are treated as test/unverified values. "
                    "Do not use them as field evidence."
                )
            ),
        }

    crop_specific = {
        "kc": kc,
        "etc_mm": None,
        "best_case_rainfall_minus_etc_mm": None,
        "rainfall_alone_covers_etc_under_100pct_effective_assumption": None,
        "status": "NOT_EVALUATED_NO_KC",
    }

    if kc is not None:
        if kc <= 0:
            raise ValueError("--kc must be greater than 0.")

        etc = et0 * kc
        best_case_gap = p - etc

        crop_specific = {
            "kc": round(kc, 4),
            "etc_mm": round(etc, 3),
            "best_case_rainfall_minus_etc_mm": round(best_case_gap, 3),
            "rainfall_alone_covers_etc_under_100pct_effective_assumption": (
                best_case_gap >= 0
            ),
            "status": (
                "RAINFALL_COULD_COVER_ETC_ONLY_UNDER_100PCT_EFFECTIVE_UPPER_BOUND"
                if best_case_gap >= 0
                else "RAINFALL_ALONE_CANNOT_COVER_ETC_EVEN_AT_100PCT_EFFECTIVE"
            ),
        }

    if p == 0:
        bound_signal = "NO_FORECAST_RAINFALL"
    elif gross_rainfall_fraction_of_et0 < 0.5:
        bound_signal = "GROSS_RAINFALL_FAR_BELOW_REFERENCE_ET0"
    elif gross_rainfall_fraction_of_et0 < 1.0:
        bound_signal = "GROSS_RAINFALL_BELOW_REFERENCE_ET0"
    else:
        bound_signal = "GROSS_RAINFALL_MEETS_OR_EXCEEDS_REFERENCE_ET0"

    return {
        "stage": 8,
        "name": "ANI Rainfall Sufficiency Bound",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_window": stage6.get("forecast_window"),
        "location": stage6.get("location"),
        "ecosystem": stage6.get("ecosystem"),
        "water_source": stage6.get("water_source"),
        "reference_water_demand": {
            "et0_fao56_mm": round(et0, 3),
            "meaning": (
                "Reference atmospheric evapotranspiration demand, not crop-specific ETc."
            ),
        },
        "rainfall_bound": {
            "gross_forecast_rainfall_mm": round(p, 3),
            "effective_rainfall_lower_bound_mm": 0.0,
            "effective_rainfall_upper_bound_mm": round(p, 3),
            "upper_bound_reason": (
                "Effective rainfall cannot physically exceed gross rainfall."
            ),
            "gross_rainfall_fraction_of_et0": round(
                gross_rainfall_fraction_of_et0, 4
            ),
            "gross_rainfall_percent_of_et0": round(
                gross_rainfall_fraction_of_et0 * 100.0, 1
            ),
            "best_case_p_minus_et0_mm": round(reference_gap_best_case, 3),
            "signal": bound_signal,
        },
        "crop_coefficient_threshold": {
            "break_even_kc_if_100pct_rainfall_effective": round(break_even_kc, 4),
            "interpretation": (
                "For any crop-stage Kc above this threshold, forecast rainfall alone "
                "cannot meet ETc over the window even under the best-case assumption "
                "that every millimeter of forecast rainfall is effective."
            ),
        },
        "crop_specific_scenario": crop_specific,
        "site_context": site,
        "methodology_guardrails": [
            (
                "This is a physical upper-bound analysis, not an effective-rainfall estimate."
            ),
            (
                "Antecedent soil-water storage may supply part of crop demand and is not "
                "quantified here."
            ),
            (
                "Runoff and deep percolation would reduce effective rainfall below the "
                "gross-rainfall upper bound."
            ),
            (
                "FAO monthly empirical effective-rainfall formulae are not applied because "
                "the ANI decision window is 10 days, not a monthly climatological period."
            ),
            (
                "No planting recommendation is generated by Stage 8."
            ),
        ],
        "next_required_evidence": [
            (
                "Verify the actual field/municipality soil series rather than using a test value."
            ),
            (
                "Obtain or defensibly estimate antecedent root-zone soil-water storage."
            ),
            (
                "Select a crop-stage/establishment-method-specific Kc only from a documented "
                "agronomic source appropriate to the intended decision."
            ),
            (
                "Validate the final planting rule with local agronomic expertise or historical outcomes."
            ),
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ANI Stage 8: derive a conservative rainfall-vs-ET0 sufficiency bound "
            "without manufacturing effective rainfall."
        )
    )
    parser.add_argument(
        "--stage6",
        type=Path,
        default=DEFAULT_STAGE6,
        help="Stage 6 JSON.",
    )
    parser.add_argument(
        "--stage7",
        type=Path,
        default=DEFAULT_STAGE7,
        help="Stage 7 JSON. Optional if the file does not exist.",
    )
    parser.add_argument(
        "--site-verification",
        choices=["test", "verified"],
        default="test",
        help=(
            "Use 'verified' only if the establishment method and soil series are "
            "actually verified for the intended field/site."
        ),
    )
    parser.add_argument(
        "--kc",
        type=float,
        default=None,
        help=(
            "Optional crop coefficient scenario. Do not supply until a documented "
            "crop-stage-specific value has been selected."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    stage6_path = resolve_path(args.stage6)
    stage7_path = resolve_path(args.stage7)
    output_path = resolve_path(args.output)

    stage6 = load_json(stage6_path)
    stage7 = load_json(stage7_path) if stage7_path.exists() else None

    report = build_report(
        stage6=stage6,
        stage7=stage7,
        site_verification=args.site_verification,
        kc=args.kc,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    rb = report["rainfall_bound"]
    kc_threshold = report["crop_coefficient_threshold"]

    print("=== ANI Pilot Stage 8 ===")
    print(
        f"{report.get('location')} {report.get('ecosystem')} | "
        f"window: {report.get('forecast_window', {}).get('start')} to "
        f"{report.get('forecast_window', {}).get('end')}"
    )
    print()
    print(f"Gross forecast rainfall: {rb['gross_forecast_rainfall_mm']} mm")
    print(f"FAO-56 ET0: {report['reference_water_demand']['et0_fao56_mm']} mm")
    print(
        "Gross rainfall / ET0:",
        f"{rb['gross_rainfall_fraction_of_et0']:.3f} "
        f"({rb['gross_rainfall_percent_of_et0']:.1f}%)",
    )
    print(
        "Best-case gross rainfall - ET0:",
        f"{rb['best_case_p_minus_et0_mm']} mm",
    )
    print(f"Bound signal: {rb['signal']}")
    print()
    print(
        "Break-even Kc if 100% of rainfall were effective:",
        kc_threshold["break_even_kc_if_100pct_rainfall_effective"],
    )
    print(
        "Meaning: any crop-stage Kc above this value cannot be met by forecast "
        "rainfall alone over the window."
    )

    if report["site_context"]:
        print()
        print(
            "Stage 7 site verification:",
            report["site_context"]["verification"].upper(),
        )

    if args.kc is not None:
        scenario = report["crop_specific_scenario"]
        print()
        print(f"Kc scenario: {scenario['kc']}")
        print(f"ETc scenario: {scenario['etc_mm']} mm")
        print(
            "Best-case rainfall - ETc:",
            f"{scenario['best_case_rainfall_minus_etc_mm']} mm",
        )
        print(f"Scenario status: {scenario['status']}")

    print()
    print("NO planting recommendation generated.")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
