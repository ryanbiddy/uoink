// Library + Reader harness (UI re-haul, SPEC "Library"): one box that
// searches or, holding a link, captures it; the type chips and the one sort
// control; list rows with one state line and B's 5-step strip; the Reader
// (title, meta, source link, the Whisper / missing-captions note, the whole
// transcript with its times in the gutter and screenshots where they were
// taken, comments and analysis below); the list beside the reader.
//
// Runs the REAL dashboard script (everything before init()) in a node:vm
// context over a fake page: every id the markup declares, the tab panels and
// nav buttons, and a document whose click listeners can be fired with a
// target that answers closest() for the selectors a scenario names. The tab
// loaders a switch runs (For You, Generate, Settings, ...) are swapped for
// recorders; the Library, capture and Reader code is the page's own.
//
//   paste  -- a pasted link is a capture, never a search: /detect names it,
//             Enter or "Uoink it" posts it to the route /detect gave (a
//             playlist link to /playlist/start), the box clears, the capture
//             shows as a row until it is saved or fails; a link Uoink can't
//             capture says so and posts nothing; plain text still searches
//   kinds  -- a type chip asks the helper for that group (kind=) and marks
//             itself pressed; the sort control asks the helper for its order
//             (sort=), never re-sorting the page on screen
//   rows   -- saved rows say "Done" and where the words came from; captures
//             on their way say Capturing / Waiting / Failed with the step in
//             words, and the strip moves only when a step really advanced
//   reader -- the transcript reads as paragraphs with stored times linked to
//             the source, screenshots sit at their times, the note explains
//             Whisper or missing captions from transcript_source and its
//             reason, comments and analysis fill their sections, Markdown
//             copies, and an untimed transcript never invents a time
//   split  -- the list stays beside an open item (the reading class) with
//             the open row marked; the topic list shows beside Library only
//   live   -- a pasted video's row follows the phase the helper reports for
//             it (/jobs live_captures, matched by the capture_ref it sent),
//             the poll leaves the job list to the stream, and the page stops
//             asking once it is saved
//   saves  -- a playlist video or a queued capture saving in the background
//             reloads Library and its topic counts; failures and repaints
//             reload nothing
//   reconcile -- a failed paste shows once, as the helper's job, with one
//             Retry; an older failure of a link pasted again steps aside
//   retry  -- an immediate retry cannot hand its running row to the previous
//             same-URL job; its own live phases keep polling
//   errors -- local and helper failures show a cause and a native Details
//             disclosure, using only sanitized error fields and escaped text
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/rehaul_library_reader_test.mjs [group ...]
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
const DETECT_WAIT_MS = 300; // the box asks /detect 220 ms after the last edit
const DEBOUNCE_WAIT_MS = 320; // the Library search debounce is 260 ms
const POLL_LIMIT_MS = 5000; // a running paste reads /jobs every 1.5 s

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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle() {
  for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r));
}

// ---- What the markup declares ---------------------------------------------
const TAGS = new Map();
const PANELS = [];
const NAV = [];
const KIND_CHIPS = [];
{
  let m;
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (id && !TAGS.has(id[1])) TAGS.set(id[1], m[1].toUpperCase());
  }
  const panelRe = /<section\b[^>]*\bdata-tab-panel="([^"]+)"[^>]*>/g;
  while ((m = panelRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[0]);
    if (id) PANELS.push({ id: id[1], name: m[1], active: /\sclass="[^"]*\bactive\b/.test(m[0]) });
  }
  const navRe = /<button\b[^>]*\bdata-tab-button="([^"]+)"[^>]*>/g;
  while ((m = navRe.exec(MARKUP)) !== null) NAV.push(m[1]);
  const chipRe = /<button class="kind-chip" type="button" data-library-kind="([^"]*)" aria-pressed="(true|false)">([^<]*)<\/button>/g;
  while ((m = chipRe.exec(MARKUP)) !== null) KIND_CHIPS.push({ kind: m[1], pressed: m[2], label: m[3] });
}

class FakeClassList {
  constructor(names = []) { this._set = new Set(names); }
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
  constructor(id, tag) {
    this.id = id;
    this.tagName = tag || "DIV";
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.title = "";
    this.href = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.open = false;
    this.scrollTop = 0;
    this.files = [];
    this.options = [];
    this.dataset = {};
    this.style = {};
    this.classList = new FakeClassList();
    this._attrs = {};
    this._listeners = {};
    // Selectors closest() answers with this element (a scenario sets them).
    this._matches = [];
    // Elements querySelectorAll() answers (a scenario sets them).
    this._children = [];
    this._focused = 0;
  }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  dispatch(type, extra = {}) {
    const event = { type, target: this, currentTarget: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, ...extra };
    for (const fn of this._listeners[type] || []) fn(event);
    return event;
  }
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
  querySelectorAll() { return this._children.slice(); }
  closest(selector) {
    const parts = String(selector).split(",").map((s) => s.trim());
    return parts.some((part) => this._matches.includes(part)) ? this : null;
  }
  contains() { return false; }
  setCustomValidity() {}
  focus() { this._focused += 1; }
  blur() {}
  select() {}
  click() { this.dispatch("click"); }
  scrollIntoView() {}
  append() {}
  appendChild(child) { return child; }
  remove() {}
  insertAdjacentHTML() {}
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    body: null,
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => ({}),
  };
}

// What /detect answers, as server.py's _classify_capture_url does.
function detectAnswer(raw) {
  if (/youtube\.com\/playlist\?list=/.test(raw)) {
    return { ok: true, source: "youtube_playlist", label: "YouTube playlist", endpoint: "/playlist/start", payload_key: "url", canonical: raw, note: "Captures every video in the playlist, up to the cap.", platform: "youtube" };
  }
  if (/youtube\.com\/watch\?v=|youtu\.be\//.test(raw)) {
    return { ok: true, source: "youtube_video", label: "YouTube video", endpoint: "/extract", payload_key: "url", canonical: raw, note: "", platform: "youtube" };
  }
  return { ok: false, source: "unsupported", label: "", endpoint: null, payload_key: null, canonical: "", note: "Uoink can't capture that link yet." };
}

const RECORDED = [
  "loadLibraryActivity", "startLibraryActivityTimer", "stopLibraryActivityTimer",
  "loadForYou", "loadWriting", "loadEvidence", "renderSources", "refreshSettings",
];

// One fresh dashboard page per scenario. `files` answers GET paths exactly
// (details, markdown); `extract` decides how POST /extract answers;
// `jobsAnswer()` is the /jobs body at the moment it is asked.
function makePage({ files = {}, extract = null, searchRows = [], jobsAnswer = null } = {}) {
  const elements = new Map();
  const panels = new Map();
  for (const panel of PANELS) {
    const el = new FakeEl(panel.id, "SECTION");
    el.dataset.tabPanel = panel.name;
    if (panel.active) el.classList.add("active");
    panels.set(panel.id, el);
    elements.set(panel.id, el);
  }
  const navButtons = NAV.map((tab) => {
    const el = new FakeEl("", "BUTTON");
    el.dataset.tabButton = tab;
    return el;
  });
  const getEl = (id) => {
    if (!elements.has(id)) elements.set(id, new FakeEl(id, TAGS.get(id)));
    return elements.get(id);
  };
  // The type chips, as the markup declares them.
  const chips = KIND_CHIPS.map((chip) => {
    const el = new FakeEl("", "BUTTON");
    el.dataset.libraryKind = chip.kind;
    el.textContent = chip.label;
    el.setAttribute("aria-pressed", chip.pressed);
    el._matches = ["[data-library-kind]"];
    return el;
  });
  getEl("libraryKinds")._children = chips;

  const docListeners = {};
  const document = {
    getElementById: getEl,
    querySelector: () => null,
    querySelectorAll: (selector) => {
      if (selector === "[data-tab-button]") return navButtons.slice();
      if (selector === "[data-tab-panel]") return [...panels.values()];
      return [];
    },
    addEventListener(type, fn) { (docListeners[type] ||= []).push(fn); },
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase()),
    body: new FakeEl("body", "BODY"),
    documentElement: new FakeEl("html", "HTML"),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };

  const requests = [];
  const held = [];
  const fakeFetch = (url, opts = {}) => {
    const path = String(url);
    const method = (opts && opts.method) || "GET";
    requests.push({ path, method, body: opts && opts.body ? String(opts.body) : "" });
    if (path === "/token") return Promise.resolve(jsonResponse({ ok: true, token: "test-token" }));
    if (path.startsWith("/jobs")) return Promise.resolve(jsonResponse(jobsAnswer ? jobsAnswer() : { ok: true, jobs: [] }));
    if (path.startsWith("/queue/status")) return Promise.resolve(jsonResponse({ ok: true, pending: [] }));
    if (path.startsWith("/detect?url=")) {
      const raw = decodeURIComponent(path.slice("/detect?url=".length));
      return Promise.resolve(jsonResponse(detectAnswer(raw)));
    }
    if (path.startsWith("/memory/search")) {
      return Promise.resolve(jsonResponse({ ok: true, results: searchRows, total: searchRows.length, corpus_total: 40, state: searchRows.length ? "matches" : "no_matches" }));
    }
    if (method === "POST" && path === "/playlist/start") return Promise.resolve(jsonResponse({ ok: true, job_id: "job_pl1" }));
    if (method === "POST" && path === "/extract") {
      return new Promise((resolve) => held.push({ path, body: opts.body, answer: (body, status = 200) => resolve(jsonResponse(body, status)) }));
    }
    if (Object.prototype.hasOwnProperty.call(files, path)) return Promise.resolve(jsonResponse(files[path]));
    return Promise.resolve(jsonResponse({ ok: true }));
  };

  const opened = [];
  const clipboard = [];
  const storage = () => {
    const m = new Map();
    return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
  };
  const window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    open(url) { opened.push(String(url)); },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    innerWidth: 1440,
    innerHeight: 900,
    location: { hash: "", href: "http://127.0.0.1/dashboard", origin: "http://127.0.0.1" },
    history: { state: null, pushState(st, _t, hash) { this.state = st; window.location.hash = hash; }, back() {} },
  };
  const ctx = {
    document,
    window,
    location: window.location,
    navigator: { clipboard: { writeText: (text) => { clipboard.push(String(text)); return Promise.resolve(); } }, userAgent: "node", platform: "Win32" },
    localStorage: storage(),
    sessionStorage: storage(),
    console,
    fetch: fakeFetch,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval() {},
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
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
;globalThis.__page = { state, els, wireEvents, wireRoutes, switchTab, openYoinkDetail, renderYoinkDetail, renderQueue,
  renderTopicOverview, cardHtml, captureStepIndex, CAPTURE_STEPS, loadLibrary, refreshJobs, handleJobsStreamEvent };`, ctx);
  vm.runInContext(RECORDED.map((name) => `${name} = function () {};`).join("\n"), ctx);
  const page = ctx.__page;
  page.wireEvents();
  page.wireRoutes();
  const fireClick = (target) => {
    const event = { type: "click", target, button: 0, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    for (const fn of docListeners.click || []) fn(event);
    return event;
  };
  return {
    page, state: page.state, els: page.els, requests, held, opened, clipboard, panels, fireClick,
    paths: () => requests.map((r) => r.path),
    count: (path) => requests.filter((r) => r.path === path).length,
    searches: () => requests.filter((r) => r.path.startsWith("/memory/search"))
      .map((r) => new URLSearchParams(r.path.split("?")[1] || "")),
  };
}

// Waits for the page's next /jobs read (the running-paste poll), then for
// what it renders.
async function nextJobsRead(p) {
  const before = p.count("/jobs");
  for (let waited = 0; waited < POLL_LIMIT_MS && p.count("/jobs") === before; waited += 50) await sleep(50);
  await settle();
  return p.count("/jobs") > before;
}

// Pastes a video link and presses Enter; true once it is posted to /extract.
async function pasteVideo(p, url) {
  edit(p.els.searchInput, url);
  await sleep(DETECT_WAIT_MS);
  await settle();
  p.els.searchInput.dispatch("keydown", { key: "Enter" });
  await settle();
  return p.held.length > 0;
}

function captureRows(p) {
  const html = p.els.libraryCaptures.innerHTML;
  return { html, rows: html.split('<article class="capture-row"').length - 1, retries: html.split(">Retry now<").length - 1 };
}

function edit(el, value) {
  el.value = value;
  el.dispatch(el.tagName === "INPUT" ? "input" : "change");
}

// ---- paste ----------------------------------------------------------------
async function groupPaste() {
  await scenario("a pasted playlist link is a capture, not a search", async () => {
    const p = makePage();
    const before = p.searches().length;
    edit(p.els.searchInput, "https://www.youtube.com/playlist?list=PL123");
    check(p.state.filters.q === "", "a link never becomes the search query", p.state.filters.q);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.searches().length === before, "pasting a link sends no Library search", p.searches().length - before);
    check(p.paths().some((path) => path.startsWith("/detect?url=")), "the box asks the helper's /detect what the link is", p.paths());
    const btn = p.els.libraryCaptureButton;
    check(!btn.classList.contains("hidden") && !btn.disabled, "Uoink it is offered for a link Uoink can capture");
    check(btn.textContent === "Uoink this youtube playlist", "the button names what it captures", btn.textContent);
    check(p.els.libraryCaptureNote.textContent.includes("Captures every video in the playlist"), "the note says what the capture does", p.els.libraryCaptureNote.textContent);
    const enter = p.els.searchInput.dispatch("keydown", { key: "Enter" });
    check(enter.defaultPrevented, "Enter in the box is the capture, not a form submit");
    await settle();
    const post = p.requests.find((r) => r.method === "POST");
    check(Boolean(post) && post.path === "/playlist/start", "a playlist link goes to the playlist route /detect named", post && post.path);
    const body = post ? JSON.parse(post.body) : {};
    check(body.url === "https://www.youtube.com/playlist?list=PL123" && body.interval === 30, "the capture posts the link with the usual interval", body);
    check(p.els.searchInput.value === "", "the box clears once the capture starts", p.els.searchInput.value);
    check(p.els.libraryCaptureNote.textContent.startsWith("Playlist started."), "the note says the playlist started", p.els.libraryCaptureNote.textContent);
    check(p.state.libraryRuns.length === 0, "the playlist job, not a local row, carries it from here", p.state.libraryRuns.length);
  });

  await scenario("a video link shows as a capture row until it is saved", async () => {
    const p = makePage();
    edit(p.els.searchInput, "https://www.youtube.com/watch?v=abc123");
    await sleep(DETECT_WAIT_MS);
    await settle();
    p.els.libraryCaptureButton.dispatch("click");
    await settle();
    check(p.held.length === 1, "Uoink it posts the video to /extract", p.held.length);
    const rows = p.els.libraryCaptures.innerHTML;
    check(!p.els.libraryCaptures.classList.contains("hidden") && rows.includes("Capturing") && rows.includes("https://www.youtube.com/watch?v=abc123"), "the capture shows under the box while it runs", rows);
    const searchesBefore = p.searches().length;
    if (!p.held.length) return;
    p.held[0].answer({ ok: true, title: "Agent loops explained", folder: "C:\\Uoink\\AI\\agent-loops" });
    await settle();
    check(p.state.libraryRuns.length === 0, "the row goes once the helper says it is saved", p.state.libraryRuns.length);
    check(p.els.libraryCaptureNote.textContent.includes("Saved \"Agent loops explained\""), "the note names what was saved", p.els.libraryCaptureNote.textContent);
    check(p.searches().length > searchesBefore, "Library reloads so the new capture is in the list", p.searches().length - searchesBefore);
    check(p.paths().includes("/library/facets"), "topics and counts reload too", p.paths().filter((x) => x.startsWith("/library")));
  });

  await scenario("a capture that fails names the step and offers Retry", async () => {
    const p = makePage();
    edit(p.els.searchInput, "https://www.youtube.com/watch?v=dead01");
    await sleep(DETECT_WAIT_MS);
    await settle();
    p.els.searchInput.dispatch("keydown", { key: "Enter" });
    await settle();
    if (!p.held.length) { check(false, "the video is posted to /extract", p.held.length); return; }
    p.held[0].answer({ ok: false, error: "This video is unavailable.", error_detail: "ERROR: [youtube] dead01: Video unavailable", failure_phase: "download" });
    await settle();
    const rows = p.els.libraryCaptures.innerHTML;
    check(rows.includes("Failed at video"), "the row says which step failed, in words", rows);
    check(rows.includes('class="step fail"'), "the strip marks the failed step too", rows);
    check(rows.includes("data-library-retry=\"https://www.youtube.com/watch?v=dead01\"") && rows.includes("Retry now"), "Retry now is offered with the link", rows);
    const run = p.state.libraryRuns[0];
    check(Boolean(run) && run.state === "failed", "the failed capture stays listed", run);
    if (!run) return;
    const dismiss = new FakeEl("", "BUTTON");
    dismiss.dataset.libraryDismiss = run.id;
    dismiss._matches = ["[data-library-dismiss]"];
    p.fireClick(dismiss);
    check(p.state.libraryRuns.length === 0 && !p.els.libraryCaptures.innerHTML.includes("dead01"), "Dismiss takes it off the list", p.els.libraryCaptures.innerHTML);
  });

  await scenario("a link Uoink can't capture says so and posts nothing", async () => {
    const p = makePage();
    edit(p.els.searchInput, "https://example.com/some/page");
    await sleep(DETECT_WAIT_MS);
    await settle();
    check(p.els.libraryCaptureButton.classList.contains("hidden"), "no Uoink it button for a link Uoink can't capture");
    check(p.els.libraryCaptureNote.textContent.includes("can't capture that link"), "the note says it can't capture it", p.els.libraryCaptureNote.textContent);
    p.els.searchInput.dispatch("keydown", { key: "Enter" });
    await settle();
    check(!p.requests.some((r) => r.method === "POST"), "Enter posts nothing", p.requests.filter((r) => r.method === "POST"));
  });

  await scenario("text still searches; a link replacing a search drops it", async () => {
    const p = makePage();
    edit(p.els.searchInput, "agent loops");
    check(p.state.filters.q === "agent loops", "text is the search query straight away", p.state.filters.q);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const last = p.searches().at(-1);
    check(Boolean(last) && last.get("q") === "agent loops" && last.get("sort") === "newest", "the search asks the helper with the query and the sort", last && last.toString());
    check(!p.paths().some((path) => path.startsWith("/detect")) && p.state.libraryRuns.length === 0, "text asks /detect nothing and starts no capture", p.paths());
    edit(p.els.searchInput, "youtu.be/abc123");
    check(p.state.filters.q === "", "the link drops the search it replaced", p.state.filters.q);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const after = p.searches().at(-1);
    check(Boolean(after) && !after.get("q"), "the list reloads without the old query", after && after.toString());
    edit(p.els.searchInput, "node.js");
    check(p.state.filters.q === "node.js", "a word with a dot is still a search", p.state.filters.q);
  });
}

// ---- kinds ----------------------------------------------------------------
async function groupKinds() {
  await scenario("a type chip asks the helper for that group", async () => {
    const p = makePage();
    const chips = p.els.libraryKinds._children;
    check(chips.length === 5 && chips.map((c) => c.textContent).join(",") === "All,Videos,Posts,Notes,Podcasts", "the chips are All, Videos, Posts, Notes, Podcasts", chips.map((c) => c.textContent));
    const videos = chips.find((c) => c.dataset.libraryKind === "videos");
    if (!videos) return;
    const before = p.searches().length;
    p.fireClick(videos);
    await settle();
    const sent = p.searches().slice(before);
    check(sent.length === 1 && sent[0].get("kind") === "videos" && sent[0].get("offset") === "0", "Videos asks for kind=videos from the first page", sent.map((s) => s.toString()));
    check(p.state.filters.kind === "videos", "the chip sets the Library kind", p.state.filters.kind);
    check(videos.getAttribute("aria-pressed") === "true" && chips[0].getAttribute("aria-pressed") === "false", "the pressed chip says so; All lets go", chips.map((c) => c.getAttribute("aria-pressed")));
    p.fireClick(videos);
    await settle();
    check(p.searches().length === before + 1, "pressing the pressed chip again asks nothing new", p.searches().length - before);
    p.fireClick(chips[0]);
    await settle();
    const all = p.searches().at(-1);
    check(Boolean(all) && !all.has("kind"), "All drops the kind", all && all.toString());
  });

  await scenario("the one sort control is answered by the helper", async () => {
    const p = makePage();
    edit(p.els.sortFilter, "oldest");
    check(p.state.filters.sort === "oldest", "the sort follows the control straight away", p.state.filters.sort);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const last = p.searches().at(-1);
    check(Boolean(last) && last.get("sort") === "oldest" && last.get("offset") === "0", "the helper orders every match, from the first page", last && last.toString());
  });
}

// ---- rows -------------------------------------------------------------------
async function groupRows() {
  await scenario("saved rows say Done and where the words came from", async () => {
    const p = makePage();
    const base = { video_id: "v1", slug: "v1", title: "Agent loops", channel: "Example", platform: "youtube", source_type: "video", yoinked_at: new Date().toISOString(), folder: "C:\\Uoink\\AI\\v1" };
    const captions = p.page.cardHtml({ ...base, transcript_source: "captions", has_transcript: true });
    check(captions.includes(">Done<") && captions.includes("YouTube captions"), "captions: Done · YouTube captions", captions);
    const whisper = p.page.cardHtml({ ...base, transcript_source: "asr", has_transcript: true });
    check(whisper.includes("transcript by Whisper"), "local ASR: Done · transcript by Whisper", whisper);
    const none = p.page.cardHtml({ ...base, transcript_source: null, has_transcript: false, asr_fallback_status: "failed" });
    check(none.includes("no captions, transcription failed"), "no words: the row says so", none);
    const note = p.page.cardHtml({ video_id: "n1", source_type: "note", platform: "note", title: "Idea", author: "You" });
    check(note.includes("your note") && note.includes('source-type-chip">note<'), "a note row names itself", note);
    check(captions.includes('data-thumb-for="v1"') && captions.includes("row-thumb"), "the row holds a slot for the real thumbnail", captions);
    check(captions.includes("Example &middot; YouTube"), "source · platform · time", captions);
  });

  await scenario("the step strip maps phases to the five steps", async () => {
    const p = makePage();
    const step = p.page.captureStepIndex;
    const table = [["metadata", "", 0], ["", "queued", 1], ["download", "", 2], ["transcribing", "", 3], ["transcript", "", 3],
      ["screenshots_chunk_2_of_3", "", 4], ["write", "", 4], ["writing", "", 4], ["comments", "", 4], ["", "running", -1]];
    for (const [phase, stateValue, want] of table) {
      check(step(phase, stateValue) === want, `phase "${phase}" (${stateValue || "no state"}) is step ${want}`, step(phase, stateValue));
    }
    check(p.page.CAPTURE_STEPS.join("|") === "details|waiting for YouTube|video|transcript|screenshots and save", "the five steps are SPEC's", p.page.CAPTURE_STEPS);
  });

  await scenario("captures on their way: Capturing, Waiting, Failed", async () => {
    const p = makePage();
    const now = new Date().toISOString();
    const later = new Date(Date.now() + 20 * 60 * 1000).toISOString();
    p.state.jobs = [
      { id: "j1", kind: "single", state: "running", title: "Running one", source_url: "https://www.youtube.com/watch?v=r1", current_video_phase: "download", started_at: now },
      { id: "j2", kind: "single", state: "queued", title: "Queued one", source_url: "https://www.youtube.com/watch?v=q1", started_at: now },
      { id: "j3", kind: "single", state: "failed", title: "Broken one", source_url: "https://www.youtube.com/watch?v=f1", current_video_phase: "transcript", error: "Transcript failed.", completed_at: now },
    ];
    const queue = { pending: [{ pending_id: 7, status: "pending", url: "https://www.youtube.com/watch?v=p1", last_error: "youtube_rate_limit", retry_after: later, attempt_count: 1 }] };
    p.state.queue = queue;
    p.page.renderQueue(queue);
    const rows = p.els.libraryCaptures.innerHTML;
    check(!p.els.libraryCaptures.classList.contains("hidden"), "the captures show above the saved list");
    check(rows.includes("Capturing") && rows.includes("video (3 of 5)"), "running: Capturing · video (3 of 5)", rows);
    check(rows.includes("Waiting") && rows.includes("one YouTube capture at a time"), "queued: Waiting · one YouTube capture at a time", rows);
    check(rows.includes("Failed at transcript") && rows.includes("data-library-retry=\"https://www.youtube.com/watch?v=f1\""), "failed: the step in words and Retry now", rows);
    check(rows.includes("HTTP 429") && rows.includes("Retries ") && rows.includes('data-retry="7"'), "rate-limited: the reason, when it retries, and Retry now", rows);
    const strip = /<span class="step-strip" aria-hidden="true">(.*?)<\/span>/.exec(rows);
    check(Boolean(strip) && strip[1] === '<i class="step done"></i><i class="step done"></i><i class="step now"></i><i class="step todo"></i><i class="step todo"></i>', "the running capture's strip: two done, video now, two to go", strip && strip[1]);
    check(!rows.includes("now advanced"), "a first render does not animate", rows);
    p.state.jobs[0] = { ...p.state.jobs[0], current_video_phase: "transcribing" };
    p.page.renderQueue(queue);
    check(p.els.libraryCaptures.innerHTML.includes("step now advanced"), "a step that advanced moves", p.els.libraryCaptures.innerHTML);
    p.page.renderQueue(queue);
    check(!p.els.libraryCaptures.innerHTML.includes("now advanced"), "a repaint with no new step does not move", p.els.libraryCaptures.innerHTML);
  });
}

// ---- reader -----------------------------------------------------------------
const READER_ROW = {
  video_id: "vidR", slug: "agent-loops", title: "Agent loops explained", channel: "Example Channel",
  topic: "AI", platform: "youtube", source_type: "video", source_url: "https://www.youtube.com/watch?v=vidR",
  folder: "C:\\Uoink\\AI\\agent-loops", duration_seconds: 754, yoinked_at: "2026-10-03T10:00:00Z",
};

function readerFiles(details, markdown = "# Agent loops explained\n\nBody") {
  return {
    "/yoinks/vidR/details": { ok: true, video_id: "vidR", details },
    "/yoinks/vidR/markdown": { ok: true, markdown },
  };
}

async function groupReader() {
  await scenario("the transcript reads as paragraphs with linked times and inline screenshots", async () => {
    const details = {
      title: "Agent loops explained", channel: "Example Channel", duration_seconds: 754, transcript_source: "captions",
      transcript: [
        { start: 0, end: 3, text: "Hello there." },
        { start: 3, end: 6, text: "This is the first idea." },
        { start: 20, end: 24, text: "A new part starts after a pause." },
      ],
      screenshots: [{ timestamp: "00:00:10", path: "screenshots/shot_0001.jpg", filename: "shot_0001.jpg" }],
      comments: [{ author: "Ana", text: "Great breakdown", like_count: 12, reply_count: 1, time_text: "2 days ago", is_pinned: false }],
      comments_status: "fetched",
      comment_intelligence: { top_themes: [{ label: "Pricing", count: 4, description: "People ask about cost.", quotes: ["How much?"] }], mentioned_products_tools: [], notable_disagreements: [] },
      hook_type: "question", hook_explanation: "It opens on a question.",
    };
    const p = makePage({ files: readerFiles(details) });
    await p.page.openYoinkDetail(READER_ROW);
    await settle();
    const html = p.els.yoinkDetail.innerHTML;
    const paras = html.split('class="reader-row reader-para"').length - 1;
    check(paras === 2, "two paragraphs: a pause starts the second", paras);
    check(html.includes('href="https://www.youtube.com/watch?v=vidR&amp;t=0s"') && html.includes(">0:00</a>"), "the first paragraph's time links to the source at 0:00", html);
    check(html.includes('href="https://www.youtube.com/watch?v=vidR&amp;t=20s"') && html.includes(">0:20</a>"), "the second paragraph's time links to 0:20", html);
    check(html.includes("Hello there. This is the first idea."), "segments join into the paragraph", html);
    const shot = html.indexOf('alt="Screenshot at 0:10"');
    const second = html.indexOf("A new part starts");
    const first = html.indexOf("Hello there.");
    check(shot > first && shot < second, "the 0:10 screenshot sits after the paragraph it falls in", [first, shot, second]);
    check(html.includes('data-reader-img="C:\\Uoink\\AI\\agent-loops\\screenshots/shot_0001.jpg"'), "the screenshot loads from the capture's folder", html);
    check(p.els.yoinkTranscriptNote.classList.contains("hidden"), "captions need no note");
    check(p.els.yoinkHeading.innerHTML === "Agent loops explained" && p.els.yoinkTitle.textContent === "Agent loops explained", "the title is the H1 and the breadcrumb's current page");
    check(p.els.yoinkSubhead.textContent.includes("Example Channel") && p.els.yoinkSubhead.textContent.includes("YouTube") && p.els.yoinkSubhead.textContent.includes("12:34"), "the meta line: channel, platform, length", p.els.yoinkSubhead.textContent);
    check(p.els.yoinkSourceLink.textContent === "Watch on YouTube" && p.els.yoinkSourceLink.href === READER_ROW.source_url && !p.els.yoinkSourceLink.classList.contains("hidden"), "watch on the source", [p.els.yoinkSourceLink.textContent, p.els.yoinkSourceLink.href]);
    check(p.els.yoinkCrumbTopic.textContent === "AI" && !p.els.yoinkCrumbTopicItem.classList.contains("hidden"), "the breadcrumb names the topic", p.els.yoinkCrumbTopic.textContent);
    check(!p.els.yoinkCommentsSection.classList.contains("hidden") && p.els.yoinkComments.innerHTML.includes("Ana") && p.els.yoinkComments.innerHTML.includes("12 likes"), "comments fill their section", p.els.yoinkComments.innerHTML);
    check(!p.els.yoinkAnalysisSection.classList.contains("hidden") && p.els.yoinkAnalysis.innerHTML.includes("Pricing") && p.els.yoinkAnalysis.innerHTML.includes("question"), "the hook and comment themes fill AI analysis", p.els.yoinkAnalysis.innerHTML);
    check(p.els.yoinkFacts.innerHTML.includes("AI") && p.els.yoinkFactMeta.textContent === "ready", "file details keep the saved facts", p.els.yoinkFactMeta.textContent);
    check(p.els.yoinkDetail.getAttribute("aria-label") === "Transcript", "the document is labelled", p.els.yoinkDetail.getAttribute("aria-label"));
  });

  await scenario("the note explains Whisper or missing captions from transcript_source and its reason", async () => {
    const asr = makePage({ files: readerFiles({ transcript_source: "asr", asr_fallback: { status: "completed", model: "base" }, transcript: [{ start: 0, end: 2, text: "Words." }] }) });
    await asr.page.openYoinkDetail(READER_ROW);
    await settle();
    check(!asr.els.yoinkTranscriptNote.classList.contains("hidden"), "a Whisper transcript gets the note");
    check(asr.els.yoinkTranscriptNote.textContent === "YouTube didn't provide captions for this video, so Uoink transcribed the audio on this PC with Whisper (Balanced model).", "the note says Whisper ran on this PC", asr.els.yoinkTranscriptNote.textContent);
    const missing = makePage({ files: readerFiles({ transcript_source: null, asr_fallback: { status: "model_not_downloaded", model: "small" }, transcript: [] }) });
    await missing.page.openYoinkDetail(READER_ROW);
    await settle();
    const text = missing.els.yoinkTranscriptNote.textContent;
    check(text.includes("isn't on this PC yet") && text.includes("Settings, Capture"), "a missing model says what to do", text);
    const off = makePage({ files: readerFiles({ transcript_source: null, asr_fallback: { status: "disabled" } }) });
    await off.page.openYoinkDetail(READER_ROW);
    await settle();
    check(off.els.yoinkTranscriptNote.textContent.includes("turned off"), "local transcription off says so", off.els.yoinkTranscriptNote.textContent);
    const failed = makePage({ files: readerFiles({ transcript_source: null, asr_fallback: { status: "failed", error: "out of memory" } }) });
    await failed.page.openYoinkDetail(READER_ROW);
    await settle();
    check(failed.els.yoinkTranscriptNote.textContent.includes("failed (out of memory)"), "a failed transcription gives its reason", failed.els.yoinkTranscriptNote.textContent);
  });

  await scenario("an untimed transcript never invents a time", async () => {
    const p = makePage({ files: readerFiles({ transcript: "First caption line\nSecond caption line" }) });
    await p.page.openYoinkDetail(READER_ROW);
    await settle();
    const html = p.els.yoinkDetail.innerHTML;
    check(html.includes("time not stored") && !html.includes("t=0s"), "the gutter says the time is unknown", html);
    check(html.includes("First caption line") && html.includes("Second caption line"), "every line is there", html);
  });

  await scenario("screenshots show even when there is no transcript", async () => {
    // Review finding: with no transcript the reader rendered the Markdown,
    // which drops image lines, so a capture's screenshots never showed.
    const details = {
      transcript_source: null, asr_fallback: { status: "model_not_downloaded", model: "small" }, transcript: [],
      screenshots: [
        { timestamp: "00:00:30", path: "screenshots/shot_0002.jpg", filename: "shot_0002.jpg" },
        { timestamp_seconds: 5, path: "screenshots/shot_0001.jpg", filename: "shot_0001.jpg" },
        { path: "screenshots/cover.jpg", filename: "cover.jpg" },
      ],
    };
    const markdown = "# Agent loops explained\n\nNo captions came with this video.\n\n![Screenshot at 00:00:05](screenshots/shot_0001.jpg)\n";
    const p = makePage({ files: readerFiles(details, markdown) });
    await p.page.openYoinkDetail(READER_ROW);
    await settle();
    const html = p.els.yoinkDetail.innerHTML;
    const first = html.indexOf('alt="Screenshot at 0:05"');
    const second = html.indexOf('alt="Screenshot at 0:30"');
    const untimed = html.indexOf('alt="Screenshot"');
    check(first >= 0 && second > first && untimed > second, "every saved screenshot shows, in time order, the untimed one last", [first, second, untimed]);
    check(html.includes('data-reader-img="C:\\Uoink\\AI\\agent-loops\\screenshots/shot_0001.jpg"'), "each loads from the capture's folder", html);
    check(html.includes('href="https://www.youtube.com/watch?v=vidR&amp;t=5s"') && html.includes(">0:05</a>"), "a screenshot's time links to the source there", html);
    const words = html.indexOf("No captions came with this video.");
    check(words >= 0 && words < first, "the saved text reads first, then the screenshots", [words, first]);
    check(!p.els.yoinkTranscriptNote.classList.contains("hidden") && p.els.yoinkTranscriptNote.textContent.includes("isn't on this PC yet"), "the note still says why there is no transcript", p.els.yoinkTranscriptNote.textContent);

    const bare = makePage({ files: readerFiles(details, "") });
    await bare.page.openYoinkDetail(READER_ROW);
    await settle();
    const bareHtml = bare.els.yoinkDetail.innerHTML;
    check(bareHtml.includes("No transcript saved.") && bareHtml.includes("The screenshots it saved are below.") && bareHtml.includes('alt="Screenshot at 0:30"'),
      "with no saved text either, the screenshots still show under the empty state", bareHtml);
  });

  await scenario("a note reads as text; Markdown copies; Send to Claude opens Claude", async () => {
    const note = { video_id: "note1", source_type: "note", platform: "note", title: "Saved idea", author: "You", topic: "" };
    const p = makePage({ files: { "/yoinks/note1/markdown": { ok: true, markdown: "---\nid: x\n---\n# Saved idea\n\nThe saved word is AMBER." } } });
    await p.page.openYoinkDetail(note);
    await settle();
    const html = p.els.yoinkDetail.innerHTML;
    check(html.includes('class="reader-prose') && html.includes("The saved word is AMBER.") && !html.includes("id: x"), "the note's text is the document, front matter dropped", html);
    check(p.els.yoinkTranscriptNote.classList.contains("hidden") && p.els.yoinkCrumbTopicItem.classList.contains("hidden"), "no transcript note and no topic crumb for an untagged note");
    check(!p.paths().includes("/yoinks/note1/details"), "a note reads no media details", p.paths());
    p.els.yoinkCopyMarkdown.dispatch("click");
    await settle();
    check(p.clipboard.length === 1 && p.clipboard[0].includes("The saved word is AMBER."), "Copy as Markdown copies the saved Markdown", p.clipboard);
    p.els.yoinkSendClaude.dispatch("click");
    await settle();
    check(p.clipboard.length === 2 && p.opened.includes("https://claude.ai/new"), "Send to Claude copies it and opens a new Claude chat", p.opened);
  });
}

// ---- split ------------------------------------------------------------------
async function groupSplit() {
  await scenario("the list stays beside the reader; the open row is marked", async () => {
    const p = makePage({ files: readerFiles({ transcript: [{ start: 0, text: "Hi." }] }) });
    const cards = ["vidR", "other"].map((id) => {
      const el = new FakeEl("", "ARTICLE");
      el.dataset.videoId = id;
      return el;
    });
    p.els.libraryGrid._children = cards;
    p.state.library = [READER_ROW];
    await p.page.openYoinkDetail(READER_ROW);
    check(p.els.librarySplit.classList.contains("reading"), "opening an item turns on the split");
    check(p.panels.get("tab-yoink").classList.contains("active"), "the reader is the active panel");
    check(cards[0].getAttribute("aria-current") === "true" && cards[1].getAttribute("aria-current") === null, "the open item's row is marked", cards.map((c) => c.getAttribute("aria-current")));
    p.page.switchTab("library");
    check(!p.els.librarySplit.classList.contains("reading"), "back on Library the split is off");
    check(cards[0].getAttribute("aria-current") === null, "no row is marked once the reader closes", cards[0].getAttribute("aria-current"));
  });

  await scenario("the topic list shows beside Library and the reader only", async () => {
    const p = makePage();
    p.state.facets = { topic: [{ value: "AI", label: "AI", count: 3 }, { value: "Uncategorized", label: "Uncategorized", count: 1 }] };
    p.page.switchTab("library");
    p.page.renderTopicOverview();
    check(!p.els.sidebarTopics.classList.contains("hidden"), "topics show beside Library");
    check(p.els.topicOverview.innerHTML.includes('data-topic-overview="AI"') && p.els.topicOverview.innerHTML.includes("<span>3</span>"), "each topic has its count", p.els.topicOverview.innerHTML);
    p.page.switchTab("writing");
    check(p.els.sidebarTopics.classList.contains("hidden"), "topics hide on Generate");
    const chip = new FakeEl("", "BUTTON");
    chip.dataset.topicOverview = "AI";
    chip._matches = ["[data-topic-overview]"];
    p.page.switchTab("yoink");
    check(!p.els.sidebarTopics.classList.contains("hidden"), "topics show beside the reader");
    const before = p.searches().length;
    p.fireClick(chip);
    await settle();
    check(p.state.activeTab === "library" && p.state.filters.topic === "AI", "a topic opens Library filtered to it", [p.state.activeTab, p.state.filters.topic]);
    const last = p.searches().at(-1);
    check(p.searches().length > before && last.get("topic") === "AI", "Library asks the helper for that topic", last && last.toString());
  });
}

// ---- live -------------------------------------------------------------------
// Review finding: /extract records only a finished job, so a pasted video's
// row sat at "Capturing" with no step while it ran.
async function groupLive() {
  await scenario("a pasted video's strip follows the phase the helper reports", async () => {
    let live = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs: [], live_captures: live }) });
    const url = "https://www.youtube.com/watch?v=live01";
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    const body = JSON.parse(p.held[0].body);
    check(typeof body.capture_ref === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(body.capture_ref), "the video names itself to /extract with a plain token", body);
    check(captureRows(p).html.includes("started here, this can take a few minutes") && !captureRows(p).html.includes("step-strip"), "until the helper reports a phase the row only says it started", captureRows(p).html);
    const ref = body.capture_ref;

    live = [{ capture_ref: ref, source_url: url, phase: "waiting" }, { capture_ref: "another-tab", source_url: "https://www.youtube.com/watch?v=x", phase: "transcript" }];
    check(await nextJobsRead(p), "while it runs the page reads /jobs for its phase");
    let html = captureRows(p).html;
    check(html.includes(">Waiting<") && html.includes("one YouTube capture at a time"), "waiting its turn reads Waiting", html);
    check(!html.includes("transcript (4 of 5)"), "another capture's phase is not this row's", html);
    check(!html.includes("now advanced"), "the first step it reports does not animate", html);

    live = [{ capture_ref: ref, source_url: url, phase: "download" }];
    await nextJobsRead(p);
    html = captureRows(p).html;
    check(html.includes(">Capturing<") && html.includes("video (3 of 5)"), "downloading reads Capturing · video (3 of 5)", html);
    const strip = /<span class="step-strip" aria-hidden="true">(.*?)<\/span>/.exec(html);
    check(Boolean(strip) && strip[1] === '<i class="step done"></i><i class="step done"></i><i class="step now advanced"></i><i class="step todo"></i><i class="step todo"></i>', "the strip moves to video", strip && strip[1]);

    live = [{ capture_ref: ref, source_url: url, phase: "screenshots" }];
    await nextJobsRead(p);
    check(captureRows(p).html.includes("screenshots and save (5 of 5)"), "the last step is screenshots and save", captureRows(p).html);

    p.held[0].answer({ ok: true, title: "Live one", folder: "C:\\Uoink\\AI\\live-one" });
    live = [];
    await settle();
    check(p.state.libraryRuns.length === 0 && captureRows(p).rows === 0, "the saved video leaves the capture rows", captureRows(p).html);
    const settled = p.count("/jobs");
    check(!(await nextJobsRead(p)) && p.count("/jobs") === settled, "the page stops asking once nothing pasted is running", p.count("/jobs") - settled);
  });

  await scenario("the paste poll takes the phase and leaves the job list to the stream", async () => {
    // A poll answer read before a newer stream event must not put an older
    // job state back (D20): a finished playlist would sit at "Capturing".
    let live = [];
    let jobs = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs, live_captures: live }) });
    const url = "https://www.youtube.com/watch?v=live02";
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    const ref = JSON.parse(p.held[0].body).capture_ref;
    const when = new Date().toISOString();
    const playlist = { id: "pl9", kind: "playlist", state: "running", playlist_title: "Course", source_url: "https://www.youtube.com/playlist?list=PL9",
      videos_total: 2, videos_done: 1, current_video_phase: "download", started_at: when };
    p.page.handleJobsStreamEvent("snapshot", { active: [playlist], recent: [], queue: {} });
    p.page.handleJobsStreamEvent("job", { ...playlist, state: "completed", videos_done: 2, current_video_phase: null, completed_at: when });
    await settle();
    jobs = [playlist];
    live = [{ capture_ref: ref, source_url: url, phase: "transcript" }];
    check(await nextJobsRead(p), "the running paste reads /jobs for its phase");
    const html = captureRows(p).html;
    check(html.includes("transcript (4 of 5)"), "the pasted row moves to the phase the poll read", html);
    const pl = p.state.jobs.find((job) => job.id === "pl9");
    check(Boolean(pl) && pl.state === "completed", "the playlist the stream finished stays finished", pl && pl.state);
    check(!html.includes('data-capture-key="job:pl9"'), "and never comes back as a running row", html);
    p.held[0].answer({ ok: true, title: "Live two", folder: "C:\\Uoink\\AI\\live-two" });
    await settle();
  });
}

// ---- saves ------------------------------------------------------------------
// Review finding: playlist and queued captures saved with no reload, so new
// saves never appeared in the list or the topic counts.
async function groupSaves() {
  const now = () => new Date().toISOString();
  await scenario("a playlist saving videos in the background reloads Library and its topics", async () => {
    const p = makePage();
    const playlist = { id: "pl1", kind: "playlist", state: "running", playlist_title: "Course", source_url: "https://www.youtube.com/playlist?list=PL1",
      videos_total: 3, videos_done: 0, current_video_phase: "download", started_at: now() };
    p.page.handleJobsStreamEvent("snapshot", { active: [playlist], recent: [], queue: {} });
    await settle();
    const searches = p.searches().length;
    const facets = p.count("/library/facets");
    const jobs = p.count("/jobs");
    check(searches === 0, "the page's first look at the jobs reloads nothing", searches);
    p.page.handleJobsStreamEvent("job", { ...playlist, current_video_phase: "transcript" });
    await settle();
    check(p.searches().length === searches, "a step with nothing saved reloads nothing", p.searches().length - searches);
    p.page.handleJobsStreamEvent("job", { ...playlist, videos_done: 1, current_video_phase: "metadata" });
    await settle();
    const sent = p.searches().slice(searches);
    check(sent.length === 1 && sent[0].get("offset") === "0", "a saved video reloads Library from the first page", sent.map((s) => s.toString()));
    check(p.count("/library/facets") === facets + 1, "and the topic counts", p.count("/library/facets") - facets);
    check(p.count("/jobs") === jobs, "without asking again for the jobs it was just given", p.count("/jobs") - jobs);
    p.page.handleJobsStreamEvent("job", { ...playlist, state: "completed", videos_done: 3, current_video_phase: null, completed_at: now() });
    await settle();
    check(p.searches().length === searches + 2 && p.count("/library/facets") === facets + 2, "the playlist finishing reloads them again", [p.searches().length - searches, p.count("/library/facets") - facets]);
  });

  await scenario("a queued capture the retry worker saves reloads Library", async () => {
    const p = makePage();
    const later = new Date(Date.now() + 20 * 60 * 1000).toISOString();
    const queue = { pending: [{ pending_id: 4, status: "pending", url: "https://www.youtube.com/watch?v=q1", last_error: "youtube_rate_limit", retry_after: later, attempt_count: 1 }] };
    p.page.handleJobsStreamEvent("snapshot", { active: [], recent: [], queue });
    await settle();
    const before = p.searches().length;
    // The worker records a finished single-video job; the row leaves the queue.
    p.page.handleJobsStreamEvent("job", { id: "j_q1", kind: "single", state: "completed", source_url: "https://www.youtube.com/watch?v=q1", videos_total: 1, videos_done: 1, completed_at: now() });
    p.page.handleJobsStreamEvent("queue", { pending: [] });
    await settle();
    check(p.searches().length === before + 1, "the saved capture reloads Library once", p.searches().length - before);
  });

  await scenario("failures, cancels and repaints reload nothing", async () => {
    const p = makePage();
    p.page.handleJobsStreamEvent("snapshot", { active: [{ id: "r1", kind: "single", state: "running", videos_done: 0 }], recent: [{ id: "old", kind: "single", state: "completed", videos_done: 1 }], queue: {} });
    await settle();
    const before = p.searches().length;
    p.page.handleJobsStreamEvent("job", { id: "r1", kind: "single", state: "failed", videos_done: 0, error: "x", completed_at: now() });
    p.page.handleJobsStreamEvent("job", { id: "c1", kind: "playlist", state: "cancelled", videos_done: 0 });
    p.page.handleJobsStreamEvent("job", { id: "n1", kind: "notification", state: "completed" });
    p.page.renderQueue({});
    p.page.renderQueue({});
    await settle();
    check(p.searches().length === before, "nothing saved, nothing reloaded", p.searches().length - before);
    check(before === 0, "a completed job already there on first look is not new", before);
  });
}

// ---- reconcile ----------------------------------------------------------------
// Review finding: a failed paste kept its local row while Library also listed
// the failed job the helper recorded, so it showed twice with two Retry buttons.
async function groupReconcile() {
  const failedJob = (id, url, when) => ({
    id, kind: "single", state: "failed", source_url: url, title: "Dead video", current_video_phase: "download",
    error: "This video is unavailable.", error_detail: "ERROR: [youtube] dead: Video unavailable",
    started_at: when, completed_at: when, updated_at: when, videos_total: 1, videos_failed: 1,
  });

  await scenario("a failed paste shows once, as the helper's job, with one Retry", async () => {
    let jobs = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs }) });
    const url = "https://www.youtube.com/watch?v=dup01";
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    jobs = [failedJob("job_dup01", url, new Date().toISOString())];
    p.held[0].answer({ ok: false, error: "This video is unavailable.", error_detail: "ERROR: [youtube] dup01: Video unavailable", failure_phase: "download", job_id: "job_dup01" });
    await settle();
    const { html, rows, retries } = captureRows(p);
    check(rows === 1 && retries === 1, "the failure shows once, with one Retry", { rows, retries, html });
    check(html.includes('data-capture-key="job:job_dup01"') && html.includes("Failed at video"), "the row is the helper's job, failed at video", html);
    check(p.state.libraryRuns.length === 0, "the local row handed over for good", p.state.libraryRuns);
    const dismiss = new FakeEl("", "BUTTON");
    dismiss.dataset.libraryDismiss = "job:job_dup01";
    dismiss._matches = ["[data-library-dismiss]"];
    p.fireClick(dismiss);
    p.page.renderQueue(p.state.queue || {});
    check(captureRows(p).rows === 0, "Dismiss clears it and it stays gone", captureRows(p).html);
  });

  await scenario("with no job named, the helper's job for the same link still takes over", async () => {
    let jobs = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs }) });
    const url = "https://www.youtube.com/watch?v=dup02";
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    jobs = [failedJob("job_dup02", url, new Date().toISOString())];
    p.held[0].answer({ ok: false, error: "Bad gateway" }, 502);
    await settle();
    const { html, rows, retries } = captureRows(p);
    check(rows === 1 && retries === 1 && html.includes('data-capture-key="job:job_dup02"'), "one row, the helper's, with one Retry", { rows, retries, html });
  });

  await scenario("Dismissing a failed paste before its job arrives keeps that job away", async () => {
    let jobs = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs }) });
    const url = "https://www.youtube.com/watch?v=dup03";
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    p.held[0].answer({ ok: false, error: "This video is unavailable.", failure_phase: "download", job_id: "job_dup03" });
    await settle();
    const run = p.state.libraryRuns[0];
    check(Boolean(run) && run.jobId === "job_dup03" && captureRows(p).rows === 1, "until the job arrives the local row stands in for it", p.state.libraryRuns);
    if (!run) return;
    const dismiss = new FakeEl("", "BUTTON");
    dismiss.dataset.libraryDismiss = run.id;
    dismiss._matches = ["[data-library-dismiss]"];
    p.fireClick(dismiss);
    jobs = [failedJob("job_dup03", url, new Date().toISOString())];
    await p.page.refreshJobs({ render: true });
    check(captureRows(p).rows === 0, "the job it named does not come back as a second row", captureRows(p).html);
  });

  await scenario("an older failure of a link pasted again steps aside for the new capture", async () => {
    const url = "https://www.youtube.com/watch?v=again1";
    const old = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    const jobs = [failedJob("job_old", url, old)];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs }) });
    await p.page.refreshJobs({ render: true });
    check(captureRows(p).html.includes('data-capture-key="job:job_old"'), "the older failure is listed", captureRows(p).html);
    if (!(await pasteVideo(p, url))) { check(false, "the video is posted to /extract", p.held.length); return; }
    const { html, rows } = captureRows(p);
    check(rows === 1 && html.includes(">Capturing<") && !html.includes("job:job_old"), "only the new capture shows while it runs", html);
  });
}

// ---- review repairs ---------------------------------------------------------
async function groupRetry() {
  await scenario("Retry within five seconds keeps the new row and its live steps", async () => {
    let jobs = [];
    let live = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs, live_captures: live }) });
    const url = "https://www.youtube.com/watch?v=quickretry1";
    if (!(await pasteVideo(p, url))) { check(false, "the first capture starts"); return; }
    const firstRun = p.state.libraryRuns[0];
    const firstRef = JSON.parse(p.held[0].body).capture_ref;
    jobs = [{ id: "job_first", kind: "single", state: "failed", source_url: url,
      started_at: firstRun.startedAt, completed_at: new Date().toISOString(),
      current_video_phase: "download", error_detail: "ERROR: Requested format is not available" }];
    p.held[0].answer({ ok: false, error: "Capture failed", error_detail: jobs[0].error_detail,
      failure_phase: "download", job_id: "job_first" });
    await settle();
    check(captureRows(p).rows === 1 && captureRows(p).retries === 1, "the first failure has one row and one Retry", captureRows(p));
    const retry = new FakeEl("", "BUTTON");
    retry.dataset.libraryRetry = url;
    retry.dataset.libraryRun = "job:job_first";
    retry._matches = ["[data-library-retry]"];
    p.fireClick(retry);
    await settle();
    check(p.held.length === 2, "Retry sends exactly one new /extract", p.held.length);
    check(Date.now() - Date.parse(firstRun.startedAt) < 5000, "the retry starts inside the old five-second match window");
    const next = p.state.libraryRuns[0];
    check(Boolean(next) && next.id !== firstRun.id && next.state === "running", "the new local run survives reconciliation", p.state.libraryRuns);
    check(captureRows(p).rows === 1 && captureRows(p).html.includes(">Capturing<") && !captureRows(p).html.includes("job:job_first"),
      "the running row replaces the dismissed failure", captureRows(p));
    if (!p.held[1]) return;
    const ref = JSON.parse(p.held[1].body).capture_ref;
    check(ref !== firstRef, "the retry has its own capture reference", ref);
    live = [{ capture_ref: firstRef, source_url: url, phase: "screenshots" },
      { capture_ref: ref, source_url: url, phase: "download" }];
    check(await nextJobsRead(p), "the retry keeps polling live phases");
    check(captureRows(p).html.includes("video (3 of 5)") && !captureRows(p).html.includes("screenshots and save (5 of 5)"),
      "the retry shows its own video step, not the previous capture's", captureRows(p));
    live = [{ capture_ref: ref, source_url: url, phase: "transcript" }];
    check(await nextJobsRead(p), "polling continues after the first phase");
    check(captureRows(p).html.includes("transcript (4 of 5)") && captureRows(p).html.includes("step now advanced"),
      "the retry strip advances to transcript", captureRows(p));
    jobs = [{ ...jobs[0], id: "job_retry", started_at: next ? next.startedAt : new Date().toISOString(),
      completed_at: new Date().toISOString(), current_video_phase: "transcript" }, ...jobs];
    live = [];
    p.held[1].answer({ ok: false, error_detail: jobs[0].error_detail, failure_phase: "transcript", job_id: "job_retry" });
    await settle();
    check(p.state.libraryRuns.length === 0 && captureRows(p).rows === 1 && captureRows(p).html.includes('data-capture-key="job:job_retry"'),
      "the retry hands over only to its own finished job", captureRows(p));
  });

  await scenario("a fresh paste also excludes an already known same-URL job", async () => {
    const url = "https://www.youtube.com/watch?v=quickpaste1";
    const job = { id: "job_known", kind: "single", state: "failed", source_url: url,
      started_at: new Date().toISOString(), completed_at: new Date().toISOString(), error: "Capture failed" };
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs: [job] }) });
    await p.page.refreshJobs({ render: true });
    await pasteVideo(p, url);
    check(p.state.libraryRuns.length === 1 && captureRows(p).rows === 1 && captureRows(p).html.includes(">Capturing<"),
      "a fresh paste keeps one running row, with the recent failure stepped aside", captureRows(p));
    p.held[0].answer({ ok: true, title: "Saved retry" });
    await settle();
  });

  await scenario("a previous same-URL job arriving late cannot take over a new capture", async () => {
    let live = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs: [], live_captures: live }) });
    const url = "https://www.youtube.com/watch?v=latefailure1";
    await pasteVideo(p, url);
    const run = p.state.libraryRuns[0];
    const ref = JSON.parse(p.held[0].body).capture_ref;
    const previous = { id: "job_late_previous", kind: "single", state: "failed", source_url: url,
      started_at: new Date(Date.parse(run.startedAt) - 1000).toISOString(),
      completed_at: new Date().toISOString(), failure_phase: "download", error: "Previous capture failed" };
    p.page.handleJobsStreamEvent("job", previous);
    await settle();
    check(p.state.libraryRuns[0] === run, "an unseen job that started earlier cannot consume the local run", p.state.libraryRuns);
    check(captureRows(p).rows === 1 && captureRows(p).html.includes(">Capturing<"),
      "the late previous failure steps aside for the new row", captureRows(p));
    live = [{ capture_ref: ref, source_url: url, phase: "transcript" }];
    check(await nextJobsRead(p), "the new run keeps polling after the old job arrives");
    check(captureRows(p).html.includes("transcript (4 of 5)"), "its live transcript step still appears", captureRows(p));
    // The helper timestamps in whole seconds. An explicit id still matches
    // the new run even if its timestamp rounds down before the browser's.
    const current = { ...previous, id: "job_late_current",
      started_at: new Date(Math.floor(Date.parse(run.startedAt) / 1000) * 1000).toISOString() };
    p.held[0].answer({ ok: false, error: "Requested format is not available", failure_phase: "download", job_id: current.id });
    await settle();
    p.page.handleJobsStreamEvent("job", current);
    await settle();
    check(p.state.libraryRuns.length === 0 && captureRows(p).rows === 1
      && captureRows(p).html.includes('data-capture-key="job:job_late_current"'),
      "the returned job id reconciles its own failure despite timestamp rounding", captureRows(p));
  });

  await scenario("only a matching reference can reconcile a job without a reliable start", async () => {
    let jobs = [];
    const p = makePage({ jobsAnswer: () => ({ ok: true, jobs }) });
    const url = "https://www.youtube.com/watch?v=refmatch123";
    await pasteVideo(p, url);
    const run = p.state.libraryRuns[0];
    const job = { id: "job_no_start", kind: "single", state: "failed", source_url: url,
      completed_at: new Date().toISOString(), error: "Requested format is not available" };
    jobs = [job];
    p.page.handleJobsStreamEvent("job", job);
    await settle();
    check(p.state.libraryRuns[0] === run, "a completion time cannot stand in for a missing start time");
    jobs = [{ ...job, started_at: new Date().toISOString(), capture_ref: "another_capture" }];
    p.page.handleJobsStreamEvent("job", jobs[0]);
    await settle();
    check(p.state.libraryRuns[0] === run, "a different capture_ref cannot fall back to the same URL");
    jobs = [{ ...job, capture_ref: run.ref }];
    p.page.handleJobsStreamEvent("job", jobs[0]);
    await settle();
    check(p.state.libraryRuns.length === 0 && captureRows(p).rows === 1,
      "the matching capture_ref hands over to exactly one helper row", captureRows(p));
    p.held[0].answer({ ok: false, error: job.error, job_id: job.id });
    await settle();
    check(captureRows(p).rows === 1, "the later extract response does not duplicate the correlated failure", captureRows(p));
  });
}

function checkFailureDisclosure(p, label) {
  const { html, rows, retries } = captureRows(p);
  const cause = /<span class="state-detail">([^<]*)<\/span>/.exec(html);
  const disclosure = /<details class="error-details"><summary>Details<\/summary><pre>([\s\S]*?)<\/pre><\/details>/.exec(html);
  check(rows === 1 && retries === 1, `${label}: one failed row and Retry`, { rows, retries });
  check(html.includes("Failed at video"), `${label}: failure phase is written out`, html);
  check(Boolean(cause) && cause[1].includes("Requested format is not available") && !/[\r\n]/.test(cause[1]), `${label}: the real cause is on one line`, cause && cause[1]);
  check(Boolean(disclosure), `${label}: native Details/summary is keyboard reachable and starts closed`, html);
  check(Boolean(disclosure) && disclosure[1].includes("ERROR: [youtube] format12345: Requested format is not available"), `${label}: Details keeps the diagnostic error line`, disclosure && disclosure[1]);
  check(Boolean(disclosure) && disclosure[1].includes("&lt;format&gt;") && !html.includes("<format>"), `${label}: diagnostic text is HTML-escaped`, html);
  check(!html.includes("Details are tucked below"), `${label}: the generic translation no longer hides the cause`, html);
  check(!/PRIVATE_SENTINEL|SECRET_SENTINEL/.test(html), `${label}: raw fields, paths and credentials stay out of the markup`, html);
}

async function groupErrors() {
  // The public error fields can contain sanitized placeholders. Extra raw
  // fields must never be used, and legacy diagnostic text is scrubbed too.
  const diagnostic = 'ERROR: [youtube] format12345: Requested format is not available\nTry &lt;literal&gt; or <format>. File "C:\\Users\\PRIVATE_SENTINEL\\My Captures\\video.mp4"; https://user:SECRET_SENTINEL@example.test/media; Authorization: Bearer SECRET_SENTINEL';
  const failure = { ok: false, error: "Uoink couldn't finish this one. Details are tucked below.", error_detail: diagnostic,
    failure_phase: "download", raw_error: "PRIVATE_SENTINEL", stderr: "SECRET_SENTINEL" };
  await scenario("a local failure exposes its sanitized cause and Details", async () => {
    const p = makePage();
    await pasteVideo(p, "https://www.youtube.com/watch?v=format12345");
    p.held[0].answer(failure);
    await settle();
    checkFailureDisclosure(p, "local failure");
  });
  await scenario("a helper-job failure exposes its sanitized cause and Details", async () => {
    const p = makePage();
    p.page.handleJobsStreamEvent("snapshot", { active: [], recent: [{ ...failure, id: "job_format", kind: "single", state: "failed",
      source_url: "https://www.youtube.com/watch?v=format12345", completed_at: new Date().toISOString() }], queue: {} });
    await settle();
    checkFailureDisclosure(p, "helper failure");
  });
  await scenario("error is the fallback when error_detail is empty", async () => {
    const p = makePage();
    p.page.handleJobsStreamEvent("snapshot", { active: [], recent: [{ id: "job_error_only", kind: "single", state: "failed",
      source_url: "https://www.youtube.com/watch?v=onlyerror01", current_video_phase: "transcript", error_detail: "   ",
      error: "Captions could not be read <again>.", completed_at: new Date().toISOString() }], queue: {} });
    await settle();
    check(captureRows(p).html.includes("Captions could not be read &lt;again&gt;."), "an error-only failure keeps its cause", captureRows(p));
    check(captureRows(p).html.includes("<summary>Details</summary><pre>Captions could not be read &lt;again&gt;.</pre>"),
      "the error-only detail is escaped too", captureRows(p));
  });
  await scenario("a local failure uses the last sanitized ERROR line as its cause", async () => {
    const p = makePage();
    await pasteVideo(p, "https://www.youtube.com/watch?v=format12345");
    p.held[0].answer({ ...failure, error_detail: `Trying another format\nERROR: First attempt failed\n${diagnostic}\nGiving up` });
    await settle();
    checkFailureDisclosure(p, "last diagnostic");
    const html = captureRows(p).html;
    check(!/<span class="state-detail">[^<]*First attempt failed/.test(html), "the cause is the final ERROR, not the first");
    check(html.includes("Trying another format") && html.includes("Giving up"), "Details retains the sanitized diagnostic context");
  });
}

const GROUPS = {
  paste: groupPaste,
  kinds: groupKinds,
  rows: groupRows,
  reader: groupReader,
  split: groupSplit,
  live: groupLive,
  saves: groupSaves,
  reconcile: groupReconcile,
  retry: groupRetry,
  errors: groupErrors,
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
