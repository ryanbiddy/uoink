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

importScripts("lib/extract.js");

const MENU_LINK = "stc-extract-link";
const MENU_PAGE = "stc-extract-page";
const MENU_SESSION = "stc-extract-session";
const ICON_URL = chrome.runtime.getURL("icons/icon128.png");
const OFFSCREEN_URL = "offscreen.html";

const LINK_PATTERNS = [
  "https://www.youtube.com/watch*",
  "https://youtu.be/*",
  "https://www.youtube.com/shorts/*",
  "https://m.youtube.com/watch*",
];
const PAGE_PATTERNS = [
  "https://www.youtube.com/watch*",
  "https://www.youtube.com/shorts/*",
];

// ---- Lifecycle ------------------------------------------------------------
chrome.runtime.onInstalled.addListener(async () => {
  await rebuildContextMenus();
  await refreshActiveSession();
  restoreQueue().catch((e) => console.warn("[stc] restore failed", e));
});

chrome.runtime.onStartup.addListener(async () => {
  await rebuildContextMenus();
  await refreshActiveSession();
  restoreQueue().catch((e) => console.warn("[stc] restore failed", e));
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.active_session) {
    rebuildContextMenus().catch((e) => console.warn("[stc] menu rebuild failed", e));
  }
});

// ---- Context menus -------------------------------------------------------
async function rebuildContextMenus() {
  await new Promise((r) => chrome.contextMenus.removeAll(r));

  chrome.contextMenus.create({
    id: MENU_LINK,
    title: "Send to Claude (extract this video)",
    contexts: ["link"],
    targetUrlPatterns: LINK_PATTERNS,
  });
  chrome.contextMenus.create({
    id: MENU_PAGE,
    title: "Send to Claude (extract this page)",
    contexts: ["page", "video"],
    documentUrlPatterns: PAGE_PATTERNS,
  });

  const active = await getActiveFromStorage();
  if (active && active.id) {
    const name = active.name || active.id;
    chrome.contextMenus.create({
      id: MENU_SESSION,
      title: `Send to Claude (add to session: ${name})`,
      contexts: ["link", "page", "video"],
      targetUrlPatterns: LINK_PATTERNS,
      documentUrlPatterns: PAGE_PATTERNS,
    });
  }
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  // Decide raw URL by menu id.
  let raw = null;
  let kind = "extract";

  if (info.menuItemId === MENU_LINK) {
    raw = info.linkUrl;
    kind = "extract";
  } else if (info.menuItemId === MENU_PAGE) {
    raw = info.pageUrl || (tab && tab.url);
    kind = "extract";
  } else if (info.menuItemId === MENU_SESSION) {
    raw = info.linkUrl || info.pageUrl || (tab && tab.url);
    kind = "session_add";
  } else {
    return;
  }

  const normalized = STC.normalizeYouTubeUrl(raw || "");
  if (!normalized) {
    notify("Send to Claude — invalid URL",
           "Couldn't find a YouTube video ID in that link.");
    return;
  }

  const interval = await STC.getInterval();
  const job = { kind, url: normalized, interval, addedAt: Date.now() };
  if (kind === "session_add") {
    const active = await getActiveFromStorage();
    if (!active || !active.id) {
      notify("Send to Claude", "No active session — start one in the popup first.");
      return;
    }
    job.session_id = active.id;
    job.session_name = active.name;
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

  if (msg.type === "notify") {
    notify(msg.title || "Send to Claude", msg.message || "")
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

  // Content-script-proxied extract calls. Page-context fetches from YouTube
  // can be killed by client-side blockers (Chrome tracking protection, AV
  // web shields) before reaching the loopback server. The SW is in the
  // extension origin and not subject to those filters.
  if (msg.type === "stcExtract" && msg.url) {
    (async () => {
      try {
        const data = await STC.postExtract(msg.url, msg.interval);
        sendResponse({ data });
      } catch (e) {
        console.error("[stc] proxied extract failed", e);
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
      } catch (e) {
        console.error("[stc] proxied session add failed", e);
        sendResponse({ networkError: String(e && e.message || e) });
      }
    })();
    return true;
  }
});

// ---- Notifications -------------------------------------------------------
function notify(title, message) {
  return new Promise((resolve) => {
    try {
      chrome.notifications.create({
        type: "basic",
        iconUrl: ICON_URL,
        title,
        message,
        priority: 1,
      }, (id) => resolve(id));
    } catch (e) {
      console.warn("[stc] notification failed", e);
      resolve(null);
    }
  });
}

// ---- Offscreen clipboard -------------------------------------------------
async function ensureOffscreen() {
  if (chrome.offscreen && chrome.offscreen.hasDocument) {
    if (await chrome.offscreen.hasDocument()) return;
  } else {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ["OFFSCREEN_DOCUMENT"],
    });
    if (contexts && contexts.length) return;
  }
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ["CLIPBOARD"],
    justification: "Write extracted transcript to the system clipboard.",
  });
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
  } finally {
    try { await chrome.offscreen.closeDocument(); } catch { /* ignore */ }
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
    notify("Send to Claude — queued", `Queued — ${ahead} video${ahead === 1 ? "" : "s"} ahead.`);
  } else {
    const verb = job.kind === "session_add" ? "Adding to session" : "Extracting";
    notify("Send to Claude — starting", `${verb}: ${shortUrl(job.url)}...`);
  }
  drain();
}

async function clearQueue() {
  await setState({ queue: [] });
  notify("Send to Claude", "Queue cleared.");
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
        return;
      }
      const job = state.queue.shift();
      const newQueue = state.queue;
      const current = { ...job, startedAt: Date.now() };
      await setState({ busy: true, current, queue: newQueue });

      try {
        await runJob(job);
      } catch (e) {
        console.error("[stc] job crashed", e);
        notify("Send to Claude — failed", String(e));
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
    data = await STC.postExtract(job.url, job.interval);
  } catch (e) {
    console.error("[stc] server unreachable", e);
    notify("Send to Claude — server offline",
           `Couldn't reach ${STC.SERVER}. Run start_server.bat in the yoink folder.`);
    return;
  }
  if (!data || !data.ok) {
    notify("Send to Claude — failed", (data && data.error) || "Unknown server error.");
    return;
  }

  await setState({ current: { ...job, startedAt: Date.now(), title: data.title || null } });

  const copied = await copyToClipboard(data.combined_md);
  await chrome.tabs.create({ url: "https://claude.ai/new", active: true });

  const shotsLine = `${data.screenshot_count} screenshots saved.`;
  const clipLine = copied
    ? "Transcript copied. Paste with Ctrl+V in the new tab."
    : "Transcript NOT copied (clipboard blocked). Open combined.md in the folder.";
  notify("Ready in Claude", `${clipLine} Screenshots folder is open in Explorer. ${shotsLine}`);
}

async function runSessionAddJob(job) {
  let data;
  try {
    data = await STC.addToSession(job.session_id, job.url, job.interval);
  } catch (e) {
    console.error("[stc] server unreachable", e);
    notify("Send to Claude — server offline",
           `Couldn't reach ${STC.SERVER}. Run start_server.bat in the yoink folder.`);
    return;
  }
  if (!data || !data.ok) {
    notify("Send to Claude — failed", (data && data.error) || "Unknown server error.");
    return;
  }

  await setState({
    current: { ...job, startedAt: Date.now(), title: data.title || null },
  });

  const sessionName = job.session_name || job.session_id;
  notify("Added to session",
         `${sessionName} · ${data.video_count} video${data.video_count === 1 ? "" : "s"} so far. ` +
         `(${data.screenshot_count} screenshots, ${data.caption_count || 0} caption lines)`);

  // Pull fresh active session state into local storage so popup + menu update.
  await refreshActiveSession();
}
