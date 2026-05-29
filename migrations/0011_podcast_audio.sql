-- v3.1 podcast audio download pipeline.
--
-- Per PROMPT-V3.1 track B step 2: download MP3 + extract metadata for
-- queued episodes. The actual download is yt-dlp + ffmpeg orchestration
-- in podcasts.py; this migration just adds the per-episode persistence
-- of where the audio landed + the download timestamp + error tracking.
--
-- Whisper transcription (step 3, separate PR) reads audio_local_path
-- to feed WhisperX.

ALTER TABLE podcast_episodes ADD COLUMN audio_local_path TEXT;
ALTER TABLE podcast_episodes ADD COLUMN audio_downloaded_at TEXT;
ALTER TABLE podcast_episodes ADD COLUMN audio_size_bytes INTEGER;
ALTER TABLE podcast_episodes ADD COLUMN audio_download_error TEXT;
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_audio_local
    ON podcast_episodes(audio_local_path);
