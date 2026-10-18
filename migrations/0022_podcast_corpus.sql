-- Podcast corpus bridge and source-aware citations.
--
-- Preserve the public episode page separately from the feed-scoped GUID.
-- Rebuild citations so non-YouTube sources can carry their real source URL
-- and timestamp fragment without fabricating a YouTube watch link.

ALTER TABLE podcast_episodes ADD COLUMN episode_page_url TEXT;

CREATE TABLE citations_v2 (
    citation_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id          TEXT NOT NULL,
    kind              TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    timestamp_start   REAL,
    timestamp_end     REAL,
    text              TEXT,
    file_path         TEXT,
    youtube_deep_link TEXT,
    source_url        TEXT,
    source_deep_link  TEXT,
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE
);

INSERT INTO citations_v2 (
    citation_id, video_id, kind, seq, timestamp_start, timestamp_end,
    text, file_path, youtube_deep_link, source_url, source_deep_link
)
SELECT
    citation_id, video_id, kind, seq, timestamp_start, timestamp_end,
    text, file_path, youtube_deep_link, youtube_deep_link, youtube_deep_link
FROM citations;

DROP TABLE citations;
ALTER TABLE citations_v2 RENAME TO citations;

CREATE INDEX IF NOT EXISTS idx_citations_video_id
    ON citations(video_id, seq);
CREATE UNIQUE INDEX IF NOT EXISTS idx_citations_unique
    ON citations(video_id, kind, seq);
