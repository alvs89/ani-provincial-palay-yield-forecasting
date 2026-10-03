# ANI: Provincial Palay Yield Forecasting System

An academic browser-based prototype for exploring provincial palay yield forecasting in the Philippines. ANI presents synthetic agricultural and agroclimatic records, computes a transparent baseline estimate, and demonstrates how a forecasting workflow and its outputs may be reviewed.

> **Research prototype notice:** The bundled records and forecast outputs are synthetic. This project does not use official Philippine Statistics Authority (PSA) or Philippine Atmospheric, Geophysical and Astronomical Services Administration (PAGASA) data, a trained machine-learning model, or a live data feed. Results are for software demonstration and academic discussion only; they must not inform operational agricultural decisions.

## Project objectives

- Demonstrate a user-facing workflow for provincial and ecosystem-level palay yield estimates.
- Present historical agricultural and agroclimatic variables through interactive filters and charts.
- Explain the relationship between temporal agricultural data, environmental indicators, and forecasting outputs.
- Provide a reproducible interface prototype that can support future research with validated data and models.

## Current implementation

ANI is a static, client-side web application built with HTML, CSS, and vanilla JavaScript. It has no package-installation step and can run directly in a modern browser.

- Dashboard with summary indicators, charts, and recent forecast records.
- Forecast input for province, ecosystem, target year, and quarter.
- Browser-side synthetic baseline calculation with a staged progress display.
- Forecast result with historical comparisons and derived rainfall and temperature summaries.
- Forecast history saved in browser `localStorage` and synchronized across open tabs.
- Historical synthetic data explorer with province, ecosystem, year, and text filters.
- Model and data page with holdout metrics calculated for a seasonal-naive baseline on synthetic records.
- Print-friendly forecast result.

## Run locally

No dependencies are required. From this directory, start a local static server:

```bash
python -m http.server 8080
```

Open <http://localhost:8080> in a browser. The application can also be opened directly from `index.html`, though a local server is recommended.

## Forecasting method

The current browser-side demonstration computes a weighted baseline using same-quarter historical yield, recent yield, and a previous comparable observation for the selected province and ecosystem. The displayed environmental summaries are calculated from the corresponding synthetic records. The model page computes MAE, RMSE, and R² for a previous-year, same-quarter seasonal-naive baseline on the synthetic 2025–2026 holdout records.

These calculations demonstrate application behavior and evaluation concepts. They are not a trained XGBoost, Random Forest, or regression model. Metrics computed on generated synthetic values do not establish predictive validity or agricultural usefulness.

## Data and limitations

- The application generates its demonstration dataset in `app.js` at runtime; no source CSV is included.
- Geographic coverage, agricultural measurements, and weather indicators are illustrative synthetic values.
- Forecasts and holdout metrics are calculated in the browser and are not independently validated.
- Forecast history is local to the current browser profile and is not backed up to a server or shared between users.
- No authentication, server-side persistence, official data integration, or production model is included.

Before research or operational use, replace the generated records with documented, licensed, quality-controlled data; implement time-aware training and validation; report uncertainty and limitations; and obtain appropriate domain review.

## Repository layout

```text
ani-standalone/
├── app.js                         # Application logic and synthetic demonstration data
├── index.html                     # Application entry point
├── styles.css                     # Main application styles
├── sidebar.css                    # Responsive navigation styles
├── sidebar.js                     # Navigation behavior
├── palay field background.jpg     # Dashboard field image
├── sidebar-rice.svg               # Sidebar rice artwork
└── favicon.*                      # Application icons
```

## Suggested academic repository metadata

- **Repository name:** `ani-provincial-palay-yield-forecasting`
- **Description:** `Academic browser prototype for provincial palay yield forecasting using synthetic agricultural and agroclimatic data.`
- **Topics:** `agriculture`, `rice-yield`, `forecasting`, `philippines`, `academic-prototype`, `data-visualization`

## Citation

If this project is used in academic work, cite the project repository and identify the version or commit used. Replace this section with the formal author list, institution, publication year, and a persistent DOI if the project is published or archived. Do not cite the prototype as evidence that its simulated forecasts are accurate.

## License

No license is currently specified. A license should only be added after the project authors choose the terms under which the source code may be reused. Third-party images and assets may have separate terms.
