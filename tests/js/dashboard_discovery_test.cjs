// Real dashboard code; all network and browser I/O is replaced. No app imports.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const page = fs.readFileSync(path.join(__dirname, "../../assets/dashboard/index.html"), "utf8");
const markup = page.split("<script>")[0];
const script = page.split("<script>")[1].split("    init().catch(")[0];
class Element {
  constructor(id, attrs = "") {
    this.id = id; this.dataset = {}; this.listeners = {}; this.attributes = {};
    for (const field of ["value", "type", "min", "max"]) this[field] = new RegExp(`\\b${field}="([^"]*)"`).exec(attrs)?.[1] || "";
    this.disabled = /\sdisabled\b/.test(attrs); this.checked = /\schecked\b/.test(attrs);
    this.options = []; this.children = []; this.textContent = "";
    const classes = new Set((/class="([^"]+)"/.exec(attrs)?.[1] || "").split(/\s+/));
    this.classList = { contains: n => classes.has(n), add: n => classes.add(n), remove: n => classes.delete(n),
      toggle(n, on = !classes.has(n)) { if (on) classes.add(n); else classes.delete(n); } };
  }
  set innerHTML(value) {
    this._html = value;
    if (this.tag === "select") {
      this.options = [...value.matchAll(/<option\b([^>]*)>/g)].map(m => new Element("", m[1]));
      this.value = this.options[0]?.value || "";
    }
    this.children = [...value.matchAll(/<input\b([^>]*)>/g)].map(m => {
      const el = new Element("", m[1]); el.dataset.discoveryPick = /data-discovery-pick="([^"]*)"/.exec(m[1])?.[1]; return el;
    });
  }
  get innerHTML() { return this._html || ""; }
  querySelectorAll(selector) { return selector === "input" ? this.children : []; }
  querySelector() { return null; }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  async fire(k, event = {}) { for (const fn of this.listeners[k] || []) await fn(event); }
  focus() { this.focused = true; }
}
const plain = value => JSON.parse(JSON.stringify(value));
function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; }
async function settle() { for (let i=0;i<20;i++) await Promise.resolve(); }
function environment() {
  const elements = new Map();
  for (const m of markup.matchAll(/<([a-z]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const el = new Element(m[3], m[2]); el.tag=m[1]; elements.set(el.id, el);
  }
  for (const m of markup.matchAll(/<select\b[^>]*id="([^"]+)"[^>]*>(.*?)<\/select>/gs)) elements.get(m[1]).innerHTML=m[2];
  const el = id => { assert(elements.has(id), `Missing #${id}`); return elements.get(id); };
  const calls = [];
  const settings = { scrapecreators_enabled:false, scrapecreators_agent_calls_enabled:false, scrapecreators_daily_credit_cap:25, scrapecreators_key_set:false, scrapecreators_key_invalid:false };
  const candidates = Array.from({length:12}, (_, i) => ({key:`k${i}`, video_id:`fixture${i}`, caption:`Post ${i}`, platform:"youtube", lift:i === 0 ? null : i, state:"new", in_library:false}));
  const receipt = {ok:true, run_id:"20261017T000000000000Z-fixture", candidates, credits_used:1};
  const plan = {ok:true, needs_confirmation:true, credits_planned:1, credits_today:2, daily_cap:25};
  let minted = 0;
  const defaultHandler = async (url, body) => {
    if (url === "/settings") {
      if (body) for (const [key,value] of Object.entries(body)) {
        if (key === "scrapecreators_key") { settings.scrapecreators_key_set=Boolean(value); settings.scrapecreators_key_invalid=false; }
        else settings[key]=value;
      }
      return {ok:true, settings:{...settings}};
    }
    if (url === "/discovery/intent") return {ok:true, user_intent_token:`intent-${++minted}`};
    if (url === "/discovery/test-key") return body.confirm_credits ? {ok:true, balance:333, credits_used:1} : plan;
    if (url === "/discovery/runs/save") return {ok:true, run:{...receipt, save_failed:false}};
    if (url.startsWith("/discovery/runs/")) return {ok:true, run:receipt};
    if (url === "/mcp/v1/tools/call") {
      const {name, arguments:args}=body.params;
      if (name === "discover_candidates") return {result:{structuredContent:args.confirm_credits ? receipt : plan}};
      if (name === "queue_discovered") return {result:{structuredContent:{ok:true, queued:args.keys.map(key=>({key})), skipped:[], candidates: candidates.map(c=>({...c,state:args.keys.includes(c.key)?"queued":c.state}))}}};
    }
    throw Error(`Unexpected request ${url}`);
  };
  let handler=defaultHandler;
  const context=vm.createContext({document:{getElementById:id=>elements.get(id)||null, querySelector:()=>null, querySelectorAll:()=>[]},
    window:{setTimeout:()=>1,clearTimeout:()=>{}}, localStorage:{getItem:()=>null}, navigator:{}, URL, URLSearchParams, AbortController, console,
    setTimeout:()=>{throw Error("Automatic retry forbidden");}, setInterval:()=>{throw Error("Automatic retry forbidden");},
    fetch:async (url, options) => {
      assert(url.startsWith("/") && !url.startsWith("//"), "third-party request");
      const body=options.body ? JSON.parse(options.body):null; calls.push({url,body});
      const data=await handler(url,body);
      return {ok:true,status:200,text:async()=>JSON.stringify(data)};
    }});
  vm.runInContext(script,context);
  const run=code=>vm.runInContext(code,context);
  run(`state.token="fixture-token"; state.settings=${JSON.stringify(settings)};
    renderAICostEstimate=()=>{}; renderAgentSetup=()=>{}; renderOutputFolder=()=>{};
    renderRolePicker=()=>{}; renderTopics=()=>{}; syncWhisperModelOptions=()=>{};
    renderWritingScreenshots=()=>{}; renderAutoUoinkStatus=()=>{}; renderLibraryMirrorFromSettings=()=>{};
    bindDiscoveryControls();`);
  el("discoveryTerm").value="@fixture";
  return {el,run,calls,settings,receipt,plan,candidates,defaultHandler,setHandler:fn=>{handler=fn;}};
}
async function ready(e) { await e.el("discoveryPlan").fire("click"); assert.equal(e.el("discoveryRun").disabled,false); }
async function picked(e, n) {
  for (let i=0;i<n;i++) { const input=e.el("discoveryResults").children[i]; input.checked=true; await e.el("discoveryResults").fire("change",{target:input}); }
}
const refusal = reason => ({ok:false,error:{code:"invalid_request",message:"The request is invalid.",details:{reason}}});
const scenarios={
  async settings() {
    const e=environment();
    assert.equal(e.el("scrapecreatorsEnabled").disabled,true);
    assert.equal(e.el("scrapecreatorsAgents").checked,false);
    assert.equal(e.el("scrapecreatorsCap").value,"25");
    e.el("scrapecreatorsDisclosure").checked=true; await e.el("scrapecreatorsDisclosure").fire("change");
    assert.equal(e.el("scrapecreatorsEnabled").disabled,true);
    e.el("scrapecreatorsKey").value="fixture-private-key"; await e.el("saveScrapecreatorsKey").fire("click");
    assert.equal(e.el("scrapecreatorsKey").value,""); assert.equal(e.el("scrapecreatorsKeyStatus").textContent,"Key saved.");
    assert.equal(e.el("scrapecreatorsEnabled").disabled,false);
    e.el("scrapecreatorsDisclosure").checked=false; await e.el("scrapecreatorsDisclosure").fire("change");
    e.el("scrapecreatorsEnabled").checked=true; assert.equal(await e.run('saveSettingControl("scrapecreatorsEnabled")'),false);
    assert.equal(e.calls.length,1);
    e.el("scrapecreatorsDisclosure").checked=true; e.el("scrapecreatorsEnabled").checked=true;
    await e.run('saveSettingControl("scrapecreatorsEnabled")');
    e.el("scrapecreatorsCap").value="501"; assert.equal(await e.run('saveSettingControl("scrapecreatorsCap")'),false);
    e.el("scrapecreatorsCap").value="30"; await e.run('saveSettingControl("scrapecreatorsCap")');
    assert.equal(e.settings.scrapecreators_daily_credit_cap,30);
    await e.el("removeScrapecreatorsKey").fire("click"); assert.equal(e.el("scrapecreatorsEnabled").disabled,true);
    assert(!JSON.stringify(e.run("state.settings")).includes("fixture-private-key"));
  },
  async settings_failure() {
    const e=environment(); e.setHandler(async()=>{throw Error("storage unavailable");});
    e.el("scrapecreatorsKey").value="private"; await e.el("saveScrapecreatorsKey").fire("click");
    assert.equal(e.calls.length,1); assert.equal(e.el("scrapecreatorsEnabled").disabled,true);
    assert.match(e.el("scrapecreatorsKeySaveStatus").textContent,/Not saved/);
    e.run('state.settings.scrapecreators_key_set=true');
    e.el("scrapecreatorsDisclosure").checked=true;
    await e.run('saveSettingsPatch({scrapecreators_enabled:true}, "scrapecreatorsEnabled")');
    e.el("scrapecreatorsDisclosure").checked=false;
    const before=e.calls.length;
    await e.run('settingEdit("scrapecreatorsEnabled").retry()');
    assert.equal(e.calls.length,before, "retry must recheck disclosure before enabling");
  },
  async settings_stale() {
    const e=environment(); e.el("scrapecreatorsKey").value="private"; await e.el("saveScrapecreatorsKey").fire("click");
    e.run('hydrateSettings({settings:{scrapecreators_key_set:false}}, {})');
    assert.equal(e.run("state.settings.scrapecreators_key_set"),true);
    assert.equal(e.el("scrapecreatorsKey").value,"");
  },
  async balance() {
    const e=environment(); e.run('state.settings.scrapecreators_key_set=true; state.settings.scrapecreators_enabled=true; renderConnectedServices()');
    await e.el("testScrapecreatorsKey").fire("click");
    assert.deepEqual(e.calls.map(c=>c.url),["/discovery/test-key"]);
    assert.match(e.el("scrapecreatorsTestStatus").textContent,/may use a credit.*1 credit planned/);
    await e.el("testScrapecreatorsKey").fire("click");
    assert.equal(e.calls[1].url,"/discovery/intent"); assert.equal(e.calls[1].body.operation.tool,"test_key");
    assert.equal(e.calls[2].body.user_intent_token,"intent-1"); assert.match(e.el("scrapecreatorsTestStatus").textContent,/333/);
  },
  async invalid_key() {
    const e=environment(); await ready(e);
    e.run('state.settings.scrapecreators_key_set=true');
    e.setHandler(async(u,b)=>u==="/mcp/v1/tools/call" ? {result:{structuredContent:refusal("scrapecreators_key_invalid")}} : e.defaultHandler(u,b));
    await e.el("discoveryRun").fire("click");
    assert.equal(e.run("state.settings.scrapecreators_key_set"),true); assert.equal(e.run("state.settings.scrapecreators_key_invalid"),true);
    assert.match(e.el("scrapecreatorsKeyStatus").textContent,/Invalid.*kept/); assert.match(e.el("discoveryStatus").textContent,/kept/);
  },
  async plan() {
    const e=environment(); assert.equal(e.calls.length,0); await ready(e);
    assert.equal(e.calls.length,1); assert.equal(e.calls[0].body.params.arguments.confirm_credits,undefined);
    assert.match(e.el("discoveryCreditPlan").textContent,/1 credit.*2 used today.*25/);
    e.el("discoveryTerm").value="other"; await e.el("discoveryTerm").fire("input");
    assert.equal(e.el("discoveryRun").disabled,true);
    e.el("discoveryPlatform").value="instagram"; e.el("discoveryMode").value="keyword"; await e.el("discoveryMode").fire("input");
    assert.equal(e.el("discoveryPlatform").value,"youtube");
  },
  async intent_failure() {
    const e=environment(); await ready(e); e.setHandler(async()=>{throw Error("mint failed");});
    await e.el("discoveryRun").fire("click"); assert.equal(e.calls.length,2);
    assert.equal(e.el("discoveryRun").disabled,true); assert.equal(e.el("discoveryFields").disabled,false);
  },
  async run() {
    const e=environment(); await ready(e); const wait=deferred();
    e.setHandler(async(u,b)=>u==="/mcp/v1/tools/call" ? wait.promise : e.defaultHandler(u,b));
    const pending=e.el("discoveryRun").fire("click"); await settle();
    assert.equal(e.el("discoveryRun").disabled,true); assert.equal(e.el("discoveryFields").disabled,true);
    await e.el("discoveryRun").fire("click"); assert.equal(e.calls.length,3);
    assert.equal(e.calls[1].url,"/discovery/intent"); assert.equal(e.calls[2].body.params.arguments.user_intent_token,"intent-1");
    wait.resolve({result:{structuredContent:e.receipt}}); await pending;
    assert.equal(e.el("discoveryRun").disabled,true); assert.equal(e.el("discoveryFields").disabled,false);
    assert.equal(e.el("discoveryResults").children[0].dataset.discoveryPick,"k11");
    assert.equal(e.el("discoveryResults").children.at(-1).dataset.discoveryPick,"k0");
    e.setHandler(e.defaultHandler); await ready(e); await e.el("discoveryRun").fire("click");
    assert.equal(e.calls.at(-1).body.params.arguments.user_intent_token,"intent-2");
  },
  async paid_failure() {
    const e=environment(); await ready(e); e.setHandler(async(u,b)=>{if(u==="/mcp/v1/tools/call")throw Error("lost response");return e.defaultHandler(u,b);});
    await e.el("discoveryRun").fire("click"); assert.equal(e.calls.length,3);
    assert.equal(e.el("discoveryRun").disabled,true); assert.match(e.el("discoveryStatus").textContent,/No automatic retry/);
  },
  async partial_failure() {
    const e=environment(); Object.assign(e.receipt,refusal("discovery_rate_limited"),{save_failed:true});
    await ready(e); await e.el("discoveryRun").fire("click");
    assert.equal(e.el("discoveryResults").children.length,12); assert.equal(e.el("discoveryRecovery").classList.contains("hidden"),false);
  },
  async save_failure() {
    const e=environment(); e.receipt.save_failed=true; await ready(e); await e.el("discoveryRun").fire("click");
    assert.equal(e.el("discoveryResults").children.length,12); assert.equal(e.el("discoveryRecovery").classList.contains("hidden"),false);
    await picked(e,1); assert.equal(e.el("discoveryQueue").disabled,true); assert.equal(e.el("discoveryPlan").disabled,true);
    await e.el("discoverySaveAgain").fire("click"); assert.equal(e.calls.at(-1).url,"/discovery/runs/save");
    assert.deepEqual(e.calls.at(-1).body,{run_id:e.receipt.run_id}); assert.equal(e.calls.length,4);
    assert.equal(e.el("discoveryQueue").disabled,false); assert.match(e.el("discoveryStatus").textContent,/No provider credits/);
  },
  async save_retry_failure() {
    const e=environment(); e.receipt.save_failed=true; await ready(e); await e.el("discoveryRun").fire("click");
    e.setHandler(async()=>{throw Error("disk full");}); await e.el("discoverySaveAgain").fire("click");
    assert.equal(e.el("discoveryResults").children.length,12); assert.equal(e.el("discoveryRecovery").classList.contains("hidden"),false);
    assert.equal(e.calls.length,4);
  },
  async save_retry_bad_response() {
    const e=environment(); e.receipt.save_failed=true; await ready(e); await e.el("discoveryRun").fire("click");
    for (const reply of [{ok:true}, {ok:true,run:{...e.receipt,run_id:"wrong-run"}}, {ok:true,run:{run_id:e.receipt.run_id}}]) {
      e.setHandler(async()=>reply); await e.el("discoverySaveAgain").fire("click");
      assert.equal(e.el("discoveryResults").children.length,12);
      assert.equal(e.el("discoveryRecovery").classList.contains("hidden"),false);
      assert.equal(e.run("discoveryState.run.run_id"),e.receipt.run_id);
      assert.equal(e.el("discoveryQueue").disabled,true);
    }
    assert.equal(e.calls.filter(c=>c.url==="/mcp/v1/tools/call").length,2, "local retry must never rediscover");
  },
  async selection() {
    const e=environment(); e.candidates[0].in_library=true; e.candidates[0].caption='<img src="https://tracker.test/x">';
    await ready(e); await e.el("discoveryRun").fire("click");
    assert.match(e.el("discoveryResults").innerHTML,/In library/); assert(!e.el("discoveryResults").innerHTML.includes('<img'));
    await picked(e,11); assert.equal(e.run("discoveryState.selected.size"),10);
    assert.equal(e.el("discoveryQueue").textContent,"Uoink selected (10)");
  },
  async queue() {
    const e=environment(); await ready(e); await e.el("discoveryRun").fire("click"); await picked(e,2);
    await e.el("discoveryQueue").fire("click"); assert.equal(e.calls[3].url,"/discovery/intent");
    assert.equal(e.calls[3].body.operation.tool,"queue_discovered"); assert.deepEqual(e.calls[3].body.operation.arguments.keys,["k11","k10"]);
    assert.equal(e.calls[4].body.params.name,"queue_discovered"); assert.equal(e.calls[4].body.params.arguments.user_intent_token,"intent-2");
    assert.equal(e.el("discoveryQueue").disabled,true); assert.match(e.el("discoveryStatus").textContent,/2 queued/);
  },
  async states() {
    const e=environment(); await ready(e); await e.el("discoveryRun").fire("click");
    ["deleted","unavailable","failed","cancelled"].forEach((s,i)=>e.candidates[i].state=s);
    await e.el("discoveryRefresh").fire("click");
    assert.equal(e.calls.at(-1).url,`/discovery/runs/${e.receipt.run_id}`);
    for(const text of ["Deleted from library","Capture unavailable","Capture failed","Capture cancelled"]) assert(e.el("discoveryResults").innerHTML.includes(text));
    assert.equal((e.el("discoveryResults").innerHTML.match(/Capture failed/g)||[]).length,1);
  },
};
const name=process.argv[2]; assert(scenarios[name],`Unknown scenario ${name}`);
scenarios[name]().then(()=>console.log(`PASS ${name}`)).catch(error=>{console.error(error);process.exitCode=1;});
