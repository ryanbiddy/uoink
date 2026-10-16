// E3 / E4 / E6 / E7 regression harness: every extension surface shows the
// real failure reason.
//
// Drives the REAL extension scripts in a fake browser (ext_fake_env.mjs):
//   lib     -- STC.friendlyError / describeFailure / describeCaptureError
//   content_youtube   -- content.js in-page button (tooltip, notification,
//                        remembered failure, setup tab only when offline)
//   content_reddit    -- content-reddit.js failure path (E6)
//   content_x_article -- content-x-article.js failure path (E6)
//   background        -- SW proxy handlers + context-menu job notifications
//   popup             -- popup.js runPopupUoinkCurrent / captureXPost /
//                        captureXArticle / runAllowSiteAndRetry; since E1 the
//                        video, Reddit and page captures (and the X Article
//                        /extract/page fallback) run in background.js's
//                        queue, so its notification and the open popup's
//                        toast or alert (refreshQueue) both carry the reason
//   retry             -- popup Recent failures Retry -> the opened page
//                        (content.js / content-reddit.js / content-x-article.js)
//                        actually starts the capture, and only then is the
//                        failure record dropped or replaced
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/ext_error_truth_test.mjs [group ...]
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

const AUTH_COPY = /authorization changed/i;
const TUCKED = /tucked below/i;
const YT_URL = "https://www.youtube.com/watch?v=abc123def45";

// The helper's real /extract failure shape (server.py: error, error_detail
// from machine_error_detail, failure_phase).
const YT_FAILURE = {
  ok: false,
  error: "YouTube would not hand this one over cleanly. Details are tucked below.",
  error_detail: [
    "Command: yt-dlp --cookies C:\\Users\\someone\\cookies.txt -f best " + YT_URL,
    "Exit code: 1",
    "WARNING: [youtube] abc123def45: nsig extraction failed",
    "ERROR: [youtube] abc123def45: an earlier error line",
    "ERROR: [youtube] abc123def45: This video requires a GVS PO Token which was not provided.",
  ].join("\n"),
  failure_phase: "download",
};
const YT_EXCERPT = "This video requires a GVS PO Token which was not provided.";

function checkYtFailure(text, where) {
  const s = String(text || "");
  check(s.includes("download"), `${where} names the failing phase`, s);
  check(s.includes(YT_EXCERPT), `${where} carries the last yt-dlp ERROR line`, s);
  check(!TUCKED.test(s), `${where} drops 'Details are tucked below'`, s);
  check(!AUTH_COPY.test(s), `${where} is not an authorization message (E4)`, s);
  check(!/cookies\.txt|Command:|an earlier error line/.test(s),
    `${where} excerpt is one line, not the command header or an earlier line`, s);
}

function lastOf(list) { return list[list.length - 1] || {}; }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function records(env) { return env.store.local.yoink_recent_failures || []; }
// A response the test releases later (the helper is still working).
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

// ---- lib -----------------------------------------------------------------
async function lib() {
  const env = makeEnv();
  env.load("lib/extract.js");
  const STC = env.ctx.STC;

  await scenario("E4 friendlyError", () => {
    const po = "ERROR: [youtube] abc123def45: This video requires a GVS PO Token which was not provided.";
    check(!AUTH_COPY.test(STC.friendlyError(po)),
      "E4: a yt-dlp 'PO Token' error is not reported as an authorization change", STC.friendlyError(po));
    const http403 = "ERROR: unable to download video data: HTTP Error 403: Forbidden";
    check(!AUTH_COPY.test(STC.friendlyError(http403)),
      "E4: yt-dlp 'HTTP Error 403: Forbidden' text stays a YouTube error", STC.friendlyError(http403));
    const maxTokens = "Claude stopped at max tokens before the analysis finished.";
    check(!AUTH_COPY.test(STC.friendlyError(maxTokens)),
      "E4: an AI 'max tokens' error is not an authorization change", STC.friendlyError(maxTokens));
    check(AUTH_COPY.test(STC.friendlyError("missing or invalid token")),
      "E4: the server's exact 'missing or invalid token' body maps to the auth recovery copy");
    check(AUTH_COPY.test(STC.friendlyError("forbidden", 403)),
      "E4: an HTTP 403 maps to the auth recovery copy");
  });

  await scenario("E4 a real 403 response reaches the display", async () => {
    const authEnv = makeEnv({
      fetch: (url) => (url.endsWith("/token")
        ? jsonResponse({ token: "fresh-token" })
        : jsonResponse({ ok: false, error: "Forbidden" }, 403)),
    });
    authEnv.load("lib/extract.js");
    const A = authEnv.ctx.STC;
    const data = await A.postExtract(YT_URL, 30);
    check(data && data.http_status === 403,
      "E4: postExtract keeps the 403 status with the helper's body", data);
    check(authEnv.fetches.filter((u) => u.endsWith("/extract")).length === 2,
      "E4: the 403 got exactly one token-refresh retry before reaching the display", authEnv.fetches);
    check(AUTH_COPY.test(A.describeFailure(data)),
      "E4: a 403 capture response (after the refresh) shows the auth recovery copy", A.describeFailure(data));

    const pageEnv = makeEnv({
      fetch: (url) => (url.endsWith("/token")
        ? jsonResponse({ token: "t" })
        : jsonResponse({ ok: false, code: "host_not_allowed",
          error: "example.com isn't on your allowlist yet." }, 403)),
    });
    pageEnv.load("lib/extract.js");
    const P = pageEnv.ctx.STC;
    const page = await P.postExtractPage("https://example.com/post");
    const shown = P.describeFailure(page);
    check(page.http_status === 403 && !AUTH_COPY.test(shown) && /allowlist/.test(shown),
      "E4: an allowlist 403 keeps its own wording instead of the auth copy", shown);

    const sessionEnv = makeEnv({
      fetch: (url) => (url.endsWith("/token")
        ? jsonResponse({ token: "t" })
        : jsonResponse({ ok: false, error: "Forbidden" }, 403)),
    });
    sessionEnv.load("lib/extract.js");
    const S = sessionEnv.ctx.STC;
    const added = await S.addToSession("sess1", YT_URL, 30);
    check(added.http_status === 403 && AUTH_COPY.test(S.describeFailure(added)),
      "E4: a 403 on session add shows the auth recovery copy too", [added, S.describeFailure(added)]);
  });

  await scenario("E3 describeFailure", () => {
    checkYtFailure(STC.describeFailure(YT_FAILURE), "E3: describeFailure");
    const long = STC.describeFailure({
      ok: false,
      error: "Uoink couldn't finish this one. Details are tucked below.",
      error_detail: "ERROR: " + "x".repeat(500),
      failure_phase: "transcript",
    });
    check(!TUCKED.test(long) && /transcript step/.test(long) && long.length < 300
      && /\.\.\.$/.test(long), "E3: a long error_detail is trimmed to one short line", long);
    const headerOnly = STC.describeFailure({
      ok: false,
      error: "Uoink couldn't finish this one. Details are tucked below.",
      error_detail: "Command: ffmpeg -i C:\\private\\in.mp4\nExit code: 1",
      failure_phase: "screenshots",
    });
    check(/screenshots step/.test(headerOnly) && !/Command:|private/.test(headerOnly)
      && !TUCKED.test(headerOnly),
      "E3: a bare Command:/Exit code: detail adds only the phase", headerOnly);
    const dup = STC.describeFailure({
      ok: false, error: "The transcript was empty.",
      error_detail: "The transcript was empty.", failure_phase: "transcript",
    });
    check(dup.split("The transcript was empty.").length === 2 && /transcript step/.test(dup),
      "E3: a detail that repeats the error is not shown twice", dup);
    // server.py ExtractionPhaseError("download", ...): longer than the
    // excerpt cap, and machine_error_detail repeats it whitespace-collapsed.
    const timedOut = "Download timed out after about 20 minutes. This is a "
      + "download/network issue, not a screenshot setting -- the video "
      + "may be very long, or the connection to YouTube is slow or being "
      + "throttled. Try again on a faster connection, or pick a shorter "
      + "video.";
    const longDup = STC.describeFailure({
      ok: false, error: timedOut, error_detail: timedOut, failure_phase: "download",
    });
    check(timedOut.length > 180 && longDup.split("Download timed out").length === 2
      && /download step\.$/.test(longDup),
      "E3: a long detail that repeats the error is not shown twice", longDup);
    const plain = STC.describeFailure({ ok: false, error: "Queue full, wait a few minutes" });
    check(plain === "Queue full, wait a few minutes",
      "E3: a failure without phase or detail keeps the server copy", plain);
  });

  await scenario("E7 describeCaptureError", async () => {
    let pings = 0;
    const pingDown = async () => { pings++; return null; };
    const pingUp = async () => { pings++; return { ok: true }; };

    const t = await STC.describeCaptureError(abortError(), { ping: pingDown });
    check(t.kind === "timeout" && /Activity/.test(t.message)
      && !/offline|Start Menu/i.test(`${t.title} ${t.message}`),
      "E7: an AbortError (request timeout) reads as still working, check Activity", t);

    const lost = [
      new Error("Extension context invalidated."),
      new TypeError("Background SW unreachable: The message port closed before a response was received."),
      new TypeError("No response from background service worker."),
    ];
    for (const e of lost) {
      const f = await STC.describeCaptureError(e, { ping: pingDown });
      check(f.kind === "lost" && /Library/.test(f.message) && !/offline/i.test(f.title),
        `E7: '${e.message}' reads as lost track, check Library`, f);
    }
    check(pings === 0, "E7: timeouts and lost ports never claim offline via /health", pings);

    const net = () => new TypeError("Failed to fetch");
    const win = await STC.describeCaptureError(net(), { ping: pingDown, os: "win" });
    check(win.kind === "offline" && /Start Menu/.test(win.message),
      "E7: a failed fetch AND a failed /health ping is offline (Windows copy)", win);
    const mac = await STC.describeCaptureError(net(), { ping: pingDown, os: "mac" });
    check(mac.kind === "offline" && /Applications/.test(mac.message) && !/Start Menu/.test(mac.message),
      "E7: offline copy is platform-aware on macOS", mac);
    const linux = await STC.describeCaptureError(net(), { ping: pingDown, os: "linux" });
    check(linux.kind === "offline" && /Terminal/.test(linux.message) && !/Start Menu/.test(linux.message),
      "E7: offline copy is platform-aware on Linux", linux);
    const up = await STC.describeCaptureError(net(), { ping: pingUp });
    check(up.kind === "lost" && /Library/.test(up.message),
      "E7: a failed fetch while /health answers is lost track, not offline", up);
  });
}

// ---- content.js (YouTube) ---------------------------------------------------
async function youtubeEnv({ capture, ping = { ok: true }, platform, activeSession, local }) {
  const env = makeEnv({
    href: "https://m.youtube.com/watch?v=abc123def45",
    title: "Some video - YouTube",
    platform,
    onSend: (msg) => {
      if (msg.type === "stcPing") return ping;
      if (msg.type === "stcExtract" || msg.type === "stcSessionAdd") return capture(msg, env);
      return { ok: true };
    },
  });
  if (local) Object.assign(env.store.local, clone(local));
  if (activeSession) env.store.local.active_session = activeSession;
  env.load("lib/extract.js");
  env.load("lib/ui.js");
  env.load("content.js");
  await settle();
  env.runIntervals(); // the injection retry loop builds the (floating) button
  await settle();
  const btn = env.document.getElementById("stc-yt-send-to-claude");
  if (!btn) throw new Error("content.js did not inject its button");
  return { env, btn };
}

async function contentYoutube() {
  await scenario("E3 content.js {ok:false}", async () => {
    const { env, btn } = await youtubeEnv({ capture: () => ({ data: YT_FAILURE }) });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink failed", "E3: content.js notifies the failure", note);
    checkYtFailure(note.message, "E3: content.js notification");
    checkYtFailure(btn.title, "E3: content.js button tooltip");
    const rec = (env.store.local.yoink_recent_failures || [])[0] || {};
    checkYtFailure(rec.error, "E3: content.js remembered failure (popup Recent row)");
    check(rec.url === YT_URL && rec.videoId === "abc123def45" && rec.title === "Some video",
      "E3: the remembered failure keeps url, videoId and page title", rec);
  });

  await scenario("E3 content.js session add {ok:false}", async () => {
    const { env, btn } = await youtubeEnv({
      capture: () => ({ data: YT_FAILURE }),
      activeSession: { id: "sess1", name: "Research" },
    });
    btn.userClick();
    await settle();
    check(env.sent.some((m) => m.type === "stcSessionAdd"), "session add went through the SW");
    checkYtFailure(lastOf(env.notifyMessages()).message, "E3: content.js session-add notification");
  });

  await scenario("E7 content.js timeout", async () => {
    const { env, btn } = await youtubeEnv({
      capture: () => ({ networkError: "signal is aborted without reason", failure: { kind: "timeout" } }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title !== "Uoink Helper offline" && /Activity/.test(note.message || ""),
      "E7: a timed-out capture says still working, check Activity", note);
    check(/Still working/.test(btn.textContent) && /Activity/.test(btn.title),
      "E7: the button label and tooltip say still working", [btn.textContent, btn.title]);
    check(env.setupTabsOpened().length === 0, "E7: a timeout does not open the setup tab",
      env.setupTabsOpened());
  });

  await scenario("E7 content.js relayed abort without a verdict", async () => {
    const { env, btn } = await youtubeEnv({
      capture: () => ({ networkError: "signal is aborted without reason" }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(/Activity/.test(note.message || "") && env.setupTabsOpened().length === 0,
      "E7: a relayed abort message still reads as still working", note);
  });

  await scenario("E7 content.js lost port", async () => {
    const { env, btn } = await youtubeEnv({
      capture: () => ({ __reject: "The message port closed before a response was received." }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink lost track" && /Library/.test(note.message || ""),
      "E7: a lost SW port says lost track, check Library", note);
    check(env.setupTabsOpened().length === 0, "E7: a lost port does not open the setup tab",
      env.setupTabsOpened());
  });

  await scenario("E7 content.js offline verdict", async () => {
    const { env, btn } = await youtubeEnv({
      platform: "MacIntel",
      capture: () => ({ networkError: "Failed to fetch", failure: { kind: "offline" } }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink Helper offline" && /Applications/.test(note.message || "")
      && !/Start Menu/.test(note.message || ""),
      "E7: offline (health ping failed too) uses platform-aware copy", note);
    check(env.setupTabsOpened().length === 1, "E7: only the offline verdict opens the setup tab",
      env.setupTabsOpened());
  });

  await scenario("E7 content.js offline status click", async () => {
    const { env, btn } = await youtubeEnv({
      ping: null, platform: "Linux x86_64", capture: () => ({ data: { ok: true } }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink Helper offline" && /Terminal/.test(note.message || "")
      && !/Start Menu/.test(note.message || ""),
      "E7: the offline-status click uses platform-aware copy", note);
    check(!env.sent.some((m) => m.type === "stcExtract"), "offline status never posts a capture");
  });
}

// ---- content-reddit.js ------------------------------------------------------
const REDDIT_URL = "https://www.reddit.com/r/test/comments/abc123/some_thread/";
const OTHER_REDDIT_URL = "https://www.reddit.com/r/test/comments/zzz999/other_thread/";

async function redditEnv({ capture, ping = { ok: true }, local }) {
  const env = makeEnv({
    href: REDDIT_URL,
    title: "Some thread : r/test",
    onSend: (msg) => {
      if (msg.type === "stcPing") return ping;
      if (msg.type === "stcExtract") return capture(msg, env);
      return { ok: true };
    },
  });
  if (local) Object.assign(env.store.local, clone(local));
  const post = env.document.createElement("div");
  env.document.body.appendChild(post);
  env.document._selectors['[data-testid="post-container"]'] = post;
  env.load("lib/extract.js");
  env.load("lib/ui.js");
  env.load("content-reddit.js");
  await settle();
  const btn = env.document.getElementById("uoink-reddit-btn");
  if (!btn) throw new Error("content-reddit.js did not inject its button");
  return { env, btn };
}

async function contentReddit() {
  await scenario("E6 reddit {ok:false}", async () => {
    const failure = {
      ok: false,
      error: "Reddit wouldn't hand this thread over. Details are tucked below.",
      error_detail: "ERROR: HTTP Error 429: Too Many Requests",
      failure_phase: "fetch",
    };
    const { env, btn } = await redditEnv({ capture: () => ({ data: failure }) });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink failed" && /Reddit wouldn't hand this thread over/.test(note.message || "")
      && /fetch step/.test(note.message || "") && /429/.test(note.message || "")
      && !TUCKED.test(note.message || ""),
      "E6: a Reddit failure is notified with its reason", note);
    check(btn.title === note.message, "E6: the Reddit button tooltip carries the reason", btn.title);
    const rec = (env.store.local.yoink_recent_failures || [])[0] || {};
    check(rec.url === REDDIT_URL && rec.error === note.message && rec.title === "Some thread : r/test",
      "E6: the Reddit failure is remembered for the popup", rec);
  });

  await scenario("E6/E7 reddit lost port", async () => {
    const { env, btn } = await redditEnv({
      capture: () => ({ __reject: "The message port closed before a response was received." }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink lost track" && /Library/.test(note.message || ""),
      "E6/E7: a Reddit capture that lost its SW port says so", note);
    check(/Library/.test(btn.title) && env.setupTabsOpened().length === 0,
      "E6/E7: tooltip carries it and no setup tab opens", [btn.title, env.setupTabsOpened()]);
    const rec = records(env)[0] || {};
    check(rec.url === REDDIT_URL && rec.error === note.message && rec.title === "Some thread : r/test",
      "E6/E7: a Reddit transport failure is remembered for the popup", rec);
  });

  await scenario("E6 reddit queue full", async () => {
    const { env, btn } = await redditEnv({
      capture: () => ({ data: { ok: false, error: "Queue full, wait a few minutes" } }),
    });
    btn.userClick();
    await settle();
    check(lastOf(env.notifyMessages()).title === "Uoink queue full",
      "E6: a full queue is notified, not just logged", lastOf(env.notifyMessages()));
    check(!(env.store.local.yoink_recent_failures || []).length,
      "E6: a full queue is not remembered as a failure");
  });

  await scenario("E6 reddit failure after navigating away", async () => {
    const answer = deferred();
    const { env, btn } = await redditEnv({ capture: () => answer.promise });
    btn.userClick();
    await settle();
    // New Reddit is a SPA: the user opens another thread while the helper
    // is still working on this one.
    env.ctx.location.href = OTHER_REDDIT_URL;
    env.document.title = "Another thread : r/test";
    answer.resolve({ data: { ok: false, error: "Reddit wouldn't hand this thread over." } });
    await settle();
    const rec = records(env)[0] || {};
    check(rec.url === REDDIT_URL && rec.title === "Some thread : r/test",
      "E6: a Reddit failure that lands after navigating away is remembered for the thread that failed",
      rec);
  });
}

// ---- content-x-article.js ---------------------------------------------------
const ARTICLE_URL = "https://x.com/jack/article/1900000000001";
const OTHER_ARTICLE_URL = "https://x.com/jack/article/1900000000002";

// parsed: the DOM parse result, or a function returning it (called per parse).
async function xArticleEnv({ extract, parsed, local }) {
  const env = makeEnv({
    href: ARTICLE_URL,
    title: "An article / X",
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtractXArticle") return extract(msg);
      return { ok: true };
    },
  });
  if (local) Object.assign(env.store.local, clone(local));
  const article = {
    ok: true, url: ARTICLE_URL, title: "An article", author: "jack",
    markdown: "Body text", images: [],
  };
  const parse = typeof parsed === "function" ? parsed : () => parsed || article;
  // The real URL helpers from lib/x-article.js; only the DOM parse is stubbed.
  env.load("lib/x-article.js");
  env.ctx.XArticle = Object.assign({}, env.ctx.XArticle, { parseXArticle: () => parse() });
  env.load("content-x-article.js");
  await settle();
  const btn = env.document.getElementById("uoink-x-article-btn");
  if (!btn) throw new Error("content-x-article.js did not inject its button");
  return { env, btn };
}

function rememberMessages(env) {
  return env.sent.filter((m) => m && m.type === "rememberFailure");
}

async function contentXArticle() {
  await scenario("E6 x-article {ok:false}", async () => {
    const { env, btn } = await xArticleEnv({
      extract: () => ({
        data: { ok: false, error: "Article body was empty. Details are tucked below." },
        failureMessage: "Article body was empty.",
      }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink failed" && note.message === "Article body was empty.",
      "E6: an X Article server failure is notified with its reason", note);
    check(btn.title === "Article body was empty.", "E6: the X Article tooltip carries the reason", btn.title);
    const rec = lastOf(rememberMessages(env));
    check(rec.url === ARTICLE_URL && rec.error === "Article body was empty." && rec.title === "An article / X",
      "E6: the X Article failure is remembered via the SW", rec);
  });

  await scenario("E6 x-article parse failure", async () => {
    const { env, btn } = await xArticleEnv({
      extract: () => ({ data: { ok: true } }),
      parsed: { ok: false, code: "no_body", error: "Couldn't find the article body on this page." },
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(/Couldn't find the article body/.test(note.message || "")
      && /Couldn't find the article body/.test(btn.title),
      "E6: an X Article parse failure is notified and in the tooltip", [note, btn.title]);
    check(/Couldn't find the article body/.test(lastOf(rememberMessages(env)).error || ""),
      "E6: the parse failure is remembered", rememberMessages(env));
    check(!env.sent.some((m) => m.type === "stcExtractXArticle"), "a failed parse posts nothing");
  });

  await scenario("E6/E7 x-article lost port", async () => {
    const { env, btn } = await xArticleEnv({
      extract: () => ({ __reject: "The message port closed before a response was received." }),
    });
    btn.userClick();
    await settle();
    const note = lastOf(env.notifyMessages());
    check(note.title === "Uoink lost track" && /Library/.test(note.message || "")
      && /Library/.test(btn.title),
      "E6/E7: an X Article capture that lost its SW port says so", [note, btn.title]);
    check(env.setupTabsOpened().length === 0, "E6/E7: a lost port opens no setup tab");
    const rememberedLost = rememberMessages(env);
    check(rememberedLost.length === 1 && rememberedLost[0].error === note.message,
      "E6/E7: an X Article transport failure is remembered for the popup", rememberedLost);
  });

  await scenario("E6/E7 x-article offline verdict", async () => {
    const offline = {
      kind: "offline", title: "Uoink Helper offline", label: "Uoink Helper offline",
      message: "Start Uoink from the Start Menu, then try again.",
    };
    const { env, btn } = await xArticleEnv({
      extract: () => ({ networkError: "Failed to fetch", failure: offline }),
    });
    btn.userClick();
    await settle();
    check(lastOf(env.notifyMessages()).title === "Uoink Helper offline"
      && env.setupTabsOpened().length === 1,
      "E6/E7: the SW's offline verdict is shown and opens setup", env.notifyMessages());
  });

  await scenario("E6 x-article failure after navigating away", async () => {
    const answer = deferred();
    const { env, btn } = await xArticleEnv({ extract: () => answer.promise });
    btn.userClick();
    await settle();
    // X is a SPA: the user opens article B while the helper works on A.
    env.ctx.location.href = OTHER_ARTICLE_URL;
    env.document.title = "Another article / X";
    answer.resolve({
      data: { ok: false, error: "Article body was empty. Details are tucked below." },
      failureMessage: "Article body was empty.",
    });
    await settle();
    const rec = lastOf(rememberMessages(env));
    check(rec.url === ARTICLE_URL && rec.title === "An article / X"
      && rec.error === "Article body was empty.",
      "E6: an X Article failure that lands after navigating away is remembered for the article that failed",
      rec);
  });
}

// ---- background.js ------------------------------------------------------------
async function backgroundEnv(routes, platform = "Win32") {
  const env = makeEnv({
    platform,
    onSend: () => undefined,
    fetch: (url, init) => {
      const handler = routes[new URL(url).pathname];
      if (!handler) throw new TypeError("Failed to fetch");
      return handler(url, init);
    },
  });
  env.load("background.js");
  await settle();
  return env;
}

const UP = {
  "/token": () => jsonResponse({ token: "test-token" }),
  "/queue/status": () => jsonResponse({ ok: true, pending_count: 0 }),
  "/health": () => jsonResponse({ ok: true }),
};

async function background() {
  await scenario("E7 SW stcExtract timeout", async () => {
    const env = await backgroundEnv({ ...UP, "/extract": () => { throw abortError(); } });
    const resp = await env.dispatch({ type: "stcExtract", url: YT_URL, interval: 30 });
    check(resp && resp.networkError && resp.failure && resp.failure.kind === "timeout",
      "E7: the SW relays a timeout verdict with the network error", resp);
  });

  await scenario("E7 SW stcExtract offline", async () => {
    const env = await backgroundEnv({});
    const resp = await env.dispatch({ type: "stcExtract", url: YT_URL, interval: 30 });
    check(resp && resp.failure && resp.failure.kind === "offline"
      && /Start Menu/.test(resp.failure.message),
      "E7: the SW calls it offline only when /health fails too", resp);
  });

  await scenario("E7 SW stcExtract lost", async () => {
    const env = await backgroundEnv({
      ...UP, "/extract": () => { throw new TypeError("Failed to fetch"); },
    });
    const resp = await env.dispatch({ type: "stcExtract", url: YT_URL, interval: 30 });
    check(resp && resp.failure && resp.failure.kind === "lost",
      "E7: a failed request while /health answers is lost track", resp);
  });

  await scenario("E3 context-menu job {ok:false}", async () => {
    const env = await backgroundEnv({ ...UP, "/extract": () => jsonResponse(YT_FAILURE) });
    await env.ctx.runExtractJob({ kind: "extract", url: YT_URL, interval: 30 });
    const note = lastOf(env.notifications);
    check(note.title === "Uoink failed", "E3: the context-menu job notifies the failure", note);
    checkYtFailure(note.message, "E3: context-menu notification");
  });

  await scenario("E7 context-menu job timeout", async () => {
    const env = await backgroundEnv({ ...UP, "/extract": () => { throw abortError(); } });
    await env.ctx.runExtractJob({ kind: "extract", url: YT_URL, interval: 30 });
    const note = lastOf(env.notifications);
    check(note.title === "Uoink still working" && /Activity/.test(note.message || ""),
      "E7: a timed-out context-menu job says still working, not offline", note);
  });

  await scenario("E7 context-menu job offline (macOS)", async () => {
    const env = await backgroundEnv({}, "MacIntel");
    await env.ctx.runExtractJob({ kind: "extract", url: YT_URL, interval: 30 });
    const note = lastOf(env.notifications);
    check(note.title === "Uoink Helper offline" && /Applications/.test(note.message || "")
      && !/Start Menu/.test(note.message || ""),
      "E7: an offline context-menu job uses platform-aware copy", note);
  });

  await scenario("E3 session-add job {ok:false}", async () => {
    const env = await backgroundEnv({ ...UP, "/session/add": () => jsonResponse(YT_FAILURE) });
    await env.ctx.runSessionAddJob({
      kind: "session_add", session_id: "sess1", session_name: "Research", url: YT_URL, interval: 30,
    });
    checkYtFailure(lastOf(env.notifications).message, "E3: session-add job notification");
  });

  await scenario("E6 SW x-article relay", async () => {
    const env = await backgroundEnv({
      ...UP,
      "/extract/x-article": () => jsonResponse({
        ok: false, error: "Article body was empty. Details are tucked below.",
      }),
    });
    const resp = await env.dispatch({
      type: "stcExtractXArticle", article: { url: ARTICLE_URL, markdown: "x" },
    });
    check(resp && resp.data && resp.data.ok === false
      && resp.failureMessage === "Article body was empty.",
      "E6: the SW words X Article failures for the content script", resp);
  });

  await scenario("E6 SW rememberFailure relay", async () => {
    const env = await backgroundEnv(UP);
    const resp = await env.dispatch({
      type: "rememberFailure", url: ARTICLE_URL, title: "An article / X", error: "Article body was empty.",
    });
    const rec = (env.store.local.yoink_recent_failures || [])[0] || {};
    check(resp && resp.ok && rec.url === ARTICLE_URL && rec.error === "Article body was empty."
      && rec.title === "An article / X",
      "E6: the SW records X Article failures where the popup reads them", [resp, rec]);
  });

  await scenario("E6 SW replace/forget a retried record", async () => {
    const env = await backgroundEnv(UP);
    env.store.local.yoink_recent_failures = [
      // Same article, different URL shape: only the id ties it to the retry.
      { id: "f-old", url: "https://x.com/i/article/1900000000001", error: "old reason" },
      { id: "f-other", url: YT_URL, error: "other reason" },
    ];
    await env.dispatch({
      type: "rememberFailure", url: ARTICLE_URL, title: "An article / X",
      error: "Article body was empty.", replaces: "f-old",
    });
    let recs = records(env);
    check(recs.length === 2 && recs[0].url === ARTICLE_URL && recs[0].id !== "f-old"
      && !recs.some((f) => f.id === "f-old") && recs.some((f) => f.id === "f-other"),
      "E6: a retried capture's new failure replaces the record the Retry came from", recs);
    const resp = await env.dispatch({ type: "forgetFailure", id: "f-other" });
    recs = records(env);
    check(resp && resp.ok && recs.length === 1 && recs[0].url === ARTICLE_URL,
      "E6: forgetFailure drops just that record", recs);
  });
}

// ---- popup.js -------------------------------------------------------------
function popupSlice(from, to) {
  const src = readFileSync(join(EXT, "popup.js"), "utf8");
  const start = src.indexOf(from);
  const end = src.indexOf(to, start);
  if (start < 0 || end <= start) throw new Error(`popup.js slice not found: ${from}`);
  return src.slice(start, end);
}

const POPUP_SENDER = {
  id: "test-extension-id", url: "chrome-extension://test-extension-id/popup.html",
};

// routes: extra helper endpoints by path (e.g. "/extract/x").
// E1: the popup hands /extract, /extract/reddit and /extract/page captures to
// the SW queue, so a real background.js (env.worker) shares the popup's
// chrome.storage and answers its runtime messages. env.tick() is one beat of
// the open popup's refreshQueue() poll after the SW has run the job.
async function popupEnv({ extract, health, platform, routes = {} }) {
  const helper = (url) => {
    const path = new URL(url).pathname;
    if (path === "/token") return jsonResponse({ token: "test-token" });
    if (routes[path]) return routes[path]();
    if (path === "/extract" && extract) return extract();
    if (path === "/health" && health) return health();
    throw new TypeError("Failed to fetch");
  };
  const store = { local: {}, sync: {}, session: {} };
  const worker = makeEnv({ platform, store, fetch: helper, onSend: () => undefined });
  worker.load("background.js");
  await settle();
  const env = makeEnv({
    platform, store, fetch: helper,
    onSend: (msg) => worker.dispatch(msg, POPUP_SENDER),
  });
  env.worker = worker;
  env.load("lib/x-article.js");
  env.load("lib/extract.js");
  // The popup's real capture functions, run against stubbed popup state.
  Object.assign(env.ctx, {
    showToast: (m) => env.toasts.push(String(m)),
    showSourceAlert: (m) => env.toasts.push(String(m)),
    pollQueueStatus: () => {},
    queuedToastMessage: () => "queued",
    saveClipboardBudget: () => {},
    shouldUseScreenshotPicker: async () => false,
    writeClipboardText: async () => true,
    markClipboardUoinkNow: () => {},
    loadRecentUoinks: () => {},
    serverQueuePendingCount: async () => 0,
    offerAllowRetry: () => {},
    pendingAllowCapture: null,
    shortLabel: (u) => String(u || ""),
    CLAUDE_URL: "https://claude.ai/new",
    serverOnline: true,
    currentSource: { source: "youtube_video", action: "video", canonical: YT_URL },
    uoinkCurrentBtn: { disabled: false, textContent: "Uoink this video" },
    currentEl: env.document.createElement("div"),
    queueEl: env.document.createElement("div"),
    clearBtn: env.document.createElement("button"),
  });
  // The real constants the hand-off code reads.
  env.runSource(popupSlice("const POPUP_CAPTURE_RESULTS_KEY", "\nlet serverOnline"), "popup.js");
  env.runSource(popupSlice("const SOURCE_BUTTON_LABELS", "\nfunction setSourceNote("), "popup.js");
  // captureXPost, messageActiveTab, captureXArticle, showXArticleFallbackResult
  env.runSource(popupSlice("async function captureXPost(", "\n// ---- Interval setting"), "popup.js");
  // the SW hand-off helpers, runPopupUoinkCurrent
  env.runSource(popupSlice("const popupCaptureHandoffs", "\nfunction offerAllowRetry("), "popup.js");
  // refreshQueue: the open popup's 1 s poll of the SW queue state
  env.runSource(popupSlice("async function refreshQueue(", "\nclearBtn.addEventListener("), "popup.js");
  env.tick = async () => {
    await settle();
    await env.ctx.refreshQueue();
  };
  return env;
}

const X_POST_URL = "https://x.com/someone/status/1720000000000000000";
const X_TEXT_SAVED = { ok: true, tweets_captured: 2, metadata: { has_video: true } };

async function popup() {
  await scenario("E3 popup toast {ok:false}", async () => {
    const env = await popupEnv({ extract: () => jsonResponse(YT_FAILURE) });
    await env.ctx.runPopupUoinkCurrent();
    await env.tick();
    checkYtFailure(lastOf(env.worker.notifications).message,
      "E3: popup capture notification (from the SW queue)");
    checkYtFailure(lastOf(env.toasts), "E3: popup toast");
  });

  await scenario("E7 popup allow-site retry is classified", async () => {
    const env = await popupEnv({
      routes: {
        "/extract/page/allowlist": () => jsonResponse({ ok: true }),
        "/extract/page": () => { throw abortError(); },
      },
    });
    const btnState = { textContent: "Allow this site and retry", disabled: false };
    Object.assign(env.ctx, {
      uoinkAllowRetryBtn: Object.assign(btnState, {
        classList: { add() {}, remove() {}, contains: () => true },
      }),
      pendingAllowHost: "example.com",
      currentSource: { source: "page", action: "page", canonical: "https://example.com/post" },
      setSourceNote: () => {},
    });
    env.runSource(popupSlice("async function runAllowSiteAndRetry(", "\nasync function runAddPodcastFeed("), "popup.js");
    await env.ctx.runAllowSiteAndRetry();
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/Activity/.test(toast) && !/aborted/i.test(toast),
      "E7: a timed-out capture after allowing a site says still working, check Activity", toast);
    const note = lastOf(env.worker.notifications);
    check(note.title === "Uoink still working" && /Activity/.test(note.message || ""),
      "E7: the SW queue's notification for it says still working too", note);
  });

  await scenario("E7 popup timeout", async () => {
    const env = await popupEnv({ extract: () => { throw abortError(); } });
    await env.ctx.runPopupUoinkCurrent();
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/Activity/.test(toast) && !/aborted/i.test(toast),
      "E7: a timed-out popup capture says still working, check Activity", toast);
    const note = lastOf(env.worker.notifications);
    check(note.title === "Uoink still working" && /Activity/.test(note.message || ""),
      "E7: the SW queue's notification says still working, not offline", note);
  });

  await scenario("E7 popup offline (Linux)", async () => {
    const env = await popupEnv({
      platform: "Linux x86_64", extract: () => { throw new TypeError("Failed to fetch"); },
    });
    await env.ctx.runPopupUoinkCurrent();
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/Terminal/.test(toast) && !/Failed to fetch/.test(toast),
      "E7: an unreachable helper (health ping failed too) gets platform-aware copy", toast);
    const note = lastOf(env.worker.notifications);
    check(note.title === "Uoink Helper offline" && /Terminal/.test(note.message || "")
      && !/Start Menu/.test(note.message || ""),
      "E7: the SW queue's offline notification is platform-aware", note);
  });

  await scenario("E7 popup lost", async () => {
    const env = await popupEnv({
      extract: () => { throw new TypeError("Failed to fetch"); },
      health: () => jsonResponse({ ok: true }),
    });
    await env.ctx.runPopupUoinkCurrent();
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/Library/.test(toast), "E7: a failed request while /health answers is lost track", toast);
    check(lastOf(env.worker.notifications).title === "Uoink lost track",
      "E7: the SW queue's notification says lost track", lastOf(env.worker.notifications));
  });

  await scenario("E3 popup captureXPost video {ok:false}", async () => {
    const env = await popupEnv({
      routes: { "/extract/x": () => jsonResponse(X_TEXT_SAVED) },
      extract: () => jsonResponse(YT_FAILURE),
    });
    await env.ctx.captureXPost(X_POST_URL, 30);
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/^Saved 2 posts\./.test(toast), "E3: captureXPost keeps the saved-post status", toast);
    checkYtFailure(toast, "E3: captureXPost video failure toast");
    checkYtFailure(lastOf(env.worker.notifications).message,
      "E3: captureXPost video failure notification (from the SW queue)");
  });

  await scenario("E7 popup captureXPost video timeout", async () => {
    const env = await popupEnv({
      routes: { "/extract/x": () => jsonResponse(X_TEXT_SAVED) },
      extract: () => { throw abortError(); },
    });
    await env.ctx.captureXPost(X_POST_URL, 30);
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/^Saved 2 posts\./.test(toast) && /Activity/.test(toast)
      && !/Couldn't queue the video/.test(toast),
      "E7: a timed-out video request says still working (check Activity), not 'couldn't queue'", toast);
  });

  await scenario("E7 popup captureXPost video offline", async () => {
    const env = await popupEnv({
      platform: "MacIntel",
      routes: { "/extract/x": () => jsonResponse(X_TEXT_SAVED) },
      extract: () => { throw new TypeError("Failed to fetch"); },
    });
    await env.ctx.captureXPost(X_POST_URL, 30);
    await env.tick();
    const toast = String(lastOf(env.toasts));
    check(/^Saved 2 posts\./.test(toast) && /Applications/.test(toast) && !/Start Menu/.test(toast),
      "E7: an unreachable helper on the video step gets platform-aware offline copy", toast);
  });

  await scenario("E3 popup captureXPost text {ok:false}", async () => {
    const env = await popupEnv({
      routes: {
        "/extract/x": () => jsonResponse({
          ok: false, code: "fetch_failed",
          error: "X wouldn't hand this post over. Details are tucked below.",
          error_detail: "ERROR: HTTP Error 429: Too Many Requests",
          failure_phase: "fetch",
        }),
      },
      extract: () => jsonResponse({ ok: true, queued: true }),
    });
    await env.ctx.captureXPost(X_POST_URL, 30);
    const toast = String(lastOf(env.toasts));
    check(/X wouldn't hand this post over/.test(toast) && /fetch step/.test(toast)
      && /429/.test(toast) && !TUCKED.test(toast),
      "E3: a refused X post toast names the phase and the detail", toast);
    await env.tick();
    check(!env.fetches.some((u) => new URL(u).pathname === "/extract")
      && !env.worker.fetches.some((u) => new URL(u).pathname === "/extract")
      && !env.sent.some((m) => m.type === "popupCapture"),
      "a refused X post queues nothing", [env.fetches, env.worker.fetches, env.sent]);
  });

  await scenario("E3 popup captureXArticle fallback {ok:false}", async () => {
    const env = await popupEnv({
      routes: {
        "/extract/page": () => jsonResponse({
          ok: false, error: "Couldn't read that page. Details are tucked below.",
          error_detail: "ERROR: HTTP Error 503: Service Unavailable", failure_phase: "fetch",
        }),
      },
    });
    await env.ctx.captureXArticle(ARTICLE_URL);
    // E1: the fallback runs in the SW queue; the open popup shows its outcome.
    await env.tick();
    const alert = String(lastOf(env.toasts));
    check(/Couldn't read that page/.test(alert) && /fetch step/.test(alert)
      && /503/.test(alert) && !TUCKED.test(alert),
      "E3: the X Article fallback alert names the phase and the detail", alert);
    const note = lastOf(env.worker.notifications);
    check(note.title === "Uoink failed" && /503/.test(note.message || "")
      && !TUCKED.test(note.message || ""),
      "E3: the SW queue's notification for the X Article fallback names the detail too", note);
  });
}

// ---- Retry from the popup's Recent failures row ----------------------------
// popup.js's real renderFailureRow. Clicking Retry hands the failure to the
// page it opens; that page's content script must start the capture, and the
// record may only go once the capture has run.
async function popupRetry(failures) {
  const env = makeEnv({});
  env.store.local.yoink_recent_failures = clone(failures);
  env.load("lib/x-article.js");
  env.load("lib/extract.js");
  Object.assign(env.ctx, {
    RECENT_FAILURES_KEY: "yoink_recent_failures",
    showToast: (m) => env.toasts.push(String(m)),
    loadRecentUoinks: async () => {},
  });
  // loadRecentFailures, saveRecentFailures, removeRecentFailure, renderFailureRow
  env.runSource(popupSlice("function loadRecentFailures(", "\n// ---- Index backfill status"), "popup.js");
  const row = env.ctx.renderFailureRow(failures[0]);
  const retryBtn = row._all().find((el) => el.tagName === "BUTTON" && el.textContent === "Retry");
  if (!retryBtn) throw new Error("renderFailureRow has no Retry button");
  retryBtn.click();
  await settle();
  return env;
}

function checkRetryHandoff(env, failure, where) {
  const handoff = env.store.local.auto_yoink || {};
  check(handoff.failure_id === failure.id && typeof handoff.ts === "number",
    `${where}: Retry hands the failure to the page it opens`, handoff);
  check(env.tabsCreated.some((t) => t.url === failure.url) && env.windowClosed,
    `${where}: Retry opens the failed page`, env.tabsCreated);
  check(records(env).some((f) => f.id === failure.id),
    `${where}: Retry keeps the record until a capture has started`, records(env));
}

const OTHER_FAILURE = {
  id: "f-other", url: "https://www.youtube.com/watch?v=zzzzzzzzzzz", videoId: "zzzzzzzzzzz",
  title: "Another video", error: "Something else.", failed_at: "2026-10-15T00:00:00.000Z",
};

async function retry() {
  await scenario("E6 Retry: Reddit thread", async () => {
    const failure = {
      id: "f-reddit", url: REDDIT_URL, videoId: null, title: "Some thread : r/test",
      error: "Reddit wouldn't hand this thread over.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    check((popup.store.local.auto_yoink || {}).url === REDDIT_URL,
      "E6: a Reddit Retry hands over the thread URL", popup.store.local.auto_yoink);
    checkRetryHandoff(popup, failure, "E6 Reddit");

    let atCapture = null;
    const { env } = await redditEnv({
      local: popup.store.local,
      capture: (_msg, page) => { atCapture = clone(records(page)); return { data: { ok: true } }; },
    });
    await settle();
    const sent = env.sent.filter((m) => m.type === "stcExtract");
    check(sent.length === 1 && sent[0].url === REDDIT_URL,
      "E6: the opened Reddit thread starts exactly one capture", env.sent);
    check(Array.isArray(atCapture) && atCapture.some((f) => f.id === "f-reddit"),
      "E6: the Reddit record is still there when the capture starts", atCapture);
    check(!("auto_yoink" in env.store.local), "E6: the Reddit page clears the handoff",
      env.store.local.auto_yoink);
    check(!records(env).some((f) => f.id === "f-reddit")
      && records(env).some((f) => f.id === "f-other"),
      "E6: once the retried Reddit capture went through, just its record is dropped", records(env));
  });

  await scenario("E6 Retry: Reddit share link that fails again", async () => {
    const shareUrl = "https://old.reddit.com/r/test/comments/abc123/some_thread/?utm_source=share";
    const failure = {
      id: "f-reddit-share", url: shareUrl, videoId: null, title: "Some thread : r/test",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    checkRetryHandoff(popup, failure, "E6 Reddit share link");
    const { env } = await redditEnv({
      local: popup.store.local,
      capture: () => ({
        data: {
          ok: false, error: "Reddit wouldn't hand this thread over. Details are tucked below.",
          error_detail: "ERROR: HTTP Error 429: Too Many Requests", failure_phase: "fetch",
        },
      }),
    });
    await settle();
    check(env.sent.some((m) => m.type === "stcExtract" && m.url === REDDIT_URL),
      "E6: a share-link Retry still captures the thread it points at", env.sent);
    const recs = records(env);
    check(!recs.some((f) => f.id === "f-reddit-share") && recs[0] && recs[0].url === REDDIT_URL
      && /429/.test(recs[0].error || "") && recs.some((f) => f.id === "f-other"),
      "E6: the retry's new failure replaces the record it came from", recs);
  });

  await scenario("E6 Retry: no capture, no lost record", async () => {
    const failure = {
      id: "f-reddit", url: REDDIT_URL, videoId: null, title: "Some thread : r/test",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    const { env } = await redditEnv({
      local: popup.store.local, ping: null, capture: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!env.sent.some((m) => m.type === "stcExtract"), "an offline helper starts no capture",
      env.sent);
    check(records(env).some((f) => f.id === "f-reddit"),
      "E6: a Retry that never started a capture keeps the record", records(env));

    const elsewhere = await redditEnv({
      local: {
        auto_yoink: {
          url: "https://www.reddit.com/r/test/comments/zzz999/other/", failure_id: "f-x", ts: Date.now(),
        },
      },
      capture: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!elsewhere.env.sent.some((m) => m.type === "stcExtract")
      && (elsewhere.env.store.local.auto_yoink || {}).failure_id === "f-x",
      "a handoff for another thread is neither run nor claimed", elsewhere.env.sent);
  });

  await scenario("E6 Retry: Reddit, navigating away before it runs", async () => {
    const failure = {
      id: "f-reddit", url: REDDIT_URL, videoId: null, title: "Some thread : r/test",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    const ping = deferred();
    const { env } = await redditEnv({
      local: popup.store.local, ping: ping.promise, capture: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!("auto_yoink" in env.store.local) && !env.sent.some((m) => m.type === "stcExtract"),
      "the thread page claims the handoff and waits for the helper status", env.sent);
    // New Reddit is a SPA: the user opens another thread before the status
    // ping answers, then the helper turns out to be up.
    env.ctx.location.href = OTHER_REDDIT_URL;
    ping.resolve({ ok: true });
    await settle();
    check(!env.sent.some((m) => m.type === "stcExtract"),
      "E6: a pending Reddit Retry never captures the thread the tab moved to", env.sent);
    check(records(env).some((f) => f.id === "f-reddit") && records(env).some((f) => f.id === "f-other"),
      "E6: the retried Reddit record is kept when its retry never ran", records(env));
  });

  await scenario("E6 Retry: X Article once it renders", async () => {
    const failure = {
      id: "f-article", url: ARTICLE_URL, videoId: null, title: "An article / X",
      error: "Article body was empty.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    checkRetryHandoff(popup, failure, "E6 X Article");

    let rendered = false;
    const article = {
      ok: true, url: ARTICLE_URL, title: "An article", author: "jack",
      markdown: "Body text", images: [],
    };
    const { env } = await xArticleEnv({
      local: popup.store.local,
      parsed: () => (rendered ? article
        : { ok: false, code: "no_body", error: "Couldn't find the article body on this page." }),
      extract: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!("auto_yoink" in env.store.local), "E6: the article page claims the handoff",
      env.store.local.auto_yoink);
    check(!env.sent.some((m) => m.type === "stcExtractXArticle") && !rememberMessages(env).length,
      "E6: the retry waits for X to render the article instead of failing on a blank page", env.sent);

    rendered = true;
    env.mutate();
    await settle();
    const captureAt = env.sent.findIndex((m) => m.type === "stcExtractXArticle");
    const forgetAt = env.sent.findIndex((m) => m.type === "forgetFailure");
    check(captureAt >= 0 && env.sent.filter((m) => m.type === "stcExtractXArticle").length === 1,
      "E6: once the article renders, the retry captures it once", env.sent);
    check(forgetAt > captureAt && env.sent[forgetAt].id === "f-article",
      "E6: the record is dropped only after the capture went through", env.sent);

    // The SW applies that message: only the retried record goes.
    const bg = await backgroundEnv(UP);
    Object.assign(bg.store.local, clone(env.store.local));
    if (forgetAt >= 0) await bg.dispatch(env.sent[forgetAt]);
    const recs = records(bg);
    check(!recs.some((f) => f.id === "f-article") && recs.some((f) => f.id === "f-other"),
      "E6: the SW drops just the retried X Article record", recs);
  });

  await scenario("E6 Retry: X Article that never renders", async () => {
    const failure = {
      id: "f-article", url: ARTICLE_URL, videoId: null, title: "An article / X",
      error: "Article body was empty.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    const { env } = await xArticleEnv({
      local: popup.store.local,
      parsed: { ok: false, code: "no_body", error: "Couldn't find the article body on this page." },
      extract: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!rememberMessages(env).length, "the retry waits before giving up", env.sent);
    // Past the render wait: the retry runs and reports the parse failure.
    env.runSource("Date.now = ((now) => () => now() + 120000)(Date.now);", "clock.js");
    env.mutate();
    await settle();
    const rec = lastOf(rememberMessages(env));
    check(/Couldn't find the article body/.test(rec.error || "") && rec.replaces === "f-article",
      "E6: an unreadable article's failure replaces the retried record", rec);
    check(!env.sent.some((m) => m.type === "stcExtractXArticle"),
      "an unreadable article posts nothing", env.sent);
  });

  await scenario("E6 Retry: X Article, navigating away before it renders", async () => {
    const failure = {
      id: "f-article", url: ARTICLE_URL, videoId: null, title: "An article / X",
      error: "Article body was empty.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    let rendered = false;
    const otherArticle = {
      ok: true, url: OTHER_ARTICLE_URL, title: "Another article", author: "jack",
      markdown: "Other body", images: [],
    };
    const { env } = await xArticleEnv({
      local: popup.store.local,
      parsed: () => (rendered ? otherArticle
        : { ok: false, code: "no_body", error: "Couldn't find the article body on this page." }),
      extract: () => ({ data: { ok: true } }),
    });
    await settle();
    check(!("auto_yoink" in env.store.local) && !env.sent.some((m) => m.type === "stcExtractXArticle"),
      "the article page claims the handoff and waits for the render", env.sent);

    // X is a SPA: before A renders the user opens article B, which renders.
    env.ctx.location.href = OTHER_ARTICLE_URL;
    env.document.title = "Another article / X";
    rendered = true;
    env.mutate();
    await settle();
    // And past the render wait, where a pending retry stops waiting.
    env.runSource("Date.now = ((now) => () => now() + 120000)(Date.now);", "clock.js");
    env.mutate();
    env.runIntervals(); // status poll
    await settle();
    const touched = env.sent.filter((m) =>
      ["stcExtractXArticle", "forgetFailure", "rememberFailure"].includes(m.type));
    check(!touched.length,
      "E6: a pending X Article Retry never captures the article the tab moved to, and A's record is neither dropped nor replaced",
      touched);
  });

  await scenario("E6 Retry: YouTube handoff waits out a pending health check and never captures the next video", async () => {
    const failure = {
      id: "f-yt", url: YT_URL, videoId: "abc123def45", title: "Some video",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    const health = deferred();
    const { env, btn } = await youtubeEnv({
      local: popup.store.local,
      ping: health.promise,
      capture: () => ({ data: { ok: true, queued: true } }),
    });
    await settle();
    check(!env.sent.some((m) => m.type === "stcExtract"),
      "E6: no capture starts while the health check is still pending", env.sent);
    // The tab moves on to another video before the helper answers.
    env.ctx.location.href = "https://m.youtube.com/watch?v=zzzzzzzzzzz";
    health.resolve({ ok: true });
    await settle();
    check(!env.sent.some((m) => m.type === "stcExtract"),
      "E6: video A's Retry never captures video B", env.sent);
    btn.userClick(); // the user captures video B by hand
    await settle();
    const sent = env.sent.filter((m) => m.type === "stcExtract");
    check(sent.length === 1 && /zzzzzzzzzzz/.test(sent[0].url || ""),
      "E6: the manual capture is video B's", sent);
    check(records(env).some((f) => f.id === "f-yt"),
      "E6: capturing B never consumes or drops A's failure record", records(env));
  });

  await scenario("E6 Retry: YouTube handoff re-checks the video after clearing the handoff", async () => {
    const failure = {
      id: "f-yt", url: YT_URL, videoId: "abc123def45", title: "Some video",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    const env = makeEnv({
      href: "https://m.youtube.com/watch?v=abc123def45",
      title: "Some video - YouTube",
      onSend: (msg) => {
        if (msg.type === "stcPing") return { ok: true };
        if (msg.type === "stcExtract") return { data: { ok: true, queued: true } };
        return { ok: true };
      },
    });
    Object.assign(env.store.local, clone(popup.store.local));
    // Hold chrome.storage.local.remove's callback until the test releases it.
    const removal = deferred();
    const local = env.ctx.chrome.storage.local;
    const realRemove = local.remove.bind(local);
    local.remove = (keys, cb) => {
      removal.promise.then(() => realRemove(keys, cb));
      return removal.promise;
    };
    env.load("lib/extract.js");
    env.load("lib/ui.js");
    env.load("content.js");
    await settle();
    env.runIntervals();
    await settle();
    env.ctx.location.href = "https://m.youtube.com/watch?v=zzzzzzzzzzz";
    removal.resolve();
    await settle();
    check(!env.sent.some((m) => m.type === "stcExtract"),
      "E6: a handoff for video A never auto-captures video B when the tab moved while it was cleared", env.sent);
    check(records(env).some((f) => f.id === "f-yt"),
      "E6: A's failure record survives", records(env));
  });

  await scenario("E6 Retry: YouTube video", async () => {
    const failure = {
      id: "f-yt", url: YT_URL, videoId: "abc123def45", title: "Some video",
      error: "Old reason.", failed_at: "2026-10-15T00:00:00.000Z",
    };
    const popup = await popupRetry([failure, OTHER_FAILURE]);
    check((popup.store.local.auto_yoink || {}).videoId === "abc123def45",
      "a YouTube Retry hands over the video id", popup.store.local.auto_yoink);
    checkRetryHandoff(popup, failure, "YouTube");

    let atCapture = null;
    const { env } = await youtubeEnv({
      local: popup.store.local,
      capture: (_msg, page) => {
        atCapture = clone(records(page));
        return { data: { ok: true, queued: true } };
      },
    });
    await settle();
    check(env.sent.filter((m) => m.type === "stcExtract").length === 1,
      "the opened video starts exactly one capture", env.sent);
    check(Array.isArray(atCapture) && atCapture.some((f) => f.id === "f-yt"),
      "the YouTube record is still there when the capture starts", atCapture);
    check(!records(env).some((f) => f.id === "f-yt") && records(env).some((f) => f.id === "f-other"),
      "once the retried YouTube capture went through, just its record is dropped", records(env));
  });
}

const GROUPS = {
  lib,
  content_youtube: contentYoutube,
  content_reddit: contentReddit,
  content_x_article: contentXArticle,
  background,
  popup,
  retry,
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
  console.error(`\n${failures} extension error-truth check(s) failed.`);
  process.exit(1);
}
console.log("\nAll extension error-truth checks passed.");
