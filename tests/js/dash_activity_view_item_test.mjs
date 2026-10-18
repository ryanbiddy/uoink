// Dashboard Activity regression harness: the live stream reconnects (D20) and
// View Item in the evidence modal opens the item (D3).
//
// Before the fix connectJobsStream() in assets/dashboard/index.html read
// /jobs/stream once: a clean end broke out of the loop and an error only
// scheduled one refreshActivity(), so after a helper restart or a PC sleep the
// Activity list, the nav badge and "N in flight" froze until a reload. View
// Item in the Library activity evidence modal called showYoinkDetail(), which
// does not exist, so it only hid the modal and left focus inside it.
//
// Runs the REAL dashboard script (everything before init()) in a node:vm
// context over a fake page holding every id the markup declares. setTimeout
// and Date are fakes the test drives, so every reconnect wait is visible and
// fired by hand; /jobs/stream answers with a stream the test feeds, ends or
// breaks.
//   reconnect -- a stream that ends cleanly or breaks is reopened after a
//                wait, each reopen catches up with refreshActivity() before
//                the stream reopens (a slow /jobs answer never lands on top
//                of the reopened stream's snapshot), and the reopened stream
//                drives Activity, the nav badge and "N in flight" again
//                (token header on every connect, split frames and heartbeats
//                still parse)
//   backoff   -- while the helper is down the waits double up to a 30 s cap,
//                a 503 refusal waits too, a stream that stayed open a while
//                starts again from 1 s, and one that ends straight away keeps
//                backing off
//   view_item -- View Item on an evidence row closes the modal, opens that
//                item's detail (the loaded Library row when there is one) and
//                puts focus on something visible in the item view, not on the
//                Library trigger the tab switch hides
//
// Every markup id sits in the tab panel the markup puts it in; an element is
// shown only while its tab panel is the active one, and, as in a browser,
// focus() only moves focus to a shown control or element with a tabindex.
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/dash_activity_view_item_test.mjs [group ...]
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAGE = readFileSync(join(ROOT, "assets", "dashboard", "index.html"), "utf8");
const SCRIPT_OPEN = PAGE.indexOf("<script>");
const SCRIPT_START = SCRIPT_OPEN + "<script>".length;
const INIT_CALL = PAGE.indexOf("    init().catch(", SCRIPT_START);
if (SCRIPT_OPEN < 0 || INIT_CALL < 0) throw new Error("dashboard script or its init() call not found");
const SCRIPT = PAGE.slice(SCRIPT_START, INIT_CALL);
const MARKUP = PAGE.slice(0, SCRIPT_OPEN);

let failures = 0;
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}
async function scenario(name, fn) {
  try {
    await fn();
  } catch (e) {
    failures++;
    console.error(`FAIL: ${name} threw: ${(e && e.stack) || e}`);
  }
}
process.on("unhandledRejection", (e) => {
  failures++;
  console.error(`FAIL: unhandled rejection: ${(e && e.stack) || e}`);
});

async function settle() {
  for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r));
}

// id -> tag, tabindex and enclosing tab panel for every element the dashboard
// markup declares, and every tab panel with whether it ships active.
const TAGS = new Map();
const TABINDEX = new Map();
const PANEL_OF = new Map();
const PANELS = [];
{
  let m;
  const panelRe = /<section\b[^>]*\bdata-tab-panel="([^"]+)"[^>]*>/g;
  while ((m = panelRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[0]);
    if (!id) continue;
    // The panel ends where its own <section> closes.
    const sectionRe = /<\/?section\b/g;
    sectionRe.lastIndex = m.index;
    let depth = 0;
    let end = MARKUP.length;
    let s;
    while ((s = sectionRe.exec(MARKUP)) !== null) {
      depth += s[0][1] === "/" ? -1 : 1;
      if (depth === 0) { end = s.index; break; }
    }
    const active = /\sclass="[^"]*\bactive\b[^"]*"/.test(m[0]);
    PANELS.push({ id: id[1], name: m[1], active, start: m.index, end });
  }
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (!id || TAGS.has(id[1])) continue;
    TAGS.set(id[1], m[1].toUpperCase());
    const tabindex = /\stabindex="([^"]*)"/.exec(m[2]);
    if (tabindex) TABINDEX.set(id[1], tabindex[1]);
    const at = m.index;
    const panel = PANELS.find((p) => at > p.start && at < p.end);
    if (panel) PANEL_OF.set(id[1], panel.id);
  }
}

// Shown = neither the element nor its tab panel is hidden, and the panel is
// the active one.
function isShown(el) {
  for (let node = el; node; node = node._parent) {
    if (node.hidden || node.classList.contains("hidden")) return false;
    if (node.dataset.tabPanel && !node.classList.contains("active")) return false;
  }
  return true;
}

function within(el, ancestor) {
  for (let node = el; node; node = node._parent) {
    if (node === ancestor) return true;
  }
  return false;
}

function describe(el) {
  if (!el) return "nothing";
  return `${el.tagName}${el.id ? `#${el.id}` : ""}${isShown(el) ? "" : " (hidden)"}`;
}

class FakeClassList {
  constructor() { this._set = new Set(); }
  add(...names) { names.forEach((n) => this._set.add(n)); }
  remove(...names) { names.forEach((n) => this._set.delete(n)); }
  contains(name) { return this._set.has(name); }
  toggle(name, force) {
    const on = force === undefined ? !this._set.has(name) : Boolean(force);
    if (on) this._set.add(name); else this._set.delete(name);
    return on;
  }
}

class FakeEl {
  constructor(id, tag, doc) {
    this.id = id;
    this.tagName = tag || "DIV";
    this._doc = doc || null;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.title = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.scrollTop = 0;
    this.files = [];
    this.options = [];
    this.dataset = {};
    this.style = {};
    this.classList = new FakeClassList();
    this._attrs = {};
    this._listeners = {};
    this._matches = [];
    this._parent = null;
  }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  setAttribute(name, value) { this._attrs[name] = String(value); }
  getAttribute(name) { return name in this._attrs ? this._attrs[name] : null; }
  hasAttribute(name) { return name in this._attrs; }
  removeAttribute(name) { delete this._attrs[name]; }
  toggleAttribute(name, force) {
    const on = force === undefined ? !(name in this._attrs) : Boolean(force);
    if (on) this._attrs[name] = ""; else delete this._attrs[name];
    return on;
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  // A fake element matches only the selectors a test gives it.
  closest(selector) { return this._matches.includes(selector) ? this : null; }
  contains() { return false; }
  setCustomValidity() {}
  // As in a browser: only a shown control, or a shown element with a
  // tabindex, takes focus.
  focus() {
    if (!this._doc || this.disabled || !isShown(this)) return;
    const control = ["BUTTON", "INPUT", "SELECT", "TEXTAREA", "SUMMARY"].includes(this.tagName)
      || (this.tagName === "A" && this.hasAttribute("href"));
    if (control || this.hasAttribute("tabindex")) this._doc.activeElement = this;
  }
  blur() {}
  select() {}
  click() {}
  scrollIntoView() {}
  append() {}
  appendChild(child) { return child; }
  remove() {}
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function jsonResponse(body, status = 200) {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    body: null,
    json: async () => body,
    text: async () => text,
    blob: async () => ({}),
  };
}

// server.py _mcp_tool_call_result: the tool reply rides in a JSON-RPC result.
function mcpReply(payload) {
  return jsonResponse({
    jsonrpc: "2.0",
    id: "fixture",
    result: {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      structuredContent: payload,
      isError: payload.ok === false,
    },
  });
}

// One /jobs/stream response body the test feeds, ends or breaks.
const encoder = new TextEncoder();
function makeStream() {
  const queued = [];
  const reads = [];
  const pump = () => {
    while (reads.length && queued.length) {
      const read = reads.shift();
      const item = queued.shift();
      if (item.error) read.reject(item.error);
      else if (item.done) read.resolve({ value: undefined, done: true });
      else read.resolve({ value: item.value, done: false });
    }
  };
  const reader = {
    read() { return new Promise((resolve, reject) => { reads.push({ resolve, reject }); pump(); }); },
    releaseLock() {},
    cancel() { return Promise.resolve(); },
  };
  return {
    open: true,
    reader,
    push(text) { queued.push({ value: encoder.encode(text) }); pump(); },
    end() { queued.push({ done: true }); pump(); },
    fail(err) { queued.push({ error: err || new TypeError("network error") }); pump(); },
  };
}

function frame(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function job(id, stateValue) {
  return { id, state: stateValue, kind: "video", title: `Job ${id}`, url: `https://example.com/${id}` };
}

const REVISION = "a".repeat(64);
function activityPacket() {
  return {
    ok: true,
    report_revision: REVISION,
    as_of: "2026-10-15T12:00:00.000Z",
    date_basis: "capture_time",
    interval: { start: "2026-10-08T00:00:00.000Z", end: "2026-10-15T00:00:00.000Z" },
    items: { total: { value: 1, metric_id: "items.total" }, coverage_ref: "cov_capture" },
    coverage: { cov_capture: { coverage_status: "retained_records" } },
    shelf_activity: {},
    sources: {},
    events: {},
    warnings: [],
  };
}

// One fresh dashboard page. `helper` is what the fake helper answers:
// down = every request but /token fails to connect; streamStatus = /jobs/stream
// answers that HTTP status instead of a stream; jobs/queue = /jobs and
// /queue/status bodies; tool = the registry tool; files = /yoinks/... bodies;
// holdNext = paths whose next answer is taken as the helper sees it at request
// time but only delivered when the test releases it.
function makePage() {
  const clock = { now: Date.parse("2026-10-15T12:00:00.000Z") };
  class FakeDate extends Date {
    constructor(...args) { super(...(args.length ? args : [clock.now])); }
    static now() { return clock.now; }
  }

  // Every setTimeout the page asks for waits here until the test fires it.
  const timers = [];
  let timerSeq = 0;
  const fakeSetTimeout = (fn, ms = 0, ...args) => {
    const t = { id: ++timerSeq, fn, ms: Number(ms) || 0, args };
    timers.push(t);
    return t.id;
  };
  const fakeClearTimeout = (id) => {
    const at = timers.findIndex((t) => t.id === id);
    if (at >= 0) timers.splice(at, 1);
  };

  const elements = new Map();
  const docListeners = {};
  const document = {
    querySelector: (selector) => (selector === ".content" ? contentEl : null),
    querySelectorAll: (selector) => (selector === "[data-tab-panel]" ? panels : []),
    addEventListener(type, fn) { (docListeners[type] ||= []).push(fn); },
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase(), document),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };
  const getEl = (id) => {
    if (!elements.has(id)) {
      const el = new FakeEl(id, TAGS.get(id), document);
      elements.set(id, el);
      if (TABINDEX.has(id)) el.setAttribute("tabindex", TABINDEX.get(id));
      const panel = PANELS.find((p) => p.id === id);
      if (panel) {
        el.dataset.tabPanel = panel.name;
        if (panel.active) el.classList.add("active");
      }
      if (PANEL_OF.has(id)) el._parent = getEl(PANEL_OF.get(id));
    }
    return elements.get(id);
  };
  document.getElementById = getEl;
  document.body = new FakeEl("body", "BODY", document);
  document.documentElement = new FakeEl("html", "HTML", document);
  const contentEl = new FakeEl("", "MAIN", document);
  const panels = PANELS.map((p) => getEl(p.id));
  // The markup ships the evidence modal hidden.
  getEl("activityEvidenceModal").classList.add("hidden");

  const helper = {
    down: false,
    streamStatus: 0,
    jobs: [],
    queue: { ok: true, pending: [], running: 0, completed_today: 0 },
    tool: () => ({ ok: true }),
    files: {},
    holdNext: [],
  };
  const requests = [];
  const streams = []; // every /jobs/stream attempt, refused ones included
  const held = []; // answers waiting for the test to release them
  const fakeFetch = (url, opts = {}) => {
    const path = String(url);
    const headers = (opts && opts.headers) || {};
    let body = null;
    try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (_) { body = opts.body; }
    requests.push({ path, method: (opts && opts.method) || "GET", token: headers["X-Uoink-Token"] || "", body });
    const answer = respond(path, body);
    const at = helper.holdNext.indexOf(path);
    if (at < 0) return answer;
    helper.holdNext.splice(at, 1);
    answer.catch(() => {}); // a refusal is delivered on release, not reported now
    return new Promise((resolve) => held.push({ path, release: () => resolve(answer) }));
  };
  const respond = (path, body) => {
    if (path === "/token") return Promise.resolve(jsonResponse({ ok: true, token: "test-token" }));
    if (helper.down) {
      if (path === "/jobs/stream") streams.push({ open: false, refused: "network" });
      return Promise.reject(new TypeError("Failed to fetch"));
    }
    if (path === "/jobs/stream") {
      if (helper.streamStatus) {
        streams.push({ open: false, refused: helper.streamStatus });
        return Promise.resolve(jsonResponse({ ok: false, error: "too many streams" }, helper.streamStatus));
      }
      const s = makeStream();
      streams.push(s);
      return Promise.resolve({ ok: true, status: 200, body: { getReader: () => s.reader } });
    }
    if (path === "/jobs") return Promise.resolve(jsonResponse({ ok: true, jobs: helper.jobs }));
    if (path === "/queue/status") return Promise.resolve(jsonResponse(helper.queue));
    if (path === "/mcp/v1/tools/call") {
      const name = body && body.params && body.params.name;
      const args = (body && body.params && body.params.arguments) || {};
      return Promise.resolve(mcpReply(helper.tool(name, args)));
    }
    if (path in helper.files) return Promise.resolve(jsonResponse(helper.files[path]));
    return Promise.resolve(jsonResponse({ ok: true }));
  };

  const window = {
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
    setTimeout: fakeSetTimeout,
    clearTimeout: fakeClearTimeout,
    open() {},
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    innerWidth: 1280,
    innerHeight: 800,
    location: { hash: "", href: "http://127.0.0.1/", origin: "http://127.0.0.1" },
  };
  const storage = () => {
    const m = new Map();
    return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
  };
  const ctx = {
    document,
    window,
    location: window.location,
    navigator: { clipboard: { writeText: () => Promise.resolve() }, userAgent: "node" },
    localStorage: storage(),
    sessionStorage: storage(),
    console,
    fetch: fakeFetch,
    Date: FakeDate,
    setTimeout: fakeSetTimeout,
    clearTimeout: fakeClearTimeout,
    setInterval: () => 0,
    clearInterval() {},
    requestAnimationFrame: (fn) => fakeSetTimeout(fn, 0),
    cancelAnimationFrame() {},
    URL: Object.assign(function FakeURL(u, base) { return new URL(u, base); }, {
      createObjectURL: () => "blob:fake",
      revokeObjectURL() {},
    }),
    URLSearchParams,
    TextDecoder,
    CSS: { escape: (s) => String(s) },
    Event: class { constructor(type) { this.type = type; } },
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
  };
  window.document = document;
  vm.createContext(ctx);
  vm.runInContext(`${SCRIPT}
;globalThis.__page = { state, els, libraryActivityState, connectJobsStream, wireLibraryActivityEvents,
  fetchActivityEvidence, focusRestore: () => activityEvidenceFocusRestore };`, ctx);
  const page = ctx.__page;

  return {
    page,
    state: page.state,
    els: page.els,
    activity: page.libraryActivityState,
    document,
    getEl,
    panels,
    helper,
    clock,
    timers,
    requests,
    streams,
    // Fire the oldest pending timer, as the browser would once it is due.
    fireTimer() {
      const t = timers.shift();
      if (!t) return false;
      t.fn(...t.args);
      return true;
    },
    pending: () => timers.map((t) => t.ms),
    held: () => held.map((h) => h.path),
    // Deliver the oldest held answer for `path`.
    release(path) {
      const at = held.findIndex((h) => h.path === path);
      if (at < 0) return false;
      held.splice(at, 1)[0].release();
      return true;
    },
    count: (path) => requests.filter((r) => r.path === path).length,
    lastStream: () => streams[streams.length - 1],
    // A click the document-level delegation sees, as a real click bubbles to it.
    click(target) {
      const event = { type: "click", target, preventDefault() {}, stopPropagation() {} };
      for (const fn of docListeners.click || []) fn(event);
    },
  };
}

function headline(p) {
  return p.els.activityHeadline.innerHTML;
}

// ---------------------------------------------------------------------------
async function groupReconnect() {
  await scenario("stream ends cleanly (helper restarted)", async () => {
    const p = makePage();
    p.page.connectJobsStream();
    await settle();
    check(p.streams.length === 1 && p.streams[0].open, "the dashboard opens the live stream", p.streams.length);
    if (!p.streams.length) return;
    p.streams[0].push(frame("snapshot", { active: [job("j1", "running"), job("j2", "queued")], recent: [], queue: { pending: 0, running: 1 } }));
    await settle();
    check(headline(p).startsWith("2 in flight"), "the first stream drives 'N in flight'", headline(p));
    check(p.els.activityNavCount.textContent === "2", "the first stream drives the nav badge", p.els.activityNavCount.textContent);

    const jobsBefore = p.count("/jobs");
    const queueBefore = p.count("/queue/status");
    p.streams[0].end();
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([1000]), "a clean end schedules a reconnect after 1 s", p.pending());
    check(p.streams.length === 1, "the stream is not reopened before the wait is over", p.streams.length);

    // The helper restarted while the stream was down: both jobs finished.
    p.helper.jobs = [job("j1", "completed"), job("j2", "completed")];
    check(p.fireTimer(), "the reconnect wait fires");
    await settle();
    check(p.streams.length === 2 && p.streams[1].open, "the stream is reopened after the wait", p.streams.length);
    check(p.count("/jobs") === jobsBefore + 1 && p.count("/queue/status") === queueBefore + 1, "the reconnect catches up with refreshActivity()", [p.count("/jobs") - jobsBefore, p.count("/queue/status") - queueBefore]);
    check(headline(p).startsWith("Nothing uoinking"), "the catch-up clears the frozen 'N in flight'", headline(p));
    if (p.streams.length < 2) return;
    p.streams[1].push(frame("job", job("j3", "running")));
    await settle();
    check(headline(p).startsWith("1 in flight"), "the reopened stream drives 'N in flight' again", headline(p));
    check(p.els.activityNavCount.textContent === "1", "the reopened stream drives the nav badge again", p.els.activityNavCount.textContent);
    check(p.state.jobs.some((row) => row.id === "j3"), "the reopened stream's job reaches Activity", p.state.jobs.map((row) => row.id));
  });

  await scenario("stream breaks mid-read (helper killed, PC slept)", async () => {
    const p = makePage();
    p.page.connectJobsStream();
    await settle();
    if (!p.streams.length) { check(false, "the dashboard opens the live stream", p.streams.length); return; }
    p.streams[0].push(frame("snapshot", { active: [job("j1", "running")], recent: [], queue: {} }));
    await settle();
    p.streams[0].fail(new TypeError("network error"));
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([1000]), "a broken stream schedules a reconnect after 1 s", p.pending());
    p.helper.jobs = [job("j1", "running"), job("j4", "queued")];
    check(p.fireTimer(), "the reconnect wait fires");
    await settle();
    check(p.streams.length === 2 && p.streams[1].open, "the broken stream is reopened", p.streams.length);
    check(headline(p).startsWith("2 in flight"), "the catch-up shows work queued while the stream was down", headline(p));
    if (p.streams.length < 2) return;
    p.streams[1].push(frame("job", job("j4", "running")));
    p.streams[1].push(frame("job", job("j1", "completed")));
    await settle();
    check(headline(p).startsWith("1 in flight"), "job updates on the reopened stream reach 'N in flight'", headline(p));
  });

  await scenario("a slow catch-up never lands on top of the reopened stream", async () => {
    const p = makePage();
    p.page.connectJobsStream();
    await settle();
    if (!p.streams.length) { check(false, "the dashboard opens the live stream", p.streams.length); return; }
    p.streams[0].push(frame("snapshot", { active: [job("j1", "running")], recent: [], queue: {} }));
    await settle();
    p.streams[0].end();
    await settle();
    // The catch-up's /jobs answer is slow, and by the time it arrives it is
    // old: the helper read j1 as still running.
    p.helper.jobs = [job("j1", "running")];
    p.helper.holdNext.push("/jobs");
    check(p.fireTimer(), "the reconnect wait fires");
    await settle();
    check(JSON.stringify(p.held()) === JSON.stringify(["/jobs"]), "the catch-up is waiting on /jobs", p.held());
    const reopenedEarly = p.streams.length > 1;
    check(!reopenedEarly, "the stream is not reopened while the catch-up is still loading", p.streams.length);
    // Meanwhile j1 finished; the stream's snapshot says so.
    const finished = frame("snapshot", { active: [], recent: [job("j1", "completed")], queue: {} });
    if (reopenedEarly && p.lastStream().open) {
      p.lastStream().push(finished);
      await settle();
    }
    check(p.release("/jobs"), "the slow /jobs answer arrives");
    await settle();
    if (!reopenedEarly) {
      const s = p.lastStream();
      check(p.streams.length === 2 && Boolean(s && s.open), "the stream reopens once the catch-up has landed", p.streams.length);
      if (!s || !s.open) return;
      s.push(finished);
      await settle();
    }
    const j1 = p.state.jobs.find((row) => row.id === "j1");
    check(Boolean(j1) && j1.state === "completed", "the finished job stays finished", j1 && j1.state);
    check(headline(p).startsWith("Nothing uoinking"), "'N in flight' does not go back up", headline(p));
    check(p.els.activityNavCount.textContent === "0", "the nav badge does not go back up", p.els.activityNavCount.textContent);
    check(p.pending().length === 0, "an open stream schedules nothing", p.pending());
  });

  await scenario("every connect carries the token; frames still parse", async () => {
    const p = makePage();
    p.page.connectJobsStream();
    await settle();
    if (!p.streams.length) { check(false, "the dashboard opens the live stream", p.streams.length); return; }
    p.streams[0].end();
    await settle();
    p.fireTimer();
    await settle();
    const streamRequests = p.requests.filter((r) => r.path === "/jobs/stream");
    check(streamRequests.length === 2 && streamRequests.every((r) => r.token === "test-token"), "each stream connect sends X-Uoink-Token", streamRequests.map((r) => r.token));
    const s = p.lastStream();
    if (!s || !s.open) return;
    s.push(": heartbeat\n\n");
    s.push(`event: job\r\ndata: ${JSON.stringify(job("j9", "running"))}\r\n`);
    await settle();
    check(!p.state.jobs.some((row) => row.id === "j9"), "half a frame is held until the rest arrives", p.state.jobs.map((row) => row.id));
    s.push("\r\n");
    await settle();
    check(p.state.jobs.some((row) => row.id === "j9") && headline(p).startsWith("1 in flight"), "a frame split across reads, with CRLF line ends, is applied", headline(p));
    check(p.pending().length === 0, "an open stream schedules nothing", p.pending());
  });
}

async function groupBackoff() {
  await scenario("helper down: waits double and stop at the cap", async () => {
    const p = makePage();
    p.page.connectJobsStream();
    await settle();
    if (!p.streams.length) { check(false, "the dashboard opens the live stream", p.streams.length); return; }
    p.streams[0].push(frame("snapshot", { active: [job("j1", "running")], recent: [], queue: {} }));
    await settle();
    p.helper.down = true;
    p.streams[0].fail(new TypeError("network error"));
    await settle();
    const waits = [];
    let refreshedEachTime = true;
    for (let i = 0; i < 8; i++) {
      const pending = p.pending();
      if (pending.length !== 1) {
        check(false, `exactly one reconnect is scheduled after failure ${i + 1}`, pending);
        break;
      }
      waits.push(pending[0]);
      const attemptsBefore = p.streams.length;
      const jobsBefore = p.count("/jobs");
      p.fireTimer();
      await settle();
      if (p.count("/jobs") !== jobsBefore + 1) refreshedEachTime = false;
      if (p.streams.length !== attemptsBefore + 1) {
        check(false, `the stream is retried after wait ${i + 1}`, p.streams.length - attemptsBefore);
        break;
      }
    }
    check(JSON.stringify(waits) === JSON.stringify([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]), "the waits double from 1 s and stop at 30 s", waits);
    check(refreshedEachTime && waits.length === 8, "every reconnect attempt calls refreshActivity()", { refreshedEachTime, attempts: waits.length });

    // The helper is back.
    p.helper.down = false;
    p.helper.jobs = [];
    check(p.fireTimer(), "the next reconnect fires once the helper is back");
    await settle();
    const s = p.lastStream();
    check(Boolean(s && s.open), "the stream is reopened once the helper is back", s && s.refused);
    check(headline(p).startsWith("Nothing uoinking"), "Activity catches up once the helper is back", headline(p));
    if (!s || !s.open) return;
    s.push(frame("snapshot", { active: [job("j5", "queued")], recent: [], queue: {} }));
    await settle();
    check(headline(p).startsWith("1 in flight") && p.els.activityNavCount.textContent === "1", "the reopened stream drives Activity and the badge", [headline(p), p.els.activityNavCount.textContent]);
  });

  await scenario("helper refuses the stream (503 too many streams)", async () => {
    const p = makePage();
    p.helper.streamStatus = 503;
    p.page.connectJobsStream();
    await settle();
    check(p.streams.length === 1 && p.streams[0].refused === 503, "the first connect is refused with 503", p.streams.map((s) => s.refused));
    check(JSON.stringify(p.pending()) === JSON.stringify([1000]), "a refused stream is retried after 1 s, not dropped", p.pending());
    p.fireTimer();
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([2000]), "a second refusal waits 2 s", p.pending());
    p.helper.streamStatus = 0;
    p.fireTimer();
    await settle();
    check(Boolean(p.lastStream() && p.lastStream().open), "the stream opens once the helper accepts it", p.streams.length);
  });

  await scenario("a healthy stream resets the wait; a stream that ends at once does not", async () => {
    const p = makePage();
    p.helper.down = true;
    p.page.connectJobsStream();
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([1000]), "the first failed connect waits 1 s", p.pending());
    p.fireTimer();
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([2000]), "the second failed connect waits 2 s", p.pending());
    p.helper.down = false;
    p.fireTimer();
    await settle();
    const healthy = p.lastStream();
    check(Boolean(healthy && healthy.open), "the third connect opens the stream", p.streams.map((s) => s.refused || "open"));
    if (!healthy || !healthy.open) return;
    healthy.push(frame("snapshot", { active: [], recent: [], queue: {} }));
    await settle();
    p.clock.now += 60000; // the stream stays open for a minute
    healthy.end();
    await settle();
    check(JSON.stringify(p.pending()) === JSON.stringify([1000]), "after a stream that stayed open a minute the wait starts at 1 s again", p.pending());

    // Accepted, then closed straight away: still a clean end, still backs off.
    const quick = [];
    for (let i = 0; i < 3; i++) {
      p.fireTimer();
      await settle();
      const s = p.lastStream();
      if (!s || !s.open) { check(false, `quick connect ${i + 1} opens`, p.streams.length); return; }
      s.end();
      await settle();
      quick.push(p.pending()[0]);
    }
    check(JSON.stringify(quick) === JSON.stringify([2000, 4000, 8000]), "streams that end at once keep backing off after a clean end", quick);
  });
}

async function groupViewItem() {
  const evidenceReply = {
    ok: true,
    report_revision: REVISION,
    rows: [{
      row_id: "r1",
      source_table: "items",
      source_key: "vid_A",
      event_time: "2026-10-14T09:00:00Z",
      observation_hash: "h1",
      details: { video_id: "vid_A" },
    }],
    total_rows: 1,
    next: null,
  };

  // Library activity is loaded and the user opened a metric's evidence from
  // its trigger in the Library tab; View Item on the row is then the focused
  // control.
  async function openEvidence(p) {
    p.activity.packet = activityPacket();
    p.activity.stale = false;
    p.activity.error = null;
    p.activity.loading = false;
    p.helper.tool = (name, args) => (name === "get_library_activity" && args.detail === "evidence" ? evidenceReply : activityPacket());
    p.helper.files["/yoinks/vid_A/details"] = { ok: true, details: { video_id: "vid_A", title: "Agent loops explained" } };
    p.helper.files["/yoinks/vid_A/markdown"] = { ok: true, markdown: "# Agent loops explained" };
    p.page.wireLibraryActivityEvents();
    const libraryPanel = p.panels.find((panel) => panel.dataset.tabPanel === "library");
    const trigger = p.getEl("activityTotalItems");
    trigger._matches = [".activity-evidence-trigger"];
    trigger.dataset.metricId = "items.total";
    check(within(trigger, libraryPanel), "the metric trigger sits in the Library tab", describe(trigger._parent));
    trigger.focus();
    check(p.document.activeElement === trigger, "the metric trigger has focus", describe(p.document.activeElement));
    await p.page.fetchActivityEvidence("items.total", 0);
    await settle();
    const modal = p.getEl("activityEvidenceModal");
    const rowsHtml = p.getEl("evidenceRowsContainer").innerHTML;
    check(!modal.classList.contains("hidden"), "the evidence modal is open", [...modal.classList._set]);
    check(rowsHtml.includes('data-open-yoink="vid_A"') && rowsHtml.includes("View Item"), "the evidence row offers View Item for its item", rowsHtml.slice(0, 200));
    const viewItem = new FakeEl("", "BUTTON", p.document);
    viewItem._matches = ["[data-open-yoink]"];
    viewItem.dataset.openYoink = "vid_A";
    viewItem._parent = p.getEl("evidenceRowsContainer");
    viewItem.focus();
    check(p.document.activeElement === viewItem, "View Item has focus", describe(p.document.activeElement));
    return { trigger, viewItem, modal };
  }

  await scenario("View Item opens the item", async () => {
    const p = makePage();
    const { trigger, viewItem, modal } = await openEvidence(p);
    p.click(viewItem);
    await settle();
    check(modal.classList.contains("hidden"), "View Item closes the evidence modal", [...modal.classList._set]);
    check(Boolean(p.state.selectedYoink) && p.state.selectedYoink.video_id === "vid_A", "the item detail is opened for the evidence row's item", p.state.selectedYoink);
    const yoinkPanel = p.panels.find((panel) => panel.dataset.tabPanel === "yoink");
    const libraryPanel = p.panels.find((panel) => panel.dataset.tabPanel === "library");
    check(yoinkPanel.classList.contains("active") && !libraryPanel.classList.contains("active"), "the item view is shown", p.panels.filter((panel) => panel.classList.contains("active")).map((panel) => panel.dataset.tabPanel));
    // The Library tab, and the trigger the modal was opened from, are hidden
    // now, so focus must not be left there or inside the closed modal.
    const focused = p.document.activeElement;
    check(focused !== trigger && focused !== viewItem, "focus does not stay on View Item or go back to the hidden Library trigger", describe(focused));
    check(Boolean(focused) && isShown(focused) && within(focused, yoinkPanel), "focus moves to something visible in the item view", describe(focused));
    check(p.page.focusRestore() === null, "the modal's saved focus target is used up");
    check(p.count("/yoinks/vid_A/details") === 1 && p.count("/yoinks/vid_A/markdown") === 1, "the item's details and transcript are loaded", p.requests.filter((r) => r.path.startsWith("/yoinks/")).map((r) => r.path));
    check(p.els.yoinkTitle.textContent === "Agent loops explained", "the item view names the item", p.els.yoinkTitle.textContent);
  });

  await scenario("View Item uses the loaded Library row", async () => {
    const p = makePage();
    const libraryRow = { video_id: "vid_A", slug: "vid_A", title: "Agent loops explained", folder: "C:\\Uoink\\vid_A", platform: "youtube", source_type: "video" };
    p.state.library = [{ video_id: "vid_B", title: "Other item" }, libraryRow];
    const { viewItem } = await openEvidence(p);
    p.click(viewItem);
    await settle();
    check(p.state.selectedYoink === libraryRow, "the detail opens the Library row for the item", p.state.selectedYoink);
    check(p.els.yoinkOpenFolder.disabled === false, "Open folder works for the opened item", p.els.yoinkOpenFolder.disabled);
  });
}

const GROUPS = {
  reconnect: groupReconnect,
  backoff: groupBackoff,
  view_item: groupViewItem,
};

const wanted = process.argv.slice(2);
const names = wanted.length ? wanted : Object.keys(GROUPS);
for (const name of names) {
  const fn = GROUPS[name];
  if (!fn) {
    failures++;
    console.error(`FAIL: unknown group ${name}`);
    continue;
  }
  const before = checks;
  await fn();
  console.log(`group ${name}: ${checks - before} checks`);
}
console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
