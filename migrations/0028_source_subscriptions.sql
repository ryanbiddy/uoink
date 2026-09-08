-- Reserved by Fable for run AM, 2026-09-07 (Phase 3 standing capture).
-- Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md, "Migration 0028 schema".
-- The DDL below is the contract's normative text, unchanged. Execute inside the
-- existing migration transaction, with foreign_keys=ON. All creates are
-- repeatable. It creates no subscriptions, consent, captures, taxonomies, or
-- classification jobs by itself; legacy registry import is application code
-- (source_subscriptions.import_legacy_registries), not SQL guessing identities.

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
