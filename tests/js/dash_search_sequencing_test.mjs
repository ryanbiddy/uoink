// Dashboard Library regression harness: search never shows stale results (D1).
//
// Before the fix loadLibrary() returned early while a load was in flight, so
// typing "ai" and then " agents" never sent the second search: the "ai"
// results stayed under an "ai agents" search box. The same guard dropped the
// Library refresh after saving a note or an image while a load was running.
//
// Runs the REAL dashboard script (assets/dashboard/index.html, everything
// before init()) in a node:vm context over a fake page holding every id the
// markup declares, with the tag it declares (so the search box is an INPUT and
// the filters are SELECTs, as wireEvents() expects). wireEvents() wires the
// real listeners; the test types into the search box, clicks Load more, sets
// the dates, and saves a note or an image the way a user does. /memory/search
// answers are held until the test releases them, in whichever order a
// scenario needs.
//   typing      -- a search typed while an older one is unanswered is still
//                  sent, and the newer answer is what Library shows whichever
//                  answer lands first
//   stale_error -- an older search failing late never replaces the newer
//                  results; an older search answering late never replaces the
//                  newer search's error
//   load_more   -- Load more still pages; a double click never duplicates
//                  rows; a search typed while Load more is unanswered drops
//                  the old query's page
//   date_range  -- a bad date range entered while a search is unanswered keeps
//                  its date message when that search answers
//   note_image  -- saving a note or an image while a search is unanswered
//                  still refreshes Library, and the save's refresh is what
//                  Library shows
//   before_debounce -- an older answer, failure or Load more page landing
//                  after the search box or a filter changed but before the
//                  260 ms debounce sends the new search is dropped too
//   refresh_before_debounce -- a note or image refresh, or Load more, started
//                  after the search box or a filter changed but before the
//                  debounce asks for the new search from its first page, so
//                  its answer never shows the old search's rows
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/dash_search_sequencing_test.mjs [group ...]
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
const DEBOUNCE_WAIT_MS = 320; // the Library filter debounce is 260 ms

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

// id -> tag for every element the dashboard markup declares.
const TAGS = new Map();
{
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let m;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (id && !TAGS.has(id[1])) TAGS.set(id[1], m[1].toUpperCase());
  }
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
  constructor(id, tag) {
    this.id = id;
    this.tagName = tag || "DIV";
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
  }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  dispatch(type) {
    const event = { type, target: this, currentTarget: this, preventDefault() {}, stopPropagation() {} };
    for (const fn of this._listeners[type] || []) fn(event);
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
  querySelectorAll() { return []; }
  closest() { return null; }
  contains() { return false; }
  setCustomValidity() {}
  focus() {}
  blur() {}
  select() {}
  click() { this.dispatch("click"); }
  scrollIntoView() {}
  append() {}
  appendChild(child) { return child; }
  remove() {}
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => ({}),
  };
}

function row(id, title) {
  return { video_id: id, slug: id, title, yoinked_at: "2026-10-01T10:00:00Z", platform: "youtube", source_type: "video" };
}

// One fresh dashboard page per scenario.
function makePage() {
  const elements = new Map();
  const getEl = (id) => {
    if (!elements.has(id)) elements.set(id, new FakeEl(id, TAGS.get(id)));
    return elements.get(id);
  };
  const docListeners = {};
  const document = {
    getElementById: getEl,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener(type, fn) { (docListeners[type] ||= []).push(fn); },
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase()),
    body: new FakeEl("body", "BODY"),
    documentElement: new FakeEl("html", "HTML"),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };

  // Every request the page makes; /memory/search is held until released.
  const requests = [];
  const searches = [];
  const fakeFetch = (url, opts = {}) => {
    const path = String(url);
    requests.push({ path, method: (opts && opts.method) || "GET" });
    if (path === "/token") return Promise.resolve(jsonResponse({ ok: true, token: "test-token" }));
    if (path.startsWith("/jobs")) return Promise.resolve(jsonResponse({ ok: true, jobs: [] }));
    if (path.startsWith("/memory/search")) {
      const params = new URLSearchParams(path.split("?")[1] || "");
      return new Promise((resolve) => {
        searches.push({
          q: params.get("q") || "",
          match: params.get("match"),
          sort: params.get("sort"),
          mode: params.get("mode"),
          platform: params.get("platform") || "",
          hook_type: params.get("hook_type") || "",
          offset: Number(params.get("offset") || 0),
          answer(rows, extra = {}) { resolve(jsonResponse({ ok: true, results: rows, total: rows.length, corpus_total: 40, state: rows.length ? "matches" : "no_matches", ...extra })); },
          fail(status = 500, error = "search broke") { resolve(jsonResponse({ ok: false, error }, status)); },
        });
      });
    }
    if (path === "/notes" || path.startsWith("/images")) return Promise.resolve(jsonResponse({ ok: true }));
    return Promise.resolve(jsonResponse({ ok: true }));
  };

  const window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
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
;globalThis.__page = { state, els, wireEvents, saveNote, saveImage, setImageSelection };`, ctx);
  const page = ctx.__page;
  for (const id of ["sortFilter", "matchFilter"]) {
    const select = MARKUP.match(new RegExp(`<select[^>]*id="${id}"[^>]*>([\\s\\S]*?)</select>`))[1];
    const options = [...select.matchAll(/<option value="([^"]*)"([^>]*)>/g)];
    page.els[id].value = (options.find((option) => /selected/.test(option[2])) || options[0])[1];
  }
  page.wireEvents();
  return { page, state: page.state, els: page.els, requests, searches, document, docListeners,
    run: (code) => vm.runInContext(code, ctx) };
}

// What a user's edit fires: wireEvents() listens for "input" on INPUTs (the
// search box, the date fields) and "change" on the SELECT filters.
function edit(el, value) {
  el.value = value;
  el.dispatch(el.tagName === "INPUT" ? "input" : "change");
}

async function typeSearch(p, text) {
  edit(p.els.searchInput, text);
  await sleep(DEBOUNCE_WAIT_MS);
  await settle();
}

function libraryIds(p) {
  return p.state.library.map((r) => r.video_id);
}

// ---------------------------------------------------------------------------
async function groupTyping() {
  await scenario("newer answer lands first", async () => {
    const p = makePage();
    check(p.els.searchInput.tagName === "INPUT", "the search box is the markup's INPUT", p.els.searchInput.tagName);
    await typeSearch(p, "ai");
    check(p.searches.length === 1 && p.searches[0].q === "ai", "typing 'ai' sends a search for 'ai'", p.searches.map((s) => s.q));
    await typeSearch(p, "ai agents");
    check(p.searches.length === 2, "typing ' agents' while 'ai' is unanswered still sends a second search", p.searches.length);
    const newer = p.searches[1];
    check(Boolean(newer) && newer.q === "ai agents", "the second search is for 'ai agents'", newer && newer.q);
    if (!newer) return;
    newer.answer([row("agents1", "AI agents deep dive")]);
    await settle();
    p.searches[0].answer([row("basics1", "AI basics"), row("basics2", "AI for beginners")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "Library holds the 'ai agents' results, not the late 'ai' answer", libraryIds(p));
    check(p.els.libraryGrid.innerHTML.includes("AI agents deep dive"), "the grid shows the 'ai agents' card");
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the grid never shows the late 'ai' card");
    check(p.els.resultSummary.textContent === "1 shown of 1 matching uoinks", "the summary counts the 'ai agents' results", p.els.resultSummary.textContent);
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });

  await scenario("older answer lands first", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    await typeSearch(p, "ai agents");
    check(p.searches.length === 2, "both searches are sent", p.searches.length);
    if (p.searches.length < 2) return;
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the older 'ai' answer is not shown under 'ai agents'");
    check(libraryIds(p).length === 0, "the older answer is not kept as the Library", libraryIds(p));
    check(p.els.resultSummary.textContent === "Loading library...", "Library still reads as loading the newer search", p.els.resultSummary.textContent);
    check(p.state.loading === true, "Library is still loading while the newer search is unanswered", p.state.loading);
    p.searches[1].answer([row("agents1", "AI agents deep dive"), row("agents2", "Agent frameworks")]);
    await settle();
    check(JSON.stringify(libraryIds(p).sort()) === JSON.stringify(["agents1", "agents2"]), "Library shows the 'ai agents' results once they land", libraryIds(p));
    check(p.els.libraryGrid.innerHTML.includes("Agent frameworks"), "the grid shows the 'ai agents' cards");
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });

  await scenario("three quick searches", async () => {
    const p = makePage();
    await typeSearch(p, "a");
    await typeSearch(p, "ai");
    await typeSearch(p, "ai agents");
    check(JSON.stringify(p.searches.map((s) => s.q)) === JSON.stringify(["a", "ai", "ai agents"]), "every settled search box value is sent", p.searches.map((s) => s.q));
    if (p.searches.length < 3) return;
    p.searches[2].answer([row("agents1", "AI agents deep dive")]);
    p.searches[0].answer([row("a1", "A is for apple")]);
    p.searches[1].answer([row("basics1", "AI basics")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "only the newest search's answer is shown", libraryIds(p));
  });
}

async function groupStaleError() {
  await scenario("older search fails late", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    await typeSearch(p, "ai agents");
    check(p.searches.length === 2, "both searches are sent", p.searches.length);
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("agents1", "AI agents deep dive")]);
    await settle();
    p.searches[0].fail(500, "older search broke");
    await settle();
    check(p.state.libraryState === "matches", "a late failure of the older search does not mark Library unavailable", p.state.libraryState);
    check(p.els.libraryGrid.innerHTML.includes("AI agents deep dive"), "the newer results stay on screen");
    check(!p.els.libraryGrid.innerHTML.includes("older search broke"), "the older search's error is not shown");
    check(p.els.resultSummary.textContent === "1 shown of 1 matching uoinks", "the summary still counts the newer results", p.els.resultSummary.textContent);
  });

  await scenario("older search answers after the newer one failed", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    await typeSearch(p, "ai agents");
    check(p.searches.length === 2, "both searches are sent", p.searches.length);
    if (p.searches.length < 2) return;
    p.searches[1].fail(500, "newer search broke");
    await settle();
    check(p.state.libraryState === "unavailable", "the newer search's failure is shown", p.state.libraryState);
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(p.state.libraryState === "unavailable", "the older answer does not replace the newer search's failure", p.state.libraryState);
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the older 'ai' card is not shown");
    check(p.els.resultSummary.textContent === "We couldn't refresh Library just now.", "the summary still reports the newer failure", p.els.resultSummary.textContent);
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });
}

async function groupLoadMore() {
  const page1 = Array.from({ length: 24 }, (_, i) => row(`p1_${i}`, `Page one item ${i}`));
  const page2 = Array.from({ length: 6 }, (_, i) => row(`p2_${i}`, `Page two item ${i}`));

  await scenario("load more pages", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    check(p.state.hasMore === true, "a first page of 24 of 30 offers Load more", p.state.hasMore);
    p.els.loadMore.dispatch("click");
    await settle();
    check(p.searches.length === 2 && p.searches[1].offset === 24 && p.searches[1].q === "ai", "Load more asks for the next page of the same search", p.searches.map((s) => [s.q, s.offset]));
    if (p.searches.length < 2) return;
    p.searches[1].answer(page2, { total: 30 });
    await settle();
    check(p.state.library.length === 30 && new Set(libraryIds(p)).size === 30, "both pages are shown once each", p.state.library.length);
    check(p.state.hasMore === false && p.els.pageSummary.textContent === "End of library", "the end of the list is reported", p.els.pageSummary.textContent);
  });

  await scenario("double click on load more", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    p.els.loadMore.dispatch("click");
    p.els.loadMore.dispatch("click");
    await settle();
    for (const s of p.searches.slice(1)) s.answer(page2, { total: 30 });
    await settle();
    const ids = libraryIds(p);
    check(ids.length === 30 && new Set(ids).size === 30, "a double click on Load more never duplicates rows", ids.length);
    check(p.state.offset === 30, "the page offset counts each row once", p.state.offset);
  });

  await scenario("search typed while load more is unanswered", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    p.els.loadMore.dispatch("click");
    await settle();
    await typeSearch(p, "ai agents");
    const newer = p.searches.find((s) => s.q === "ai agents");
    check(Boolean(newer), "the new search is sent while Load more is unanswered", p.searches.map((s) => s.q));
    if (!newer) return;
    newer.answer([row("agents1", "AI agents deep dive")]);
    await settle();
    p.searches[1].answer(page2, { total: 30 });
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "the old query's next page is not appended to the new results", libraryIds(p));
    check(p.state.offset === 1, "the page offset belongs to the new search", p.state.offset);
  });
}

async function groupDateRange() {
  await scenario("bad date range while a search is unanswered", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    check(p.els.dateFrom.tagName === "INPUT" && p.els.dateTo.tagName === "INPUT", "the date fields are the markup's INPUTs", [p.els.dateFrom.tagName, p.els.dateTo.tagName]);
    edit(p.els.dateFrom, "2026-10-10");
    edit(p.els.dateTo, "2026-10-01");
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.state.libraryState === "invalid_range", "the bad date range is reported straight away", p.state.libraryState);
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(p.state.libraryState === "invalid_range", "the earlier search answering does not replace the date message", p.state.libraryState);
    check(p.els.resultSummary.textContent === "Start date has to be before end date.", "the summary keeps the date message", p.els.resultSummary.textContent);
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the earlier search's card is not shown");
    check(p.searches.length === 1, "no search is sent for the bad range", p.searches.length);
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });
}

async function groupNoteImage() {
  await scenario("note saved while a search is unanswered", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    p.els.noteTextInput.value = "remember the agent loop";
    const saving = p.page.saveNote();
    await settle();
    const noteAt = p.requests.findIndex((r) => r.path === "/notes" && r.method === "POST");
    check(noteAt >= 0, "the note is posted", p.requests.map((r) => r.path));
    check(p.searches.length === 2, "saving the note refreshes Library although a search is unanswered", p.searches.length);
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("note1", "remember the agent loop"), row("basics1", "AI basics")]);
    await settle();
    await saving;
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(libraryIds(p).includes("note1"), "the new note is in Library", libraryIds(p));
    check(p.els.libraryGrid.innerHTML.includes("remember the agent loop"), "the grid shows the new note");
  });

  await scenario("image saved while a search is unanswered", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    p.page.setImageSelection({ type: "image/png", size: 2048, name: "whiteboard.png" });
    const saving = p.page.saveImage();
    await settle();
    const imageAt = p.requests.findIndex((r) => r.path.startsWith("/images") && r.method === "POST");
    check(imageAt >= 0, "the image is posted", p.requests.map((r) => r.path));
    check(p.searches.length === 2, "saving the image refreshes Library although a search is unanswered", p.searches.length);
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("image1", "whiteboard.png"), row("basics1", "AI basics")]);
    await settle();
    await saving;
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(libraryIds(p).includes("image1"), "the new image is in Library", libraryIds(p));
    check(p.els.libraryGrid.innerHTML.includes("whiteboard.png"), "the grid shows the new image");
  });
}

// The edit fires its listener but the 260 ms debounce has not sent the new
// search yet when the older answer lands; settle() only spins setImmediate,
// so it never reaches the debounce timer.
async function groupBeforeDebounce() {
  await scenario("older answer lands before the new search is sent", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    check(p.searches.length === 1 && p.searches[0].q === "ai", "typing 'ai' sends a search for 'ai'", p.searches.map((s) => s.q));
    if (p.searches.length < 1) return;
    edit(p.els.searchInput, "ai agents");
    await settle();
    check(p.searches.length === 1, "the 'ai agents' search is still waiting for the debounce", p.searches.length);
    p.searches[0].answer([row("basics1", "AI basics"), row("basics2", "AI for beginners")]);
    await settle();
    check(libraryIds(p).length === 0, "the 'ai' answer landing before the debounce is not kept as the Library", libraryIds(p));
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the 'ai' card never shows under 'ai agents'");
    check(p.els.resultSummary.textContent === "Loading library...", "Library still reads as loading", p.els.resultSummary.textContent);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.searches.length === 2 && p.searches[1].q === "ai agents", "the debounced 'ai agents' search is still sent", p.searches.map((s) => s.q));
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("agents1", "AI agents deep dive")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "Library shows the 'ai agents' results", libraryIds(p));
    check(p.els.libraryGrid.innerHTML.includes("AI agents deep dive"), "the grid shows the 'ai agents' card");
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });

  await scenario("older search fails before the new search is sent", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    if (p.searches.length < 1) { check(false, "typing 'ai' sends a search", p.searches.length); return; }
    edit(p.els.searchInput, "ai agents");
    await settle();
    check(p.searches.length === 1, "the 'ai agents' search is still waiting for the debounce", p.searches.length);
    p.searches[0].fail(500, "older search broke");
    await settle();
    check(p.state.libraryState !== "unavailable", "the 'ai' failure landing before the debounce does not mark Library unavailable", p.state.libraryState);
    check(!p.els.libraryGrid.innerHTML.includes("older search broke"), "the 'ai' search's error is not shown");
    check(p.els.resultSummary.textContent === "Loading library...", "Library still reads as loading", p.els.resultSummary.textContent);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.searches.length === 2 && p.searches[1].q === "ai agents", "the debounced 'ai agents' search is still sent", p.searches.map((s) => s.q));
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("agents1", "AI agents deep dive")]);
    await settle();
    check(p.state.libraryState === "matches", "Library shows the 'ai agents' results", p.state.libraryState);
    check(p.els.libraryGrid.innerHTML.includes("AI agents deep dive"), "the grid shows the 'ai agents' card");
  });

  await scenario("filter changed while a search is unanswered", async () => {
    const p = makePage();
    await typeSearch(p, "ai");
    if (p.searches.length < 1) { check(false, "typing 'ai' sends a search", p.searches.length); return; }
    check(p.els.platformFilter.tagName === "SELECT", "the platform filter is the markup's SELECT", p.els.platformFilter.tagName);
    edit(p.els.platformFilter, "youtube");
    await settle();
    check(p.searches.length === 1, "the filtered search is still waiting for the debounce", p.searches.length);
    p.searches[0].answer([row("basics1", "AI basics")]);
    await settle();
    check(libraryIds(p).length === 0, "the unfiltered answer landing before the debounce is not kept as the Library", libraryIds(p));
    check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the unfiltered card never shows under the new filter");
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.searches.length === 2 && p.searches[1].platform === "youtube", "the debounced filtered search is still sent", p.searches.map((s) => [s.q, s.platform]));
    if (p.searches.length < 2) return;
    p.searches[1].answer([row("yt1", "AI on YouTube")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["yt1"]), "Library shows the filtered results", libraryIds(p));
    check(p.state.loading === false, "the Library is not left loading", p.state.loading);
  });

  await scenario("load more page lands before the new search is sent", async () => {
    const page1 = Array.from({ length: 24 }, (_, i) => row(`p1_${i}`, `Page one item ${i}`));
    const page2 = Array.from({ length: 6 }, (_, i) => row(`p2_${i}`, `Page two item ${i}`));
    const p = makePage();
    await typeSearch(p, "ai");
    if (p.searches.length < 1) { check(false, "typing 'ai' sends a search", p.searches.length); return; }
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    p.els.loadMore.dispatch("click");
    await settle();
    check(p.searches.length === 2 && p.searches[1].offset === 24, "Load more asks for the next page", p.searches.map((s) => [s.q, s.offset]));
    if (p.searches.length < 2) return;
    edit(p.els.searchInput, "ai agents");
    await settle();
    check(p.searches.length === 2, "the 'ai agents' search is still waiting for the debounce", p.searches.length);
    p.searches[1].answer(page2, { total: 30 });
    await settle();
    check(!libraryIds(p).some((id) => id.startsWith("p2_")), "the old query's next page landing before the debounce is not appended", libraryIds(p).length);
    check(!p.els.libraryGrid.innerHTML.includes("Page two item"), "the grid never shows the old query's next page");
    check(p.state.offset === 24, "the page offset does not count the old query's next page", p.state.offset);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const newer = p.searches.find((s) => s.q === "ai agents");
    check(Boolean(newer) && newer.offset === 0, "the debounced 'ai agents' search is still sent from the first page", p.searches.map((s) => [s.q, s.offset]));
    if (!newer) return;
    newer.answer([row("agents1", "AI agents deep dive")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "Library shows the 'ai agents' results", libraryIds(p));
    check(p.state.offset === 1, "the page offset belongs to the new search", p.state.offset);
  });
}

// A load the user starts between the edit and the 260 ms debounce: it must
// ask for what the controls now say, from the first page. Each search is
// answered with what a real Library holds for the query it actually sent.
const AI_ROWS = [row("basics1", "AI basics"), row("basics2", "AI for beginners")];
const AGENT_ROWS = [row("agents1", "AI agents deep dive")];
function answerAsLibrary(s, extraRows = []) {
  s.answer(extraRows.concat(s.q === "ai agents" ? AGENT_ROWS : s.q === "ai" ? AI_ROWS : []));
}

async function groupRefreshBeforeDebounce() {
  for (const kind of ["note", "image"]) {
    await scenario(`${kind} saved after the search box changed, before the debounce`, async () => {
      const p = makePage();
      await typeSearch(p, "ai");
      if (p.searches.length < 1) { check(false, "typing 'ai' sends a search", p.searches.length); return; }
      edit(p.els.searchInput, "ai agents");
      await settle();
      let saving;
      let saved;
      if (kind === "note") {
        p.els.noteTextInput.value = "remember the agent loop";
        saved = row("note1", "remember the agent loop");
        saving = p.page.saveNote();
      } else {
        p.page.setImageSelection({ type: "image/png", size: 2048, name: "whiteboard.png" });
        saved = row("image1", "whiteboard.png");
        saving = p.page.saveImage();
      }
      await settle();
      check(p.searches.length === 2, `saving the ${kind} refreshes Library before the debounce fires`, p.searches.length);
      if (p.searches.length < 2) return;
      const refresh = p.searches[1];
      check(refresh.q === "ai agents" && refresh.offset === 0, `the ${kind} refresh searches for 'ai agents', not the old 'ai'`, [refresh.q, refresh.offset]);
      answerAsLibrary(refresh, [saved]);
      await settle();
      await saving;
      check(!p.els.libraryGrid.innerHTML.includes("AI basics"), `the ${kind} refresh never shows the 'ai' cards under 'ai agents'`);
      check(JSON.stringify(libraryIds(p).sort()) === JSON.stringify([saved.video_id, "agents1"].sort()), `Library holds the new ${kind} and the 'ai agents' results only`, libraryIds(p));
      answerAsLibrary(p.searches[0]);
      await settle();
      check(!p.els.libraryGrid.innerHTML.includes("AI basics"), "the late 'ai' answer is not shown either");
      await sleep(DEBOUNCE_WAIT_MS);
      await settle();
      const debounced = p.searches[2];
      check(Boolean(debounced) && debounced.q === "ai agents", "the debounced 'ai agents' search is still sent", p.searches.map((s) => s.q));
      if (!debounced) return;
      answerAsLibrary(debounced, [saved]);
      await settle();
      check(JSON.stringify(libraryIds(p).sort()) === JSON.stringify([saved.video_id, "agents1"].sort()), "Library shows the 'ai agents' results", libraryIds(p));
      check(p.state.loading === false, "the Library is not left loading", p.state.loading);
    });
  }

  await scenario("load more clicked after the search box changed, before the debounce", async () => {
    const page1 = Array.from({ length: 24 }, (_, i) => row(`p1_${i}`, `Page one item ${i}`));
    const p = makePage();
    await typeSearch(p, "ai");
    if (p.searches.length < 1) { check(false, "typing 'ai' sends a search", p.searches.length); return; }
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    check(p.state.hasMore === true, "a first page of 24 of 30 offers Load more", p.state.hasMore);
    edit(p.els.searchInput, "ai agents");
    await settle();
    p.els.loadMore.dispatch("click");
    await settle();
    check(p.searches.length === 2, "Load more is sent before the debounce fires", p.searches.length);
    if (p.searches.length < 2) return;
    const more = p.searches[1];
    check(more.q === "ai agents" && more.offset === 0, "Load more asks for the first page of 'ai agents', not the next 'ai' page", [more.q, more.offset]);
    if (more.q === "ai agents") answerAsLibrary(more);
    else more.answer(Array.from({ length: 6 }, (_, i) => row(`p2_${i}`, `Page two item ${i}`)), { total: 30 });
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "Library holds only the 'ai agents' results", libraryIds(p));
    check(!p.els.libraryGrid.innerHTML.includes("Page one item") && !p.els.libraryGrid.innerHTML.includes("Page two item"), "the grid never shows the 'ai' pages under 'ai agents'");
    check(p.state.offset === 1, "the page offset belongs to the new search", p.state.offset);
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const debounced = p.searches[2];
    check(Boolean(debounced) && debounced.q === "ai agents" && debounced.offset === 0, "the debounced 'ai agents' search is still sent from the first page", p.searches.map((s) => [s.q, s.offset]));
    if (!debounced) return;
    answerAsLibrary(debounced);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["agents1"]), "Library shows the 'ai agents' results", libraryIds(p));
    check(p.state.offset === 1 && p.state.loading === false, "the offset is the new search's and Library is not left loading", [p.state.offset, p.state.loading]);
  });

  await scenario("load more clicked after a filter changed, before the debounce", async () => {
    const page1 = Array.from({ length: 24 }, (_, i) => row(`p1_${i}`, `Page one item ${i}`));
    const p = makePage();
    edit(p.els.hookFilter, "question");
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    check(p.searches.length === 1 && p.searches[0].hook_type === "question", "the hook filter sends a filtered search", p.searches.map((s) => s.hook_type));
    if (p.searches.length < 1) return;
    p.searches[0].answer(page1, { total: 30 });
    await settle();
    edit(p.els.platformFilter, "tiktok");
    await settle();
    p.els.loadMore.dispatch("click");
    await settle();
    check(p.searches.length === 2, "Load more is sent before the debounce fires", p.searches.length);
    if (p.searches.length < 2) return;
    const more = p.searches[1];
    check(more.platform === "tiktok" && more.offset === 0, "Load more asks for the first page under the new platform filter", [more.platform, more.offset]);
    check(more.hook_type === "", "Load more drops the YouTube-only hook filter the new platform hides", more.hook_type);
    more.answer([row("tt1", "AI on TikTok")]);
    await settle();
    check(JSON.stringify(libraryIds(p)) === JSON.stringify(["tt1"]), "Library holds only the new filter's results", libraryIds(p));
    check(!p.els.libraryGrid.innerHTML.includes("Page one item"), "the grid never shows the old filter's rows");
    await sleep(DEBOUNCE_WAIT_MS);
    await settle();
    const debounced = p.searches[2];
    check(Boolean(debounced) && debounced.platform === "tiktok" && debounced.hook_type === "", "the debounced search asks for the same filters", p.searches.map((s) => [s.platform, s.hook_type]));
  });
}

async function groupSearchModes() {
  const p = makePage();
  await typeSearch(p, "pressurized rover");
  check(p.searches[0].match === "strict", "search defaults to all words");
  check(p.searches[0].sort === "relevance", "query defaults to Best match");
  check(p.els.sortFilter.value === "relevance", "sort control displays Best match");
  check(p.els.matchFilter.value === "strict", "match control displays All words");
  check(p.searches[0].mode === "keyword", "semantic search cannot broaden All words");
  console.log("library_search_params: " + JSON.stringify(p.searches[0]));
  edit(p.els.sortFilter, "oldest");
  await sleep(DEBOUNCE_WAIT_MS);
  check(p.searches[1].sort === "oldest", "date sort stays available");
  edit(p.els.matchFilter, "forgiving");
  await sleep(DEBOUNCE_WAIT_MS);
  check(p.searches[2].match === "forgiving", "Any words stays available");
  check(p.searches[2].mode === "auto", "Any words keeps optional semantic search");
  check(p.searches[2].sort === "oldest", "matching change preserves chosen date order");
  p.searches[0].answer([row("stale", "Old strict result")]);
  p.searches[2].answer([row("broad", "Any word result")]);
  await settle();
  check(JSON.stringify(libraryIds(p)) === JSON.stringify(["broad"]), "late strict answer cannot replace chosen matching");
  await typeSearch(p, "pressurized rover cabin");
  check(p.searches[3].sort === "oldest" && p.searches[3].match === "forgiving", "editing a query preserves chosen options");
  await typeSearch(p, "");
  check(p.searches[4].sort === "newest", "clearing query restores newest browse order");
  p.els.clearFilters.dispatch("click");
  await settle();
  check(p.els.matchFilter.value === "strict" && p.els.sortFilter.value === "newest", "Clear filters restores defaults");
  await typeSearch(p, "pressurized rover");
  p.run('removeLibraryFilter("q")');
  await settle();
  check(p.searches.at(-1).q === "" && p.searches.at(-1).sort === "newest", "removing the Search chip restores newest browse order");
  check(p.els.sortFilter.value === "newest", "the sort control follows the removed search");
}

async function groupSearchQuotes() {
  const p = makePage();
  await typeSearch(p, "pressurized rover");
  const hit = { ...row("moon", "Moon Base episode"), source_type: "episode", platform: "podcast",
    passage_verified: true, timestamp_seconds: 92.5,
    passage: { text: 'A pressurized rover keeps <crew> & equipment safe.', start: 92.5, timing: "coarse" } };
  p.searches[0].answer([hit]);
  await settle();
  const html = p.els.libraryGrid.innerHTML;
  // Query words are wrapped in <mark>; the quote text itself stays escaped.
  const unmarked = (text) => text.replace(/<\/?mark>/g, "");
  check(unmarked(html).includes('A pressurized rover keeps &lt;crew&gt; &amp; equipment safe.'), "row shows the escaped verified quote");
  check(html.includes("A <mark>pressurized</mark> <mark>rover</mark> keeps"), "query words are highlighted in the quote");
  p.state.filters.q = "crew";
  p.run("renderLibrary()");
  check(p.els.libraryGrid.innerHTML.includes("&lt;<mark>crew</mark>&gt;") && !p.els.libraryGrid.innerHTML.includes("<crew>"),
    "a highlight inside escaped text cannot inject markup");
  p.state.filters.q = "pressurized rover";
  check(/<a[^>]*href="#item\/moon\?t=92\.5"[^>]*>1:32<\/a>/.test(html), "quote has a timestamp link to the saved item");
  check(html.includes('aria-label="Open Moon Base episode at 1:32"'), "timestamp link names the item and time");
  for (const [passage, itemTime, expected] of [
    [{ timestamp_seconds: 12.48, start: 10 }, 0, 12.48],
    [{ timestamp_seconds: "", start: 92.5 }, 0, 92.5],
    [{ timestamp_seconds: 0, start: 92.5 }, 214, 0],
    [{ start: null }, 214, 214],
  ]) {
    p.state.library = [{ ...hit, timestamp_seconds: itemTime, passage: { text: hit.passage.text, ...passage } }];
    p.run("renderLibrary()");
    check(p.els.libraryGrid.innerHTML.includes(`href="#item/moon?t=${expected}"`), "quote prefers its own stored time, with the item time as fallback", [passage, itemTime, expected]);
  }
  p.state.library = [{ ...hit, video_id: "", slug: "", folder: "fixtures/moon" }];
  p.run("renderLibrary()");
  check(unmarked(p.els.libraryGrid.innerHTML).includes("A pressurized rover") && !p.els.libraryGrid.innerHTML.includes("?t="), "folder-only row keeps its quote without a broken timestamp link");
  p.state.library = [{ ...hit, timestamp_seconds: 0, passage: { ...hit.passage, start: 0 } }];
  p.run("renderLibrary()");
  check(p.els.libraryGrid.innerHTML.includes('?t=0"') && p.els.libraryGrid.innerHTML.includes('>0:00</a>'), "zero is a real stored timestamp");
  p.state.library = [{ ...hit, timestamp_seconds: null, passage: { text: hit.passage.text, timing: "not_timed" } }];
  p.run("renderLibrary()");
  check(unmarked(p.els.libraryGrid.innerHTML).includes("A pressurized rover") && !p.els.libraryGrid.innerHTML.includes("?t="), "untimed text shows a quote without an invented time");
  p.state.library = [{ ...hit, passage_verified: false, _snippet: "Unrelated opening text" }];
  p.run("renderLibrary()");
  check(!p.els.libraryGrid.innerHTML.includes("?t=") && !unmarked(p.els.libraryGrid.innerHTML).includes("A pressurized rover"), "unverified passage cannot become a quote or link");
  check(!p.els.libraryGrid.innerHTML.includes("Unrelated opening text"), "metadata matches do not quote unrelated discovery text");
  p.state.library = [hit];
  p.state.filters.q = "";
  p.run("renderLibrary()");
  check(!unmarked(p.els.libraryGrid.innerHTML).includes("A pressurized rover"), "browse rows do not retain search quotes");
}

async function groupSearchMoments() {
  const p = makePage();
  const route = p.run('parseRoute("#item/moon%2Fbase?t=92.5")');
  check(route.id === "moon/base" && route.seconds === 92.5, "deep link keeps item identity and precise stored seconds");
  check(route.hash === "#item/moon%2Fbase?t=92.5", "timed item route round trips");
  for (const value of ["", "-2", "Infinity", "nope"]) {
    check(p.run(`parseRoute("#item/moon?t=${value}").seconds`) == null, `invalid time ${value} does not invent a moment`);
  }
  const hit = row("moon", "Moon Base episode");
  p.state.library = [hit];
  const paragraphs = [0, 92.5, 150].map((seconds) => {
    const el = new FakeEl("para", "DIV");
    el.dataset.readerSeconds = String(seconds);
    el.scrollIntoView = () => { p.scrolled = seconds; };
    el.focus = () => { p.focused = seconds; };
    return el;
  });
  p.document.querySelectorAll = (selector) => selector === ".reader-para[data-reader-seconds]" ? paragraphs : [];
  p.run(`
    globalThis.detailReads = 0;
    globalThis.markdownReads = 0;
    loadYoinkDetails = async () => {
      detailReads++;
      return { transcript: [{ start: 92.5, end: 100, text: "A pressurized rover." }] };
    };
    loadYoinkMarkdown = async () => { markdownReads++; return ""; };
    loadLibraryActivity = startLibraryActivityTimer = stopLibraryActivityTimer = () => {};
    navigateTo("#item/moon?t=92.5");
  `);
  await settle();
  await p.run("new Promise(requestAnimationFrame)");
  check(p.state.selectedYoink.video_id === "moon", "timestamp link opens the saved item");
  check(p.scrolled === 92.5 && p.focused === 92.5, "reader scrolls and focuses the paragraph at the exact fractional match time");
  const rendered = p.run('readerTranscriptHtml(state.selectedYoink, state.selectedYoinkSidecar)');
  check(rendered.includes('data-reader-seconds="92.5"'), "reader paragraphs expose their precise stored time for the jump");
  const untimed = p.run('readerTranscriptHtml(state.selectedYoink, { transcript: [{ text: "No stored time." }] })');
  check(!untimed.includes("data-reader-seconds"), "missing segment time does not become an undefined reader timestamp");
  p.run('navigateTo("#item/moon?t=0")');
  await settle();
  await p.run("new Promise(requestAnimationFrame)");
  check(p.scrolled === 0, "a second timestamp on the same item moves to the new moment");
  check(p.run("detailReads === 1 && markdownReads === 1"), "a second timestamp on the open item reuses its loaded content");
  p.run('navigateTo("#library"); navigateTo("#item/moon?t=150")');
  await p.run("new Promise(requestAnimationFrame)");
  check(p.scrolled === 150 && p.run("detailReads === 1 && markdownReads === 1"), "returning to the selected item reveals the new moment without fetching it again");
  p.state.library.push(row("rovers", "Rovers video"));
  p.run(`
    loadYoinkDetails = () => {
      detailReads++;
      return new Promise((resolve) => { globalThis.finishDetails = resolve; });
    };
    navigateTo("#item/rovers?t=0");
    navigateTo("#item/rovers?t=150");
  `);
  await p.run("new Promise(requestAnimationFrame)");
  p.run('finishDetails({ transcript: [{ start: 150, text: "Another rover." }] })');
  await settle();
  await p.run("new Promise(requestAnimationFrame)");
  check(p.scrolled === 150, "a timestamp changed during loading is still the moment revealed when content arrives");
  check(p.run("detailReads === 2 && markdownReads === 2"), "changing the pending item's timestamp does not duplicate its fetches");
  p.scrolled = null;
  p.run(`
    loadYoinkDetails = () => new Promise((resolve) => { globalThis.finishDetails = resolve; });
    navigateTo("#item/moon?t=92.5");
    navigateTo("#library");
    finishDetails({ transcript: [{ start: 90, text: "A pressurized rover." }] });
  `);
  await settle();
  await p.run("new Promise(requestAnimationFrame)");
  check(p.state.activeTab === "library" && p.scrolled === null, "late item details cannot move the user after leaving the reader");
}

const GROUPS = {
  search_modes: groupSearchModes,
  search_quotes: groupSearchQuotes,
  search_moments: groupSearchMoments,
  typing: groupTyping,
  stale_error: groupStaleError,
  load_more: groupLoadMore,
  date_range: groupDateRange,
  note_image: groupNoteImage,
  before_debounce: groupBeforeDebounce,
  refresh_before_debounce: groupRefreshBeforeDebounce,
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
