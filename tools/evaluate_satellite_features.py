from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from ml.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    previous_period,
)
from ml.train_model import XGB_PARAMS, add_eligibility_counts

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_PATH = (
    ROOT / "data" / "processed" / "forecast_ready_research_2001_2025.csv"
)
DEFAULT_SATELLITE_PATH = (
    ROOT / "data" / "processed" / "province_quarter_satellite.csv"
)

SATELLITE_FEATURES = [
    "Cropland_NDVI_Lag1",
    "Cropland_EVI_Lag1",
    "Cropland_NDVI_Lag4",
    "Cropland_EVI_Lag4",
]
MIN_HOLDOUT_COMPLETE_CASE_COVERAGE_PCT = 90.0

# Feature selection is performed only on the 2024 development-validation year.
# The 2025 chronological holdout is not inspected until one candidate is fixed.
CANDIDATE_FEATURE_SETS = {
    "ndvi_lag1_lag4": [
        "Cropland_NDVI_Lag1",
        "Cropland_NDVI_Lag4",
    ],
    "evi_lag1_lag4": [
        "Cropland_EVI_Lag1",
        "Cropland_EVI_Lag4",
    ],
    "ndvi_evi_lag1": [
        "Cropland_NDVI_Lag1",
        "Cropland_EVI_Lag1",
    ],
    "ndvi_evi_lag1_lag4": SATELLITE_FEATURES,
}


def add_satellite_lags(
    frame: pd.DataFrame,
    satellite: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    lookup = {
        (row.Province, int(row.Year), int(row.Quarter)): (
            float(row.Cropland_NDVI_Mean),
            float(row.Cropland_EVI_Mean),
        )
        for row in satellite.itertuples(index=False)
        # ANI historical records before the 2024 Maguindanao split represent
        # the former undivided province. Current DENR Norte/Sur boundaries do
        # not spatially match those older records, so satellite values are
        # intentionally withheld instead of assigning a mismatched polygon.
        if not (
            row.Province == "Maguindanao del Sur"
            and int(row.Year) < 2024
        )
    }

    satellite_values = {feature: [] for feature in SATELLITE_FEATURES}

    for row in result.itertuples(index=False):
        target_year = int(row.Target_Year)
        target_quarter = int(row.Target_Quarter)
        lag1 = previous_period(target_year, target_quarter, 1)
        lag4 = previous_period(target_year, target_quarter, 4)

        lag1_values = lookup.get((row.Province, *lag1))
        lag4_values = lookup.get((row.Province, *lag4))

        satellite_values["Cropland_NDVI_Lag1"].append(
            lag1_values[0] if lag1_values else np.nan
        )
        satellite_values["Cropland_EVI_Lag1"].append(
            lag1_values[1] if lag1_values else np.nan
        )
        satellite_values["Cropland_NDVI_Lag4"].append(
            lag4_values[0] if lag4_values else np.nan
        )
        satellite_values["Cropland_EVI_Lag4"].append(
            lag4_values[1] if lag4_values else np.nan
        )

    for feature, values in satellite_values.items():
        result[feature] = values

    return result


def build_pipeline(extra_numeric: Iterable[str] = ()) -> Pipeline:
    numeric = NUMERIC_FEATURES + list(extra_numeric)
    preprocessing = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=True,
                ),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", "passthrough", numeric),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessing),
            ("model", XGBRegressor(**XGB_PARAMS)),
        ]
    )


def metric_dict(
    y_true: pd.Series,
    prediction: np.ndarray,
) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, prediction)),
        "rmse": float(mean_squared_error(y_true, prediction) ** 0.5),
        "r2": float(r2_score(y_true, prediction)),
    }


def eligible_year(
    counted: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    return counted[
        (counted["Target_Year"] == year)
        & (counted["Prior_Total"] >= 40)
        & (counted["Prior_Same_Quarter"] >= 8)
    ].copy()


def fit_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    extra_features: list[str],
) -> tuple[np.ndarray, Pipeline]:
    features = MODEL_FEATURES + extra_features
    model = build_pipeline(extra_features)
    model.fit(train[features], train[TARGET_COLUMN])
    return model.predict(test[features]), model


def complete_case_metrics(
    test: pd.DataFrame,
    prediction: np.ndarray,
    features: list[str],
) -> dict:
    complete = test[features].notna().all(axis=1).to_numpy()
    if not complete.any():
        return {
            "rows": 0,
            "coverage_pct": 0.0,
            "metrics": None,
        }
    return {
        "rows": int(complete.sum()),
        "coverage_pct": float(complete.mean() * 100),
        "metrics": metric_dict(
            test.loc[complete, TARGET_COLUMN],
            prediction[complete],
        ),
    }


def paired_results(
    test: pd.DataFrame,
    baseline_prediction: np.ndarray,
    satellite_prediction: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    paired = test[
        [
            "Province",
            "Ecosystem",
            "Target_Year",
            "Target_Quarter",
            TARGET_COLUMN,
        ]
    ].copy()
    paired["baseline_prediction"] = baseline_prediction
    paired["satellite_prediction"] = satellite_prediction
    paired["baseline_abs_error"] = (
        paired[TARGET_COLUMN] - paired["baseline_prediction"]
    ).abs()
    paired["satellite_abs_error"] = (
        paired[TARGET_COLUMN] - paired["satellite_prediction"]
    ).abs()

    province = (
        paired.groupby("Province", as_index=False)
        .agg(
            cases=(TARGET_COLUMN, "size"),
            baseline_mae=("baseline_abs_error", "mean"),
            satellite_mae=("satellite_abs_error", "mean"),
        )
    )
    province["satellite_better"] = (
        province["satellite_mae"] < province["baseline_mae"]
    )
    return paired, province


def evaluate(
    research: pd.DataFrame,
    satellite: pd.DataFrame,
) -> dict:
    augmented = add_satellite_lags(research, satellite)
    counted = add_eligibility_counts(augmented)

    development_train = augmented[augmented["Target_Year"] <= 2023].copy()
    validation_2024 = eligible_year(counted, 2024)

    baseline_validation_prediction, _ = fit_predict(
        development_train,
        validation_2024,
        [],
    )
    baseline_validation = metric_dict(
        validation_2024[TARGET_COLUMN],
        baseline_validation_prediction,
    )

    candidates: dict[str, dict] = {}
    for name, satellite_features in CANDIDATE_FEATURE_SETS.items():
        prediction, _ = fit_predict(
            development_train,
            validation_2024,
            satellite_features,
        )
        candidate_metrics = metric_dict(
            validation_2024[TARGET_COLUMN],
            prediction,
        )
        candidates[name] = {
            "features": satellite_features,
            "metrics": candidate_metrics,
            "mae_change_vs_current": (
                candidate_metrics["mae"] - baseline_validation["mae"]
            ),
            "complete_case": complete_case_metrics(
                validation_2024,
                prediction,
                satellite_features,
            ),
        }

    ranked = sorted(
        candidates.items(),
        key=lambda item: (
            item[1]["metrics"]["mae"],
            item[1]["metrics"]["rmse"],
            -item[1]["metrics"]["r2"],
        ),
    )
    selected_name, selected = ranked[0]

    selection_improves_validation = (
        selected["metrics"]["mae"] < baseline_validation["mae"]
    )

    final_train = augmented[augmented["Target_Year"] <= 2024].copy()
    holdout_2025 = eligible_year(counted, 2025)

    baseline_holdout_prediction, _ = fit_predict(
        final_train,
        holdout_2025,
        [],
    )
    satellite_holdout_prediction, _ = fit_predict(
        final_train,
        holdout_2025,
        selected["features"],
    )

    baseline_holdout = metric_dict(
        holdout_2025[TARGET_COLUMN],
        baseline_holdout_prediction,
    )
    satellite_holdout = metric_dict(
        holdout_2025[TARGET_COLUMN],
        satellite_holdout_prediction,
    )

    paired, province = paired_results(
        holdout_2025,
        baseline_holdout_prediction,
        satellite_holdout_prediction,
    )

    selected_complete_case = complete_case_metrics(
        holdout_2025,
        satellite_holdout_prediction,
        selected["features"],
    )

    satellite_periods = satellite[
        ["Year", "Quarter"]
    ].drop_duplicates().copy()
    satellite_periods["period_key"] = (
        satellite_periods["Year"].astype(int) * 4
        + satellite_periods["Quarter"].astype(int)
        - 1
    )
    minimum_period_key = int(satellite_periods["period_key"].min())
    maximum_period_key = int(satellite_periods["period_key"].max())
    observed_period_keys = set(
        satellite_periods["period_key"].astype(int).tolist()
    )
    missing_periods = []
    for period_key in range(minimum_period_key, maximum_period_key + 1):
        if period_key in observed_period_keys:
            continue
        missing_periods.append(
            {
                "year": period_key // 4,
                "quarter": period_key % 4 + 1,
            }
        )

    promote = bool(
        selection_improves_validation
        and satellite_holdout["mae"] < baseline_holdout["mae"]
        and satellite_holdout["rmse"] <= baseline_holdout["rmse"]
        and satellite_holdout["r2"] >= baseline_holdout["r2"]
        and selected_complete_case["coverage_pct"]
        >= MIN_HOLDOUT_COMPLETE_CASE_COVERAGE_PCT
    )

    return {
        "satellite_dataset": {
            "source_product": "MODIS/Terra MOD13A1 Collection 6.1",
            "vegetation_indices": ["NDVI", "EVI"],
            "native_spatial_resolution_m": 500,
            "temporal_resolution": "16-day composite",
            "rows": int(len(satellite)),
            "provinces": int(satellite["Province"].nunique()),
            "coverage_start": {
                "year": minimum_period_key // 4,
                "quarter": minimum_period_key % 4 + 1,
            },
            "coverage_end": {
                "year": maximum_period_key // 4,
                "quarter": maximum_period_key % 4 + 1,
            },
            "missing_full_quarters_within_coverage": missing_periods,
            "spatial_alignment_note": (
                "Pre-2024 satellite values for Maguindanao del Sur are "
                "withheld during model evaluation because ANI's older "
                "agricultural records represent the former undivided "
                "Maguindanao province while the current DENR boundary is "
                "post-split."
            ),
        },
        "selection_protocol": {
            "development_training_through": 2023,
            "feature_selection_validation_year": 2024,
            "final_holdout_year": 2025,
            "primary_selection_metric": "MAE",
            "note": (
                "Satellite feature composition is selected on 2024 only. "
                "The 2025 chronological holdout is evaluated after selection."
            ),
        },
        "validation_2024": {
            "eligible_rows": int(len(validation_2024)),
            "current_feature_model": baseline_validation,
            "candidates": candidates,
            "selected_candidate": selected_name,
            "selected_features": selected["features"],
            "selected_candidate_improves_mae": selection_improves_validation,
        },
        "holdout_2025": {
            "eligible_rows": int(len(holdout_2025)),
            "current_feature_model": baseline_holdout,
            "satellite_augmented_model": satellite_holdout,
            "delta_satellite_minus_current": {
                "mae_change": (
                    satellite_holdout["mae"] - baseline_holdout["mae"]
                ),
                "mae_change_pct": (
                    (satellite_holdout["mae"] - baseline_holdout["mae"])
                    / baseline_holdout["mae"]
                    * 100
                ),
                "rmse_change": (
                    satellite_holdout["rmse"] - baseline_holdout["rmse"]
                ),
                "r2_change": (
                    satellite_holdout["r2"] - baseline_holdout["r2"]
                ),
            },
            "selected_feature_complete_case": selected_complete_case,
            "provinces_satellite_better": int(
                province["satellite_better"].sum()
            ),
            "provinces_compared": int(len(province)),
        },
        "selected_candidate": selected_name,
        "selected_features": selected["features"],
        "acceptance_rule": {
            "validation_mae_must_improve": True,
            "holdout_mae_must_improve": True,
            "holdout_rmse_must_not_worsen": True,
            "holdout_r2_must_not_worsen": True,
            "minimum_holdout_complete_case_coverage_pct": (
                MIN_HOLDOUT_COMPLETE_CASE_COVERAGE_PCT
            ),
        },
        "promote_to_deployment": promote,
        "deployment_decision": (
            "promote_satellite_features"
            if promote
            else "retain_current_deployed_feature_set"
        ),
        "paired_results": paired,
        "province_comparison": province,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Select satellite vegetation predictors using 2024 development "
            "validation, then evaluate the fixed candidate on the untouched "
            "2025 chronological holdout."
        )
    )
    parser.add_argument(
        "--satellite",
        type=Path,
        default=DEFAULT_SATELLITE_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs" / "satellite_evaluation",
    )
    args = parser.parse_args()

    research = pd.read_csv(RESEARCH_PATH)
    satellite = pd.read_csv(args.satellite)
    results = evaluate(research, satellite)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results["paired_results"].to_csv(
        args.output_dir / "paired_2025_predictions.csv",
        index=False,
    )
    results["province_comparison"].to_csv(
        args.output_dir / "province_comparison.csv",
        index=False,
    )

    summary = {
        key: value
        for key, value in results.items()
        if key not in {"paired_results", "province_comparison"}
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))

    if summary["promote_to_deployment"]:
        print(
            "RESULT: The satellite candidate passed development selection "
            "and improved all required 2025 holdout criteria."
        )
    else:
        print(
            "RESULT: Do not promote satellite predictors to the deployed "
            "yield model under the current acceptance rule."
        )


if __name__ == "__main__":
    main()
