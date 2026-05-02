// Send to Claude — content script.
// Injects a button under the YouTube player (alongside Like / Share / Download)
// that POSTs the current video URL to the local helper server, copies the
// returned markdown to the clipboard, and opens claude.ai in a new tab.
//
// Network/storage logic lives in lib/extract.js (exposed as window.STC) and
// is shared with background.js.

(() => {
  "use strict";

  const BTN_CLASS = "stc-yt-injected-button";
  const BTN_ID = "stc-yt-send-to-claude";
  const ANCHOR_SELECTORS = [
    "ytd-watch-metadata #top-level-buttons-computed",
    "#top-level-buttons-computed",
    "ytd-watch-metadata #actions-inner",
    "ytd-watch-metadata #actions",
    "#actions-inner",
    "#actions",
  ];

  // ---- Styles (scoped via the unique class prefix) ----------------------
  const STYLE_ID = "stc-yt-styles";
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .${BTN_CLASS} {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 36px;
        padding: 0 16px;
        margin-left: 8px;
        border: none;
        border-radius: 18px;
        background: var(--yt-spec-badge-chip-background, rgba(255,255,255,0.1));
        color: var(--yt-spec-text-primary, #fff);
        font-family: "Roboto", "Arial", sans-serif;
        font-size: 14px;
        font-weight: 500;
        line-height: 36px;
        cursor: pointer;
        white-space: nowrap;
        transition: background-color 0.12s ease;
      }
      .${BTN_CLASS}:hover { background: rgba(255,255,255,0.2); }
      .${BTN_CLASS}:active { background: rgba(255,255,255,0.28); }
      .${BTN_CLASS}[disabled] { opacity: 0.7; cursor: progress; }
      .${BTN_CLASS}.stc-yt-error { background: rgba(217,87,87,0.25); color: #ffd9d9; }
      .${BTN_CLASS}.stc-yt-success { background: rgba(87,217,131,0.25); color: #d9ffe7; }
      .${BTN_CLASS} .stc-yt-icon { width: 16px; height: 16px; flex-shrink: 0; }
      .${BTN_CLASS} .stc-yt-spinner {
        width: 14px; height: 14px;
        border: 2px solid rgba(255,255,255,0.3);
        border-top-color: currentColor;
        border-radius: 50%;
        animation: stc-yt-spin 0.7s linear infinite;
      }
      @keyframes stc-yt-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
  }

  const ICON_SVG = `
    <svg class="stc-yt-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M12 2 L14.2 9.8 L22 12 L14.2 14.2 L12 22 L9.8 14.2 L2 12 L9.8 9.8 Z"
            fill="currentColor"/>
    </svg>
  `;

  function setButtonState(btn, state, label) {
    btn.classList.remove("stc-yt-error", "stc-yt-success");
    if (state === "error") btn.classList.add("stc-yt-error");
    if (state === "success") btn.classList.add("stc-yt-success");
    if (state === "working") {
      btn.disabled = true;
      btn.innerHTML = `<span class="stc-yt-spinner"></span><span>${label}</span>`;
    } else {
      btn.disabled = false;
      btn.innerHTML = `${ICON_SVG}<span>${label}</span>`;
    }
  }

  function resetButtonAfter(btn, ms) {
    setTimeout(() => setButtonState(btn, "default", defaultLabel()), ms);
  }

  function notify(title, message) {
    try {
      chrome.runtime.sendMessage({ type: "notify", title, message });
    } catch (e) {
      console.warn("[Send to Claude] notify failed", e);
    }
  }

  function openTab(url) {
    try {
      chrome.runtime.sendMessage({ type: "openTab", url });
    } catch (e) {
      console.warn("[Send to Claude] openTab failed", e);
    }
  }

  // ---- Active session awareness -----------------------------------------
  let activeSession = null;

  function getActiveFromStorage() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ active_session: null }, (items) => {
          resolve(items.active_session || null);
        });
      } catch { resolve(null); }
    });
  }

  function defaultLabel() {
    return activeSession ? `Add to session: ${activeSession.name || activeSession.id}` : "Send to Claude";
  }

  function refreshDefaultLabel() {
    const btn = document.getElementById(BTN_ID);
    if (!btn || btn.disabled) return;
    setButtonState(btn, "default", defaultLabel());
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.active_session) {
      activeSession = changes.active_session.newValue || null;
      refreshDefaultLabel();
    }
  });

  // ---- Click handler ----------------------------------------------------
  async function onClick(btn) {
    const rawUrl = window.location.href;
    if (!/youtube\.com\/watch/.test(rawUrl)) return;

    const url = STC.normalizeYouTubeUrl(rawUrl) || rawUrl;
    activeSession = await getActiveFromStorage(); // freshen in case popup just changed it
    const interval = await STC.getInterval();

    if (activeSession && activeSession.id) {
      return runSessionAdd(btn, url, interval);
    }
    return runExtract(btn, url, interval);
  }

  async function runExtract(btn, url, interval) {
    setButtonState(btn, "working", "Working...");

    let data;
    try {
      data = await STC.postExtractViaBg(url, interval);
    } catch (e) {
      console.error("[Send to Claude] server unreachable", e);
      setButtonState(btn, "error", "Start the local server");
      btn.title = "Run start_server.bat in the yoink folder, then try again.";
      notify("Send to Claude — server offline",
             `Couldn't reach ${STC.SERVER}. Run start_server.bat in the yoink folder.`);
      resetButtonAfter(btn, 5000);
      return;
    }

    if (!data || !data.ok) {
      const msg = (data && data.error) || "Unknown server error.";
      setButtonState(btn, "error", "Failed — see notification");
      btn.title = msg;
      notify("Send to Claude — failed", msg);
      resetButtonAfter(btn, 5000);
      return;
    }

    let copied = false;
    try {
      await navigator.clipboard.writeText(data.combined_md);
      copied = true;
    } catch (e) {
      console.warn("[Send to Claude] clipboard API failed, falling back", e);
      try {
        const ta = document.createElement("textarea");
        ta.value = data.combined_md;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        copied = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch (e2) {
        console.error("[Send to Claude] clipboard fallback failed", e2);
      }
    }

    openTab("https://claude.ai/new");

    const shotsLine = `${data.screenshot_count} screenshots saved.`;
    const clipLine = copied
      ? "Transcript copied. Paste in the new tab with Ctrl+V."
      : "Transcript NOT copied (clipboard blocked). Open combined.md in the folder.";
    notify("Ready in Claude", `${clipLine} Screenshots folder is open in Explorer. ${shotsLine}`);

    setButtonState(btn, "success", "Sent ✓");
    btn.title = `Saved to: ${data.folder}`;
    resetButtonAfter(btn, 3000);
  }

  async function runSessionAdd(btn, url, interval) {
    const sessionName = activeSession.name || activeSession.id;
    setButtonState(btn, "working", `Adding to ${sessionName}...`);

    let data;
    try {
      data = await STC.addToSessionViaBg(activeSession.id, url, interval);
    } catch (e) {
      console.error("[Send to Claude] server unreachable", e);
      setButtonState(btn, "error", "Start the local server");
      btn.title = "Run start_server.bat in the yoink folder, then try again.";
      notify("Send to Claude — server offline",
             `Couldn't reach ${STC.SERVER}. Run start_server.bat in the yoink folder.`);
      resetButtonAfter(btn, 5000);
      return;
    }

    if (!data || !data.ok) {
      const msg = (data && data.error) || "Unknown server error.";
      setButtonState(btn, "error", "Failed — see notification");
      btn.title = msg;
      notify("Send to Claude — failed", msg);
      resetButtonAfter(btn, 5000);
      return;
    }

    notify("Added to session",
           `${sessionName} · ${data.video_count} video${data.video_count === 1 ? "" : "s"} so far. ` +
           `End the session in the popup to send to Claude.`);

    setButtonState(btn, "success", `Added (${data.video_count})`);
    btn.title = `Saved to: ${data.folder}`;
    resetButtonAfter(btn, 3000);
  }

  // ---- Inject -----------------------------------------------------------
  function findAnchor() {
    for (const sel of ANCHOR_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function injectButton() {
    if (!/youtube\.com\/watch/.test(window.location.href)) return false;
    if (document.getElementById(BTN_ID)) return true;

    const anchor = findAnchor();
    if (!anchor) return false;

    injectStyles();

    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.className = BTN_CLASS;
    btn.type = "button";
    btn.title = "Extract transcript + screenshots and open Claude";
    setButtonState(btn, "default", defaultLabel());
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      onClick(btn);
    });

    anchor.appendChild(btn);
    // Now that the button exists, fetch the latest active-session state and
    // re-label if needed.
    getActiveFromStorage().then((s) => {
      activeSession = s;
      refreshDefaultLabel();
    });
    return true;
  }

  function tryInjectWithRetries() {
    let tries = 0;
    const maxTries = 20;
    const interval = setInterval(() => {
      tries += 1;
      if (injectButton() || tries >= maxTries) clearInterval(interval);
    }, 500);
  }

  window.addEventListener("yt-navigate-finish", () => {
    setTimeout(tryInjectWithRetries, 250);
  });

  const observer = new MutationObserver(() => {
    if (!document.getElementById(BTN_ID)) injectButton();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  tryInjectWithRetries();
})();
