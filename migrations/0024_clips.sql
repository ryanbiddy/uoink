-- Living library, phase 1: clips.
--
-- A clip is a merged, de-overlapped window of transcript cues (roughly
-- 45-120 s of speech ending on a sentence boundary) derived from the
-- `citations` rows of kind 'transcript_chunk'. Raw caption cues average
-- ~37 characters and repeat the tail of the previous cue, which makes them
-- useless as search hits and as evidence; clips are the quotable unit.
--
-- Clips are DERIVED data: clips.py rebuilds them deterministically from
-- citations, so nothing here needs to be exported or migrated by hand.
-- Deleting a yoink cascades through citations and clips alike.
--
-- clips_fts is an external-content FTS5 table (content='clips') so the
-- text is stored once; the three triggers keep the FTS index in sync with
-- every insert / delete / update on clips, including FK-cascade deletes.

CREATE TABLE IF NOT EXISTS clips (
    clip_id          INTEGER PRIMARY KEY,
    video_id         TEXT NOT NULL,
    seq              INTEGER NOT NULL,      -- clip order within the video
    start            REAL,                  -- first cue's timestamp_start
    end              REAL,                  -- last cue's timestamp_end
    text             TEXT NOT NULL,         -- merged, de-overlapped cue text
    speaker          TEXT,                  -- reserved; NULL in phase 1
    source_deep_link TEXT,                  -- first cue's source-neutral link
    cue_count        INTEGER,               -- cues merged into this clip
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE,
    UNIQUE (video_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_clips_video_seq
    ON clips(video_id, seq);

CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts USING fts5(
    text,
    content='clips',
    content_rowid='clip_id'
);

CREATE TRIGGER IF NOT EXISTS clips_fts_ai AFTER INSERT ON clips BEGIN
    INSERT INTO clips_fts(rowid, text) VALUES (new.clip_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS clips_fts_ad AFTER DELETE ON clips BEGIN
    INSERT INTO clips_fts(clips_fts, rowid, text)
        VALUES ('delete', old.clip_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS clips_fts_au AFTER UPDATE ON clips BEGIN
    INSERT INTO clips_fts(clips_fts, rowid, text)
        VALUES ('delete', old.clip_id, old.text);
    INSERT INTO clips_fts(rowid, text) VALUES (new.clip_id, new.text);
END;
