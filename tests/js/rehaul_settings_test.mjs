// Real settings functions, fake DOM and transport. No helper, files, or network writes.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const page = readFileSync(new URL('../../assets/dashboard/index.html', import.meta.url), 'utf8');
const logic = page.slice(page.indexOf('    const SETTINGS_FIELDS'), page.indexOf('    async function postHelper'));
const authLogic = page.slice(page.indexOf('    async function authFetch('), page.indexOf('    function prettyHook('));
const refreshLogic = page.slice(page.indexOf('    async function refreshSettings()'), page.indexOf('    function diagnoseSummary('));
const folderLogic = page.slice(page.indexOf('    async function pickOutputFolder()'), page.indexOf('    async function retryWithLiteMode('));
const discoveryLogic = page.slice(page.indexOf('    const discoveryState ='), page.indexOf('    function renderSources()'));
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r)); };
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };

function setup() {
  const nodes = new Map(), writes = [], storage = new Map();
  class El {
    constructor(id, attrs='') {
      this.id=id; this.value=''; this.checked=false; this.type=/type="([^"]*)"/.exec(attrs)?.[1] || 'text';
      this.min=/min="([^"]*)"/.exec(attrs)?.[1]; this.max=/max="([^"]*)"/.exec(attrs)?.[1];
      this.dataset={}; this.attrs={}; this.events={}; this.textContent=''; this.innerHTML=''; this.children=[];
      const classes=new Set(); this.classList={toggle:(n,on)=>on?classes.add(n):classes.delete(n), contains:n=>classes.has(n)};
    }
    addEventListener(name, fn) { (this.events[name] ||= []).push(fn); }
    setAttribute(k,v) { this.attrs[k]=v; }
    getAttribute(k) { return this.attrs[k] || null; }
    emit(name) { for(const f of this.events[name] || []) f({target:this}); }
    appendChild(el) { this.children.push(el); return el; }
    replaceChildren(...els) { this.children=[...els]; this.textContent=''; }
  }
  for(const m of page.slice(0,page.indexOf('<script>')).matchAll(/<\w+\b([^>]*\bid="([^"]+)"[^>]*)>/g)) nodes.set(m[2],new El(m[2],m[1]));
  for(const m of page.matchAll(/data-setting-retry="([^"]+)"/g)) nodes.get(`${m[1]}SaveRetry`).dataset.settingRetry=m[1];
  const document={ getElementById:id=>nodes.get(id) || null, createElement:tag=>Object.assign(new El(''),{tagName:tag.toUpperCase()}), querySelectorAll:sel=>sel==='[data-setting-retry]'?[...nodes.values()].filter(n=>n.dataset.settingRetry):[] };
  const state={settings:{},token:'fake-token'};
  let handler = async (path,opts) => {
    const body=opts.body?JSON.parse(opts.body):{};
    if(path==='/settings') return {ok:true,settings:{...body}};
    return {ok:true};
  };
  const c=vm.createContext({document,state,els:Object.fromEntries(nodes),console,AbortController,
    window:{setTimeout,clearTimeout,location:{origin:'http://fixture.invalid'}},
    localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    confirm:()=>true,
    authFetch:async (path,opts={})=>{writes.push({path,body:opts.body?JSON.parse(opts.body):null});return handler(path,opts);},
    renderRolePicker:role=>{nodes.get('rolePicker').value=role;},
    renderTopics:topics=>{nodes.get('topicList').value=JSON.stringify(topics);},
    syncWhisperModelOptions:()=>{},reliabilityStatusText:()=>'',renderWritingScreenshots:()=>{},renderAgentSetup:()=>{},renderAutoUoinkStatus:()=>{},renderLibraryMirrorFromSettings:()=>{},
    readTopicEditor:()=>[{name:'Research',keywords:['source']}],
    outputFolderPathFromSettings:()=>state.settings.output_dir_configured,
    renderOutputFolder:path=>{nodes.get('outputFolder').value=path;},
    htmlEscape:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
    prettyHook:type=>String(type).replaceAll('_',' '),
  });
  vm.runInContext(discoveryLogic + logic + refreshLogic + folderLogic,c);
  c.wireSettingsAutosave();
  return {c,nodes,writes,storage,state,setHandler:fn=>{handler=fn;},run:code=>vm.runInContext(code,c),
    useHttp:(status,body)=>{
      c.getToken=async()=>state.token;
      c.fetch=async(path,opts={})=>{
        writes.push({path,body:opts.body?JSON.parse(opts.body):null});
        return {ok:status>=200&&status<300,status,text:async()=>JSON.stringify(body)};
      };
      vm.runInContext(authLogic,c);
    },
    status:id=>nodes.get(`${id}SaveStatus`).textContent,
    change:(id,value)=>{const el=nodes.get(id);if(el.type==='checkbox')el.checked=value;else el.value=String(value);el.emit('input');el.emit('change');},
    flush:async()=>{await tick();await vm.runInContext('settingsWriteQueue',c);await tick();}};
}

const groups = {
  async folder_cancel() {
    const p=setup();
    p.state.settings={output_dir_configured:'C:/Example/Original',clipboard_screenshot_cap:8};
    p.nodes.get('outputFolder').value=p.state.settings.output_dir_configured;
    p.useHttp(200,{ok:false,cancelled:true,error:'No folder selected.',settings:{output_dir_configured:'C:/Example/Old'}});
    await p.c.pickOutputFolder();
    assert.deepEqual(p.writes,[{path:'/settings/output-folder/pick',body:{initial_dir:'C:/Example/Original'}}]);
    assert.equal(p.status('outputFolder'),'No folder selected.');
    assert.equal(p.nodes.get('outputFolder').attrs['aria-invalid'],'false');
    assert.ok(p.nodes.get('outputFolderSaveRetry').classList.contains('hidden'));
    assert.equal(p.run('settingEdit("outputFolder").dirty'),false);
    assert.equal(p.nodes.get('pickOutputFolder').disabled,false);
    assert.equal(p.nodes.get('outputFolder').value,'C:/Example/Original');
    assert.equal(p.state.settings.output_dir_configured,'C:/Example/Original','cancel does not adopt the dialog snapshot');
    const versions=p.run('Object.fromEntries([...settingEdits].map(([id,edit])=>[id,edit.version]))');
    p.c.hydrateSettings({settings:{output_dir_configured:'C:/Example/Reloaded'}},versions);
    assert.equal(p.nodes.get('outputFolder').value,'C:/Example/Reloaded','cancel must not block later hydration');
    p.useHttp(200,{ok:false,error:'settings write failed'});
    await p.c.pickOutputFolder();
    assert.equal(p.status('outputFolder'),'Not saved: settings write failed');
    assert.equal(p.nodes.get('outputFolder').attrs['aria-invalid'],'true');
    assert.equal(p.run('settingEdit("outputFolder").dirty'),true);
    assert.ok(!p.nodes.get('outputFolderSaveRetry').classList.contains('hidden'));

    const cancelled=deferred();
    // Restore the in-memory transport for a newer edit while the dialog is open.
    p.c.authFetch=()=>cancelled.promise;
    const choosing=p.c.pickOutputFolder();await tick();
    p.nodes.get('outputFolder').value='C:/Example/New draft';p.nodes.get('outputFolder').emit('input');
    cancelled.reject(Object.assign(new Error('No folder selected.'),{data:{cancelled:true}}));
    await choosing;
    assert.equal(p.nodes.get('outputFolder').value,'C:/Example/New draft');
    assert.match(p.status('outputFolder'),/^Not saved yet/);
    assert.equal(p.run('settingEdit("outputFolder").dirty'),true,'cancel cannot clear a newer draft');
  },
  async reload_races() {
    const p=setup(),saving=deferred();
    for(const fn of ['loadSettingsMcp','loadTasteSettings','loadPlaylistSettings','loadPodcastFeedSettings','loadChannels','loadAllowedSites','loadAgentSetup','loadAIPricing','loadHookCorrections','loadSkillSystemPrompt']) p.c[fn]=async()=>{};
    let stored={clipboard_screenshot_cap:4,hook_type_enabled:false};
    p.c.hydrateSettings({settings:stored},{});
    p.setHandler(async(path,opts)=>{
      assert.equal(path,'/settings');
      if(opts.method==='POST') {
        await saving.promise;
        Object.assign(stored,JSON.parse(opts.body));
      }
      return {ok:true,settings:{...stored}};
    });
    p.change('screenshotCount',8);await tick();
    const reload=p.c.refreshSettings();await tick();
    assert.equal(p.writes.filter(x=>x.body===null).length,0,'reload must wait for pending saves before taking a server snapshot');
    // Another queued write after Reload must also survive its response.
    p.change('hookTypeToggle',true);
    saving.resolve();await p.flush();await reload;
    assert.equal(p.nodes.get('screenshotCount').value,'8');
    assert.equal(p.state.settings.clipboard_screenshot_cap,8);
    assert.equal(p.status('screenshotCount'),'Saved');
    assert.equal(p.nodes.get('hookTypeToggle').checked,true);
    assert.equal(p.state.settings.hook_type_enabled,true);

    const reading=deferred();
    p.setHandler(async(path,opts)=>opts.method==='POST'
      ? {ok:true,settings:JSON.parse(opts.body)} : reading.promise);
    const slowReload=p.c.refreshSettings();await tick();
    p.change('screenshotCount',11);await p.flush();
    reading.resolve({ok:true,settings:{clipboard_screenshot_cap:8,hook_type_enabled:true}});
    await slowReload;
    assert.equal(p.nodes.get('screenshotCount').value,'11','an edit made after GET started survives its stale body');
    assert.equal(p.state.settings.clipboard_screenshot_cap,11);
    assert.equal(p.status('screenshotCount'),'Saved');

    const folderRead=deferred();
    p.state.settings.output_dir_configured='C:/Example/Old';
    p.state.settings.output_dir_pending_restart=false;
    p.setHandler(async(path,opts)=>opts.method==='POST'
      ? {ok:true,settings:{output_dir_configured:'C:/Example/New',output_dir_pending_restart:true}} : folderRead.promise);
    const folderReload=p.c.refreshSettings();await tick();
    p.change('outputFolder','C:/Example/New');await p.flush();
    folderRead.resolve({ok:true,settings:{output_dir_configured:'C:/Example/Old',output_dir_pending_restart:false}});
    await folderReload;
    assert.equal(p.nodes.get('outputFolder').value,'C:/Example/New');
    assert.equal(p.state.settings.output_dir_configured,'C:/Example/New','preserve the acknowledged folder field used by other actions');
    assert.equal(p.state.settings.output_dir_pending_restart,true);
    assert.equal(p.status('outputFolder'),'Saved');
  },
  async mirror_errors() {
    for(const [id,path] of [['tasteHooks','/memory/taste'],['tasteFormats','/memory/taste'],['tasteAvoid','/memory/taste'],['tasteUser','/memory/user']]) {
      const p=setup(),content='Keep this draft';
      p.useHttp(200,{ok:true,mirror:{ok:false,error:'Vault denied <write> sk-ant-fixture-secret'}});
      p.change(id,content);await p.flush();
      const original=p.writes.at(-1);
      assert.equal(original.path,path);
      assert.equal(p.status(id),'Saved locally; Obsidian copy failed: Vault denied <write> [redacted key]');
      assert.equal(p.nodes.get(id).attrs['aria-invalid'],'true');
      assert.equal(p.nodes.get(id).value,content);
      assert.equal(p.run(`settingEdit("${id}").dirty`),true);
      assert.ok(!p.nodes.get(`${id}SaveRetry`).classList.contains('hidden'));
      p.useHttp(200,{ok:true,content:'A stale read'});
      await p.c.loadTasteSettings();
      assert.equal(p.nodes.get(id).value,content,'reload preserves a draft whose mirror still needs retry');
      assert.match(p.status(id),/Obsidian copy failed/);
      p.useHttp(200,{ok:true,mirror:{ok:true,path:'C:/Example/Vault/Uoink/memory.md'}});
      p.nodes.get(`${id}SaveRetry`).emit('click');await p.flush();
      assert.deepEqual(p.writes.at(-1),original,'retry keeps the existing API payload');
      assert.equal(p.status(id),'Saved');
      assert.equal(p.nodes.get(id).attrs['aria-invalid'],'false');
      assert.equal(p.run(`settingEdit("${id}").dirty`),false);
      assert.ok(p.nodes.get(`${id}SaveRetry`).classList.contains('hidden'));
    }
  },
  async taste_reload() {
    const p=setup(),saving=deferred();let content='Old notes';
    p.setHandler(async(path,opts)=>{
      if(opts.method==='POST') {await saving.promise;content=JSON.parse(opts.body).content;return {ok:true,mirror:{ok:true}};}
      return {ok:true,content,anchors:{}};
    });
    p.change('tasteUser','Fresh notes');await tick();
    const reload=p.c.loadTasteSettings();await tick();
    assert.equal(p.writes.filter(x=>x.path==='/memory/user'&&x.body===null).length,0,'memory reload waits for saves too');
    saving.resolve();await p.flush();await reload;
    assert.equal(p.nodes.get('tasteUser').value,'Fresh notes');
    assert.equal(p.status('tasteUser'),'Saved');
  },
  async screenshot() {
    const p=setup(), rendered=[];
    p.c.renderWritingScreenshots=()=>rendered.push(p.state.settings.writing_show_screenshot_picker);
    assert.equal(p.nodes.get('writingScreenshotPickerToggle').events.change.length,1);
    for(const enabled of [false,true]) {
      p.change('writingScreenshotPickerToggle',enabled);await p.flush();
      assert.deepEqual(p.writes.at(-1),{path:'/settings',body:{writing_show_screenshot_picker:enabled}});
      assert.equal(p.state.settings.writing_show_screenshot_picker,enabled);
      assert.equal(p.status('writingScreenshotPickerToggle'),'Saved');
    }
    assert.deepEqual(rendered,[false,true],'composer follows acknowledged settings');
    p.setHandler(()=>{throw new Error('disk is full');});
    p.change('writingScreenshotPickerToggle',false);await p.flush();
    assert.equal(p.status('writingScreenshotPickerToggle'),'Not saved: disk is full');
    assert.equal(p.state.settings.writing_show_screenshot_picker,true,'failed save preserves confirmed state');
    assert.equal(p.nodes.get('writingScreenshotPickerToggle').checked,false,'failed edit is available to retry');
    p.setHandler(async()=>({ok:true,settings:{writing_show_screenshot_picker:false}}));
    p.nodes.get('writingScreenshotPickerToggleSaveRetry').emit('click');await p.flush();
    assert.equal(p.status('writingScreenshotPickerToggle'),'Saved');
    assert.deepEqual(rendered,[false,true,false]);
  },
  async wiring() {
    const p=setup();
    assert.equal(p.writes.length,0,'opening settings never writes defaults');
    const ids=p.run('Object.keys(SETTINGS_FIELDS)');
    for(const id of ids) {
      assert.equal(p.nodes.get(id).events.change.length,1,id);
      assert.ok(p.nodes.has(`${id}SaveStatus`),id);
    }
    for(const [id,field] of [['commentIntelligenceToggle','comment_intelligence_enabled'],['hookTypeToggle','hook_type_enabled'],['smartScreenshotPickerToggle','smart_screenshot_picker_enabled'],['claimVerificationToggle','claim_verification_enabled'],['notificationsEnabled','notifications_enabled']]) {
      p.change(id,true); await p.flush();
      assert.deepEqual(p.writes.at(-1),{path:'/settings',body:{[field]:true}});
      assert.equal(p.status(id),'Saved');
    }
  },
  async save() {
    const p=setup();
    p.change('screenshotCount',0); await p.flush();
    assert.deepEqual(p.writes[0].body,{clipboard_screenshot_cap:0});
    p.change('screenshotCount',12); await p.flush();
    assert.equal(p.writes.at(-1).body.clipboard_screenshot_cap,12);
    for(const invalid of ['',-1,13,1.5,'bad']) { const n=p.writes.length;p.change('screenshotCount',invalid);await p.flush();assert.equal(p.writes.length,n);assert.match(p.status('screenshotCount'),/^Not saved:/); }
    p.change('whisperModel','large-v3-turbo'); await p.flush();
    assert.deepEqual(p.writes.at(-1).body,{whisper_model:'large-v3-turbo'});
    p.nodes.get('topicList').emit('change'); await p.flush();
    assert.deepEqual(p.writes.at(-1).body,{topics:[{name:'Research',keywords:['source']}]});
  },
  async races() {
    const p=setup(),first=deferred();
    p.setHandler(async(path,opts)=>p.writes.length===1?first.promise:{ok:true,settings:JSON.parse(opts.body)});
    p.change('hookTypeToggle',true);await tick();
    p.change('hookTypeToggle',false);p.change('commentIntelligenceToggle',true);await tick();
    assert.equal(p.writes.length,1,'later writes wait');
    first.resolve({ok:true,settings:{hook_type_enabled:true,comment_intelligence_enabled:false}});
    await p.flush();
    assert.deepEqual(p.writes.map(x=>x.body),[{hook_type_enabled:true},{hook_type_enabled:false},{comment_intelligence_enabled:true}]);
    assert.equal(p.nodes.get('hookTypeToggle').checked,false);
    assert.equal(p.status('hookTypeToggle'),'Saved');
    assert.equal(p.state.settings.comment_intelligence_enabled,true);
    const second=deferred();p.setHandler(()=>second.promise);
    p.change('screenshotCount',4);await tick();
    p.nodes.get('screenshotCount').value='9';p.nodes.get('screenshotCount').emit('input');
    second.resolve({ok:true,settings:{clipboard_screenshot_cap:4}});await p.flush();
    assert.equal(p.nodes.get('screenshotCount').value,'9');
    assert.match(p.status('screenshotCount'),/^Not saved yet/);
  },
  async errors() {
    const p=setup();p.setHandler(()=>{throw new Error('disk is full');});
    p.change('hookTypeToggle',true);await p.flush();
    assert.equal(p.nodes.get('hookTypeToggle').checked,true,'failed edits stay visible');
    assert.equal(p.status('hookTypeToggle'),'Not saved: disk is full');
    assert.equal(p.nodes.get('hookTypeToggle').attrs['aria-invalid'],'true');
    p.setHandler(async()=>({ok:true,settings:{hook_type_enabled:true}}));
    p.nodes.get('hookTypeToggleSaveRetry').emit('click');await p.flush();
    assert.equal(p.status('hookTypeToggle'),'Saved');
    p.setHandler(async()=>({ok:true,settings:{}}));
    p.change('defaultEvidenceSources','https://example.test/source');await p.flush();
    assert.match(p.status('defaultEvidenceSources'),/does not support/);
    assert.ok(p.nodes.get('defaultEvidenceSourcesSaveRetry').classList.contains('hidden'));
    p.setHandler(async()=>({ok:true,settings:{hook_type_enabled:true}}));
    p.change('hookTypeToggle',false);await p.flush();assert.match(p.status('hookTypeToggle'),/did not keep/);
    p.setHandler(async()=>({ok:false,error:'validation failed'}));
    p.change('commentIntelligenceToggle',true);await p.flush();assert.match(p.status('commentIntelligenceToggle'),/validation failed/);
    p.c.window.setTimeout=fn=>setTimeout(fn,5);
    p.c.authFetch=(path,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{const e=new Error('abort');e.name='AbortError';reject(e);}));
    p.change('hookTypeToggle',true);await p.flush();assert.match(p.status('hookTypeToggle'),/did not respond/);
    p.c.authFetch=async()=>({ok:true,settings:{hook_type_enabled:true}});
    p.nodes.get('hookTypeToggleSaveRetry').emit('click');await p.flush();assert.equal(p.status('hookTypeToggle'),'Saved','timeout does not wedge later saves');
  },
  async unsupported() {
    const {control,field,value,status,body}=JSON.parse(process.argv[3]);
    const p=setup();p.useHttp(status,body);
    const input=Array.isArray(value)?value.join('\n'):value;
    p.change(control,input);await p.flush();
    assert.deepEqual(p.writes,[{path:'/settings',body:{[field]:value}}]);
    assert.equal(p.status(control),'Not saved: This helper does not support this setting.');
    assert.equal(p.nodes.get(control).attrs['aria-invalid'],'true');
    assert.equal(p.nodes.get(control).type==='checkbox'?p.nodes.get(control).checked:p.nodes.get(control).value,input,'keep the unsaved draft');
    assert.ok(!Object.hasOwn(p.state.settings,field),'never adopt a rejected setting');
    assert.ok(p.nodes.get(`${control}SaveRetry`).classList.contains('hidden'),'unsupported settings cannot be retried');
    p.nodes.get(`${control}SaveRetry`).emit('click');await p.flush();
    assert.equal(p.writes.length,1,'no retry of an unsupported setting');
    assert.equal(p.storage.size,0,'do not promise a later sync');
    p.useHttp(200,{ok:true,settings:{hook_type_enabled:true}});
    p.change('hookTypeToggle',true);await p.flush();
    assert.equal(p.status('hookTypeToggle'),'Saved','other settings still save');
  },
  async http_errors() {
    const p=setup();
    for(const [status,error] of [[400,'hook_type_enabled must be boolean'],[403,'missing or invalid token'],[500,'settings field required']]) {
      p.useHttp(status,{ok:false,error});
      p.change('hookTypeToggle',true);await p.flush();
      assert.equal(p.status('hookTypeToggle'),`Not saved: ${error}`,'other HTTP errors keep the helper reason');
      assert.ok(!p.nodes.get('hookTypeToggleSaveRetry').classList.contains('hidden'));
    }
    p.useHttp(200,{ok:true,settings:{hook_type_enabled:true}});
    p.nodes.get('hookTypeToggleSaveRetry').emit('click');await p.flush();
    assert.equal(p.status('hookTypeToggle'),'Saved');
    p.useHttp(400,{ok:false,error:'settings field required'});
    p.change('tasteAvoid','A draft');await p.flush();
    assert.equal(p.status('tasteAvoid'),'Not saved: settings field required','the unsupported mapping is specific to /settings');
  },
  async hydrate() {
    const p=setup();p.change('screenshotCount',8);await p.flush();
    p.nodes.get('tasteAvoid').value='typing';p.nodes.get('tasteAvoid').emit('input');
    p.nodes.get('anthropicKey').value='new private key';p.nodes.get('anthropicKey').emit('input');
    p.c.hydrateSettings({settings:{clipboard_screenshot_cap:4,comment_intelligence_enabled:true,topics:[],whisper_model:'small'}},{});
    assert.equal(p.nodes.get('screenshotCount').value,'8','late GET cannot reset acknowledged edit');
    assert.equal(p.nodes.get('commentIntelligenceToggle').checked,true);
    assert.equal(p.nodes.get('anthropicKey').value,'new private key');
    assert.equal(p.nodes.get('tasteAvoid').value,'typing');
    assert.equal(p.writes.length,1,'hydration does not save');
  },
  async key() {
    const p=setup(),first=deferred();p.setHandler(()=>first.promise);
    p.change('anthropicKey','sk-ant-fixture-first');await tick();
    p.nodes.get('anthropicKey').value='sk-ant-fixture-new';p.nodes.get('anthropicKey').emit('input');
    first.resolve({ok:true,settings:{anthropic_key_set:true}});await p.flush();
    assert.equal(p.nodes.get('anthropicKey').value,'sk-ant-fixture-new');
    p.setHandler(async()=>({ok:true,settings:{anthropic_key_set:true}}));
    p.nodes.get('anthropicKey').emit('change');await p.flush();assert.equal(p.nodes.get('anthropicKey').value,'');
    assert.equal(p.storage.size,0,'key never stored in browser storage');
    p.c.confirm=()=>false;p.nodes.get('clearKey').emit('click');await p.flush();assert.equal(p.writes.length,2);
    p.c.confirm=()=>true;p.setHandler(async()=>({ok:true,settings:{anthropic_key_set:false}}));p.nodes.get('clearKey').emit('click');await p.flush();assert.deepEqual(p.writes.at(-1).body,{anthropic_key:null});
    p.setHandler(()=>{throw new Error('bad sk-ant-fixture-secret');});p.change('anthropicKey','sk-ant-fixture-secret');await p.flush();assert.ok(!p.status('anthropicKey').includes('sk-ant-'));
  },
  async empty_key() {
    const p=setup();p.state.settings.anthropic_key_set=true;
    p.nodes.get('anthropicKey').emit('blur');await p.flush();
    assert.equal(p.status('anthropicKey'),'','an untouched empty field is not an edit');
    for(const value of ['', '   ']) {
      p.nodes.get('anthropicKey').value=value;p.nodes.get('anthropicKey').emit('input');
      p.nodes.get('anthropicKey').emit('blur');await p.flush();
      assert.equal(p.status('anthropicKey'),'Not saved: enter a key, or choose Remove key to delete the saved key.');
      assert.equal(p.nodes.get('anthropicKey').attrs['aria-invalid'],'true');
      assert.equal(p.writes.length,0,'empty blur must not remove a saved key');
      assert.equal(p.state.settings.anthropic_key_set,true);
      assert.ok(p.nodes.get('anthropicKeySaveRetry').classList.contains('hidden'));
    }
    p.change('anthropicKey','');await p.flush();
    assert.match(p.status('anthropicKey'),/^Not saved:.*Remove key/,'change also validates empty keys');
    const pending=deferred();p.setHandler(()=>pending.promise);
    p.change('anthropicKey','sk-ant-fixture-pending');await tick();
    p.nodes.get('anthropicKey').value='';p.nodes.get('anthropicKey').emit('input');p.nodes.get('anthropicKey').emit('blur');
    pending.resolve({ok:true,settings:{anthropic_key_set:true}});await p.flush();
    assert.match(p.status('anthropicKey'),/^Not saved:.*Remove key/,'older saves cannot hide empty-key validation');
    p.c.confirm=()=>false;p.nodes.get('clearKey').emit('click');await p.flush();assert.equal(p.writes.length,1);
    p.c.confirm=()=>true;p.setHandler(async()=>({ok:true,settings:{anthropic_key_set:false}}));
    p.nodes.get('clearKey').emit('click');await p.flush();
    assert.deepEqual(p.writes.at(-1),{path:'/settings',body:{anthropic_key:null}});
    assert.equal(p.status('anthropicKey'),'Saved');
    assert.equal(p.state.settings.anthropic_key_set,false);
  },
  async interval() {
    const p=setup();assert.equal(p.c.dashboardScreenshotInterval(),30);
    p.change('screenshotInterval',75);assert.equal(p.c.dashboardScreenshotInterval(),75);assert.equal(p.status('screenshotInterval'),'Saved in this browser');
    for(const n of [0,301,5.1,'']) {p.change('screenshotInterval',n);assert.equal(p.c.dashboardScreenshotInterval(),75);assert.match(p.status('screenshotInterval'),/^Not saved:/);}
    assert.equal(p.writes.length,0,'no invented server setting');
    p.c.localStorage.setItem=()=>{throw Error('blocked');};p.change('screenshotInterval',100);assert.match(p.status('screenshotInterval'),/storage is unavailable/);
  },
  async key_test() {
    const p=setup();
    p.setHandler(async()=>({ok:true,valid:false,error:'Key rejected: sk-ant-fixture-secret'}));
    await p.c.testKey();
    assert.deepEqual(p.writes.at(-1),{path:'/settings/test-key',body:{}});
    assert.equal(p.status('anthropicKey'),'Key test failed: Key rejected: [redacted key]');
    assert.equal(p.nodes.get('testKey').disabled,false);
    p.setHandler(async()=>({ok:true,valid:true}));await p.c.testKey();
    assert.equal(p.status('anthropicKey'),'Key test passed.');
    const pending=deferred();p.setHandler(()=>pending.promise);
    const first=p.c.testKey();await tick();const count=p.writes.length;
    await p.c.testKey();assert.equal(p.writes.length,count,'only one key test at a time');
    p.nodes.get('anthropicKey').value='sk-ant-fixture-new';p.nodes.get('anthropicKey').emit('input');
    pending.resolve({ok:true,valid:true});await first;
    assert.match(p.status('anthropicKey'),/^Not saved yet/,'stale validation cannot mark a new key valid');
    await p.c.testKey();assert.equal(p.writes.length,count,'unsaved edits must be saved before testing');
    assert.equal(p.nodes.get('testKey').disabled,false);
  },
  async taste() {
    const p=setup();p.change('tasteAvoid','No hype');await p.flush();assert.deepEqual(p.writes.at(-1),{path:'/memory/taste',body:{section:'avoid',content:'No hype'}});
    p.change('tasteUser','## Channels I admire\nExample');await p.flush();assert.equal(p.writes.at(-1).path,'/memory/user');
    assert.equal(p.c.tasteSection('## Avoid\n\nNo hype\n\n## Performance anchors\nAuto','Avoid'),'No hype');
    assert.equal(p.c.tasteSection('## Avoid\n_no anchors yet_\n','Avoid'),'');
    p.setHandler(async()=>({ok:true,anchors:{best:[{video_id:'one',title:'<img src=x>'}],worst:[]}}));
    p.nodes.get('tasteAnchorId').value='one';p.nodes.get('tasteAnchorType').value='best';await p.c.addTasteAnchor();
    assert.deepEqual(p.writes.at(-1).body,{video_id:'one',anchor_type:'best'});
    assert.ok(p.nodes.get('tasteAnchorList').innerHTML.includes('&lt;img'));
  },
  async anchor_draft() {
    const p=setup();
    p.change('tasteAnchorId','example-capture');p.nodes.get('tasteAnchorId').emit('blur');await p.flush();
    assert.equal(p.writes.length,0,'the draft waits for the Add anchor action');
    assert.equal(p.status('tasteAnchorId'),'Not saved yet. Choose a rating, then select Add anchor.');
    p.nodes.get('tasteAnchorType').value='worst';p.nodes.get('tasteAnchorType').emit('change');
    p.nodes.get('addTasteAnchor').emit('click');await p.flush();
    assert.deepEqual(p.writes,[{path:'/taste/anchors',body:{video_id:'example-capture',anchor_type:'worst'}}]);
    assert.equal(p.status('tasteAnchorId'),'Saved');
    assert.equal(p.nodes.get('tasteAnchorId').value,'');
  },
  async mcp() {
    const links={cursor:'cursor://anysphere.cursor-deeplink/mcp/install?name=uoink&config=fixture',vscode:'vscode:mcp/install?%7B%22name%22%3A%22uoink%22%7D'};
    const p=setup();p.setHandler(async path=>path==='/mcp/v1/config'?{ok:true,install_links:links,http:{url:'http://fixture.invalid/mcp/v1',auth_header:'X-Uoink-Token'}}:{ok:true,mcp_config:{claude_desktop:{mcpServers:{uoink:{command:'python',args:['fixture.py']}}},cursor:{mcpServers:{uoink:{command:'python',args:['fixture.py'],env:{UOINK_MCP_TOOLSET:'core'}}}},raw:'ignored'}});
    await p.c.loadSettingsMcp();
    assert.deepEqual(JSON.parse(p.nodes.get('mcpConfig').value),{mcpServers:{uoink:{command:'python',args:['fixture.py']}}});
    p.nodes.get('mcpClient').value='stdio';p.nodes.get('mcpClient').emit('change');assert.equal(JSON.parse(p.nodes.get('mcpConfig').value).transport,'stdio');
    p.nodes.get('mcpClient').value='cursor';p.nodes.get('mcpClient').emit('change');assert.equal(JSON.parse(p.nodes.get('mcpConfig').value).mcpServers.uoink.env.UOINK_MCP_TOOLSET,'core');
    p.nodes.get('mcpClient').value='vscode';p.nodes.get('mcpClient').emit('change');assert.equal(JSON.parse(p.nodes.get('mcpConfig').value).servers.uoink.type,'stdio');
    p.nodes.get('mcpClient').value='http';p.nodes.get('mcpClient').emit('change');assert.equal(JSON.parse(p.nodes.get('mcpConfig').value).headers['X-Uoink-Token'],'fake-token');
    assert.equal(p.nodes.get('addToCursor').disabled,false);
    assert.equal(p.nodes.get('addToVscode').disabled,false);
    const count=p.writes.length;
    for(const [client,id] of [['cursor','addToCursor'],['vscode','addToVscode']]) {
      p.nodes.get(id).emit('click');
      assert.equal(p.c.window.location.href,links[client]);
      assert.match(p.nodes.get('mcpInstallStatus').textContent,/cannot confirm installation/);
    }
    assert.equal(p.writes.length,count,'clicking install uses the already loaded link without a request');
    p.c.setMcpInstallLinks({cursor:'https://outside.invalid/',vscode:'javascript:alert(1)'});
    assert.equal(p.nodes.get('addToCursor').disabled,true);
    assert.equal(p.nodes.get('addToVscode').disabled,true);
    p.nodes.get('addToCursor').emit('click');
    assert.equal(p.c.window.location.href,links.vscode,'invalid schemes never navigate');
    p.c.setMcpInstallLinks(links);
    const loading=deferred();p.setHandler(()=>loading.promise);
    const reload=p.c.loadSettingsMcp();await tick();
    assert.equal(p.nodes.get('addToCursor').disabled,true,'clear stale links during reload');
    loading.reject(new Error('offline fixture'));await reload;
    assert.equal(p.nodes.get('addToVscode').disabled,true);
    assert.match(p.nodes.get('mcpInstallStatus').textContent,/Could not load/);
  },
};
// Also drives the migrated setup-settings regressions against these real controls.
export { setup, tick, deferred, page, authLogic };
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const group=process.argv[2];assert.ok(groups[group],group);await groups[group]();console.log(`PASS ${group}`);
}
