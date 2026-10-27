# ANI presentation-readiness audit — 27 October 2026

## Scope and result
This audit reviewed the local integration verification, frontend/backend health, national rice source references, data coverage, scenario mathematics, input validation, and representative browser rendering. It is **not** a claim of exhaustive visual, cross-browser, security, or predictive validity testing.

## Verified checks
- `python verify_installation.py`: PASS (backend health/metadata, model availability, agricultural/weather record consistency, 2025 holdout, lag availability, 2026 Q3 eligibility, satellite/near-term/long-term context, province normalization).
- `node tools/audit_rice_supply.cjs .`: PASS (29 assertions covering three rice calculators, shortage/surplus scenarios, reference markup, and numeric entry patterns).
- JavaScript syntax for affected pages and Git diff whitespace checks: PASS.
- Browser headless DOM: dashboard loads and Rice Supply navigation text appears; API `/health` and static assets serve HTTP 200.
- Official PSA 2025 national palay production 19.67 MMT, harvested area 4.75 million hectares, and yield 4.14 MT/ha match displayed reference values. PSA 2025 rice SSR 78.1% also matches.
- Official PSA 2022 rice Supply Utilization Accounts match domestic milled-rice production 12.921 MMT and imports 3.863 MMT. PSA notes that later complete supply accounts for 2023–2024 are under review (May 2026 release).
- Current PhilRice/PSA context: 2026 semester-one palay production 9.02 MMT, September 2026 rice imports 0.418 MMT, September 1 rice stocks 1.91 MMT. These values must not be combined as if the same reporting period.

## Issue corrected in this audit
- Numeric-only text inputs had incremental-value feedback but output calculators could still calculate from a value violating the configured step. Added a shared `riceValueConforms` check and enforced it inside all three rice calculators. A regression audit now covers representative valid/invalid input formats and scenario formulas.

## Known limits and open presentation risks
1. Provincial records vs national statistics: 2025 local palay history aggregates to 19.579261 MMT and 4.721420 million hectares; official PSA national values are 19.67 MMT and 4.75 million hectares. The difference remains unreconciled. The national rice panels correctly retain the separate official national baseline; do not aggregate provincial rows as an official national forecast without source-level reconciliation.
2. There is no validated four-quarter future national production or import-requirement forecast. Future National Supply Outlook values are assumptions, not official import decisions or independently validated future results. The 2022 net-food-disposable baseline is historical, not observed future demand.
3. Scenario results use rounding for display; calculations retain unrounded intermediate values. Coverage is not the PSA official SSR. Supply gap is not automatically import volume.
4. No complete browser interaction/responsive visual audit at multiple screen sizes was completed in this run, and a formal external-user usability test has not been performed.
5. The model evaluation provides historical evidence on the fixed holdout; it does not guarantee future predictions. The long-term CMIP6 module is a climate-analog scenario, not a validated yield forecast.

## Recommended presentation scope
Safe for a **provisional prototype demonstration** with honest labels: show validated 2025 holdout results, historical/current national indicators with reference dates, and assumption-driven calculators. **Not certified as fully presentation-ready for claims about future national rice import volumes** until source reconciliation, national forecast backtesting, and full UI interaction/visual checks are complete.

## Primary sources
- https://psa.gov.ph/statistics/crops/palay-situation-report/node/1684082355
- https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__AFIS/0022E5ESSR0.px/table/tableViewLayout2/
- https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px/table/tableViewLayout2/
- https://ricelytics.philrice.gov.ph/rice_industry
- https://psa.gov.ph/content/rice-and-corn-stocks-inventory-september-2026
## Follow-up technical re-audit (2026-10-27)
- Reran full integration verifier: all documented checks passed.
- Extended Rice Supply regression suite to **29 assertions**, including numeric year conversion and correct scenario interpretation wording. All pass.
- Direct source reconciliation: 588 provincial records spanning 82 provinces sum to 19.579261 MMT palay and 4.721420 million hectares for 2025, against PSA national 19.67 MMT and 4.75 million hectares (differences: about 90,739 MT and 28,580 ha). These discrepancies are not silently adjusted or filled.
- Verified national 2025 rice SSR of 78.1% against PSA OpenSTAT and its definition. PSA adopted 63% palay milling recovery beginning in 2023 according to the same metadata.
- The 2025 model holdout, 2026 Q1 active training cutoff, and independent climate/context modules remain untouched.
- UI appearance was excluded at user request; there is no claim that every page has been visually tested.
- **Verdict:** technically suitable for a scoped prototype demonstration with clearly labeled scenarios and historic holdout. Not validated to forecast actual annual rice imports or to aggregate 2025 provincial totals as official national estimates.

## Browser walkthrough completed (October 27, 2026)

A subsequent browser-level quality-assurance run using Microsoft Edge covered dashboard, forecasting navigation, near-term and long-term sub-tabs, historical data, national rice tabs, result history, Model & Data, and About ANI. Tested viewports: 1440 x 900 (desktop), 900 x 900 (tablet), and 390 x 844 (mobile). The corrected mobile sidebar flow and visible tooltip test passed. No JavaScript page errors or document-level horizontal overflow appeared in the tested states. The advanced illustrative supply interpretation, guided target-year change, and numeric-input rejection and range feedback also passed.

Supporting scripts and captured results: `tools/browser_audit_ani.py`, `tools/browser_audit_flows.py`, `outputs/ani_browser_audit.json`, and `outputs/ani_browser_flows.json`.

**Evidence boundary:** These automated browser checks do not exhaustively validate all province/ecosystem cases, manually inspect every responsive element, or establish full keyboard, screen-reader, Firefox, or Safari compatibility. The resulting presentation verdict is readiness for a *scoped academic prototype demonstration*, not unqualified production certification.

## Documentation consolidation

The repository README now describes the final user-facing Rice Supply tabs rather than historic "Stage 1 / Stage 2" development terminology, distinguishes current and historical source periods, and documents the validated scope and remaining national-data reconciliation. Documentation-only changes do not alter XGBoost training, scenario math, or integrated datasets.
