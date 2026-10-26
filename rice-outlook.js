/* ANI Stage 2: auditable, deterministic supply outlook scenarios, NOT ML import forecasts. */
const ANI_RICE_OUTLOOK_BASELINE = Object.freeze({year:2025,palayMMT:19.67,areaMHa:4.75,source:'PSA 2025 Palay Situation Report'});
const riceOutlookDefaults = Object.freeze({targetYear:2027,yieldChange:0,areaChange:0,milling:63,demand:'',openingStocks:'',reserve:'',otherUses:0,exports:0});
function riceOutlookPanel(){
 return `<section class="riceOutlook" aria-labelledby="rice-outlook-title">
 <div class="riceSupplyHeading"><div><span class="riceSupplyEyebrow">NATIONAL PLANNING • SCENARIO ANALYSIS</span><h2 id="rice-outlook-title">National Rice Supply Outlook</h2><p>Explore how assumed changes in production and demand affect potential rice supply. This is not an official government import forecast.</p></div><span class="riceSupplyTag">Stage 2 • Scenario</span></div>
 <div class="riceOutlookInfo"><strong>Starting point:</strong> PSA 2025 national palay production: 19.67 million MT; harvested area: 4.75 million ha. Future values below are <strong>assumptions</strong>, not XGBoost forecasts. ANI's provincial 2025 local records total about 19.58 million MT and require reconciliation before use as a national forecasting baseline.</div>
 <div class="riceScenarioInputs riceOutlookInputs">
 <label>Scenario target year<select id="riceOutlookYear"><option value="2027">2027</option><option value="2028">2028</option><option value="2029">2029</option><option value="2030">2030</option></select></label>
 <label>Yield change from 2025 (%)<input id="riceOutlookYieldChange" type="number" min="-90" max="150" step="0.5" value="0"></label>
 <label>Harvested-area change from 2025 (%)<input id="riceOutlookAreaChange" type="number" min="-90" max="150" step="0.5" value="0"></label>
 <label>Milling recovery (%)<input id="riceOutlookMilling" type="number" min="1" max="100" step="0.5" value="63"></label>
 <label>Target-year rice requirement (MMT)<input id="riceOutlookDemand" type="number" min="0.01" max="60" step="0.1" placeholder="Required • scenario assumption"></label>
 <label>Opening rice stocks (MMT)<input id="riceOutlookOpeningStocks" type="number" min="0" max="30" step="0.1" placeholder="Required • scenario assumption"></label>
 <label>Desired ending rice stocks (MMT)<input id="riceOutlookReserve" type="number" min="0" max="30" step="0.1" placeholder="Required • scenario assumption"></label>
 <label>Other uses/losses (MMT)<input id="riceOutlookOtherUses" type="number" min="0" max="30" step="0.1" value="0"></label>
 <label>Rice exports (MMT)<input id="riceOutlookExports" type="number" min="0" max="30" step="0.1" value="0"></label>
 </div>
 <div class="riceOutlookActions"><button id="riceOutlookReset" type="button">Reset assumptions</button><button id="riceOutlookExample" type="button">Load illustrative example</button></div>
 <div class="riceResultHeading"><strong>Scenario results</strong><span>Not an official rice import forecast</span></div><div class="riceScenarioResults riceOutlookResults" aria-live="polite">
 <div><span>Scenario palay production</span><strong id="riceOutlookPalay">—</strong></div>
 <div><span>Milled-rice equivalent</span><strong id="riceOutlookMilled">—</strong></div>
 <div><span>Production coverage</span><strong id="riceOutlookCoverage">—</strong></div>
 <div><span>Indicative supply balance</span><strong id="riceOutlookBalance">—</strong></div>
 <div><span>Additional supply needed</span><strong id="riceOutlookNeed">—</strong></div>
 <div><span>Demand-equivalent required yield</span><strong id="riceOutlookRequired">—</strong></div>
 </div>
 <div id="riceOutlookInterpretation" class="riceOutlookInfo" role="status">Enter rice requirements and stock assumptions to view a supply balance. These values are intentionally blank: no fabricated demand projection is supplied.</div>
 <details class="riceOutlookMethod"><summary>Calculation method and limitations</summary><p>Scenario palay output = 2025 PSA national palay output × (1 + yield-change %) × (1 + harvested-area-change %). Milled-rice equivalent = scenario palay × milling recovery. Production coverage = milled-rice equivalent ÷ assumed target-year requirement. Indicative supply balance = milled-rice equivalent + opening stocks − requirement − other uses/losses − exports − desired ending stocks. Additional supply needed = maximum of zero and negative balance. Demand-equivalent required palay yield = requirement ÷ (scenario harvested area × milling recovery). Requirement, stocks, losses and exports must be consistent in <strong>milled rice MMT</strong> for the same annual period.</p><p>This is a conditional annual scenario, not a forecast of national import volumes, official SSR, or a recommendation to import. Actual import decisions depend on timing, market and government policy. Do not add model-derived provincial estimates to the official national baseline: that would double-count production.</p><p>Primary references: <a href="https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px" target="_blank" rel="noopener noreferrer">PSA Supply Utilization Accounts</a>; <a href="https://psa.gov.ph/statistics/technical-notes/167330" target="_blank" rel="noopener noreferrer">PSA supply-account definitions</a>; <a href="https://ricelytics.philrice.gov.ph/rice_industry" target="_blank" rel="noopener noreferrer">PhilRice national statistics</a>.</p></details>
 </section>`;
}
function calculateRiceOutlook(v){
 const {yieldChange,areaChange,milling,demand,openingStocks,reserve,otherUses,exports}=v;
 const palay=ANI_RICE_OUTLOOK_BASELINE.palayMMT*(1+yieldChange/100)*(1+areaChange/100);
 const area=ANI_RICE_OUTLOOK_BASELINE.areaMHa*(1+areaChange/100);
 const milled=palay*milling/100;
 const coverage=milled/demand*100;
 const balance=milled+openingStocks-demand-otherUses-exports-reserve;
 return {palay,area,milled,coverage,balance,need:Math.max(0,-balance),required:demand/(area*milling/100)};
}
function readRiceOutlook(){
 const map={yieldChange:'riceOutlookYieldChange',areaChange:'riceOutlookAreaChange',milling:'riceOutlookMilling',demand:'riceOutlookDemand',openingStocks:'riceOutlookOpeningStocks',reserve:'riceOutlookReserve',otherUses:'riceOutlookOtherUses',exports:'riceOutlookExports'};
 const out={};for(const [key,id] of Object.entries(map)){const raw=String(document.getElementById(id)?.value??'').trim();out[key]=raw===''?NaN:Number(raw)}return out;
}
function updateRiceOutlook(){
 const ids=['riceOutlookPalay','riceOutlookMilled','riceOutlookCoverage','riceOutlookBalance','riceOutlookNeed','riceOutlookRequired'];if(!document.getElementById(ids[0]))return;
 const v=readRiceOutlook(),finite=Object.values(v).every(Number.isFinite);
 const valid=finite&&v.yieldChange>=-90&&v.yieldChange<=150&&v.areaChange>=-90&&v.areaChange<=150&&v.milling>0&&v.milling<=100&&v.demand>0&&v.demand<=60&&[v.openingStocks,v.reserve,v.otherUses,v.exports].every(x=>x>=0&&x<=30);
 if(!valid){ids.forEach(id=>document.getElementById(id).textContent='—');document.getElementById('riceOutlookInterpretation').textContent='Complete all inputs with valid numbers. Requirement and beginning/ending stocks are required. All volumes must refer to the same target year and use milled rice MMT.';return;}
 const r=calculateRiceOutlook(v),mm=x=>x.toFixed(2)+' MMT';
 [mm(r.palay),mm(r.milled),r.coverage.toFixed(1)+'%',(r.balance>=0?'+':'')+mm(r.balance),mm(r.need),r.required.toFixed(2)+' MT/ha'].forEach((value,i)=>document.getElementById(ids[i]).textContent=value);
 const year=document.getElementById('riceOutlookYear').value;
 document.getElementById('riceOutlookInterpretation').textContent=`For the ${year} assumptions, domestic milled-rice output would cover ${r.coverage.toFixed(1)}% of the entered annual requirement. ${r.balance>=0?'The assumed supply balance is non-negative after stocks and other uses.':'The assumed supply balance is negative after stocks and other uses.'} Additional supply needed is not an official import requirement or import prediction.`;
}
function initializeRiceOutlook(){
 if(!document.getElementById('riceOutlookYear'))return;
 const keys=['Year','YieldChange','AreaChange','Milling','Demand','OpeningStocks','Reserve','OtherUses','Exports'];
 keys.forEach(key=>{const el=document.getElementById('riceOutlook'+key);if(el)el.addEventListener('input',updateRiceOutlook)});
 document.getElementById('riceOutlookReset').onclick=()=>{const d=riceOutlookDefaults; const vals={Year:d.targetYear,YieldChange:d.yieldChange,AreaChange:d.areaChange,Milling:d.milling,Demand:d.demand,OpeningStocks:d.openingStocks,Reserve:d.reserve,OtherUses:d.otherUses,Exports:d.exports};Object.entries(vals).forEach(([k,v])=>document.getElementById('riceOutlook'+k).value=v);updateRiceOutlook()};
 document.getElementById('riceOutlookExample').onclick=()=>{const ex={Year:2027,YieldChange:5,AreaChange:0,Milling:63,Demand:17,OpeningStocks:2,Reserve:2,OtherUses:0.5,Exports:0};Object.entries(ex).forEach(([k,v])=>document.getElementById('riceOutlook'+k).value=v);updateRiceOutlook()};
 updateRiceOutlook();
}
