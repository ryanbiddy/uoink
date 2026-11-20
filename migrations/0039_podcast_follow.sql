-- A Follow action permits scheduled RSS checks independently of audio capture.
ALTER TABLE source_subscriptions ADD COLUMN follow_feed INTEGER NOT NULL DEFAULT 0 CHECK(follow_feed IN (0,1));

CREATE TRIGGER IF NOT EXISTS clear_podcast_follow_after_archive
AFTER UPDATE OF archived ON source_subscriptions WHEN NEW.archived=1 AND NEW.follow_feed=1
BEGIN
    UPDATE source_subscriptions SET follow_feed=0 WHERE source_id=NEW.source_id;
END;
