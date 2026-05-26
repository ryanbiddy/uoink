// Shared Uoink UI/client helpers.
//
// Loaded as a classic script so popup/setup/Memory pages, content scripts,
// and the background service worker can all consume the same small helper
// surface without switching the extension to ES modules.
(function (global) {
  "use strict";

  const DEFAULT_SERVER = "http://127.0.0.1:5179";
  const DEFAULT_HEALTH_FIELDS = [
    "transcript",
    "screenshots",
    "comments",
    "hook",
    "comment_intelligence",
  ];

  function serverBase(options) {
    return options && options.server
      || (global.STC && global.STC.SERVER)
      || DEFAULT_SERVER;
  }

  function tokenGetter(options) {
    return options && options.getToken
      || (global.STC && global.STC.getToken)
      || null;
  }

  async function authedFetch(path, init = {}, options = {}) {
    const getToken = tokenGetter(options);
    const url = /^https?:\/\//i.test(String(path))
      ? String(path)
      : `${serverBase(options)}${path}`;

    const doFetch = async (token) => {
      const headers = Object.assign({}, init.headers || {});
      if (token) headers["X-Yoink-Token"] = token;
      return fetch(url, Object.assign({}, init, {
        headers,
        mode: init.mode || "cors",
        credentials: init.credentials || "omit",
        cache: init.cache || "no-store",
      }));
    };

    let token = getToken ? await getToken() : null;
    let res = await doFetch(token);
    if (res.status === 403 && getToken) {
      token = await getToken({ refresh: true });
      res = await doFetch(token);
    }
    return { res, token };
  }

  async function authedJson(path, init = {}, options = {}) {
    const { res } = await authedFetch(path, init, options);
    let body = null;
    try { body = await res.json(); } catch { /* empty or non-JSON body */ }

    if (!res.ok || !body) {
      const detail = body && body.error ? body.error : `HTTP ${res.status}`;
      if (options.throwOnHttp) {
        const err = new Error(detail);
        err.status = res.status;
        throw err;
      }
      return body || { ok: false, error: detail };
    }
    return body;
  }

  function screenshotCountFromData(data, text) {
    const direct = Number(
      data && (
        data.clipboard_screenshot_count
        ?? data.screenshots_in_clipboard
        ?? data.included_screenshot_count
      )
    );
    if (Number.isFinite(direct) && direct >= 0) return Math.round(direct);
    if (Array.isArray(data && data.clipboard_screenshots)) {
      return data.clipboard_screenshots.length;
    }
    const body = String(text || data && (data.corpus_md_paste || data.uoink_md || data.yoink_md) || "");
    const matches = body.match(/!\[[^\]]*]\([^)]*\)/g);
    return matches ? matches.length : 0;
  }

  function clipboardBudgetFromData(data, clipboardText) {
    if (!data || typeof data !== "object") return null;
    const text = String(clipboardText || data.corpus_md_paste || data.uoink_md || data.yoink_md || "");
    const tokens = Number(data.token_estimate ?? data.clipboard_token_estimate);
    return {
      screenshotCount: screenshotCountFromData(data, text),
      tokenEstimate: Number.isFinite(tokens)
        ? Math.max(0, Math.round(tokens))
        : Math.round(text.length / 4),
      updatedAt: Date.now(),
    };
  }

  function formatTokenEstimate(tokens) {
    const n = Number(tokens);
    if (!Number.isFinite(n) || n < 0) return null;
    if (n >= 1000) return `${Math.round(n / 1000)}k`;
    return `${Math.round(n)}`;
  }

  function minutesUntil(value) {
    if (!value) return null;
    if (typeof value === "number" && Number.isFinite(value)) {
      return value > 10_000
        ? Math.max(0, Math.ceil((value - Date.now()) / 60000))
        : Math.max(0, Math.ceil(value / 60));
    }
    const when = Date.parse(value);
    if (!Number.isNaN(when)) return Math.max(0, Math.ceil((when - Date.now()) / 60000));
    return null;
  }

  function queuedMessage(data, options = {}) {
    const mins = minutesUntil(data && (
      data.next_retry_in_seconds
      ?? data.retry_in_seconds
      ?? data.next_retry_at
    ));
    const retry = mins == null ? "soon" : (mins <= 0 ? "now" : `in ${mins} min`);
    const suffix = options.suffix ? ` ${options.suffix}` : "";
    return `Queued - will retry ${retry}.${suffix}`;
  }

  function prettyHookType(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (ch) => ch.toUpperCase());
  }

  function healthLabel(key) {
    return prettyHookType(key);
  }

  function normalizeHealthValue(value) {
    if (value == null) return { status: "skipped", reason: "" };
    if (typeof value === "string") return { status: value, reason: "" };
    if (typeof value === "boolean") {
      return { status: value ? "ok" : "missing", reason: "" };
    }
    if (typeof value === "object") {
      return {
        status: String(value.status || value.state || value.result || (value.ok ? "ok" : "skipped")),
        reason: String(value.reason || value.error || value.message || ""),
      };
    }
    return { status: String(value), reason: "" };
  }

  function healthDotClass(status) {
    const s = String(status || "").toLowerCase();
    if (["ok", "success", "complete", "completed", "available", "present", "pass"].includes(s)) {
      return "ok";
    }
    if (["missing", "failed", "error", "warning", "warn", "blocked", "unavailable"].includes(s)) {
      return "missing";
    }
    return "skipped";
  }

  function healthEntries(health, fields = DEFAULT_HEALTH_FIELDS) {
    if (!health || typeof health !== "object") return [];
    const keys = [];
    for (const key of fields) {
      if (Object.prototype.hasOwnProperty.call(health, key)) keys.push(key);
    }
    for (const key of Object.keys(health)) {
      if (!keys.includes(key)) keys.push(key);
    }
    return keys.slice(0, 5).map((key) => {
      const normalized = normalizeHealthValue(health[key]);
      return { key, label: healthLabel(key), ...normalized };
    });
  }

  function healthTooltip(entries) {
    return entries.map((entry) => {
      const reason = entry.reason ? ` - ${entry.reason}` : "";
      return `${entry.label}: ${entry.status || "skipped"}${reason}`;
    }).join("\n");
  }

  function renderHealthDots(health, options = {}) {
    const entries = healthEntries(health, options.fields || DEFAULT_HEALTH_FIELDS);
    if (!entries.length) return null;

    const row = document.createElement("span");
    row.className = options.className || "health-row";
    row.title = healthTooltip(entries);
    row.setAttribute("aria-label", row.title);

    for (const entry of entries) {
      const dot = document.createElement("span");
      dot.className = `${options.dotClassName || "health-dot"} ${healthDotClass(entry.status)}`;
      const reason = entry.reason ? ` - ${entry.reason}` : "";
      dot.title = `${entry.label}: ${entry.status || "skipped"}${reason}`;
      row.appendChild(dot);
    }
    return row;
  }

  global.UoinkUI = {
    authedFetch,
    authedJson,
    screenshotCountFromData,
    clipboardBudgetFromData,
    formatTokenEstimate,
    minutesUntil,
    queuedMessage,
    prettyHookType,
    healthEntries,
    healthTooltip,
    renderHealthDots,
  };
  global.YoinkUI = global.UoinkUI;

  if (typeof customElements !== "undefined") {
    class UoinkMark extends HTMLElement {
      connectedCallback() {
        if (!this.shadowRoot) {
          this.attachShadow({ mode: "open" });
          this.render();
        }
        this._observer = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const width = entry.contentRect.width || this.getBoundingClientRect().width;
            this.updateTips(width);
          }
        });
        this._observer.observe(this);
      }
      disconnectedCallback() {
        if (this._observer) {
          this._observer.disconnect();
        }
      }
      render() {
        this.shadowRoot.innerHTML = `
          <style>
            :host {
              display: inline-block;
              vertical-align: middle;
            }
            svg {
              display: block;
              width: 100%;
              height: 100%;
            }
          </style>
          <svg id="svg" viewBox="0 0 100 100">
            <path d="M 0 0 L 32 0 L 32 60 L 68 60 L 68 0 L 100 0 L 100 80 Q 100 100 80 100 L 20 100 Q 0 100 0 80 Z" fill="currentColor"/>
            <rect id="tip-left" x="0" y="0" width="32" height="20" fill="#FFF4EC"/>
            <rect id="tip-right" x="68" y="0" width="32" height="20" fill="#FFF4EC"/>
          </svg>
        `;
      }
      updateTips(width) {
        const left = this.shadowRoot.getElementById("tip-left");
        const right = this.shadowRoot.getElementById("tip-right");
        if (!left || !right) return;
        if (width <= 32) {
          left.setAttribute("height", "20");
          left.setAttribute("fill", "#FFF4EC");
          right.setAttribute("height", "20");
          right.setAttribute("fill", "#FFF4EC");
        } else {
          left.setAttribute("height", "14");
          left.setAttribute("fill", "#FFD23F");
          right.setAttribute("height", "14");
          right.setAttribute("fill", "#FFD23F");
        }
      }
    }
    customElements.define("uoink-mark", UoinkMark);
  }
})(typeof self !== "undefined" ? self : globalThis);
