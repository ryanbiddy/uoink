-- Pins can precede the item while a blocked capture waits in the local queue.
CREATE TABLE IF NOT EXISTS item_moments (
    video_id TEXT NOT NULL,
    seconds INTEGER NOT NULL CHECK(seconds >= 0),
    pinned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    note TEXT,
    pending_id INTEGER REFERENCES pending_yoinks(pending_id) ON DELETE CASCADE,
    PRIMARY KEY(video_id, seconds)
);
CREATE TRIGGER IF NOT EXISTS moments_after_capture AFTER INSERT ON yoinks BEGIN
    UPDATE item_moments SET pending_id=NULL WHERE video_id=NEW.video_id;
END;
CREATE TRIGGER IF NOT EXISTS moments_after_delete AFTER DELETE ON yoinks BEGIN
    DELETE FROM item_moments WHERE video_id=OLD.video_id;
END;
CREATE TRIGGER IF NOT EXISTS moments_after_cancel AFTER UPDATE OF status ON pending_yoinks
WHEN NEW.status='cancelled' BEGIN
    DELETE FROM item_moments WHERE pending_id=NEW.pending_id;
END;
