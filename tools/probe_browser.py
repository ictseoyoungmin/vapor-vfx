"""Optional environment probe only; not an application or shader test."""
import datetime,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
result={'status':'BLOCKED','webgl2':False,'webgpu':False,'scope':'blank-page capability probe, not renderer validation; context exposure does not establish host GPU support','timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  exe=shutil.which('chromium') or shutil.which('chromium-browser')
  browser=p.chromium.launch(executable_path=exe,headless=True,args=['--no-sandbox'])
  page=browser.new_page()
  result.update(page.evaluate('''() => {const c=document.createElement('canvas');const g=c.getContext('webgl2');return {webgl2:!!g,webgpu:!!navigator.gpu,secureContext:isSecureContext,userAgent:navigator.userAgent};}'''))
  result['status']='AVAILABLE' if result['webgl2'] and result['webgpu'] else 'BLOCKED'
  browser.close()
except Exception as e:result['error']=str(e)
path=ROOT/'reports/browser-capability.json';path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
