# Surface map: helper HTTP API (v3.2.6 additions)

Covers the two routes added by U-01. This file grows as PRs touch backend
routes; UI surfaces get their own maps in this folder.

The helper is the stdlib-only HTTP server in `server.py`, bound to
`127.0.0.1:5179`. Routes are dispatched by exact path match inside
`Handler.do_GET`. Two auth postures exist:

- **Public**: dispatched before the token gate. For liveness probes, UI
  shells, and product metadata that contains no user data.
- **Token-gated**: dispatched after `_require_token()`. The caller must send
  `X-Uoink-Token: <token>` (the dashboard gets it from the `/token`
  handshake). Missing or wrong token answers `403 {"ok": false}`.

---

## GET /open-extension (token-gated)

**What it does.** Pops the OS file manager with the bundled browser-extension
folder selected, so a user following the "get the extension" card can point
`chrome://extensions` > "Load unpacked" at a folder they can see. On Windows
this runs `explorer /select,<path>`; macOS `open -R`; Linux opens the parent
folder (no portable select affordance).

**Why it exists.** UX-07: the dashboard had zero install path for the
extension. The extension ships on disk at `<install dir>/extension`
(`%LOCALAPPDATA%\Uoink\extension` on an installed copy), and this route is
the only sanctioned way to reveal it. The sandboxed `/open-folder` route
cannot do this job: it rejects any path outside the output root
(`DESKTOP_ROOT`), and the install dir lives outside it by design. The
pattern here follows `/open-prompts` instead (unsandboxed reveal of a known
file inside the install dir, never a caller-supplied path).

**Request.** No parameters. Query string ignored.

**Responses.** Always JSON. Failures still answer HTTP 200 so the dashboard
can render the error copy without an exception path (same contract as
`/open-prompts` and `/open-folder`):

| Case | Status | Body |
|---|---|---|
| Revealed | 200 | `{"ok": true, "path": "<absolute extension dir>"}` |
| Folder missing on disk | 200 | `{"ok": false, "error": "extension folder not found at <path>"}` |
| File manager launch failed | 200 | `{"ok": false, "error": "<OS error text>"}` |
| No/bad token | 403 | `{"ok": false, ...}` |

**State it touches.** None. Read-only on the index and settings; the only
side effect is the spawned file-manager process.

**Consumers (planned).** The Sources-tab install card and the Library empty
state (dashboard, U-13/AG's site page tells users the same path as text).

## GET /hooks/guide (public)

**What it does.** Serves the canonical nine hook-type definitions as JSON.

**Why it exists.** UX-14: hook vocabulary shows up on every library card
badge, the Library hook filter, and the Generate hook-pattern picker, but
the app never defines a hook anywhere. U-06 builds the in-app explainer on
top of this route.

**Source of truth.** `_HOOK_TYPE_DEFINITIONS` in `server.py`: an ordered
tuple of `(id, one-line definition)` pairs. The same rows render the
`_HOOK_TYPE_GUIDE` system-prompt block used by the hook classifier, so the
UI explainer and the classifier can never disagree.
`tests/test_u01_backend_enablers.py` pins the rendered prompt byte-for-byte.

**Auth posture.** Public, same as `/sources/manifest`: pure product
metadata, zero user data, safe for the static site or the extension popup
to read without the token dance.

**Request.** No parameters.

**Response.** `200 {"ok": true, "hooks": [...]}` with exactly 9 entries in
canonical guide order (`curiosity_gap` first, `other` last). Each entry:

```json
{
  "id": "curiosity_gap",
  "label": "Curiosity Gap",
  "description": "teases an answer or outcome without revealing it, opening an information gap the viewer wants closed."
}
```

- `id` is the stable enum value, always one of `HOOK_TYPES` (matches the
  `hook_type` field stored on every uoink and the Library filter values).
- `label` is `_hook_display_name(id)`: underscores to spaces, Title Case.
  Display-only; never round-trip it back to the API.
- `description` is the classifier's own one-liner, lowercase lead-in.
  Renderers should prepend their own framing sentence (U-06 owns that copy).

**Known consumer caveat.** The Generate "Hook pattern" picker today shows a
different, corpus-derived lens list. Reconciling the two taxonomies is
U-06's job and will be logged in DECISIONS-LOG.md; this route serves the
classification taxonomy only.

---

## GET /detect (token-gated)

Added by V-2a for the dashboard's universal "paste a URL to uoink" box.

**What it does.** Classifies one pasted URL into a single capture source and
tells the caller which existing route + payload key to use. Thin wrapper over
`_classify_capture_url`, which composes the validators that already ship
(`_normalize_youtube_url`, `_normalize_playlist_url`, `_normalize_twitter_url`,
`reddit_extractor.is_reddit_thread_url`, `_looks_like_feed_url`,
`_normalize_any_url`) plus `_detect_platform_from_url`. Detection therefore
can never claim a source the capture route would reject.

**Why it exists.** So the dashboard has one clean detection call instead of
duplicating every normaliser in JS, and so detection stays glued to the
routes. See `docs/surface-maps/universal-capture.md`.

**Request.** `?url=<raw url>`. No body.

**Response.** Always `200`. Supported URL:

```json
{
  "ok": true,
  "source": "youtube_video",
  "label": "YouTube video",
  "endpoint": "/extract",
  "payload_key": "url",
  "canonical": "https://www.youtube.com/watch?v=ID",
  "note": "",
  "platform": "youtube"
}
```

`source` is one of `youtube_video`, `youtube_playlist`, `x_video`,
`reddit_thread`, `podcast_feed`, `web_page`. `endpoint` is the route to POST
to; `payload_key` is the body key it expects (`url` for most, `feed_url` for
podcasts). Send `canonical` as the value; add `interval` for `/extract` and
`/playlist/start`.

Unsupported URL (also `200`, not an error): `ok: false`, `source:
"unsupported"` or `"empty"`, `endpoint: null`, and a plain-language `note`.
X video carries an honest `note` that it captures the video only.
