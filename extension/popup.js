// Popup script. STC.* helpers come from lib/extract.js loaded just before.

// ---- v2 dev flag ----------------------------------------------------------
// FLIP TO FALSE WHEN CODEX BACKEND LANDS.
// Routes STC.playlist* / STC.jobStatus / STC.jobCancel through the local mock
// layer (lib/mock-api.js) instead of the real server. See docs/v2-api.md
// (lands on codex/v2-backend-playlist) for the contract these mocks shadow.
const USE_MOCK_API = false;
globalThis.YOINK_USE_MOCK_API = USE_MOCK_API;

const DEFAULT_INTERVAL = 30;
const CORPUS_WARN_CHARS = 500_000;

// Sprint 3: Comment Intelligence + Hook Type background-work indicator.
// Both features land their analysis after extraction completes; Hook Type
// now waits for comments too (post-Sprint-3-backend decision), so the
// "still running" copy is the same for both. Returns the user-facing
// string given the settings snapshot, or "" if neither feature is on.
// Used by the playlist done panel AND the picker's done state.
function buildBackgroundAiIndicator(settings) {
  if (!settings) return "";
  const ci = !!settings.comment_intelligence_enabled;
  const hook = !!settings.hook_type_enabled;
  // Skip the indicator entirely if no key is set â€” the features won't run.
  if ((ci || hook) && settings.anthropic_key_set === false) return "";
  if (ci && hook) {
    return "Comment Intelligence and Hook Type are still running in the " +
      "background â€” re-open per-video .md files in a few minutes for the " +
      "full analysis.";
  }
  if (ci) {
    return "Comment Intelligence is still running in the background â€” " +
      "re-open per-video .md files in a few minutes for analysis.";
  }
  if (hook) {
    return "Hook Type analysis is still running in the background â€” " +
      "re-open per-video .md files in a few minutes.";
  }
  return "";
}

// ---- DOM handles ----------------------------------------------------------
const dot = document.getElementById("dot");
const status = document.getElementById("status");
const intervalInput = document.getElementById("interval");
const saved = document.getElementById("saved");

const sessionInactive = document.getElementById("session-inactive");
const sessionActive = document.getElementById("session-active");
const startSection = document.getElementById("start-section");
const sessionNameInput = document.getElementById("session-name");
const startBtn = document.getElementById("start-session");
const recentSessionsEl = document.getElementById("recent-sessions");

const activeNameEl = document.getElementById("active-name");
const activeMetaEl = document.getElementById("active-meta");
const recentAdditionsEl = document.getElementById("recent-additions");
const promptsEl = document.getElementById("prompts");
const endBtn = document.getElementById("end-session");
const cancelBtn = document.getElementById("cancel-session");
const sessionWarn = document.getElementById("session-warn");

const currentEl = document.getElementById("current-job");
const queueEl = document.getElementById("queue-depth");
const clearBtn = document.getElementById("clear-queue");
const backfillBanner = document.getElementById("backfill-banner");
const backfillText = document.getElementById("backfill-text");
const backfillDismiss = document.getElementById("backfill-dismiss");
const backfillCancel = document.getElementById("backfill-cancel");
const queueStatusBanner = document.getElementById("queue-status-banner");
const queueBannerMain = document.getElementById("queue-banner-main");
const queueBannerText = document.getElementById("queue-banner-text");
const queueBannerToggle = document.getElementById("queue-banner-toggle");
const queueBannerActions = document.getElementById("queue-banner-actions");
const queueDetails = document.getElementById("queue-details");
const firstUoinkPanel = document.getElementById("first-uoink-panel");
const currentVideoPreview = document.getElementById("current-video-preview");
const uoinkCurrentBtn = document.getElementById("uoink-current-btn");
const destinationPanel = document.getElementById("destination-panel");
const quickPromptsPanel = document.getElementById("quick-prompts-panel");
const recentPanel = document.getElementById("recent-panel");
const moreOptions = document.getElementById("more-options");
const modeSelectorWrap = document.getElementById("mode-selector-wrap");

// ---- Server status --------------------------------------------------------
const statusHelp = document.getElementById("status-help");
const sendClaudeBtn = document.getElementById("send-claude");
const sendChatgptBtn = document.getElementById("send-chatgpt");
const destHint = document.getElementById("dest-hint");
const clipboardBudgetEl = document.getElementById("clipboard-budget");
const DEST_HINT_DEFAULT = destHint ? destHint.textContent : "";
const DEST_DISABLED_TIP = "Uoink a video first";
const LAST_YOINK_CLIPBOARD_KEY = "yoink_last_clipboard_at";
const LAST_CLIPBOARD_BUDGET_KEY = "yoink_last_clipboard_budget";
const LAST_UOINK_WINDOW_MS = 5 * 60 * 1000;
let currentMode = "single";
const RECENT_FAILURES_KEY = "yoink_recent_failures";
const BACKFILL_DISMISSED_KEY = "yoink_backfill_dismissed_signature";
const MORE_OPTIONS_OPEN_KEY = "yoink_popup_more_options_open";
const QUEUE_EXPANDED_KEY = "yoink_popup_queue_expanded";
let serverOnline = false;
let isTier2 = false;
let lastUoinkAt = 0;
let lastClipboardBudget = null;
let currentVideoUrl = null;
let queueExpanded = false;
let knownRecentUoinkCount = 0;

// Make a link-styled control (an <a role="button">) keyboard-operable:
// Enter or Space fires the element's existing click handler. Mirrors the
// keydown wiring on #active-playlist-pill.
function wireKeyActivation(el) {
  if (!el) return;
  el.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      el.click();
    }
  });
}

function hasRecentClipboardUoink() {
  return !!lastUoinkAt && Date.now() - lastUoinkAt <= LAST_UOINK_WINDOW_MS;
}

function updateDestButtons() {
  const recent = hasRecentClipboardUoink();
  const enabled = serverOnline && recent;
  for (const b of [sendClaudeBtn, sendChatgptBtn]) {
    if (!b) continue;
    b.disabled = !enabled;
    b.title = enabled
      ? ""
      : (serverOnline ? DEST_DISABLED_TIP : "Server must be running to uoink");
  }
  if (destHint) {
    if (!serverOnline) {
      destHint.textContent = "Start Uoink Server to enable these.";
    } else if (!recent) {
      destHint.textContent = "Uoink a video first. Destinations unlock for 5 minutes after a successful copy.";
    } else {
      destHint.textContent = DEST_HINT_DEFAULT;
    }
  }
}

function formatTokenEstimate(tokens) {
  return globalThis.UoinkUI.formatTokenEstimate(tokens);
}

function screenshotCountFromData(data, text) {
  return globalThis.UoinkUI.screenshotCountFromData(data, text);
}

function clipboardBudgetFromData(data, clipboardText) {
  return globalThis.UoinkUI.clipboardBudgetFromData(data, clipboardText);
}

function renderClipboardBudget() {
  if (!clipboardBudgetEl) return;
  if (!lastClipboardBudget || !hasRecentClipboardUoink()) {
    clipboardBudgetEl.classList.add("hidden");
    clipboardBudgetEl.textContent = "";
    clipboardBudgetEl.classList.remove("warn");
    return;
  }
  const screenshots = Number(lastClipboardBudget.screenshotCount) || 0;
  const tokens = Number(lastClipboardBudget.tokenEstimate) || 0;
  const tokenText = formatTokenEstimate(tokens) || "unknown";
  const shotLabel = `${screenshots} screenshot${screenshots === 1 ? "" : "s"}`;
  clipboardBudgetEl.textContent = `${shotLabel} \u00b7 ~${tokenText} tokens`;
  if (tokens > 50_000) {
    clipboardBudgetEl.textContent += " \u00b7 Large paste - Claude may truncate.";
    clipboardBudgetEl.classList.add("warn");
  } else {
    clipboardBudgetEl.classList.remove("warn");
  }
  clipboardBudgetEl.classList.remove("hidden");
}

function saveClipboardBudget(data, clipboardText) {
  const budget = clipboardBudgetFromData(data, clipboardText);
  if (!budget) return;
  lastClipboardBudget = budget;
  renderClipboardBudget();
  try {
    chrome.storage.local.set({ [LAST_CLIPBOARD_BUDGET_KEY]: budget });
  } catch { /* ignore */ }
}

function markClipboardUoinkNow() {
  lastUoinkAt = Date.now();
  updateDestButtons();
  renderClipboardBudget();
  updateFocalMode();
  try {
    chrome.storage.local.set({ [LAST_YOINK_CLIPBOARD_KEY]: lastUoinkAt });
  } catch { /* ignore */ }
}

try {
  chrome.storage.local.get({
    [LAST_YOINK_CLIPBOARD_KEY]: 0,
    [LAST_CLIPBOARD_BUDGET_KEY]: null,
  }, (items) => {
    lastUoinkAt = Number(items && items[LAST_YOINK_CLIPBOARD_KEY]) || 0;
    lastClipboardBudget = (items && items[LAST_CLIPBOARD_BUDGET_KEY]) || null;
    updateDestButtons();
    renderClipboardBudget();
    updateFocalMode();
  });
} catch { /* ignore */ }

function isVersionAtLeast(v1, v2) {
  if (!v1) return false;
  const parts1 = String(v1).split('-')[0].split('.').map(Number);
  const parts2 = String(v2).split('-')[0].split('.').map(Number);
  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0;
    const p2 = parts2[i] || 0;
    if (p1 > p2) return true;
    if (p1 < p2) return false;
  }
  return true;
}

async function ping() {
  const data = await STC.ping();
  const helperDownCard = document.getElementById("helper-down-card");
  const modeSelector = document.getElementById("mode-selector-wrap");
  const modeSingle = document.getElementById("mode-single");
  const modePlaylist = document.getElementById("mode-playlist");

  if (data && data.ok) {
    serverOnline = true;
    dot.classList.remove("down"); dot.classList.add("up");
    status.textContent = "Uoink Helper is running.";
    if (helperDownCard) helperDownCard.classList.add("hidden");
    if (modeSelector) modeSelector.classList.remove("hidden");
    if (modeSingle) {
      if (currentMode === "single") modeSingle.classList.remove("hidden");
    }
    if (modePlaylist) {
      if (currentMode === "playlist") modePlaylist.classList.remove("hidden");
    }
    updateDestButtons();
    if (uoinkCurrentBtn && currentVideoUrl) uoinkCurrentBtn.disabled = false;

    // Detect Tier 2 dashboard support
    const oldTier2 = isTier2;
    isTier2 = (data.tier_2_dashboard === true) || 
              (data.version && isVersionAtLeast(data.version, "2.2.0"));

    const openDashboardLink = document.getElementById("open-dashboard");
    const openIndexLink = document.getElementById("open-index");
    if (openDashboardLink) openDashboardLink.classList.toggle("hidden", !isTier2);
    if (openIndexLink) openIndexLink.classList.toggle("hidden", isTier2);

    if (oldTier2 !== isTier2) {
      // Re-initialize queue status polling under the new mode
      startQueueStatusPolling();
    }
  } else {
    serverOnline = false;
    isTier2 = false;
    dot.classList.remove("up"); dot.classList.add("down");
    status.textContent = "Helper offline.";
    if (helperDownCard) helperDownCard.classList.remove("hidden");
    if (modeSelector) modeSelector.classList.add("hidden");
    if (modeSingle) modeSingle.classList.add("hidden");
    if (modePlaylist) modePlaylist.classList.add("hidden");
    updateDestButtons();
    if (uoinkCurrentBtn) uoinkCurrentBtn.disabled = true;

    const openDashboardLink = document.getElementById("open-dashboard");
    const openIndexLink = document.getElementById("open-index");
    if (openDashboardLink) openDashboardLink.classList.add("hidden");
    if (openIndexLink) openIndexLink.classList.remove("hidden");
    
    stopQueueStatusPolling();
  }
}

if (statusHelp) {
  statusHelp.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({
      url: chrome.runtime.getURL("setup.html?source=offline"),
      active: true,
    });
    window.close();
  });
  wireKeyActivation(statusHelp);
}

const troubleshootSetupBtn = document.getElementById("troubleshoot-setup-btn");
if (troubleshootSetupBtn) {
  troubleshootSetupBtn.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({
      url: chrome.runtime.getURL("setup.html?source=offline"),
      active: true,
    });
    window.close();
  });
}

function isFirstLoadUser() {
  return knownRecentUoinkCount <= 0 && !hasRecentClipboardUoink();
}

function updateFocalMode() {
  const firstLoad = isFirstLoadUser();
  if (firstUoinkPanel) firstUoinkPanel.classList.toggle("hidden", !firstLoad);
  if (destinationPanel) destinationPanel.classList.toggle("hidden", firstLoad);
  if (quickPromptsPanel) quickPromptsPanel.classList.toggle("hidden", firstLoad);
  if (recentPanel) recentPanel.classList.toggle("hidden", firstLoad);
  if (modeSelectorWrap) modeSelectorWrap.classList.toggle("hidden", firstLoad);
}

function readMoreOptionsState() {
  if (!moreOptions) return;
  try {
    chrome.storage.local.get({ [MORE_OPTIONS_OPEN_KEY]: false }, (items) => {
      moreOptions.open = !!(items && items[MORE_OPTIONS_OPEN_KEY]);
    });
  } catch { /* ignore */ }
}

if (moreOptions) {
  moreOptions.addEventListener("toggle", () => {
    try {
      chrome.storage.local.set({ [MORE_OPTIONS_OPEN_KEY]: !!moreOptions.open });
    } catch { /* ignore */ }
  });
}

async function loadCurrentVideoPreview() {
  if (!currentVideoPreview || !uoinkCurrentBtn) return;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    const url = tab && tab.url;
    const normalized = STC.normalizeYouTubeUrl(url || "");
    currentVideoUrl = normalized;
    if (!normalized) {
      currentVideoPreview.textContent = "Open a YouTube video tab, then reopen this popup.";
      uoinkCurrentBtn.disabled = true;
      return;
    }
    currentVideoPreview.textContent = (tab.title || "YouTube video").replace(/\s+-\s+YouTube\s*$/i, "");
    uoinkCurrentBtn.disabled = !serverOnline;
  } catch {
    currentVideoPreview.textContent = "Couldn't read the current tab.";
    uoinkCurrentBtn.disabled = true;
  }
}

// ---- Interval setting -----------------------------------------------------
function loadInterval() {
  chrome.storage.sync.get({ interval: DEFAULT_INTERVAL }, (items) => {
    let n = parseInt(items.interval, 10);
    if (!Number.isFinite(n) || n < 5 || n > 300) n = DEFAULT_INTERVAL;
    intervalInput.value = n;
  });
}
let saveTimer = null;
function showSaved() {
  saved.classList.add("show");
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saved.classList.remove("show"), 1200);
}
intervalInput.addEventListener("change", () => {
  let n = parseInt(intervalInput.value, 10);
  if (!Number.isFinite(n)) n = DEFAULT_INTERVAL;
  n = Math.max(5, Math.min(300, n));
  intervalInput.value = n;
  chrome.storage.sync.set({ interval: n }, showSaved);
});

// ---- Session UI -----------------------------------------------------------
let activeSession = null;

function fmtCount(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function shortLabel(url) {
  try {
    const u = new URL(url);
    const id = u.searchParams.get("v");
    return id ? `youtu.be/${id}` : url;
  } catch { return url; }
}

function renderActive(session) {
  activeSession = session;
  if (!session) {
    sessionActive.classList.add("hidden");
    sessionInactive.classList.remove("hidden");
    return;
  }
  sessionInactive.classList.add("hidden");
  sessionActive.classList.remove("hidden");
  activeNameEl.textContent = session.name || session.id;
  activeMetaEl.textContent = `${fmtCount(session.video_count || 0, "video")} added`;

  const recent = session.recent || [];
  recentAdditionsEl.innerHTML = "";
  if (!recent.length) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.style.cssText = "font-size:11px;padding:4px 6px";
    empty.textContent = "No videos yet.";
    recentAdditionsEl.appendChild(empty);
  } else {
    for (const v of recent) {
      const item = document.createElement("div");
      item.className = "recent-item";
      item.title = v.url || "";
      item.textContent = v.title || shortLabel(v.url || "");
      recentAdditionsEl.appendChild(item);
    }
  }
}

async function refreshActiveFromServer() {
  // Ask the background to repull from the server and update storage.
  // Background also fires the storage.onChanged event; we just need to read it.
  try {
    await chrome.runtime.sendMessage({ type: "refreshActiveSession" });
  } catch { /* ignore â€” fall back to local storage */ }
  const s = await readActiveFromStorage();
  renderActive(s);
}

function readActiveFromStorage() {
  return new Promise((resolve) => {
    chrome.storage.local.get({ active_session: null }, (items) => {
      resolve(items.active_session || null);
    });
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.active_session) {
    renderActive(changes.active_session.newValue || null);
  }
  if (area === "local" && changes[LAST_YOINK_CLIPBOARD_KEY]) {
    lastUoinkAt = Number(changes[LAST_YOINK_CLIPBOARD_KEY].newValue) || 0;
    updateDestButtons();
    renderClipboardBudget();
    updateFocalMode();
  }
  if (area === "local" && changes[LAST_CLIPBOARD_BUDGET_KEY]) {
    lastClipboardBudget = changes[LAST_CLIPBOARD_BUDGET_KEY].newValue || null;
    renderClipboardBudget();
  }
});

// ---- Start session --------------------------------------------------------
startBtn.addEventListener("click", async () => {
  const name = (sessionNameInput.value || "").trim();
  startBtn.disabled = true;
  startBtn.textContent = "Starting...";
  try {
    const res = await STC.startSession(name);
    if (!res || !res.ok) {
      const msg = (res && res.error) || "Failed to start session.";
      showToast(msg);
      return;
    }
    sessionNameInput.value = "";
    if (startSection.hasAttribute("open")) startSection.removeAttribute("open");
    await refreshActiveFromServer();
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = "Start session";
  }
});

// ---- Cancel session -------------------------------------------------------
cancelBtn.addEventListener("click", async () => {
  if (!activeSession) return;
  if (!confirm(`Cancel session "${activeSession.name}"? Files stay on disk; no corpus will be generated.`)) return;
  cancelBtn.disabled = true;
  try {
    await STC.cancelSession(activeSession.id);
    await refreshActiveFromServer();
    await loadRecentSessions();
  } finally {
    cancelBtn.disabled = false;
  }
});

// ---- End session ----------------------------------------------------------
endBtn.addEventListener("click", async () => {
  if (!activeSession) return;
  const id = activeSession.id;
  const name = activeSession.name || id;

  endBtn.disabled = true;
  endBtn.textContent = "Closing...";
  sessionWarn.classList.add("hidden");

  let res;
  try {
    res = await STC.closeSession(id);
  } catch (e) {
    showToast(`Couldn't reach server: ${e}`);
    endBtn.disabled = false;
    endBtn.textContent = "End session";
    return;
  }

  if (!res || !res.ok) {
    showToast((res && res.error) || "Failed to close session.");
    endBtn.disabled = false;
    endBtn.textContent = "End session";
    return;
  }

  // Copy via background (offscreen). Popups can call navigator.clipboard
  // directly too â€” try that first for the fast path, then fall back.
  let copied = false;
  try {
    await navigator.clipboard.writeText(res.corpus_md);
    copied = true;
  } catch {
    try {
      const r = await chrome.runtime.sendMessage({ type: "copyToClipboard", text: res.corpus_md });
      copied = !!(r && r.ok);
    } catch { /* leave copied false */ }
  }

  // Notify. The destination buttons up top let the user pick where to paste,
  // so we don't auto-open a tab here â€” that would force Claude.
  const lines = `${fmtCount(res.video_count, "video")}, ${fmtCount(res.caption_count || 0, "caption line")}`;
  const note = copied
    ? `Session uoinked! ${lines}. Pick a destination above and paste.`
    : `Session closed. ${lines}. Clipboard failed â€” corpus.md is in the session folder (already open in Explorer).`;
  await chrome.runtime.sendMessage({ type: "notify", title: "Research session uoinked", message: note });
  if (copied) {
    markClipboardUoinkNow();
    STC.logEngagement("paste", "popup", { length: res.corpus_md.length }).catch(() => {});
    showToast("Session uoinked! Pick a destination above.");
  }

  // Large-corpus warning
  if ((res.corpus_md || "").length > CORPUS_WARN_CHARS) {
    sessionWarn.classList.remove("hidden");
    sessionWarn.innerHTML =
      `Corpus is ${(res.corpus_md.length / 1000).toFixed(0)}K characters â€” may exceed the ` +
      `paste-friendly size. Drag <code>corpus.md</code> into Claude or ChatGPT instead.<br>` +
      `<button id="open-folder" class="secondary" style="margin-top:6px">Open session folder</button>`;
    document.getElementById("open-folder").addEventListener("click", () => {
      STC.openSession(id);
    });
  }

  endBtn.disabled = false;
  endBtn.textContent = "End session";
  await refreshActiveFromServer();
  await loadRecentSessions();
});

// ---- Recent sessions ------------------------------------------------------
async function loadRecentSessions() {
  const res = await STC.listSessions();
  recentSessionsEl.innerHTML = "";
  const all = (res && res.sessions) ? res.sessions : [];
  // Show last 5 closed/cancelled (skip the open one since it's shown above).
  const past = all.filter((s) => s.status !== "open").slice(0, 5);
  if (!past.length) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.style.cssText = "font-size:11px;padding:4px 6px";
    empty.textContent = "No past sessions yet.";
    recentSessionsEl.appendChild(empty);
    return;
  }
  for (const s of past) {
    const item = document.createElement("div");
    item.className = "recent-item";
    const date = (s.created_at || "").slice(0, 10);
    item.innerHTML = `<span>${escapeHtml(s.name || s.session_id)}</span>` +
                     `<span class="meta">${s.video_count} Â· ${s.status} Â· ${date}</span>`;
    item.title = s.folder || "";
    item.addEventListener("click", () => STC.openSession(s.session_id));
    recentSessionsEl.appendChild(item);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ---- Prompt library -------------------------------------------------------
// prompts.json is read fresh each time the popup opens. Users can edit it
// directly (see README) and the change shows up next time the popup is opened.
const quickPromptsEl = document.getElementById("quick-prompts");
const popupToast = document.getElementById("popup-toast");

function showToast(message) {
  if (!popupToast) return;
  popupToast.textContent = message;
  popupToast.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => popupToast.classList.remove("show"), 1800);
}

async function fetchPrompts() {
  try {
    const res = await fetch(chrome.runtime.getURL("prompts.json"));
    return await res.json();
  } catch (e) {
    console.warn("[popup] prompts.json missing or invalid", e);
    return [];
  }
}

function renderPromptList(targetEl, prompts) {
  targetEl.innerHTML = "";
  if (!prompts.length) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.style.cssText = "font-size:11px;padding:4px 6px";
    empty.textContent = "No prompts defined. Edit prompts.json to add some.";
    targetEl.appendChild(empty);
    return;
  }
  for (const p of prompts) {
    const body = p.prompt || p.text || "";
    const row = document.createElement("div");
    row.className = "prompt-item";

    const label = document.createElement("span");
    label.className = "prompt-label";
    label.title = body;
    label.textContent = p.label || p.id || "(untitled)";

    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(body);
        btn.textContent = "Copied";
        btn.classList.add("copied");
        showToast("Prompt copied! Paste in Claude after the corpus.");
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.classList.remove("copied");
        }, 1500);
      } catch (e) {
        btn.textContent = "Failed";
      }
    });

    row.appendChild(label);
    row.appendChild(btn);
    targetEl.appendChild(row);
  }
}

async function loadPrompts() {
  const prompts = await fetchPrompts();
  // Always-visible Quick Prompts panel.
  if (quickPromptsEl) renderPromptList(quickPromptsEl, prompts);
  // Session panel (only shown when a session is active).
  if (promptsEl) renderPromptList(promptsEl, prompts);
}

// ---- Background queue panel ----------------------------------------------
async function refreshQueue() {
  try {
    const s = await chrome.storage.session.get({
      busy: false, current: null, queue: [],
    });
    if (s.busy && s.current) {
      const label = s.current.title || shortLabel(s.current.url);
      const verb = s.current.kind === "session_add" ? "Adding" : "Extracting";
      currentEl.textContent = `${verb}: ${label}`;
      currentEl.classList.remove("panel-muted");
    } else {
      currentEl.textContent = "Idle.";
      currentEl.classList.add("panel-muted");
    }
    const depth = (s.queue || []).length;
    queueEl.textContent = `${depth} video${depth === 1 ? "" : "s"} queued.`;
    queueEl.classList.toggle("panel-muted", depth === 0);
    clearBtn.disabled = depth === 0;
  } catch (e) {
    console.warn("[popup] refreshQueue failed", e);
  }
}
clearBtn.addEventListener("click", () => {
  clearBtn.disabled = true;
  chrome.runtime.sendMessage({ type: "clearQueue" }, () => refreshQueue());
});

// ---- Recent uoinks --------------------------------------------------------
const recentUoinksEl = document.getElementById("recent-uoinks");
const HEALTH_FIELDS = [
  "transcript",
  "screenshots",
  "comments",
  "hook",
  "comment_intelligence",
];
const HOOK_TYPE_CATEGORIES = [
  "curiosity_gap",
  "question",
  "contrarian",
  "story_open",
  "promise_list",
  "demo",
  "authority",
  "stakes",
  "other",
];

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
  retry.textContent = "Retry";
  retry.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    const videoId = failure.videoId || (failure.url && STC.extractVideoId(failure.url));
    if (!videoId) {
      showToast("Can't retry â€” missing video URL.");
      return;
    }
    await removeRecentFailure(failure.id);
    chrome.storage.local.set({ auto_yoink: { videoId, ts: Date.now() } }, () => {
      chrome.tabs.create({
        url: failure.url || `https://www.youtube.com/watch?v=${videoId}`,
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

// ---- Index backfill status -------------------------------------------------
let backfillTimer = null;
let lastBackfillSignature = "";
let dismissedBackfillSignature = "";

function stopBackfillPolling() {
  if (backfillTimer) clearInterval(backfillTimer);
  backfillTimer = null;
}

function backfillSignature(status) {
  if (!status || status.state !== "running") return "";
  return `running:${Number(status.total) || 0}`;
}

function readDismissedBackfill() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get({ [BACKFILL_DISMISSED_KEY]: "" }, (items) => {
        dismissedBackfillSignature = String(items && items[BACKFILL_DISMISSED_KEY] || "");
        resolve(dismissedBackfillSignature);
      });
    } catch {
      dismissedBackfillSignature = "";
      resolve("");
    }
  });
}

function writeDismissedBackfill(signature) {
  dismissedBackfillSignature = signature || "";
  try {
    chrome.storage.local.set({ [BACKFILL_DISMISSED_KEY]: dismissedBackfillSignature });
  } catch { /* ignore */ }
}

async function popupAuthedJson(path, init = {}) {
  return globalThis.UoinkUI.authedJson(path, init);
}

function hideBackfillBanner() {
  if (backfillBanner) backfillBanner.classList.add("hidden");
}

function renderBackfillStatus(status) {
  if (!backfillBanner || !backfillText) return;
  if (!status || status.state !== "running") {
    hideBackfillBanner();
    lastBackfillSignature = "";
    writeDismissedBackfill("");
    stopBackfillPolling();
    return;
  }

  const signature = backfillSignature(status);
  lastBackfillSignature = signature;
  if (signature && signature === dismissedBackfillSignature) {
    hideBackfillBanner();
    return;
  }

  const current = Number.isFinite(Number(status.current)) ? Number(status.current) : 0;
  const total = Number.isFinite(Number(status.total)) ? Number(status.total) : 0;
  backfillText.textContent = `Indexing your uoinks: ${current} of ${total}...`;
  backfillBanner.classList.remove("hidden");
}

async function pollBackfillStatus() {
  if (document.hidden) return;
  try {
    const status = await popupAuthedJson("/index/backfill-status", { method: "GET" });
    renderBackfillStatus(status || null);
  } catch {
    hideBackfillBanner();
  }
}

function startBackfillPolling() {
  stopBackfillPolling();
  pollBackfillStatus();
  backfillTimer = setInterval(pollBackfillStatus, 2000);
}

if (backfillDismiss) {
  backfillDismiss.addEventListener("click", (ev) => {
    ev.preventDefault();
    if (lastBackfillSignature) writeDismissedBackfill(lastBackfillSignature);
    hideBackfillBanner();
  });
  wireKeyActivation(backfillDismiss);
}

if (backfillCancel) {
  backfillCancel.addEventListener("click", async (ev) => {
    ev.preventDefault();
    backfillCancel.textContent = "Cancelling...";
    try {
      await popupAuthedJson("/index/backfill-cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      hideBackfillBanner();
      showToast("Indexing cancelled.");
    } catch {
      showToast("Couldn't cancel indexing.");
    } finally {
      backfillCancel.textContent = "Cancel";
      pollBackfillStatus();
    }
  });
  wireKeyActivation(backfillCancel);
}

// ---- Rate-limit queue status ---------------------------------------------
let queueStatusTimer = null;
let lastQueueStatus = null;
let dismissedQueueFailureSignature = "";

function stopQueueStatusPolling() {
  if (queueStatusTimer) clearInterval(queueStatusTimer);
  queueStatusTimer = null;
  stopSseStream();
}

function queueRows(status) {
  if (!status || typeof status !== "object") return [];
  const buckets = [
    status.items,
    status.queue,
    status.pending,
    status.failed,
    status.failures,
    status.failed_items,
    status.jobs,
  ].filter(Array.isArray);
  const rows = [];
  const seen = new Set();
  for (const bucket of buckets) {
    for (const item of bucket) {
      const key = queueItemId(item) || JSON.stringify(item);
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(item);
    }
  }
  return rows;
}

function queueItemId(item) {
  return item && (item.pending_id || item.id || item.job_id || item.queue_id || item.video_id);
}

function shortQueueLabel(item) {
  if (!item) return "Queued uoink";
  return item.title || item.url || item.source_url || item.video_url || item.video_id || "Queued uoink";
}

function minutesUntil(value) {
  return globalThis.UoinkUI.minutesUntil(value);
}

function nextRetryLabel(status) {
  const mins = minutesUntil(status && (status.next_retry_in_seconds ?? status.retry_in_seconds ?? status.next_retry_at));
  if (mins == null) return "";
  if (mins <= 0) return "now";
  return `${mins} min`;
}

async function queueAction(path, id) {
  const body = id ? { pending_id: id, id } : {};
  return popupAuthedJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function makeQueueButton(label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    onClick(btn);
  });
  return btn;
}

function setQueueExpanded(expanded) {
  queueExpanded = !!expanded;
  if (queueDetails) queueDetails.classList.toggle("hidden", !queueExpanded);
  if (queueBannerToggle) queueBannerToggle.textContent = queueExpanded ? "Hide" : "Details";
  try {
    chrome.storage.local.set({ [QUEUE_EXPANDED_KEY]: queueExpanded });
  } catch { /* ignore */ }
}

function renderQueueDetails(status) {
  if (!queueDetails) return;
  queueDetails.innerHTML = "";
  const rows = queueRows(status);
  const runningRaw = status && (status.current || status.running || status.running_item);
  const runningRows = Array.isArray(runningRaw) ? runningRaw : (runningRaw ? [runningRaw] : []);
  const all = runningRows.map((item) => Object.assign({ state: "running" }, item)).concat(rows);

  if (!all.length) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.textContent = "No queued uoinks.";
    queueDetails.appendChild(empty);
    return;
  }

  for (const item of all) {
    const row = document.createElement("div");
    row.className = "queue-row";
    const title = document.createElement("div");
    title.className = "queue-row-title";
    const state = item.state || item.status || "queued";
    title.textContent = `${state}: ${shortQueueLabel(item)}`;
    title.title = shortQueueLabel(item);

    const actions = document.createElement("div");
    actions.className = "queue-row-actions";
    const id = queueItemId(item);
    if (id && state !== "running") {
      actions.appendChild(makeQueueButton("Retry", async (btn) => {
        btn.disabled = true;
        await queueAction("/queue/retry-now", id);
        pollQueueStatus();
      }));
    }
    if (id) {
      actions.appendChild(makeQueueButton("Cancel", async (btn) => {
        btn.disabled = true;
        await queueAction("/queue/cancel", id);
        pollQueueStatus();
      }));
    }

    row.appendChild(title);
    row.appendChild(actions);
    queueDetails.appendChild(row);
  }
}

function renderQueueBanner(status) {
  if (!queueStatusBanner || !queueBannerText) return;
  lastQueueStatus = status || null;
  const pending = Number(status && (status.pending_count ?? status.queued_count)) || 0;
  const running = Number(status && status.running_count) || (status && status.running ? 1 : 0);
  const failed = Number(status && status.failed_count) || 0;

  queueStatusBanner.classList.remove("warn", "error");
  if (queueBannerActions) queueBannerActions.innerHTML = "";

  if (!pending && !running && !failed) {
    queueStatusBanner.classList.add("hidden");
    return;
  }

  if (failed > 0) {
    const failSig = `failed:${failed}`;
    if (dismissedQueueFailureSignature === failSig) {
      queueStatusBanner.classList.add("hidden");
      return;
    }
    queueStatusBanner.classList.add("error");
    queueBannerText.textContent = `${failed} uoink${failed === 1 ? "" : "s"} failed after 3 retries.`;
    if (queueBannerActions) {
      queueBannerActions.appendChild(makeQueueButton("Retry now", async (btn) => {
        btn.disabled = true;
        await queueAction("/queue/retry-now");
        pollQueueStatus();
      }));
      queueBannerActions.appendChild(makeQueueButton("Dismiss", () => {
        dismissedQueueFailureSignature = failSig;
        queueStatusBanner.classList.add("hidden");
      }));
    }
  } else if (running > 0) {
    dismissedQueueFailureSignature = "";
    const runningRaw = status.current || status.running || status.running_item;
    const current = Array.isArray(runningRaw) ? runningRaw[0] : (runningRaw || {});
    queueBannerText.textContent = `Uoinking now: ${shortQueueLabel(current)}`;
  } else {
    dismissedQueueFailureSignature = "";
    queueStatusBanner.classList.add("warn");
    const retry = nextRetryLabel(status);
    queueBannerText.textContent = retry
      ? `${pending} uoink${pending === 1 ? "" : "s"} queued \u00b7 next retry ${retry}`
      : `${pending} uoink${pending === 1 ? "" : "s"} queued`;
  }

  renderQueueDetails(status);
  queueStatusBanner.classList.remove("hidden");
  if (queueDetails) queueDetails.classList.toggle("hidden", !queueExpanded);
  if (queueBannerToggle) queueBannerToggle.textContent = queueExpanded ? "Hide" : "Details";
}

let sseAbortController = null;
let sseState = {
  active: [],
  recent: [],
  queue: { pending: 0, running: 0, failed: 0, succeeded: 0, cancelled: 0, next_retry_at: null }
};

async function startSseStream() {
  stopSseStream();
  if (document.hidden || !serverOnline) return;

  sseAbortController = new AbortController();
  const signal = sseAbortController.signal;

  try {
    const token = await STC.getToken();
    if (!token) return;

    const res = await fetch(`${STC.SERVER}/jobs/stream`, {
      headers: { "X-Uoink-Token": token },
      signal
    });

    if (!res.ok) {
      console.error("[Uoink] Failed to connect to jobs stream", res.status);
      return;
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    // Reset local state on fresh connect
    sseState = {
      active: [],
      recent: [],
      queue: { pending: 0, running: 0, failed: 0, succeeded: 0, cancelled: 0, next_retry_at: null }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (signal.aborted) break;

      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (frame.startsWith(":")) continue; // heartbeat comment
        
        const ev = /^event:\s*(.*)$/m.exec(frame)?.[1];
        const data = /^data:\s*(.*)$/m.exec(frame)?.[1];
        if (ev && data) {
          try {
            handleSseEvent(ev, JSON.parse(data));
          } catch (e) {
            console.error("[Uoink] Failed to parse SSE event data", e);
          }
        }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.error("[Uoink] Error in SSE stream", e);
      // Retry connection after 5 seconds if still online and visible
      setTimeout(() => {
        if (serverOnline && !document.hidden) {
          startSseStream();
        }
      }, 5000);
    }
  }
}

function stopSseStream() {
  if (sseAbortController) {
    sseAbortController.abort();
    sseAbortController = null;
  }
}

function handleSseEvent(event, data) {
  if (event === "snapshot") {
    sseState.active = data.active || [];
    sseState.recent = data.recent || [];
    if (data.queue) sseState.queue = data.queue;
  } else if (event === "job") {
    const idx = sseState.active.findIndex(j => j.id === data.id);
    const isTerminal = ["completed", "cancelled", "failed"].includes(data.state);
    
    if (isTerminal) {
      if (idx >= 0) sseState.active.splice(idx, 1);
      const rIdx = sseState.recent.findIndex(j => j.id === data.id);
      if (rIdx >= 0) {
        sseState.recent[rIdx] = data;
      } else {
        sseState.recent.unshift(data);
        if (sseState.recent.length > 10) sseState.recent.pop();
      }
    } else {
      if (idx >= 0) {
        sseState.active[idx] = data;
      } else {
        sseState.active.push(data);
      }
    }
  } else if (event === "queue") {
    sseState.queue = data;
  }

  // Trigger UI render
  renderQueueBanner(getStatusForRender());
}

function getStatusForRender() {
  const runningJobs = sseState.active.filter(j => j.state === "running");
  const queuedJobs = sseState.active.filter(j => j.state === "queued" || j.state === "idle");
  const failedJobs = sseState.active.filter(j => j.state === "failed");
  const recentFailures = sseState.recent.filter(j => j.state === "failed");

  return {
    pending_count: sseState.queue.pending,
    running_count: sseState.queue.running,
    failed_count: sseState.queue.failed,
    next_retry_at: sseState.queue.next_retry_at,
    current: runningJobs,
    items: queuedJobs,
    failed_items: failedJobs.concat(recentFailures)
  };
}

async function pollQueueStatus() {
  if (document.hidden) return;
  try {
    const status = await popupAuthedJson("/queue/status", { method: "GET" });
    if (!status || status.ok === false) return;
    renderQueueBanner(status);
  } catch {
    // Queue is polish-only; don't turn the popup red when an older helper
    // does not have Sprint 19 endpoints yet.
  }
}

function startQueueStatusPolling() {
  stopQueueStatusPolling();
  if (isTier2) {
    startSseStream();
  } else {
    pollQueueStatus();
    queueStatusTimer = setInterval(pollQueueStatus, 5000);
  }
}

async function serverQueuePendingCount() {
  if (sseAbortController && sseState.queue) {
    return Number(sseState.queue.pending) || 0;
  }
  try {
    const status = await popupAuthedJson("/queue/status", { method: "GET" });
    if (!status || status.ok === false) return 0;
    lastQueueStatus = status;
    return Number(status.pending_count ?? status.queued_count) || 0;
  } catch {
    return 0;
  }
}

if (queueBannerMain) {
  queueBannerMain.addEventListener("click", () => setQueueExpanded(!queueExpanded));
  wireKeyActivation(queueBannerMain);
}
if (queueBannerToggle) {
  queueBannerToggle.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    setQueueExpanded(!queueExpanded);
  });
  wireKeyActivation(queueBannerToggle);
}

try {
  chrome.storage.local.get({ [QUEUE_EXPANDED_KEY]: false }, (items) => {
    queueExpanded = !!(items && items[QUEUE_EXPANDED_KEY]);
    setQueueExpanded(queueExpanded);
  });
} catch { /* ignore */ }

function queuedToastMessage(data) {
  const mins = minutesUntil(data && (data.next_retry_in_seconds ?? data.retry_in_seconds ?? data.next_retry_at));
  const retry = mins == null ? "soon" : (mins <= 0 ? "now" : `in ${mins} min`);
  return `Queued - will retry ${retry}. Open the popup to view queue.`;
}

async function shouldUseScreenshotPicker() {
  try {
    const res = await STC.getSettings();
    return !!(res && res.ok && res.settings &&
      res.settings.smart_screenshot_picker_enabled === true);
  } catch {
    return false;
  }
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

async function runPopupUoinkCurrent() {
  if (!uoinkCurrentBtn || !currentVideoUrl) return;
  if ((await serverQueuePendingCount()) >= 5) {
    showToast("Queue full, wait a few minutes.");
    pollQueueStatus();
    return;
  }
  const old = uoinkCurrentBtn.textContent;
  uoinkCurrentBtn.disabled = true;
  uoinkCurrentBtn.textContent = "Uoinking...";
  try {
    const interval = await STC.getInterval();
    const data = await STC.postExtract(currentVideoUrl, interval);
    if (data && data.ok && data.queued) {
      showToast(queuedToastMessage(data));
      pollQueueStatus();
      return;
    }
    if (!data || !data.ok) {
      showToast(STC.friendlyError(data && data.error));
      return;
    }
    const clipboardText = data.corpus_md_paste || data.yoink_md || "";
    saveClipboardBudget(data, clipboardText);
    if (await shouldUseScreenshotPicker()) {
      await STC.stashPickerCorpus(data);
      showToast("Uoink ready - pick screenshots in the popup.");
      return;
    }
    const copied = await writeClipboardText(clipboardText);
    if (!copied) {
      await chrome.runtime.sendMessage({ type: "clipboardRetry", text: clipboardText });
      showToast("Couldn't copy. Use the Try again notification.");
      return;
    }
    markClipboardUoinkNow();
    await chrome.tabs.create({ url: CLAUDE_URL, active: true });
    showToast("Uoinked ★ Paste in Claude.");
    loadRecentUoinks();
  } catch (e) {
    showToast(`Uoink failed: ${e && e.message || e}`);
  } finally {
    uoinkCurrentBtn.disabled = !serverOnline || !currentVideoUrl;
    uoinkCurrentBtn.textContent = old;
  }
}

if (uoinkCurrentBtn) {
  uoinkCurrentBtn.addEventListener("click", runPopupUoinkCurrent);
}

function renderHealthRow(health) {
  return globalThis.UoinkUI.renderHealthDots(health, { fields: HEALTH_FIELDS });
}

function topEntityNames(row) {
  const raw = row && Array.isArray(row.top_entities) ? row.top_entities : [];
  return raw
    .map((entity) => {
      if (typeof entity === "string") return entity.trim();
      if (entity && typeof entity === "object") {
        return String(entity.name || entity.label || "").trim();
      }
      return "";
    })
    .filter(Boolean)
    .slice(0, 5);
}

function renderEntityIndicator(row) {
  const count = Number(row && row.entity_count);
  if (!Number.isFinite(count) || count <= 0) return null;

  const indicator = document.createElement("span");
  indicator.className = "entity-indicator";
  indicator.textContent = `\u{1F4CD} ${count} ${count === 1 ? "entity" : "entities"}`;

  const names = topEntityNames(row);
  const tooltip = names.length
    ? names.join("\n")
    : `${count} ${count === 1 ? "entity" : "entities"} detected`;
  indicator.title = tooltip;
  indicator.setAttribute("aria-label", tooltip);

  return indicator;
}

function hookDisplayName(hookType) {
  return globalThis.UoinkUI.prettyHookType(String(hookType || "").trim());
}

function numberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function hookInfo(row) {
  if (!row || typeof row !== "object") return null;
  const hook = row.hook_analysis || row.hook || row.taxonomy || {};
  const hookType = row.hook_type
    || row.corrected_hook_type
    || hook.hook_type
    || hook.corrected_hook_type
    || hook.type
    || hook.category;
  if (!hookType) return null;

  return {
    hookType: String(hookType).trim().toLowerCase(),
    confidence: numberOrNull(
      row.hook_type_confidence
      ?? row.hook_confidence
      ?? row.confidence
      ?? hook.confidence
      ?? hook.hook_type_confidence
      ?? hook.hook_confidence
    ),
    similarCorrectionsUsed: numberOrNull(
      row.similar_corrections_used
      ?? hook.similar_corrections_used
      ?? hook.corrections_used
    ) || 0,
    videoId: row.video_id
      || hook.video_id
      || (row.url && STC.extractVideoId(row.url))
      || (row.source_url && STC.extractVideoId(row.source_url))
      || null,
  };
}

async function postHookCorrection(videoId, correctedHookType) {
  return popupAuthedJson("/taxonomy/correct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: videoId,
      corrected_hook_type: correctedHookType,
      user_reason: "",
    }),
  });
}

async function postTasteAnchor(videoId, anchorType, title) {
  const body = {
    video_id: videoId,
    anchor_type: anchorType,
    title: title || ""
  };
  
  try {
    const res = await fetch(`${STC.SERVER}/taste/anchors`, {
      method: "POST",
      mode: "cors",
      headers: {
        "Content-Type": "application/json",
        "X-Yoink-Token": await STC.getToken()
      },
      body: JSON.stringify(body)
    });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch {
    chrome.storage.local.get({ uoink_taste_anchors: { best: [], worst: [], admired_channels: [] } }, (stored) => {
      const anchors = stored.uoink_taste_anchors || { best: [], worst: [], admired_channels: [] };
      const list = anchorType === "best" ? anchors.best : anchors.worst;
      
      if (!list.some(x => (x.video_id || x) === videoId)) {
        list.push({ video_id: videoId, title: title || videoId });
      }
      
      chrome.storage.local.set({ uoink_taste_anchors: anchors });
    });
  }
}

function renderHookCalibration(row) {
  const info = hookInfo(row);
  if (!info) return null;

  const wrap = document.createElement("div");
  wrap.className = "recent-item-hook";
  wrap.addEventListener("click", (ev) => ev.stopPropagation());

  const chip = document.createElement("span");
  chip.className = "hook-chip";
  if (info.confidence != null && info.confidence <= 2) {
    chip.classList.add("warning");
  }

  const confidenceText = info.confidence == null
    ? ""
    : ` \u00b7 confidence ${info.confidence}/5`;
  chip.textContent = `${hookDisplayName(info.hookType)}${confidenceText}`;

  wrap.appendChild(chip);

  const suffix = document.createElement("span");
  suffix.className = "hook-muted";
  if (info.similarCorrectionsUsed > 0) {
    suffix.textContent = `(calibrated from ${info.similarCorrectionsUsed} past corrections)`;
    wrap.appendChild(suffix);
  }

  const message = document.createElement("span");
  message.className = "hook-correction-message";

  if (info.videoId) {
    const correctionLink = document.createElement("span");
    correctionLink.className = "hook-correction-link";
    correctionLink.setAttribute("role", "button");
    correctionLink.tabIndex = 0;
    correctionLink.textContent = "wrong?";

    const hideTimer = setTimeout(() => {
      if (correctionLink.isConnected) correctionLink.remove();
    }, 60_000);

    const openCorrectionPicker = () => {
      clearTimeout(hideTimer);
      correctionLink.remove();
      message.textContent = "";
      message.className = "hook-correction-message";

      const select = document.createElement("select");
      select.className = "hook-correction-select";
      select.setAttribute("aria-label", "Correct hook type");

      for (const category of HOOK_TYPE_CATEGORIES) {
        const option = document.createElement("option");
        option.value = category;
        option.textContent = hookDisplayName(category);
        option.selected = category === info.hookType;
        select.appendChild(option);
      }

      select.addEventListener("change", async () => {
        const corrected = select.value;
        if (!corrected || corrected === info.hookType) return;
        select.disabled = true;
        message.textContent = "Updating...";
        message.className = "hook-correction-message";
        try {
          const res = await postHookCorrection(info.videoId, corrected);
          if (!res || res.ok === false) {
            throw new Error((res && res.error) || "Correction failed");
          }
          info.hookType = corrected;
          chip.classList.remove("warning");
          const confidenceText = info.confidence == null
            ? ""
            : ` \u00b7 confidence ${info.confidence}/5`;
          chip.textContent = `${hookDisplayName(corrected)}${confidenceText}`;
          suffix.textContent = "+1 calibration";
          if (!suffix.isConnected) wrap.appendChild(suffix);
          message.textContent =
            "Updated - thank you, future classifications will use this calibration.";
          select.remove();
        } catch (e) {
          message.className = "hook-correction-error";
          message.textContent = (e && e.message) || "Correction failed";
          select.disabled = false;
        }
      });

      wrap.appendChild(select);
      if (!message.isConnected) wrap.appendChild(message);
      select.focus();
    };

    correctionLink.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openCorrectionPicker();
    });
    correctionLink.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        ev.stopPropagation();
        openCorrectionPicker();
      }
    });
    wrap.appendChild(correctionLink);

    // Anchor best/worst buttons (Sprint 3)
    const star = document.createElement("span");
    star.className = "hook-correction-link";
    star.style.marginLeft = "8px";
    star.textContent = "⭐";
    star.title = "Mark as 10/10 Best Anchor";
    star.tabIndex = 0;
    star.setAttribute("role", "button");
    const markBest = async (ev) => {
      ev.stopPropagation();
      star.style.opacity = 0.5;
      await postTasteAnchor(info.videoId, "best", row.title);
      star.style.opacity = 1;
      showToast("Marked as Best Anchor! ✓");
    };
    star.addEventListener("click", markBest);
    star.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); markBest(e); } });

    const cross = document.createElement("span");
    cross.className = "hook-correction-link";
    cross.style.marginLeft = "8px";
    cross.textContent = "❌";
    cross.title = "Mark as 0/10 Worst Anchor";
    cross.tabIndex = 0;
    cross.setAttribute("role", "button");
    const markWorst = async (ev) => {
      ev.stopPropagation();
      cross.style.opacity = 0.5;
      await postTasteAnchor(info.videoId, "worst", row.title);
      cross.style.opacity = 1;
      showToast("Marked as Worst Anchor! ✓");
    };
    cross.addEventListener("click", markWorst);
    cross.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); markWorst(e); } });

    wrap.appendChild(star);
    wrap.appendChild(cross);
  }

  return wrap;
}

// ---- Pairwise Hook Calibration (Sprint 3) --------------------------------
async function fetchHookText(slug) {
  if (!slug) return null;
  try {
    let res = await globalThis.UoinkUI.authedJson("/mcp/v1/tools/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "get_uoink_corpus",
        arguments: { slug }
      })
    });
    if (!res || res.error) {
      res = await globalThis.UoinkUI.authedJson("/mcp/v1/tools/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "get_yoink_corpus",
          arguments: { slug }
        })
      });
    }
    const data = res && res.result && res.result.structuredContent;
    const md = data && data.corpus_md;
    if (md) {
      const startIdx = md.indexOf("<!-- HOOK_START -->");
      const endIdx = md.indexOf("<!-- HOOK_END -->");
      if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
        let hookText = md.substring(startIdx + "<!-- HOOK_START -->".length, endIdx).trim();
        // Clean up formatting
        hookText = hookText.replace(/^## Hook Analysis\s*/i, "");
        hookText = hookText.replace(/^\*\*Hook Type:\*\*\s*[^\n]*\s*/i, "");
        hookText = hookText.replace(/^\*\*Analysis:\*\*\s*/i, "");
        hookText = hookText.trim();
        if (hookText) {
          if (hookText.length > 150) {
            return hookText.substring(0, 147) + "...";
          }
          return hookText;
        }
      }
    }
  } catch (e) {
    console.warn("fetchHookText failed for", slug, e);
  }
  return null;
}

let tcPairwiseCurrentPair = null;

async function initPairwiseCalibration(recentYoinks) {
  const card = document.getElementById("pairwise-calibration-card");
  if (!card) return;

  // 1. Check condition: 5+ yoinks
  if (!recentYoinks || recentYoinks.length < 5) {
    card.classList.add("hidden");
    return;
  }

  // 2. Check dismiss: 24h limit
  const dismissedAt = await new Promise((r) => {
    chrome.storage.local.get(["uoink_pairwise_dismissed_at"], (items) => {
      r(Number(items.uoink_pairwise_dismissed_at) || 0);
    });
  });

  if (Date.now() - dismissedAt < 24 * 60 * 60 * 1000) {
    card.classList.add("hidden");
    return;
  }

  // Wire dismiss button
  const dismissBtn = document.getElementById("pairwise-dismiss-btn");
  if (dismissBtn) {
    dismissBtn.onclick = () => {
      chrome.storage.local.set({ uoink_pairwise_dismissed_at: Date.now() }, () => {
        card.classList.add("hidden");
      });
    };
  }

  // Select two random yoinks
  const idxA = Math.floor(Math.random() * recentYoinks.length);
  let idxB = Math.floor(Math.random() * recentYoinks.length);
  while (idxB === idxA) {
    idxB = Math.floor(Math.random() * recentYoinks.length);
  }

  const yoinkA = recentYoinks[idxA];
  const yoinkB = recentYoinks[idxB];
  tcPairwiseCurrentPair = { a: yoinkA, b: yoinkB };

  const btnA = document.getElementById("pairwise-option-a");
  const btnB = document.getElementById("pairwise-option-b");
  const skipBtn = document.getElementById("pairwise-skip-btn");
  const syncNote = document.getElementById("pairwise-sync-note");

  if (!btnA || !btnB || !skipBtn) return;

  btnA.disabled = true;
  btnB.disabled = true;
  btnA.textContent = "Loading hook A...";
  btnB.textContent = "Loading hook B...";

  card.classList.remove("hidden");

  // Fetch hook texts
  const [hookA, hookB] = await Promise.all([
    fetchHookText(yoinkA.folder ? yoinkA.folder.split(/[\\/]/).pop() : null),
    fetchHookText(yoinkB.folder ? yoinkB.folder.split(/[\\/]/).pop() : null)
  ]);

  btnA.disabled = false;
  btnB.disabled = false;

  btnA.textContent = hookA ? `👈 ${hookA}` : `👈 ${yoinkA.title} (${hookDisplayName(yoinkA.hook_type)})`;
  btnB.textContent = hookB ? `👉 ${hookB}` : `👉 ${yoinkB.title} (${hookDisplayName(yoinkB.hook_type)})`;

  const submitChoice = async (choice) => {
    btnA.disabled = true;
    btnB.disabled = true;
    skipBtn.disabled = true;

    const answer = {
      pair_a: yoinkA.video_id,
      pair_b: yoinkB.video_id,
      choice: choice
    };

    try {
      const res = await fetch(`${STC.SERVER}/taste/answer`, {
        method: "POST",
        mode: "cors",
        headers: {
          "Content-Type": "application/json",
          "X-Yoink-Token": await STC.getToken()
        },
        body: JSON.stringify(answer)
      });
      if (res.ok) {
        if (syncNote) syncNote.classList.add("hidden");
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (e) {
      console.warn("Failed to POST taste answer, saving locally", e);
      chrome.storage.local.get({ uoink_pairwise_pending: [] }, (stored) => {
        const pending = stored.uoink_pairwise_pending || [];
        pending.push(answer);
        chrome.storage.local.set({ uoink_pairwise_pending: pending }, () => {
          if (syncNote) syncNote.classList.remove("hidden");
        });
      });
    }

    // Advance to next pair
    btnA.disabled = false;
    btnB.disabled = false;
    skipBtn.disabled = false;
    initPairwiseCalibration(recentYoinks);
  };

  btnA.onclick = () => submitChoice("a");
  btnB.onclick = () => submitChoice("b");
  skipBtn.onclick = () => submitChoice("skip");
}

async function loadRecentUoinks() {
  if (!recentUoinksEl) return;
  let recent = [];
  const failures = await loadRecentFailures();
  try {
    const res = await STC.listRecent();
    recent = (res && res.recent) || [];
  } catch { /* server may be down — leave the placeholder */ }
  loadResurfaceCard(recent).catch(() => {});
  knownRecentUoinkCount = recent.length + failures.length;
  updateFocalMode();
  initPairwiseCalibration(recent);
  recentUoinksEl.innerHTML = "";
  for (const failure of failures) {
    recentUoinksEl.appendChild(renderFailureRow(failure));
  }

  // Populate active uoink card if there is at least one recent uoink
  const activeUoinkCard = document.getElementById("active-uoink-card");
  if (activeUoinkCard) {
    if (recent.length > 0) {
      activeUoinkCard.classList.remove("hidden");
      const last = recent[0];
      const titleEl = document.getElementById("active-uoink-title");
      const channelEl = document.getElementById("active-uoink-channel");
      const durationEl = document.getElementById("active-uoink-duration");
      
      if (titleEl) titleEl.textContent = last.title || "(Untitled)";
      if (channelEl) channelEl.textContent = last.channel || "YouTube";
      if (durationEl) durationEl.textContent = last.topic || "Uncategorized";

      const hookContainer = document.getElementById("active-uoink-hook-container");
      if (hookContainer) {
        hookContainer.innerHTML = "";
        const hookRow = renderHookCalibration(last);
        if (hookRow) {
          const wrongLink = hookRow.querySelector(".hook-correction-link");
          if (wrongLink) {
            wrongLink.textContent = "✏️";
            wrongLink.title = "Correct Hook Type";
          }
          hookContainer.appendChild(hookRow);
        }
      }

      const openClaudeBtn = document.getElementById("active-uoink-open-claude");
      if (openClaudeBtn) {
        openClaudeBtn.onclick = (e) => {
          e.stopPropagation();
          chrome.tabs.create({ url: "https://claude.ai/new", active: true });
        };
      }

      const copyMDBtn = document.getElementById("active-uoink-copy-md");
      if (copyMDBtn) {
        copyMDBtn.onclick = async (e) => {
          e.stopPropagation();
          copyMDBtn.disabled = true;
          copyMDBtn.textContent = "Copying...";
          
          try {
            let res = await STC._postJson("/mcp/v1/tools/call", {
              name: "get_uoink_corpus",
              arguments: { slug: last.slug }
            });
            if (!res || res.error) {
              res = await STC._postJson("/mcp/v1/tools/call", {
                name: "get_yoink_corpus",
                arguments: { slug: last.slug }
              });
            }
            const data = res && res.result && res.result.structuredContent;
            if (data && data.ok && data.corpus_md) {
              const copied = await writeClipboardText(data.corpus_md);
              if (copied) {
                showToast("Copied markdown to clipboard!");
              } else {
                showToast("Clipboard copy blocked.");
              }
            } else {
              showToast("Failed to retrieve markdown.");
            }
          } catch (err) {
            showToast("Error retrieving markdown.");
          } finally {
            copyMDBtn.disabled = false;
            copyMDBtn.textContent = "Copy Markdown";
          }
        };
      }
    } else {
      activeUoinkCard.classList.add("hidden");
    }
  }

  if (!recent.length && !failures.length) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.style.cssText = "font-size:11px;padding:4px 6px";
    empty.textContent = "No uoinks yet.";
    recentUoinksEl.appendChild(empty);
    return;
  }
  for (const r of recent) {
    const item = document.createElement("div");
    item.className = "recent-item";
    item.title = r.folder || "";
    const main = document.createElement("div");
    main.className = "recent-item-main";

    const text = document.createElement("span");
    text.className = "recent-item-text";

    const pf = r.platform || "";
    let pfText = "";
    let pfClass = "";
    if (pf === "youtube") {
      pfText = "YouTube";
      pfClass = "youtube";
    } else if (pf === "twitter") {
      pfText = "X";
      pfClass = "twitter";
    } else if (pf) {
      pfText = pf.charAt(0).toUpperCase() + pf.slice(1);
      pfClass = "generic";
    }
    if (pfText) {
      const pfChip = document.createElement("span");
      pfChip.className = `platform-chip ${pfClass}`;
      pfChip.textContent = pfText;
      text.appendChild(pfChip);
    }

    const title = document.createElement("span");
    title.textContent = r.title || "(untitled)";
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = r.topic || "—";
    text.appendChild(title);
    text.appendChild(meta);
    main.appendChild(text);

    const healthRow = renderHealthRow(r.health);
    const entityIndicator = renderEntityIndicator(r);
    const hookRow = renderHookCalibration(r);
    if (entityIndicator) main.appendChild(entityIndicator);
    if (healthRow) main.appendChild(healthRow);
    item.appendChild(main);
    if (hookRow) item.appendChild(hookRow);
    item.addEventListener("click", () => {
      STC.logEngagement("opened", "popup", { video_id: r.video_id, title: r.title, folder: r.folder }).catch(() => {});
      if (r.folder) STC.openFolder(r.folder);
    });
    recentUoinksEl.appendChild(item);
  }
}

async function loadResurfaceCard(recent) {
  const card = document.getElementById("resurface-card");
  const listEl = document.getElementById("resurface-list");
  if (!card || !listEl) return;

  const dismissKey = "uoink_resurface_dismissed_at";
  let dismissedAt = 0;
  try {
    const items = await new Promise((r) => chrome.storage.local.get({ [dismissKey]: 0 }, r));
    dismissedAt = items[dismissKey] || 0;
  } catch (e) {
    console.warn("Storage error reading resurface dismiss:", e);
  }

  if (Date.now() - dismissedAt < 24 * 60 * 60 * 1000) {
    card.classList.add("hidden");
    return;
  }

  let resurfaceItems = [];
  let isFromFallback = false;

  try {
    const res = await STC.getResurfaceToday();
    if (res && res.ok && Array.isArray(res.items)) {
      resurfaceItems = res.items;
    } else {
      isFromFallback = true;
    }
  } catch (e) {
    isFromFallback = true;
  }

  if (isFromFallback) {
    let scoresMap = {};
    try {
      const scoresRes = await STC.getEngagementScores();
      if (scoresRes && scoresRes.ok) {
        scoresMap = scoresRes.scores || scoresRes.engagement_scores || {};
      }
    } catch (e) {
      console.warn("Failed to fetch engagement scores:", e);
    }

    const hasEngagementData = Object.keys(scoresMap).length > 0;
    if (!hasEngagementData) {
      card.classList.add("hidden");
      return;
    }

    let allYoinks = [];
    try {
      const searchRes = await STC.memorySearch({ sort: "engagement" });
      if (searchRes && searchRes.ok && Array.isArray(searchRes.results)) {
        allYoinks = searchRes.results;
      } else if (searchRes && Array.isArray(searchRes)) {
        allYoinks = searchRes;
      }
    } catch (e) {
      console.warn("Failed to search memory:", e);
    }

    if (allYoinks.length === 0 && Array.isArray(recent)) {
      allYoinks = recent;
    }

    if (allYoinks.length < 10) {
      card.classList.add("hidden");
      return;
    }

    const fourteenDaysAgo = Date.now() - 14 * 24 * 60 * 60 * 1000;
    const eligible = allYoinks.filter(y => {
      if (!y.video_id) return false;
      const lastOpened = y.last_opened_at || y.opened_at || y.yoinked_at || y.created_at;
      if (!lastOpened) return true;
      const lastOpenedTs = Date.parse(lastOpened);
      return isNaN(lastOpenedTs) || lastOpenedTs < fourteenDaysAgo;
    });

    if (eligible.length === 0) {
      card.classList.add("hidden");
      return;
    }

    eligible.forEach(y => {
      y.engagement_score = scoresMap[y.video_id] || 0;
    });
    const scoredEligible = eligible.filter(y => y.engagement_score > 0);
    if (scoredEligible.length === 0) {
      card.classList.add("hidden");
      return;
    }

    scoredEligible.sort((a, b) => b.engagement_score - a.engagement_score);
    resurfaceItems = scoredEligible.slice(0, 3);
  } else {
    if (resurfaceItems.length === 0) {
      card.classList.add("hidden");
      return;
    }
  }

  if (resurfaceItems.length === 0) {
    card.classList.add("hidden");
    return;
  }

  listEl.innerHTML = "";
  for (const item of resurfaceItems.slice(0, 3)) {
    const itemEl = document.createElement("div");
    itemEl.className = "resurface-item";

    const thumb = document.createElement("img");
    thumb.className = "resurface-thumb";
    thumb.src = item.thumbnail_url || `https://i.ytimg.com/vi/${item.video_id}/mqdefault.jpg`;
    thumb.alt = "";

    const contentWrap = document.createElement("div");
    contentWrap.style.cssText = "flex: 1; min-width: 0;";

    const title = document.createElement("div");
    title.className = "resurface-item-title";
    title.style.cssText = "font-size: 11px; font-weight: 600; color: var(--cream); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
    title.textContent = item.title || "(Untitled)";

    const meta = document.createElement("div");
    meta.className = "resurface-meta";
    
    const age = formatAgeString(item.yoinked_at || item.created_at);
    const ageStr = age ? `${age} &middot; ` : "";
    const score = item.value_score || item.engagement_score || 1.0;
    
    meta.innerHTML = `${ageStr}<span class="resurface-score-chip">Score: ${score.toFixed(1)}</span>`;

    contentWrap.appendChild(title);
    contentWrap.appendChild(meta);
    itemEl.appendChild(thumb);
    itemEl.appendChild(contentWrap);

    itemEl.addEventListener("click", () => {
      STC.logEngagement("opened", "popup", { video_id: item.video_id, title: item.title, folder: item.folder, resurfaced: true }).catch(() => {});
      if (item.folder) STC.openFolder(item.folder);
    });

    listEl.appendChild(itemEl);
  }

  card.classList.remove("hidden");

  const dismissBtn = document.getElementById("resurface-dismiss-btn");
  if (dismissBtn) {
    dismissBtn.onclick = async () => {
      card.classList.add("hidden");
      try {
        await new Promise((r) => chrome.storage.local.set({ [dismissKey]: Date.now() }, r));
      } catch (e) {
        console.warn("Storage error writing resurface dismiss:", e);
      }
    };
  }

  const viewAllLink = document.getElementById("resurface-view-all");
  if (viewAllLink) {
    viewAllLink.onclick = (ev) => {
      ev.preventDefault();
      chrome.tabs.create({ url: "http://127.0.0.1:5179/dashboard?tab=foryou" });
      window.close();
    };
  }
}

function formatAgeString(dateStr) {
  if (!dateStr) return "";
  const t = Date.parse(dateStr);
  if (isNaN(t)) return "";
  const diffDays = Math.floor((Date.now() - t) / (24 * 60 * 60 * 1000));
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) return `${diffWeeks}w ago`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths}mo ago`;
}

// ---- Destination buttons --------------------------------------------------
const CLAUDE_URL = "https://claude.ai/new";
const CHATGPT_URL = "https://chatgpt.com/";

function openDestination(url, label) {
  chrome.tabs.create({ url, active: true });
  showToast(`Opened ${label} - paste your most recent uoink.`);
}

document.getElementById("send-claude").addEventListener("click", () => {
  openDestination(CLAUDE_URL, "Claude");
});
document.getElementById("send-chatgpt").addEventListener("click", () => {
  openDestination(CHATGPT_URL, "ChatGPT");
});

// ---- View all uoinks ------------------------------------------------------
const openIndexLink = document.getElementById("open-index");
if (openIndexLink) {
  openIndexLink.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopImmediatePropagation();
    chrome.tabs.create({ url: chrome.runtime.getURL("uoink-memory.html") });
  });
}
// Legacy fallback below opens _all-yoinks-index.md if the Memory hook fails.
document.getElementById("open-index").addEventListener("click", async (ev) => {
  ev.preventDefault();
  try {
    const res = await STC.openIndex();
    if (!res || res.ok === false) {
      showToast("Couldn't open the uoinks index â€” server may be down.");
    }
  } catch {
    showToast("Couldn't open the uoinks index â€” server may be down.");
  }
});
wireKeyActivation(document.getElementById("open-index"));

// ---- Open dashboard (Sprint 21 / Tier 2) -----------------------------------
const openDashboardLink = document.getElementById("open-dashboard");
if (openDashboardLink) {
  openDashboardLink.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({ url: `${STC.SERVER}/dashboard` });
  });
  wireKeyActivation(openDashboardLink);
}

// ---- Settings link (Sprint 2) ---------------------------------------------
// Lives in the popup footer so it's visible in both single-video and playlist
// modes. setup.html is the canonical settings surface (Codex's lane), so we
// just open it in a new tab â€” never duplicate the form inside the popup.
const openSettingsLink = document.getElementById("open-settings");
if (openSettingsLink) {
  openSettingsLink.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({
      url: chrome.runtime.getURL("setup.html?source=popup"),
      active: true,
    });
    window.close();
  });
  wireKeyActivation(openSettingsLink);
}

// ---- MCP setup link (Sprint 4) --------------------------------------------
// Deep-links to the MCP section of setup.html. Setup.html ships an id
// "mcp-settings" anchor; the section content (Claude Desktop / Cursor /
// generic HTTP config snippets) is rendered by Codex's setup.js.
const openMcpLink = document.getElementById("open-mcp-setup");
if (openMcpLink) {
  openMcpLink.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({
      url: chrome.runtime.getURL("setup.html?source=popup#mcp-settings"),
      active: true,
    });
    window.close();
  });
  wireKeyActivation(openMcpLink);
}

// ---- Boot -----------------------------------------------------------------
ping();
loadInterval();
loadPrompts();
readMoreOptionsState();
loadCurrentVideoPreview();
refreshQueue();
refreshActiveFromServer();
loadRecentSessions();
loadRecentUoinks();
readDismissedBackfill().then(startBackfillPolling);
startQueueStatusPolling();

const queueTimer = setInterval(refreshQueue, 1000);
const pingTimer = setInterval(ping, 3000);
const sessionTimer = setInterval(async () => {
  // Periodically pull active session from server in case background updated
  // it while popup was open (e.g. context-menu add finished).
  try { await chrome.runtime.sendMessage({ type: "refreshActiveSession" }); }
  catch { /* ignore */ }
}, 2000);
window.addEventListener("unload", () => {
  clearInterval(queueTimer);
  clearInterval(pingTimer);
  clearInterval(sessionTimer);
  stopBackfillPolling();
  stopQueueStatusPolling();
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopBackfillPolling();
    stopQueueStatusPolling();
  } else {
    startBackfillPolling();
    startQueueStatusPolling();
  }
});

// =====================================================================
// v2 â€” Playlist mode
// =====================================================================
// Self-contained: only touches its own DOM (#mode-playlist + .mode-btn) and
// the #mode-single wrapper visibility. The single-video flow above runs
// untouched whenever mode = "single".
// ---------------------------------------------------------------------

(function setupPlaylistMode() {
  const POLL_MS = 1000;
  const PLAYLIST_CAP = 10;
  const PHASES = ["metadata", "download", "screenshots", "comments"];

  // Inline SVG placeholder for thumbs the i.ytimg.com fetch couldn't load
  // (mock IDs, age-restricted, or offline). Keeps the row layout stable.
  const PLACEHOLDER_THUMB =
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      "<svg xmlns='http://www.w3.org/2000/svg' width='80' height='45' viewBox='0 0 80 45'>" +
        "<rect width='80' height='45' fill='#3a3a3f'/>" +
        "<text x='40' y='28' fill='#888' font-size='11' text-anchor='middle' " +
        "font-family='sans-serif'>YT</text></svg>"
    );

  const modeSingleEl = document.getElementById("mode-single");
  const modePlaylistEl = document.getElementById("mode-playlist");
  const modeBtns = document.querySelectorAll(".mode-btn[data-mode]");

  // Input panel
  const inputPanel = document.getElementById("pl-input-panel");
  const urlInput = document.getElementById("pl-url");
  const previewBtn = document.getElementById("pl-preview-btn");
  const inputError = document.getElementById("pl-input-error");

  // Preview panel
  const previewPanel = document.getElementById("pl-preview-panel");
  const previewPlaylistTitleEl = document.getElementById("pl-preview-playlist-title");
  const previewSubtitleEl = document.getElementById("pl-preview-subtitle");
  const previewWarningsEl = document.getElementById("pl-preview-warnings");
  const previewListEl = document.getElementById("pl-preview-list");
  const startBtn = document.getElementById("pl-start-btn");

  // Progress panel
  const progressPanel = document.getElementById("pl-progress-panel");
  const progressPlaylistTitleEl = document.getElementById("pl-progress-playlist-title");
  const progressFill = document.getElementById("pl-progress-fill");
  const progressText = document.getElementById("pl-progress-text");
  const progressMessageEl = document.getElementById("pl-progress-message");
  const progressCiEl = document.getElementById("pl-progress-ci");
  const progressDisconnectEl = document.getElementById("pl-progress-disconnect");
  const progressWarningsEl = document.getElementById("pl-progress-warnings");
  const phaseRow = document.getElementById("pl-phase-row");
  const cancelBtnEl = document.getElementById("pl-cancel-btn");

  // Done panel
  const donePanel = document.getElementById("pl-done-panel");
  const doneSummary = document.getElementById("pl-done-summary");
  const doneMeta = document.getElementById("pl-done-meta");
  const doneMessageEl = document.getElementById("pl-done-message");
  const doneCiEl = document.getElementById("pl-done-ci");
  const doneWarningsEl = document.getElementById("pl-done-warnings");
  const doneFailedListEl = document.getElementById("pl-done-failed-list");
  const openFolderBtn = document.getElementById("pl-open-folder-btn");
  const startAnotherBtn = document.getElementById("pl-start-another-btn");

  // Cancelled panel
  const cancelledPanel = document.getElementById("pl-cancelled-panel");
  const cancelledSummaryEl = document.getElementById("pl-cancelled-summary");
  const cancelledMetaEl = document.getElementById("pl-cancelled-meta");
  const cancelledMessageEl = document.getElementById("pl-cancelled-message");
  const cancelledWarningsEl = document.getElementById("pl-cancelled-warnings");
  const cancelledFolderBtn = document.getElementById("pl-cancelled-folder-btn");
  const cancelledRestartBtn = document.getElementById("pl-cancelled-restart-btn");

  // Failed panel
  const failedPanel = document.getElementById("pl-failed-panel");
  const failedMsg = document.getElementById("pl-failed-msg");
  const failedFolderBtn = document.getElementById("pl-failed-folder-btn");
  const failedRestartBtn = document.getElementById("pl-failed-restart-btn");

  // ---- State -----------------------------------------------------------
  let previewedUrl = null;
  let previewedPlaylist = null;       // unwrapped res.playlist from /playlist/preview
  let activeJobId = null;
  let pollTimer = null;
  let resultPayload = null;           // job.result on completion
  let lastJob = null;                 // most recent job object (any state)
  // Sprint 2: one-time GET /settings snapshot. Only the
  // comment_intelligence_enabled flag is consumed in the popup today; we
  // cache the whole settings object so future read-only reads are free.
  let cachedSettings = null;

  // Fire-and-forget on IIFE boot. The CI indicator's render guards against
  // cachedSettings still being null (treats it as "not enabled") so a slow
  // settings response can't block the progress UI.
  (async function loadSettings() {
    try {
      const res = await STC.getSettings();
      if (res && res.ok && res.settings) {
        cachedSettings = res.settings;

        // Check migration banners
        const migrationSuccessBanner = document.getElementById("migration-success-banner");
        if (migrationSuccessBanner) {
          if (res.settings.migration_just_happened === true) {
            migrationSuccessBanner.classList.remove("hidden");
            const migrationDismissBtn = document.getElementById("migration-dismiss-btn");
            if (migrationDismissBtn) {
              migrationDismissBtn.onclick = async () => {
                migrationSuccessBanner.classList.add("hidden");
                try {
                  await STC.updateSettings({ migration_just_happened: false });
                } catch (e) {
                  console.warn("Failed to dismiss migration banner", e);
                }
              };
            }
          }
        }

        const desktopCorpusMigrationBanner = document.getElementById("desktop-corpus-migration-banner");
        if (desktopCorpusMigrationBanner) {
          if (res.settings.desktop_corpus_migration_pending === true) {
            desktopCorpusMigrationBanner.classList.remove("hidden");
            
            const moveBtn = document.getElementById("desktop-corpus-move-btn");
            if (moveBtn) {
              moveBtn.onclick = async () => {
                desktopCorpusMigrationBanner.classList.add("hidden");
                showToast("Moving files...");
                try {
                  await STC.updateSettings({ desktop_corpus_migration_action: "move" });
                  showToast("Migration started.");
                } catch (e) {
                  showToast("Failed to start migration.");
                }
              };
            }

            const keepBtn = document.getElementById("desktop-corpus-keep-btn");
            if (keepBtn) {
              keepBtn.onclick = async () => {
                desktopCorpusMigrationBanner.classList.add("hidden");
                try {
                  await STC.updateSettings({ desktop_corpus_migration_action: "keep" });
                } catch (e) {
                  console.warn("Failed to keep both", e);
                }
              };
            }
          }
        }
      }
    } catch { /* settings fetch is non-fatal */ }
  })();

  // ---- mode switching --------------------------------------------------
  // currentMode is shared with the top-level ping() handler so reconnects
  // can restore whichever panel the user already had selected.

  function setMode(mode) {
    currentMode = mode;
    for (const b of modeBtns) {
      const isActive = b.dataset.mode === mode;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-selected", isActive ? "true" : "false");
    }
    if (mode === "playlist") {
      modeSingleEl.classList.add("hidden");
      modePlaylistEl.classList.remove("hidden");
    } else {
      modePlaylistEl.classList.add("hidden");
      modeSingleEl.classList.remove("hidden");
    }
    // Sprint 6 (item 4): the pill is only visible while user is in
    // single-video mode AND a playlist job is non-terminal. Reconcile
    // after every mode change.
    _renderActivePlaylistPill();
  }
  for (const b of modeBtns) {
    b.addEventListener("click", () => {
      if (b.disabled) return;
      setMode(b.dataset.mode);
    });
  }

  // ---- Sprint 6 (item 4): active-playlist pill -------------------------
  // Shown when user is in single-video mode AND lastJob is non-terminal
  // (queued or running). Clicking returns to playlist mode + progress
  // panel. On terminal state we just hide the pill â€” the next-popup-open
  // "Last uoink completed" affordance (item 3) is what surfaces the
  // result on the playlist input panel.
  const activePlaylistPillEl = document.getElementById("active-playlist-pill");
  const activePlaylistPillLabelEl = document.getElementById("active-playlist-pill-label");

  function _isJobNonTerminal(job) {
    return !!(job && (job.state === "queued" || job.state === "running"));
  }

  function _renderActivePlaylistPill() {
    if (!activePlaylistPillEl) return;
    const showPill = currentMode === "single" && _isJobNonTerminal(lastJob);
    if (!showPill) {
      activePlaylistPillEl.classList.add("hidden");
      return;
    }
    // Label uses textContent to keep XSS-discipline â€” playlist_title
    // could in principle be attacker-shaped via a malicious playlist
    // title (yt-dlp would surface it). Safe via textContent.
    const total = lastJob.videos_total || 0;
    const done = (lastJob.videos_done || 0) + (lastJob.videos_failed || 0);
    const title = lastJob.playlist_title || "Playlist";
    const state = lastJob.state === "queued" ? "Queued" : `${done}/${total}`;
    activePlaylistPillLabelEl.textContent = `${title} Â· ${state}`;
    activePlaylistPillEl.classList.remove("hidden");
  }

  function _onPillActivate() {
    if (!_isJobNonTerminal(lastJob)) return;
    setMode("playlist");
    showOnly(progressPanel);
  }
  if (activePlaylistPillEl) {
    activePlaylistPillEl.addEventListener("click", _onPillActivate);
    activePlaylistPillEl.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        _onPillActivate();
      }
    });
  }

  // ---- helpers ---------------------------------------------------------
  function fmtDuration(seconds) {
    if (seconds == null) return "â€”";
    const s = Math.max(0, parseInt(seconds, 10) || 0);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, "0")}`;
  }

  function fmtNullable(v) { return (v == null || v === "") ? "â€”" : v; }

  function showOnly(panel) {
    for (const el of [inputPanel, previewPanel, progressPanel, donePanel, cancelledPanel, failedPanel]) {
      if (!el) continue;
      el.classList.toggle("hidden", el !== panel);
    }
  }

  function showError(msg) {
    inputError.textContent = msg;
    inputError.classList.remove("hidden");
  }
  function clearError() {
    inputError.textContent = "";
    inputError.classList.add("hidden");
  }

  // Render the contract's `warnings: [...]` array into a strip element.
  // Hides the strip when the array is empty/missing.
  function renderWarnings(stripEl, warnings) {
    if (!stripEl) return;
    const list = Array.isArray(warnings) ? warnings : [];
    if (!list.length) {
      stripEl.textContent = "";
      stripEl.classList.add("hidden");
      return;
    }
    // Multi-warning support: join with " Â· ". The contract only specifies
    // "playlist exceeds cap" today but the shape is an array â€” handle N.
    stripEl.textContent = list.join(" Â· ");
    stripEl.classList.remove("hidden");
  }

  function setText(el, text) {
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("hidden", !text);
  }

  function resetPlaylistUI() {
    stopPolling();
    activeJobId = null;
    resultPayload = null;
    lastJob = null;
    _renderActivePlaylistPill();
    previewedUrl = null;
    previewedPlaylist = null;
    urlInput.value = "";
    clearError();
    previewListEl.innerHTML = "";
    renderWarnings(previewWarningsEl, []);
    renderWarnings(progressWarningsEl, []);
    renderWarnings(doneWarningsEl, []);
    renderWarnings(cancelledWarningsEl, []);
    setText(previewPlaylistTitleEl, "");
    setText(previewSubtitleEl, "");
    setText(progressPlaylistTitleEl, "");
    setText(progressMessageEl, "");
    setText(doneMessageEl, "");
    setText(cancelledMessageEl, "");
    setText(cancelledMetaEl, "");
    doneFailedListEl.innerHTML = "";
    doneFailedListEl.classList.add("hidden");
    progressFill.style.width = "0%";
    progressText.textContent = "Queuedâ€¦";
    progressCiEl.classList.add("hidden");
    progressDisconnectEl.classList.add("hidden");
    progressDisconnectEl.replaceChildren();
    doneCiEl.classList.add("hidden");
    doneCiEl.textContent = "";
    for (const chip of phaseRow.querySelectorAll(".pl-phase-chip")) {
      chip.classList.remove("active", "done");
    }
    showOnly(inputPanel);
  }

  // ---- preview ---------------------------------------------------------
  function isLikelyPlaylistUrl(s) {
    // Light client-side guard â€” the backend is authoritative. Just enough to
    // catch an obvious mis-paste so we don't 500ms-spin on garbage.
    if (!s) return false;
    try {
      const u = new URL(s);
      if (!/youtube\.com$|youtu\.be$/.test(u.hostname.replace(/^www\.|^m\./, ""))) return false;
      return u.searchParams.has("list") || u.pathname.includes("/playlist");
    } catch {
      return false;
    }
  }

  previewBtn.addEventListener("click", async () => {
    const raw = (urlInput.value || "").trim();
    clearError();
    if (!isLikelyPlaylistUrl(raw)) {
      showError("That doesn't look like a YouTube playlist URL.");
      return;
    }
    previewBtn.disabled = true;
    previewBtn.textContent = "Previewingâ€¦";
    try {
      const res = await STC.playlistPreview(raw);
      if (!res || !res.ok || !res.playlist) {
        showError((res && res.error) || "Couldn't preview that playlist.");
        return;
      }
      previewedUrl = raw;
      previewedPlaylist = res.playlist;
      renderPreview(res.playlist);
      showOnly(previewPanel);
    } catch (e) {
      showError(`Preview failed: ${e && e.message || e}`);
    } finally {
      previewBtn.disabled = false;
      previewBtn.textContent = "Preview";
    }
  });

  function renderPreview(playlist) {
    // Playlist heading line + uploader.
    previewPlaylistTitleEl.textContent = playlist.title || "(untitled playlist)";
    const uploader = fmtNullable(playlist.uploader);
    const vc = playlist.video_count != null ? playlist.video_count : (playlist.videos || []).length;
    const willProc = playlist.will_process_count != null ? playlist.will_process_count : (playlist.videos || []).length;
    previewSubtitleEl.textContent = `${uploader} Â· ${willProc} of ${vc} videos`;

    // Message (e.g., "Playlist has 12 videos -- uoinking the first 10.")
    // is displayed as the warnings strip when present alongside warnings,
    // otherwise we surface it inside the warnings strip too â€” it carries
    // the same "be aware of the cap" signal as the warnings list.
    // Per the contract, prefer `message` (human copy) when both exist;
    // fall back to the raw warnings list when only warnings are present.
    const warnings = playlist.warnings || [];
    if (playlist.message) {
      renderWarnings(previewWarningsEl, [playlist.message]);
    } else {
      renderWarnings(previewWarningsEl, warnings);
    }

    // Video list â€” contract shape: {index, id, url, title, channel, duration_seconds}
    previewListEl.innerHTML = "";
    for (const v of (playlist.videos || [])) {
      const row = document.createElement("div");
      row.className = "pl-video";

      // Thumb from YouTube's standard mqdefault path. The onerror swap is
      // what handles mock IDs (which 404) and the offline case.
      const img = document.createElement("img");
      img.className = "pl-thumb";
      img.alt = "";
      if (v.id) img.src = `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`;
      else img.src = PLACEHOLDER_THUMB;
      img.addEventListener("error", () => {
        if (img.src !== PLACEHOLDER_THUMB) img.src = PLACEHOLDER_THUMB;
      });
      row.appendChild(img);

      const meta = document.createElement("div");
      meta.className = "pl-meta";
      const title = document.createElement("div");
      title.className = "pl-title";
      title.textContent = v.title || "(untitled)";
      const sub = document.createElement("div");
      sub.className = "pl-duration";
      // channel and duration_seconds may both be null per the contract.
      // Use the nullable-format helper instead of erroring.
      const channelLabel = fmtNullable(v.channel);
      const durationLabel = fmtDuration(v.duration_seconds);
      sub.textContent = `${channelLabel} Â· ${durationLabel}`;
      meta.appendChild(title);
      meta.appendChild(sub);
      row.appendChild(meta);

      previewListEl.appendChild(row);
    }

    startBtn.disabled = !(playlist.videos && playlist.videos.length);
  }

  // ---- start -----------------------------------------------------------
  startBtn.addEventListener("click", async () => {
    if (!previewedUrl) return;
    startBtn.disabled = true;
    startBtn.textContent = "Startingâ€¦";
    try {
      // Sprint 5: source interval from the same chrome.storage.sync setting
      // single-video uses, so the popup's interval slider actually applies
      // to playlist jobs. Backend defaults to 30 if we sent nothing.
      const interval = await STC.getInterval();
      const res = await STC.playlistStart(previewedUrl, interval);
      // Contract: returns both top-level job_id and nested job.
      if (!res || !res.ok || !res.job_id) {
        showError((res && res.error) || "Couldn't start playlist uoink.");
        showOnly(inputPanel);
        return;
      }
      activeJobId = res.job_id;
      lastJob = res.job || null;

      // Pre-paint the progress panel from the start response so we don't
      // wait a poll tick for the title/warnings/message to appear.
      progressFill.style.width = "0%";
      const total = (res.job && res.job.videos_total) ||
        (previewedPlaylist && previewedPlaylist.will_process_count) ||
        PLAYLIST_CAP;
      progressText.textContent = `Queued â€” ${total} videos`;
      progressPlaylistTitleEl.textContent =
        (res.job && res.job.playlist_title) ||
        (previewedPlaylist && previewedPlaylist.title) || "";
      progressPlaylistTitleEl.classList.toggle("hidden", !progressPlaylistTitleEl.textContent);
      setText(progressMessageEl, (res.job && res.job.message) || "");
      renderWarnings(progressWarningsEl, (res.job && res.job.warnings) || []);

      for (const chip of phaseRow.querySelectorAll(".pl-phase-chip")) {
        chip.classList.remove("active", "done");
      }
      showOnly(progressPanel);
      startPolling();
    } catch (e) {
      showError(`Start failed: ${e && e.message || e}`);
      showOnly(inputPanel);
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "Uoink playlist";
    }
  });

  // ---- polling ---------------------------------------------------------
  // Sprint 5: polling becomes self-healing. A transient network blip used to
  // silently swallow errors and let the progress panel freeze. Now we count
  // consecutive failures; after STALL_THRESHOLD the panel shows a banner
  // and the poll cadence downshifts to SLOW_POLL_MS so a recovered helper
  // auto-reconnects without burning the user's network. A single successful
  // poll resets both the counter and the cadence.
  //
  // Sprint 6: the banner now includes an inline "Open setup guide" link
  // (item 1) and, after AUTO_OPEN_SETUP_MS of continuous disconnect, the
  // popup auto-opens the setup guide once per episode (item 2).
  const STALL_THRESHOLD = 5;     // consecutive failures before banner shows
  const SLOW_POLL_MS = 10_000;   // recovery cadence once stalled
  const AUTO_OPEN_SETUP_MS = 30_000; // total disconnect before auto-opening setup
  let pollFailures = 0;
  let pollCadence = POLL_MS;     // current interval between pollOnce ticks
  let bannerPainted = false;     // banner DOM built this stall episode
  // _disconnectStartTs is set on the FIRST failure (not the threshold cross)
  // so the 30s auto-open timer measures actual disconnect duration, not
  // banner-visibility duration. Threshold-cross would make the auto-open
  // fire at ~35s of disconnect, which is harder to reason about.
  let disconnectStartTs = 0;
  let setupAutoOpened = false;

  const SETUP_OFFLINE_URL = chrome.runtime.getURL("setup.html?source=offline");

  // Sprint 7: persisted rate-limit so the popup doesn't auto-open the setup
  // guide on every popup-open against a still-offline helper. 5 minutes is
  // long enough that a user who closed the tab on purpose isn't pestered,
  // short enough that a sustained outage with multiple popup opens still
  // eventually re-surfaces the guide as a reminder.
  const AUTO_OPEN_RATE_LIMIT_MS = 5 * 60 * 1000;
  const AUTO_OPEN_TIMESTAMP_KEY = "uoink_setup_auto_open_at";

  function _shouldSuppressAutoOpen() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ [AUTO_OPEN_TIMESTAMP_KEY]: 0 }, (items) => {
          const last = (items && items[AUTO_OPEN_TIMESTAMP_KEY]) || 0;
          resolve(Date.now() - last < AUTO_OPEN_RATE_LIMIT_MS);
        });
      } catch { resolve(false); }
    });
  }

  function _markAutoOpened() {
    try {
      chrome.storage.local.set({ [AUTO_OPEN_TIMESTAMP_KEY]: Date.now() });
    } catch { /* non-fatal: rate limit becomes per-session if storage fails */ }
  }

  async function _maybeAutoOpenSetup() {
    if (await _shouldSuppressAutoOpen()) {
      console.info("[playlist] auto-open setup suppressed by rate limit");
      return;
    }
    try {
      chrome.tabs.create({ url: SETUP_OFFLINE_URL, active: true });
      _markAutoOpened();
    } catch (e) {
      console.warn("[playlist] auto-open setup failed", e);
    }
  }

  function startPolling() {
    stopPolling();
    pollFailures = 0;
    pollCadence = POLL_MS;
    bannerPainted = false;
    disconnectStartTs = 0;
    setupAutoOpened = false;
    progressDisconnectEl.classList.add("hidden");
    progressDisconnectEl.replaceChildren();
    pollOnce();
    pollTimer = setInterval(pollOnce, pollCadence);
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function _setPollCadence(ms) {
    if (ms === pollCadence) return;
    pollCadence = ms;
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = setInterval(pollOnce, pollCadence);
    }
  }

  // Build the banner DOM once per stall episode. createElement-only
  // (no innerHTML interpolation) per the XSS discipline established in
  // Sprint 5 â€” even though the strings here are static, keeping the
  // pattern consistent avoids future-PR regressions.
  function _paintDisconnectBanner() {
    progressDisconnectEl.replaceChildren();
    const text = document.createElement("span");
    text.textContent =
      "Helper offline. Open setup -> Helper status to diagnose. ";
    progressDisconnectEl.appendChild(text);
    const link = document.createElement("a");
    link.textContent = "Open setup guide";
    link.href = "#";
    // Sprint 9: aria-label tells screen readers what the link does AND
    // that activation opens a new tab â€” a11y polish deferred from Sprint 6.
    link.setAttribute("aria-label", "Opens setup guide in a new tab");
    link.style.color = "#ffd9d9";
    link.style.textDecoration = "underline";
    link.style.cursor = "pointer";
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      chrome.tabs.create({ url: SETUP_OFFLINE_URL, active: true });
    });
    progressDisconnectEl.appendChild(link);
    progressDisconnectEl.classList.remove("hidden");
  }

  function _onPollSuccess() {
    if (pollFailures === 0 && pollCadence === POLL_MS && !bannerPainted) return;
    pollFailures = 0;
    bannerPainted = false;
    disconnectStartTs = 0;
    setupAutoOpened = false;
    progressDisconnectEl.classList.add("hidden");
    progressDisconnectEl.replaceChildren();
    _setPollCadence(POLL_MS);
  }

  function _onPollFailure(reason) {
    pollFailures++;
    // Track the start of the disconnect episode on the very first failure,
    // not the threshold cross â€” see comment above on disconnectStartTs.
    if (disconnectStartTs === 0) disconnectStartTs = Date.now();
    if (pollFailures < STALL_THRESHOLD) return;

    // Paint the banner once on threshold cross; don't repaint per tick.
    // Repainting would re-attach the click handler unnecessarily and
    // (subtly) reset any text-selection the user had on the banner.
    if (!bannerPainted) {
      _paintDisconnectBanner();
      bannerPainted = true;
      _setPollCadence(SLOW_POLL_MS);
    }

    // Item 2 (Sprint 6 + 7): after AUTO_OPEN_SETUP_MS of continuous
    // disconnect, attempt to open the setup guide once per episode.
    // _onPollSuccess clears the in-memory flag so a recovered-then-
    // relapsed connection can re-trigger after another 30s.
    // Sprint 7 adds a chrome.storage.local rate-limit on top: even
    // within the in-memory flag rules, if the last auto-open happened
    // less than AUTO_OPEN_RATE_LIMIT_MS ago (across popup sessions),
    // suppress the tab open. We set setupAutoOpened = true BEFORE the
    // async storage check so a fast-firing poll doesn't double-spawn
    // the async work; if the rate-limit suppresses the open, the flag
    // stays set for the rest of this episode (matching spec: "suppress
    // auto-open even after 30s of disconnect this episode").
    if (!setupAutoOpened &&
        disconnectStartTs > 0 &&
        Date.now() - disconnectStartTs >= AUTO_OPEN_SETUP_MS) {
      setupAutoOpened = true;
      _maybeAutoOpenSetup();
    }

    if (reason) console.warn("[playlist] poll stalled:", reason);
  }

  async function pollOnce() {
    if (!activeJobId) return;
    let res;
    try {
      res = await STC.jobStatus(activeJobId);
    } catch (e) {
      _onPollFailure(e);
      return;
    }
    if (!res || !res.ok) {
      // ok:false with a non-recoverable error -> fail the job. But a
      // transient {ok: false} without a recognisable error string is also
      // treated as a poll failure (helper restarted mid-call, body parse
      // failed, etc) â€” give it the stall budget before declaring failure.
      const err = res && res.error;
      if (err && /not found|invalid/i.test(String(err))) {
        stopPolling();
        enterFailed(err);
        return;
      }
      _onPollFailure(err || "no response");
      return;
    }
    if (!res.job) {
      _onPollFailure("missing job field");
      return;
    }
    _onPollSuccess();
    const job = res.job;
    lastJob = job;
    renderProgress(job);

    if (job.state === "completed") {
      stopPolling();
      resultPayload = job.result || null;
      await onCompleted(job);
    } else if (job.state === "cancelled") {
      stopPolling();
      onCancelled(job);
    } else if (job.state === "failed") {
      stopPolling();
      enterFailed(job.error || "Playlist uoink failed.");
    }
  }

  function renderProgress(job) {
    const total = job.videos_total ||
      (previewedPlaylist && previewedPlaylist.will_process_count) ||
      PLAYLIST_CAP;
    const done = job.videos_done || 0;
    const failed = job.videos_failed || 0;
    // Progress = successful + failed (both consume a "slot"), so the bar
    // doesn't stall when a video fails.
    const advanced = Math.min(total, done + failed);
    const pct = total > 0 ? Math.min(100, Math.round((advanced / total) * 100)) : 0;
    progressFill.style.width = `${pct}%`;

    if (job.state === "queued") {
      progressText.textContent = `Queued â€” ${total} videos`;
    } else if (job.current_video) {
      const title = job.current_video.title || "(untitled)";
      const idx = job.current_video.index || (advanced + 1);
      progressText.textContent = `Video ${idx} of ${total}: ${title}`;
    } else if (job.state === "running") {
      progressText.textContent = `${done} of ${total} videos done`;
    }

    setText(progressMessageEl, job.message || "");
    renderWarnings(progressWarningsEl, job.warnings || []);
    if (job.playlist_title) {
      progressPlaylistTitleEl.textContent = job.playlist_title;
      progressPlaylistTitleEl.classList.remove("hidden");
    }

    // Sprint 2: Comment Intelligence indicator. Only when the current video
    // is actually in the comments phase AND the user has CI enabled.
    // Comments phase runs in the background; we tell the user it won't
    // block playlist progress so they don't think the bar has stalled.
    const ciEnabled = !!(cachedSettings && cachedSettings.comment_intelligence_enabled);
    const inCommentsPhase = job.current_video_phase === "comments";
    progressCiEl.classList.toggle("hidden", !(ciEnabled && inCommentsPhase));

    // Phase chips: highlight active, mark prior phases done.
    const activeIdx = PHASES.indexOf(job.current_video_phase);
    for (const chip of phaseRow.querySelectorAll(".pl-phase-chip")) {
      const phase = chip.dataset.phase;
      const idx = PHASES.indexOf(phase);
      chip.classList.remove("active", "done");
      if (activeIdx < 0) continue;
      if (idx < activeIdx) chip.classList.add("done");
      else if (idx === activeIdx) chip.classList.add("active");
    }

    // Sprint 6 (item 4): keep the single-video pill in sync with progress.
    // Cheap to call every tick; the function short-circuits when the pill
    // is already in the right state.
    _renderActivePlaylistPill();
  }

  // ---- cancel ----------------------------------------------------------
  cancelBtnEl.addEventListener("click", async () => {
    if (!activeJobId) return;
    cancelBtnEl.disabled = true;
    cancelBtnEl.textContent = "Cancellingâ€¦";
    try {
      const res = await STC.jobCancel(activeJobId);
      // Contract: cancel returns the full updated job. If we got it, render
      // the cancelled view immediately instead of waiting for the next poll
      // tick â€” same data, faster transition.
      if (res && res.ok && res.job) {
        stopPolling();
        lastJob = res.job;
        _renderActivePlaylistPill();
        onCancelled(res.job);
      }
      // If res.ok is false (e.g. "job is already finished"), let the next
      // poll tick observe the real terminal state.
    } catch (e) {
      console.warn("[playlist] cancel failed", e);
    } finally {
      // Reset button state in case the panel hasn't flipped yet.
      setTimeout(() => {
        cancelBtnEl.disabled = false;
        cancelBtnEl.textContent = "Cancel";
      }, 1500);
    }
  });

  function onCancelled(job) {
    const done = job.videos_done || 0;
    const failed = job.videos_failed || 0;
    const total = job.videos_total || PLAYLIST_CAP;
    cancelledSummaryEl.textContent = "Cancelled.";
    setText(cancelledMetaEl, `${done} of ${total} videos completed${failed ? ` Â· ${failed} failed` : ""}`);
    setText(cancelledMessageEl, job.message || "");
    renderWarnings(cancelledWarningsEl, job.warnings || []);
    showOnly(cancelledPanel);
  }

  // ---- completion ------------------------------------------------------
  async function onCompleted(job) {
    const result = job.result || {};
    let copied = false;
    const corpusText = result.combined_md_text || "";
    if (corpusText) {
      try {
        await navigator.clipboard.writeText(corpusText);
        copied = true;
      } catch {
        try {
          const r = await chrome.runtime.sendMessage({
            type: "copyToClipboard",
            text: corpusText,
          });
          copied = !!(r && r.ok);
        } catch { /* leave copied=false */ }
      }
    }

    const perVideo = result.per_video || [];
    const successCount = perVideo.filter((p) => p.ok).length;
    const failedVideos = perVideo.filter((p) => p.ok === false);
    const kb = corpusText ? (corpusText.length / 1024).toFixed(1) : "0";

    doneSummary.textContent = copied
      ? "Done â€” corpus copied to clipboard"
      : "Done â€” clipboard blocked, open the folder";

    const totalProcessed = perVideo.length || job.videos_total || 0;
    const metaBits = [`${successCount} of ${totalProcessed} videos`, `${kb} KB combined`];
    if (failedVideos.length) metaBits.splice(1, 0, `${failedVideos.length} failed`);
    doneMeta.textContent = metaBits.join(" Â· ");

    setText(doneMessageEl, job.message || "");
    renderWarnings(doneWarningsEl, job.warnings || []);
    renderFailedList(failedVideos);

    // Sprint 3: CI/Hook still-running indicator. Shown when either feature
    // is enabled (and the user has a key set); the per-video .md files
    // keep updating on disk after the playlist transitions to completed.
    const aiCopy = buildBackgroundAiIndicator(cachedSettings);
    doneCiEl.textContent = aiCopy;
    doneCiEl.classList.toggle("hidden", !aiCopy);

    showOnly(donePanel);

    if (copied) {
      markClipboardUoinkNow();
      STC.logEngagement("paste", "popup", { length: corpusText.length }).catch(() => {});
      showToast("Playlist uoinked! Paste in Claude or ChatGPT.");
    }
  }

  function renderFailedList(failed) {
    doneFailedListEl.innerHTML = "";
    if (!failed.length) {
      doneFailedListEl.classList.add("hidden");
      return;
    }
    for (const f of failed) {
      const item = document.createElement("div");
      item.className = "pl-failed-item";

      const titleLine = document.createElement("div");
      const icon = document.createElement("span");
      icon.className = "pl-failed-icon";
      icon.textContent = "âš ";
      const titleSpan = document.createElement("span");
      titleSpan.className = "pl-failed-title";
      titleSpan.textContent = `#${f.index} ${f.title || "(untitled)"}`;
      titleLine.appendChild(icon);
      titleLine.appendChild(titleSpan);
      item.appendChild(titleLine);

      const errLine = document.createElement("div");
      errLine.className = "pl-failed-error";
      errLine.textContent = f.error || "Failed (no detail provided).";
      item.appendChild(errLine);

      doneFailedListEl.appendChild(item);
    }
    doneFailedListEl.classList.remove("hidden");
  }

  // Sprint 2: Open Folder targets job.session_folder, which the contract
  // guarantees is populated from `queued` onwards and through every terminal
  // state (cancelled, failed, completed). Fall back to result.combined_md_path
  // only defensively (older job snapshots before Sprint 2).
  async function openSessionFolder() {
    const path =
      (lastJob && lastJob.session_folder) ||
      (resultPayload && resultPayload.combined_md_path) ||
      null;
    if (!path) {
      showToast("No folder path available.");
      return;
    }
    try {
      // openFolder is the existing v1 server endpoint â€” in mock mode the
      // server may not be running, in which case the toast below is the
      // recovery.
      const res = await STC.openFolder(path);
      if (!res || res.ok === false) showToast("Couldn't open folder â€” server may be offline.");
    } catch {
      showToast("Couldn't open folder â€” server may be offline.");
    }
  }
  openFolderBtn.addEventListener("click", openSessionFolder);
  cancelledFolderBtn.addEventListener("click", openSessionFolder);
  failedFolderBtn.addEventListener("click", openSessionFolder);

  startAnotherBtn.addEventListener("click", resetPlaylistUI);
  cancelledRestartBtn.addEventListener("click", resetPlaylistUI);
  failedRestartBtn.addEventListener("click", resetPlaylistUI);

  function enterFailed(msg) {
    failedMsg.textContent = msg;
    showOnly(failedPanel);
  }

  // ---- Sprint 6 (item 3): last-uoink completed affordance --------------
  // 30-minute window picked over 60 or 15: shorter than 60 keeps the popup
  // honest about "recent" (a uoink from 45 min ago is probably out of mind
  // and clutters the surface), longer than 15 covers the case where the
  // user starts an uoink, walks away, and comes back to finish reading.
  // No dismissal Ã— yet â€” auto-expiry covers most of the value, and adding
  // a per-job dismissal-storage was deemed not worth the complexity for
  // first ship. Document if we hit user pushback.
  const LAST_UOINK_WINDOW_MS = 30 * 60 * 1000;
  const lastUoinkEl = document.getElementById("pl-last-uoink");
  const lastUoinkPrefixEl = document.getElementById("pl-last-uoink-prefix");
  const lastUoinkTitleEl = document.getElementById("pl-last-uoink-title");
  const lastUoinkSuffixEl = document.getElementById("pl-last-uoink-suffix");
  const lastUoinkBtn = document.getElementById("pl-last-uoink-btn");

  function _hideLastUoink() {
    if (lastUoinkEl) lastUoinkEl.classList.add("hidden");
    if (lastUoinkBtn) lastUoinkBtn.onclick = null;
  }

  function _renderLastUoink(job) {
    if (!lastUoinkEl || !lastUoinkTitleEl || !lastUoinkBtn) return;
    if (!job) { _hideLastUoink(); return; }
    // Sprint 7: kind-aware label per the updated /jobs contract.
    // Single jobs populate `title`; playlist jobs populate `playlist_title`.
    // Both fields go through textContent so a hostile YouTube-side title
    // (yt-dlp surfaces it as-is) can't inject markup.
    let prefix, label, suffix = "";
    if (job.kind === "single") {
      prefix = "Last uoink: ";
      label = job.title || job.source_url || "Single video";
    } else {
      // Default to playlist for any non-single kind (today only "playlist"
      // exists; defensively handle future kinds with the same shape).
      prefix = "Last playlist: ";
      label = job.playlist_title || "Playlist";
      const count = typeof job.videos_done === "number" ? job.videos_done : 0;
      if (count > 0) suffix = ` (${count} video${count === 1 ? "" : "s"})`;
    }
    if (lastUoinkPrefixEl) lastUoinkPrefixEl.textContent = prefix;
    lastUoinkTitleEl.textContent = label;
    if (lastUoinkSuffixEl) lastUoinkSuffixEl.textContent = suffix;
    lastUoinkBtn.onclick = async () => {
      const path = job.session_folder;
      if (!path) {
        showToast("No folder path available.");
        return;
      }
      try {
        const res = await STC.openFolder(path);
        if (!res || res.ok === false) {
          showToast("Couldn't open folder â€” server may be offline.");
        }
      } catch {
        showToast("Couldn't open folder â€” server may be offline.");
      }
    };
    lastUoinkEl.classList.remove("hidden");
  }

  function _isRecentCompleted(job) {
    if (!job || job.state !== "completed") return false;
    if (typeof job.videos_done !== "number" || job.videos_done <= 0) return false;
    if (!job.completed_at) return false;
    const t = Date.parse(job.completed_at);
    if (Number.isNaN(t)) return false;
    return (Date.now() - t) < LAST_UOINK_WINDOW_MS;
  }

  // ---- boot ------------------------------------------------------------
  // Sprint 5: try to recover an in-flight playlist job before settling into
  // the default input view. If the user closed the popup mid-job, the helper
  // is still running the work in-process and `GET /jobs` will return it.
  // When we find a non-terminal job we flip into playlist mode, repaint the
  // progress panel from the snapshot, and resume polling. If none found,
  // default to the input panel as before.
  // Sprint 6 (item 3): if no in-flight job is found, look for a recently
  // completed job (within LAST_UOINK_WINDOW_MS) and surface an "Open folder"
  // affordance on the playlist input panel.
  showOnly(inputPanel);
  (async function recoverActiveJob() {
    let res;
    try {
      res = await STC.jobsList();
    } catch { return; }
    if (!res || !res.ok || !Array.isArray(res.jobs)) return;
    const sortedByUpdated = [...res.jobs]
      .filter((j) => j && j.id)
      .sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
    const active = sortedByUpdated.find(
      (j) => j.state === "queued" || j.state === "running"
    );
    if (active) {
      activeJobId = active.id;
      lastJob = active;
      progressFill.style.width = "0%";
      for (const chip of phaseRow.querySelectorAll(".pl-phase-chip")) {
        chip.classList.remove("active", "done");
      }
      renderProgress(active);
      showOnly(progressPanel);
      setMode("playlist");
      startPolling();
      return;
    }
    // No in-flight job â€” look for a recently completed one. Sort by
    // completed_at desc (falling back to updated_at if completed_at is
    // missing) and pick the freshest.
    const recent = res.jobs
      .filter(_isRecentCompleted)
      .sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || "")))[0];
    if (recent) _renderLastUoink(recent);
  })();
})();

// =====================================================================
// v3 â€” Smart Screenshot Picker
// =====================================================================
// Activates when chrome.storage.local.pending_picker is set by the
// background or content-script intercept. When active, the picker view
// owns the popup surface (mode selector and both mode panels hide). On
// Copy/Cancel: writes the chosen corpus to clipboard, clears the pending
// state, opens Claude, and closes the popup â€” same end behavior as v1
// auto-copy, just user-mediated.
// ---------------------------------------------------------------------

(function setupPickerMode() {
  const pickerMode = document.getElementById("picker-mode");
  const modeSelectorWrap = document.getElementById("mode-selector-wrap");
  const modeSingleEl = document.getElementById("mode-single");
  const modePlaylistEl = document.getElementById("mode-playlist");
  const pickerTitleEl = document.getElementById("picker-title");
  const pickerSourceMetaEl = document.getElementById("picker-source-meta");
  const pickerCountEl = document.getElementById("picker-count");
  const pickerSelectAllLink = document.getElementById("picker-select-all");
  const pickerGridEl = document.getElementById("picker-grid");
  const pickerErrorEl = document.getElementById("picker-error");
  const pickerDoneIndicatorEl = document.getElementById("picker-done-indicator");
  const pickerCancelBtn = document.getElementById("picker-cancel-btn");
  const pickerCopyBtn = document.getElementById("picker-copy-btn");

  // ---- State ----
  let pendingPicker = null;
  let screenshots = [];      // [{ alt, path }] parsed from yoink_md
  let selectedSet = new Set(); // 0-based indices selected for copy
  let cachedSettings = null;
  let thumbCache = new Map();  // path -> blob/data URL (avoid refetching)

  // One-time settings snapshot for the CI/Hook done indicator. Same
  // pattern as the playlist controller (its own fetch is isolated from
  // this one â€” cheap enough that the duplication is worth the
  // encapsulation).
  (async function loadSettings() {
    try {
      const res = await STC.getSettings();
      if (res && res.ok && res.settings) cachedSettings = res.settings;
    } catch { /* settings fetch is non-fatal */ }
  })();

  // ---- Visibility ----
  function showPicker() {
    pickerMode.classList.remove("hidden");
    modeSelectorWrap.classList.add("hidden");
    modeSingleEl.classList.add("hidden");
    modePlaylistEl.classList.add("hidden");
  }
  function hidePicker() {
    pickerMode.classList.add("hidden");
    modeSelectorWrap.classList.remove("hidden");
    // Whichever mode the user was in before the picker activated isn't
    // tracked â€” restoring to single-video matches the v1 boot default.
    modeSingleEl.classList.remove("hidden");
    modePlaylistEl.classList.add("hidden");
  }

  // ---- Parse screenshots from yoink_md ----
  // Match the file-reference markdown: ![alt](C:/.../shot_0001.jpg).
  // Tolerant of leading whitespace; rejects data: URLs (those belong to
  // the multimodal paste corpus, not the canonical screenshot list).
  function parseScreenshots(uoinkMd) {
    if (!uoinkMd) return [];
    const out = [];
    const re = /!\[([^\]]*)\]\(([^)]+)\)/g;
    let m;
    while ((m = re.exec(uoinkMd)) !== null) {
      const src = m[2].trim();
      if (src.startsWith("data:")) continue;
      out.push({ alt: m[1] || "", path: src });
    }
    return out;
  }

  // Build a filtered corpus by removing image lines at the given drop
  // indices. Operates on whichever corpus the user wants to send to
  // clipboard â€” for the multimodal-paste case (corpus_md_paste) this
  // preserves the base64-embedded form for KEPT screenshots while
  // dropping unselected ones. Image lines are matched in source order
  // and aligned to the yoink_md parse positionally.
  function buildFilteredCorpus(sourceCorpus, dropIndices) {
    if (!sourceCorpus) return "";
    if (!dropIndices || !dropIndices.length) return sourceCorpus;
    const lines = sourceCorpus.split(/\r?\n/);
    const imgLineIndices = [];
    const re = /!\[[^\]]*\]\([^)]+\)/;
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) imgLineIndices.push(i);
    }
    const dropSet = new Set();
    for (const idx of dropIndices) {
      if (idx >= 0 && idx < imgLineIndices.length) {
        dropSet.add(imgLineIndices[idx]);
      }
    }
    return lines.filter((_, i) => !dropSet.has(i)).join("\n");
  }

  // ---- Rendering ----
  function updateCount() {
    pickerCountEl.textContent =
      `${selectedSet.size} of ${screenshots.length} selected`;
    pickerSelectAllLink.textContent =
      selectedSet.size === screenshots.length ? "Deselect all" : "Select all";
    pickerCopyBtn.disabled = false; // 0-selected is a valid (text-only) copy
  }

  function renderGrid() {
    pickerGridEl.innerHTML = "";
    if (!screenshots.length) {
      const empty = document.createElement("div");
      empty.className = "picker-empty";
      empty.textContent = "No screenshots found in this uoink.";
      pickerGridEl.appendChild(empty);
      pickerCopyBtn.disabled = false; // copy the unmodified corpus
      pickerSelectAllLink.classList.add("hidden");
      return;
    }
    pickerSelectAllLink.classList.remove("hidden");
    for (let i = 0; i < screenshots.length; i++) {
      const s = screenshots[i];
      const tile = document.createElement("div");
      tile.className = "picker-thumb loading";
      if (selectedSet.has(i)) tile.classList.add("selected");
      tile.dataset.index = String(i);
      tile.title = s.alt || s.path;

      const img = document.createElement("img");
      img.alt = s.alt || "";
      // Lazy-load thumbnails. The grid is typically <20 items; firing
      // them all in parallel is fine for local server load.
      _loadThumb(s.path).then((src) => {
        img.src = src;
        tile.classList.remove("loading");
      }).catch((err) => {
        tile.classList.remove("loading");
        console.warn("[picker] thumb load failed", s.path, err);
        // Leave the diagonal-stripe loading background visible so the
        // tile is still clickable (user can include/exclude even when
        // the thumb didn't render).
      });
      tile.appendChild(img);

      const idxBadge = document.createElement("div");
      idxBadge.className = "picker-thumb-index";
      idxBadge.textContent = String(i + 1);
      tile.appendChild(idxBadge);

      const check = document.createElement("div");
      check.className = "picker-thumb-check";
      check.textContent = "âœ“";
      tile.appendChild(check);

      tile.addEventListener("click", () => toggleIndex(i));
      pickerGridEl.appendChild(tile);
    }
  }

  async function _loadThumb(path) {
    if (thumbCache.has(path)) return thumbCache.get(path);
    const src = await STC.getScreenshotThumbnail(path);
    thumbCache.set(path, src);
    return src;
  }

  // Sprint 4 (1c): real-mode thumbnails come back as blob: URLs from
  // URL.createObjectURL(). Revoke them on picker exit so they don't sit
  // in memory until popup unload. Mock-mode entries are data: URLs â€” no
  // revocation needed (and revoking a data URL is a no-op anyway, but
  // skipping the call keeps the loop cheap on large grids).
  function _revokeThumbBlobs() {
    for (const src of thumbCache.values()) {
      if (typeof src === "string" && src.startsWith("blob:")) {
        try { URL.revokeObjectURL(src); }
        catch (e) { console.warn("[picker] revoke failed", e); }
      }
    }
    thumbCache.clear();
  }

  function toggleIndex(i) {
    if (selectedSet.has(i)) selectedSet.delete(i);
    else selectedSet.add(i);
    const tile = pickerGridEl.querySelector(`[data-index="${i}"]`);
    if (tile) tile.classList.toggle("selected", selectedSet.has(i));
    updateCount();
  }

  pickerSelectAllLink.addEventListener("click", () => {
    if (selectedSet.size === screenshots.length) {
      selectedSet.clear();
    } else {
      selectedSet = new Set(screenshots.map((_, i) => i));
    }
    for (const tile of pickerGridEl.querySelectorAll(".picker-thumb")) {
      const i = parseInt(tile.dataset.index, 10);
      tile.classList.toggle("selected", selectedSet.has(i));
    }
    updateCount();
  });
  wireKeyActivation(pickerSelectAllLink);

  // ---- Activation ----
  function showError(msg) {
    pickerErrorEl.textContent = msg || "";
    pickerErrorEl.classList.toggle("hidden", !msg);
  }

  // Sprint 4 (1b): relative-time helper for the picker source meta line.
  // Two-uoinks-back-to-back disambiguation: when pending_picker gets
  // overwritten, the user sees "just now" vs "3m ago" so they know which
  // uoink they're looking at. Falls back to ISO date for older stashes
  // (shouldn't happen in practice â€” pending_picker is cleared on copy).
  function formatRelativeTime(iso) {
    if (!iso) return "";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "";
    const diffSec = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (diffSec < 10) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) {
      const m = Math.round(diffSec / 60);
      return `${m}m ago`;
    }
    if (diffSec < 86400) {
      const h = Math.round(diffSec / 3600);
      return `${h}h ago`;
    }
    return iso.slice(0, 10); // YYYY-MM-DD fallback
  }

  function activate(payload) {
    pendingPicker = payload || null;
    if (!pendingPicker) { hidePicker(); return; }
    showError("");
    pickerTitleEl.textContent = pendingPicker.title || "Untitled video";
    const rel = formatRelativeTime(pendingPicker.yoinked_at);
    pickerSourceMetaEl.textContent = rel ? `Uoinked ${rel}` : "";
    screenshots = parseScreenshots(pendingPicker.yoink_md);
    selectedSet = new Set(screenshots.map((_, i) => i)); // default all selected
    _revokeThumbBlobs(); // release any prior-payload blobs before reusing
    renderGrid();
    updateCount();

    // CI/Hook indicator on the picker (single-video done surface).
    const aiCopy = buildBackgroundAiIndicator(cachedSettings);
    pickerDoneIndicatorEl.textContent = aiCopy;
    pickerDoneIndicatorEl.classList.toggle("hidden", !aiCopy);

    showPicker();
  }

  // ---- Finish actions (Copy / Cancel) ----
  async function _writeClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      STC.logEngagement("paste", "popup", { length: text.length }).catch(() => {});
      return true;
    } catch {
      try {
        const r = await chrome.runtime.sendMessage({
          type: "copyToClipboard", text,
        });
        const ok = !!(r && r.ok);
        if (ok) {
          STC.logEngagement("paste", "popup", { length: text.length }).catch(() => {});
        }
        return ok;
      } catch { return false; }
    }
  }

  async function _clearPending() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.remove("pending_picker", () => resolve());
      } catch { resolve(); }
    });
  }

  async function _finish(kind /* "copy" | "cancel" */) {
    if (!pendingPicker) { hidePicker(); return; }
    pickerCopyBtn.disabled = true;
    pickerCancelBtn.disabled = true;
    pickerCopyBtn.textContent = kind === "copy" ? "Copyingâ€¦" : "Cancellingâ€¦";

    // Source corpus: prefer multimodal paste so KEPT screenshots stay
    // base64-embedded. Falls back to yoink_md when corpus_md_paste isn't
    // present (dev mode without Pillow, etc).
    const sourceCorpus =
      pendingPicker.corpus_md_paste || pendingPicker.yoink_md || "";

    let clipboardText;
    if (kind === "copy") {
      const dropIndices = [];
      for (let i = 0; i < screenshots.length; i++) {
        if (!selectedSet.has(i)) dropIndices.push(i);
      }
      clipboardText = buildFilteredCorpus(sourceCorpus, dropIndices);
    } else {
      // Cancel = copy unmodified corpus (matches v1 default behavior).
      clipboardText = sourceCorpus;
    }

    const copied = await _writeClipboard(clipboardText);
    await _clearPending();
    _revokeThumbBlobs(); // Sprint 4 (1c): release blob URLs from getScreenshotThumbnail

    if (copied) {
      markClipboardUoinkNow();
      // Open Claude tab to match the v1 auto-copy flow, then close popup.
      try {
        await chrome.tabs.create({ url: "https://claude.ai/new", active: true });
      } catch (e) {
        console.warn("[picker] tab create failed", e);
      }
    } else {
      try {
        await chrome.runtime.sendMessage({ type: "clipboardRetry", text: clipboardText });
      } catch { /* ignore */ }
      window.close();
      return;
    }

    // Sprint 4 (1a): route through STC.buildUoinkedMessage so the picker
    // path gets the same first-uoink CTA treatment as v1 auto-copy. The
    // helper atomically flips has_completed_first_yoink on first success
    // and returns either the first-uoink CTA copy or the topic-aware
    // subsequent copy. We pass a minimal data-shape (only `.topic` is
    // consumed by the helper) reconstituted from the stashed payload.
    try {
      const data = { topic: pendingPicker && pendingPicker.topic };
      const message = await STC.buildUoinkedMessage(data, copied);
      // Title surfaces the picker-specific detail (how many screenshots
      // were kept) so the user-visible signal isn't lost when the message
      // body becomes the standard CTA/topic copy.
      const titleSuffix = kind === "copy"
        ? ` (${selectedSet.size} of ${screenshots.length} screenshots)`
        : "";
      await chrome.runtime.sendMessage({
        type: "notify",
        title: copied ? `Uoinked ★${titleSuffix}` : "Uoink ready (clipboard blocked)",
        message,
      });
    } catch (e) {
      // notify is fire-and-forget; log but don't surface to user
      console.warn("[picker] notify failed", e);
    }

    window.close();
  }

  pickerCopyBtn.addEventListener("click", () => _finish("copy"));
  pickerCancelBtn.addEventListener("click", () => _finish("cancel"));

  // ---- Boot ----
  // On popup open, check if a picker is waiting. Also subscribe to
  // storage changes so an open popup auto-switches if a fresh yoink
  // arrives mid-session.
  function _readPending() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ pending_picker: null }, (items) => {
          resolve((items && items.pending_picker) || null);
        });
      } catch { resolve(null); }
    });
  }
  (async function bootPicker() {
    const p = await _readPending();
    if (p) activate(p);
  })();

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.pending_picker) {
      const next = changes.pending_picker.newValue;
      if (next) activate(next);
      else { _revokeThumbBlobs(); hidePicker(); }
    }
    if (changes[LAST_YOINK_CLIPBOARD_KEY]) {
      lastUoinkAt = Number(changes[LAST_YOINK_CLIPBOARD_KEY].newValue) || 0;
      updateDestButtons();
    }
    if (changes[RECENT_FAILURES_KEY]) {
      loadRecentUoinks();
    }
  });
})();
