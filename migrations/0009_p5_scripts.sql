-- v3 P5 Script Studio -- generated scripts grounded in corpus + taste.
--
-- A script is one structured generation pass: the agent (using its own
-- model via MCP) produces a hook + beats + body + CTA + source citations
-- grounded in a workspace's assembled corpus slice + optional S4 taste
-- anchors. The helper persists structure; the agent does the writing.
--
-- Compute policy (locked, model-agnostic by default): same posture as
-- P4 critique -- two-phase. Phase 1 returns grounding context; phase 2
-- persists the generated script the agent produces.

CREATE TABLE IF NOT EXISTS scripts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    generated_at    TEXT NOT NULL,
    format          TEXT,                       -- S1 facet value
    target_length_sec INTEGER,
    hook            TEXT,                       -- the opening line/seconds
    beats           TEXT NOT NULL DEFAULT '[]', -- JSON list of beat objects
                                                 -- {label, content, timecode}
    body            TEXT,                       -- prose body
    cta             TEXT,                       -- call to action
    shot_list       TEXT NOT NULL DEFAULT '[]', -- JSON list of shot rows
                                                 -- {scene, broll, notes}
    source_yoinks   TEXT NOT NULL DEFAULT '[]', -- JSON list of citation
                                                 -- {video_id, slug, why}
    mode            TEXT NOT NULL DEFAULT 'agent',  -- agent | byo_key
    parent_script_id INTEGER,                   -- previous version (for revisions)
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_script_id) REFERENCES scripts(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_scripts_workspace ON scripts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_scripts_generated_at ON scripts(generated_at);
CREATE INDEX IF NOT EXISTS idx_scripts_parent ON scripts(parent_script_id);
