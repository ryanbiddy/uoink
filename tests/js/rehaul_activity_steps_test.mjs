// No helper or real network. Exercise the shipped script, including authFetch.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const html = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const script = html.split("<script>")[1].split("    init().catch(")[0];
let checks = 0;
function check(value, message) { checks++; assert.ok(value, message); }
function same(actual, expected, message) { checks++; assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected, message); }
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
const today = new Date().toISOString();
const yesterday = new Date(Date.now() - 86400000).toISOString();
const video = "https://www.youtube.com/watch?v=abcdefghijk";
const failed = (extra = {}) => ({ id: "j1", kind: "single", title: "A failed capture", state: "failed", source_url: video,
  failure_phase: "download", phase: "done", completed_at: today, error_detail: "ERROR: [youtube] abcdefghijk: HTTP Error 429", ...extra });
const pending = (extra = {}) => ({ pending_id: 7, status: "pending", url: video, attempt_count: 0,
  retry_after: new Date(Date.now() + 60000).toISOString(), ...extra });

function makePage() {
  const elements = new Map();
  const listeners = {};
  const document = { activeElement: null, querySelector: () => null, querySelectorAll: () => [],
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
  const element = (id = "") => ({ id, innerHTML: "", textContent: "", value: "", disabled: false, hidden: false,
    dataset: {}, style: {}, open: false, isConnected: true, handlers: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    setAttribute() {}, removeAttribute() {}, getAttribute() { return ""; },
    querySelectorAll() { return []; }, querySelector() { return null; }, closest() { return null; },
    addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); },
    focus() { document.activeElement = this; }, showModal() { this.open = true; }, close() { this.open = false; },
    scrollIntoView() {}, contains() { return false; } });
  document.getElementById = (id) => { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
  document.createElement = () => element();
  document.body = element("body"); document.documentElement = element("html");
  const storage = new Map();
  const localStorage = { getItem: (k) => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) };
  const requests = [];
  const helper = { jobs: [], queue: { pending: [] }, fail: "", hold: null, detect: { ok: true, endpoint: "/extract", canonical: video } };
  const fetch = async (path, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    requests.push({ path, body, options });
    let data = path === "/token" ? { ok: true, token: "fixture" } : path === "/jobs" ? { jobs: helper.jobs }
      : path === "/queue/status" ? helper.queue : path.startsWith("/detect") ? helper.detect : { ok: true };
    if (helper.hold && path === helper.hold.path) await helper.hold.promise;
    if (path === helper.fail) data = { ok: false, error: "Fixture request refused" };
    return { ok: data.ok !== false, status: data.ok === false ? 409 : 200, json: async () => data, text: async () => JSON.stringify(data) };
  };
  const window = { addEventListener() {}, matchMedia: () => ({ matches: false }), location: { hash: "#activity" } };
  const ctx = { document, window, location: window.location, navigator: {}, localStorage, sessionStorage: localStorage,
    fetch, console, URL, URLSearchParams, TextDecoder, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1,
    clearInterval() {}, requestAnimationFrame() {}, CSS: { escape: (s) => s } };
  vm.createContext(ctx);
  vm.runInContext(script + `\n;globalThis.page = { state, els, activitySteps, activityEntries, activityRowHtml,
    activityLastError, activityRetrySchedule, renderQueue, openCaptureFailure, closeCaptureFailure,
    actOnActivityFailure, handleJobsStreamEvent, wireEvents, activityRemovalKey };`, ctx);
  const page = ctx.page;
  // Background library refresh is unrelated to these rows and can only see
  // the fake helper anyway; suppress its rendering, not Activity behaviour.
  vm.runInContext('loadLibrary = async () => {}; loadLibraryFacets = async () => {};', ctx);
  page.state.activeTab = "activity";
  return { ...page, get: document.getElementById, document, requests, helper, storage, ctx };
}

async function steps() {
  const p = makePage();
  for (const [phase, index] of [["metadata", 0], ["fetch", 0], ["details", 0], ["waiting", 1], ["rate_limit", 1],
    ["download", 2], ["video", 2], ["download_chunk_2_of_3", 2], ["transcript", 3], ["captions", 3],
    ["transcribing", 3], ["whisper", 3], ["screenshots_chunk_2_of_3", 4], ["writing", 4], ["publish", 4], ["comments", 4], ["classify", 4]]) {
    const input = Object.freeze({ state: "running", phase });
    const result = p.activitySteps(input);
    same(result.index, index, phase);
    same(result.steps.map((s) => s.state), Array.from({ length: 5 }, (_, i) => i < index ? "done" : i === index ? "now" : "todo"), phase);
    check(result.label.includes(index === 1 ? "Waiting" : `${index + 1} of 5`), "label gives words and position");
  }
  for (const [phase, index] of [["metadata", 0], ["waiting", 1], ["download", 2], ["transcript", 3], ["screenshots", 4]]) {
    const input = Object.freeze(failed({ failure_phase: phase, current_video_phase: "done" }));
    const result = p.activitySteps(input);
    same(result.index, index, "failure_phase wins over done");
    check(result.steps[index].state === "fail" && result.label.startsWith("Failed at "), "failed segment and words");
  }
  same(p.activitySteps({ state: "error", current_video_phase: "transcribing" }).index, 3, "legacy helper failure");
  check(p.activitySteps(pending({ failure_phase: "transcript" })).failed, "pending failed attempt retains phase");
  check(!p.activitySteps(pending({ last_error: "capture_ownership_unavailable" })).failed, "lock waiting is not a capture failure");
  same(p.activitySteps({ state: "running", phase: "future_phase" }).steps.map((s) => s.state), Array(5).fill("todo"), "unknown progress never invented");
  same(p.activitySteps({ state: "failed" }).index, -1, "unknown failure does not guess metadata");
  same(p.activitySteps({ state: "queued" }).index, 1, "queued waits");
  for (const state of ["done", "completed", "succeeded"]) same(p.activitySteps({ state }).steps.map((s) => s.state), Array(5).fill("done"), state);
  same(p.activitySteps({ state: "cancelled", phase: "download" }).steps.map((s) => s.state), Array(5).fill("todo"), "cancelled never claims success or failure");
}

async function rows() {
  const p = makePage();
  p.state.jobs = [failed(), failed({ id: "duplicate" }), { id: "active", state: "running", title: "Downloading", phase: "download" },
    { id: "saved", state: "completed", title: "Today's save", completed_at: today, result: { transcript_source: "asr" } },
    { id: "old", state: "completed", title: "Old save", completed_at: yesterday, transcript_source: "captions", source_url: "https://youtu.be/ZYXWVUTSRQP" }];
  p.state.library = [{ video_id: "abcdefghijk", title: "Saved version", transcript_source: "captions", source_url: video }];
  p.state.queue = { pending: [pending({ status: "failed" })] };
  p.renderQueue(p.state.queue);
  same(p.state.activityEntries.length, 4, "job, duplicate job, queue and saved row merge per source");
  same(p.state.activityEntries.map((e) => e.group).sort(), ["attention", "earlier", "progress", "today"], "all four groups");
  check(p.get("attentionRows").innerHTML.includes("Failed at video (3 of 5)"), "failure label");
  check(p.get("attentionRows").innerHTML.includes("YouTube captions"), "saved transcript provenance joins the job");
  check(p.get("completedRows").innerHTML.includes("transcript by Whisper"), "result transcript source");
  check(p.get("earlierRows").innerHTML.includes("Old save"), "earlier is visible");
  check(!p.get("queueRows").innerHTML.includes("A failed capture"), "failure listed once");
  for (const entry of p.state.activityEntries) {
    const row = p.activityRowHtml(entry);
    same((row.match(/<i class="step /g) || []).length, 5, "every row has five segments");
    check(row.includes('<time datetime="') || row.includes("Time not reported"), "honest time");
  }
  p.renderQueue({ pending: [pending({ status: "running", phase: "transcript" })] });
  check(!p.get("attentionRows").innerHTML.includes("A failed capture"), "running retry moves out of attention");
  check(p.get("queueRows").innerHTML.includes("Capturing · transcript (4 of 5)"), `running retry uses new phase: ${p.get("queueRows").innerHTML}`);
  p.state.jobs = [failed({ title: '<img src=x onerror="boom">' })];
  p.renderQueue({ pending: [] });
  check(p.get("attentionRows").innerHTML.includes("&lt;img") && !p.get("attentionRows").innerHTML.includes("<img"), "titles escaped");
  p.renderQueue({ pending: [] });
  check(!p.get("attentionRows").innerHTML.includes(" advanced"), "failure repaints do not animate");
  p.state.jobs = [];
  p.state.library = [];
  p.state.liveCaptures = [{ capture_ref: "local1", source_url: video, phase: "transcript", started_at: today }];
  p.renderQueue({ pending: [] });
  check(p.get("queueRows").innerHTML.includes("transcript (4 of 5)"), "live extract has no job yet but still shows its phase");
  p.state.jobs = [failed({ state: "completed", completed_at: new Date(Date.now() + 1000).toISOString() })];
  p.renderQueue({ pending: [] });
  same(p.state.activityEntries.length, 1, "finished job supersedes a stale live record");
  check(p.state.activityEntries[0].model.done, "completed capture never becomes active again");
  p.state.liveCaptures = [];
  p.renderQueue({ pending: [pending({ queued_at: today })] });
  check(p.state.activityEntries.some((entry) => entry.group === "progress" && entry.pending), "a new queued capture is not swallowed by an earlier success");
}

async function errors() {
  const p = makePage();
  const raw = 'noise\nERROR: first cause\n' + 'x'.repeat(7000) + '\n\u001b[31mERROR: [youtube] final <script> HTTP 429 https://x.test/?token=secret C:\\Users\\Private\\file --password=hidden\u001b[0m\ncleanup';
  const detail = p.activityLastError({ error_detail: raw });
  check(detail.startsWith("ERROR: [youtube] final"), "last ERROR survives long preamble");
  for (const secret of ["first cause", "secret", "Private", "hidden", "\u001b", "cleanup"]) check(!detail.includes(secret), `scrubbed ${secret}`);
  check(p.activityLastError({ error_detail: 'ERROR: /home/ryan/file Bearer hidden_token' }).includes("[redacted]"), "bearer scrubbed");
  check(!p.activityLastError({ error_detail: 'ERROR: "/home/ryan/private file"' }).includes("ryan"), "quoted path scrubbed");
  check(p.activityLastError({ raw_stderr: "private diagnostic" }).startsWith("No error detail"), "only public error fields");
  check(p.activityLastError({ last_error: "ERROR: queue cause" }).includes("queue cause"), "pending fallback");
  const entry = { row: failed(), pending: pending() };
  const schedule = p.activityRetrySchedule(entry);
  check(schedule.startsWith("Retries on its own at "), "scheduled clock time");
  check(schedule.includes("2 minutes, then 4 minutes after each failed attempt"), "real conditional backoff");
  check(p.activityRetrySchedule({ ...entry, pending: pending({ attempt_count: 2 }) }).includes("last automatic attempt"), "retry cap");
  for (const queued of [null, pending({ status: "failed" }), pending({ attempt_count: 3 })])
    check(p.activityRetrySchedule({ row: failed(), pending: queued }).startsWith("No automatic retries"), "no false promise");
  check(p.activityRetrySchedule({ row: failed(), pending: pending({ retry_after: yesterday }) }).startsWith("Retry is due"), "past schedule");
  check(p.activityRetrySchedule({ row: failed(), pending: pending({ retry_after: "bad" }) }).startsWith("Waiting"), "invalid schedule");
}

async function caption429() {
  const p = makePage();
  // /queue/status retains this token, but no failure_phase, while retries remain.
  const queued = Object.freeze(pending({ last_error: "youtube_rate_limit" }));
  const model = p.activitySteps(queued);
  same(model.index, 1, "caption 429 identifies waiting for YouTube");
  check(model.failed && !model.waiting, "caption 429 is a failed attempt awaiting retry");
  same(model.steps.map((step) => step.state), ["done", "fail", "todo", "todo", "todo"], "caption 429 strip marks the failed step");
  same(model.label, "Failed at waiting for YouTube (2 of 5)", "caption 429 has a readable step label");
  same(p.activitySteps({ ...queued, failure_phase: "transcript" }).index, 3, "explicit failure phase takes precedence over the token");
  const running = p.activitySteps({ ...queued, status: "running", phase: "download" });
  check(!running.failed && running.index === 2 && running.steps[2].state === "now", "running retry ignores the previous 429");
  const message = "ERROR: YouTube refused it (HTTP 429).";
  same(p.activityLastError(queued), message, "caption 429 token has a readable diagnostic");
  same(p.activityLastError({ ...queued, error_detail: "ERROR: Captions refused (HTTP 429) https://x.test/?token=private" }),
    "ERROR: Captions refused (HTTP 429) <url>", "real ERROR detail takes precedence and stays sanitized");

  p.handleJobsStreamEvent("queue", { pending: [queued] });
  same(p.state.activityEntries.map((entry) => entry.group), ["progress"], "a pending retry stays in In progress");
  same(p.get("activityFailedBadge").textContent, "", "a pending retry is not counted as a hard failure");
  same(p.get("activityNavCount").textContent, "1", "a pending retry counts as active work");
  check(!p.get("attentionRows").innerHTML.includes('data-activity-key="pending:7"'), "pending retry is absent from Needs attention");
  const row = p.get("queueRows").innerHTML;
  check(row.includes(model.label) && row.includes('<i class="step fail">'), "row renders the caption 429 failed strip and label");
  check(!row.includes("youtube_rate_limit"), "row does not expose the machine token");
  p.openCaptureFailure("pending:7", p.get("trigger"));
  check(p.els.captureFailureDrawer.open, "pending caption failure opens its drawer");
  const items = [...p.get("captureFailureSteps").innerHTML.matchAll(/<li>(.*?)<\/li>/g)].map((match) => match[1]);
  same(items.length, 5, "drawer keeps all five steps");
  check(items[0].includes("✓") && items[0].includes("Done"), "drawer marks details done");
  check(items[1].includes("✕") && items[1].includes("waiting for YouTube") && items[1].includes("Failed"), "drawer marks YouTube waiting failed with icon and words");
  check(items.slice(2).every((item) => item.includes("○") && item.includes("Not reached")), "drawer leaves later steps unreached");
  same(p.get("captureFailureError").textContent, message, "drawer shows the readable 429 diagnostic");
  check(p.get("captureFailureSchedule").textContent.startsWith("Retries on its own at "), "pending caption failure retains its retry schedule");
  check(!p.get("retryCaptureFailure").disabled && !p.get("removeCaptureFailure").disabled, "pending caption failure keeps Retry now and Remove available");
  p.closeCaptureFailure();

  for (const attempt of [0, 1, 2]) for (const withJob of [false, true]) {
    p.state.jobs = withJob ? [failed({ failure_phase: "", error_detail: "", last_error: "youtube_rate_limit" })] : [];
    p.renderQueue({ pending: [pending({ last_error: "youtube_rate_limit", attempt_count: attempt })] });
    same(p.state.activityEntries.length, 1, "pending retry and its failed job render once");
    const entry = p.state.activityEntries[0];
    same(entry.group, "progress", "every remaining retry stays in progress, including merged jobs");
    same(entry.model.index, 1, "merged caption retry keeps the waiting-for-YouTube failure step");
    same(p.get("activityFailedBadge").textContent, "", "remaining retries never inflate the failed badge");
    same(p.get("activityNavCount").textContent, "1", "merged retries count once as active work");
    p.openCaptureFailure(entry.key, p.get("trigger"));
    same(p.get("captureFailureError").textContent, message, "merged retry drawer keeps the readable 429");
    check(p.get("captureFailureSchedule").textContent.startsWith("Retries on its own at "), "remaining retries retain automatic schedule copy");
    p.closeCaptureFailure();
  }
  p.state.jobs = [];
  p.handleJobsStreamEvent("queue", { pending: [pending({ last_error: "youtube_rate_limit", status: "failed", attempt_count: 3, retry_exhausted: true })] });
  same(p.state.activityEntries[0].group, "attention", "exhausted caption failure moves to Needs attention");
  same(p.get("activityFailedBadge").textContent, "1 failed", "exhausted caption failure counts in the badge");
  same(p.get("activityNavCount").textContent, "0", "exhausted caption failure is no longer active");
}

async function exhaustion() {
  const p = makePage();
  const gaveUp = "Uoink gave up after 3 attempts. It won't retry this one on its own.";
  const job = failed({ retry_exhausted: true, attempt_count: 3 });
  const stopped = pending({ status: "failed", retry_exhausted: true, attempt_count: 3, last_error: "HTTP Error 429" });
  for (const [jobs, queued] of [[[job], []], [[], [stopped]], [[job], [stopped]], [[job], [pending()]]]) {
    p.state.jobs = jobs;
    p.renderQueue({ pending: queued });
    same(p.state.activityEntries.length, 1, "exhausted job/pending merge into one row");
    same(p.state.activityEntries[0].group, "attention", "exhaustion overrides a stale pending retry");
    same(p.get("activityFailedBadge").textContent, "1 failed", "exhausted capture keeps the hard failure badge");
    const copy = p.get("attentionRows").innerHTML.replaceAll("&#39;", "'");
    // When a stale pending record predates the exhausted job, its count
    // cannot hide that the helper has stopped retrying.
    check(copy.includes(gaveUp), "row retains exhausted copy and attempt count");
    check(!/Retries on its own|Retrying\.\.\./.test(copy), "terminal row never promises another retry");
    p.openCaptureFailure(p.state.activityEntries[0].key, p.get("trigger"));
    const schedule = p.get("captureFailureSchedule").textContent;
    check(schedule.includes("won't retry") && !schedule.includes("Retries on its own"), "drawer agrees with row");
    check(!p.get("retryCaptureFailure").disabled, "manual retry remains available");
    p.closeCaptureFailure();
  }
  p.state.jobs = [failed({ retry_exhausted: true })];
  p.renderQueue({ pending: [] });
  check(p.get("attentionRows").innerHTML.includes("Uoink gave up on this one. It won&#39;t retry it on its own."), "missing count never invents attempts");
  const legacy = p.activityRowHtml({ key: "legacy", row: failed({ error_detail: "HTTP Error 429" }) });
  check(legacy.includes("No automatic retries are scheduled") && !legacy.includes("Retrying..."), "legacy terminal rate limit stays stopped");
  const scheduled = p.activityRetrySchedule({ row: failed(), pending: pending() });
  check(scheduled.includes("Retries on its own at"), "non-terminal schedule is preserved");
  const requested = p.activityRetrySchedule({ row: job, pending: pending({ attempt_count: 3 }) });
  check(requested.includes("Your requested retry is scheduled") && !requested.includes("Retries on its own"), "manual retry after exhaustion is distinguished from automatic retries");
  same(p.activityRetrySchedule({ row: job, pending: pending({ status: "running", attempt_count: 3 }) }), "Retrying now.", "running manual attempt supersedes exhaustion");
}

async function actions() {
  const p = makePage();
  p.wireEvents();
  p.state.jobs = p.helper.jobs = [failed()];
  p.state.queue = p.helper.queue = { pending: [pending()] };
  p.renderQueue(p.state.queue);
  const trigger = p.get("fixtureTrigger"); trigger.focus();
  p.openCaptureFailure("job:j1", trigger);
  check(p.els.captureFailureDrawer.open, "drawer opens");
  same(p.document.activeElement.id, "captureFailureTitle", "heading receives focus");
  check(p.get("captureFailureSteps").innerHTML.includes("✕") && p.get("captureFailureSteps").innerHTML.includes("Not reached"), "step list symbols and words");
  check(p.get("captureFailureError").textContent.startsWith("ERROR:"), "last error is text, not markup");
  p.els.captureFailureDrawer.handlers.cancel[0]({ preventDefault() {} });
  check(!p.els.captureFailureDrawer.open && p.document.activeElement === trigger, "Escape closes and restores focus");
  p.openCaptureFailure("job:j1", trigger);
  p.helper.fail = "/queue/retry-now";
  await p.actOnActivityFailure("retry");
  check(p.els.captureFailureDrawer.open, "failed retry stays open");
  check(p.get("captureFailureActionStatus").textContent.includes("Fixture request refused"), "actual failure inline");
  check(!p.get("retryCaptureFailure").disabled, "retry re-enabled after failure");
  p.helper.fail = "";
  await p.actOnActivityFailure("retry");
  same(p.requests.filter((r) => r.path === "/queue/retry-now").at(-1).body, { pending_id: 7 }, "pending retry uses queue identity");
  check(!p.requests.some((r) => r.path === "/extract"), "pending retry does not create a second extraction");
  p.openCaptureFailure("job:j1", trigger);
  p.helper.fail = "/queue/cancel";
  await p.actOnActivityFailure("remove");
  check(p.els.captureFailureDrawer.open && p.state.activityEntries.some((e) => e.key === "job:j1"), "failed cancel never dismisses");
  p.helper.fail = "";
  await p.actOnActivityFailure("remove");
  check(!p.state.activityEntries.some((e) => e.key === "job:j1"), "removed failure stays removed after refresh");
  check(p.storage.has("uoink_activity_removed"), "removal survives reload");
  check(!p.requests.some((r) => /delete|remove/.test(r.path)), "Remove never deletes library data");
  p.state.activityRemoved = null;
  p.renderQueue(p.helper.queue);
  check(!p.state.activityEntries.length, "persisted dismissal rehydrates");
  p.state.jobs = p.helper.jobs = [failed({ completed_at: new Date(Date.now() + 1000).toISOString() })];
  p.renderQueue({ pending: [] });
  check(p.state.activityEntries.length === 1, "a later failure is not hidden");
  p.state.queue = p.helper.queue = { pending: [] };
  p.helper.detect = { ok: true, endpoint: "/playlist/start", canonical: "https://www.youtube.com/playlist?list=PLfixture" };
  p.openCaptureFailure("job:j1", trigger);
  await p.actOnActivityFailure("retry");
  check(p.requests.some((r) => r.path === "/playlist/start"), "job-only retry respects detect route");
  check(p.requests.filter((r) => r.path !== "/token").every((r) => r.options.headers["X-Uoink-Token"] === "fixture"), "all helper calls authenticated");
  // Failed pending rows are already terminal: /queue/cancel would reject
  // them. Remove dismisses their Activity history without that API call.
  p.state.jobs = [];
  p.state.queue = p.helper.queue = { pending: [pending({ status: "failed", attempt_count: 3 })] };
  p.helper.jobs = [];
  p.renderQueue(p.state.queue);
  p.openCaptureFailure("pending:7", trigger);
  const cancelCount = p.requests.filter((r) => r.path === "/queue/cancel").length;
  await p.actOnActivityFailure("remove");
  same(p.requests.filter((r) => r.path === "/queue/cancel").length, cancelCount, "terminal Remove never calls cancel");
  check(!p.state.activityEntries.length && !p.els.captureFailureDrawer.open, "terminal failure can be removed");
}

async function stream() {
  const p = makePage();
  p.handleJobsStreamEvent("snapshot", { active: [{ id: "live", state: "running", phase: "metadata" }], recent: [failed()], queue: { pending: [pending()] } });
  check(p.get("queueRows").innerHTML.includes("details (1 of 5)"), "snapshot renders live steps");
  p.openCaptureFailure("job:j1", p.get("trigger"));
  p.handleJobsStreamEvent("job", failed({ failure_phase: "transcript", error_detail: "ERROR: new failure" }));
  check(p.get("captureFailureLabel").textContent.includes("transcript (4 of 5)"), "open drawer follows events");
  same(p.get("captureFailureError").textContent, "ERROR: new failure", "drawer diagnostic refreshes");
  let release;
  p.helper.hold = { path: "/queue/status", promise: new Promise((r) => { release = r; }) };
  p.helper.queue = { pending: [pending({ status: "running", phase: "download" })] };
  p.handleJobsStreamEvent("queue", { pending: 1, running: 0, next_retry_at: pending().retry_after });
  await settle();
  check(p.state.activityEntries.find((e) => e.key === "job:j1").pending.pending_id === 7, "count event preserves pending details while fetching");
  check(p.requests.some((r) => r.path === "/queue/status"), "count-only server stream fetches details");
  p.handleJobsStreamEvent("queue", { pending: [pending({ status: "running", phase: "transcript" })] });
  release(); await settle();
  check(p.get("queueRows").innerHTML.includes("transcript (4 of 5)"), "late queue fetch cannot overwrite newer event");
  check(!p.els.captureFailureDrawer.open, "retry starting closes stale failure drawer");
  p.handleJobsStreamEvent("job", { id: "live", state: "completed", completed_at: today });
  check(p.get("completedRows").innerHTML.includes('step done'), "completion moves into Today");
}

const groups = { steps, rows, errors, caption429, exhaustion, actions, stream };
for (const name of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(groups)) {
  assert.ok(groups[name], `Unknown group ${name}`);
  const before = checks;
  await groups[name]();
  console.log(`PASS ${name}: ${checks - before} checks`);
}
