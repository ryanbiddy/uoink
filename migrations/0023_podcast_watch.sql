-- Automatic podcast feed watching.
--
-- Feed registration remains metadata-only by default. auto_ingest is an
-- explicit per-feed opt-in for downloading, transcribing, and publishing
-- episodes discovered while the flag is enabled. The episode marker makes
-- that intent durable across helper restarts without sweeping in an older
-- back catalogue when a user turns the flag on later.

ALTER TABLE podcast_feeds ADD COLUMN auto_ingest INTEGER NOT NULL DEFAULT 0;
ALTER TABLE podcast_episodes ADD COLUMN auto_ingest_requested INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_podcast_feeds_watch_due
    ON podcast_feeds(enabled, last_polled_at);
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_auto_ingest
    ON podcast_episodes(feed_id, auto_ingest_requested, yoink_video_id);
