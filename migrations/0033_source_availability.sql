-- Track source availability separately from saved media, including confirmation
-- delays, per-host backoff, and the last bounded checker run.
CREATE TABLE IF NOT EXISTS source_availability (
    video_id TEXT PRIMARY KEY REFERENCES yoinks(video_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(status IN ('available', 'deleted', 'private', 'region_blocked', 'unknown')),
    pending_status TEXT CHECK(pending_status IS NULL OR
        pending_status IN ('deleted', 'private', 'region_blocked')),
    pending_since TEXT,
    last_checked_at TEXT,
    next_check_at TEXT,
    status_changed_at TEXT,
    gone_since TEXT,
    http_status INTEGER,
    detail TEXT,
    checker TEXT,
    consecutive_errors INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS source_availability_status_gone
    ON source_availability(status, gone_since);
CREATE INDEX IF NOT EXISTS source_availability_due
    ON source_availability(next_check_at);

CREATE TABLE IF NOT EXISTS source_availability_hosts (
    host TEXT PRIMARY KEY,
    backoff_until TEXT,
    strikes INTEGER NOT NULL DEFAULT 0,
    last_request_at TEXT
);

CREATE TABLE IF NOT EXISTS source_availability_state (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    last_run_started_at TEXT,
    last_run_finished_at TEXT,
    last_run_json TEXT
);
