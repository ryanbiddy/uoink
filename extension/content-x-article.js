// Uoink — X (Twitter) ARTICLE content script (V-2c).
//
// PRIMARY article-capture path. Detects an X Article page, injects a
// "Uoink this article" button in the shipped button visual language, and on
// click reads the rendered Article DOM from the user's authenticated session
// (via lib/x-article.js -> XArticle.parseXArticle), then hands the parsed
// {url, title, author, markdown, images} to the local helper through the
// background service worker (POST /extract/x-article). Reading the DOM here
// side-steps X's login wall exactly like content-reddit.js does for Reddit.
//
// The popup drives the same parse by messaging this script
// ({type: "uoinkParseXArticle"}); when this script isn't present or the parse
// fails, the popup falls back to the /extract/page best-effort path.

(() => {
  "use strict";

  const BTN_CLASS = "uoink-btn";
  const BTN_ID = "uoink-x-article-btn";
  const STYLE_ID = "stc-x-article-styles";
  const DOT_CLASS = "stc-x-article-status-dot";

  function isArticlePage() {
    try {
      return !!(globalThis.XArticle
        && XArticle.isXArticleUrl(window.location.href));
    } catch {
      return false;
    }
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${BTN_ID}.${BTN_CLASS} {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 2147483646;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 36px;
        padding: 0 14px;
        border: none;
        border-radius: 18px;
        background: #C2410C;
        color: #FFF4EC;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
        transition: background-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
      }
      #${BTN_ID}.${BTN_CLASS}:hover { background: #FF3D00; color: #FFFFFF; }
      #${BTN_ID}.${BTN_CLASS}:active { transform: scale(0.97); }
      #${BTN_ID}.${BTN_CLASS}[disabled] { opacity: 0.7; cursor: progress; }
      #${BTN_ID}.${BTN_CLASS}.stc-x-article-error { background: #3A1F1F; color: #FFD9D9; }
      #${BTN_ID}.${BTN_CLASS}.stc-x-article-success { background: #1F2B22; color: #D9FFE7; }

      #${BTN_ID} .${DOT_CLASS} {
        width: 8px; height: 8px; border-radius: 50%;
        flex-shrink: 0; background: #888;
        transition: background-color 0.18s ease, box-shadow 0.18s ease;
      }
      #${BTN_ID}.uoink-status-online .${DOT_CLASS} {
        background: #00C853; box-shadow: 0 0 6px rgba(0,200,83,0.55);
      }
      #${BTN_ID}.uoink-status-offline .${DOT_CLASS} {
        background: #B8421A; box-shadow: 0 0 6px rgba(184,66,26,0.55);
      }
      #${BTN_ID}.uoink-status-checking .${DOT_CLASS} {
        background: #888; animation: stc-x-article-pulse 1.4s ease-in-out infinite;
      }
      #${BTN_ID}.uoink-status-checking { cursor: progress; }
      @keyframes stc-x-article-pulse {
        0%, 100% { opacity: 1; } 50% { opacity: 0.35; }
      }
      #${BTN_ID} .stc-x-article-icon { width: 11px; height: 14px; flex-shrink: 0; }
      #${BTN_ID} .stc-x-article-spinner {
        width: 12px; height: 12px;
        border: 2px solid rgba(255,255,255,0.3);
        border-top-color: currentColor;
        border-radius: 50%;
        animation: stc-x-article-spin 0.7s linear infinite;
      }
      @keyframes stc-x-article-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
  }

  const ICON_SVG = `
    <svg class="stc-x-article-icon" viewBox="0 0 100 100" width="11" height="14" aria-hidden="true" style="display:block;">
      <path d="M 0 0 L 32 0 L 32 60 L 68 60 L 68 0 L 100 0 L 100 80 Q 100 100 80 100 L 20 100 Q 0 100 0 80 Z" fill="currentColor"/>
      <rect x="0" y="0" width="32" height="20" fill="#FFF4EC"/>
      <rect x="68" y="0" width="32" height="20" fill="#FFF4EC"/>
    </svg>`;
  const DOT_SVG = `<span class="${DOT_CLASS}" aria-hidden="true"></span>`;

  let serverStatus = "checking";
  let statusTimer = null;
  let statusInflight = false;
  const STATUS_POLL_MS = 10000;

  function defaultLabel() {
    return serverStatus === "offline" ? "Helper offline" : "Uoink this article";
  }

  function setButtonState(btn, state, label) {
    btn.classList.remove("stc-x-article-error", "stc-x-article-success");
    if (state === "error") btn.classList.add("stc-x-article-error");
    if (state === "success") btn.classList.add("stc-x-article-success");

    btn.replaceChildren();
    const wrap = document.createElement("span");
    wrap.style.display = "inline-flex";
    wrap.style.alignItems = "center";
    wrap.style.gap = "6px";
    if (state === "working") {
      btn.disabled = true;
      wrap.innerHTML = `<span class="stc-x-article-spinner"></span>`;
    } else {
      btn.disabled = serverStatus === "checking";
      wrap.innerHTML = `${DOT_SVG}${ICON_SVG}`;
    }
    while (wrap.firstChild) btn.appendChild(wrap.firstChild);
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    btn.appendChild(labelEl);
  }

  function applyStatus(btn) {
    if (!btn) return;
    if (btn.querySelector(".stc-x-article-spinner")) return;
    btn.classList.remove("uoink-status-online", "uoink-status-offline", "uoink-status-checking");
    btn.classList.add(`uoink-status-${serverStatus}`);
    if (serverStatus === "online") {
      btn.title = "Read this X Article into your local corpus";
      btn.disabled = false;
    } else if (serverStatus === "offline") {
      btn.title = "Uoink Helper offline. Click to start.";
      btn.disabled = false;
    } else {
      btn.title = "Checking Uoink Helper status...";
      btn.disabled = true;
    }
  }

  function setServerStatus(next) {
    if (serverStatus === next) return;
    serverStatus = next;
    const btn = document.getElementById(BTN_ID);
    if (btn) {
      applyStatus(btn);
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

  function openSetupOffline() {
    try {
      chrome.runtime.sendMessage({
        type: "openTab",
        url: chrome.runtime.getURL("setup.html?source=offline"),
      });
    } catch (e) {
      console.warn("[Uoink] openSetupOffline failed", e);
    }
  }

  // Parse the article out of the live DOM. Returns the parser payload.
  function parseArticle() {
    try {
      return globalThis.XArticle.parseXArticle(document, window.location.href);
    } catch (e) {
      console.error("[Uoink] X Article parse threw", e);
      return { ok: false, code: "parse_error",
               error: "Couldn't read this article: " + (e && e.message || e) };
    }
  }

  async function handleClick(btn) {
    if (serverStatus === "offline") {
      openSetupOffline();
      return;
    }
    if (serverStatus !== "online") return;

    setButtonState(btn, "working", "Uoinking...");
    const parsed = parseArticle();
    if (!parsed || !parsed.ok) {
      console.warn("[Uoink] X Article parse failed:", parsed && parsed.error);
      setButtonState(btn, "error", "Couldn't read it");
      setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3500);
      return;
    }

    try {
      chrome.runtime.sendMessage(
        { type: "stcExtractXArticle", article: parsed },
        (response) => {
          if (chrome.runtime.lastError || !response || response.networkError) {
            const detail = (response && response.networkError) || "Helper unreachable.";
            console.error("[Uoink] X Article capture failed:", detail);
            setButtonState(btn, "error", "Failed!");
            setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
            return;
          }
          const data = response.data;
          if (!data || !data.ok) {
            console.error("[Uoink] X Article server error:", data && data.error);
            setButtonState(btn, "error", "Failed!");
            setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
            return;
          }
          setButtonState(btn, "success", "Uoinked!");
          setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
        });
    } catch (e) {
      console.error("[Uoink] X Article dispatch failed", e);
      setButtonState(btn, "error", "Failed!");
      setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
    }
  }

  function injectButton() {
    if (!isArticlePage()) {
      const existing = document.getElementById(BTN_ID);
      if (existing) existing.remove();
      return;
    }
    if (document.getElementById(BTN_ID)) return;
    if (!document.body) return;

    injectStyles();
    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.className = BTN_CLASS;
    setButtonState(btn, "default", defaultLabel());
    applyStatus(btn);
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      handleClick(btn);
    });
    document.body.appendChild(btn);
  }

  // Popup-driven parse. The popup messages this script; we parse the live DOM
  // and hand back the payload so the popup can POST it (or fall back to
  // /extract/page when we return ok:false or aren't present at all).
  try {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (!msg || msg.type !== "uoinkParseXArticle") return;
      const parsed = parseArticle();
      sendResponse({ ok: !!(parsed && parsed.ok), article: parsed });
      return true;
    });
  } catch { /* messaging unavailable in some contexts */ }

  // X is a SPA: re-check on DOM churn so the button appears after a client
  // navigation into an article and disappears when leaving one.
  const observer = new MutationObserver(() => injectButton());
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  }
  injectButton();
  startStatusPolling();

  window.addEventListener("beforeunload", () => {
    if (statusTimer) clearInterval(statusTimer);
    observer.disconnect();
  });
})();
