/* Reuse ANI's existing infoLabel tooltip system for both national rice tabs. */
const RICE_FIELD_TIPS={
'Assumed palay yield (MT/ha)':'Expected amount of unmilled palay harvested per hectare. MT/ha means metric tons per hectare.',
'Assumed annual harvested area (million ha)':'Total area harvested during the year, including land harvested more than once. One million ha equals one million hectares.',
'Assumed annual rice requirement (million MT)':'Amount of milled rice assumed to be needed during the year. This is entered by the user, not an official future estimate.',
'Assumed milling recovery (%)':'Percentage of harvested palay expected to become milled rice after processing.',
'Target year':'Select 2027-2030 to explore possible rice needs. Results depend on your assumptions, not official forecasts.',
'Annual growth in rice food needs (%)':'Assumed annual percentage increase or decrease in rice available for human food, starting from the 2022 PSA baseline.',
'Change in palay yield versus 2025 (%)':'Assumed percentage difference in palay harvested per hectare compared with the 2025 national level.',
'Change in harvested area versus 2025 (%)':'Assumed percentage change in total annual area harvested compared with 2025.',
'Palay-to-rice recovery (%)':'Share of palay that becomes milled rice; 63% means 63 kg of rice per 100 kg of palay.',
'Scenario target year':'Year assigned to this supply-balance scenario. Changing the year alone does not forecast changes in supply.',
'Yield change from 2025 (%)':'Assumed percentage change in average yield relative to 2025; it is not an XGBoost forecast.',
'Harvested-area change from 2025 (%)':'Assumed percentage change in annual harvested area relative to 2025.',
'Milling recovery (%)':'Portion of palay converted into milled rice, entered as a percentage.',
'Target-year rice requirement (MMT)':'Assumed annual milled-rice need, expressed in million metric tons. Do not include the same uses again under losses.',
'Opening rice stocks (MMT)':'Milled rice assumed to be in storage at the start of the selected year.',
'Desired ending rice stocks (MMT)':'Milled rice planned to remain in storage at the end of the year.',
'Other uses/losses (MMT)':'Additional rice uses and losses not already included in the annual requirement.',
'Rice exports (MMT)':'Amount of milled rice assumed to leave the country during the selected year.',
'2025 national palay yield':'Actual average Philippine palay harvested per hectare in 2025, reported by PSA.',
'2025 palay production':'Total unmilled palay produced in the Philippines during 2025.',
'2025 harvested area':'Total Philippine palay area harvested in 2025; land with multiple harvests can be counted more than once.',
'2025 rice self-sufficiency':'Published share of domestic rice production in the national rice-supply measure; not the calculator coverage rate.',
'Government yield aspiration':'Historical DA rice-productivity objective for particular programs and areas, not a universal yield threshold.',
'Masagana rice sufficiency goal':'DA program target for the share of Philippine rice supply provided by domestic production by 2028.',
'2022 total rice supply':'Historical total rice available in the 2022 supply account, including domestic output and imports.',
'2022 total rice utilization':'Historical total rice used for food and other purposes in the 2022 supply account.',
'Implied palay production':'Calculated total unmilled palay: assumed yield multiplied by harvested area.',
'Implied milled-rice equivalent':'Calculated rice after milling: palay production multiplied by the recovery rate.',
'Domestic production coverage':'Calculated percentage of an assumed rice requirement supplied by domestic milled rice.',
'Indicative production gap':'Calculated shortfall between assumed rice requirement and domestic output, excluding stocks and other uses.',
'Required national average yield':'Calculated palay tons per hectare needed to meet the entered requirement using the assumed area and recovery.',
'Projected food availability needed':'Estimated future food-use rice amount from a 2022 PSA baseline and a user-entered annual growth rate.',
'Scenario domestic milled rice':'Rice output implied by assumed yield change, harvested-area change and milling recovery.',
'Domestic food-needs coverage':'Share of the estimated rice food needs supplied by domestic production in this scenario.',
'Food-only production gap':'Amount by which estimated food needs exceed scenario domestic output; not the amount to import.',
'Scenario palay production':'Estimated unmilled palay output based on assumed 2025-relative changes in yield and harvested area.',
'Milled-rice equivalent':'Expected milled rice produced from scenario palay after applying the recovery rate.',
'Production coverage':'Percent of the entered annual rice requirement that scenario domestic output could meet.',
'Indicative supply balance':'Milled rice plus opening stocks, less demand, other uses, exports and desired ending stocks.',
'Additional supply needed':'Positive shortage when the scenario supply balance is negative; not an official import recommendation.',
'Demand-equivalent required yield':'Palay yield needed to cover the specified rice requirement through domestic production alone.',
'2025 full-year palay production':'PSA-reported national production of unmilled palay for the whole year 2025.',
'2026 first-half palay production':'Reported palay harvested from January through June 2026; not a full-year total.',
'September 2026 rice imports':'Rice import inflows reported for September 2026 alone, not annual imports.',
'September 2026 rice stocks':'Rice held in inventory as of the reported September 2026 reference date.',
'2022 domestic milled rice':'Domestic rice output after milling in the historical PSA 2022 supply account.',
'2022 rice available for human food':'PSA net food disposable amount in 2022; it is not directly measured household consumption.',
'2022 rice imports':'Rice brought into the Philippines during 2022 in the official historical supply account.'
};
function riceAttachTooltips(){
 if(typeof infoLabel!=='function'||typeof INFO_TIPS==='undefined')return;
 Object.assign(INFO_TIPS,RICE_FIELD_TIPS);
 const root=document.querySelector('.ricePage');if(!root)return;
 const selectors=['.riceScenarioInputs label','.riceGuidedGrid label','.riceSupplyStat > span','.riceGuidanceFacts small','.riceScenarioResults > div > span','.riceGuidedResults > div > span'];
 for(const sel of selectors){
  root.querySelectorAll(sel).forEach(el=>{
   if(el.dataset.riceExplained==='true')return;
   const node=Array.from(el.childNodes).find(n=>n.nodeType===3&&n.textContent.trim());
   if(!node)return;
   const label=node.textContent.trim();
   if(!RICE_FIELD_TIPS[label])return;
   node.textContent='';
   el.insertAdjacentHTML('afterbegin',infoLabel(label));
   el.dataset.riceExplained='true';
  });
 }
}

/* Numeric restrictions apply to the rice scenarios only; preserve ordinary ANI forms. */
function riceNumericCandidate(value,allowNegative){
 const pattern=allowNegative?/^-?\d*(?:\.\d*)?$/:/^\d*(?:\.\d*)?$/;
 return pattern.test(value);
}
function riceValueConforms(raw,element){
 if(raw==null||String(raw).trim()==='')return false;
 const n=Number(raw),min=Number(element?.getAttribute('min')??'-Infinity'),max=Number(element?.getAttribute('max')??'Infinity'),step=Number(element?.getAttribute('step')||1);
 return Number.isFinite(n)&&n>=min&&n<=max&&riceNumericCandidate(String(raw).trim(),min<0)&&(!(step>0)||Math.abs(n/step-Math.round(n/step))<=1e-7);
}
function riceInitializeNumericValidation(){
 const root=document.querySelector('.ricePage');if(!root)return;
 root.querySelectorAll('input[type="number"],input[data-rice-number="true"]').forEach(el=>{
  if(el.dataset.riceNumericReady)return;
  el.dataset.riceNumericReady='true';el.dataset.riceNumber='true';
  const min=Number(el.getAttribute('min')),max=Number(el.getAttribute('max'));
  const allowNegative=min<0;
  const step=Number(el.getAttribute('step')||1);
  // text + decimal keypad avoids browser-specific acceptance of e/E and plus signs.
  el.type='text';el.setAttribute('inputmode','decimal');el.setAttribute('autocomplete','off');
  const message=document.createElement('small');message.className='riceFieldError';message.setAttribute('role','status');message.hidden=true;el.after(message);
  let lastValid=el.value;
  const feedback=text=>{message.hidden=!text;message.textContent=text;el.setAttribute('aria-invalid',String(Boolean(text)))};
  const validate=()=>{
   const raw=el.value.trim();const num=Number(raw);
   if(!riceNumericCandidate(raw,allowNegative)){feedback('Only numeric values are accepted.');return}
   if(raw!==''&&raw!=='-'&&raw!=='.'&&raw!=='-.'){
    if(num<min||num>max){feedback(`Enter a number between ${min} and ${max}.`);return}
    if(step>0 && Math.abs(num/step-Math.round(num/step))>1e-7){feedback(`Use increments of ${step}.`);return}
   }
   feedback('');
  };
  const proposed=(insertion)=>el.value.slice(0,el.selectionStart??el.value.length)+insertion+el.value.slice(el.selectionEnd??el.value.length);
  el.addEventListener('beforeinput',event=>{
   if(event.isComposing||!event.inputType?.startsWith('insert')||event.data==null)return;
   if(!riceNumericCandidate(proposed(event.data),allowNegative)){event.preventDefault();feedback(allowNegative?'Enter digits, a decimal point, or a leading minus sign.':'Enter digits and an optional decimal point only.')}
  });
  el.addEventListener('keydown',event=>{
   if(event.ctrlKey||event.metaKey||event.altKey||event.key.length!==1)return;
   if(!riceNumericCandidate(proposed(event.key),allowNegative)){event.preventDefault();feedback(allowNegative?'Enter digits, a decimal point, or a leading minus sign.':'Enter digits and an optional decimal point only.')}
  });
  el.addEventListener('paste',event=>{
   const pasted=event.clipboardData?.getData('text')??'';
   if(!riceNumericCandidate(proposed(pasted),allowNegative)){event.preventDefault();feedback('Only numeric values are accepted.')}
  });
  el.addEventListener('input',()=>{
   if(!riceNumericCandidate(el.value,allowNegative)){el.value=lastValid;feedback('Only numeric values are accepted.');return}
   lastValid=el.value;validate();
  });
  el.addEventListener('blur',validate);
  validate();
 });
}
