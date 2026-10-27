from playwright.sync_api import sync_playwright
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
report=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True, executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
 for size in [(1440,900),(900,900),(390,844)]:
  page=browser.new_page(viewport={'width':size[0],'height':size[1]})
  errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8080/',wait_until='domcontentloaded')
  page.wait_for_timeout(1200)
  def sample(label):
   report.append({'viewport':size,'page':label,'title':page.title(),'h1':page.locator('main h1').all_text_contents()[:2], 'overflow':page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2'),'errors':errors[-5:]})
  sample('dashboard')
  for name in ['Generate Estimate','Historical Data','Rice Supply & Sufficiency','Result History','Model & Data','About ANI']:
   try:
    if size[0] < 760: page.locator('.menuBtn').click()
    b=page.locator('.sidebar button').filter(has_text=name).first
    b.click(timeout=3500)
    page.wait_for_timeout(350)
    sample(name)
    if name=='Rice Supply & Sufficiency':
     for tab in ['National Supply Outlook','Productivity & Benchmarks']:
      page.get_by_role('tab',name=tab).click()
      page.wait_for_timeout(200)
      sample(tab)
     page.get_by_role('tab',name='National Supply Outlook').click()
     if page.locator('#riceOutlookExample').count():
      page.locator('#riceOutlookExample').click()
      report.append({'viewport':size,'page':'rice-example','interpretation':page.locator('#riceOutlookInterpretation').inner_text(),'results':page.locator('.riceOutlookResults').all_text_contents()[:1]})
     if page.locator('#riceGuideYear').count():
      page.locator('#riceGuideYear').select_option('2029')
      report.append({'viewport':size,'page':'rice-guided','interpretation':page.locator('#riceGuideInterpretation').inner_text()})
     icons=page.locator('.ricePage .riceTabPanel:not([hidden]) .infoTipTrigger:visible')
     if icons.count():
      icons.first.hover(timeout=4000)
      report.append({'viewport':size,'page':'tooltip','visible':page.locator('.ricePage .infoTipPopup:visible').count()})
   except Exception as ex:
    report.append({'viewport':size,'page':name,'failure':str(ex)[:280]})
  page.close()
 browser.close()
(ROOT/'outputs'/'ani_browser_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for x in report:print(json.dumps(x,ensure_ascii=True)[:420])
