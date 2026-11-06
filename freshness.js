/* Periodic latest-available data; saved/generated outputs remain immutable snapshots. */
let aniFreshness = null;
let aniRefreshBusy = false;
let aniRefreshTimer;
let aniLastRefresh = 0;
const aniSnapshotPages = new Set(['result','nearterm-result','projection-result']);
const aniOriginalRender = render;

function aniFreshnessText() {
  if (!aniFreshness) return '';
  return Object.entries(aniFreshness.sources || {}).map(([name, source]) =>
    `${name}: ${source.referencePeriod || 'period unavailable'}; released ${source.releaseDate || 'date not provided'}; ${source.status}`
  ).join(' · ');
}

function aniRenderPreservingPosition() {
  const x = window.scrollX, y = window.scrollY;
  const active = document.activeElement;
  const id = active?.id;
  const selection = active && 'selectionStart' in active ? [active.selectionStart,active.selectionEnd] : null;
  const disclosures = [...document.querySelectorAll('details')].map(el=>el.open);
  render();
  document.querySelectorAll('details').forEach((el,i)=>{if(i<disclosures.length)el.open=disclosures[i]});
  const restored = id && document.getElementById(id);
  if (restored) {
    restored.focus({preventScroll:true});
    if (selection && typeof restored.setSelectionRange === 'function' && selection[0] !== null) {
      try { restored.setSelectionRange(...selection); } catch { /* select/number fields */ }
    }
  }
  window.scrollTo(x,y);
}

render = function() {
  aniOriginalRender();
  const topnote = document.querySelector('.topnote');
  if(topnote && aniFreshness) {
    // Existing text container only: no layout, color, control or style changes.
    const source=aniFreshness.sources?.['PSA agriculture'];
    topnote.textContent = aniSnapshotPages.has(state.page)
      ? 'Saved result: source values remain as recorded when this result was generated.'
      : `Latest integrated PSA data: ${source?.referencePeriod||'unavailable'} · Released: ${source?.releaseDate||'date not provided'} · ${source?.status||'Update status unavailable'}.`;
    topnote.title=aniFreshnessText();
  }
};

async function aniRefreshAvailableData(force=false) {
  if(aniRefreshBusy || document.hidden || (!force && Date.now()-aniLastRefresh<60000)) return;
  aniRefreshBusy=true;
  try {
    const response=await fetch(`${API_BASE}/data-snapshot`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
    if(!response.ok)throw new Error('Data refresh unavailable');
    const snapshot=await response.json();
    if(!snapshot.meta || !Array.isArray(snapshot.historical?.records) || !snapshot.projection || !snapshot.freshness)throw new Error('Incomplete data snapshot');
    const changed=snapshot.generation!==aniFreshness?.generation;
    apiMeta=snapshot.meta; projectionMeta=snapshot.projection;
    data=snapshot.historical.records;
    provinceRegion=snapshot.historical.province_regions||snapshot.meta.province_regions||{};
    aniFreshness=snapshot.freshness;
    // Never replace an open result's environmental/report snapshot behind the user.
    if(!aniSnapshotPages.has(state.page)) environmentalSupport=snapshot.environmental;
    if(changed) {
      // Refresh availability without choosing a different target or invoking a prediction.
      const key=`${state.request.province}|${state.request.ecosystem}`;
      const query=new URLSearchParams({province:state.request.province,ecosystem:state.request.ecosystem});
      try {
        const availability=await fetch(`${API_BASE}/forecast-availability?${query}`,{cache:'no-store',signal:AbortSignal.timeout(15000)});
        if(availability.ok && key===`${state.request.province}|${state.request.ecosystem}`) {
          const payload=await availability.json();
          state.availableTargets=payload.availableTargets||[];
          state.nearestTargetAssessment=payload.nearestTargetAssessment||null;
          state.availabilityKey=key;state.availabilityFetchedAt=Date.now();
        }
      } catch { /* existing availability is retained; generating revalidates */ }
    }
    aniLastRefresh=Date.now();
    // A re-render during active typing or processing could lose transient component state.
    const typing=['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName);
    if(!typing && !state.page.includes('processing') && state.page!=='rice' && !aniSnapshotPages.has(state.page))aniRenderPreservingPosition();
  } catch(error) {
    if(aniFreshness) {
      aniFreshness={...aniFreshness,sources:Object.fromEntries(Object.entries(aniFreshness.sources).map(([key,value])=>[key,{...value,status:'Refresh unavailable; retaining last loaded data'}]))};
      const note=document.querySelector('.topnote');
      if(note)note.textContent='Data refresh unavailable. Displaying the last successfully loaded values and reference periods.';
    }
    console.warn('ANI retained its last complete data snapshot:',error.message);
  } finally { aniRefreshBusy=false; }
}

window.addEventListener('online',()=>aniRefreshAvailableData(true));
window.addEventListener('focus',()=>aniRefreshAvailableData());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)aniRefreshAvailableData()});
window.addEventListener('storage',event=>{
  if(event.key===null && ['dashboard','history'].includes(state.page))aniRenderPreservingPosition();
});
aniRefreshTimer=setInterval(()=>aniRefreshAvailableData(),60000);
aniRefreshAvailableData(true);
