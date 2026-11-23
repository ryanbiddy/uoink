# Timed cues and whole-show saves (for Zing and other clip tools)

Uoink 3.18 adds two things a clip tool can build on:

1. **A timed cues read** (`uoink.cues.read` v1): for one saved item, every
   transcript cue as `{start, end, text}` in seconds, where those timings came
   from, the original publish date, the duration and the source URL. Plus a
   list call that filters saved items by show and by publish date.
2. **Whole-show saves** (`/shows`): the user pastes a YouTube channel, a
   playlist, a podcast feed or a list of links, sees the episode count and a
   time and disk estimate, and starts a transcript-only save of every episode.

Both are local reads and writes on the user's own helper. Every route needs
the `X-Uoink-Token` header. Corpus read v1 (`/api/corpus/v1/*`) is unchanged:
same URLs, same envelopes, byte for byte. No MCP tools were added. The MCP
`get_transcript` tool with `include_timestamps: true` already returns timed
segments for YouTube items, and its default output stays as it was.

The examples below use a made-up show, The Tidepool Hour, and the helper's
default address `http://127.0.0.1:5179`.

## Timed cues read

| Method | Path | Result |
|---|---|---|
| GET | `/api/cues/v1/items/<id>` | one item's cues, timing source and dates |
| GET | `/api/cues/v1/items` | item references filtered by words, show and dates |

Both are in the helper's OpenAPI document (`GET /openapi/v1/spec.json`) as
`get_timed_cues` and `list_timed_cue_items`. Every response is an envelope:

```json
{"ok": true, "contract": "uoink.cues.read", "version": 1, "operation": "get", "data": {}}
```

Errors keep the envelope with `ok: false` and
`error: {code, message, retryable}`. Codes: `invalid_request` (400, an
unknown or malformed parameter), `not_found` (404), `unavailable` (503,
retryable). Unknown parameters are refused, not ignored, so a typo never
widens a query silently.

### One item

`GET /api/cues/v1/items/tpcaptions1?start=0&end=10`

| Parameter | Meaning |
|---|---|
| `start`, `end` | seconds, optional: only cues that overlap that window |
| `limit` | most cues in one response, 1 to 5000, default 1000 |
| `offset` | 0 or more, a position in the window. Use `page.next_offset` |
| `include_words` | `0` leaves word timings out (default `1`) |

`page.total` counts every cue in the window and `page.next_offset` is
`null` on the last page. A multi-hour episode with word timings can run to
several MB, so ask for pages, or `include_words=0` when cue timings are enough.

```json
{
  "ok": true,
  "contract": "uoink.cues.read",
  "version": 1,
  "operation": "get",
  "data": {
    "item": {
      "id": "tpcaptions1",
      "title": "Captions episode",
      "channel": "The Tidepool Hour",
      "platform": "youtube",
      "source_type": "youtube",
      "source_url": "https://www.youtube.com/watch?v=tpcaptions1",
      "published_at": "2025-03-04T15:00:00Z",
      "duration_seconds": 95.0,
      "captured_at": "2026-11-02T09:00:00",
      "description": "Tide tables, read aloud."
    },
    "timing": {"source": "captions", "caption_kind_known": true, "word_timings": false},
    "range": {"start": 0.0, "end": 10.0},
    "cue_count": 2,
    "page": {"limit": 1000, "offset": 0, "total": 2, "next_offset": null},
    "cues": [
      {"start": 0.0, "end": 4.25, "text": "Welcome back to the pool.",
       "deep_link": "https://www.youtube.com/watch?v=tpcaptions1&t=0s"},
      {"start": 4.25, "end": 9.0, "text": "Today: anemones.",
       "deep_link": "https://www.youtube.com/watch?v=tpcaptions1&t=4s"}
    ]
  }
}
```

Fields:

- `cues` are sorted by `start`, rounded to milliseconds. `end` is never before
  `start`. `deep_link` is present when Uoink stored a link that opens the
  source at that cue. `speaker` is present only when the cue has an attributed
  speaker with provenance (podcast episodes with speaker labels).
  `words` (`[{start, end, text}]`, sorted, `end` never before `start`) is
  present only when valid word timings were stored. Today Uoink stores word
  timings only where its transcriber kept them, so expect cue-level timings
  in most items and check `timing.word_timings` (true only when a cue has
  valid words) before relying on words.
- `timing.source` is where the timings came from:
  - `captions`: the creator's uploaded captions.
  - `auto_captions`: the platform's automatic captions.
  - `local_asr`: Whisper on the user's computer (videos saved with local
    transcription, and podcast episodes).
  - `null`: the item has no transcript.
- `timing.caption_kind_known` is `false` for captions saved before 3.18,
  which did not record whether they were uploaded or automatic. Those report
  `source: "captions"`.
- `item.published_at` is the original publish date, never the capture time.
  It is ISO 8601 when Uoink knows the time (`2025-03-04T15:00:00Z`), or a day
  (`2024-01-10`) when the source only gave a day (yt-dlp's `upload_date`, an
  RSS `pubDate`). `null` when unknown. `captured_at` is when Uoink saved it.
- No response carries a file path.

A local transcription example (a cue with word timings):

```json
{
  "timing": {"source": "local_asr", "caption_kind_known": true, "word_timings": true},
  "cues": [
    {"start": 0.0, "end": 2.0, "text": "Hello reef",
     "words": [{"start": 0.0, "end": 0.6, "text": "Hello"},
               {"start": 0.7, "end": 1.4, "text": "reef"}]}
  ]
}
```

### Items by show and publish date

`GET /api/cues/v1/items?channel=The%20Tidepool%20Hour&published_from=2025-01-01&limit=2`

| Parameter | Meaning |
|---|---|
| `q` | words to search for (keyword search) |
| `channel` | exact show or channel name |
| `published_from`, `published_to` | original publish date bounds, inclusive, `YYYY-MM-DD` |
| `date_from`, `date_to` | capture date bounds, inclusive, `YYYY-MM-DD` |
| `limit` | 1 to 200, default 50 |
| `offset` | 0 or more |

Items with no known publish date never match a publish bound. Without `q`,
the newest capture comes first.

```json
{
  "ok": true,
  "contract": "uoink.cues.read",
  "version": 1,
  "operation": "search",
  "data": {
    "filters": {"q": null, "channel": "The Tidepool Hour", "published_from": "2025-01-01",
                "published_to": null, "date_from": null, "date_to": null},
    "page": {"limit": 2, "offset": 0, "total": 2, "next_offset": null},
    "items": [
      {"id": "tppodcast01", "title": "Podcast episode", "channel": "The Tidepool Hour",
       "platform": "podcast", "source_type": "episode",
       "source_url": "https://tidepool.example.com/ep/1", "published_at": "2025-03-03",
       "duration_seconds": null, "captured_at": "2026-11-05T09:00:00",
       "cues_url": "/api/cues/v1/items/tppodcast01"},
      {"id": "tpcaptions1", "title": "Captions episode", "channel": "The Tidepool Hour",
       "platform": "youtube", "source_type": "youtube",
       "source_url": "https://www.youtube.com/watch?v=tpcaptions1",
       "published_at": "2025-03-04T15:00:00Z", "duration_seconds": 95.0,
       "captured_at": "2026-11-02T09:00:00", "cues_url": "/api/cues/v1/items/tpcaptions1"}
    ]
  }
}
```

The same filters work on the Library route
(`GET /memory/search?channel=...&published_from=...&published_to=...`) and in
the CLI.

### CLI

```text
uoink cues tpcaptions1                    # one item, JSON envelope
uoink cues tpcaptions1 --start 0 --end 10 --text
uoink cues --channel "The Tidepool Hour" --from 2025-01-01 --to 2025-12-31
uoink cues --words anemones --limit 20
uoink cues --channel "The Tidepool Hour" --limit 50 --offset 50   # the next page
uoink cues tpcaptions1 --limit 500 --offset 500                   # cues 501 to 1000
```

`uoink cues` reads the local library in-process and prints the same
envelopes as the HTTP routes (`--text` for a readable view). Mixing an item
id with list flags is a usage error (exit 2).

## Whole-show saves

A run lists every episode first and saves nothing until the user starts it.
Each episode is saved as a transcript only: captions first (the uploaded track
wins over the automatic one), no video download, no screenshots, comments,
entity extraction or channel details. Local transcription runs only when the
user turned it on for that run, and only for episodes without captions (it
downloads the audio, transcribes it, then deletes the audio). Podcast feeds
always use local transcription, and their audio is kept with each episode,
as it is for any saved podcast episode.

Episodes go one at a time through Uoink's normal download queue, after
anything the user saves themselves. While YouTube's bot-check cooldown is on,
or a queued episode is waiting out a bot check or a 429, the run waits. A
podcast host that refuses (a 429, a 5xx, a timeout) makes the run wait 2
minutes, then twice as long each time up to an hour, and five host failures
in a row pause it with the reason. A run keeps going after the helper
restarts. An episode already in the library is skipped, never saved twice
and never replaced, and one the user removed is left out.

Only public `http(s)` feed addresses are accepted: loopback, private and
link-local hosts and credentials in the link are refused before anything is
stored, and the fetch checks the resolved address again.

### Start a run

`POST /shows/preview` with `{"text": "https://www.youtube.com/@tidepoolhour"}`
returns `202` with the run in `listing`. Poll `GET /shows/<id>` until it is
`ready`:

```json
{
  "ok": true,
  "run": {
    "id": "show_625ad0293689",
    "kind": "youtube_channel",
    "kind_label": "YouTube channel",
    "url": "https://www.youtube.com/@tidepoolhour/videos",
    "title": "The Tidepool Hour - Videos",
    "state": "ready",
    "reason": null,
    "wait_until": null,
    "asr": false,
    "listing_note": null,
    "counts": {"queued": 315, "running": 0, "done": 0, "failed": 0, "skipped": 2, "total": 317},
    "estimate": {
      "to_save": 315, "already_saved": 2, "audio_minutes": 10300, "durations_known": 315,
      "hours": 3.9, "asr_hours_at_most": 0.0, "asr_hours_if_all": 34.3,
      "disk_mb": 78.8, "audio_download_mb_at_most": 0, "needs_asr": false
    },
    "current": null,
    "failures": [],
    "failures_total": 0,
    "created_at": "2026-11-20T13:48:16Z",
    "started_at": null,
    "finished_at": null,
    "updated_at": "2026-11-20T13:48:16Z"
  }
}
```

The estimate is rough. `hours` is the time to save what is left at one
episode at a time (about 45 seconds per captioned video, or about 12 minutes
of local transcription per hour of podcast audio). `asr_hours_if_all` is the
most local transcription could add if no video had captions. `disk_mb` is the
transcripts and thumbnails (plus kept audio for podcasts).

Then `POST /shows/show_625ad0293689/start` with `{"asr": false}`.

### Follow it

`GET /shows/show_625ad0293689` while it runs:

```json
{
  "ok": true,
  "run": {
    "id": "show_625ad0293689",
    "state": "running",
    "reason": null,
    "counts": {"queued": 311, "running": 1, "done": 2, "failed": 1, "skipped": 2, "total": 317},
    "current": {"key": "yt:tp000000005", "title": "The Tidepool Hour episode 5",
                "url": "https://www.youtube.com/watch?v=tp000000005", "video_id": "tp000000005",
                "state": "running", "reason": null, "attempts": 0, "duration_seconds": 1805,
                "published_at": null, "updated_at": "2026-11-20T13:48:16Z"},
    "failures": [
      {"key": "yt:tp000000004", "title": "The Tidepool Hour episode 4",
       "url": "https://www.youtube.com/watch?v=tp000000004", "video_id": "tp000000004",
       "state": "failed",
       "reason": "No captions for this video, and local transcription is off for this save.",
       "attempts": 0, "duration_seconds": 1804, "published_at": null,
       "updated_at": "2026-11-20T13:48:16Z"}
    ],
    "failures_total": 1
  }
}
```

Fields left out above are the same as in the `ready` example.
`?episodes=1` adds every episode with its state and reason
(`&episodes_limit=8` for only the first eight). A saved episode's
`video_id` is its library id, so `GET /api/cues/v1/items/<video_id>` returns
its cues once it is `done`.

Run states: `listing`, `ready`, `running`, `waiting` (with `wait_until` and
`reason` `bot_check` or `rate_limited` from YouTube, or `host_busy` from a
podcast host), `paused` (by the user, or with a `reason` such as
transcription not being set up or the host failing five in a row), `done`,
`cancelled`, `failed` (the source could not be listed, with `reason`).

Other actions, all `POST` with a JSON body (`{}` is fine):

| Path | Does |
|---|---|
| `/shows/<id>/pause` | starts no more episodes (the one in flight finishes) |
| `/shows/<id>/resume` | carries on |
| `/shows/<id>/cancel` | stops the run: a queued episode leaves the download queue and a podcast download stops before transcription. An episode already publishing, or a podcast transcription already queued, finishes and is recorded (`current` shows it), and nothing starts after it |
| `/shows/<id>/retry-failed` | queues the failed episodes again, optionally with `{"asr": true}` |
| `/shows/<id>/dismiss` | removes a finished, cancelled or never-started run from the list |

Errors are `{ok: false, code, error}`: 400 `empty`, `invalid_url`,
`unsupported`, `invalid`; 404 `not_found`; 409 `invalid_state`, `needs_asr`
(a podcast feed started without local transcription) or `asr_unavailable`
(local transcription is not set up).
