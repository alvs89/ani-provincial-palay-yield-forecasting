# ANI: Provincial Palay Yield Forecasting System

ANI is an academic prototype for provincial palay yield forecasting in the Philippines. The repository combines a browser interface, processed agricultural and weather datasets, a reproducible XGBoost training workflow, and a FastAPI prediction service.

> **Research prototype:** Forecasts are analytical estimates, not official PSA crop statistics or guaranteed agricultural outcomes. The supplied weather features use a preliminary nearest NASA POWER grid point for each province representative centroid. This spatial method requires further validation before the model can be treated as a final research model.

## Features

- Forecast palay yield by province, ecosystem, year, and quarter.
- Build lagged agricultural and weather features and enforce input eligibility before prediction.
- Serve forecasts and historical records through FastAPI.
- Explore the processed historical data in the browser UI.
- Save forecast runs to browser history, with view and delete actions.
- Review XGBoost and seasonal baseline metrics from the bundled 2025 chronological holdout.
- Retrain the pipeline from the forecast-ready dataset.

## Architecture

```text
Browser UI (HTML, CSS, JavaScript)
        │ HTTP / JSON
        ▼
FastAPI service (backend/main.py)
        ├── Eligibility checks and lag feature construction (ml/features.py)
        ├── Processed agriculture and weather data (data/processed/)
        └── Trained scikit-learn / XGBoost pipeline (models/)
```

## Requirements

- Python 3.10 or later recommended.
- Dependencies pinned in `requirements.txt`.
- Windows users can run `setup_ani.bat` to create `.venv`, install dependencies, patch the frontend, and retrain the model. The setup script will overwrite the bundled model and metadata when it retrains.

Manual setup from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Start the API:

```powershell
uvicorn backend.main:app --reload
```

In a second terminal, serve the frontend:

```powershell
python -m http.server 8080
```

Open <http://localhost:8080>. API health is at <http://127.0.0.1:8000/health>, and interactive API documentation is at <http://127.0.0.1:8000/docs>.

For the one-click Windows launcher, use `run_ani.bat` after setup.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API and model version status |
| `GET` | `/meta` | Model metadata, geographic coverage, data cutoff, and suggested next target |
| `GET` | `/model-info` | Bundled model and evaluation metadata |
| `GET` | `/historical?province=...&ecosystem=...` | Historical records for one selection |
| `GET` | `/historical/all` | Records used by the frontend explorer |
| `POST` | `/predict` | Eligibility-checked yield estimate |

Example request:

```json
{
  "province": "Nueva Ecija",
  "ecosystem": "Irrigated",
  "target_year": 2026,
  "target_quarter": 1
}
```

The API returns an eligibility explanation without a prediction when required agricultural lags, weather lags, or minimum history are unavailable. The current data cutoff is 2025 Q4, so the next target period may be 2026 Q1 for eligible province and ecosystem combinations. Later 2026 quarters require the intervening actual records.

## Data and predictors

`data/processed/` contains three processed datasets:

- `forecast_ready.csv`: feature and target rows for chronological training and evaluation.
- `palay_history.csv`: provincial quarterly production, harvested area, and yield history.
- `province_quarter_weather.csv`: quarterly weather summaries.

The pipeline uses 16 predictors: province, ecosystem, target quarter; lagged yields and rolling yield; lagged area and production; and lagged rainfall, temperature, relative humidity, and wind speed. Target-quarter yield, production, harvested area, and complete target-quarter weather are excluded from predictors.

The bundle documentation describes the agricultural history as PSA-derived and the weather input as NASA POWER. Before academic publication or redistribution, add complete dataset citations, extraction dates, licenses, geographic processing details, and a data dictionary. The included weather mapping is preliminary centroid-nearest-grid extraction rather than province-area spatial aggregation.

## Model and evaluation

The bundled model is `ANI-XGB-v0.1-centroid-weather`, an integration prototype trained on the supplied forecast-ready records through 2025. Its documented chronological evaluation uses 511 eligible 2025 holdout cases:

| Model | MAE (t/ha) | RMSE (t/ha) | R² |
| --- | ---: | ---: | ---: |
| Previous-year same-quarter baseline | 0.2576 | 0.3842 | 0.7821 |
| XGBoost pipeline | 0.2232 | 0.3077 | 0.8603 |

These metrics describe the supplied evaluation run and dataset only. They do not establish performance on future periods, other data sources, or operational conditions. The weather spatial method and source data should be reviewed and the model re-evaluated before making final thesis claims.

To reproduce training and update the pipeline and metadata:

```powershell
python -m ml.train_model
```

## Forecast history

Forecast records are saved in the browser's `localStorage`; they are not stored by FastAPI or shared between users. The prediction itself uses the local API and bundled model, while the history remains browser-local.

## Repository structure

```text
backend/                 FastAPI service
data/processed/          Processed agricultural and weather datasets
ml/                      Feature construction and model training
models/                  Model pipeline and metadata
tools/                   Frontend integration utility
app.js                   Browser application logic
index.html               Application entry point
styles.css               Main styles
sidebar.css, sidebar.js  Navigation styles and behavior
```

## Academic citation and licensing

Add the authors, institution, project date, and a persistent archive identifier here before formal academic release. Cite the underlying agricultural and weather sources independently of this software. No software license is currently declared; choose a license only after confirming author rights and the redistribution terms of included data and image assets.
