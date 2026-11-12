// Setup owns install, verify and the first capture. Settings live in the dashboard.
// Agent connections now expose all 99 tools; capped clients can use UOINK_MCP_TOOLSET=core.
"use strict";
const SERVER = "http://127.0.0.1:5179";
const POLL_MS = 2000;
const HEARTBEAT_MS = 10000;
// The one version constant for download links. Bump it when a release is
// published; the Mac DMG and the Windows installer ship together. Set
// PUBLISHED_MAC_DMG to "" to fall back to the manual Mac instructions.
const PUBLISHED_INSTALLER_VERSION = "3.16.3";
const PUBLISHED_MAC_DMG = PUBLISHED_INSTALLER_VERSION;
// Same tracked redirect the uoink.app buttons use (it counts downloads without
// IP addresses or cookies, then sends the visitor to the GitHub release asset).
const GET_BASE = "https://usage.uoink.app/get";
const RUNNING_COPY = { win: "Running on this PC", mac: "Running on this Mac", linux: "Running on this computer" };
const $ = (id) => document.getElementById(id);
let platformOs = "win";
let platformArch = "";
let funnelState = "checking";
let downloadClicked = false;
let helperUp = false;
let pollTimer = null;
let probe = null;
let probeGeneration = 0;
let captureStarting = false;
let captureId = null;
let captureFinished = false;

function scrollBehavior() {
  const preferred = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  // Setup has no animated scroll surface. Keep navigation instant even when
  // the system permits motion; only readers, toasts and capture strips move.
  return preferred === "smooth" ? "auto" : preferred;
}

async function showStoreInstall() {
  const url = await globalThis.UoinkStore?.load();
  if (!url) return;
  $("store-install-link").href = url;
  $("store-install").hidden = false;
}

function downloadUrl(os) {
  return `${GET_BASE}/${os === "mac" ? "mac" : "windows"}?v=${os === "mac" ? PUBLISHED_MAC_DMG : PUBLISHED_INSTALLER_VERSION}&from=extension`;
}

// Chrome reports "arm" for Apple silicon and "x86-64" for Intel.
function isIntelMac() { return platformOs === "mac" && /^x86/i.test(platformArch); }

function setPlatform(os, arch) {
  const value = String(os || "").toLowerCase();
  platformOs = /^(mac|darwin)/.test(value) ? "mac" : /^(linux|cros|openbsd)/.test(value) ? "linux" : "win";
  if (arch !== undefined) platformArch = String(arch || "");
  document.body.dataset.platform = platformOs;
  const windows = platformOs === "win";
  const macDownload = platformOs === "mac" && PUBLISHED_MAC_DMG !== "" && !isIntelMac();
  $("download-btn").hidden = !windows && !macDownload;
  $("manual-install").hidden = windows || macDownload;
  $("download-btn").href = downloadUrl("win");
  $("download-btn").textContent = "Download for Windows";
  if (macDownload) {
    $("download-btn").href = downloadUrl("mac");
    $("download-btn").textContent = "Download for Mac";
  }
  $("install-instructions").textContent = windows
    ? "Download the Windows installer, open it, and follow the installation steps. Agent connections include all 99 Uoink tools."
    : macDownload
      ? "Download Uoink for Mac (Apple silicon), open it, and drag Uoink to Applications. Then open Uoink from Applications."
      : isIntelMac()
        ? "The Mac app is built for Apple silicon (M1 or newer) and does not run on Intel Macs. Use the manual install instructions."
        : `No ${platformOs === "mac" ? "Mac" : "Linux"} download is published yet. Use the manual install instructions.`;
  if (!helperUp && $("status-block").dataset.state === "down") $("status-instructions").textContent = helperOfflineDetail();
  renderFunnel();
}

// Store-first funnel. States: checking (first probe pending), needs-app (helper
// not found), connecting (the download was started, waiting for the helper) and
// connected. Pure rendering from helperUp, probeDone and downloadClicked.
function funnelCopy() {
  const where = { win: "this PC", mac: "this Mac", linux: "this computer" }[platformOs];
  const why = "Uoink saves transcripts to your own disk, so it needs a small app on your computer. It is free and has no account.";
  if (funnelState === "connected") {
    return { title: "Connected", body: `Uoink is running on ${where}. Your captures save to your own library on this computer.`,
      next: ["Open any YouTube video and click the Uoink button, or paste a link in step 3 below.", "Your saved video shows up in the Library with its transcript."] };
  }
  if (funnelState === "connecting") {
    const how = platformOs === "mac" ? "Open the downloaded file, drag Uoink to Applications, then open Uoink."
      : "Open the installer you just downloaded and finish it. Uoink starts when it is done.";
    return { title: "Waiting for Uoink to start", body: why, next: [how, "This page connects by itself. You do not need to refresh."] };
  }
  if (funnelState === "checking") return { title: "Checking for Uoink", body: "Looking for the Uoink app on this computer.", next: [] };
  const intel = isIntelMac();
  const unsupported = intel || platformOs === "linux";
  return {
    title: "Uoink needs its free desktop app",
    body: why,
    next: unsupported
      ? [intel ? "This Mac has an Intel chip. The Mac app is built for Apple silicon (M1 or newer), so there is no download for it yet."
          : "There is no Linux installer. Linux users can run the helper from source.",
        "Use the manual install instructions below. This page connects once the helper is running."]
      : ["Download the app and open it.", "Come back to this tab. It connects by itself and shows what to try first."],
  };
}

function renderFunnel() {
  const copy = funnelCopy();
  document.body.dataset.funnel = funnelState;
  $("funnel").dataset.state = funnelState;
  $("funnel-title").textContent = copy.title;
  $("funnel-body").textContent = copy.body;
  const list = $("funnel-next");
  list.replaceChildren();
  for (const line of copy.next) {
    const li = document.createElement("li");
    li.textContent = line;
    list.appendChild(li);
  }
  list.hidden = !copy.next.length;
  const connected = funnelState === "connected";
  $("install").hidden = connected;
  $("progress-install-item").hidden = connected;
  $("funnel-os").hidden = connected || funnelState === "checking";
  $("funnel-os").textContent = { win: "Windows 10 or 11", mac: isIntelMac() ? "Mac with an Intel chip" : "Mac with Apple silicon", linux: "Linux" }[platformOs];
}

function setFunnel(helperAnswered) {
  funnelState = helperAnswered ? "connected" : downloadClicked ? "connecting" : "needs-app";
  renderFunnel();
}

function helperOfflineDetail() {
  if (platformOs === "mac") return "Open Uoink from Applications, or run uoink-helper from Terminal. This page will check again automatically.";
  if (platformOs === "linux") return "Run uoink-helper from Terminal. This page will check again automatically.";
  return "Open the Windows Start Menu, type Uoink, and start Uoink Server. This page will check again automatically.";
}

function markCurrent(step) {
  for (const name of ["install", "verify", "capture"]) {
    const link = $("progress-" + name);
    if (name === step) link.setAttribute("aria-current", "step");
    else link.removeAttribute("aria-current");
  }
  // One primary per page: the current step's main action. Install shows
  // either the download or the manual instructions, never both.
  const main = {
    install: [$("download-btn"), $("manual-install")],
    verify: [$("verify-btn")],
    capture: [$("uoink-suggested-btn")],
  };
  for (const [name, buttons] of Object.entries(main)) {
    for (const button of buttons) button.classList.toggle("primary", name === step);
  }
}

// Old bookmarks and extension links still lead to the settings they named.
function applySource() {
  const routes = {
    "#mcp-settings": "agents", "#skill-settings": "agents",
    "#comment-intelligence": "ai", "#hook-type-settings": "ai",
    "#hook-calibration-settings": "ai", "#claim-verification-settings": "ai",
    "#smart-screenshot-settings": "ai", "#taste-anchors-settings": "ai",
    "#taste-calibration-onboarding": "ai", "#creator-tools-settings": "library",
    "#your-channels-settings": "library", "#helper-status-section": "app",
  };
  const source = new URLSearchParams(location.search).get("source");
  const section = routes[location.hash];
  $("settings-moved").hidden = !(section || source === "popup");
  $("settings-destination").href = `${SERVER}/dashboard#settings/${section || "capture"}`;
  const step = { "#install": "install", "#verify": "verify", "#first-capture": "capture" }[location.hash];
  markCurrent(step || (helperUp ? "capture" : source === "offline" || section || source === "popup" ? "verify" : "install"));
}

function renderAvailability() {
  $("uoink-suggested-btn").disabled = !helperUp || captureStarting || !!captureId;
  $("uoink-suggested-btn").textContent = captureStarting ? "Starting capture…" : captureFinished ? "Captured" : captureId ? "Capture started" : "Uoink this video";
  $("capture-hint").textContent = !helperUp ? "Connect the helper to start a capture."
    : "The capture runs in the background and saves to your library.";
}

function showConnection(up) {
  helperUp = up;
  $("status-block").dataset.state = up ? "running" : "down";
  $("status-text").textContent = up ? RUNNING_COPY[platformOs] : "Uoink is offline";
  $("status-instructions").textContent = up ? "Connected. You can start your first capture." : helperOfflineDetail();
  if (!up) $("diagnose").hidden = true;
  setFunnel(up);
  markCurrent(up ? "capture" : funnelState === "needs-app" ? "install" : "verify");
  renderAvailability();
}

async function readJson(path, signal) {
  const response = await fetch(SERVER + path, { method: "GET", mode: "cors", cache: "no-store", signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (!data || data.ok === false) throw new Error("Helper check failed");
  return data;
}

function renderDiagnose(body) {
  const list = $("diagnose-list");
  list.replaceChildren();
  const checks = Array.isArray(body.checks) ? body.checks : Array.isArray(body.results) ? body.results : [];
  for (const check of checks) {
    const status = String(check.status || check.state || (check.ok ? "ok" : "error")).toLowerCase();
    const passed = ["ok", "pass", "passed", "running", "available", "healthy"].includes(status);
    const row = document.createElement("li");
    row.className = "diagnose-row";
    const name = document.createElement("div");
    name.className = "diagnose-name";
    name.textContent = `${passed ? "Passed" : "Needs attention"} · ${String(check.label || check.name || "Check").replace(/_/g, " ")}`;
    const detail = document.createElement("div");
    detail.className = "diagnose-detail";
    detail.textContent = String(check.detail || check.message || check.error || status);
    row.appendChild(name);
    row.appendChild(detail);
    list.appendChild(row);
  }
  if (!checks.length) {
    const row = document.createElement("li");
    row.textContent = "The helper returned no additional checks.";
    list.appendChild(row);
  }
  // Public /diagnose deliberately omits local paths. No folder actions here.
  $("diagnose").hidden = false;
}

async function checkConnection(refreshChecks = false) {
  if (probe || document.hidden) return;
  clearTimeout(pollTimer);
  pollTimer = null;
  const generation = ++probeGeneration;
  const controller = new AbortController();
  probe = controller;
  const timeout = setTimeout(() => controller.abort(), 4000);
  $("verify-btn").setAttribute("aria-busy", "true");
  $("verify-btn").textContent = "Checking…";
  const wasUp = helperUp;
  try {
    const health = await readJson("/health", controller.signal);
    if (generation !== probeGeneration) return;
    if (health.platform || health.os) setPlatform(health.platform || health.os);
    showConnection(true);
    if (!wasUp || refreshChecks) {
      try {
        const checks = await readJson("/diagnose", controller.signal);
        if (generation === probeGeneration) renderDiagnose(checks);
      } catch {
        // A diagnostics error does not mean the successful health probe failed.
        if (generation === probeGeneration) {
          $("diagnose-list").textContent = "Additional checks are unavailable. The helper answered the connection check.";
          $("diagnose").hidden = false;
        }
      }
    }
  } catch {
    if (generation === probeGeneration) showConnection(false);
  } finally {
    clearTimeout(timeout);
    if (generation === probeGeneration) {
      probe = null;
      $("verify-btn").setAttribute("aria-busy", "false");
      $("verify-btn").textContent = "Check again";
      if (!document.hidden) pollTimer = setTimeout(checkConnection, helperUp ? HEARTBEAT_MS : POLL_MS);
    }
  }
}

async function readCaptureResult() {
  if (!captureId) return;
  const id = captureId;
  try {
    const state = await chrome.storage.session.get(["popup_capture_results"]);
    if (captureId !== id) return;
    const result = (state.popup_capture_results || []).find(row => row.id === id);
    if (!result) return;
    if (!result.ok) {
      $("capture-status").textContent = "Capture failed";
      $("capture-error").textContent = result.message || STC.describeFailure(result);
      $("capture-error").hidden = false;
      captureId = null;
    } else if (result.queued) {
      $("capture-status").textContent = "Waiting · one YouTube capture at a time. Follow this capture in Activity.";
    } else {
      captureFinished = true;
      $("capture-status").textContent = "Done · saved to your library";
      $("capture-destination").href = result.video_id
        ? `${SERVER}/dashboard#item/${encodeURIComponent(result.video_id)}` : `${SERVER}/dashboard#library`;
      $("capture-destination").textContent = result.video_id ? "Read capture" : "Open Library";
    }
    renderAvailability();
  } catch {
    $("capture-status").textContent = "Check Activity for this capture’s progress. You can close this tab.";
  }
}

async function startFirstCapture() {
  if (!helperUp || captureStarting || captureId) return;
  const url = STC.normalizeYouTubeUrl($("first-capture-url").value.trim());
  if (!url) {
    $("capture-result").hidden = false;
    $("capture-status").hidden = true;
    $("capture-destination").hidden = true;
    $("capture-error").textContent = "Paste a YouTube video link first.";
    $("capture-error").hidden = false;
    $("first-capture-url").setAttribute("aria-invalid", "true");
    $("first-capture-url").focus();
    return;
  }
  $("first-capture-url").removeAttribute("aria-invalid");
  captureStarting = true;
  captureFinished = false;
  $("capture-result").hidden = false;
  $("capture-error").hidden = true;
  $("capture-status").hidden = false;
  $("capture-destination").hidden = false;
  $("capture-status").textContent = "Starting capture…";
  $("capture-destination").href = `${SERVER}/dashboard#activity`;
  $("capture-destination").textContent = "View in Activity";
  renderAvailability();
  try {
    const result = await chrome.runtime.sendMessage({ type: "popupCapture", job: {
      route: "video", url, saveOnly: true,
    } });
    if (!result || !result.ok || !result.id) throw new Error(result && result.error || "The extension could not start this capture. Try again.");
    captureId = result.id;
    $("capture-status").textContent = "Capture started. Follow progress in Activity. You can close this tab.";
    // A fast job may finish before the acknowledgement reaches this page.
    await readCaptureResult();
  } catch (error) {
    $("capture-status").textContent = "Capture could not start";
    $("capture-error").textContent = STC.describeFailure({ error: error.message });
    $("capture-error").hidden = false;
  } finally {
    captureStarting = false;
    renderAvailability();
  }
}

$("skip-install").addEventListener("click", (event) => {
  event.preventDefault();
  markCurrent("verify");
  // Setup navigation does not animate; motion is reserved for the reader,
  // capture step strip and toasts.
  $("verify").scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  $("verify-btn").focus({ preventScroll: true });
  checkConnection(true);
});
$("verify-btn").addEventListener("click", () => checkConnection(true));
$("download-btn").addEventListener("click", () => {
  downloadClicked = true;
  if (!helperUp) setFunnel(false);
});
$("uoink-suggested-btn").addEventListener("click", startFirstCapture);
$("first-capture-url").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) startFirstCapture();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.popup_capture_results) readCaptureResult();
});
document.addEventListener("visibilitychange", () => {
  clearTimeout(pollTimer);
  if (document.hidden) {
    ++probeGeneration;
    if (probe) probe.abort();
    probe = null;
    $("verify-btn").setAttribute("aria-busy", "false");
    $("verify-btn").textContent = "Check again";
  } else {
    checkConnection();
    readCaptureResult();
  }
});
window.addEventListener("hashchange", applySource);
setPlatform("win");
renderFunnel();
chrome.runtime.getPlatformInfo(info => setPlatform(info && info.os, info && info.arch));
applySource();
showStoreInstall();
checkConnection();
