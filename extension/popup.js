"use strict";
const POPUP_CAPTURE_RESULTS_KEY = "popup_capture_results";
let serverOnline = false;
const RECENT_FAILURES_KEY = "yoink_recent_failures";
const currentSourcePreview = document.getElementById("current-source-preview");
const uoinkCurrentBtn = document.getElementById("uoink-current-btn");
const uoinkAllowRetryBtn = document.getElementById("uoink-allow-retry-btn");
const uoinkPodcastBtn = document.getElementById("uoink-podcast-btn");
const currentSourceNote = document.getElementById("current-source-note");
const currentSourceAlert = document.getElementById("current-source-alert");
const currentSourceAlertText = document.getElementById("current-source-alert-text");
let currentSource = null;
let pendingAllowHost = null;
let pendingAllowCapture = null;
let pendingPodcastFeed = null;
const captureData = { worker: {}, jobs: [], live: [], pending: [], recent: [], failures: [] };
let closed = false;
let queueRead = 0;
let helperRead = 0;
let recentRead = 0;
let jobsRevision = 0;
let pasteBusy = false;
const rowElements = new Map();
const rowModels = new Map();
const rowActions = new Map();

function showToast(message) {
  // Persistent inline feedback; queued captures do not trigger a toast.
  document.getElementById("popup-toast").textContent = String(message || "").replace(/★/g, "").trim();
}
function showSourceAlert(message) {
  currentSourceAlertText.textContent = message;
  currentSourceAlert.classList.remove("hidden");
}
function clearSourceAlert() {
  currentSourceAlertText.textContent = "";
  currentSourceAlert.classList.add("hidden");
}
document.getElementById("current-source-alert-dismiss").addEventListener("click", clearSourceAlert);
const SOURCE_BUTTON_LABELS = Object.fromEntries(
  Object.entries(STC.CAPTURE_SOURCES).map(([source, { label }]) => [source, `Uoink this ${label}`])
);

function setSourceNote(text) {
  if (!currentSourceNote) return;
  if (text) {
    currentSourceNote.textContent = text;
    currentSourceNote.classList.remove("hidden");
  } else {
    currentSourceNote.textContent = "";
    currentSourceNote.classList.add("hidden");
  }
}

// Read the page's RSS/Atom feed link via activeTab + chrome.scripting. This
// is the ONLY source that can't be classified from the tab URL alone -- the
// feed URL lives in <link rel="alternate" type="application/rss+xml">.
async function sniffPodcastFeed(tab) {
  if (!tab || !tab.id) return null;
  if (!chrome.scripting || !chrome.scripting.executeScript) return null;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const sel = 'link[rel="alternate"][type*="rss"], '
          + 'link[rel="alternate"][type*="atom"], '
          + 'link[type="application/rss+xml"], '
          + 'link[type="application/atom+xml"]';
        const links = Array.from(document.querySelectorAll(sel));
        for (const l of links) {
          if (l.href) return l.href;
        }
        return null;
      },
    });
    const hit = results && results.find((r) => r && r.result);
    return hit ? hit.result : null;
  } catch {
    return null;
  }
}

// A1: probe the live tab DOM for a rendered X Article body. This is what lets
// the popup recognise an article even when the URL is its announcing /status/
// tweet, a t.co redirect, or an SPA route the address bar hasn't settled — the
// URL lies, the DOM doesn't. Selectors mirror XArticle.BODY_SELECTORS (kept in
// sync there); this runs in the page world via activeTab + scripting, so it
// can't reference the extension's globals.
async function probeXArticleDom(tab) {
  if (!tab || !tab.id) return false;
  if (!chrome.scripting || !chrome.scripting.executeScript) return false;
  const host = (() => {
    try { return new URL(tab.url || "").hostname.toLowerCase(); }
    catch { return ""; }
  })();
  const X_HOSTS = new Set([
    "x.com", "www.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
  ]);
  if (!X_HOSTS.has(host)) return false;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const sel = [
          '[data-testid="twitterArticleRichTextComponent"]',
          '[data-testid="longformRichTextComponent"]',
          '[data-testid="ArticleBody"]',
          '[data-testid="articleBody"]',
          '[data-testid="longform-article"]',
        ];
        return sel.some((s) => !!document.querySelector(s));
      },
    });
    const hit = results && results.find((r) => r && r.result);
    return !!hit;
  } catch {
    return false;
  }
}

// Classify the active tab client-side and drive the one adaptive primary
// button (plus the X-text / podcast / allow-retry secondaries). Replaces
// the YouTube-only preview and its "Open a YouTube video tab" dead end.
async function detectCurrentSource() {
  if (!currentSourcePreview || !uoinkCurrentBtn) return;
  // Reset the secondaries; each detect pass re-decides which apply.
  if (uoinkAllowRetryBtn) uoinkAllowRetryBtn.classList.add("hidden");
  if (uoinkPodcastBtn) uoinkPodcastBtn.classList.add("hidden");
  clearSourceAlert();
  pendingAllowHost = null;
  pendingAllowCapture = null;
  pendingPodcastFeed = null;
  setSourceNote("");
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    const url = (tab && tab.url) || "";
    // A1: let a live-DOM article signal win over URL-shape guessing so an
    // actual article never silently degrades to "Uoink this page".
    const hasArticleDom = await probeXArticleDom(tab);
    const cls = STC.resolveTabSource(url, { hasArticleDom });
    if (!cls || !cls.ok) {
      currentSource = null;
      currentSourcePreview.textContent =
        "This page isn't supported. Paste a link below.";
      uoinkCurrentBtn.textContent = "Nothing to uoink here";
      uoinkCurrentBtn.disabled = true;
      return;
    }
    // A generic web page may actually be a podcast page. Don't relabel the
    // primary (a news article with an RSS feed isn't "a podcast") -- offer
    // the feed as a secondary "Add this podcast feed" button instead.
    if (cls.source === "web_page") {
      const feed = await sniffPodcastFeed(tab);
      if (feed && uoinkPodcastBtn) {
        pendingPodcastFeed = feed;
        uoinkPodcastBtn.classList.remove("hidden");
        uoinkPodcastBtn.disabled = !serverOnline;
      }
    }
    currentSource = cls;
    const title = (tab.title || "").replace(/\s+-\s+YouTube\s*$/i, "").trim();
    // E1: the SW queue shows (and records a failure) under the tab title.
    currentSource.title = title;
    currentSourcePreview.textContent = title || cls.canonical;
    uoinkCurrentBtn.textContent =
      SOURCE_BUTTON_LABELS[cls.source] || "Uoink this tab";
    uoinkCurrentBtn.disabled = !serverOnline;
    setSourceNote("");
    document.getElementById("current-source-origin").textContent = sourceLabel(cls.canonical);
    loadTabThumbnail(tab, cls);
    // Queue storage can resolve before tab detection when the popup reopens.
    applyCaptureQueueState(captureData.worker);
  } catch {
    currentSource = null;
    currentSourcePreview.textContent = "Couldn't read the current tab.";
    uoinkCurrentBtn.textContent = "Uoink this tab";
    uoinkCurrentBtn.disabled = true;
  }
}

async function captureXPost(url, interval) {
  const textData = await STC.postExtractX(url);
  // Flag off, or a video-only post with no text worth saving -> video path.
  if (!textData || textData.code === "disabled" || textData.code === "empty") {
    await queueCapture({ route: "video", url, interval });
    return;
  }
  // X refused the fetch (404 / 429 / tombstone / block page). The server's
  // copy already says which; show it and stop -- no queue, no broken uoink.
  if (!textData.ok) {
    showToast(STC.describeFailure(textData)
      || "X wouldn't hand over this post. Try again in a minute.");
    return;
  }
  const count = Number(textData.tweets_captured) || 1;
  const posts = `${count} post${count === 1 ? "" : "s"}`;
  const hasVideo = Boolean(textData.metadata && textData.metadata.has_video);
  if (hasVideo) {
    // saveOnly: as before, the video half isn't copied or opened in Claude.
    // E3/E7: if it fails, the SW notifies and records the real reason, and
    // this popup (while still open) shows it after the prefix. L-2: a full
    // queue says the video wasn't queued instead of hiding the dropped video.
    const handed = await handOffCapture(
      { route: "video", url, interval, saveOnly: true },
      {
        failurePrefix: `Saved ${posts}. Video: `,
        queueFullMessage: `Saved ${posts}. Video not queued -- the queue is full. `
          + `Try the video again in a few minutes.`,
      });
    if (handed.ok) {
      showToast(`Saved ${posts} + queued the video.`);
    } else {
      showToast(`Saved ${posts}. Video: ${handed.message}`);
    }
    loadRecentUoinks();
    return;
  }
  showToast(`Saved ${posts} to your library.`);
  loadRecentUoinks();
}

// V-2c: capture an X ARTICLE (long-form). PRIMARY path asks the in-page
// content script (content-x-article.js) to parse the rendered Article out of
// the user's authenticated DOM, then POSTs the parsed {url,title,author,
// markdown,images} to /extract/x-article. FALLBACK: if the content script
// isn't present (SPA nav / not injected) or the parse comes back thin, try
// the best-effort /extract/page path — which fails honestly when X
// login-walls a logged-out fetch instead of saving junk.
function messageActiveTab(tabId, payload) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, payload, (resp) => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    } catch { resolve(null); }
  });
}

async function captureXArticle(url) {
  let tab = null;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    tab = tabs && tabs[0];
  } catch { tab = null; }

  // 1) PRIMARY — content-script DOM parse.
  let parsed = null;
  if (tab && tab.id) {
    const resp = await messageActiveTab(tab.id, { type: "uoinkParseXArticle" });
    if (resp && resp.ok && resp.article && resp.article.ok) {
      parsed = resp.article;
    }
  }
  if (parsed) {
    const data = await STC.postExtractXArticle(parsed);
    if (data && data.ok) {
      const imgs = Number(data.image_count
        || (parsed.images && parsed.images.length)) || 0;
      const extra = imgs ? ` (${imgs} image${imgs === 1 ? "" : "s"})` : "";
      showToast(`Saved the article${extra} to your library.`);
      loadRecentUoinks();
      return;
    }
    showToast(STC.describeFailure(data)
      || "Read the article but couldn't save it. Try again.");
    return;
  }

  // 2) FALLBACK — best-effort /extract/page. E1: the SW queue runs it
  // (STC.postExtractPage there) so closing the popup can't kill it; the SW
  // copies, opens Claude, or notifies honestly on a login wall, and this
  // popup, if still open, shows the outcome via showXArticleFallbackResult.
  await queueCapture({ route: "page", url }, { xArticle: true });
}

// The X Article fallback's outcome in a popup that's still open (called by
// showCaptureResult). An allowlist wall gets the generic "Allow this site and
// retry"; a success, or a request the SW stopped waiting on (result.kind:
// timeout / lost / offline), the generic toast, as before. Returns true if it
// showed something.
function showXArticleFallbackResult(result) {
  // A2: X login wall (or any failure to serve the article to a pasted link) is
  // honest and actionable, not a generic failure. Surface it as a PERSISTENT
  // alert (not a 1.8s toast) that names what happened and what to do, so the
  // user never reads a walled capture as a silent no-op.
  if (result.code === "x_login_wall") {
    showSourceAlert("X blocks logged-out link fetches, so Uoink can't read "
      + "this article from a pasted link. Click the \"Uoink this article\" "
      + "button on the page (bottom-right) to save it from your logged-in "
      + "session. Nothing was saved.");
    return true;
  }
  if (!result.ok && !result.kind) {
    showSourceAlert(result.message
      || "X didn't serve this article to Uoink. Open the article and click "
        + "the in-page \"Uoink this article\" button while you're logged in. "
        + "Nothing was saved.");
    return true;
  }
  return false;
}

// ---- Capture request hand-off ----
const popupCaptureHandoffs = new Map();
let currentSourceQueued = false;
let currentCaptureBusy = false;
const pendingCaptureRequests = new Set();
// The SW queue route each source's capture runs as (STC.queueJobRoute); only
// that capture of this tab holds the button.
const SOURCE_CAPTURE_ROUTES = {
  video: ["video"], x_video: ["x_post", "video"], reddit: ["reddit"], page: ["page"], x_article: ["page"],
  playlist: ["playlist"], podcast: ["podcast"],
};

function capturesCurrentSource(url, route) {
  return !!currentSource && STC.queueUrlKey(url) === STC.queueUrlKey(currentSource.canonical)
    && !!SOURCE_CAPTURE_ROUTES[currentSource.action]?.includes(route);
}

async function handOffCapture(request, view) {
  const job = Object.assign({
    title: (currentSource && currentSource.title) || "",
  }, request);
  let res = null;
  pendingCaptureRequests.add(job);
  applyCaptureQueueState(captureData.worker || {});
  try {
    res = await chrome.runtime.sendMessage({ type: "popupCapture", job });
  } catch (e) {
    console.warn("[popup] capture hand-off failed", e);
  } finally {
    // Keep the button held until persisted queue state replaces this request.
    await refreshQueue();
    pendingCaptureRequests.delete(job);
    applyCaptureQueueState(captureData.worker || {});
  }
  if (!res || !res.ok) {
    return {
      ok: false,
      message: (res && res.error) || "Uoink couldn't start this capture. Try again.",
    };
  }
  // The request rides along so an allowlist wall can rerun this capture.
  if (res.id) popupCaptureHandoffs.set(res.id, Object.assign({ request: job }, view));
  return { ok: true, duplicate: !!res.duplicate, ahead: Number(res.ahead) || 0 };
}

async function queueCapture(request, view) {
  const handed = await handOffCapture(request, view);
  if (!handed.ok) {
    showToast(handed.message);
  } else if (handed.duplicate) {
    showToast("Already uoinking this one. You can close this popup.");
  } else if (handed.ahead) {
    showToast(`Queued behind ${handed.ahead} other uoink${handed.ahead === 1 ? "" : "s"}. `
      + "You can close this popup.");
  } else {
    showToast("Uoinking in the background. You can close this popup.");
  }
  return handed.ok;
}

// Called by refreshQueue() with the SW queue state. The primary button reads
// "Uoinking..." while this tab's source is queued or running; a capture this
// popup handed off shows its outcome once (the SW already notified).
function applyCaptureQueueState(s) {
  if (uoinkCurrentBtn && currentSource) {
    // A capture running longer than the request timeout was left behind by
    // a service worker Chrome stopped mid-job; it doesn't hold the button.
    const current = s.busy && s.current
      && Date.now() - (Number(s.current.startedAt) || 0) < STC.REQUEST_TIMEOUT_MS
      ? s.current
      : null;
    // Same URL (#fragment aside, as the SW matches it) and the capture this
    // button runs: a session add or another route for the same URL is a
    // different job.
    const jobs = [current].concat(s.queue || []);
    const queued = jobs.some((job) => job && capturesCurrentSource(job.url, STC.queueJobRoute(job)))
      || [...pendingCaptureRequests].some(job => capturesCurrentSource(job.url, job.route));
    if (queued) {
      uoinkCurrentBtn.textContent = "Uoinking...";
      uoinkCurrentBtn.disabled = true;
    } else if (currentSourceQueued) {
      uoinkCurrentBtn.textContent =
        SOURCE_BUTTON_LABELS[currentSource.source] || "Uoink this page";
      uoinkCurrentBtn.disabled = !serverOnline || currentCaptureBusy;
    }
    currentSourceQueued = queued;
  }
  const results = Array.isArray(s[POPUP_CAPTURE_RESULTS_KEY])
    ? s[POPUP_CAPTURE_RESULTS_KEY]
    : [];
  // Stored newest first; show them in the order they finished.
  for (const result of results.slice().reverse()) {
    const view = result && popupCaptureHandoffs.get(result.id);
    if (!view) continue;
    popupCaptureHandoffs.delete(result.id);
    showCaptureResult(result, view);
  }
}

function showCaptureResult(result, view) {
  // Keep the saved-post outcome while reporting the separate video's result.
  if (result.followUp?.id) {
    popupCaptureHandoffs.set(result.followUp.id, {
      ...result.followUp, request: { route: "video", url: result.url, saveOnly: true },
    });
  }
  // Allowlist wall: the one-click "Allow this site and retry" button.
  if (result.code === "host_not_allowed") {
    offerAllowRetry(result.url, view.request);
    return;
  }
  if (result.code === "queue_full") {
    showToast(view.queueFullMessage || result.message);
    pollQueueStatus();
    return;
  }
  if (view.xArticle && showXArticleFallbackResult(result)) return;
  if (!result.ok) {
    showToast(`${view.failurePrefix || ""}${result.message}`);
    // The SW added (or replaced) a Recent failures row for it.
    loadRecentUoinks();
    return;
  }
  showToast(view.successMessage || result.message);
  if (result.queued) pollQueueStatus();
  loadRecentUoinks();
}

async function runPopupUoinkCurrent() {
  if (!uoinkCurrentBtn || !currentSource || currentCaptureBusy) return;
  currentCaptureBusy = true;
  const src = currentSource;
  const old = uoinkCurrentBtn.textContent;
  uoinkCurrentBtn.disabled = true;
  uoinkCurrentBtn.textContent = "Uoinking...";
  try {
    const interval = await STC.getInterval();

    // Preview can take minutes. The worker owns it after this popup closes.
    if (src.action === "playlist") {
      await queueCapture({ route: "playlist", url: src.canonical, interval });
      return;
    }

    // Podcast feed: subscribe to metadata watch mode. Audio stays opt-in.
    if (src.action === "podcast") {
      await queueCapture({ route: "podcast", url: src.canonical, interval }, {
        successMessage: "Podcast feed saved. Uoink will watch metadata; audio stays off.",
      });
      return;
    }

    // Article / web page: allowlist-gated. Runs in the SW queue (E1); on
    // host_not_allowed, showCaptureResult surfaces the one-click "Allow this
    // site and retry" button instead of a dead error.
    if (src.action === "page") {
      await queueCapture({ route: "page", url: src.canonical, interval });
      return;
    }

    // YouTube video: corpus-returning capture. /extract queues, so the SW
    // queue checks the helper's queue for room before it runs (E1); this
    // popup doesn't wait on /queue/status before handing it over.
    if (src.action === "video") {
      await queueCapture({ route: "video", url: src.canonical, interval });
      return;
    }
    // The worker owns the text and optional video, including deduplication
    // against pasted links, after this popup closes.
    if (src.action === "x_video") {
      await queueCapture({ route: "x_post", url: src.canonical, interval });
      return;
    }
    // X article: content-script DOM parse first, /extract/page as fallback.
    if (src.action === "x_article") {
      await captureXArticle(src.canonical);
      return;
    }
    if (src.action === "reddit") {
      await queueCapture({ route: "reddit", url: src.canonical, interval });
      return;
    }
  } catch (e) {
    // E7: timed out / lost track / offline (only when /health fails too).
    const failure = await STC.describeCaptureError(e);
    showToast(failure.message);
  } finally {
    currentCaptureBusy = false;
    uoinkCurrentBtn.disabled = !serverOnline || !currentSource;
    uoinkCurrentBtn.textContent = SOURCE_BUTTON_LABELS[src.source] || old;
    applyCaptureQueueState(captureData.worker || {});
    // E1: back to "Uoinking..." while the SW queue still has this source.
    refreshQueue();
  }
}

// Reveal the "Allow this site and retry" affordance for a page that hit the
// allowlist wall. Stashes the host so the click handler can grant + re-fire.
// E1: request is the walled capture as handed to the SW queue; its URL,
// title and Recent failures record (retryOf) are what gets re-fired, since a
// Retry's page needn't be this tab's.
function offerAllowRetry(pageUrl, request) {
  try {
    pendingAllowHost = new URL(pageUrl).hostname;
  } catch {
    pendingAllowHost = null;
  }
  pendingAllowCapture = null;
  if (!pendingAllowHost) {
    showToast("That page's site can't be allowed automatically.");
    return;
  }
  pendingAllowCapture = { url: pageUrl, title: (request && request.title) || "" };
  if (request && request.retryOf) pendingAllowCapture.retryOf = request.retryOf;
  setSourceNote(`Uoink hasn't been allowed on ${pendingAllowHost} yet.`);
  if (uoinkAllowRetryBtn) {
    uoinkAllowRetryBtn.classList.remove("hidden");
    uoinkAllowRetryBtn.disabled = !serverOnline;
  }
}

async function runAllowSiteAndRetry() {
  if (!uoinkAllowRetryBtn || !pendingAllowHost) return;
  // The capture that hit the wall (offerAllowRetry), else this tab's page.
  const capture = pendingAllowCapture
    || (currentSource && { url: currentSource.canonical });
  if (!capture) return;
  const host = pendingAllowHost;
  const old = uoinkAllowRetryBtn.textContent;
  uoinkAllowRetryBtn.disabled = true;
  uoinkAllowRetryBtn.textContent = "Allowing...";
  try {
    const allow = await STC.addAllowedSite(host);
    if (!allow || !allow.ok) {
      showToast(STC.friendlyError(allow && allow.error) || "Couldn't allow that site.");
      return;
    }
    uoinkAllowRetryBtn.classList.add("hidden");
    setSourceNote("");
    pendingAllowHost = null;
    pendingAllowCapture = null;
    // E1: the capture itself runs in the SW queue; a second allowlist wall
    // comes back through showCaptureResult and re-offers this button.
    await queueCapture(Object.assign({ route: "page" }, capture));
  } catch (e) {
    // E7: timed out / lost track / offline, same as the main capture button.
    const failure = await STC.describeCaptureError(e);
    showToast(failure.message);
  } finally {
    uoinkAllowRetryBtn.textContent = old;
    if (!uoinkAllowRetryBtn.classList.contains("hidden")) {
      uoinkAllowRetryBtn.disabled = !serverOnline;
    }
  }
}

async function runAddPodcastFeed() {
  if (!uoinkPodcastBtn || !pendingPodcastFeed || uoinkPodcastBtn.disabled) return;
  const feed = pendingPodcastFeed;
  const old = uoinkPodcastBtn.textContent;
  uoinkPodcastBtn.disabled = true;
  uoinkPodcastBtn.textContent = "Adding...";
  try {
    if (await queueCapture({ route: "podcast", url: feed }, {
      successMessage: "Podcast feed saved. Uoink will watch metadata; audio stays off.",
    })) uoinkPodcastBtn.classList.add("hidden");
  } catch (e) {
    showToast(`Couldn't add feed: ${e && e.message || e}`);
  } finally {
    uoinkPodcastBtn.textContent = old;
    if (!uoinkPodcastBtn.classList.contains("hidden")) {
      uoinkPodcastBtn.disabled = !serverOnline;
    }
  }
}

if (uoinkCurrentBtn) {
  uoinkCurrentBtn.addEventListener("click", runPopupUoinkCurrent);
}
if (uoinkAllowRetryBtn) {
  uoinkAllowRetryBtn.addEventListener("click", runAllowSiteAndRetry);
}
if (uoinkPodcastBtn) {
  uoinkPodcastBtn.addEventListener("click", runAddPodcastFeed);
}

async function writeClipboardText(text) {
  try {
    await navigator.clipboard.writeText(text);
    STC.logEngagement("paste", "popup", { length: text.length }).catch(() => {});
    return true;
  } catch {
    try {
      const r = await chrome.runtime.sendMessage({ type: "copyToClipboard", text });
      const ok = !!(r && r.ok);
      if (ok) {
        STC.logEngagement("paste", "popup", { length: text.length }).catch(() => {});
      }
      return ok;
    } catch {
      return false;
    }
  }
}

function loadRecentFailures() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get({ [RECENT_FAILURES_KEY]: [] }, (items) => {
        const failures = Array.isArray(items && items[RECENT_FAILURES_KEY])
          ? items[RECENT_FAILURES_KEY]
          : [];
        resolve(failures.slice(0, 5));
      });
    } catch { resolve([]); }
  });
}

function saveRecentFailures(failures) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.set({ [RECENT_FAILURES_KEY]: failures.slice(0, 5) }, resolve);
    } catch { resolve(); }
  });
}

async function removeRecentFailure(id) {
  const failures = await loadRecentFailures();
  await saveRecentFailures(failures.filter((f) => f.id !== id));
  await loadRecentUoinks();
}

function renderFailureRow(failure) {
  const row = document.createElement("div");
  row.className = "recent-failure";
  row.title = failure.error || "";

  const title = document.createElement("div");
  title.className = "recent-failure-title";
  title.textContent = `Failed: ${failure.title || failure.videoId || "YouTube video"}`;

  const error = document.createElement("div");
  error.className = "recent-failure-error";
  error.textContent = failure.error || "Uoink failed.";

  const actions = document.createElement("div");
  actions.className = "recent-failure-actions";

  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "Retry now";
  retry.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    const isReddit = failure.url && STC.normalizeRedditUrl(failure.url);
    const isTwitter = failure.url && STC.normalizeTwitterUrl(failure.url);
    // E6: the X Article button now records failures too.
    const isXArticle = failure.url && STC.isXArticleUrl(failure.url);
    const videoId = failure.videoId || (failure.url && STC.extractVideoId(failure.url));
    // E1: a capture the SW queue ran and recorded (its record has a route: a
    // web page, a Reddit thread, a YouTube or X post's video, a short) reruns
    // in that queue, so a Retry of one that's already queued or running
    // joins it instead of a content-script tab starting a second capture.
    // The record stays until the rerun goes through; a new failure replaces
    // it. Records the in-page buttons wrote have no route and go below, and
    // so does an X Article whatever wrote it: the queue only has the helper's
    // logged-out /extract/page fetch, which X walls, while the handoff below
    // opens the article for content-x-article.js's logged-in DOM capture.
    if (!isXArticle && ["video", "reddit", "page", "playlist", "podcast", "x_post"].includes(failure.route)) {
      await queueCapture({
        route: failure.route,
        url: failure.url,
        title: failure.title || "",
        saveOnly: !!failure.saveOnly,
        retryOf: failure.id,
      });
      return;
    }
    if (!videoId && !isReddit && !isTwitter && !isXArticle) {
      showToast("Can't retry: the URL is missing or invalid.");
      return;
    }
    // The page's content script claims this handoff and starts the capture;
    // the record stays until that capture goes through (or is replaced by
    // its new failure), so a Retry that never starts loses nothing.
    const autoYoinkObj = videoId
      ? { videoId, failure_id: failure.id, ts: Date.now() }
      : { url: failure.url, failure_id: failure.id, ts: Date.now() };
    chrome.storage.local.set({ auto_yoink: autoYoinkObj }, () => {
      chrome.tabs.create({
        url: failure.url || (videoId ? `https://www.youtube.com/watch?v=${videoId}` : ""),
        active: true,
      });
      window.close();
    });
  });

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.textContent = "Dismiss";
  dismiss.addEventListener("click", (ev) => {
    ev.stopPropagation();
    removeRecentFailure(failure.id);
  });

  actions.appendChild(retry);
  actions.appendChild(dismiss);
  row.appendChild(title);
  row.appendChild(error);
  row.appendChild(actions);
  return row;
}


// ---- Captures list ----
function sourceLabel(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return ""; }
}
async function loadTabThumbnail(tab, source) {
  const image = document.getElementById("current-source-thumbnail");
  image.hidden = true;
  let src = "";
  const id = STC.extractVideoId(source.canonical);
  if (id) src = `https://i.ytimg.com/vi/${encodeURIComponent(id)}/mqdefault.jpg`;
  else if (tab?.id && chrome.scripting?.executeScript) {
    try {
      const rows = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
        const meta = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
        try { return meta?.content ? new URL(meta.content, location.href).href : ""; } catch (_) { return ""; }
      }});
      src = rows?.find(row => row.result)?.result || "";
    } catch (_) { /* neutral thumbnail for restricted pages */ }
  }
  if (currentSource !== source || !/^https?:\/\//i.test(src)) return;
  image.referrerPolicy = "no-referrer";
  image.onload = () => { image.hidden = false; };
  image.onerror = () => { image.hidden = true; };
  image.src = src;
}

async function refreshQueue() {
  const request = ++queueRead;
  try {
    const s = await chrome.storage.session.get({ busy: false, current: null, queue: [], [POPUP_CAPTURE_RESULTS_KEY]: [] });
    if (closed || request !== queueRead) return;
    captureData.worker = s;
    applyCaptureQueueState(s);
    renderCaptures();
  } catch (_) { /* retain the last queue during worker restart */ }
}

async function loadRecentUoinks() {
  const request = ++recentRead;
  const failures = await loadRecentFailures();
  let recent = null;
  try {
    const data = await STC.listRecent();
    if (data?.ok !== false && Array.isArray(data?.recent)) recent = data.recent;
  } catch (_) { /* retain saved captures while offline */ }
  if (closed || request !== recentRead) return;
  captureData.failures = failures;
  if (recent) captureData.recent = recent;
  renderCaptures();
}

async function pollQueueStatus() {
  if (closed || document.hidden || !serverOnline) return;
  const request = ++helperRead;
  const revision = jobsRevision;
  const results = await Promise.allSettled([
    UoinkUI.authedJson("/queue/status"), STC.jobsList(),
  ]);
  if (closed || request !== helperRead) return;
  const queue = results[0].status === "fulfilled" && results[0].value;
  const jobs = results[1].status === "fulfilled" && results[1].value;
  if (queue && queue.ok !== false && Array.isArray(queue.pending)) captureData.pending = queue.pending;
  if (jobs && jobs.ok !== false) {
    if (Array.isArray(jobs.live_captures)) captureData.live = jobs.live_captures;
    // An older GET cannot rewind a newer stream event.
    if (revision === jobsRevision && Array.isArray(jobs.jobs)) captureData.jobs = jobs.jobs;
  }
  renderCaptures();
}

function handleSseEvent(event, data) {
  if (event === "snapshot") {
    jobsRevision++;
    captureData.jobs = [...(data.active || []), ...(data.recent || [])];
    loadRecentUoinks();
    pollQueueStatus();
  } else if (event === "job" && data.id) {
    jobsRevision++;
    captureData.jobs = [data, ...captureData.jobs.filter(row => row.id !== data.id)].slice(0, 30);
    if (["completed", "failed", "cancelled"].includes(data.state)) { loadRecentUoinks(); pollQueueStatus(); }
  } else if (event === "queue") pollQueueStatus();
  renderCaptures();
}
const captureStream = PopupCaptures.stream({
  connect: async signal => (await UoinkUI.authedFetch("/jobs/stream", { signal })).res,
  onEvent: handleSseEvent,
  onState: state => {
    document.getElementById("capture-sync").textContent = state === "live" ? "" : "Reconnecting. Showing the last known status.";
  },
});

function popupOfflineHint() {
  const os = String(navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "").toLowerCase();
  if (/mac|darwin|linux|cros|chrome os/.test(os)) {
    return "Uoink ships for Windows only. If you ran it from source, start python server.py again in Terminal.";
  }
  return "Start Uoink from the Start menu, then try again.";
}
async function ping() {
  let health = null;
  try { health = await STC.ping(); } catch (_) {}
  if (closed) return;
  const wasOnline = serverOnline;
  serverOnline = !!health?.ok;
  document.getElementById("status").textContent = serverOnline ? "Running" : "Offline";
  document.getElementById("dot").className = `status-dot ${serverOnline ? "running" : "offline"}`;
  document.getElementById("status-help").textContent = serverOnline ? "" : popupOfflineHint();
  uoinkCurrentBtn.disabled = !serverOnline || !currentSource || currentSourceQueued || currentCaptureBusy;
  uoinkAllowRetryBtn.disabled = !serverOnline;
  uoinkPodcastBtn.disabled = !serverOnline;
  document.getElementById("paste-add").disabled = !serverOnline || pasteBusy;
  if (serverOnline && !document.hidden) {
    captureStream.start();
    if (!wasOnline) { pollQueueStatus(); loadRecentUoinks(); }
  } else captureStream.stop();
}

async function submitPaste(event) {
  event.preventDefault();
  const input = document.getElementById("paste-url");
  const button = document.getElementById("paste-add");
  const error = document.getElementById("paste-error");
  if (button.disabled || pasteBusy) return;
  error.textContent = "";
  input.removeAttribute("aria-invalid");
  const raw = input.value.trim();
  const url = STC.normalizeAnyUrl(raw);
  if (!url || !/^https?:\/\//i.test(raw)) {
    error.textContent = "Paste a full http or https link.";
    input.setAttribute("aria-invalid", "true"); input.focus(); return;
  }
  pasteBusy = true; button.disabled = true;
  try {
    const source = STC.classifyCaptureUrl(url);
    const route = source.action === "x_article" ? "page"
      : source.action === "x_video" ? "x_post" : source.action;
    const request = { route, url: source.canonical, title: sourceLabel(url) };
    const accepted = await handOffCapture(request, { xArticle: source.action === "x_article" });
    if (!accepted.ok) throw new Error(accepted.message);
    if (input.value.trim() === raw) input.value = "";
    showToast("Capture added. You can close this popup.");
    await refreshQueue();
  } catch (err) { error.textContent = err.message || "Couldn't add this link. Try again."; }
  finally { pasteBusy = false; button.disabled = !serverOnline; }
}

function element(tag, className, text) {
  const el = document.createElement(tag);
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function makeCaptureRow() {
  const row = element("li", "capture-row");
  const title = element("h3", "capture-title");
  const source = element("p", "capture-source");
  const strip = element("span", "step-strip"); strip.setAttribute("aria-hidden", "true");
  const segments = PopupCaptures.STEPS.map(() => { const s = element("i", "step"); strip.appendChild(s); return s; });
  const state = element("p", "capture-state");
  const error = element("p", "capture-error");
  const actions = element("div", "capture-actions");
  row.append(title, source, strip, state, error, actions);
  return { row, title, source, strip, segments, state, error, actions, signature: "", index: -1 };
}
function renderCaptures() {
  const list = document.getElementById("captures-list");
  const rows = PopupCaptures.merge(captureData);
  const keys = new Set(rows.map(row => row.key));
  for (const [key, view] of rowElements) {
    if (!keys.has(key)) { view.row.remove(); rowElements.delete(key); rowModels.delete(key); }
  }
  const empty = list.querySelector(".empty-state");
  if (rows.length && empty) empty.remove();
  if (!rows.length && !empty) list.appendChild(element("li", "empty-state", "No captures yet."));
  document.getElementById("capture-count").textContent = rows.length ? `${rows.length} recent` : "";
  rows.forEach((row, position) => {
    rowModels.set(row.key, row);
    let view = rowElements.get(row.key);
    if (!view) { view = makeCaptureRow(); rowElements.set(row.key, view); }
    const m = row.model;
    view.title.textContent = row.title;
    view.title.title = row.title;
    view.source.textContent = row.channel || row.saved?.channel || sourceLabel(row.source_url || row.url) || row.platform || "";
    view.state.textContent = (m.failed ? "✕ " : m.done ? "✓ " : "") + m.label;
    view.state.className = `capture-state${m.failed ? " failed" : ""}`;
    view.error.textContent = m.failed ? PopupCaptures.safeError(row) : "";
    view.error.hidden = !m.failed;
    view.strip.hidden = m.done || m.cancelled;
    const advanced = view.index >= 0 && m.index > view.index;
    view.segments.forEach((segment, i) => {
      const cls = `step ${m.segments[i]}`;
      if (segment.className.replace(" advanced", "") !== cls) segment.className = cls;
      if (advanced && i === m.index) segment.classList.add("advanced");
    });
    view.index = m.index;
    const id = row.video_id;
    const signature = JSON.stringify([m.failed, m.done, id, PopupCaptures.slug(row), !!row.pending, row.code, !!captureHookType(row)]);
    if (view.signature !== signature) {
      view.actions.replaceChildren(); view.signature = signature;
      if (m.failed) {
        const retry = element("button", "", "Retry now"); retry.type = "button";
        retry.addEventListener("click", () => retryCapture(row.key, retry));
        view.actions.appendChild(retry);
      }
      if (m.done) {
        // /recent supplies the library id even when a capture response has only a folder.
        const read = element("a", "button", "Read");
        read.href = `${STC.SERVER}/dashboard#${id ? `item/${encodeURIComponent(id)}` : "library"}`;
        read.target = "_blank"; read.rel = "noreferrer";
        if (!id) read.textContent = "Library";
        const copy = element("button", "", "Copy Markdown"); copy.type = "button";
        copy.disabled = !PopupCaptures.slug(row) && !row.result?.combined_md_text;
        copy.addEventListener("click", () => copyCaptureMarkdown(rowModels.get(row.key), copy));
        view.actions.append(read, copy);
      }
      view.row.querySelector(".capture-tools")?.remove();
      if (m.done) view.row.appendChild(makeCaptureTools(row));
    }
    // Reuse nodes, including focused Retry/Copy controls, across stream ticks.
    if (list.children[position] !== view.row) list.insertBefore(view.row, list.children[position] || null);
  });
}

async function retryCapture(key, button) {
  if (rowActions.has(key)) return;
  const row = rowModels.get(key);
  if (!row) return;
  rowActions.set(key, true); button.disabled = true;
  try {
    if (row.pending?.pending_id || row.pending_id) {
      const response = await UoinkUI.authedJson("/queue/retry-now", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pending_id: row.pending?.pending_id || row.pending_id }),
      });
      if (!response?.ok) throw new Error(STC.describeFailure(response));
      showToast("Retry accepted. Captures will update as it runs.");
    } else if (row.failure || STC.isXArticleUrl(row.source_url || row.url)) {
      // Keep the P1 hand-off for in-page failures (especially logged-in X Articles).
      const retryRow = renderFailureRow(row.failure || { ...row, url: row.source_url || row.url });
      retryRow.querySelector("button").click();
    } else {
      const url = row.source_url || row.url;
      if (row.code === "host_not_allowed") { offerAllowRetry(url, row); return; }
      const source = STC.classifyCaptureUrl(url);
      const route = row.route || (source.action === "x_article" ? "page"
        : source.action === "x_video" ? "x_post" : source.action);
      const accepted = await handOffCapture({ route, url: source.canonical, title: row.title, saveOnly: !!row.saveOnly },
        { xArticle: source.action === "x_article" });
      if (!accepted.ok) throw new Error(accepted.message);
      showToast("Retry accepted. Captures will update as it runs.");
    }
    await refreshQueue(); await pollQueueStatus();
  } catch (err) { showToast(err.message || "Couldn't retry this capture."); }
  finally { rowActions.delete(key); button.disabled = false; }
}

async function copyCaptureMarkdown(row, button, destination = null) {
  if (!row || button.disabled) return;
  const label = button.textContent;
  button.disabled = true; button.textContent = "Copying...";
  try {
    const slug = PopupCaptures.slug(row);
    let markdown = row.result?.combined_md_text || "";
    if (slug) {
      const res = await UoinkUI.authedJson("/mcp/v1/tools/call", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "get_uoink_corpus", arguments: { slug } }),
      });
      const data = res?.result?.structuredContent;
      markdown = data?.ok ? data.corpus_md : "";
    }
    if (!markdown) { showToast("Failed to retrieve markdown."); return; }
    if (!await writeClipboardText(markdown)) { showToast("Clipboard copy blocked."); return; }
    if (destination) {
      try {
        await chrome.tabs.create({ url: destination.url, active: true });
        showToast(`Copied. Paste your capture into ${destination.label}.`);
      } catch (_) { showToast(`Copied, but couldn't open ${destination.label}. Open it and paste your capture.`); }
    } else showToast("Copied markdown to clipboard!");
  } catch (_) { showToast("Error retrieving markdown."); }
  finally { button.disabled = false; button.textContent = label; }
}

// Keep these existing capabilities inside Captures until Generate hosts them.
// Each destination copies this saved item first; no stale-clipboard time limit.
const HOOK_TYPE_CATEGORIES = ["curiosity_gap", "question", "contrarian", "story_open", "promise_list", "demo", "authority", "stakes", "other"];
const hookSaves = new Set();
function captureHookType(row) {
  const saved = row.saved || row;
  const hook = saved.hook_analysis || saved.hook || saved.taxonomy || {};
  return saved.corrected_hook_type || saved.hook_type || hook.corrected_hook_type || hook.hook_type || hook.type || hook.category || "";
}
function makeCaptureTools(row) {
  const details = element("details", "capture-tools");
  details.appendChild(element("summary", "", "Use this capture"));
  const destinations = element("div", "capture-actions");
  for (const destination of [{ label: "Claude", url: "https://claude.ai/new" }, { label: "ChatGPT", url: "https://chatgpt.com/" }]) {
    const send = element("button", "", `Send to ${destination.label}`); send.type = "button";
    send.disabled = !PopupCaptures.slug(row) && !row.result?.combined_md_text;
    send.addEventListener("click", () => copyCaptureMarkdown(rowModels.get(row.key), send, destination));
    destinations.appendChild(send);
  }
  details.appendChild(destinations);
  if (row.video_id && captureHookType(row)) {
    const form = element("form", "hook-form");
    const label = element("label", "", "Correct hook type");
    const select = document.createElement("select"); select.setAttribute("aria-label", "Correct hook type");
    for (const category of HOOK_TYPE_CATEGORIES) {
      const option = element("option", "", UoinkUI.prettyHookType(category)); option.value = category;
      select.appendChild(option);
    }
    select.value = captureHookType(row);
    label.appendChild(select);
    const actions = element("div", "capture-actions");
    const save = element("button", "", "Save correction"); save.type = "submit";
    actions.appendChild(save);
    const status = document.createElement("p"); status.className = "hook-correction-message";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    form.append(label, actions, status);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const id = row.video_id, corrected = select.value;
      if (hookSaves.has(id) || !HOOK_TYPE_CATEGORIES.includes(corrected)) return;
      hookSaves.add(id); select.disabled = true; save.disabled = true;
      status.classList.remove("error"); status.textContent = "Saving...";
      try {
        const result = await UoinkUI.authedJson("/taxonomy/correct", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ video_id: id, corrected_hook_type: corrected, user_reason: "" }),
        }, { throwOnHttp: true });
        if (!result?.ok) throw new Error(result?.error || "Correction was not saved");
        for (const saved of captureData.recent) {
          if (PopupCaptures.itemId(saved) === id) saved.hook_type = saved.corrected_hook_type = corrected;
        }
        status.textContent = "Saved. Future classifications will use this correction.";
      } catch (error) {
        status.classList.add("error"); status.textContent = `Not saved: ${error.message || error}. Try again.`;
      } finally { hookSaves.delete(id); select.disabled = false; save.disabled = false; }
    });
    details.appendChild(form);
  }
  return details;
}

let promptsLoading = false, promptsLoaded = false;
async function loadStarterPrompts() {
  if (promptsLoading || promptsLoaded) return;
  promptsLoading = true;
  const status = document.getElementById("starter-prompts-status");
  const list = document.getElementById("starter-prompts-list");
  status.textContent = "Loading...";
  try {
    const response = await fetch(chrome.runtime.getURL("prompts.json"));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const prompts = await response.json();
    if (!Array.isArray(prompts)) throw new Error("Invalid prompt list");
    list.replaceChildren();
    for (const prompt of prompts) {
      const row = element("div", "prompt-row");
      const label = String(prompt.label || prompt.title || prompt.id || "Untitled prompt");
      const copy = element("button", "", "Copy"); copy.type = "button";
      copy.setAttribute("aria-label", `Copy ${label}`);
      copy.addEventListener("click", async () => {
        if (copy.disabled) return;
        copy.disabled = true;
        const copied = await writeClipboardText(String(prompt.prompt || prompt.text || ""));
        status.textContent = copied ? "Prompt copied. Paste it after your capture." : "Clipboard copy blocked. Try again.";
        copy.disabled = false;
      });
      row.append(element("span", "", label), copy); list.appendChild(row);
    }
    promptsLoaded = true;
    status.textContent = prompts.length ? "" : "No starter prompts are saved.";
  } catch (error) { status.textContent = `Couldn't load starter prompts: ${error.message || error}. Close and reopen this section to retry.`; }
  finally { promptsLoading = false; }
}
document.getElementById("starter-prompts").addEventListener("toggle", event => {
  if (event.target.open) loadStarterPrompts();
});

// The existing opt-in screenshot selection stays reachable inside Captures.
// It never takes over the three-zone popup or hides its navigation.
let pickerPayload = null;
let pickerUrls = [];
async function refreshPicker() {
  const data = await chrome.storage.local.get({ pending_picker: null });
  const payload = data.pending_picker;
  if (closed || JSON.stringify(payload) === JSON.stringify(pickerPayload)) return;
  pickerPayload = payload;
  pickerUrls.forEach(url => URL.revokeObjectURL(url)); pickerUrls = [];
  const host = document.getElementById("pending-picker"); host.replaceChildren();
  if (!payload) return;
  const details = element("details", "picker");
  details.appendChild(element("summary", "", `Choose screenshots: ${payload.title || "Capture"}`));
  const shots = [...String(payload.yoink_md || "").matchAll(/!\[([^\]]*)\]\(([^)]+)\)/g)].filter(m => !m[2].startsWith("data:"));
  const choices = shots.map((shot, i) => {
    const label = element("label", "picker-choice");
    const check = document.createElement("input"); check.type = "checkbox"; check.checked = true;
    const img = document.createElement("img"); img.width = 64; img.height = 40; img.alt = "";
    label.append(check, img, document.createTextNode(shot[1] || `Screenshot ${i + 1}`)); details.appendChild(label);
    STC.getScreenshotThumbnail(shot[2]).then(src => {
      if (pickerPayload !== payload || closed) { if (src.startsWith("blob:")) URL.revokeObjectURL(src); return; }
      if (src.startsWith("blob:")) pickerUrls.push(src); img.src = src;
    }).catch(() => {});
    return check;
  });
  const copy = element("button", "", "Copy with selected"); copy.type = "button";
  copy.addEventListener("click", async () => {
    copy.disabled = true;
    let i = 0;
    const source = payload.corpus_md_paste || payload.yoink_md || "";
    const selected = source.replace(/!\[[^\]]*\]\([^)]+\)/g, match => choices[i++]?.checked === false ? "" : match);
    if (await writeClipboardText(selected)) {
      // A new capture may have arrived while the clipboard was writing.
      const latest = await chrome.storage.local.get({ pending_picker: null });
      if (JSON.stringify(latest.pending_picker) === JSON.stringify(payload)) await chrome.storage.local.remove("pending_picker");
      showToast("Copied markdown to clipboard!"); refreshPicker();
    } else { showToast("Clipboard copy blocked."); copy.disabled = false; }
  });
  details.appendChild(copy); host.appendChild(details);
}

// Research sessions predate Generate modes. Keep their existing capture
// controls reachable until the dashboard hosts them; no popup settings.
let activeSession = null;
let sessionBusy = false;
async function refreshResearchSession() {
  const status = document.getElementById("session-status");
  try {
    const [active, recent] = await Promise.all([STC.getActiveSession(), STC.listSessions()]);
    if (active?.ok === false || recent?.ok === false) throw new Error("Couldn't load research sessions.");
    activeSession = active?.session || null;
    document.getElementById("session-start-form").hidden = !!activeSession;
    document.getElementById("session-active").hidden = !activeSession;
    document.getElementById("session-active-name").textContent = activeSession
      ? `${activeSession.name || activeSession.session_id} · ${activeSession.video_count || 0} videos` : "";
    const list = document.getElementById("recent-sessions"); list.replaceChildren();
    for (const session of (recent?.sessions || []).filter(row => row.status !== "open").slice(0, 5)) {
      const open = element("button", "", session.name || session.session_id); open.type = "button";
      open.addEventListener("click", async () => {
        try {
          const result = await STC.openSession(session.session_id);
          if (!result?.ok) throw new Error(result?.error || "Couldn't open this session.");
        } catch (error) { status.textContent = error.message; }
      });
      list.appendChild(open);
    }
  } catch (error) { status.textContent = error.message || "Couldn't load research sessions."; }
}
async function researchSessionAction(action) {
  if (sessionBusy || (action !== "start" && !activeSession)) return;
  if (action === "cancel" && !confirm("Cancel this session? Its files stay on disk; no corpus will be generated.")) return;
  sessionBusy = true;
  const status = document.getElementById("session-status");
  const buttons = ["start-session", "end-session", "cancel-session"].map(id => document.getElementById(id));
  buttons.forEach(button => { button.disabled = true; });
  status.textContent = action === "start" ? "Starting..." : action === "end" ? "Closing..." : "Cancelling...";
  try {
    const id = activeSession?.session_id;
    const result = action === "start" ? await STC.startSession(document.getElementById("session-name").value.trim())
      : action === "end" ? await STC.closeSession(id) : await STC.cancelSession(id);
    if (!result?.ok) throw new Error(result?.error || "Couldn't update this session.");
    if (action === "end") {
      const copied = result.corpus_md && await writeClipboardText(result.corpus_md);
      status.textContent = copied ? "Session closed. Markdown copied." : "Session closed. Open its folder for corpus.md.";
      if (result.corpus_md?.length > 500000) status.textContent += " This corpus is large; attach corpus.md if it won't fit in a paste.";
    } else status.textContent = action === "start" ? "Session started." : "Session cancelled. Files kept.";
    await chrome.runtime.sendMessage({ type: "refreshActiveSession" });
    await refreshResearchSession();
  } catch (error) { status.textContent = error.message || "Couldn't update this session."; }
  finally { sessionBusy = false; buttons.forEach(button => { button.disabled = false; }); }
}
document.getElementById("research-session").addEventListener("toggle", event => {
  if (event.target.open) refreshResearchSession();
});
document.getElementById("session-start-form").addEventListener("submit", event => { event.preventDefault(); researchSessionAction("start"); });
document.getElementById("end-session").addEventListener("click", () => researchSessionAction("end"));
document.getElementById("cancel-session").addEventListener("click", () => researchSessionAction("cancel"));

document.getElementById("paste-form").addEventListener("submit", submitPaste);
document.getElementById("popup-version").textContent = `v${chrome.runtime.getManifest().version}`;
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session") refreshQueue();
  if (area === "local" && changes[RECENT_FAILURES_KEY]) loadRecentUoinks();
  if (area === "local" && changes.pending_picker) refreshPicker();
  if (area === "local" && changes.active_session && document.getElementById("research-session").open) refreshResearchSession();
});
const queueTimer = setInterval(refreshQueue, 1000);
const helperTimer = setInterval(pollQueueStatus, 3000);
const pingTimer = setInterval(ping, 5000);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) captureStream.stop();
  else { refreshQueue(); pollQueueStatus(); loadRecentUoinks(); ping(); }
});
window.addEventListener("unload", () => {
  closed = true; captureStream.stop(); clearInterval(queueTimer); clearInterval(helperTimer); clearInterval(pingTimer);
  pickerUrls.forEach(url => URL.revokeObjectURL(url));
});
detectCurrentSource(); refreshQueue(); loadRecentUoinks(); refreshPicker(); ping();
