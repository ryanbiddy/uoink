// Setup settings moved to dashboard Settings. Exercise the actual destination
// DOM, change handlers, save queue, hydration and authenticated transport.
// Section Save buttons became change events. Failed drafts now have an explicit
// Retry save beside each control; no implicit cross-field replay or key storage.
// Retains the original seven regression groups without a frozen legacy UI.
import assert from 'node:assert/strict';
import { setup, tick, deferred, page, authLogic } from './rehaul_settings_test.mjs';

let checks = 0;
async function scenario(name, fn) { await fn(); checks++; console.log('ok: ' + name); }
const base = {
  hook_type_enabled: false, comment_intelligence_enabled: false,
  smart_screenshot_picker_enabled: false, clipboard_screenshot_cap: 4,
  claim_verification_enabled: false, obsidian_vault_path: '', anthropic_key_set: true,
};
const fields = {
  hookTypeToggle: 'hook_type_enabled', commentIntelligenceToggle: 'comment_intelligence_enabled',
  smartScreenshotPickerToggle: 'smart_screenshot_picker_enabled', screenshotCount: 'clipboard_screenshot_cap',
  claimVerificationToggle: 'claim_verification_enabled', obsidianVaultPath: 'obsidian_vault_path',
  mirrorScriptsToggle: 'mirror_scripts_to_obsidian', defaultEvidenceSources: 'default_evidence_sources',
};
const response = (body, status = 200) => ({ok: status < 400, status, text: async () => JSON.stringify(body)});

async function fixture({settings = {}, onPost, onGet, boot = true} = {}) {
  const p = setup();
  p.server = {...base, ...settings}; p.posts = []; p.gets = []; p.timers = new Map();
  let timerId = 0;
  p.c.window.setTimeout = (fn, ms) => {const id = ++timerId; p.timers.set(id, {fn, ms}); return id;};
  p.c.window.clearTimeout = id => p.timers.delete(id);
  p.expire = async () => {
    assert.ok(p.timers.size > 0);
    for (const [id, timer] of [...p.timers]) {
      assert.ok(timer.ms > 0 && timer.ms <= 60000, 'bounded request timeout');
      p.timers.delete(id); timer.fn();
    }
    await tick();
  };
  p.echo = () => response({ok:true, settings:{...p.server}});
  p.store = body => {
    for (const key of Object.keys(base)) if (Object.hasOwn(body, key)) {
      p.server[key] = key === 'obsidian_vault_path' ? body[key].replace(/[\\/]+$/, '') : body[key];
    }
    if (Object.hasOwn(body, 'anthropic_key')) p.server.anthropic_key_set = Boolean(body.anthropic_key);
    return p.echo();
  };
  p.onPost = onPost || (body => p.store(body)); p.onGet = onGet || (() => p.echo());
  p.c.getToken = async () => 'fixture-token';
  p.c.fetch = (path, opts = {}) => {
    assert.equal(path, '/settings', 'only stubbed transport');
    assert.equal(opts.headers['X-Uoink-Token'], 'fixture-token', 'real authFetch sends its token');
    const body = opts.body ? JSON.parse(opts.body) : null;
    (body ? p.posts : p.gets).push(body || path);
    if (body) assert.equal(opts.headers['Content-Type'], 'application/json');
    return new Promise((resolve, reject) => {
      const abort = () => reject(Object.assign(new Error('aborted'), {name:'AbortError'}));
      opts.signal.addEventListener('abort', abort, {once:true});
      if (opts.signal.aborted) {abort(); return;}
      Promise.resolve().then(() => body ? p.onPost(body, p) : p.onGet(p)).then(resolve, reject)
        .finally(() => opts.signal.removeEventListener('abort', abort));
    });
  };
  p.run(authLogic);
  for (const name of ['loadSettingsMcp','loadTasteSettings','loadPlaylistSettings','loadPodcastFeedSettings','loadChannels','loadAllowedSites','loadAgentSetup','loadAIPricing','loadHookCorrections','loadSkillSystemPrompt']) p.c[name] = async () => {};
  p.el = id => {assert.ok(p.nodes.has(id), 'real destination control: ' + id); return p.nodes.get(id);};
  p.type = (id, v) => {const el=p.el(id); if(el.type==='checkbox') el.checked=v; else el.value=String(v); el.emit('input');};
  p.retry = id => p.el(id+'SaveRetry').emit('click');
  if (boot) await p.c.refreshSettings();
  return p;
}
function value(p,id) {const el=p.el(id); return el.type==='checkbox'?el.checked:el.value;}
function status(p,id,text,state) {
  if(text instanceof RegExp) assert.match(p.status(id),text); else assert.equal(p.status(id),text);
  assert.equal(p.el(id+'SaveStatus').dataset.state,state);
  assert.equal(p.el(id).attrs['aria-invalid'],state==='error'?'true':'false');
}
function saved(p,id) {
  status(p,id,'Saved','saved'); assert.equal(p.run(`settingEdit('${id}').dirty`),false);
  assert.ok(p.el(id+'SaveRetry').classList.contains('hidden'));
}
function inSection(id,section) {
  const start=page.indexOf(`id="settings-${section}"`),end=page.indexOf('</section>',start);
  for(const suffix of ['', 'SaveStatus', 'SaveRetry']) {
    const at=page.indexOf(`id="${id}${suffix}"`);
    assert.ok(start>=0&&at>start&&at<end,`${id}${suffix} belongs to ${section}`);
  }
}
function held(p) {
  const queue=[];
  p.onPost=body=>new Promise(resolve=>queue.push({body,answer:error=>resolve(error?response({ok:false,error}):p.store(body))}));
  return {queue,
    async one(error) {assert.ok(queue.length);queue.shift().answer(error);await tick();},
    async all(newestFirst,refuse=()=>null) {
      for(let n=0;queue.length&&n<30;n++) {const req=newestFirst?queue.pop():queue.shift();req.answer(refuse(req.body));await tick();}
      assert.equal(queue.length,0);await p.flush();
    },
  };
}

const groups = {
  async hook_type() {
    await scenario('Hook Type and feedback moved together to AI features',async()=>inSection('hookTypeToggle','ai'));
    await scenario('load reads saved Hook Type without writing defaults',async()=>{
      for(const enabled of [false,true]) {
        const p=await fixture({settings:{hook_type_enabled:enabled}});
        assert.equal(value(p,'hookTypeToggle'),enabled);assert.deepEqual(p.posts,[]);assert.equal(p.timers.size,0);
      }
    });
    await scenario('toggle saves just its field, never an API key being typed',async()=>{
      const p=await fixture();p.type('anthropicKey','sk-ant-fixture-draft');
      for(const enabled of [true,false]) {
        p.change('hookTypeToggle',enabled);await p.flush();assert.deepEqual(p.posts.at(-1),{hook_type_enabled:enabled});
        assert.equal(p.server.hook_type_enabled,enabled);assert.equal(value(p,'hookTypeToggle'),enabled);saved(p,'hookTypeToggle');
        assert.equal(value(p,'anthropicKey'),'sk-ant-fixture-draft');assert.equal(p.run('settingEdit("anthropicKey").dirty'),true);
      }
      assert.equal(p.posts.length,2);
    });
  },
  async screenshot() {
    await scenario('picker and count feedback moved with their controls',async()=>{
      inSection('smartScreenshotPickerToggle','ai');inSection('screenshotCount','capture');
    });
    await scenario('picker saves independently of screenshot count',async()=>{
      const p=await fixture();assert.equal(value(p,'smartScreenshotPickerToggle'),false);
      p.change('smartScreenshotPickerToggle',true);await p.flush();assert.deepEqual(p.posts,[{smart_screenshot_picker_enabled:true}]);
      saved(p,'smartScreenshotPickerToggle');assert.equal(p.server.smart_screenshot_picker_enabled,true);assert.equal(p.status('screenshotCount'),'');
    });
    await scenario('count sends integers and validates the rendered range before saving',async()=>{
      const p=await fixture();assert.equal(value(p,'screenshotCount'),'4');
      for(const count of [7,0,12]) {
        p.change('screenshotCount',count);await p.flush();assert.deepEqual(p.posts.at(-1),{clipboard_screenshot_cap:count});
        assert.equal(p.server.clipboard_screenshot_cap,count);assert.equal(value(p,'screenshotCount'),String(count));saved(p,'screenshotCount');
      }
      for(const invalid of ['40','-1','1.5','','bad']) {
        p.change('screenshotCount',invalid);await p.flush();assert.equal(p.posts.length,3);assert.equal(p.server.clipboard_screenshot_cap,12);
        status(p,'screenshotCount','Not saved: enter a whole number from 0 to 12.','error');assert.equal(value(p,'screenshotCount'),invalid);
      }
      p.change('screenshotCount',8);await p.flush();saved(p,'screenshotCount');
    });
  },
  async failure() {
    for(const failure of ['settings write failed','Failed to fetch']) await scenario(failure+' appears beside the draft with retry',async()=>{
      const p=await fixture();p.onPost=()=>{if(failure==='Failed to fetch')throw new TypeError(failure);return response({ok:false,error:failure});};
      p.change('hookTypeToggle',true);await p.flush();assert.deepEqual(p.posts,[{hook_type_enabled:true}]);
      assert.equal(p.server.hook_type_enabled,false);assert.equal(p.state.settings.hook_type_enabled,false,'confirmed value survives a failed edit');
      assert.equal(value(p,'hookTypeToggle'),true,'new UI keeps the failed draft for retry');status(p,'hookTypeToggle','Not saved: '+failure,'error');
      assert.ok(!p.el('hookTypeToggleSaveRetry').classList.contains('hidden'));
      p.onPost=body=>p.store(body);p.retry('hookTypeToggle');await p.flush();saved(p,'hookTypeToggle');assert.equal(p.server.hook_type_enabled,true);
    });
    for(const omit of [true,false]) await scenario('OK response '+(omit?'omitting':'refusing')+' the value is never Saved',async()=>{
      const p=await fixture();p.onPost=()=>response({ok:true,settings:omit?{}:{...p.server}});
      p.change('hookTypeToggle',true);await p.flush();status(p,'hookTypeToggle',omit?/does not support/:/did not keep/,'error');
      assert.equal(p.el('hookTypeToggleSaveRetry').classList.contains('hidden'),omit);
      assert.equal(p.server.hook_type_enabled,false);assert.equal(p.state.settings.hook_type_enabled,false);
    });
    await scenario('stale failed save cannot undo a newer saved choice',async()=>{
      const p=await fixture(),h=held(p);p.change('hookTypeToggle',true);await tick();p.change('hookTypeToggle',false);await tick();
      assert.equal(p.posts.length,1);await h.one('slow and failed');await h.all(false);
      assert.deepEqual(p.posts,[{hook_type_enabled:true},{hook_type_enabled:false}]);
      assert.equal(value(p,'hookTypeToggle'),false);assert.equal(p.server.hook_type_enabled,false);saved(p,'hookTypeToggle');
    });
  },
  async overlap() {
    for(const newestFirst of [false,true]) {
      for(const [first,a,next,b,refusal] of [
        ['hookTypeToggle',true,'hookTypeToggle',false,null],
        ['commentIntelligenceToggle',true,'hookTypeToggle',true,null],
        ['screenshotCount',7,'smartScreenshotPickerToggle',true,'smart_screenshot_picker_enabled'],
        ['hookTypeToggle',true,'claimVerificationToggle',true,'hook_type_enabled'],
        ['commentIntelligenceToggle',true,'claimVerificationToggle',true,null],
      ]) await scenario(`${first} then ${next}, newest-first=${newestFirst}`,async()=>{
        const p=await fixture(),h=held(p);p.change(first,a);await tick();p.change(next,b);await tick();
        assert.equal(h.queue.length,1,'writes are serialized');status(p,first,'Saving…','saving');status(p,next,'Saving…','saving');
        await h.all(newestFirst,body=>Object.hasOwn(body,refusal)?'write refused':null);
        assert.deepEqual(p.posts,[{[fields[first]]:a},{[fields[next]]:b}]);
        for(const [id,v] of new Map([[first,a],[next,b]])) {
          if(fields[id]===refusal) {status(p,id,'Not saved: write refused','error');assert.equal(p.server[fields[id]],base[fields[id]]);}
          else {saved(p,id);assert.equal(p.server[fields[id]],v);}
          assert.equal(value(p,id),p.el(id).type==='checkbox'?v:String(v));
        }
      });
      await scenario('Hook Type changed before load answers, newest-first='+newestFirst,async()=>{
        const read=deferred(),p=await fixture({boot:false,onGet:()=>read.promise}),h=held(p);
        const loading=p.c.refreshSettings();await tick();p.change('hookTypeToggle',true);await tick();
        assert.equal(p.posts.length,1,'slow GET does not hold writes');if(newestFirst)await h.all(true);
        read.resolve(response({ok:true,settings:{...base}}));await loading;if(!newestFirst)await h.all(false);
        assert.equal(value(p,'hookTypeToggle'),true);assert.equal(p.server.hook_type_enabled,true);saved(p,'hookTypeToggle');
      });
    }
    for(const [id,old,draft] of [['screenshotCount',7,'9'],['obsidianVaultPath','D:/Seven','D:/Nine'],['hookTypeToggle',true,false]]) {
      for(const error of [null,'write failed']) await scenario(`${id} newer typing survives ${error||'success'} and reload`,async()=>{
        const p=await fixture(),h=held(p);p.change(id,old);await tick();p.type(id,draft);await h.one(error);await p.flush();
        assert.equal(value(p,id),draft);status(p,id,/^Not saved yet/,'');await p.c.refreshSettings();assert.equal(value(p,id),draft);
        p.el(id).emit('change');await tick();await h.all(false);saved(p,id);assert.equal(p.server[fields[id]],id==='screenshotCount'?9:draft);
      });
    }
    for(const clear of [false,true]) await scenario('key typing survives outstanding '+(clear?'removal':'save'),async()=>{
      const p=await fixture(),h=held(p);if(clear)p.el('clearKey').emit('click');else p.change('anthropicKey','sk-ant-fixture-first');
      await tick();p.type('anthropicKey','sk-ant-fixture-new');await h.all(false);
      assert.deepEqual(p.posts,[{anthropic_key:clear?null:'sk-ant-fixture-first'}]);assert.equal(p.server.anthropic_key_set,!clear);
      assert.equal(value(p,'anthropicKey'),'sk-ant-fixture-new');status(p,'anthropicKey',/^Not saved yet/,'');assert.equal(p.storage.size,0);
    });
    await scenario('saved vault reloads another tab’s change without writing old path back',async()=>{
      const p=await fixture();p.change('obsidianVaultPath','D:/VaultA');await p.flush();saved(p,'obsidianVaultPath');
      p.server.obsidian_vault_path='D:/VaultB';await p.c.refreshSettings();assert.equal(value(p,'obsidianVaultPath'),'D:/VaultB');
      p.change('claimVerificationToggle',true);await p.flush();assert.deepEqual(p.posts.at(-1),{claim_verification_enabled:true});assert.equal(p.server.obsidian_vault_path,'D:/VaultB');
    });
    await scenario('late hydration cannot replace a newer draft',async()=>{
      const p=await fixture(),reading=deferred();p.onGet=()=>reading.promise;
      const loading=p.c.refreshSettings();await tick();p.type('obsidianVaultPath','D:/Typed');
      reading.resolve(response({ok:true,settings:{...base,obsidian_vault_path:'D:/Older'}}));await loading;
      assert.equal(value(p,'obsidianVaultPath'),'D:/Typed');status(p,'obsidianVaultPath',/^Not saved yet/,'');assert.deepEqual(p.posts,[]);
    });
  },
  async ci_save() {
    await scenario('CI and key have individual autosave feedback in AI features',async()=>{
      inSection('commentIntelligenceToggle','ai');inSection('anthropicKey','ai');const p=await fixture();p.type('anthropicKey','sk-ant-fixture-typed');
      p.change('commentIntelligenceToggle',true);await p.flush();assert.deepEqual(p.posts,[{comment_intelligence_enabled:true}]);saved(p,'commentIntelligenceToggle');
      assert.equal(value(p,'anthropicKey'),'sk-ant-fixture-typed');p.el('anthropicKey').emit('change');await p.flush();
      assert.deepEqual(p.posts[1],{anthropic_key:'sk-ant-fixture-typed'});saved(p,'anthropicKey');assert.equal(value(p,'anthropicKey'),'');assert.equal(p.storage.size,0);
    });
    await scenario('refused CI change shows its real failure beside its draft',async()=>{
      const p=await fixture();p.onPost=()=>response({ok:false,error:'CI refused'});p.change('commentIntelligenceToggle',true);await p.flush();
      status(p,'commentIntelligenceToggle','Not saved: CI refused','error');assert.equal(p.server.comment_intelligence_enabled,false);assert.equal(p.status('anthropicKey'),'');
    });
    await scenario('untouched key blur and reload save nothing',async()=>{
      const p=await fixture();p.el('anthropicKey').emit('blur');await p.flush();await p.c.refreshSettings();assert.deepEqual(p.posts,[]);assert.equal(p.status('anthropicKey'),'');
    });
    for(const newestFirst of [false,true])await scenario('key waits for outstanding CI toggle, newest-first='+newestFirst,async()=>{
      const p=await fixture(),h=held(p);p.change('commentIntelligenceToggle',true);await tick();p.change('anthropicKey','sk-ant-fixture-queued');await tick();assert.equal(p.posts.length,1);
      await h.all(newestFirst);assert.deepEqual(p.posts,[{comment_intelligence_enabled:true},{anthropic_key:'sk-ant-fixture-queued'}]);
      assert.equal(p.server.comment_intelligence_enabled,true);assert.equal(p.server.anthropic_key_set,true);saved(p,'commentIntelligenceToggle');saved(p,'anthropicKey');
    });
  },
  async section_status() {
    for(const [id,v,section] of [['claimVerificationToggle',true,'ai'],['obsidianVaultPath','C:/Vault/','library']]) {
      await scenario(id+' shows Saving then Saved beside its control',async()=>{
        inSection(id,section);const p=await fixture(),h=held(p);p.change(id,v);await tick();assert.deepEqual(p.posts,[{[fields[id]]:v}]);status(p,id,'Saving…','saving');
        await h.all(false);saved(p,id);assert.equal(p.server[fields[id]],id==='obsidianVaultPath'?'C:/Vault':v);assert.equal(value(p,id),v);
        assert.equal(p.status(id==='obsidianVaultPath'?'claimVerificationToggle':'obsidianVaultPath'),'');
      });
      for(const offline of [false,true])await scenario(id+' retains refused draft, offline='+offline,async()=>{
        const p=await fixture();p.onPost=()=>{if(offline)throw new TypeError('Failed to fetch');return response({ok:false,error:'write failed'});};
        p.change(id,v);await p.flush();status(p,id,offline?'Not saved: Failed to fetch':'Not saved: write failed','error');
        assert.equal(value(p,id),v);assert.equal(p.run(`settingEdit('${id}').dirty`),true);await p.c.refreshSettings();assert.equal(value(p,id),v);
        p.onPost=body=>p.store(body);p.retry(id);await p.flush();saved(p,id);assert.equal(p.storage.size,0,'no false later-sync promise');
      });
    }
    for(const [id,v,section] of [['mirrorScriptsToggle',true,'library'],['defaultEvidenceSources','https://example.test/source\n','ai']])await scenario(id+' omitted by helper is never Saved',async()=>{
      inSection(id,section);const p=await fixture();p.change(id,v);await p.flush();
      assert.deepEqual(p.posts,[{[fields[id]]:id==='defaultEvidenceSources'?['https://example.test/source']:true}]);assert.ok(!Object.hasOwn(p.server,fields[id]));
      status(p,id,/does not support/,'error');assert.ok(p.el(id+'SaveRetry').classList.contains('hidden'));assert.equal(value(p,id),v);
      p.retry(id);await p.flush();assert.equal(p.posts.length,1);
    });
    await scenario('supported field save cannot hide sibling unsupported error',async()=>{
      const p=await fixture();p.change('mirrorScriptsToggle',true);await p.flush();p.change('obsidianVaultPath','C:/Vault');await p.flush();
      saved(p,'obsidianVaultPath');status(p,'mirrorScriptsToggle',/does not support/,'error');assert.deepEqual(p.posts,[{mirror_scripts_to_obsidian:true},{obsidian_vault_path:'C:/Vault'}]);
    });
    for(const later of ['obsidianVaultPath','mirrorScriptsToggle'])for(const overlap of [false,true])await scenario('claim failure clears only on its retry, later='+later+', overlap='+overlap,async()=>{
      const p=await fixture(),h=held(p);p.change('claimVerificationToggle',true);await tick();if(!overlap)await h.one('first write refused');
      p.change(later,later==='obsidianVaultPath'?'C:/Vault':true);await tick();if(overlap){assert.equal(h.queue.length,1);await h.one('first write refused');}
      status(p,'claimVerificationToggle','Not saved: first write refused','error');await h.all(false);
      assert.equal(p.server.claim_verification_enabled,false);assert.ok(!Object.hasOwn(p.posts[1],'claim_verification_enabled'));status(p,'claimVerificationToggle','Not saved: first write refused','error');
      if(later==='obsidianVaultPath')saved(p,later);else status(p,later,/does not support/,'error');
      p.retry('claimVerificationToggle');await tick();await h.all(false);saved(p,'claimVerificationToggle');assert.equal(p.server.claim_verification_enabled,true);
    });
    await scenario('refused sibling cannot relabel an already stored claim',async()=>{
      const p=await fixture(),h=held(p);p.change('claimVerificationToggle',true);p.change('obsidianVaultPath','C:/Vault');await tick();
      await h.one();saved(p,'claimVerificationToggle');await h.one('vault refused');saved(p,'claimVerificationToggle');status(p,'obsidianVaultPath','Not saved: vault refused','error');
    });
    await scenario('older success cannot call a newer claim change Saved',async()=>{
      const p=await fixture(),h=held(p);p.change('claimVerificationToggle',true);await tick();p.change('claimVerificationToggle',false);await tick();
      await h.one();status(p,'claimVerificationToggle','Saving…','saving');await h.one('off refused');status(p,'claimVerificationToggle','Not saved: off refused','error');
      assert.equal(p.server.claim_verification_enabled,true);assert.equal(value(p,'claimVerificationToggle'),false);
    });
  },
  async read_timeout() {
    for(const newestFirst of [false,true])await scenario('unanswered GET cannot hold writes, stale answer order='+newestFirst,async()=>{
      const read=deferred(),p=await fixture({boot:false,onGet:()=>read.promise}),h=held(p);const loading=p.c.refreshSettings();await tick();assert.equal(p.gets.length,1);
      const readTimer=[...p.timers.values()][0];assert.ok(readTimer.ms>0&&readTimer.ms<=60000);
      p.change('hookTypeToggle',true);await tick();assert.deepEqual(p.posts,[{hook_type_enabled:true}]);readTimer.fn();await loading;
      assert.match(p.el('settingsLoadStatus').textContent,/Could not load settings:.*did not respond/);
      if(newestFirst)await h.all(true);read.resolve(response({ok:true,settings:{...base}}));await tick();if(!newestFirst)await h.all(false);
      saved(p,'hookTypeToggle');assert.equal(value(p,'hookTypeToggle'),true);assert.equal(p.server.hook_type_enabled,true);
      p.change('claimVerificationToggle',true);await tick();await h.all(false);saved(p,'claimVerificationToggle');assert.equal(p.timers.size,0);
    });
    await scenario('answered read clears its time limit',async()=>{
      const p=await fixture({settings:{comment_intelligence_enabled:true}});assert.equal(p.timers.size,0);assert.equal(value(p,'commentIntelligenceToggle'),true);assert.equal(p.el('settingsLoadStatus').textContent,'');
    });
    for(const first of ['hookTypeToggle','clearKey','claimVerificationToggle'])await scenario('timed-out load cannot send defaults, first='+first,async()=>{
      const read=deferred(),p=await fixture({boot:false,settings:{obsidian_vault_path:'C:/Saved',comment_intelligence_enabled:true},onGet:()=>read.promise});
      const loading=p.c.refreshSettings();await tick();await p.expire();await loading;
      if(first==='clearKey')p.el(first).emit('click');else p.change(first,true);await p.flush();
      assert.deepEqual(p.posts,[first==='clearKey'?{anthropic_key:null}:{[fields[first]]:true}]);assert.equal(p.server.obsidian_vault_path,'C:/Saved');assert.equal(p.server.comment_intelligence_enabled,true);
      p.onGet=()=>p.echo();await p.c.refreshSettings();assert.equal(value(p,'obsidianVaultPath'),'C:/Saved');assert.equal(value(p,'commentIntelligenceToggle'),true);
      read.resolve(response({ok:true,settings:{...base}}));await tick();assert.equal(value(p,'obsidianVaultPath'),'C:/Saved');assert.equal(value(p,'commentIntelligenceToggle'),true);
    });
    for(const supported of [false,true])await scenario('failed draft survives timeout, clears only on acknowledged retry, supported='+supported,async()=>{
      const p=await fixture(),id=supported?'obsidianVaultPath':'mirrorScriptsToggle',draft=supported?'D:/Pending':true;
      p.onPost=()=>response({ok:false,error:'write failed'});p.change(id,draft);await p.flush();
      const read=deferred();p.onGet=()=>read.promise;const loading=p.c.refreshSettings();await tick();await p.expire();await loading;
      p.onPost=body=>p.store(body);p.change('hookTypeToggle',true);await p.flush();assert.equal(value(p,id),draft);status(p,id,'Not saved: write failed','error');
      assert.deepEqual(p.posts.at(-1),{hook_type_enabled:true},'drafts never piggyback');p.retry(id);await p.flush();
      if(supported){saved(p,id);assert.equal(p.server.obsidian_vault_path,draft);}else{status(p,id,/does not support/,'error');assert.equal(p.run(`settingEdit('${id}').dirty`),true);}
      read.resolve(response({ok:true,settings:{...base}}));await tick();assert.equal(value(p,id),draft);
    });
    for(const id of ['obsidianVaultPath','screenshotCount'])for(const focus of [false,true])await scenario('typing after failed read survives save/reload, '+id+', focused='+focus,async()=>{
      const p=await fixture({boot:false,onGet:()=>new Promise(()=>{})});const loading=p.c.refreshSettings();await tick();await p.expire();await loading;
      const h=held(p);p.change('hookTypeToggle',true);await tick();const draft=id==='screenshotCount'?'11':'D:/Typing';p.type(id,draft);if(focus)p.c.document.activeElement=p.el(id);
      await h.all(false);p.onGet=()=>p.echo();await p.c.refreshSettings();assert.equal(value(p,id),draft);status(p,id,/^Not saved yet/,'');
      p.el(id).emit('change');await tick();await h.all(false);saved(p,id);assert.equal(p.server[fields[id]],id==='screenshotCount'?11:draft);
    });
    await scenario('focused unedited field hydrates after failed read',async()=>{
      const p=await fixture({boot:false,settings:{obsidian_vault_path:'C:/Saved'},onGet:()=>new Promise(()=>{})});
      const loading=p.c.refreshSettings();await tick();await p.expire();await loading;p.c.document.activeElement=p.el('obsidianVaultPath');p.onGet=()=>p.echo();await p.c.refreshSettings();
      assert.equal(value(p,'obsidianVaultPath'),'C:/Saved');assert.deepEqual(p.posts,[]);
    });
  },
};
for(const name of process.argv.slice(2).length?process.argv.slice(2):Object.keys(groups)) {
  assert.ok(groups[name],name);const before=checks;await groups[name]();console.log(`group ${name}: ${checks-before} scenarios passed`);
}
