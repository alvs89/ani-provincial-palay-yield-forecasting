from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import sklearn
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
RESEARCH_DATA_PATH = (
    ROOT / "data" / "processed" / "forecast_ready_research_2001_2025.csv"
)
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "ani_xgboost_pipeline.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"

MODEL_VERSION = "ANI-XGB-2026Q1-centroid-weather"
DEPLOYMENT_TRAIN_THROUGH_YEAR = 2026
DEPLOYMENT_TRAIN_THROUGH_QUARTER = 1

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
        "evaluation_training_through_year": 2024,
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


def deployment_training_rows(df: pd.DataFrame) -> pd.DataFrame:
    through_cutoff = (
        (df["Target_Year"] < DEPLOYMENT_TRAIN_THROUGH_YEAR)
        | (
            (df["Target_Year"] == DEPLOYMENT_TRAIN_THROUGH_YEAR)
            & (df["Target_Quarter"] <= DEPLOYMENT_TRAIN_THROUGH_QUARTER)
        )
    )
    return df[through_cutoff].copy()


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    deployment_df = pd.read_csv(DATA_PATH)
    research_df = pd.read_csv(RESEARCH_DATA_PATH)

    if int(research_df["Target_Year"].max()) != 2025:
        raise RuntimeError(
            "The fixed research/evaluation dataset must end in 2025."
        )

    metrics = evaluate_holdout(research_df)
    train_df = deployment_training_rows(deployment_df)

    if train_df.empty:
        raise RuntimeError("No deployment training rows are available.")
    latest_train = train_df.sort_values(
        ["Target_Year", "Target_Quarter"]
    ).iloc[-1]
    if (
        int(latest_train["Target_Year"]) != DEPLOYMENT_TRAIN_THROUGH_YEAR
        or int(latest_train["Target_Quarter"])
        != DEPLOYMENT_TRAIN_THROUGH_QUARTER
    ):
        raise RuntimeError(
            "Deployment training data do not reach the configured cutoff."
        )

    latest_integrated = deployment_df.sort_values(
        ["Target_Year", "Target_Quarter"]
    ).iloc[-1]

    final_pipeline = build_pipeline()
    final_pipeline.fit(train_df[MODEL_FEATURES], train_df[TARGET_COLUMN])
    joblib.dump(final_pipeline, MODEL_PATH)

    metadata = {
        "model_name": "ANI XGBoost Regression",
        "model_version": MODEL_VERSION,
        "scikit_learn_version": sklearn.__version__,
        "status": "active",
        "trained_through_year": DEPLOYMENT_TRAIN_THROUGH_YEAR,
        "trained_through_quarter": DEPLOYMENT_TRAIN_THROUGH_QUARTER,
        "training_rows": int(len(train_df)),
        "integrated_forecast_ready_rows": int(len(deployment_df)),
        "integrated_data_through_year": int(latest_integrated["Target_Year"]),
        "integrated_data_through_quarter": int(
            latest_integrated["Target_Quarter"]
        ),
        "weather_spatial_method": (
            "nearest NASA POWER grid point to province representative centroid"
        ),
        "important_note": (
            "Weather inputs are centroid-based provincial approximations and are not "
            "province-area-weighted averages. The integrated 2026 Q1-Q2 weather "
            "summaries use NASA POWER daily data aggregated to quarters."
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
    print(
        "Deployment training cutoff: "
        f"Q{DEPLOYMENT_TRAIN_THROUGH_QUARTER} "
        f"{DEPLOYMENT_TRAIN_THROUGH_YEAR} "
        f"({len(train_df)} rows)"
    )
    print(
        "Integrated forecast-ready coverage: "
        f"Q{int(latest_integrated['Target_Quarter'])} "
        f"{int(latest_integrated['Target_Year'])} "
        f"({len(deployment_df)} rows)"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
