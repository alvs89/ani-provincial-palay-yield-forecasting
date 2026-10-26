/* ANI Stage 2: auditable, deterministic supply outlook scenarios, NOT ML import forecasts. */
const ANI_RICE_OUTLOOK_BASELINE = Object.freeze({year:2025,palayMMT:19.67,areaMHa:4.75,source:'PSA 2025 Palay Situation Report'});
const riceOutlookDefaults = Object.freeze({targetYear:2027,yieldChange:0,areaChange:0,milling:63,demand:'',openingStocks:'',reserve:'',otherUses:0,exports:0});
function riceOutlookPanel(){
 return `<section class="riceOutlook" aria-labelledby="rice-outlook-title">
 <div class="riceSupplyHeading"><div><span class="riceSupplyEyebrow">NATIONAL PLANNING • SCENARIO ANALYSIS</span><h2 id="rice-outlook-title">National Rice Supply Outlook</h2><p>Explore how assumed changes in production and demand affect potential rice supply. This is not an official government import forecast.</p></div><span class="riceSupplyTag">Stage 2 • Scenario</span></div>
 <div class="riceOutlookInfo"><strong>Starting point:</strong> PSA 2025 national palay production: 19.67 million MT; harvested area: 4.75 million ha. Changing the target year does not automatically change the forecast: future values below are <strong>user-specified assumptions</strong>, not XGBoost predictions. ANI's provincial 2025 local records total about 19.58 million MT and require reconciliation before use as a national forecasting baseline.</div>
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
 <details class="riceOutlookMethod"><summary>Calculation method and limitations</summary>
 <div class="riceMethodContent">
 <p class="riceMethodIntro">These formulas explain how the scenario results are calculated. Volume inputs use million metric tons (MMT) of milled rice, unless noted otherwise.</p>
 <div class="riceMethodGrid">
  <div class="riceMethodItem"><h4>1. Palay production</h4><div class="riceMethodFormula" role="math" aria-label="2025 palay production multiplied by yield multiplier multiplied by area multiplier">2025 palay production &times; yield multiplier &times; area multiplier</div><p>Each multiplier equals 1 plus its percentage change divided by 100.</p></div>
  <div class="riceMethodItem"><h4>2. Milled-rice equivalent</h4><div class="riceMethodFormula" role="math" aria-label="Scenario palay production multiplied by milling recovery rate">Scenario palay production &times; milling recovery rate</div><p>Converts estimated palay output into milled rice.</p></div>
  <div class="riceMethodItem"><h4>3. Production coverage</h4><div class="riceMethodFormula" role="math" aria-label="Milled rice divided by annual rice requirement, multiplied by 100 percent"><span class="riceFraction"><span>Milled rice</span><span>Annual rice requirement</span></span><span>&times; 100%</span></div><p>The share of assumed annual demand covered by domestic production.</p></div>
  <div class="riceMethodItem"><h4>4. Supply balance</h4><div class="riceMethodFormula" role="math" aria-label="Milled rice plus opening stocks minus requirement minus other uses and losses minus exports minus desired ending stocks">Milled rice + opening stocks &minus; annual rice requirement &minus; other uses/losses &minus; exports &minus; desired ending stocks</div><p>Shows a surplus or deficit after the entered assumptions.</p></div>
  <div class="riceMethodItem"><h4>5. Additional supply needed</h4><div class="riceMethodFormula" role="math" aria-label="Maximum of zero and negative supply balance">max(0, &minus;supply balance)</div><p>Shows the shortage when the supply balance is negative; otherwise zero.</p></div>
  <div class="riceMethodItem"><h4>6. Required average palay yield</h4><div class="riceMethodFormula" role="math" aria-label="Annual rice requirement divided by harvested area multiplied by milling recovery rate"><span class="riceFraction"><span>Annual rice requirement</span><span>Harvested area &times; milling recovery rate</span></span></div><p>Yield needed for production alone to cover demand, excluding stocks.</p></div>
 </div>
 <div class="riceMethodNote"><strong>Important:</strong> This is an illustrative annual scenario, not a prediction of actual rice imports or PSA's official self-sufficiency ratio. Import decisions also depend on market conditions, stock timing and public policy. Do not add provincial predictions to the national baseline, as that would double-count production.</div>
 <div class="riceMethodSources"><strong>Official references</strong><a href="https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2B__AA__SU/0012B5ESUA0.px" target="_blank" rel="noopener noreferrer">PSA Supply Utilization Accounts</a><a href="https://psa.gov.ph/statistics/technical-notes/167330" target="_blank" rel="noopener noreferrer">PSA methodology</a><a href="https://ricelytics.philrice.gov.ph/rice_industry" target="_blank" rel="noopener noreferrer">PhilRice statistics</a></div>
 </div></details>
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
 document.getElementById('riceOutlookInterpretation').textContent=riceInterpretSupply({year,coverage:r.coverage,balance:r.balance,need:r.need,openingStocks:v.openingStocks,reserve:v.reserve});
}
function initializeRiceOutlook(){
 if(!document.getElementById('riceOutlookYear'))return;
 const keys=['Year','YieldChange','AreaChange','Milling','Demand','OpeningStocks','Reserve','OtherUses','Exports'];
 keys.forEach(key=>{const el=document.getElementById('riceOutlook'+key);if(el)el.addEventListener('input',updateRiceOutlook)});
 document.getElementById('riceOutlookReset').onclick=()=>{const d=riceOutlookDefaults; const vals={Year:d.targetYear,YieldChange:d.yieldChange,AreaChange:d.areaChange,Milling:d.milling,Demand:d.demand,OpeningStocks:d.openingStocks,Reserve:d.reserve,OtherUses:d.otherUses,Exports:d.exports};Object.entries(vals).forEach(([k,v])=>document.getElementById('riceOutlook'+k).value=v);updateRiceOutlook()};
 document.getElementById('riceOutlookExample').onclick=()=>{const ex={Year:2027,YieldChange:5,AreaChange:0,Milling:63,Demand:17,OpeningStocks:2,Reserve:2,OtherUses:0.5,Exports:0};Object.entries(ex).forEach(([k,v])=>document.getElementById('riceOutlook'+k).value=v);updateRiceOutlook()};
 updateRiceOutlook();
}
