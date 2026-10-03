from __future__ import annotations

import json
from pathlib import Path

import joblib
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
)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "forecast_ready.csv"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "ani_xgboost_pipeline.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"

MODEL_VERSION = "ANI-XGB-v0.1-centroid-weather"

XGB_PARAMS = {
    "n_estimators": 500,
    "learning_rate": 0.03,
    "max_depth": 4,
    "min_child_weight": 3,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "reg_lambda": 3,
    "objective": "reg:squarederror",
    "random_state": 42,
    "tree_method": "hist",
    "n_jobs": 4,
}


def build_pipeline() -> Pipeline:
    preprocessing = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", "passthrough", NUMERIC_FEATURES),
        ]
    )

    model = XGBRegressor(**XGB_PARAMS)

    return Pipeline(
        steps=[
            ("preprocess", preprocessing),
            ("model", model),
        ]
    )


def add_eligibility_counts(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.sort_values(
        ["Province", "Ecosystem", "Target_Year", "Target_Quarter"]
    ).copy()
    ordered["Prior_Total"] = ordered.groupby(
        ["Province", "Ecosystem"]
    ).cumcount()
    ordered["Prior_Same_Quarter"] = ordered.groupby(
        ["Province", "Ecosystem", "Target_Quarter"]
    ).cumcount()
    return ordered


def evaluate_holdout(df: pd.DataFrame) -> dict:
    train = df[df["Target_Year"] <= 2024].copy()
    counted = add_eligibility_counts(df)
    test = counted[
        (counted["Target_Year"] == 2025)
        & (counted["Prior_Total"] >= 40)
        & (counted["Prior_Same_Quarter"] >= 8)
    ].copy()

    pipeline = build_pipeline()
    pipeline.fit(train[MODEL_FEATURES], train[TARGET_COLUMN])

    y_true = test[TARGET_COLUMN]
    y_pred = pipeline.predict(test[MODEL_FEATURES])
    baseline = test["Yield_Lag4_mt_per_ha"]

    baseline_mae = mean_absolute_error(y_true, baseline)
    model_mae = mean_absolute_error(y_true, y_pred)

    return {
        "evaluation_period": "2025 holdout",
        "eligible_rows": int(len(test)),
        "baseline": {
            "name": "Previous-year same-quarter yield",
            "mae": float(baseline_mae),
            "rmse": float(mean_squared_error(y_true, baseline) ** 0.5),
            "r2": float(r2_score(y_true, baseline)),
        },
        "xgboost": {
            "mae": float(model_mae),
            "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
            "r2": float(r2_score(y_true, y_pred)),
        },
        "mae_improvement_pct": float(
            (baseline_mae - model_mae) / baseline_mae * 100
        ),
    }


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    metrics = evaluate_holdout(df)

    # Deployment model:
    # After evaluation is fixed, fit the selected pipeline on all available
    # forecast-ready records through 2025 so it can be used for later periods
    # whose required lagged inputs become available.
    final_pipeline = build_pipeline()
    final_pipeline.fit(df[MODEL_FEATURES], df[TARGET_COLUMN])
    joblib.dump(final_pipeline, MODEL_PATH)

    metadata = {
        "model_name": "ANI XGBoost Regression",
        "model_version": MODEL_VERSION,
        "status": "integration prototype",
        "trained_through_year": int(df["Target_Year"].max()),
        "training_rows": int(len(df)),
        "weather_spatial_method": (
            "nearest NASA POWER grid point to province representative centroid "
            "(preliminary integration dataset)"
        ),
        "important_note": (
            "Preferred final study method remains province-area weather aggregation "
            "if verified boundaries and implementation are completed."
        ),
        "features": MODEL_FEATURES,
        "target": TARGET_COLUMN,
        "eligibility_rule": {
            "minimum_prior_quarters": 40,
            "minimum_same_quarter_observations": 8,
            "all_required_features": True,
        },
        "xgboost_parameters": XGB_PARAMS,
        "evaluation": metrics,
    }

    METADATA_PATH.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved metadata: {METADATA_PATH}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
