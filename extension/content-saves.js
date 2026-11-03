// Read only the rendered saves list. Scrolling and helper requests need a click.
(() => {
  "use strict";

  function pageUrl(value, base, hosts) {
    if (typeof value !== "string" || !value || /[\s\\]/.test(value)) return null;
    try {
      const url = new URL(value, base);
      return url.protocol === "https:" && !url.port && !url.username && !url.password
        && hosts.includes(url.hostname) ? url : null;
    } catch {
      return null;
    }
  }

  function parseYouTubeId(value) {
    const url = pageUrl(value, "https://www.youtube.com", ["www.youtube.com", "m.youtube.com", "youtube.com"]);
    if (!url || url.pathname !== "/watch") return null;
    const id = url.searchParams.get("v");
    return id && id.length === 11 && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
  }

  function normalizeXStatus(value) {
    const url = pageUrl(value, "https://x.com", ["x.com", "twitter.com", "www.x.com", "www.twitter.com"]);
    // Media, analytics and other action links are not the tweet's permalink.
    const match = url && url.pathname.match(/^\/([A-Za-z0-9_]{1,15})\/status\/([0-9]+)\/?$/);
    return match ? `https://x.com/${match[1]}/status/${match[2]}` : null;
  }

  function normalizeRedditPermalink(value) {
    const url = pageUrl(value, "https://www.reddit.com", ["reddit.com", "www.reddit.com", "old.reddit.com"]);
    const match = url && url.pathname.match(/^\/r\/([A-Za-z0-9_]+)\/comments\/([A-Za-z0-9]+)\/([^/\s?#]+)(?:\/([A-Za-z0-9]+))?\/?$/);
    if (!match || match[3] === "." || match[3] === "..") return null;
    return `https://www.reddit.com/r/${match[1]}/comments/${match[2]}/${match[3]}/`
      + (match[4] ? `${match[4]}/` : "");
  }

  // Tests can exercise parsing without a DOM, extension APIs, or networking.
  if (globalThis.__UOINK_SAVES_TEST__) {
    globalThis.__UOINK_SAVES_HELPERS__ = { parseYouTubeId, normalizeXStatus, normalizeRedditPermalink };
    return;
  }

  const MAX_ITEMS = 5000;
  const COLLECT_MS = 500;
  const SCROLL_MS = 2500;
  const PREFIX = "uoink-saves-";
  const items = new Map();
  let active = null;
  let closed = false;
  let panel = null;
  let style = null;
  let controls = null;
  let observer = null;
  let collectTimer = null;
  let lastCollect = 0;
  let scrollTimer = null;
  let lastScrollY = window.scrollY;
  let lastCount = 0;
  let emptySteps = 0;
  let busy = false;
  let batch = null;
  let stagedSize = 0;

  function detectPage() {
    const { hostname, pathname, search, protocol } = window.location;
    if (protocol !== "https:") return null;
    if (hostname === "www.youtube.com" && /^\/playlist\/?$/.test(pathname)
        && new URLSearchParams(search).get("list") === "WL") {
      return { source: "watch_later", label: "Watch Later videos", key: "watch_later" };
    }
    if (["x.com", "twitter.com"].includes(hostname) && /^\/i\/bookmarks\/?$/.test(pathname)) {
      return { source: "x_bookmarks", label: "bookmarks", key: "x_bookmarks" };
    }
    if (["www.reddit.com", "old.reddit.com"].includes(hostname)
        && /^\/user\/[A-Za-z0-9_-]+\/saved\/?$/i.test(pathname)) {
      return { source: "reddit_saved", label: "saved posts", key: pathname.replace(/\/$/, "") };
    }
    return null;
  }

  function setText(node, text) {
    // Do not feed our own updates back into the page observer.
    if (node.textContent !== text) node.textContent = text;
  }

  function render() {
    if (!controls) return;
    setText(controls.heading, `Uoink: ${items.size} ${active.label} found`);
    setText(controls.scroll, scrollTimer === null ? "Auto-scroll" : "Stop");
    setText(controls.send, `Send ${items.size} to Uoink`);
    setText(controls.scrolling, scrollTimer !== null ? `Scrolling... ${items.size} found`
      : items.size === MAX_ITEMS ? "5,000-item limit reached." : "");
    controls.scroll.disabled = busy || items.size >= MAX_ITEMS;
    controls.send.disabled = !!(busy || !items.size || (batch && batch.nextOffset !== null)
      || (batch && items.size <= stagedSize));
    controls.next.hidden = !batch || batch.nextOffset === null;
    controls.next.disabled = busy;
    controls.close.disabled = busy;
    panel.setAttribute("aria-busy", String(busy));
    setText(controls.progress, batch ? `${batch.done} of ${batch.total} sent` : "");
  }

  function remember(id, value, metadata = {}) {
    if (!id || !value || value.length > 300 || items.has(id) || items.size >= MAX_ITEMS) return;
    items.set(id, { value, ...metadata });
  }

  function collect() {
    if (collectTimer !== null) clearTimeout(collectTimer);
    collectTimer = null;
    const previous = active;
    syncPage();
    if (!active || active !== previous || items.size >= MAX_ITEMS) return;
    lastCollect = Date.now();
    if (active.source === "watch_later") {
      for (const row of document.querySelectorAll("ytd-playlist-video-renderer")) {
        for (const link of row.querySelectorAll('a#video-title, a[href*="watch?v="]')) {
          const id = parseYouTubeId(link.getAttribute("href"));
          if (!id) continue;
          const title = row.querySelector("a#video-title");
          const channel = row.querySelector("#channel-name, ytd-channel-name");
          remember(id, id, {
            title: (title && (title.getAttribute("title") || title.textContent) || "").trim().slice(0, 300),
            channel: (channel && channel.textContent || "").trim().slice(0, 200),
          });
          break;
        }
        if (items.size >= MAX_ITEMS) break;
      }
    } else if (active.source === "x_bookmarks") {
      for (const tweet of document.querySelectorAll('article[data-testid="tweet"]')) {
        for (const time of tweet.querySelectorAll("time")) {
          const link = time.closest("a[href]");
          const url = link && normalizeXStatus(link.getAttribute("href"));
          if (url) {
            remember(url.split("/").pop(), url);
            break;
          }
        }
        if (items.size >= MAX_ITEMS) break;
      }
    } else {
      for (const row of document.querySelectorAll('shreddit-post[permalink], .thing[data-permalink], a[href*="/comments/"]')) {
        const url = normalizeRedditPermalink(row.getAttribute("permalink")
          || row.getAttribute("data-permalink") || row.getAttribute("href"));
        if (url) {
          const parts = new URL(url).pathname.split("/");
          remember(`${parts[4].toLowerCase()}:${(parts[6] || "").toLowerCase()}`, url);
        }
        if (items.size >= MAX_ITEMS) break;
      }
    }
    if (items.size >= MAX_ITEMS) stopScrolling();
    render();
  }

  function scheduleCollect(records) {
    if (!active || collectTimer !== null || items.size >= MAX_ITEMS) return;
    if (records.every((record) => panel.contains(record.target))) return;
    collectTimer = setTimeout(collect, Math.max(0, COLLECT_MS - (Date.now() - lastCollect)));
  }

  function stopScrolling() {
    if (scrollTimer !== null) clearInterval(scrollTimer);
    scrollTimer = null;
    render();
  }

  function scrollStep() {
    window.scrollBy({ top: Math.round(window.innerHeight * 0.9), behavior: "instant" });
    lastScrollY = window.scrollY;
  }

  function toggleScrolling() {
    if (scrollTimer !== null) { stopScrolling(); return; }
    const page = active;
    collect();
    if (!active || active !== page || busy || items.size >= MAX_ITEMS) return;
    lastCount = items.size;
    emptySteps = 0;
    lastScrollY = window.scrollY;
    scrollTimer = setInterval(() => {
      syncPage();
      if (!active || scrollTimer === null) return;
      emptySteps = items.size === lastCount ? emptySteps + 1 : 0;
      lastCount = items.size;
      if (emptySteps >= 4 || items.size >= MAX_ITEMS) { stopScrolling(); return; }
      scrollStep();
    }, SCROLL_MS);
    scrollStep();
    render();
  }

  function sendMessage(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (!response) {
          reject(new Error("Uoink didn't respond. Reload this page and try again."));
        } else {
          resolve(response);
        }
      });
    });
  }

  async function send(next) {
    const previous = active;
    syncPage();
    if (!active || active !== previous || busy) return;
    stopScrolling();
    if (!next) collect();
    if (next ? !batch || batch.nextOffset === null : !items.size) return;
    const page = active;
    const offset = next ? batch.nextOffset : 0;
    const size = items.size;
    const message = next ? { type: "stcImportNext", url: batch.url, offset }
      : { type: "stcStageSaves", source: page.source,
        items: Array.from(items.values(), (item) => item.value).slice(0, MAX_ITEMS) };
    busy = true;
    setText(controls.status, "Sending to Uoink...");
    render();
    try {
      const result = await sendMessage(message);
      syncPage();
      if (active !== page) return;
      if (!next && /^uoink-saves:[0-9a-f]{16}$/.test(result.url)) {
        stagedSize = size;
        batch = { url: result.url, total: result.total ?? result.count, done: 0, nextOffset: 0 };
      }
      if (!result.ok) throw new Error(result.error || "Uoink couldn't import these saves.");
      if (batch) {
        batch.total = result.total;
        batch.done = Math.min(result.total, offset + result.found);
        batch.nextOffset = result.next_offset;
      }
      setText(controls.status, result.message || "Sent to Uoink.");
    } catch (error) {
      syncPage();
      if (active === page) setText(controls.status, error.message || String(error));
    } finally {
      if (active === page) { busy = false; render(); }
    }
  }

  function element(tag, name, text) {
    const node = document.createElement(tag);
    node.className = PREFIX + name;
    if (text) node.textContent = text;
    return node;
  }

  function button(name, text, action) {
    const node = element("button", name, text);
    node.type = "button";
    node.addEventListener("click", (event) => {
      // A page script calling .click() must not start a collection or import.
      if (!event.isTrusted || node.disabled) return;
      event.stopPropagation();
      action();
    });
    return node;
  }

  function createPanel() {
    style = document.createElement("style");
    style.textContent = `
      #uoink-saves-panel { all: initial; position: fixed; right: 20px; bottom: 20px;
        z-index: 2147483647; box-sizing: border-box; width: 320px; max-width: calc(100vw - 40px);
        padding: 16px; border: 1px solid #EBD5C5; border-radius: 12px; background: #FFFFFF;
        color: #0A0A0A; font: 13px/1.5 system-ui, sans-serif; box-shadow: 0 4px 14px #0004; }
      #uoink-saves-panel * { box-sizing: border-box; }
      #uoink-saves-panel .uoink-saves-heading { display: block; padding-right: 32px; font-weight: 600; }
      #uoink-saves-panel .uoink-saves-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
      #uoink-saves-panel button { all: unset; box-sizing: border-box; display: inline-flex;
        align-items: center; justify-content: center; min-height: 36px; padding: 0 12px;
        border: 1px solid #94745F; border-radius: 18px; background: #FFFFFF; color: #0A0A0A;
        font: 600 13px/1.5 system-ui, sans-serif; cursor: pointer; touch-action: manipulation; }
      #uoink-saves-panel button:hover { background: #FBE6D6; }
      #uoink-saves-panel .uoink-saves-send, #uoink-saves-panel .uoink-saves-next {
        background: #C2410C; color: #FFFFFF; border-color: #C2410C; }
      #uoink-saves-panel .uoink-saves-send:hover, #uoink-saves-panel .uoink-saves-next:hover { background: #B23C0B; }
      #uoink-saves-panel button:focus-visible { outline: 2px solid #0A0A0A; outline-offset: 2px; }
      #uoink-saves-panel button:disabled { opacity: 0.55; cursor: default; }
      #uoink-saves-panel .uoink-saves-close { position: absolute; right: 8px; top: 8px;
        min-height: 32px; width: 32px; padding: 0; border: 0; font-size: 20px; }
      #uoink-saves-panel .uoink-saves-status, #uoink-saves-panel .uoink-saves-progress,
      #uoink-saves-panel .uoink-saves-scrolling { display: block; margin-top: 8px; overflow-wrap: anywhere; }
      #uoink-saves-panel [hidden], #uoink-saves-panel :empty { display: none; }
    `;
    document.head.appendChild(style);
    panel = element("section", "panel");
    panel.id = PREFIX + "panel";
    panel.setAttribute("aria-label", "Uoink saves");
    const heading = element("div", "heading");
    const scrolling = element("div", "scrolling");
    scrolling.setAttribute("role", "status");
    const status = element("div", "status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const progress = element("div", "progress");
    const actions = element("div", "actions");
    const close = button("close", "×", () => { closed = true; deactivate(); });
    close.setAttribute("aria-label", "Close Uoink saves panel");
    const scroll = button("scroll", "Auto-scroll", toggleScrolling);
    const sendButton = button("send", "", () => send(false));
    const next = button("next", "Next 50", () => send(true));
    for (const node of [scroll, sendButton, next]) actions.appendChild(node);
    for (const node of [heading, close, scrolling, actions, status, progress]) panel.appendChild(node);
    controls = { heading, scrolling, status, progress, close, scroll, send: sendButton, next };
    document.body.appendChild(panel);
    render();
  }

  function deactivate() {
    if (observer) observer.disconnect();
    observer = null;
    if (collectTimer !== null) clearTimeout(collectTimer);
    collectTimer = null;
    stopScrolling();
    if (panel) panel.remove();
    if (style) style.remove();
    panel = style = controls = active = batch = null;
    busy = false;
    stagedSize = 0;
    items.clear();
  }

  function syncPage() {
    const page = closed ? null : detectPage();
    if (page && active && page.key === active.key) return;
    if (!page && !active) return;
    deactivate();
    if (!page) return;
    active = page;
    createPanel();
    collect();
    observer = new MutationObserver(scheduleCollect);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ["href", "permalink", "data-permalink"] });
  }

  document.addEventListener("yt-navigate-finish", syncPage);
  window.addEventListener("popstate", syncPage);
  // Content scripts cannot reliably patch the page's isolated History API.
  setInterval(syncPage, 1000);
  window.addEventListener("scroll", () => {
    if (scrollTimer !== null && window.scrollY < lastScrollY - 1) stopScrolling();
    lastScrollY = window.scrollY;
  }, { passive: true });
  window.addEventListener("wheel", (event) => {
    if (event.isTrusted && event.deltaY < 0) stopScrolling();
  }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopScrolling(); });
  syncPage();
})();
