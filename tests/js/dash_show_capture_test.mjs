// Save a whole show: the dashboard's estimate copy, run states, buttons and
// the escaped run row. Pulls the helpers out of the REAL dashboard script by
// name and runs them in a node:vm context. No network.
// Run directly:  node tests/js/dash_show_capture_test.mjs
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

const NOW = Date.parse("2026-11-20T12:00:00Z");
const FakeDate = class extends Date {
  constructor(...args) { super(...(args.length ? args : [NOW])); }
  static now() { return NOW; }
};
const ctx = vm.createContext({ Date: FakeDate, Intl, Number, Math, Array, String, Set, JSON });
vm.runInContext([
  "const SHOW_ACTIVE_STATES = [\"listing\", \"running\", \"waiting\"];",
  grab("htmlEscape"), grab("fmtAge"), grab("showHoursText"), grab("showDiskText"), grab("showCount"),
  grab("showEstimateLines"), grab("showAsrText"), grab("showRunStatus"), grab("showRunActions"),
  grab("showRunHtml"),
].join("\n"), ctx);

const BANNED = /—|;|seamless|leverage|robust|delve|straightforward|unlock/i;

// Estimates, in the words the confirm step uses.
check(ctx.showHoursText(0.2) === "about 12 minutes", "short runs read in minutes", ctx.showHoursText(0.2));
check(ctx.showHoursText(3.94) === "about 3.9 hours", "hours keep one decimal", ctx.showHoursText(3.94));
check(ctx.showHoursText(1) === "about 1 hour", "one hour is singular", ctx.showHoursText(1));
check(ctx.showHoursText(100) === "about 4 days", "long runs read in days", ctx.showHoursText(100));
check(ctx.showDiskText(0.4) === "under 1 MB", "tiny disk use", ctx.showDiskText(0.4));
check(ctx.showDiskText(79.4) === "about 79 MB", "megabytes", ctx.showDiskText(79.4));
check(ctx.showDiskText(13860) === "about 13.5 GB", "gigabytes", ctx.showDiskText(13860));

const youtube = {
  id: "show_aaaaaaaaaaaa", kind: "youtube_channel", title: "The Tidepool Hour - Videos", state: "ready",
  counts: { total: 317, queued: 315, skipped: 2, done: 0, failed: 0, running: 0 },
  estimate: { to_save: 315, already_saved: 2, hours: 3.9, disk_mb: 79.4, asr_hours_if_all: 41.6 },
};
const ylines = ctx.showEstimateLines(youtube);
check(ylines[0] === "315 episodes to save, 2 already in your library or left out.", "the count line", ylines[0]);
check(ylines[1].includes("about 3.9 hours") && ylines[1].includes("about 79 MB") && ylines[1].includes("Nothing else leaves this computer."),
  "time, disk and what leaves the computer", ylines[1]);
check(ctx.showAsrText(youtube).includes("then deletes it") && ctx.showAsrText(youtube).includes("about 41.6 hours"),
  "the ASR choice says what it downloads and the most time it adds", ctx.showAsrText(youtube));
const podcast = { ...youtube, kind: "podcast_feed", estimate: { to_save: 308, already_saved: 2, hours: 51.3, disk_mb: 13870 } };
const plines = ctx.showEstimateLines(podcast);
check(plines[1].includes("Transcribing on this computer") && plines[1].includes("about 13.5 GB"),
  "a podcast says it transcribes locally and keeps the audio", plines[1]);
check([...ylines, ...plines, ctx.showAsrText(youtube), ctx.showAsrText(podcast)].every((l) => !BANNED.test(l)),
  "no em dashes, semicolons or banned words in the estimate copy");

// Run states.
const base = { ...youtube, counts: { total: 317, done: 40, failed: 3, skipped: 2, queued: 271, running: 1 },
  estimate: { ...youtube.estimate, hours: 3.4 } };
const running = ctx.showRunStatus({ ...base, state: "running", reason: null });
check(running.label === "40 of 315 saved", "running shows saved of to-save", running.label);
check(running.note === "About 3.4 hours left. 3 episodes failed.", "running says time left and failures", running.note);
check(ctx.showRunStatus({ ...base, state: "running", reason: "queue_busy" }).note === "Waiting for your other saves to finish first.",
  "a busy queue says your saves go first");
const waiting = ctx.showRunStatus({ ...base, state: "waiting", reason: "bot_check", wait_until: "2026-11-20T12:30:00Z" });
check(waiting.label === "Waiting on YouTube" && waiting.note.startsWith("YouTube asked Uoink to slow down. Trying again in 30 minutes"),
  "a bot check says when it tries again", waiting.note);
check(ctx.showRunStatus({ ...base, state: "paused", reason: "Set up transcription in Settings first." }).note === "Set up transcription in Settings first.",
  "a blocked run says why it paused");
check(ctx.showRunStatus({ ...base, state: "done" }).note === "40 episodes saved. 3 episodes failed. 2 already in your library or left out.",
  "done sums up", ctx.showRunStatus({ ...base, state: "done" }).note);
check(ctx.showRunStatus({ ...base, state: "failed", reason: "That feed came back empty." }).note === "That feed came back empty.",
  "a failed listing shows its reason");
const allStates = ["listing", "ready", "running", "waiting", "paused", "done", "cancelled", "failed"];
check(allStates.every((s) => { const r = ctx.showRunStatus({ ...base, state: s }); return r.label && !BANNED.test(r.label + r.note); }),
  "every state has a label and plain copy");

// Buttons per state.
const actions = (state) => ctx.showRunActions({ ...base, state }).map((a) => a[0]).join(",");
check(actions("running") === "pause,retry-failed,cancel", "running: pause, retry failed, cancel", actions("running"));
check(actions("paused") === "resume,retry-failed,cancel", "paused: resume", actions("paused"));
check(actions("done") === "retry-failed,dismiss", "done: retry failed, remove", actions("done"));
check(actions("ready") === "review,dismiss", "ready: review and start, remove", actions("ready"));
check(actions("cancelled") === "dismiss", "cancelled: remove", actions("cancelled"));
check(ctx.showRunActions({ ...base, state: "running", counts: { ...base.counts, failed: 0 } }).length === 2,
  "no retry button without failures");

// The run row escapes everything and stays bounded.
const evil = { ...base, state: "running", title: "<img src=x onerror=alert(1)>" + "x".repeat(400),
  failures: [{ title: "<b>bad</b>", reason: "<script>alert(1)</script>", url: "https://example.test/v" }], failures_total: 61 };
const html = ctx.showRunHtml(evil);
check(!html.includes("<img") && !html.includes("<script>") && !html.includes("<b>bad"), "titles and reasons are escaped");
check(html.includes('class="show-run-title" title="&lt;img'), "the full title is in the tooltip");
check(html.includes('role="progressbar"') && html.includes('aria-valuenow="43"') && html.includes("width:14%"),
  "running rows draw a progress bar", html.match(/width:\d+%/));
check(html.includes("61 failures with reasons") && html.includes("and 60 more"), "failures are summed and capped");
check(!ctx.showRunHtml({ ...base, state: "done", failures: [] }).includes("progressbar"), "finished rows drop the bar");

// Markup and CSS guards.
const card = PAGE.slice(PAGE.indexOf('id="showCaptureCard"'), PAGE.indexOf('id="noteCapture"'));
check(card.includes('id="openShowCapture"') && !card.includes('class="button primary"'), "the Sources card adds no second primary button");
const modal = PAGE.slice(PAGE.indexOf('id="showCaptureModal"'), PAGE.indexOf('id="listImportModal"'));
check(modal.includes('role="dialog"') && modal.includes('aria-modal="true"') && modal.includes('aria-labelledby="showCaptureTitle"'), "the dialog is labelled");
check((modal.match(/class="button primary"/g) || []).length === 1, "the dialog has one primary action");
check(modal.indexOf('id="showCaptureStart"') < modal.indexOf('id="showCapturePreview"'),
  "Start sits above the episode sample, so a phone sees it without scrolling past the list");
check(!/window\.setInterval\(pollShowRuns/.test(PAGE) && /setInterval\(pollShowRuns, 5000\)/.test(PAGE),
  "the run list polls from the boot timers, not from wireShowCapture");
check(!BANNED.test(card.replace(/<[^>]+>/g, "")) && !BANNED.test(modal.replace(/<[^>]+>/g, "")), "card and dialog copy is plain");
check(/\.show-run-title \{[^}]*min-width: 0;[^}]*text-overflow: ellipsis/.test(PAGE), "long show titles end in an ellipsis");
check(/\.show-run-note,\s*\.show-capture-estimate p \{[^}]*overflow-wrap: anywhere/.test(PAGE), "notes and estimates break long words");
check(/\.show-run \{[^}]*min-width: 0/.test(PAGE) && /\.show-runs \{[^}]*min-width: 0/.test(PAGE), "grid children can shrink");
check(/\.show-run-failures li span \+ span \{[^}]*overflow-wrap: anywhere/.test(PAGE), "failure reasons wrap");
check(PAGE.includes("wireShowCapture();"), "the dashboard wires the show card");
check(PAGE.includes('authFetch("/shows/preview"') && PAGE.includes('authFetch("/shows")'), "the dialog talks to the helper routes");

// What a run says while an episode finishes, a busy podcast host and ASR time.
const finishing = { ...base, current: { key: "pod:1", title: "Tidepool 4", state: "running" } };
check(ctx.showRunStatus({ ...finishing, state: "cancelled" }).note === "40 episodes saved before you cancelled. The episode in progress finishes first.",
  "a cancelled run says the episode in progress finishes", ctx.showRunStatus({ ...finishing, state: "cancelled" }).note);
check(ctx.showRunStatus({ ...finishing, state: "paused" }).note.endsWith("Resume to keep going. The episode in progress finishes first."),
  "a paused run says the same", ctx.showRunStatus({ ...finishing, state: "paused" }).note);
check(!ctx.showRunStatus({ ...base, state: "cancelled", current: null }).note.includes("in progress"), "nothing in flight, nothing to finish");
const host = ctx.showRunStatus({ ...base, kind: "podcast_feed", state: "waiting", reason: "host_busy", wait_until: "2026-11-20T12:04:00Z" });
check(host.label === "Waiting on the show's host" && host.note === "The show's host is busy or not answering. Trying again in 4 minutes.",
  "a busy podcast host is named, not YouTube", host);
const asrRun = ctx.showRunStatus({ ...base, state: "running", asr: true, counts: { ...base.counts, failed: 0 },
  estimate: { ...base.estimate, hours: 3.4, asr_hours_at_most: 30 } });
check(asrRun.note === "About 3.4 hours left. Up to about 33.4 hours if videos need transcribing here.",
  "a run with local transcription on counts its ASR time", asrRun.note);
check(!ctx.showRunStatus({ ...base, state: "running", kind: "podcast_feed", asr: true,
  estimate: { ...base.estimate, asr_hours_at_most: 0 } }).note.includes("Up to"), "podcast time already includes transcription");
check([host.note, asrRun.note].every((l) => !BANNED.test(l)), "the new copy is plain");

// The dialog, the preview and polling, against a small fake page.
function grabAny(name) {
  const fn = grab(name);
  return PAGE.slice(PAGE.indexOf(`function ${name}(`) - 6, PAGE.indexOf(`function ${name}(`)) === "async " ? `async ${fn}` : fn;
}
const els = {};
function fakeEl(id) {
  const classes = new Set();
  return { id, value: "", textContent: "", innerHTML: "", disabled: false, checked: false, offsetParent: {},
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    setAttribute() {}, removeAttribute() {}, addEventListener() {}, querySelectorAll: () => [] };
}
const fakeDoc = { hidden: false, activeElement: null, getElementById: (id) => (els[id] ||= fakeEl(id)), addEventListener() {} };
const fetched = [];
let answer = null;
const page = vm.createContext({ Date: FakeDate, Intl, Number, Math, Array, String, Set, JSON, Promise, Boolean,
  document: fakeDoc, focusFirstIn() {}, restoreFocus() {}, showToast() {}, window: { setTimeout: (f) => f() },
  authFetch: (url) => { fetched.push(url); return new Promise((resolve) => { answer = resolve; }); } });
vm.runInContext([
  "var SHOW_ACTIVE_STATES = [\"listing\", \"running\", \"waiting\"];",
  "var SHOW_PREVIEW_EPISODES = 8;",
  "var showCaptureState = { run: null, seq: 0, opener: null, runs: [], last: 0, loading: false, again: false, visible: false };",
  ...["htmlEscape", "fmtAge", "showHoursText", "showDiskText", "showCount", "showEstimateLines", "showAsrText",
    "showRunStatus", "showRunActions", "showRunHtml", "renderShowRuns", "loadShowRuns", "showCardVisible",
    "pollShowRuns", "showCaptureEl", "resetShowCapture", "openShowCapture", "renderShowPreview",
    "loadShowPreview"].map(grabAny),
].join("\n"), page);
const settle = () => new Promise((resolve) => setImmediate(resolve));

const readyRun = { ...youtube, episodes: Array.from({ length: 8 }, (_, i) => ({ title: `Episode ${i}`, state: "queued" })) };
page.showCaptureState.seq = 1;
const previewing = page.loadShowPreview(readyRun.id, 1);
check(fetched.at(-1) === `/shows/${readyRun.id}?episodes=1&episodes_limit=8`, "the preview asks for eight episodes, not every one", fetched.at(-1));
answer({ run: readyRun });
await previewing;
check(els.showCapturePreview.innerHTML.includes("Episode 7") && els.showCapturePreview.innerHTML.includes("and 309 more"),
  "the sample counts the rest from the run's total", els.showCapturePreview.innerHTML.slice(-60));
check(els.showCaptureStart.disabled === false && page.showCaptureState.run === readyRun, "Start is ready after a preview");
fakeDoc.getElementById("showCaptureInput").value = "https://www.youtube.com/@tidepoolhour";
page.openShowCapture(null);
check(els.showCaptureInput.value === "" && els.showCapturePreview.innerHTML === "" && els.showCaptureStart.disabled === true
  && page.showCaptureState.run === null, "Save a whole show opens a fresh form, never the last preview");

fetched.length = 0;
page.loadShowRuns();
page.loadShowRuns();
page.loadShowRuns();
check(fetched.length === 1, "refreshes asked for while one is in flight send nothing yet", fetched);
answer({ runs: [{ ...base, state: "ready", current: null }] });
await settle();
check(fetched.length === 2, "then one more runs, so an action never leaves an old answer on screen", fetched);
answer({ runs: [{ ...base, state: "done", current: null }] });
await settle();
check(fetched.length === 2 && page.showCaptureState.loading === false && page.showCaptureState.runs[0].state === "done",
  "and the list settles on the newest answer", page.showCaptureState.runs.map((r) => r.state));

fetched.length = 0;
page.showCaptureState.visible = true;
page.pollShowRuns();
page.pollShowRuns();
check(fetched.length === 0, "no polling while every run is idle", fetched);
page.showCaptureState.runs = [{ ...base, state: "cancelled", current: { key: "pod:1" } }];
page.pollShowRuns();
check(fetched.length === 1, "a cancelled run with an episode still finishing keeps polling", fetched);
answer({ runs: [] });
await settle();
fakeDoc.hidden = true;
page.pollShowRuns();
fakeDoc.hidden = false;
page.pollShowRuns();
check(fetched.length === 2, "coming back to the page refreshes once", fetched);
answer({ runs: [] });
await settle();
page.pollShowRuns();
check(fetched.length === 2, "and then waits for something to change", fetched);

console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
