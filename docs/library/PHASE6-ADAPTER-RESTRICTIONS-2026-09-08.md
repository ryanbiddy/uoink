# Phase 6 adapter restrictions: chapters, speaker turns, and fetch allow-lists (2026-09-08)

**Author:** grok · **For:** Astra's Phase 6 contract (`PHASE6-CONTRACT-2026-09-08.md`) and run BC implementers.
**Brief:** `PHASE6-BRIEF-2026-09-08.md` (run BB-grok). **Decisions:** 4, 5, 9 in `DECISIONS-2026-09-04.md`. **Prior policy:** `POLICY-MEMO-2026-09-04.md`, `PHASE3-ADAPTER-LIMITS-2026-09-07.md`.
**Not legal advice. No code, no helper, no port 5179, no live index, no model run, no commit.**

This note freezes, per source type, whether **chapters** and **speaker turns** exist at the source, what each in-repo adapter **may fetch** to obtain them under the existing allow-lists, what it **must not fetch**, and Twitch's **notify-only** boundary with its authorization and delivery unknowns. Every restriction cites an adapter file and line from the brief's list. Missing chapter or speaker data is explicit and is never inferred. A label such as `SPEAKER_00` is not an identity. Cross-video / cross-source speaker identity stays deferred.

It does **not** reopen accepted defaults: per-source opt-in default off; back-catalog ceiling 25; 10 starts per source per UTC day; detection (RSS/Atom) separable from capture (yt-dlp / enclosure); Twitch notify-only; X watching deferred; residential IP, low rate; optional diarization opt-in and off by default.

---

## 0. Summary matrix

| Source type | Adapter | Chapters at the source? | Speaker turns at the source? | Phase 6 may obtain them by | Phase 6 must not |
|---|---|---|---|---|---|
| YouTube video | `yt_extract.py` (CLI) + standing Atom in `source_subscriptions.py` | **Yes, sometimes.** Creator chapter markers (`start_time`, `end_time`, `title`) on the video. Absent on many videos. **Not** in the Atom detector feed. **Not** read by `yt_extract.py` today. | **No structured turns.** Captions are `(start, end, text)`. No speaker field. | Read `chapters` from the **already-fetched** yt-dlp metadata blob at capture. English caption tracks already on the allow-list. Local WhisperX diarization of already-downloaded audio, opt-in, default off — that is ASR, not a YouTube fetch. | New APIs, InnerTube, Data API, Atom-for-chapters, comment authors as speakers, inventing chapters from description text, expanding `sub-lang` past `en.*,en`, detector-time media. |
| Podcast episode | `podcasts.py` | **Not in the parsed feed.** RSS/Atom parse has no chapter element. Podcasting 2.0 `podcast:chapters` JSON may exist at some publishers; this adapter does not see it. | **Not in the feed.** Timed labels exist only after local WhisperX diarization of the enclosure. Show title is not a host. | Detection: RSS/Atom GET. Capture: the item's `enclosure` URL only, after consent. Speaker labels: local ASR of that file when `diarize=True`. | Episode-page scrape, `podcast:chapters` JSON, `itunes:block`-violating credentialed feeds, YouTube-as-podcast, non-http(s) enclosure, treating show title as a person. |
| X post / thread | `x_extractor.py` | **No.** Posts are ordered documents, not timed chapters. | **No timed turns.** `author_handle` is the account, not a speaker-in-time. | Public syndication JSON for the pasted `/status/` id, walking **up** the author's own chain. Optional FxTwitter full-text remains unofficial (policy: default-off). | GraphQL, Nitter, headless scrape, replies **below** the shared post, official X API watcher, treating thread posts as chapter rows or speaker turns. |
| X article | `x_article_extractor.py` | **No.** Long-form article, not timed media. | **No.** | Accept the extension's already-parsed DOM payload. **No network in this module.** | Helper fetch of `x.com/article/…` (login wall), syndication (does not serve articles), GraphQL. |
| Page | `page_extractor.py` | **No timed chapters.** HTML headings are document structure. | **No.** | GET an allow-listed `http(s)` host. Crawl4AI on-device, or stdlib HTML. | Hosts off the allow-list, `javascript:`/`file:`/…, third-party crawl APIs, follow-links deeper than 1, promoting headings to chapter rows. |
| Reddit thread | `reddit_extractor.py` | **No.** Heading levels encode comment depth. | **No timed turns.** `u/author` is the commenter. | Public `https://www.reddit.com/<path>.json` for a thread URL. | OAuth, subreddit listings, `more`/continue-thread fetches, deleted/removed bodies, comment authors as clip speakers. |
| Note | `notes.py` | **No.** User markdown is the body. | **No.** | Nothing. Persist the jotted text. | Any URL fetch, ASR, or inferred speakers/chapters. |
| Twitch | **None.** Not a `source_subscriptions` kind. | Out of scope. | Out of scope. | Notify-only EventSub **after** a verified authorization/delivery design. Nothing is ingested. | VOD/clip/HLS/chat/ASR, Helix `Get Streams` polling as a watcher, yt-dlp Twitch extractor, adding `twitch` to `KINDS`. |

---

## 1. Frozen meanings (so adapters are not asked for the wrong object)

**Chapter (Phase 6):** a timed range bound to one item and one source revision, with a title the **source** supplied (`start_time` / `end_time` / `title`). It is navigation metadata. HTML headings, Reddit comment-depth headings, X `## 1/N` thread posts, and note `#` titles are **not** chapters.

**Speaker turn (Phase 6):** a source-local label on a timed cue or clip (`SPEAKER_00`, or a caption voice tag if one survived parsing). It names a turn inside one media item. It is **not** an X handle, a Reddit username, a podcast show title, or a YouTube channel name. Cross-item identity is deferred (`PHASE6-BRIEF-2026-09-08.md`; `ASTRA-PHASE-PLAN-2026-09-04.md` Phase 6).

**Allow-list** here means the fetch classes the tree already permits, not a new Phase 6 permission:

| Class | Where it is encoded |
|---|---|
| Standing source kinds | `source_subscriptions.py:93` `KINDS = ("podcast_rss", "youtube_channel", "youtube_playlist")` |
| Page hosts | `page_extractor.py:82` `DEFAULT_ALLOW_SEEDS`; `page_extractor.py:352-431` `allowed_sites` |
| YouTube captions | `yt_extract.py:181-183` `--sub-lang en.*,en` |
| Podcast enclosure | `podcasts.py:382`, `1285-1318`, `1355-1364` |
| X post URL | `x_extractor.py:41-44` `_STATUS_RE` |
| X article URL | `x_article_extractor.py:32-37` `_ARTICLE_RE` |
| Reddit thread URL | `reddit_extractor.py:29-32` `_THREAD_RE` |
| Note | no URL class (`notes.py:10-13`) |

**Not an adapter fetch:** WhisperX diarization (`whisper_runner.py` `transcribe_audio(..., diarize: bool = False)`). It runs on a file already on disk. Default off (`server.py` setting `diarization_default: False`). Phase 6 may persist those labels when the run actually produced them (`diarization_ran`). It must not call diarization to invent source chapters, and must not treat a failed/off run as speakers.

---

## 2. YouTube video — `yt_extract.py`

### 2.1 What exists at the source

| Object | At YouTube? | In this adapter today? |
|---|---|---|
| Chapters | **Yes, when the creator set them** (player chapter markers / description timestamps). yt-dlp exposes `metadata["chapters"]` as `{start_time, end_time, title}`. Many videos have none. | **No.** `yt_extract.py` never reads a `chapters` key. The brief recorded this (`PHASE6-BRIEF-2026-09-08.md`). |
| Speaker turns | **No structured field.** Manual and auto captions are timed text. Voice tags, if any, are markup inside the cue. | `parse_srt` yields `(start, end, text)` only (`yt_extract.py:128`, `154-155`). HTML/markup is stripped (`yt_extract.py:153`), so a `<v Name>` voice tag would be discarded. |

The helper's **other** YouTube capture path (not this CLI) already GETs the metadata blob (`server.py:_fetch_metadata`, `--dump-single-json --no-download`) and already groups transcript markdown by `metadata.get("chapters")` (`server.py:4119`, `4165-4179`). That blob is also written to `metadata.json` in the yoink folder (`server.py:4354-4359`). Phase 6 chapter **rows** should be projected from that already-fetched object when present. That is not a new network class.

The standing detector does not see chapters. `YouTubeAtomAdapter.parse` keeps `yt:videoId`, title, watch URL, published time, and `channel_id` (`source_subscriptions.py:775-812`). Atom `videos.xml` has no chapter list (Phase 3 limits §3.1: duration is already absent).

### 2.2 What the adapter may fetch

| May | Cite | Bound |
|---|---|---|
| Video title via `yt-dlp --get-title` | `yt_extract.py:171-172` | Capture CLI only. Not a detector. |
| English human + auto captions and a low-res media file | `yt_extract.py:177-189`: `--write-auto-subs --write-subs --sub-lang en.*,en --convert-subs srt` plus `-f worst[height>=360]/worst` | Same language allow-list as helper capture. Residential IP, low rate (decision 4). |
| Parse those captions into timed cues | `yt_extract.py:213`, `128-158` | Text only. |
| **Reuse** chapters from a yt-dlp info JSON that capture **already** obtained | Not in `yt_extract.py`. Helper: `--dump-single-json --no-download`. | Reading a field off an existing blob is allowed. Adding a **second** metadata GET just for chapters is not required and must not become a detector call. |
| Local WhisperX on already-downloaded audio, if the user opted into diarization | Not this file. `whisper_runner.py:231` default `diarize=False`. | Source-local `SPEAKER_NN` labels only. `diarization_ran` must stay honest. |

### 2.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Treat `yt_extract.py` as a channel/playlist detector | Capture CLI; no listing. Phase 3 already forbade scheduler use. | `yt_extract.py:1-7`; `PHASE3-ADAPTER-LIMITS-2026-09-07.md` §4.1 |
| Pull chapters from Atom `videos.xml` | The detector does not emit them. Detection must stay metadata-only. | `source_subscriptions.py:798-805` |
| YouTube Data API (`videos.list`, `captions.download`, …) | Decision 4: do not wrap capture as an API client. Official `captions.download` is edit-gated. | Prior freeze in `PHASE3-ADAPTER-LIMITS-2026-09-07.md` §1, §3.2 |
| Extra InnerTube / `/youtubei/` / timedtext URLs beyond the existing yt-dlp capture command | `robots.txt` disallows `/youtubei/`. New scrapes reopen decision 4. | `yt_extract.py:177-189` is the allow-listed command; it has no `--write-info-json` and no extra extractor-args |
| Non-English tracks (`--sub-lang` other than `en.*,en`) | Language allow-list. | `yt_extract.py:183` |
| Comments as speaker or chapter evidence | Comments are a separate helper worker (`--write-comments`). Not this adapter; not a turn clock. | Out of `yt_extract.py` |
| Infer chapters from description timestamps when `chapters` is missing or empty | Missing data is explicit. | `yt_extract.py` has no description parser |
| Infer speakers from caption text (`>> JOHN:`) | Not a source-local label with a run id. | `yt_extract.py:153-155` |
| Cross-video speaker identity | Deferred. | Brief |
| Members-only, private, or live-only content the existing extractor already fails | Detector and capture already cannot see these. | Phase 3 §3.1 |
| `--sleep-interval`, cookies, PO-token flags as a "chapter fetch" change | Capture-posture change, not Phase 6. | Phase 3 §4.3 |

`yt_extract.py` also has no `--skip-download`, no rate-limit sleep, and no chapter walk in `combined.md` (it buckets captions by screenshot interval, `yt_extract.py:220-232`). Phase 6 must not "fix" that CLI by adding new endpoints. Persist chapters from the helper metadata blob; leave detector and CLI fetch sets unchanged.

---

## 3. Podcast episode — `podcasts.py`

### 3.1 What exists at the source

| Object | At the publisher? | In this adapter today? |
|---|---|---|
| Chapters | **Sometimes, outside our parse.** RSS 2.0/Atom have no core chapter element. Podcasting 2.0 `<podcast:chapters url="…" type="application/json+chapters">` and older `psc:chapters` exist in the wild. | **Not parsed.** `parse_feed_body` keeps guid, title, `audio_url`, episode page, duration, published, description (`podcasts.py:339-351`, `384-392`, `419-427`). `_ITUNES_NS` is declared (`podcasts.py:291`) and used only for duration (`podcasts.py:318-336`, `383`). No `itunes:block`, no `podcast:chapters`, no `podcast:person`, no `podcast:transcript`. |
| Speaker turns | **Not in the feed.** A minority of shows attach a transcript URL; this parser does not read it. Hosts are not a timed turn list. | Timed `speaker` is copied only from local transcript JSON (`podcasts.py:1007-1012`). Corpus markdown appends ` — {speaker}` when present (`podcasts.py:1106-1108`). Sidecar records `speakers` and `diarization_ran` (`podcasts.py:1146-1148`). **`host` is explicitly `None`:** "RSS core metadata identifies the show, not necessarily its host" (`podcasts.py:1135-1138`). |

Standing detection through `PodcastRssAdapter.parse` is the same shape: guid/link/atom id, title, page, enclosure URL, published, duration — still no chapters (`source_subscriptions.py:815-884`, metadata at `874-875`).

### 3.2 What the adapter may fetch

| May | Cite | Bound |
|---|---|---|
| RSS 2.0 / Atom 1.0 feed GET (conditional ETag / If-Modified-Since) | `podcasts.py:8-14`, `438-446`; standing twin `source_subscriptions.py:815-819` | Detection. Timeout 8 s (`podcasts.py:67`). UA `Uoink/3.1 (+https://uoink.video)` (`podcasts.py:71`). Cap 50 entries materialized (`podcasts.py:57`). |
| After consent + start reservation: the episode **enclosure URL only**, via yt-dlp `--extract-audio` after `--` | `podcasts.py:382` (RSS enclosure); `409-416` (Atom `rel="enclosure"`); `1285-1318` (http(s) gate); `1355-1364` (`--extract-audio --audio-format mp3 --max-filesize` 2 GiB, `--`, enclosure) | Capture. Not the episode page. Not YouTube. `auto_ingest` cannot bypass Phase 3 consent (`podcasts.py:239-250`). |
| Local WhisperX of that MP3, `diarize` default false | Transcript bridge `podcasts.py:980-1016`, `1068-1181`. Standing capture passes `diarize=bool(settings.get("diarization_default"))` with that setting false. | Speaker turns from this run only. Empty speakers when diarization is off or failed. |

Feed URL validation stays the existing conservative gate: http(s), no userinfo, no `javascript:`/`file:`/`data:` (`podcasts.py:78-119`).

### 3.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Episode page / show site HTML to invent chapters or hosts | Policy: "Download only the enclosure URL in the feed (no site scrape)." Parser already stores `episode_page_url` and must not GET it for Phase 6. | `podcasts.py:378-388`; `POLICY-MEMO-2026-09-04.md` podcast table |
| `podcast:chapters` JSON (or `psc:chapters`) | Tag is not in the parse allow-list. Fetching a second URL advertised in XML would be a **new** network class, even if http(s). Freeze as must-not until a later policy explicitly allows feed-advertised chapter files under the same SEC-01 `--` treatment as enclosures. | `podcasts.py:384-392`, `419-427` — fields enumerated, chapters absent |
| Publisher transcript URLs (`podcast:transcript`, etc.) | Same: not parsed; would skip local ASR provenance. | `podcasts.py:339-351` |
| Treat show title / feed title as a speaker or host | Sidecar already refuses that. | `podcasts.py:1135-1138` |
| YouTube `videos.xml` as a podcast (no enclosure → no audio_url) | Phase 3: do not route YouTube through enclosure download. | `podcasts.py:382`, `1309-1310`; `source_subscriptions.py:93` keeps the kinds split |
| Non-http(s) enclosure, option-injection, `file:` | SEC-01. | `podcasts.py:1285-1318`, `1363-1364` |
| Credentialed / private RSS uoink cannot auth | Skip; do not scrape the site. `itunes:block` is **still not parsed** (Phase 3 §4.4). Do not add a scraper to compensate. | `podcasts.py:339-434` has no `itunes:block` branch |
| Diarization without opt-in; inferring a single speaker when `diarization_ran` is false | Missing is explicit. | `podcasts.py:1146-1148` |
| Detection-time audio | Module and standing service never capture from detection. | `podcasts.py:3-6`; `source_subscriptions.py:19-21` |

---

## 4. X post / thread — `x_extractor.py`

### 4.1 What exists at the source

| Object | At X? | In this adapter today? |
|---|---|---|
| Chapters | **No.** A thread is a sequence of posts, not timed ranges inside one media item. | Markdown is `## {index}/{count}` over captured posts (`x_extractor.py:274-276`). Those headings are capture-scope labels, not Phase 6 chapters. |
| Speaker turns | **No timed turns.** Each post has an account. A self-thread is one author by construction of the walk. | `_shape_tweet` keeps `author_name` / `author_handle` / `text` (`x_extractor.py:208-223`). No start/end clock. |

Honest scope already in the module: syndication serves one post and links **upward** only; posts **below** the shared URL are unreachable without authenticated GraphQL (`x_extractor.py:10-15`, restated in render copy `270-272`).

### 4.2 What the adapter may fetch

| May | Cite | Bound |
|---|---|---|
| Public syndication JSON for a `/status/{id}` URL | `x_extractor.py:34` `SYNDICATION_URL`; `115-125` GET with token + `lang=en` | Paste-a-URL capture only. Decision 9: **watching deferred**. Not a standing source kind (`source_subscriptions.py:93`). |
| Walk the author's own parent chain, at most 25 hops | `x_extractor.py:39` `MAX_THREAD_HOPS`; `226-254` `collect_thread` | Same-author `in_reply_to_handle` only (`x_extractor.py:237-239`). Missing ancestor stops the walk; capture still succeeds (`x_extractor.py:249-250`). |
| Embedded `parent` payload when the id matches | `x_extractor.py:244-245` | Avoids a refetch; still syndication, not GraphQL. |

FxTwitter `api.fxtwitter.com/2/status/{id}` (`x_extractor.py:35`, `160-183`) is called today on every successful syndication fetch (`x_extractor.py:156-157`). That is **not** a published X interface. `POLICY-MEMO-2026-09-04.md` addendum: put it behind `fxtwitter_enrichment_enabled`, default **off**. Phase 6 must not depend on FxTwitter for chapters or speakers (it cannot supply either). It must not treat FxTwitter as identity.

### 4.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Authenticated GraphQL / "replies below" | Module forbids it; X ToS + developer rules: non-API automation is a permanent-suspension offense; liquidated damages. Watching stays deferred. | `x_extractor.py:10-15`, `270-272` |
| Nitter, RSS, headless browser, official X API as a watcher | Decision 9; Nitter dead. | `x_extractor.py` has no such client; `source_subscriptions.py:93` has no `x_*` kind |
| Article URLs through this adapter | Articles are not posts; syndication does not serve them. | `x_extractor.py:55-65` delegates to `x_article_extractor.is_x_article_url` |
| Video bytes / HLS of an X native video | Empty text+photo post is refused with "use the regular Uoink button" (`x_extractor.py:308-311`). That other path is yt-dlp `twitter:api=syndication` (`server.py:1516-1517`), still **not** this module, still no source chapters. | `x_extractor.py:308-311` |
| Promote thread posts to chapter rows or author handles to speaker turns | Wrong object. No clock. | `x_extractor.py:208-223`, `274-276` |
| Expand `MAX_THREAD_HOPS` or walk other authors' replies "for speakers" | Hostile-chain cap; GraphQL. | `x_extractor.py:39`, `237-239` |

---

## 5. X article — `x_article_extractor.py`

### 5.1 What exists at the source

Long-form article HTML. **No timed chapters. No speaker turns.** Author metadata is byline, not a turn list (`x_article_extractor.py:123-128`).

### 5.2 What the adapter may fetch

**Nothing on the network.** "No network happens here — the parsing already ran in the page" (`x_article_extractor.py:14-15`). `build_extract_result` validates a payload the extension already parsed (`x_article_extractor.py:82-136`). Allowed URL shapes: `/i/article/{id}` or `/{handle}/article/{id}` (`x_article_extractor.py:32-37`, `48-57`).

### 5.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Helper `urlopen` of the article URL | X login/nojs wall. Shared failure is `page_extractor._is_x_login_wall` → `code: "x_login_wall"` (`x_article_extractor.py:139-143`; `page_extractor.py:479-495`). | `x_article_extractor.py:139-143` |
| Syndication / FxTwitter | Those endpoints do not serve Articles (`x_extractor.py:56-59`). | `x_article_extractor.py:3-8` |
| GraphQL, headless, or a standing article watcher | Decision 9. | Not in `KINDS` (`source_subscriptions.py:93`) |
| Invent chapters from article headings or speakers from byline | Wrong object. | `x_article_extractor.py:118-136` returns markdown + author fields only |

---

## 6. Page — `page_extractor.py`

### 6.1 What exists at the source

A web document. **No timed chapters. No speaker turns.** `<h1>`–`<h6>` are document structure (`page_extractor.py:575-579` in the stdlib converter). `author_for` for generic pages is the **host** (`page_extractor.py:216-222`), which is a site identity, not a speaker.

### 6.2 What the adapter may fetch

| May | Cite | Bound |
|---|---|---|
| `http`/`https` URL with a valid host, no credentials, no `javascript:`/`data:`/`file:`/… | `page_extractor.py:309-349` `normalize_page_url` | Scheme allow-list. |
| Host on the **active** page allow-list | `page_extractor.py:82` defaults `youtube.com`, `youtu.be`, `x.com`, `twitter.com`; `352-431` `allowed_sites`; gate `457-462` | User-extensible. Default-on hosts are those four, not "the open web". |
| On-device Crawl4AI, or stdlib urllib GET | `page_extractor.py:10-11`, `435-478`, `597-615` | "No third-party API." Timeout 15 s, body cap 8 MB (`page_extractor.py:268-269`). |
| Optional screenshot when JS render is on | `page_extractor.py:515-516` | Not chapter/speaker data. |
| `follow_links_depth` 0 or 1 | `page_extractor.py:271-274`, `463-464` | Cap 1. |

Writing Studio may pass `enforce_allowlist=False` (`page_extractor.py:447-449`). Phase 6 must not use that bypass to harvest chapters/speakers from off-list hosts.

### 6.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Hosts not in `allowed_sites` | `host_not_allowed`. | `page_extractor.py:457-462` |
| Dangerous schemes / userinfo / junk hosts | Existing validator. | `page_extractor.py:322-340` |
| Cloud crawl APIs | Compute policy: on-device. | `page_extractor.py:10-11` |
| Depth-2+ crawls | Fan-out bound. | `page_extractor.py:271-274` |
| Persist X's login wall as content | Honest `x_login_wall`. | `page_extractor.py:277-301`, `479-495` |
| Promote HTML headings to Phase 6 chapter rows, or the site host to a speaker label | Wrong object. | `page_extractor.py:216-222`, `567-594` |
| Follow links off YouTube/X seeds "to find chapters" | Allow-list + depth cap. | `page_extractor.py:82`, `463-464` |

---

## 7. Reddit thread — `reddit_extractor.py`

### 7.1 What exists at the source

A post plus a comment tree. **No timed chapters.** Heading levels in the markdown are comment **depth** (`reddit_extractor.py:172-176`). **No timed speaker turns.** `author` is `u/name` on a comment (`reddit_extractor.py:114-118`). OP username is not durable identity; `page_extractor.author_for` prefers `r/{subreddit}` (`page_extractor.py:208-215`).

### 7.2 What the adapter may fetch

| May | Cite | Bound |
|---|---|---|
| Public `.json` of a thread URL matching `_THREAD_RE` | `reddit_extractor.py:3-4`, `29-32`, `44-58`, `61-74` | No API key, no OAuth. Host normalised to `www.reddit.com`. UA `uoink/1.0` (`reddit_extractor.py:24`). Timeout 20 s. |
| Flatten comments with depth + score limits | `reddit_extractor.py:25-27`, `97-126` | Depth default 4, score threshold 2, hard cap 500 comments. |

### 7.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| OAuth / official Reddit API | Adapter is the public `.json` endpoint only. | `reddit_extractor.py:3-4` |
| Non-thread URLs (listings, users, wikis) | `is_reddit_thread_url` / `canonical_json_url` return false/None. | `reddit_extractor.py:40-48` |
| `more` stubs / continue-thread / `morechildren` | Skipped: `kind != "t1"` continues. | `reddit_extractor.py:102-103` |
| Deleted or removed bodies | Skipped. | `reddit_extractor.py:105-107` |
| Comments below score threshold or past 500 | Caps. | `reddit_extractor.py:27`, `100-101`, `112-113` |
| Private / quarantined / rate-limited threads | 403/429 surfaced; nothing saved. | `reddit_extractor.py:76-84` |
| Treat `u/author` as a Phase 6 speaker turn or depth headings as chapters | No clock; wrong object. | `reddit_extractor.py:114-118`, `172-176` |
| A standing Reddit watcher | Not a `KINDS` value. | `source_subscriptions.py:93` |

---

## 8. Note — `notes.py`

### 8.1 What exists at the source

The user's own markdown (`notes.py:10-13`, `42-44`). **No chapters. No speaker turns.** Author defaults to `"You"` (`notes.py:49`, `109`).

### 8.2 What the adapter may fetch

**Nothing.** `build_note` / `persist_note` validate and write local files + an index row (`notes.py:89-123`, `126-211`). No `urlopen`, no yt-dlp, no allow-list host.

### 8.3 What it must not fetch

| Must not | Why | Cite |
|---|---|---|
| Any URL, feed, or media | A note is jotted text. | `notes.py:10-13`, `89-123` |
| ASR / diarization of a note | There is no audio path. | Module has none |
| Infer chapters from markdown headings or speakers from `author` | Title derivation strips heading markers for the **folder title** only (`notes.py:76-86`). That is not a chapter table. `author` is the user (`notes.py:109`). | `notes.py:76-86`, `109` |

---

## 9. Twitch notify-only — `source_subscriptions.py` (absence is the restriction)

Twitch is **not implemented**. Phase 6 must not grow chapters, speakers, clips, or corpus rows from Twitch. Decision 9 and the phase plan: notify-only; implementation waits for a **verified authorization/delivery design**. Encrypted sync and X watching remain out of scope.

### 9.1 In-repo boundary (what the tree actually allows)

| Restriction | Cite |
|---|---|
| Standing kinds are only `podcast_rss`, `youtube_channel`, `youtube_playlist`. There is no `twitch` kind, adapter, or register-source enum value. | `source_subscriptions.py:93` `KINDS`; `94-101` `ADAPTERS`; `324-334` `register_source.kind`; `887-892` `default_adapters` |
| `0028` CHECK matches that enum. Adding Twitch is a new migration, not a Phase 6 media-depth patch. | `migrations/0028_source_subscriptions.sql:11` (same three kinds) |
| The service "never captures from detection." Adapters return observations; capture runs only after a `started` ledger row. | `source_subscriptions.py:19-21` |
| Default `CaptureBackend.run` is `no_backend`. | `source_subscriptions.py:928-929` |
| YouTube URL parse accepts only youtube.com hosts; it cannot be overloaded for Twitch. | `source_subscriptions.py:533-534` |
| Caps 25 / 10 are unused for Twitch because **nothing is ingested**. | `source_subscriptions.py:63-64`; `POLICY-MEMO-2026-09-04.md` Twitch table |

### 9.2 What notify-only would be allowed to do (later, not this phase)

Policy freeze (`POLICY-MEMO-2026-09-04.md`; `THE-LIVING-LIBRARY-2026-09-04.md:145`):

- EventSub `stream.online` / `stream.offline` on **opted-in** broadcaster ids.
- Surface a "live now" notice.
- No VOD, clip, HLS, chat scrape, or ASR of Twitch.

Re-read 2026-09-08 of Twitch EventSub *Subscription Types* (https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#streamonline): `stream.online` v1 still exists. Quote: "The `stream.online` subscription type sends a notification when the specified broadcaster starts a stream." Authorization on **that type**: **"No authorization required."** That phrase means **no Helix scope on the event**. It does **not** mean "no app, no token, no transport."

Twitch ToS §7 still bans data mining and downloading except as expressly permitted (`POLICY-MEMO-2026-09-04.md`). Notify-only stays inside EventSub. VOD grab stays forbidden.

### 9.3 Authorization unknowns (block implementation until named)

These are unknown **to this product**, not unknown to Twitch's docs. Phase 6 must not guess them.

| Unknown | Why it blocks | What the vendor docs say (read 2026-09-08) |
|---|---|---|
| **Transport vs token class** | Webhook and WebSocket **reject the other token type** (`invalid transport and auth combination`). | *Managing Subscriptions* (https://dev.twitch.tv/docs/eventsub/manage-subscriptions/, page published 2026-09-03): WebSockets **must** use a **user** access token (if the event lists no scope, "create a user access token with no scope"). Webhooks **must** use an **app** access token. |
| **Webhook callback** | Helper is local. Decision 2 / Phase 4: no public tunnel for a scheduler. Twitch webhooks need HTTPS on port 443 plus a verification challenge. | EventSub overview: implement a webhook callback **before** subscribing. |
| **WebSocket session** | Fits "installed on the user's machine" better than webhooks, but needs a persistent `wss://eventsub.wss.twitch.tv/ws` client, a welcome `session_id`, subscribe-within-timeout, keepalive, reconnect, and a **user** token stored on disk. Uoink has none of that. | *Getting Events Using WebSockets* (page published 2026-09-03). |
| **Client ID / secret** | Helix `POST /helix/eventsub/subscriptions` needs a Twitch application. This repo has no Client ID, no secret store, no OAuth loop. | Create EventSub Subscription. |
| **Who authorizes** | "No authorization required" on `stream.online` is not "no user consent in uoink." Decision 5 still wants per-source opt-in. Unknown: is the user token the library owner's, and may it subscribe to **other** broadcaster ids? | Type docs vs product consent are different layers. |
| **Conduits** | Backend scale-out; need app tokens and shard bookkeeping. Wrong shape for a residential helper. | *Handling Conduit Events*. |
| **Revocation** | User-removed / `authorization_revoked` must not be silently ignored, and there is no receipt design yet. | WebSocket handling: subscriptions revoke on user removal or token revoke. |

Until those are designed and Ryan-authorized, **do not** add a Twitch adapter, a `twitch` kind, or a Helix client.

### 9.4 Delivery unknowns (block implementation until named)

| Unknown | Why it blocks |
|---|---|
| **Missed events while the helper is off** | WebSocket delivers only to a live session. Webhooks retry, then give up. No durable "was live at T" log exists. A GUI-only helper (decision 2) will miss goes-live. |
| **At-least-once duplicates** | EventSub resends. No `message_id` dedupe table exists. |
| **What "notify" writes** | No corpus item, no chapter row, no clip, no start ledger charge. Unknown: tray toast, dashboard chip, MCP resource, or all three — and the retention of "live now" after `stream.offline`. |
| **Pairing online/offline** | Two subscription types. Offline without a prior online, and the reverse, have no specified UI. |
| **VOD window** | Product text notes VODs expire in 7–60 days (`THE-LIVING-LIBRARY-2026-09-04.md:145`). Irrelevant to notify-only, and must not become a reason to download "before it expires." |
| **Helix `Get Streams` polling** | Looks like a local substitute. It is **not** EventSub, it is automated access, and it is **not** allowed as the watcher. |
| **yt-dlp Twitch extractor / HLS** | Capture. Forbidden. |

### 9.5 What Phase 6 must not fetch from Twitch (even "just for chapters/speakers")

No VOD, clip, HLS, chat log, emote set, or audio. No ASR. No scraping `twitch.tv`. No adding Twitch URLs to `page_extractor` defaults to "get chapters." No standing detector. Caps 25/10 do not authorize ingest.

---

## 10. Standing-source rule that applies to every kind above

`source_subscriptions.py` is the allow-list for **automatic** work:

1. Kinds: podcast RSS and YouTube channel/playlist Atom only (`source_subscriptions.py:93`).
2. Adapters return observations; they never download media (`source_subscriptions.py:19-21`, `775-812`, `815-884`).
3. Capture is an injected backend **after** a `started` row (`source_subscriptions.py:19-21`, `909-929`).
4. X, Reddit, pages, notes, Twitch are **not** standing sources. Paste/extension/jot capture stays on-demand.
5. Phase 6 chapter/speaker persistence must not piggy-back a new fetch onto detection polls.

---

## 11. Frozen rules for Astra's contract (without reopening defaults)

1. **YouTube chapters** = `chapters` on the yt-dlp metadata blob already obtained at capture, when that list is non-empty. `yt_extract.py` does not read them (`yt_extract.py:177-189`, `213`) and must not grow a new fetch to compensate. Atom detection must not grow a chapter fetch (`source_subscriptions.py:798-805`). Absent list → explicit missing.
2. **YouTube speaker turns** do not exist at the source. Captions stay `(start, end, text)` (`yt_extract.py:128-155`). Optional local diarization of already-downloaded audio is the only turn source; default off.
3. **Podcast chapters** are not available through `podcasts.py` as written. Do not GET episode pages or chapter JSON files (`podcasts.py:384-392`).
4. **Podcast speaker turns** come only from local transcript segments (`podcasts.py:1007-1012`, `1146-1148`). Show title is not a host (`podcasts.py:1135-1138`).
5. **X post/article/thread, page, reddit, note:** no Phase 6 chapters, no Phase 6 speaker turns. Do not recast authors, headings, or thread posts as those objects (`x_extractor.py:10-15, 274-276`; `x_article_extractor.py:14-15`; `page_extractor.py:457-462`; `reddit_extractor.py:102-103, 114-118`; `notes.py:10-13`).
6. **Twitch** stays notify-only and **unimplemented**. No kind, no adapter, no ingest (`source_subscriptions.py:93`, `19-21`). Authorization (token class × transport, Client ID, user vs app, local callback) and delivery (offline helper, dedupe, surface, no-VOD) are **unverified**. Helix polling and yt-dlp Twitch are not substitutes.
7. **Do not infer.** Missing chapter or speaker data is explicit. Re-extraction must not silently invent labels that old citations never had.
8. **Do not** enable diarization by default, expand caption languages, add Data API / GraphQL / `morechildren` / `podcast:chapters` clients, or put the helper on a public tunnel to receive EventSub webhooks.

---

## 12. Ambiguities this note resolves

| Ambiguity | Resolution |
|---|---|
| `yt_extract.py` vs helper `server.py` for YouTube chapters | The named adapter does not read chapters. The helper already fetches the info JSON that contains them. Phase 6 may persist that existing field. It may not add a new YouTube API or a detector fetch. |
| May we parse description timestamps when yt-dlp omitted `chapters`? | No. Missing is explicit. |
| May we keep SRT `<v Speaker>` as a source-local label? | Not from `yt_extract.py` as written: tags are stripped (`yt_extract.py:153`). Do not add a new caption-format scrape to recover them. |
| Are Podcasting 2.0 chapter files "just another enclosure"? | No, not under the current parse allow-list. Must not fetch until a later policy names that URL class. |
| Is the podcast show title a speaker? | No (`podcasts.py:1135-1138`). |
| Are X thread posts chapters? Reddit depth headings? Page `<h2>`? Note titles? | No. |
| Are X/Reddit authors speaker turns? | No. Account/commenter ≠ timed turn. |
| May FxTwitter be used for Phase 6 labels? | No. It has no chapters/turns; it is unofficial; policy wants it default-off. |
| May Phase 6 register Twitch as a source kind? | No. `KINDS` is closed (`source_subscriptions.py:93`). |
| Does `stream.online` "No authorization required" mean we can ship notify-only without OAuth design? | No. It means no **scope on the event**. Transport still needs an app or user token, and webhook vs websocket disagree about which. That design is not verified. |
| May we poll Helix `Get Streams` or yt-dlp Twitch until EventSub is designed? | No. |
| Does page allow-list default-on YouTube/X authorize standing watchers for those hosts? | No. Standing watchers are `KINDS` only. Page allow-list is on-demand `extract_page`. |

---

## 13. Sources (every limit)

| Claim | Source |
|---|---|
| Decisions 4, 5, 9 | `docs/library/DECISIONS-2026-09-04.md` |
| Twitch notify-only; no VOD; EventSub posture; X deferred; enclosure-only podcasts; yt-dlp residential | `docs/library/POLICY-MEMO-2026-09-04.md` (Twitch table re-confirmed against EventSub type page 2026-09-08) |
| Detector vs capture; Atom has no duration/chapters; `yt_extract.py` is capture-only | `docs/library/PHASE3-ADAPTER-LIMITS-2026-09-07.md` |
| Phase 6 objects; `yt_extract.py` does not read chapters; clips have no speaker/chapter field today; Twitch waits on auth/delivery design | `docs/library/PHASE6-BRIEF-2026-09-08.md`; `docs/library/ASTRA-PHASE-PLAN-2026-09-04.md` Phase 6 |
| `stream.online` v1, "No authorization required" on the **type** | https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#streamonline · read 2026-09-08 |
| Webhook = app token; WebSocket = user token; mix fails | https://dev.twitch.tv/docs/eventsub/manage-subscriptions/ · published 2026-09-03 · read 2026-09-08 |
| WebSocket endpoint `wss://eventsub.wss.twitch.tv/ws` | https://dev.twitch.tv/docs/eventsub/handling-websocket-events/ · published 2026-09-03 · read 2026-09-08 |
| In-repo adapters | `yt_extract.py`, `podcasts.py`, `x_extractor.py`, `x_article_extractor.py`, `page_extractor.py`, `reddit_extractor.py`, `notes.py`, `source_subscriptions.py` as cited |
| Clips still INSERT `speaker` as NULL | `clips.py:308-309`; `migrations/0024_clips.sql` "reserved; NULL in phase 1" (observation, not an adapter fetch) |
| Diarization default off | `whisper_runner.py:231`; `server.py` `diarization_default: False` |

Not measured this run: a live yt-dlp `chapters` payload, a live `videos.xml` body, a live EventSub handshake, FxTwitter, or any helper/index. Those remain prior-run claims where cited. No code, no commit.
