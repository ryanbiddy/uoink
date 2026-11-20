// Library health: "Transcribe saves that have no words" (3.18). Pulls the
// pure view helpers out of the REAL dashboard script by name and runs them in
// a node:vm context, then checks the markup, copy and overflow guards.
// No network. Run directly:  node tests/js/dash_transcript_backfill_test.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAGE = readFileSync(join(ROOT, "assets", "dashboard", "index.html"), "utf8");

function grab(name) {
  const at = PAGE.indexOf(`function ${name}(`);
  if (at < 0) throw new Error(`function ${name} not found`);
  const open = PAGE.indexOf("{", PAGE.indexOf(")", at));
  let depth = 0;
  for (let i = open; i < PAGE.length; i++) {
    if (PAGE[i] === "{") depth++;
    else if (PAGE[i] === "}" && --depth === 0) return PAGE.slice(at, i + 1);
  }
  throw new Error(`function ${name} never closes`);
}

let failures = 0;
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}

const ctx = vm.createContext({ Number, Math, Set, Array, String, Object, Boolean });
vm.runInContext(["backfillCount", "backfillDuration", "backfillView", "halfCaptureRows"].map(grab).join("\n"), ctx);

const progress = (extra = {}) => ({ done: 0, left: 0, total: 0, transcribed: 0, no_words: 0, gone: 0, failed: 0, eta_seconds: 0, ...extra });

// Empty library: a clear empty state and no buttons.
let view = ctx.backfillView({ state: "idle", count: 0, on_disk: 0, download: 0, gone: 0, no_words: 0, progress: progress(), backoff: {}, model_ready: true, half_captures: [] });
check(view.empty === true, "a count of 0 is the empty state");
check(view.headline === "Every save with video has its words.", "empty headline", view.headline);
check(!view.showStart && !view.showPause && !view.showResume, "no controls when there is nothing to do");
check(view.notes.length === 0 && view.progress === null, "no notes or progress bar when empty");
view = ctx.backfillView({ state: "idle", count: 0, progress: progress(), model_ready: false, model_message: "The transcription model is not on this computer yet.", half_capture_count: 0 });
check(view.notes.length === 0, "no model nag when there is nothing to transcribe", view.notes);

// One save: singular wording.
view = ctx.backfillView({ state: "idle", count: 1, on_disk: 1, download: 0, progress: progress(), model_ready: true });
check(view.headline === "1 save has video but no transcript", "singular headline", view.headline);
check(view.showStart && !view.startDisabled, "Start shows for one save");

// A big library mid-run.
view = ctx.backfillView({
  state: "running", count: 1065, on_disk: 140, download: 925, gone: 19, no_words: 4,
  progress: progress({ done: 12, left: 1053, total: 1065, eta_seconds: 11400, transcribed: 10, failed: 2 }),
  current: { key: "a", title: "A very long talk about making things that goes on and on", fraction: 0.4, waiting_for_capture: true },
  backoff: { x: { seconds_left: 1080, reason: "rate_limited" } }, model_ready: true,
});
check(view.headline === "1,065 saves have video but no transcript", "big counts read with commas", view.headline);
check(view.breakdown.startsWith("140 on this computer, 925 to download again."), "split by where the video is", view.breakdown);
check(view.breakdown.includes("4 saves have no speech to transcribe."), "no-speech saves are named", view.breakdown);
check(view.progressText === "12 done, 1,053 left, about 3 h 10 min to go.", "done, left and time left", view.progressText);
check(view.progress.value === 12 && view.progress.max === 1065, "bar covers done plus left", view.progress);
check(view.current === "Now: A very long talk about making things that goes on and on (40%)", "current title and share", view.current);
check(view.currentTitle.length > 40, "full title kept for the hover text");
check(view.showPause && !view.showStart && !view.showResume, "only Pause while running");
const notes = view.notes.map(n => n.text);
check(notes.includes("Waiting while your capture finishes."), "says it waits for a capture", notes);
check(notes.some(n => n.startsWith("X asked Uoink to slow down. Trying again in 18 min.")), "back-off is plain", notes);
check(notes.some(n => n.startsWith("19 saves can't be transcribed because the video is gone")), "gone saves are counted honestly", notes);
check(notes.some(n => n.startsWith("2 saves did not work this time.")), "failures are named while running", notes);

// Paused, pausing, and a finished run.
view = ctx.backfillView({ state: "paused", pausing: false, count: 30, on_disk: 30, progress: progress({ done: 5, left: 25 }), model_ready: true });
check(view.showResume && !view.showPause && !view.showStart, "Resume while paused");
check(view.progressText === "Paused. 5 done, 25 left.", "paused progress", view.progressText);
view = ctx.backfillView({ state: "paused", pausing: true, count: 30, on_disk: 30, progress: progress({ done: 5, left: 25 }), model_ready: true });
check(!view.showResume && view.progressText === "Pausing at the next safe point.", "no Resume until the pause lands", view.progressText);
view = ctx.backfillView({ state: "done", count: 2, on_disk: 2, progress: progress({ done: 9, transcribed: 6, no_words: 2, gone: 1 }), model_ready: true });
check(view.progressText === "Last run: 6 transcribed, 2 had no speech, 1 gone.", "last run summary", view.progressText);
check(view.showStart, "Start again after a run when saves are left");

// Missing model: Start is off and the note links to the model picker.
view = ctx.backfillView({ state: "idle", count: 3, on_disk: 3, progress: progress(), model_ready: false, model_message: "The transcription model is not on this computer yet. Download it in Settings, then start again." });
check(view.startDisabled, "Start is off without the model");
const modelNote = view.notes.find(n => n.link);
check(modelNote && modelNote.link === "#settings/transcription-model", "links to the model picker", modelNote);

// Durations.
check(ctx.backfillDuration(30) === "about a minute", "short eta", ctx.backfillDuration(30));
check(ctx.backfillDuration(600) === "about 10 min", "minutes eta", ctx.backfillDuration(600));
check(ctx.backfillDuration(7200) === "about 2 h", "whole hours", ctx.backfillDuration(7200));

// Captures that did not finish.
const rows = ctx.halfCaptureRows({
  model_ready: true, requested: ["folder:AI/b"], current: { key: "folder:AI/c" },
  half_captures: [
    { key: "folder:AI/a", title: "On disk", folder_name: "a", media: "on_disk" },
    { key: "folder:AI/b", title: "Queued one", folder_name: "b", media: "download" },
    { key: "folder:AI/c", title: "Running one", folder_name: "c", media: "on_disk" },
    { key: "folder:AI/d", title: "", folder_name: "d", media: "download", settled: "gone" },
  ],
});
check(rows.length === 4, "one row per stopped capture");
check(rows[0].button === "Finish" && !rows[0].disabled && rows[0].meta === "a · video on this computer", "Finish row", rows[0]);
check(rows[1].button === "Queued" && rows[1].disabled && rows[1].meta === "b · video downloads again", "queued row", rows[1]);
check(rows[2].button === "Finishing…" && rows[2].disabled, "running row", rows[2]);
check(rows[3].disabled && rows[3].title === "d" && rows[3].meta === "The video is gone and no copy is here.", "gone row", rows[3]);
check(ctx.halfCaptureRows({ model_ready: false, half_captures: [{ key: "k", title: "t", media: "on_disk" }] })[0].disabled, "Finish is off without the model");
check(ctx.halfCaptureRows(null).length === 0, "no rows before the first read");

// Markup: the block lives in Settings > Library and export, reachable by #settings/library-health.
const markup = PAGE.split("<script>", 1)[0];
const library = markup.split('id="settings-library"', 2)[1].split("</section>", 1)[0];
check(library.includes('id="settings-library-health"'), "Library health sits in Library and export");
for (const id of ["backfillCount", "backfillStart", "backfillPause", "backfillResume", "backfillOrder", "backfillProgress", "backfillCost", "halfCaptureList"]) {
  check(library.includes(`id="${id}"`), `${id} is in the block`);
}
const block = library.split('id="settings-library-health"', 2)[1].split('id="settings-card-image"', 1)[0];
const cost = block.split('id="backfillCost">', 2)[1].split("</p>", 1)[0];
check(/CPU/.test(cost) && /downloaded again/.test(cost) && /Nothing else leaves this computer/.test(cost), "the cost note says what it costs", cost);

// Copy rules: no em dashes or semicolons in this block's copy or view strings.
const script = ["backfillView", "halfCaptureRows", "renderTranscriptBackfill"].map(grab).join("\n");
const strings = [...script.matchAll(/(["`])((?:\\.|(?!\1).)*)\1/g)].map(m => m[2]).filter(s => /[a-z] [a-z]/i.test(s));
const prose = block.replace(/<[^>]+>/g, " ") + " " + strings.join(" ");
check(!prose.includes("—"), "no em dashes");
check(!/[a-z];/i.test(prose.replace(/&[a-z]+;/g, "")), "no semicolons in copy");
for (const word of ["seamless", "leverage", "robust", "delve", "straightforward", "unlock"]) {
  check(!new RegExp(`\\b${word}\\b`, "i").test(prose), `no "${word}"`);
}

// Overflow guards for long titles at phone width.
const css = PAGE.split("<style>", 2)[1].split("</style>", 1)[0];
check(/\.half-capture-row \{[^}]*grid-template-columns: minmax\(0, 1fr\) auto[^}]*min-width: 0/.test(css), "rows give text a shrinking column");
check(/\.half-capture-title \{[^}]*text-overflow: ellipsis/.test(css), "long titles get an ellipsis");
check(/\.backfill-current \{[^}]*text-overflow: ellipsis/.test(css), "current title gets an ellipsis");
check(/\.backfill-count \{[^}]*overflow-wrap: anywhere/.test(css), "the count wraps");
check(script.includes("title.title = row.title") && script.includes("current.title = view.currentTitle"), "ellipsized titles keep a title attribute");
check(script.includes("textContent") && !/innerHTML/.test(script), "status text is never HTML");

// Loading: the count is read when the block comes into view, and the status
// polls only while a run, a pause or a Finish is in progress.
const bind = grab("bindTranscriptBackfill");
check(/new IntersectionObserver\(/.test(bind) && /isIntersecting\)\) loadTranscriptBackfill\(\)/.test(bind), "reads when the block is seen");
check(/typeof IntersectionObserver === "function"/.test(bind), "safe where IntersectionObserver is missing");
const load = grab("loadTranscriptBackfill");
check(/state\.activeTab === "settings" && backfillActive\(data\)/.test(load), "polls only on Settings while active");
vm.runInContext(grab("backfillActive"), ctx);
check(ctx.backfillActive({ state: "running" }) && ctx.backfillActive({ state: "paused", pausing: true })
  && ctx.backfillActive({ state: "idle", requested: ["k"] }) && !ctx.backfillActive({ state: "done", requested: [] })
  && !ctx.backfillActive(null), "active means running, pausing or a Finish in flight");

// Behaviour, with a tiny fake DOM: the real load, render and bind functions.
function fakeEl(id) {
  const classes = new Set(id === "backfillProgressWrap" || id === "backfillCurrent" ? ["hidden"] : []);
  const el = {
    id, textContent: "", title: "", value: "", disabled: false, dataset: {}, children: [],
    classList: { toggle(name, on) { if (on) classes.add(name); else classes.delete(name); }, contains: n => classes.has(n) },
    replaceChildren(...kids) { el.children = kids; }, prepend(kid) { el.children.unshift(kid); },
    append(...kids) { el.children.push(...kids); }, addEventListener() {}, setAttribute() {},
    closest() { return label; },
  };
  return el;
}
const label = fakeEl("label");
function fakePage({ hidden = false, observer = false } = {}) {
  const els = new Map();
  const timers = [];
  const listeners = {};
  const reads = [];
  const doc = {
    hidden, activeElement: null,
    getElementById: id => { if (!els.has(id)) els.set(id, fakeEl(id)); return els.get(id); },
    createElement: tag => fakeEl(tag),
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  const page = vm.createContext({
    Number, Math, Set, Array, String, Object, Boolean, Promise, Error,
    document: doc, state: { activeTab: "settings" }, BACKFILL_ROUTE: "/library/transcript-backfill",
    backfillData: null, backfillTimer: null, backfillBusy: false, backfillVersion: 0, backfillRetries: 0, backfillStale: false,
    window: { setTimeout: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimeout() {} },
    settingError: err => String(err.message || "error"),
    readSettingsResource: async () => { reads.push(1); if (page.answer instanceof Error) throw page.answer; return page.answer; },
    transcriptBackfillAction() {},
    ...(observer ? { IntersectionObserver: class { observe() {} } } : {}),
  });
  vm.runInContext(["backfillCount", "backfillDuration", "backfillView", "halfCaptureRows", "renderTranscriptBackfill",
    "backfillActive", "loadTranscriptBackfill", "bindTranscriptBackfill"]
    .map(name => (PAGE.includes(`async function ${name}(`) ? "async " : "") + grab(name)).join("\n"), page);
  return { page, timers, listeners, reads, el: id => doc.getElementById(id) };
}
const offline = () => Object.assign(new Error("offline"), { status: 0 });
const busy = () => Object.assign(new Error("slow down"), { status: 429 });
const idle = { state: "idle", count: 3, on_disk: 3, progress: progress(), model_ready: true, requested: [] };

let p = fakePage();
p.page.answer = idle;
await p.page.loadTranscriptBackfill();
p.page.answer = busy();
await p.page.loadTranscriptBackfill();
check(p.timers.length === 0, "an idle block does not poll after a 429", p.timers);
p.page.answer = offline();
await p.page.loadTranscriptBackfill();
check(p.timers.length === 0, "an idle block does not poll while the helper is down", p.timers);

p = fakePage();
p.page.answer = offline();
for (let i = 0; i < 8; i++) await p.page.loadTranscriptBackfill();
check(p.timers.length === 5, "a first read that keeps failing retries five times, then stops", p.timers);
check(p.timers.every((ms, i) => i === 0 || ms > p.timers[i - 1]) && p.timers[4] <= 120000, "each retry waits longer", p.timers);

p = fakePage();
p.page.answer = { ...idle, state: "running", progress: progress({ done: 1, left: 2 }) };
await p.page.loadTranscriptBackfill();
check(p.timers.length === 1 && p.timers[0] === 3000, "a run polls every 3 s", p.timers);
p.page.answer = busy();
await p.page.loadTranscriptBackfill();
check(p.timers.length === 2, "a run keeps trying after a 429", p.timers);

p = fakePage({ hidden: true });
p.page.answer = offline();
await p.page.loadTranscriptBackfill();
check(p.timers.length === 0, "no retries while the page is hidden", p.timers);
p.page.bindTranscriptBackfill();
check(p.reads.length === 2, "without IntersectionObserver the block still reads once", p.reads.length);
p.page.document.hidden = false;
p.page.answer = idle;
p.listeners.visibilitychange();
await new Promise(resolve => setTimeout(resolve, 0));
check(p.reads.length === 3 && p.el("backfillCount").textContent.startsWith("3 saves"), "coming back to the page reads again");
p = fakePage({ observer: true });
p.page.bindTranscriptBackfill();
check(p.reads.length === 0, "with IntersectionObserver it waits until the block is seen");

// A Finish outside a run: no bar, but the item it is on shows.
p = fakePage();
p.page.answer = { ...idle, requested: ["folder:AI/x"], current: { key: "folder:AI/x", title: "Stopped capture", fraction: 0.5 } };
await p.page.loadTranscriptBackfill();
check(!p.el("backfillProgressWrap").classList.contains("hidden"), "the progress area shows during a Finish");
check(p.el("backfillProgress").classList.contains("hidden"), "the bar stays hidden without a run");
check(p.el("backfillCurrent").textContent === "Now: Stopped capture (50%)" && !p.el("backfillCurrent").classList.contains("hidden"),
  "Finish shows its progress", p.el("backfillCurrent").textContent);

console.log(`\n${checks - failures}/${checks} checks passed`);
if (failures) process.exit(1);
