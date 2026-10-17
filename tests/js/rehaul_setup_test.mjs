// Real setup and worker scripts with an in-memory DOM, storage and transport.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { EXT, makeEnv, jsonResponse, settle } from './ext_fake_env.mjs';
const html = readFileSync(join(EXT, 'setup.html'), 'utf8');
const dashboard = readFileSync(new URL('../../assets/dashboard/index.html', import.meta.url), 'utf8');
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; };

async function setup(options = {}) {
  const env = makeEnv({...options, fetch: (url, init) => {
    const path = new URL(url).pathname;
    if (options.fetch) return options.fetch(path, init);
    if (path === '/health') return jsonResponse({ok:true});
    if (path === '/diagnose') return jsonResponse({ok:true,checks:[{name:'index_db_writable',status:'ok'}]});
    throw new Error('Unexpected setup request: ' + path);
  }});
  const create = env.document.createElement.bind(env.document);
  env.document.createElement = tag => {
    const el = create(tag); el.attrs = {};
    el.setAttribute = (key,value) => {el.attrs[key] = String(value);};
    el.removeAttribute = key => {delete el.attrs[key];};
    el.getAttribute = key => el.attrs[key] ?? null;
    el.focus = () => {env.document.activeElement = el;};
    el.scrollIntoView = opts => {env.scroll = opts;};
    return el;
  };
  for (const match of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const el = env.document.createElement(match[1]); el.id = match[2];
    el.hidden = /\shidden\b/.test(match[0]);
    el.disabled = /\sdisabled\b/.test(match[0]);
    for (const attr of match[0].matchAll(/([\w-]+)="([^"]*)"/g)) {
      el.setAttribute(attr[1],attr[2]);
      if (attr[1].startsWith('data-')) el.dataset[attr[1].slice(5)] = attr[2];
    }
    env.document.body.appendChild(el);
  }
  env.el = id => env.document.getElementById(id);
  env.events = {};
  env.document.addEventListener = (name,fn) => {env.events[name]=fn;};
  env.ctx.addEventListener = (name,fn) => {env.events[name]=fn;};
  env.chrome.storage.onChanged.addListener = fn => {env.storageChanged=fn;};
  env.chrome.runtime.getPlatformInfo = cb => cb({os:options.os || 'win'});
  env.ctx.location = {search:options.search || '', hash:options.hash || ''};
  env.ctx.matchMedia = () => ({matches:options.reducedMotion !== false});
  env.delays = new Map();
  const timeout = env.ctx.setTimeout;
  env.ctx.setTimeout = (fn,ms) => {const id=timeout(fn);env.delays.set(id,ms);return id;};
  env.fireTimer = async ms => {
    const timer = [...env.timeouts].find(([id])=>env.delays.get(id)===ms);
    assert.ok(timer,`timer ${ms} exists`);
    env.timeouts.delete(timer[0]);timer[1]();await settle();
  };
  env.load('lib/extract.js');env.load('setup.js');await settle();
  return env;
}
async function result(env,row) {
  await env.chrome.storage.session.set({popup_capture_results:[row]});
  env.storageChanged({popup_capture_results:{newValue:[row]}},'session');await settle();
}

const groups = {
  async offline() {
    const env = await setup({fetch:()=>{throw new TypeError('offline');}});
    assert.equal(env.el('status-block').dataset.state,'down');
    assert.match(env.el('status-text').textContent,/offline/);
    assert.match(env.el('status-instructions').textContent,/Windows Start Menu/);
    assert.equal(env.el('uoink-suggested-btn').disabled,true);
    assert.ok(env.fetches.every(url=>url.endsWith('/health')),'no diagnostics storm while offline');
    env.el('uoink-suggested-btn').click();await settle();assert.equal(env.sent.length,0);
    await env.fireTimer(2000);assert.equal(env.fetches.length,2);
    env.el('skip-install').click();await settle();
    assert.equal(env.scroll.behavior,'auto');assert.equal(env.document.activeElement.id,'verify-btn');
  },
  async platforms() {
    for (const [os,word] of [['win','Start Menu'],['mac','Applications'],['linux','Terminal']]) {
      const env=await setup({os,fetch:()=>jsonResponse({ok:false},503)});
      assert.match(env.el('status-instructions').textContent,new RegExp(word));
      assert.equal(env.el('download-btn').hidden,os!=='win');
      assert.equal(env.el('manual-install').hidden,os==='win');
      assert.match(env.el('download-btn').href,/v3\.8\.0\/Uoink-Setup-3\.8\.0\.exe$/);
      if(os!=='win') assert.doesNotMatch(env.el('status-instructions').textContent,/Windows/);
    }
  },
  async navigation_motion() {
    for (const reducedMotion of [true, false]) {
      const env = await setup({reducedMotion});
      env.el('skip-install').click();await settle();
      assert.equal(env.scroll.behavior,'auto','setup navigation never animates, with either motion preference');
      assert.equal(env.document.activeElement.id,'verify-btn');
    }
  },
  async heartbeat() {
    let up=true;
    const env=await setup({fetch:path=>path==='/health'?jsonResponse({ok:up},up?200:503):jsonResponse({ok:true,checks:[]})});
    assert.equal(env.el('uoink-suggested-btn').disabled,false);
    assert.equal(env.el('progress-capture').getAttribute('aria-current'),'step');
    await env.fireTimer(10000);
    assert.equal(env.fetches.filter(url=>url.endsWith('/diagnose')).length,1);
    up=false;await env.fireTimer(10000);
    assert.equal(env.el('uoink-suggested-btn').disabled,true);
    assert.equal(env.el('diagnose').hidden,true);
    up=true;await env.fireTimer(2000);
    assert.equal(env.el('status-text').textContent,'Running on this PC');
    assert.equal(env.el('uoink-suggested-btn').disabled,false);
    assert.equal(env.fetches.filter(url=>url.endsWith('/diagnose')).length,2);
  },
  async visibility() {
    const pending=deferred();let first=true;
    const env=await setup({fetch:path=>path==='/health'&&first?(first=false,pending.promise):jsonResponse({ok:false},503)});
    env.document.hidden=true;env.events.visibilitychange();await settle();
    env.document.hidden=false;env.events.visibilitychange();await settle();
    assert.equal(env.el('status-block').dataset.state,'down');
    pending.resolve(jsonResponse({ok:true}));await settle();
    assert.equal(env.el('status-block').dataset.state,'down','stale health cannot overwrite a resumed probe');
    env.document.hidden=true;env.events.visibilitychange();await settle();
    assert.equal(env.timeouts.size,0,'no probes while backgrounded');
  },
  async diagnostics() {
    const env=await setup();
    assert.match(env.el('diagnose-list').textContent,/Passed · index db writable/);
    assert.equal(env.el('diagnose-list')._all().filter(el=>['A','BUTTON'].includes(el.tagName)).length,0,'pathless diagnostics never make a dead folder control');
    env.runSource('renderDiagnose({checks:[{name:"<img onerror=bad>",status:"error",detail:"<script>bad</script>"}]})');
    assert.match(env.el('diagnose-list').textContent,/Needs attention/);
    assert.equal(env.el('diagnose-list')._all().filter(el=>el.tagName==='SCRIPT').length,0);
    const unavailable=await setup({fetch:path=>path==='/health'?jsonResponse({ok:true}):jsonResponse({},403)});
    assert.equal(unavailable.el('status-block').dataset.state,'running');
    assert.match(unavailable.el('diagnose-list').textContent,/unavailable/);
  },
  async routes() {
    const destinations = [
      ['#mcp-settings', 'agents', 'mcpConfig'],
      ['#skill-settings', 'agents', 'skillSystemPrompt'],
      ['#comment-intelligence', 'ai', 'commentIntelligenceToggle'],
      ['#hook-type-settings', 'ai', 'hookTypeToggle'],
      ['#hook-calibration-settings', 'ai', 'hookCorrectionsList'],
      ['#claim-verification-settings', 'ai', 'claimVerificationToggle'],
      ['#smart-screenshot-settings', 'ai', 'smartScreenshotPickerToggle'],
      ['#taste-anchors-settings', 'ai', 'tasteAnchorList'],
      ['#taste-calibration-onboarding', 'ai', 'tasteUser'],
      ['#creator-tools-settings', 'library', 'channelsList'],
      ['#your-channels-settings', 'library', 'channelsList'],
      ['#helper-status-section', 'app', 'helperStatus'],
    ];
    for(const [hash,section,control] of destinations) {
      const env=await setup({hash});
      assert.equal(env.el('settings-moved').hidden,false);
      assert.ok(env.el('settings-destination').href.endsWith('#settings/'+section));
      const start = dashboard.indexOf(`id="settings-${section}"`);
      const end = dashboard.indexOf('</section>', start);
      assert.ok(start >= 0 && end > start, `${hash} names an existing dashboard section`);
      assert.ok(dashboard.slice(start, end).includes(`id="${control}"`), `${hash} opens the section containing ${control}`);
      assert.deepEqual(env.fetches.map(url=>new URL(url).pathname),['/health','/diagnose']);
      // Existing setup tabs must also update their destination after hash navigation.
      env.ctx.location.hash='#taste-anchors-settings';env.events.hashchange();
      assert.ok(env.el('settings-destination').href.endsWith('#settings/ai'));
    }
    const env=await setup({search:'?source=popup'});
    assert.equal(env.el('settings-moved').hidden,false);
    env.ctx.location.hash='#verify';env.events.hashchange();
    assert.equal(env.el('progress-verify').getAttribute('aria-current'),'step');
  },
  async capture() {
    const env=await setup({onSend:()=>({ok:true,id:'first'})});
    env.el('uoink-suggested-btn').click();await settle();
    assert.equal(env.sent.length,1);
    assert.equal(env.sent[0].type,'popupCapture');
    assert.equal(env.sent[0].job.route,'video');assert.equal(env.sent[0].job.saveOnly,true);
    assert.equal(env.sent[0].job.url,'https://www.youtube.com/watch?v=8rABwKRsec4');
    assert.equal(env.tabsCreated.length,0);assert.equal(env.notifications.length,0);
    assert.match(env.el('capture-status').textContent,/Capture started/);
    await result(env,{id:'other',ok:true,video_id:'wrong'});
    assert.match(env.el('capture-status').textContent,/Capture started/);
    await result(env,{id:'first',ok:true,queued:true});
    assert.match(env.el('capture-status').textContent,/Waiting/);
    await result(env,{id:'first',ok:true,video_id:'abc/a?b'});
    assert.equal(env.el('capture-destination').href,'http://127.0.0.1:5179/dashboard#item/abc%2Fa%3Fb');
    assert.equal(env.el('capture-status').textContent,'Done · saved to your library');
  },
  async capture_failure() {
    let captures=0;
    const env=await setup({onSend:()=>({ok:true,id:++captures===1?'first':'retry'})});
    env.el('uoink-suggested-btn').click();await settle();
    const message='Failed at the transcript step: ERROR: HTTP 429';
    await result(env,{id:'first',ok:false,message,failure_phase:'transcript'});
    assert.equal(env.el('capture-error').textContent,message);
    assert.equal(env.el('capture-error').hidden,false);
    assert.equal(env.el('uoink-suggested-btn').disabled,false);
    env.el('uoink-suggested-btn').click();await settle();
    assert.equal(env.sent.length,2);assert.equal(env.el('capture-error').hidden,true);
    for(const reply of [{ok:false,error:'Queue full'},undefined,{__reject:'Lost worker port'}]) {
      const p=await setup({onSend:()=>reply});
      p.el('uoink-suggested-btn').click();await settle();
      assert.equal(p.el('capture-status').textContent,'Capture could not start');
      assert.equal(p.el('capture-error').hidden,false);assert.equal(p.el('uoink-suggested-btn').disabled,false);
    }
  },
  async capture_races() {
    const ack=deferred();
    const env=await setup({onSend:()=>ack.promise});
    env.el('uoink-suggested-btn').click();env.el('uoink-suggested-btn').click();await settle();
    assert.equal(env.sent.length,1);
    await env.fireTimer(10000);assert.equal(env.el('uoink-suggested-btn').disabled,true,'heartbeat cannot unlock an in-flight capture');
    await result(env,{id:'fast',ok:true,video_id:'saved'});
    ack.resolve({ok:true,id:'fast'});await settle();
    assert.equal(env.el('capture-status').textContent,'Done · saved to your library');
    env.el('uoink-suggested-btn').click();await settle();assert.equal(env.sent.length,1);
  },
  async worker() {
    const store={local:{yoink_token:'fixture'},sync:{},session:{}};
    const completion=deferred();
    const worker=makeEnv({store,fetch:(url)=>{
      const path=new URL(url).pathname;
      if(path==='/health') return jsonResponse({ok:true});
      if(path==='/token') return jsonResponse({token:'fixture'});
      if(path==='/queue/status') return jsonResponse({ok:true,pending_count:0});
      if(path==='/extract') return completion.promise;
      return jsonResponse({ok:true});
    }});
    worker.load('background.js');await settle();
    const env=await setup({store,onSend:msg=>worker.dispatch(msg,{url:worker.chrome.runtime.getURL('setup.html')})});
    env.el('uoink-suggested-btn').click();await settle();
    assert.equal(worker.fetches.filter(url=>url.endsWith('/extract')).length,1);
    assert.equal(worker.notifications.length,0,'no queued notifications');
    env.document.hidden=true;env.events.visibilitychange();
    completion.resolve(jsonResponse({ok:true,video_id:'first-saved',title:'Example',folder:'C:/Fixture/Example'}));await settle();
    assert.equal(store.session.popup_capture_results[0].ok,true);
    assert.equal(worker.notifications.length,1,'completion survives closing/backgrounding setup');
    assert.equal(worker.tabsCreated.length,0,'setup capture saves without opening Claude');
    env.document.hidden=false;env.events.visibilitychange();await settle();
    assert.equal(env.el('capture-destination').href,'http://127.0.0.1:5179/dashboard#item/first-saved');
  },
  async notifications() {
    const env=makeEnv();env.load('background.js');await settle();
    for(const title of ['Uoink queued','Queued','Playlist started','Uoink']) {
      const response=await env.dispatch({type:'notify',title,message:'Queue cleared.'});
      assert.equal(response.ok,true,'suppressed messages still acknowledge');
    }
    await env.dispatch({type:'clearQueue'});await settle();
    assert.equal(env.notifications.length,0);
    for(const title of ['Uoink failed','Uoink Helper offline','Uoink queue full','Clipboard copy blocked','Copy still blocked','Uoink lost track','Uoink still working',"Couldn't capture this X Article",'Uoinked ★','Posts saved','Added to session','Uoink ready','Copied to clipboard']) {
      await env.dispatch({type:'notify',title,message:'Outcome'});
      assert.equal(env.notifications.at(-1).title,title);
    }
    assert.equal(env.notifications.length,13);
  },
};
const group=process.argv[2];assert.ok(groups[group],group);await groups[group]();console.log('PASS '+group);
