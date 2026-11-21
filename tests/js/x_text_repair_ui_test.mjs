// 3.18.0 dashboard: the "Fix cut-off X posts" block (Settings, Library and
// export) and the reader's cut-off prompt. Runs the real functions from
// assets/dashboard/index.html against a small fake DOM.
// Run directly:  node tests/js/x_text_repair_ui_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "..", "..", "assets", "dashboard", "index.html"), "utf8");
const start = html.indexOf("    // ---- 3.18.0: an X save that holds only part of the post");
const end = html.indexOf("    for (const [id, onClick] of [", start);
if (start < 0 || end < 0) throw new Error("x text block not found in index.html");

let failures = 0;
function check(cond, msg, extra) {
  if (!cond) { failures++; console.error(`FAIL: ${msg}`, extra === undefined ? "" : extra); }
  else console.log(`ok: ${msg}`);
}

function el(tag = "div") {
  const classes = new Set();
  const node = {
    tagName: tag.toUpperCase(), textContent: "", innerHTML: "", disabled: false, title: "", href: "", dataset: {},
    target: "", rel: "", children: [],
    classList: {
      toggle(name, on) { if (on === undefined ? !classes.has(name) : on) classes.add(name); else classes.delete(name); },
      add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    append(...kids) { node.children.push(...kids); },
    replaceChildren(...kids) { node.children = kids; node.innerHTML = ""; },
  };
  return node;
}
// Everything a list node holds, as plain records, to check what the page would show.
function flat(node) {
  return node.children.flatMap((child) => [child, ...flat(child)]);
}
const IDS = ["x-text-repair", "xTextRepairCount", "xTextRepairHow", "xTextRepairControls", "xTextRepairStart",
  "xTextRepairPause", "xTextRepairStop", "xTextRepairProgress", "xTextRepairListBox", "xTextRepairListLabel",
  "xTextRepairList", "yoinkXCutOff", "yoinkXCutOffText", "yoinkXCutOffFix", "yoinkXCutOffOpen",
  "yoinkXCutOffStatus", "fxtwitterToggle"];

function page({ settings = {}, replies = {} } = {}) {
  const nodes = Object.fromEntries(IDS.map((id) => [id, el()]));
  const calls = [];
  const ctx = {
    state: { settings, activeTab: "settings", selectedYoink: null, selectedYoinkSidecar: null },
    document: { getElementById: (id) => nodes[id] || null, createElement: (tag) => el(tag) },
    window: { setTimeout: () => 0, clearTimeout: () => {} },
    Date, Number, Math, Boolean, String, Object, JSON, Array, Promise, encodeURIComponent,
    htmlEscape: (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
    videoIdOf: (row) => (row && row.video_id) || "",
    authFetch: async (path, opts = {}) => {
      calls.push([path, opts.body ? JSON.parse(opts.body) : null]);
      const key = opts.body ? JSON.parse(opts.body).action : (path.includes("?video_id=") ? "item" : "get");
      let reply = replies[key];
      if (Array.isArray(reply)) reply = reply.length > 1 ? reply.shift() : reply[0];
      if (reply instanceof Error) throw reply;
      return reply;
    },
    saveSettingsPatch: async (patch) => { Object.assign(settings, patch); return true; },
    openYoinkDetail: async () => { calls.push(["reopen"]); },
  };
  vm.createContext(ctx);
  vm.runInContext(html.slice(start, end), ctx);
  ctx.xTextPause = async () => {};  // no real waiting between status checks
  return { ctx, nodes, calls };
}
const hidden = (node) => node.classList.contains("hidden");

// ---- empty state ---------------------------------------------------------------
{
  const p = page({ replies: { get: { ok: true, status: "idle", candidates: 0, articles: 0, sample: [], fixed_total: 0 } } });
  await p.ctx.loadXTextRepair();
  check(p.nodes.xTextRepairCount.textContent === "No X saves look cut off.", "empty state says nothing is cut off");
  check(hidden(p.nodes.xTextRepairControls) && hidden(p.nodes.xTextRepairHow) && hidden(p.nodes.xTextRepairListBox),
    "empty state hides the controls, the explanation and the list");
}

// ---- switch off: count, both ways, nothing starts --------------------------------
{
  const sample = Array.from({ length: 20 }, (_, i) => ({ video_id: `x_${i}`, title: i ? `Post ${i}` : "<b>odd</b> title",
    url: `https://x.com/i/status/19000000000000000${String(i).padStart(2, "0")}`, kind: i === 3 ? "article" : "thread" }));
  const p = page({ replies: { get: { ok: true, status: "idle", candidates: 1065, articles: 12, sample, fxtwitter: false } } });
  await p.ctx.loadXTextRepair();
  check(p.nodes.xTextRepairCount.textContent === "1,053 X saves may be cut off and 12 saved posts only link to an X Article.",
    "a 1,000+ library gets a readable count", p.nodes.xTextRepairCount.textContent);
  const how = p.nodes.xTextRepairHow.innerHTML;
  check(/FxTwitter/.test(how) && /Uoink this post/.test(how) && how.includes('href="#settings/x-full-text"'),
    "switch off explains both ways and links to the switch", how);
  check(p.nodes.xTextRepairStart.disabled === true && /FxTwitter/.test(p.nodes.xTextRepairStart.title),
    "Start is off until the switch is on");
  check(p.nodes.xTextRepairListLabel.textContent === "Posts to open and save (first 20 of 1,065)", "the list says it is a sample");
  const items = flat(p.nodes.xTextRepairList);
  check(p.nodes.xTextRepairList.children.length === 20 && p.nodes.xTextRepairList.innerHTML === "",
    "the list is built node by node, never from HTML");
  check(items.some((n) => n.textContent === "<b>odd</b> title" && n.tagName === "A"), "titles are text, not markup");
  check(items.filter((n) => n.tagName === "SPAN" && n.textContent === "Article").length === 1, "Article links are labelled");
  check(!/—|;/.test(how.replace(/&[a-z]+;/g, "")), "no em dash or semicolon in the copy");
  check(/FxTwitter is never asked/.test(how) && !/sends nothing anywhere/.test(how), "the copy says only what is true");
}

// ---- review fix: a stored link is never rendered unless it is an X post ----------------
{
  const bad = ["javascript:alert(1)", "https://evil.test/i/status/1", "data:text/html,hi", "JAVASCRIPT:alert(1)",
    "https://x.com/i/status/1\" onmouseover=\"alert(1)", "https://x.com.evil.test/i/status/1", 7, null];
  const sample = bad.map((url, i) => ({ video_id: `x_${i}`, title: `Post ${i}`, url, kind: "thread" }))
    .concat([{ video_id: "x_ok", title: "Fine", url: "https://x.com/i/status/1900000000000000002", kind: "thread" }]);
  const p = page({ replies: { get: { ok: true, status: "idle", candidates: 9, articles: 0, sample, fxtwitter: false } } });
  await p.ctx.loadXTextRepair();
  const links = flat(p.nodes.xTextRepairList).filter((n) => n.tagName === "A");
  check(links.length === 1 && links[0].href === "https://x.com/i/status/1900000000000000002"
    && links[0].rel === "noreferrer" && links[0].target === "_blank", "only the real X post becomes a link",
    links.map((n) => n.href));
  check(flat(p.nodes.xTextRepairList).filter((n) => n.tagName === "SPAN").length === 8,
    "the others are listed as plain text");
}

// ---- switch on: start, progress, back-off ------------------------------------------
{
  const running = { ok: true, status: "running", running: true, candidates: 40, articles: 0, sample: [], fxtwitter: true,
    total: 40, run: { checked: 5, fixed: 4 }, current: { title: "Studio changes" }, backoff_until: Date.now() / 1000 + 120 };
  const p = page({ settings: { fxtwitter_enrichment_enabled: true },
    replies: { get: { ok: true, status: "idle", candidates: 40, articles: 0, sample: [], fxtwitter: true }, start: running } });
  await p.ctx.loadXTextRepair();
  check(p.nodes.xTextRepairStart.disabled === false && /about 3 minutes/.test(p.nodes.xTextRepairHow.innerHTML),
    "switch on: Start is ready and the time it takes is said", p.nodes.xTextRepairHow.innerHTML);
  p.ctx.authFetch = async (path, opts = {}) => { p.calls.push([path, opts.body ? JSON.parse(opts.body) : null]); return running; };
  await p.ctx.xTextRepairAction("start");
  check(p.calls.some(([path, body]) => path === "/library/x-text-repair" && body && body.action === "start"), "Start posts start");
  const line = p.nodes.xTextRepairProgress.textContent;
  check(/Checked 5 of 40\. Fixed 4\./.test(line) && /Studio changes/.test(line) && /slow down/.test(line),
    "progress names the count, the post and the back-off", line);
  check(p.nodes.xTextRepairStart.disabled && !p.nodes.xTextRepairPause.disabled && !p.nodes.xTextRepairStop.disabled,
    "while running only Pause and Stop work");
}

// ---- refused start keeps the block readable ----------------------------------------
{
  const refusal = Object.assign(new Error("Turn on Get full long posts and Articles through FxTwitter in Settings, Capture first."), {
    data: { ok: false, code: "needs_fxtwitter", status: "idle", candidates: 3, articles: 0, sample: [], fxtwitter: false,
      error: "Turn on Get full long posts and Articles through FxTwitter in Settings, Capture first." } });
  const p = page({ replies: { get: { ok: true, status: "idle", candidates: 3, sample: [], fxtwitter: false }, start: refusal } });
  await p.ctx.loadXTextRepair();
  await p.ctx.xTextRepairAction("start");
  check(p.nodes.xTextRepairCount.textContent === "3 X saves may be cut off.", "a refused start keeps the count");
  check(/Settings, Capture/.test(p.nodes.xTextRepairProgress.textContent), "and says why");
}

// ---- the reader's prompt -------------------------------------------------------------
{
  // Deliberately changed in review: the fix answers "queued" and the reader
  // asks how it went until the helper's worker is done.
  const p = page({ replies: { fix: { ok: true, queued: true, status: "working" },
    item: [{ ok: true, item: { status: "working" } }, { ok: true, item: { status: "fixed", note: "" } }] } });
  const row = { video_id: "x_one" };
  const sidecar = { x_text_cut_off: { reason: "long_post", open_url: "https://x.com/i/status/1900000000000000002" } };
  p.ctx.state.selectedYoink = row;
  p.ctx.state.selectedYoinkSidecar = sidecar;
  p.ctx.renderXCutOff(row, sidecar);
  check(!hidden(p.nodes.yoinkXCutOff) && /cut this post short/.test(p.nodes.yoinkXCutOffText.textContent),
    "a cut-off post shows the prompt");
  check(p.nodes.yoinkXCutOffFix.textContent === "Turn on FxTwitter and get it"
    && p.nodes.yoinkXCutOffOpen.href === "https://x.com/i/status/1900000000000000002",
    "two choices: turn the switch on, or open the post on X");
  await p.ctx.fixXCutOff();
  check(p.ctx.state.settings.fxtwitter_enrichment_enabled === true, "the first choice turns the switch on");
  check(p.calls.some(([path, body]) => path === "/library/x-text-repair" && body && body.action === "fix" && body.video_id === "x_one")
    && p.calls.some(([name]) => name === "reopen"), "then fixes this save and reloads it", p.calls);
  p.ctx.renderXCutOff(row, { x_text_cut_off: { reason: "article", open_url: "https://x.com/i/article/1900000000000000777", title: "Build notes" } });
  check(/links to an X Article, "Build notes"/.test(p.nodes.yoinkXCutOffText.textContent)
    && p.nodes.yoinkXCutOffOpen.textContent === "Open the Article on X", "an Article link post says so");
  p.ctx.renderXCutOff(row, {});
  check(hidden(p.nodes.yoinkXCutOff), "a whole save shows no prompt");
  check(p.calls.filter(([path]) => path === "/library/x-text-repair?video_id=x_one").length === 2,
    "it asked about this save until it was done", p.calls);
  p.ctx.renderXCutOff(row, { x_text_cut_off: { reason: "long_post", open_url: "javascript:alert(1)" } });
  check(hidden(p.nodes.yoinkXCutOff), "a prompt with a link that isn't X is not shown");
}

// ---- review fix: saving an Article leaves only the confirmation -------------------------
{
  const p = page({ settings: { fxtwitter_enrichment_enabled: true }, replies: { fix: { ok: true, queued: true },
    item: { ok: true, item: { status: "fixed", saved_as: "x-article_abc", note: "" } } } });
  const row = { video_id: "x_art" };
  const sidecar = { x_text_cut_off: { reason: "article", open_url: "https://x.com/i/article/1900000000000000777", title: "Notes" } };
  p.ctx.state.selectedYoink = row;
  p.ctx.state.selectedYoinkSidecar = sidecar;
  p.ctx.renderXCutOff(row, sidecar);
  await p.ctx.fixXCutOff();
  check(!hidden(p.nodes.yoinkXCutOff) && /Saved the Article as its own item/.test(p.nodes.yoinkXCutOffText.textContent),
    "the confirmation shows", p.nodes.yoinkXCutOffText.textContent);
  check(hidden(p.nodes.yoinkXCutOffFix) && hidden(p.nodes.yoinkXCutOffOpen) && sidecar.x_text_cut_off === null,
    "and the stale prompt and its button are gone");
}

// ---- review fix: a fix that FxTwitter can't finish says why ------------------------------
{
  const p = page({ settings: { fxtwitter_enrichment_enabled: true }, replies: { fix: { ok: true, queued: true },
    item: { ok: true, item: { status: "failed", code: "rate_limited", note: "FxTwitter asked Uoink to slow down. Try again in a few minutes." } } } });
  const row = { video_id: "x_slow" };
  const sidecar = { x_text_cut_off: { reason: "long_post", open_url: "https://x.com/i/status/1900000000000000002" } };
  p.ctx.state.selectedYoink = row;
  p.ctx.state.selectedYoinkSidecar = sidecar;
  await p.ctx.fixXCutOff();
  check(/slow down/.test(p.nodes.yoinkXCutOffStatus.textContent) && !p.nodes.yoinkXCutOffFix.disabled,
    "the reason shows and the button works again", p.nodes.yoinkXCutOffStatus.textContent);
}

// ---- review fix: an interrupted run keeps being checked ----------------------------------
{
  let timers = 0;
  const p = page({ replies: { get: { ok: true, status: "interrupted", candidates: 4, articles: 0, sample: [], fxtwitter: false } } });
  p.ctx.window.setTimeout = () => { timers++; return 1; };
  await p.ctx.loadXTextRepair();
  check(timers === 1, "an interrupted run is checked again");
  check(/Turn FxTwitter back on/.test(p.nodes.xTextRepairProgress.textContent),
    "with the switch off it says what to do", p.nodes.xTextRepairProgress.textContent);
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nall cut-off X post dashboard checks passed");
