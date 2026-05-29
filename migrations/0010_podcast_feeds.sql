-- v3.1 podcast support.
--
-- Per ROADMAP + PROMPT-V3.1: branding decision -- expand Uoink to cover
-- podcasts (don't fork as sibling product; one tool, one corpus).
--
-- This migration introduces ONLY the RSS feed + episode tracking tables.
-- The audio download pipeline + Whisper transcription land in subsequent
-- PRs (track B step 2 + step 3). Episodes here are metadata-only until
-- the user opts in to downloading.
--
-- Cascade: deleting a feed drops its episodes via FK.

CREATE TABLE IF NOT EXISTS podcast_feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_url        TEXT NOT NULL UNIQUE,
    title           TEXT,                       -- pulled from <channel><title>
    description     TEXT,
    homepage        TEXT,
    last_polled_at  TEXT,                       -- NULL until first successful poll
    last_etag       TEXT,                       -- HTTP ETag for conditional GET
    last_modified   TEXT,                       -- HTTP Last-Modified header
    poll_interval_min INTEGER NOT NULL DEFAULT 60,  -- min between polls
    enabled         INTEGER NOT NULL DEFAULT 1,
    added_at        TEXT NOT NULL,
    error_count     INTEGER NOT NULL DEFAULT 0,  -- consecutive poll failures
    last_error      TEXT                          -- last error message
);
CREATE INDEX IF NOT EXISTS idx_podcast_feeds_enabled
    ON podcast_feeds(enabled);

CREATE TABLE IF NOT EXISTS podcast_episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id         INTEGER NOT NULL,
    -- guid is the RSS <item><guid> -- the canonical episode identity.
    -- Some feeds reuse audio URLs; some don't include enclosure URLs.
    -- guid is the only reliable dedupe key.
    guid            TEXT NOT NULL,
    title           TEXT,
    audio_url       TEXT,
    duration_seconds INTEGER,
    published_at    TEXT,                       -- pubDate or atom:published
    description     TEXT,
    -- Status flow: new -> queued (when user opts in) -> downloaded ->
    --              transcribed -> ignored (user dismissed).
    status          TEXT NOT NULL DEFAULT 'new',
    -- Once downloaded + transcribed, the episode becomes a yoink row;
    -- store the linkage so the dashboard can navigate.
    yoink_video_id  TEXT,
    discovered_at   TEXT NOT NULL,
    FOREIGN KEY (feed_id) REFERENCES podcast_feeds(id) ON DELETE CASCADE,
    UNIQUE (feed_id, guid)
);
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_feed
    ON podcast_episodes(feed_id);
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_status
    ON podcast_episodes(status);
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_published
    ON podcast_episodes(published_at);
