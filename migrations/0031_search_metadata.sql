-- Rank clip IDs without reading the much larger passage text rows.
CREATE INDEX IF NOT EXISTS idx_clips_search_metadata ON clips(clip_id, video_id, seq);
