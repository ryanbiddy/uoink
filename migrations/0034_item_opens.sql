-- When the reader last opened each saved item. Local only. Powers the
-- "Rediscover" shelf ("You haven't opened this yet"). A separate table keeps
-- the yoinks row untouched, so a re-save never wipes it.
CREATE TABLE IF NOT EXISTS item_opens (
    video_id TEXT PRIMARY KEY,
    last_opened_at TEXT NOT NULL
);
