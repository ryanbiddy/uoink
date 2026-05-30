-- v3.2 Writing Studio.
--
-- Tweets, threads, blogs grounded in any uoink, with Voice DNA prepended,
-- creator credit non-suppressible, and per-user style anchors (up to 10).
--
-- Compute policy (locked, model-agnostic + LOCAL-FIRST):
-- Calling agent does the LLM writing via MCP using its own model. Helper
-- persists structure + does the Voice DNA scan post-generation.
-- BYO-key on-server pathway is scaffolded by mode column but not
-- implemented in this PR (same posture as P4/P5).

CREATE TABLE IF NOT EXISTS writing_pieces (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    yoink_id          TEXT,                          -- source uoink video_id (nullable for free-form writing)
    kind              TEXT NOT NULL,                  -- 'tweet' | 'thread' | 'blog'
    version           INTEGER NOT NULL DEFAULT 1,    -- per-source-yoink revision counter
    parent_id         INTEGER,                       -- FK self -- previous revision id
    title             TEXT,                          -- blog title, NULL for tweet
    dek               TEXT,                          -- blog subtitle, NULL otherwise
    body              TEXT NOT NULL,                 -- output body (markdown for blogs, plain for tweets/threads)
    tags              TEXT NOT NULL DEFAULT '[]',    -- JSON array of suggested tags
    source_credit_line TEXT NOT NULL,                -- mandatory; "via @handle · short_link" or full "Source" section
    voice_warnings    TEXT NOT NULL DEFAULT '[]',    -- JSON array of {phrase, position, category, matched_text}
    style_anchor_ids  TEXT NOT NULL DEFAULT '[]',    -- JSON array of style_anchor ids used
    mode              TEXT NOT NULL DEFAULT 'agent', -- 'agent' | 'byo_key'
    generated_at      TEXT NOT NULL,
    angle             TEXT,                          -- optional editorial angle passed by caller
    target_length     INTEGER,                       -- chars for tweet, words for blog
    FOREIGN KEY (parent_id) REFERENCES writing_pieces(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_writing_pieces_yoink_id
    ON writing_pieces(yoink_id);
CREATE INDEX IF NOT EXISTS idx_writing_pieces_kind
    ON writing_pieces(kind);
CREATE INDEX IF NOT EXISTS idx_writing_pieces_generated_at
    ON writing_pieces(generated_at);

-- Substack-style anchors: user-curated voice references (the prose of a
-- favorite writer, a TED talk transcript, etc.) the generator pulls
-- alongside Voice DNA. Capped at 10 per Ryan's locked answer #4.
CREATE TABLE IF NOT EXISTS style_anchors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,                       -- user-chosen label
    source_type  TEXT NOT NULL,                       -- 'url' | 'text'
    source_url   TEXT,                                -- when source_type='url'
    raw_text     TEXT,                                -- when source_type='text' (or extracted prose for url)
    active       INTEGER NOT NULL DEFAULT 1,          -- soft toggle for "use in next generation"
    added_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_style_anchors_active
    ON style_anchors(active);
