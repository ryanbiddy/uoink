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

function el() {
  const classes = new Set();
  return {
    textContent: "", innerHTML: "", disabled: false, title: "", href: "", dataset: {},
    classList: {
      toggle(name, on) { if (on === undefined ? !classes.has(name) : on) classes.add(name); else classes.delete(name); },
      add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
  };
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
    document: { getElementById: (id) => nodes[id] || null },
    window: { setTimeout: () => 0, clearTimeout: () => {} },
    Date, Number, Math, Boolean, String, Object, JSON, Array,
    htmlEscape: (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
    videoIdOf: (row) => (row && row.video_id) || "",
    authFetch: async (path, opts = {}) => {
      calls.push([path, opts.body ? JSON.parse(opts.body) : null]);
      const reply = replies[opts.body ? JSON.parse(opts.body).action : "get"];
      if (reply instanceof Error) throw reply;
      return reply;
    },
    saveSettingsPatch: async (patch) => { Object.assign(settings, patch); return true; },
    openYoinkDetail: async () => { calls.push(["reopen"]); },
  };
  vm.createContext(ctx);
  vm.runInContext(html.slice(start, end), ctx);
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
  check(p.nodes.xTextRepairList.innerHTML.includes("&lt;b&gt;odd&lt;/b&gt; title") && !p.nodes.xTextRepairList.innerHTML.includes("<b>"),
    "titles are escaped");
  check((p.nodes.xTextRepairList.innerHTML.match(/<span>Article<\/span>/g) || []).length === 1, "Article links are labelled");
  check(!/—|;/.test(how.replace(/&[a-z]+;/g, "")), "no em dash or semicolon in the copy");
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
  const p = page({ replies: { fix: { ok: true, outcome: "fixed" } } });
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
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nall cut-off X post dashboard checks passed");
