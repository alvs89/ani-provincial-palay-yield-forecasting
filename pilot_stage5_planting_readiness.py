from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_VALIDATION_FIELDS = [
    "validation_status",
    "validated_for_location",
    "validated_for_ecosystem",
    "validated_for_establishment_method",
    "effective_rainfall_rule",
    "soil_water_rule",
    "temperature_rule",
    "wind_rule",
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _missing_or_unvalidated(config: dict[str, Any]) -> list[str]:
    missing: list[str] = []

    for key in REQUIRED_VALIDATION_FIELDS:
        if key not in config:
            missing.append(key)

    if config.get("validation_status") != "VALIDATED":
        missing.append("validation_status=VALIDATED")

    # A validated recommendation engine must have numeric, reviewed thresholds.
    for section, fields in {
        "effective_rainfall_rule": ["minimum_mm"],
        "soil_water_rule": ["minimum", "maximum", "unit"],
        "temperature_rule": ["minimum_c", "maximum_c"],
        "wind_rule": ["maximum_gust_kmh"],
    }.items():
        rule = config.get(section)
        if not isinstance(rule, dict):
            missing.append(section)
            continue
        for field in fields:
            if rule.get(field) is None:
                missing.append(f"{section}.{field}")

    return sorted(set(missing))


def build_readiness_report(
    stage4: dict[str, Any],
    config: dict[str, Any],
    establishment_method: str | None,
    soil_series: str | None,
    effective_rainfall_mm: float | None,
) -> dict[str, Any]:
    inputs = stage4.get("stage3_inputs", {})
    signals = stage4.get("signals", [])

    rainfall_signal = next(
        (s for s in signals if s.get("factor") == "Rainfall forecast source agreement"),
        {},
    )
    temp_signal = next(
        (s for s in signals if s.get("factor") == "Mean temperature"),
        {},
    )

    evidence: list[dict[str, str]] = []

    agreement_status = rainfall_signal.get("status", "unknown")
    evidence.append(
        {
            "item": "Rainfall source consistency",
            "status": "SUPPORTIVE" if agreement_status == "strong" else "CAUTION",
            "detail": rainfall_signal.get(
                "value", "No Stage 4 rainfall-agreement signal found."
            ),
        }
    )

    temp_status = temp_signal.get("status", "unknown")
    evidence.append(
        {
            "item": "Temperature context",
            "status": (
                "SUPPORTIVE"
                if temp_status == "favorable_context"
                else "CAUTION"
            ),
            "detail": temp_signal.get(
                "value", "No Stage 4 temperature signal found."
            ),
        }
    )

    evidence.append(
        {
            "item": "Establishment method",
            "status": "AVAILABLE" if establishment_method else "MISSING",
            "detail": establishment_method or (
                "Specify dry direct seeding, wet direct seeding, or transplanting; "
                "water requirements differ by establishment method."
            ),
        }
    )

    evidence.append(
        {
            "item": "Local soil context",
            "status": "AVAILABLE" if soil_series else "MISSING",
            "detail": soil_series or (
                "Province-level surface soil moisture alone cannot establish field water adequacy. "
                "Nueva Ecija contains soil series with different drainage and flooding limitations."
            ),
        }
    )

    evidence.append(
        {
            "item": "Effective rainfall",
            "status": "AVAILABLE" if effective_rainfall_mm is not None else "MISSING",
            "detail": (
                f"{effective_rainfall_mm:.2f} mm"
                if effective_rainfall_mm is not None
                else (
                    "Forecast rainfall total is available, but effective rainfall / crop-water "
                    "balance has not yet been calculated."
                )
            ),
        }
    )

    validation_blocks = _missing_or_unvalidated(config)

    runtime_blocks = []
    if not establishment_method:
        runtime_blocks.append("establishment_method")
    if not soil_series:
        runtime_blocks.append("soil_series")
    if effective_rainfall_mm is None:
        runtime_blocks.append("effective_rainfall_mm")

    can_issue = not validation_blocks and not runtime_blocks

    if not can_issue:
        decision = "FIELD_CHECK_AND_VALIDATION_REQUIRED"
        recommendation = None
        recommendation_status = "WITHHELD"
        rationale = (
            "ANI has useful forecast context, but an automated planting recommendation is "
            "withheld because the local agronomic rule has not been validated and/or required "
            "field-specific inputs are missing."
        )
    else:
        # This block is deliberately unreachable with the supplied UNVALIDATED config.
        # It becomes active only after the thesis team replaces the placeholder values with
        # expert-reviewed/local-validated thresholds and sets validation_status=VALIDATED.
        rain_min = float(config["effective_rainfall_rule"]["minimum_mm"])
        sm_min = float(config["soil_water_rule"]["minimum"])
        sm_max = float(config["soil_water_rule"]["maximum"])
        t_min = float(config["temperature_rule"]["minimum_c"])
        t_max = float(config["temperature_rule"]["maximum_c"])
        wind_max = float(config["wind_rule"]["maximum_gust_kmh"])

        soil_moisture = float(inputs["soil_moisture_0_7cm_m3_m3"])
        mean_temp = float(inputs["mean_temperature_c"])
        max_gust = float(inputs["max_wind_gust_kmh"])

        checks = {
            "effective_rainfall": float(effective_rainfall_mm) >= rain_min,
            "soil_moisture": sm_min <= soil_moisture <= sm_max,
            "temperature": t_min <= mean_temp <= t_max,
            "wind": max_gust <= wind_max,
        }

        if all(checks.values()):
            decision = "FAVORABLE_PLANTING_WINDOW"
            recommendation_status = "VALIDATED_RULE_OUTPUT"
            recommendation = (
                "Conditions meet all locally validated planting-window rules in the active ANI ruleset."
            )
        elif sum(checks.values()) >= 3:
            decision = "MARGINAL_PLANTING_WINDOW"
            recommendation_status = "VALIDATED_RULE_OUTPUT"
            recommendation = (
                "Most validated conditions are satisfied, but at least one rule requires caution."
            )
        else:
            decision = "UNFAVORABLE_PLANTING_WINDOW"
            recommendation_status = "VALIDATED_RULE_OUTPUT"
            recommendation = (
                "Multiple locally validated planting-window conditions are not satisfied."
            )

        rationale = f"Validated rule checks: {checks}"

    return {
        "stage": 5,
        "name": "ANI Planting Readiness Evidence Gate",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_stage4": {
            "location": stage4.get("location"),
            "ecosystem": stage4.get("ecosystem"),
            "water_source": stage4.get("water_source"),
            "forecast_window": stage4.get("forecast_window"),
        },
        "decision": decision,
        "recommendation_status": recommendation_status,
        "planting_recommendation": recommendation,
        "rationale": rationale,
        "evidence": evidence,
        "validation_blocks": validation_blocks,
        "runtime_blocks": runtime_blocks,
        "ruleset": {
            "name": config.get("ruleset_name"),
            "version": config.get("ruleset_version"),
            "validation_status": config.get("validation_status"),
        },
        "methodology_guardrail": (
            "Stage 5 is rule-based decision support and is separate from the XGBoost yield model. "
            "Do not claim that XGBoost generated the planting recommendation."
        ),
        "next_required_work": [
            "Choose and document the crop establishment method.",
            "Add municipality/field soil series or equivalent soil-water calibration.",
            "Calculate effective rainfall / crop-water balance rather than using total rainfall alone.",
            "Have candidate thresholds reviewed by an agronomist/AEW or validate them against historical field outcomes.",
            "Only then set the ruleset validation_status to VALIDATED.",
        ],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ANI Stage 5: evidence gate for a future validated planting-window recommendation."
    )
    p.add_argument(
        "--stage4",
        default="outputs/stage4_condition_interpretation.json",
        help="Stage 4 JSON file.",
    )
    p.add_argument(
        "--rules",
        default="config/planting_rules.json",
        help="Planting-rule configuration file.",
    )
    p.add_argument(
        "--establishment-method",
        choices=["dry-direct-seeding", "wet-direct-seeding", "transplanting"],
        default=None,
    )
    p.add_argument(
        "--soil-series",
        default=None,
        help="Local soil series or locally validated soil class.",
    )
    p.add_argument(
        "--effective-rainfall-mm",
        type=float,
        default=None,
        help="Effective rainfall for the decision window, if calculated.",
    )
    p.add_argument(
        "--output",
        default="outputs/stage5_planting_readiness.json",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    stage4 = load_json(Path(args.stage4))
    config = load_json(Path(args.rules))

    report = build_readiness_report(
        stage4=stage4,
        config=config,
        establishment_method=args.establishment_method,
        soil_series=args.soil_series,
        effective_rainfall_mm=args.effective_rainfall_mm,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== ANI Pilot Stage 5 ===")
    print(f"Decision: {report['decision']}")
    print(f"Recommendation status: {report['recommendation_status']}")
    print()

    print("Evidence:")
    for row in report["evidence"]:
        print(f"- {row['item']}: {row['status']} | {row['detail']}")

    print()
    if report["validation_blocks"]:
        print("Ruleset validation blocks:")
        for item in report["validation_blocks"]:
            print(f"- {item}")

    if report["runtime_blocks"]:
        print()
        print("Missing runtime inputs:")
        for item in report["runtime_blocks"]:
            print(f"- {item}")

    print()
    print(report["rationale"])
    print()
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
