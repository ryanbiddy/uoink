# Surface map: X text/thread capture (U-15)

Captures the TEXT of an X post plus the author's own earlier chain as a
yoink. Ships dark behind a flag. Today X was video-only (yt-dlp with
`twitter:api=syndication`); this adds the text path over the same public
endpoint.

## The flag

`x_text_capture_enabled` (boolean settings key, absent/false by default).

- Server side: `POST /extract/x` answers
  `{ok: false, code: "disabled", error: "...x_text_capture_enabled..."}`
  before touching the network while the flag is off.
- Extension side: the popup button only renders when the flag reads true
  (via `STC.getSettings()`), so nothing changes for anyone who hasn't
  opted in. Flip the key through the Settings PATCH or settings.json.

## Backend: `x_extractor.py`

House pattern of `reddit_extractor.py`: fetch separated from parse/render,
`_fetch` injection for tests, `extract_result` shaped for
`page_extractor.persist_page_yoink`.

- **Endpoint**: `https://cdn.syndication.twimg.com/tweet-result?id=<id>&
  token=<t>&lang=en`, UA `Googlebot` (the combination yt-dlp ships).
- **Token**: `((Number(id)/1e15)*Math.PI).toString(36)` with all `0`s and
  `.`s stripped. `_js_base36` is a port of yt-dlp's `js_number_to_string`
  digit emitter (jsinterp.py, Unlicense) so the Python output matches the
  browser digit for digit; `test_u15_x_capture.py` pins 4 node-generated
  reference tokens.
- **Thread walk** (`collect_thread`): fetch the shared post, then follow
  `in_reply_to_status_id_str` upward while the parent is the same author,
  using the embedded `parent` payload when present (zero extra fetches for
  chains the endpoint inlines), hop-capped at 25. A deleted ancestor stops
  the walk but keeps the partial capture.
- **Honest scope**: the public endpoint serves one post at a time and only
  links upward. Posts BELOW the shared one are unreachable without
  authenticated GraphQL. The rendered markdown says exactly that, and the
  metadata carries `capture_scope`.
- **Failure copy** (all `ValueError` -> `{ok:false, code, error}`): 404
  ("deleted, protected account, or X refusing the public endpoint"), 429
  rate limit, empty body, non-JSON block page, `TweetTombstone`. A
  text-less video post returns `code: "empty"` and points at the regular
  Uoink button.

## Route: `POST /extract/x` (token-gated)

`{url}` -> flag gate -> `x_extractor.extract_x_thread` ->
`page_extractor.persist_page_yoink(source_type="x_thread",
subfolder="X", slug_prefix="x")`.

| Case | Status | Body |
|---|---|---|
| Flag off | 200 | `{ok: false, code: "disabled", error}` |
| Saved | 200 | `{ok: true, video_id, title, tweets_captured, metadata}` |
| X refused / bad URL / empty post | 200 | `{ok: false, code, error}` (extractor's copy) |
| Persist failed | 500 | `{ok: false, error}` |
| No/bad token | 403 | |

Title shape: `@handle: <first 60 chars of the root post>`. Markdown:
`# Author (@handle) on X`, source link, capture-scope line, then each post
as `## n/N` with text + date + photo/video notes.

## Extension

- `STC.postExtractX(url)` in `lib/extract.js`: POST `/extract/x`, 60s
  timeout, relays the server JSON.
- Popup (`popup.html` / `popup.js`): `#uoink-x-text-btn` ("Save post text
  + thread"), hidden by default. `syncXTextButton` shows it only when the
  active tab is an X status URL (`STC.normalizeTwitterUrl`) AND the server
  flag is on. Click -> "Saving text..." -> success toast with the post
  count, or the server's failure copy verbatim.
- The existing video path (context menus, "Uoink current video") is
  untouched; a video post's markdown tells the user to use it.

## Tests / proof

`tests/test_u15_x_capture.py` (red on unpatched main: no module, route
404): URL matcher, token-vs-JS pin, single post, embedded-parent walk with
zero refetches, refetch walk, other-author stop, deleted-ancestor
survival, honest failure copy, flag-off default, token gate, full
persist-through-index round trip, extension wiring. Live X traffic is
deliberately not exercised in CI; the flag keeps the feature dark until a
human tries it against real X.
