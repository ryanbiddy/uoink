// Execute the shipped research UI with synthetic data and no network or browser.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const page = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const script = page.slice(page.indexOf("// BEGIN RESEARCH:"), page.indexOf("// END RESEARCH"));
const escape = page.slice(page.indexOf("    function htmlEscape("), page.indexOf("    const FOCUSABLE_SELECTOR"));
const external = page.slice(page.indexOf("    function nativeApi("), page.indexOf("    // Bind fixed product buttons"));
const clickStart = page.indexOf('document.addEventListener("click", openExternalLink);');
const clickHandlers = page.slice(clickStart, page.indexOf('document.addEventListener("click", (event) => {', clickStart));
const settings = page.slice(page.indexOf("    function settingEdit("), page.indexOf("    function saveSettingControl("));
const switchTab = page.match(/    function switchTab\([\s\S]+?\n    }\r?\n/)[0];
class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.listeners = {};
    this.value = ""; this.checked = false; this.disabled = false; this.text = ""; this.attributes = {};
    const classes = new Set();
    this.classList = { add: (v) => classes.add(v), remove: (v) => classes.delete(v),
      toggle: (v, on) => on ? classes.add(v) : classes.delete(v), contains: (v) => classes.has(v) };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map((n) => n.textContent).join(""); }
  set innerHTML(_) { assert.fail("untrusted HTML insertion"); }
  append(...nodes) { nodes.forEach((node) => { node.parent = this; }); this.children.push(...nodes); }
  replaceChildren(...nodes) { this.text = ""; this.children = []; this.append(...nodes); }
  get firstChild() { return this.children[0]; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return name === "href" ? this.href : this.attributes[name] ?? null; }
  hasAttribute(name) {
    return name === "data-source-link" ? Object.hasOwn(this.dataset, "sourceLink") : Object.hasOwn(this.attributes, name);
  }
  closest(selector) {
    if (selector === `#${this.id}` || (selector.startsWith('a[target=') && this.tagName === "A"
        && (this.target === "_blank" || this.hasAttribute("data-source-link")))) return this;
    return this.parent?.closest(selector) || null;
  }
  focus() { this.focused = true; }
  click() { this.clicked = true; }
  remove() {}
}
const nodes = new Map();
for (const match of page.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"/gi)) {
  const node = new Element(match[1]); node.id = match[2]; nodes.set(node.id, node);
}
const sourceKinds = ["library", "youtube", "podcast", "hn", "hackertube", "reddit"];
const chips = sourceKinds.map((kind) => {
  const n = new Element("input"); n.dataset.researchSource = kind; n.checked = kind === "library";
  if (kind !== "library" && kind !== "reddit") n.dataset.researchConsent = kind;
  return n;
});
const panelConsent = (id) => sourceKinds.slice(1, -1).map((kind) => {
  const n = new Element("input"); n.dataset.researchConsent = kind; nodes.get(id).append(n); return n;
});
const consent = chips.slice(1, -1), settingsConsent = panelConsent("researchSettingsConsent");
const timers = new Map(), calls = [], requests = [], copies = [], opened = [], toasts = [], listeners = new Map();
let timerId = 0, now = 1000;
class Clock extends Date { static now() { return now; } }
const context = vm.createContext({
  URL, Blob, Set, Map, Date: Clock, console, AbortController,
  state: { activeTab: "research", settings: { research_network_sources: [] } },
  document: { hidden: false, body: new Element("body"),
    createElement: (tag) => new Element(tag),
    getElementById: (id) => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); },
    querySelectorAll: (selector) => selector === "[data-research-source]" ? chips : selector === "[data-research-consent]" ? [...consent, ...settingsConsent] : [],
    addEventListener: (name, fn) => listeners.set(name, fn) },
  window: { setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout: (id) => timers.delete(id),
    open: (...args) => opened.push(args) },
  navigator: { clipboard: { writeText: async (text) => copies.push(text) } },
  fmtDuration: (n) => n ? `${n / 60} min` : "--:--", showToast: (text) => toasts.push(text), renderAICostEstimate() {},
  registryToolError: (_, result) => Object.assign(new Error(result?.error?.message || "tool failed"), { data: result }),
  NAV_OWNER: {}, els: {}, pageScrollPosition: () => ({}), setPageScrollPosition() {},
  markOpenLibraryRow() {}, syncSidebarTopics() {}, loadLibraryAvailability() {}, loadLibraryActivity() {},
  startLibraryActivityTimer() {}, stopLibraryActivityTimer() {}, syncReaderCrumbs() {}, pushRoute() {}, routeForTab() {},
});
const evaluate = (code) => vm.runInContext(code, context);
evaluate("const settingEdits = new Map(); let settingsWriteQueue = Promise.resolve(); const SETTINGS_FIELDS = {};"
  + escape + external + clickHandlers + settings + script + switchTab);
const runId = "rr_20261103000000_aabbccdd";
const attack = '<img src="https://evil.example/" onerror="boom()">';
const candidate = { key: "yt:talk0000001", kind: "youtube", title: attack, channel: "Example", duration_s: 900,
  url: "https://www.youtube.com/watch?v=talk0000001", why_ranked: [attack], est_capture: "captions", capturable: true };
let view = { ok: true, run_id: runId, scope: { question: "Synthetic evals", max_sources: 12 }, candidates: [candidate],
  queries: ["Synthetic evals", "Synthetic evals talk", "Synthetic evals podcast"], prompt: "Continue synthetic run " + runId,
  exports: { md: true, html: true }, share_text: "Synthetic share text", report: null, verification: { accepted: [], dropped: [], stats: {} } };
let settingsFailure = false, settingsGate = null, viewFailure = null, toolFailure = null;
let status = { ok: true, ready_count: 1, counts: { ready: 1 }, items: [{ state: "ready" }], asr_minutes_left: 120, done: true };
context.authFetch = async (path, options = {}) => {
  requests.push(path);
  if (path === "/settings") {
    if (settingsFailure) throw new Error("Synthetic save failed");
    if (settingsGate) await settingsGate;
    return { ok: true, settings: options.body ? JSON.parse(options.body) : context.state.settings };
  }
  assert.ok(path === "/research" || path === `/research/${runId}`, path);
  if (path !== "/research" && viewFailure) throw viewFailure;
  return path === "/research" ? { runs: [{ run_id: runId, question: attack, created_at: "2026-11-03" }] } : structuredClone(view);
};
context.callRegistryTool = async (name, args) => {
  calls.push([name, args]);
  if (name === "research_start") return { ok: true, run_id: runId, needs_consent: [] };
  if (name === "research_discover") return { ok: true, candidates: [candidate], skipped: [], errors: [] };
  if (name === "research_capture") return { ok: true, queued: [candidate], already: [], skipped: [], eta: { min_minutes: 1, max_minutes: 2 } };
  if (name === "research_status") return structuredClone(toolFailure || status);
  assert.fail(`unexpected tool ${name}`);
};
const poll = async () => {
  assert.equal(timers.size, 1);
  const [id, timer] = [...timers][0];
  timers.delete(id); now += timer.delay; await timer.fn();
};
const selectRun = () => context.researchWork(() => context.openResearchRun(runId));

const actionCase = process.argv[2];
if (["mixed_selection", "mixed_saved_guard", "saved_only", "completed_selection", "action_visibility", "skipped_sources"].includes(actionCase)) {
  const saved = { ...candidate, key: "lib:saved", title: "Saved talk", in_library: true };
  const episode = { ...saved, key: "pod:saved", kind: "podcast", capturable: false };
  const unavailable = { ...candidate, key: "pod:new", kind: "podcast", capturable: false };
  view.candidates = [saved, episode, candidate, unavailable];
  context.callRegistryTool = async (name, args) => {
    calls.push([name, args]);
    if (name === "research_capture") return { ok: true,
      queued: args.keys.includes(candidate.key) ? [candidate] : [],
      already: [saved, episode].filter((c) => args.keys.includes(c.key)),
      skipped: [], eta: { min_minutes: 0, max_minutes: 1 } };
    if (name === "research_status") return structuredClone(status);
    assert.fail(name);
  };
  context.wireResearch();
  if (actionCase === "mixed_selection") {
    await selectRun();
    await nodes.get("researchCapture").listeners.click();
    assert.deepEqual([...calls.at(-1)[1].keys], [saved.key, episode.key, candidate.key],
      "one capture request includes every eligible selected source");
    assert.match(nodes.get("researchProgress").textContent, /Queued 1; already saved 2/);
    assert.equal(timers.size, 1);
    view.scope.max_sources = 2;
    await selectRun();
    evaluate(`researchState.selected.add(${JSON.stringify(candidate.key)})`);
    const before = calls.length;
    await nodes.get("researchCapture").listeners.click();
    assert.equal(calls.length, before, "saved sources still count toward the selection limit");
  } else if (actionCase === "mixed_saved_guard") {
    await selectRun();
    assert.ok(nodes.get("researchUseSaved").disabled, "Use saved cannot submit half of a mixed selection");
    await nodes.get("researchUseSaved").listeners.click();
    assert.equal(calls.length, 0, "the handler also rejects a mixed saved-only action");
    const check = nodes.get("researchCandidates").children[2].children[0].children[0];
    check.checked = false; check.listeners.change();
    assert.equal(nodes.get("researchUseSaved").disabled, false);
    await nodes.get("researchUseSaved").listeners.click();
    assert.deepEqual([...calls.at(-1)[1].keys], [saved.key, episode.key]);
  } else if (actionCase === "saved_only") {
    view.candidates = [saved, episode];
    await selectRun();
    const normal = context.callRegistryTool;
    let finishStatus;
    context.callRegistryTool = (name, args) => name === "research_status"
      ? new Promise((resolve) => { finishStatus = resolve; }) : normal(name, args);
    const pending = poll();
    await nodes.get("researchUseSaved").listeners.click();
    const message = nodes.get("researchProgress").textContent;
    assert.match(message, /Using 2 saved transcripts/);
    assert.equal(timers.size, 0, "using saved transcripts schedules no capture poll");
    assert.equal(evaluate("researchState.eta"), null);
    finishStatus(status); await pending;
    context.callRegistryTool = normal;
    const before = calls.length;
    await context.refreshResearch();
    assert.equal(calls.length, before);
    assert.equal(nodes.get("researchProgress").textContent, message, "neither stale nor later polls replace the saved-only result");
    assert.ok(nodes.get("researchUseSaved").disabled, "saved sources already added to the run need no second action");
  } else if (actionCase === "completed_selection") {
    await selectRun();
    await nodes.get("researchCapture").listeners.click();
    status = { ...status, ready_count: 3, counts: { ready: 2, captioned: 1 },
      items: [{ key: saved.key, state: "ready" }, { key: episode.key, state: "ready" },
        { key: candidate.key, state: "captioned" }] };
    await poll();
    const finished = () => {
      assert.ok(nodes.get("researchCapture").disabled);
      assert.ok(nodes.get("researchCapture").classList.contains("hidden"));
      assert.ok(nodes.get("researchUseSaved").disabled, "completion must not turn into another action on the same sources");
      assert.equal(evaluate("researchState.selected.size"), 0);
      assert.equal(nodes.get("researchCandidates").children[2].children[0].children[0].checked, false);
      assert.equal(timers.size, 0);
    };
    finished();
    assert.equal(view.candidates[2].in_library, undefined, "the server view still has discovery-time metadata");
    await selectRun(); await poll();
    finished();
  } else if (actionCase === "skipped_sources") {
    for (const includeSaved of [true, false]) {
      view.candidates = includeSaved ? [saved, candidate] : [candidate];
      context.callRegistryTool = async () => ({ ok: true, queued: [], already: includeSaved ? [saved] : [],
        skipped: [{ key: candidate.key, reason: "asr_budget" }], eta: { min_minutes: 0, max_minutes: 0 } });
      await selectRun();
      await nodes.get("researchCapture").listeners.click();
      assert.deepEqual([...evaluate("researchState.selected")], [candidate.key], "skipped sources stay selected for retry");
      assert.equal(nodes.get("researchCapture").disabled, false);
      assert.equal(timers.size, 0);
      assert.match(nodes.get("researchProgress").textContent,
        includeSaved ? /Using 1 saved transcript\./ : /No sources were added\./);
      assert.match(nodes.get("researchProgress").textContent, /asr_budget/);
    }
  } else {
    for (const candidates of [[], [unavailable], [candidate], [saved], [saved, candidate]]) {
      view.candidates = candidates;
      await selectRun();
      assert.equal(nodes.get("researchUseSaved").classList.contains("hidden"), !candidates.includes(saved));
      assert.equal(nodes.get("researchCapture").classList.contains("hidden"), !candidates.includes(candidate));
    }
  }
  console.log(`Research source regression passed: ${actionCase}`);
  process.exit(0);
}

if (process.argv[2] === "source_actions") {
  const saved = { ...candidate, key: "lib:saved", title: "Saved talk", in_library: true };
  const episode = { ...saved, key: "pod:saved", kind: "podcast", capturable: false };
  const unavailable = { ...candidate, key: "pod:new", kind: "podcast", capturable: false };
  view.candidates = [saved, episode];
  await selectRun();
  assert.ok(nodes.get("researchCapture").disabled, "saved transcripts cannot be captured again");
  assert.ok(nodes.get("researchCapture").classList.contains("hidden"));
  assert.equal(nodes.get("researchUseSaved").disabled, false);
  assert.match(nodes.get("researchCandidates").textContent, /Use saved/);
  const before = calls.length;
  await context.researchWork(context.captureResearch);
  assert.equal(calls.length, before, "Capture new never submits saved-only selections");
  context.callRegistryTool = async (name, args) => {
    calls.push([name, args]);
    if (name === "research_capture") return { ok: true,
      queued: args.keys.includes(candidate.key) ? [candidate] : [],
      already: [saved, episode].filter((c) => args.keys.includes(c.key)),
      skipped: [], eta: { min_minutes: 0, max_minutes: 0 } };
    if (name === "research_status") return structuredClone(status);
    assert.fail(name);
  };
  context.wireResearch();
  await nodes.get("researchUseSaved").listeners.click();
  assert.deepEqual([...calls.at(-1)[1].keys], [saved.key, episode.key]);
  assert.match(nodes.get("researchProgress").textContent, /Using 2 saved transcripts/);
  assert.doesNotMatch(nodes.get("researchProgress").textContent, /Queued|Estimated/);

  view.candidates = [saved, candidate, unavailable];
  await selectRun();
  assert.equal(nodes.get("researchCapture").disabled, false);
  assert.equal(nodes.get("researchCapture").classList.contains("hidden"), false);
  assert.match(nodes.get("researchCandidates").textContent, /Capture new/);
  assert.equal(nodes.get("researchCandidates").children[2].children[0].children[0].disabled, true);
  assert.ok(nodes.get("researchUseSaved").disabled);
  const beforeMixed = calls.length;
  await nodes.get("researchUseSaved").listeners.click();
  assert.equal(calls.length, beforeMixed, "Use saved cannot submit only part of the selection");
  await context.researchWork(context.captureResearch);
  assert.deepEqual([...calls.at(-1)[1].keys], [saved.key, candidate.key], "capture includes saved and new sources");

  // Status marks the transcript saved and removes the completed pick.
  status = { ...status, items: [{ key: candidate.key, state: "captioned" }] };
  await context.refreshResearch();
  assert.ok(nodes.get("researchCapture").disabled);
  assert.ok(nodes.get("researchCapture").classList.contains("hidden"));
  assert.ok(nodes.get("researchUseSaved").disabled);
  assert.match(nodes.get("researchCandidates").textContent, /Use saved/);
  console.log("Research source actions passed.");
  process.exit(0);
}

// Same-origin input cannot invent a trusted link host; podcast hosts are per item.
const safe = (url, source = {}) => context.researchSafeLink(url, source);
for (const host of ["youtube.com", "www.youtube.com", "youtu.be", "news.ycombinator.com"]) {
  assert.ok(safe(`https://${host}/watch?v=example&t=20s`));
}
for (const url of ["http://youtube.com/x", "javascript:alert(1)", "//youtube.com/x", "https://youtube.com.evil.example/",
  "https://evil.example/?next=youtube.com", "https://user@youtube.com/", "https://@youtube.com/",
  "https://youtube.com:444/", "https://youtube.com:/", "https://%79outube.com/", "https://youtube.com/\nattack",
  "https://youtube.com/\u200battack", "https://youtube.com\\@evil.example/", "file:///report.html"]) assert.equal(safe(url), null, url);
const podcast = { kind: "podcast", episode_url: "https://episodes.example/show", enclosure_url: "https://audio.example/episode.mp3" };
assert.ok(safe("https://audio.example/episode.mp3#t=20", podcast));
assert.equal(safe("https://audio.example/episode.mp3#t=20"), null);
assert.equal(safe("https://evil.example/", podcast), null);
assert.equal(safe("https://127.0.0.1/private", { kind: "podcast", source_url: "https://127.0.0.1/private" }), null);
for (const host of ["local", "localhost", "intranet.local", "sub.localhost", "sub.internal", "internal",
  "127.0.0.1", "10.0.0.1", "169.254.169.254", "0x7f000001", "2130706433", "[::1]", "[fc00::1]"]) {
  for (const suffix of ["", ".", ".."]) {
    const url = `https://${host}${suffix}/episode.mp3`;
    assert.equal(safe(url, { kind: "podcast", episode_url: url, enclosure_url: url, source_url: url }), null, url);
  }
}
assert.equal(safe("https://youtube.com./watch?v=x"), "https://youtube.com/watch?v=x");
assert.ok(safe("https://audio.example./episode.mp3", podcast));
assert.ok(safe("https://audio.example/episode.mp3", { kind: "podcast", source_url: "https://audio.example../show" }));
assert.equal(context.htmlEscape('<script>"&\''), "&lt;script&gt;&quot;&amp;&#39;");

// Each chip both grants consent and selects that source, including Settings edits.
context.renderResearchConsent();
assert.equal(chips[0].disabled, false);
assert.ok(chips.slice(1, -1).every((n) => !n.disabled && !n.checked));
consent[0].checked = true;
await context.saveResearchConsent(consent[0]);
assert.deepEqual([...context.state.settings.research_network_sources], ["youtube"]);
assert.equal(chips[1].disabled, false); assert.equal(chips[1].checked, true);
assert.equal(chips[5].disabled, true);
settingsFailure = true;
consent[1].checked = true;
await context.saveResearchConsent(consent[1]);
assert.equal(consent[1].checked, false); assert.equal(chips[2].disabled, false);
assert.equal(settingsConsent[1].checked, false);
assert.equal(nodes.get("researchConsentSaveRetry").classList.contains("hidden"), false);
settingsFailure = false;
settingsConsent[2].checked = true;
await context.saveResearchConsent(settingsConsent[2]);
let finishSettings;
settingsGate = new Promise((resolve) => { finishSettings = resolve; });
const retry = context.settingEdit("researchConsent").retry();
assert.ok([...consent, ...settingsConsent].every((input) => input.disabled));
assert.equal(nodes.get("researchDiscover").disabled, true, "discovery waits for consent to save");
finishSettings(); await retry; settingsGate = null;
assert.deepEqual([...context.state.settings.research_network_sources], ["youtube", "podcast", "hn"]);
assert.ok([...consent.slice(0, 3), ...settingsConsent.slice(0, 3)].every((input) => input.checked && !input.disabled));
assert.equal(nodes.get("researchConsentSaveRetry").classList.contains("hidden"), true);
assert.equal(context.settingEdit("researchConsent").retry, null);
settingsConsent[2].checked = false;
await context.saveResearchConsent(settingsConsent[2]);
assert.equal(chips[3].checked, false, "revoking consent in Settings clears the chip");

// Exercise start -> discover -> select -> capture -> poll with the real UI code.
context.wireResearch();
nodes.get("researchQuestion").value = "Synthetic evals";
nodes.get("researchMax").value = "12"; nodes.get("researchAsr").value = "120";
await context.researchWork(context.startResearch);
assert.deepEqual(calls.map(([name]) => name), ["research_start", "research_discover"]);
assert.equal(calls[0][1].source_kinds.join(","), "library,youtube,podcast");
assert.equal(calls[1][1].queries.length, 3);
assert.ok(nodes.get("researchCandidates").textContent.includes(attack));
assert.equal(nodes.get("researchCandidatesHeading").focused, true);
await context.researchWork(context.captureResearch);
assert.equal(calls.at(-1)[0], "research_capture");
assert.deepEqual([...calls.at(-1)[1].keys], [candidate.key]);
assert.ok(nodes.get("researchProgress").textContent.includes("Estimated 1–2 min"));
await context.refreshResearch();
assert.ok(nodes.get("researchProgress").textContent.includes("1 ready"));
assert.equal(timers.size, 0, "a finished capture stops polling");
status = { ok: true, ready_count: 0, counts: {}, items: [], asr_minutes_left: 120, done: true };
await selectRun(); await poll();
assert.ok(nodes.get("researchProgress").textContent.includes("No capture has started"));
assert.equal(timers.size, 0, "browsing an uncaptured run probes status once");
status = { ok: true, ready_count: 0, counts: { failed: 1 },
  items: [{ state: "failed", title: attack, error: "transcript_unavailable" }], asr_minutes_left: 120, done: true };
await selectRun(); await poll();
assert.ok(nodes.get("researchProgress").textContent.includes("No sources are ready"));
assert.equal(timers.size, 0);

// Each displayed field is inert text. Dropped quotes never appear, even if supplied.
view.report = { title: attack, question: attack, summary: attack, date: "2026-11-03", sources_searched: 1,
  sources: [{ item_id: "source", title: attack, channel: "Example", kind: "youtube", duration_s: 900, claim_count: 1 }], disagreements: [],
  claims: [{ id: "good", text: attack, section: "Evals", flags: [], receipts: [{ item_id: "source", deep_link: candidate.url, time_label: "00:20", channel: "Example", title: attack }] },
    { id: "flagged", text: "Flagged claim", section: "Evals", flags: ["asr_doubt", "overstated", "low_overlap", "one_sided_search"], receipts: [] }] };
view.verification = { accepted: [{ id: "good" }], stats: { accepted: 1, flagged: 1, dropped: 1, tiers_run: ["1", "2"] },
  dropped: [{ text: attack, reasons: ["quote_not_found"], quote: "DO NOT DISPLAY THIS QUOTE" }] };
context.renderResearchReport(view);
const report = nodes.get("researchReport");
assert.ok(report.textContent.includes("receipt"));
assert.ok(report.textContent.includes("flagged: asr_doubt"));
assert.ok(report.textContent.includes("channel-level attribution"));
assert.ok(report.textContent.includes("Didn't make the cut (1)"));
assert.ok(report.textContent.includes("quote_not_found"));
assert.ok(!report.textContent.includes("DO NOT DISPLAY"));
const descendants = (node) => node.children.flatMap((child) => [child, ...descendants(child)]);
assert.equal(descendants(report).filter((node) => ["IMG", "SCRIPT", "IFRAME"].includes(node.tagName)).length, 0);
const link = descendants(report).find((node) => node.tagName === "A");
assert.equal(link.rel, "noopener noreferrer"); assert.equal(link.target, "_blank");
const candidateLink = descendants(nodes.get("researchCandidates")).find((node) => node.tagName === "A");
// Follow the shipped delegated click/auxclick handlers all the way to the opener.
for (const sourceLink of [candidateLink, link,
  context.researchLink("HN", "https://news.ycombinator.com/item?id=1"),
  context.researchLink("Podcast", "https://audio.example/episode.mp3#t=20", podcast)]) {
  assert.equal(sourceLink.hasAttribute("data-source-link"), true);
  const child = new Element("span"); sourceLink.append(child);
  for (const type of ["click", "auxclick"]) {
    const event = { target: child, button: type === "auxclick" ? 1 : 0, preventDefault() { this.defaultPrevented = true; } };
    listeners.get(type)(event);
    assert.equal(event.defaultPrevented, true);
    assert.deepEqual(opened.at(-1), [sourceLink.href, "_blank", "noopener,noreferrer"]);
  }
}
assert.equal(toasts.length, 0, "validated source links must not trigger the blocked-link toast");
const dropped = descendants(report).find((node) => node.tagName === "DETAILS");
assert.ok(!dropped.open);
context.renderResearchReport({ ...view, exports: { html: false, md: true }, report: null });
assert.equal(nodes.get("researchPublished").classList.contains("hidden"), false);
assert.equal(nodes.get("researchMarkdown").disabled, false);
assert.equal(nodes.get("researchHtml").disabled, true);

const count = calls.length;
await nodes.get("researchCopyPrompt").listeners.click();
assert.equal(copies.at(-1), view.prompt);
assert.equal(calls.length, count);
status = { ok: true, ready_count: 0, counts: { queued: 1 }, items: [{ state: "queued" }], asr_minutes_left: 120, done: false };
await selectRun(); await poll();
assert.equal(timers.size, 1, "active capture keeps polling");
const activeCalls = calls.length;
context.document.hidden = true; listeners.get("visibilitychange")();
assert.equal(timers.size, 0); await context.refreshResearch(); assert.equal(calls.length, activeCalls);
context.document.hidden = false; listeners.get("visibilitychange")();
assert.equal(timers.size, 1);
context.switchTab("library");
assert.equal(timers.size, 0);
await context.refreshResearch(); assert.equal(calls.length, activeCalls);
context.state.activeTab = "research"; context.scheduleResearchPoll();
assert.equal([...timers.values()][0].delay, 5000);

// Hiding/leaving during a request must not start the second request or a timer.
const normalTool = context.callRegistryTool;
for (const hidden of [true, false]) {
  await selectRun();
  let finishStatus;
  context.callRegistryTool = () => new Promise((resolve) => { finishStatus = resolve; });
  const requestCount = requests.length, pending = poll();
  if (hidden) { context.document.hidden = true; listeners.get("visibilitychange")(); }
  else context.switchTab("library");
  finishStatus(status); await pending;
  assert.equal(requests.length, requestCount);
  assert.equal(timers.size, 0);
  context.document.hidden = false; context.state.activeTab = "research"; context.callRegistryTool = normalTool;
}

// Completed runs stop even before publication; reopening fetches new exports.
view = { ...view, exports: { html: false, md: false }, report: null };
status = { ...status, done: true, ready_count: 1, counts: { ready: 1 }, items: [{ state: "ready" }] };
await selectRun(); await poll(); assert.equal(timers.size, 0);
view.exports.md = true;
await nodes.get("researchReload").listeners.click();
assert.equal(nodes.get("researchPublished").classList.contains("hidden"), false);
await poll(); assert.equal(timers.size, 0);

status = { ...status, done: false, ready_count: 0, counts: { queued: 1 }, items: [{ state: "queued" }] };
for (const statusCode of [400, 403, 404]) {
  await selectRun(); viewFailure = Object.assign(new Error("Unavailable run"), { status: statusCode });
  await poll(); assert.equal(timers.size, 0);
  const stoppedCalls = calls.length; await context.refreshResearch(); assert.equal(calls.length, stoppedCalls);
  viewFailure = null;
}
await selectRun(); toolFailure = { ok: false, error: { code: "not_found", message: "Run not found" } };
await poll(); assert.equal(timers.size, 0); toolFailure = null;

// Transient failures retry within the same deadline, which visibility cannot reset.
await selectRun(); viewFailure = Object.assign(new Error("Temporary failure"), { status: 503 });
await poll(); assert.equal(timers.size, 1); viewFailure = null;
const deadline = evaluate("researchState.pollDeadline");
context.document.hidden = true; listeners.get("visibilitychange")();
now = deadline - 1000;
context.document.hidden = false; listeners.get("visibilitychange")();
assert.equal([...timers.values()][0].delay, 1000);
const expiredCalls = calls.length; await poll();
assert.equal(calls.length, expiredCalls); assert.equal(timers.size, 0);
assert.match(nodes.get("researchProgress").textContent, /stopped after 30 minutes/);
context.scheduleResearchPoll(); assert.equal(timers.size, 0);
await selectRun(); assert.equal(timers.size, 1, "explicitly reopening a run starts another bounded session");

// A stale run fetch cannot replace a newer selection.
let finishOld;
const laterId = "rr_20261103000001_11223344";
context.authFetch = (path) => path.endsWith(runId) ? new Promise((resolve) => { finishOld = resolve; })
  : Promise.resolve({ ...view, run_id: laterId, scope: { ...view.scope, question: "Later question" } });
const old = context.openResearchRun(runId);
await context.openResearchRun(laterId);
finishOld(view); await old;
assert.equal(evaluate("researchState.runId"), laterId);
assert.ok(nodes.get("researchRunLabel").textContent.includes("Later question"));
console.log("Research dashboard: links, consent, capture, safe rendering, clipboard and polling passed.");
