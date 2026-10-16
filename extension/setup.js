// Setup page — drives the install + first-run flow.
//
// Two entry points (distinguished by ?source=...):
//   ?source=install  — opened by background.js after a fresh install. Shows
//                      all four steps top-to-bottom.
//   ?source=offline  — opened by content.js when the user clicks Uoink on
//                      YouTube but the local server is unreachable. Skips
//                      the welcome step and jumps straight to verify.
//
// The "verify" step polls the local server every POLL_MS until it answers,
// then unlocks step 4. Polling stops once the server is up.

// ---- Suggested video for step 4. Edit here to swap. ----------------------
// (Channel-friendly default: a short, popular Lenny's Podcast clip.)
const SUGGESTED_VIDEO = {
  // YouTube watch URL. Used both as the link target and to derive the ID.
  url: "https://www.youtube.com/watch?v=8rABwKRsec4",
  title: "Andrej Karpathy on AGI, hiring, and the future of programming",
  byline: "Lenny's Podcast",
};


// ---- Constants -----------------------------------------------------------
const SERVER = "http://127.0.0.1:5179";
// /health is the canonical liveness probe (added as an alias for /ping in v1).
const PING_PATH = "/health";
const POLL_MS = 2000;
const AUTO_YOINK_TTL_MS = 60_000;
// Latest published, non-prerelease Windows asset. Update only after the
// matching GitHub release asset exists.
const PUBLISHED_INSTALLER_VERSION = "3.8.0";
let platformOs = "win";

// ---- DOM handles ---------------------------------------------------------
const params = new URLSearchParams(location.search);
const source = params.get("source") || "install";
const requestedHash = location.hash || "";
const isSettingsMode = source === "popup"
  || requestedHash === "#mcp-settings"
  || requestedHash === "#skill-settings";
const firstSettingsSection = document.getElementById("comment-intelligence");

const step1 = document.getElementById("step-1");
const step2 = document.getElementById("step-2");
const step3 = document.getElementById("step-3");
const step4 = document.getElementById("step-4");

const getStartedBtn = document.getElementById("get-started-btn");
const skipInstall = document.getElementById("skip-install");
const downloadBtn = document.getElementById("download-btn");

const statusBlock = document.getElementById("status-block");
const statusText = document.getElementById("status-text");
const statusInstructions = document.getElementById("status-instructions");
const diagnoseList = document.getElementById("diagnose-list");

const pageTitle = document.getElementById("page-title");
const pageLede = document.getElementById("page-lede");

const suggestedThumb = document.getElementById("suggested-thumb");
const suggestedTitle = document.getElementById("suggested-title");
const suggestedByline = document.getElementById("suggested-byline");
const uoinkSuggestedBtn = document.getElementById("uoink-suggested-btn");
const openInstallFolderBtn = document.getElementById("open-install-folder-btn");
let installFolderPath = "";
const ciEnabled = document.getElementById("ci-enabled");
const ciEnabledStatus = document.getElementById("ci-enabled-status");
const ciKeyInput = document.getElementById("anthropic-key");
const ciStatus = document.getElementById("ci-status");
const ciSaveBtn = document.getElementById("ci-save-btn");
const ciTestBtn = document.getElementById("ci-test-btn");
const ciClearBtn = document.getElementById("ci-clear-btn");
const aiCostEstimate = document.getElementById("ai-cost-estimate");
const hookTypeEnabled = document.getElementById("hook-type-enabled");
const hookTypeStatus = document.getElementById("hook-type-status");
const smartScreenshotPickerEnabled = document.getElementById("smart-screenshot-picker-enabled");
const smartScreenshotPickerStatus = document.getElementById("smart-screenshot-picker-status");
const clipboardScreenshotCap = document.getElementById("clipboard-screenshot-cap");
const clipboardScreenshotCapStatus = document.getElementById("clipboard-screenshot-cap-status");
const hookCalibrationSummary = document.getElementById("hook-calibration-summary");
const hookCorrectionsList = document.getElementById("hook-corrections-list");
const mcpStdioPath = document.getElementById("mcp-stdio-path");
const mcpHttpUrl = document.getElementById("mcp-http-url");
const mcpHttpToken = document.getElementById("mcp-http-token");
const mcpConfigEls = {
  claude: document.getElementById("mcp-config-claude"),
  chatgpt: document.getElementById("mcp-config-chatgpt"),
  cursor: document.getElementById("mcp-config-cursor"),
  generic: document.getElementById("mcp-config-generic"),
};
const mcpCopyButtons = Array.from(document.querySelectorAll("[data-copy-client]"));
const skillSystemPrompt = document.getElementById("skill-system-prompt");
const skillPromptCopyBtn = document.getElementById("skill-prompt-copy");

// ---- Platform detection ---------------------------------------------------
function normalizePlatform(os) {
  const value = String(os || "").toLowerCase();
  if (value === "mac" || value === "darwin" || value === "macos") return "mac";
  if (value === "win" || value.startsWith("win")) return "win";
  if (value === "linux" || value === "cros" || value === "openbsd") return "linux";
  return "win";
}

function setPlatform(os) {
  platformOs = normalizePlatform(os);
  document.body.dataset.platform = platformOs;
  applyDownloadState();
}

function currentPlatform() {
  return normalizePlatform(document.body.dataset.platform || platformOs);
}

function startHelperLabel() {
  if (currentPlatform() === "mac") return "Show Mac start steps";
  if (currentPlatform() === "linux") return "Show terminal steps";
  return "Start helper";
}

function helperOfflineDetail() {
  if (currentPlatform() === "mac") {
    return "Open Uoink from Applications, or run uoink-helper from Terminal, then this panel will refresh.";
  }
  if (currentPlatform() === "linux") {
    return "Run uoink-helper from Terminal, then this panel will refresh.";
  }
  return "Start Uoink Server from the Windows Start Menu, then this panel will refresh.";
}

function outputFolderActionLabel() {
  return currentPlatform() === "mac" ? "Open in Finder" : "Open output folder";
}

function initPlatformInfo() {
  setPlatform(document.body.dataset.platform || "win");
  try {
    if (chrome && chrome.runtime && chrome.runtime.getPlatformInfo) {
      chrome.runtime.getPlatformInfo((info) => {
        setPlatform(info && info.os);
      });
    }
  } catch { /* keep default Windows rendering */ }
}

initPlatformInfo();

// ---- Suggested-video population -----------------------------------------
function videoIdFromUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname.replace(/^www\.|^m\./, "") === "youtu.be") {
      return u.pathname.replace(/^\/+/, "").split("/")[0] || null;
    }
    return u.searchParams.get("v");
  } catch {
    return null;
  }
}

const suggestedVideoId = videoIdFromUrl(SUGGESTED_VIDEO.url);
if (suggestedVideoId) {
  suggestedThumb.src = `https://i.ytimg.com/vi/${suggestedVideoId}/hqdefault.jpg`;
}
suggestedTitle.textContent = SUGGESTED_VIDEO.title;
suggestedByline.textContent = SUGGESTED_VIDEO.byline;

// ---- Source-driven layout ------------------------------------------------
function applySource() {
  if (source === "offline") {
    // Skip the welcome + install steps; user already has the extension.
    step1.classList.add("hidden");
    step2.classList.add("hidden");
    markCurrent(step3);
  } else if (isSettingsMode) {
    // Returning users opened Settings / Agent Integration from the popup.
    // Keep the install walkthrough out of the way and land directly on the
    // settings surface they came here to manage.
    step1.classList.add("hidden");
    step2.classList.add("hidden");
    step3.classList.add("hidden");
    if (firstSettingsSection) markCurrent(firstSettingsSection);
    requestAnimationFrame(() => {
      const target = requestedHash
        ? document.getElementById(requestedHash.replace(/^#/, ""))
        : firstSettingsSection;
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  } else {
    markCurrent(step1);
  }
  // Header copy is driven by current status, not just source. Initial state
  // is "checking" -- updateHeader gets called again on every status change.
  updateHeader("checking");
}

// Keep page title/lede in sync with the live status. Without this, the
// source=offline path stayed on "Uoink isn't running yet" even after the
// status block flipped green, so the page contradicted itself.
function updateHeader(status) {
  if (status === "running") {
    pageTitle.textContent = isSettingsMode ? "Uoink settings." : "Uoink is ready.";
    pageLede.textContent = isSettingsMode
      ? "Manage local AI features and agent integration."
      : "The local helper is running. Open the dashboard from your tray to view your full library, or uoink a supported source to begin.";
    return;
  }
  if (source === "offline") {
    pageTitle.textContent = "Uoink isn't running yet.";
    pageLede.textContent =
      "Start the Uoink helper and this page will detect it automatically.";
  } else if (isSettingsMode) {
    pageTitle.textContent = "Uoink settings.";
    pageLede.textContent =
      "Start the local helper to manage settings and agent integration.";
  } else {
    pageTitle.textContent = "Let's get you set up.";
    pageLede.textContent =
      "Two minutes. Then you'll be turning sources into a local corpus your AI can read.";
  }
}

function markCurrent(stepEl) {
  for (const el of [step1, step2, step3, step4]) {
    el.classList.remove("is-current");
  }
  if (stepEl) stepEl.classList.add("is-current");
}

function markDone(stepEl) {
  stepEl.classList.add("is-done");
  stepEl.classList.remove("is-current");
}

// ---- Step nav ------------------------------------------------------------
getStartedBtn.addEventListener("click", () => {
  markDone(step1);
  markCurrent(step2);
  step2.scrollIntoView({ behavior: "smooth", block: "start" });
});

skipInstall.addEventListener("click", (ev) => {
  ev.preventDefault();
  markDone(step2);
  markCurrent(step3);
  step3.scrollIntoView({ behavior: "smooth", block: "start" });
});

// ---- Step 3: live server polling ----------------------------------------
let pollTimer = null;
let polling = false;

function setStatus(state, text) {
  statusBlock.classList.remove("is-checking", "is-running", "is-down");
  statusBlock.classList.add(`is-${state}`);
  statusText.textContent = text;
}

async function pingOnce() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch(SERVER + PING_PATH, {
      method: "GET",
      mode: "cors",
      cache: "no-store",
      signal: ctrl.signal,
    });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

function normalizeDiagnoseChecks(body) {
  if (!body || typeof body !== "object") return [];
  const raw = Array.isArray(body.checks)
    ? body.checks
    : (Array.isArray(body.results) ? body.results : null);
  if (raw) return raw;
  return Object.entries(body)
    .filter(([key, value]) => key !== "ok" && value && typeof value === "object")
    .map(([key, value]) => Object.assign({ name: key }, value));
}

function diagnoseStatusClass(status) {
  const s = String(status || "").toLowerCase();
  if (["ok", "pass", "passed", "running", "available", "healthy"].includes(s)) return "ok";
  if (["warn", "warning", "skipped", "missing", "degraded"].includes(s)) return "warn";
  return "error";
}

function diagnoseIcon(status) {
  const cls = diagnoseStatusClass(status);
  if (cls === "ok") return "ok";
  if (cls === "warn") return "!";
  return "x";
}

function diagnoseName(check) {
  return String(check.label || check.name || check.id || "Check")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function diagnoseAction(check) {
  const id = String(check.id || check.name || check.check || "").toLowerCase();
  const detail = String(check.detail || check.message || check.error || "").toLowerCase();
  const action = String(check.action || check.recommended_action || "").toLowerCase();
  const haystack = `${id} ${detail} ${action}`;
  if (/helper|server|running|start/.test(haystack) && !/anthropic/.test(haystack)) {
    return {
      label: startHelperLabel(),
      run: () => {
        statusInstructions.classList.remove("hidden");
        statusInstructions.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    };
  }
  if (/output|folder|writable|write/.test(haystack)) {
    return {
      label: outputFolderActionLabel(),
      run: async () => {
        const path = check.path || check.folder || check.output_folder || check.output_dir || check.fallback_path;
        if (path && window.STC && STC.openFolder) {
          try { await STC.openFolder(path); } catch { /* best effort */ }
        }
      },
    };
  }
  if (/anthropic|api key|key/.test(haystack)) {
    return {
      label: /401|invalid/.test(haystack) ? "Update key" : "Add key",
      run: () => {
        const target = document.getElementById("comment-intelligence");
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (ciKeyInput) ciKeyInput.focus();
      },
    };
  }
  return null;
}

function renderDiagnose(body) {
  if (!diagnoseList) return;
  const checks = normalizeDiagnoseChecks(body);
  diagnoseList.innerHTML = "";
  if (!checks.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No diagnostic checks returned yet.";
    diagnoseList.appendChild(empty);
    return;
  }
  for (const check of checks) {
    const status = check.status || check.state || check.result || (check.ok ? "ok" : "error");
    const row = document.createElement("div");
    row.className = "diagnose-row";

    const icon = document.createElement("div");
    icon.className = `diagnose-icon ${diagnoseStatusClass(status)}`;
    icon.textContent = diagnoseIcon(status);

    const text = document.createElement("div");
    const name = document.createElement("div");
    name.className = "diagnose-name";
    name.textContent = diagnoseName(check);
    const detail = document.createElement("div");
    detail.className = "diagnose-detail";
    detail.textContent = check.detail || check.message || check.error || String(status);
    text.appendChild(name);
    text.appendChild(detail);

    row.appendChild(icon);
    row.appendChild(text);

    const action = diagnoseAction(check);
    if (action) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "button ghost diagnose-action";
      btn.textContent = action.label;
      btn.addEventListener("click", action.run);
      row.appendChild(btn);
    } else {
      row.appendChild(document.createElement("span"));
    }
    diagnoseList.appendChild(row);
  }
}

async function loadDiagnose() {
  if (!diagnoseList) return;
  try {
    const res = await fetch(`${SERVER}/diagnose`, {
      method: "GET",
      mode: "cors",
      cache: "no-store",
    });
    const body = await res.json();
    if (!res.ok || !body || body.ok === false) throw new Error((body && body.error) || `HTTP ${res.status}`);
    if (body.platform || body.os) setPlatform(body.platform || body.os);
    const dbCheck = body.checks && body.checks.find(c => c.name === "index_db_writable");
    if (dbCheck && dbCheck.detail) {
      const path = dbCheck.detail;
      installFolderPath = path.replace(/[\\/]index\.db$/i, "");
      const folderDetailEl = document.getElementById("install-folder-path");
      if (folderDetailEl) {
        folderDetailEl.textContent = installFolderPath;
      }
    }
    renderDiagnose(body);
  } catch (e) {
    diagnoseList.innerHTML = "";
    const row = document.createElement("div");
    row.className = "diagnose-row";
    const icon = document.createElement("div");
    icon.className = "diagnose-icon error";
    icon.textContent = "x";
    const text = document.createElement("div");
    const name = document.createElement("div");
    name.className = "diagnose-name";
    name.textContent = "Helper offline";
    const detail = document.createElement("div");
    detail.className = "diagnose-detail";
    detail.textContent = helperOfflineDetail();
    text.appendChild(name);
    text.appendChild(detail);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "button ghost diagnose-action";
    btn.textContent = startHelperLabel();
    btn.addEventListener("click", () => {
      statusInstructions.classList.remove("hidden");
      statusInstructions.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    row.appendChild(icon);
    row.appendChild(text);
    row.appendChild(btn);
    diagnoseList.appendChild(row);
  }
}

async function tickPoll() {
  loadDiagnose();
  const up = await pingOnce();
  if (up) {
    onServerUp();
    return;
  }
  // Switch from "checking" to "down" instructions only after the first
  // failed probe, so the user sees a quick spinner first instead of an
  // immediate scary "not running" message.
  if (statusBlock.classList.contains("is-checking")) {
    setStatus("down", "Uoink isn't running yet");
    statusInstructions.classList.remove("hidden");
    updateHeader("down");
  }
}

function startPolling() {
  if (polling) return;
  polling = true;
  setStatus("checking", "Checking for Uoink...");
  statusInstructions.classList.add("hidden");
  // Fire one immediately so a running server flips green right away.
  tickPoll();
  pollTimer = setInterval(tickPoll, POLL_MS);
}

function stopPolling() {
  polling = false;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function onServerUp() {
  stopPolling();
  setStatus("running", "Uoink is running ✓");
  statusInstructions.classList.add("hidden");
  updateHeader("running");
  setCIControlsEnabled(true);
  loadAIPricing();
  loadCISettings();
  loadHookCorrections();
  loadTasteAnchors();
  loadMCPConfig();
  loadSkillSystemPrompt();
  loadDiagnose();
  markDone(step3);
  if (isSettingsMode) return;
  if (step4.classList.contains("hidden")) {
    step4.classList.remove("hidden");
    markCurrent(step4);
    // Defer scroll so the layout settles before we move the viewport.
    requestAnimationFrame(() => {
      step4.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  } else {
    markCurrent(step4);
  }
}

// ---- Comment Intelligence settings --------------------------------------
let ciLoaded = false;
let aiSettings = null;
let aiPricing = null;
// Settings writes from this page go to the helper one at a time, in the order
// they were made, so a later change is never overwritten by an earlier write
// and no answer is older than one already handled.
let settingsWriteQueue = Promise.resolve();
// field -> writes carrying it that the helper has not answered yet.
const pendingSettingWrites = {};

function writeSettings(body) {
  const fields = Object.keys(body);
  // Each field's edit count as it goes out: the helper storing it confirms
  // those edits (confirmSettingEdits).
  const sentEdits = {};
  for (const f of fields) {
    pendingSettingWrites[f] = (pendingSettingWrites[f] || 0) + 1;
    sentEdits[f] = settingEditCount(f);
  }
  const run = settingsWriteQueue
    .then(() => STC.updateSettings(body))
    .then((res) => {
      if (res && res.ok) {
        for (const f of fields) {
          if (settingStored(res.settings, f, body[f])) confirmSettingEdits(f, sentEdits[f]);
        }
      }
      return res;
    })
    .finally(() => {
      for (const f of fields) pendingSettingWrites[f] -= 1;
    });
  settingsWriteQueue = run.catch(() => {});
  return run;
}

// A field with a newer write still queued keeps showing the change being
// saved; that write's answer settles it.
function settingWritePending(field) {
  return (pendingSettingWrites[field] || 0) > 0;
}

// Settings fields holding the user's own value the helper hasn't stored yet:
// edited on this page, or restored from a failed save
// (loadPendingV3Settings).
const changedSettingFields = new Set();
// Fields whose control shows the helper's value (renderCISettings put it
// there, or the helper stored what it shows).
const loadedSettingFields = new Set();

// User edits (every input or change) per field, counted. A save or load notes
// the count when it starts; putting a value back after it is skipped for a
// field edited since.
const settingEditCounts = {};
// Per field, the edit count the helper has confirmed: a save carrying the
// field at that count was stored (or a failed save's value was put back).
const confirmedSettingEdits = {};

function settingEditCount(field) {
  return settingEditCounts[field] || 0;
}

function noteSettingEdited(field) {
  settingEditCounts[field] = settingEditCount(field) + 1;
  changedSettingFields.add(field);
}

// Edits the helper hasn't confirmed (newer than any stored save, or not
// saved yet): no settings answer is shown over them.
function settingEditsUnconfirmed(field) {
  return settingEditCount(field) > (confirmedSettingEdits[field] || 0);
}

// The helper stored field as it was at edit count `count`: later answers may
// show it again (e.g. a value another tab saved since).
function confirmSettingEdits(field, count) {
  confirmedSettingEdits[field] = Math.max(confirmedSettingEdits[field] || 0, count);
  changedSettingFields.delete(field);
  loadedSettingFields.add(field);
}

// A field a save may carry: its control shows the helper's value or the
// user's. Until the read answers (it can fail or time out) every other
// control shows its HTML default, and sending that would overwrite what the
// helper has saved.
function settingKnown(field) {
  return changedSettingFields.has(field) || loadedSettingFields.has(field);
}

function knownSettingsOnly(body) {
  for (const field of Object.keys(body)) {
    if (!settingKnown(field)) delete body[field];
  }
  return body;
}

// A save's answer carries the helper's settings. If the read on load never
// showed them, fill in the controls the user hasn't changed from it.
function adoptSettings(settings) {
  if (!settings) return;
  if (ciLoaded) {
    aiSettings = Object.assign({}, aiSettings, settings);
    return;
  }
  renderCISettings(Object.assign({}, aiSettings, settings), true);
}

// The settings read on load waits its turn in the same queue. STC.getSettings
// has no timeout of its own, so give up on it here: a helper that never
// answers must not hold every later save behind it. The clock starts when the
// read is sent; an answer that comes after the limit is ignored.
const SETTINGS_READ_TIMEOUT_MS = 10000;

function readSettingsInTurn() {
  const read = settingsWriteQueue.then(() => new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("Uoink helper did not answer"));
    }, SETTINGS_READ_TIMEOUT_MS);
    Promise.resolve()
      .then(() => STC.getSettings())
      .then(resolve, reject)
      .finally(() => clearTimeout(timer));
  }));
  settingsWriteQueue = read.catch(() => {});
  return read;
}

function setCIStatus(text, mode) {
  if (!ciStatus) return;
  ciStatus.textContent = text;
  ciStatus.classList.remove("ok", "warn");
  if (mode) ciStatus.classList.add(mode);
}

function dollars(n) {
  if (!Number.isFinite(n)) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

function readClipboardScreenshotCap() {
  if (!clipboardScreenshotCap) return 4;
  const parsed = Number.parseInt(clipboardScreenshotCap.value, 10);
  if (!Number.isFinite(parsed)) return 4;
  return Math.max(0, Math.min(12, parsed));
}

function renderAICostEstimate() {
  if (!aiCostEstimate) return;
  const hasKey = !!(
    (aiSettings && aiSettings.anthropic_key_set)
    || (ciKeyInput && ciKeyInput.value.trim())
  );
  const ciOn = !!(ciEnabled && ciEnabled.checked);
  const hookOn = !!(hookTypeEnabled && hookTypeEnabled.checked);
  if (!hasKey || !aiPricing || (!ciOn && !hookOn)) {
    aiCostEstimate.classList.add("hidden");
    aiCostEstimate.textContent = "";
    return;
  }

  const est = aiPricing.est_per_video || {};
  const parts = [];
  if (ciOn) parts.push(`Comment Intelligence ${dollars(Number(est.ci || 0))}`);
  if (hookOn) parts.push(`Hook Type ${dollars(Number(est.hook || 0))}`);
  const total = ciOn && hookOn
    ? Number(est.both || 0)
    : Number((ciOn ? est.ci : est.hook) || 0);
  const model = aiPricing.display_model || aiPricing.model || "Anthropic";
  aiCostEstimate.innerHTML = [
    `≈ ${dollars(total)} estimated per video`,
    `<small>${parts.join(" + ")} · ${model} estimate, actual token usage may vary.</small>`,
  ].join("");
  aiCostEstimate.classList.remove("hidden");
}

function setCIControlsEnabled(enabled) {
  const els = [
    ciEnabled,
    ciKeyInput,
    ciSaveBtn,
    ciTestBtn,
    ciClearBtn,
    hookTypeEnabled,
    smartScreenshotPickerEnabled,
    clipboardScreenshotCap,
    ycChannelInput,
    ycAddBtn,
    ycRecognizeBtn,
    ctWorkspaceFormat,
    ctTargetLength,
    ctObsidianPath,
    ctObsidianMirror,
    cvEnabled,
    cvSources,
  ];
  for (const el of els) {
    if (el) el.disabled = !enabled;
  }
  if (ctStyleSourceRadios) {
    for (const r of ctStyleSourceRadios) {
      r.disabled = !enabled;
    }
  }
  if (!enabled) setCIStatus("Start Uoink Server to manage settings.", "warn");
  if (!enabled && aiCostEstimate) aiCostEstimate.classList.add("hidden");
}

// onlyGiven (adoptSettings): a save's answer stands in for a read that never
// answered, so only the fields it has are shown, never over one holding the
// user's value (changedSettingFields), and the key box and its status line
// are left alone. keyEdits: the key box's edit count when the read or save
// started; a key typed since stays in the box.
function renderCISettings(settings, onlyGiven, keyEdits) {
  if (!settings) return;
  aiSettings = settings;
  // A control keeps what it shows when a newer change to it is still being
  // saved or the user edited it here (typing included) and the helper hasn't
  // stored that edit yet.
  const show = (field) => {
    if (settingWritePending(field) || settingEditsUnconfirmed(field)) return false;
    const given = Object.prototype.hasOwnProperty.call(settings, field);
    if (onlyGiven && (!given || changedSettingFields.has(field))) return false;
    if (given) loadedSettingFields.add(field);
    return true;
  };
  if (ciEnabled && show("comment_intelligence_enabled")) {
    ciEnabled.checked = !!settings.comment_intelligence_enabled;
  }
  if (hookTypeEnabled && show("hook_type_enabled")) {
    hookTypeEnabled.checked = !!settings.hook_type_enabled;
  }
  if (smartScreenshotPickerEnabled && show("smart_screenshot_picker_enabled")) {
    smartScreenshotPickerEnabled.checked = !!settings.smart_screenshot_picker_enabled;
  }
  if (clipboardScreenshotCap && show("clipboard_screenshot_cap")) {
    const cap = Number.isFinite(Number(settings.clipboard_screenshot_cap))
      ? Number(settings.clipboard_screenshot_cap)
      : 4;
    clipboardScreenshotCap.value = String(Math.max(0, Math.min(12, cap)));
  }
  if (ciKeyInput && !onlyGiven && settingEditCount("anthropic_key") === keyEdits) {
    ciKeyInput.value = "";
    ciKeyInput.dataset.dirty = "false";
    ciKeyInput.placeholder = settings.anthropic_key_set
      ? "Key saved - enter a new key to replace"
      : "sk-ant-...";
  }
  if (!onlyGiven) {
    setCIStatus(settings.anthropic_key_set ? "Key set" : "Key not set.",
                settings.anthropic_key_set ? "ok" : "warn");
  }
  renderAICostEstimate();

  // Populate Your Channels
  if (show("your_channels")) {
    yourChannelsList = settings.your_channels || [];
    renderYcList();
  }

  // Populate Creator Tools
  if (ctWorkspaceFormat && show("default_workspace_format")) {
    ctWorkspaceFormat.value = settings.default_workspace_format || "markdown";
  }
  if (ctTargetLength && show("default_target_length")) {
    const len = settings.default_target_length || "5m";
    const lenToVal = { "30s": 0, "60s": 1, "5m": 2, "15m": 3, "30m": 4 };
    ctTargetLength.value = lenToVal[len] !== undefined ? lenToVal[len] : 2;
    updateTargetLengthDisplay(ctTargetLength.value);
  }
  if (ctStyleSourceRadios && show("style_anchors_source")) {
    const source = settings.style_anchors_source || "taste";
    for (const r of ctStyleSourceRadios) {
      r.checked = r.value === source;
    }
  }
  if (ctObsidianPath && show("obsidian_vault_path")) {
    ctObsidianPath.value = settings.obsidian_vault_path || "";
  }
  if (ctObsidianMirror && show("mirror_scripts_to_obsidian")) {
    ctObsidianMirror.checked = !!settings.mirror_scripts_to_obsidian;
  }

  // Populate Claim Verification
  if (cvEnabled && show("claim_verification_enabled")) {
    cvEnabled.checked = !!settings.claim_verification_enabled;
  }
  if (cvSources && show("default_evidence_sources")) {
    const sources = Array.isArray(settings.default_evidence_sources)
      ? settings.default_evidence_sources.join("\n")
      : (settings.default_evidence_sources || "");
    cvSources.value = sources;
  }
  
  updateCreatorToolsVisibility();
}

async function fetchPricingWithToken(token) {
  return fetch(`${SERVER}/settings/pricing`, {
    method: "GET",
    mode: "cors",
    cache: "no-store",
    headers: token ? { "X-Yoink-Token": token } : {},
  });
}

async function loadAIPricing() {
  if (!window.STC || !STC.getToken) return;
  try {
    let token = await STC.getToken();
    let res = await fetchPricingWithToken(token);
    if (res.status === 403) {
      token = await STC.getToken({ refresh: true });
      res = await fetchPricingWithToken(token);
    }
    const body = await res.json();
    if (res.ok && body && body.ok && body.pricing) {
      aiPricing = body.pricing;
      renderAICostEstimate();
    }
  } catch {
    // Cost visibility is a trust affordance, not a setup blocker.
  }
}

async function loadCISettings() {
  if (ciLoaded || !window.STC || !STC.getSettings) return;
  try {
    // Read in turn with the writes, so a save made while this read is out
    // is not undone by an answer from before it.
    const keyEdits = settingEditCount("anthropic_key");
    const res = await readSettingsInTurn();
    if (!res || !res.ok) {
      setCIStatus((res && res.error) || "Settings unavailable", "warn");
      return;
    }
    ciLoaded = true;
    renderCISettings(res.settings, false, keyEdits);
  } catch (err) {
    setCIStatus(`Settings unavailable: ${(err && err.message) || "read failed"}`, "warn");
  }
}

if (ciKeyInput) {
  ciKeyInput.addEventListener("input", () => {
    ciKeyInput.dataset.dirty = "true";
    // Not a setting a save may carry on its own: only counted, so an answer
    // doesn't clear a key typed since its save or read started.
    settingEditCounts.anthropic_key = settingEditCount("anthropic_key") + 1;
    renderAICostEstimate();
  });
}

for (const toggle of [ciEnabled, hookTypeEnabled]) {
  if (toggle) toggle.addEventListener("change", renderAICostEstimate);
}

// Comment Intelligence, Hook Type and Smart Screenshot Picker (and the
// screenshot count) save as soon as they change: just that field (never the
// API key), with Saved / Save failed on the control's own status line. These
// saves are the only writes that carry Hook Type, the picker and the count;
// the Comment Intelligence buttons leave its toggle out while its own save is
// out (ciToggleBody). A failed save puts the control back to the helper's
// value.
function setSettingStatus(el, text, mode) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("ok", "warn");
  if (mode) el.classList.add(mode);
}

// The helper answers ok to a body carrying fields it does not keep and leaves
// them out of the settings it sends back. A field counts as saved only when
// that answer has it (with the value sent, for a toggle or a number).
const SETTING_NOT_SUPPORTED = "Not saved: Uoink helper does not support this setting";

function settingStored(settings, field, sent) {
  if (!settings || !Object.prototype.hasOwnProperty.call(settings, field)) return false;
  if (typeof sent === "boolean" || typeof sent === "number") return settings[field] === sent;
  return true;
}

async function saveSettingOnChange(field, value, statusEl, restore) {
  if (!window.STC || !STC.updateSettings) return;
  noteSettingEdited(field);
  const edits = settingEditCount(field);
  setSettingStatus(statusEl, "Saving...", null);
  let error = "Save failed";
  try {
    const res = await writeSettings({ [field]: value });
    if (res && res.ok) {
      adoptSettings(res.settings);
      if (settingStored(res.settings, field, value)) {
        // A newer change to the same field is queued; its answer decides.
        if (!settingWritePending(field)) setSettingStatus(statusEl, "Saved", "ok");
        return;
      }
      error = SETTING_NOT_SUPPORTED;
    } else if (res && res.error) {
      error = `Save failed: ${res.error}`;
    }
  } catch {
    error = "Save failed: Uoink helper unreachable";
  }
  if (settingWritePending(field)) return;
  // Edited again since this save was made (typing, not yet saved): keep it.
  if (settingEditCount(field) === edits && aiSettings && aiSettings[field] !== undefined) {
    restore(aiSettings[field]);
    // The control shows the helper's value again: the undone edit no longer
    // holds later answers off it.
    confirmSettingEdits(field, edits);
    renderAICostEstimate();
  }
  setSettingStatus(statusEl, error, "warn");
}

if (hookTypeEnabled) {
  hookTypeEnabled.addEventListener("change", () => {
    saveSettingOnChange("hook_type_enabled", !!hookTypeEnabled.checked, hookTypeStatus,
      (saved) => { hookTypeEnabled.checked = !!saved; });
  });
}

if (smartScreenshotPickerEnabled) {
  smartScreenshotPickerEnabled.addEventListener("change", () => {
    saveSettingOnChange(
      "smart_screenshot_picker_enabled",
      !!smartScreenshotPickerEnabled.checked,
      smartScreenshotPickerStatus,
      (saved) => { smartScreenshotPickerEnabled.checked = !!saved; }
    );
  });
}

if (clipboardScreenshotCap) {
  // Typing counts as an edit before the field is left (no answer replaces it).
  clipboardScreenshotCap.addEventListener("input",
    () => noteSettingEdited("clipboard_screenshot_cap"));
  clipboardScreenshotCap.addEventListener("change", () => {
    // Show the clamped number that is actually saved.
    const cap = readClipboardScreenshotCap();
    clipboardScreenshotCap.value = String(cap);
    saveSettingOnChange("clipboard_screenshot_cap", cap, clipboardScreenshotCapStatus,
      (saved) => { clipboardScreenshotCap.value = String(saved); });
  });
}

if (ciEnabled) {
  ciEnabled.addEventListener("change", () => {
    saveSettingOnChange("comment_intelligence_enabled", !!ciEnabled.checked, ciEnabledStatus,
      (saved) => { ciEnabled.checked = !!saved; });
  });
}

// The Comment Intelligence toggle for a write from its section's buttons:
// left out while the toggle's own save is out (that save carries the newest
// choice and reports it on the toggle's line), and while the page has its
// HTML default only (settingKnown).
function ciToggleBody() {
  const field = "comment_intelligence_enabled";
  if (settingWritePending(field)) return {};
  return knownSettingsOnly({ [field]: !!(ciEnabled && ciEnabled.checked) });
}

if (ciSaveBtn) {
  ciSaveBtn.addEventListener("click", async () => {
    if (!window.STC || !STC.updateSettings) return;
    // Hook Type, the picker and the screenshot count save when changed;
    // sending them here too could put back a value changed since.
    const body = ciToggleBody();
    const rawKey = ciKeyInput ? ciKeyInput.value.trim() : "";
    const keyDirty = ciKeyInput && ciKeyInput.dataset.dirty === "true";
    if (rawKey || keyDirty) body.anthropic_key = rawKey || null;
    // The helper refuses a save with no setting in it.
    if (!Object.keys(body).length) {
      setCIStatus("Type an API key to save it.", "warn");
      return;
    }

    setCIStatus("Saving...", null);
    ciSaveBtn.disabled = true;
    const keyEdits = settingEditCount("anthropic_key");
    try {
      const res = await writeSettings(body);
      if (!res || !res.ok) {
        setCIStatus((res && res.error) || "Save failed", "warn");
        return;
      }
      renderCISettings(res.settings, false, keyEdits);
    } catch {
      setCIStatus("Save failed", "warn");
    } finally {
      ciSaveBtn.disabled = false;
    }
  });
}

if (ciTestBtn) {
  ciTestBtn.addEventListener("click", async () => {
    if (!window.STC || !STC.testAnthropicKey) return;
    const rawKey = ciKeyInput ? ciKeyInput.value.trim() : "";
    setCIStatus("Testing key...", null);
    ciTestBtn.disabled = true;
    try {
      const res = await STC.testAnthropicKey(rawKey || undefined);
      if (res && res.valid) {
        setCIStatus("Key test passed", "ok");
        return;
      }
      setCIStatus(`Last test failed: ${(res && res.error) || "unknown error"}`, "warn");
    } catch {
      setCIStatus("Last test failed: server unavailable", "warn");
    } finally {
      ciTestBtn.disabled = false;
    }
  });
}

if (ciClearBtn) {
  ciClearBtn.addEventListener("click", async () => {
    if (!window.STC || !STC.updateSettings) return;
    const confirmed = window.confirm(
      "Clear the saved Anthropic API key from this computer?"
    );
    if (!confirmed) return;

    setCIStatus("Clearing key...", null);
    ciClearBtn.disabled = true;
    const keyEdits = settingEditCount("anthropic_key");
    try {
      const res = await writeSettings(Object.assign(ciToggleBody(), { anthropic_key: null }));
      if (!res || !res.ok) {
        setCIStatus((res && res.error) || "Clear failed", "warn");
        return;
      }
      // A key typed since Clear key was clicked stays in the box.
      if (ciKeyInput && settingEditCount("anthropic_key") === keyEdits) {
        ciKeyInput.value = "";
        ciKeyInput.dataset.dirty = "false";
        ciKeyInput.placeholder = "sk-ant-...";
      }
      adoptSettings(res.settings);
      aiSettings = Object.assign({}, aiSettings || {}, { anthropic_key_set: false });
      setCIStatus("Key not set.", "warn");
      renderAICostEstimate();
    } catch {
      setCIStatus("Clear failed", "warn");
    } finally {
      ciClearBtn.disabled = false;
    }
  });
}

// ---- Hook Type calibration history --------------------------------------
async function fetchSetupJsonWithToken(path, init = {}) {
  if (!window.STC || !STC.getToken || !globalThis.UoinkUI) {
    return { ok: false, error: "Uoink helper unavailable" };
  }
  return globalThis.UoinkUI.authedJson(path, init, { server: SERVER });
}

function hookTypeLabel(value) {
  return globalThis.UoinkUI.prettyHookType(value) || "Unknown";
}

function correctionDateLabel(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function correctionRowsFromResponse(body) {
  if (!body || typeof body !== "object") return [];
  if (Array.isArray(body.corrections)) return body.corrections;
  if (Array.isArray(body.items)) return body.items;
  if (Array.isArray(body.results)) return body.results;
  return [];
}

function renderHookCorrections(body) {
  if (!hookCalibrationSummary || !hookCorrectionsList) return;
  const rows = correctionRowsFromResponse(body);
  const total = Number.isFinite(Number(body && body.total))
    ? Number(body.total)
    : rows.length;

  hookCorrectionsList.innerHTML = "";
  hookCalibrationSummary.textContent =
    `You've made ${total} correction${total === 1 ? "" : "s"}. ` +
    "Your classifier is calibrated to your judgment.";

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No corrections yet. When you fix a Hook Type in the popup, it will appear here.";
    hookCorrectionsList.appendChild(empty);
    return;
  }

  for (const row of rows.slice(0, 20)) {
    const item = document.createElement("div");
    item.className = "correction-row";

    const left = document.createElement("div");
    const titleText = row.title || row.video_title || row.slug || "Untitled uoink";
    const folder = row.folder || row.session_folder || row.output_folder || "";
    const title = document.createElement(folder ? "button" : "div");
    title.className = "correction-title";
    title.textContent = titleText;
    if (folder) {
      title.type = "button";
      title.title = "Open uoink folder";
      title.addEventListener("click", async () => {
        try { await STC.openFolder(folder); } catch { /* best effort */ }
      });
    }

    const types = document.createElement("div");
    types.className = "correction-types";
    const original = hookTypeLabel(
      row.original_hook_type || row.previous_hook_type || row.from_hook_type
    );
    const corrected = hookTypeLabel(
      row.corrected_hook_type || row.hook_type || row.to_hook_type
    );
    types.textContent = `${original} \u2192 ${corrected}`;

    left.appendChild(title);
    left.appendChild(types);

    const date = document.createElement("div");
    date.className = "correction-date";
    date.textContent = correctionDateLabel(
      row.corrected_at || row.created_at || row.updated_at || row.date
    );

    item.appendChild(left);
    item.appendChild(date);
    hookCorrectionsList.appendChild(item);
  }
}

async function loadHookCorrections() {
  if (!hookCalibrationSummary || !hookCorrectionsList) return;
  hookCalibrationSummary.textContent = "Loading calibration history...";
  hookCorrectionsList.innerHTML = "";
  try {
    const body = await fetchSetupJsonWithToken("/taxonomy/corrections?limit=20", {
      method: "GET",
    });
    if (!body || body.ok === false) {
      throw new Error((body && body.error) || "Calibration history unavailable");
    }
    renderHookCorrections(body);
  } catch (e) {
    hookCalibrationSummary.textContent =
      (e && e.message) || "Calibration history unavailable.";
  }
}

// ---- MCP config snippets -------------------------------------------------
let mcpSnippets = {};

function jsonPretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function stdioServerConfig(config) {
  return {
    mcpServers: {
      uoink: {
        command: config.stdio.command,
        args: config.stdio.args,
      },
    },
  };
}

function buildMcpSnippets(config, token) {
  const stdio = stdioServerConfig(config);
  const http = {
    url: config.http.url,
    headers: { "X-Uoink-Token": token || "<token>" },
  };
  return {
    claude: jsonPretty(stdio),
    chatgpt: jsonPretty({
      name: "uoink",
      transport: "stdio",
      command: config.stdio.command,
      args: config.stdio.args,
    }),
    cursor: jsonPretty(stdio),
    generic: [
      "STDIO:",
      jsonPretty(stdio),
      "",
      "HTTP:",
      jsonPretty(http),
    ].join("\n"),
  };
}

function renderMcpConfig(config, token) {
  if (!config || !config.ok) return;
  const stdioText = [config.stdio.command].concat(config.stdio.args || []).join(" ");
  if (mcpStdioPath) mcpStdioPath.textContent = stdioText;
  if (mcpHttpUrl) mcpHttpUrl.textContent = config.http.url;
  if (mcpHttpToken) {
    mcpHttpToken.textContent = token ? `X-Uoink-Token: ${token}` : "Token unavailable.";
  }
  mcpSnippets = buildMcpSnippets(config, token);
  for (const [client, el] of Object.entries(mcpConfigEls)) {
    if (el) el.textContent = mcpSnippets[client] || "";
  }
}

function scrollToRequestedAnchor() {
  if (!requestedHash) return;
  const target = document.getElementById(requestedHash.replace(/^#/, ""));
  if (!target) return;
  requestAnimationFrame(() => {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

async function fetchMcpConfigWithToken(token) {
  return fetch(`${SERVER}/mcp/v1/config`, {
    method: "GET",
    mode: "cors",
    cache: "no-store",
    headers: token ? { "X-Yoink-Token": token } : {},
  });
}

async function loadMCPConfig() {
  if (!window.STC || !STC.getToken) return;
  try {
    let token = await STC.getToken();
    let res = await fetchMcpConfigWithToken(token);
    if (res.status === 403) {
      token = await STC.getToken({ refresh: true });
      res = await fetchMcpConfigWithToken(token);
    }
    const config = await res.json();
    if (!res.ok || !config || !config.ok) throw new Error("MCP config unavailable");
    renderMcpConfig(config, token);
    scrollToRequestedAnchor();
  } catch {
    const msg = "MCP config unavailable. Make sure Uoink Server is running.";
    if (mcpStdioPath) mcpStdioPath.textContent = msg;
    if (mcpHttpUrl) mcpHttpUrl.textContent = msg;
  }
}

for (const btn of mcpCopyButtons) {
  btn.addEventListener("click", async () => {
    const client = btn.getAttribute("data-copy-client");
    const text = mcpSnippets[client];
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const old = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = old; }, 1200);
    } catch {
      const old = btn.textContent;
      btn.textContent = "Copy failed";
      setTimeout(() => { btn.textContent = old; }, 1200);
    }
  });
}

// ---- Uoink Operator Skill fallback prompt --------------------------------
async function fetchSkillPromptWithToken(token) {
  return fetch(`${SERVER}/skill/system-prompt`, {
    method: "GET",
    mode: "cors",
    cache: "no-store",
    headers: token ? { "X-Yoink-Token": token } : {},
  });
}

async function loadSkillSystemPrompt() {
  if (!skillSystemPrompt || !window.STC || !STC.getToken) return;
  try {
    let token = await STC.getToken();
    let res = await fetchSkillPromptWithToken(token);
    if (res.status === 403) {
      token = await STC.getToken({ refresh: true });
      res = await fetchSkillPromptWithToken(token);
    }
    if (!res.ok) throw new Error("skill prompt unavailable");
    skillSystemPrompt.value = await res.text();
  } catch {
    skillSystemPrompt.value = "System prompt unavailable. Make sure Uoink Server is running.";
  }
}

if (skillPromptCopyBtn) {
  skillPromptCopyBtn.addEventListener("click", async () => {
    const text = skillSystemPrompt ? skillSystemPrompt.value : "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const old = skillPromptCopyBtn.textContent;
      skillPromptCopyBtn.textContent = "Copied";
      setTimeout(() => { skillPromptCopyBtn.textContent = old; }, 1200);
    } catch {
      const old = skillPromptCopyBtn.textContent;
      skillPromptCopyBtn.textContent = "Copy failed";
      setTimeout(() => { skillPromptCopyBtn.textContent = old; }, 1200);
    }
  });
}

// ---- Step 4: hand off to YouTube + auto-trigger Uoink -------------------
uoinkSuggestedBtn.addEventListener("click", async () => {
  // Stash a flag the YouTube content script will read on injection so it
  // auto-clicks the Uoink button. TTL guards against the user opening the
  // page later from history and getting a surprise uoink.
  if (suggestedVideoId) {
    try {
      await chrome.storage.local.set({
        auto_yoink: { videoId: suggestedVideoId, ts: Date.now() },
      });
    } catch (e) {
      console.warn("[stc] auto_yoink set failed", e);
    }
  }
  try {
    await chrome.tabs.create({ url: SUGGESTED_VIDEO.url, active: true });
  } catch {
    window.open(SUGGESTED_VIDEO.url, "_blank", "noopener");
  }
});

if (openInstallFolderBtn) {
  openInstallFolderBtn.addEventListener("click", () => {
    const path = installFolderPath;
    if (!path) {
      // We only know the real install folder once the helper reports it.
      // Never guess: a hardcoded per-user path (`C:\Users\<someone>\...` or an
      // unexpanded `~/`) resolves to the wrong folder -- or nothing at all --
      // on every machine but the one it was written on. The page already shows
      // `%LOCALAPPDATA%\Uoink` as the hint, which expands in Explorer.
      console.warn("Install folder unknown (helper has not reported a path yet)");
      return;
    }
    const fileUrl = "file:///" + path.replace(/\\/g, "/");
    try {
      if (chrome && chrome.tabs && chrome.tabs.create) {
        chrome.tabs.create({ url: fileUrl });
        return;
      }
    } catch (e) {
      console.warn("chrome.tabs.create failed", e);
    }
    window.open(fileUrl, "_blank");
  });
}

// ---- Pre-launch download button state -----------------------------------
function preventDefaultClick(ev) {
  ev.preventDefault();
}

function applyDownloadState() {
  if (!downloadBtn) return;
  if (currentPlatform() === "win") {
    const installerName = `Uoink-Setup-${PUBLISHED_INSTALLER_VERSION}.exe`;
    downloadBtn.classList.remove("disabled");
    downloadBtn.removeAttribute("aria-disabled");
    downloadBtn.title = "";
    downloadBtn.href =
      `https://github.com/ryanbiddy/uoink/releases/download/v${PUBLISHED_INSTALLER_VERSION}/${installerName}`;
    const winSpan = downloadBtn.querySelector("[data-win-only]");
    if (winSpan) winSpan.textContent = installerName;
    downloadBtn.removeEventListener("click", preventDefaultClick);
  } else {
    downloadBtn.classList.add("disabled");
    downloadBtn.setAttribute("aria-disabled", "true");
    const macSpan = downloadBtn.querySelector('[data-mac-only]');
    const linuxSpan = downloadBtn.querySelector('[data-linux-only]');
    if (macSpan) macSpan.textContent = "Mac build queued";
    if (linuxSpan) linuxSpan.textContent = "Windows installer only";
    downloadBtn.title = "Mac build is queued after Windows stabilizes.";
    downloadBtn.addEventListener("click", preventDefaultClick);
    downloadBtn.removeAttribute("href");
  }
}

// ---- Taste Calibration Onboarding (Sprint 3) -----------------------------
let tcAdmiredChannels = [];
const tcHookRatings = {};
const tcHookIndexToType = {
  0: 'curiosity_gap',
  1: 'contrarian',
  2: 'demo'
};

const tcChannelsInput = document.getElementById("tc-channels-input");
const tcAddChannelBtn = document.getElementById("tc-add-channel-btn");
const tcChannelChips = document.getElementById("tc-channel-chips");
const tcSaveBtn = document.getElementById("tc-save-btn");
const tcSkipBtn = document.getElementById("tc-skip-btn");
const tcStatus = document.getElementById("tc-status");
const tcPendingNote = document.getElementById("tc-pending-note");
const tcDislikesInput = document.getElementById("tc-dislikes-input");

function renderTcChips() {
  if (!tcChannelChips) return;
  tcChannelChips.innerHTML = "";
  tcAdmiredChannels.forEach((chan, idx) => {
    const chip = document.createElement("span");
    chip.className = "tc-channel-chip";
    chip.textContent = chan;
    
    const remove = document.createElement("span");
    remove.className = "remove-chip";
    remove.textContent = " ✕";
    remove.addEventListener("click", () => {
      tcAdmiredChannels.splice(idx, 1);
      renderTcChips();
    });
    chip.appendChild(remove);
    tcChannelChips.appendChild(chip);
  });
}

function addAdmiredChannel(name) {
  name = (name || "").trim();
  if (!name) return;
  if (tcAdmiredChannels.includes(name)) return;
  tcAdmiredChannels.push(name);
  renderTcChips();
  if (tcChannelsInput) tcChannelsInput.value = "";
}

// Wire channel suggestion clicks
document.querySelectorAll(".tc-suggestion").forEach(el => {
  el.addEventListener("click", (ev) => {
    ev.preventDefault();
    addAdmiredChannel(el.getAttribute("data-val"));
  });
});

if (tcAddChannelBtn && tcChannelsInput) {
  tcAddChannelBtn.addEventListener("click", () => {
    addAdmiredChannel(tcChannelsInput.value);
  });
  tcChannelsInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      addAdmiredChannel(tcChannelsInput.value);
    }
  });
}

// Wire hook rating buttons
document.querySelectorAll(".tc-rating-buttons").forEach(container => {
  const hookIndex = container.getAttribute("data-hook-index");
  const hookType = tcHookIndexToType[hookIndex];
  
  const buttons = container.querySelectorAll(".tc-rate-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      buttons.forEach(b => b.classList.remove("active"));
      const rating = btn.getAttribute("data-rating");
      tcHookRatings[hookType] = rating;
      btn.classList.add("active");
    });
  });
});

// Load pending taste profile from storage if any
async function loadPendingTasteProfile() {
  chrome.storage.local.get(["uoink_taste_pending"], (items) => {
    const pending = items.uoink_taste_pending;
    if (pending) {
      tcAdmiredChannels = pending.admired_channels || [];
      renderTcChips();
      if (pending.dislikes && tcDislikesInput) {
        tcDislikesInput.value = pending.dislikes;
      }
      // Populate ratings
      if (pending.hook_ratings) {
        Object.entries(pending.hook_ratings).forEach(([type, rating]) => {
          tcHookRatings[type] = rating;
          // Find matching button
          const index = Object.keys(tcHookIndexToType).find(k => tcHookIndexToType[k] === type);
          if (index !== undefined) {
            const btn = document.querySelector(`.tc-rating-buttons[data-hook-index="${index}"] .tc-rate-btn[data-rating="${rating}"]`);
            if (btn) btn.classList.add("active");
          }
        });
      }
      if (tcPendingNote) tcPendingNote.classList.remove("hidden");
    }
  });
}

// Save Taste Profile
if (tcSaveBtn) {
  tcSaveBtn.addEventListener("click", async () => {
    tcSaveBtn.disabled = true;
    tcStatus.textContent = "Saving taste profile...";
    tcStatus.className = "settings-status";
    
    const profile = {
      admired_channels: tcAdmiredChannels,
      hook_ratings: tcHookRatings,
      dislikes: tcDislikesInput ? tcDislikesInput.value.trim() : ""
    };
    
    const scrollToNext = () => {
      const target = document.getElementById("hook-type-settings");
      if (target) {
        setTimeout(() => {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 800);
      }
    };
    
    try {
      // POST to /memory/taste
      const res = await fetch(`${SERVER}/memory/taste`, {
        method: "POST",
        mode: "cors",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-Yoink-Token": await STC.getToken()
        },
        body: JSON.stringify(profile)
      });
      
      if (res.ok) {
        // Success
        tcStatus.textContent = "Taste profile saved ✓";
        tcStatus.className = "settings-status ok";
        if (tcPendingNote) tcPendingNote.classList.add("hidden");
        // Clear pending from storage
        chrome.storage.local.remove("uoink_taste_pending");
        scrollToNext();
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (e) {
      // Fallback to local storage
      console.warn("Failed to POST taste profile, falling back to local storage", e);
      chrome.storage.local.set({ uoink_taste_pending: profile }, () => {
        tcStatus.textContent = "Taste profile saved locally (syncs later) ✓";
        tcStatus.className = "settings-status ok";
        if (tcPendingNote) tcPendingNote.classList.remove("hidden");
        scrollToNext();
      });
    } finally {
      tcSaveBtn.disabled = false;
    }
  });
}

if (tcSkipBtn) {
  tcSkipBtn.addEventListener("click", () => {
    tcStatus.textContent = "Taste calibration skipped.";
    tcStatus.className = "settings-status warn";
    const target = document.getElementById("hook-type-settings");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// ---- Taste Anchors Settings (Sprint 3) -----------------------------------
const anchorsBestList = document.getElementById("anchors-best-list");
const anchorsWorstList = document.getElementById("anchors-worst-list");
const anchorsChannelsList = document.getElementById("anchors-channels-list");
const taStatus = document.getElementById("ta-status");
const taPendingNote = document.getElementById("ta-pending-note");

async function loadTasteAnchors() {
  if (!anchorsBestList || !anchorsWorstList || !anchorsChannelsList) return;
  
  try {
    // Try to GET /taste/anchors
    const res = await fetch(`${SERVER}/taste/anchors`, {
      method: "GET",
      mode: "cors",
      cache: "no-store",
      headers: {
        "X-Yoink-Token": await STC.getToken()
      }
    });
    
    if (res.ok) {
      const data = await res.json();
      renderTasteAnchors(data.anchors || data);
      if (taPendingNote) taPendingNote.classList.add("hidden");
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch {
    // Fallback to chrome.storage.local. Older helpers do not expose this route,
    // and the local cache is the intended compatibility path.
    chrome.storage.local.get({ uoink_taste_anchors: { best: [], worst: [], admired_channels: [] } }, (items) => {
      const anchors = items.uoink_taste_anchors || { best: [], worst: [], admired_channels: [] };
      renderTasteAnchors(anchors);
      if (taPendingNote) taPendingNote.classList.remove("hidden");
    });
  }
}

function renderTasteAnchorsList(listEl, items, type, emptyMsg) {
  listEl.innerHTML = "";
  if (!items || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "panel-muted";
    empty.style.cssText = "font-size:11px;padding:4px 6px";
    empty.textContent = emptyMsg;
    listEl.appendChild(empty);
    return;
  }
  
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "correction-row";
    
    const titleBtn = document.createElement("button");
    titleBtn.className = "correction-title";
    titleBtn.type = "button";
    titleBtn.title = "Remove from anchors";
    titleBtn.textContent = item.title || item.name || item.video_id || item;
    
    const removeLabel = document.createElement("div");
    removeLabel.className = "correction-date";
    removeLabel.textContent = "✕ Remove";
    removeLabel.style.cursor = "pointer";
    
    const removeFn = async () => {
      row.style.opacity = 0.5;
      row.style.pointerEvents = "none";
      const id = item.video_id || item.id || item;
      try {
        const res = await fetch(`${SERVER}/taste/anchors/${encodeURIComponent(id)}`, {
          method: "DELETE",
          mode: "cors",
          headers: {
            "X-Yoink-Token": await STC.getToken()
          }
        });
        if (res.ok) {
          loadTasteAnchors();
        } else {
          throw new Error(`HTTP ${res.status}`);
        }
      } catch {
        chrome.storage.local.get({ uoink_taste_anchors: { best: [], worst: [], admired_channels: [] } }, (stored) => {
          const anchors = stored.uoink_taste_anchors || { best: [], worst: [], admired_channels: [] };
          if (type === "best") {
            anchors.best = anchors.best.filter(x => (x.video_id || x) !== id);
          } else if (type === "worst") {
            anchors.worst = anchors.worst.filter(x => (x.video_id || x) !== id);
          } else {
            anchors.admired_channels = anchors.admired_channels.filter(x => x !== id);
          }
          chrome.storage.local.set({ uoink_taste_anchors: anchors }, () => {
            loadTasteAnchors();
          });
        });
      }
    };
    
    titleBtn.addEventListener("click", removeFn);
    removeLabel.addEventListener("click", removeFn);
    
    row.appendChild(titleBtn);
    row.appendChild(removeLabel);
    listEl.appendChild(row);
  });
}

function renderTasteAnchors(data) {
  renderTasteAnchorsList(anchorsBestList, data.best || [], "best", "No best anchors set. Mark videos as 10/10 in the popup.");
  renderTasteAnchorsList(anchorsWorstList, data.worst || [], "worst", "No worst anchors set. Mark videos as 0/10 in the popup.");
  renderTasteAnchorsList(anchorsChannelsList, data.admired_channels || data.channels || [], "channel", "No admired channels set.");
}

// ---- v3 Setup settings additions -----------------------------------------
const ycChannelInput = document.getElementById("yc-channel-input");
const ycAddBtn = document.getElementById("yc-add-btn");
const ycList = document.getElementById("yc-list");
const ycRecognizeBtn = document.getElementById("yc-recognize-btn");
const ycStatus = document.getElementById("yc-status");

const creatorToolsSection = document.getElementById("creator-tools-settings");
const ctWorkspaceFormat = document.getElementById("ct-workspace-format");
const ctTargetLength = document.getElementById("ct-target-length");
const ctLengthDisplay = document.getElementById("ct-length-display");
const ctStyleSourceRadios = document.getElementsByName("ct-style-source");
const ctScriptsPath = document.getElementById("ct-scripts-path");
const ctObsidianPath = document.getElementById("ct-obsidian-path");
const ctObsidianMirror = document.getElementById("ct-obsidian-mirror");

const creatorToolsStatus = document.getElementById("creator-tools-status");

const cvEnabled = document.getElementById("cv-enabled");
const cvSources = document.getElementById("cv-sources");
const cvOverrideInfo = document.getElementById("cv-override-info");
const claimVerificationStatus = document.getElementById("claim-verification-status");

const settingsPendingBanner = document.getElementById("settings-pending-banner");

let yourChannelsList = [];
// saveV3Settings calls made so far and those not answered yet; a section's
// status line still waiting -> { since: the number of the save its latest
// change made, fields: the fields changed there that no answer has shown as
// kept yet }.
let v3SavesMade = 0;
let v3SavesQueued = 0;
const v3StatusWaiting = new Map();

// A section's line names the settings in it the helper did not keep.
const V3_SETTING_LABELS = {
  default_target_length: "Default target length",
  default_workspace_format: "Default workspace format",
  style_anchors_source: "Style anchors source",
  obsidian_vault_path: "Obsidian vault path",
  mirror_scripts_to_obsidian: "Mirror scripts to Obsidian vault",
  claim_verification_enabled: "Scan transcripts for checkable claims",
  default_evidence_sources: "Default evidence sources",
};

function v3NotSupportedText(fields) {
  const names = [...fields].map((f) => `"${V3_SETTING_LABELS[f] || f}"`);
  return `Not saved: Uoink helper does not support ${names.join(", ")}`;
}

function renderYcList() {
  if (!ycList) return;
  ycList.innerHTML = "";
  if (yourChannelsList.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No channels added yet.";
    ycList.appendChild(empty);
    return;
  }
  
  yourChannelsList.forEach((chan, idx) => {
    const row = document.createElement("div");
    row.className = "correction-row yc-item";
    row.style.margin = "4px 0";
    
    const leftWrap = document.createElement("div");
    const nameVal = document.createElement("div");
    nameVal.className = "correction-title";
    nameVal.textContent = chan;
    
    const statusVal = document.createElement("div");
    statusVal.className = "yc-item-status";
    statusVal.style.cssText = "font-size: 11px; color: var(--text-mute);";
    statusVal.textContent = "Added";
    
    leftWrap.appendChild(nameVal);
    leftWrap.appendChild(statusVal);
    
    const rightWrap = document.createElement("div");
    rightWrap.style.cssText = "display: flex; gap: 8px; align-items: center;";
    
    const verifyBtn = document.createElement("button");
    verifyBtn.className = "button ghost yc-verify-btn";
    verifyBtn.type = "button";
    verifyBtn.style.cssText = "padding: 4px 8px; font-size: 11px; font-weight: 600; height: auto;";
    verifyBtn.textContent = "Verify";
    verifyBtn.addEventListener("click", () => {
      verifyChannel(chan, statusVal, verifyBtn);
    });
    
    const removeBtn = document.createElement("span");
    removeBtn.className = "remove-chip yc-remove-btn";
    removeBtn.style.cssText = "cursor: pointer; font-size: 16px; color: var(--text-mute); padding: 0 4px;";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      yourChannelsList.splice(idx, 1);
      renderYcList();
      updateCreatorToolsVisibility();
      saveV3Settings(null, "your_channels");
    });
    
    rightWrap.appendChild(verifyBtn);
    rightWrap.appendChild(removeBtn);
    
    row.appendChild(leftWrap);
    row.appendChild(rightWrap);
    
    ycList.appendChild(row);
  });
}

function updateCreatorToolsVisibility() {
  if (creatorToolsSection) {
    if (yourChannelsList.length >= 1) {
      creatorToolsSection.classList.remove("hidden");
    } else {
      creatorToolsSection.classList.add("hidden");
    }
  }
}

function updateTargetLengthDisplay(val) {
  if (!ctLengthDisplay) return;
  const lenVals = { 0: "30s", 1: "60s", 2: "5m", 3: "15m", 4: "30m" };
  ctLengthDisplay.textContent = lenVals[val] || "5m";
}

async function verifyChannel(channelName, statusEl, btnEl) {
  statusEl.textContent = "Verifying...";
  statusEl.style.color = "var(--text-mute)";
  btnEl.disabled = true;
  
  try {
    const token = await STC.getToken();
    const res = await fetch(`${SERVER}/channels/verify`, {
      method: "POST",
      mode: "cors",
      headers: {
        "Content-Type": "application/json",
        "X-Yoink-Token": token
      },
      body: JSON.stringify({ channel: channelName })
    });
    const data = await res.json();
    if (res.ok && data && data.ok) {
      statusEl.textContent = "Verified ✓";
      statusEl.style.color = "var(--ok)";
    } else {
      statusEl.textContent = (data && data.error) || `Failed (HTTP ${res.status})`;
      statusEl.style.color = "var(--vermillion)";
    }
  } catch (err) {
    statusEl.textContent = "Failed (Server offline)";
    statusEl.style.color = "var(--vermillion)";
  } finally {
    btnEl.disabled = false;
  }
}

// Every saveV3Settings call sends the Your Channels, Creator tools and Claim
// verification settings the page has from the helper or the user changed
// here (settingKnown), so each save made after a change carries it.
// The section the change was made in (field: the setting changed) shows
// Saving..., then Saved as soon as one of those saves is stored with every
// field changed there kept, Not saved when the helper stored the save but
// left one out, or Save failed once all of them have failed. A section that
// failed still waits: a later save from any section that is stored carries
// its change too and settles it.
async function saveV3Settings(statusEl, field) {
  const seq = ++v3SavesMade;
  if (field) noteSettingEdited(field);
  if (statusEl) {
    const waiting = v3StatusWaiting.get(statusEl) || { since: 0, fields: new Set() };
    waiting.since = seq;
    if (field) waiting.fields.add(field);
    v3StatusWaiting.set(statusEl, waiting);
    setSettingStatus(statusEl, "Saving...", null);
  }
  v3SavesQueued += 1;
  const lenVals = { 0: "30s", 1: "60s", 2: "5m", 3: "15m", 4: "30m" };
  let selectedStyleSource = "taste";
  if (ctStyleSourceRadios) {
    for (const r of ctStyleSourceRadios) {
      if (r.checked) selectedStyleSource = r.value;
    }
  }
  
  const sourcesText = cvSources ? cvSources.value.trim() : "";
  const sourcesArray = sourcesText ? sourcesText.split(/\r?\n/).map(s => s.trim()).filter(Boolean) : [];

  const body = {
    your_channels: yourChannelsList,
    default_workspace_format: ctWorkspaceFormat ? ctWorkspaceFormat.value : "markdown",
    default_target_length: ctTargetLength ? (lenVals[ctTargetLength.value] || "5m") : "5m",
    style_anchors_source: selectedStyleSource,
    obsidian_vault_path: ctObsidianPath ? ctObsidianPath.value.trim() : "",
    mirror_scripts_to_obsidian: ctObsidianMirror ? !!ctObsidianMirror.checked : false,
    claim_verification_enabled: cvEnabled ? !!cvEnabled.checked : false,
    default_evidence_sources: sourcesArray
  };

  // Comment Intelligence, Hook Type, the picker and the screenshot count save
  // on their own when changed (saveSettingOnChange), so they are not repeated
  // here.
  const v3Fields = Object.keys(body);
  knownSettingsOnly(body);

  let failed = null;
  // The settings the helper sent back, once it has stored this save.
  let stored = null;
  try {
    if (!window.STC || !STC.updateSettings) {
      throw new Error("STC.updateSettings unavailable");
    }
    const res = await writeSettings(body);
    if (res && res.ok) {
      // Only what the helper stored leaves the pending record, plus fields
      // an earlier version kept there that these saves no longer carry.
      const kept = res.settings || {};
      updatePendingRecord((record) => {
        for (const f of Object.keys(record)) {
          if (!v3Fields.includes(f) || (f in body && settingStored(kept, f, body[f]))) {
            delete record[f];
          }
        }
        return record;
      });
      adoptSettings(res.settings);
      stored = res.settings || {};
    } else {
      failed = (res && res.error) ? `Save failed: ${res.error}` : "Save failed";
      throw new Error((res && res.error) || "Save settings failed");
    }
  } catch (err) {
    if (!failed) failed = "Save failed: Uoink helper unreachable";
    console.warn("Failed to POST settings to server, storing in pending:", err);
    updatePendingRecord((record) => Object.assign(record, body));
  }

  v3SavesQueued -= 1;
  for (const [el, waiting] of [...v3StatusWaiting]) {
    // Changed again after this save was made: a newer save carries it.
    if (waiting.since > seq) continue;
    if (stored) {
      for (const f of [...waiting.fields]) {
        if (settingStored(stored, f, body[f])) waiting.fields.delete(f);
      }
      if (waiting.fields.size === 0) {
        setSettingStatus(el, "Saved", "ok");
        v3StatusWaiting.delete(el);
      } else {
        setSettingStatus(el, v3NotSupportedText(waiting.fields), "warn");
      }
    } else if (v3SavesQueued === 0) {
      setSettingStatus(el, failed, "warn");
    }
  }
}

// uoink_settings_pending holds the settings failed saves carried until the
// helper stores them; the banner shows while it holds any. change(record)
// edits a copy and returns it; updates run one at a time, in order.
let pendingRecordUpdates = Promise.resolve();

function updatePendingRecord(change) {
  pendingRecordUpdates = pendingRecordUpdates.then(() => new Promise((resolve) => {
    chrome.storage.local.get(["uoink_settings_pending"], (items) => {
      const prior = items && items.uoink_settings_pending;
      const record = change(Object.assign({}, prior && typeof prior === "object" ? prior : {}));
      const done = () => {
        if (settingsPendingBanner) {
          settingsPendingBanner.classList.toggle("hidden", !Object.keys(record).length);
        }
        resolve();
      };
      if (Object.keys(record).length) {
        chrome.storage.local.set({ uoink_settings_pending: record }, done);
      } else {
        chrome.storage.local.remove("uoink_settings_pending", done);
      }
    });
  })).catch((e) => console.warn("Pending settings not updated:", e));
}

async function loadPendingV3Settings() {
  chrome.storage.local.get(["uoink_settings_pending"], (items) => {
    const stored = items.uoink_settings_pending;
    if (stored) {
      if (settingsPendingBanner) settingsPendingBanner.classList.remove("hidden");
      // A field the user already edited here keeps that edit (saved or not,
      // it is newer than this record).
      const pending = Object.assign({}, stored);
      for (const field of Object.keys(pending)) {
        if (settingEditCount(field) > 0) delete pending[field];
      }
      // They are the user's changes: later saves carry them (settingKnown)
      // and a save's answer doesn't put the helper's old values back
      // (adoptSettings).
      for (const field of ["your_channels", ...Object.keys(V3_SETTING_LABELS)]) {
        if (pending[field] !== undefined) changedSettingFields.add(field);
      }
      if (pending.your_channels !== undefined) {
        yourChannelsList = pending.your_channels;
        renderYcList();
      }
      if (pending.default_workspace_format !== undefined && ctWorkspaceFormat) {
        ctWorkspaceFormat.value = pending.default_workspace_format;
      }
      if (pending.default_target_length !== undefined && ctTargetLength) {
        const lenToVal = { "30s": 0, "60s": 1, "5m": 2, "15m": 3, "30m": 4 };
        ctTargetLength.value = lenToVal[pending.default_target_length] !== undefined ? lenToVal[pending.default_target_length] : 2;
        updateTargetLengthDisplay(ctTargetLength.value);
      }
      if (pending.style_anchors_source !== undefined && ctStyleSourceRadios) {
        for (const r of ctStyleSourceRadios) {
          r.checked = r.value === pending.style_anchors_source;
        }
      }
      if (pending.obsidian_vault_path !== undefined && ctObsidianPath) {
        ctObsidianPath.value = pending.obsidian_vault_path;
      }
      if (pending.mirror_scripts_to_obsidian !== undefined && ctObsidianMirror) {
        ctObsidianMirror.checked = !!pending.mirror_scripts_to_obsidian;
      }
      if (pending.claim_verification_enabled !== undefined && cvEnabled) {
        cvEnabled.checked = !!pending.claim_verification_enabled;
      }
      if (pending.default_evidence_sources !== undefined && cvSources) {
        cvSources.value = Array.isArray(pending.default_evidence_sources)
          ? pending.default_evidence_sources.join("\n")
          : pending.default_evidence_sources;
      }
      updateCreatorToolsVisibility();
    }
  });
}

// Wire up events
if (ycAddBtn && ycChannelInput) {
  const addChannel = () => {
    const val = ycChannelInput.value.trim();
    if (val) {
      if (!yourChannelsList.includes(val)) {
        yourChannelsList.push(val);
        renderYcList();
        updateCreatorToolsVisibility();
        saveV3Settings(null, "your_channels");
      }
      ycChannelInput.value = "";
    }
  };
  ycAddBtn.addEventListener("click", addChannel);
  ycChannelInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      addChannel();
    }
  });
}

if (ycRecognizeBtn) {
  ycRecognizeBtn.addEventListener("click", async () => {
    if (ycStatus) {
      ycStatus.textContent = "Triggering backfill recognize...";
      ycStatus.className = "settings-status";
    }
    ycRecognizeBtn.disabled = true;
    try {
      const token = await STC.getToken();
      const res = await fetch(`${SERVER}/channels/recognize-now`, {
        method: "POST",
        mode: "cors",
        headers: {
          "X-Yoink-Token": token
        }
      });
      const data = await res.json();
      if (res.ok && data && data.ok) {
        if (ycStatus) {
          ycStatus.textContent = "Backfill recognition started ✓";
          ycStatus.className = "settings-status ok";
        }
      } else {
        throw new Error((data && data.error) || `HTTP ${res.status}`);
      }
    } catch (err) {
      if (ycStatus) {
        ycStatus.textContent = "Backfill failed (Server offline)";
        ycStatus.className = "settings-status warn";
      }
    } finally {
      ycRecognizeBtn.disabled = false;
    }
  });
}

if (ctTargetLength) {
  ctTargetLength.addEventListener("input", (ev) => {
    updateTargetLengthDisplay(ev.target.value);
    saveV3Settings(creatorToolsStatus, "default_target_length");
  });
}

if (ctWorkspaceFormat) {
  ctWorkspaceFormat.addEventListener("change",
    () => saveV3Settings(creatorToolsStatus, "default_workspace_format"));
}

if (ctStyleSourceRadios) {
  for (const r of ctStyleSourceRadios) {
    r.addEventListener("change", () => saveV3Settings(creatorToolsStatus, "style_anchors_source"));
  }
}

if (ctObsidianPath) {
  ctObsidianPath.addEventListener("input", () => noteSettingEdited("obsidian_vault_path"));
  ctObsidianPath.addEventListener("change",
    () => saveV3Settings(creatorToolsStatus, "obsidian_vault_path"));
}

if (ctObsidianMirror) {
  ctObsidianMirror.addEventListener("change",
    () => saveV3Settings(creatorToolsStatus, "mirror_scripts_to_obsidian"));
}

if (cvEnabled) {
  cvEnabled.addEventListener("change",
    () => saveV3Settings(claimVerificationStatus, "claim_verification_enabled"));
}

if (cvSources) {
  cvSources.addEventListener("input", () => noteSettingEdited("default_evidence_sources"));
  cvSources.addEventListener("change",
    () => saveV3Settings(claimVerificationStatus, "default_evidence_sources"));
}

if (cvOverrideInfo) {
  cvOverrideInfo.addEventListener("click", (ev) => {
    ev.preventDefault();
    chrome.tabs.create({ url: "http://127.0.0.1:5179/dashboard" });
  });
}

// ---- Boot ----------------------------------------------------------------
setCIControlsEnabled(false);
applyDownloadState();
applySource();
loadPendingTasteProfile();
loadPendingV3Settings();
loadTasteAnchors();
startPolling();

// If the tab gets backgrounded for a while we don't burn cycles polling,
// but we resume the moment it's visible again so a user who tabbed away to
// run the installer sees the green check immediately on return.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (statusBlock.classList.contains("is-running")) return;
    stopPolling();
  } else {
    if (!statusBlock.classList.contains("is-running")) startPolling();
  }
});
