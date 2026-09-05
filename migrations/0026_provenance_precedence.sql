-- Reconcile explicit metadata kinds even when 0025 filled source_type.
-- Keep 0025 immutable. Same key order and aliases as provenance.py:
-- metadata source_type, kind, type; then existing sidecar/platform/URL result.
WITH aliases(alias, canonical) AS (
    VALUES ('video', 'video'), ('podcast', 'episode'), ('episode', 'episode'),
           ('x_post', 'x_thread'), ('x_thread', 'x_thread'), ('x_article', 'x_article'),
           ('page', 'page'), ('reddit', 'reddit_thread'), ('reddit_thread', 'reddit_thread'),
           ('note', 'note'), ('image', 'image'), ('short_video', 'short_video')
), metadata AS (
    SELECT rowid, CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END AS doc
    FROM yoinks
), explicit AS (
    SELECT rowid, coalesce(
        (SELECT canonical FROM aliases WHERE alias = lower(trim(json_extract(doc, '$.source_type')))),
        (SELECT canonical FROM aliases WHERE alias = lower(trim(json_extract(doc, '$.kind')))),
        (SELECT canonical FROM aliases WHERE alias = lower(trim(json_extract(doc, '$.type'))))
    ) AS kind
    FROM metadata
)
UPDATE yoinks SET source_type = (SELECT kind FROM explicit WHERE explicit.rowid = yoinks.rowid)
WHERE rowid IN (SELECT rowid FROM explicit WHERE kind IS NOT NULL)
  AND source_type IS NOT (SELECT kind FROM explicit WHERE explicit.rowid = yoinks.rowid);
