-- S6 cross-product engagement: caller-issued idempotency keys.
-- Existing Uoink-owned events retain NULL keys and their legacy route.

ALTER TABLE engagement_events ADD COLUMN event_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_engagement_event_id
ON engagement_events(event_id)
WHERE event_id IS NOT NULL;
