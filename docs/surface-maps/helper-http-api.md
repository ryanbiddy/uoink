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

## MCP tool schemas (3.16.2)

`POST /mcp/v1` with `tools/list` and `POST /mcp/v1/tools/list` advertise the
same full name, description and input-schema list as default stdio. Both
transports use `client_input_schema` to flatten the top-level `oneOf` in
`claim_library_work`, `apply_reshelving` and `set_source_consent`. Calls still
validate against the exact frozen schemas and keep their existing refusals.

`GET /mcp/v1/sse` points clients at `/mcp/v1`, so it uses that same listing.
`GET /mcp/v1/config` contains connection settings only, with no tool schemas.
OpenAPI and `/sources/schema` describe the frozen contracts and keep `oneOf`.
The public discovery manifests (`/.well-known/uoink-mcp.json` and
`/developers/manifest`) contain endpoints and counts, with no input schemas.
The `.mcpb` manifest lists names and descriptions; its launched stdio server
supplies the flattened input schemas at runtime. Contract documents also keep
the frozen schemas.

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
An X post routes to `/extract/x` (text + thread, shipped v3.3.0) with an
honest `note`; a video in the post is queued via the extension's Uoink button.

---

## POST /api/suite/v1/capture and GET /api/suite/v1/capture/<job_id> (token-gated)

Capability `uoink.capture/1`, listed in `/.well-known/suite-service.json` and
the runtime lease next to `uoink.corpus.read/1`, `uoink.engagement.ingest/1`
and `uoink.media.handoff/1`. Added for sibling suite apps that need to save one
source link into the user's library.

**Auth.** `X-Uoink-Token`, the same header and check as every other route on
this page and as `POST /api/engagement/v1/events`. Missing or wrong token: the
usual `403 {"ok": false, "error": "missing or invalid token"}`. Loopback only;
on an isolated install it answers on that install's port.

**Request.** `POST` JSON `{"url": "<http(s) url>", "source_hint": optional}`.
`source_hint` is one of the `/detect` sources (`youtube_video`,
`youtube_playlist`, `x_video`, `reddit_thread`, `podcast_feed`, `web_page`;
`short_video` and `x_article` are accepted too). It is only a hint: the route
classifies the URL with the same `_classify_capture_url` as `GET /detect`, and
detection decides.

**What happens.**

1. An unsupported URL stops here (`unsupported_url`).
2. If the canonical URL is already in the library, the response is `exists`
   with that item and nothing is captured. The lookup uses the identity the
   library and research "Use saved" use: the video ID or recorded source URL for
   videos, and the saved-page, Reddit-thread and X-post key for everything else.
   A deleted item does not count.
3. A web page (or X article) whose host is not on the page allowlist, and any
   podcast feed, stops with `consent_required`.
4. Video sources stop with `media_unavailable` when this install has no media
   capability.
5. The capture then goes to the existing code for that source:
   `uoink_reddit_thread` and `uoink_page` run inline and answer `saved`.
   `youtube_video`, `short_video` and `x_video` (`uoink_video`, `uoink_url`) can
   take minutes, so they run on a worker thread and answer `queued` with a
   `job_id`. A `youtube_playlist` starts the existing playlist job and answers
   `queued` with that job's id. While one video capture started here is still
   running, another gets `busy`.

**Success.** `200` for `saved` and `exists`, `202` for `queued`:

```json
{
  "ok": true,
  "contract": "uoink.capture",
  "version": 1,
  "status": "saved",
  "source": "reddit_thread",
  "item_id": "abc123",
  "job_id": null,
  "canonical": "https://www.reddit.com/r/test/comments/abc123/a_title/",
  "item_uri": "uoink://item/abc123"
}
```

`item_id` and `item_uri` are `null` while queued (and for a finished playlist,
which is many items). `job_id` is `null` unless queued.

**Job lookup.** `GET /api/suite/v1/capture/<job_id>` returns the same shape with
`status` of `queued` (`202`), `saved` or `error` (`200`). An `error` carries a
plain `message`. It reads both jobs started here and playlist jobs.

**Errors.** `{"ok": false, "contract": "uoink.capture", "version": 1, "error":
"<code>", "message": "<plain words>"}`:

| code | HTTP | meaning |
|---|---|---|
| `bad_request` | 400 | missing or non-string `url`, unknown `source_hint`, malformed job id |
| `unsupported_url` | 400 | not a link Uoink can capture |
| `consent_required` | 409 | site not on the page allowlist, or a podcast feed |
| `media_unavailable` | 501 | video capture is not available on this install |
| `busy` | 429 | a video capture started here is still running |
| `not_found` | 404 | no job with that id |
| `capture_failed` | 502 | the capture tool ran and could not save the link |

---

## GET /relay/status and POST /relay/check (token-gated)

**What they do.** Report and trigger the phone inbox poller (Uoink Relay,
`docs/relay.md`). `GET /relay/status` returns
`{ok, enabled, configured, last_poll_at, last_ok_at, last_error,
last_capture_error, picked_up_total, last_pending_count, polling}`.
`POST /relay/check` wakes the `relay-inbox` thread, waits up to 8 s for the
check and returns the same shape. Both always answer HTTP 200.

**Auth posture.** Token-gated like `/settings`: the status reveals whether the
user set up a relay. Neither route returns or logs the pull token;
`last_error` is fixed plain-language text.

**State it touches.** In-memory poller state only. The settings live in
`settings.json` (`relay_enabled`, `relay_url`, `relay_poll_minutes`) and the
pull token in the keyring (`relay_pull_token`, isolation-aware service).

**Outbound requests.** Only to the saved `relay_url`, only while
`relay_enabled` is true: `GET /v1/links` and `DELETE /v1/links/<id>`.

**Consumers.** Dashboard Settings > Capture > Phone inbox.

---

## GET /zing/status, POST /zing/handoff and GET /zing/handoff/<job_id> (token-gated)

**What they do.** Back the dashboard's "Make a Short with Zing" button.
`GET /zing/status` runs Zing's no-network probe (`zing from-uoink --probe --json`,
5 s timeout) and returns `{ok, available, service_version, reason, features}`.
It is `available` only when Zing answers with contract `ryan.suite.handoff`
version 1 and lists `uoink.item/1` in `accepts`. `features` is the probe's list of
strings (empty for an older Zing); `allow_download` in it means Zing can fetch a
video Uoink did not keep. Any failure is `available: false` with a plain
`reason`; the route always answers 200 and never raises. The result is cached for
five minutes (30 seconds when Zing was not found).

`POST /zing/handoff` takes `{"video_id": "<id>", "allow_download": bool}`. It
checks the id format and that the item exists and is not deleted, refuses (409
`zing_unavailable`) if the probe fails, then starts
`zing from-uoink uoink://item/<id> --json` detached and answers
`202 {ok: true, job_id}` at once. `--allow-download` is added only when
`allow_download` is exactly `true` and the probe listed `allow_download`. A bad
id is 400 `invalid_id`; an unknown or deleted item is 404; a second hand-off for
an item that already has one running is 409 `busy`; a start failure is 502
`failed`.

`GET /zing/handoff/<job_id>` returns
`{ok, job_id, state, percent, page, project, reused, downloaded, error, message, host}`.
`state` is `running`, `done` or `error`. While running, `percent` is the newest
download percent Zing reported (0-100, or null; it can stall or jump). When
`done`, `page`, `project`, `reused` and `downloaded` are set. When `error`,
`error` and a plain-words `message` are set. Zing's codes map as `invalid_ref`,
`uoink_unavailable`, `media_unavailable` (keep the item's media first: the
`keep_media` setting, short videos only), `project_exists`, `download_failed`
and `failed`; no first line within the timeout is `timeout`. `download_needed`
means Uoink did not keep the video and Zing needs the user's OK to fetch it;
`host` is then the host of the item's own source link as Uoink stores it (never
parsed from Zing's message). If the item has no http(s) source link it is
reported as `media_unavailable`. An unknown job id is 404.

Jobs live in memory only (cap 100; the oldest finished job is dropped first) and
are lost on a helper restart; the Zing child itself is detached and is never
killed. The reader waits up to 60 s for Zing's first line, or 75 minutes when
`--allow-download` was passed (Zing's own download limit is one hour, plus time
to merge).

**Auth posture.** Token-gated. A missing or wrong token answers `403`.

**State it touches.** None of its own. The child gets `UOINK_TOKEN` and
`UOINK_URL` (the helper's active base URL, which is the isolated binding's URL
on isolated installs) so Zing can read the item's kept media through
`uoink.media.handoff/1`. Nothing is written to `settings.json`.
That contract's `media.path` is the kept file's resolved absolute path: a plain
local path, or `\\?\C:\...` for a long Windows path. When a library on a
mapped drive resolves to a `\\server\share` path, Uoink sends the stored
drive-letter path instead (with `\\?\` if it is too long), because Zing
refuses share paths. A library stored on a share stays a share path, and Zing
falls back to asking to download. Containment inside the item folder is always
checked on the resolved path.

**Outbound requests.** None from the helper. Zing makes its own loopback calls
to this helper; with `--allow-download` Zing, not Uoink, fetches the video.

**Consumers.** Dashboard reader, "Make a Short with Zing": click, POST, poll
once a second. If the job ends in `download_needed` (and `features` has
`allow_download`) it asks inline whether to download from the host; Download
POSTs again with `allow_download: true`, Cancel does nothing. The dashboard opens
only the `http://127.0.0.1:<port>/?t=...` page the job returned.
