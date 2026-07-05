// Uoink — Reddit content script.
// Injects a Uoink capture button on Reddit comment threads.
// Communicates with local helper to extract the thread and copy it to the clipboard.

(() => {
  "use strict";

  const BTN_CLASS = "uoink-btn";
  const BTN_ID = "uoink-reddit-btn";
  const STYLE_ID = "stc-reddit-styles";
  const DOT_CLASS = "stc-reddit-status-dot";

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .${BTN_CLASS} {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 32px;
        padding: 0 12px;
        margin-left: 8px;
        border: none;
        border-radius: 16px;
        background: #C2410C;
        color: #FFF4EC;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        vertical-align: middle;
        transition: background-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
      }
      .${BTN_CLASS}:hover {
        background: #FF3D00;
        color: #FFFFFF;
      }
      .${BTN_CLASS}:active {
        transform: scale(0.97);
      }
      .${BTN_CLASS}[disabled] { opacity: 0.7; cursor: progress; }
      .${BTN_CLASS}.stc-reddit-error { background: #3A1F1F; color: #FFD9D9; }
      .${BTN_CLASS}.stc-reddit-success { background: #1F2B22; color: #D9FFE7; }

      .${BTN_CLASS} .${DOT_CLASS} {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
        background: #888;
        transition: background-color 0.18s ease, box-shadow 0.18s ease;
      }
      .${BTN_CLASS}.uoink-status-online .${DOT_CLASS} {
        background: #00C853;
        box-shadow: 0 0 6px rgba(0,200,83,0.55);
      }
      .${BTN_CLASS}.uoink-status-offline .${DOT_CLASS} {
        background: #B8421A;
        box-shadow: 0 0 6px rgba(184,66,26,0.55);
      }
      .${BTN_CLASS}.uoink-status-checking .${DOT_CLASS} {
        background: #888;
        animation: stc-reddit-pulse 1.4s ease-in-out infinite;
      }
      .${BTN_CLASS}.uoink-status-checking { cursor: progress; }
      .${BTN_CLASS} .${DOT_CLASS}.stc-reddit-flash {
        animation: stc-reddit-dot-flash 0.55s ease-out;
      }

      @keyframes stc-reddit-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.35; }
      }
      @keyframes stc-reddit-dot-flash {
        0% { transform: scale(1); }
        45% { transform: scale(1.7); }
        100% { transform: scale(1); }
      }

      .${BTN_CLASS} .stc-reddit-icon {
        width: 11px;
        height: 14px;
        flex-shrink: 0;
        margin-right: 2px;
      }
      .${BTN_CLASS} .stc-reddit-spinner {
        width: 12px; height: 12px;
        border: 2px solid rgba(255,255,255,0.3);
        border-top-color: currentColor;
        border-radius: 50%;
        animation: stc-reddit-spin 0.7s linear infinite;
      }
      @keyframes stc-reddit-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
  }

  const ICON_SVG = `
    <svg class="stc-reddit-icon" viewBox="0 0 100 100" width="11" height="14" aria-hidden="true" style="display: block;">
      <path d="M 0 0 L 32 0 L 32 60 L 68 60 L 68 0 L 100 0 L 100 80 Q 100 100 80 100 L 20 100 Q 0 100 0 80 Z" fill="currentColor"/>
      <rect x="0" y="0" width="32" height="20" fill="#FFF4EC"/>
      <rect x="68" y="0" width="32" height="20" fill="#FFF4EC"/>
    </svg>
  `;
  const DOT_SVG = `<span class="${DOT_CLASS}" aria-hidden="true"></span>`;

  let serverStatus = "checking";
  let statusTimer = null;
  let statusInflight = false;
  const STATUS_POLL_MS = 10000;

  function findRedditAnchor() {
    // Old Reddit
    const oldRedditButtons = document.querySelector("div.top-matter ul.flat-list.buttons");
    if (oldRedditButtons) {
      return { element: oldRedditButtons, type: "old" };
    }

    // Modern Reddit (shreddit)
    const shredditPost = document.querySelector("shreddit-post");
    if (shredditPost) {
      // 1. Try to find the post-actions bar
      const actions = shredditPost.querySelector("shreddit-post-actions");
      if (actions) {
        return { element: actions, type: "modern-actions" };
      }
      // 2. Try to find the share button or comment tracker
      const share = shredditPost.querySelector("shreddit-action-share");
      if (share && share.parentElement) {
        return { element: share.parentElement, type: "modern-share" };
      }
      // 3. Fallback: append to footer slot if it exists
      const footer = shredditPost.querySelector('[slot="footer"]');
      if (footer) {
        return { element: footer, type: "modern-footer" };
      }
      return { element: shredditPost, type: "modern-fallback" };
    }

    // Generic fallback
    const postContainer = document.querySelector('[data-testid="post-container"]');
    if (postContainer) {
      return { element: postContainer, type: "fallback-testid" };
    }

    return null;
  }

  function defaultLabel() {
    return serverStatus === "offline" ? "Helper offline" : "Uoink thread";
  }

  function setButtonState(btn, state, label) {
    btn.classList.remove("stc-reddit-error", "stc-reddit-success");
    if (state === "error") btn.classList.add("stc-reddit-error");
    if (state === "success") btn.classList.add("stc-reddit-success");

    btn.replaceChildren();
    const chromeWrap = document.createElement("span");
    chromeWrap.style.display = "inline-flex";
    chromeWrap.style.alignItems = "center";
    chromeWrap.style.gap = "6px";
    if (state === "working") {
      btn.disabled = true;
      chromeWrap.innerHTML = `<span class="stc-reddit-spinner"></span>`;
    } else {
      btn.disabled = serverStatus === "checking";
      chromeWrap.innerHTML = `${DOT_SVG}${ICON_SVG}`;
    }
    while (chromeWrap.firstChild) btn.appendChild(chromeWrap.firstChild);
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    btn.appendChild(labelEl);
  }

  function applyStatusToButton(btn) {
    if (!btn) return;
    if (btn.querySelector(".stc-reddit-spinner")) return;

    btn.classList.remove("uoink-status-online", "uoink-status-offline", "uoink-status-checking");
    btn.classList.add(`uoink-status-${serverStatus}`);

    if (serverStatus === "online") {
      btn.title = "Extract thread markdown + comments and open Claude";
      btn.disabled = false;
    } else if (serverStatus === "offline") {
      btn.title = "Uoink Helper offline. Click to start.";
      btn.disabled = false;
    } else {
      btn.title = "Checking Uoink Helper status...";
      btn.disabled = true;
    }
  }

  function flashDot(btn) {
    const dot = btn && btn.querySelector(`.${DOT_CLASS}`);
    if (!dot) return;
    dot.classList.remove("stc-reddit-flash");
    void dot.offsetWidth;
    dot.classList.add("stc-reddit-flash");
  }

  function setServerStatus(next) {
    if (serverStatus === next) return;
    const prev = serverStatus;
    serverStatus = next;
    const btn = document.getElementById(BTN_ID);
    if (btn) {
      applyStatusToButton(btn);
      if (prev !== "checking") flashDot(btn);
      setButtonState(btn, "default", defaultLabel());
    }
  }

  async function pollStatus() {
    if (statusInflight) return;
    statusInflight = true;
    try {
      const res = await new Promise((resolve) => {
        try {
          chrome.runtime.sendMessage({ type: "stcPing" }, (r) => {
            if (chrome.runtime.lastError) return resolve(null);
            resolve(r || null);
          });
        } catch { resolve(null); }
      });
      setServerStatus(res && res.ok ? "online" : "offline");
    } catch {
      setServerStatus("offline");
    } finally {
      statusInflight = false;
    }
  }

  function startStatusPolling() {
    if (statusTimer) clearInterval(statusTimer);
    pollStatus();
    statusTimer = setInterval(pollStatus, STATUS_POLL_MS);
  }

  function stopStatusPolling() {
    if (statusTimer) {
      clearInterval(statusTimer);
      statusTimer = null;
    }
  }

  function openSetupOffline() {
    try {
      chrome.runtime.sendMessage({ type: "openTab", url: chrome.runtime.getURL("setup.html?source=offline") });
    } catch (e) {
      console.warn("[Uoink] openSetupOffline failed", e);
    }
  }

  async function handleUoinkClick(btn) {
    if (serverStatus === "offline") {
      openSetupOffline();
      return;
    }
    if (serverStatus !== "online") return;

    setButtonState(btn, "working", "Uoinking...");

    const url = window.location.href;
    const interval = 30; // default interval

    try {
      chrome.runtime.sendMessage({ type: "stcExtract", url, interval }, async (response) => {
        if (chrome.runtime.lastError || !response || response.networkError) {
          const detail = response && response.networkError || "Helper unreachable.";
          console.error("[Uoink] capture failed:", detail);
          setButtonState(btn, "error", "Failed!");
          setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
          return;
        }

        const data = response.data;
        if (!data || !data.ok) {
          console.error("[Uoink] server error:", data && data.error);
          setButtonState(btn, "error", "Failed!");
          setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
          return;
        }

        setButtonState(btn, "success", "Uoinked!");
        setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
      });
    } catch (e) {
      console.error("[Uoink] dispatch failed", e);
      setButtonState(btn, "error", "Failed!");
      setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
    }
  }

  function injectButton() {
    if (document.getElementById(BTN_ID)) return;

    const anchor = findRedditAnchor();
    if (!anchor) return;

    injectStyles();

    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.className = BTN_CLASS;
    btn.style.margin = "0 8px";
    setButtonState(btn, "default", defaultLabel());
    applyStatusToButton(btn);

    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      handleUoinkClick(btn);
    });

    if (anchor.type === "old") {
      const li = document.createElement("li");
      li.appendChild(btn);
      anchor.element.appendChild(li);
    } else if (anchor.type === "modern-actions") {
      anchor.element.insertAdjacentElement("afterend", btn);
    } else {
      anchor.element.appendChild(btn);
    }
  }

  // Monitor DOM to ensure button stays injected across single page transitions.
  const observer = new MutationObserver(() => {
    injectButton();
  });

  observer.observe(document.body, { childList: true, subtree: true });
  injectButton();
  startStatusPolling();

  window.addEventListener("beforeunload", () => {
    stopStatusPolling();
    observer.disconnect();
  });
})();
