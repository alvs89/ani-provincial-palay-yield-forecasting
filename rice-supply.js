/* ANI Stage 1: sourced national rice reference and assumption-based scenario; independent of ML. */
const ANI_RICE_REFERENCES = Object.freeze({
  palayYear:2025, yield:4.14, palay:19.67, area:4.75, ssr:78,
  supplyYear:2022, supply:18.65, utilization:16.80,
  sources:[
    ['PSA — 2025 Palay Situation Report','https://psa.gov.ph/statistics/crops/palay-situation-report/node/1684082355'],
    ['DA–PhilRice Ricelytics — rice industry','https://ricelytics.philrice.gov.ph/rice_industry'],
    ['PSA — Rice Supply Utilization Accounts','https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px/table/tableViewLayout2/'],
    ['DA — Masagana Rice Program (2023–2028)','https://calabarzon.da.gov.ph/wp-content/uploads/2024/08/Rice-Program-for-Website.pdf'],
    ['DA — Historical RCEF productivity aspirations (2019)','https://www.da.gov.ph/da-chief-assures-support-to-rice-farmers-amid-liberalized-trade/']
  ]
});
function riceSupplyPanel(){
 const s=ANI_RICE_REFERENCES;
 return `<section class="riceSupplyPanel" aria-labelledby="rice-supply-title">
  <div class="riceSupplyHeading"><div><span class="riceSupplyEyebrow">NATIONAL REFERENCE • PHILIPPINES</span><h2 id="rice-supply-title">Rice Supply & Productivity Benchmarks</h2><p>Official historical indicators and an optional calculation scenario. Not a prediction of rice imports.</p></div><span class="riceSupplyTag">Stage 1 • Reference</span></div>
  <div class="riceSupplyGrid">
   <article class="riceSupplyStat"><span>2025 national palay yield</span><strong>4.14 <small>MT/ha</small></strong><em>PSA actual • 2025</em></article>
   <article class="riceSupplyStat"><span>2025 palay production</span><strong>19.67 <small>MMT</small></strong><em>PSA actual • 2025</em></article>
   <article class="riceSupplyStat"><span>2025 harvested area</span><strong>4.75 <small>million ha</small></strong><em>PSA actual • 2025</em></article>
   <article class="riceSupplyStat"><span>2025 rice self-sufficiency</span><strong>78<small>%</small></strong><em>PhilRice / PSA • 2025</em></article>
  </div>
  <details class="riceDisclosure"><summary><span><strong>Government goals & historical supply</strong><small>View program targets and older national statistics</small></span></summary><div class="riceDisclosureBody"><div class="riceSupplyGrid riceSupplyPolicy">
   <article class="riceSupplyStat"><span>Government yield aspiration</span><strong>5–6 <small>MT/ha</small></strong><em>Historical RCEF-era program direction, not a universal 2026 threshold</em></article>
   <article class="riceSupplyStat"><span>Masagana rice sufficiency goal</span><strong>≥97<small>%</small></strong><em>DA 2023–2028 program target; not current actual</em></article>
   <article class="riceSupplyStat"><span>2022 total rice supply</span><strong>18.65 <small>MMT</small></strong><em>PhilRice historical supply account • 2022</em></article>
   <article class="riceSupplyStat"><span>2022 total rice utilization</span><strong>16.80 <small>MMT</small></strong><em>PhilRice historical supply account • 2022</em></article>
  </div>
  <div class="riceHistory"><h3>Historical Rice Supply and Import Context</h3><p>PSA Supply Utilization Accounts • million metric tons of milled rice equivalent (published 2020–2022 series)</p>
   <div class="riceHistoryTableWrap"><table><thead><tr><th>Year</th><th>Domestic rice production</th><th>Rice imports</th></tr></thead><tbody><tr><th>2020</th><td>12.619 MMT</td><td>2.219 MMT</td></tr><tr><th>2021</th><td>13.054 MMT</td><td>2.967 MMT</td></tr><tr><th>2022</th><td>12.921 MMT</td><td>3.863 MMT</td></tr></tbody></table></div>
   <p class="riceSupplyNotice">Historical imports are actual reported supply-account values, not import forecasts or policy recommendations. This table intentionally stops at 2022 rather than implying that unreconciled recent annual supply accounts are final.</p></div>
  <p class="riceSupplyNotice"><strong>Different reporting periods:</strong> The supply/utilization figures refer to 2022, while the yield, production and self-sufficiency figures refer to 2025. Do not subtract or divide them across years. PSA notes that 2023–2024 Supply Utilization Accounts are under review.</p>
  </div></details><div class="riceScenario" id="rice-simulation">
   <div><h3>Required Yield & Production Coverage Scenario</h3><p>Independent assumption calculator — does not use ANI's XGBoost predictions or estimate official import volumes.</p></div>
   <div class="riceScenarioInputs">
    <label>Assumed palay yield (MT/ha)<input id="riceScenarioYield" type="number" min="0.01" max="20" step="0.01" value="4.14" inputmode="decimal"></label>
    <label>Assumed annual harvested area (million ha)<input id="riceScenarioArea" type="number" min="0.01" max="20" step="0.01" value="4.75" inputmode="decimal"></label>
    <label>Assumed annual rice requirement (million MT)<input id="riceScenarioDemand" type="number" min="0.01" max="60" step="0.1" placeholder="e.g., 17.0" inputmode="decimal"></label>
    <label>Assumed milling recovery (%)<input id="riceScenarioRecovery" type="number" min="1" max="100" step="0.1" value="63" inputmode="decimal"></label>
   </div>
   <p class="riceSupplyNotice">Yield and area start at published 2025 national figures solely as editable inputs. The 63% recovery is an illustrative planning assumption; use an appropriately documented conversion for official comparisons. Enter a rice requirement to activate coverage calculations.</p>
   <div class="riceResultHeading"><strong>Calculated outlook</strong><span>Based on the assumptions above</span></div><div class="riceScenarioResults" aria-live="polite">
    <div><span>Implied palay production</span><strong id="riceCalcPalay">—</strong></div>
    <div><span>Implied milled-rice equivalent</span><strong id="riceCalcMilled">—</strong></div>
    <div><span>Domestic production coverage</span><strong id="riceCalcCoverage">—</strong></div>
    <div><span>Indicative production gap</span><strong id="riceCalcGap">—</strong></div>
    <div><span>Required national average yield</span><strong id="riceCalcRequired">—</strong></div>
   </div>
   <p id="riceCalcNote" class="riceSupplyNotice">Enter a valid annual rice requirement to calculate a scenario.</p>
   <p class="riceSupplyNotice"><strong>Interpretation:</strong> A production gap is not an import requirement. This scenario excludes rice stocks, reserves, losses, nonfood uses, exports and official import policy. Coverage here is not PSA's official self-sufficiency ratio.</p>
  </div>
  <details class="riceDisclosure riceSourcesDisclosure"><summary><span><strong>Sources & data notes</strong><small>Review the official references behind these indicators</small></span></summary><div class="riceSupplySources"><strong>Official data references</strong><div>${s.sources.map(([name,url])=>`<a href="${url}" target="_blank" rel="noopener noreferrer">${name} ↗</a>`).join('')}</div></div>
 </details></section>`;
}
function updateRiceScenario(){
 const read=id=>Number(document.getElementById(id)?.value);
 const yieldEl=document.getElementById('riceScenarioYield'),areaEl=document.getElementById('riceScenarioArea'),demandEl=document.getElementById('riceScenarioDemand'),recoveryEl=document.getElementById('riceScenarioRecovery');
 if(!yieldEl||!areaEl||!demandEl||!recoveryEl)return;
 const values=[yieldEl,areaEl,demandEl,recoveryEl].map(el=>el.value.trim()===''?NaN:Number(el.value));
 const [y,a,d,r]=values;const valid=values.every(Number.isFinite)&&y>0&&y<=20&&a>0&&a<=20&&d>0&&d<=60&&r>0&&r<=100;
 const ids=['riceCalcPalay','riceCalcMilled','riceCalcCoverage','riceCalcGap','riceCalcRequired'];
 if(!valid){ids.forEach(id=>document.getElementById(id).textContent='—');document.getElementById('riceCalcNote').textContent='Enter positive, in-range values for all four inputs (including rice requirement).';return;}
 const p=y*a,m=p*r/100,coverage=m/d*100,gap=Math.max(0,d-m),required=d/(a*r/100);
 [p.toFixed(2)+' MMT',m.toFixed(2)+' MMT',coverage.toFixed(1)+'%',gap.toFixed(2)+' MMT',required.toFixed(2)+' MT/ha'].forEach((v,i)=>document.getElementById(ids[i]).textContent=v);
 document.getElementById('riceCalcNote').textContent=coverage>=100?'Scenario domestic output covers the entered rice requirement before other supply-account adjustments.':'Scenario domestic output falls short of the entered rice requirement before other supply-account adjustments.';
}
document.addEventListener('input',event=>{if(event.target?.id?.startsWith('riceScenario'))updateRiceScenario()});
