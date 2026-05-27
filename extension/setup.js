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
const ciKeyInput = document.getElementById("anthropic-key");
const ciStatus = document.getElementById("ci-status");
const ciSaveBtn = document.getElementById("ci-save-btn");
const ciTestBtn = document.getElementById("ci-test-btn");
const ciClearBtn = document.getElementById("ci-clear-btn");
const aiCostEstimate = document.getElementById("ai-cost-estimate");
const hookTypeEnabled = document.getElementById("hook-type-enabled");
const smartScreenshotPickerEnabled = document.getElementById("smart-screenshot-picker-enabled");
const clipboardScreenshotCap = document.getElementById("clipboard-screenshot-cap");
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
      : "The local helper is running. Uoink any YouTube video to begin.";
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
      "Two minutes. Then you'll be uoinking videos straight into Claude.";
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
  for (const el of [
    ciEnabled,
    ciKeyInput,
    ciSaveBtn,
    ciTestBtn,
    ciClearBtn,
    hookTypeEnabled,
    smartScreenshotPickerEnabled,
    clipboardScreenshotCap,
  ]) {
    if (el) el.disabled = !enabled;
  }
  if (!enabled) setCIStatus("Start Uoink Server to manage settings.", "warn");
  if (!enabled && aiCostEstimate) aiCostEstimate.classList.add("hidden");
}

function renderCISettings(settings) {
  if (!settings) return;
  aiSettings = settings;
  if (ciEnabled) ciEnabled.checked = !!settings.comment_intelligence_enabled;
  if (hookTypeEnabled) hookTypeEnabled.checked = !!settings.hook_type_enabled;
  if (smartScreenshotPickerEnabled) {
    smartScreenshotPickerEnabled.checked = !!settings.smart_screenshot_picker_enabled;
  }
  if (clipboardScreenshotCap) {
    const cap = Number.isFinite(Number(settings.clipboard_screenshot_cap))
      ? Number(settings.clipboard_screenshot_cap)
      : 4;
    clipboardScreenshotCap.value = String(Math.max(0, Math.min(12, cap)));
  }
  if (ciKeyInput) {
    ciKeyInput.value = "";
    ciKeyInput.dataset.dirty = "false";
    ciKeyInput.placeholder = settings.anthropic_key_set
      ? "Key saved - enter a new key to replace"
      : "sk-ant-...";
  }
  setCIStatus(settings.anthropic_key_set ? "Key set" : "Key not set.",
              settings.anthropic_key_set ? "ok" : "warn");
  renderAICostEstimate();
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
    const res = await STC.getSettings();
    if (!res || !res.ok) {
      setCIStatus((res && res.error) || "Settings unavailable", "warn");
      return;
    }
    ciLoaded = true;
    renderCISettings(res.settings);
  } catch {
    setCIStatus("Settings unavailable", "warn");
  }
}

if (ciKeyInput) {
  ciKeyInput.addEventListener("input", () => {
    ciKeyInput.dataset.dirty = "true";
    renderAICostEstimate();
  });
}

for (const toggle of [ciEnabled, hookTypeEnabled]) {
  if (toggle) toggle.addEventListener("change", renderAICostEstimate);
}

if (ciSaveBtn) {
  ciSaveBtn.addEventListener("click", async () => {
    if (!window.STC || !STC.updateSettings) return;
    const body = {
      comment_intelligence_enabled: !!(ciEnabled && ciEnabled.checked),
      hook_type_enabled: !!(hookTypeEnabled && hookTypeEnabled.checked),
      smart_screenshot_picker_enabled: !!(
        smartScreenshotPickerEnabled && smartScreenshotPickerEnabled.checked
      ),
      clipboard_screenshot_cap: readClipboardScreenshotCap(),
    };
    const rawKey = ciKeyInput ? ciKeyInput.value.trim() : "";
    const keyDirty = ciKeyInput && ciKeyInput.dataset.dirty === "true";
    if (rawKey || keyDirty) body.anthropic_key = rawKey || null;

    setCIStatus("Saving...", null);
    ciSaveBtn.disabled = true;
    try {
      const res = await STC.updateSettings(body);
      if (!res || !res.ok) {
        setCIStatus((res && res.error) || "Save failed", "warn");
        return;
      }
      renderCISettings(res.settings);
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
    try {
      const res = await STC.updateSettings({
        comment_intelligence_enabled: !!(ciEnabled && ciEnabled.checked),
        hook_type_enabled: !!(hookTypeEnabled && hookTypeEnabled.checked),
        smart_screenshot_picker_enabled: !!(
          smartScreenshotPickerEnabled && smartScreenshotPickerEnabled.checked
        ),
        clipboard_screenshot_cap: readClipboardScreenshotCap(),
        anthropic_key: null,
      });
      if (!res || !res.ok) {
        setCIStatus((res && res.error) || "Clear failed", "warn");
        return;
      }
      if (ciKeyInput) {
        ciKeyInput.value = "";
        ciKeyInput.dataset.dirty = "false";
        ciKeyInput.placeholder = "sk-ant-...";
      }
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
    let path = installFolderPath;
    if (!path) {
      path = currentPlatform() === "mac"
        ? "~/Library/Application Support/Uoink"
        : "C:\\Users\\hello\\AppData\\Local\\Uoink";
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
    downloadBtn.classList.remove("disabled");
    downloadBtn.removeAttribute("aria-disabled");
    downloadBtn.title = "";
    downloadBtn.href = "https://github.com/ryanbiddy/uoink/releases/download/v2.1.0/Uoink-Setup-2.1.0.exe";
    downloadBtn.removeEventListener("click", preventDefaultClick);
  } else {
    downloadBtn.classList.add("disabled");
    downloadBtn.setAttribute("aria-disabled", "true");
    const macSpan = downloadBtn.querySelector('[data-mac-only]');
    const linuxSpan = downloadBtn.querySelector('[data-linux-only]');
    if (macSpan) macSpan.textContent = "Coming soon";
    if (linuxSpan) linuxSpan.textContent = "Coming soon";
    downloadBtn.title = "Installer publishes at launch.";
    downloadBtn.addEventListener("click", preventDefaultClick);
    downloadBtn.removeAttribute("href");
  }
}

// ---- Boot ----------------------------------------------------------------
setCIControlsEnabled(false);
applyDownloadState();
applySource();
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
