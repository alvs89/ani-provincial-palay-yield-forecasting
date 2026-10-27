from playwright.sync_api import sync_playwright
import json, pathlib
out=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
 page=b.new_page(viewport={'width':1366,'height':860})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8080/',wait_until='domcontentloaded')
 page.locator('.sidebar button[data-page="forecast"]').click()
 for name in ['Near-Term Palay Outlook','Long-Term Projection']:
  try:
   page.get_by_text(name,exact=True).first.click(timeout=3000)
   out.append({'flow':name,'body':page.locator('main').inner_text()[:220],'errors':list(errors),'overflow':page.evaluate('document.documentElement.scrollWidth>window.innerWidth+2')})
  except Exception as e:out.append({'flow':name,'error':str(e)[:180]})
 page.locator('.sidebar button[data-page="rice"]').click()
 page.get_by_role('tab',name='National Supply Outlook').click()
 # Verify input rejection and error state without changing the predicted dataset.
 control=page.locator('#riceGuideDemandGrowth');control.fill('1')
 control.press('e');out.append({'flow':'numeric-letters','value':control.input_value(),'rejected':control.input_value()=='1'})
 control.fill('11');out.append({'flow':'numeric-range','aria_invalid':control.get_attribute('aria-invalid'),'feedback':page.locator('.riceFieldError:visible').all_text_contents()[:2]})
 control.fill('1');page.locator('#riceGuideYear').select_option('2030');out.append({'flow':'guided-year','text':page.locator('#riceGuideInterpretation').inner_text()[:250]})
 b.close()
pathlib.Path('outputs/ani_browser_flows.json').write_text(json.dumps(out,indent=2),encoding='utf8')
for entry in out:print(json.dumps(entry))
