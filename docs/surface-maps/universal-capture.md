# Surface map: universal capture (V-2a)

Capture used to be scattered. The in-page button injected only on YouTube
and Reddit, the popup captured the current tab, right-click covered YouTube
and X, and playlist and RSS URLs lived in separate settings boxes. There
was no single "paste any URL, detect the source, uoink it" entry point.

V-2a adds one: a prominent "Uoink anything" box at the top of the Sources
tab, reachable from the Library empty state. You paste a link, Uoink detects
the source and shows a chip, and one "Uoink it" button routes to the correct
existing capture route. No capture logic was reimplemented.

## The detection brain: `_classify_capture_url`

`server._classify_capture_url(raw)` is the one place that decides what a URL
is. It composes the validators that already ship, so detection can never
drift from what the capture routes actually accept:

| Check (in order) | Reused function | Source | Route | Payload key |
|---|---|---|---|---|
| YouTube video | `_normalize_youtube_url` | `youtube_video` | `/extract` | `url` |
| YouTube playlist | `_normalize_playlist_url` | `youtube_playlist` | `/playlist/start` | `url` |
| X video | `_normalize_twitter_url` | `x_video` | `/extract` | `url` |
| Reddit thread | `reddit_extractor.is_reddit_thread_url` | `reddit_thread` | `/extract/reddit` | `url` |
| Podcast feed | `_looks_like_feed_url` (shape heuristic) | `podcast_feed` | `/podcasts/feeds` | `feed_url` |
| Web page | `_normalize_any_url` | `web_page` | `/extract/page` | `url` |
| anything else | (none accept it) | `unsupported` | none | none |

`_detect_platform_from_url` rides along as the `platform` field.

Precedence notes:

- Video wins over playlist. A `watch?v=...&list=...` URL is a single video
  (you're watching one), so it routes to `/extract`, not a playlist add. A
  bare `playlist?list=...` (no `v=`) is the playlist.
- Podcast detection is shape-only (`.rss`/`.xml`, a `/feed|/rss|/podcast`
  path segment, a `feeds.` host, or `format=rss|xml`). Feeds are just
  http(s) URLs, so there is no certain signal. When the shape isn't there,
  the URL falls through to the web-page path instead of a wrong guess.

The returned dict is what both `/detect` and the dashboard render:

```json
{
  "ok": true,
  "source": "x_video",
  "label": "X video",
  "endpoint": "/extract",
  "payload_key": "url",
  "canonical": "https://x.com/handle/status/123",
  "note": "Captures the video only. Tweet and thread text isn't supported yet.",
  "platform": "twitter"
}
```

## Honest states

- **X video** carries `note`: "Captures the video only. Tweet and thread
  text isn't supported yet." The box shows exactly that. It never implies
  tweet-text capture works (that lives behind the flagged `/extract/x`).
- **Unsupported** answers `ok: false` with the plain label "Not a supported
  source yet" and a note that lists what does work. It is a valid answer,
  not an error: the button stays disabled instead of failing weird.
- **Web page** note is honest that `/extract/page` is allowlist-gated. If
  the capture returns `host_not_allowed`, the box tells you to add the site
  in Settings.

## GET /detect (token-gated)

See `docs/surface-maps/helper-http-api.md`. Thin wrapper over
`_classify_capture_url`. Always 200. Token-gated like the rest of the
dashboard-read surface; the dashboard sends the `/token` handshake token.

## Dashboard wiring (`assets/dashboard/index.html`)

- The box is `#universalCapture` in the Sources tab: `#universalCaptureInput`
  (URL), `#universalCaptureChip` (the detection chip), `#universalCaptureNote`
  (honest per-source note, rendered verbatim from the server), and
  `#universalCaptureButton` ("Uoink it").
- Detection runs on `input` (debounced 220ms), `paste`, `blur`, and Enter,
  via `GET /detect`. A redundant re-detect on an unchanged value is skipped,
  so a blur firing right as you click the button never disables it mid-click.
- The capture POSTs to `universalState.endpoint` (the route the server
  handed back), with the payload key the server named, so the dashboard can
  never route somewhere detection didn't sanction. `/extract` and
  `/playlist/start` also get `interval: 30`; the others ignore it.
- On success the job shows in Activity (`refreshActivity()`) and the result
  lands in Library, same as any other capture.
- The Library empty state has "Paste a URL to uoink" (`#emptyPasteUrl`)
  which jumps to the box and focuses it.

## What was deliberately not done

- Capture logic was not reimplemented. Every route (`/extract`,
  `/extract/reddit`, `/extract/page`, `/playlist/start`, `/podcasts/feeds`)
  is the same one the extension and settings boxes already use.
- The Sources source-map cards keep their per-source capture copy; the
  universal box is the one capture entry point, so no per-card URL inputs
  were added (that would re-clutter the P5 "one clean flow" work).

## Tests

`tests/test_v2a_universal_capture.py`: classifier precedence and routing,
the video-over-playlist rule, X honesty, unsupported honesty, the `/detect`
route (classifies + 200 for unsupported + token gate), and the dashboard
wiring (box present, routes off the detected endpoint, honest note rendered,
no em dashes in the new copy).
