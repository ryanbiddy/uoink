-- The query contract prefix-matches the final word. Short, common prefixes
-- otherwise merge hundreds of token posting lists for each BM25 cursor.
-- Preserve source FTS rowids and rebuild only derived search indexes.
ALTER TABLE yoinks_fts RENAME TO yoinks_fts_before_prefix;
CREATE VIRTUAL TABLE yoinks_fts USING fts5(
    video_id UNINDEXED, slug, channel, title, topic, hook_type, content,
    prefix='2 3'
);
INSERT INTO yoinks_fts(rowid, video_id, slug, channel, title, topic, hook_type, content)
SELECT rowid, video_id, slug, channel, title, topic, hook_type, content
FROM yoinks_fts_before_prefix;
DROP TABLE yoinks_fts_before_prefix;

-- A one-token source key lets FTS intersect a bounded source page before
-- ranking clips. The key is derived, never part of the searchable passage.
ALTER TABLE clips ADD COLUMN search_source TEXT
    GENERATED ALWAYS AS (lower(hex(video_id))) VIRTUAL;
DROP TRIGGER clips_fts_ai;
DROP TRIGGER clips_fts_ad;
DROP TRIGGER clips_fts_au;
DROP TABLE clips_fts;
CREATE VIRTUAL TABLE clips_fts USING fts5(
    text, search_source, content='clips', content_rowid='clip_id', prefix='2 3'
);
CREATE TRIGGER clips_fts_ai AFTER INSERT ON clips BEGIN
    INSERT INTO clips_fts(rowid, text, search_source)
        VALUES (new.clip_id, new.text, new.search_source);
END;
CREATE TRIGGER clips_fts_ad AFTER DELETE ON clips BEGIN
    INSERT INTO clips_fts(clips_fts, rowid, text, search_source)
        VALUES ('delete', old.clip_id, old.text, old.search_source);
END;
CREATE TRIGGER clips_fts_au AFTER UPDATE ON clips BEGIN
    INSERT INTO clips_fts(clips_fts, rowid, text, search_source)
        VALUES ('delete', old.clip_id, old.text, old.search_source);
    INSERT INTO clips_fts(rowid, text, search_source)
        VALUES (new.clip_id, new.text, new.search_source);
END;
INSERT INTO clips_fts(clips_fts) VALUES ('rebuild');
