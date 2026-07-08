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
      notify("Uoink", "No active session. Start one in the popup first.");
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
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;
  if (msg.target === "offscreen") return;

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
        sendResponse({ networkError: String(e && e.message || e) });
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
        sendResponse({ data });
        if (data && data.ok) tryOpenPopup();
      } catch (e) {
        console.error("[stc] proxied x-article extract failed", e);
        sendResponse({ networkError: String(e && e.message || e) });
      }
    })();
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
        sendResponse({ networkError: String(e && e.message || e) });
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

async function _doEnqueue(job) {
  const state = await getState();
  state.queue.push(job);
  await setState({ queue: state.queue });

  const ahead = (state.busy ? 1 : 0) + state.queue.length - 1;
  if (state.busy || state.queue.length > 1) {
    notify("Uoink queued", `${ahead} video${ahead === 1 ? "" : "s"} ahead`);
  } else {
    notify("Uoinking", `${shortUrl(job.url)}...`);
  }
  drain();
}

async function clearQueue() {
  await setState({ queue: [] });
  notify("Uoink", "Queue cleared.");
}

async function restoreQueue() {
  const state = await getState();
  if (state.busy) await setState({ busy: false, current: null });
  if (state.queue && state.queue.length) drain();
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
  try {
    while (true) {
      const state = await getState();
      if (!state.queue.length) {
        await setState({ busy: false, current: null });
        checkHealthAndUpdateBadge().catch(() => {});
        return;
      }
      const job = state.queue.shift();
      const newQueue = state.queue;
      const current = { ...job, startedAt: Date.now() };
      await setState({ busy: true, current, queue: newQueue });
      checkHealthAndUpdateBadge().catch(() => {});

      try {
        await runJob(job);
      } catch (e) {
        console.error("[Uoink] job crashed", e);
        notify("Uoink failed", String(e));
      }
    }
  } finally {
    _draining.running = false;
  }
}

async function runJob(job) {
  if (job.kind === "session_add") return runSessionAddJob(job);
  return runExtractJob(job);
}

async function runExtractJob(job) {
  let data;
  try {
    if (job.usePage) {
      data = await STC.postExtractPage(job.url);
    } else if (job.useExtractAny) {
      data = await STC.postExtractAny(job.url, job.interval);
    } else if (job.useReddit) {
      data = await STC.postExtractReddit(job.url, job.interval);
    } else {
      data = await STC.postExtract(job.url, job.interval);
    }
  } catch (e) {
    console.error("[Uoink] server unreachable", e);
    // No tab open here -- setup.html only opens from direct user actions
    // (the in-page YouTube button or the popup help link), never from
    // background-queued jobs. Keeps unrelated context-menu work from
    // surprising the user with new tabs.
    notify("Uoink Helper offline",
           "Start Uoink from the Start Menu, then try again.");
    return;
  }
  if (!data || !data.ok) {
    // A2: an X login wall (or a pasted X link X won't serve logged-out) is not
    // a generic failure — it's honest and actionable. Say what happened and
    // what to do, and make it persistent so it isn't a toast that vanishes.
    if (data && data.code === "x_login_wall") {
      await notifyWalledXArticle();
      return;
    }
    notify("Uoink failed", STC.friendlyError(data && data.error),
           { requireInteraction: true });
    return;
  }
  if (data.queued) {
    const id = await notify("Uoink queued", `${queuedMessage(data)} Click View queue for status.`, {
      buttons: [{ title: "View queue" }],
    });
    if (id) _queueViewNotificationIds.add(id);
    return;
  }

  await setState({ current: { ...job, startedAt: Date.now(), title: data.title || null } });

  // Sprint 3: Smart Screenshot Picker intercept. When the user has the
  // picker setting enabled, we hand the corpus off to the popup instead of
  // auto-copying. Default off keeps v1 behavior byte-identical.
  if (await _useScreenshotPicker()) {
    await rememberClipboardBudget(data, data.corpus_md_paste || data.yoink_md);
    await STC.stashPickerCorpus(data);
    notify("Uoink ready",
           "Click the Uoink icon to pick which screenshots to include.");
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
    return;
  }
  await markClipboardYoinkNow();
  await chrome.tabs.create({ url: "https://claude.ai/new", active: true });

  // Shared helper handles first-yoink-vs-subsequent copy + atomically marks
  // the has_completed_first_yoink flag. Same code is called from content.js
  // so the in-page YouTube button gets the same first-time CTA.
  const message = await STC.buildUoinkedMessage(data, copied);
  notify("Uoinked ★", message);
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

// Message a tab and resolve the response (or null if the content script isn't
// there / errors). Mirrors the popup's messageActiveTab.
function messageTab(tabId, payload) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, payload, (resp) => {
        void chrome.runtime.lastError; // no listener -> lastError; treat as null
        resolve(resp || null);
      });
    } catch { resolve(null); }
  });
}

// A1: capture an X Article from the context menu the same way the in-page
// button and the popup do — parse the rendered Article DOM out of the user's
// authenticated session first (side-steps X's login wall), and only fall back
// to the best-effort /extract/page fetch when the in-page parser isn't
// available. A walled fallback reports honestly (A2) instead of saving junk.
async function captureXArticleFromTab(tabId, pageUrl) {
  // 1) PRIMARY — in-page DOM parse via content-x-article.js.
  const resp = await messageTab(tabId, { type: "uoinkParseXArticle" });
  const parsed = (resp && resp.ok && resp.article && resp.article.ok)
    ? resp.article : null;
  if (parsed) {
    let data;
    try {
      data = await STC.postExtractXArticle(parsed);
    } catch (e) {
      console.error("[stc] context-menu x-article capture failed", e);
      notify("Uoink Helper offline",
             "Start Uoink from the Start Menu, then try again.",
             { requireInteraction: true });
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
           STC.friendlyError(data && data.error)
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
    notify("Uoink Helper offline",
           "Start Uoink from the Start Menu, then try again.",
           { requireInteraction: true });
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
           STC.friendlyError(pageData && pageData.error)
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
    console.error("[Uoink] server unreachable", e);
    notify("Uoink Helper offline",
           "Start Uoink from the Start Menu, then try again.");
    return;
  }
  if (!data || !data.ok) {
    notify("Uoink failed", STC.friendlyError(data && data.error));
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
