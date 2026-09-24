# Phase 3 adapter limits: YouTube detection without capture (2026-09-07)

**Author:** grok · **For:** Astra's Phase 3 contract (`PHASE3-CONTRACT-2026-09-07.md`) and run AM implementers.
**Brief:** `PHASE3-BRIEF-2026-09-07.md` (run AL). **Decisions:** 1, 4, 5, 9 in `DECISIONS-2026-09-04.md`. **Prior policy:** `POLICY-MEMO-2026-09-04.md`.
**Not legal advice. No code, no helper, no port 5179, no live index, no model run, no commit.**

This note freezes the **chosen YouTube standing detector** and the **documented limits** of every in-repo listing/capture adapter that could be mistaken for it. It does **not** reopen accepted defaults: per-source opt-in default off; back-catalog ceiling 25; 10 starts per source per UTC day; detection (RSS/Atom) separable from capture (yt-dlp); Twitch notify-only; X watching deferred; residential IP, low rate.

---

## 1. Chosen standing detector

**YouTube Atom video-feed pull** (HTTP GET of the same topic URL Google documents for Data API push notifications). Detection only: metadata. No video, no captions, no InnerTube, no yt-dlp.

| Kind | URL | Required key |
|---|---|---|
| Channel | `https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}` | Channel id (`UC…`), not `@handle` |
| Playlist | `https://www.youtube.com/feeds/videos.xml?playlist_id={PLAYLIST_ID}` | Playlist id from `list=` (`PL…`, `UU…` uploads playlist, etc.) |

**Cite (official identity + topic URL):** YouTube Data API, *Subscribe to Push Notifications*, last updated **2026-09-04 UTC**. Topic URL is `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`. Notification/entry identity is `<id>yt:video:VIDEO_ID</id>` plus `<yt:videoId>` and `<yt:channelId>` in namespace `http://www.youtube.com/xml/schemas/2015`. Push fires on upload **or** title/description update. URL: https://developers.google.com/youtube/v3/guides/push_notifications · read 2026-09-07.

**Cite (project choice):** `DECISIONS-2026-09-04.md` decision 4 ("Detection (RSS) and capture stay separable"); `THE-LIVING-LIBRARY-2026-09-04.md` §6 Watchers ("YouTube channel RSS (`youtube.com/feeds/videos.xml?channel_id=UC…`, 15 latest, verified live)"); `POLICY-MEMO-2026-09-04.md` "YouTube channel RSS (detection only)"; `ASTRA-PHASE-PLAN-2026-09-04.md` Phase 3 ("YouTube detector, with detection independent from capture").

**Not chosen** (still documented below so they are not silently reused):

| Adapter | Why it is not the standing detector |
|---|---|
| `yt_extract.py` | Capture CLI: downloads media + English subs. No listing. |
| `mobile_playlists._fetch_playlist_video_ids` / `poll_playlist` | yt-dlp InnerTube listing that **enqueues capture**. Defaults and caps disagree with decisions 4 and 5. |
| `server._fetch_playlist_preview` / `_fetch_channel_context` | On-demand yt-dlp listing for Playlist Mode / corpus enrichment, not a watcher. |
| YouTube Data API `playlistItems` / `search` / `videos.list` | Would make uoink an API client. Decision 4 and the 2026-09-04 memo: do not wrap capture or detection as a YouTube API client. |
| PubSubHubbub push of the same Atom topic | Official, but needs a **public callback URL**. The helper is local (decision 2). Phase 4 already forbids putting the helper on a public tunnel for a scheduler. Pull the feed instead. |
| `channels.py` HTML GET of `/@handle` or `/channel/id` | Self-channel verification only. Automated HTML fetch; not a detector. |

Playlist `?playlist_id=` is the same Atom resource family as the documented `?channel_id=` topic. Google's push guide names only `channel_id`. Phase 3 still uses the playlist form for standing playlist sources so detection stays RSS/Atom rather than yt-dlp.

---

## 2. Detection cursor (the id Astra must persist)

**Canonical item id = YouTube video id string**, compared for equality, independent of capture.

| Source | How to read it |
|---|---|
| Atom entry | Prefer `<yt:videoId>` (`http://www.youtube.com/xml/schemas/2015`). Else Atom `<id>` of the form `yt:video:{VIDEO_ID}` — strip the `yt:video:` prefix. **Cite:** push-notifications guide (section 1). |
| yt-dlp `--flat-playlist` (not the standing detector) | `entry["id"]` (`mobile_playlists.py:158-167`). |
| Podcast RSS/Atom (existing) | Episode `guid`, else item/entry link (`podcasts.py:327-354`). Unchanged. |

**Do not** key the cursor on Atom `<updated>` or `<published>`. The official push guide says title/description edits re-notify the **same** `yt:videoId`. Repeated discovery of that id is not a new start.

**Do not** use `server.py`'s `_VIDEO_ID_RE` (`^[A-Za-z0-9_-]{6,}$`, `server.py:5073`) as the cursor type. It is a URL parser, not a video-id type, and it would accept playlist ids.

Store the bare video id so an RSS cursor and a future listing cursor can share one table. Capture, when later reserved, canonicalizes to `https://www.youtube.com/watch?v={VIDEO_ID}` (`server.py:6378-6381`).

---

## 3. Limits of the chosen Atom pull

### 3.1 Window and completeness

| Limit | Value | Cite | Contract consequence |
|---|---|---|---|
| Documented pull `maxResults` | **None.** Google does not publish a page size for GET of `videos.xml`. | Push-notifications guide documents the URL and entry shape, not a count. | Do not invent a query param. |
| Observed window | **15 latest** public uploads (channel) / 15 latest playlist entries. | `THE-LIVING-LIBRARY-2026-09-04.md:145` ("15 latest, verified live"). **This run did not re-fetch a live `videos.xml`.** | First enrollment can fill at most `min(25, feed length)` ≈ **15**, not 25. Decision 5's 25 is a **ceiling**, not a fill quota the adapter can meet. |
| Pagination | None. No Atom `rel="next"`. | Push-notifications sample feed; Atom 1.0 has no YouTube next-page on this resource. | Older than the window is invisible to standing detection. |
| Identity churn | Same video id on title/description edit. | Push-notifications guide: notify on upload **or** title/description update. | Cursor is id-set, not "new `<updated>`". |
| `@handle` | **Not a feed parameter.** Topic URL requires `channel_id`. | Same guide: `channel_id=CHANNEL_ID` (Data API channel id). | Enrollment must obtain a `UC…` id before the first poll. Resolving `@handle` via HTML (`channels.py`) or yt-dlp is extra automated access, **out of this detector**. Reject `@handle`-only input at the registry until a `channel_id` is known. |
| Legacy `?user=` | Old username form, not `@handle`. | Not in the current push guide. | Do not accept it. |
| Visibility | Public uploads/entries only. | Consumer ToS + public feed. | Unlisted, private, members-only, scheduled-not-yet-public, live-only without a public VOD: not detected. |
| Shorts | Typically appear as ordinary `yt:videoId` entries when public. | Same feed; no Shorts filter in the documented schema. | Treat as ordinary items. Capture already accepts Shorts (`server.py:5107-5110`). |
| Community posts / tabs | Not in the video feed. | Push guide lists upload / title / description only. | Out of scope. |
| Enclosure / media URL | **None.** Entries have Atom `<link rel="alternate">` to `watch?v=` and `media:group` metadata, not an RSS 2.0 `<enclosure>` of the video file. | Push-notifications sample; RSS 2.0 enclosure is a different format (`https://www.rssboard.org/rss-specification`, read 2026-09-04). | **Do not** route YouTube detections through `podcasts.download_episode_audio`. Capture is the existing yt-dlp caption/media path **after** an atomic start reservation. |
| Duration | Not in the documented Atom sample. `podcasts.parse_feed_body` Atom branch sets `duration_seconds: None` (`podcasts.py:372`). | `podcasts.py:341-375`. | Detection records id, title, published, alternate link. Duration is a capture/metadata concern. |

**Back-catalog 25 vs RSS 15 is not a policy change and is not a defect in decision 5.** The 25-item cap remains the product ceiling (`DECISIONS-2026-09-04.md` #5; `podcasts.py:62` `AUTO_INGEST_BACK_CATALOG_CAP = 25`). YouTube Atom simply cannot saturate it. Filling the remaining ~10 with `yt-dlp --flat-playlist --playlist-end 25` would mix listing (InnerTube) into "detection" and reopen decision 4. **Do not do that in Phase 3.**

### 3.2 Terms, robots.txt, API overlay (re-read 2026-09-07)

Same posture as the 2026-09-04 memo. **No change that makes decision 4 untenable.**

| Fact | 2026-09-04 memo | Re-read 2026-09-07 |
|---|---|---|
| Consumer ToS date | 15 Dec 2023 | **Still 15 Dec 2023** ("Dated: December 15, 2023" / "Effective as of December 15, 2023"). https://www.youtube.com/t/terms?hl=en&gl=US&override_hl=1 |
| Automated-access ban | Permissions and Restrictions **(3)** | Unchanged: "access the Service using any automated means (such as robots, botnets or scrapers) except (a) in the case of public search engines, in accordance with YouTube’s robots.txt file; or (b) with YouTube’s prior written permission." |
| Download ban | Same section **(1)** | Unchanged. Detection does not download Content; capture still sits here. |
| Circumvention ban | Same section **(2)** | Unchanged. PO-token / botguard workarounds remain a capture risk, not an RSS risk. |
| Liquidated damages | Absent (contrast X) | Still absent. |
| `robots.txt` `User-agent: *` | `Disallow: /feeds/videos.xml` | **Unchanged**, fetched https://www.youtube.com/robots.txt 2026-09-07. Also still `Disallow: /youtubei/` (InnerTube; yt-dlp listing). A uoink watcher is not a public search engine, so exception (3)(a) does not apply. |
| API Services ToS | Last updated 2026-04-28 | **Still 2026-04-28 UTC.** https://developers.google.com/youtube/terms/api-services-terms-of-service |
| Developer Policies | Last updated 2026-06-24 | Page still dated 2026-06-24 (memo). III.D.7 undocumented APIs; III.E.1 no storing audiovisual content via the API. Channel RSS is **not** a Data API method. |
| Official caption download | `captions.download` requires edit permission | **Unchanged** ("This method is requires the user to have permission to edit the video."), scopes `youtube.force-ssl` / `youtubepartner`, last updated 2026-09-04 UTC. https://developers.google.com/youtube/v3/docs/captions/download · no third-party public-track path. |

**Posture (unchanged):** detection-only Atom pull, per-source opt-in, default off, 25 ceiling / 10 starts, residential IP. Poll on a **human RSS cadence** (minutes), not the 30-second scheduler tick. Do not follow into capture unless that source is opted in and a start is reserved.

September 2026 YouTube **creator** policy updates (branded-content labeling, first-frame view counting; https://support.google.com/youtube/answer/10008196) do not change consumer ToS (1)(2)(3) or this detector.

### 3.3 Rate posture for the Atom pull (decision 4)

Decision 4: status-quo capture from the home residential IP, **low rate**; detection and capture separable.

| Knob | Limit | Cite | Phase 3 rule |
|---|---|---|---|
| Scheduler tick | 30 s | `server.py:1684` `_PODCAST_FEED_TICK_SEC = 30`; `server.py:7274-7282` | Tick may **scan due rows**. Tick must **not** GET YouTube. |
| Network due-time | Podcast feeds: default 60 min, **min 15**, max 1440 | `podcasts.py:123-131`, `list_due_feeds` `podcasts.py:226` | **Reuse this for YouTube Atom.** Do not inherit monitored-playlist default 5 min / min 1 (`mobile_playlists.py:65`; `migrations/0013_monitored_playlists.sql` default 5). Policy memo: "minutes, not the 30-second podcast tick." |
| Conditional GET | ETag / If-Modified-Since | `podcasts.py:385-414` | Reuse. 304 is a successful empty poll (`podcasts.py:521-529`). |
| HTTP timeout | 8 s | `podcasts.py:67` `_FEED_FETCH_TIMEOUT_SEC = 8.0` | Tight XML GET. Do not use yt-dlp's 30 s listing timeout or the 30 min download floor. |
| User-Agent | `Uoink/3.1 (+https://uoink.video)` | `podcasts.py:71` | Identify the helper. Do not spoof a browser. 403s on UA are a visible feed error, not a reason to switch to yt-dlp. |
| Per-poll materialize cap (podcast parser) | 50 | `podcasts.py:57` `_EPISODES_PER_POLL_CAP = 50` | Non-binding for YouTube (~15). Product caps 25 / 10 still apply **after** parse, at enrollment / start reservation. |
| Daily starts | 10 / source / UTC day | Decision 5; `podcasts.py:63` | Capture ledger, not detection. Detection may see more ids than it is allowed to start. |
| Capture pacing (when a start is reserved) | 5 s sleep between playlist videos; 429 backoff 30→300 s; pending-queue 60 s × 2^n cap 15 min | `server.py:423-425`; `docs/v2-api.md` "Playlist pacing"; `server.py:4885` | Existing capture posture. Do not tighten or loosen here. |
| Guest / bot checks | Project 2026-09-04 claim: cloud IPs blocked; PO tokens ~12 h; ~300 videos/hour guest | `THE-LIVING-LIBRARY-2026-09-04.md:145` | **Not re-measured this run.** Applies to **capture** (yt-dlp), not Atom GET. Keep capture on the residential IP. Never from a datacenter IP (`POLICY-MEMO-2026-09-04.md`). |

---

## 4. In-repo adapters (limits, so they are not reused as the watcher)

### 4.1 `yt_extract.py` — capture only

| Limit | Value | Cite |
|---|---|---|
| Role | Per-URL transcript + screenshots. Not a channel/playlist detector. | Module docstring `yt_extract.py:1-17`. |
| Network | `yt-dlp --get-title` then `yt-dlp --write-auto-subs --write-subs --sub-lang en.*,en --convert-subs srt` plus a low-res video download. | `yt_extract.py:172-189`. |
| Languages | English (`en.*,en`) only. | Same. |
| Sleep / rate-limit / `--skip-download` | None. | Same. |
| Identity | Input URL, not a feed cursor. | CLI `url` arg. |

Do not call this from a scheduler.

### 4.2 `mobile_playlists.py` — listing that currently captures

Existing mobile → desktop playlist bridge. **Compute policy in the module docstring already says it auto-queues unseen videos** (`mobile_playlists.py:1-13`). That is capture, not detection.

| Limit | Value | Cite | Phase 3 conflict |
|---|---|---|---|
| Listing command | `yt-dlp --flat-playlist --dump-json --no-warnings --skip-download <playlist_url>` (docstring says `--dump-single-json`; code uses `--dump-json`) | `mobile_playlists.py:8-10, 126-139` | InnerTube / HTML. `robots.txt` disallows `/youtubei/`. Same ToS (3) as capture. |
| `--playlist-end` | **Not set.** Default is last item. | yt-dlp README: `--playlist-end NUMBER` "Playlist video to end at (default is last)"; `--flat-playlist` "Do not extract a playlist's URL result entries; some entry metadata may be missing". Pinned binary: yt-dlp **2026.07.04** (`docs/build-installer.md`). | Will try to enumerate the whole playlist (YouTube product max ~5,000). |
| Timeout | 30 s | `mobile_playlists.py:36-38` `_PLAYLIST_LIST_TIMEOUT_SEC = 30` | Large playlists fail or truncate. |
| New-per-poll cap | **50** | `mobile_playlists.py:40-42, 229-230` `_NEW_VIDEOS_PER_POLL_CAP = 50` | Above 25 and 10. Must not be the Phase 3 start cap. |
| Enabled default | **1 (on)** | `migrations/0013_monitored_playlists.sql:22` | Violates decision 5 default-off. Phase 3 consent defaults **off**. |
| Poll interval | Default **5** min, clamp **1–1440** | `mobile_playlists.py:65`; migration default 5 | Too hot for decision 4. Use podcast min 15 / default 60. |
| Cursor | JSON array `last_seen_video_ids` of **all** ids seen this pass (or captured ids when a taste filter is set) | `mobile_playlists.py:306-334`; migration comment "YouTube playlist max is ~5,000" | Coupled to capture/taste. Phase 3 cursor is detection-only video ids. |
| Side effect of `poll_playlist` | `idx.enqueue_pending(...)` when a URL normalizer is passed | `mobile_playlists.py:267-280` | Standing detector must **not** enqueue. Capture happens only after corpus-independent start reservation + consent. |
| Metadata | `id`, `title`, best-effort `channel`/`uploader`/`uploader_id`. Duration often missing under `--flat-playlist`. | `mobile_playlists.py:160-167`; yt-dlp `--flat-playlist` "some entry metadata may be missing" | Fine for listing; not needed if Atom is the detector. |
| Taste auto-uoink | Separate opt-in, default off | `server.py:836-844` `auto_uoink_enabled` | Out of Phase 3. Do not fold taste into source consent. |
| Background tick | **None.** Poll is HTTP `POST /playlists/monitored/poll` or `/auto-uoink/scan`. | `server.py:11303-11322`, `11372-11433` | Not proof a watcher exists (brief). |

YouTube playlist size: migration 0013 comment "~5,000"; YouTube Help, *Like or dislike a video*: "A maximum of 5,000 videos can be displayed in the Liked Videos playlist" (https://support.google.com/youtube/answer/6083270). Treat 5,000 as the product max the listing adapter can ever see.

`_normalize_playlist_url` (`server.py:5345-5368`) accepts any `list=` matching `^[A-Za-z0-9_-]{2,}$` on `/playlist` or `/watch`. That includes `WL` (Watch Later), `LL` (Liked), and mix/`RD…` ids. Those need cookies or are auto-generated. **Phase 3 standing sources: public `PL…` / channel uploads `UU…` only.** Reject `WL`, `LL`, `RD`.

### 4.3 Other yt-dlp usage in `server.py` (capture / preview)

Canonical command: `YTDLP_CMD = [sys.executable, "-m", "yt_dlp", "--extractor-args", "twitter:api=syndication"]` (`server.py:1510-1511`). Pin: **2026.07.04**.

| Call site | Flags | Limit | Role |
|---|---|---|---|
| Extraction download | `--write-auto-subs --write-subs --sub-lang en.*,en --convert-subs srt`, format `worst*[vcodec!=none]…`, `--max-filesize` 2 GiB, retries 10 | `server.py:1517, 4371-4400`; timeout floor 30 min, hard cap 2 h (`server.py:391-399`) | **Capture.** English captions first; media when needed. |
| Chunked long-video subs | `--skip-download --write-auto-subs --write-subs --sub-lang en.*,en` | `server.py:4437-4451`; timeout `COMMENTS_TIMEOUT_SEC` = 5 min | Capture, captions optional. |
| Playlist Mode preview | `--dump-single-json --flat-playlist` **no `--playlist-end`**, then cap **10** videos | `server.py:367` `PLAYLIST_VIDEO_CAP = 10`; `server.py:6390-6446` | Interactive capture job, not standing detection. Cap 10 is a **job** cap, coincidentally equal to the daily start cap but not a ledger. |
| Channel context (last 5) | `--dump-single-json --flat-playlist --playlist-end 5` on `{channel}/videos` | `server.py:2927-2944` | Best-effort enrichment at extract time. |
| Comments | `--write-comments --skip-download`, `youtube:max_comments=100` | `server.py:4024-4031` | Not detection. |
| Rate-limit handling | HTTP 429 → pending queue, initial 60 s, exp backoff cap 15 min; playlist job sleep default 5 s | `server.py:4868-4885, 423-425` | Capture only. |
| Bot / sign-in copy | "Sign in to confirm you're not a bot", captcha, members-only, live/premiere | `server.py:4898-4906` | Capture failures. Atom GET will not see members-only. |

yt-dlp listing options the repo **does not** pass today (and Phase 3 detection must not start passing): `--sleep-interval`, `--sleep-requests`, `--sleep-subtitles`, `--extractor-retries` overrides, cookies, PO-token flags. Adding them would be a capture-posture change, not a detector.

### 4.4 Podcast RSS (existing; YouTube must not pretend to be this)

Podcast detection is already the right shape: parse, persist ids, **do not** download until `auto_ingest` is on.

| Limit | Value | Cite |
|---|---|---|
| Formats | RSS 2.0 + Atom 1.0 | `podcasts.py:8-11, 312-375` |
| Enclosure | RSS `<enclosure url>` must be http(s); Atom `link rel="enclosure"` | `podcasts.py:330, 357-364`; RSS 2.0.11 `<enclosure>` (https://www.rssboard.org/rss-specification, read 2026-09-04) |
| First poll | Treated as back catalog; `auto_ingest_requested` left 0 until repair enrolls ≤25 | `podcasts.py:432-438, 672-680` |
| Daily starts | Inferred from `audio_downloaded_at` / `transcript_finished_at` / `jobs` timestamps | `podcasts.py:626-648` | Brief: replace with an atomic start ledger before concurrency. **Do not copy this inference.** |
| Download | yt-dlp `--extract-audio` of the **enclosure URL only**, after `--`, `--max-filesize` 2 GiB, timeout 600 s | `podcasts.py:809, 1201-1254` | SEC-01 repair: http(s) check + `--` separator. |
| `itunes:block` | **Not parsed.** | `parse_feed_body` has no `itunes:block` branch | Existing gap, not a 2026-09-07 policy change. Skip credentialed / blocked feeds when the publisher says so; do not scrape the show site. |
| Feed URL | http(s), no userinfo, no `javascript:`/`file:`… | `podcasts.py:78-119` | Keep. YouTube detector URLs are constructed from validated ids, not attacker feed XML. |

**If someone pointed `poll_feed` at `videos.xml` today:** Atom parse would succeed (`root_name == "feed"`), guid would be `yt:video:…`, `audio_url` would be `None`, duration `None`. Download would fail "episode has no audio_url". That is why YouTube needs its own detection path and the existing yt-dlp **capture** path, not podcast enclosure download.

---

## 5. Policy changes since 2026-09-04

| Surface | Change since the memo? | Affects Phase 3 detection / podcasts / D4? |
|---|---|---|
| YouTube consumer ToS | **No.** Still 15 Dec 2023. Restrictions (1)(2)(3) same text. | No. Decision 4 remains the accepted contract risk. |
| `robots.txt` | **No.** Still `Disallow: /feeds/videos.xml` and `/youtubei/` for `*`. | No. |
| API Services ToS | **No.** Last updated 2026-04-28. | No. |
| Developer Policies | **No** dated bump past 2026-06-24 in this re-read. | No. |
| `captions.download` | Page timestamp 2026-09-04 UTC; still requires edit permission. | No official third-party caption path. Capture stays yt-dlp. |
| Push-notifications / Atom topic | Page last updated 2026-09-04 UTC; same topic URL and `yt:videoId`. | Confirms the chosen detector's identity fields. Does **not** authorize PubSubHubbub from a local helper. |
| Creator/monetization policy (Aug–Sep 2026) | Branded content, view counting. | No. Not consumer ToS, not a watcher rule. |
| RSS 2.0 / podcast enclosure | Unchanged spec. | No. Podcast posture stands. |
| Twitch / X | Not re-opened. Decision 9 holds. | Out of Phase 3. |
| In-repo product policy | No later library memo amends D4/D5/D9. Phase 0 wired 25/10 into `podcasts.py` (`AUTO_INGEST_*`). | Implementers must **not** copy playlist-monitor defaults (enabled=1, 5 min, cap 50, enqueue-on-poll). |

**Would make decision 4 untenable (unchanged triggers):** ToS adding X-style liquidated damages; a written C&D against personal-library caption fetch; or a working official path that covers third-party captions. None of those landed between 2026-09-04 and this re-read.

---

## 6. Frozen rules for Astra's contract (without reopening defaults)

1. **Detector** = HTTP GET `videos.xml?channel_id=` or `?playlist_id=`. Identity = YouTube video id (`yt:videoId` / stripped `yt:video:`).
2. **Capture** = existing yt-dlp caption-first path, only after consent + atomic start reservation. Never from the detector.
3. **Consent** = per-source opt-in, default **off**. Do not inherit `monitored_playlists.enabled` default 1.
4. **Back catalog** = ceiling 25. YouTube Atom will typically enroll ≤15. That is adapter-limited, not a new product number.
5. **Daily starts** = 10 per source per UTC day, ledgered at **start**, not inferred from timestamps, not `_NEW_VIDEOS_PER_POLL_CAP`.
6. **Due-time** = podcast-class (min 15 min, default 60). Tick 30 s only scans due rows.
7. **No Data API client, no PubSubHubbub, no `@handle` poll, no yt-dlp backfill to chase 25, no X, no Twitch ingest.**
8. **Do not** reuse `podcasts.poll_feed` unchanged for YouTube (no enclosure). **Do not** reuse `mobile_playlists.poll_playlist` unchanged (it captures).
9. Failed Atom GET / 403 / parse error is a visible source-health failure; it does not spend a start. Failed yt-dlp download accounting is capture/ledger (Astra), not this note.
10. Watcher does no model reasoning (phase plan). Taste auto-uoink stays a separate default-off flag.

---

## 7. Ambiguities this note resolves

| Ambiguity | Resolution |
|---|---|
| Which in-repo adapter is "the" YouTube detector? | Neither `yt_extract.py` nor `mobile_playlists.py`. The detector is the Atom pull Google documents at `feeds/videos.xml`. Those modules are capture / coupled listing. |
| Channel vs playlist? | Same adapter, two query keys (`channel_id`, `playlist_id`). |
| What id does the cursor store? | Bare YouTube video id. |
| Can RSS meet the 25-item back-catalog? | No. Cap remains 25; feed window ~15. Do not backfill with yt-dlp. |
| May we use PubSubHubbub because it is official? | No. Local helper, no public callback, no tunnel. |
| May we use yt-dlp `--flat-playlist --playlist-end 25` at opt-in only? | Not in Phase 3. That is listing via InnerTube, not RSS detection. |
| May YouTube items flow through podcast enclosure download? | No. |
| Are playlist-monitor defaults the source-subscription defaults? | No. |
| Did ToS/robots change since 2026-09-04? | No, on this re-read. |

---

## 8. Sources (every limit)

| Claim | Source |
|---|---|
| Decisions 1, 4, 5, 9 | `docs/library/DECISIONS-2026-09-04.md` |
| RSS vs capture split; 15 latest verified | `docs/library/THE-LIVING-LIBRARY-2026-09-04.md` §6; `POLICY-MEMO-2026-09-04.md` |
| Atom topic URL, `yt:videoId`, title/description re-notify | https://developers.google.com/youtube/v3/guides/push_notifications · last updated 2026-09-04 UTC · read 2026-09-07 |
| Consumer ToS (1)(2)(3), dated 15 Dec 2023 | https://www.youtube.com/t/terms?hl=en&gl=US&override_hl=1 · read 2026-09-07 |
| `Disallow: /feeds/videos.xml`, `/youtubei/` | https://www.youtube.com/robots.txt · fetched 2026-09-07 |
| API Services ToS last updated 2026-04-28 | https://developers.google.com/youtube/terms/api-services-terms-of-service · read 2026-09-07 |
| `captions.download` still edit-gated | https://developers.google.com/youtube/v3/docs/captions/download · last updated 2026-09-04 UTC · read 2026-09-07 |
| RSS 2.0 enclosure | https://www.rssboard.org/rss-specification · read 2026-09-04 (unchanged) |
| yt-dlp `--flat-playlist`, `--playlist-end` default last, `--dump-json` | yt-dlp README / PyPI · pin 2026.07.04 (`docs/build-installer.md`) |
| In-repo constants | `yt_extract.py`, `mobile_playlists.py`, `podcasts.py`, `server.py`, `migrations/0013_monitored_playlists.sql` as cited |
| Playlist 5,000 display cap (Liked) | https://support.google.com/youtube/answer/6083270 |
| PubSubHubbub needs a public callback | Same push-notifications guide; rejected under decision 2 / Phase 4 no-tunnel |

Not measured this run: a live `videos.xml` body (would be running detection); yt-dlp guest-limit ~300/hour; PO-token lifetime. Those remain the 2026-09-04 project claims where cited.
