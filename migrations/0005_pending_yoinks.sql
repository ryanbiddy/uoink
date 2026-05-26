-- Yoink library index -- rate-limit retry queue (v5, Sprint 19 / C4).
-- Applied by index._run_migrations() on top of 0004. Backs the
-- queue+retry flow that absorbs YouTube 429s: /extract enqueues the URL
-- here instead of erroring, and a background worker retries with
-- exponential backoff up to 3 attempts.

CREATE TABLE IF NOT EXISTS pending_yoinks (
    pending_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    interval_seconds INTEGER DEFAULT 30,
    queued_at TEXT NOT NULL,
    retry_after TEXT NOT NULL,         -- ISO timestamp; next eligible attempt
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,              -- 'pending' | 'running' | 'failed' | 'succeeded' | 'cancelled'
    last_error TEXT,
    succeeded_job_id TEXT              -- single-extract job_id on success
);

CREATE INDEX IF NOT EXISTS idx_pending_yoinks_status_retry
    ON pending_yoinks(status, retry_after);
CREATE INDEX IF NOT EXISTS idx_pending_yoinks_queued_at
    ON pending_yoinks(queued_at DESC);
