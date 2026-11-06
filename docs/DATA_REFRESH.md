# ANI operational data refresh

## Scope

ANI checks supported official sources at backend startup and every six hours while the backend is running. The frontend checks the atomic `/data-snapshot` endpoint every 60 seconds and on focus, reconnection, or return to a visible tab. This is periodic latest-available data, not real-time observations.

The existing top-note shows the latest integrated PSA reference period, known release date, and freshness status. Its tooltip gives per-source periods, release dates, and check status. Source details already displayed in context panels retain their existing layout. No CSS redesign is included.

## Coverage and limitations

| Source | Automatic behavior | Remaining limitation |
| --- | --- | --- |
| PAGASA regional agri-weather | Fetch, validate, archive previous JSON, atomically publish latest bulletin | Availability depends on the official page; missing release dates remain unknown |
| PAGASA climate risk | Fetch and validate ENSO/drought context before publishing | Incomplete or older payloads retain the previous snapshot |
| PSA farmgate prices | Fetch and validate latest monthly provincial price observations | Publication cadence is monthly, not live prices |
| PSA agricultural statistics | Check official page; reload validated local CSV replacements | Official source returned HTTP 403 during verification; automated release import is not configured |
| Near-Term Palay Outlook | Check official page; reload validated local JSON replacement | Official source returned HTTP 403 during verification; release parsing/import is not configured |
| NASA POWER quarterly weather | Check source availability; reload validated local CSV replacements | Quarterly aggregation/import still requires the existing data preparation workflow |
| Satellite vegetation | Check source availability; reload validated local CSV replacements | Raster processing/import still requires the existing satellite preparation workflow |

An accessible page is not evidence that new numerical observations have been imported. The source status explicitly distinguishes page checks from successful imports. Failures preserve existing observations and expose the check failure. Do not describe all sources as automatically current.

## Consistency and preservation

- The backend validates candidate tables and JSON before replacing the in-memory operational snapshot. Failed validation retains the previously accepted snapshot.
- Checks include required columns/fields, duplicate keys, numerical values, quarter ranges, and regression of the latest reference period. Accepted updates rebuild operational feature context and projection context, without fitting or replacing the trained model.
- Metadata, historical records, projection metadata, environmental context, and freshness are returned together by `/data-snapshot`. Request handling is synchronized with reloads to avoid mixing versions within a response.
- Dashboard, Historical Data, Generate Estimate, Result History, Model & Data, and About use the updated shared data. Result History also responds to existing local-storage update events, including storage clearing.
- Current page, input selections, focus, scroll position, and disclosure state are preserved during permitted background rendering. Rendering is deferred during editing. Generated result pages and stored results remain snapshots and are not recomputed by data refresh.
- The first load of this newly installed frontend requires reopening or reloading the page once. Subsequent checks do not require full reloads.
- Prior imported JSON/CSV content is archived by content hash under `data/processed/refresh_archive/`; check state is in `data/processed/refresh_status.json`. Both are local operational artifacts excluded from Git.
- The XGBoost artifact, fixed evaluation data, feature definitions, and stored forecasts are unchanged. New source observations do not retrain the model or relax eligibility rules.

## Verified source periods on 6 November 2026

- Integrated PSA agriculture and NASA POWER: Q2 2026; recorded PSA release 29 July 2026.
- Satellite context: Q3 2026.
- PAGASA agri-weather: 1–10 November 2026; retrieval is not represented as a release date.
- PAGASA ENSO advisory: 3 November 2026, Advisory No. 6.
- Near-Term Palay Outlook: July–September 2026; recorded release 13 October 2026.
- Farmgate prices: September 2026.

These are verified integrated periods, not a guarantee that blocked sources have no newer publication.

## Verification commands

Run from the ANI checkout:

```powershell
.venv\Scripts\python.exe -m unittest tools.test_refresh
.venv\Scripts\python.exe verify_installation.py
.venv\Scripts\python.exe tools\verify_browser_refresh.py
node --check app.js
node --check freshness.js
git diff --check
```

The four refresh unit tests cover schema variants, invalid/older data rejection, bulletin validation, and successful/failed snapshot replacement. Browser verification uses isolated contexts at 1440, 900, and 390 pixels, with a mocked future snapshot that never modifies source files. It checks value updates, preserved selections/results/history, navigation count, JavaScript errors, and horizontal overflow. The installation verifier checks model/evaluation integrity, operational data, environmental freshness, forecast eligibility, and regional mappings.

Manual official-source check:

```powershell
.venv\Scripts\python.exe -m tools.automatic_refresh --once
```

## Next operational requirements

Implement and validate official agricultural and standing-crop release importers, and schedule the weather aggregation and satellite processing pipelines, before claiming fully automatic ingestion for those sources. Keep the backend running for the six-hour source schedule. Investigate source access failures through supported official distribution channels; do not substitute invented observations.
