-- V-3 taste-aware auto-uoink (opt-in).
--
-- Records WHY a monitored-playlist candidate was auto-captured so the
-- Activity tab + the V-4 discovery digest can honestly label it
-- "auto-uoinked (taste match)" and show the taste score behind the call.
--
-- Both columns are nullable and left NULL by the existing manual poll
-- path, so this migration is fully backward compatible: pre-V-3 events
-- (and every manually-queued mobile-playlist row) read back with no
-- capture_reason and no taste_score.
--
--   capture_reason  short machine tag, e.g. 'auto_uoink:taste' -- present
--                   only on rows the taste filter chose to capture.
--   taste_score     the 0.0-1.0 taste score at capture time (audit trail;
--                   lets the digest sort fresh captures by confidence).

ALTER TABLE mobile_queue_events ADD COLUMN capture_reason TEXT;
ALTER TABLE mobile_queue_events ADD COLUMN taste_score REAL;

CREATE INDEX IF NOT EXISTS idx_mobile_queue_events_capture_reason
    ON mobile_queue_events(capture_reason);
