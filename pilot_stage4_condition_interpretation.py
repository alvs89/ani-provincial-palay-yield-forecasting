from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Signal:
    factor: str
    status: str
    value: str
    interpretation: str
    basis: str


def relative_difference(a: float, b: float) -> float:
    denom = (abs(a) + abs(b)) / 2.0
    if denom == 0:
        return 0.0
    return abs(a - b) / denom * 100.0


def rainfall_agreement(open_meteo_mm: float, chirps_mm: float) -> tuple[str, float]:
    """
    This is a SOURCE-AGREEMENT diagnostic, not an agronomic threshold.
    Thresholds only describe how close the two forecast totals are.
    """
    diff = relative_difference(open_meteo_mm, chirps_mm)
    if diff <= 20:
        return "strong", diff
    if diff <= 40:
        return "moderate", diff
    return "weak", diff


def temperature_context(mean_temp_c: float) -> tuple[str, str]:
    """
    Broad physiological context based on IRRI/ORYZA cardinal temperatures.
    This is NOT a planting-date recommendation.
    Typical rice development parameters cited in ORYZA literature:
    base ~8 C, optimum ~30 C, maximum ~42 C.
    """
    if 24 <= mean_temp_c <= 32:
        return (
            "favorable_context",
            "Mean temperature is close to the broad optimum region used in rice crop-development literature."
        )
    if 18 <= mean_temp_c < 24 or 32 < mean_temp_c <= 36:
        return (
            "caution_context",
            "Mean temperature is usable for rice growth but is farther from the broad optimum region."
        )
    return (
        "stress_context",
        "Mean temperature is outside the broad range normally treated as near-optimal for rice development."
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    agreement, agreement_pct = rainfall_agreement(
        args.open_meteo_rainfall, args.chirps_rainfall
    )
    temp_status, temp_text = temperature_context(args.mean_temp)

    signals: list[Signal] = [
        Signal(
            factor="Rainfall forecast source agreement",
            status=agreement,
            value=(
                f"Open-Meteo {args.open_meteo_rainfall:.2f} mm vs "
                f"CHIRPS3-GEFS {args.chirps_rainfall:.2f} mm "
                f"({agreement_pct:.1f}% relative difference)"
            ),
            interpretation=(
                "The two independent rainfall totals are reasonably close."
                if agreement == "strong"
                else
                "The two rainfall products show some disagreement; treat the rainfall outlook with added caution."
                if agreement == "moderate"
                else
                "The rainfall products diverge materially; do not base a planting decision on one source alone."
            ),
            basis="ANI Stage 4 source-consistency rule; not an agronomic suitability threshold.",
        ),
        Signal(
            factor="Mean temperature",
            status=temp_status,
            value=f"{args.mean_temp:.2f} C",
            interpretation=temp_text,
            basis=(
                "Broad rice development context from IRRI/ORYZA literature "
                "(cardinal temperatures approximately 8 C base, 30 C optimum, 42 C maximum)."
            ),
        ),
        Signal(
            factor="Forecast rainfall",
            status="context_only",
            value=(
                f"{args.open_meteo_rainfall:.2f} mm Open-Meteo; "
                f"{args.chirps_rainfall:.2f} mm CHIRPS3-GEFS over the forecast window"
            ),
            interpretation=(
                "Rainfall is recorded as a planning signal, but ANI does not convert this total "
                "into a rainfed planting recommendation without effective-rainfall and crop-water-balance calibration."
            ),
            basis=(
                "FAO crop-water guidance requires crop stage, evapotranspiration, effective rainfall, "
                "and water-balance context rather than a rainfall-total-only rule."
            ),
        ),
        Signal(
            factor="Rainy days",
            status="context_only",
            value=f"{args.rainy_days} day(s)",
            interpretation=(
                "Rainfall frequency is retained for interpretation. No favorable/unfavorable threshold "
                "is applied until a local Nueva Ecija planting rule is validated."
            ),
            basis="No validated ANI rainfed planting threshold has been established yet.",
        ),
        Signal(
            factor="Surface soil moisture",
            status="requires_soil_calibration",
            value=f"{args.soil_moisture:.3f} m3/m3",
            interpretation=(
                "Volumetric soil moisture cannot be labeled adequate or inadequate without soil texture "
                "and locally relevant field-capacity / wilting-point information."
            ),
            basis="Soil-moisture thresholds are soil-specific; a universal cutoff would be misleading.",
        ),
        Signal(
            factor="Relative humidity",
            status="context_only",
            value=f"{args.mean_rh:.2f}%",
            interpretation=(
                "Humidity is preserved as environmental context. ANI does not infer disease risk from RH alone."
            ),
            basis="Disease-pressure assessment would require crop stage, duration/leaf wetness, pathogen context, and validation.",
        ),
        Signal(
            factor="Maximum wind gust",
            status="context_only",
            value=f"{args.max_gust:.1f} km/h",
            interpretation=(
                "Wind is retained as context. No lodging or damage threshold is applied without crop-stage and variety information."
            ),
            basis="Wind vulnerability is stage- and variety-dependent.",
        ),
    ]

    required_for_validated_recommendation = [
        "Locally validated rainfed planting decision thresholds for Nueva Ecija",
        "Crop establishment method and intended planting/transplanting stage",
        "Reference evapotranspiration (ETo) or a defensible water-balance estimate",
        "Effective rainfall rather than rainfall total alone",
        "Soil texture plus field capacity / wilting point or equivalent local soil-water calibration",
        "Validation of the rule against historical planting outcomes or expert agronomic review",
    ]

    # Evidence gate:
    # ANI may show planning context now, but it must not fabricate a "plant now" recommendation.
    recommendation_status = "WITHHELD_PENDING_VALIDATION"
    planning_signal = (
        "PROVISIONAL / CAUTION"
        if args.water.lower().startswith("rain")
        else "CONTEXT AVAILABLE"
    )

    summary = (
        f"For {args.province} ({args.ecosystem}, {args.water}), the {args.start_date} to "
        f"{args.end_date} outlook shows {args.open_meteo_rainfall:.1f} mm Open-Meteo rainfall, "
        f"{args.chirps_rainfall:.2f} mm CHIRPS3-GEFS rainfall, {args.rainy_days} rainy days, "
        f"{args.mean_temp:.2f} C mean temperature, {args.mean_rh:.2f}% mean RH, "
        f"{args.max_gust:.1f} km/h maximum gust, and {args.soil_moisture:.3f} m3/m3 "
        f"surface soil moisture. Rainfall-source agreement is {agreement} "
        f"({agreement_pct:.1f}% relative difference). Temperature is broadly compatible "
        f"with rice development, but the available variables are not sufficient to issue "
        f"a validated planting-date recommendation."
    )

    return {
        "stage": 4,
        "name": "ANI Public-Condition Interpretation and Evidence Gate",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Province/ecosystem-level environmental planning context. "
            "Does not alter the trained XGBoost yield prediction."
        ),
        "location": args.province,
        "ecosystem": args.ecosystem,
        "water_source": args.water,
        "forecast_window": {
            "start": args.start_date,
            "end": args.end_date,
        },
        "stage3_inputs": {
            "open_meteo_rainfall_mm": args.open_meteo_rainfall,
            "rainy_days": args.rainy_days,
            "mean_temperature_c": args.mean_temp,
            "mean_relative_humidity_pct": args.mean_rh,
            "max_wind_gust_kmh": args.max_gust,
            "soil_moisture_0_7cm_m3_m3": args.soil_moisture,
            "chirps3_gefs_rainfall_mm": args.chirps_rainfall,
            "chirps_issue": args.chirps_issue,
        },
        "planning_signal": planning_signal,
        "planting_recommendation_status": recommendation_status,
        "planting_recommendation": None,
        "summary": summary,
        "signals": [asdict(s) for s in signals],
        "required_before_validated_planting_recommendation": required_for_validated_recommendation,
        "integration_note": (
            "Keep this Stage 4 report separate from the XGBoost feature vector. "
            "The current ANI model was trained on lagged quarterly agricultural/weather features, "
            "not on these forward 10-day conditions."
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ANI Stage 4: interpret Stage 3 public conditions without overstating model capability."
    )
    p.add_argument("--province", default="Nueva Ecija")
    p.add_argument("--ecosystem", required=True)
    p.add_argument("--water", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--open-meteo-rainfall", type=float, required=True)
    p.add_argument("--rainy-days", type=int, required=True)
    p.add_argument("--mean-temp", type=float, required=True)
    p.add_argument("--mean-rh", type=float, required=True)
    p.add_argument("--max-gust", type=float, required=True)
    p.add_argument("--soil-moisture", type=float, required=True)
    p.add_argument("--chirps-rainfall", type=float, required=True)
    p.add_argument("--chirps-issue", required=True)
    p.add_argument(
        "--output",
        default="outputs/stage4_condition_interpretation.json",
        help="Output JSON path.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== ANI Pilot Stage 4 ===")
    print(
        f"{report['location']} {report['ecosystem']} | water: {report['water_source']} | "
        f"window: {report['forecast_window']['start']} to {report['forecast_window']['end']}"
    )
    print()
    print(report["summary"])
    print()
    print(f"Planning signal: {report['planning_signal']}")
    print(f"Planting recommendation: {report['planting_recommendation_status']}")
    print()
    print("Signals:")
    for signal in report["signals"]:
        print(f"- {signal['factor']}: {signal['status']} | {signal['value']}")
    print()
    print(f"Saved: {out}")
    print()
    print(
        "Next ANI step: calibrate/validate a planting rule before replacing "
        "WITHHELD_PENDING_VALIDATION with a planting recommendation."
    )


if __name__ == "__main__":
    main()
