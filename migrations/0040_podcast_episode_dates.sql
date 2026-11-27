-- Preserve the publisher's original date for display. The migration runner
-- parses RFC and Atom dates in the same transaction as this schema change.
ALTER TABLE podcast_episodes ADD COLUMN published_at_ms INTEGER;
CREATE INDEX IF NOT EXISTS idx_podcast_feed_episode_date
    ON podcast_episodes(feed_id, published_at_ms DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_podcast_episode_date
    ON podcast_episodes(published_at_ms DESC, id DESC);

-- Imported registries have a cutover accounting hold. Older RSS watches
-- can also have a successful check stamped directly on the feed. Both had
-- permission to check metadata before the subscription scheduler took over.
UPDATE source_subscriptions SET follow_feed=1
WHERE kind='podcast_rss' AND archived=0 AND detection_enabled=1 AND follow_feed=0
  AND EXISTS (SELECT 1 FROM podcast_feeds f WHERE f.id=legacy_feed_id AND f.enabled=1
              AND (accounting_hold_until_ms>0 OR f.last_polled_at IS NOT NULL));

-- Surface the last failed check even if the next retry is still hours away.
UPDATE podcast_feeds AS f SET error_count=c.error_count,
    last_error=CASE c.last_error_code
        WHEN 'feed_too_large' THEN 'The last feed check exceeded the 8 MiB limit.'
        WHEN 'malformed_feed' THEN 'Uoink could not read the feed''s XML.'
        WHEN 'feed_unreachable' THEN 'Uoink could not reach the feed.'
        WHEN 'poll_timeout' THEN 'The feed took too long to respond.'
        ELSE COALESCE(NULLIF(c.last_error_message, ''), 'Uoink could not check this feed.')
    END
FROM source_subscriptions s JOIN source_detection_cursors c USING (source_id)
WHERE s.legacy_feed_id=f.id AND c.error_count>0;
