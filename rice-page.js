/* Progressive disclosure for national rice context. All calculators remain separate from XGBoost. */
function riceDashboardSummary(){
 return `<section class="riceDashboardSummary" aria-labelledby="riceDashboardHeading">
 <div class="riceDashboardTitle"><div><span class="riceSupplyEyebrow">PHILIPPINE RICE CONTEXT</span><h2 id="riceDashboardHeading">National Rice Productivity</h2><p>A quick comparison of published national indicators and historical government objectives.</p></div><span class="riceSupplyTag">Official references</span></div>
 <div class="riceDashboardMetrics">
  <div><span>National yield • 2025</span><strong>4.14 <small>MT/ha</small></strong><small>PSA reported</small></div>
  <div><span>Yield aspiration • historical</span><strong>5–6 <small>MT/ha</small></strong><small>DA program direction</small></div>
  <div><span>Self-sufficiency • 2025</span><strong>78<small>%</small></strong><small>PhilRice reported</small></div>
  <div><span>Self-sufficiency goal • 2028</span><strong>≥97<small>%</small></strong><small>Masagana program goal</small></div>
 </div>
 <button type="button" class="riceDashboardLink" data-page="rice">Explore rice supply & sufficiency <span aria-hidden="true">→</span></button>
 </section>`;
}
function riceFullPage(){
 return `<div class="ricePage riceTabbedPage">
 ${hero('NATIONAL RICE CONTEXT','Rice Supply & Sufficiency','Explore official Philippine rice benchmarks and assumption-based supply scenarios.')}
 <div class="riceTabsWrap">
 <div class="riceTabList" role="tablist" aria-label="Rice supply analyses">
 <button id="rice-tab-reference" type="button" role="tab" aria-controls="rice-panel-reference" aria-selected="true" tabindex="0" data-rice-tab="reference">Productivity & Benchmarks</button>
 <button id="rice-tab-outlook" type="button" role="tab" aria-controls="rice-panel-outlook" aria-selected="false" tabindex="-1" data-rice-tab="outlook">National Supply Outlook</button>
 </div>
 <section id="rice-panel-reference" class="riceTabPanel" role="tabpanel" aria-labelledby="rice-tab-reference" tabindex="0">
 ${riceSupplyPanel()}
 </section>
 <section id="rice-panel-outlook" class="riceTabPanel" role="tabpanel" aria-labelledby="rice-tab-outlook" tabindex="0" hidden>
 ${riceOutlookPanel()}
 </section>
 </div>
 <p class="ricePageFoot"><strong>Planning context only.</strong> National supply scenarios are hypothetical, not official import forecasts or ANI XGBoost predictions.</p>
 </div>`;
}
function initializeRiceTabs(){
 const tabs=[...document.querySelectorAll('[data-rice-tab]')];if(!tabs.length)return;
 const activate=(name,focus=false)=>{tabs.forEach(tab=>{const selected=tab.dataset.riceTab===name;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;const panel=document.getElementById(tab.getAttribute('aria-controls'));if(panel)panel.hidden=!selected;if(selected&&focus)tab.focus()});};
 tabs.forEach((tab,i)=>{tab.addEventListener('click',()=>activate(tab.dataset.riceTab));tab.addEventListener('keydown',e=>{let next;if(e.key==='ArrowRight')next=(i+1)%tabs.length;else if(e.key==='ArrowLeft')next=(i-1+tabs.length)%tabs.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=tabs.length-1;else return;e.preventDefault();activate(tabs[next].dataset.riceTab,true)})});
 activate('reference');
}
