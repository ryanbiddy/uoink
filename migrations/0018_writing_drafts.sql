-- v3.2.5 Writing draft persistence (G-03, QA #32 backend half).
--
-- The dashboard's Save button needs a real place to put work in progress.
-- Drafts are looser than writing_pieces: no credit requirement, no version
-- chain, just the composer state so a reload can recover it. A draft
-- graduates into writing_pieces through the normal two-phase persist.

CREATE TABLE IF NOT EXISTS writing_drafts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    yoink_id           TEXT,                           -- source uoink video_id, nullable
    kind               TEXT NOT NULL DEFAULT 'tweet',  -- composer output mode at save time
    title              TEXT,
    body               TEXT NOT NULL,                  -- current draft text (may be mid-edit)
    source_credit_line TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_writing_drafts_updated_at
    ON writing_drafts(updated_at);
CREATE INDEX IF NOT EXISTS idx_writing_drafts_yoink_id
    ON writing_drafts(yoink_id);
