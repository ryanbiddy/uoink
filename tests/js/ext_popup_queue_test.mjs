// E1 regression harness: popup captures survive the popup closing.
//
// Chrome closes the popup as soon as the user clicks back into the page.
// popup.js used to await STC.postExtract (and postExtractReddit /
// postExtractPage) in its own document, and the helper's /extract only
// answers once the whole capture is done, so closing the popup killed the
// request and lost the clipboard copy, Claude tab, notification and failure
// record. The popup now hands the capture to background.js's queue (the one
// the context menu uses) and returns.
//
// Drives popup.js's REAL capture, hand-off, refreshQueue and Recent failures
// code and the REAL background.js in two fake extension contexts
// (ext_fake_env.mjs) that share chrome.storage; the popup's runtime messages
// reach the SW's listeners as the popup page's. A capture endpoint (or the
// popup's own /queue/status check) called from the popup context never
// answers: the popup document dies with the request still open.
//   handoff -- the popup sends one popupCapture message and returns while the
//              helper is still working (or hasn't answered /queue/status);
//              it never calls a capture endpoint, X Article fallback included
//   closed  -- with the popup gone, the SW still copies, opens Claude,
//              notifies, and records failures
//   open    -- a popup that stays (or is re-)opened renders the SW queue
//              ("Uoinking...") and shows a handed-off outcome once; duplicate
//              clicks (joining a context-menu capture too), a session add of
//              the same URL, waiting behind another capture, a full helper
//              queue, the allowlist and login walls
//   worker  -- the SW takes popupCapture only from extension pages with a
//              known route and an http(s) URL; context-menu jobs unchanged
//   retry   -- Recent failures Retry on a capture the SW queue recorded (a
//              web page, an X post's video) reruns it there; the record stays
//              until the rerun goes through, and a new failure replaces it;
//              a Retry of a capture already queued or running joins it (a
//              context-menu one too); Allow this site and retry after a
//              Retry's wall reruns the Retry's page, not the active tab's
//   restart -- MV3: the SW keeps itself alive while a job runs, and a new SW
//              takes back a capture Chrome stopped the old one in the middle
//              of: resumed once (a popup click joins it, no second
//              extraction), otherwise dropped with the lost-track notice
//   race    -- chrome.storage.session answers that come back late: a popup
//              capture (or Clear queue) sent while drain()'s read of the
//              queue is still out is neither erased, stranded nor undone
//
// No network: fetch is a stub inside each vm context.
// Run directly:  node tests/js/ext_popup_queue_test.mjs [group ...]
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EXT, abortError, jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

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

const YT_URL = "https://www.youtube.com/watch?v=abc123def45";
const REDDIT_URL = "https://www.reddit.com/r/test/comments/abc123/some_thread/";
const PAGE_URL = "https://example.com/post";
// Another site's page: the active tab while a Recent failures Retry runs.
const OTHER_PAGE_URL = "https://different.example/active";
const X_POST_URL = "https://x.com/someone/status/1720000000000000000";
const ARTICLE_URL = "https://x.com/jack/article/1900000000001";
const CLAUDE_URL = "https://claude.ai/new";
// The helper endpoints that hold the request open for the whole capture.
const CAPTURE_PATHS = ["/extract", "/extract/reddit", "/extract/page", "/extract/any"];
const POPUP_SENDER = {
  id: "test-extension-id", url: "chrome-extension://test-extension-id/popup.html",
};
const CONTENT_SENDER = { id: "test-extension-id", url: YT_URL, tab: { id: 7 } };

const CORPUS = {
  ok: true,
  title: "Some video",
  folder: "C:\\Uoink\\Tech\\some-video",
  topic: "Tech",
  corpus_md_paste: "# Some video\n\nTranscript with embedded screenshots.",
  yoink_md: "# Some video\n\nTranscript.",
};
// The helper's real /extract failure shape (error, error_detail, failure_phase).
const YT_FAILURE = {
  ok: false,
  error: "YouTube would not hand this one over cleanly. Details are tucked below.",
  error_detail: [
    "Command: yt-dlp -f best " + YT_URL,
    "Exit code: 1",
    "ERROR: [youtube] abc123def45: This video requires a GVS PO Token which was not provided.",
  ].join("\n"),
  failure_phase: "download",
};
const PO_TOKEN_LINE = "This video requires a GVS PO Token which was not provided.";
const X_TEXT_SAVED = { ok: true, tweets_captured: 2, metadata: { has_video: true } };
const PAGE_FAILURE = {
  ok: false,
  error: "Couldn't read that page. Details are tucked below.",
  error_detail: "ERROR: HTTP Error 503: Service Unavailable",
  failure_phase: "fetch",
};
const QUEUE_FULL = { ok: true, pending_count: 5 };

function lastOf(list) { return list[list.length - 1] || {}; }
function pathOf(url) { return new URL(url).pathname; }
function captureFetches(env) {
  return env.fetches.filter((u) => CAPTURE_PATHS.includes(pathOf(u)));
}
function fetchesOf(env, path) {
  return env.fetches.filter((u) => pathOf(u) === path);
}
function records(store) { return store.local.yoink_recent_failures || []; }
function clipboardWrites(worker) {
  return worker.sent.filter((m) => m && m.target === "offscreen" && m.type === "copy");
}
function handedOff(popup) {
  return popup.sent.filter((m) => m && m.type === "popupCapture");
}
// A helper response the test releases later (the capture is still running).
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
// Recent failures rows as the SW queue writes them for popup captures.
function pageRecord() {
  return {
    id: "f-page", url: PAGE_URL, videoId: null, title: "A post",
    error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z", route: "page",
  };
}
function otherRecord() {
  return {
    id: "f-other", url: "https://www.youtube.com/watch?v=zzzzzzzzzzz", videoId: "zzzzzzzzzzz",
    title: "Another video", error: "Something else.", failed_at: "2026-10-15T00:00:00.000Z",
  };
}
// Click Retry on a Recent failures row the way the popup renders it.
function clickRetry(popup, failure) {
  const row = popup.ctx.renderFailureRow(failure);
  const btn = row._all().find((el) => el.tagName === "BUTTON" && el.textContent === "Retry now");
  if (!btn) throw new Error("renderFailureRow has no Retry button");
  btn.click();
}

const POPUP_SRC = readFileSync(join(EXT, "popup.js"), "utf8");
function popupSlice(from, to) {
  const start = POPUP_SRC.indexOf(from);
  const end = POPUP_SRC.indexOf(to, start);
  if (start < 0 || end <= start) throw new Error(`popup.js slice not found: ${from}`);
  return POPUP_SRC.slice(start, end);
}

// The SW: a real background.js whose fetch is the fake helper.
// routes: helper endpoints by path -> (url, init) => Response | Promise.
// store: chrome.storage to start from (a worker Chrome restarted shares the
// one the stopped worker left).
async function makeWorker({ routes = {}, platform, store } = {}) {
  store = store || { local: {}, sync: {}, session: {} };
  const helper = (url, init) => {
    const path = pathOf(url);
    if (path === "/token") return jsonResponse({ token: "test-token" });
    if (path === "/health") return jsonResponse({ ok: true });
    if (path === "/engagement/log") return jsonResponse({ ok: true });
    if (routes[path]) return routes[path](url, init);
    throw new TypeError("Failed to fetch");
  };
  const worker = makeEnv({
    platform,
    store,
    fetch: helper,
    // The offscreen document's clipboard write succeeds.
    onSend: (msg) => (msg && msg.target === "offscreen" ? { ok: true } : undefined),
  });
  worker.load("background.js");
  await settle();
  return { worker, store, helper };
}

// The popup, open on a tab showing `url`: popup.js's real code in its own
// context, sharing chrome.storage with the worker.
async function makePopup({ worker, store, helper }, { url, title }) {
  const popup = makeEnv({
    store,
    fetch: (u, init) => (CAPTURE_PATHS.includes(pathOf(u))
      ? new Promise(() => {}) // the popup closes before this ever answers
      : helper(u, init)),
    onSend: (msg) => worker.dispatch(msg, POPUP_SENDER),
  });
  popup.allowOffers = [];
  popup.alerts = [];
  popup.popupCopies = 0;
  popup.queueStatusChecks = 0;
  popup.load("lib/x-article.js");
  popup.load("lib/extract.js");
  // What detectCurrentSource would have set for this tab.
  const source = Object.assign(popup.ctx.STC.classifyCaptureUrl(url), { title });
  const btn = popup.document.createElement("button");
  const allowBtn = popup.document.createElement("button");
  allowBtn.classList.add("hidden");
  Object.assign(popup.ctx, {
    showToast: (m) => popup.toasts.push(String(m)),
    // The persistent source alert (the X Article walls), kept apart from toasts.
    showSourceAlert: (m) => popup.alerts.push(String(m)),
    setSourceNote: () => {},
    pollQueueStatus: () => {},
    queuedToastMessage: () => "queued",
    saveClipboardBudget: () => {},
    shouldUseScreenshotPicker: async () => false,
    writeClipboardText: async () => { popup.popupCopies++; return true; },
    markClipboardUoinkNow: () => {},
    loadRecentUoinks: () => {},
    // The popup's own /queue/status check: like a capture endpoint, it never
    // answers before the popup closes.
    serverQueuePendingCount: () => { popup.queueStatusChecks++; return new Promise(() => {}); },
    offerAllowRetry: (pageUrl) => popup.allowOffers.push(pageUrl),
    RECENT_FAILURES_KEY: "yoink_recent_failures",
    shortLabel: (u) => String(u || ""),
    CLAUDE_URL,
    serverOnline: true,
    currentSource: source,
    pendingAllowHost: null,
    pendingAllowCapture: null,
    uoinkCurrentBtn: btn,
    uoinkAllowRetryBtn: allowBtn,
    queueRead: 0, closed: false, captureData: {}, renderCaptures: () => {},
    currentEl: popup.document.createElement("div"),
    queueEl: popup.document.createElement("div"),
    clearBtn: popup.document.createElement("button"),
  });
  popup.runSource(popupSlice("const POPUP_CAPTURE_RESULTS_KEY", "\nlet serverOnline"), "popup.js");
  popup.runSource(popupSlice("const SOURCE_BUTTON_LABELS", "\nfunction setSourceNote("), "popup.js");
  // captureXPost, messageActiveTab, captureXArticle, showXArticleFallbackResult
  popup.runSource(popupSlice("async function captureXPost(", "\n// ---- Capture request hand-off"), "popup.js");
  // the SW hand-off helpers, runPopupUoinkCurrent
  popup.runSource(popupSlice("const popupCaptureHandoffs", "\nfunction offerAllowRetry("), "popup.js");
  popup.runSource(popupSlice("async function runAllowSiteAndRetry(", "\nasync function runAddPodcastFeed("), "popup.js");
  // refreshQueue: the open popup's 1 s poll of chrome.storage.session
  popup.runSource(popupSlice("async function refreshQueue(", "\nasync function loadRecentUoinks("), "popup.js");
  // loadRecentFailures ... renderFailureRow: the Recent failures rows
  popup.runSource(popupSlice("function loadRecentFailures(", "\n// ---- Captures list"), "popup.js");
  btn.textContent = popup.runSource("SOURCE_BUTTON_LABELS[currentSource.source]", "probe.js");
  popup.label = btn.textContent;
  popup.source = source;
  popup.btn = btn;
  // One beat of the open popup's refreshQueue() poll.
  popup.tick = async () => {
    await settle();
    await popup.ctx.refreshQueue();
  };
  return popup;
}

// Click the way the popup's button does, and say whether the handler
// returned before the test let the helper answer.
async function returnsEarly(fn) {
  let returned = false;
  fn().then(() => { returned = true; }, () => { returned = true; });
  await settle();
  return returned;
}

// ---- handoff ----------------------------------------------------------------
async function handoff() {
  await scenario("video", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this video returns while the helper is still working on it");
    check(!captureFetches(popup).length,
      "E1: the popup no longer awaits postExtract (it calls no capture endpoint)", popup.fetches);
    const sent = handedOff(popup);
    check(sent.length === 1 && sent[0].job.route === "video"
      && sent[0].job.url === popup.source.canonical && sent[0].job.title === "Some video",
      "E1: the popup hands the video to the SW queue in one popupCapture message", sent);
    const current = base.store.session.current || {};
    check(base.store.session.busy === true && current.url === popup.source.canonical
      && current.origin === "popup" && current.interval === 30 && current.title === "Some video",
      "E1: the SW queue in chrome.storage.session is running it", base.store.session);
    check(base.worker.fetches.filter((u) => pathOf(u) === "/extract").length === 1,
      "E1: the SW holds the /extract request, not the popup", base.worker.fetches);
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    check(base.store.session.busy === false && !(base.store.session.queue || []).length,
      "the SW queue drains once the helper answers", base.store.session);
  });

  await scenario("reddit", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/reddit": () => answer.promise } });
    const popup = await makePopup(base, { url: REDDIT_URL, title: "Some thread : r/test" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this thread returns while the helper is still working on it");
    const job = (handedOff(popup)[0] || {}).job || {};
    check(job.route === "reddit" && !captureFetches(popup).length
      && base.worker.fetches.some((u) => pathOf(u) === "/extract/reddit"),
      "E1: a Reddit thread goes to the SW queue, which calls /extract/reddit",
      [job, popup.fetches, base.worker.fetches]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "Some thread" }));
    await settle();
  });

  await scenario("page", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this page returns while the helper is still fetching it");
    const job = (handedOff(popup)[0] || {}).job || {};
    check(job.route === "page" && !captureFetches(popup).length
      && base.worker.fetches.some((u) => pathOf(u) === "/extract/page"),
      "E1: a web page goes to the SW queue, which calls /extract/page",
      [job, popup.fetches, base.worker.fetches]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await settle();
  });

  await scenario("X post with a video", async () => {
    const answer = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/x": () => jsonResponse(X_TEXT_SAVED),
        "/extract": () => answer.promise,
      },
    });
    const popup = await makePopup(base, { url: X_POST_URL, title: "A post on X" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this post returns while its video is still being captured");
    check(!popup.fetches.some((u) => pathOf(u) === "/extract/x") && !captureFetches(popup).length
      && fetchesOf(base.worker, "/extract/x").length === 1,
      "E1: the worker saves the post text and captures its video without the popup", popup.fetches);
    const job = base.store.session.current || {};
    check(base.worker.ctx.STC.queueJobRoute(job) === "video" && job.saveOnly === true && job.url === popup.source.canonical,
      "the X post's video job is save-only, as before", job);
    await popup.tick();
    check(lastOf(popup.toasts) === "Saved 2 posts + queued the video.",
      "the popup says the text is saved and the video is queued", popup.toasts);
    answer.resolve(jsonResponse(CORPUS));
    await settle();
  });

  await scenario("allow this site and retry", async () => {
    const answer = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/page/allowlist": () => jsonResponse({ ok: true }),
        "/extract/page": () => answer.promise,
      },
    });
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    popup.ctx.pendingAllowHost = "example.com";
    check(await returnsEarly(() => popup.ctx.runAllowSiteAndRetry()),
      "E1: Allow this site and retry returns while the page capture runs");
    check(popup.fetches.some((u) => pathOf(u) === "/extract/page/allowlist")
      && !captureFetches(popup).length
      && base.worker.fetches.some((u) => pathOf(u) === "/extract/page"),
      "E1: the popup allows the site, then the SW queue fetches the page",
      [popup.fetches, base.worker.fetches]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await settle();
  });

  await scenario("video while the helper's queue status is pending", async () => {
    const status = deferred();
    const base = await makeWorker({
      routes: {
        "/queue/status": () => status.promise,
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this video returns while /queue/status hasn't answered");
    check(handedOff(popup).length === 1 && popup.queueStatusChecks === 0,
      "E1: the popup hands the video over without waiting on the helper's queue status",
      [handedOff(popup), popup.queueStatusChecks]);
    check(base.worker.fetches.some((u) => pathOf(u) === "/queue/status")
      && !base.worker.fetches.some((u) => pathOf(u) === "/extract"),
      "E1: the SW checks the helper's queue before it calls /extract", base.worker.fetches);
    // The popup closed before the helper's queue status answered.
    status.resolve(jsonResponse({ ok: true, pending_count: 0 }));
    await settle();
    check(base.worker.fetches.filter((u) => pathOf(u) === "/extract").length === 1
      && clipboardWrites(base.worker).length === 1
      && base.worker.tabsCreated.some((t) => t.url === CLAUDE_URL)
      && lastOf(base.worker.notifications).title === "Uoinked ★",
      "E1: then the SW runs the capture, copies, opens Claude and notifies, popup or not",
      [base.worker.fetches, base.worker.tabsCreated, base.worker.notifications]);
  });

  await scenario("X post video-only while the helper's queue status is pending", async () => {
    const status = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/x": () => jsonResponse({ ok: false, code: "empty" }),
        "/queue/status": () => status.promise,
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    const popup = await makePopup(base, { url: X_POST_URL, title: "A post on X" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: a video-only X post returns while /queue/status hasn't answered");
    const job = (handedOff(popup)[0] || {}).job || {};
    check(job.route === "x_post" && !job.saveOnly && popup.queueStatusChecks === 0
      && fetchesOf(base.worker, "/queue/status").length === 1 && !captureFetches(base.worker).length,
      "E1: its video goes to the SW queue without the popup checking the helper's queue",
      [handedOff(popup), popup.queueStatusChecks]);
    status.resolve(jsonResponse({ ok: true, pending_count: 0 }));
    await settle();
    check(clipboardWrites(base.worker).length === 1,
      "and the SW captures it once the status answers", base.worker.fetches);
  });

  await scenario("X Article fallback", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    // No in-page parser answers on this tab, so the popup falls back.
    const popup = await makePopup(base, { url: ARTICLE_URL, title: "An article / X" });
    check(await returnsEarly(() => popup.ctx.runPopupUoinkCurrent()),
      "E1: Uoink this article returns while the /extract/page fallback is still running");
    const job = (handedOff(popup)[0] || {}).job || {};
    check(handedOff(popup).length === 1 && job.route === "page"
      && job.url === popup.source.canonical && job.title === "An article / X",
      "E1: the X Article fallback goes to the SW queue in one popupCapture message",
      handedOff(popup));
    check(!captureFetches(popup).length
      && base.worker.fetches.filter((u) => pathOf(u) === "/extract/page").length === 1,
      "E1: the SW holds the /extract/page request, not the popup",
      [popup.fetches, base.worker.fetches]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "An article" }));
    await settle();
  });
}

// ---- closed -----------------------------------------------------------------
// Each scenario clicks, then the user clicks back into the page: Chrome closes
// the popup and nothing more runs there. The helper answers after that.
async function closed() {
  await scenario("success after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const toastsAtClose = popup.toasts.length;
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    const writes = clipboardWrites(base.worker);
    check(writes.length === 1 && writes[0].text === CORPUS.corpus_md_paste,
      "E1: the SW copies the corpus to the clipboard after the popup closed", writes);
    check(base.worker.tabsCreated.filter((t) => t.url === CLAUDE_URL).length === 1,
      "E1: the SW opens Claude", base.worker.tabsCreated);
    const note = lastOf(base.worker.notifications);
    check(note.title === "Uoinked ★", "E1: the SW notifies that the uoink finished", note);
    check(Number(base.store.local.yoink_last_clipboard_at) > 0,
      "E1: the copy is marked for the popup's Send-to buttons", base.store.local);
    check(base.worker.fetches.some((u) => pathOf(u) === "/engagement/log"),
      "the popup's paste engagement event is still logged", base.worker.fetches);
    check(!records(base.store).length,
      "a capture that went through leaves no failure record", records(base.store));
    check(popup.toasts.length === toastsAtClose && !popup.tabsCreated.length && !popup.popupCopies,
      "none of it depended on the closed popup", [popup.toasts, popup.tabsCreated]);
  });

  await scenario("failure after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    answer.resolve(jsonResponse(YT_FAILURE));
    await settle();
    const note = lastOf(base.worker.notifications);
    const msg = String(note.message || "");
    check(note.title === "Uoink failed" && /download step/.test(msg) && msg.includes(PO_TOKEN_LINE)
      && !/tucked below/i.test(msg) && note.requireInteraction === true,
      "E1/E3: the SW notifies the failure with its real reason and keeps it on screen", note);
    const rec = records(base.store)[0] || {};
    check(rec.url === popup.source.canonical && rec.videoId === "abc123def45"
      && rec.title === "Some video" && rec.error === note.message,
      "E1: the failure is remembered for the popup's Recent failures row (with Retry)",
      records(base.store));
    check(!clipboardWrites(base.worker).length && !base.worker.tabsCreated.length,
      "a failed capture copies nothing and opens no tab", base.worker.tabsCreated);
  });

  await scenario("timeout after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    answer.reject(abortError());
    await settle();
    const note = lastOf(base.worker.notifications);
    check(note.title === "Uoink still working" && /Activity/.test(note.message || ""),
      "E1/E7: a capture the SW stopped waiting on says still working, check Activity", note);
    check(!records(base.store).length,
      "a timeout isn't recorded as a failure: the helper may still finish it", records(base.store));
  });

  await scenario("Reddit thread after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/reddit": () => answer.promise } });
    const popup = await makePopup(base, { url: REDDIT_URL, title: "Some thread : r/test" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const thread = { ...CORPUS, title: "Some thread", corpus_md_paste: "# Some thread\n\nComments." };
    answer.resolve(jsonResponse(thread));
    await settle();
    const writes = clipboardWrites(base.worker);
    check(writes.length === 1 && writes[0].text === thread.corpus_md_paste
      && base.worker.tabsCreated.some((t) => t.url === CLAUDE_URL)
      && lastOf(base.worker.notifications).title === "Uoinked ★",
      "E1: a Reddit capture still copies, opens Claude and notifies after the popup closed",
      [writes, base.worker.tabsCreated, base.worker.notifications]);
  });

  await scenario("X post video after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/x": () => jsonResponse(X_TEXT_SAVED),
        "/extract": () => answer.promise,
      },
    });
    const popup = await makePopup(base, { url: X_POST_URL, title: "A post on X" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    const note = lastOf(base.worker.notifications);
    check(note.title === "Uoinked ★" && /Saved the video/.test(note.message || ""),
      "E1: the SW finishes the X post's video after the popup closed and says so", note);
    check(!clipboardWrites(base.worker).length && !base.worker.tabsCreated.length,
      "as before, the video half of an X post isn't copied or opened in Claude",
      [clipboardWrites(base.worker), base.worker.tabsCreated]);
  });

  await scenario("X Article fallback after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    const popup = await makePopup(base, { url: ARTICLE_URL, title: "An article / X" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const toastsAtClose = popup.toasts.length;
    const article = { ...CORPUS, title: "An article", corpus_md_paste: "# An article\n\nBody." };
    answer.resolve(jsonResponse(article));
    await settle();
    const writes = clipboardWrites(base.worker);
    check(writes.length === 1 && writes[0].text === article.corpus_md_paste
      && base.worker.tabsCreated.filter((t) => t.url === CLAUDE_URL).length === 1
      && lastOf(base.worker.notifications).title === "Uoinked ★",
      "E1: the SW finishes the X Article fallback: copies, opens Claude and notifies",
      [writes, base.worker.tabsCreated, base.worker.notifications]);
    check(popup.toasts.length === toastsAtClose && !popup.alerts.length
      && !popup.tabsCreated.length && !popup.popupCopies,
      "none of it depended on the closed popup", [popup.toasts, popup.alerts, popup.tabsCreated]);
  });

  await scenario("X Article login wall after the popup closed", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    const popup = await makePopup(base, { url: ARTICLE_URL, title: "An article / X" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    answer.resolve(jsonResponse({
      ok: false, code: "x_login_wall", error: "X asked for a login before showing this article.",
    }));
    await settle();
    const note = lastOf(base.worker.notifications);
    check(note.title === "Couldn't capture this X Article" && note.requireInteraction === true
      && /Uoink this article/.test(note.message || "") && /Nothing was saved/.test(note.message || ""),
      "E1/A2: the SW still says, and keeps on screen, that X walled the article", note);
    check(!records(base.store).length && !clipboardWrites(base.worker).length
      && !base.worker.tabsCreated.length,
      "a login wall copies nothing, opens nothing and isn't a Recent failures row",
      [records(base.store), base.worker.tabsCreated]);
  });
}

// ---- open -------------------------------------------------------------------
async function openPopup() {
  await scenario("Uoinking... then the outcome, once", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/You can close this popup/.test(lastOf(popup.toasts)),
      "E1: the popup says the capture carries on without it", popup.toasts);
    await popup.ctx.refreshQueue();
    check(popup.btn.textContent === "Uoinking..." && popup.btn.disabled === true,
      "E1: the open popup renders the SW queue: Uoinking... while this tab's capture runs",
      [popup.btn.textContent, popup.btn.disabled]);
    answer.resolve(jsonResponse(CORPUS));
    await popup.tick();
    check(lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "E1: the open popup shows the outcome the SW published", popup.toasts);
    check(popup.btn.textContent === popup.label && popup.btn.disabled === false,
      "the button comes back once the queue is done", [popup.btn.textContent, popup.btn.disabled]);
    const shown = popup.toasts.length;
    await popup.tick();
    check(popup.toasts.length === shown, "the outcome is shown once", popup.toasts);
  });

  await scenario("a second click while it runs", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(popup.toasts)),
      "a second click while the capture runs says it's already running", popup.toasts);
    check(!(base.store.session.queue || []).length,
      "and queues no duplicate", base.store.session);
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    check(base.worker.fetches.filter((u) => pathOf(u) === "/extract").length === 1
      && clipboardWrites(base.worker).length === 1,
      "the helper sees the capture once", base.worker.fetches);
  });

  await scenario("waiting behind a context-menu capture", async () => {
    const first = deferred();
    const base = await makeWorker({
      routes: {
        "/extract": () => first.promise,
        "/extract/page": () => jsonResponse({ ...CORPUS, title: "A post" }),
      },
    });
    await base.worker.ctx.enqueue({ kind: "extract", url: YT_URL, interval: 30, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/^Queued behind 1 other uoink\./.test(lastOf(popup.toasts)),
      "E1: a popup capture takes its turn in the SW queue and says so", popup.toasts);
    check(!base.worker.fetches.some((u) => pathOf(u) === "/extract/page"),
      "it waits for the capture already running", base.worker.fetches);
    first.resolve(jsonResponse(CORPUS));
    await popup.tick();
    check(base.worker.fetches.some((u) => pathOf(u) === "/extract/page")
      && lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "then it runs, and the open popup shows its outcome", popup.toasts);
  });

  await scenario("allowlist wall", async () => {
    const base = await makeWorker({
      routes: {
        "/extract/page": () => jsonResponse({
          ok: false, code: "host_not_allowed", error: "example.com isn't on your allowlist yet.",
        }, 403),
      },
    });
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    check(popup.allowOffers.length === 1 && popup.allowOffers[0] === popup.source.canonical,
      "E1: an allowlist wall from the SW queue still offers Allow this site and retry",
      popup.allowOffers);
    const note = lastOf(base.worker.notifications);
    check(note.title === "Uoink failed" && /allowlist/.test(note.message || "")
      && !/authorization/i.test(note.message || ""),
      "the SW names the allowlist, not an auth change", note);
    check(!records(base.store).length,
      "an allowlist wall isn't a failed capture: no Recent failures row", records(base.store));
  });

  await scenario("a click that joins a context-menu capture that goes through", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    // The context menu's "Uoink this page" for the page the popup is open on.
    await base.worker.ctx.enqueue({ kind: "extract", url: PAGE_URL, usePage: true, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && fetchesOf(base.worker, "/extract/page").length === 1
      && !(base.store.session.queue || []).length,
      "E1: a popup click joins the context-menu capture of the same page: no second extraction",
      [popup.toasts, base.worker.fetches, base.store.session]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await popup.tick();
    check(lastOf(popup.toasts) === "Uoinked ★ Paste in Claude."
      && clipboardWrites(base.worker).length === 1,
      "E1: the open popup shows the outcome of the context-menu capture it joined",
      [popup.toasts, clipboardWrites(base.worker)]);
    const shown = popup.toasts.length;
    await popup.tick();
    check(popup.toasts.length === shown, "the joined outcome is shown once", popup.toasts);
  });

  await scenario("a page the context menu queued with its #fragment", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    // The context menu queues the tab's raw URL, fragment and all; the popup
    // classifies the same tab without it.
    const tabUrl = `${PAGE_URL}#section`;
    await base.worker.ctx.enqueue({ kind: "extract", url: tabUrl, usePage: true, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: tabUrl, title: "A post" });
    await popup.ctx.refreshQueue();
    check(popup.source.canonical === PAGE_URL
      && popup.btn.textContent === "Uoinking..." && popup.btn.disabled === true,
      "E1: the open popup shows the context-menu capture of this page (#fragment aside) running",
      [popup.source.canonical, popup.btn.textContent, popup.btn.disabled]);
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && !(base.store.session.queue || []).length,
      "E1: a popup click on that tab joins it instead of queueing a second capture",
      [popup.toasts, base.store.session]);
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await popup.tick();
    await settle();
    check(fetchesOf(base.worker, "/extract/page").length === 1
      && clipboardWrites(base.worker).length === 1
      && base.worker.tabsCreated.filter((t) => t.url === CLAUDE_URL).length === 1,
      "E1: one extraction, one clipboard write, one Claude tab",
      [base.worker.fetches, clipboardWrites(base.worker).length, base.worker.tabsCreated]);
    check(lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "and the open popup shows its outcome", popup.toasts);
  });

  await scenario("a click that joins a context-menu capture that fails", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    await base.worker.ctx.enqueue({ kind: "extract", url: PAGE_URL, usePage: true, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    answer.resolve(jsonResponse(PAGE_FAILURE));
    await popup.tick();
    check(/503/.test(lastOf(popup.toasts)),
      "E1: the open popup shows the real reason the context-menu capture it joined failed",
      popup.toasts);
    const rec = records(base.store)[0] || {};
    check(records(base.store).length === 1 && rec.url === PAGE_URL && rec.route === "page"
      && rec.title === "A post" && /503/.test(rec.error || ""),
      "E1: and the failure gets the popup's Recent failures row, ready for Retry",
      records(base.store));
    check(fetchesOf(base.worker, "/extract/page").length === 1,
      "the page was fetched once", base.worker.fetches);
  });

  await scenario("a popup reopened mid-capture", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const first = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => first.ctx.runPopupUoinkCurrent());
    // That popup closed; the user opens it again on the same tab.
    const again = await makePopup(base, { url: YT_URL, title: "Some video" });
    await again.ctx.refreshQueue();
    check(again.btn.textContent === "Uoinking..." && again.btn.disabled === true,
      "E1: a reopened popup reads the running capture from the SW queue",
      [again.btn.textContent, again.btn.disabled]);
    answer.resolve(jsonResponse(CORPUS));
    await again.tick();
    check(!again.toasts.length,
      "a reopened popup doesn't replay an outcome the SW already notified", again.toasts);
    check(again.btn.textContent === again.label && again.btn.disabled === false,
      "and its button comes back", [again.btn.textContent, again.btn.disabled]);
  });

  await scenario("a capture a stopped service worker left behind", async () => {
    const base = await makeWorker({});
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    // Chrome stopped the SW mid-capture long ago; its busy flag is still in
    // chrome.storage.session.
    Object.assign(base.store.session, {
      busy: true,
      queue: [],
      current: {
        kind: "extract", url: popup.source.canonical, startedAt: Date.now() - 11 * 60 * 1000,
      },
    });
    await popup.ctx.refreshQueue();
    check(popup.btn.textContent === popup.label && popup.btn.disabled === false,
      "a capture older than the request timeout doesn't hold the button",
      [popup.btn.textContent, popup.btn.disabled]);
    base.store.session.current.startedAt = Date.now();
    await popup.ctx.refreshQueue();
    check(popup.btn.textContent === "Uoinking..." && popup.btn.disabled === true,
      "a capture still inside the timeout does", [popup.btn.textContent, popup.btn.disabled]);
  });

  await scenario("a session add of the same video is a different job", async () => {
    const added = deferred();
    const base = await makeWorker({
      routes: {
        "/session/add": () => added.promise,
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    await base.worker.ctx.enqueue({
      kind: "session_add", url: YT_URL, interval: 30, addedAt: Date.now(),
      session_id: "s1", session_name: "Research",
    });
    await settle();
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await popup.ctx.refreshQueue();
    check(popup.btn.textContent === popup.label && popup.btn.disabled === false,
      "E1: adding this video to a session doesn't paint its capture button Uoinking...",
      [popup.btn.textContent, popup.btn.disabled]);
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/^Queued behind 1 other uoink\./.test(lastOf(popup.toasts)),
      "E1: a popup capture isn't a duplicate of a session add of the same URL", popup.toasts);
    const queued = base.store.session.queue || [];
    check(queued.length === 1 && queued[0].origin === "popup" && queued[0].kind === "extract",
      "the capture is queued behind the session add", queued);
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && (base.store.session.queue || []).length === 1,
      "a second click matches the queued capture, not the session add", popup.toasts);
    added.resolve(jsonResponse({ ok: true, title: "Some video", video_count: 1 }));
    await popup.tick();
    check(base.worker.fetches.filter((u) => pathOf(u) === "/extract").length === 1
      && clipboardWrites(base.worker).length === 1
      && base.worker.tabsCreated.some((t) => t.url === CLAUDE_URL)
      && lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "E1: then the capture runs: extraction, clipboard, Claude tab and the popup's result",
      [base.worker.fetches, base.worker.tabsCreated, popup.toasts]);
  });

  await scenario("the helper's queue is full", async () => {
    const base = await makeWorker({
      routes: {
        "/queue/status": () => jsonResponse(QUEUE_FULL),
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    check(lastOf(popup.toasts) === "Queue full. Give it a few minutes, then try again.",
      "E1: the open popup still says the queue is full, from the SW's check", popup.toasts);
    const note = lastOf(base.worker.notifications);
    check(note.title === "Queue full", "the SW notifies it too (the popup may be gone)", note);
    check(!base.worker.fetches.some((u) => pathOf(u) === "/extract")
      && !clipboardWrites(base.worker).length && !records(base.store).length,
      "nothing is captured, and a full queue isn't a Recent failures row",
      [base.worker.fetches, records(base.store)]);
    check(popup.btn.textContent === popup.label && popup.btn.disabled === false,
      "the button comes back", [popup.btn.textContent, popup.btn.disabled]);
  });

  await scenario("the helper's queue is full for an X post's video", async () => {
    const base = await makeWorker({
      routes: {
        "/extract/x": () => jsonResponse(X_TEXT_SAVED),
        "/queue/status": () => jsonResponse(QUEUE_FULL),
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    const popup = await makePopup(base, { url: X_POST_URL, title: "A post on X" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    check(lastOf(popup.toasts)
      === "Saved 2 posts. Video not queued -- the queue is full. Try the video again in a few minutes.",
      "L-2: the saved text is reported and the dropped video isn't hidden", popup.toasts);
    check(!base.worker.fetches.some((u) => pathOf(u) === "/extract"),
      "the video isn't captured", base.worker.fetches);
  });

  await scenario("X Article walls in a popup that stays open", async () => {
    const base = await makeWorker({
      routes: {
        "/extract/page": () => jsonResponse({
          ok: false, code: "x_login_wall", error: "X asked for a login before showing this article.",
        }),
      },
    });
    const popup = await makePopup(base, { url: ARTICLE_URL, title: "An article / X" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    check(popup.alerts.length === 1 && /logged-out link fetches/.test(popup.alerts[0])
      && /Nothing was saved/.test(popup.alerts[0]),
      "E1/A2: the open popup shows the login wall as its persistent alert", popup.alerts);
    check(!popup.toasts.some((t) => /logged-out|login/i.test(t)),
      "not as a toast that vanishes", popup.toasts);

    const failing = await makeWorker({ routes: { "/extract/page": () => jsonResponse(PAGE_FAILURE) } });
    const again = await makePopup(failing, { url: ARTICLE_URL, title: "An article / X" });
    await returnsEarly(() => again.ctx.runPopupUoinkCurrent());
    await again.tick();
    check(again.alerts.length === 1 && /fetch step/.test(again.alerts[0]) && /503/.test(again.alerts[0])
      && !/tucked below/i.test(again.alerts[0]),
      "E1/E3: any other fallback failure is a persistent alert with its real reason", again.alerts);
  });
}

// ---- worker -----------------------------------------------------------------
async function worker() {
  await scenario("only extension pages", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const resp = await base.worker.dispatch(
      { type: "popupCapture", job: { route: "video", url: YT_URL } }, CONTENT_SENDER);
    await settle();
    check(resp && resp.ok === false, "a content script can't start a popup capture", resp);
    check(!base.store.session.busy && !(base.store.session.queue || []).length
      && !captureFetches(base.worker).length,
      "and nothing is queued or fetched", [base.store.session, base.worker.fetches]);
  });

  await scenario("route and URL checks", async () => {
    const base = await makeWorker({});
    const refused = [
      { route: "playlist", url: YT_URL },
      { route: "video", url: "javascript:alert(1)" },
      { route: "page", url: "file:///C:/secrets.txt" },
      { route: "video" },
    ];
    for (const job of refused) {
      const resp = await base.worker.dispatch({ type: "popupCapture", job }, POPUP_SENDER);
      check(resp && resp.ok === false && typeof resp.error === "string",
        `the SW refuses a popup capture of ${JSON.stringify(job)}`, resp);
    }
    await settle();
    check(!base.store.session.busy && !(base.store.session.queue || []).length,
      "nothing was queued", base.store.session);
  });

  await scenario("interval", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    base.store.sync.interval = 45;
    const resp = await base.worker.dispatch({
      type: "popupCapture", job: { route: "video", url: YT_URL, interval: 99999 },
    }, POPUP_SENDER);
    await settle();
    check(resp && resp.ok === true && typeof resp.id === "string"
      && (base.store.session.current || {}).interval === 45,
      "an out-of-range interval falls back to the saved setting", [resp, base.store.session]);
    answer.resolve(jsonResponse(CORPUS));
    await settle();
  });

  await scenario("context-menu jobs keep their behaviour", async () => {
    const base = await makeWorker({ routes: { "/extract": () => jsonResponse(YT_FAILURE) } });
    await base.worker.ctx.runExtractJob({ kind: "extract", url: YT_URL, interval: 30 });
    const note = lastOf(base.worker.notifications);
    check(note.title === "Uoink failed" && String(note.message || "").includes(PO_TOKEN_LINE),
      "a context-menu failure still notifies its reason", note);
    check(!records(base.store).length && !(base.store.session.popup_capture_results || []).length,
      "a context-menu job adds no Recent failures row and no popup result, as before",
      [records(base.store), base.store.session]);
  });
}

// ---- retry ------------------------------------------------------------------
async function retry() {
  await scenario("a failed popup capture records how to rerun it", async () => {
    const base = await makeWorker({ routes: { "/extract/page": () => jsonResponse(PAGE_FAILURE) } });
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await settle();
    const rec = records(base.store)[0] || {};
    check(rec.url === PAGE_URL && rec.route === "page" && rec.title === "A post"
      && /503/.test(rec.error || ""),
      "E1: a failed web-page capture's Recent failures row says it ran as a page capture",
      records(base.store));
  });

  await scenario("Retry a web page", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    clickRetry(popup, pageRecord());
    await settle();
    check(!popup.toasts.some((t) => /Can't retry/.test(t)),
      "E1: Retry takes a web page the SW queue recorded", popup.toasts);
    const sent = handedOff(popup);
    const job = (sent[0] || {}).job || {};
    check(sent.length === 1 && job.route === "page" && job.url === PAGE_URL
      && job.retryOf === "f-page" && job.title === "A post",
      "E1: Retry hands the page back to the SW queue, naming the record it came from", sent);
    check(base.worker.fetches.filter((u) => pathOf(u) === "/extract/page").length === 1
      && !captureFetches(popup).length && !popup.tabsCreated.length && !popup.windowClosed,
      "E1: the SW reruns it; the popup calls no capture endpoint and opens no tab",
      [base.worker.fetches, popup.fetches, popup.tabsCreated]);
    check(records(base.store).some((f) => f.id === "f-page"),
      "E1: the record stays while the rerun is in flight", records(base.store));
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await popup.tick();
    check(!records(base.store).some((f) => f.id === "f-page")
      && records(base.store).some((f) => f.id === "f-other"),
      "E1: once the rerun went through, just its record is dropped", records(base.store));
    check(clipboardWrites(base.worker).length === 1
      && base.worker.tabsCreated.some((t) => t.url === CLAUDE_URL)
      && lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "and it copies, opens Claude, and the open popup says so",
      [base.worker.tabsCreated, popup.toasts]);
  });

  await scenario("Retry a web page that fails again", async () => {
    const base = await makeWorker({ routes: { "/extract/page": () => jsonResponse(PAGE_FAILURE) } });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    clickRetry(popup, pageRecord());
    await popup.tick();
    const recs = records(base.store);
    const rec = recs.find((f) => f.url === PAGE_URL) || {};
    check(!recs.some((f) => f.id === "f-page") && recs.filter((f) => f.url === PAGE_URL).length === 1
      && /503/.test(rec.error || "") && rec.route === "page" && recs.some((f) => f.id === "f-other"),
      "E1: the rerun's new failure replaces the record it came from", recs);
    check(/503/.test(lastOf(popup.toasts)), "the open popup shows the new reason", popup.toasts);
  });

  await scenario("Retry that the SW stopped waiting on", async () => {
    const base = await makeWorker({ routes: { "/extract/page": () => { throw abortError(); } } });
    base.store.local.yoink_recent_failures = [pageRecord()];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    clickRetry(popup, pageRecord());
    await settle();
    check(handedOff(popup).length === 1
      && lastOf(base.worker.notifications).title === "Uoink still working",
      "the rerun ran and timed out", base.worker.notifications);
    check(records(base.store).some((f) => f.id === "f-page"),
      "E1: a rerun with no known outcome keeps the record", records(base.store));
  });

  await scenario("Retry an X post's video", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const rec = {
      id: "f-xvideo", url: X_POST_URL, videoId: null, title: "A post on X",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z", route: "video", saveOnly: true,
    };
    base.store.local.yoink_recent_failures = [rec];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    clickRetry(popup, rec);
    await settle();
    const job = (handedOff(popup)[0] || {}).job || {};
    check(job.route === "video" && job.saveOnly === true && job.retryOf === "f-xvideo"
      && job.url === X_POST_URL && !popup.tabsCreated.length,
      "E1: an X post video's Retry reruns it in the SW queue, save-only as before", handedOff(popup));
    check(records(base.store).some((f) => f.id === "f-xvideo"),
      "the record stays while it runs", records(base.store));
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    check(!records(base.store).length && !clipboardWrites(base.worker).length
      && /Saved the video/.test(lastOf(base.worker.notifications).message || ""),
      "E1: once it's saved the record goes, and nothing is copied", base.worker.notifications);
  });

  await scenario("Retry while the same capture is running", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    clickRetry(popup, pageRecord());
    await settle();
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && fetchesOf(base.worker, "/extract/page").length === 1
      && !(base.store.session.queue || []).length,
      "E1: a Retry of the page capture already running joins it: no second extraction",
      [popup.toasts, base.worker.fetches, base.store.session]);
    check(records(base.store).some((f) => f.id === "f-page"),
      "the record stays while it runs", records(base.store));
    answer.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await popup.tick();
    check(!records(base.store).some((f) => f.id === "f-page")
      && records(base.store).some((f) => f.id === "f-other"),
      "E1: the running capture's success drops the record the Retry named, and only that one",
      records(base.store));
    check(clipboardWrites(base.worker).length === 1
      && fetchesOf(base.worker, "/extract/page").length === 1
      && lastOf(popup.toasts) === "Uoinked ★ Paste in Claude.",
      "the capture ran once, and the open popup shows its outcome",
      [clipboardWrites(base.worker), base.worker.fetches, popup.toasts]);
  });

  await scenario("Retry while the same capture waits in the queue", async () => {
    const first = deferred();
    const base = await makeWorker({
      routes: {
        "/extract": () => first.promise,
        "/extract/page": () => jsonResponse({ ...CORPUS, title: "A post" }),
      },
    });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    await base.worker.ctx.enqueue({ kind: "extract", url: YT_URL, interval: 30, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    clickRetry(popup, pageRecord());
    await settle();
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && (base.store.session.queue || []).length === 1,
      "E1: a Retry of a page capture waiting in the queue joins it",
      [popup.toasts, base.store.session.queue]);
    first.resolve(jsonResponse(CORPUS));
    await popup.tick();
    check(fetchesOf(base.worker, "/extract/page").length === 1
      && !records(base.store).some((f) => f.id === "f-page")
      && records(base.store).some((f) => f.id === "f-other"),
      "E1: once that capture goes through, the record the Retry named is gone",
      [base.worker.fetches, records(base.store)]);
  });

  await scenario("Retry that joins a context-menu capture that fails again", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    await base.worker.ctx.enqueue({ kind: "extract", url: PAGE_URL, usePage: true, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(base, { url: OTHER_PAGE_URL, title: "The active tab" });
    clickRetry(popup, pageRecord());
    await settle();
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && fetchesOf(base.worker, "/extract/page").length === 1,
      "E1: a Retry joins the context-menu capture of the same page",
      [popup.toasts, base.worker.fetches]);
    answer.resolve(jsonResponse(PAGE_FAILURE));
    await popup.tick();
    const recs = records(base.store);
    const rec = recs.find((f) => f.url === PAGE_URL) || {};
    check(!recs.some((f) => f.id === "f-page") && recs.filter((f) => f.url === PAGE_URL).length === 1
      && /503/.test(rec.error || "") && rec.route === "page" && rec.title === "A post"
      && recs.some((f) => f.id === "f-other"),
      "E1: the joined capture's new failure replaces the Retry's record and its old reason", recs);
    check(/503/.test(lastOf(popup.toasts)),
      "E1: the open popup shows the joined capture's new reason", popup.toasts);
  });

  await scenario("Retry a Reddit thread the SW queue recorded, while it runs again", async () => {
    let calls = 0;
    const second = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/reddit": () => (++calls === 1 ? jsonResponse(PAGE_FAILURE) : second.promise),
      },
    });
    const popup = await makePopup(base, { url: REDDIT_URL, title: "Some thread : r/test" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    const rec = records(base.store)[0] || {};
    check(rec.route === "reddit" && rec.url === popup.source.canonical,
      "the SW queue recorded the failed thread", records(base.store));
    // Capture the thread again; while that runs, click the record's Retry.
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    clickRetry(popup, rec);
    await settle();
    const sent = handedOff(popup);
    const job = (sent[2] || {}).job || {};
    check(sent.length === 3 && job.route === "reddit" && job.url === rec.url
      && job.retryOf === rec.id && !popup.tabsCreated.length && !popup.windowClosed,
      "E1: Retry on a thread the SW queue recorded goes back to that queue, "
        + "not to a content-script tab", [sent, popup.tabsCreated, popup.windowClosed]);
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && fetchesOf(base.worker, "/extract/reddit").length === 2,
      "E1: and joins the capture of that thread already running: no second extraction",
      [popup.toasts, base.worker.fetches]);
    second.resolve(jsonResponse({ ...CORPUS, title: "Some thread" }));
    await popup.tick();
    check(!records(base.store).length && fetchesOf(base.worker, "/extract/reddit").length === 2,
      "E1: once that capture goes through, the record the Retry named is gone",
      [records(base.store), base.worker.fetches]);
  });

  await scenario("Retry an X Article the SW queue recorded", async () => {
    const base = await makeWorker({ routes: { "/extract/page": () => jsonResponse(PAGE_FAILURE) } });
    const popup = await makePopup(base, { url: ARTICLE_URL, title: "An article / X" });
    // The popup's Article capture falls back to the SW queue's /extract/page,
    // which fails and is recorded the way background.js writes it.
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    await popup.tick();
    const rec = records(base.store)[0] || {};
    check(rec.route === "page" && rec.url === popup.source.canonical,
      "the SW queue recorded the failed Article fallback as a page capture", records(base.store));
    const handed = handedOff(popup).length;
    clickRetry(popup, rec);
    await settle();
    check(handedOff(popup).length === handed && fetchesOf(base.worker, "/extract/page").length === 1,
      "E1: Retry on that Article doesn't rerun the logged-out /extract/page fetch",
      [handedOff(popup), base.worker.fetches]);
    const handoff = base.store.local.auto_yoink || {};
    check(handoff.url === rec.url && handoff.failure_id === rec.id
      && popup.tabsCreated.length === 1 && popup.tabsCreated[0].url === rec.url
      && popup.windowClosed,
      "E1: it opens the article for content-x-article.js's logged-in DOM capture (auto_yoink)",
      [handoff, popup.tabsCreated, popup.windowClosed]);
    check(records(base.store).some((f) => f.id === rec.id),
      "and the record stays until that capture settles", records(base.store));
  });

  await scenario("Retry a YouTube video the SW queue recorded", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    const rec = {
      id: "f-yt", url: YT_URL, videoId: "abc123def45", title: "Some video",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z", route: "video",
    };
    base.store.local.yoink_recent_failures = [rec, otherRecord()];
    const popup = await makePopup(base, { url: PAGE_URL, title: "A post" });
    clickRetry(popup, rec);
    await settle();
    const job = (handedOff(popup)[0] || {}).job || {};
    check(job.route === "video" && job.url === YT_URL && job.retryOf === "f-yt"
      && job.title === "Some video" && !popup.tabsCreated.length && !popup.windowClosed
      && fetchesOf(base.worker, "/extract").length === 1,
      "E1: Retry on a video the SW queue recorded reruns it in that queue, "
        + "not through a content-script tab", [handedOff(popup), popup.tabsCreated]);
    answer.resolve(jsonResponse(CORPUS));
    await popup.tick();
    check(!records(base.store).some((f) => f.id === "f-yt")
      && records(base.store).some((f) => f.id === "f-other"),
      "E1: once the rerun goes through, just its record is dropped", records(base.store));
  });

  await scenario("a Retry whose record has a #fragment joins, then it fails", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract/page": () => answer.promise } });
    // Two records for the same page: one a context-menu capture recorded
    // with the tab's #fragment.
    const fragRecord = { ...pageRecord(), id: "f-frag", url: `${PAGE_URL}#section` };
    base.store.local.yoink_recent_failures = [pageRecord(), fragRecord, otherRecord()];
    const popup = await makePopup(base, { url: OTHER_PAGE_URL, title: "The active tab" });
    clickRetry(popup, pageRecord());
    await settle();
    clickRetry(popup, fragRecord);
    await settle();
    check(/Already uoinking this one/.test(lastOf(popup.toasts))
      && fetchesOf(base.worker, "/extract/page").length === 1,
      "E1: a Retry of the same page with a #fragment joins the capture already running",
      [popup.toasts, base.worker.fetches]);
    answer.resolve(jsonResponse(PAGE_FAILURE));
    await popup.tick();
    const recs = records(base.store);
    check(!recs.some((f) => f.id === "f-page" || f.id === "f-frag")
      && recs.filter((f) => /^https:\/\/example\.com\/post/.test(f.url)).length === 1
      && recs.some((f) => f.id === "f-other"),
      "E1: its new failure replaces both Retries' records", recs);
  });

  await scenario("Retry a web page from another tab, through the allowlist", async () => {
    // The helper walls every page until example.com is on the allowlist.
    let allowed = false;
    const base = await makeWorker({
      routes: {
        "/extract/page/allowlist": () => { allowed = true; return jsonResponse({ ok: true }); },
        "/extract/page": () => (allowed
          ? jsonResponse({ ...CORPUS, title: "A post" })
          : jsonResponse({
            ok: false, code: "host_not_allowed", error: "example.com isn't on your allowlist yet.",
          }, 403)),
      },
    });
    base.store.local.yoink_recent_failures = [pageRecord(), otherRecord()];
    // The active tab is another site's page; the Retry is for example.com/post.
    const popup = await makePopup(base, { url: OTHER_PAGE_URL, title: "The active tab" });
    // popup.js's real "Allow this site and retry" offer instead of the stub.
    popup.runSource(popupSlice("function offerAllowRetry(", "\nasync function runAllowSiteAndRetry("),
      "popup.js");
    clickRetry(popup, pageRecord());
    await popup.tick();
    check(popup.ctx.pendingAllowHost === "example.com"
      && !popup.ctx.uoinkAllowRetryBtn.classList.contains("hidden"),
      "the Retry's allowlist wall offers Allow this site and retry for the Retry's site",
      popup.ctx.pendingAllowHost);
    await popup.ctx.runAllowSiteAndRetry();
    await popup.tick();
    const sent = handedOff(popup);
    const job = (sent[1] || {}).job || {};
    check(sent.length === 2 && job.route === "page" && job.url === PAGE_URL
      && job.retryOf === "f-page" && job.title === "A post",
      "E1: Allow this site and retry reruns the failed capture's page, not the active tab's, "
        + "and still names the record it came from", sent);
    const results = base.store.session.popup_capture_results || [];
    check(results.length === 2 && results.every((r) => r.url === PAGE_URL)
      && results[0].ok === true,
      "the SW queue never captures the active tab", results);
    check(!records(base.store).some((f) => f.id === "f-page")
      && records(base.store).some((f) => f.id === "f-other"),
      "E1: once the rerun goes through, the record the Retry came from is dropped",
      records(base.store));
  });
}

// ---- restart ----------------------------------------------------------------
// MV3: Chrome can stop the service worker while the helper is still working on
// a capture, and starts a new one on the next event with chrome.storage.session
// as the old one left it. The old worker's request never answers: it died with
// the worker.
const REUSED = {
  // What the helper answers a repeat /extract that waited behind the capture
  // it was running: the saved capture, without its markdown.
  ok: true, reused: true, reason: "captured_while_waiting", video_id: "abc123def45",
  title: "Some video", folder: "C:\\Uoink\\Tech\\some-video", screenshot_count: 3,
};

// A session the old worker left mid-job: `current` running, `queue` behind it.
function stoppedStore(current, queue = []) {
  return {
    local: {},
    sync: {},
    session: { busy: true, current: { startedAt: Date.now() - 60 * 1000, ...current }, queue },
  };
}

async function restart() {
  await scenario("nothing to take back", async () => {
    const base = await makeWorker({ routes: { "/extract": () => jsonResponse(CORPUS) } });
    check(!base.worker.notifications.length && !base.store.session.busy
      && !captureFetches(base.worker).length,
      "a worker start with an empty queue does nothing", [base.worker.notifications, base.store.session]);
  });

  await scenario("keep-alive while a capture runs", async () => {
    const answer = deferred();
    const base = await makeWorker({ routes: { "/extract": () => answer.promise } });
    let pings = 0;
    base.worker.chrome.runtime.getPlatformInfo = (cb) => {
      pings++;
      if (typeof cb === "function") cb({ os: "win" });
    };
    const popup = await makePopup(base, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const delays = [...base.worker.intervalDelays.values()];
    check(delays.length === 1 && delays[0] > 0 && delays[0] < 30 * 1000,
      "E1/MV3: while a job runs the SW keeps a timer shorter than Chrome's 30 s idle stop", delays);
    base.worker.runIntervals();
    check(pings === 1,
      "E1/MV3: and each beat is an extension API call, which keeps the worker alive", pings);
    answer.resolve(jsonResponse(CORPUS));
    await settle();
    base.worker.runIntervals();
    check(pings === 1 && !base.worker.intervals.size,
      "the timer stops once the queue is done", [pings, base.worker.intervals.size]);
  });

  await scenario("stopped before the helper answered", async () => {
    const dead = deferred(); // never answers: it died with the first worker
    const first = await makeWorker({ routes: { "/extract": () => dead.promise } });
    const popup = await makePopup(first, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const id = (first.store.session.current || {}).id;
    check(first.store.session.busy === true && typeof id === "string"
      && fetchesOf(first.worker, "/extract").length === 1,
      "the first worker is waiting on the helper", first.store.session);
    // Chrome stops that worker; the next event starts a new one.
    const answer = deferred();
    const next = await makeWorker({ store: first.store, routes: { "/extract": () => answer.promise } });
    const current = next.store.session.current || {};
    check(next.store.session.busy === true && current.id === id && current.resumed === true,
      "E1/MV3: the new worker takes the interrupted capture back instead of leaving it stranded",
      next.store.session);
    check(fetchesOf(next.worker, "/extract").length === 1,
      "E1/MV3: and asks the helper for it again", next.worker.fetches);
    // The user opens the popup again and clicks.
    const again = await makePopup(next, { url: YT_URL, title: "Some video" });
    await again.ctx.refreshQueue();
    check(again.btn.textContent === "Uoinking..." && again.btn.disabled === true,
      "the reopened popup shows it running", [again.btn.textContent, again.btn.disabled]);
    await returnsEarly(() => again.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(again.toasts))
      && !(next.store.session.queue || []).length
      && fetchesOf(next.worker, "/extract").length === 1,
      "E1/MV3: a popup click for it joins the resumed capture: no second extraction",
      [again.toasts, next.store.session, next.worker.fetches]);
    answer.resolve(jsonResponse(CORPUS));
    await again.tick();
    check(clipboardWrites(next.worker).length === 1
      && next.worker.tabsCreated.filter((t) => t.url === CLAUDE_URL).length === 1
      && lastOf(next.worker.notifications).title === "Uoinked ★",
      "E1/MV3: the new worker finishes it: copies, opens Claude and notifies",
      [clipboardWrites(next.worker), next.worker.tabsCreated, next.worker.notifications]);
    check(lastOf(again.toasts) === "Uoinked ★ Paste in Claude.",
      "the reopened popup shows the outcome", again.toasts);
    check(next.store.session.busy === false && !next.store.session.current
      && !(next.store.session.queue || []).length,
      "and nothing is left stranded", next.store.session);
  });

  await scenario("a stopped capture fails", async () => {
    const dead = deferred();
    const first = await makeWorker({ routes: { "/extract": () => dead.promise } });
    const popup = await makePopup(first, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const next = await makeWorker({ store: first.store, routes: { "/extract": () => jsonResponse(YT_FAILURE) } });
    await settle();
    const rec = records(next.store)[0] || {};
    check(lastOf(next.worker.notifications).title === "Uoink failed"
      && rec.url === popup.source.canonical && rec.title === "Some video",
      "E1/MV3: a resumed capture's failure is still notified and recorded for Retry",
      [next.worker.notifications, records(next.store)]);
  });

  await scenario("the helper answers with the capture it was running", async () => {
    const dead = deferred();
    const first = await makeWorker({ routes: { "/extract": () => dead.promise } });
    const popup = await makePopup(first, { url: YT_URL, title: "Some video" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    const next = await makeWorker({ store: first.store, routes: { "/extract": () => jsonResponse(REUSED) } });
    await settle();
    const note = lastOf(next.worker.notifications);
    check(note.title === "Uoinked ★" && /Saved "Some video" to your library/.test(note.message || "")
      && /Copy Markdown/.test(note.message || ""),
      "E1/MV3: a capture the helper reused is reported saved, with how to copy it", note);
    check(!clipboardWrites(next.worker).length && !next.worker.tabsCreated.length,
      "it copies nothing and opens no empty Claude tab",
      [clipboardWrites(next.worker), next.worker.tabsCreated]);
    check(next.store.session.busy === false && !records(next.store).length,
      "and the queue is done", next.store.session);
  });

  await scenario("stopped twice", async () => {
    const store = stoppedStore(
      {
        kind: "extract", url: YT_URL, interval: 30, origin: "popup", id: "popup-twice",
        title: "Some video", checkRoom: true, resumed: true,
      },
      [{ kind: "extract", url: PAGE_URL, usePage: true, origin: "popup", id: "popup-next", title: "A post" }]);
    const next = await makeWorker({
      store,
      routes: {
        "/extract": () => jsonResponse(CORPUS),
        "/extract/page": () => jsonResponse({ ...CORPUS, title: "A post" }),
      },
    });
    await settle();
    check(!fetchesOf(next.worker, "/extract").length,
      "E1/MV3: a capture already resumed once isn't sent again", next.worker.fetches);
    const lost = next.worker.notifications.find((n) => n.title === "Uoink lost track") || {};
    check(/check your Library/.test(lost.message || ""),
      "E1/MV3: it gets the lost-track notice instead", next.worker.notifications);
    const result = (next.store.session.popup_capture_results || [])
      .find((r) => r.id === "popup-twice") || {};
    check(result.ok === false && result.kind === "lost",
      "and a popup still open for it hears the same", next.store.session.popup_capture_results);
    check(!records(next.store).length,
      "an unknown outcome isn't recorded as a failure", records(next.store));
    check(fetchesOf(next.worker, "/extract/page").length === 1
      && clipboardWrites(next.worker).length === 1 && next.store.session.busy === false,
      "E1/MV3: the job queued behind it still runs", [next.worker.fetches, next.store.session]);
  });

  await scenario("stopped after the helper answered", async () => {
    const store = stoppedStore({
      kind: "extract", url: YT_URL, interval: 30, origin: "popup", id: "popup-done",
      title: "Some video", answered: true,
    });
    const next = await makeWorker({ store, routes: { "/extract": () => jsonResponse(CORPUS) } });
    await settle();
    check(!fetchesOf(next.worker, "/extract").length
      && lastOf(next.worker.notifications).title === "Uoink lost track"
      && next.store.session.busy === false,
      "E1/MV3: a capture the helper already answered isn't captured again",
      [next.worker.fetches, next.worker.notifications]);
  });

  await scenario("a popup joined a context-menu capture, then the worker stopped", async () => {
    const dead = deferred(); // never answers: it died with the first worker
    const first = await makeWorker({ routes: { "/extract/page": () => dead.promise } });
    await first.worker.ctx.enqueue({ kind: "extract", url: PAGE_URL, usePage: true, addedAt: Date.now() });
    await settle();
    const popup = await makePopup(first, { url: PAGE_URL, title: "A post" });
    await returnsEarly(() => popup.ctx.runPopupUoinkCurrent());
    check(/Already uoinking this one/.test(lastOf(popup.toasts)),
      "the popup click joined the context-menu capture", popup.toasts);
    const next = await makeWorker({
      store: first.store, routes: { "/extract/page": () => jsonResponse(PAGE_FAILURE) },
    });
    await popup.tick();
    const rec = records(next.store)[0] || {};
    check(fetchesOf(next.worker, "/extract/page").length === 1 && /503/.test(lastOf(popup.toasts))
      && rec.url === PAGE_URL && rec.title === "A post" && /503/.test(rec.error || ""),
      "E1/MV3: the resumed capture still answers the popup that joined it, and records its failure",
      [popup.toasts, records(next.store)]);
  });

  await scenario("a session add stopped mid-way", async () => {
    const store = stoppedStore({
      kind: "session_add", url: YT_URL, interval: 30, session_id: "s1", session_name: "Research",
      id: "job-add",
    });
    const next = await makeWorker({
      store, routes: { "/session/add": () => jsonResponse({ ok: true, video_count: 2 }) },
    });
    await settle();
    check(!fetchesOf(next.worker, "/session/add").length
      && lastOf(next.worker.notifications).title === "Uoink lost track"
      && next.store.session.busy === false,
      "E1/MV3: a session add isn't sent again (it would add the video twice)",
      [next.worker.fetches, next.worker.notifications]);
  });
}

// ---- race -------------------------------------------------------------------
// The SW's queue state (busy, current, queue in chrome.storage.session) is
// read and written back by separate async steps: an enqueue, drain() taking
// the next job or going idle, Clear queue. Storage answers can come back
// late, and a step that writes back what it read before another step's write
// undoes that write. Each scenario holds drain()'s read of the queue and sends
// the competing message while its answer is out.
function popupCaptureMsg(route, url, title) {
  return { type: "popupCapture", job: { route, url, title } };
}

// Holds the answer to the worker's next storage.session read of the queue
// state that match() accepts. The read itself already happened: it answers
// with what storage held when it was made.
function holdQueueRead(worker, match) {
  const gate = deferred();
  let caught = false;
  worker.storageDelay.session = (request) => {
    if (caught || request.op !== "get" || !(request.keys || []).includes("queue") || !match()) {
      return undefined;
    }
    caught = true;
    return gate.promise;
  };
  return { caught: () => caught, release: () => gate.resolve() };
}

// k turns of the event loop.
function turns(k) {
  let p = Promise.resolve();
  for (let i = 0; i < k; i++) p = p.then(() => new Promise((r) => setImmediate(r)));
  return p;
}

// Let the event loop turn until cond() holds (or `rounds` turns pass).
async function settleUntil(cond, rounds = 4000) {
  for (let i = 0; i < rounds && !cond(); i++) await new Promise((r) => setImmediate(r));
}

// From now on every storage.session answer the worker gets comes back 0-4
// event-loop turns late, in a fixed pseudo-random pattern per seed (MINSTD),
// so answers to requests made in one order arrive in another.
function lateSessionAnswers(worker, seed) {
  let n = seed;
  worker.storageDelay.session = () => {
    n = (n * 48271) % 2147483647;
    return turns(n % 5);
  };
}

function draining(worker) {
  return worker.runSource("_draining.running", "probe.js");
}

// Nothing stranded: the queue is empty and idle, and no drain() is left
// holding the flag or its keep-alive timer.
function idleQueue(base) {
  const s = base.store.session;
  return s.busy === false && !s.current && !(s.queue || []).length
    && draining(base.worker) === false && !base.worker.intervals.size;
}

function resultFor(store, id) {
  return (store.session.popup_capture_results || []).find((r) => r.id === id) || {};
}

async function race() {
  await scenario("a popup capture sent while drain() reads the queue", async () => {
    const page = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/page": () => page.promise,
        "/extract/reddit": () => jsonResponse({ ...CORPUS, title: "Some thread" }),
      },
    });
    // drain()'s first read of the queue once the page capture is in it.
    const hold = holdQueueRead(base.worker,
      () => (base.store.session.queue || []).some((j) => j.url === PAGE_URL));
    const first = await base.worker.dispatch(popupCaptureMsg("page", PAGE_URL, "A post"), POPUP_SENDER);
    await settle();
    check(first && first.ok === true && hold.caught(),
      "the page capture is queued, and drain()'s read of the queue answers late",
      [first, hold.caught(), base.store.session]);
    const replied = base.worker.dispatch(
      popupCaptureMsg("reddit", REDDIT_URL, "Some thread"), POPUP_SENDER);
    await settle();
    hold.release();
    await settle();
    const second = await replied;
    check(second && second.ok === true && !second.duplicate,
      "the capture sent while that answer was out is acknowledged", second);
    page.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await settle();
    check(fetchesOf(base.worker, "/extract/page").length === 1
      && fetchesOf(base.worker, "/extract/reddit").length === 1
      && resultFor(base.store, (second || {}).id).ok === true,
      "E1: drain() doesn't write back a stale queue that erases it: both captures run once",
      [base.worker.fetches, base.store.session]);
    check(idleQueue(base), "and the queue ends idle with nothing stranded",
      [base.store.session, draining(base.worker), base.worker.intervals.size]);
  });

  await scenario("a popup capture sent while drain() goes idle", async () => {
    const page = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/page": () => page.promise,
        "/extract/reddit": () => jsonResponse({ ...CORPUS, title: "Some thread" }),
      },
    });
    const first = await base.worker.dispatch(popupCaptureMsg("page", PAGE_URL, "A post"), POPUP_SENDER);
    await settle();
    // drain()'s read of the queue after the page capture finished.
    const hold = holdQueueRead(base.worker,
      () => resultFor(base.store, (first || {}).id).ok === true);
    page.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await settle();
    check(hold.caught() && !(base.store.session.queue || []).length,
      "the page capture is done, and drain()'s read of the empty queue answers late",
      [hold.caught(), base.store.session]);
    const replied = base.worker.dispatch(
      popupCaptureMsg("reddit", REDDIT_URL, "Some thread"), POPUP_SENDER);
    await settle();
    hold.release();
    await settle();
    const second = await replied;
    check(second && second.ok === true && !second.duplicate,
      "the capture sent while that answer was out is acknowledged", second);
    check(fetchesOf(base.worker, "/extract/reddit").length === 1
      && resultFor(base.store, (second || {}).id).ok === true,
      "E1: drain() going idle doesn't strand it: it runs and its outcome is published",
      [base.worker.fetches, base.store.session]);
    check(idleQueue(base), "and the queue ends idle with nothing stranded",
      [base.store.session, draining(base.worker), base.worker.intervals.size]);
  });

  await scenario("Clear queue while drain() reads the queue", async () => {
    const page = deferred();
    const base = await makeWorker({
      routes: {
        "/extract/page": () => page.promise,
        "/extract/reddit": () => jsonResponse({ ...CORPUS, title: "Some thread" }),
        "/queue/status": () => jsonResponse({ ok: true, pending_count: 0 }),
        "/extract": () => jsonResponse(CORPUS),
      },
    });
    const first = await base.worker.dispatch(popupCaptureMsg("page", PAGE_URL, "A post"), POPUP_SENDER);
    await base.worker.dispatch(popupCaptureMsg("reddit", REDDIT_URL, "Some thread"), POPUP_SENDER);
    await base.worker.dispatch(popupCaptureMsg("video", YT_URL, "Some video"), POPUP_SENDER);
    await settle();
    const hold = holdQueueRead(base.worker,
      () => resultFor(base.store, (first || {}).id).ok === true);
    page.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
    await settle();
    check(hold.caught() && (base.store.session.queue || []).length === 2,
      "two captures wait, and drain()'s read of the queue answers late",
      [hold.caught(), base.store.session]);
    // The popup's Clear button while that answer is out.
    const replied = base.worker.dispatch({ type: "clearQueue" }, POPUP_SENDER);
    await settle();
    hold.release();
    await settle();
    const cleared = await replied;
    check(cleared && cleared.ok === true, "Clear queue answers", cleared);
    check(fetchesOf(base.worker, "/extract/reddit").length === 1
      && !fetchesOf(base.worker, "/extract").length,
      "drain() doesn't write back what Clear queue removed: the job it took runs, the cleared one doesn't",
      [base.worker.fetches, base.store.session]);
    check(idleQueue(base), "and the queue ends idle with nothing stranded",
      [base.store.session, draining(base.worker), base.worker.intervals.size]);
  });

  await scenario("captures while every storage answer comes back late", async () => {
    const problems = [];
    for (let seed = 1; seed <= 16; seed++) {
      const page = deferred();
      const base = await makeWorker({
        routes: {
          "/extract/page": () => page.promise,
          "/extract/reddit": () => jsonResponse({ ...CORPUS, title: "Some thread" }),
          "/queue/status": () => jsonResponse({ ok: true, pending_count: 0 }),
          "/extract": () => jsonResponse(CORPUS),
        },
      });
      lateSessionAnswers(base.worker, seed);
      // Two quick clicks, then a third a few turns after the first capture's
      // helper answers (each seed lands it somewhere else in the queue's
      // steps).
      const replies = [
        base.worker.dispatch(popupCaptureMsg("page", PAGE_URL, "A post"), POPUP_SENDER),
        base.worker.dispatch(popupCaptureMsg("reddit", REDDIT_URL, "Some thread"), POPUP_SENDER),
      ];
      await turns(seed % 4);
      page.resolve(jsonResponse({ ...CORPUS, title: "A post" }));
      await turns(seed);
      replies.push(base.worker.dispatch(popupCaptureMsg("video", YT_URL, "Some video"), POPUP_SENDER));
      const answers = await Promise.all(replies);
      const published = () => answers.every((a) => resultFor(base.store, (a || {}).id).ok === true);
      await settleUntil(() => idleQueue(base) && published());
      await settle();
      const runs = ["/extract/page", "/extract/reddit", "/extract"]
        .map((p) => fetchesOf(base.worker, p).length);
      if (!answers.every((a) => a && a.ok === true && !a.duplicate)
          || runs.some((n) => n !== 1) || !published() || !idleQueue(base)) {
        problems.push({
          seed, answers, runs, session: base.store.session, draining: draining(base.worker),
        });
      }
    }
    check(!problems.length,
      "E1: with storage answers late and out of order, every acknowledged capture runs once and the queue ends idle",
      problems);
  });
}

const GROUPS = {
  handoff,
  closed,
  open: openPopup,
  worker,
  retry,
  restart,
  race,
};

const requested = process.argv.slice(2);
const names = requested.length ? requested : Object.keys(GROUPS);
for (const name of names) {
  const run = GROUPS[name];
  if (!run) {
    failures++;
    console.error(`FAIL: unknown group ${name}`);
    continue;
  }
  const before = checks;
  await scenario(name, run);
  await settle();
  console.log(`group ${name}: ${checks - before} checks`);
}

if (failures) {
  console.error(`\n${failures} popup queue check(s) failed.`);
  process.exit(1);
}
console.log("\nAll popup queue checks passed.");
