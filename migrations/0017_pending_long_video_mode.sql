-- v3.2.4: retain the user's long-video retry mode across helper restarts.
ALTER TABLE pending_yoinks
    ADD COLUMN long_video_mode TEXT NOT NULL DEFAULT 'full';
