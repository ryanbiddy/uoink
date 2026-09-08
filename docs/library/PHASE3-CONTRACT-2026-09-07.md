# Phase 3 standing capture contract, 2026-09-07

Contract: `phase3-v1-2026-09-07`. Owner: Astra (`codex`). Integrator: Fable.
Reviewed base: `7fca0a840ef1586d3c7924643a45ab95a3785d97`.

Run AM must give every automatic capture a durable source consent decision and an
atomic start reservation. Discovery writes metadata independently. A capture can
start only while its source is on, within its daily allowance, and after its
enrollment boundary has been recorded. Successful capture leaves a visible unfiled
item and schedules Phase 2 assignment after corpus publication completes.

This is the codex deliverable for [run AL](PHASE3-BRIEF-2026-09-07.md), under
[the orchestration contract](ORCHESTRATION-V1-2026-09-04.md). It freezes the semantics
and proposed DDL below for implementation; it does not certify an implementation.
Acceptance gates are tests to write, not passed tests. No implementation, migration
file, model execution, helper execution, live-index access, or commit belongs to AL.

The accepted scope remains podcasts and YouTube channels/playlists, per-source
capture off by default, at most 25 back-catalog items per source, and 10 starts per
source per UTC day. The watcher performs no LLM reasoning. X watching stays out;
Twitch stays notify-only. Capture follows decision 4's existing low-rate residential
posture. Source opt-in does not enable optional AI features, authorize a model
download, select a taxonomy, or enable label application.

## Evidence and integration surfaces

These observations describe the reviewed source tree. None establishes that the
general subscription service already exists.

| Surface | Observed behavior and required integration |
|---|---|
| `server.py`, `_podcast_feed_scheduler_tick` (7245), `_poll_podcast_feed_for_watch` (7121) | A 30-second tick checks due feeds; polling then calls capture. Replace the standing-work coordinator with separate detection and capture passes. Keep distinct heartbeat, poll-success, poll-failure, and ingest-completion times. |
| `podcasts.py`, `poll_feed` (504), `_upsert_episodes_with_ids` (418) | Metadata identities are feed-scoped GUIDs. Poll success, episode insertion, and automatic eligibility currently commit separately. The subscription adapter must commit its observations and cursor together and must not let an old marker authorize capture. |
| `podcasts.py`, `count_daily_ingest_starts` (626), `repair_stranded_auto_ingest` (672) | Starts are inferred from download/transcript/job timestamps; enrollment counts all request markers together. Neither is the new ledger or lifetime back-catalog count. |
| `mobile_playlists.py`, `_fetch_playlist_video_ids` (126), `poll_playlist` (171) | The actual command uses `--flat-playlist --dump-json --skip-download`, with a 30-second timeout. Polling can enqueue directly. It limits new events to 50, then the plain path records all returned IDs as seen. The new detector must retain every accepted observation independently of which items can capture. |
| `podcasts.py`, `_episode_corpus_id` (849), `episode_to_corpus` (958) | Corpus identity derives from feed URL plus GUID. Files, item upsert, citations, and episode linkage have separate durable steps; publication needs reconciliation before classification. |
| `index.py`, `write_transaction` (486), `library_service` (509) | `BEGIN IMMEDIATE` supplies the database write boundary. Its lock alone does not make a subprocess launch or a separate queue commit atomic. |
| `migrations/0027_library_substrate.sql`; `library_work.py`, `prepare_run` (380) | Work requires a run, manifest, approved taxonomy, prompt hash, and frozen evidence packet. `prepare_run` builds these and rejects an existing run ID; it is not a generic idempotent enqueue API. |
| `assets/dashboard/index.html`, `renderPodcastFeedList` (10560), `setPodcastAutoIngest` (10652) | Existing controls report a boolean and metadata-only state; they do not show enrollment, reservations, or UTC allowance. Gemini owns the real flow and failure tests. |

Fable reserves `0028_source_subscriptions.sql`. The SQL in this document stays here
until the implementation dispatch. Claude owns the service, migration, server,
registry, and service tests in AM. Fable must also explicitly assign the necessary
`podcasts.py` and `mobile_playlists.py` adapter edits to that worker: the old paths
otherwise bypass the contract. Gemini owns the dashboard and its tests. Do not edit
`library_work.py`, `library_cards.py`, Phase 2 tests, prompts, or the proof harness.

Grok owns `PHASE3-ADAPTER-LIMITS-2026-09-07.md`; Gemini owns
`PHASE3-UI-TEST-PLAN-2026-09-07.md`. Neither file is present at the reviewed base.
The detector identities and capability requirements below are frozen locally;
Fable must reconcile them with Grok's collected note before dispatching AM. This
document makes no external platform-limit or policy-change claim on Grok's behalf.

## Source identity and detection

One `source_subscriptions` row represents one normalized source. Its `source_id`
is `src_` plus SHA-256 of UTF-8 `kind + "\n" + source_key`. The canonical key is the
normalized podcast feed URL, YouTube channel ID, or YouTube playlist ID. Display
names, titles, watch positions, and playlist ordering never change identity.
Re-adding an existing source returns that row and preserves its history and caps.
Removing a source archives it; physical deletion of consent, identities, or ledger
rows is outside this phase. Re-registration unarchives it with capture off.

| Kind / adapter | Observation identity | Frozen behavior |
|---|---|---|
| `podcast_rss` / `podcast_rss_v1` | Trimmed RSS GUID, or RSS item link when GUID is absent; Atom entry ID | Match the parser's existing identity fallback. A missing identity is rejected; titles, dates, and enclosure URLs are not substitute keys. Preserve the identity method in metadata. |
| `youtube_channel` / `youtube_channel_rss_v1` | Validated YouTube video ID from the channel feed (`yt:videoId`) | Accept canonical `/channel/UC…` URLs or channel-feed URLs carrying the same channel ID. Handle resolution, channel crawling, and extractor fallback are outside v1. |
| `youtube_playlist` / `youtube_playlist_flat_v1` | Validated `id` from the existing yt-dlp flat listing | Reuse the metadata-only listing seam. Reconstruct video URLs from validated IDs; never execute an entry-provided URL or command. Playlist removal/re-addition does not create a new capture identity. |

For v1 input validation, video IDs match `^[A-Za-z0-9_-]{11}$`, channel IDs match
`^UC[A-Za-z0-9_-]{22}$`, and playlist IDs use the existing allowed alphabet with a
local 2–200 character bound. These are accepted adapter input shapes, not guarantees
that any matching ID names an accessible source. Reject repeated `list` or
`channel_id` parameters, including identical repetitions. Podcast entry IDs are
opaque strings of 1–2,048 characters; reject control characters and invalid Unicode.

Channel and playlist observations of the same video share `capture_key =
youtube:<video_id>`. Podcast capture keys are `podcast:` plus SHA-256 of normalized
feed URL, newline, and entry ID. Preserve the current `episode_<suffix>` corpus ID;
check its full identity before linking so a truncated-hash collision becomes a
visible conflict. Different podcast feeds are not deduplicated by title or audio
URL. That would conflate independently identified episodes.

`source_items` is the durable set of observed entry IDs, with a unique
`(source_id, entry_id)` key. `item_id` is `si_` plus SHA-256 of `source_id`, newline,
and entry ID. A cursor consists of that set plus `source_detection_cursors`:
successful scan sequence, conditional-request validators, attempt/success times,
due time, and poll ownership. It is not a publication-date high-water mark or a
list of successful captures. An older publication discovered later is still an
observation. Duplicate IDs in one response collapse to one row; conflicting
metadata is reported and never creates a second item.

Every successful poll commits observations, enrollment effects, validators, and
cursor sequence in one write transaction. A crash commits all or none. Poll
failure leaves the success sequence and validators unchanged. A valid HTTP 304
advances successful-poll time and sequence but inserts no observations; an initial
or resume boundary requires an actual valid snapshot, so omit conditional headers
while that boundary is pending. An empty valid snapshot completes the boundary
with zero new entries. Malformed output never masquerades as an empty source.

Bind each poll to the consent epoch at claim time. If consent changed before its
result commits, retain validated observations as metadata but grant no eligibility
and complete no enrollment boundary from that stale poll. The next due poll uses
the current epoch. Persist each item's first-observed epoch (null when observed
off or through a stale poll) and prospective scan revision. A later complete poll
can grant future eligibility to previously staged partial observations only when
their first-observed epoch is still current and their prospective scan revision
has not yet been committed. This prevents both losing partial-batch discoveries
and relabeling an old off-period observation as new work.

The adapter reports `coverage = window | complete | partial | unknown`, observed
count, and truncation. `complete` describes that returned enumeration, not the
source's historical completeness. A bounded feed window can complete an enrollment
boundary; a truncated/partial extractor response cannot. Incomplete batches may
persist validated observations as metadata, but advance no success cursor or
enrollment and create no new eligibility. Keep the full durable identity set;
do not prune seen IDs to the latest response.

The podcast parser currently returns at most the first 50 entries, without sorting
them. The playlist's current 50-event cap is not a bound on extractor network work.
AM must expose those distinctions instead of presenting either as platform limits.
Use bounded response bytes, subprocess output, item count, and wall time, with
exact adapter budgets recorded in Grok's note and AM's fixtures. No silent
truncation, endless pagination, authentication escalation, or automatic switch to
media capture is permitted. The 25-item enrollment limit is always an upper bound;
it is not a promise that an adapter can discover 25 historical items.

## Consent and enrollment

Capture consent is `off` or `on`. Detection has a separate enabled flag and
continues while capture is off. Archiving disables detection and sets capture off.
Reads do not enroll, poll, start work, or change consent.

| Event | Durable change | Capture consequence |
|---|---|---|
| New source | `off`, revision 0, epoch 0, initial enrollment not completed | Metadata polling only. |
| Confirm off → on | Increment revision and epoch; store the bound receipt; set boundary to `initial` if never enrolled, otherwise `resume` | No new start until that boundary completes. |
| First valid initial snapshot while on | Choose at most 25 eligible, uncommitted observations; persist the exact cohort and complete initial enrollment | Cohort can start gradually under daily and rate limits. |
| Later normal snapshot while on | Newly observed, valid entries get `future` eligibility | Existing observations retain their original eligibility and outcome. |
| Confirm on → off | Increment revision; record receipt; clear pending boundary; release every unstarted reservation in the same transaction | No later reservation or transition to started is authorized by the old epoch. |
| Started work when switched off | Preserve charged ledger row and visible in-flight state | That already-started pipeline may finish and publish. Failure cannot launch another attempt while off. |
| Confirm off → on after initial enrollment | Increment epoch; complete one `resume` snapshot before new starts | Previously eligible unfinished items resume; previously unseen items in the boundary snapshot are metadata-only. Subsequent new observations can qualify as future items. |
| Same-state request | Record a no-change receipt, without incrementing revision or epoch | Never restarts enrollment or replenishes allowance. |

Initial enrollment is once per stable source identity, not once per toggle. Sort
eligible known observations by valid publication time descending, then first-seen
time descending, then entry ID ascending; missing/invalid dates sort after valid
ones. Apply the cap to the selected cohort, including items awaiting tomorrow's
allowance. Record each item's `eligibility = back_catalog`; never refill that
cohort because an item failed, was deleted, or became unavailable. Future eligibility
does not consume back-catalog slots. If the first snapshot has only eight usable
items, initial enrollment ends at eight.

The first snapshot includes known metadata plus the new boundary observations;
exclude deleted, already committed, or permanently invalid entries. Until it
arrives, the UI says enrollment is pending and shows "up to 25" (or the remaining
cap), not an invented exact count. `source_status` shows the current known candidate
count and coverage. Those counts are descriptive, not a frozen promise about the
next network response.

The resume boundary prevents an off period or outage from importing an unbounded
missed back catalog as "new." Items seen while off stay metadata-only. Existing
eligible items are held by source consent and resume without consuming more
back-catalog slots. No reset/backfill-more operation is exposed in v1.

Consent mutation requires a user-confirmed operation, the expected source revision,
and an operation key. Enabling also binds the displayed cursor revision; disabling
does not depend on cursor freshness. Use the same trusted local-session pattern as
Phase 2: the authenticated dashboard confirmation route mints a five-minute,
single-operation token. No registry tool mints tokens or trusts a supplied actor
string. The UI confirmation names the source, bounded enrollment, 10-start UTC
allowance, and what turning off does to current work. It is the source opt-in
itself, not an additional generic confirmation flow.

Token consumption, consent revision, releases, and the receipt commit atomically.
Identical retries from the same session and token return the original receipt,
including after token expiry if already consumed successfully. A changed request
under the same operation key conflicts. A stale request writes nothing. The UI
loads current status after a receipt retry so an old successful "on" receipt cannot
overwrite a later "off" display.

## Atomic starts, failure, and restart

An ingest start is the durable authorization immediately before the first capture
side effect: item-specific network acquisition, extraction, or transcription work.
Detection and reservation alone are not starts. A row can briefly reserve a daily
slot before dispatch, and the UI reports reserved and charged slots separately.

Each reservation owns one integer slot from 1 through 10 for its source and UTC
day. An occupied slot is any ledger row whose state is not `released`. A partial
unique index enforces `(source_id, utc_day, slot)`; slots plus serialized claims
prevent an eleventh allocation. Counts come exclusively from this ledger.

The claim transaction uses `BEGIN IMMEDIATE`, a bounded busy timeout, and a fresh
database read of consent, epoch, completed boundary, due time, item eligibility,
attempt limit, existing corpus identity, and active reservations. It chooses a free
slot, inserts `reserved`, and marks the item reserved. Concurrent connections must
either observe that result or return a retryable busy/capacity outcome. An in-memory
mutex or "count, then insert" outside the transaction is insufficient.

Ledger source/item/key, consent epoch, day, slot, and reservation time are immutable.
Set `started_at_ms` at most once and never clear it; terminal rows cannot be reset
to reserved. Owner replacement is a fenced recovery action, not another attempt
under an old slot. Test these service rules as well as the SQL constraints.

There is at most one active reservation per source and per global capture key.
If another source owns the same video, keep this observation eligible with reason
`capture_in_progress_elsewhere`; charge only the winning source. When that capture
commits, link all matching observations to it without starting or charging again.
An already committed corpus item is linked before reservation, also with no charge.
Keep the successful capture-key record after deletion to prevent automatic
rediscovery from resurrecting deleted content.

Also check committed/deleted `source_items` by capture key before a claim. They
preserve this rule for linked pre-existing captures that have no standing ledger
row. Corpus deletion marks every matching observation deleted; archive preserves
those records. Do not reconstruct a new capture obligation from a removed item.

| Ledger transition | Accounting and recovery rule |
|---|---|
| No row → `reserved` | Hold one current-day slot; no network or model activity. Reservation expires after 120 seconds if not dispatched. |
| `reserved` → `started` | Recheck current consent and epoch, same UTC day, item identity, and owner token in a write transaction. Set `started_at_ms`, increment the item's actual-start counter, and commit before dispatch. |
| `reserved` → `released` | Allowed only before `started_at_ms` exists: off, expiry, preflight failure, known duplicate, or day rollover. Keep the row and reason; release the active ownership and slot. |
| `started` → `succeeded` | Corpus publication is complete; retain the charged slot, global success identity, and item linkage. |
| `started` → `failed` | Definitive failure, with the old worker stopped. Release active ownership, retain the day's charge, and record retry eligibility. |
| `started` → `uncertain` | Worker outcome is unknown after restart or loss of heartbeat. Retain active ownership and the charge until reconciled. |
| `uncertain` → `succeeded` / `failed` | Verify committed artifacts or prove the old worker is stopped. Never start a replacement merely because a lease expired. |

"Release on failure" releases an unstarted slot or a failed attempt's active
ownership. It never refunds an actual start. Ten failed downloads still consume
the ten-start allowance. A retry after a real failure creates a new ledger row and
uses a new slot on its actual start day. Resuming local publication from already
validated output keeps the original attempt and charge; restarting acquisition or
transcription after failure is another start. Do not hide pipeline retries inside
the old pending-queue retry worker. Transport-level retries inside one bounded
adapter invocation must be declared in the adapter limits and must not reset its
total timeout; there is no unbounded re-invocation under one charge.

Automatic attempts stop after three actual starts per source item. Transient
failures wait at least 15 minutes after attempt one and 60 minutes after attempt
two, also respecting the source's capture due time and next UTC allowance. Terminal
errors (invalid identity, unsupported/private/deleted item, missing separately
approved transcription setup) remain visible and blocked. Three consecutive
preflight failures also block automatic retries until the underlying configuration
or item metadata changes; preflight failures do not use slots or actual attempts.
Off/on never clears actual attempt counts. A new retry/reset control is outside v1;
existing retry controls for a subscription-owned job must use the same reservation
guard and counters. Independent user-requested one-off captures retain their
existing consent semantics; they do not turn on standing capture.

Keep the existing 30-second scheduling cadence. As a contract policy, new sources
default to a 60-minute detection interval, adjustable from 15 to 1,440 minutes.
Existing shorter playlist intervals normalize to 15 minutes at cutover. Allow at
most one new start per source per configured interval, measured from its last
`started` transition, and one active pipeline per source. The daily cap is not a
target to exhaust in one burst. Releases before start do not advance this start
clock; repeated preflight failure has its own backoff.

All authoritative times use UTC Unix milliseconds from the server clock. The UTC
day is `YYYY-MM-DD` derived from the reservation time. Recheck it at dispatch: a
23:59:59 reservation cannot start at 00:00:01 with yesterday's slot. Release it and
claim a new row for today. A pipeline actually started yesterday may finish today
without charging again. A failed retry started today charges today. There is no
daily reset job and no deletion of yesterday's rows. Clock rollback must not move
a source's persisted due times backwards or reuse a newer observed day; return
`clock_regressed` until the clock catches up or an operator reconciles it.

The reservation itself is the durable dispatch intent. Persist its backend job
identity atomically with any durable queue insertion; use the start ID as the job's
idempotency identity. A queue API that commits independently cannot be used unchanged
for this step. The server worker must claim the owner token before executing and
must honor it on publication. Source-owned pending jobs must bypass the old generic
automatic retry/reset behavior. Jobs queued without a started marker cannot run
after consent is off.

On restart, reconcile before dispatching new work:

1. Recover committed source rows, cursors, and receipts. Do not reset consent,
   enrollment counts, daily slots, or retry counters.
2. Release expired/unstarted reservations, including old-day and old-epoch rows.
   Valid unstarted rows may be claimed once, within their original expiry and day.
3. Check the durable backend job and its process identity for started rows. An
   unknown or surviving owner remains `uncertain`/in flight. A timeout alone does
   not prove process death. Fence obsolete callbacks with the owner token.
4. Reconcile deterministic files, index row, provenance, citations, and clips.
   Complete local publication once when outputs are valid. Partial output without
   a usable completion record is failed after the owner is stopped; any renewed
   capture needs a fresh reservation and current consent.
5. Reconcile committed captures whose classification handoff is missing. Poll
   recovery and classification repair do not start a capture or a client.

These are process-crash guarantees to test. Power-loss durability is not claimed
without a separate storage/flush test. Complete loss of the subscription database
restores sources as capture off; corpus files and old boolean flags cannot recreate
consent, charged slots, or a successful-capture tombstone history.

## Scheduler and adapter boundaries

Each tick performs bounded local reconciliation, claims due detection work, and
advances eligible capture work independently. An exhausted capture allowance does
not stop detection. A poll failure does not erase earlier eligible work. Detection
failure updates `last_poll_attempt_ms`, error fields, and next due time, while
preserving `last_poll_success_ms`. A no-work tick is a heartbeat, not a successful
source poll or ingest.

Claim poll ownership and its 120-second lease atomically before network I/O. The
fetch runs outside the database transaction. Persist an owner token; reject late
results from an expired/replaced owner. A poll timeout records failure and schedules
another due time; two schedulers cannot dispatch the same due poll. Adapter total
wall-time budgets must fit the lease. Do not use the process-only
`_podcast_feed_poll_lock` as cross-process ownership.

For failure number `n`, the local backoff is
`min(1440 minutes, interval * 2^(min(n-1, 7)))`. A valid upstream Retry-After can
extend that delay; do not shorten it. A success schedules the next poll at
completion plus the interval. Bounded positive jitter may delay, never advance,
that due time. Manual refresh uses this same due-time/lease gate and returns
`not_due` with the persisted due time rather than triggering another fetch.

Adapters return validated observations, coverage, validators, and typed errors.
They do not call the capture queue, taste scorer, reasoning model, or classification
client. Existing playlist manual/taste scans and podcast watch routes must delegate
source-owned capture eligibility to the subscription service. Neither a global
auto-uoink flag nor `monitored_playlists.enabled` can override per-source consent.
Keep unrelated one-off capture entry points separate, but prevent them from racing
an active subscription capture of the same canonical item. The common dispatcher
must hold a cross-process execution lock per capture key, recheck the corpus after
acquiring it, and keep ownership through publication. Standing claims still require
their database reservation. A manual capture already holding that lock causes the
standing item to wait without starting; a completed manual capture is linked without
a standing charge. Surviving subprocesses still require the restart reconciliation
above before another invocation. Do not claim cross-process deduplication from a
Python thread lock alone.

Treat source text, IDs, URLs, and subprocess output as untrusted data. Registration
accepts only supported HTTP(S) forms, without credentials, fragments, control
characters, or ambiguous repeated identity parameters. Validate redirect targets
and resolved network addresses, not just the initial URL; reject loopback,
link-local, private-network, and non-HTTP targets in production. A loopback fixture
exception is allowed only through explicit test injection on the disposable AN
helper, never a registry parameter. Argument arrays, fixed options, and rebuilt
canonical YouTube URLs prevent shell/option injection. HTML-escape source text in
the UI; never treat feed text as instructions or as a user consent event.

## Migration 0028 schema

This DDL is normative for AM. Run through the existing migration transaction with
foreign keys enabled. All creates are repeatable. It creates no subscriptions,
consent, captures, taxonomies, or classification jobs by itself. Application
transactions enforce the cross-table state transitions described above; the SQL
constraints provide identity, slot, and active-ownership backstops.

```sql
CREATE TABLE IF NOT EXISTS source_subscriptions (
    source_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('podcast_rss','youtube_channel','youtube_playlist')),
    source_key TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    display_name TEXT,
    adapter TEXT NOT NULL CHECK(adapter IN
        ('podcast_rss_v1','youtube_channel_rss_v1','youtube_playlist_flat_v1')),
    legacy_feed_id INTEGER UNIQUE REFERENCES podcast_feeds(id),
    legacy_playlist_id INTEGER UNIQUE REFERENCES monitored_playlists(id),
    detection_enabled INTEGER NOT NULL DEFAULT 1 CHECK(detection_enabled IN (0,1)),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    consent_state TEXT NOT NULL DEFAULT 'off' CHECK(consent_state IN ('off','on')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision BETWEEN 0 AND 2147483647),
    consent_epoch INTEGER NOT NULL DEFAULT 0 CHECK(consent_epoch >= 0),
    boundary TEXT NOT NULL DEFAULT 'none' CHECK(boundary IN ('none','initial','resume')),
    initial_enrollment_completed_ms INTEGER,
    back_catalog_enrolled INTEGER NOT NULL DEFAULT 0 CHECK(back_catalog_enrolled BETWEEN 0 AND 25),
    poll_interval_min INTEGER NOT NULL DEFAULT 60 CHECK(poll_interval_min BETWEEN 15 AND 1440),
    capture_not_before_ms INTEGER NOT NULL DEFAULT 0,
    accounting_hold_until_ms INTEGER NOT NULL DEFAULT 0,
    last_observed_ms INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    UNIQUE(kind, source_key),
    CHECK(archived=0 OR (consent_state='off' AND detection_enabled=0)),
    CHECK(consent_state='on' OR boundary='none'),
    CHECK((kind='podcast_rss' AND adapter='podcast_rss_v1' AND legacy_playlist_id IS NULL)
       OR (kind='youtube_channel' AND adapter='youtube_channel_rss_v1'
           AND legacy_feed_id IS NULL AND legacy_playlist_id IS NULL)
       OR (kind='youtube_playlist' AND adapter='youtube_playlist_flat_v1' AND legacy_feed_id IS NULL))
);
CREATE TABLE IF NOT EXISTS source_consent_receipts (
    operation_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_subscriptions(source_id),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    session_hash TEXT NOT NULL,
    authority TEXT NOT NULL CHECK(authority IN ('local_user','legacy_explicit_opt_in','archive')),
    old_state TEXT NOT NULL CHECK(old_state IN ('off','on')),
    new_state TEXT NOT NULL CHECK(new_state IN ('off','on')),
    before_revision INTEGER NOT NULL,
    after_revision INTEGER NOT NULL CHECK(after_revision IN (before_revision,before_revision+1)),
    consent_epoch INTEGER NOT NULL,
    response_json TEXT NOT NULL CHECK(json_valid(response_json)),
    created_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_user_intents (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    source_id TEXT NOT NULL REFERENCES source_subscriptions(source_id),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    session_hash TEXT NOT NULL,
    expires_ms INTEGER NOT NULL,
    consumed_by TEXT UNIQUE REFERENCES source_consent_receipts(operation_key)
);
CREATE TABLE IF NOT EXISTS source_detection_cursors (
    source_id TEXT PRIMARY KEY REFERENCES source_subscriptions(source_id),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision BETWEEN 0 AND 2147483647),
    last_poll_attempt_ms INTEGER,
    last_poll_success_ms INTEGER,
    next_poll_at_ms INTEGER NOT NULL DEFAULT 0,
    etag TEXT,
    last_modified TEXT,
    coverage TEXT NOT NULL DEFAULT 'unknown' CHECK(coverage IN ('window','complete','partial','unknown')),
    observed_count INTEGER NOT NULL DEFAULT 0 CHECK(observed_count >= 0),
    truncated INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0,1)),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK(error_count >= 0),
    last_error_code TEXT,
    last_error_message TEXT,
    poll_owner_token TEXT,
    poll_consent_epoch INTEGER,
    poll_lease_expires_ms INTEGER,
    CHECK((poll_owner_token IS NULL AND poll_consent_epoch IS NULL AND poll_lease_expires_ms IS NULL)
       OR (poll_owner_token IS NOT NULL AND length(poll_owner_token)>=43
           AND poll_consent_epoch IS NOT NULL AND poll_lease_expires_ms IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS source_detection_due ON source_detection_cursors(next_poll_at_ms);
CREATE TABLE IF NOT EXISTS source_items (
    item_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_subscriptions(source_id),
    entry_id TEXT NOT NULL,
    capture_key TEXT NOT NULL,
    canonical_url TEXT,
    title TEXT,
    published_at_ms INTEGER,
    first_seen_ms INTEGER NOT NULL,
    last_seen_ms INTEGER NOT NULL,
    first_scan_revision INTEGER NOT NULL,
    first_seen_consent_epoch INTEGER,
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
    legacy_episode_id INTEGER REFERENCES podcast_episodes(id),
    eligibility TEXT NOT NULL DEFAULT 'none' CHECK(eligibility IN ('none','back_catalog','future')),
    enrolled_epoch INTEGER,
    state TEXT NOT NULL DEFAULT 'observed' CHECK(state IN
        ('observed','eligible','reserved','started','uncertain','committed','failed','deleted')),
    actual_starts INTEGER NOT NULL DEFAULT 0 CHECK(actual_starts BETWEEN 0 AND 3),
    preflight_failures INTEGER NOT NULL DEFAULT 0 CHECK(preflight_failures >= 0),
    retry_at_ms INTEGER,
    blocked_reason TEXT,
    video_id TEXT,
    committed_at_ms INTEGER,
    UNIQUE(source_id, entry_id),
    UNIQUE(source_id, item_id),
    CHECK((eligibility='none' AND enrolled_epoch IS NULL)
       OR (eligibility!='none' AND enrolled_epoch IS NOT NULL))
    -- No yoinks FK: retain identity/tombstone after corpus deletion.
);
CREATE INDEX IF NOT EXISTS source_items_capture_key ON source_items(capture_key);
CREATE INDEX IF NOT EXISTS source_items_ready ON source_items(source_id,state,retry_at_ms,first_seen_ms);
CREATE TABLE IF NOT EXISTS source_capture_starts (
    start_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    capture_key TEXT NOT NULL,
    consent_epoch INTEGER NOT NULL,
    utc_day TEXT NOT NULL CHECK(length(utc_day)=10),
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 10),
    state TEXT NOT NULL CHECK(state IN ('reserved','started','uncertain','succeeded','failed','released')),
    reserved_at_ms INTEGER NOT NULL,
    reservation_expires_ms INTEGER NOT NULL,
    started_at_ms INTEGER,
    finished_at_ms INTEGER,
    owner_token TEXT NOT NULL CHECK(length(owner_token)>=43),
    owner_instance TEXT NOT NULL,
    backend_kind TEXT,
    backend_id TEXT,
    release_or_failure_code TEXT,
    video_id TEXT,
    FOREIGN KEY(source_id,item_id) REFERENCES source_items(source_id,item_id),
    UNIQUE(backend_kind,backend_id),
    CHECK(reservation_expires_ms > reserved_at_ms),
    CHECK(utc_day=strftime('%Y-%m-%d',reserved_at_ms/1000,'unixepoch')),
    CHECK((state IN ('reserved','released') AND started_at_ms IS NULL)
       OR (state IN ('started','uncertain','succeeded','failed') AND started_at_ms IS NOT NULL)),
    CHECK(started_at_ms IS NULL OR
        (started_at_ms >= reserved_at_ms AND started_at_ms < reservation_expires_ms
         AND utc_day=strftime('%Y-%m-%d',started_at_ms/1000,'unixepoch'))),
    CHECK((backend_kind IS NULL AND backend_id IS NULL)
       OR (backend_kind IS NOT NULL AND backend_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS source_daily_slot ON source_capture_starts(source_id,utc_day,slot)
    WHERE state!='released';
CREATE UNIQUE INDEX IF NOT EXISTS source_one_active_source ON source_capture_starts(source_id)
    WHERE state IN ('reserved','started','uncertain');
CREATE UNIQUE INDEX IF NOT EXISTS source_one_active_capture ON source_capture_starts(capture_key)
    WHERE state IN ('reserved','started','uncertain','succeeded');
CREATE INDEX IF NOT EXISTS source_starts_item ON source_capture_starts(item_id,reserved_at_ms);
CREATE TABLE IF NOT EXISTS source_classification_policy (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    version_id TEXT NOT NULL REFERENCES shelf_versions(version_id),
    prompt_hash TEXT NOT NULL CHECK(length(prompt_hash)=64),
    configured_by TEXT NOT NULL,
    configured_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_classification_outbox (
    capture_key TEXT PRIMARY KEY,
    video_id TEXT NOT NULL UNIQUE,
    committed_at_ms INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','waiting_configuration','enqueued','blocked')),
    run_id TEXT UNIQUE,
    version_id TEXT REFERENCES shelf_versions(version_id),
    prompt_hash TEXT CHECK(prompt_hash IS NULL OR length(prompt_hash)=64),
    source_revision TEXT CHECK(source_revision IS NULL OR length(source_revision)=64),
    work_id TEXT REFERENCES library_work(work_id),
    last_error_code TEXT,
    updated_at_ms INTEGER NOT NULL,
    CHECK(state!='enqueued' OR (run_id IS NOT NULL AND work_id IS NOT NULL)),
    CHECK((run_id IS NULL AND version_id IS NULL AND prompt_hash IS NULL AND source_revision IS NULL)
       OR (run_id IS NOT NULL AND version_id IS NOT NULL AND prompt_hash IS NOT NULL AND source_revision IS NOT NULL))
    -- Retain blocked records after item deletion; do not cascade a handoff away.
);
CREATE INDEX IF NOT EXISTS source_classification_pending ON source_classification_outbox(state,committed_at_ms);
```

Import existing registries in an idempotent, local startup reconciliation before
any scheduler or pending worker can launch. This is application data conversion,
not SQL that guesses identities from URLs. Preserve legacy row IDs and source URLs;
record conflicts rather than merging different feeds by title. The new tables
become authoritative; old flags/cursors are compatibility projections and must not
become a second scheduler authority.

An existing podcast `auto_ingest=1` is an explicit per-feed opt-in: preserve it as
on with a `legacy_explicit_opt_in` receipt and initial boundary pending. Do not infer
playlist consent from `enabled=1` or a global taste setting; imported playlists are
off. Import known metadata and committed links without capture. Existing unstarted
podcast markers do not enlarge the new initial cohort beyond 25. Existing started
legacy jobs require reconciliation before another attempt; do not invent start
timestamps or charges from their latest update time.

For every imported source, hold new starts until the next UTC day after cutover
and until legacy active jobs are reconciled. The status reports
`legacy_accounting_hold` and its expiry separately from the new ledger's counts.
This avoids presenting timestamp inference as accurate remaining allowance for
the cutover day. Migration/reconciliation reruns must preserve the original hold,
receipt, and boundary; they never postpone the hold by another day or reenroll a
cohort. Disabled legacy detection stays disabled, independently of retained capture
consent. Old delete routes must archive the source and preserve referenced rows.

## Post-commit classification handoff

The durable capture row exists before work begins, so it also records the obligation
to finish or reconcile publication. Use deterministic artifacts and corpus identity.
Publish corpus/sidecar, index content, valid provenance, citations, and clips through
the existing pipeline. Verify each required step and its commit before reporting
capture complete. Missing clips are legitimate only where there is no timed evidence;
never synthesize timing to satisfy a gate.

After publication commits, a separate write transaction marks the item committed,
the ledger succeeded, and inserts its outbox row with `INSERT OR IGNORE`. An outbox
failure cannot roll back published content: leave it visible as unfiled and let
restart reconciliation repair the missing handoff from the capture record. A crash
after files or the item upsert but before citations/clip completion must finish or
flag that partial publication before creating classification work.

Linking a pre-existing corpus item does not create a new classification request.
Its existing Phase 2 state remains authoritative; if it has no assignment work,
the source view reports `not_requested`. Only a capture record owned by this
subscription pipeline establishes a new outbox obligation.

The outbox dispatcher runs deterministic local service calls only:

1. Read an explicit `source_classification_policy` binding to an approved/active,
   immutable taxonomy and approved assignment prompt hash. Only a trusted operator
   can configure this singleton; source consent cannot set it. No policy means
   `waiting_configuration`, visible with the unfiled item. Do not seed taxonomy,
   select an arbitrary previous run, or change prompts during AM.
2. After checking the committed evidence card, freeze `version_id`, `prompt_hash`,
   source revision, and deterministic `run_id = ss_` plus SHA-256 of the capture key
   in the outbox. One source capture creates one single-item run. Never append to a
   measured or existing frozen Phase 2 manifest.
3. Outside that write transaction, call
   `index.library_service().prepare_run` with trusted operator `RequestContext`,
   the frozen run/version/prompt IDs, and `video_ids:[video_id]`. This uses existing
   Phase 2 packet validation and creates the run, manifest, and assignment work.
4. Read the resulting run and work and verify the video, taxonomy, prompt policy,
   and source revision against the outbox binding before marking it enqueued.
   If a concurrent dispatcher or previous crash already created that exact run,
   the existing service returns `idempotency_conflict`; adopt it only after these
   checks. A mismatched run is `classification_conflict`, never overwritten.
5. A crash between steps 3 and 4 recovers by inspecting the deterministic run ID;
   it does not create another run. An evidence revision change, deletion, pin,
   recovery conflict, or unavailable service yields a visible blocked handoff or
   the Phase 2 accounted disposition. It never authorizes recapture.

`ready` assignment work without a current client lease displays
`waiting_for_client`; capture is still complete and the item remains unfiled.
Do not claim that a client process is offline solely from absence of a lease.
The watcher never spawns a client, claims model work on its behalf, submits labels,
or enables apply. Existing Phase 2 retry, pin, preview, and application rules remain
in force. AN's happy-path fixture must configure a valid approved taxonomy/prompt
binding so the gate checks a real ready work row, not merely an outbox placeholder.

## Registry and dashboard contract

Public registry tools are `list_sources`, `register_source`, `source_status`, and
`set_source_consent`. Both HTTP and MCP adapters call the same service with trusted
transport context. Input schemas below follow the Phase 2 envelope and JSON Schema
2020-12 dialect. Each `inputSchema` is self-contained. No client supplies capture
caps, actor privileges, adapter commands, source paths, or clock values.

```json
{
  "contract_version": "phase3-v1-2026-09-07",
  "json_schema_dialect": "https://json-schema.org/draft/2020-12/schema",
  "tools": [
    {
      "name": "list_sources",
      "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
          "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
          "consent_state": {"enum": ["off", "on"]},
          "include_archived": {"type": "boolean", "default": false},
          "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
          "cursor": {"type": "string", "minLength": 1, "maxLength": 512}
        },
        "additionalProperties": false
      }
    },
    {
      "name": "register_source",
      "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
          "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
          "url": {"type": "string", "minLength": 1, "maxLength": 2048},
          "display_name": {"type": "string", "minLength": 1, "maxLength": 200},
          "poll_interval_min": {"type": "integer", "minimum": 15, "maximum": 1440, "default": 60}
        },
        "required": ["kind", "url"],
        "additionalProperties": false
      }
    },
    {
      "name": "source_status",
      "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
          "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
          "item_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
          "item_cursor": {"type": "string", "minLength": 1, "maxLength": 512}
        },
        "required": ["source_id"],
        "additionalProperties": false
      }
    },
    {
      "name": "set_source_consent",
      "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
          "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
          "consent_state": {"enum": ["off", "on"]},
          "expected_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
          "expected_cursor_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
          "operation_key": {"type": "string", "minLength": 1, "maxLength": 200, "pattern": "^[A-Za-z0-9_-]+$"},
          "user_intent_token": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43,128}$"}
        },
        "required": ["source_id", "consent_state", "expected_revision", "operation_key", "user_intent_token"],
        "oneOf": [
          {"properties": {"consent_state": {"const": "on"}}, "required": ["expected_cursor_revision"]},
          {"properties": {"consent_state": {"const": "off"}}, "not": {"required": ["expected_cursor_revision"]}}
        ],
        "additionalProperties": false
      }
    }
  ]
}
```

Schema validation is strict: reject duplicate JSON keys, malformed Unicode,
non-finite numbers, boolean-as-integer coercion, unknown fields, oversized bodies
(16 KiB), and nesting deeper than 16. URL semantic validation follows the adapter
boundary above; a JSON string alone is insufficient. Reject malformed/foreign
pagination cursors; bind them to filters and source identity. Order sources by
`source_id` and source items by `(first_seen_ms, item_id)` with keyset pagination.
Reads return a consistent transaction snapshot; cursors are not user-controlled
SQL or offsets into an unbounded result.

`register_source` creates only the off row and its due cursor, with no immediate
network I/O. A duplicate canonical source returns `created:false` and its existing
configuration without silently changing interval, name, or consent. Unarchiving
returns the same source with capture off and a receipt; it cannot replenish history.
The registry exposes no force-poll, bulk enable, arbitrary retry, limit override,
or delete-history tool. Existing refresh/archive UI routes use the same service.

Every success contains `ok:true`, `schema_version:1`, and
`contract_version:"phase3-v1-2026-09-07"`. Required response fields are:

| Operation / object | Required fields and meaning |
|---|---|
| `list_sources` | `sources:[summary]`, `next_cursor` (string or null), `as_of_ms`. |
| `register_source` | `created` (boolean), `source` (summary); validation errors create no row. |
| `source_status` | `source` (summary), `items`, `next_item_cursor`, `as_of_ms`. Include all active reservations separately as `in_flight`, even when the item page does not contain them. |
| `set_source_consent` | `operation_key`, `changed`, `source_id`, before/after revision, `consent_state`, `consent_epoch`, `boundary`, `released_reservations` (count), `in_flight` (IDs/states), and `recorded_at_ms`. This is the stored mutation receipt; current status is a separate read. |
| Source summary | Stable ID, kind, canonical URL, display name, adapter, consent state/revision/epoch, detection enabled, archived, interval, boundary; `enrollment`, `allowance`, `detection`, and item counts by state. |
| `enrollment` | `cap:25`, `enrolled` (0–25), `initial_completed` (boolean), `known_candidates` (count), `pending` (boolean), `remaining_initial_slots` (0 after initial completion), `coverage`. |
| `allowance` | `utc_day`, `cap:10`, `reserved`, `charged`, `remaining=max(0,10-reserved-charged)`, `resets_at_ms` (next midnight), `capture_not_before_ms`, and `hold_reason`/`hold_until_ms` (nullable). Held capacity must not display as startable allowance. |
| `detection` | Cursor revision, last attempt, last success, next due, observed count, coverage, truncation, consecutive failures, and nullable sanitized error `{code,message}`. |
| Item / in-flight record | Item ID, entry ID, safe title/URL, eligibility, capture state, blocked reason, actual attempts, retry time, nullable start ID, charged UTC day, video ID, committed time, classification state and work ID. Never return owner tokens, queue internals, paths, or transcript bodies here. |

Nullable timestamps and IDs are explicitly `null`; counts are nonnegative integers;
flags are booleans. `charged` counts rows with a non-null `started_at_ms` for the
requested source/day, including failures and uncertain work. `reserved` counts
unreleased, unstarted rows. Classification display is one of `not_captured`,
`pending`, `waiting_configuration`, `waiting_for_client`, `leased`, `accepted`,
`unmapped`, `unsupported`, `blocked`, or `cancelled`, derived from the outbox and
current Phase 2 row; `not_requested` denotes a pre-existing capture without work.
`accepted` describes staging, not applied shelving.

Errors use `{ok:false,schema_version:1,contract_version,error:{code,message,
retryable,details}}`. Codes are `validation_error`, `not_found`, `unsupported_source`,
`source_archived`, `user_intent_required`, `invalid_user_intent`, `stale_revision`,
`stale_cursor`, `idempotency_conflict`, `invalid_cursor`, `storage_busy`,
`service_unavailable`, and `internal_error`. Stale errors return current revisions;
retrying requires a refreshed view and renewed intent. Poll/capture operational
states such as `allowance_exhausted`, `not_due`, `legacy_accounting_hold`,
`clock_regressed`, `feed_unreachable`, `download_failed`, `recovery_required`, and
`classification_conflict` live in source/item status; reading a failed source is
still a successful read. Sanitize error messages to 512 characters; no raw SQL,
subprocess stderr, secret-bearing query strings, or local paths enter public data.

The dashboard-only `POST /sources/consent-intent` accepts
`{"operation": <set_source_consent arguments without user_intent_token>}`. Validate
the same schema with only that token field omitted, bind canonical request hash,
source/cursor revisions and authenticated session, and return the token, expiry,
and display summary. This route requires the established local-user confirmation,
origin/CSRF checks, and authentication. It is not an MCP tool. Mutations through
HTTP and MCP consume the same capability and receipt. Source creation and read
authentication do not confer authority to mint consent tokens from feed content.

## Acceptance gates to implement and run

AM uses temporary fixture databases and fake adapters/clock/queue workers. AN reruns
the affected suites on Fable's integrated candidate SHA and adds the controlled
disposable-helper flow from the brief. Astra reviews the integrated implementation,
including deduplication, reservations, restarts, and conflict resolutions. No worker
base result certifies the integrated candidate.

| Gate / test to write | Fixture and expected observation |
|---|---|
| S01 migration and rerun | Empty database through 0027 and populated legacy registries; run 0028 twice through the real migration runner. Identities/FKs/indexes survive, no automatic work is created, and imports preserve their first receipt/hold. |
| S02 default off and legacy conversion | New RSS/channel/playlist, old podcast opt-in, old enabled playlist, global taste on. Only explicit old podcast consent transfers; cutover hold is visible; a global flag cannot start an off source. |
| S03 initial cohort | 80 known entries with valid/invalid/tied dates, precommitted/deleted items, and an adapter returning a limited window. Exact deterministic cohort is at most 25, never refills after failure/deletion, and reports coverage. Empty initial response enrolls zero. |
| S04 durable off/on/off | Confirm on, restart, complete initial boundary, reserve, switch off, restart again. Consent receipts persist; all unstarted reservations release; no old-epoch dispatch succeeds. Duplicate on does not enroll again. |
| S05 in-flight revocation race | Pause immediately before and after the started transaction; race off against start on two connections. Off wins: zero dispatch. Start wins: one charged pipeline can complete visibly while source is off. Failure while off cannot retry. |
| S06 resume gap | Poll while off, miss several polls, then reenable. First resume snapshot marks unseen gap items metadata-only; prior eligible work resumes; genuinely new later IDs become future-eligible. Old cohort count stays fixed. |
| S07 durable independent detection | Reordered/repeated feed and playlist IDs, 60 valid observations with capacity for one capture, removal/re-addition, missing identity, conflicting duplicate IDs, and capture-enqueue failure. Complete a partial batch and change consent during a delayed poll. No lost observations, stale-epoch eligibility, duplicate capture, or capture-dependent cursor. |
| S08 poll failure/coverage | 304, empty valid body, malformed XML/JSON, bounded-output overflow, timeout, partial playlist listing, and upstream retry delay. Only valid snapshots advance success/enrollment; failure preserves validators and earliest permitted due time. |
| S09 due-time concurrency | Two scheduler connections with the same fake due clock and a blocked adapter. One network poll; tick/status/manual refresh cannot bypass due time. Late stale-owner result is rejected; capture allowance exhaustion does not suppress polling. |
| S10 atomic daily allowance | Nine charged starts for one source, then two independently connected schedulers race distinct items for the last slot. Exactly one reservation/dispatch; occupied and charged counts never exceed 10. Repeat from zero through exhaustion with failures. A second source retains its own allowance. |
| S11 failure/retry accounting | Preflight rejection releases capacity; failed actual download retains its slot; a retry creates a second charged row. Three failed attempts stop automatically; off/on and generic pending retry/reset cannot bypass counts/backoff. |
| S12 UTC boundary and clock | Reserve 23:59:59, dispatch 00:00:01; old row released, new-day row required. Started work crosses midnight once. Retry charges its new day. Non-UTC host clock/DST and backwards-clock fixtures cannot reset or advance allowances incorrectly. |
| S13 restart reservation | Terminate after reserve commit/before dispatch, after started commit/before backend acknowledgment, and during worker execution. A restart neither refunds a started row nor dispatches a duplicate; unknown owner blocks until reconciliation. |
| S14 queue atomicity and fencing | Inject failure between durable backend insertion and reservation binding, replay the same start ID, and deliver an obsolete worker callback. There is one job binding, no orphan launch, and stale ownership cannot publish or mutate another attempt. |
| S15 cross-source deduplication | Same YouTube ID in a channel and two playlists, two schedulers, pre-existing and concurrent manual capture, and a removed/re-added source. One corpus identity and standing success record when standing capture wins; only its source is charged. Manual completion links without a standing charge. Deleted committed item is not resurrected. |
| S16 publication crash boundaries | Stop after corpus file, sidecar, item upsert, citations, clips, complete publication, and outbox commit. Partial ingest never gets premature work; committed ingest remains visible and eventually gets one handoff. Preserve source URL/type/platform and real timing. |
| S17 Phase 2 enqueue/replay | Approved fixture taxonomy/prompt; stop after `prepare_run` commits but before outbox acknowledgment; race two dispatchers. One matching single-item run/manifest/work row. Conflicting run ID blocks, existing measured manifests remain unchanged. |
| S18 classification waiting | No configured taxonomy/prompt, unavailable Phase 2 service, no client lease, deleted/revised/pinned source, and blocked Phase 2 recovery. Show the distinct condition; keep captured item visible; never start a model, re-capture, apply, or fake a ready job. |
| S19 registry parity/adversarial input | Same valid/invalid payloads through HTTP, MCP, and direct service. Reject duplicates, wrong types, huge/deep JSON, extra caps/actor fields, forged/expired/cross-session tokens, changed replay, stale cursors, malicious URLs, redirects, IDs, titles, and subprocess output. Zero unintended state/network changes. |
| S20 real consent UI | Gemini's collected plan: default off, pending enrollment, actual cohort/counts, allowance exhausted, refresh errors, off with in-flight work, lost mutation response, stale confirmation, and restart. Browser-visible state must match persisted service state. |
| S21 integrated controlled capture | AN only: disposable helper, local fixture feed with explicit fixture-only network allowance, configured Phase 2 taxonomy/prompt, and synthetic timed transcript. Newly detected entry lands once with provenance/clips, a visible unfiled item, and one ready work row after publication. No model/client is needed to demonstrate waiting-for-client. |
| S22 packaging and protected scope | Installed disposable candidate includes the new module/migration and registry schemas. Existing unrelated capture still works; no changes to protected Phase 2 surfaces. Test instrumentation confirms no watcher LLM/client spawn and no access to resident port 5179 or live index. |

These service tests belong under `tests/test_source_subscriptions*.py`; Gemini
selects dashboard test locations in its own plan. Fable must dispatch any required
packaging or compatibility-test edits explicitly, with one owner per shared file.

## AL document verification

Source inspection used `Get-Content` and `rg` inside the assigned worktree;
`git rev-parse HEAD` established the base above. An inline Python document check
parsed the embedded JSON, validated all four input schemas against Draft 2020-12,
and checked 16 valid/adversarial input examples. It executed the proposed DDL twice
in SQLite memory against the actual 0027 DDL plus minimal parent-table stubs.
Constraint probes checked active ownership, global capture identity, released-slot
reuse, failed-start charges, the ten-slot ceiling, independent source allowance,
foreign keys, and an invalid cross-day dispatch. Together with gate numbering and
whitespace checks, 34 document/schema assertions passed. The final checks also
reject incomplete poll ownership and a next-day dispatch that is still inside
its reservation's 120-second lifetime.

This check imported no project runtime modules and opened no existing database.
It did not exercise the migration runner, scheduler, queue, filesystem publication,
client, or UI. The S01–S22 runtime gates remain unrun. Only this contract document
was added; implementation and acceptance stay with AM/AN.

## Ambiguities resolved and collection checks

| Ambiguity | Ruling in this contract |
|---|---|
| Does capture-off disable metadata detection? | No; detection is a separate persisted flag. Archive disables both. |
| Does toggling refill 25 slots or import an off-period backlog? | No; one lifetime initial cohort and an explicit resume boundary. |
| Does "25" promise a complete back catalog? | No; it caps the visible, valid initial snapshot and reports adapter coverage. |
| Does failed capture refund the daily allowance? | Only an unstarted reservation is refundable. Failed actual starts remain charged; retries are new starts. |
| Can a reservation from yesterday start today? | No; release and re-reserve for the actual start day. |
| Does off kill existing work or erase evidence? | It cancels unstarted reservations; already-started work may finish and remains visible. |
| Does lease expiry prove a capture worker stopped? | No; keep uncertain ownership until reconciled. |
| Are process locks or timestamps enough for the cap? | No; database claims plus ten uniquely occupied slots enforce it across connections. |
| Does re-discovery or playlist removal authorize re-capture? | No; durable observation and global successful-capture identity survive. |
| Does a second subscribed source pay for the same video? | No; only the source that starts the capture uses a slot. |
| Can a successful poll omit entries because capture is full? | No; detection persistence and capture eligibility are independent. Partial enumeration is explicit. |
| What are the YouTube detectors? | Channel RSS using video IDs; existing yt-dlp flat playlist listing using `id`. No channel-handle resolver or silent fallback. |
| Is the 30-second tick an outbound polling rate? | No; default hourly due-time polling, minimum 15 minutes, with failure backoff. These are local policy choices, not platform guarantees. |
| How is legacy consent/accounting handled? | Preserve explicit podcast opt-in, never infer playlist consent, cap the initial cohort, and hold new legacy-source starts until the next UTC day and reconciliation. |
| Can a client simply set an `on` boolean? | It must consume a capability for the source decision confirmed in the local UI. Reads and source registration cannot enable capture. |
| How does 0027 accept post-capture work? | Durable outbox plus existing `prepare_run`, one frozen single-item run, verified replay; no direct insertion that bypasses Phase 2 validation. |
| What if no taxonomy, prompt binding, or client is available? | Visible unfiled capture with configuration/queue/client waiting state; no server reasoning or automatic apply. |
| Does restart or total database loss restore authority from sidecars? | Restart uses the ledger; total database loss does not reconstruct consent or allowance from corpus files. |

Before AM, Fable must collect Grok's note and Gemini's plan, reconcile exact adapter
resource budgets and any conflicting UI assumptions with this version, and name the
implementation base and owners for adapter/packaging edits. An adapter limit that
prevents a required capability is a concrete implementation blocker; it must be
reported without silently changing consent or caps. No unresolved user decision is
needed for the contract's state machine, ledger accounting, or post-commit handoff.
