-- v2.5 substrate schema (PR 1 of the v2.5 substrate build).
--
-- Declares the SHAPE that S1 / S2 / S4 / P3 consume. Tables/columns are
-- created here; population happens in the subsequent PRs. Two layers of
-- versioning are at play:
--   - schema_version (this table, tracked per migration file by the runner) =
--     SQL schema version, bumped automatically by index._run_migrations.
--   - yoinks.schema_version (new column below) = per-row DATA-SHAPE version
--     so v2.5 readers can tell "this row predates facets / pre-engagement /
--     pre-v2-sidecar" without inspecting every field. Existing rows default
--     to 1; v2.5+ writers set 2.
--
-- Per the index runner's convention: CREATE / ADD use IF NOT EXISTS where
-- SQLite allows it. SQLite does NOT support `ALTER TABLE ADD COLUMN IF NOT
-- EXISTS`, but the runner wraps the whole file + the schema_version bump in
-- one BEGIN IMMEDIATE / COMMIT, so a crash leaves the txn rolled back and the
-- next boot re-runs cleanly. (Sprint 19.6 / Fix 2 contract.)

-- ---- 1. Per-row data-shape version on yoinks --------------------------------
ALTER TABLE yoinks ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1;

-- ---- 2. S1 facet columns (bounded-cardinality enums) ------------------------
-- topic + hook_type already exist on the v1 schema; these are net new. NULL
-- until S1 classifies (classification is lazy + agent-driven per the locked
-- compute policy -- no eager Anthropic calls).
ALTER TABLE yoinks ADD COLUMN format TEXT;             -- one_shot|talking_head|tutorial|listicle|narrative|vlog|interview|screen_recording|broll_heavy
ALTER TABLE yoinks ADD COLUMN performance_tier TEXT;   -- over|average|under (vs channel median)
ALTER TABLE yoinks ADD COLUMN production_style TEXT;   -- free-form short string
ALTER TABLE yoinks ADD COLUMN length_bucket TEXT;      -- short|medium|long|deep

-- ---- 3. S1 free-form tags (separate from bounded facets above) -------------
CREATE TABLE IF NOT EXISTS yoink_tags (
    video_id TEXT NOT NULL,
    tag      TEXT NOT NULL,
    source   TEXT NOT NULL DEFAULT 'agent',  -- agent | user | auto
    added_at TEXT NOT NULL,
    PRIMARY KEY (video_id, tag),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_yoink_tags_tag ON yoink_tags(tag);

-- ---- 4. S2 engagement events (pure local instrumentation, zero outbound) ---
-- Populated by /engagement/log from popup, dashboard, MCP, extension. The
-- aggregation pipeline computes value_score with time decay -- see the S2 PR.
CREATE TABLE IF NOT EXISTS engagement_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT NOT NULL,
    event_type TEXT NOT NULL,    -- opened|search_hit|search_click|paste|cite|recent_open
    ts_utc     TEXT NOT NULL,
    source     TEXT NOT NULL     -- popup|dashboard|mcp|extension
);
CREATE INDEX IF NOT EXISTS idx_engagement_video ON engagement_events(video_id);
CREATE INDEX IF NOT EXISTS idx_engagement_ts    ON engagement_events(ts_utc);

-- ---- 5. S4 memory layer key/value -------------------------------------------
-- Used by the markdown memory writer for last-consolidation timestamps,
-- optional Obsidian vault path, and other persistent metadata. The TASTE.md /
-- USER.md files themselves live on disk under %LOCALAPPDATA%\Uoink\memory\;
-- this table is just the pointer + bookkeeping layer.
CREATE TABLE IF NOT EXISTS memory_layer (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

-- ---- 6. P3 your-channel registry --------------------------------------------
-- Multi-channel support per the roadmap (some users have 2-3 channels).
-- Populated by the "Your channels" Settings panel (PR 5).
CREATE TABLE IF NOT EXISTS user_channels (
    handle      TEXT PRIMARY KEY,    -- @handle or channel id, normalised
    channel_id  TEXT,                -- YouTube channel id once verified
    name        TEXT,
    added_at    TEXT NOT NULL,
    verified_at TEXT
);
