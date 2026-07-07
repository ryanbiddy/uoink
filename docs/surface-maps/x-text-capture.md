# Surface map: X text/thread capture (U-15, shipped V-2b)

Captures the TEXT of an X post plus the author's own earlier chain as a
yoink. X used to be video-only (yt-dlp with `twitter:api=syndication`);
this adds the text path over the same public endpoint. **V-2b ships it on
by default**: a single X post now captures its words, and its video too
when it has one -- no longer video-only.

## The flag

`x_text_capture_enabled` (boolean settings key, **default `True`** as of
V-2b; `_default_settings()` / `_normalize_settings`).

- Server side: `POST /extract/x` answers
  `{ok: false, code: "disabled", error: "...x_text_capture_enabled..."}`
  before touching the network when a user has explicitly set the key
  `False`.
- Extension side: the primary "Uoink this post" button drives the capture
  (see below). A user who opts out (`False`) falls back to the video-only
  path automatically, so nothing breaks.

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
subfolder="X", slug_prefix="x", data_root=DESKTOP_ROOT)`.

**Storage root** (fixed after the v3.3.1 capture test): the corpus lands
under the configured output root (`DESKTOP_ROOT` /
`UOINK_OUTPUT_DIR`) at `<output_root>/X/<url-digest>/x.md` — the same root
video captures, the corpus scan (`_iter_corpus_folders`), and the stale-path
heal all use. It previously passed `data_root=DATA_ROOT`, so X (and the
sibling Reddit / universal-page routes, which shared the same pattern) wrote
their corpus into `%LOCALAPPDATA%\Uoink\` instead, splitting a user's corpus
off their chosen output drive and leaving files the heal couldn't see. All
three page-shaped persist callers (`/extract/x`, `/extract/reddit`,
`/extract/page`, plus the `uoink_page` / `uoink_reddit_thread` MCP tools) now
use `DESKTOP_ROOT`.

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

## Extension (V-2b: one button, text + video)

- `STC.postExtractX(url)` in `lib/extract.js`: POST `/extract/x`, 60s
  timeout, relays the server JSON.
- Popup (`popup.html` / `popup.js`): the source-aware primary button
  ("Uoink this post" on an X status tab) routes through **`captureXPost`**.
  The standalone text button is retired.
  - Calls `postExtractX` first (text/thread, synchronous).
  - If the post also carries video (`metadata.has_video`), queues the
    video through the same `/extract` path YouTube uses ->
    "Saved N posts + queued the video."
  - Text-only post -> "Saved N post(s) to your library."
  - `code: "empty"` (video-only, no text) or `code: "disabled"` (user
    opted out) -> falls back to the `/extract` video path
    (`handleCorpusCapture`), so a video post never dead-ends.
  - Any other `ok: false` (404 / 429 / tombstone / block) -> the server's
    honest copy via `showToast`; nothing is queued, no half-saved uoink.

## Tests / proof

`tests/test_u15_x_capture.py`: URL matcher, token-vs-JS pin, single post,
embedded-parent walk with zero refetches, refetch walk, other-author stop,
deleted-ancestor survival, honest failure copy, disabled-when-off route,
token gate, full persist-through-index round trip, **default-flag-on**
(`test_default_flag_on`), extension wiring (primary button owns X, old
button retired), **output-root storage**
(`test_capture_lands_under_output_root` — corpus lands under the configured
output root, not `%LOCALAPPDATA%`), and **current popup copy/version**
(`test_popup_x_copy_and_version_current` — text-first X note, no hardcoded
version). Live X traffic is not exercised in CI.

Live verification (V-2b, from the build IP): `x/jack/status/20` -> 1 post
captured; `x/naval/status/...` mid-thread -> 2 posts walked up root-first;
`x/SpaceX/status/...` -> `has_video: True` (combined flow queues the
video); tombstone + deleted posts -> honest `fetch_failed` copy; full
`POST /extract/x` round trip persisted `source_type: x_thread` into the
corpus.
