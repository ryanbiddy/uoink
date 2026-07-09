# Surface map: short-form video capture (TikTok, Instagram Reels, YouTube Shorts)

Context-layer build sequence item 2. A TikTok, an Instagram Reel, or a
YouTube Short becomes a first-class uoink in the same corpus as everything
else: platform / source_type / author / topic, queryable by AI and by you.

The design principle: **reuse, do not rebuild**. yt-dlp already supports all
three networks, so short videos ride the exact same download / transcript /
thumbnail pipeline (`_run_extraction`) that YouTube videos use. No new
downloader, no new persistence path. The only new code is the routing that
recognizes these URLs and the taxonomy tag that files them.

## What lands

Same shape as a YouTube video capture: the clip is downloaded, ffmpeg pulls
screenshots on the interval, the caption/description text and any
platform-provided transcript are captured, a thumbnail is saved, and the
corpus markdown + JSON sidecar land in a readable folder under the output
root (`DESKTOP_ROOT/<topic>/<slug>/`), never AppData. Because the caption
and description are always captured, a short is queryable even when the
platform exposes no spoken transcript.

## Taxonomy (the one judgment call)

- **platform**: `tiktok`, `instagram`, or `youtube`. A TikTok / Reel gets
  its own platform tag. A YouTube Short stays `platform=youtube` because it
  *is* YouTube.
- **source_type**: `short_video` for all three. This is a **new**
  source_type, deliberately NOT the existing `video`. Reusing `video` would
  have broken platform derivation: `page_extractor._SOURCE_TYPE_PLATFORM`
  hard-maps `video -> youtube`, so a TikTok tagged `video` would have been
  mis-filed as a YouTube row. `short_video` is intentionally absent from
  that table so `platform_for()` falls through to host detection, which now
  knows the TikTok and Instagram hosts. Existing YouTube long-form video
  rows keep `source_type='video'` and are untouched.
- **author**: the creator/uploader. `page_extractor.author_for()` returns
  `None` for the short platforms (same as YouTube/podcasts), so the caller
  falls back to `sidecar.channel`, which the pipeline fills from yt-dlp's
  `channel` / `uploader` / `creator`.
- **topic**: classified by the existing `_classify_topic()` over
  title + description + tags + channel.

## Classifier + routing

The raw URL matters: a YouTube Short's `/shorts/` signal is lost once the
URL normalizes to `watch?v=`, so short detection runs against the pasted
URL, before normalization.

- `server._normalize_tiktok_url` / `_normalize_instagram_url` host-gate and
  canonicalize (TikTok keeps its host, including the `vm.`/`vt.` short-link
  redirect hosts that yt-dlp resolves; Instagram accepts `/reel`, `/reels`,
  `/p`). `youtu.be/<id>` carries no short signal and stays a regular video.
- `server._normalize_short_video_url` -> `(canonical, platform)`, and
  `_is_short_video_url` -> bool. Both mirror the extension's
  `normalizeShortVideoUrl` in `extension/lib/extract.js` so the popup
  classifier can never disagree with what `/extract` accepts.
- `_classify_capture_url` gains a `short_video` branch (before the YouTube
  branch) that routes to `/extract`. `_normalize_video_url` accepts TikTok
  and Instagram, so `POST /extract` and `POST /extract/any` both take them;
  `_validate_url_interval` stamps `__source_type='short_video'`, which
  `_handle_extract` threads into `_run_extraction`, which writes it to the
  sidecar. `_index_yoink` reads it and derives platform + author.

## Honest failure

TikTok and Instagram rate-limit and login-wall aggressively. When yt-dlp
can't fetch (login required, private, region-locked, 429), the metadata
fetch in `_handle_extract` raises before any folder is created, so
**nothing is persisted** and the user gets an actionable message. Same
honesty discipline as X. `_source_name_from_error` recognizes TikTok and
Instagram so the copy names the source.

## Surfacing

No special-casing anywhere downstream. Once a short is indexed it appears in
`/recent`, filters in `/memory/search?platform=tiktok` /
`?source_type=short_video`, shows up in `/library/facets` with the labels
"TikTok" / "Instagram" / "Short video", and is readable by every MCP tool
that reads the corpus (the memory-search filters already accept
`platform` / `source_type` / `author`). The popup shows "Uoink this short
video" on a TikTok / Reel / Short tab.

## Tests

- `tests/test_short_video.py`: classifier routing, normalizers,
  platform/author taxonomy, a MOCKED end-to-end extraction (yt-dlp + ffmpeg
  stubbed via `_run_subprocess`) asserting the persisted row carries the
  right platform/source_type/author/topic and surfaces in search + facets,
  and an honest-failure test (login wall persists nothing).
- `tests/js/classifier_test.mjs`: the extension classifier for TikTok, the
  `vm.` short link, Instagram Reels (with and without the author prefix),
  YouTube Shorts (canonical is the watch URL), and the guard that a regular
  watch URL is NOT a short.

Tests use mocks on purpose: live TikTok / Instagram are unreliable in CI.
