# ANI: Provincial Palay Yield Forecasting System

ANI is a provincial palay yield forecasting system for the Philippines. It combines processed agricultural history, lagged agroclimatic information, an XGBoost regression model, a FastAPI service, and a browser-based user interface.

ANI reports model results according to the target quarter: **Prospective Forecast**, **Current-Quarter Estimate**, or **Retrospective Estimate**. Model eligibility and temporal classification are separate. A target is offered only when the required historical and lagged inputs exist; its result type depends on whether the target quarter is future, in progress, or completed.

All model outputs are analytical estimates. They are not official PSA crop statistics and do not guarantee agricultural outcomes.

## System components

- Browser interface for estimates, historical records, model information, and Result History.
- FastAPI service for model metadata, historical records, estimate availability, and XGBoost inference.
- Processed agricultural, weather, and satellite vegetation datasets in `data/processed/`.
- Bundled scikit-learn/XGBoost pipeline in `models/`.
- Historical yield benchmarks, associated pre-target signals, satellite vegetation, provincial palay farmgate-price context, official PAGASA regional agri-weather context, and official PAGASA climate-risk context presented alongside model results.
- Separate Environmental Decision Support output. Contextual layers are not inputs to the XGBoost yield model and do not replace a yield estimate.

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
- `province_quarter_satellite.csv`: quarterly cropland-masked MODIS NDVI/EVI summaries used for controlled satellite-feature evaluation.
- `palay_farmgate_prices.csv`: monthly provincial PSA OpenSTAT palay farmgate-price records retained as market context, not model predictors.
- `pagasa_regional_agri_weather.json`: integrated DOST-PAGASA 10-Day Regional Agri-Weather information used as official latest-published-period context, not model predictors.
- `pagasa_climate_risk.json`: DOST-PAGASA ENSO advisory and provincial meteorological drought assessment/outlook context, stored separately from model inputs.
- `data_provenance.json`: source matrices, coverage, data-status, agricultural/weather/satellite/context methods, and evaluation/deployment provenance.

ANI's modeling unit is the province. Selected-city OpenSTAT series are outside that unit, and PSA notes that BARMM aggregate totals can include Eight Cluster Areas that are not separately assignable to a province. Accordingly, sums of ANI province-level rows are not intended to reproduce PSA national or regional aggregate totals exactly.

ANI reports the integrated data cutoff at runtime through `GET /meta`. This describes the data currently integrated into ANI and is not a general claim that no newer source release exists.

## Satellite vegetation data

ANI maintains a province-quarter satellite vegetation dataset derived from **NASA MODIS/Terra MOD13A1 Collection 6.1**. The product provides 16-day NDVI and EVI composites at 500 m resolution. ANI aggregates quality-screened observations within DENR provincial boundaries after applying an ESA Climate Change Initiative cropland mask. Cropland classes 10, 11, 12, 20, and 30 are included; the preceding year's land-cover map is used where available, and the 2020 map is retained for 2021 onward because it is the latest annual ESA CCI map available through the selected source.

The satellite series covers **Q1 2000 through Q3 2026** for 82 provinces. The Microsoft Planetary Computer MODIS mirror used by the extraction pipeline contains no Terra Q3 2025 items over the Philippines. NASA Earthdata CMR lists the corresponding MOD13A1 source granules, so ANI treats this as an access-platform mirror gap rather than an absence of satellite observation. The quarter is left missing rather than silently mixing access sources or synthesizing vegetation values. Pre-2024 satellite values for Maguindanao del Sur are also withheld during model evaluation because older agricultural records represent the former undivided Maguindanao province while the current DENR polygon represents the post-split province.

Satellite predictors are governed by the same chronological-validation principle as the active model. Candidate lagged NDVI/EVI features are selected using 2024 development validation and then checked on the fixed 2025 holdout. Under the predefined acceptance rule, the satellite candidate did **not** qualify for deployment: the current feature model produced 2025 MAE **0.2232 MT/ha**, while the selected satellite-augmented candidate produced **0.2250 MT/ha**. The satellite candidate slightly improved RMSE and R², but it worsened the primary MAE metric and had only **74.8% complete-case satellite coverage** on the holdout. The active deployed model therefore retains the agricultural-plus-weather predictor set rather than forcing a weaker or incompletely observed satellite feature set into production.

For generated estimates, ANI presents a separate **Satellite Vegetation Context** when the immediately preceding quarter has a usable MODIS observation. The context reports pre-target cropland NDVI/EVI and compares them with earlier observations from the same seasonal quarter. The seasonal status is based on the previous-quarter NDVI relative to its historical 25th–75th percentile range. Satellite availability never determines yield-model eligibility and the context does not alter the XGBoost estimate. If the required pre-target satellite period is unavailable, ANI withholds only the satellite context rather than interpolating a value or withholding an otherwise valid yield estimate.

The extraction and evaluation workflows are reproducible through `python -m tools.build_satellite_vegetation` and `python -m tools.evaluate_satellite_features`.

## Farmer-facing contextual layers

ANI supplements the model estimate with independent information that improves interpretation without changing XGBoost inference.

**Historical Yield Benchmarks** compare the estimate with pre-target PSA history for the same province, ecosystem, and calendar quarter. ANI reports the province same-quarter median, recent five-year same-quarter median, historical upper quartile, regional same-quarter median, and historical percentile. These values are historical reference benchmarks and are not presented as a universal or agronomic optimal yield.

**Associated Pre-Target Signals** summarize agricultural and environmental changes observed before the target quarter, including same-quarter production and harvested-area changes, rainfall relative to its historical seasonal median, temperature relative to its historical seasonal median, and the available satellite NDVI seasonal comparison. These signals describe coincident conditions; they do not establish that any one factor caused a yield change.

**Provincial Palay Market Context** uses the PSA OpenSTAT Farm Price Survey for Palay. ANI stores monthly provincial farmgate prices for dry palay and reports the latest available price, month-over-month change, year-over-year change, and trailing 12-month range when sufficient records exist. Farmgate prices are market information and do not alter the yield estimate.

**Official PAGASA Agri-Weather Context** uses DOST-PAGASA's 10-Day Regional Agri-Weather Information. ANI records the published forecast period, regional rainfall range, number of rainy days, temperature range, relative humidity, reported rice stages, and farm operations. This information supports current farm planning but remains separate from the historical lagged weather variables used by XGBoost.

**Official PAGASA Climate Risk Context** displays the latest published ENSO advisory together with PAGASA's provincial meteorological drought assessment and outlook. ANI shows PAGASA's own classifications—Not affected, Dry condition, Dry spell, and Drought—without calculating a replacement drought category. These climate-risk records are decision context only and do not alter the XGBoost yield estimate.

The bundled contextual files can be refreshed from their public sources with:

```powershell
.venv\Scripts\python.exe -m tools.update_farmer_context
```

The application includes the integrated copies so normal installation and offline demonstration do not depend on a successful live web request. Source periods remain visible in the interface so users can judge freshness.

## Near-Term Palay Outlook

ANI includes a separate **Near-Term Palay Outlook** mode that combines the latest published PSA Monthly Palay and Corn Situation Reporting System (MPCSRS) standing-crop release with current official PAGASA planning context for the selected province.

The integrated October 13, 2026 PSA release covers **July–September 2026** standing crops as of **September 1, 2026**. It provides national published estimates for palay production, harvest area, yield, harvested share, crop growth stages, and planting-intention progress. Because ANI does not currently integrate a province-specific public MPCSRS table, the system labels these standing-crop figures as a **national published summary** and does not infer province-level values.

The province selection localizes the accompanying PAGASA 10-Day Regional Agri-Weather and climate-risk context. This outlook is descriptive decision-support context only: it does **not** alter the quarterly XGBoost model, its fixed 2025 holdout evaluation, or the separate long-term CMIP6 projection.

The 2026 MPCSRS survey schedule indicates that the next survey month after September is November, with results targeted for **December 15, 2026**. ANI therefore displays the exact release/reference period instead of presenting unreleased Q4 standing-crop values as current official data.

## Experimental long-term climate projection

ANI also provides a separate **Long-Term Projection** mode for **3-, 5-, and 10-year** scenario exploration. This module is intentionally separate from the deployed next-quarter XGBoost model because future Lag 1 yield, production, and harvested-area observations do not exist several years in advance.

The module retrieves future climate conditions from **NASA NEX-GDDP-CMIP6** for the selected province, quarter, year, and SSP pathway. It currently uses a small multi-model ensemble—ACCESS-CM2, GFDL-ESM4, and MPI-ESM1-2-HR—and the variables precipitation, daily maximum/minimum temperature, relative humidity, and near-surface wind speed. Daily data are aggregated to quarterly rainfall and mean climate summaries.

For each CMIP6 model, ANI finds the **five most climatically similar historical observations** for the same province, ecosystem, and calendar quarter using rainfall, mean temperature, relative humidity, and wind speed. The observed yields from those historical analog years form that climate model's projected yield. The user-facing central value is the median across available climate models, while the displayed range incorporates both climate-model spread and the historical analog-yield spread.

This is an **experimental scenario projection**, not a precise long-range forecast and not an official PSA projection. A chronological 2021–2025 check, trained from 2001–2020 historical analogs, produced:

| Method | MAE (MT/ha) | RMSE (MT/ha) | R² |
| --- | ---: | ---: | ---: |
| Climate-analog projection | 0.4174 | 0.5449 | 0.6201 |
| Previous-year same-quarter baseline | 0.2572 | 0.3970 | 0.7955 |

Because the climate-analog method is weaker than the short-term seasonal baseline, ANI labels it experimental and does not present it as a replacement for the validated quarterly XGBoost model. Its purpose is to explore how historically comparable yield conditions relate to possible future climate scenarios when actual future agricultural lags are unavailable.

The projection workflow is reproducible through:

```powershell
.venv\Scripts\python.exe -m tools.build_province_centroids
.venv\Scripts\python.exe -m tools.evaluate_long_term_projection
```

NEX-GDDP-CMIP6 point/quarter responses are cached locally after retrieval so repeated demonstrations of the same scenario do not require downloading the same data again.

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

## Environmental and farmer decision context

ANI keeps prediction and supporting context distinct. The deployed XGBoost model is limited to its validated agricultural and lagged agroclimatic predictor set. Historical benchmarks, associated pre-target signals, satellite vegetation, PSA farmgate prices, PAGASA agri-weather information, and PAGASA climate-risk information are displayed as independent contextual layers.

Environmental Decision Support remains a separate short-term analysis. Its availability is matched to province and ecosystem and checked against the stored report's forecast window. Environmental summaries do not replace the model result or constitute a planting recommendation. Field-specific interpretation requires verified site context and locally validated agronomic decision thresholds.

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

The verification suite checks agricultural, weather, satellite, market, official agri-weather, and official climate-risk data integrity; fixed 2025 evaluation metrics; deployment training cutoff; satellite deployment decision; contextual-layer separation from XGBoost; Q3/Q4 eligibility behavior; province normalization; current region mapping; temporal classification; and environmental freshness rules.

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
data/processed/          Agricultural, weather, satellite, market, agri-weather, climate-risk, provenance, and model-ready datasets
data/reference/          Frozen geospatial references used by satellite aggregation
ml/                      Feature construction and model training
models/                  Serialized model and metadata
outputs/                 Environmental and satellite-evaluation outputs
tools/                   Reproducible satellite extraction/evaluation and public contextual-data refresh utilities
app.js                   Browser application logic
environmental.js         Environmental decision-support presentation
index.html               Application entry point
styles.css               Main application styles
sidebar.css, sidebar.js  Navigation styles and behavior
setup_ani.bat            Environment setup and verification
run_ani.bat              Local application launcher
verify_installation.py   Deterministic integration verification
```
