#!/usr/bin/env python3
"""ANI Pilot Stage 9 — Consolidated environmental decision-support summary.

This stage does not introduce a new prediction model or agronomic threshold.
It consolidates the already-computed evidence from Stages 4, 5, 6, 7 and 8
into one machine-readable output that can later be exposed by the ANI backend
and frontend alongside the separate XGBoost yield forecast.

Guardrails:
- XGBoost yield forecasting remains separate.
- Stage 9 does not generate a planting recommendation.
- Test/unverified site context remains explicitly marked as test evidence.
- Kc scenarios remain scenarios unless locally validated.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"

DEFAULT_STAGE4 = OUTPUT_DIR / "stage4_condition_interpretation.json"
DEFAULT_STAGE5 = OUTPUT_DIR / "stage5_planting_readiness.json"
DEFAULT_STAGE6 = OUTPUT_DIR / "stage6_water_balance.json"
DEFAULT_STAGE7 = OUTPUT_DIR / "stage7_site_context.json"
DEFAULT_STAGE8 = OUTPUT_DIR / "stage8_fao_initial_kc_scenario.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "environmental_decision_support.json"


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def load_json(path: Path, required: bool = True) -> dict[str, Any] | None:
    path = resolve(path)
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_signal(stage4: dict[str, Any], factor: str) -> dict[str, Any] | None:
    for signal in stage4.get("signals", []):
        if signal.get("factor") == factor:
            return signal
    return None


def build_summary(
    stage4: dict[str, Any],
    stage5: dict[str, Any],
    stage6: dict[str, Any],
    stage7: dict[str, Any] | None,
    stage8: dict[str, Any],
) -> dict[str, Any]:
    wb = stage6.get("water_balance", {})
    bound = stage8.get("rainfall_bound", {})
    kc_scenario = stage8.get("crop_specific_scenario", {})
    site = stage8.get("site_context") or {}

    rainfall = wb.get("forecast_rainfall_mm")
    et0 = wb.get("reference_et0_fao56_mm")
    p_minus_et0 = wb.get("climatic_water_balance_p_minus_et0_mm")
    ratio = wb.get("rainfall_to_et0_ratio")

    kc = kc_scenario.get("kc")
    etc = kc_scenario.get("etc_mm")
    rainfall_minus_etc = kc_scenario.get("best_case_rainfall_minus_etc_mm")

    site_verification = site.get("verification")
    if not site_verification and stage7:
        site_verification = "unverified"

    rainfall_signal = get_signal(stage4, "Rainfall forecast source agreement")
    temperature_signal = get_signal(stage4, "Mean temperature")

    blockers = list(stage5.get("runtime_blocks", []))
    validation_blocks = list(stage5.get("validation_blocks", []))

    # Stage 7 can resolve these conceptually, but only if explicitly verified.
    if stage7 and site_verification == "verified":
        if stage7.get("establishment_method", {}).get("status") == "AVAILABLE":
            blockers = [x for x in blockers if x != "establishment_method"]
        if stage7.get("soil_context", {}).get("status") == "AVAILABLE":
            blockers = [x for x in blockers if x != "soil_series"]

    # Effective rainfall remains unavailable unless Stage 6 has a value.
    effective_rainfall = stage6.get("effective_rainfall", {})
    if effective_rainfall.get("effective_rainfall_mm") is not None:
        blockers = [x for x in blockers if x != "effective_rainfall_mm"]

    if (
        rainfall is not None
        and et0 is not None
        and float(rainfall) < float(et0)
    ):
        atmospheric_water_status = "DEFICIT_SIGNAL"
    else:
        atmospheric_water_status = "NO_DEFICIT_SIGNAL"

    crop_water_status = "NOT_EVALUATED"
    if kc is not None and rainfall_minus_etc is not None:
        crop_water_status = (
            "RAINFALL_ALONE_INSUFFICIENT_IN_SCENARIO"
            if float(rainfall_minus_etc) < 0
            else "RAINFALL_COULD_BE_SUFFICIENT_IN_SCENARIO"
        )

    overall_status = "FIELD_VALIDATION_REQUIRED"
    if atmospheric_water_status == "DEFICIT_SIGNAL":
        overall_status = "CAUTION_WATER_DEFICIT_SIGNAL"
    if crop_water_status == "RAINFALL_ALONE_INSUFFICIENT_IN_SCENARIO":
        overall_status = "CAUTION_RAINFALL_INSUFFICIENT_IN_REFERENCE_SCENARIO"

    conclusion_parts = []

    if rainfall is not None and et0 is not None:
        conclusion_parts.append(
            f"Forecast rainfall is {float(rainfall):.2f} mm versus "
            f"{float(et0):.2f} mm FAO-56 reference ET0."
        )

    if ratio is not None:
        conclusion_parts.append(
            f"Gross rainfall equals about {float(ratio) * 100:.1f}% of reference ET0."
        )

    if kc is not None and etc is not None and rainfall_minus_etc is not None:
        conclusion_parts.append(
            f"Under the provisional Kc={float(kc):.2f} reference scenario, "
            f"ETc is {float(etc):.2f} mm and the best-case gross-rainfall "
            f"minus ETc balance is {float(rainfall_minus_etc):.2f} mm."
        )

    conclusion_parts.append(
        "This supports a cautionary water-availability interpretation, not a "
        "planting recommendation, because effective rainfall, antecedent root-zone "
        "water storage, verified site context, and locally validated decision rules "
        "remain unresolved."
    )

    return {
        "stage": 9,
        "name": "ANI Consolidated Environmental Decision Support",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Environmental decision-support summary for the selected forecast window. "
            "This output is separate from the ANI XGBoost provincial yield forecast."
        ),
        "context": {
            "location": stage4.get("location"),
            "ecosystem": stage4.get("ecosystem"),
            "water_source": stage4.get("water_source"),
            "forecast_window": stage4.get("forecast_window"),
        },
        "environmental_conditions": {
            "rainfall_source_agreement": rainfall_signal,
            "temperature_context": temperature_signal,
            "mean_relative_humidity_pct": (
                stage4.get("stage3_inputs", {}).get("mean_relative_humidity_pct")
            ),
            "max_wind_gust_kmh": (
                stage4.get("stage3_inputs", {}).get("max_wind_gust_kmh")
            ),
            "surface_soil_moisture_m3_m3": (
                stage4.get("stage3_inputs", {}).get("soil_moisture_0_7cm_m3_m3")
            ),
        },
        "water_balance": {
            "forecast_rainfall_mm": rainfall,
            "reference_et0_fao56_mm": et0,
            "p_minus_et0_mm": p_minus_et0,
            "rainfall_to_et0_ratio": ratio,
            "atmospheric_water_status": atmospheric_water_status,
            "effective_rainfall_mm": effective_rainfall.get("effective_rainfall_mm"),
            "effective_rainfall_status": effective_rainfall.get("status"),
        },
        "rainfall_sufficiency_bound": {
            "effective_rainfall_upper_bound_mm": (
                bound.get("effective_rainfall_upper_bound_mm")
            ),
            "gross_rainfall_percent_of_et0": (
                bound.get("gross_rainfall_percent_of_et0")
            ),
            "break_even_kc_if_100pct_rainfall_effective": (
                stage8.get("crop_coefficient_threshold", {}).get(
                    "break_even_kc_if_100pct_rainfall_effective"
                )
            ),
            "bound_signal": bound.get("signal"),
        },
        "crop_water_reference_scenario": {
            "status": crop_water_status,
            "kc": kc,
            "estimated_etc_mm": etc,
            "best_case_rainfall_minus_etc_mm": rainfall_minus_etc,
            "scenario_label": (
                "FAO reference sensitivity scenario; not locally validated"
                if kc is not None
                else None
            ),
        },
        "site_context": {
            "verification": site_verification,
            "establishment_method": (
                stage7.get("establishment_method") if stage7 else None
            ),
            "soil_context": (
                stage7.get("soil_context") if stage7 else None
            ),
            "usable_as_field_evidence": site_verification == "verified",
        },
        "decision_support": {
            "overall_status": overall_status,
            "planting_recommendation_status": "WITHHELD",
            "planting_recommendation": None,
            "conclusion": " ".join(conclusion_parts),
            "remaining_runtime_blocks": blockers,
            "remaining_validation_blocks": validation_blocks,
        },
        "integration": {
            "xgboost_relationship": (
                "Separate. Do not add Stage 4-9 values to the trained XGBoost feature "
                "vector unless the model is retrained and revalidated with those predictors."
            ),
            "recommended_ui_role": (
                "Display as an Environmental Conditions / Decision Support panel beside "
                "the existing yield forecast result."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ANI Stage 9: consolidate environmental evidence into one JSON output."
    )
    p.add_argument("--stage4", type=Path, default=DEFAULT_STAGE4)
    p.add_argument("--stage5", type=Path, default=DEFAULT_STAGE5)
    p.add_argument("--stage6", type=Path, default=DEFAULT_STAGE6)
    p.add_argument("--stage7", type=Path, default=DEFAULT_STAGE7)
    p.add_argument("--stage8", type=Path, default=DEFAULT_STAGE8)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    stage4 = load_json(args.stage4)
    stage5 = load_json(args.stage5)
    stage6 = load_json(args.stage6)
    stage7 = load_json(args.stage7, required=False)
    stage8 = load_json(args.stage8)

    report = build_summary(
        stage4=stage4,
        stage5=stage5,
        stage6=stage6,
        stage7=stage7,
        stage8=stage8,
    )

    output_path = resolve(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    ds = report["decision_support"]
    wb = report["water_balance"]
    scenario = report["crop_water_reference_scenario"]

    print("=== ANI Pilot Stage 9 ===")
    print(
        f"{report['context']['location']} {report['context']['ecosystem']} | "
        f"window: {report['context']['forecast_window']['start']} to "
        f"{report['context']['forecast_window']['end']}"
    )
    print()
    print(f"Forecast rainfall: {wb['forecast_rainfall_mm']} mm")
    print(f"FAO-56 ET0: {wb['reference_et0_fao56_mm']} mm")
    print(f"P - ET0: {wb['p_minus_et0_mm']} mm")
    print(f"Rainfall / ET0: {wb['rainfall_to_et0_ratio']}")
    print(f"Atmospheric water status: {wb['atmospheric_water_status']}")

    if scenario["kc"] is not None:
        print()
        print(
            f"Reference Kc scenario: {scenario['kc']} | "
            f"ETc: {scenario['estimated_etc_mm']} mm"
        )
        print(
            "Best-case rainfall - ETc:",
            f"{scenario['best_case_rainfall_minus_etc_mm']} mm",
        )
        print(f"Scenario status: {scenario['status']}")

    print()
    print(f"Overall environmental status: {ds['overall_status']}")
    print(f"Planting recommendation: {ds['planting_recommendation_status']}")

    if ds["remaining_runtime_blocks"]:
        print()
        print("Remaining runtime blocks:")
        for item in ds["remaining_runtime_blocks"]:
            print(f"- {item}")

    print()
    print("Conclusion:")
    print(ds["conclusion"])
    print()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
