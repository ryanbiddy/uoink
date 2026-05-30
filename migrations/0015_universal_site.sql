-- v3.2 Universal Site Uoinking.
--
-- Per PROMPT-V3.2-CC-BACKEND.md Deliverable 2 + Ryan's locked answer #1:
-- opt-in allowlist (default sites pre-added: YouTube + X/Twitter; user
-- adds others). Pages land in the SAME yoinks table as video uoinks,
-- distinguished by source_type='page' so the dashboard can render the
-- right card variant.

-- 1) Extend yoinks with source_type. NULL/'video' for existing rows;
--    'page' for new universal-site captures; future values reserved.
ALTER TABLE yoinks ADD COLUMN source_type TEXT;
CREATE INDEX IF NOT EXISTS idx_yoinks_source_type
    ON yoinks(source_type);

-- 2) User's allowlist of sites that the extension is allowed to capture.
--    Wildcard host_pattern supported -- '*.docs.example.com' matches
--    sub.docs.example.com via _host_matches(). Default-seeded by the
--    helper on first migration (see allowed_sites_default_seed below).
CREATE TABLE IF NOT EXISTS allowed_sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_pattern TEXT NOT NULL UNIQUE,
    added_at    TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_allowed_sites_active
    ON allowed_sites(active);

-- 3) Default seeds. Ryan's locked answer #1: YouTube + X/Twitter
--    pre-added; user adds others. INSERT OR IGNORE so re-running the
--    migration is safe; the user can also remove these defaults later.
INSERT OR IGNORE INTO allowed_sites (url_pattern, added_at)
    VALUES ('youtube.com', '2026-05-30T00:00:00Z');
INSERT OR IGNORE INTO allowed_sites (url_pattern, added_at)
    VALUES ('youtu.be', '2026-05-30T00:00:00Z');
INSERT OR IGNORE INTO allowed_sites (url_pattern, added_at)
    VALUES ('x.com', '2026-05-30T00:00:00Z');
INSERT OR IGNORE INTO allowed_sites (url_pattern, added_at)
    VALUES ('twitter.com', '2026-05-30T00:00:00Z');
