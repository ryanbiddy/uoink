-- A Follow action permits scheduled RSS checks independently of audio capture.
ALTER TABLE source_subscriptions ADD COLUMN follow_feed INTEGER NOT NULL DEFAULT 0 CHECK(follow_feed IN (0,1));

-- 3.17 Follow used add_feed without a title. The scheduler skipped these
-- enabled feeds until a consent change. Restore RSS polling only.
UPDATE source_subscriptions SET follow_feed=1
WHERE follow_feed=0 AND kind='podcast_rss' AND detection_enabled=1 AND archived=0 AND consent_epoch=0
  AND EXISTS (
      SELECT 1 FROM podcast_feeds WHERE id=source_subscriptions.legacy_feed_id
      AND enabled=1 AND error_count=0 AND last_polled_at IS NULL
      AND lower(trim(coalesce(title,''))) IN ('','untitled podcast'))
  AND NOT EXISTS (
      SELECT 1 FROM source_detection_cursors c WHERE c.source_id=source_subscriptions.source_id
      AND c.last_poll_attempt_ms IS NOT NULL);

-- Legacy direct polls also stamped failures. A prior success time cannot be recovered.
UPDATE podcast_feeds SET last_polled_at=NULL WHERE error_count>0 AND last_polled_at IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS clear_podcast_follow_after_archive
AFTER UPDATE OF archived ON source_subscriptions WHEN NEW.archived=1 AND NEW.follow_feed=1
BEGIN
    UPDATE source_subscriptions SET follow_feed=0 WHERE source_id=NEW.source_id;
END;
