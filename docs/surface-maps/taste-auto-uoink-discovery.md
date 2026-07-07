# Surface map: taste-aware auto-uoink (V-3) + local discovery digest (V-4)

The North-Star surface: turn the corpus from a place you fill by hand into
a place that fills itself with the good stuff (V-3) and hands you a calm,
owned "what's worth your attention" digest with a draft one click away
(V-4). Opt-in, local, no auto-spend, no fabricated data. Built by
**composing** existing subsystems -- `/resurface` (R-01), the taste model
(taste anchors + engagement + corpus), and the monitored-playlist bridge
-- not by inventing a crawler or a feed.

## V-3 -- taste-aware auto-uoink (OPT-IN, default OFF)

### The taste scorer (`taste_scoring.py`, new)

Pure, local, deterministic. No network, no LLM. Two calls:

- `build_taste_profile(idx)` folds four existing signals into one profile:
  - **taste anchors** (`memory_layer.get_taste_anchors`): 10/10 (best) +
    0/10 (worst) videos and admired channels;
  - **engagement** (`idx.top_engaged`): channels you actually open/cite,
    weighted by the time-decayed `value_score`;
  - **corpus shape** (`idx.search_yoinks_for_memory`): channels saved more
    than once + recurring title vocabulary;
  - **the anchor `avoid` note** (`memory_layer.get_anchor`).
  A sparse corpus yields `has_signal: False` -- scoring stays quiet until
  it has real signal (honest by design).
- `score_candidate(profile, {title, channel})` -> `{score 0..1, reasons[],
  blocked}`. Every contribution is small, signed, and carries a
  human-readable reason. `blocked` marks a worst-channel / avoid-term hit
  (never captured regardless of other matches).
- `make_filter(profile, threshold=DEFAULT_THRESHOLD)` -> a
  `callable(candidate)` the poll uses. `DEFAULT_THRESHOLD = 0.5`.

### The taste-gated poll (`mobile_playlists.poll_playlist`, extended)

Two new optional params keep ONE polling code path:

- `taste_filter` -- when passed, the poll becomes selective: only
  candidates that clear the bar are enqueued (reusing the existing
  `enqueue_pending` -> retry-worker capture path) and logged; each captured
  event row is stamped `capture_reason='auto_uoink:taste'` + `taste_score`.
  Declined candidates go to `skipped[]` (no queue row, no event) so
  Activity stays clean. With no filter the behaviour is the unchanged
  pre-V-3 "capture every new video" manual poll.
- `fetch_entries` -- test injection point (avoids a real yt-dlp call).

`_fetch_playlist_video_ids` now also captures `channel`/`uploader` from the
flat-playlist entry when yt-dlp exposes it (title-only otherwise).
`list_taste_captures(idx)` returns the auto-uoinked events for the digest.

### The endpoints

- `POST /auto-uoink/scan` (`_handle_auto_uoink_scan`): refuses with **409**
  unless `auto_uoink_enabled` is on; if there are no enabled monitored
  playlists it returns an honest `needs_sources` explanation (no crawler);
  otherwise builds one profile, scans every enabled source with the taste
  filter, and returns `{captured[], skipped[], sources[], message}`.
- `GET /auto-uoink/status` (`_handle_auto_uoink_status`): `{enabled,
  threshold, monitored_sources, has_taste_signal, needs_sources}`.

### Migration + settings

- `migrations/0019_auto_uoink.sql`: adds nullable `capture_reason` +
  `taste_score` to `mobile_queue_events` (backward compatible -- manual /
  pre-V-3 rows read back NULL).
- `auto_uoink_enabled` bool added to `_default_settings` (**False**),
  `_normalize_settings`, `_public_settings` (with read-only
  `auto_uoink_threshold`), and the settings-POST `boolean_fields`.

### Safety model (opt-in, reversible, honest)

Default OFF -> only over playlists the user already added -> capture is the
same local yt-dlp + transcription as a manual save (**no AI spend**) ->
captures labelled "auto-uoinked (taste match)" -> auto-captured uoinks are
ordinary uoinks the user can delete -> turning the toggle off stops future
scans. No web crawling, no new accounts, no fabricated items.

## V-4 -- local discovery digest

`GET /discovery` (`_handle_discovery` -> `_discovery_payload`) composes the
existing `_resurface_payload` (R-01: worth_revisiting, connections,
corpus_gaps, anchors) with the V-3 `_auto_uoink_recent_captures` into one
calm, ranked `attention[]` stream. Each auto-uoink capture is joined to its
corpus row (`idx.get_yoink`) so a finished one exposes `in_corpus: true`
and a one-click "Write from this"; an item still extracting is shown
honestly as "capturing". The payload passes the resurface keys straight
through, so the existing `renderForYou()` keeps working unchanged
(discovery is a superset). Framing is a standing digest -- no counters, no
fake urgency (Voice DNA).

## Dashboard (`assets/dashboard/index.html`)

- **For You tab**: `loadForYou()` now calls `/discovery` (falls back to
  `/resurface`, then the client approximation). A new "Fresh from your
  sources" panel (`#freshPanel`, `renderFresh`) renders the auto-uoinked
  items; each ready one reuses the U-04 `[data-write-from]` deep link.
- **Settings tab**: a "Taste-aware auto-uoink" block (`#auto-uoink`) with
  the opt-in toggle (`#autoUoinkToggle`), a live status line
  (`renderAutoUoinkStatus` -> `/auto-uoink/status`), a "Scan my sources
  now" button (`runAutoUoinkScan` -> `/auto-uoink/scan`), and the honest
  copy (opt-in, sources-only, no spend, reversible).

## Routes consumed / added

- `GET /discovery` (new), `GET /auto-uoink/status` (new),
  `POST /auto-uoink/scan` (new).
- Reused: `GET /resurface`, `GET /settings` + `POST /settings`, the
  monitored-playlist routes, the U-04 write-from deep link.

## Tests / proof

- `tests/test_taste_scoring.py` -- profile build + scoring: empty corpus
  captures nothing; admired channel captures; worst channel + avoid term
  are blocked; unrelated stays below the bar.
- `tests/test_auto_uoink_poll.py` -- taste-gated poll captures on-taste /
  skips off-taste, persists `capture_reason`+`taste_score`, is idempotent.
- `tests/test_auto_uoink_scan.py` -- default OFF; scan while off -> 409;
  ON with no sources -> honest `needs_sources`; status contract + token
  gate.
- `tests/test_discovery_route.py` -- `/discovery` composition, token gate,
  a taste capture surfaces labelled + corpus-joined, ranked attention has
  write-from ids.
- Live drive: `scratchpad/v34_launcher.py` + `v34_shots.js` (screenshots
  in `handoff/screenshots/v3v4-discovery-2026-07-07/`).

## Honest limitations

- Auto-uoink only works over sources the user already tracks (monitored
  playlists) -- it is not a web discovery crawler.
- From a flat-playlist listing only id + title (+ sometimes channel) are
  available, so channel-based scoring applies only when yt-dlp exposes the
  uploader; otherwise scoring leans on title-vocabulary overlap.
- A declined candidate is still marked "seen", so it is not re-scored on a
  later poll if taste later changes (matches the existing poll dedupe
  contract).
- There is no background auto-poll worker; scans are user-triggered (the
  "Scan my sources now" button / `POST /auto-uoink/scan`).
