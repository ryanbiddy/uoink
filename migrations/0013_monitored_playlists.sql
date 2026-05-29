-- v3.1 mobile -> desktop playlist bridge.
--
-- Per PROMPT-V3.1-FULL-BUILD-PLAN.md track C (Ryan-requested net-new
-- feature). User creates a designated YouTube playlist on mobile,
-- adds videos with one tap, helper polls + diffs + auto-queues the
-- unseen ones.
--
-- Schema:
--   monitored_playlists: the registry the user manages from Settings.
--     last_seen_video_ids stores the dedupe set as a JSON array so we
--     don't need a sub-table; YouTube playlist max is ~5,000 which
--     fits comfortably in a TEXT column.
--   mobile_queue_events: per-discovery log so the Activity tab can
--     show "1 new from playlist X at HH:MM" separately from rate-
--     limit retries and other queue sources.

CREATE TABLE IF NOT EXISTS monitored_playlists (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_url      TEXT NOT NULL UNIQUE,
    name              TEXT,                         -- user-visible label
    poll_interval_min INTEGER NOT NULL DEFAULT 5,   -- per prompt: every 5 min default
    enabled           INTEGER NOT NULL DEFAULT 1,
    last_polled_at    TEXT,
    last_seen_video_ids TEXT NOT NULL DEFAULT '[]', -- JSON array of video_ids
    error_count       INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    added_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monitored_playlists_enabled
    ON monitored_playlists(enabled);

CREATE TABLE IF NOT EXISTS mobile_queue_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id  INTEGER NOT NULL,
    video_id     TEXT NOT NULL,
    video_title  TEXT,
    discovered_at TEXT NOT NULL,
    -- Status flow: discovered -> queued (handed to /extract) ->
    --              extracted | failed. The dashboard groups by
    --              playlist + status.
    status       TEXT NOT NULL DEFAULT 'discovered',
    pending_id   INTEGER,    -- linked pending_yoinks row id when queued
    FOREIGN KEY (playlist_id) REFERENCES monitored_playlists(id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mobile_queue_events_playlist
    ON mobile_queue_events(playlist_id);
CREATE INDEX IF NOT EXISTS idx_mobile_queue_events_status
    ON mobile_queue_events(status);
CREATE INDEX IF NOT EXISTS idx_mobile_queue_events_discovered
    ON mobile_queue_events(discovered_at);
