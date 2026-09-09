const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('C:/Users/hello/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = __dirname;
const folder = path.join(root, 'browser-source-01');
fs.mkdirSync(folder);
const record = { started_at: new Date().toISOString(), requested_url: 'https://x.com/NASAAdmin/status/2020984085754282078',
  scope: 'Fresh anonymous isolated Chrome context; returned text-only Source link only', network_failures: [] };
(async () => {
 const browser = await chromium.launch({headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  record.browser_version = browser.version();
  const context = await browser.newContext({viewport: {width:1280,height:900}});
  await context.route('**/*', route => {
   const u = new URL(route.request().url());
   if (u.port === '5179' || u.protocol === 'file:') return route.abort();
   return route.continue();
  });
  const page = await context.newPage();
  page.on('requestfailed', req => record.network_failures.push({url:req.url(), failure:req.failure()}));
  try {
   const response = await page.goto(record.requested_url,{waitUntil:'domcontentloaded',timeout:30000});
   record.http_status = response && response.status();
   await page.locator('body').waitFor({state:'visible',timeout:15000});
   await page.waitForTimeout(4000);
   record.actual_url=page.url(); record.title=await page.title();
   fs.writeFileSync(path.join(folder,'page-snapshot.txt'),await page.locator('body').innerText(),'utf8');
   record.visible_buttons=await page.getByRole('button').evaluateAll(es=>es.map(e=>({label:e.getAttribute('aria-label'),text:e.innerText})).filter(x=>x.label||x.text));
   record.player_state=await page.locator('video').evaluateAll(es=>es.map(e=>({currentTime:e.currentTime,paused:e.paused,ended:e.ended,readyState:e.readyState,error:e.error&&{code:e.error.code,message:e.error.message}})));
   await page.screenshot({path:path.join(folder,'source.png'),fullPage:false});
  } catch(error) { record.error=String(error); await page.screenshot({path:path.join(folder,'source-error.png')}).catch(()=>{}); }
  await context.close();
 } finally { await browser.close(); record.ended_at=new Date().toISOString(); fs.writeFileSync(path.join(folder,'observation.json'),JSON.stringify(record,null,2)+'\n'); }
 console.log(JSON.stringify({folder,actual_url:record.actual_url,title:record.title,player_state:record.player_state,error:record.error}));
})().catch(e=>{console.error(e);process.exitCode=1});
