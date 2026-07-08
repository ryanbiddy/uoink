-- Phase 2 categorization: source-agnostic taxonomy on the yoinks table.
--
-- The data model was YouTube-shaped: `channel` was the sole "who" field, and
-- for every non-YouTube source it got hard-coded to the URL hostname
-- (x.com, reddit.com, ...), so an X Article by @boardyai showed up as
-- "x.com" and there was no way to filter "show my X posts" or "everything
-- from YouTube". Two new first-class columns fix that:
--
--   platform  youtube | x | reddit | podcast | web  -- the source network
--   author    the real "who": YouTube uploader, X author "(@handle)",
--             reddit "r/<sub>", or the site host for a bare web page
--
-- Both are nullable + additive, so pre-Phase-2 rows read back cleanly and
-- the migration is backward compatible. The SQL-derivable part of the
-- backfill runs here (platform from source_type, author=channel for
-- YouTube rows). The part that needs the on-disk sidecar (the real X /
-- Reddit author, and correcting the hostname `channel` values) runs in the
-- Python sidecar backfill (page_extractor.backfill_platform_author), which
-- the helper triggers once at boot and exposes as `--backfill-authors`.
--
-- Idempotent: the runner routes the ALTERs through _safe_alter_add_column
-- (a re-run is a no-op) and every UPDATE only touches rows still missing
-- the value (WHERE platform IS NULL / author IS NULL), so re-running the
-- statements never clobbers a value a later write set.

ALTER TABLE yoinks ADD COLUMN platform TEXT;
ALTER TABLE yoinks ADD COLUMN author TEXT;

CREATE INDEX IF NOT EXISTS idx_yoinks_platform ON yoinks(platform);
CREATE INDEX IF NOT EXISTS idx_yoinks_author ON yoinks(author);

-- Backfill platform from the already-stored source_type. NULL source_type is
-- a legacy (pre-v3.2) YouTube video, so it maps to youtube alongside 'video'.
UPDATE yoinks SET platform = CASE
    WHEN source_type IN ('x_thread', 'x_article') THEN 'x'
    WHEN source_type = 'reddit_thread'             THEN 'reddit'
    WHEN source_type = 'page'                      THEN 'web'
    WHEN source_type = 'episode'                   THEN 'podcast'
    ELSE 'youtube'
END
WHERE platform IS NULL;

-- Legacy (pre-v3.2) YouTube rows have a NULL source_type. Normalise them to
-- 'video' so the Source-type facet is complete and every row is filterable by
-- type, not just the newer non-YouTube captures.
UPDATE yoinks SET source_type = 'video'
WHERE source_type IS NULL AND platform = 'youtube';

-- YouTube's `channel` already holds the real uploader, so author = channel
-- for those rows. Non-YouTube rows carry the hostname in `channel` (the bug),
-- so they are left NULL here and filled from their sidecar by the Python pass.
UPDATE yoinks SET author = channel
WHERE author IS NULL
  AND platform = 'youtube'
  AND channel IS NOT NULL
  AND channel != '';
