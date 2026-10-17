// Shared helper used by both the content script and the service worker.
// Loaded as a classic script (NOT an ES module) so the same file can be:
//   - listed in manifest content_scripts.js BEFORE content.js
//   - imported via importScripts() inside background.js
// Exposes everything on globalThis.STC.

(function (global) {
  "use strict";

  const SERVER = "http://127.0.0.1:5179";
  const DEFAULT_INTERVAL = 30;
  const REQUEST_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes

  // ---- Auth token (P0-1) ----------------------------------------------
  // Per-install token issued by the local server. Fetched lazily on first
  // mutating request, cached in memory + chrome.storage.local. On 403 we
  // refresh once (handles the server-reinstall-regenerated-token case).
  // /token is gated server-side by the chrome-extension:// origin, so a
  // webpage attempting CSRF can't grab it.
  const TOKEN_STORAGE_KEY = "yoink_token";
  let _cachedToken = null;
  let _tokenFetchPromise = null;

  function _readStoredToken() {
    return new Promise((r) => {
      try {
        chrome.storage.local.get({ [TOKEN_STORAGE_KEY]: null }, (i) => {
          r((i && i[TOKEN_STORAGE_KEY]) || null);
        });
      } catch { r(null); }
    });
  }
  function _writeStoredToken(t) {
    return new Promise((r) => {
      try { chrome.storage.local.set({ [TOKEN_STORAGE_KEY]: t }, () => r()); }
      catch { r(); }
    });
  }
  async function _fetchFreshToken() {
    try {
      // Chromium worker GETs omit Origin and send Sec-Fetch-Site: none.
      // POST carries chrome-extension://<id>, so the helper can enforce its
      // ID allowlist. Keep the custom client header for the bootstrap gate.
      const res = await fetch(`${SERVER}/token`, {
        method: "POST",
        mode: "cors",
        credentials: "omit",
        cache: "no-store",
        headers: { "X-Yoink-Client": "yoink-extension" },
      });
      if (!res.ok) return null;
      const data = await res.json();
      return (data && typeof data.token === "string") ? data.token : null;
    } catch { return null; }
  }
  async function getToken({ refresh = false } = {}) {
    if (!refresh && _cachedToken) return _cachedToken;
    if (!refresh) {
      const stored = await _readStoredToken();
      if (stored) { _cachedToken = stored; return stored; }
    }
    // Coalesce parallel fetches so the first wave of authed requests after
    // a wake doesn't slam /token N times.
    if (!_tokenFetchPromise) {
      _tokenFetchPromise = (async () => {
        const fresh = await _fetchFreshToken();
        if (fresh) {
          _cachedToken = fresh;
          await _writeStoredToken(fresh);
        }
        const out = fresh;
        _tokenFetchPromise = null;
        return out;
      })();
    }
    return _tokenFetchPromise;
  }
  async function _authedFetch(path, init) {
    init = init || {};
    const doFetch = async (tk) => {
      const headers = Object.assign({}, init.headers || {});
      if (tk) headers["X-Yoink-Token"] = tk;
      return fetch(`${SERVER}${path}`, Object.assign({}, init, {
        headers, mode: "cors", credentials: "omit",
      }));
    };
    let token = await getToken();
    let res = await doFetch(token);
    if (res.status === 403) {
      // Server may have regenerated the token (reinstall) -- refresh once.
      // A2: this retry is what keeps a STALE token from dead-ending a capture
      // (the live `rejected POST /extract/page (token mismatch)` 403). Every
      // authed route -- including /extract/page and /extract/x-article -- goes
      // through here, so none can bypass the refresh. If /token itself hiccups
      // and returns nothing, fall back to the last stored token rather than
      // retrying with no token at all (which would 403 a second time).
      token = await getToken({ refresh: true });
      if (!token) token = await _readStoredToken();
      res = await doFetch(token);
    }
    return res;
  }

  // Pull a YouTube video ID out of any of the URL shapes the context menu
  // can hand us. Returns null if nothing video-shaped is found.
  function extractVideoId(rawUrl) {
    let u;
    try { u = new URL(rawUrl); }
    catch { return null; }

    const host = u.hostname.replace(/^www\.|^m\./, "");

    if (host === "youtu.be") {
      const id = u.pathname.replace(/^\/+/, "").split("/")[0];
      return /^[\w-]{6,}$/.test(id) ? id : null;
    }

    if (host === "youtube.com") {
      if (u.pathname === "/watch") {
        const id = u.searchParams.get("v");
        return id && /^[\w-]{6,}$/.test(id) ? id : null;
      }
      const shorts = u.pathname.match(/^\/shorts\/([\w-]{6,})/);
      if (shorts) return shorts[1];
      const embed = u.pathname.match(/^\/embed\/([\w-]{6,})/);
      if (embed) return embed[1];
    }

    return null;
  }

  // Canonicalize to the standard watch URL the server knows how to handle.
  // Strips tracking junk (si, pp, feature, ...); preserves t (timestamp) so
  // future features can use it.
  function normalizeYouTubeUrl(rawUrl) {
    const id = extractVideoId(rawUrl);
    if (!id) return null;

    let t = null;
    try {
      const u = new URL(rawUrl);
      t = u.searchParams.get("t") || u.searchParams.get("start");
    } catch { /* ignore */ }

    let normalized = `https://www.youtube.com/watch?v=${id}`;
    if (t) normalized += `&t=${encodeURIComponent(t)}`;
    return normalized;
  }

  const TWITTER_HOSTS = new Set(["twitter.com", "www.twitter.com", "mobile.twitter.com", "x.com", "www.x.com"]);

  function normalizeTwitterUrl(raw) {
    if (!raw) return null;
    let u;
    try {
      u = new URL(raw.includes("://") ? raw : "https://" + raw);
    } catch {
      return null;
    }
    const host = u.hostname.toLowerCase();
    if (!TWITTER_HOSTS.has(host)) {
      return null;
    }
    const parts = u.pathname.replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length === 0 || parts[0] === "") return null;
    
    if (parts[0].toLowerCase() === "i" && parts.length >= 3 && parts[1] === "status") {
      if (/^\d{15,19}$/.test(parts[2])) {
        return `https://x.com/i/status/${parts[2]}`;
      }
      return null;
    }
    if (parts.length >= 3 && parts[1] === "status") {
      const handle = parts[0];
      const statusId = parts[2];
      if (/^[A-Za-z0-9_]{1,15}$/.test(handle) && /^\d{15,19}$/.test(statusId)) {
        return `https://x.com/${handle}/status/${statusId}`;
      }
    }
    return null;
  }

  // V-2c / A1: X ARTICLE (long-form) URL detection. Distinct from a status
  // URL: articles live at x.com/<handle>/article/<id> or x.com/i/article/<id>.
  //
  // A1 (authoritative routing): there is exactly ONE JS definition of the
  // Article URL shape — XArticle.normalizeXArticleUrl in lib/x-article.js.
  // This delegates to it so the popup classifier, the background context menu,
  // and the in-page content script can never disagree on what an Article is.
  // x-article.js is loaded before extract.js everywhere STC classifies an
  // Article tab (popup.html, background.js importScripts); when it isn't
  // present (a context that never classifies Articles) this returns null.
  // Do not reintroduce a local regex copy here.
  function normalizeXArticleUrl(raw) {
    const lib = global.XArticle;
    return (lib && typeof lib.normalizeXArticleUrl === "function")
      ? lib.normalizeXArticleUrl(raw)
      : null;
  }

  function isXArticleUrl(raw) {
    return !!normalizeXArticleUrl(raw);
  }

  // Short-form video (context-layer item 2): TikTok, Instagram Reels, and
  // YouTube Shorts. Mirrors server._normalize_short_video_url so the popup
  // classifier can never disagree with what /extract will accept. yt-dlp owns
  // all three; these just host-gate + canonicalize the URLs.
  const TIKTOK_HOSTS = new Set([
    "tiktok.com", "www.tiktok.com", "m.tiktok.com",
    "vm.tiktok.com", "vt.tiktok.com",
  ]);
  const INSTAGRAM_HOSTS = new Set([
    "instagram.com", "www.instagram.com", "m.instagram.com",
  ]);
  const _IG_KIND_RE = /^\/(?:[^/]+\/)?(reel|reels|p)\/([A-Za-z0-9_-]+)/i;

  function normalizeTikTokUrl(raw) {
    if (!raw || typeof raw !== "string") return null;
    let u;
    try { u = new URL(raw.includes("://") ? raw : "https://" + raw); }
    catch { return null; }
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const host = (u.hostname || "").toLowerCase();
    if (!TIKTOK_HOSTS.has(host)) return null;
    const path = (u.pathname || "").replace(/\/+$/, "");
    if (!path) return null;
    return `https://${host}${path}`;
  }

  function normalizeInstagramUrl(raw) {
    if (!raw || typeof raw !== "string") return null;
    let u;
    try { u = new URL(raw.includes("://") ? raw : "https://" + raw); }
    catch { return null; }
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const host = (u.hostname || "").toLowerCase();
    if (!INSTAGRAM_HOSTS.has(host)) return null;
    const m = (u.pathname || "").match(_IG_KIND_RE);
    if (!m) return null;
    return `https://www.instagram.com/${m[1].toLowerCase()}/${m[2]}/`;
  }

  // youtube.com/shorts/<id> is a Short; youtu.be/<id> carries no such signal
  // so it stays a regular video (honest: we don't guess).
  function isYouTubeShortUrl(raw) {
    if (!raw || typeof raw !== "string") return false;
    let u;
    try { u = new URL(raw.includes("://") ? raw : "https://" + raw); }
    catch { return false; }
    const host = (u.hostname || "").replace(/^www\.|^m\./, "").toLowerCase();
    return host === "youtube.com" && /^\/shorts\//.test(u.pathname || "");
  }

  // Returns the canonical URL for a short-form video (TikTok / Instagram Reel
  // / YouTube Short), or null. A YouTube Short normalizes to the watch URL
  // (it extracts through the same path) but classifies as source "short_video".
  function normalizeShortVideoUrl(raw) {
    if (isYouTubeShortUrl(raw)) {
      const yt = normalizeYouTubeUrl(raw);
      if (yt) return yt;
    }
    return normalizeTikTokUrl(raw) || normalizeInstagramUrl(raw);
  }

  function getInterval() {
    return new Promise((resolve) => {
      try {
        chrome.storage.sync.get({ interval: DEFAULT_INTERVAL }, (items) => {
          let n = parseInt(items && items.interval, 10);
          if (!Number.isFinite(n) || n < 5 || n > 300) n = DEFAULT_INTERVAL;
          resolve(n);
        });
      } catch {
        resolve(DEFAULT_INTERVAL);
      }
    });
  }

  // U-15: X text/thread capture. POST /extract/x with the raw status URL.
  // The server owns the feature flag (x_text_capture_enabled) and the
  // honest failure copy, so this just relays the JSON body. 60s timeout:
  // worst case is a hop-capped ancestor walk, not a transcript job.
  async function postExtractX(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60 * 1000);
    try {
      const res = await _authedFetch("/extract/x", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
        signal: controller.signal,
      });
      return withHttpStatus(await res.json(), res);
    } finally {
      clearTimeout(timer);
    }
  }

  // V-2c: X ARTICLE capture. POST /extract/x-article with the DOM already
  // parsed by the content script (the payload is
  // {url, title, author, markdown, images}) — the server never touches X, it
  // just persists the pre-parsed article as source_type 'x_article'. 60s
  // timeout: this is a local write, not a network extraction.
  async function postExtractXArticle(article) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60 * 1000);
    try {
      const res = await _authedFetch("/extract/x-article", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(article || {}),
        signal: controller.signal,
      });
      return withHttpStatus(await res.json().catch(() => ({
        ok: false, error: "Server returned a non-JSON response." })), res);
    } finally {
      clearTimeout(timer);
    }
  }

  // POST /extract with a 10-minute timeout. Returns the server's JSON body
  // (success or {ok: false, error: ...}). Throws only for network failures
  // (server unreachable / aborted).
  async function postExtract(url, interval) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const targetUrl = `${SERVER}/extract`;
    const requestBody = { url, interval };
    try {
      let res;
      try {
        res = await _authedFetch("/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
          signal: controller.signal,
        });
      } catch (e) {
        if (e instanceof TypeError) {
          console.error("[Uoink] server unreachable at", targetUrl, e);
        } else {
          console.error("[Uoink] fetch aborted/failed", targetUrl, e);
        }
        throw e;
      }

      const text = await res.text();
      if (!res.ok) {
        console.error("[Uoink] HTTP", res.status, "body:", text);
      }
      try {
        return withHttpStatus(JSON.parse(text), res);
      } catch {
        console.error("[Uoink] JSON parse error, raw text:", text);
        return withHttpStatus({ ok: false, error: "Server returned a non-JSON response." }, res);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  async function postExtractAny(url, interval) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const targetUrl = `${SERVER}/extract/any`;
    const requestBody = { url, interval };
    try {
      let res;
      try {
        res = await _authedFetch("/extract/any", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
          signal: controller.signal,
        });
      } catch (e) {
        if (e instanceof TypeError) {
          console.error("[Uoink] server unreachable at", targetUrl, e);
        } else {
          console.error("[Uoink] fetch aborted/failed", targetUrl, e);
        }
        throw e;
      }

      const text = await res.text();
      if (!res.ok) {
        console.error("[Uoink] HTTP", res.status, "body:", text);
      }
      try {
        return withHttpStatus(JSON.parse(text), res);
      } catch {
        console.error("[Uoink] JSON parse error, raw text:", text);
        return withHttpStatus({ ok: false, error: "Server returned a non-JSON response." }, res);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  async function ping() {
    // /health and /ping are intentionally unauthenticated -- they're the
    // public liveness probe used by the popup, the in-page button, and
    // setup.html. Keep them token-free so a stale token can't make the
    // server look offline.
    try {
      const res = await fetch(`${SERVER}/health`, {
        method: "GET", mode: "cors", credentials: "omit", cache: "no-store",
      });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  // ---- Session API -----------------------------------------------------
  async function _postJson(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await _authedFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });
      return withHttpStatus(await res.json().catch(() => ({
        ok: false, error: "Server returned a non-JSON response.",
      })), res);
    } finally {
      clearTimeout(timer);
    }
  }

  async function _getJson(path) {
    try {
      const res = await _authedFetch(path, { method: "GET" });
      return await res.json().catch(() => ({ ok: false, error: "Bad JSON" }));
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  // ---- Playlist / job API (v2) ----------------------------------------
  // These four endpoints belong to the v2 playlist flow. Popup sets
  // globalThis.YOINK_USE_MOCK_API = true while the real backend is being
  // built on `codex/v2-backend-playlist`; flip it off (in popup.js) once the
  // server lands and reconcile the wire shapes here against docs/v2-api.md.
  function _useMock() {
    return !!(global.YOINK_USE_MOCK_API && global.MOCK_API);
  }
  function playlistPreview(url) {
    if (_useMock()) return global.MOCK_API.playlistPreview(url);
    return _postJson("/playlist/preview", { url });
  }
  function playlistStart(url, interval) {
    // Sprint 5: the popup sources interval from the same chrome.storage.sync
    // setting single-video uses (5-300, default 30). Backend defaults to 30
    // if interval is omitted, so this stays compatible with older callers
    // that pass only url.
    const body = (typeof interval === "number" && Number.isFinite(interval))
      ? { url, interval } : { url };
    if (_useMock()) return global.MOCK_API.playlistStart(url, interval);
    return _postJson("/playlist/start", body);
  }
  function jobStatus(jobId) {
    if (_useMock()) return global.MOCK_API.jobStatus(jobId);
    return _getJson(`/jobs/${encodeURIComponent(jobId)}`);
  }
  function jobCancel(jobId) {
    if (_useMock()) return global.MOCK_API.jobCancel(jobId);
    return _postJson(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});
  }
  function jobsList() {
    if (_useMock()) return global.MOCK_API.jobsList();
    return _getJson("/jobs");
  }
  // Settings helpers — originally landed via codex/v2-sprint2 without mock
  // routing. Wrapped here so mock-mode (USE_MOCK_API = true) exercises the
  // Comment Intelligence settings surface without needing the local server.
  // Shapes mirror docs/v2-comment-intelligence.md.
  function getSettings() {
    if (_useMock()) return global.MOCK_API.getSettings();
    return _getJson("/settings");
  }
  function updateSettings(settings) {
    if (_useMock()) return global.MOCK_API.updateSettings(settings || {});
    return _postJson("/settings", settings || {});
  }
  function testAnthropicKey(anthropicKey) {
    if (_useMock()) return global.MOCK_API.testAnthropicKey(anthropicKey);
    const body = {};
    if (typeof anthropicKey === "string") body.anthropic_key = anthropicKey;
    return _postJson("/settings/test-key", body);
  }

  // ---- Smart Screenshot Picker (Sprint 3) ------------------------------
  // getScreenshotThumbnail wraps the authenticated GET /file?path=<abs-path>
  // endpoint Codex shipped on codex/v2-sprint3. Returns a string usable as
  // <img src>: a blob URL in production (created from the response body),
  // a data URL in mock mode. Callers MAY want to URL.revokeObjectURL() the
  // returned blob URL when the thumbnail is no longer needed; for the
  // popup picker we just rely on the popup unload for cleanup.
  async function getScreenshotThumbnail(path) {
    if (_useMock()) return global.MOCK_API.getScreenshotThumbnail(path);
    if (!path || typeof path !== "string") {
      throw new Error("getScreenshotThumbnail: path required");
    }
    const res = await _authedFetch(
      `/file?path=${encodeURIComponent(path)}`,
      { method: "GET" }
    );
    if (!res.ok) {
      // Surface a short, friendly reason. The server's error string is in
      // a JSON body when content-type allows; otherwise just status text.
      let detail = `${res.status}`;
      try {
        const body = await res.json();
        if (body && body.error) detail = body.error;
      } catch { /* binary or empty body */ }
      throw new Error(`thumbnail fetch failed: ${detail}`);
    }
    const ct = res.headers.get("Content-Type") || "";
    if (!/^image\//i.test(ct)) {
      throw new Error(`thumbnail fetch returned non-image content-type: ${ct}`);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }

  // ---- Pending picker stash --------------------------------------------
  // When smart_screenshot_picker_enabled is true, both background.js (queue
  // path) and content.js (in-page-button path) hand the freshly-extracted
  // corpus off to the popup via chrome.storage.local rather than auto-
  // copying. The popup's boot path reads `pending_picker` and renders the
  // picker view. Shared helper so the intercept logic stays in one place.
  //
  // We stash the multimodal paste version (corpus_md_paste) AND the file-
  // reference version (yoink_md) — yoink_md is parsed for absolute
  // screenshot paths (which get sent to /file for thumbnails); the
  // clipboard payload is built from corpus_md_paste so selected screenshots
  // retain their base64-embedded form.
  async function stashPickerCorpus(data) {
    const payload = {
      // yoinked_at marks when the corpus finished extracting (effectively
      // now, since we stash immediately after STC.postExtract resolves).
      // Popup uses this for the picker source-meta relative-time line.
      yoinked_at: new Date().toISOString(),
      title: (data && data.title) || "",
      folder: (data && data.folder) || "",
      corpus_md_paste: (data && data.corpus_md_paste) || "",
      yoink_md: (data && data.yoink_md) || "",
      topic: (data && data.topic) || null,
    };
    return new Promise((resolve) => {
      try {
        chrome.storage.local.set({ pending_picker: payload }, () => resolve(true));
      } catch (e) {
        console.error("[Uoink] stashPickerCorpus failed", e);
        resolve(false);
      }
    });
  }

  function startSession(name) { return _postJson("/session/start", { name: name || "" }); }
  function addToSession(sessionId, url, interval) {
    return _postJson("/session/add", { session_id: sessionId, url, interval });
  }
  function closeSession(sessionId) { return _postJson("/session/close", { session_id: sessionId }); }
  function cancelSession(sessionId) { return _postJson("/session/cancel", { session_id: sessionId }); }
  function listSessions() { return _getJson("/session/list"); }
  function getActiveSession() { return _getJson("/session/active"); }
  function openSession(sessionId) { return _postJson("/session/open", { session_id: sessionId }); }
  function openPromptsFile() { return _getJson("/open-prompts"); }
  function openIndex() { return _getJson("/open-index"); }
  function listRecent() { return _getJson("/recent"); }
  function openFolder(path) {
    return _getJson("/open-folder?path=" + encodeURIComponent(path));
  }

  // ---- Background-proxied versions for content scripts -----------------
  // Page-context fetches from content scripts can be intercepted by Chrome's
  // tracking protection, AV web shields, and similar client-side filters
  // (which produce ERR_BLOCKED_BY_CLIENT even for localhost). Routing through
  // the extension service worker bypasses those filters because the SW's
  // request originates from the extension origin, not the page.
  async function _proxy(type, payload) {
    let res;
    try {
      res = await chrome.runtime.sendMessage({ type, ...payload });
    } catch (e) {
      console.error("[Uoink] background proxy failed", type, e);
      throw new TypeError(`Background SW unreachable: ${e && e.message || e}`);
    }
    if (!res) throw new TypeError("No response from background service worker.");
    if (res.networkError) {
      const err = new TypeError(res.networkError);
      // E7: the SW classified the failure where it was thrown (it still had
      // the AbortError name and could ping /health). Keep that verdict.
      if (res.failure && res.failure.kind) err.uoinkKind = res.failure.kind;
      throw err;
    }
    return res.data;
  }

  function postExtractViaBg(url, interval) {
    return _proxy("stcExtract", { url, interval });
  }
  function postExtractXArticleViaBg(article) {
    return _proxy("stcExtractXArticle", { article });
  }
  function addToSessionViaBg(sessionId, url, interval) {
    return _proxy("stcSessionAdd", { session_id: sessionId, url, interval });
  }

  // Translate raw server errors into copy a non-technical user can act
  // on. By the time this runs the built-in 403-retry has already
  // refreshed the token once and still got rejected, so surfacing
  // "missing or invalid token" verbatim only confuses the user.
  // E4: only a real auth rejection maps to the recovery instruction: an
  // HTTP 403 (when the caller knows the status) or the server's exact
  // token-mismatch body. Matching any "token"/"forbidden" substring turned
  // yt-dlp's "PO token" and "HTTP Error 403: Forbidden" failures into a
  // bogus authorization message.
  // E3: the extension has no details disclosure, so the server's "Details
  // are tucked below." pointer is dropped instead of pointing at nothing.
  const AUTH_REJECTED_ERROR = "missing or invalid token";

  // Capture helpers relay the helper's JSON body; keep its HTTP status with
  // it so describeFailure can tell a rejected token from an ordinary error.
  function withHttpStatus(body, res) {
    if (res && !res.ok && body && typeof body === "object" && body.http_status === undefined) {
      body.http_status = res.status;
    }
    return body;
  }
  function friendlyError(rawMsg, httpStatus) {
    const msg = String(rawMsg || "Uoink hit an unknown error.");
    if (httpStatus === 403 || msg.trim() === AUTH_REJECTED_ERROR) {
      return "Uoink helper authorization changed. Try reloading the extension or restarting the Uoink helper from your Start Menu.";
    }
    return msg.replace(/\s*Details are tucked below\.?/gi, "").trim()
      || "Uoink couldn't finish this one.";
  }

  // E3: one line of the server's raw error_detail: the last yt-dlp
  // "ERROR:" line, else the last line that isn't machine_error_detail's
  // Command:/Exit code: header.
  const DETAIL_EXCERPT_MAX = 180;
  function errorDetailLine(detail) {
    const lines = String(detail || "").split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    let pick = "";
    for (let i = lines.length - 1; i >= 0; i--) {
      if (/^ERROR:/.test(lines[i])) { pick = lines[i]; break; }
    }
    if (!pick) {
      pick = lines.filter((line) => !/^(Command|Exit code):/i.test(line)).pop() || "";
    }
    return pick.replace(/^ERROR:\s*/, "").replace(/\s+/g, " ").trim();
  }

  // The same line, trimmed so it fits a notification.
  function errorDetailExcerpt(detail) {
    const line = errorDetailLine(detail);
    if (line.length <= DETAIL_EXCERPT_MAX) return line;
    return line.slice(0, DETAIL_EXCERPT_MAX - 3).trimEnd() + "...";
  }

  // E3: the user-facing reason for an {ok: false} capture response: the
  // friendly error plus the failing phase and an error_detail excerpt,
  // which every extension surface used to drop.
  function describeFailure(data, httpStatus) {
    const d = data || {};
    // A 403 is an authorization change unless the helper says the page's
    // host just isn't allowlisted (that 403 carries its own wording).
    const status = httpStatus === undefined ? d.http_status : httpStatus;
    const base = friendlyError(d.error,
      status === 403 && d.code !== "host_not_allowed" ? 403 : undefined);
    const phase = String(d.failure_phase || "").replace(/[_-]+/g, " ").trim();
    // A phase error's detail repeats the error itself. Compare the whole
    // line, not the trimmed excerpt, so a long one isn't shown twice.
    const squash = (s) => s.replace(/\s+/g, " ").toLowerCase();
    const line = errorDetailLine(d.error_detail);
    const excerpt = line && !squash(base).includes(squash(line))
      ? errorDetailExcerpt(d.error_detail)
      : "";
    if (phase && excerpt) return `${base} Failed at the ${phase} step: ${excerpt}`;
    if (phase) return `${base} Failed at the ${phase} step.`;
    if (excerpt) return `${base} Detail: ${excerpt}`;
    return base;
  }

  // E7: platform-aware "start the helper" copy (mirrors setup.js
  // helperOfflineDetail). Content scripts can't call getPlatformInfo, so
  // read navigator, which every extension context has.
  function _platform(os) {
    let raw = os;
    if (!raw) {
      try {
        const nav = global.navigator || {};
        raw = (nav.userAgentData && nav.userAgentData.platform)
          || nav.platform || nav.userAgent || "";
      } catch { raw = ""; }
    }
    const value = String(raw || "").toLowerCase();
    if (value.includes("mac") || value === "darwin") return "mac";
    if (value.includes("linux") || value.includes("cros")
        || value.includes("chrome os") || value === "openbsd") return "linux";
    return "win";
  }

  function helperOfflineHint(os) {
    const platform = _platform(os);
    if (platform === "mac") {
      return "Open Uoink from Applications, or run uoink-helper from Terminal, then try again.";
    }
    if (platform === "linux") {
      return "Run uoink-helper from Terminal, then try again.";
    }
    return "Start Uoink from the Start Menu, then try again.";
  }

  // E7: a thrown capture request is not proof the helper is down.
  //   timeout -- our AbortController gave up waiting; the helper may still
  //              be working on it.
  //   lost    -- the SW port / extension context went away mid-request.
  //   network -- the fetch itself failed; a /health ping decides between
  //              offline (ping fails too) and lost (helper is up).
  //   error   -- anything else; show its message.
  const LOST_TRACK_RE = /extension context invalidated|message port closed|receiving end does not exist|could not establish connection|background sw unreachable|no response from background/i;
  function captureErrorKind(e) {
    if (e && typeof e.uoinkKind === "string" && e.uoinkKind) return e.uoinkKind;
    const name = (e && e.name) || "";
    const message = String((e && e.message) || e || "");
    if (name === "AbortError" || name === "TimeoutError") return "timeout";
    // A relayed abort arrives as a plain message ("signal is aborted
    // without reason"); every abort in this file is a request timeout.
    if (/\baborted\b/i.test(message)) return "timeout";
    if (LOST_TRACK_RE.test(message)) return "lost";
    if (name === "TypeError") return "network";
    return "error";
  }

  function captureFailureCopy(kind, e, os) {
    if (kind === "timeout") {
      return {
        kind, title: "Uoink still working", label: "Still working",
        message: "Uoink stopped waiting, but the helper may still be finishing this one. Check Activity in the Uoink dashboard before trying again.",
      };
    }
    if (kind === "lost") {
      return {
        kind, title: "Uoink lost track", label: "Lost track",
        message: "Uoink lost track of this capture. It may still have finished, so check your Library before trying again.",
      };
    }
    if (kind === "offline") {
      return {
        kind, title: "Uoink Helper offline", label: "Uoink Helper offline",
        message: helperOfflineHint(os),
      };
    }
    return {
      kind: "error", title: "Uoink failed", label: "Uoink failed",
      message: `Uoink failed: ${(e && e.message) || e || "unknown error"}`,
    };
  }

  // Returns {kind, title, label, message} for an error thrown by a capture
  // request. options.ping overrides the /health probe; options.os forces a
  // platform. Content scripts rarely reach the ping: the SW classifies
  // network failures before relaying them (see _proxy).
  async function describeCaptureError(e, options) {
    const opts = options || {};
    let kind = captureErrorKind(e);
    if (kind === "network") {
      let health = null;
      try { health = await (opts.ping || ping)(); } catch { health = null; }
      kind = health && health.ok ? "lost" : "offline";
    }
    return captureFailureCopy(kind, e, opts.os);
  }

  // Recent-failure memory shared by the in-page buttons (content.js,
  // content-reddit.js, and content-x-article.js via the SW). The popup's
  // Recent panel renders these rows; newest first, one per URL, five max.
  // replacesId: the record a popup Retry came from; this failure replaces it.
  const RECENT_FAILURES_KEY = "yoink_recent_failures";
  function rememberFailure(url, error, extra, replacesId) {
    const videoId = extractVideoId(url);
    const entry = Object.assign({
      id: `${Date.now()}-${videoId || "video"}`,
      url,
      videoId,
      title: "",
      error,
      failed_at: new Date().toISOString(),
    }, extra || {});
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ [RECENT_FAILURES_KEY]: [] }, (items) => {
          const failures = Array.isArray(items && items[RECENT_FAILURES_KEY])
            ? items[RECENT_FAILURES_KEY]
            : [];
          const kept = failures.filter((f) => f.url !== url
            && !(replacesId && f.id === replacesId));
          const next = [entry].concat(kept).slice(0, 5);
          chrome.storage.local.set({ [RECENT_FAILURES_KEY]: next }, () => resolve());
        });
      } catch { resolve(); }
    });
  }

  // E6: a popup Retry keeps its record until the retried capture has gone
  // through; then the page drops it here. No id, nothing to drop.
  function forgetFailure(id) {
    if (!id) return Promise.resolve();
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ [RECENT_FAILURES_KEY]: [] }, (items) => {
          const failures = Array.isArray(items && items[RECENT_FAILURES_KEY])
            ? items[RECENT_FAILURES_KEY]
            : [];
          const next = failures.filter((f) => !f || f.id !== id);
          if (next.length === failures.length) return resolve();
          chrome.storage.local.set({ [RECENT_FAILURES_KEY]: next }, () => resolve());
        });
      } catch { resolve(); }
    });
  }

  // E1: which helper capture a background.js queue job runs (runExtractJob's
  // branches): "video" (/extract), "any" (/extract/any), "reddit" or "page".
  // A session add isn't a capture: null. The SW matches duplicate popup
  // captures on it, and the popup's button only follows its own route.
  function queueJobRoute(job) {
    if (!job || job.kind !== "extract") return null;
    if (job.usePage) return "page";
    if (job.useExtractAny) return "any";
    if (job.useReddit) return "reddit";
    return "video";
  }

  // E1: the form of a queue job's URL that duplicate matching compares (the
  // SW's sameCapture, the popup's "Uoinking..." button). The context menu
  // queues the tab's raw URL, #fragment and all, while the popup classifies
  // the same tab without it, and the helper drops the fragment anyway
  // (normalizeAnyUrl mirrors it), so https://example.com/post#section and
  // https://example.com/post are one capture.
  function queueUrlKey(url) {
    return normalizeAnyUrl(url) || String(url || "");
  }

  // Shared "uoinked!" notification builder. Called from both the in-page
  // YouTube button success path (content.js) and the SW-driven queue path
  // (background.js) so the first-uoink CTA fires no matter which path the
  // user takes -- previously only the SW path set the flag, and a normal
  // YouTube-button click never got the special copy.
  //
  // Returns the message string to pass to chrome.notifications.create (each
  // caller fires it via its own context-appropriate path). Atomically marks
  // has_completed_first_yoink on the first successful + copied uoink.
  async function buildUoinkedMessage(data, copied) {
    const FIRST_UOINK_MSG =
      "Your first corpus is in your clipboard. Paste in Claude to see what it can do →";
    let firstTime = false;
    try {
      const stored = await new Promise((r) => {
        try {
          chrome.storage.local.get({ has_completed_first_yoink: false }, (i) => r(i));
        } catch { r({ has_completed_first_yoink: false }); }
      });
      firstTime = !stored.has_completed_first_yoink;
      if (firstTime && copied) {
        await new Promise((r) => {
          try {
            chrome.storage.local.set({ has_completed_first_yoink: true }, () => r());
          } catch { r(); }
        });
      }
    } catch { /* fall through to topic-aware copy */ }

    if (firstTime && copied) return FIRST_UOINK_MSG;

    // Topic-aware default copy (subsequent uoinks).
    const realTopic = data && data.topic && data.topic !== "Uncategorized" ? data.topic : null;
    const topicLine = realTopic ? `Saved to: ${realTopic}. ` : "";
    const tail = "Comments and any enabled AI analyses will arrive shortly in the saved corpus file.";
    if (copied) {
      return `${topicLine}Paste with Ctrl+V in Claude or ChatGPT. ${tail}`.trim();
    }
    return `${topicLine}Clipboard was blocked. Open the saved file in the uoink folder.`.trim();
  }

  async function logEngagement(eventType, source, metadata) {
    const payload = {
      event_type: eventType,
      source: source || "unknown",
      timestamp: new Date().toISOString(),
      metadata: metadata || {}
    };
    try {
      const res = await _authedFetch("/engagement/log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.status === 200 || res.status === 201 || res.ok) {
        return { ok: true };
      }
      throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      console.warn("[Uoink] Engagement log failed, buffering locally:", e);
      await _bufferEngagementEvent(payload);
      return { ok: false, buffered: true };
    }
  }

  function _bufferEngagementEvent(payload) {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ uoink_engagement_pending: [] }, (items) => {
          const pending = Array.isArray(items.uoink_engagement_pending) ? items.uoink_engagement_pending : [];
          pending.push(payload);
          chrome.storage.local.set({ uoink_engagement_pending: pending }, () => resolve());
        });
      } catch (err) {
        console.error("[Uoink] Failed to buffer event:", err);
        resolve();
      }
    });
  }

  async function replayPendingEngagementEvents() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get({ uoink_engagement_pending: [] }, async (items) => {
          const pending = Array.isArray(items.uoink_engagement_pending) ? items.uoink_engagement_pending : [];
          if (pending.length === 0) {
            resolve();
            return;
          }
          const remaining = [];
          for (const payload of pending) {
            try {
              const res = await _authedFetch("/engagement/log", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
              });
              if (res.status === 200 || res.status === 201 || res.ok) {
                continue;
              }
              remaining.push(payload);
            } catch (err) {
              remaining.push(payload);
            }
          }
          chrome.storage.local.set({ uoink_engagement_pending: remaining }, () => resolve());
        });
      } catch (err) {
        console.error("[Uoink] Failed to replay events:", err);
        resolve();
      }
    });
  }

  function getResurfaceToday() {
    return _getJson("/resurface/today");
  }

  function getEngagementScores() {
    return _getJson("/engagement/scores");
  }

  function memorySearch(params) {
    let query = "";
    if (params) {
      const parts = [];
      for (const [k, v] of Object.entries(params)) {
        parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
      }
      if (parts.length) query = "?" + parts.join("&");
    }
    return _getJson("/memory/search" + query);
  }

  function normalizeRedditUrl(rawUrl) {
    if (!rawUrl) return null;
    let u;
    try { u = new URL(rawUrl); }
    catch { return null; }

    const host = u.hostname.replace(/^www\.|^old\.|^new\.|^np\./, "").toLowerCase();
    if (host !== "reddit.com") return null;

    // Pattern: /r/<subreddit>/comments/<id>/<slug>/
    const match = u.pathname.match(/^\/r\/([^/]+)\/comments\/([^/]+)/);
    if (!match) return null;

    const subreddit = match[1];
    const id = match[2];
    
    // Canonicalize to www.reddit.com/r/<sub>/comments/<id>/
    return `https://www.reddit.com/r/${subreddit}/comments/${id}/`;
  }

  // ---- Client-side capture classifier (V-2a parity, no /detect) --------
  // The dashboard's universal paste box classifies server-side via
  // _classify_capture_url -> GET /detect. /detect is NOT in the shipped
  // helper build, so the popup classifies the ACTIVE TAB here instead,
  // reusing the same normalizers so the popup can never disagree with what
  // the capture route will actually accept. Precedence mirrors the server:
  // a watch URL that also carries a list= param is a VIDEO (the user is
  // watching), so video is checked before playlist.
  const _PLAYLIST_ID_RE = /^[A-Za-z0-9_-]{2,}$/;

  function normalizePlaylistUrl(raw) {
    if (!raw || typeof raw !== "string") return null;
    let u;
    try { u = new URL(raw.includes("://") ? raw : "https://" + raw); }
    catch { return null; }
    const host = (u.hostname || "").toLowerCase();
    if (!["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host)) {
      return null;
    }
    const listId = u.searchParams.get("list") || "";
    if (!listId || !_PLAYLIST_ID_RE.test(listId)) return null;
    // Drop the video position: Playlist Mode always starts from the first
    // entry after the cap. Only accept playlist-shaped paths.
    if (!["", "/", "/playlist", "/watch"].includes(u.pathname)) return null;
    return `https://www.youtube.com/playlist?list=${listId}`;
  }

  // Shape-only signal that a URL is a podcast/RSS feed. Feeds are just
  // http(s) URLs, so we only claim "podcast feed" when the URL clearly
  // looks like one; everything else falls through to the generic web-page
  // path. Mirrors server _looks_like_feed_url so the chip stays honest.
  const _FEED_URL_HINT_RE =
    /(\.(rss|xml)$|\/(feed|feeds|rss|podcast|podcasts)(\/|$)|[?&]format=(rss|xml))/i;

  function looksLikeFeedUrl(raw) {
    if (!raw || typeof raw !== "string") return false;
    let u;
    try { u = new URL(raw.includes("://") ? raw : "https://" + raw); }
    catch { return false; }
    if (u.protocol !== "http:" && u.protocol !== "https:") return false;
    const host = (u.hostname || "").toLowerCase();
    if (host.startsWith("feeds.") || host.startsWith("feed.")) return true;
    const probe = u.search ? `${u.pathname}${u.search}` : u.pathname;
    return _FEED_URL_HINT_RE.test(probe);
  }

  // Generic http(s) validator + canonicalizer. Mirrors the generic branch
  // of server _normalize_any_url: rejects dangerous schemes and non-DNS
  // hostnames, then returns scheme://host[:port]/path?query (no fragment).
  const _GENERIC_HOST_RE = /^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$/;
  const _BAD_SCHEMES = [
    "javascript:", "data:", "vbscript:", "file:", "ftp:", "mailto:", "blob:",
  ];

  function normalizeAnyUrl(raw) {
    if (!raw || typeof raw !== "string") return null;
    raw = raw.trim();
    if (!raw) return null;
    const lower = raw.toLowerCase();
    for (const bad of _BAD_SCHEMES) {
      if (lower.startsWith(bad)) return null;
    }
    const withScheme = raw.includes("://") ? raw : "https://" + raw;
    let u;
    try { u = new URL(withScheme); } catch { return null; }
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const host = u.hostname || "";
    if (!host || host.length > 253) return null;
    if (!_GENERIC_HOST_RE.test(host)) return null;
    let netloc = host.toLowerCase();
    if (u.port) netloc = `${netloc}:${u.port}`;
    const query = u.search || "";
    return `${u.protocol}//${netloc}${u.pathname}${query}`;
  }

  // Per-source routing metadata. `action` is the popup dispatch key;
  // `endpoint` documents the capture route each source actually hits.
  const CAPTURE_SOURCES = {
    youtube_video: {
      label: "video", endpoint: "/extract", action: "video", note: "",
    },
    youtube_playlist: {
      label: "playlist", endpoint: "/playlist/start", action: "playlist",
      note: "Captures every video in the playlist, up to the cap.",
    },
    short_video: {
      label: "short video", endpoint: "/extract", action: "video",
      note: "Captures the clip, its caption, and a transcript when the "
        + "platform provides one.",
    },
    x_video: {
      label: "post", endpoint: "/extract", action: "x_video",
      note: "Captures the post text and the author's thread -- plus the "
        + "video if the post has one.",
    },
    x_article: {
      label: "article", endpoint: "/extract/x-article", action: "x_article",
      note: "Reads X's long-form article out of the page you're logged into. "
        + "If that can't be read, Uoink falls back to fetching the page.",
    },
    reddit_thread: {
      label: "thread", endpoint: "/extract/reddit", action: "reddit", note: "",
    },
    podcast_feed: {
      label: "podcast", endpoint: "/podcasts/feeds", action: "podcast",
      note: "Adds the RSS feed and watches new episode metadata. Audio stays off by default.",
    },
    web_page: {
      label: "page", endpoint: "/extract/page", action: "page", note: "",
    },
  };

  function _classifyResult(source, canonical) {
    const spec = CAPTURE_SOURCES[source];
    return {
      ok: true,
      source,
      label: spec.label,
      endpoint: spec.endpoint,
      action: spec.action,
      canonical,
      note: spec.note,
    };
  }

  // Classify a single URL into exactly one capture source. Returns
  // {ok, source, label, endpoint, action, canonical, note}. ok is false
  // ("unsupported" / "empty") when nothing accepts it.
  function classifyCaptureUrl(raw) {
    const text = (raw || "").trim();
    if (!text) {
      return {
        ok: false, source: "empty", label: "", endpoint: null,
        action: null, canonical: "", note: "",
      };
    }
    // Short-form video (TikTok / Instagram Reel / YouTube Short) before the
    // plain YouTube branch so a /shorts/ link reads as a short. A regular
    // watch URL returns null here, so youtube_video still wins for it.
    const sv = normalizeShortVideoUrl(text);
    if (sv) return _classifyResult("short_video", sv);
    const yt = normalizeYouTubeUrl(text);
    if (yt) return _classifyResult("youtube_video", yt);
    const pl = normalizePlaylistUrl(text);
    if (pl) return _classifyResult("youtube_playlist", pl);
    const xa = normalizeXArticleUrl(text);
    if (xa) return _classifyResult("x_article", xa);
    const tw = normalizeTwitterUrl(text);
    if (tw) return _classifyResult("x_video", tw);
    const rd = normalizeRedditUrl(text);
    if (rd) return _classifyResult("reddit_thread", rd);
    if (looksLikeFeedUrl(text)) {
      return _classifyResult("podcast_feed", normalizeAnyUrl(text) || text);
    }
    const generic = normalizeAnyUrl(text);
    if (generic) return _classifyResult("web_page", generic);
    return {
      ok: false, source: "unsupported", label: "", endpoint: null,
      action: null, canonical: text,
      note: "Uoink can't read this link yet. YouTube, X, Reddit threads, "
        + "podcasts, and most web pages work.",
    };
  }

  // A1: resolve what the ACTIVE TAB is, letting a live-DOM signal win over
  // URL-shape guessing. classifyCaptureUrl alone mislabels an X Article that
  // was reached via its announcing /status/ tweet, a t.co redirect, or an SPA
  // route the address bar hasn't settled — all classify as x_video or
  // web_page and fall to "Uoink this page". When the popup probes the tab and
  // finds a rendered Article body (opts.hasArticleDom), we route to the
  // article path regardless of the URL shape, so an actual article never
  // silently degrades. The canonical URL is the clean /article/ form when the
  // URL already carries it, else the tab URL (the reliable capture is the
  // in-page DOM parse, which reads location.href itself; this URL is only the
  // /extract/page fallback target).
  function resolveTabSource(rawUrl, opts) {
    const options = opts || {};
    const cls = classifyCaptureUrl(rawUrl);
    if (options.hasArticleDom && cls.source !== "x_article") {
      const canonical = normalizeXArticleUrl(rawUrl)
        || (cls && cls.canonical) || (rawUrl || "").trim();
      return _classifyResult("x_article", canonical);
    }
    return cls;
  }

  // ---- Article / web-page capture (P1) ---------------------------------
  async function postExtractPage(url) {
    const res = await _authedFetch("/extract/page", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const text = await res.text();
    if (!res.ok && res.status !== 403) {
      console.error("[Uoink] HTTP", res.status, "body:", text);
    }
    try {
      return withHttpStatus(JSON.parse(text), res);
    } catch {
      return withHttpStatus({ ok: false, error: "Server returned a non-JSON response." }, res);
    }
  }

  // One-click allowlist grant: POST /extract/page/allowlist {action:'add'}.
  // The server matches a bare hostname pattern against the host AND its
  // subdomains, so passing the tab's hostname is enough.
  async function addAllowedSite(urlPattern) {
    const res = await _authedFetch("/extract/page/allowlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "add", url_pattern: urlPattern }),
    });
    return await res.json().catch(() => ({
      ok: false, error: "Server returned a non-JSON response.",
    }));
  }

  // ---- Podcast feed subscribe (P1) -------------------------------------
  async function postPodcastFeed(feedUrl) {
    const res = await _authedFetch("/podcasts/feeds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feed_url: feedUrl }),
    });
    return await res.json().catch(() => ({
      ok: false, error: "Server returned a non-JSON response.",
    }));
  }

  async function postExtractReddit(url, interval) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const targetUrl = `${SERVER}/extract/reddit`;
    const requestBody = { url, interval };
    try {
      let res;
      try {
        res = await _authedFetch("/extract/reddit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
          signal: controller.signal,
        });
      } catch (e) {
        if (e instanceof TypeError) {
          console.error("[Uoink] server unreachable at", targetUrl, e);
        } else {
          console.error("[Uoink] fetch aborted/failed", targetUrl, e);
        }
        throw e;
      }

      const text = await res.text();
      if (!res.ok) {
        console.error("[Uoink] HTTP", res.status, "body:", text);
      }
      try {
        return withHttpStatus(JSON.parse(text), res);
      } catch {
        console.error("[Uoink] JSON parse error, raw text:", text);
        return withHttpStatus({ ok: false, error: "Server returned a non-JSON response." }, res);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  global.STC = {
    SERVER,
    DEFAULT_INTERVAL,
    REQUEST_TIMEOUT_MS,
    extractVideoId,
    normalizeYouTubeUrl,
    normalizeTwitterUrl,
    normalizeXArticleUrl,
    isXArticleUrl,
    normalizeRedditUrl,
    normalizePlaylistUrl,
    normalizeTikTokUrl,
    normalizeInstagramUrl,
    isYouTubeShortUrl,
    normalizeShortVideoUrl,
    looksLikeFeedUrl,
    normalizeAnyUrl,
    classifyCaptureUrl,
    resolveTabSource,
    CAPTURE_SOURCES,
    getInterval,
    postExtract,
    postExtractAny,
    postExtractX,
    postExtractXArticle,
    postExtractXArticleViaBg,
    postExtractReddit,
    postExtractPage,
    addAllowedSite,
    postPodcastFeed,
    ping,
    startSession,
    addToSession,
    closeSession,
    cancelSession,
    listSessions,
    getActiveSession,
    openSession,
    postExtractViaBg,
    addToSessionViaBg,
    openPromptsFile,
    openIndex,
    listRecent,
    openFolder,
    buildUoinkedMessage,
    buildYoinkedMessage: buildUoinkedMessage,
    getToken,
    friendlyError,
    errorDetailExcerpt,
    describeFailure,
    helperOfflineHint,
    captureErrorKind,
    describeCaptureError,
    rememberFailure,
    forgetFailure,
    queueJobRoute,
    queueUrlKey,
    playlistPreview,
    playlistStart,
    jobStatus,
    jobCancel,
    jobsList,
    getSettings,
    updateSettings,
    testAnthropicKey,
    getScreenshotThumbnail,
    stashPickerCorpus,
    logEngagement,
    replayPendingEngagementEvents,
    getResurfaceToday,
    getEngagementScores,
    memorySearch,
  };
})(typeof self !== "undefined" ? self : globalThis);
