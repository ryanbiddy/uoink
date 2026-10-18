// Dashboard shell harness (UI re-haul, SPEC "Dashboard IA"): hash routes
// with a working Back, the Activity "N failed" badge, and the OS-correct
// helper status at the bottom of the sidebar.
//
// Runs the REAL dashboard script (everything before init()) in a node:vm
// context over a fake page built from the markup: every id the markup
// declares (and only those; getElementById answers null for anything else,
// as a browser does), the five nav buttons with the badges inside them, the
// tab panels, and a fake window.history / location that records pushState
// and fires popstate plus hashchange on Back and Forward, as Chrome does.
//
// The loaders a tab switch runs (loadWriting, refreshSettings, ...) are
// swapped for recorders, so the test sees which screen loaded without
// driving every screen's network. The routing, the badge and the status
// code under test are the page's own.
//
//   routes  -- parseRoute maps every SPEC route and the older links to one
//              screen and one canonical hash; routeForTab is its inverse
//   history -- each move pushes exactly one entry; Back and Forward show
//              the screen again without pushing; #settings/<section> opens
//              on load without pushing; the item view's Back uses
//              history.back() when the page pushed the entry
//   deeplink -- a fresh #item/<id> (no Library row on the page yet) looks
//              the saved row up before the item renders, with the REAL
//              renderYoinkDetail: Open folder works and the saved topic
//              shows (never an id-only stand-in reading Uncategorized); an
//              older item is found by its saved title, however many items
//              share it, or by reading Library to the end (short pages are
//              not the end); an item Library does not have, or a Library
//              that does not answer, says so with every action off; the
//              helper's "no item under this id" settles it after one page;
//              a page that fails, a Library that shrinks mid-lookup or a
//              rate limit that never lifts is never read as "not found";
//              a 429 waits and the lookup carries on; moving elsewhere
//              while it runs wins; Back goes to Library
//   links   -- in-app hash links (#for-you, #activity, #settings/<x>) push
//              one entry and are not also followed by the browser; a bare
//              "#", an unknown hash and a ctrl-click are left alone
//   badge   -- Activity's badge says "N failed" for failed jobs plus failed
//              queue rows (one per video, cancelled work excluded), names it
//              in the nav button's label, and hides at zero
//   status  -- the sidebar says "Running on this PC" (Mac, computer), and
//              offline says how to start Uoink: the Start menu on Windows;
//              on macOS and Linux, where no build ships, that Uoink is
//              Windows-only and a source run restarts with server.py; the
//              10 s poll does not rewrite an unchanged status
//
// No network: fetch is a stub inside the vm context; /memory/search serves
// a fake saved Library the way the helper does (newest first, paged, q
// matching the title).
// Run directly:  node tests/js/rehaul_shell_test.mjs [group ...]
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

// ---- What the markup declares ---------------------------------------------
// id -> tag, classes, tabindex and position; the tab panels and their extent;
// the nav buttons and their extent (the badges sit inside them); each
// Settings section's heading.
const TAGS = new Map();
const CLASSES = new Map();
const TABINDEX = new Map();
const POS = new Map();
const PANELS = [];
const NAV = [];
const HEADINGS = new Map();
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
    PANELS.push({ id: id[1], name: m[1], start: m.index, end });
  }
  const navRe = /<button\b[^>]*\bdata-tab-button="([^"]+)"[^>]*>/g;
  while ((m = navRe.exec(MARKUP)) !== null) {
    const label = /\sdata-nav-label="([^"]*)"/.exec(m[0]);
    NAV.push({
      tab: m[1],
      label: label ? label[1] : "",
      active: /\sclass="[^"]*\bactive\b[^"]*"/.test(m[0]),
      current: /\saria-current="page"/.test(m[0]),
      start: m.index,
      end: MARKUP.indexOf("</button>", m.index),
    });
  }
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (!id || TAGS.has(id[1])) continue;
    TAGS.set(id[1], m[1].toUpperCase());
    POS.set(id[1], m.index);
    const cls = /\sclass="([^"]*)"/.exec(m[2]);
    CLASSES.set(id[1], cls ? cls[1].split(/\s+/).filter(Boolean) : []);
    const tabindex = /\stabindex="([^"]*)"/.exec(m[2]);
    if (tabindex) TABINDEX.set(id[1], tabindex[1]);
  }
  const headRe = /<section class="settings-section" id="([^"]+)" aria-labelledby="([^"]+)">/g;
  while ((m = headRe.exec(MARKUP)) !== null) HEADINGS.set(m[1], m[2]);
}

// Shown = neither the element nor an ancestor is hidden, and its tab panel
// is the active one.
function isShown(el) {
  for (let node = el; node; node = node._parent) {
    if (node.hidden || node.classList.contains("hidden")) return false;
    if (node.dataset.tabPanel && !node.classList.contains("active")) return false;
  }
  return true;
}

function describe(el) {
  if (!el) return "nothing";
  return `${el.tagName}${el.id ? `#${el.id}` : ""}${isShown(el) ? "" : " (hidden)"}`;
}

// The selectors the shell uses with closest(): tags, and a tag with one
// attribute test ("a[href^=\"#\"]"); comma lists of those.
function matchesSimple(el, selector) {
  const m = /^([a-z]+)?(?:\[([a-z-]+)(\^?=)"([^"]*)"\])?$/i.exec(selector.trim());
  if (!m || (!m[1] && !m[2])) return false;
  if (m[1] && el.tagName !== m[1].toUpperCase()) return false;
  if (m[2]) {
    const value = el.getAttribute(m[2]);
    if (value === null) return false;
    if (m[3] === "^=" && !value.startsWith(m[4])) return false;
    if (m[3] === "=" && value !== m[4]) return false;
  }
  return true;
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
    this._text = "";
    this._writes = 0;
    this.value = "";
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
    this._parent = null;
    this._heading = null;
    this._scrolls = 0;
  }
  // Counts writes, so a test can tell an unchanged status was left alone.
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); this._writes += 1; }
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
  // A Settings section answers its heading; nothing else is modelled.
  querySelector() { return this._heading; }
  querySelectorAll() { return []; }
  closest(selector) {
    const parts = String(selector).split(",");
    for (let node = this; node; node = node._parent) {
      if (parts.some((part) => matchesSimple(node, part))) return node;
    }
    return null;
  }
  contains(other) {
    for (let node = other; node; node = node._parent) {
      if (node === this) return true;
    }
    return false;
  }
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
  click() { (this._listeners.click || []).slice().forEach((fn) => fn({ type: "click", target: this, preventDefault() {} })); }
  scrollIntoView() { this._scrolls += 1; }
  append() {}
  appendChild(child) { return child; }
  remove() {}
  insertAdjacentHTML() {}
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

// Saved Library rows as /memory/search returns them.
const DEEP_ROW = {
  video_id: "vid9",
  slug: "deep-link-interview",
  title: "Deep link interview",
  channel: "Example Channel",
  topic: "Research",
  platform: "youtube",
  source_type: "video",
  source_url: "https://www.youtube.com/watch?v=vid9",
  folder: "C:\\Users\\me\\Desktop\\Uoink\\Research\\deep-link-interview",
  duration_seconds: 754,
};
const OLD_ROW = {
  video_id: "old1",
  slug: "pricing-interview",
  title: "Pricing interview from last spring",
  channel: "Archive Channel",
  topic: "Pricing",
  platform: "youtube",
  source_type: "video",
  source_url: "https://www.youtube.com/watch?v=old1",
  folder: "C:\\Users\\me\\Desktop\\Uoink\\Pricing\\pricing-interview",
};

// Saved under one title in the Library index and another in its saved
// details (the title it was captured with), so a title search misses it.
const RENAMED_ROW = {
  video_id: "renamed1",
  title: "Renamed in Library",
  saved_title: "Original upload name",
  topic: "Interviews",
  platform: "youtube",
  source_type: "video",
  folder: "C:\\Users\\me\\Desktop\\Uoink\\Interviews\\renamed-in-library",
};

// `size` saved rows, newest first, with `row` at position `at`.
function bigLibrary(size, row, at) {
  const rows = Array.from({ length: size - 1 }, (_, n) => ({
    video_id: `bulk${String(n).padStart(4, "0")}`,
    title: `Bulk capture ${n}`,
    topic: "Bulk",
    folder: `C:\\Users\\me\\Desktop\\Uoink\\Bulk\\bulk-${n}`,
  }));
  rows.splice(at, 0, row);
  return rows;
}

// `size` saved rows sharing one title, newest first: saved0 is the newest,
// saved<size-1> the oldest.
function sameTitleLibrary(size, title) {
  return Array.from({ length: size }, (_, n) => ({
    video_id: `saved${n}`,
    title,
    topic: "Standups",
    folder: `C:\\Users\\me\\Desktop\\Uoink\\Standups\\standup-${n}`,
  }));
}

// The tab loaders switchTab() runs, swapped for recorders.
const RECORDED = [
  "loadLibraryActivity",
  "startLibraryActivityTimer",
  "stopLibraryActivityTimer",
  "loadForYou",
  "loadWriting",
  "loadEvidence",
  "renderSources",
  "refreshActivity",
  "refreshSettings",
  "renderYoinkDetail",
];
// `keep` names loaders that stay real (the deep-link checks keep
// renderYoinkDetail, so they see what the item view actually renders).
function stubsFor(keep = []) {
  return RECORDED.filter((name) => !keep.includes(name))
    .map((name) => `${name} = function () { __calls.push("${name}"); };`).join("\n")
    // Activity row markup is not what the badge test is about.
    + "\njobRowHtml = function () { return \"\"; };"
    + "\nqueueRowHtml = function () { return \"\"; };"
    + "\ncompletedRowHtml = function () { return \"\"; };";
}

// One fresh dashboard page at `hash`. platform / uaPlatform feed navigator;
// `library` is what /memory/search serves; `libraryDown` makes it fail.
// onSearch(query, answer) sees each /memory/search first: it may change
// `library`, or return { status, body } to answer instead (answer() builds
// the usual body from `library` as it is then).
function makePage({ hash = "", platform = "Win32", uaPlatform = "", library = [DEEP_ROW], keep = [], libraryDown = false, onSearch = null } = {}) {
  // Every setTimeout the page asks for waits here until the test runs it.
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
  const runTimers = () => {
    for (let n = 0; timers.length && n < 50; n++) {
      const t = timers.shift();
      t.fn(...t.args);
    }
  };

  const docListeners = {};
  const winListeners = {};
  const elements = new Map();
  const document = {
    querySelector: (selector) => (selector === ".content" ? contentEl : null),
    querySelectorAll: (selector) => {
      if (selector === "[data-tab-button]") return navButtons;
      if (selector === "[data-tab-panel]") return panels;
      return [];
    },
    addEventListener(type, fn) { (docListeners[type] ||= []).push(fn); },
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase(), document),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };
  const navButtons = NAV.map((n) => {
    const button = new FakeEl("", "BUTTON", document);
    button.classList.add("nav-button");
    if (n.active) button.classList.add("active");
    if (n.current) button.setAttribute("aria-current", "page");
    button.dataset.tabButton = n.tab;
    if (n.label) button.dataset.navLabel = n.label;
    return button;
  });
  const navAround = (pos) => {
    const at = NAV.findIndex((n) => pos > n.start && pos < n.end);
    return at < 0 ? null : navButtons[at];
  };
  const getEl = (id) => {
    if (!TAGS.has(id)) return null;
    if (!elements.has(id)) {
      const el = new FakeEl(id, TAGS.get(id), document);
      elements.set(id, el);
      (CLASSES.get(id) || []).forEach((name) => el.classList.add(name));
      if (TABINDEX.has(id)) el.setAttribute("tabindex", TABINDEX.get(id));
      const own = PANELS.find((p) => p.id === id);
      if (own) el.dataset.tabPanel = own.name;
      const pos = POS.get(id);
      const nav = navAround(pos);
      if (nav) {
        el._parent = nav;
      } else {
        const host = PANELS.find((p) => p.id !== id && pos > p.start && pos < p.end);
        if (host) el._parent = getEl(host.id);
      }
      if (HEADINGS.has(id)) el._heading = getEl(HEADINGS.get(id));
    }
    return elements.get(id);
  };
  document.getElementById = getEl;
  document.body = new FakeEl("body", "BODY", document);
  document.documentElement = new FakeEl("html", "HTML", document);
  const contentEl = new FakeEl("", "MAIN", document);
  const panels = PANELS.map((p) => getEl(p.id));

  // window.location / window.history: one entry per pushState, Back and
  // Forward fire popstate and (when the hash changes) hashchange.
  const location = { hash, href: `http://127.0.0.1/dashboard${hash}`, origin: "http://127.0.0.1" };
  const entries = [{ state: null, hash }];
  let at = 0;
  let backs = 0;
  const pushes = [];
  const fire = (type, extra = {}) => {
    (winListeners[type] || []).slice().forEach((fn) => fn({ type, ...extra }));
  };
  const go = (delta) => {
    const next = at + delta;
    if (next < 0 || next >= entries.length) return;
    const before = entries[at].hash;
    at = next;
    location.hash = entries[at].hash;
    fire("popstate", { state: entries[at].state });
    if (entries[at].hash !== before) fire("hashchange");
  };
  const history = {
    get state() { return entries[at].state; },
    get length() { return entries.length; },
    pushState(state, _title, url) {
      entries.splice(at + 1);
      entries.push({ state, hash: String(url) });
      at = entries.length - 1;
      location.hash = String(url);
      pushes.push(String(url));
    },
    replaceState(state, _title, url) {
      entries[at] = { state, hash: url === undefined ? entries[at].hash : String(url) };
      location.hash = entries[at].hash;
    },
    back() { backs += 1; go(-1); },
    forward() { go(1); },
    go,
  };
  // A hash typed into the address bar: a new entry with no state.
  const typeHash = (next) => {
    entries.splice(at + 1);
    entries.push({ state: null, hash: next });
    at = entries.length - 1;
    location.hash = next;
    fire("popstate", { state: null });
    fire("hashchange");
  };

  const helper = { down: false, libraryDown, health: () => ({ ok: true, version: "3.9.1", port: 5179 }) };
  const requests = [];
  const fakeFetch = (url) => {
    const path = String(url);
    requests.push(path);
    if (path === "/token") return Promise.resolve(jsonResponse({ ok: true, token: "test-token" }));
    if (path === "/health") {
      if (helper.down) return Promise.reject(new TypeError("Failed to fetch"));
      return Promise.resolve(jsonResponse(helper.health()));
    }
    // Library search as the helper answers it: newest first, paged by
    // limit/offset, q keeping the rows whose title has every word.
    if (path.startsWith("/memory/search?")) {
      if (helper.libraryDown) return Promise.reject(new TypeError("Failed to fetch"));
      const query = new URL(path, "http://127.0.0.1").searchParams;
      const answer = () => {
        const words = String(query.get("q") || "").toLowerCase().split(/[^a-z0-9_]+/).filter(Boolean);
        const hits = library.filter((row) => words.every((word) => String(row.title || "").toLowerCase().includes(word)));
        const offset = Number(query.get("offset") || 0);
        const limit = Number(query.get("limit") || 50);
        return {
          ok: true,
          state: hits.length ? "matches" : "no_matches",
          total: hits.length,
          corpus_total: library.length,
          limit,
          offset,
          results: hits.slice(offset, offset + limit),
        };
      };
      const instead = onSearch ? onSearch(query, answer) : undefined;
      if (instead) return Promise.resolve(jsonResponse(instead.body, instead.status));
      return Promise.resolve(jsonResponse(answer()));
    }
    // An item's saved details and transcript. Ids starting "gone" are not
    // saved at all (the helper's 404 for an id its index has no row for).
    const item = /^\/yoinks\/([^/]+)\/(details|markdown)$/.exec(path);
    if (item) {
      const id = decodeURIComponent(item[1]);
      if (id.startsWith("gone")) return Promise.resolve(jsonResponse({ ok: false, error: "uoink not found" }, 404));
      const row = library.find((saved) => saved.video_id === id);
      const title = row ? row.saved_title || row.title : "Loaded item";
      if (item[2] === "markdown") return Promise.resolve(jsonResponse({ ok: true, markdown: `# ${title}` }));
      return Promise.resolve(jsonResponse({ ok: true, details: { video_id: id, title, channel: row ? row.channel || "" : "" } }));
    }
    return Promise.resolve(jsonResponse({ ok: true }));
  };

  const window = {
    addEventListener(type, fn) { (winListeners[type] ||= []).push(fn); },
    removeEventListener() {},
    dispatchEvent() {},
    setTimeout: fakeSetTimeout,
    clearTimeout: fakeClearTimeout,
    open() {},
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    innerWidth: 1280,
    innerHeight: 800,
    location,
    history,
  };
  const storage = () => {
    const m = new Map();
    return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
  };
  const navigator = {
    platform,
    userAgent: "Mozilla/5.0 (test harness)",
    clipboard: { writeText: () => Promise.resolve() },
  };
  if (uaPlatform) navigator.userAgentData = { platform: uaPlatform };
  const ctx = {
    document,
    window,
    location,
    history,
    navigator,
    localStorage: storage(),
    sessionStorage: storage(),
    console,
    fetch: fakeFetch,
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
    TextEncoder,
    CSS: { escape: (s) => String(s) },
    Event: class { constructor(type) { this.type = type; } },
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
    __calls: [],
  };
  window.document = document;
  vm.createContext(ctx);
  vm.runInContext(`${SCRIPT}
;globalThis.__page = { state, els, parseRoute, routeForTab, applyHashRoute, navigateTo, switchTab,
  openYoinkDetail, openEvidenceFor, goBack, wireRoutes, renderQueue, refreshHealth,
  lookupPage: ITEM_LOOKUP_PAGE, lookupRetryMs: ITEM_LOOKUP_RETRY_MS, lookupRetries: ITEM_LOOKUP_RETRIES,
  route: () => currentRoute };`, ctx);
  vm.runInContext(stubsFor(keep), ctx);
  const page = ctx.__page;

  return {
    page,
    state: page.state,
    els: page.els,
    calls: ctx.__calls,
    document,
    history,
    location,
    pushes,
    helper,
    requests,
    getEl,
    typeHash,
    runTimers,
    pendingTimers: () => timers.map((t) => t.ms),
    back: () => history.back(),
    forward: () => history.forward(),
    backs: () => backs,
    nav: (tab) => navButtons[NAV.findIndex((n) => n.tab === tab)],
    shown: () => PANELS.filter((p) => getEl(p.id).classList.contains("active")).map((p) => p.name).join(","),
    count: (name) => ctx.__calls.filter((call) => call === name).length,
    // A click the document-level delegation sees, as a real click bubbles to it.
    click(target, extra = {}) {
      const event = {
        type: "click",
        target,
        button: 0,
        defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; },
        stopPropagation() {},
        ...extra,
      };
      for (const fn of docListeners.click || []) fn(event);
      return event;
    },
    link(href) {
      const a = new FakeEl("", "A", document);
      a.setAttribute("href", href);
      return a;
    },
  };
}

// A page loaded the way init() starts it: routes wired, the hash applied.
function loadPage(options) {
  const p = makePage(options);
  p.page.wireRoutes();
  p.page.applyHashRoute();
  return p;
}

// ---------------------------------------------------------------------------
async function groupRoutes() {
  await scenario("every SPEC route and older link names one screen", async () => {
    const p = makePage();
    const cases = [
      ["", "library", "#library"],
      ["#", "library", "#library"],
      ["#library", "library", "#library"],
      ["#/activity", "activity", "#activity"],
      ["#item/abc123", "yoink", "#item/abc123", { id: "abc123" }],
      ["#item/a%2Fb", "yoink", "#item/a%2Fb", { id: "a/b" }],
      ["#item/", "library", "#library"],
      ["#activity", "activity", "#activity"],
      ["#tab-activity", "activity", "#activity"],
      ["#generate", "writing", "#generate", { mode: "write" }],
      ["#generate/write", "writing", "#generate", { mode: "write" }],
      ["#generate/nonsense", "writing", "#generate", { mode: "write" }],
      ["#writing", "writing", "#generate"],
      ["#build", "writing", "#generate"],
      ["#script", "writing", "#generate"],
      ["#sources", "sources", "#sources"],
      ["#settings", "settings", "#settings"],
      ["#settings/capture", "settings", "#settings/capture", { section: "capture" }],
      ["#settings/App", "settings", "#settings/app", { section: "app" }],
      ["#about", "settings", "#settings/about", { section: "about" }],
      ["#byo-key", "settings", "#settings/byo-key", { section: "byo-key" }],
      ["#for-you", "for-you", "#for-you"],
      ["#evidence/vid1", "evidence", "#evidence/vid1", { id: "vid1" }],
      ["#features", "library", "#library"],
    ];
    for (const [hash, tab, canonical, extra = {}] of cases) {
      const route = p.page.parseRoute(hash);
      const fits = Boolean(route) && route.tab === tab && route.hash === canonical
        && Object.entries(extra).every(([key, value]) => route[key] === value);
      check(fits, `${JSON.stringify(hash)} shows ${tab} at ${canonical}`, route);
    }
    for (const hash of ["#nope", "#tab-library", "#library2"]) {
      check(p.page.parseRoute(hash) === null, `${hash} names no screen`, p.page.parseRoute(hash));
    }
  });

  await scenario("a tab switch knows its own hash", async () => {
    const p = makePage();
    for (const [tab, hash] of [["library", "#library"], ["activity", "#activity"], ["writing", "#generate"],
      ["sources", "#sources"], ["settings", "#settings"], ["for-you", "#for-you"]]) {
      check(p.page.routeForTab(tab) === hash, `${tab} shows at ${hash}`, p.page.routeForTab(tab));
    }
    check(p.page.routeForTab("settings", { section: "app" }) === "#settings/app", "a Settings section has its own hash", p.page.routeForTab("settings", { section: "app" }));
    p.state.selectedYoink = { video_id: "vid 1" };
    check(p.page.routeForTab("yoink") === "#item/vid%201", "the item view is #item/<id>, id encoded", p.page.routeForTab("yoink"));
    p.state.selectedYoink = null;
    check(p.page.routeForTab("yoink") === "", "an item view with no item names no hash", p.page.routeForTab("yoink"));
    p.state.selectedEvidenceVideo = "vid2";
    check(p.page.routeForTab("evidence") === "#evidence/vid2", "Evidence is #evidence/<id>", p.page.routeForTab("evidence"));
  });
}

async function groupHistory() {
  await scenario("each move is one entry and Back walks them in order", async () => {
    const p = loadPage();
    check(p.shown() === "library" && p.state.activeTab === "library" && p.pushes.length === 0, "a fresh load shows Library without a new entry", [p.shown(), p.pushes]);
    check(p.nav("library").getAttribute("aria-current") === "page", "Library is the current nav item", p.nav("library").getAttribute("aria-current"));

    p.page.switchTab("activity");
    check(JSON.stringify(p.pushes) === JSON.stringify(["#activity"]) && p.location.hash === "#activity", "Activity pushes #activity", p.pushes);
    check(Boolean(p.history.state) && p.history.state.uoinkDepth === 1, "the entry is marked as the page's own", p.history.state);
    check(p.shown() === "activity" && p.count("refreshActivity") === 1, "Activity is on screen and loads its rows", [p.shown(), p.count("refreshActivity")]);
    check(p.nav("activity").getAttribute("aria-current") === "page" && p.nav("activity").classList.contains("active")
      && p.nav("library").getAttribute("aria-current") === null && !p.nav("library").classList.contains("active"),
      "the nav marks Activity current and Library not", [p.nav("activity").getAttribute("aria-current"), p.nav("library").getAttribute("aria-current")]);

    p.page.switchTab("writing");
    check(p.pushes[1] === "#generate" && p.shown() === "writing", "Generate pushes #generate", p.pushes);

    await p.page.openYoinkDetail({ video_id: "vid1", title: "One" });
    await settle();
    check(p.pushes[2] === "#item/vid1" && p.history.state.uoinkDepth === 3, "opening an item pushes #item/<id>", [p.pushes, p.history.state]);
    check(p.shown() === "yoink" && p.nav("library").getAttribute("aria-current") === "page", "the item view shows under Library in the nav", [p.shown(), p.nav("library").getAttribute("aria-current")]);

    const pushed = p.pushes.length;
    const writingLoads = p.count("loadWriting");
    p.back();
    check(p.shown() === "writing" && p.page.route() === "#generate", "Back returns to Generate", [p.shown(), p.page.route()]);
    check(p.count("loadWriting") === writingLoads + 1, "Generate loads once though Back fires popstate and hashchange", p.count("loadWriting") - writingLoads);
    p.back();
    check(p.shown() === "activity", "Back again returns to Activity", p.shown());
    p.back();
    check(p.shown() === "library" && p.state.activeTab === "library", "Back again returns to the first, hash-less Library entry", p.shown());
    check(p.pushes.length === pushed, "Back never adds an entry", p.pushes);
    p.forward();
    check(p.shown() === "activity" && p.pushes.length === pushed, "Forward shows Activity again without an entry", [p.shown(), p.pushes]);
  });

  await scenario("Back to an item already open shows it without fetching it again", async () => {
    const p = loadPage();
    await p.page.openYoinkDetail({ video_id: "vid2" });
    await settle();
    p.page.openEvidenceFor("vid2", "Two");
    check(p.pushes[p.pushes.length - 1] === "#evidence/vid2" && p.shown() === "evidence", "Evidence pushes #evidence/<id>", [p.pushes, p.shown()]);
    const fetched = p.requests.filter((path) => path === "/yoinks/vid2/details").length;
    p.back();
    await settle();
    check(p.shown() === "yoink" && p.state.selectedYoink && p.state.selectedYoink.video_id === "vid2", "Back from Evidence shows the item again", [p.shown(), p.state.selectedYoink]);
    check(p.requests.filter((path) => path === "/yoinks/vid2/details").length === fetched, "the item is not fetched twice", p.requests);
  });

  await scenario("a deep link to an item opens it on load", async () => {
    const p = loadPage({ hash: "#item/vid9" });
    await settle();
    check(p.shown() === "yoink" && p.state.selectedYoink && p.state.selectedYoink.video_id === "vid9", "#item/<id> opens that item", [p.shown(), p.state.selectedYoink]);
    check(p.requests.includes("/yoinks/vid9/details") && p.requests.includes("/yoinks/vid9/markdown"), "the item's details and transcript load", p.requests);
    check(p.pushes.length === 0 && p.page.route() === "#item/vid9", "a deep link adds no entry", p.pushes);
    p.page.goBack();
    check(p.shown() === "library" && JSON.stringify(p.pushes) === JSON.stringify(["#library"]), "the item's Back on a fresh deep link goes to Library", [p.shown(), p.pushes]);
    check(p.backs() === 0, "and does not leave the dashboard through history.back()", p.backs());
  });

  await scenario("the item's Back button uses the browser's Back after an in-app move", async () => {
    const p = loadPage();
    p.page.switchTab("sources");
    await p.page.openYoinkDetail({ video_id: "vid3" });
    await settle();
    const pushed = p.pushes.length;
    check((p.els.yoinkBack._listeners.click || []).length === 1, "wireRoutes binds the item view's Back button", (p.els.yoinkBack._listeners.click || []).length);
    p.els.yoinkBack.click();
    check(p.backs() === 1 && p.shown() === "sources", "Back on the item returns to Sources", [p.backs(), p.shown()]);
    check(p.pushes.length === pushed, "and adds no entry", p.pushes);
  });

  await scenario("#settings/<section> shows Settings at that section", async () => {
    const p = loadPage({ hash: "#settings/app" });
    check(p.shown() === "settings" && p.count("refreshSettings") === 1 && p.pushes.length === 0, "a deep link to Settings > App opens Settings", [p.shown(), p.pushes]);
    p.runTimers();
    check(p.getEl("settings-app")._scrolls === 1, "the App section scrolls into view", p.getEl("settings-app")._scrolls);
    check(p.document.activeElement === p.getEl("settingsAppTitle"), "focus lands on the App heading", describe(p.document.activeElement));

    p.typeHash("#about");
    p.runTimers();
    check(p.page.route() === "#settings/about" && p.shown() === "settings", "the old #about lands on Settings > About", [p.page.route(), p.shown()]);
    check(p.getEl("settings-about")._scrolls === 1 && p.document.activeElement === p.getEl("settings-about"), "About scrolls into view and takes focus", [p.getEl("settings-about")._scrolls, describe(p.document.activeElement)]);
    check(p.count("refreshSettings") === 1, "moving within Settings does not reload it", p.count("refreshSettings"));

    p.typeHash("#settings/byo-key");
    p.runTimers();
    check(p.getEl("byo-key")._scrolls === 1, "#settings/byo-key still reaches the key block", p.getEl("byo-key")._scrolls);

    p.typeHash("#settings/nowhere");
    p.runTimers();
    check(p.shown() === "settings", "an unknown section still shows Settings", p.shown());

    p.typeHash("#nope");
    check(p.shown() === "library", "a typed hash that names no screen shows Library", p.shown());
  });
}

// The item view's actions; none may work before the saved row is found.
const ITEM_ACTIONS = ["yoinkOpenFolder", "yoinkOpenMarkdown", "yoinkRetryCapture", "yoinkEvidence", "yoinkWriteFrom", "yoinkRetranscribe"];

function searchesOf(p) {
  return p.requests.filter((path) => path.startsWith("/memory/search?"))
    .map((path) => new URL(path, "http://127.0.0.1").searchParams);
}

async function groupDeeplink() {
  await scenario("a fresh #item/<id> finds the saved row before the item renders", async () => {
    const p = loadPage({ hash: "#item/vid9", keep: ["renderYoinkDetail"] });
    // Library has not answered yet: the item view says it is looking.
    check(p.shown() === "yoink" && p.els.yoinkHeading.textContent === "Opening this uoink", "the item view says it is looking the item up", [p.shown(), p.els.yoinkHeading.textContent]);
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action is off while it looks", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
    check(!p.els.yoinkFacts.innerHTML.includes("Uncategorized"), "no id-only stand-in reads Uncategorized", p.els.yoinkFacts.innerHTML);
    await settle();
    const row = p.state.selectedYoink;
    check(Boolean(row) && row.folder === DEEP_ROW.folder && row.topic === "Research", "the item opens with its saved Library row", row);
    check(!p.els.yoinkOpenFolder.disabled, "Open folder works", p.els.yoinkOpenFolder.disabled);
    check(p.els.yoinkFacts.innerHTML.includes("Research") && !p.els.yoinkFacts.innerHTML.includes("Uncategorized"), "the saved topic shows, not Uncategorized", p.els.yoinkFacts.innerHTML);
    check(p.els.yoinkTitle.textContent === "Deep link interview", "the saved title shows", p.els.yoinkTitle.textContent);
    check(p.pushes.length === 0 && p.page.route() === "#item/vid9", "the lookup adds no history entry", [p.pushes, p.page.route()]);
    check(searchesOf(p).length === 1, "a recent item is found on Library's first page", searchesOf(p).map(String));
  });

  await scenario("an older item is found by its saved title", async () => {
    const p = loadPage({ hash: "#item/old1", library: bigLibrary(450, OLD_ROW, 300), keep: ["renderYoinkDetail"] });
    await settle();
    const row = p.state.selectedYoink;
    check(Boolean(row) && row.video_id === "old1" && row.folder === OLD_ROW.folder, "the older item opens with its saved row", row);
    check(p.els.yoinkFacts.innerHTML.includes("Pricing") && !p.els.yoinkOpenFolder.disabled, "its topic shows and Open folder works", [p.els.yoinkFacts.innerHTML, p.els.yoinkOpenFolder.disabled]);
    const searches = searchesOf(p);
    check(searches.length === 2 && searches[1].get("q") === OLD_ROW.title, "one newest page, then one search by its saved title", searches.map(String));
  });

  await scenario("an item Library does not have says so, with every action off", async () => {
    const p = loadPage({ hash: "#item/gone1", keep: ["renderYoinkDetail"] });
    await settle();
    check(p.state.selectedYoink === null && p.els.yoinkHeading.textContent === "Uoink couldn't find this item", "the item view says nothing saved matches", [p.state.selectedYoink, p.els.yoinkHeading.textContent]);
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action stays off", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
    check(!p.els.yoinkFacts.innerHTML.includes("Uncategorized"), "no stand-in facts are shown", p.els.yoinkFacts.innerHTML);
    check(!p.requests.some((path) => path.startsWith("/yoinks/gone1/")), "nothing is loaded for an item Library does not have", p.requests);
  });

  await scenario("a Library that does not answer says so", async () => {
    const p = loadPage({ hash: "#item/vid9", libraryDown: true, keep: ["renderYoinkDetail"] });
    await settle();
    check(p.state.selectedYoink === null && p.els.yoinkHeading.textContent === "Couldn't open this uoink", "the item view says it couldn't open the item", [p.state.selectedYoink, p.els.yoinkHeading.textContent]);
    check(p.els.yoinkSubhead.textContent.includes("Reload this page"), "and says what to do", p.els.yoinkSubhead.textContent);
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action stays off", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
  });

  await scenario("an older item whose title many items share is found however far back it is", async () => {
    // The review's case: 2,201 saved items with one title. The oldest sits
    // past the newest 2,000 rows and past the first 50 title matches.
    const size = 2201;
    const p = loadPage({ hash: "#item/saved2200", library: sameTitleLibrary(size, "Weekly standup"), keep: ["renderYoinkDetail"] });
    await settle();
    const row = p.state.selectedYoink;
    check(Boolean(row) && row.video_id === "saved2200" && row.folder.endsWith("\\standup-2200"), "the oldest item opens with its own saved row", row);
    check(p.els.yoinkHeading.textContent !== "Uoink couldn't find this item" && !p.els.yoinkOpenFolder.disabled, "it is not reported missing and Open folder works", [p.els.yoinkHeading.textContent, p.els.yoinkOpenFolder.disabled]);
    check(p.els.yoinkFacts.innerHTML.includes("Standups"), "its saved topic shows", p.els.yoinkFacts.innerHTML);
    const searches = searchesOf(p);
    const byTitle = searches.filter((q) => q.get("q") === "Weekly standup");
    const offsets = byTitle.map((q) => Number(q.get("offset")));
    const expected = Array.from({ length: Math.ceil(size / p.page.lookupPage) }, (_, n) => n * p.page.lookupPage);
    check(JSON.stringify(offsets) === JSON.stringify(expected), "every page of title matches is read, in order, until the item turns up", offsets);
    check(searches.length === byTitle.length + 1, "one newest page first; the title pages find it", searches.map(String));
  });

  await scenario("an older item the title search misses is found by reading Library to the end", async () => {
    // Its saved details carry the title it was captured with, the index a
    // newer one, and Library leaves out rows it cannot show, so every
    // newest-first page comes back three rows short of the page size.
    const size = 1500;
    const p = loadPage({
      hash: "#item/renamed1",
      library: bigLibrary(size, RENAMED_ROW, 1450),
      keep: ["renderYoinkDetail"],
      onSearch: (query, answer) => {
        const body = answer();
        if (!query.get("q")) body.results = body.results.slice(3);
        return { status: 200, body };
      },
    });
    await settle();
    const row = p.state.selectedYoink;
    check(Boolean(row) && row.video_id === "renamed1" && row.folder === RENAMED_ROW.folder, "the item opens with its saved row", row);
    check(p.els.yoinkFacts.innerHTML.includes("Interviews") && !p.els.yoinkOpenFolder.disabled, "its topic shows and Open folder works", [p.els.yoinkFacts.innerHTML, p.els.yoinkOpenFolder.disabled]);
    const searches = searchesOf(p);
    check(searches.filter((q) => q.get("q")).length === 1 && searches.some((q) => q.get("q") === "Original upload name"), "the search by its saved title comes back empty", searches.map(String));
    const newest = searches.filter((q) => !q.get("q")).map((q) => Number(q.get("offset")));
    check(JSON.stringify(newest) === JSON.stringify([0, 200, 400, 600, 800, 1000, 1200, 1400]), "short pages are not the end: newest-first pages step by the page size until it turns up", newest);
  });

  await scenario("an item the helper has no record of is settled by its id after one page", async () => {
    const size = 3000;
    const p = loadPage({ hash: "#item/gone-far", library: bigLibrary(size, OLD_ROW, size - 1), keep: ["renderYoinkDetail"] });
    await settle();
    check(p.state.selectedYoink === null && p.els.yoinkHeading.textContent === "Uoink couldn't find this item", "the item view says nothing saved matches", [p.state.selectedYoink, p.els.yoinkHeading.textContent]);
    check(p.requests.includes("/yoinks/gone-far/details"), "the helper is asked for the item by its id", p.requests);
    check(searchesOf(p).length === 1, "its 'no item under this id' answer ends the lookup without reading all of Library", searchesOf(p).map(String));
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action stays off", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
  });

  await scenario("an item Library search never lists is called missing only once every page is read", async () => {
    // The helper still has its details (a trashed item, say), but Library
    // search does not list it.
    const p = loadPage({ hash: "#item/trashed1", library: bigLibrary(1000, OLD_ROW, 5), keep: ["renderYoinkDetail"] });
    await settle();
    check(p.els.yoinkHeading.textContent === "Uoink couldn't find this item", "after the last page the item view says nothing matches", p.els.yoinkHeading.textContent);
    const newest = searchesOf(p).filter((q) => !q.get("q")).map((q) => Number(q.get("offset")));
    check(JSON.stringify(newest) === JSON.stringify([0, 200, 400, 600, 800]), "every newest-first page was read first", newest);
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action stays off", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
  });

  await scenario("a Library page that fails part-way is not read as not found", async () => {
    const p = loadPage({
      hash: "#item/trashed2",
      library: bigLibrary(1000, OLD_ROW, 5),
      keep: ["renderYoinkDetail"],
      onSearch: (query) => (!query.get("q") && query.get("offset") === "600"
        ? { status: 503, body: { ok: false, error: "search failed", state: "unavailable" } }
        : undefined),
    });
    await settle();
    check(p.els.yoinkHeading.textContent === "Couldn't open this uoink", "the item view says it couldn't open the item, not that it is missing", p.els.yoinkHeading.textContent);
    check(!searchesOf(p).some((q) => q.get("offset") === "800"), "the lookup stops at the failed page", searchesOf(p).map(String));
    check(ITEM_ACTIONS.every((id) => p.els[id].disabled), "every item action stays off", ITEM_ACTIONS.filter((id) => !p.els[id].disabled));
  });

  await scenario("a Library that shrinks during the lookup is not read as not found", async () => {
    // Items deleted from the top while the lookup reads move the rest up,
    // so one could slide past the pages already read.
    const library = bigLibrary(1000, OLD_ROW, 5);
    let deleted = false;
    const p = loadPage({
      hash: "#item/trashed3",
      library,
      keep: ["renderYoinkDetail"],
      onSearch: (query) => {
        if (!deleted && !query.get("q") && query.get("offset") === "400") {
          deleted = true;
          library.splice(10, 3);
        }
        return undefined;
      },
    });
    await settle();
    check(deleted && p.els.yoinkHeading.textContent === "Couldn't open this uoink", "the item view says it couldn't open the item, not that it is missing", [deleted, p.els.yoinkHeading.textContent]);
    check(!searchesOf(p).some((q) => q.get("offset") === "600"), "the lookup stops once Library changed", searchesOf(p).map(String));
  });

  await scenario("a rate-limited Library page waits, then the lookup carries on", async () => {
    const limited = (times) => {
      let left = times;
      return (query) => {
        if (query.get("offset") !== "1000" || left <= 0) return undefined;
        left -= 1;
        return { status: 429, body: { ok: false, error: "too many requests" } };
      };
    };
    const at1000 = (p) => searchesOf(p).filter((q) => q.get("offset") === "1000").length;

    const p = loadPage({ hash: "#item/saved2200", library: sameTitleLibrary(2201, "Weekly standup"), keep: ["renderYoinkDetail"], onSearch: limited(2) });
    await settle();
    check(p.state.selectedYoink === null && p.els.yoinkHeading.textContent === "Opening this uoink", "a 429 is no answer: the item view is still looking", [p.state.selectedYoink, p.els.yoinkHeading.textContent]);
    check(p.pendingTimers().includes(p.page.lookupRetryMs), "the lookup waits before it asks again", p.pendingTimers());
    p.runTimers();
    await settle();
    check(at1000(p) === 2 && p.state.selectedYoink === null, "a second 429 waits again", [at1000(p), p.state.selectedYoink]);
    p.runTimers();
    await settle();
    const row = p.state.selectedYoink;
    check(Boolean(row) && row.video_id === "saved2200" && at1000(p) === 3, "then it carries on from the same page and finds the item", [row, at1000(p)]);

    const q = loadPage({ hash: "#item/saved2200", library: sameTitleLibrary(2201, "Weekly standup"), keep: ["renderYoinkDetail"], onSearch: limited(Infinity) });
    for (let n = 0; n < q.page.lookupRetries + 5; n++) {
      q.runTimers();
      await settle();
    }
    check(q.state.selectedYoink === null && q.els.yoinkHeading.textContent === "Couldn't open this uoink", "a rate limit that never lifts ends as couldn't open, never as not found", [q.state.selectedYoink, q.els.yoinkHeading.textContent]);
    check(at1000(q) === q.page.lookupRetries + 1, "after a bounded number of waits", at1000(q));

    const r = loadPage({ hash: "#item/saved2200", library: sameTitleLibrary(2201, "Weekly standup"), keep: ["renderYoinkDetail"], onSearch: limited(Infinity) });
    await settle();
    r.page.switchTab("activity");
    const before = searchesOf(r).length;
    r.runTimers();
    await settle();
    check(r.shown() === "activity" && searchesOf(r).length === before && r.state.selectedYoink === null, "moving elsewhere during a wait ends the lookup", [r.shown(), searchesOf(r).length, before]);
  });

  await scenario("moving elsewhere while the lookup runs wins", async () => {
    const p = loadPage({ hash: "#item/vid9", keep: ["renderYoinkDetail"] });
    p.page.switchTab("activity");
    await settle();
    check(p.shown() === "activity" && p.state.selectedYoink === null, "Activity stays on screen; the late answer opens nothing", [p.shown(), p.state.selectedYoink]);
    check(!p.requests.includes("/yoinks/vid9/details"), "the item is not loaded behind Activity", p.requests);
    check(JSON.stringify(p.pushes) === JSON.stringify(["#activity"]), "only the move to Activity is in history", p.pushes);

    const q = loadPage({ hash: "#item/vid9", keep: ["renderYoinkDetail"] });
    await q.page.openYoinkDetail({ video_id: "vid3", title: "Picked from Library", folder: "C:\\Users\\me\\Desktop\\Uoink\\Misc\\picked" });
    await settle();
    check(q.state.selectedYoink && q.state.selectedYoink.video_id === "vid3" && q.page.route() === "#item/vid3", "an item opened meanwhile stays open", [q.state.selectedYoink, q.page.route()]);
  });

  await scenario("the item view's Back goes to Library from a fresh deep link", async () => {
    const p = loadPage({ hash: "#item/gone2", keep: ["renderYoinkDetail"] });
    await settle();
    p.els.yoinkBack.click();
    check(p.shown() === "library" && JSON.stringify(p.pushes) === JSON.stringify(["#library"]), "Back shows Library with one entry", [p.shown(), p.pushes]);
    check(p.backs() === 0, "and does not leave the dashboard through history.back()", p.backs());
  });
}

async function groupLinks() {
  await scenario("in-app hash links push one entry and are not followed twice", async () => {
    const p = loadPage();
    const forYou = p.click(p.link("#for-you"));
    check(forYou.defaultPrevented && JSON.stringify(p.pushes) === JSON.stringify(["#for-you"]), "the Library's For You link pushes #for-you once", p.pushes);
    check(p.shown() === "for-you" && p.count("loadForYou") === 1, "For You is on screen and loads", [p.shown(), p.count("loadForYou")]);
    check(p.nav("library").getAttribute("aria-current") === "page", "For You shows under Library in the nav", p.nav("library").getAttribute("aria-current"));

    const bare = p.click(p.link("#"));
    check(!bare.defaultPrevented && p.pushes.length === 1, "a bare # link is left alone", p.pushes);
    const unknown = p.click(p.link("#nope"));
    check(!unknown.defaultPrevented && p.pushes.length === 1, "a link to no screen is left to the browser", p.pushes);
    const ctrl = p.click(p.link("#activity"), { ctrlKey: true });
    check(!ctrl.defaultPrevented && p.pushes.length === 1, "a ctrl-click keeps its new-tab meaning", p.pushes);

    const activity = p.click(p.link("#activity"));
    check(activity.defaultPrevented && p.shown() === "activity" && p.pushes[1] === "#activity", "Sources' View in Activity link opens Activity", [p.shown(), p.pushes]);

    const capture = p.click(p.link("#settings/capture"));
    p.runTimers();
    check(capture.defaultPrevented && p.shown() === "settings" && p.pushes[2] === "#settings/capture", "a Settings section link opens Settings once", [p.shown(), p.pushes]);
    check(p.document.activeElement === p.getEl("settingsCaptureTitle"), "focus lands on the Capture heading", describe(p.document.activeElement));
    const ai = p.click(p.link("#settings/ai"));
    p.runTimers();
    check(ai.defaultPrevented && p.pushes[3] === "#settings/ai" && p.document.activeElement === p.getEl("settingsAiTitle"), "the next section link moves within Settings", [p.pushes, describe(p.document.activeElement)]);
    p.back();
    p.runTimers();
    check(p.page.route() === "#settings/capture" && p.document.activeElement === p.getEl("settingsCaptureTitle"), "Back returns to the Capture section", [p.page.route(), describe(p.document.activeElement)]);
  });
}

async function groupBadge() {
  await scenario("Activity says how many captures failed", async () => {
    const p = makePage();
    const badge = p.els.activityFailedBadge;
    check(Boolean(badge) && badge.classList.contains("hidden"), "the badge ships hidden inside the Activity nav item", badge && [...badge.classList._set]);
    check(badge.closest("button") === p.nav("activity"), "the badge sits in the Activity nav button", describe(badge.closest("button")));
    p.state.jobs = [
      { id: "j1", state: "failed", video_id: "aaaaaaaaaaa", title: "A" },
      { id: "j2", state: "error", video_id: "bbbbbbbbbbb", title: "B" },
      { id: "j3", state: "cancelled", video_id: "ccccccccccc", title: "C" },
      { id: "j4", state: "running", video_id: "ddddddddddd", title: "D" },
    ];
    p.page.renderQueue({
      ok: true,
      pending: [
        { pending_id: "p1", status: "failed", video_id: "aaaaaaaaaaa" },
        { pending_id: "p2", status: "failed", video_id: "eeeeeeeeeee" },
        { pending_id: "p3", status: "queued", video_id: "fffffffffff" },
      ],
    });
    check(badge.textContent === "3 failed" && !badge.classList.contains("hidden"), "two failed jobs plus one other failed queue row read 3 failed", badge.textContent);
    check(badge.title === "3 failed captures in Activity", "the badge says what it counts", badge.title);
    check(p.els.activityNavCount.textContent === "2", "the in-flight count still counts running and queued work", p.els.activityNavCount.textContent);
    check(p.nav("activity").getAttribute("aria-label") === "Activity, 2 active jobs, 3 failed", "the nav item's name says it in words", p.nav("activity").getAttribute("aria-label"));

    p.state.jobs = [{ id: "j3", state: "cancelled", video_id: "ccccccccccc" }];
    p.page.renderQueue({ ok: true, pending: [] });
    check(badge.textContent === "" && badge.classList.contains("hidden"), "no failures, no badge (cancelled is not a failure)", [badge.textContent, [...badge.classList._set]]);
    check(p.nav("activity").getAttribute("aria-label") === "Activity, 0 active jobs", "the nav item's name drops the failures", p.nav("activity").getAttribute("aria-label"));

    p.state.jobs = [{ id: "j5", state: "failed", url: "https://example.com/post", title: "Post" }];
    p.page.renderQueue({});
    check(badge.textContent === "1 failed" && badge.title === "1 failed capture in Activity", "one failure reads 1 failed", [badge.textContent, badge.title]);
    check(p.nav("activity").getAttribute("aria-label") === "Activity, 0 active jobs, 1 failed", "the name is rebuilt, not appended twice", p.nav("activity").getAttribute("aria-label"));
  });
}

async function groupStatus() {
  await scenario("Windows: running on this PC, offline says the Start menu", async () => {
    const p = makePage({ platform: "Win32" });
    const pill = p.els.runningPill;
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Running on this PC", "running reads Running on this PC", p.els.helperStatusText.textContent);
    check(pill.classList.contains("online") && !pill.classList.contains("offline"), "the dot is the running one", [...pill.classList._set]);
    check(p.els.helperOfflineFix.classList.contains("hidden") && p.els.helperOfflineFix.textContent === "", "no fix line while running", p.els.helperOfflineFix.textContent);

    p.helper.down = true;
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Uoink is offline" && pill.classList.contains("offline") && !pill.classList.contains("online"), "a failed /health reads Uoink is offline", [p.els.helperStatusText.textContent, [...pill.classList._set]]);
    check(p.els.helperOfflineFix.textContent === "Start Uoink from the Start menu. This page reconnects by itself." && !p.els.helperOfflineFix.classList.contains("hidden"), "offline says how to start Uoink on Windows", p.els.helperOfflineFix.textContent);

    const writes = [p.els.helperStatusText._writes, p.els.helperOfflineFix._writes];
    await p.page.refreshHealth();
    check(p.els.helperStatusText._writes === writes[0] && p.els.helperOfflineFix._writes === writes[1], "the next poll leaves an unchanged status alone", [p.els.helperStatusText._writes, p.els.helperOfflineFix._writes, writes]);

    p.helper.down = false;
    p.helper.health = () => ({ ok: false });
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Uoink is offline", "a helper that answers ok:false is offline too", p.els.helperStatusText.textContent);
    p.helper.health = () => ({ ok: true, version: "3.9.1" });
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Running on this PC" && p.els.helperOfflineFix.classList.contains("hidden"), "coming back reads running again", p.els.helperStatusText.textContent);
  });

  // No Mac or Linux build ships (docs/mac-install.md), so there is no app to
  // open: offline says so and names the source run's restart instead.
  const SOURCE_FIX = "Uoink ships for Windows only. If you ran it from source, start python server.py again. This page reconnects by itself.";

  await scenario("macOS: running on this Mac, offline names the source run", async () => {
    const p = makePage({ platform: "MacIntel", uaPlatform: "macOS" });
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Running on this Mac", "running reads Running on this Mac", p.els.helperStatusText.textContent);
    p.helper.down = true;
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Uoink is offline" && !p.els.helperOfflineFix.classList.contains("hidden"), "offline reads Uoink is offline with a fix line", [p.els.helperStatusText.textContent, [...p.els.helperOfflineFix.classList._set]]);
    check(p.els.helperOfflineFix.textContent === SOURCE_FIX, "offline on macOS says Uoink is Windows-only and how a source run restarts", p.els.helperOfflineFix.textContent);
    check(!p.els.helperOfflineFix.textContent.includes("Start menu") && !p.els.helperOfflineFix.textContent.includes("Applications"), "no Windows launcher and no Mac app that does not exist", p.els.helperOfflineFix.textContent);
  });

  await scenario("Linux: running on this computer, offline names the source run", async () => {
    const p = makePage({ platform: "Linux x86_64" });
    await p.page.refreshHealth();
    check(p.els.helperStatusText.textContent === "Running on this computer", "running reads Running on this computer", p.els.helperStatusText.textContent);
    p.helper.down = true;
    await p.page.refreshHealth();
    check(p.els.helperOfflineFix.textContent === SOURCE_FIX, "offline on Linux says Uoink is Windows-only and how a source run restarts", p.els.helperOfflineFix.textContent);
    check(!p.els.helperOfflineFix.textContent.includes("Start menu"), "no Windows launcher on Linux", p.els.helperOfflineFix.textContent);
  });
}

const GROUPS = {
  routes: groupRoutes,
  history: groupHistory,
  deeplink: groupDeeplink,
  links: groupLinks,
  badge: groupBadge,
  status: groupStatus,
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
