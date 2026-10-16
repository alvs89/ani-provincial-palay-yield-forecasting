# ANI: Provincial Palay Yield Forecasting System

ANI is a provincial palay yield forecasting system for the Philippines. It combines processed agricultural history, lagged agroclimatic information, an XGBoost regression model, a FastAPI service, and a browser-based user interface.

ANI reports model results according to the target quarter: **Prospective Forecast**, **Current-Quarter Estimate**, or **Retrospective Estimate**. Model eligibility and temporal classification are separate. A target is offered only when the required historical and lagged inputs exist; its result type depends on whether the target quarter is future, in progress, or completed.

All model outputs are analytical estimates. They are not official PSA crop statistics and do not guarantee agricultural outcomes.

## System components

- Browser interface for estimates, historical records, model information, and Result History.
- FastAPI service for model metadata, historical records, estimate availability, and XGBoost inference.
- Processed agricultural and weather datasets in `data/processed/`.
- Bundled scikit-learn/XGBoost pipeline in `models/`.
- Separate Environmental Decision Support output. Its values are not inputs to the XGBoost yield model and do not replace a yield estimate.

## Data sources and integrated coverage

Agricultural history is derived from PSA OpenSTAT provincial palay records. The 2026 integrated records use the official production table **2E4EVCP0** and area-harvested table **2E4EAHC0**. Yield is calculated as production divided by harvested area for usable records.

ANI's integrated agricultural history currently extends through **Q2 2026**. In the current PSA source release, Q1 2026 observations are published and Q2 2026 observations are marked **Preliminary**. Preliminary source values remain identifiable in the processed data and may be revised in a later PSA release.

Quarterly agroclimatic features are sourced from NASA POWER. Weather variables are represented using the nearest source grid point to a representative provincial centroid. The 2026 Q1-Q2 weather records use NASA POWER daily values aggregated to quarterly summaries. These values are provincial-scale approximations and are not province-area-weighted averages.

The principal processed datasets are:

- `palay_history.csv`: provincial quarterly production, harvested area, calculated yield, region context, ecosystem, and available source-status fields.
- `province_quarter_weather.csv`: quarterly rainfall, temperature, relative humidity, and wind-speed summaries.
- `forecast_ready.csv`: integrated model-ready rows through Q2 2026.
- `forecast_ready_research_2001_2025.csv`: fixed research/evaluation dataset retained through 2025.
- `psa_2026_q1_q2_source_records.csv`: source-traceable Q1-Q2 2026 agricultural records.
- `province_centroids_psgc.csv`: representative provincial coordinates used for the weather extraction method.
- `data_provenance.json`: source matrices, coverage, data-status, modeling-scope, weather-method, and evaluation/deployment provenance.

ANI's modeling unit is the province. Selected-city OpenSTAT series are outside that unit, and PSA notes that BARMM aggregate totals can include Eight Cluster Areas that are not separately assignable to a province. Accordingly, sums of ANI province-level rows are not intended to reproduce PSA national or regional aggregate totals exactly.

ANI reports the integrated data cutoff at runtime through `GET /meta`. This describes the data currently integrated into ANI and is not a general claim that no newer source release exists.

## Predictor set

The deployed XGBoost pipeline uses:

- Province
- Ecosystem
- Target quarter
- Yield Lag 1
- Yield Lag 4
- Rolling four-quarter mean yield
- Area Harvested Lag 4
- Production Lag 4
- Rainfall Lag 1 and Lag 4
- Mean Temperature Lag 1 and Lag 4
- Relative Humidity Lag 1 and Lag 4
- Wind Speed Lag 1 and Lag 4

Target-quarter actual yield, production, harvested area, and complete target-quarter weather are not model inputs.

## Eligibility and result interpretation

The backend uses the same feature builder for availability checks and prediction. A target is eligible only when:

- at least **40 prior quarterly agricultural observations** are available;
- at least **8 prior observations for the same quarter** are available; and
- every required lagged agricultural and weather input is present.

ANI does not fabricate, recursively predict, or interpolate missing agricultural quarters to satisfy eligibility.

Temporal classification is independent of eligibility:

- A future target quarter is a **Prospective Forecast**.
- A target quarter currently in progress is a **Current-Quarter Estimate**.
- A completed target quarter is a **Retrospective Estimate** based on pre-target inputs.

With integrated agricultural and weather records through Q2 2026, Q3 2026 can be model-eligible for province-ecosystem combinations that satisfy the history rules. Q4 2026 remains unavailable until the required Q3 agricultural Lag 1 observation exists.

If an estimate uses a preliminary immediately preceding agricultural quarter, the result interface identifies that input-data status.

## Model evaluation and deployment fitting

ANI separates model evaluation from final deployment fitting.

For model evaluation:

1. Training records are limited to data through **2024**.
2. Eligible **2025** cases form the final chronological holdout.
3. XGBoost is compared with a seasonal naive baseline using the previous-year same-quarter yield.

The fixed 2025 holdout contains **511 eligible cases**.

| Model | MAE (MT/ha) | RMSE (MT/ha) | R² |
| --- | ---: | ---: | ---: |
| Previous-year same-quarter baseline | 0.2576 | 0.3842 | 0.7821 |
| XGBoost pipeline | 0.2232 | 0.3077 | 0.8603 |

XGBoost reduces MAE by approximately **13.35%** relative to the seasonal naive baseline on this fixed holdout.

After the evaluation is fixed, the selected XGBoost pipeline is refit for deployment using eligible model-ready observations through **Q1 2026**. Q2 2026 remains integrated as preliminary operational history and can support lagged inference without being included in model fitting.

The bundled model version is `ANI-XGB-2026Q1-centroid-weather`.

The serialized model artifact is created with scikit-learn **1.7.2**. Install the pinned requirements to preserve model compatibility.

## Historical and administrative context

Historical records retain their associated regional context. For current province selection and display, ANI uses the latest integrated context together with current PSA administrative notes. This allows the interface to reflect the Negros Island Region for Negros Occidental, Negros Oriental, and Siquijor, and the 2026 realignment of Sulu to Region IX, while preserving historical observations.

## Environmental Decision Support

Environmental Decision Support is a separate short-term contextual analysis and does not alter the XGBoost yield estimate. Its availability is matched to province and ecosystem and checked against the stored report's forecast window.

Environmental summaries do not replace the model result or constitute a planting recommendation. Field-specific interpretation requires verified site context and locally validated agronomic decision thresholds.

## Installation and use

On Windows, run from the repository root:

```bat
setup_ani.bat
run_ani.bat
```

Setup creates `.venv` if needed, installs the pinned requirements, and runs integration verification. It does not retrain the bundled model.

The launcher starts:

- API: `http://127.0.0.1:8000`
- Interface: `http://localhost:8080`
- API documentation while running: `http://127.0.0.1:8000/docs`

Open ANI through the served interface rather than opening `index.html` directly.

For manual startup:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
python -m http.server 8080 --bind 127.0.0.1
```

## Verification and controlled retraining

Run the deterministic integration checks with:

```powershell
.venv\Scripts\python.exe verify_installation.py
```

The verification suite checks the data cutoffs, fixed 2025 evaluation metrics, deployment training cutoff, Q3/Q4 eligibility behavior, province normalization, current region mapping, temporal classification, and environmental freshness rules.

An authorized developer can explicitly rebuild the deployment artifact with:

```powershell
python -m ml.train_model
```

The training script evaluates only the fixed research/evaluation file through 2025 and fits the deployment artifact only through the configured deployment cutoff. Retraining rewrites the serialized model artifact and metadata and should be followed by `verify_installation.py`.

## Result History

Results saved in Result History are stored on the current device in browser storage. They are not synchronized to an account or server and are not shared between devices.

## Repository layout

```text
backend/                 FastAPI service
data/processed/          Integrated agricultural, weather, provenance, and model-ready datasets
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
