-- v3 A2 claim extraction + verification.
--
-- LOCKED FRAMING (ROADMAP A2): claim extraction + verification ASSISTANCE.
-- Never auto-assert "this creator lied." Surface checkable claims with
-- evidence + sources. The user judges. Dashboard copy + MCP tool descriptions
-- enforce this -- the SQL is plumbing.
--
-- Loki inspiration (vendor/loki/): the 5-step pipeline -- decompose into
-- claims, assess check-worthiness, generate verification queries, retrieve
-- evidence, surface evidence + claim. Implementation is model-agnostic: the
-- calling agent does the LLM work via MCP; the helper persists structure.

CREATE TABLE IF NOT EXISTS claims (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id             TEXT NOT NULL,
    claim_text           TEXT NOT NULL,
    -- 0.0 - 1.0 -- agent-supplied. NULL when not yet assessed.
    check_worthiness     REAL,
    -- extracted | verified | not-attempted -- per ROADMAP A2 status enum.
    status               TEXT NOT NULL DEFAULT 'extracted',
    -- JSONL of {source_url, quote, alignment_signal} -- alignment_signal is
    -- one of: supports | contradicts | mixed | inconclusive (NEVER 'true' or
    -- 'false' -- never auto-assert truth verdicts).
    evidence             TEXT NOT NULL DEFAULT '[]',
    extracted_at         TEXT NOT NULL,
    verified_at          TEXT,
    -- Free-form context preserved per claim (timestamp in source video,
    -- speaker name, surrounding sentence) so a downstream review has
    -- enough handle to re-locate the claim without re-running extraction.
    context_json         TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_video ON claims(video_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_claims_check_worthiness
    ON claims(check_worthiness);
