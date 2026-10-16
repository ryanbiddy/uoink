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
      maybeRunRetry();
    }
  }

  function startStatusPolling() {
    if (statusTimer) clearInterval(statusTimer);
    pollStatus();
    statusTimer = setInterval(pollStatus, STATUS_POLL_MS);
  }

  function stopStatusPolling() {
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = null;
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

  function notify(title, message) {
    try {
      chrome.runtime.sendMessage({ type: "notify", title, message });
    } catch (e) {
      console.warn("[Uoink] notify failed", e);
    }
  }

  // E6: same failure path as the YouTube button (content.js): the reason
  // goes in the button title, a notification, and the popup's remembered
  // failures. This script loads without lib/extract.js, so the SW words the
  // failure (response.failure / response.failureMessage) and records it.
  const LOST_TRACK_FAILURE = {
    kind: "lost", title: "Uoink lost track", label: "Lost track",
    message: "Uoink lost track of this capture. It may still have finished, so check your Library before trying again.",
  };

  // page: {url, title} of the article the capture started on, taken before
  // dispatch -- X is a SPA, so by the time the helper answers the tab may
  // show another article. replaces: the popup Retry record this failure
  // replaces (see claimRetry).
  function rememberFailure(page, error, replaces) {
    try {
      chrome.runtime.sendMessage({
        type: "rememberFailure",
        url: page.url,
        title: page.title,
        error,
        replaces: replaces || null,
      });
    } catch (e) {
      console.warn("[Uoink] rememberFailure failed", e);
    }
  }

  // A retried capture that went through drops the popup Retry record.
  function forgetFailure(id) {
    if (!id) return;
    try {
      chrome.runtime.sendMessage({ type: "forgetFailure", id });
    } catch (e) {
      console.warn("[Uoink] forgetFailure failed", e);
    }
  }

  function showFailure(btn, label, title, message) {
    setButtonState(btn, "error", label);
    btn.title = message;
    notify(title, message);
    setTimeout(() => setButtonState(btn, "default", defaultLabel()), 5000);
  }

  // retryOf: the popup Retry record this capture retries (see claimRetry).
  async function handleClick(btn, retryOf) {
    if (serverStatus === "offline") {
      openSetupOffline();
      return;
    }
    if (serverStatus !== "online") return;

    setButtonState(btn, "working", "Uoinking...");
    const page = { url: window.location.href, title: document.title || "" };
    const parsed = parseArticle();
    if (!parsed || !parsed.ok) {
      console.warn("[Uoink] X Article parse failed:", parsed && parsed.error);
      const msg = (parsed && parsed.error) || "Couldn't read this article.";
      rememberFailure(page, msg, retryOf);
      showFailure(btn, "Couldn't read it", "Uoink failed", msg);
      return;
    }

    try {
      chrome.runtime.sendMessage(
        { type: "stcExtractXArticle", article: parsed },
        (response) => {
          const lastError = chrome.runtime.lastError;
          if (lastError || !response || response.networkError) {
            const detail = (response && response.networkError)
              || (lastError && lastError.message) || "Helper unreachable.";
            console.error("[Uoink] X Article capture failed:", detail);
            // No response at all means the SW port went away mid-request.
            const failure = (response && response.failure) || LOST_TRACK_FAILURE;
            rememberFailure(page, failure.message, retryOf);
            showFailure(btn, failure.label, failure.title, failure.message);
            if (failure.kind === "offline") openSetupOffline();
            return;
          }
          const data = response.data;
          if (!data || !data.ok) {
            console.error("[Uoink] X Article server error:", data && data.error);
            const msg = response.failureMessage
              || (data && data.error) || "Couldn't save this article.";
            rememberFailure(page, msg, retryOf);
            showFailure(btn, "Failed!", "Uoink failed", msg);
            return;
          }
          forgetFailure(retryOf);
          setButtonState(btn, "success", "Uoinked!");
          setTimeout(() => setButtonState(btn, "default", defaultLabel()), 3000);
        });
    } catch (e) {
      console.error("[Uoink] X Article dispatch failed", e);
      showFailure(btn, LOST_TRACK_FAILURE.label, LOST_TRACK_FAILURE.title,
                  LOST_TRACK_FAILURE.message);
    }
  }

  // ---- Retry handoff from the popup ---------------------------------------
  // The popup's Recent failures Retry writes {auto_yoink: {url, failure_id,
  // ts}} and opens the article. Claim it once on the matching article. X
  // renders the article after the page loads, so the capture starts once the
  // helper status is known and the article parses (or the wait runs out, and
  // the parse failure is reported like a click would).
  const AUTO_UOINK_TTL_MS = 60_000;
  const AUTO_UOINK_PARSE_WAIT_MS = 20_000;
  let pendingRetry = null;

  function articleId(url) {
    const canonical = globalThis.XArticle && XArticle.normalizeXArticleUrl(url || "");
    return canonical ? canonical.slice(canonical.lastIndexOf("/") + 1) : null;
  }

  async function claimRetry() {
    const stored = await new Promise((r) => {
      try {
        chrome.storage.local.get({ auto_yoink: null }, (i) => r(i && i.auto_yoink));
      } catch { r(null); }
    });
    if (!stored || !stored.url) return;
    if (Date.now() - (stored.ts || 0) > AUTO_UOINK_TTL_MS) {
      try { chrome.storage.local.remove("auto_yoink"); } catch { /* ignore */ }
      return;
    }
    const target = articleId(stored.url);
    if (!target || target !== articleId(window.location.href)) return;
    // Clear before starting so a refresh or another tab can't re-fire it.
    await new Promise((r) => {
      try { chrome.storage.local.remove("auto_yoink", r); } catch { r(); }
    });
    pendingRetry = {
      target,
      failureId: stored.failure_id || null,
      waitUntil: Date.now() + AUTO_UOINK_PARSE_WAIT_MS,
    };
    maybeRunRetry();
  }

  function maybeRunRetry() {
    if (!pendingRetry) return;
    // The tab left the retried article before the retry ran: drop it so it
    // never captures another page; the record stays for another Retry.
    if (articleId(window.location.href) !== pendingRetry.target) {
      pendingRetry = null;
      return;
    }
    if (serverStatus === "checking") return;
    const btn = document.getElementById(BTN_ID);
    if (!btn) return;
    if (serverStatus === "online" && Date.now() < pendingRetry.waitUntil) {
      const parsed = parseArticle();
      if (!parsed || !parsed.ok) return; // not rendered yet; DOM churn re-checks
    }
    const { failureId } = pendingRetry;
    pendingRetry = null;
    handleClick(btn, failureId);
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
    maybeRunRetry();
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

  // E2: X is a SPA, so the manifest loads this script on every X page (Chrome
  // only injects declared scripts on a real page load) and it self-gates on
  // the URL: the button and the /health polling only run on an article.
  let lastHref = null;
  let onArticle = false;
  // Returns true when the URL changed since the last check.
  function syncToUrl() {
    const href = window.location.href;
    if (href === lastHref) return false;
    lastHref = href;
    onArticle = isArticlePage();
    if (!onArticle) stopStatusPolling();
    else if (!statusTimer) startStatusPolling();
    return true;
  }

  // Re-check on DOM churn and back/forward so the button appears after a
  // client navigation into an article and disappears when leaving one. Off
  // an article, churn costs a string compare until the URL changes.
  function onPageChange() {
    if (!syncToUrl() && !onArticle) return;
    injectButton();
    maybeRunRetry();
  }
  const observer = new MutationObserver(onPageChange);
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  }
  window.addEventListener("popstate", onPageChange);
  injectButton();
  syncToUrl();
  claimRetry().catch((e) => console.warn("[Uoink] auto_yoink failed", e));

  window.addEventListener("beforeunload", () => {
    if (statusTimer) clearInterval(statusTimer);
    observer.disconnect();
  });
})();
