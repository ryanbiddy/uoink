# Tier 2 (v2.2) — cross-agent contracts (owned by CC)

Status: **DRAFT / WIP** — CC owns these surfaces (helper backend + pywebview shells + wizard). Codex (dashboard UI, splash HTML, `uoink-card`/`uoink-running-pill`) and AG (extension popup) consume them. This is the source of truth; CC updates it as the helper code lands. A copy lives at `uoink-handoff/TIER-2-CONTRACTS-FROM-CC.md` for agents who read the handoff folder.

Base: branched off `main @ ca674b7` (already includes v2.1.1 + Tier 1 install: tray, wizard bitmaps, `[Code]` migrating page). Tier 2 **extends** those files, does not duplicate them.

All endpoints are on the existing loopback helper `http://127.0.0.1:5179`. Auth is the existing `X-Uoink-Token` header (token in `%LOCALAPPDATA%\Uoink\token.txt`, fetched by the page via `GET /token`) **except** where noted (`/diagnose`, `/health`, `/splash` are public; SSE uses a query-param token — see §1).

---

## 1. `/jobs` SSE event stream  ← Activity tab + popup queue both consume

**New endpoint:** `GET /jobs/stream` → `Content-Type: text/event-stream`.

**Auth (important):** `EventSource` cannot set custom headers, so the stream takes the token as a **query param**: `GET /jobs/stream?token=<token>`. Same-origin only; rejects cross-origin `Origin`. (The existing `/mcp/v1/sse` is MCP-shaped; we add a dedicated job stream rather than overload it.)

**Connect behavior:** on connect the server emits one `snapshot` event with the full current state, then incremental events. A `: heartbeat` comment is sent every 15 s to keep the connection alive through proxies/sleep.

### Event types

| `event:` | when | `data` (JSON) |
|---|---|---|
| `snapshot` | once, on connect | `{ "active": [Job], "recent": [Job], "queue": Queue }` |
| `job` | a job changes phase/status | `Job` |
| `queue` | rate-limit queue counts change | `Queue` |
| (comment) | every 15 s | `: heartbeat` |

### `Job` payload
```json
{
  "id": "job_7xTGNNLPyMI_1716800103",
  "video_id": "7xTGNNLPyMI",
  "url": "https://www.youtube.com/watch?v=7xTGNNLPyMI",
  "title": "Deep Dive into LLMs like ChatGPT",
  "channel": "Andrej Karpathy",
  "status": "running",
  "phase": "transcribe",
  "phases_done": ["fetch"],
  "progress": 0.42,
  "started_at": "2026-05-27T10:15:03Z",
  "updated_at": "2026-05-27T10:15:21Z",
  "error": null
}
```
- `status` ∈ `queued | running | done | error | canceled`
- `phase` ∈ `fetch | transcribe | screenshots | classify | write | done` (drives the Activity phase chips: fetch → transcribe → screenshots → classify → write)
- `progress` is 0..1 for the current phase (null if indeterminate)
- `error` is null unless `status:"error"`, then a short human string + `error_code` (`rate_limited | needs_cookies | network | ytdlp | unknown`)

### Phase-transition examples (sequential `job` events for one yoink)
```
event: job
data: {"id":"job_x","video_id":"7xTG","status":"running","phase":"fetch","phases_done":[],"progress":null,...}

event: job
data: {"id":"job_x","status":"running","phase":"transcribe","phases_done":["fetch"],"progress":0.4,...}

event: job
data: {"id":"job_x","status":"running","phase":"screenshots","phases_done":["fetch","transcribe"],"progress":0.7,...}

event: job
data: {"id":"job_x","status":"running","phase":"classify","phases_done":["fetch","transcribe","screenshots"],...}

event: job
data: {"id":"job_x","status":"done","phase":"done","phases_done":["fetch","transcribe","screenshots","classify","write"],"progress":1.0,...}
```
Failure example:
```
event: job
data: {"id":"job_x","status":"error","phase":"transcribe","error":"YouTube asked for sign-in; retry with cookies","error_code":"needs_cookies",...}
```

### `Queue` payload (mirrors existing `/queue/status`)
```json
{ "pending": 2, "running": 1, "retry_after": "2026-05-27T10:18:00Z", "completed_today": 14 }
```

**Consumers:** Codex's Activity tab and AG's popup queue both open one `EventSource("/jobs/stream?token=…")`. Single source of truth — no polling. Existing `GET /jobs`, `/queue/status` remain for non-streaming reads / fallback.

---

## 2. New / extended helper endpoints (CC builds)

### Settings — `GET /settings` (extended)
```json
{
  "anthropic_key_set": true,
  "anthropic_key_masked": "sk-ant-…a1b2",
  "output_dir": "C:\\Users\\hello\\Desktop\\Uoink",
  "autostart": true,
  "screenshot_count": 4,
  "topics": [{"name":"AI and ML","keywords":["llm","agent","claude"]}, ...],
  "pricing": { ... existing /settings/pricing shape ... }
}
```
### `POST /settings` (partial update; any subset)
```json
{ "anthropic_key": "sk-ant-…", "output_dir": "D:\\Uoink", "autostart": false, "screenshot_count": 8,
  "topics": [{"name":"...","keywords":["..."]}] }
```
- Key is written to Credential Manager (never echoed back unmasked). `output_dir` validated writable. `autostart` toggles the `HKCU\…\Run\Uoink` value (reuses the migrate_install Run-key helpers). Returns the updated `GET /settings` body.
- Existing `POST /settings/test-key` unchanged (Test/Replace button).

### `GET /settings/mcp-config` — MCP snippet generator (Copy button)
Returns `{ "claude_desktop": {…}, "cursor": {…}, "raw": "<json string>" }` — ready-to-paste `mcpServers` config pointing at `uoink_mcp.py` under `{app}`.

### `GET /update/check` — notify-only update check
```json
{ "current": "2.2.0", "latest": "2.2.1", "update_available": true,
  "url": "https://github.com/ryanbiddy/uoink/releases/tag/v2.2.1",
  "published_at": "2026-06-01T00:00:00Z", "checked_at": "2026-06-02T09:00:00Z", "cached": true }
```
- Polls GitHub `releases/latest`, result cached ≥24 h on disk (monthly user-visible cadence). **Never downloads or self-updates** — links out only. Network failure → `{ "update_available": false, "error": "offline" }` (silent in UI).

### `POST /helper/quit` — graceful stop (dashboard "Stop helper" + tray Quit)
Token-gated. Responds `{ "ok": true }` then shuts the server down (`server.shutdown()` on a worker thread; PID file cleared via the existing atexit hook). The dashboard/tray should expect the connection to drop right after the 200.

### `GET /open-last-youtube` — "Open last YouTube tab" (Finished + Splash CTA)
Token-gated. Enumerates top-level Chromium windows (Win32 `EnumWindows` + window title heuristic for "… - YouTube …") to focus an existing YouTube tab; if none found, opens `https://www.youtube.com` in the default browser. Returns `{ "ok": true, "action": "focused_existing" | "opened_new", "url": "…" }`. Replaces the dropped "⌘V paste URL" empty-state idea (per plan §5). macOS path is a later stub.

### `GET /splash` — splash page (public)
Serves Codex-authored splash HTML from `assets/splash/` (CC adds the route + staging; Codex authors the HTML/CSS). The splash JS calls `GET /diagnose` to choose the success vs. failure (port-conflict) variant, and `window.pywebview.api.*` for window control (§3).

---

## 3. pywebview ⇄ helper IPC (dashboard + splash windows)

The dashboard and splash are **chromeless pywebview windows that load helper-served HTTP pages** (`/dashboard`, `/splash`). Page→data is plain `fetch()` against the API above — **no special IPC for data**. The only native bridge is window control, exposed by CC as a pywebview `js_api`:

```js
// available as window.pywebview.api.* inside the pywebview windows
window.pywebview.api.minimize()        // splash: minimize to tray
window.pywebview.api.close()           // close this window
window.pywebview.api.open_dashboard()  // open/focus the main dashboard window
window.pywebview.api.open_url(url)     // open a URL in the user's default browser (external links)
```

**Feature-detection contract (Codex must follow):** the same HTML is also reachable in a plain browser tab (Tier 1 / fallback), where `window.pywebview` is **undefined**. Codex's JS must guard:
```js
const native = window.pywebview?.api;
function openExternal(u){ native ? native.open_url(u) : window.open(u, "_blank"); }
```
Splash auto-dismiss (8 s linger) + slide-up animation are owned by CC's pywebview wrapper (native window geometry/animation), **not** the HTML — the splash HTML is static; clicking anywhere calls `native?.open_dashboard()`.

**Sentinel:** CC writes `%LOCALAPPDATA%\Uoink\.first-run-done` after the splash shows once; subsequent boots skip the splash (tray only).

---

## 4. Brand tokens
Single source of truth is Codex's `assets/brand/tokens.css` (do not fork). CC's wizard bitmaps + any CC-rendered HTML pull from it. New tokens: `--ink-warm #15110D`, `--border #2C2621`, `--muted #C8B19F`, `--dim #8F7B6E`, `--ok #00C853` (dot only; `#0F8F3F` for ok-as-type-on-cream). Contrast rule stands: **no `--rust #C2410C` text on `--ink`** — use `--rust-bright #F97316` for body on dark.

## 5. Open items CC is resolving (plan §5)
1. Tray 16 px glyph → hand-baked cream-tip PNG (size-aware rule; simpler than ResizeObserver in a tray bitmap).
2. Activity vs popup queue → both on `/jobs/stream` (§1).
3. ⌘V empty-state line → dropped; replaced by passive tip (Codex owns the copy).
4. Migration failure (locked `index.db` because old Yoink helper running) → CC adds a "Close Yoink first" interstitial in the Migrating page; checks before copy.
5. "Open last YouTube tab" → `GET /open-last-youtube` (§2).
