# Tier 2 (v2.2) — cross-agent contracts (owned by CC)

Status: **DRAFT / WIP** — CC owns these surfaces (helper backend + pywebview shells + wizard). Codex (dashboard UI, splash HTML, `uoink-card`/`uoink-running-pill`) and AG (extension popup) consume them. This is the source of truth; CC updates it as the helper code lands. A copy lives at `uoink-handoff/TIER-2-CONTRACTS-FROM-CC.md`.

Base: branched off `main @ ca674b7` (already includes v2.1.1 + Tier 1 install: tray, wizard bitmaps, `[Code]` migrating page). Tier 2 **extends** those files, does not duplicate them.

All endpoints are on the existing loopback helper `http://127.0.0.1:5179`. Auth is the existing `X-Uoink-Token` header (token in `%LOCALAPPDATA%\Uoink\token.txt`, fetched via `GET /token`) **except** the public `GET /diagnose`, `/health`, `/splash`.

---

## 1. `/jobs/stream` SSE event stream  ← Activity tab + popup queue both consume  **[IMPLEMENTED]**

**Endpoint:** `GET /jobs/stream` → `Content-Type: text/event-stream`.

**Auth — header, NOT a query param.** The stream is gated by the usual `X-Uoink-Token` header. `EventSource` can't set headers, and the helper **deliberately removed** `?token=` support (it leaks the token into browser history / access logs — see `_request_token` in `server.py`). So **consume with `fetch()` + a `ReadableStream` reader, not `EventSource`:**
```js
const { token } = await (await fetch("/token", {headers:{"X-Uoink-Client":"uoink-extension"}})).json();
const res = await fetch("/jobs/stream", {headers:{"X-Uoink-Token": token}});
const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
for (;;) {
  const {value, done} = await reader.read(); if (done) break;
  buf += dec.decode(value, {stream:true});
  let i; while ((i = buf.indexOf("\n\n")) >= 0) {
    const frame = buf.slice(0, i); buf = buf.slice(i + 2);
    if (frame.startsWith(":")) continue;            // heartbeat comment
    const ev = /^event: (.*)$/m.exec(frame)?.[1];
    const data = /^data: (.*)$/m.exec(frame)?.[1];
    if (ev && data) handle(ev, JSON.parse(data));    // ev: snapshot|job|queue
  }
}
```
Same-origin (helper-served dashboard) needs no preflight; the extension origin uses the existing CORS allowlist that already permits `X-Uoink-Token`. Streams are capped at 8 concurrent (→ `503`).

**Connect behavior:** one `snapshot` on connect, then `job` / `queue` deltas (server polls job/queue state every 1 s and emits only changes), plus a `: heartbeat` comment every 15 s. One thread per connection; reaped on client disconnect.

### Event types
| `event:` | when | `data` (JSON) |
|---|---|---|
| `snapshot` | once, on connect | `{ "active": [Job], "recent": [Job], "queue": Queue }` |
| `job` | a job's public record changed | `Job` |
| `queue` | rate-limit queue counts changed | `Queue` |
| (comment) | every 15 s | `: heartbeat` |

`active` = jobs whose `state` is non-terminal; `recent` = up to 10 most-recent terminal jobs.

### `Job` payload — **identical to `GET /jobs` (`_public_job`)**, single source of truth:
```json
{
  "id": "job_a",
  "kind": "single",                     // "single" | "playlist"
  "state": "running",                   // idle | queued | running | completed | cancelled | failed
  "source_url": "https://youtu.be/abc",
  "title": "Karpathy LLMs",
  "playlist_title": null,
  "session_folder": null,
  "videos_total": 1, "videos_done": 0, "videos_failed": 0,
  "current_video": null,
  "current_video_phase": "transcribe",  // free-form phase label -> the phase chip
  "started_at": "2026-05-27T10:15:03Z",
  "updated_at": "2026-05-27T10:15:21Z",
  "completed_at": null,
  "error": null,
  "result": null,
  "warnings": [],
  "message": null
}
```
Phase chips read `current_video_phase` (single jobs) and `videos_done`/`videos_total` (playlists). A terminal `state` (`failed`) with `error` set is a failure row.

### `Queue` payload — mirrors `GET /queue/status` counts:
```json
{ "pending": 2, "running": 1, "failed": 0, "succeeded": 5, "cancelled": 0,
  "next_retry_at": "2026-05-27T10:18:00Z" }
```

**Consumers:** Codex's Activity tab + AG's popup queue each open ONE fetch-stream. Existing `GET /jobs`, `GET /queue/status` stay for non-streaming reads / fallback.

> **Reconciliation vs PR #8:** Codex's assumed schema used `status` / `phase`. The authoritative shape is `state` / `current_video_phase` (it matches the live `/jobs` endpoint, so dashboard + stream are one shape). Converge in review.

---

## 2. New / extended helper endpoints (CC builds)

Build order (each lands as its own commit): `/jobs/stream` ✅ → `/update/check` → `/settings`(extended) + `/settings/mcp-config` → `/helper/quit` + `/open-last-youtube` → `/splash`.

### Settings — `GET /settings` (extended)
```json
{
  "anthropic_key_set": true,
  "anthropic_key_masked": "sk-ant-…a1b2",
  "output_dir": "C:\\Users\\hello\\Desktop\\Uoink",
  "autostart": true,
  "screenshot_count": 4,
  "topics": [{"name":"AI and ML","keywords":["llm","agent","claude"]}],
  "pricing": { "...": "existing /settings/pricing shape" }
}
```
### `POST /settings` (partial; any subset)
```json
{ "anthropic_key":"sk-ant-…", "output_dir":"D:\\Uoink", "autostart":false,
  "screenshot_count":8, "topics":[{"name":"…","keywords":["…"]}] }
```
Key → Credential Manager (never echoed unmasked); `output_dir` validated writable; `autostart` toggles `HKCU\…\Run\Uoink` (reuses the migrate_install Run-key helpers). Returns the updated `GET /settings`. Existing `POST /settings/test-key` unchanged.

### `GET /settings/mcp-config` — MCP snippet (Copy button)
`{ "claude_desktop": {…}, "cursor": {…}, "raw": "<json string>" }` — paste-ready `mcpServers` config pointing at `uoink_mcp.py` under `{app}`.

### `GET /update/check` — notify-only
```json
{ "current":"2.2.0", "latest":"2.2.1", "update_available":true,
  "url":"https://github.com/ryanbiddy/uoink/releases/tag/v2.2.1",
  "published_at":"2026-06-01T00:00:00Z", "checked_at":"2026-06-02T09:00:00Z", "cached":true }
```
Polls GitHub `releases/latest`, cached ≥24 h. **Never downloads / self-updates.** Offline → `{ "update_available": false, "error": "offline" }` (silent in UI).

### `POST /helper/quit` — graceful stop (dashboard "Stop helper" + tray Quit)
Token-gated. Responds `{ "ok": true }`, then shuts the server down (worker-thread `server.shutdown()`; PID cleared via atexit). Expect the connection to drop right after the 200.

### `GET /open-last-youtube` — "Open last YouTube tab" CTA
Token-gated. Win32 `EnumWindows` + title heuristic to focus an existing "… - YouTube …" window; else opens `https://www.youtube.com`. Returns `{ "ok":true, "action":"focused_existing"|"opened_new", "url":"…" }`. (Replaces the dropped ⌘V empty-state idea, plan §5.) macOS: later stub.

### `GET /splash` — splash page (public)
Serves Codex-authored splash HTML from `assets/splash/` (CC adds route + staging; Codex authors HTML/CSS). Splash JS calls `GET /diagnose` to pick success vs failure (port-conflict) and `window.pywebview.api.*` for window control (§3).

---

## 3. pywebview ⇄ helper IPC (dashboard + splash windows)

Chromeless pywebview windows load helper-served HTTP pages (`/dashboard`, `/splash`). Page→data is plain `fetch()` — **no special IPC for data**. The only native bridge is window control, exposed by CC as a pywebview `js_api`:
```js
window.pywebview.api.minimize()        // splash: minimize to tray
window.pywebview.api.close()           // close this window
window.pywebview.api.open_dashboard()  // open/focus the main dashboard window
window.pywebview.api.open_url(url)     // open a URL in the default browser
```
**Feature-detect (Codex must follow):** the same HTML also loads in a plain browser tab where `window.pywebview` is undefined:
```js
const native = window.pywebview?.api;
const openExternal = u => native ? native.open_url(u) : window.open(u, "_blank");
```
Splash slide-up + 8 s linger are owned by CC's pywebview wrapper (native geometry), not the HTML; clicking the splash calls `native?.open_dashboard()`. **Sentinel:** CC writes `%LOCALAPPDATA%\Uoink\.first-run-done` after the splash shows once.

---

## 4. Brand tokens
Single source of truth = Codex's `assets/brand/tokens.css` (do not fork). New: `--ink-warm #15110D`, `--border #2C2621`, `--muted #C8B19F`, `--dim #8F7B6E`, `--ok #00C853` (dot only; `#0F8F3F` for ok-as-type-on-cream). Contrast rule stands: **no `--rust #C2410C` text on `--ink`** — use `--rust-bright #F97316` for body on dark.

## 5. Open items CC is resolving (plan §5)
1. Tray 16 px glyph → hand-baked cream-tip PNG (size-aware rule).
2. Activity vs popup queue → both on `/jobs/stream` (§1). ✅ defined
3. ⌘V empty-state → dropped; passive tip instead (Codex owns copy).
4. Migration failure (locked `index.db`, old Yoink helper running) → "Close Yoink first" interstitial in the Migrating page; check before copy.
5. "Open last YouTube tab" → `GET /open-last-youtube` (§2).
