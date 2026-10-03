const sidebarPaths={
 dashboard:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 forecast:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 historical:'<path d="M3 3v18h18M7 17v-5m5 5V8m5 9V5"/>',
 history:'<path d="M20 7v5h-5M20 12a8 8 0 1 0-2 5"/>',
 model:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7"/>',
 about:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>'
};
const sidebarIcon=name=>`<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${sidebarPaths[name]}</svg>`;
let sidebarCollapsed=false,sidebarOpen=false;
try{sidebarCollapsed=localStorage.getItem('ani-sidebar-design-collapsed')==='true'}catch{}
const sidebarMedia=window.matchMedia('(max-width:760px)');
function aniSidebar(page){const active=['processing','result'].includes(page)?'forecast':page;return `<aside id="ani-sidebar" class="sidebar" aria-label="ANI navigation"><header class="brand"><img src="palay_icon_transparent.png?v=6b437dfd51" class="brandmark" width="52" height="64" alt=""><div class="brand-copy"><b>ANI</b><small>Provincial Palay Yield<br>Forecasting System</small></div><button class="sidebar-close" aria-label="Close navigation">&#215;</button></header><nav aria-label="Main navigation">${nav.map(([p,i,label])=>`<button data-page="${p}" aria-label="${label}" title="${label}" class="${p===active?'active':''}" ${p===active?'aria-current="page"':''}>${sidebarIcon(p)}<span class="nav-label">${label}</span></button>`).join('')}</nav><div class="rice-illustration" aria-hidden="true"><img src="ani-standalone-sidebar-rice.png?v=5e88b6031b" alt=""></div><footer class="sidebar-footer"><button class="sidebar-toggle" aria-controls="ani-sidebar" aria-expanded="${!sidebarCollapsed}" aria-label="${sidebarCollapsed?'Expand':'Collapse'} sidebar"><span class="collapse-symbol" aria-hidden="true">${sidebarCollapsed?'&#187;':'&#171;'}</span><span class="collapse-label">Collapse</span></button></footer></aside><div class="sidebar-overlay" aria-hidden="true"></div>`}
function syncSidebar(){
 const sidebar=document.querySelector('.sidebar');if(!sidebar)return;
 const open=sidebarMedia.matches&&sidebarOpen;
 document.documentElement.classList.toggle('sidebar-collapsed',sidebarCollapsed);
 document.documentElement.classList.toggle('sidebar-open',open);
 sidebar.inert=sidebarMedia.matches&&!open;
 document.querySelector('.content').inert=open;
 sidebar.setAttribute('role',open?'dialog':'complementary');
 if(open)sidebar.setAttribute('aria-modal','true');else sidebar.removeAttribute('aria-modal');
 const toggle=document.querySelector('.sidebar-toggle');
 toggle.setAttribute('aria-expanded',String(!sidebarCollapsed));
 toggle.setAttribute('aria-label',`${sidebarCollapsed?'Expand':'Collapse'} sidebar`);
 toggle.querySelector('.collapse-symbol').textContent=sidebarCollapsed?'\u00bb':'\u00ab';
 document.querySelector('.menuBtn').setAttribute('aria-expanded',String(open));
}
function closeSidebar(focus=true){sidebarOpen=false;syncSidebar();if(focus)document.querySelector('.menuBtn').focus()}
function bindSidebar(){
 syncSidebar();
 document.querySelector('.sidebar-toggle').onclick=()=>{sidebarCollapsed=!sidebarCollapsed;try{localStorage.setItem('ani-sidebar-design-collapsed',String(sidebarCollapsed))}catch{}syncSidebar()};
 document.querySelector('.menuBtn').onclick=()=>{sidebarOpen=true;syncSidebar();document.querySelector('.sidebar-close').focus()};
 document.querySelector('.sidebar-close').onclick=()=>closeSidebar();
 document.querySelector('.sidebar-overlay').onclick=()=>closeSidebar();
}
sidebarMedia.addEventListener('change',()=>{sidebarOpen=false;syncSidebar();if(sidebarMedia.matches)document.querySelector('.menuBtn').focus();else document.querySelector('.sidebar-toggle').focus()});
document.addEventListener('keydown',e=>{
 if(!sidebarOpen||!sidebarMedia.matches)return;
 if(e.key==='Escape'){e.preventDefault();closeSidebar()}
 if(e.key==='Tab'){
  const first=document.querySelector('.sidebar-close'),last=document.querySelector('.sidebar nav button:last-child');
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
 }
});
