// Dashboard Writing drafts regression harness: saving never overwrites another
// source's draft (D21) and Generate/Revise never loses the draft on screen
// (D22).
//
// Before the fix saveWritingDraft() in assets/dashboard/index.html sent the
// last saved draft id whatever source was picked, and POST /writing/draft
// updates the row whose id it gets (source and all), so saving a draft for
// video B overwrote the saved draft for video A. Generate/Revise wrote
// "Preparing your draft..." into the preview and the composer and turned Save
// on, so a failed or agent-less run lost hand edits and Save could store the
// placeholder.
//
// Runs the REAL dashboard script (everything before init()) in a node:vm
// context over a fake page holding every id the markup declares, with the
// classes and disabled state the markup gives it. The fake helper keeps
// drafts the way index.save_writing_draft does: insert without an id, update
// that row in place with one, 404 for an unknown id.
//   source_switch   -- save for A, switch to B (or clear the source), save:
//                      A's draft is untouched and B gets its own; saving
//                      again from the same source still updates in place
//   recovered_draft -- a draft recovered after a reload stays with its
//                      source: its id is reused only once that source is
//                      picked again
//   generate_run    -- while Generate runs, progress shows in its own status
//                      line, the preview and composer keep the draft,
//                      Save/Copy/Revise/Generate are off and a second click
//                      starts nothing; a failure keeps the draft and says so
//                      in the status line; a success replaces the draft
//   no_agent        -- a run that comes back without a draft (no writing
//                      agent) keeps hand edits and earlier output; with
//                      nothing written the setup notice still fills the
//                      preview
//   script_run      -- the script path follows the same rules
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/dash_draft_safety_test.mjs [group ...]
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

// id -> tag, classes and disabled state for every element the markup declares.
const TAGS = new Map();
const CLASSES = new Map();
const DISABLED = new Set();
{
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let m;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (!id || TAGS.has(id[1])) continue;
    TAGS.set(id[1], m[1].toUpperCase());
    const cls = /\sclass="([^"]*)"/.exec(m[2]);
    CLASSES.set(id[1], cls ? cls[1].split(/\s+/).filter(Boolean) : []);
    if (/\sdisabled(?=[\s=\/]|$)/.test(m[2])) DISABLED.add(id[1]);
  }
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
    this.hidden = false;
    this.disabled = DISABLED.has(id);
    this.checked = false;
    this.scrollTop = 0;
    this.files = [];
    this.options = [];
    this.dataset = {};
    this.style = {};
    this.classList = new FakeClassList(CLASSES.get(id) || []);
    this._attrs = {};
  }
  addEventListener() {}
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
  closest() { return null; }
  contains() { return false; }
  setCustomValidity() {}
  focus() {}
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

const TOOL_PATH = "/mcp/v1/tools/call";
const ASSEMBLE_PATH = "/api/corpus/v1/assemble";
const DRAFT_KEY = "uoink.writingDraftId";

// Two saved sources in the Generate picker. writingRowId() reads `id`.
const SOURCES = [
  { id: "yoink-A", video_id: "vidA", title: "Video A", channel: "Creator A", url: "https://www.youtube.com/watch?v=vidAAAAAAAA" },
  { id: "yoink-B", video_id: "vidB", title: "Video B", channel: "Creator B", url: "https://www.youtube.com/watch?v=vidBBBBBBBB" },
];

// One fresh dashboard page on the Generate tab. `helper` is the fake helper:
// drafts = stored writing drafts by id; tool = the MCP tool reply;
// assemble = [status, body] for the corpus assembly; holdNext = paths whose
// next answer is computed at request time but delivered only on release.
function makePage() {
  const timers = [];
  const fakeSetTimeout = (fn, ms = 0) => { timers.push({ fn, ms }); return timers.length; };
  const view = { mode: "" }; // the checked writingMode radio; "" = none (tweet)

  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (selector === ".content") return contentEl;
      if (selector === 'input[name="writingMode"]:checked' && view.mode) return { value: view.mode };
      return null;
    },
    querySelectorAll: () => [],
    addEventListener() {},
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase()),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };
  const getEl = (id) => {
    if (!elements.has(id)) elements.set(id, new FakeEl(id, TAGS.get(id)));
    return elements.get(id);
  };
  document.getElementById = getEl;
  document.body = new FakeEl("body", "BODY");
  document.documentElement = new FakeEl("html", "HTML");
  const contentEl = new FakeEl("", "MAIN");

  const helper = {
    drafts: new Map(),
    nextDraftId: 1,
    tool: () => ({ ok: true }),
    assemble: () => [200, { ok: true, data: { assembled: [] } }],
    holdNext: [],
  };
  // index.save_writing_draft: insert without an id, update that row (source,
  // kind, body, credit) with one, refuse an unknown id or a blank body.
  const saveDraft = (body) => {
    const text = String((body && body.body) || "");
    if (!text.trim()) return [400, { ok: false, error: "draft body required" }];
    const row = {
      yoink_id: String(body.source_yoink_id || body.yoink_id || "").trim() || null,
      kind: String(body.kind || "tweet"),
      title: body.title === undefined ? null : body.title,
      body: text,
      source_credit_line: body.source_credit_line === undefined ? null : body.source_credit_line,
    };
    let id = body.id;
    if (id === undefined || id === null) {
      id = helper.nextDraftId++;
    } else {
      id = Number(id);
      if (!helper.drafts.has(id)) return [404, { ok: false, error: `draft ${id} not found` }];
    }
    helper.drafts.set(id, { id, ...row });
    return [200, { ok: true, draft: { ...helper.drafts.get(id) }, id }];
  };

  const requests = [];
  const held = [];
  const respond = (path, method, body) => {
    if (path === "/token") return jsonResponse({ ok: true, token: "test-token" });
    if (path === "/writing/draft" && method === "POST") {
      const [status, payload] = saveDraft(body);
      return jsonResponse(payload, status);
    }
    const draftGet = /^\/writing\/draft\/(\d+)$/.exec(path);
    if (draftGet) {
      const draft = helper.drafts.get(Number(draftGet[1]));
      return draft
        ? jsonResponse({ ok: true, draft: { ...draft }, body: draft.body })
        : jsonResponse({ ok: false, error: "draft not found" }, 404);
    }
    const item = /^\/api\/corpus\/v1\/items\/([^/?]+)$/.exec(path);
    if (item) {
      const source = SOURCES.find((s) => s.video_id === decodeURIComponent(item[1]));
      if (!source) return jsonResponse({ ok: false, error: "not found" }, 404);
      return jsonResponse({
        ok: true,
        data: {
          item: { video_id: source.video_id, title: source.title, channel: source.channel, url: source.url },
          content: { markdown: "" },
          attachments: [],
        },
      });
    }
    if (path.startsWith("/yoinks/") && path.includes("/screenshots")) return jsonResponse({ ok: true, screenshots: [] });
    if (path === TOOL_PATH) {
      const name = body && body.params && body.params.name;
      const args = (body && body.params && body.params.arguments) || {};
      return mcpReply(helper.tool(name, args));
    }
    if (path === ASSEMBLE_PATH) {
      const [status, payload] = helper.assemble(body);
      return jsonResponse(payload, status);
    }
    return jsonResponse({ ok: true });
  };
  const fakeFetch = (url, opts = {}) => {
    const path = String(url);
    const method = (opts && opts.method) || "GET";
    let body = null;
    try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (_) { body = opts.body; }
    requests.push({ path, method, body });
    const answer = respond(path, method, body);
    const at = helper.holdNext.indexOf(path);
    if (at < 0) return Promise.resolve(answer);
    helper.holdNext.splice(at, 1);
    return new Promise((resolve) => held.push({ path, release: () => resolve(answer) }));
  };

  const window = {
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
    setTimeout: fakeSetTimeout,
    clearTimeout() {},
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
    setTimeout: fakeSetTimeout,
    clearTimeout() {},
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
;globalThis.__page = { state, els, saveWritingDraft, restoreWritingDraft, selectWritingSourceById,
  clearWritingSource, generateWriting, syncThreadInput, setWritingOutput, currentWritingText };`, ctx);
  const page = ctx.__page;
  page.state.writingSourceRows = SOURCES.map((s) => ({ ...s }));
  page.state.writingSourceLoaded = true;

  // The composer cards are textareas inside #threadBuilder. Typing changes a
  // textarea's value, not the builder's markup, so a card keeps what was
  // typed until the page renders the builder again; count those renders.
  const builder = getEl("threadBuilder");
  let builderHtml = String(builder.innerHTML || "");
  let builderRenders = 0;
  Object.defineProperty(builder, "innerHTML", {
    get: () => builderHtml,
    set: (value) => { builderHtml = String(value); builderRenders++; },
  });
  let typed = null;

  const ACTIONS = ["copyWriting", "saveWriting", "reviseWriting"];
  return {
    page,
    state: page.state,
    els: page.els,
    view,
    helper,
    getEl,
    storage: ctx.localStorage,
    async pick(letter) {
      await page.selectWritingSourceById(`yoink-${letter}`);
      await settle();
    },
    // What the document "input" delegation does for a composer card.
    type(text, index = 0) {
      page.syncThreadInput({ dataset: { threadText: String(index) }, value: text, closest: () => null });
      typed = { text, renders: builderRenders };
    },
    // Whether a composer card shows `text`: typed into a card the page has
    // not rendered since, or rendered into the builder.
    composerShows(text) {
      if (typed && typed.text === text && typed.renders === builderRenders) return true;
      return builderHtml.includes(text);
    },
    async save() {
      await page.saveWritingDraft();
      await settle();
    },
    posts: () => requests.filter((r) => r.path === "/writing/draft" && r.method === "POST").map((r) => r.body),
    count: (path) => requests.filter((r) => r.path === path).length,
    held: () => held.map((h) => h.path),
    release(path) {
      const at = held.findIndex((h) => h.path === path);
      if (at < 0) return false;
      held.splice(at, 1)[0].release();
      return true;
    },
    actionStates: () => Object.fromEntries([...ACTIONS, "generateWriting"].map((id) => [id, getEl(id).disabled ? "off" : "on"])),
    actionsOff: () => ACTIONS.every((id) => getEl(id).disabled),
    actionsOn: () => ACTIONS.every((id) => !getEl(id).disabled),
    generateOff: () => getEl("generateWriting").disabled,
    status() {
      const el = getEl("writingGenerateStatus");
      const html = String(el.innerHTML || "");
      return { shown: !el.classList.contains("hidden") && html.trim() !== "", html: html.trim() };
    },
    preview: () => ({ raw: String(page.els.writingOutput.dataset.rawText || ""), html: String(page.els.writingOutput.innerHTML || "") }),
    composer: () => [...page.state.writingDrafts],
    composerHtml: () => builderHtml,
  };
}

function hasPlaceholder(p) {
  const text = `${p.preview().raw}\n${p.preview().html}\n${p.composer().join("\n")}\n${p.composerHtml()}\n${p.page.currentWritingText()}`;
  return text.includes("Preparing your draft") || text.includes("Preparing a grounded script");
}

function draftRow(p, id) {
  const row = p.helper.drafts.get(id);
  return row ? { yoink_id: row.yoink_id, body: row.body } : null;
}

// ---------------------------------------------------------------------------
async function groupSourceSwitch() {
  await scenario("save for A, switch to B, save", async () => {
    const p = makePage();
    await p.pick("A");
    p.type("Draft for video A.");
    await p.save();
    check(p.posts().length === 1 && p.posts()[0].id === undefined, "the first save creates a draft", p.posts());
    check(JSON.stringify(draftRow(p, 1)) === JSON.stringify({ yoink_id: "yoink-A", body: "Draft for video A." }), "draft 1 is A's draft", draftRow(p, 1));

    await p.pick("B");
    p.type("Draft for video B.");
    await p.save();
    const second = p.posts()[1] || {};
    check(second.id === undefined, "saving for B does not send A's draft id", second.id);
    check(second.source_yoink_id === "yoink-B", "the save for B is filed under B", second.source_yoink_id);
    check(JSON.stringify(draftRow(p, 1)) === JSON.stringify({ yoink_id: "yoink-A", body: "Draft for video A." }), "A's saved draft is untouched", draftRow(p, 1));
    check(p.helper.drafts.size === 2 && JSON.stringify(draftRow(p, 2)) === JSON.stringify({ yoink_id: "yoink-B", body: "Draft for video B." }), "B gets a draft of its own", [...p.helper.drafts.values()]);
    check(p.state.writingDraftId === 2 && p.storage.getItem(DRAFT_KEY) === "2", "the page now holds B's draft id, and so does the reload key", [p.state.writingDraftId, p.storage.getItem(DRAFT_KEY)]);

    // And back again: B's draft is not overwritten from A either.
    await p.pick("A");
    p.type("Second draft for video A.");
    await p.save();
    const third = p.posts()[2] || {};
    check(third.id === undefined, "switching back to A and saving does not send B's draft id", third.id);
    check(JSON.stringify(draftRow(p, 2)) === JSON.stringify({ yoink_id: "yoink-B", body: "Draft for video B." }), "B's saved draft is untouched", draftRow(p, 2));
    check(JSON.stringify(draftRow(p, 1)) === JSON.stringify({ yoink_id: "yoink-A", body: "Draft for video A." }), "A's first draft is still untouched", draftRow(p, 1));
  });

  await scenario("clear the source, then save", async () => {
    const p = makePage();
    await p.pick("A");
    p.type("Draft for video A.");
    await p.save();
    p.page.clearWritingSource();
    p.type("A draft with no source yet.");
    await p.save();
    const second = p.posts()[1] || {};
    check(second.id === undefined && second.source_yoink_id === undefined, "a save with no source picked does not send A's draft id", second);
    check(JSON.stringify(draftRow(p, 1)) === JSON.stringify({ yoink_id: "yoink-A", body: "Draft for video A." }), "A's saved draft keeps its source and body", draftRow(p, 1));
    check(p.helper.drafts.size === 2 && JSON.stringify(draftRow(p, 2)) === JSON.stringify({ yoink_id: null, body: "A draft with no source yet." }), "the sourceless draft is saved on its own", [...p.helper.drafts.values()]);
  });

  await scenario("saving again from the same source updates that draft", async () => {
    const p = makePage();
    await p.pick("A");
    p.type("Draft for video A.");
    await p.save();
    p.type("Draft for video A, tightened.");
    await p.save();
    check((p.posts()[1] || {}).id === 1, "a second save from A updates A's draft", p.posts()[1]);
    check(p.helper.drafts.size === 1 && draftRow(p, 1).body === "Draft for video A, tightened.", "A still has one draft, with the new body", [...p.helper.drafts.values()]);
    // A look at B without saving there leaves A's draft A's.
    await p.pick("B");
    await p.pick("A");
    p.type("Draft for video A, final.");
    await p.save();
    check((p.posts()[2] || {}).id === 1, "back on A, Save still updates A's draft", p.posts()[2]);
    check(p.helper.drafts.size === 1 && JSON.stringify(draftRow(p, 1)) === JSON.stringify({ yoink_id: "yoink-A", body: "Draft for video A, final." }), "no duplicate draft for A", [...p.helper.drafts.values()]);
  });
}

async function groupRecoveredDraft() {
  function seeded() {
    const p = makePage();
    p.helper.drafts.set(7, { id: 7, yoink_id: "yoink-A", kind: "tweet", title: null, body: "Recovered draft for video A.", source_credit_line: "via @CreatorA" });
    p.helper.nextDraftId = 8;
    p.storage.setItem(DRAFT_KEY, "7");
    return p;
  }

  await scenario("a recovered draft is not overwritten from another source", async () => {
    const p = seeded();
    await p.pick("B");
    await p.page.restoreWritingDraft();
    await settle();
    check(p.page.currentWritingText() === "Recovered draft for video A.", "the saved draft is recovered into the composer", p.page.currentWritingText());
    check(p.state.writingDraftId === 7, "the page holds the recovered draft id", p.state.writingDraftId);
    p.type("Recovered draft for video A, reworked for B.");
    await p.save();
    const sent = p.posts()[0] || {};
    check(sent.id === undefined && sent.source_yoink_id === "yoink-B", "saving with B picked does not send A's draft id", sent);
    check(JSON.stringify(draftRow(p, 7)) === JSON.stringify({ yoink_id: "yoink-A", body: "Recovered draft for video A." }), "the recovered draft for A is untouched", draftRow(p, 7));
    check(JSON.stringify(draftRow(p, 8)) === JSON.stringify({ yoink_id: "yoink-B", body: "Recovered draft for video A, reworked for B." }), "B's draft is saved on its own", draftRow(p, 8));
  });

  await scenario("a recovered draft saved before its source is picked keeps its source", async () => {
    const p = seeded();
    await p.page.restoreWritingDraft();
    await settle();
    p.type("Recovered draft for video A, edited.");
    await p.save();
    const sent = p.posts()[0] || {};
    check(sent.id === undefined, "saving with no source picked does not send A's draft id", sent);
    check(JSON.stringify(draftRow(p, 7)) === JSON.stringify({ yoink_id: "yoink-A", body: "Recovered draft for video A." }), "the recovered draft keeps its source", draftRow(p, 7));
    check(p.helper.drafts.size === 2, "the sourceless save is a new draft", [...p.helper.drafts.values()]);
  });

  await scenario("a recovered draft updates in place once its source is picked", async () => {
    const p = seeded();
    await p.page.restoreWritingDraft();
    await settle();
    await p.pick("A");
    p.type("Recovered draft for video A, finished.");
    await p.save();
    const sent = p.posts()[0] || {};
    check(sent.id === 7 && sent.source_yoink_id === "yoink-A", "with A picked again, Save updates the recovered draft", sent);
    check(p.helper.drafts.size === 1 && JSON.stringify(draftRow(p, 7)) === JSON.stringify({ yoink_id: "yoink-A", body: "Recovered draft for video A, finished." }), "the recovered draft holds the new body", [...p.helper.drafts.values()]);
  });
}

const HAND = "My own take on video A, typed by hand.";
const EARLIER = "Earlier generated draft for video A.";
const GENERATED = "Generated tweet for video A.";

async function groupGenerateRun() {
  await scenario("a failed Generate keeps hand edits", async () => {
    const p = makePage();
    await p.pick("A");
    p.type(HAND);
    check(p.actionsOn(), "a hand-written draft turns Save/Copy/Revise on", p.actionStates());
    p.helper.tool = () => ({ ok: false, error: "model timed out" });
    p.helper.holdNext.push(TOOL_PATH);
    const run = p.page.generateWriting();
    await settle();
    check(JSON.stringify(p.held()) === JSON.stringify([TOOL_PATH]), "the generate request is in flight", p.held());
    const during = p.status();
    check(during.shown && during.html.includes("Preparing your draft..."), "progress shows in its own status line", during);
    check(!hasPlaceholder(p), "the progress text is not written into the preview or the composer", { preview: p.preview().raw, composer: p.composer() });
    check(JSON.stringify(p.composer()) === JSON.stringify([HAND]) && p.composerShows(HAND), "the composer keeps the hand edits while Generate runs", p.composer());
    check(p.page.currentWritingText() === HAND, "what Save would store is still the hand edit", p.page.currentWritingText());
    check(p.actionsOff(), "Save, Copy and Revise are off while Generate runs", p.actionStates());
    check(p.generateOff(), "Generate is off while it runs", p.actionStates());
    const second = p.page.generateWriting();
    await settle();
    check(p.count(TOOL_PATH) === 1, "a second Generate while one runs starts nothing", p.count(TOOL_PATH));

    check(p.release(TOOL_PATH), "the generate answer arrives");
    await run;
    await second;
    await settle();
    check(JSON.stringify(p.composer()) === JSON.stringify([HAND]) && p.composerShows(HAND), "a failed Generate keeps the hand edits", p.composer());
    check(!hasPlaceholder(p), "no placeholder is left behind", { preview: p.preview().raw, composer: p.composer() });
    const after = p.status();
    check(after.shown && after.html.includes("needs another pass") && !after.html.includes("Preparing"), "the failure is reported in the status line", after);
    check(p.actionsOn(), "Save, Copy and Revise come back for the kept draft", p.actionStates());
    check(!p.generateOff(), "Generate can be tried again", p.actionStates());
    await p.save();
    check(p.posts().length === 1 && p.posts()[0].body === HAND, "Save stores the hand edit", p.posts().map((b) => b.body));
  });

  await scenario("a failed Regenerate keeps the earlier generated draft", async () => {
    const p = makePage();
    await p.pick("A");
    p.page.setWritingOutput(EARLIER);
    check(p.actionsOn(), "an earlier generated draft turns Save/Copy/Revise on", p.actionStates());
    p.helper.tool = () => ({ ok: false, error: "model timed out" });
    p.helper.holdNext.push(TOOL_PATH);
    const run = p.page.generateWriting();
    await settle();
    check(p.preview().raw === EARLIER && JSON.stringify(p.composer()) === JSON.stringify([EARLIER]), "the earlier draft stays on screen while Regenerate runs", { preview: p.preview().raw, composer: p.composer() });
    check(p.actionsOff(), "Save, Copy and Revise are off while Regenerate runs", p.actionStates());
    check(p.release(TOOL_PATH), "the generate answer arrives");
    await run;
    await settle();
    check(p.preview().raw === EARLIER && p.preview().html.includes(EARLIER), "the preview still shows the earlier draft", p.preview());
    check(JSON.stringify(p.composer()) === JSON.stringify([EARLIER]), "the composer still holds the earlier draft", p.composer());
    check(p.status().shown && p.status().html.includes("needs another pass"), "the failure is reported in the status line", p.status());
    check(p.actionsOn(), "Save, Copy and Revise come back", p.actionStates());
    await p.save();
    check(p.posts().length === 1 && p.posts()[0].body === EARLIER, "Save stores the earlier draft", p.posts().map((b) => b.body));
  });

  await scenario("a successful Generate replaces the draft", async () => {
    const p = makePage();
    await p.pick("A");
    p.type(HAND);
    p.helper.tool = () => ({ ok: true, body: GENERATED, source_credit_line: "via @CreatorA" });
    p.helper.holdNext.push(TOOL_PATH);
    const run = p.page.generateWriting();
    await settle();
    p.type(`${HAND} Edited while it ran.`);
    check(p.actionsOff(), "typing while Generate runs keeps Save, Copy and Revise off", p.actionStates());
    check(p.status().shown && p.status().html.includes("Preparing your draft..."), "progress still shows in the status line", p.status());
    check(p.release(TOOL_PATH), "the generate answer arrives");
    await run;
    await settle();
    const composer = p.composer();
    check(p.preview().raw.startsWith(GENERATED), "the generated draft fills the preview", p.preview().raw);
    check(composer.length === 1 && composer[0].startsWith(GENERATED) && !composer[0].includes(HAND), "the generated draft replaces the composer", composer);
    check(!p.status().shown, "the status line clears on success", p.status());
    check(p.actionsOn() && !p.generateOff(), "Save, Copy, Revise and Generate come back on", p.actionStates());
    await p.save();
    check(p.posts().length === 1 && String(p.posts()[0].body).startsWith(GENERATED), "Save stores the generated draft", p.posts().map((b) => b.body));
  });
}

const GROUNDING = { ok: true, mode: "grounding_only", context: { source_credit_line: "via @CreatorA" } };

async function groupNoAgent() {
  await scenario("Generate with no writing agent keeps hand edits", async () => {
    const p = makePage();
    await p.pick("A");
    p.type(HAND);
    p.helper.tool = () => GROUNDING;
    await p.page.generateWriting();
    await settle();
    check(p.count(TOOL_PATH) === 1, "Generate asked the helper", p.count(TOOL_PATH));
    check(JSON.stringify(p.composer()) === JSON.stringify([HAND]) && p.composerShows(HAND), "the composer keeps the hand edits", p.composer());
    check(!hasPlaceholder(p), "no placeholder is left behind", { preview: p.preview().raw, composer: p.composer() });
    check(p.status().shown && p.status().html.includes("Connect a writing agent"), "the status line says a writing agent is needed", p.status());
    check(p.actionsOn(), "Save, Copy and Revise stay on for the hand edit", p.actionStates());
    await p.save();
    check(p.posts().length === 1 && p.posts()[0].body === HAND, "Save stores the hand edit", p.posts().map((b) => b.body));
  });

  await scenario("Generate with no writing agent keeps the earlier generated draft", async () => {
    const p = makePage();
    await p.pick("A");
    p.page.setWritingOutput(EARLIER);
    p.helper.tool = () => GROUNDING;
    await p.page.generateWriting();
    await settle();
    check(p.preview().raw === EARLIER && p.preview().html.includes(EARLIER), "the preview still shows the earlier draft", p.preview());
    check(JSON.stringify(p.composer()) === JSON.stringify([EARLIER]), "the composer still holds the earlier draft", p.composer());
    check(p.status().shown && p.status().html.includes("Connect a writing agent"), "the status line says a writing agent is needed", p.status());
    check(p.actionsOn(), "Save, Copy and Revise stay on", p.actionStates());
  });

  await scenario("Generate with no writing agent and nothing written", async () => {
    const p = makePage();
    await p.pick("A");
    check(p.actionsOff(), "nothing written: Save, Copy and Revise start off", p.actionStates());
    p.helper.tool = () => GROUNDING;
    await p.page.generateWriting();
    await settle();
    check(p.preview().html.includes("Connect a writing agent") && p.preview().raw === "", "the setup notice fills the empty preview", p.preview());
    check(!p.status().shown, "the status line is clear", p.status());
    check(p.actionsOff(), "Save, Copy and Revise stay off", p.actionStates());
    check(!p.generateOff(), "Generate is on again", p.actionStates());
    check(!hasPlaceholder(p), "no placeholder is left behind", { preview: p.preview().raw, composer: p.composer() });
  });
}

const EARLIER_SCRIPT = "Earlier script for video A.";

async function groupScriptRun() {
  await scenario("a failed script run keeps the earlier script", async () => {
    const p = makePage();
    p.view.mode = "script";
    await p.pick("A");
    p.page.setWritingOutput(EARLIER_SCRIPT);
    p.helper.assemble = () => [500, { ok: false, error: "assembly failed" }];
    p.helper.holdNext.push(ASSEMBLE_PATH);
    const run = p.page.generateWriting();
    await settle();
    check(JSON.stringify(p.held()) === JSON.stringify([ASSEMBLE_PATH]), "the script grounding request is in flight", p.held());
    check(p.status().shown && p.status().html.includes("Preparing a grounded script..."), "script progress shows in the status line", p.status());
    check(!hasPlaceholder(p) && p.preview().raw === EARLIER_SCRIPT, "the earlier script stays on screen while the run is going", p.preview().raw);
    check(p.actionsOff() && p.generateOff(), "Save, Copy, Revise and Generate are off while the script runs", p.actionStates());
    check(p.release(ASSEMBLE_PATH), "the grounding answer arrives");
    await run;
    await settle();
    check(p.preview().raw === EARLIER_SCRIPT && JSON.stringify(p.composer()) === JSON.stringify([EARLIER_SCRIPT]), "a failed script run keeps the earlier script", { preview: p.preview().raw, composer: p.composer() });
    check(p.status().shown && p.status().html.includes("Generate needs another pass"), "the failure is reported in the status line", p.status());
    check(p.actionsOn() && !p.generateOff(), "Save, Copy, Revise and Generate come back on", p.actionStates());
    await p.save();
    check(p.posts().length === 1 && p.posts()[0].body === EARLIER_SCRIPT && p.posts()[0].kind === "script", "Save stores the earlier script", p.posts());
  });

  await scenario("a script run with no writing agent keeps the earlier script", async () => {
    const p = makePage();
    p.view.mode = "script";
    await p.pick("A");
    p.page.setWritingOutput(EARLIER_SCRIPT);
    await p.page.generateWriting();
    await settle();
    check(p.count(ASSEMBLE_PATH) === 1, "the script run grounded itself", p.count(ASSEMBLE_PATH));
    check(p.preview().raw === EARLIER_SCRIPT && JSON.stringify(p.composer()) === JSON.stringify([EARLIER_SCRIPT]), "the earlier script stays", { preview: p.preview().raw, composer: p.composer() });
    check(p.status().shown && p.status().html.includes("Connect a writing agent"), "the status line says a writing agent is needed", p.status());
    check(p.actionsOn(), "Save, Copy and Revise stay on", p.actionStates());
    check(!hasPlaceholder(p), "no placeholder is left behind", { preview: p.preview().raw, composer: p.composer() });
  });
}

const GROUPS = {
  source_switch: groupSourceSwitch,
  recovered_draft: groupRecoveredDraft,
  generate_run: groupGenerateRun,
  no_agent: groupNoAgent,
  script_run: groupScriptRun,
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
