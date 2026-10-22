// Execute the shipped semantic settings code with local, deterministic I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(require('node:path').join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const code = page.slice(page.indexOf('    let semanticState ='), page.indexOf('    function wireSettingsAutosave()'));
function env() {
  const elements = new Map();
  for (const match of page.matchAll(/<[^>]+\bid="(semantic[^"]+)"[^>]*>/g)) {
    const classes = new Set();
    elements.set(match[1], { checked: /\schecked\b/.test(match[0]), disabled: /\sdisabled\b/.test(match[0]),
      textContent: '', attributes: {}, listeners: {}, classList: {toggle: (name, on) => on ? classes.add(name) : classes.delete(name)},
      addEventListener(name, fn) { this.listeners[name] = fn; }, removeAttribute(name) { delete this.attributes[name]; },
      showModal() { this.open = true; } });
  }
  const calls = [], timers = [];
  let current = {ok:true,state:'not_installed',enabled:false,terms_version:'current-fixture',acceptance:null};
  let handler = async (path, options) => {
    if (path === '/search/terms') { current = {...current, acceptance:{accepted:true}}; return current; }
    if (path === '/search/model' && options.method === 'POST') current = {...current, enabled:true,state:'downloading',bytes:100,download_bytes:330000000};
    if (path === '/search/model' && options.method === 'DELETE') current = {ok:true,state:'not_installed',enabled:false,acceptance:null,terms_version:'current-fixture'};
    if (path === '/search/pause') current = {...current,paused:true};
    if (path === '/search/start') current = {...current,paused:false,state:'indexing',done:3,total:9};
    return current;
  };
  const invoke = async (path, options={}) => { assert(path.startsWith('/search/')); calls.push({path,...options}); return handler(path,options); };
  const context = vm.createContext({document:{getElementById:id=>elements.get(id),querySelectorAll:()=>[]},
    window:{clearTimeout:()=>{},setTimeout:(fn)=>timers.push(fn)}, state:{activeTab:'settings'},
    readSettingsResource:invoke, settingsRequest:invoke, settingError:err=>err.message, confirm:()=>true});
  vm.runInContext(code,context);
  const run = value => vm.runInContext(value,context);
  run('bindSemanticSearch()');
  return {run, calls, timers, el:id=>elements.get(id), setHandler:fn=>handler=fn};
}
(async () => {
  const e = env();
  assert.equal(e.el('semanticAccept').checked,false);
  await e.run('loadSemanticStatus()');
  assert.equal(e.el('semanticDownload').disabled,true);
  assert.equal(e.calls.length,1); // status never downloads or accepts
  e.el('semanticAccept').checked=true;
  e.run('renderSemanticStatus()');
  assert.equal(e.el('semanticDownload').disabled,false);
  await e.run('semanticAction("download")');
  assert.deepEqual(e.calls.slice(1,3).map(c=>c.path),['/search/terms','/search/model']);
  assert.deepEqual(JSON.parse(e.calls[1].body),{accepted:true,terms_version:'current-fixture'});
  assert.match(e.el('semanticStatus').textContent,/Downloading/);
  assert.equal(e.el('semanticProgress').max,330000000);
  assert.equal(e.timers.length,1);
  await e.run('semanticAction("pause")');
  assert.match(e.el('semanticStatus').textContent,/Paused/);
  await e.run('semanticAction("start")');
  assert.match(e.el('semanticStatus').textContent,/3 of 9/);
  await e.run('semanticAction("remove")');
  assert.equal(e.el('semanticAccept').checked,false);
  assert.equal(e.el('semanticDownload').disabled,true);
  assert(e.calls.some(c=>c.path==='/search/model' && c.method==='DELETE'));
  const failure = env();
  await failure.run('loadSemanticStatus()');
  failure.el('semanticAccept').checked=true;
  failure.setHandler(async () => { throw Error('terms not accepted'); });
  await failure.run('semanticAction("download")');
  assert(!failure.calls.some(c=>c.path==='/search/model'));
  assert.match(failure.el('semanticStatus').textContent,/terms not accepted/);
  const stale = env();
  let release;
  stale.setHandler(() => new Promise(resolve => {release=resolve;}));
  const first = stale.run('loadSemanticStatus()');
  stale.setHandler(async () => ({state:'ready',enabled:true,acceptance:{accepted:true},done:9,total:9}));
  await stale.run('loadSemanticStatus()');
  release({state:'indexing',done:0,total:9});
  await first;
  assert.match(stale.el('semanticStatus').textContent,/Ready/);
  console.log('PASS semantic settings: consent, progress, pause, resume, remove, failure, stale status');
})().catch(error => { console.error(error); process.exitCode=1; });
