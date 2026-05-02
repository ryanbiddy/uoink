// Popup script. STC.* helpers come from lib/extract.js loaded just before.

const DEFAULT_INTERVAL = 30;
const CORPUS_WARN_CHARS = 500_000;

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

// ---- Server status --------------------------------------------------------
async function ping() {
  const data = await STC.ping();
  if (data && data.ok) {
    dot.classList.remove("down"); dot.classList.add("up");
    status.textContent = `Server up (v${data.version || "?"})`;
  } else {
    dot.classList.remove("up"); dot.classList.add("down");
    status.textContent = "Server down — run start_server.bat";
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
  } catch { /* ignore — fall back to local storage */ }
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
      alert(msg); // simple inline error — popup is a tight space
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

// ---- End & Send to Claude -------------------------------------------------
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
    alert(`Couldn't reach server: ${e}`);
    endBtn.disabled = false;
    endBtn.textContent = "End & Send to Claude";
    return;
  }

  if (!res || !res.ok) {
    alert((res && res.error) || "Failed to close session.");
    endBtn.disabled = false;
    endBtn.textContent = "End & Send to Claude";
    return;
  }

  // Copy via background (offscreen). Popups can call navigator.clipboard
  // directly too — try that first for the fast path, then fall back.
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

  // Open Claude
  await chrome.tabs.create({ url: "https://claude.ai/new", active: true });

  // Notify
  const lines = `${fmtCount(res.video_count, "video")}, ${fmtCount(res.caption_count || 0, "caption line")}`;
  const note = copied
    ? `Session sent. ${lines}. Paste in Claude.`
    : `Session closed. ${lines}. Clipboard failed — corpus.md is at the session folder (already open in Explorer).`;
  await chrome.runtime.sendMessage({ type: "notify", title: "Research session sent", message: note });

  // Large-corpus warning
  if ((res.corpus_md || "").length > CORPUS_WARN_CHARS) {
    sessionWarn.classList.remove("hidden");
    sessionWarn.innerHTML =
      `Corpus is ${(res.corpus_md.length / 1000).toFixed(0)}K characters — may exceed Claude's ` +
      `paste-friendly size. Drag <code>corpus.md</code> into Claude instead.<br>` +
      `<button id="open-folder" class="secondary" style="margin-top:6px">Open session folder</button>`;
    document.getElementById("open-folder").addEventListener("click", () => {
      STC.openSession(id);
    });
  }

  endBtn.disabled = false;
  endBtn.textContent = "End & Send to Claude";
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
                     `<span class="meta">${s.video_count} · ${s.status} · ${date}</span>`;
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

// ---- Suggested prompts ----------------------------------------------------
async function loadPrompts() {
  promptsEl.innerHTML = "";
  let prompts = [];
  try {
    const res = await fetch(chrome.runtime.getURL("prompts.json"));
    prompts = await res.json();
  } catch (e) {
    console.warn("[popup] prompts.json missing", e);
    return;
  }
  for (const p of prompts) {
    const row = document.createElement("div");
    row.className = "prompt-item";

    const label = document.createElement("span");
    label.className = "prompt-label";
    label.title = p.text;
    label.textContent = p.label;

    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(p.text);
        btn.textContent = "Copied";
        btn.classList.add("copied");
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
    promptsEl.appendChild(row);
  }
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

// ---- Boot -----------------------------------------------------------------
ping();
loadInterval();
loadPrompts();
refreshQueue();
refreshActiveFromServer();
loadRecentSessions();

const queueTimer = setInterval(refreshQueue, 1000);
const sessionTimer = setInterval(async () => {
  // Periodically pull active session from server in case background updated
  // it while popup was open (e.g. context-menu add finished).
  try { await chrome.runtime.sendMessage({ type: "refreshActiveSession" }); }
  catch { /* ignore */ }
}, 2000);
window.addEventListener("unload", () => {
  clearInterval(queueTimer);
  clearInterval(sessionTimer);
});
