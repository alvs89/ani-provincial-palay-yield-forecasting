from __future__ import annotations

import re
from pathlib import Path

APP = Path("app.js")

if not APP.exists():
    raise SystemExit("app.js was not found. Run this script from the repository root.")

text = APP.read_text(encoding="utf-8")
backup = APP.with_name("app.synthetic.backup.js")
if not backup.exists():
    backup.write_text(text, encoding="utf-8")

# 1) Replace the browser-generated synthetic dataset with data loaded from FastAPI.
pattern = re.compile(r"\Aconst provinceRegion=.*?\nconst state=", re.S)
replacement = r"""const API_BASE='http://127.0.0.1:8000';
let provinceRegion={};
let data=[];
let apiMeta=null;

async function loadRealData(){
  const [metaResponse,historyResponse]=await Promise.all([
    fetch(`${API_BASE}/meta`),
    fetch(`${API_BASE}/historical/all`)
  ]);
  if(!metaResponse.ok||!historyResponse.ok){
    throw new Error('ANI backend is unavailable. Start FastAPI on port 8000.');
  }
  apiMeta=await metaResponse.json();
  const historyPayload=await historyResponse.json();
  provinceRegion=historyPayload.province_regions||apiMeta.province_regions||{};
  data=historyPayload.records||[];
}

const state="""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(
        "Could not find the synthetic-data block in app.js. "
        "Your app.js may differ from the version this patch was prepared for."
    )

# 2) Use the next currently supportable period from the present data cutoff.
text = text.replace("targetYear:2026,targetQuarter:2", "targetYear:2026,targetQuarter:1")

# 3) Replace the demo weighted formula with a real backend request.
pattern = re.compile(r"function forecast\(req\)\{.*?\}\nconst icon=", re.S)
replacement = r"""async function forecast(req){
  const response=await fetch(`${API_BASE}/predict`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      province:req.province,
      ecosystem:req.ecosystem,
      target_year:req.targetYear,
      target_quarter:req.targetQuarter
    })
  });
  const payload=await response.json();
  if(!response.ok){
    throw new Error(payload.detail||'Forecast request failed.');
  }
  if(!payload.eligible){
    throw new Error(payload.reason||payload.message||'Forecast unavailable.');
  }
  return payload;
}
const icon="""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not replace the old forecast() function.")

# 4) Existing processing animation can remain, but the final step now awaits FastAPI.
old = "state.current=forecast(state.request);save(state.current);state.page='result';render()"
new = (
    "forecast(state.request).then(f=>{"
    "state.current=f;save(state.current);state.page='result';render()"
    "}).catch(err=>{state.page='forecast';render();alert(err.message)})"
)
if old not in text:
    raise SystemExit("Could not find the old synchronous forecast call.")
text = text.replace(old, new, 1)

# 5) Keep the current design but update the content to reflect real data/model use.
replacements = {
    "Using synthetic demonstration dataset and mock forecasting engine.":
        "Using processed PSA agricultural data, NASA POWER weather data, and a trained XGBoost model.",
    "Synthetic demonstration dataset â€” not official PSA/PAGASA records.":
        "Processed ANI historical dataset derived from PSA agricultural records and NASA POWER weather data.",
    "Demo data only": "Processed data",
    "This is a live interface simulation over synthetic sample records. It is not a live PSA/PAGASA feed or a trained XGBoost model.":
        "ANI is using the locally deployed trained XGBoost model and processed historical dataset. Results are analytical estimates and are not official PSA forecasts.",
    "ANI computes a weighted baseline from the selected province and ecosystemâ€™s synthetic historical yields. Rainfall and temperature summaries are derived from the same sample records. This is a browser-side demonstration, not a trained model or a live agricultural data feed.":
        "ANI sends the selected province, ecosystem, and target period to the local FastAPI backend. The backend constructs the finalized lagged agricultural and agroclimatic features, checks forecast eligibility, applies the trained XGBoost pipeline, and returns the predicted yield together with historical seasonal context.",
    "Demo forecasts are synthetic and should not be interpreted as official PSA statistics, PAGASA products, or guaranteed agricultural outcomes.":
        "ANI forecasts are machine-learning-based analytical estimates and should not be interpreted as official PSA statistics or guaranteed agricultural outcomes.",
    "PAGASA-type variables: rainfall, temperature, relative humidity and other validated indicators.":
        "NASA POWER variables: rainfall, temperature, relative humidity, and wind speed.",
    "<li><b>Geographic:</b> Province, region, ecosystem</li>":
        "<li><b>Geographic:</b> Province and ecosystem</li>",
    "<li><b>Temporal:</b> Year, quarter</li>":
        "<li><b>Temporal:</b> Target quarter</li>",
    "<li><b>Agroclimatic:</b> Rainfall, temperature, humidity</li>":
        "<li><b>Agroclimatic:</b> Lagged rainfall, temperature, humidity, and wind speed</li>",
    "Primary candidate; will be evaluated against baseline regression models.":
        "Selected regression model for the current ANI integration prototype.",
    "Primary candidate, subject to validation":
        "Selected model after chronological evaluation",
}
for old_text,new_text in replacements.items():
    text=text.replace(old_text,new_text)

# 6) Current real historical coverage is 2000-2025.
text=text.replace("'12','Philippine provinces in demo dataset'",
                  "Object.keys(provinceRegion).length,'Philippine provinces represented'")
text=text.replace("'2018 â€“ 2026','Historical demonstration period'",
                  "'2000 â€“ 2025','Processed historical data period'")
text=text.replace("r.year===2026", "r.year===2025")

# 7) Use the actual years loaded from the backend in Historical Data filters.
text=text.replace(
    "[2018,2019,2020,2021,2022,2023,2024,2025,2026].map",
    "[...new Set(data.map(r=>r.year))].sort((a,b)=>a-b).map",
)

# 8) Current processed source data support the next period Q1 2026.
text=text.replace(
    "[2026,2027].map(y=>`<option value=\"${y}\" ${r.targetYear===y?'selected':''}>${y}${y>2026?' (Forecast beyond sample data)':''}</option>`).join('')",
    "[2026].map(y=>`<option value=\"${y}\" ${r.targetYear===y?'selected':''}>${y}</option>`).join('')",
)

# 9) Improve result labels to match the finalized academic interpretation.
text=text.replace("'Historical Average'", "'Historical Median'")
text=text.replace("'Same-quarter historical average'", "'Same-quarter historical median'")
text=text.replace("'Difference from Average'", "'Difference from Median'")
text=text.replace("'Relative to historical average'", "'Relative to historical seasonal median'")
text=text.replace("'Historical Range'", "'Typical Historical Range'")

# 10) Replace XGBoost n/a metrics with model metadata loaded from FastAPI.
selected_card = (
    '<div class="selected"><b>XGBoost Regressor</b><span>Primary candidate</span>'
    '<small>MAE n/a</small><small>RMSE n/a</small><small>RÂ² n/a</small></div>'
)
selected_replacement = (
    '<div class="selected"><b>XGBoost Regressor</b><span>Selected model</span>'
    '<small>MAE ${apiMeta?.model?.evaluation?.xgboost?.mae?.toFixed(3)??"n/a"} MT/ha</small>'
    '<small>RMSE ${apiMeta?.model?.evaluation?.xgboost?.rmse?.toFixed(3)??"n/a"} MT/ha</small>'
    '<small>RÂ² ${apiMeta?.model?.evaluation?.xgboost?.r2?.toFixed(3)??"n/a"}</small></div>'
)
text=text.replace(selected_card, selected_replacement)

# 11) Boot the UI only after real historical data has been loaded.
last = text.rfind("render();")
if last == -1:
    raise SystemExit("Could not find the final render() call.")
text = (
    text[:last]
    + "loadRealData().then(()=>{"
      "const next=apiMeta?.suggested_next_target;"
      "if(next){state.request.targetYear=next.year;state.request.targetQuarter=next.quarter;}"
      "render();"
      "}).catch(err=>{document.getElementById('app').innerHTML="
      "`<main style=\"padding:2rem;font-family:system-ui\"><h1>ANI backend not running</h1>"
      "<p>${err.message}</p><p>Start it with: <code>uvicorn backend.main:app --reload</code></p></main>`;"
      "});"
    + text[last + len("render();"):]
)

APP.write_text(text, encoding="utf-8")
print("Patched app.js successfully.")
print(f"Backup preserved at: {backup}")
