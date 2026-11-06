"""Isolated browser verification; mock future snapshots never touch source files."""
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
report=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    for width in (1440,900,390):
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8080/',wait_until='networkidle')
        page.wait_for_function('typeof aniFreshness !== "undefined" && aniFreshness !== null')
        snapshot=page.request.get('http://127.0.0.1:8000/data-snapshot').json()
        before=page.evaluate('({page:state.page,count:data.length,request:JSON.stringify(state.request),history:JSON.stringify(saved())})')
        changed=copy.deepcopy(snapshot)
        changed['generation']='browser-test-new-release'
        changed['freshness']['generation']=changed['generation']
        changed['historical']['records'].append(copy.deepcopy(changed['historical']['records'][-1]))
        changed['freshness']['sources']['PSA agriculture']['status']='TEST snapshot only'
        page.route('**/data-snapshot',lambda route:route.fulfill(json=changed))
        page.evaluate('aniRefreshAvailableData(true)')
        after=page.evaluate('({page:state.page,count:data.length,request:JSON.stringify(state.request),history:JSON.stringify(saved())})')
        assert after['count']==before['count']+1
        assert all(after[k]==before[k] for k in ('page','request','history'))
        assert page.locator('.topnote').inner_text().find('TEST snapshot only')>=0
        for name in ('forecast','historical','history','model','about'):
            page.evaluate('(name)=>{state.page=name;render()}',name)
            assert page.locator('main').count()==1
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2'),name
        page.evaluate("state.page='forecast';render();")
        page.wait_for_timeout(200)
        selection=page.evaluate('JSON.stringify(state.request)')
        page.locator('#province').focus()
        page.evaluate('aniRefreshAvailableData(true)')
        assert page.evaluate('JSON.stringify(state.request)')==selection
        assert page.evaluate('document.activeElement.id')=='province'
        # Generated output is never recomputed or rewritten by a background refresh.
        page.evaluate("state.current={forecastId:'refresh-test-only',predictedYield:4.25};state.page='result';")
        result=page.evaluate('JSON.stringify(state.current)')
        page.evaluate('aniRefreshAvailableData(true)')
        assert page.evaluate('JSON.stringify(state.current)')==result
        assert page.evaluate('JSON.stringify(saved())')==before['history']
        assert not errors,errors
        report.append({'width':width,'status':'PASS','snapshotUpdate':True,'selectionPreserved':True,'resultPreserved':True,'savedHistoryPreserved':True,'navigationReloads':page.evaluate('performance.getEntriesByType("navigation").length'),'noOverflow':True})
        page.close()
    browser.close()
print(json.dumps(report,indent=2))
