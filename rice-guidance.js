/* National rice decision-support explainer: historical evidence + conditional projection.
   2022 PSA Supply Utilization Accounts: rice net food disposable = 15.200 MMT.
   This is FOOD AVAILABILITY, not the entire supply requirement or official forecast. */
const ANI_RICE_FOOD_BASELINE = Object.freeze({year:2022,netFoodMMT:15.2,source:"PSA rice Supply Utilization Accounts 2022"});
function riceGuidancePanel(){
 return `<section class="riceGuidance" aria-labelledby="riceGuidanceTitle">
 <div class="riceGuidanceHeading"><span class="riceToolKicker">PHILIPPINE RICE SUPPLY</span><h3 id="riceGuidanceTitle">Domestic production and rice import dependence</h3>
 <p>Domestic palay production supplies most of the country&#39;s rice, while imports and existing inventories contribute to availability. Import needs depend on total requirements, available stocks, seasonal harvest timing, and market conditions &mdash; not yield per hectare alone.</p></div>
 <div class="riceGuidanceCurrent"><div class="riceGuidanceCurrentTitle"><strong>Latest published indicators</strong><span>Different reference periods are identified on each card</span></div>
 <div class="riceGuidanceFacts riceGuidanceLatestFacts">
  <div><small>2025 full-year palay production</small><strong>19.67 MMT</strong><span>PSA; unmilled palay</span></div>
  <div><small>2025 rice self-sufficiency</small><strong>78.1%</strong><span>PSA official annual ratio</span></div>
  <div><small>2026 first-half palay production</small><strong>9.02 MMT</strong><span>PhilRice / PSA; January&ndash;June</span></div>
  <div><small>September 2026 rice imports</small><strong>0.418 MMT</strong><span>Monthly reported inflows</span></div>
  <div><small>September 2026 rice stocks</small><strong>1.91 MMT</strong><span>Inventory as of September 1</span></div>
 </div></div>
 <p class="riceGuidanceInsight"><strong>What this tells us:</strong> The 2025 self-sufficiency ratio shows that domestic production did not account for all rice supply. Reported imports and stocks provide more recent supply context, but the 2026 partial-year and monthly figures cannot establish a full-year shortage or next-year import requirement.</p>
 <div class="riceGuidanceLinks"><a href="https://psa.gov.ph/content/palay-situation-report-october-december-2025-and-january-december-2025" target="_blank" rel="noopener noreferrer">PSA 2025 palay statistics</a><a href="https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__AFIS/0022E5ESSR0.px/table/tableViewLayout2/" target="_blank" rel="noopener noreferrer">PSA rice self-sufficiency</a><a href="https://ricelytics.philrice.gov.ph/rice_industry" target="_blank" rel="noopener noreferrer">PhilRice rice industry indicators</a><a href="https://psa.gov.ph/content/rice-and-corn-stocks-inventory-september-2026" target="_blank" rel="noopener noreferrer">PSA September rice stocks</a></div>
 <details class="riceDisclosure riceGuidanceHistory"><summary><span><strong>How domestic supply and imports are counted</strong><small>Historical 2022 rice supply account &middot; comparable annual breakdown</small></span></summary>
 <div class="riceDisclosureBody"><div class="riceGuidanceFacts"><div><small>2022 domestic milled rice</small><strong>12.92 MMT</strong><span>PSA production</span></div><div><small>2022 rice available for human food</small><strong>15.20 MMT</strong><span>PSA net food disposable</span></div><div><small>2022 rice imports</small><strong>3.86 MMT</strong><span>PSA recorded imports</span></div></div>
 <p class="riceGuidanceInsight">In 2022, food availability exceeded domestic milled-rice production by approximately 2.28 MMT. Imports, beginning stocks, and other utilization components explain the larger national supply balance; this difference is <strong>not</strong> the volume of imports required.</p>
 <p class="riceGuidanceNote">The 2022 example is retained because the newer complete Supply Utilization Accounts for 2023&ndash;2024 were under PSA review as of its May 2026 update. It should not be interpreted as the latest monthly rice situation.</p>
 <a class="riceGuidanceSource" href="https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px/table/tableViewLayout2/" target="_blank" rel="noopener noreferrer">PSA rice Supply Utilization Accounts</a></div>
 </details>
 </section>`;
}
function riceGuidedScenarioPanel(){
 return `<section class="riceGuided" aria-labelledby="riceGuidedTitle">
 <div class="riceToolHeading"><div><span class="riceToolKicker">GUIDED PLANNING SCENARIO</span><h3 id="riceGuidedTitle">Could domestic rice production cover future food needs?</h3>
 <p>Start with published historical figures and test your own assumptions. Results describe a possible outcome, <strong>not a validated future forecast</strong>.</p></div></div>
 <div class="riceGuidedGrid">
 <label>Target year<select id="riceGuideYear"><option>2027</option><option>2028</option><option>2029</option><option>2030</option></select></label>
 <label>Annual growth in rice food needs (%)<input id="riceGuideDemandGrowth" type="number" min="-5" max="10" step="0.1" value="1"></label>
 <label>Change in palay yield versus 2025 (%)<input id="riceGuideYieldChange" type="number" min="-50" max="100" step="0.5" value="0"></label>
 <label>Change in harvested area versus 2025 (%)<input id="riceGuideAreaChange" type="number" min="-50" max="100" step="0.5" value="0"></label>
 <label>Palay-to-rice recovery (%)<input id="riceGuideRecovery" type="number" min="1" max="100" step="0.5" value="63"></label></div>
 <div class="riceGuidedResults" aria-live="polite">
 <div><span>Projected food availability needed</span><strong id="riceGuideDemandResult">—</strong></div>
 <div><span>Scenario domestic milled rice</span><strong id="riceGuideProductionResult">—</strong></div>
 <div><span>Domestic food-needs coverage</span><strong id="riceGuideCoverageResult">—</strong></div>
 <div><span>Food-only production gap</span><strong id="riceGuideGapResult">—</strong></div></div>
 <p id="riceGuideInterpretation" class="riceGuidanceInsight" role="status"></p>
 <details class="riceOutlookMethod"><summary>Data sources, assumptions and limitations</summary>
 <div class="riceMethodContent"><p>The starting 15.20 MMT is PSA's <strong>2022 total net food disposable</strong>, not observed consumption or the complete national rice requirement. For the selected year, projected food needs = 15.20 × (1 + annual food-needs growth / 100)<sup>(target year − 2022)</sup>.</p>
 <p>Scenario domestic palay output = 19.67 MMT (PSA 2025) × (1 + assumed yield change / 100) × (1 + assumed area change / 100). Multiply by the entered milling recovery to obtain milled-rice equivalent. Food-needs coverage = domestic milled rice / projected food needs × 100%. The food-only production gap is the positive difference between them.</p>
 <p>These inputs are <strong>user-defined assumptions</strong>; there is no official 2027 rice-demand forecast or 2027 national production forecast generated by this calculator. The estimated food-only gap excludes stocks, other utilization, exports, reserve requirements and market policy, and <strong>must not be labeled an import requirement</strong>.</p>
 <a href="https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px/table/tableViewLayout2/" target="_blank" rel="noopener noreferrer">PSA supply utilization accounts</a> · <a href="https://psa.gov.ph/statistics/crops/palay-situation-report/node/1684082355" target="_blank" rel="noopener noreferrer">PSA 2025 palay output</a></div></details>
 </section>`;
}
function riceGuidedMath({year,demandGrowth,yieldChange,areaChange,recovery}){
 const food=15.2*Math.pow(1+demandGrowth/100,year-2022);
 const palay=19.67*(1+yieldChange/100)*(1+areaChange/100);
 const production=palay*recovery/100;
 return {food,palay,production,coverage:production/food*100,gap:Math.max(0,food-production)};
}
function updateRiceGuide(){
 if(!document.getElementById('riceGuideYear'))return;
 const read=id=>{const s=String(document.getElementById(id).value??'').trim();return s===''?NaN:Number(s)};
 const v={year:read('riceGuideYear'),demandGrowth:read('riceGuideDemandGrowth'),yieldChange:read('riceGuideYieldChange'),areaChange:read('riceGuideAreaChange'),recovery:read('riceGuideRecovery')};
 const fields=['riceGuideDemandResult','riceGuideProductionResult','riceGuideCoverageResult','riceGuideGapResult'];
 const valid=Object.values(v).every(Number.isFinite)&&v.year>=2027&&v.year<=2030&&v.demandGrowth>=-5&&v.demandGrowth<=10&&v.yieldChange>=-50&&v.yieldChange<=100&&v.areaChange>=-50&&v.areaChange<=100&&v.recovery>0&&v.recovery<=100;
 if(!valid){fields.forEach(id=>document.getElementById(id).textContent='—');document.getElementById('riceGuideInterpretation').textContent='Enter valid numbers within the indicated input ranges.';return;}
 const r=riceGuidedMath(v);
 [r.food.toFixed(2)+' MMT',r.production.toFixed(2)+' MMT',r.coverage.toFixed(1)+'%',r.gap.toFixed(2)+' MMT'].forEach((value,i)=>document.getElementById(fields[i]).textContent=value);
 riceRenderFoodInterpretation(document.getElementById('riceGuideInterpretation'),{year:v.year,coverage:r.coverage,gap:r.gap,food:r.food,production:r.production});
}
function initializeRiceGuide(){
 const ids=['riceGuideYear','riceGuideDemandGrowth','riceGuideYieldChange','riceGuideAreaChange','riceGuideRecovery'];
 if(!document.getElementById(ids[0]))return;
 ids.forEach(id=>document.getElementById(id).addEventListener('input',updateRiceGuide));
 updateRiceGuide();
}
