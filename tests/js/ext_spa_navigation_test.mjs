// E2 regression harness: the in-page buttons appear after in-site (History
// API) navigation on YouTube and X.
//
// The manifest now loads content.js on every YouTube page and
// content-x-article.js on every X page, so each script has to self-gate on
// the URL. Drives the REAL scripts in a fake browser (ext_fake_env.mjs):
//   youtube    -- content.js loaded on a non-video page stays inert (no
//                 button, no /health polling, DOM churn costs no URL parse);
//                 navigating to a video (yt-navigate-finish, or only the DOM
//                 observer as on m.youtube.com) builds a working button and
//                 starts polling; popstate back off it tears both down; a
//                 hidden tab's navigation doesn't restart polling
//   x_article  -- content-x-article.js loaded on the timeline stays inert;
//                 navigating into an article (DOM observer) builds a working
//                 button and starts polling; popstate back removes both; a
//                 pending popup Retry is still dropped by SPA navigation
//   background -- background.js captureXArticleFromTab: no receiver in the
//                 tab -> inject lib/x-article.js + content-x-article.js and
//                 ask exactly once more; any other outcome injects nothing
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/ext_spa_navigation_test.mjs [group ...]
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

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

const STATUS_POLL_MS = 10000;
const INJECT_RETRY_MS = 500;

// window / document event listeners the scripts register (the fake env's
// own addEventListener is a no-op), so the test can fire them.
function captureListeners(env) {
  const win = {};
  const doc = {};
  env.ctx.addEventListener = (type, fn) => { (win[type] ||= []).push(fn); };
  env.document.addEventListener = (type, fn) => { (doc[type] ||= []).push(fn); };
  return {
    fireWindow(type) { for (const fn of win[type] || []) fn({ type }); },
    fireDocument(type) { for (const fn of doc[type] || []) fn({ type }); },
  };
}

// Fire every pending setTimeout callback once (e.g. yt-navigate-finish's
// deferred injection), the way the page's event loop would.
function runTimeouts(env) {
  for (const [id, fn] of [...env.timeouts]) {
    if (!env.timeouts.has(id)) continue;
    env.timeouts.delete(id);
    fn();
  }
}

function timersOf(env, ms) {
  return [...env.intervalDelays.values()].filter((d) => d === ms).length;
}
function pings(env) {
  return env.sent.filter((m) => m && m.type === "stcPing").length;
}

// ---- content.js (YouTube) ---------------------------------------------------
const YT_BTN_ID = "stc-yt-send-to-claude";
const YT_ANCHOR = "ytd-watch-metadata #top-level-buttons-computed";
const VIDEO_ID = "abc123def45";

async function youtubeEnv(href) {
  const env = makeEnv({
    href,
    title: "Some video - YouTube",
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtract") return { data: { ok: true, queued: true } };
      return { ok: true };
    },
  });
  const events = captureListeners(env);
  env.load("lib/extract.js");
  env.load("lib/ui.js");
  // Count URL checks: content.js asks STC.normalizeYouTubeUrl for every one.
  const urlChecks = { n: 0 };
  const realNormalize = env.ctx.STC.normalizeYouTubeUrl;
  env.ctx.STC.normalizeYouTubeUrl = (raw) => { urlChecks.n++; return realNormalize(raw); };
  env.load("content.js");
  await settle();
  return { env, events, urlChecks };
}

// The desktop /watch action row the button anchors to.
function addWatchAnchor(env) {
  const anchor = env.document.createElement("div");
  env.document.body.appendChild(anchor);
  env.document._selectors[YT_ANCHOR] = anchor;
  return anchor;
}

async function youtube() {
  await scenario("E2 YouTube home stays inert", async () => {
    const { env, urlChecks } = await youtubeEnv("https://www.youtube.com/");
    check(!env.document.getElementById(YT_BTN_ID), "E2: no button on the YouTube home page");
    check(pings(env) === 0 && timersOf(env, STATUS_POLL_MS) === 0,
      "E2: no /health polling on a page that isn't a video", env.sent);
    check(timersOf(env, INJECT_RETRY_MS) === 0,
      "E2: no button-injection retry loop on a page that isn't a video",
      [...env.intervalDelays.values()]);
    urlChecks.n = 0;
    for (let i = 0; i < 5; i++) env.mutate();
    await settle();
    check(urlChecks.n === 0,
      "E2: DOM churn off a video page re-parses no URL (a string compare only)", urlChecks.n);
    check(!env.document.getElementById(YT_BTN_ID) && pings(env) === 0,
      "E2: DOM churn alone on the home page builds nothing and pings nothing", env.sent);
  });

  await scenario("E2 YouTube home -> watch via yt-navigate-finish", async () => {
    const { env, events } = await youtubeEnv("https://www.youtube.com/");
    const anchor = addWatchAnchor(env);
    // YouTube's router: pushState to the video, then yt-navigate-finish.
    env.ctx.location.href = `https://www.youtube.com/watch?v=${VIDEO_ID}`;
    events.fireWindow("yt-navigate-finish");
    check(pings(env) === 1 && timersOf(env, STATUS_POLL_MS) === 1,
      "E2: arriving on a video starts /health polling once", env.sent);
    runTimeouts(env);
    env.runIntervals();
    await settle();
    const btn = env.document.getElementById(YT_BTN_ID);
    check(!!btn && btn.parentElement === anchor,
      "E2: the in-page button appears in the action row after in-site navigation");
    check(!!btn && !btn.disabled && btn.classList.contains("uoink-status-online"),
      "E2: the button shows the live helper status", btn && [...btn.classList.names]);
    check(timersOf(env, INJECT_RETRY_MS) === 0,
      "E2: the injection retry loop stops once the button is in", [...env.intervalDelays.values()]);
    if (btn) btn.userClick();
    await settle();
    const sent = env.sent.filter((m) => m.type === "stcExtract");
    check(sent.length === 1 && sent[0].url === `https://www.youtube.com/watch?v=${VIDEO_ID}`,
      "E2: the button captures the video the tab navigated to", sent);

    // Another video: polling keeps its one timer.
    env.ctx.location.href = "https://www.youtube.com/watch?v=zzzzzzzzzzz";
    events.fireWindow("yt-navigate-finish");
    check(timersOf(env, STATUS_POLL_MS) === 1,
      "E2: video -> video keeps a single /health poller", [...env.intervalDelays.values()]);
  });

  await scenario("E2 m.youtube.com: DOM observer alone, then popstate back", async () => {
    const { env, events } = await youtubeEnv("https://m.youtube.com/");
    check(!env.document.getElementById(YT_BTN_ID) && pings(env) === 0,
      "E2: mobile home page: no button, no polling", env.sent);
    // No yt-navigate-finish here: only the page re-rendering sees the change.
    env.ctx.location.href = `https://m.youtube.com/watch?v=${VIDEO_ID}`;
    env.mutate();
    await settle();
    const btn = env.document.getElementById(YT_BTN_ID);
    check(!!btn && btn.parentElement === env.document.body
      && btn.classList.contains("stc-yt-shorts-floating"),
      "E2: the DOM observer notices the new URL and builds the floating button");
    check(pings(env) >= 1 && timersOf(env, STATUS_POLL_MS) === 1,
      "E2: and starts /health polling", env.sent);

    // Back button to the home page.
    env.ctx.location.href = "https://m.youtube.com/";
    events.fireWindow("popstate");
    check(!env.document.getElementById(YT_BTN_ID),
      "E2: popstate off the video removes the floating button");
    check(timersOf(env, STATUS_POLL_MS) === 0,
      "E2: and stops /health polling", [...env.intervalDelays.values()]);
    const before = pings(env);
    env.runIntervals();
    await settle();
    check(pings(env) === before, "E2: no further pings off the video", env.sent);

    // Forward again via popstate: back on the video.
    env.ctx.location.href = `https://m.youtube.com/shorts/${VIDEO_ID}`;
    events.fireWindow("popstate");
    runTimeouts(env);
    env.runIntervals();
    await settle();
    check(!!env.document.getElementById(YT_BTN_ID) && timersOf(env, STATUS_POLL_MS) === 1,
      "E2: popstate onto a Short brings the button and polling back", [...env.intervalDelays.values()]);
  });

  await scenario("E2 hidden tabs and visibility", async () => {
    const { env, events } = await youtubeEnv(`https://www.youtube.com/watch?v=${VIDEO_ID}`);
    check(timersOf(env, STATUS_POLL_MS) === 1, "a video page loads polling");
    env.document.hidden = true;
    events.fireDocument("visibilitychange");
    check(timersOf(env, STATUS_POLL_MS) === 0, "a hidden tab stops polling");
    // Autoplay moves a hidden tab to the next video.
    env.ctx.location.href = "https://www.youtube.com/watch?v=zzzzzzzzzzz";
    events.fireWindow("yt-navigate-finish");
    check(timersOf(env, STATUS_POLL_MS) === 0,
      "E2: in-site navigation in a hidden tab doesn't restart polling", [...env.intervalDelays.values()]);
    env.document.hidden = false;
    events.fireDocument("visibilitychange");
    check(timersOf(env, STATUS_POLL_MS) === 1, "showing the tab resumes polling");

    const home = await youtubeEnv("https://www.youtube.com/");
    home.env.document.hidden = true;
    home.events.fireDocument("visibilitychange");
    home.env.document.hidden = false;
    home.events.fireDocument("visibilitychange");
    check(pings(home.env) === 0 && timersOf(home.env, STATUS_POLL_MS) === 0,
      "E2: showing a non-video YouTube tab starts no polling", home.env.sent);
  });
}

// ---- content-x-article.js -----------------------------------------------------
const X_BTN_ID = "uoink-x-article-btn";
const ARTICLE_URL = "https://x.com/jack/article/1900000000001";
const ARTICLE = {
  ok: true, url: ARTICLE_URL, title: "An article", author: "jack",
  markdown: "Body text", images: [],
};

// parsed: the DOM parse result, or a function returning it (called per parse).
async function xArticleEnv(href, { parsed, local } = {}) {
  const env = makeEnv({
    href,
    title: "An article / X",
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtractXArticle") return { data: { ok: true } };
      return { ok: true };
    },
  });
  if (local) Object.assign(env.store.local, JSON.parse(JSON.stringify(local)));
  const events = captureListeners(env);
  env.load("lib/x-article.js");
  const real = env.ctx.XArticle;
  const parse = typeof parsed === "function" ? parsed : () => parsed || ARTICLE;
  // The real URL helpers; only the DOM parse is stubbed. URL checks counted.
  const urlChecks = { n: 0 };
  env.ctx.XArticle = Object.assign({}, real, {
    parseXArticle: () => parse(),
    isXArticleUrl: (raw) => { urlChecks.n++; return real.isXArticleUrl(raw); },
  });
  env.load("content-x-article.js");
  await settle();
  return { env, events, urlChecks };
}

async function xArticle() {
  await scenario("E2 X timeline stays inert", async () => {
    const { env, urlChecks } = await xArticleEnv("https://x.com/home");
    check(!env.document.getElementById(X_BTN_ID), "E2: no article button on the X timeline");
    check(pings(env) === 0 && timersOf(env, STATUS_POLL_MS) === 0,
      "E2: no /health polling on an X page that isn't an article", env.sent);
    urlChecks.n = 0;
    for (let i = 0; i < 5; i++) env.mutate();
    await settle();
    check(urlChecks.n === 0,
      "E2: timeline DOM churn re-parses no URL (a string compare only)", urlChecks.n);
    check(!env.document.getElementById(X_BTN_ID) && pings(env) === 0,
      "E2: DOM churn alone on the timeline builds nothing and pings nothing", env.sent);
  });

  await scenario("E2 X timeline -> article -> back", async () => {
    const { env, events } = await xArticleEnv("https://x.com/home");
    // X's router pushStates (no event); the observer sees the re-render.
    env.ctx.location.href = ARTICLE_URL;
    env.mutate();
    await settle();
    const btn = env.document.getElementById(X_BTN_ID);
    check(!!btn, "E2: the article button appears after in-site navigation");
    check(pings(env) >= 1 && timersOf(env, STATUS_POLL_MS) === 1,
      "E2: arriving on an article starts /health polling once", env.sent);
    check(!!btn && !btn.disabled && btn.classList.contains("uoink-status-online"),
      "E2: the article button shows the live helper status", btn && [...btn.classList.names]);
    if (btn) btn.userClick();
    await settle();
    const sent = env.sent.filter((m) => m.type === "stcExtractXArticle");
    check(sent.length === 1 && sent[0].article && sent[0].article.url === ARTICLE_URL,
      "E2: the button captures the article the tab navigated to", sent);

    env.mutate(); // more churn on the article: still one button, one poller
    check(env.document.body.childNodes.filter((c) => c.id === X_BTN_ID).length === 1
      && timersOf(env, STATUS_POLL_MS) === 1,
      "E2: churn on the article adds no second button or poller", [...env.intervalDelays.values()]);

    env.ctx.location.href = "https://x.com/home";
    events.fireWindow("popstate");
    check(!env.document.getElementById(X_BTN_ID),
      "E2: popstate back to the timeline removes the article button");
    check(timersOf(env, STATUS_POLL_MS) === 0,
      "E2: and stops /health polling", [...env.intervalDelays.values()]);
    const before = pings(env);
    env.runIntervals();
    await settle();
    check(pings(env) === before, "E2: no further pings off the article", env.sent);
  });

  await scenario("E2 a pending Retry is still dropped by SPA navigation", async () => {
    let rendered = false;
    const { env, events } = await xArticleEnv(ARTICLE_URL, {
      parsed: () => (rendered ? ARTICLE
        : { ok: false, code: "empty", error: "Couldn't find the article on this page." }),
      local: { auto_yoink: { url: ARTICLE_URL, failure_id: "f-article", ts: Date.now() } },
    });
    await settle();
    check(!("auto_yoink" in env.store.local), "the article page claims the Retry handoff",
      env.store.local.auto_yoink);
    env.ctx.location.href = "https://x.com/home";
    env.mutate();
    await settle();
    // Back to the article, which renders now.
    env.ctx.location.href = ARTICLE_URL;
    rendered = true;
    events.fireWindow("popstate");
    env.mutate();
    env.runIntervals();
    await settle();
    const touched = env.sent.filter((m) =>
      ["stcExtractXArticle", "forgetFailure", "rememberFailure"].includes(m.type));
    check(!touched.length,
      "E2: leaving the retried article drops the pending Retry; coming back never auto-captures",
      touched);
    check(!!env.document.getElementById(X_BTN_ID), "the button is back on the article");
  });
}

// ---- background.js captureXArticleFromTab -------------------------------------
const NO_RECEIVER = "Could not establish connection. Receiving end does not exist.";
const PORT_CLOSED = "The message port closed before a response was received.";
const TAB_ID = 7;

// tab: whether content-x-article.js listens in the tab, what an unanswered
// message reports, and whether chrome.scripting.executeScript works.
async function backgroundEnv({ listening = false, error = NO_RECEIVER,
  injectThrows = false, injectionListens = true } = {}) {
  const env = makeEnv({
    onSend: () => undefined,
    fetch: (url) => {
      const path = new URL(url).pathname;
      if (path === "/token") return jsonResponse({ token: "test-token" });
      if (path === "/health") return jsonResponse({ ok: true });
      if (path === "/queue/status") return jsonResponse({ ok: true, pending_count: 0 });
      if (path === "/extract/x-article") return jsonResponse({ ok: true, image_count: 0 });
      if (path === "/extract/page") return jsonResponse({ ok: false, code: "x_login_wall" });
      throw new TypeError("Failed to fetch");
    },
  });
  env.load("background.js");
  await settle();
  const tab = { listening, messages: [], injections: [] };
  env.chrome.tabs.sendMessage = (tabId, msg, cb) => {
    tab.messages.push({ tabId, msg: JSON.parse(JSON.stringify(msg)) });
    Promise.resolve().then(() => {
      if (tab.listening) {
        cb({ ok: true, article: ARTICLE });
        return;
      }
      env.chrome.runtime.lastError = { message: error };
      try { cb(undefined); } finally { env.chrome.runtime.lastError = undefined; }
    });
  };
  env.chrome.scripting = {
    executeScript: async (details) => {
      tab.injections.push(JSON.parse(JSON.stringify(details)));
      if (injectThrows) throw new Error("Cannot access contents of the page.");
      if (injectionListens) tab.listening = true;
      return [{ result: undefined }];
    },
  };
  return { env, tab };
}

function pathsFetched(env) {
  return env.fetches.map((u) => new URL(u).pathname);
}

async function background() {
  await scenario("E2 no receiver -> inject and ask once more", async () => {
    const { env, tab } = await backgroundEnv();
    await env.ctx.captureXArticleFromTab(TAB_ID, ARTICLE_URL);
    await settle();
    check(tab.injections.length === 1, "E2: the scripts are injected once", tab.injections);
    const inj = tab.injections[0] || {};
    check(inj.target && inj.target.tabId === TAB_ID
      && JSON.stringify(inj.files) === JSON.stringify(["lib/x-article.js", "content-x-article.js"]),
      "E2: lib/x-article.js then content-x-article.js go into the clicked tab", inj);
    check(tab.messages.length === 2
      && tab.messages.every((m) => m.tabId === TAB_ID && m.msg.type === "uoinkParseXArticle"),
      "E2: the parse is asked for again exactly once after injecting", tab.messages);
    const paths = pathsFetched(env);
    check(paths.includes("/extract/x-article") && !paths.includes("/extract/page"),
      "E2: the in-page parse is saved; no login-walled /extract/page fallback", paths);
    check(env.notifications.some((n) => /Saved the X Article/.test(n.message || "")),
      "E2: the user is told the article was saved", env.notifications);
  });

  await scenario("E2 receiver present -> no injection", async () => {
    const { env, tab } = await backgroundEnv({ listening: true });
    await env.ctx.captureXArticleFromTab(TAB_ID, ARTICLE_URL);
    await settle();
    check(tab.injections.length === 0 && tab.messages.length === 1,
      "E2: a tab whose content script answers is asked once and nothing is injected",
      [tab.injections, tab.messages]);
    check(pathsFetched(env).includes("/extract/x-article"), "the parse is saved");
  });

  await scenario("E2 another messaging error -> no injection", async () => {
    const { env, tab } = await backgroundEnv({ error: PORT_CLOSED });
    await env.ctx.captureXArticleFromTab(TAB_ID, ARTICLE_URL);
    await settle();
    check(tab.injections.length === 0 && tab.messages.length === 1,
      "E2: a listener that didn't answer is not a missing script: nothing injected",
      [tab.injections, tab.messages]);
    check(pathsFetched(env).includes("/extract/page"),
      "the existing /extract/page fallback still runs", pathsFetched(env));
  });

  await scenario("E2 injection fails -> fallback, no second ask", async () => {
    const { env, tab } = await backgroundEnv({ injectThrows: true });
    await env.ctx.captureXArticleFromTab(TAB_ID, ARTICLE_URL);
    await settle();
    check(tab.injections.length === 1 && tab.messages.length === 1,
      "E2: a failed injection is not followed by a second ask", [tab.injections, tab.messages]);
    check(pathsFetched(env).includes("/extract/page")
      && !pathsFetched(env).includes("/extract/x-article"),
      "E2: and the /extract/page fallback runs", pathsFetched(env));
  });

  await scenario("E2 still no receiver after injecting -> retried once only", async () => {
    const { env, tab } = await backgroundEnv({ injectionListens: false });
    await env.ctx.captureXArticleFromTab(TAB_ID, ARTICLE_URL);
    await settle();
    check(tab.injections.length === 1 && tab.messages.length === 2,
      "E2: one injection, one retry, no loop", [tab.injections, tab.messages]);
    check(pathsFetched(env).includes("/extract/page"),
      "E2: then the /extract/page fallback runs", pathsFetched(env));
  });
}

const GROUPS = {
  youtube,
  x_article: xArticle,
  background,
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
  console.error(`\n${failures} extension SPA-navigation check(s) failed.`);
  process.exit(1);
}
console.log("\nAll extension SPA-navigation checks passed.");
