-- Saves the user put on a shelf by hand (a move, a Tidy accept, a shelf named
-- at capture). Automatic routing (a new capture of the same link, an import
-- folder, a late transcript, an old hint) never changes their shelf. seq goes
-- up with each hand move of that save, so an undo can tell whether the save
-- was moved again since. A separate table keeps the yoinks row untouched, so
-- a re-save never wipes it.
CREATE TABLE IF NOT EXISTS shelf_by_hand (
    video_id TEXT PRIMARY KEY REFERENCES yoinks(video_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 1,
    set_at TEXT NOT NULL
);
