-- The original publish (air) day of each saved item, as YYYY-MM-DD, indexed
-- for the published_from / published_to search filters. Sources store the
-- date in different shapes (ISO 8601 with an offset, yt-dlp's YYYYMMDD, an
-- RSS pubDate), so index.py reads it from metadata_json in Python: it fills
-- the existing rows in the same transaction as this migration and keeps the
-- column current on every save.
ALTER TABLE yoinks ADD COLUMN published_day TEXT;
CREATE INDEX IF NOT EXISTS idx_yoinks_published_day ON yoinks(published_day);
