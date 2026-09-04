-- Recover source_type for legacy rows from the indexed platform and source URL.
-- Python's provenance.backfill_source_types completes ambiguous rows from the
-- sidecar after this migration commits.

WITH candidates AS (
    SELECT
        rowid,
        lower(trim(coalesce(platform, ''))) AS platform_name,
        lower(trim(CASE
            WHEN json_valid(metadata_json)
            THEN coalesce(json_extract(metadata_json, '$.url'), '')
            ELSE ''
        END)) AS source_url,
        lower(trim(CASE
            WHEN json_valid(metadata_json)
            THEN coalesce(json_extract(metadata_json, '$.content_type'), '')
            ELSE ''
        END)) AS content_type
    FROM yoinks
    WHERE source_type IS NULL OR trim(source_type) = ''
), derived AS (
    SELECT rowid, CASE
        WHEN platform_name = 'note' THEN 'note'
        WHEN platform_name = 'image' THEN 'image'
        WHEN platform_name = 'podcast' THEN 'episode'
        WHEN platform_name IN ('tiktok', 'instagram') THEN 'short_video'
        WHEN platform_name IN ('x', 'twitter') THEN
            CASE WHEN source_url LIKE '%/i/article/%'
                       OR content_type = 'article'
                 THEN 'x_article' ELSE 'x_thread' END
        WHEN platform_name = 'reddit' THEN 'reddit_thread'
        WHEN platform_name = 'youtube' THEN
            CASE WHEN source_url LIKE '%youtube.com/shorts/%'
                 THEN 'short_video' ELSE 'video' END
        WHEN platform_name IN ('web', 'generic') THEN 'page'
        WHEN source_url LIKE '%youtube.com/shorts/%'
             OR source_url LIKE '%tiktok.com/%'
             OR source_url LIKE '%instagram.com/reel/%' THEN 'short_video'
        WHEN source_url LIKE '%youtube.com/%'
             OR source_url LIKE '%youtu.be/%' THEN 'video'
        WHEN source_url LIKE '%x.com/%'
             OR source_url LIKE '%twitter.com/%' THEN
            CASE WHEN source_url LIKE '%/i/article/%'
                 THEN 'x_article' ELSE 'x_thread' END
        WHEN source_url LIKE '%reddit.com/%' THEN 'reddit_thread'
        WHEN source_url LIKE 'http://%'
             OR source_url LIKE 'https://%' THEN 'page'
        ELSE NULL
    END AS source_type
    FROM candidates
)
UPDATE yoinks
SET source_type = (
    SELECT derived.source_type
    FROM derived
    WHERE derived.rowid = yoinks.rowid
)
WHERE rowid IN (
    SELECT rowid FROM derived WHERE source_type IS NOT NULL
);
