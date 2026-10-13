# ANI: Provincial Palay Yield Forecasting System

ANI is a provincial palay yield forecasting system for the Philippines. It combines processed agricultural history, lagged agroclimatic information, an XGBoost regression model, a FastAPI service, and a browser-based user interface.

ANI reports model results according to the target quarter: **Prospective Forecast**, **Current-Quarter Estimate**, or **Retrospective Estimate**. A model-eligible result indicates that the required historical and lagged inputs are available; it does not indicate that the target quarter is in the future.

All model outputs are analytical estimates. They are not official PSA crop statistics and do not guarantee agricultural outcomes.

## System components

- Browser interface for estimates, historical records, model information, and Result History.
- FastAPI service for model metadata, historical records, estimate availability, and XGBoost inference.
- Processed agricultural and weather datasets in `data/processed/`.
- Bundled scikit-learn/XGBoost pipeline in `models/`.
- Separate Environmental Decision Support output. Its values are not inputs to the XGBoost yield model and do not replace a yield estimate.

## Data sources and coverage

The processed agricultural history is derived from PSA OpenSTAT records. Quarterly agroclimatic features are sourced from NASA POWER. ANI's integrated agricultural coverage is reported at runtime through `GET /meta`; this is the latest period integrated into ANI and is not a claim about the latest PSA data.

NASA POWER weather variables are represented using the nearest grid point to a representative provincial centroid. These are provincial-scale approximations and are not province-area-weighted averages. Weather and agricultural coverage can vary by province and quarter.

The processed datasets are:

- `palay_history.csv`: provincial quarterly production, harvested area, and yield records.
- `province_quarter_weather.csv`: quarterly weather summaries.
- `forecast_ready.csv`: model training and evaluation rows.

The XGBoost predictor set includes province, ecosystem, target quarter, prior yields and production/area values, and lagged rainfall, temperature, relative humidity, and wind speed. Target-quarter actual outcomes and complete target-quarter weather are not model inputs.

## Eligibility and result interpretation

The backend constructs the same required lagged features for availability checks and predictions. A target is eligible only when at least **40 prior quarterly observations**, at least **8 prior observations for the same quarter**, and all required input features are available. ANI does not impute absent agricultural quarters to satisfy these rules.

Temporal classification is independent of eligibility:

- A future target quarter is a **Prospective Forecast**.
- A target quarter currently in progress is a **Current-Quarter Estimate**.
- A completed target quarter is a **Retrospective Estimate** based on pre-target historical inputs.

The result view includes the same-quarter historical median, 25th–75th percentile range, and historical status. These describe context and do not explain causes or prescribe action.

## Model evaluation and artifact

The bundled model version is `ANI-XGB-v0.1-centroid-weather`. Evaluation uses training records through 2024 and eligible 2025 cases as a chronological holdout. The selected XGBoost pipeline is then refit on all forecast-ready records through 2025 for deployment. The evaluation comparison is the previous-year same-quarter yield baseline and XGBoost.

| Model | MAE (MT/ha) | RMSE (MT/ha) | R² |
| --- | ---: | ---: | ---: |
| Previous-year same-quarter baseline | 0.2576 | 0.3842 | 0.7821 |
| XGBoost pipeline | 0.2232 | 0.3077 | 0.8603 |

These metrics describe the supplied data and evaluation period. They do not establish performance for other periods, sources, or operating conditions.

The serialized model artifact was created with scikit-learn **1.7.2**. Install the pinned requirements to preserve compatibility. Model training changes the model and metadata, so it is not part of application setup.

## Environmental Decision Support

Environmental Decision Support is a separate short-term contextual analysis and does not alter the XGBoost yield estimate. Its availability is matched to province and ecosystem and checked against the report's forecast window. Environmental summaries do not replace the model result or constitute a planting recommendation. Field-specific interpretation requires verified site context and locally validated agronomic decision thresholds.

## Installation and use

On Windows, run from the repository root:

```bat
setup_ani.bat
run_ani.bat
```

Setup creates `.venv` if needed, installs the pinned requirements, and runs the integration verification. It does not retrain the bundled model.

The normal launcher starts the API at `http://127.0.0.1:8000` and the browser interface at `http://localhost:8080`. Open the interface in a browser; do not open `index.html` directly. API documentation is available at `http://127.0.0.1:8000/docs` while the service is running.

For manual startup:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, serve the frontend:

```powershell
python -m http.server 8080 --bind 127.0.0.1
```

## Verification and retraining

Run the deterministic backend and model integration checks with:

```powershell
.venv\Scripts\python.exe verify_installation.py
```

An authorized developer can explicitly retrain the model with:

```powershell
python -m ml.train_model
```

This command rewrites the serialized model artifact and its metadata. Review model evaluation and artifact compatibility after retraining.

## Result History

Results saved in Result History are stored on the current device in browser storage. They are not synchronized to an account or server and are not shared between devices.

## Repository layout

```text
backend/                 FastAPI service
data/processed/          Processed agricultural and weather datasets
ml/                      Feature construction and model training
models/                  Serialized model and metadata
outputs/                 Environmental decision-support report
app.js                   Browser application logic
environmental.js         Environmental decision-support presentation
index.html               Application entry point
styles.css               Main application styles
sidebar.css, sidebar.js  Navigation styles and behavior
setup_ani.bat            Environment setup and verification
run_ani.bat              Local application launcher
verify_installation.py   Deterministic integration verification
```
