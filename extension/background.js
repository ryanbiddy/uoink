// v3 TODO: rename native messaging host to com.uoink.helper after installer
// migration is widely deployed (target: 90 days post v2.1 release).

// Background service worker.
//
// Responsibilities:
//   - Context menus: extract this link, extract this page, add to active session
//   - openTab + notify on behalf of the content script
//   - Job queue (one extraction at a time), persisted to chrome.storage.session
//   - Clipboard via the offscreen document API
//   - Track the currently-active research session in chrome.storage.local
//
// Network logic is shared with content.js via lib/extract.js (importScripts;
// exposes globalThis.STC).

// x-article.js owns the single X-Article URL definition (A1). It loads before
// extract.js so STC.normalizeXArticleUrl/isXArticleUrl delegate to XArticle,
// and so the context menu can detect an Article and route it to the in-page
// DOM parse instead of the login-walled /extract/page fetch.
importScripts("lib/x-article.js", "lib/extract.js", "lib/ui.js");

const MENU_LINK = "stc-extract-link";
const MENU_PAGE = "stc-extract-page";
const MENU_SESSION = "stc-extract-session";
const MENU_REDDIT_LINK = "stc-extract-reddit-link";
const MENU_REDDIT_PAGE = "stc-extract-reddit-page";
const MENU_ARTICLE_PAGE = "stc-extract-article-page";
const ICON_URL = chrome.runtime.getURL("icons/icon128.png");
const OFFSCREEN_URL = "offscreen.html";
// CLIPBOARD covers the existing copy path; MATCH_MEDIA lets the doc stay
// alive so it can push prefers-color-scheme change events back here.
const OFFSCREEN_REASONS = ["CLIPBOARD", "MATCH_MEDIA"];
const LAST_YOINK_CLIPBOARD_KEY = "yoink_last_clipboard_at";
const LAST_CLIPBOARD_BUDGET_KEY = "yoink_last_clipboard_budget";
const _clipboardRetryPayloads = new Map();
const _queueViewNotificationIds = new Set();

const LINK_PATTERNS = [
  "https://www.youtube.com/watch*",
  "https://youtu.be/*",
  "https://www.youtube.com/shorts/*",
  "https://m.youtube.com/watch*",
  "https://m.youtube.com/shorts/*",
  "*://x.com/*/status/*",
  "*://twitter.com/*/status/*",
  "*://mobile.twitter.com/*/status/*",
  "*://www.x.com/*/status/*",
  "*://*.reddit.com/r/*/comments/*",
];
const PAGE_PATTERNS = [
  "https://www.youtube.com/watch*",
  "https://www.youtube.com/shorts/*",
  "https://m.youtube.com/watch*",
  "https://m.youtube.com/shorts/*",
  "*://x.com/*/status/*",
  "*://twitter.com/*/status/*",
  "*://*.reddit.com/r/*/comments/*",
];

// ---- Lifecycle ------------------------------------------------------------
chrome.runtime.onInstalled.addListener(async (details) => {
  await rebuildContextMenus();
  await refreshActiveSession();
  syncThemeIcon().catch((e) => console.warn("[stc] theme sync failed", e));
  restoreQueue().catch((e) => console.warn("[stc] restore failed", e));
  chrome.alarms.create("health-check", { periodInMinutes: 0.25 });
  checkHealthAndUpdateBadge().catch((e) => console.warn("[stc] checkHealthAndUpdateBadge failed", e));

  // Eager auth-token prefetch. Without this, the user's first authed
  // request blocks on a /token round-trip, and a transient failure there
  // surfaces as "missing or invalid token" before the lazy refetch kicks
  // in. Doing it on install/update means the token is in
  // chrome.storage.local before the user clicks anything.
  STC.getToken({ refresh: true }).catch((e) =>
    console.warn("[stc] token prefetch failed", e));

  // Fresh install only. Note: Chrome fires onInstalled with reason="install"
  // every time an *unpacked* extension is reloaded from chrome://extensions/,
  // not just on a true first install. Gate on a persistent flag instead of
  // trusting reason alone, otherwise every dev reload spawns a new setup
  // tab and the user thinks toolbar clicks are accumulating tabs.
  if (details && details.reason === "install") {
    try {
      const { setup_seen_at = null } = await chrome.storage.local.get({
        setup_seen_at: null,
      });
      if (!setup_seen_at) {
        await chrome.storage.local.set({ setup_seen_at: Date.now() });
        await chrome.tabs.create({
          url: chrome.runtime.getURL("setup.html?source=install"),
          active: true,
        });
      }
    } catch (e) {
      console.warn("[stc] setup open failed", e);
    }
  }
});

chrome.runtime.onStartup.addListener(async () => {
  await rebuildContextMenus();
  await refreshActiveSession();
  syncThemeIcon().catch((e) => console.warn("[stc] theme sync failed", e));
  restoreQueue().catch((e) => console.warn("[stc] restore failed", e));
  chrome.alarms.create("health-check", { periodInMinutes: 0.25 });
  checkHealthAndUpdateBadge().catch((e) => console.warn("[stc] checkHealthAndUpdateBadge failed", e));
});

// SW spins up on demand (notification click, message, alarm, etc) and the OS
// theme may have flipped while it was idle. Re-sync on every wake.
syncThemeIcon().catch((e) => console.warn("[stc] theme sync failed", e));
chrome.alarms.create("health-check", { periodInMinutes: 0.25 });
checkHealthAndUpdateBadge().catch((e) => console.warn("[stc] checkHealthAndUpdateBadge failed", e));

// ---- Alarms and Commands --------------------------------------------------
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "health-check") {
    checkHealthAndUpdateBadge().catch((e) => console.warn("[stc] checkHealthAndUpdateBadge failed", e));
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "uoink-video") {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id && tab.url) {
      chrome.tabs.sendMessage(tab.id, { type: "uoinkShortcutTriggered" }, async (response) => {
        if (chrome.runtime.lastError || !response || !response.success) {
          // Fallback: trigger background extract if it's a youtube url
          const normalized = STC.normalizeYouTubeUrl(tab.url);
          if (normalized) {
            const active = await getActiveFromStorage();
            const interval = await STC.getInterval();
            const kind = active && active.id ? "session_add" : "extract";
            const job = { kind, url: normalized, interval, addedAt: Date.now() };
            if (kind === "session_add") {
              job.session_id = active.id;
              job.session_name = active.name;
            }
            if (kind === "extract" && !(await serverQueueHasRoom())) {
              notify("Queue full", "Give it a few minutes, then try again.");
              return;
            }
            await enqueue(job);
          }
        }
      });
    }
  }
});

async function checkHealthAndUpdateBadge() {
  let isOnline = false;
  try {
    const res = await STC.ping();
    isOnline = !!(res && res.ok);
  } catch (e) {
    isOnline = false;
  }

  const state = await getState();
  const isBusy = !!(state.busy || (state.queue && state.queue.length > 0));

  if (isOnline) {
    STC.replayPendingEngagementEvents().catch((e) => console.warn("[stc] replay failed", e));
  }

  if (!isOnline) {
    await chrome.action.setBadgeText({ text: "OFF" });
    await chrome.action.setBadgeBackgroundColor({ color: "#C2410C" }); // Rust
    await chrome.action.setBadgeTextColor({ color: "#FFF4EC" }); // Cream
  } else if (isBusy) {
    await chrome.action.setBadgeText({ text: "..." });
    await chrome.action.setBadgeBackgroundColor({ color: "#FF3D00" }); // Vermillion
    await chrome.action.setBadgeTextColor({ color: "#FFF4EC" }); // Cream
  } else {
    await chrome.action.setBadgeText({ text: "" });
  }
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.active_session) {
    rebuildContextMenus().catch((e) => console.warn("[stc] menu rebuild failed", e));
  }
});

// ---- Context menus -------------------------------------------------------
async function rebuildContextMenus() {
  await new Promise((r) => chrome.contextMenus.removeAll(r));

  // YouTube / general video
  chrome.contextMenus.create({
    id: MENU_LINK,
    title: "Uoink video link",
    contexts: ["link"],
    targetUrlPatterns: LINK_PATTERNS.filter(p => !p.includes("reddit.com")),
  });
  chrome.contextMenus.create({
    id: MENU_PAGE,
    title: "Uoink video",
    contexts: ["page", "video"],
    documentUrlPatterns: PAGE_PATTERNS.filter(p => !p.includes("reddit.com")),
  });

  // Reddit thread
  chrome.contextMenus.create({
    id: MENU_REDDIT_LINK,
    title: "Uoink Reddit thread link",
    contexts: ["link"],
    targetUrlPatterns: ["*://*.reddit.com/r/*/comments/*"],
  });
  chrome.contextMenus.create({
    id: MENU_REDDIT_PAGE,
    title: "Uoink Reddit thread",
    contexts: ["page"],
    documentUrlPatterns: ["*://*.reddit.com/r/*/comments/*"],
  });

  // Article / web page. On an X Article this routes to the in-page DOM parse
  // (see the click handler); on any other page it's the allowlist-gated
  // /extract/page fetch. The title is updated per-tab by
  // updateArticleMenuTitle so it reads "Uoink this article" on an X Article
  // and "Uoink this page" elsewhere (A1: no more static mislabel).
  chrome.contextMenus.create({
    id: MENU_ARTICLE_PAGE,
    title: "Uoink this page",
    contexts: ["page"],
    documentUrlPatterns: ["http://*/*", "https://*/*"],
  });

  const active = await getActiveFromStorage();
  if (active && active.id) {
    const name = active.name || active.id;
    chrome.contextMenus.create({
      id: MENU_SESSION,
      title: `Uoink into session: ${name}`,
      contexts: ["link", "page", "video"],
      targetUrlPatterns: LINK_PATTERNS,
      documentUrlPatterns: PAGE_PATTERNS,
    });
  }
}

// A1: keep the "Uoink this page / article" context-menu label honest per tab.
// The single MENU_ARTICLE_PAGE item shows on every http(s) page; its title
// flips to "Uoink this article" when the tab is an X Article so the label
// matches what the click will actually do.
function isXArticleTab(url) {
  try {
    return !!(globalThis.XArticle && XArticle.isXArticleUrl(url || ""));
  } catch { return false; }
}

async function updateArticleMenuTitle(url) {
  const title = isXArticleTab(url) ? "Uoink this article" : "Uoink this page";
  try {
    await new Promise((resolve) =>
      chrome.contextMenus.update(MENU_ARTICLE_PAGE, { title }, () => {
        void chrome.runtime.lastError; // menu may not exist yet; ignore
        resolve();
      }));
  } catch { /* menus unavailable in some contexts */ }
}

try {
  chrome.tabs.onActivated.addListener(async ({ tabId }) => {
    try {
      const tab = await chrome.tabs.get(tabId);
      await updateArticleMenuTitle(tab && tab.url);
    } catch { /* tab gone */ }
  });
  chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
    if (changeInfo.url || (changeInfo.status === "complete" && tab)) {
      updateArticleMenuTitle(tab && tab.url).catch(() => {});
    }
  });
} catch { /* tabs events unavailable in some contexts */ }

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  // Decide raw URL by menu id.
  let raw = null;
  let kind = "extract";

  // Article / web page. A1: detect an X Article FIRST and route it to the
  // in-page DOM parse (the only path that gets past X's login wall) instead
  // of the login-walled /extract/page fetch. Genuinely generic pages still
  // take the /extract/page path (reuses the corpus success path via
  // job.usePage).
  if (info.menuItemId === MENU_ARTICLE_PAGE) {
    const pageUrl = info.pageUrl || (tab && tab.url);
    if (!pageUrl || !/^https?:\/\//i.test(pageUrl)) {
      notify("Invalid URL", "Couldn't read a web page URL from this tab.");
      return;
    }
    if (isXArticleTab(pageUrl) && tab && tab.id) {
      await captureXArticleFromTab(tab.id, pageUrl);
      return;
    }
    if (!(await serverQueueHasRoom())) {
      notify("Queue full", "Wait a few minutes");
      return;
    }
    await enqueue({ kind: "extract", url: pageUrl, usePage: true, addedAt: Date.now() });
    return;
  }

  if (info.menuItemId === MENU_LINK || info.menuItemId === MENU_REDDIT_LINK) {
    raw = info.linkUrl;
    kind = "extract";
  } else if (info.menuItemId === MENU_PAGE || info.menuItemId === MENU_REDDIT_PAGE) {
    raw = info.pageUrl || (tab && tab.url);
    kind = "extract";
  } else if (info.menuItemId === MENU_SESSION) {
    raw = info.linkUrl || info.pageUrl || (tab && tab.url);
    kind = "session_add";
  } else {
    return;
  }

  let normalized = STC.normalizeYouTubeUrl(raw || "");
  let isTwitter = false;
  let isReddit = false;
  if (!normalized) {
    normalized = STC.normalizeTwitterUrl(raw || "");
    if (normalized) {
      isTwitter = true;
    }
  }
  if (!normalized) {
    normalized = STC.normalizeRedditUrl(raw || "");
    if (normalized) {
      isReddit = true;
    }
  }
  if (!normalized) {
    notify("Invalid URL", "Couldn't find a YouTube video, X/Twitter post, or Reddit thread in that link.");
    return;
  }

  const interval = await STC.getInterval();
  const job = { kind, url: normalized, interval, addedAt: Date.now() };
  if (isTwitter) {
    job.useExtractAny = true;
  }
  if (isReddit) {
    job.useReddit = true;
  }
  if (kind === "session_add") {
    const active = await getActiveFromStorage();
    if (!active || !active.id) {
      notify("Uoink failed", "No active session. Start one in the popup first.");
      return;
    }
    job.session_id = active.id;
    job.session_name = active.name;
  }
  if (kind === "extract" && !(await serverQueueHasRoom())) {
    notify("Queue full", "Wait a few minutes");
    return;
  }
  await enqueue(job);
});

// ---- Generic message handling --------------------------------------------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;
  if (msg.target === "offscreen") return;

  // E1: a capture handed over by the popup (see enqueuePopupCapture). Only
  // extension pages can start one; content scripts keep their own routes.
  if (msg.type === "popupCapture") {
    if (!isExtensionPage(sender)) {
      sendResponse({ ok: false, error: "Only the Uoink popup can start this capture." });
      return;
    }
    enqueuePopupCapture(msg.job).then(sendResponse, (e) => {
      sendResponse({ ok: false, error: `Uoink couldn't queue this capture: ${(e && e.message) || e}` });
    });
    return true;
  }

  if (msg.type === "openTab" && msg.url) {
    chrome.tabs.create({ url: msg.url, active: true }, (tab) => {
      sendResponse({ ok: true, tabId: tab && tab.id });
    });
    return true;
  }

  if (msg.type === "stcPing") {
    // Proxy /health probes through the SW. Direct localhost fetches from a
    // YouTube content script can be killed by client-side blockers (Chrome
    // tracking protection, AV web shields) before they reach the loopback
    // server, which would falsely paint the in-page button as offline.
    STC.ping().then((data) => sendResponse(data || null));
    return true;
  }

  if (msg.type === "notify") {
    notify(msg.title || "Uoink", msg.message || "")
      .then((id) => sendResponse({ ok: true, id }));
    return true;
  }

  if (msg.type === "clearQueue") {
    clearQueue().then(() => sendResponse({ ok: true }));
    return true;
  }

  if (msg.type === "refreshActiveSession") {
    refreshActiveSession().then((s) => sendResponse({ ok: true, session: s }));
    return true;
  }

  if (msg.type === "copyToClipboard" && typeof msg.text === "string") {
    copyToClipboard(msg.text).then((ok) => sendResponse({ ok }));
    return true;
  }

  if (msg.type === "clipboardRetry" && typeof msg.text === "string") {
    notifyClipboardRetry(msg.text).then((id) => sendResponse({ ok: !!id, id }));
    return true;
  }

  if (msg.type === "themeChanged" && typeof msg.isDark === "boolean") {
    updateIconForTheme(msg.isDark).catch((e) => console.warn("[stc] setIcon failed", e));
    return;
  }

  // Content-script-proxied extract calls. Page-context fetches from YouTube
  // can be killed by client-side blockers (Chrome tracking protection, AV
  // web shields) before reaching the loopback server. The SW is in the
  // extension origin and not subject to those filters.
  if (msg.type === "stcExtract" && msg.url) {
    (async () => {
      try {
        if (!(await serverQueueHasRoom())) {
          sendResponse({ data: { ok: false, error: "Queue full, wait a few minutes" } });
          return;
        }
        let data;
        if (STC.normalizeRedditUrl(msg.url)) {
          data = await STC.postExtractReddit(msg.url, msg.interval);
        } else {
          data = await STC.postExtract(msg.url, msg.interval);
        }
        sendResponse({ data });
        if (data && data.ok) tryOpenPopup();
      } catch (e) {
        console.error("[stc] proxied extract failed", e);
        sendResponse({
          networkError: String(e && e.message || e),
          failure: await STC.describeCaptureError(e),
        });
      }
    })();
    return true;
  }
  // V-2c: X ARTICLE capture proxied from the in-page content script. The
  // article is already parsed from the page DOM; the SW just relays it to the
  // helper (same blocker-bypass rationale as stcExtract). No queue guard —
  // this is a local persist, not a transcription job.
  if (msg.type === "stcExtractXArticle" && msg.article) {
    (async () => {
      try {
        const data = await STC.postExtractXArticle(msg.article);
        // content-x-article.js loads without lib/extract.js, so word its
        // failure here with the same helper the other in-page buttons use.
        sendResponse({
          data,
          failureMessage: (data && data.ok) ? null : STC.describeFailure(data),
        });
        if (data && data.ok) tryOpenPopup();
      } catch (e) {
        console.error("[stc] proxied x-article extract failed", e);
        sendResponse({
          networkError: String(e && e.message || e),
          failure: await STC.describeCaptureError(e),
        });
      }
    })();
    return true;
  }
  // E6: remembered failure for content-x-article.js (no STC there). Same
  // record content.js and content-reddit.js write via STC.rememberFailure.
  // msg.replaces / forgetFailure: the popup Retry record a retried capture
  // replaces (on failure) or drops (on success).
  if (msg.type === "rememberFailure" && typeof msg.url === "string") {
    STC.rememberFailure(msg.url, String(msg.error || ""), {
      title: String(msg.title || ""),
    }, msg.replaces).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.type === "forgetFailure" && typeof msg.id === "string") {
    STC.forgetFailure(msg.id).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.type === "stcSessionAdd" && msg.session_id && msg.url) {
    (async () => {
      try {
        const data = await STC.addToSession(msg.session_id, msg.url, msg.interval);
        sendResponse({ data });
        if (data && data.ok) tryOpenPopup();
      } catch (e) {
        console.error("[stc] proxied session add failed", e);
        sendResponse({
          networkError: String(e && e.message || e),
          failure: await STC.describeCaptureError(e),
        });
      }
    })();
    return true;
  }
});

// Best-effort popup auto-open after a successful yoink. Chrome MV3 only
// honors openPopup() in narrow circumstances (must be a focused window with
// the action visible, sometimes requires a recent user gesture). Failures
// are silently swallowed — the user can still click the extension icon.
function tryOpenPopup() {
  try {
    if (chrome.action && typeof chrome.action.openPopup === "function") {
      const maybe = chrome.action.openPopup();
      if (maybe && typeof maybe.catch === "function") {
        maybe.catch(() => { /* ignore — MV3 restrictions */ });
      }
    }
  } catch { /* ignore */ }
}

// ---- Notifications -------------------------------------------------------
function notify(title, message, extraOptions = {}) {
  // Only capture outcomes interrupt the user. Content scripts still send
  // queued messages for older helpers; acknowledge them without a desktop toast.
  const finished = /^(?:Uoinked(?: ★)?|Uoink ready|Posts saved|Added to session|Copied to clipboard)$/i.test(title);
  const failed = /(?:failed|offline|blocked|queue full|invalid URL|lost track|still working|couldn't (?:read|capture))/i.test(title);
  if (!finished && !failed) return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      chrome.notifications.create({
        type: "basic",
        iconUrl: ICON_URL,
        title,
        message,
        priority: 1,
        ...extraOptions,
      }, (id) => resolve(id));
    } catch (e) {
      console.warn("[stc] notification failed", e);
      resolve(null);
    }
  });
}

async function markClipboardYoinkNow() {
  try {
    await chrome.storage.local.set({ [LAST_YOINK_CLIPBOARD_KEY]: Date.now() });
  } catch { /* ignore */ }
}

function screenshotCountFromData(data, text) {
  return globalThis.YoinkUI.screenshotCountFromData(data, text);
}

async function rememberClipboardBudget(data, clipboardText) {
  const budget = globalThis.YoinkUI.clipboardBudgetFromData(data, clipboardText);
  try {
    await chrome.storage.local.set({ [LAST_CLIPBOARD_BUDGET_KEY]: budget });
  } catch { /* ignore */ }
}

function minutesUntil(value) {
  return globalThis.YoinkUI.minutesUntil(value);
}

function queuedMessage(data) {
  return globalThis.YoinkUI.queuedMessage(data);
}

async function getServerQueueStatus() {
  try {
    const token = STC.getToken ? await STC.getToken() : null;
    let res = await fetch(`${STC.SERVER}/queue/status`, {
      method: "GET",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: token ? { "X-Yoink-Token": token } : {},
    });
    if (res.status === 403 && STC.getToken) {
      const fresh = await STC.getToken({ refresh: true });
      res = await fetch(`${STC.SERVER}/queue/status`, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        cache: "no-store",
        headers: fresh ? { "X-Yoink-Token": fresh } : {},
      });
    }
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function serverQueueHasRoom() {
  const status = await getServerQueueStatus();
  const pending = Number(status && (status.pending_count ?? status.queued_count)) || 0;
  return pending < 5;
}

async function notifyClipboardRetry(text) {
  const id = await notify("Clipboard copy blocked", "Your uoink is ready. Click Try again to copy it.", {
    buttons: [{ title: "Try again" }],
  });
  if (id) _clipboardRetryPayloads.set(id, text);
  return id;
}

try {
  chrome.notifications.onButtonClicked.addListener((id, buttonIndex) => {
    if (_queueViewNotificationIds.has(id)) {
      _queueViewNotificationIds.delete(id);
      tryOpenPopup();
      return;
    }
    if (buttonIndex !== 0 || !_clipboardRetryPayloads.has(id)) return;
    const text = _clipboardRetryPayloads.get(id);
    _clipboardRetryPayloads.delete(id);
    copyToClipboard(text).then(async (ok) => {
      if (ok) {
        await markClipboardYoinkNow();
        notify("Copied to clipboard", "Open Claude or ChatGPT from the Uoink popup, then paste.");
      } else {
        notify("Copy still blocked", "Open the saved uoink folder and copy the markdown file manually.");
      }
    });
  });
  chrome.notifications.onClosed.addListener((id) => {
    _clipboardRetryPayloads.delete(id);
    _queueViewNotificationIds.delete(id);
  });
} catch { /* notifications unavailable in some test contexts */ }

// ---- Offscreen (clipboard + theme detection) -----------------------------
// The offscreen doc is now long-lived: closing it would kill the
// matchMedia listener that drives theme-aware icon swaps. Both clipboard
// writes and theme detection share a single document.
//
// Concurrency: ensureOffscreen() can be hit from multiple async paths
// (clipboard write + theme sync + queue startup). Without coalescing, two
// callers can both observe "no doc exists" before either has called
// createDocument(), then both try to create -- the second throws "Only a
// single offscreen document may be created". Cache the in-flight create
// promise so concurrent callers wait on the same operation.
let _ensureOffscreenInflight = null;
async function ensureOffscreen() {
  if (chrome.offscreen && chrome.offscreen.hasDocument) {
    if (await chrome.offscreen.hasDocument()) return;
  } else {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ["OFFSCREEN_DOCUMENT"],
    });
    if (contexts && contexts.length) return;
  }
  if (_ensureOffscreenInflight) return _ensureOffscreenInflight;
  _ensureOffscreenInflight = (async () => {
    try {
      await chrome.offscreen.createDocument({
        url: OFFSCREEN_URL,
        reasons: OFFSCREEN_REASONS,
        justification:
          "Write extracted transcript to the system clipboard, and watch " +
          "prefers-color-scheme so the toolbar icon matches the browser theme.",
      });
    } catch (e) {
      // If a concurrent caller created the doc between our existence check
      // and createDocument(), the second create throws -- swallow that
      // specific case so callers see a successful-creation outcome.
      if (!String(e && e.message || e).includes("single offscreen document")) {
        throw e;
      }
    } finally {
      _ensureOffscreenInflight = null;
    }
  })();
  return _ensureOffscreenInflight;
}

async function copyToClipboard(text) {
  try {
    await ensureOffscreen();
    const res = await chrome.runtime.sendMessage({
      target: "offscreen",
      type: "copy",
      text,
    });
    return !!(res && res.ok);
  } catch (e) {
    console.error("[stc] copyToClipboard failed", e);
    return false;
  }
}

// ---- Theme-aware toolbar icon -------------------------------------------
// Chrome's manifest `theme_icons` field is honored by Chrome and Edge but
// not by every Chromium fork (notably Comet, where the icon stays stuck on
// the default). Drive the swap from JS instead so it works everywhere.
async function updateIconForTheme(isDark) {
  await chrome.action.setIcon({
    path: {
      "16": "icons/icon16.png",
      "32": "icons/icon32.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png",
    },
  });
}

async function syncThemeIcon() {
  // MV3 service workers don't expose matchMedia, so the offscreen doc owns
  // detection and pushes change events back to us. We still pull on wake in
  // case the OS theme flipped while the SW was idle.
  if (typeof self.matchMedia === "function") {
    try {
      const mq = self.matchMedia("(prefers-color-scheme: dark)");
      await updateIconForTheme(mq.matches);
      mq.addEventListener("change", (e) => {
        updateIconForTheme(e.matches).catch(() => { /* ignore */ });
      });
      return;
    } catch { /* fall through to offscreen */ }
  }

  await ensureOffscreen();
  try {
    const res = await chrome.runtime.sendMessage({
      target: "offscreen",
      type: "queryTheme",
    });
    if (res && typeof res.isDark === "boolean") {
      await updateIconForTheme(res.isDark);
    }
  } catch (e) {
    console.warn("[stc] queryTheme failed", e);
  }
}

// ---- Active session sync -------------------------------------------------
async function getActiveFromStorage() {
  const { active_session = null } = await chrome.storage.local.get({ active_session: null });
  return active_session;
}

async function refreshActiveSession() {
  const res = await STC.getActiveSession();
  const session = (res && res.ok) ? res.session : null;
  const value = session ? {
    id: session.session_id,
    name: session.name,
    video_count: session.video_count,
    folder: session.folder,
    recent: session.recent || [],
  } : null;
  await chrome.storage.local.set({ active_session: value });
  return value;
}

// ---- Queue ---------------------------------------------------------------
const _draining = { running: false };
// MV3: Chrome stops an extension service worker after 30 s without an
// extension event or API call, and can stop one that's waiting on a slow
// fetch, so a capture the helper takes minutes over could die with the
// worker. Chrome's documented keep-alive is a cheap extension API call on a
// timer: drain() makes one every 20 s while it has jobs. restoreQueue()
// handles the stops this can't prevent.
const KEEPALIVE_MS = 20 * 1000;

function keepWorkerAlive() {
  try {
    chrome.runtime.getPlatformInfo(() => {});
  } catch { /* ignore */ }
}

async function getState() {
  return chrome.storage.session.get({ busy: false, current: null, queue: [] });
}
async function setState(patch) {
  return chrome.storage.session.set(patch);
}

let _enqueueChain = Promise.resolve();
function enqueue(job) {
  _enqueueChain = _enqueueChain.then(() => _doEnqueue(job)).catch((e) => {
    console.error("[stc] enqueue failed", e);
  });
  return _enqueueChain;
}

// Runs fn on the enqueue chain, after every queue change already asked for,
// so the steps that read and rewrite the queue state (enqueuePopupCapture,
// restoreQueue, settleCaptureRequest, drain's takeNextJob, clearQueue) take
// turns. Resolves with fn's result.
function queueStep(fn) {
  const step = _enqueueChain.then(fn);
  _enqueueChain = step.catch((e) => {
    console.error("[stc] enqueue failed", e);
  });
  return step;
}

async function _doEnqueue(job) {
  // Every job carries an id (popup captures already do): a popup's outcome
  // and a popup click or Retry that joins the job (addPopupJoin) key on it.
  if (!job.id) job.id = `job-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const state = await getState();
  state.queue.push(job);
  await setState({ queue: state.queue });

  // Captures shows queued/running work. Notifications are for outcomes.
  drain();
}

function clearQueue() {
  return queueStep(async () => {
    await setState({ queue: [] });
  });
}

// MV3: Chrome can still stop this worker mid-job (an update, a crash, a stop
// the keep-alive can't prevent), and the next one starts with
// chrome.storage.session as the old one left it: busy, the job it was
// running as `current`, the rest queued. Nothing of the old worker survives,
// so that job isn't running anywhere. Every worker start runs this once, as
// the first queue step, so it comes before the click or menu item that woke
// the worker up:
//  - a capture the helper hadn't answered goes back to the head of the
//    queue, once. It finishes here (clipboard, Claude tab, notification,
//    failure record), and a popup click for it is a duplicate instead of a
//    second capture. The helper holds a repeat of a YouTube capture it's
//    still running until that one is done and answers with it (no second
//    download); anything else, or one it had already finished, runs again.
//  - a job the helper had answered, one already resumed once, or a session
//    add (sending it again would add the video twice) is dropped with the
//    "lost track" notice instead.
// Then the queue drains. (This used to run only on browser start or an
// update, when chrome.storage.session is empty anyway.)
let _restored = null;
function restoreQueue() {
  if (!_restored) _restored = queueStep(recoverInterruptedJob);
  return _restored;
}

async function recoverInterruptedJob() {
  const state = await getState();
  if (!state.busy) {
    if (state.queue.length) drain();
    return;
  }
  const queue = state.queue;
  const stopped = state.current ? { ...state.current } : null;
  let lost = null;
  if (stopped) {
    delete stopped.startedAt;
    if (stopped.kind === "extract" && !stopped.answered && !stopped.resumed) {
      stopped.resumed = true;
      queue.unshift(stopped);
    } else {
      lost = stopped;
    }
  }
  await setState({ busy: false, current: null, queue });
  if (lost) {
    const join = await takePopupJoin(lost.id);
    const failure = await notifyThrownCaptureError({ uoinkKind: "lost" });
    await publishPopupResult(joinedByPopup(lost, join), {
      ok: false, kind: failure.kind, message: failure.message,
    });
  }
  if (queue.length) drain();
}

restoreQueue().catch((e) => console.warn("[stc] restore failed", e));

// ---- Popup captures (E1) ---------------------------------------------------
// The popup used to await /extract (and /extract/reddit, /extract/page) in its
// own document. Chrome closes the popup as soon as the user clicks back into
// the page, which killed the request and lost its clipboard copy, Claude tab
// and failure record, so users retried captures that had actually finished.
// The popup now hands the capture to this queue and returns; runExtractJob
// does the side effects here and publishes the outcome for a popup that's
// still open (popup.js refreshQueue -> applyCaptureQueueState).
// The popup's Recent failures Retry for a capture this queue ran sends the
// same message with retryOf (the record's id): the record stays until the
// rerun goes through, and a new failure replaces it. A click or Retry for a
// capture that's already queued or running, the context menu's included,
// joins that job instead (addPopupJoin).
const POPUP_CAPTURE_RESULTS_KEY = "popup_capture_results";
// Popup requests that joined a queued or running job, by job id: {title,
// retries: [the Recent failures ids a Retry named]}. That job then settles
// as a popup capture (joinedByPopup), whatever started it.
const POPUP_CAPTURE_JOINS_KEY = "popup_capture_joins";
const POPUP_CAPTURE_ROUTES = ["video", "reddit", "page", "playlist", "podcast", "x_post"];
const QUEUE_FULL_MESSAGE = "Queue full. Give it a few minutes, then try again.";
// How long a popup video waits on /queue/status at its turn before going
// ahead anyway, so a stalled status call can't hold up the queue.
const QUEUE_ROOM_WAIT_MS = 10 * 1000;

function isExtensionPage(sender) {
  const base = chrome.runtime.getURL("");
  return !!(sender && typeof sender.url === "string" && sender.url.startsWith(base));
}

// Two jobs that would run the same capture of the same URL with the same
// side effects (a save-only X video doesn't copy or open Claude). A session
// add has no capture route, so nothing matches it. URLs compare without a
// #fragment (STC.queueUrlKey): a context-menu job keeps the tab's.
function sameCapture(a, b) {
  const route = STC.queueJobRoute(a);
  return !!(a && b && route) && STC.queueUrlKey(a.url) === STC.queueUrlKey(b.url)
    && route === STC.queueJobRoute(b) && !!a.saveOnly === !!b.saveOnly;
}

function enqueuePopupCapture(req) {
  const url = req && typeof req.url === "string" ? req.url : "";
  if (!POPUP_CAPTURE_ROUTES.includes(req && req.route) || !STC.normalizeAnyUrl(url)
      || (req.route === "playlist" && !STC.normalizePlaylistUrl(url))
      || (req.route === "x_post" && !STC.normalizeTwitterUrl(url))) {
    return Promise.resolve({ ok: false, error: "Uoink can't capture this tab from the popup." });
  }
  // Inside the enqueue chain, so two quick clicks can't both pass the
  // duplicate check before either job is stored.
  return queueStep(async () => {
    const state = await getState();
    // Only this service worker's drain() runs captures (restoreQueue has
    // already taken back a job a stopped worker left). A job the helper has
    // answered is finishing up: a click now is a new capture.
    const running = _draining.running && state.busy && state.current
      && !state.current.answered ? state.current : null;
    const job = {
      kind: "extract",
      url,
      addedAt: Date.now(),
      origin: "popup",
      id: `popup-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      title: typeof req.title === "string" ? req.title.slice(0, 300) : "",
    };
    if (req.route === "page") job.usePage = true;
    if (req.route === "reddit") job.useReddit = true;
    if (req.route === "playlist") job.usePlaylist = true;
    if (req.route === "podcast") job.usePodcast = true;
    if (req.route === "x_post") job.useXPost = true;
    // The popup used to check the helper's queue before a video; that
    // check now runs in runExtractJob so the popup never waits on it.
    if (req.route === "video") job.checkRoom = true;
    if (req.saveOnly) job.saveOnly = true;
    if (typeof req.retryOf === "string" && req.retryOf) job.retryOf = req.retryOf.slice(0, 100);
    const same = [running].concat(state.queue).find((other) => sameCapture(other, job));
    if (same) {
      // A click or Retry for a capture that's already queued or running
      // (a context-menu one included): no second extraction, and that job
      // answers this popup too: its outcome is published, a failure gets a
      // Recent failures row, and a Retry's record goes once it goes through.
      if (same.id) await addPopupJoin(same.id, job);
      drain(); // no-op while running
      return { ok: true, duplicate: true, id: same.id || null };
    }
    let interval = parseInt(req.interval, 10);
    if (!Number.isFinite(interval) || interval < 5 || interval > 300) {
      interval = await STC.getInterval();
    }
    job.interval = interval;
    const ahead = (running ? 1 : 0) + state.queue.length;
    await _doEnqueue(job);
    return { ok: true, id: job.id, ahead };
  });
}

// req: the popup's job that matched (sameCapture) the queued or running one.
async function addPopupJoin(jobId, req) {
  const items = await chrome.storage.session.get({ [POPUP_CAPTURE_JOINS_KEY]: {} });
  const all = Object.assign({}, items[POPUP_CAPTURE_JOINS_KEY]);
  const prior = all[jobId] || {};
  const retries = Array.isArray(prior.retries) ? prior.retries : [];
  all[jobId] = {
    title: prior.title || req.title || "",
    retries: req.retryOf && !retries.includes(req.retryOf) ? retries.concat(req.retryOf) : retries,
  };
  await chrome.storage.session.set({ [POPUP_CAPTURE_JOINS_KEY]: all });
}

// The popup requests that joined this job ({title, retries}), or null when
// none did; forgets them.
async function takePopupJoin(jobId) {
  if (!jobId) return null;
  const items = await chrome.storage.session.get({ [POPUP_CAPTURE_JOINS_KEY]: {} });
  const all = Object.assign({}, items[POPUP_CAPTURE_JOINS_KEY]);
  if (!(jobId in all)) return null;
  const join = all[jobId] || {};
  delete all[jobId];
  await chrome.storage.session.set({ [POPUP_CAPTURE_JOINS_KEY]: all });
  return { title: join.title || "", retries: Array.isArray(join.retries) ? join.retries : [] };
}

// A job a popup request joined (takePopupJoin) settles as a popup capture:
// it publishes its outcome for that popup and records a failure in Recent
// failures, under the popup's title when the job has none (a context-menu
// job doesn't). Without a join, the job as it is.
function joinedByPopup(job, join) {
  if (!join) return job;
  return Object.assign({}, job, { origin: "popup", title: job.title || join.title });
}

// E1: the job's capture request is over: the helper answered, the request
// threw, or the helper's queue had no room. One queue step, so a popup
// click or Retry can't slip in between: the running job is marked answered
// (restoreQueue won't send it again, and a later click is a new capture,
// not a duplicate) and the popup requests that joined it are taken.
// Resolves with those (takePopupJoin), or null.
function settleCaptureRequest(job) {
  return queueStep(async () => {
    const state = await getState();
    if (job.id && state.busy && state.current && state.current.id === job.id) {
      await setState({ current: { ...state.current, answered: true } });
    }
    return takePopupJoin(job.id);
  });
}

// The outcome of a popup capture, for the popup if it's still open (it shows
// the ones it handed off). Newest first, five max. A context-menu job has no
// origin and publishes nothing, unless a popup joined it (joinedByPopup).
async function publishPopupResult(job, result) {
  if (!job || job.origin !== "popup" || !job.id) return;
  try {
    const items = await chrome.storage.session.get({ [POPUP_CAPTURE_RESULTS_KEY]: [] });
    const prior = Array.isArray(items[POPUP_CAPTURE_RESULTS_KEY])
      ? items[POPUP_CAPTURE_RESULTS_KEY]
      : [];
    const entry = Object.assign({
      id: job.id, url: job.url, title: job.title || "", route: STC.queueJobRoute(job),
      saveOnly: !!job.saveOnly,
      finishedAt: Date.now(), ...(job.captureResult || {}),
    }, result);
    await chrome.storage.session.set({
      [POPUP_CAPTURE_RESULTS_KEY]: [entry]
        .concat(prior.filter((r) => r && r.id !== job.id))
        .slice(0, 5),
    });
  } catch (e) {
    console.warn("[stc] popup capture result not stored", e);
  }
}

// serverQueueHasRoom, but no answer within `ms` counts as room, the way the
// popup's own check treated a failed /queue/status.
function serverQueueHasRoomWithin(ms) {
  let timer = null;
  const gaveUp = new Promise((resolve) => { timer = setTimeout(() => resolve(true), ms); });
  return Promise.race([serverQueueHasRoom(), gaveUp]).finally(() => clearTimeout(timer));
}

// What the popup's Recent failures Retry needs to rerun a failed popup
// capture in this queue.
function popupFailureExtra(job) {
  const extra = { title: job.title || "", route: STC.queueJobRoute(job) };
  if (job.saveOnly) extra.saveOnly = true;
  return extra;
}

function shortUrl(url) {
  try {
    const u = new URL(url);
    const id = u.searchParams.get("v");
    return id ? `youtu.be/${id}` : url;
  } catch { return url; }
}

async function drain() {
  if (_draining.running) return;
  _draining.running = true;
  const keepAlive = setInterval(keepWorkerAlive, KEEPALIVE_MS);
  let idle = false;
  try {
    while (true) {
      const job = await queueStep(takeNextJob);
      checkHealthAndUpdateBadge().catch(() => {});
      if (!job) {
        idle = true;
        return;
      }

      try {
        await runJob(job);
      } catch (e) {
        console.error("[Uoink] job crashed", e);
        notify("Uoink failed", String(e));
      }
    }
  } finally {
    clearInterval(keepAlive);
    // takeNextJob already let go when the queue went idle, and a drain() an
    // enqueue started after that owns the flag now.
    if (!idle) _draining.running = false;
  }
}

// drain()'s queue step, so an enqueue (or Clear queue) can't land between
// reading the queue and writing it back: the next job becomes `current`, or,
// with none left, the queue goes idle and this drain() lets go in the same
// step. A job enqueued after that starts a new drain() instead of waiting on
// one that's about to stop. Resolves with the job, or null when idle.
async function takeNextJob() {
  const state = await getState();
  if (!state.queue.length) {
    await setState({ busy: false, current: null });
    _draining.running = false;
    return null;
  }
  const job = state.queue.shift();
  await setState({ busy: true, current: { ...job, startedAt: Date.now() }, queue: state.queue });
  return job;
}

async function runJob(job) {
  if (job.kind === "session_add") return runSessionAddJob(job);
  return runExtractJob(job);
}

async function runExtractJob(job) {
  // E1: a popup video checks the helper's queue here, at its turn, instead
  // of the popup waiting on /queue/status before handing it over. A full
  // queue isn't a failed capture: no Recent failures row, and a retried
  // record stays.
  if (job.checkRoom && !(await serverQueueHasRoomWithin(QUEUE_ROOM_WAIT_MS))) {
    job = joinedByPopup(job, await settleCaptureRequest(job));
    notify("Queue full", "Give it a few minutes, then try again.");
    await publishPopupResult(job, { ok: false, code: "queue_full", message: QUEUE_FULL_MESSAGE });
    return;
  }
  let data;
  let savedXPosts = false;
  try {
    if (job.usePlaylist) {
      data = await STC.playlistStart(job.url, job.interval);
    } else if (job.usePodcast) {
      // A page's RSS/Atom link need not contain "feed" or end in .xml.
      // The helper validates the feed; URL hints only classify pasted links.
      data = await STC.postPodcastFeed(job.url);
    } else if (job.useXPost) {
      data = await STC.postExtractX(job.url);
      if (!data || data.code === "disabled" || data.code === "empty") {
        // A video-only post keeps the same queue-room guard as a video.
        if (!(await serverQueueHasRoomWithin(QUEUE_ROOM_WAIT_MS))) {
          job = joinedByPopup(job, await settleCaptureRequest(job));
          notify("Queue full", "Give it a few minutes, then try again.");
          await publishPopupResult(job, { ok: false, code: "queue_full", message: QUEUE_FULL_MESSAGE });
          return;
        }
        data = await STC.postExtract(job.url, job.interval);
      } else savedXPosts = !!data.ok;
    } else if (job.usePage) {
      data = await STC.postExtractPage(job.url);
    } else if (job.useExtractAny) {
      data = await STC.postExtractAny(job.url, job.interval);
    } else if (job.useReddit) {
      data = await STC.postExtractReddit(job.url, job.interval);
    } else {
      data = await STC.postExtract(job.url, job.interval);
    }
  } catch (e) {
    console.error("[Uoink] extract request failed", e);
    job = joinedByPopup(job, await settleCaptureRequest(job));
    // No tab open here -- setup.html only opens from direct user actions
    // (the in-page YouTube button or the popup help link), never from
    // background-queued jobs. Keeps unrelated context-menu work from
    // surprising the user with new tabs.
    const failure = await notifyThrownCaptureError(e);
    await publishPopupResult(job, { ok: false, kind: failure.kind, message: failure.message });
    return;
  }
  // E1: the Recent failures records this capture settles: its own retryOf,
  // plus any a Retry named when it joined this job while queued or running.
  const join = await settleCaptureRequest(job);
  job = joinedByPopup(job, join);
  // Keep only the fields the small Captures view needs, never a base64 corpus.
  job.captureResult = {
    title: (data && data.title) || job.title || "",
    video_id: data && data.video_id, folder: data && data.folder,
    video_slug: data && data.video_slug, job_id: data && data.job_id,
    pending_id: data && data.pending_id,
    failure_phase: data && data.failure_phase, error_detail: data && data.error_detail,
  };
  const retried = [job.retryOf].concat(join ? join.retries : []).filter(Boolean);
  if (!data || !data.ok) {
    // A2: an X login wall (or a pasted X link X won't serve logged-out) is not
    // a generic failure — it's honest and actionable. Say what happened and
    // what to do, and make it persistent so it isn't a toast that vanishes.
    if (data && data.code === "x_login_wall") {
      await notifyWalledXArticle();
      await publishPopupResult(job, {
        ok: false, code: data.code, message: STC.describeFailure(data),
      });
      return;
    }
    const message = STC.describeFailure(data);
    // E1: a failed popup capture (or one a popup joined) gets a Recent
    // failures row, like the in-page button's, replacing the retried
    // records: rememberFailure drops the one it names and any row for this
    // exact URL; the rest go by id (a joined Retry's URL can differ by its
    // #fragment, see sameCapture). An allowlist wall isn't a failed
    // capture: the popup offers "Allow this site and retry" for it instead.
    if (job.origin === "popup" && !(data && data.code === "host_not_allowed")) {
      for (const id of retried.slice(1)) await STC.forgetFailure(id);
      await STC.rememberFailure(job.url, message, {
        ...popupFailureExtra(job), failure_phase: data && data.failure_phase,
        error_detail: data && data.error_detail,
      }, retried[0]);
    }
    notify("Uoink failed", message,
           { requireInteraction: true });
    await publishPopupResult(job, {
      ok: false, code: (data && data.code) || null, message,
    });
    return;
  }
  // The helper took the retried capture: its Recent failures rows can go.
  for (const id of retried) await STC.forgetFailure(id);
  if (savedXPosts) {
    // /extract/x already saved a readable item. Finish that result before
    // the separate video request, just as captureXPost does in the popup.
    const count = Number(data.tweets_captured) || 1;
    const saved = `Saved ${count} post${count === 1 ? "" : "s"}`;
    let message = `${saved} to your library.`;
    let followUp = null;
    if (data.metadata && data.metadata.has_video) {
      try {
        const video = await enqueuePopupCapture({ route: "video", url: job.url,
          interval: job.interval, title: `Video from ${data.title || job.title || "X post"}`, saveOnly: true });
        message = video.ok ? `${saved} + queued the video.`
          : `${saved}. Video not queued: ${video.error}`;
        if (video.ok) followUp = {
          id: video.id,
          failurePrefix: `${saved}. Video: `,
          queueFullMessage: `${saved}. Video not queued -- the queue is full. Try the video again in a few minutes.`,
        };
      } catch (_) {
        message = `${saved}. Couldn't queue the video. Try capturing the post again.`;
      }
    }
    notify("Posts saved", message);
    await publishPopupResult(job, { ok: true, message, followUp });
    return;
  }
  if (job.usePlaylist) {
    await publishPopupResult(job, { ok: true, queued: true, message: "Playlist started. Follow it in Captures." });
    return;
  }
  if (job.usePodcast) {
    await publishPopupResult(job, { ok: true, message: "Podcast feed saved. Uoink will watch metadata; audio stays off." });
    return;
  }
  if (data.queued) {
    await publishPopupResult(job, { ok: true, queued: true, message: queuedMessage(data) });
    return;
  }

  await setState({
    current: {
      ...job, startedAt: Date.now(), title: data.title || job.title || null, answered: true,
    },
  });

  // E1: the video half of an X post whose text the popup already saved. The
  // popup never copied that one or opened Claude for it, so neither do we.
  if (job.saveOnly) {
    const message = data.title
      ? `Saved the video "${data.title}" to your library.`
      : "Saved the video to your library.";
    notify("Uoinked ★", message);
    await publishPopupResult(job, { ok: true, message });
    return;
  }

  // E1: a capture the helper reused comes back without its markdown (a job
  // restoreQueue resumed waited behind the capture the helper was still
  // running). Say it's saved rather than copy nothing and open Claude.
  if (!data.corpus_md_paste && !data.yoink_md) {
    const message = data.title
      ? `Saved "${data.title}" to your library. Use Copy Markdown in the Uoink popup to paste it.`
      : "Saved to your library. Use Copy Markdown in the Uoink popup to paste it.";
    notify("Uoinked ★", message);
    await publishPopupResult(job, { ok: true, message });
    return;
  }

  // Sprint 3: Smart Screenshot Picker intercept. When the user has the
  // picker setting enabled, we hand the corpus off to the popup instead of
  // auto-copying. Default off keeps v1 behavior byte-identical.
  if (await _useScreenshotPicker()) {
    await rememberClipboardBudget(data, data.corpus_md_paste || data.yoink_md);
    await STC.stashPickerCorpus(data);
    notify("Uoink ready",
           "Click the Uoink icon to pick which screenshots to include.");
    await publishPopupResult(job, {
      ok: true, message: "Uoink ready. Pick screenshots in the popup.",
    });
    return;
  }

  // Prefer the multimodal paste version (transcript + base64-embedded
  // screenshots) so a single Ctrl+V into Claude/ChatGPT delivers both.
  // Fall back to the file version if the server didn't generate one
  // (Pillow missing in dev, generation failure, etc).
  const clipboardText = data.corpus_md_paste || data.yoink_md;
  await rememberClipboardBudget(data, clipboardText);
  const copied = await copyToClipboard(clipboardText);
  if (!copied) {
    await notifyClipboardRetry(clipboardText);
    await publishPopupResult(job, {
      ok: true, message: "Couldn't copy. Use the Try again notification.",
    });
    return;
  }
  if (job.origin === "popup") {
    // The popup logged its own pastes; keep that signal now the SW copies.
    STC.logEngagement("paste", "popup", { length: clipboardText.length }).catch(() => {});
  }
  await markClipboardYoinkNow();
  await chrome.tabs.create({ url: "https://claude.ai/new", active: true });

  // Shared helper handles first-yoink-vs-subsequent copy + atomically marks
  // the has_completed_first_yoink flag. Same code is called from content.js
  // so the in-page YouTube button gets the same first-time CTA.
  const message = await STC.buildUoinkedMessage(data, copied);
  notify("Uoinked ★", message);
  await publishPopupResult(job, { ok: true, message: "Uoinked ★ Paste in Claude." });
}

// E7: a thrown capture request is not proof the helper is down. Say what it
// means: still working (we stopped waiting), lost track, or offline (only
// when the /health ping fails too, with platform-aware start copy).
// Returns the {kind, title, label, message} it showed.
async function notifyThrownCaptureError(e, extraOptions) {
  const failure = await STC.describeCaptureError(e);
  await notify(failure.title, failure.message, extraOptions);
  return failure;
}

// A2: the one honest, persistent "X walled it" message. requireInteraction
// keeps the Chrome notification on screen until the user dismisses it, so the
// walled capture is never a silent no-op. Copy is plain (no em/en dashes,
// Voice DNA) and actionable: open the article and click the in-page button.
function notifyWalledXArticle() {
  return notify(
    "Couldn't capture this X Article",
    "X blocks logged-out link fetches, so Uoink can't read it from a pasted "
      + "link. Open the article and click the \"Uoink this article\" button on "
      + "the page (bottom-right) to save it from your logged-in session. "
      + "Nothing was saved.",
    { requireInteraction: true });
}

// Chrome's lastError when nothing in the tab listens for the message.
const NO_RECEIVER_RE = /Receiving end does not exist|Could not establish connection/i;

// Message a tab and resolve {resp, noReceiver}: resp is the response (or null
// if the content script errors / doesn't answer), noReceiver is true when the
// content script isn't in the tab at all. Mirrors the popup's messageActiveTab.
function messageTab(tabId, payload) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, payload, (resp) => {
        const err = chrome.runtime.lastError;
        resolve({
          resp: resp || null,
          noReceiver: !!err && NO_RECEIVER_RE.test(String(err.message || "")),
        });
      });
    } catch { resolve({ resp: null, noReceiver: false }); }
  });
}

// E2: a tab open since before the extension was installed or updated never
// got the declared content scripts. Inject the article parser and its
// content script (host permission + "scripting"); true if they ran.
async function injectXArticleScripts(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["lib/x-article.js", "content-x-article.js"],
    });
    return true;
  } catch (e) {
    console.warn("[stc] x-article script injection failed", e);
    return false;
  }
}

// A1: capture an X Article from the context menu the same way the in-page
// button and the popup do — parse the rendered Article DOM out of the user's
// authenticated session first (side-steps X's login wall), and only fall back
// to the best-effort /extract/page fetch when the in-page parser isn't
// available. A walled fallback reports honestly (A2) instead of saving junk.
async function captureXArticleFromTab(tabId, pageUrl) {
  // 1) PRIMARY — in-page DOM parse via content-x-article.js. E2: with no
  // receiver in the tab, inject the script and ask once more.
  const ask = { type: "uoinkParseXArticle" };
  let reply = await messageTab(tabId, ask);
  if (reply.noReceiver && await injectXArticleScripts(tabId)) {
    reply = await messageTab(tabId, ask);
  }
  const resp = reply.resp;
  const parsed = (resp && resp.ok && resp.article && resp.article.ok)
    ? resp.article : null;
  if (parsed) {
    let data;
    try {
      data = await STC.postExtractXArticle(parsed);
    } catch (e) {
      console.error("[stc] context-menu x-article capture failed", e);
      await notifyThrownCaptureError(e, { requireInteraction: true });
      return;
    }
    if (data && data.ok) {
      const imgs = Number(data.image_count) || 0;
      const extra = imgs ? ` (${imgs} image${imgs === 1 ? "" : "s"})` : "";
      notify("Uoinked ★", `Saved the X Article${extra} to your library.`);
      tryOpenPopup();
      return;
    }
    notify("Uoink failed",
           STC.describeFailure(data)
             || "Read the article but couldn't save it. Try again.",
           { requireInteraction: true });
    return;
  }

  // 2) FALLBACK — best-effort /extract/page. Honest on a login wall (A2).
  let pageData;
  try {
    pageData = await STC.postExtractPage(pageUrl);
  } catch (e) {
    console.error("[stc] context-menu x-article page fallback failed", e);
    await notifyThrownCaptureError(e, { requireInteraction: true });
    return;
  }
  if (pageData && pageData.code === "x_login_wall") {
    await notifyWalledXArticle();
    return;
  }
  if (pageData && pageData.code === "host_not_allowed") {
    // X hosts ship in the default allowlist, so this is unlikely here; still,
    // don't dead-end — point at the reliable in-page path.
    await notifyWalledXArticle();
    return;
  }
  if (!pageData || !pageData.ok) {
    notify("Uoink failed",
           STC.describeFailure(pageData)
             || "X didn't serve this article to Uoink. Open it and use the "
               + "in-page \"Uoink this article\" button while logged in.",
           { requireInteraction: true });
    return;
  }
  // Rare success (a genuinely readable page): copy + open like a normal page.
  const clipboardText = pageData.corpus_md_paste || pageData.yoink_md;
  if (clipboardText) {
    await rememberClipboardBudget(pageData, clipboardText);
    const copied = await copyToClipboard(clipboardText);
    const message = await STC.buildUoinkedMessage(pageData, copied);
    notify("Uoinked ★", message);
  } else {
    notify("Uoinked ★", "Saved the article to your library.");
  }
  tryOpenPopup();
}

// Fetches /settings on demand and returns true if the picker is enabled.
// Cheap (local request) and called once per job, so we don't bother caching
// here — the SW gets recycled often anyway.
async function _useScreenshotPicker() {
  try {
    const res = await STC.getSettings();
    return !!(res && res.ok && res.settings &&
              res.settings.smart_screenshot_picker_enabled === true);
  } catch (e) {
    console.warn("[Uoink] settings fetch failed, picker disabled by default", e);
    return false;
  }
}

async function runSessionAddJob(job) {
  let data;
  try {
    data = await STC.addToSession(job.session_id, job.url, job.interval);
  } catch (e) {
    console.error("[Uoink] session add request failed", e);
    await notifyThrownCaptureError(e);
    return;
  }
  if (!data || !data.ok) {
    notify("Uoink failed", STC.describeFailure(data));
    return;
  }

  await setState({
    current: { ...job, startedAt: Date.now(), title: data.title || null },
  });

  const sessionName = job.session_name || job.session_id;
  notify("Added to session", `${sessionName} · ${data.video_count} video${data.video_count === 1 ? "" : "s"}`);

  // Pull fresh active session state into local storage so popup + menu update.
  await refreshActiveSession();
}
