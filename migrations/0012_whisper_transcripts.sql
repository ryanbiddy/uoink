-- v3.1 WhisperX transcription pipeline.
--
-- Per PROMPT-V3.1 track B step 3 + track D (A1 re-transcription).
-- Both flows share the WhisperX worker + model -- one runtime, two
-- entry points (podcast episodes vs. existing yoinks).
--
-- Adds the per-row transcription metadata so the dashboard can show
-- which model was used, whether diarization ran, and where the JSON
-- transcript landed on disk.
--
-- Audio-only podcast episodes get their transcript here; existing
-- yoinks (with YouTube auto-captions) get a parallel field on the
-- sidecar (handled lazily by the helper without a schema change).

ALTER TABLE podcast_episodes ADD COLUMN transcript_local_path TEXT;
ALTER TABLE podcast_episodes ADD COLUMN transcript_status TEXT
    NOT NULL DEFAULT 'none';
    -- none | queued | running | done | failed
ALTER TABLE podcast_episodes ADD COLUMN transcript_model_used TEXT;
    -- tiny | base | small | medium | large -- echoes settings.whisper_model
ALTER TABLE podcast_episodes ADD COLUMN diarization_ran INTEGER
    NOT NULL DEFAULT 0;
ALTER TABLE podcast_episodes ADD COLUMN transcript_finished_at TEXT;
ALTER TABLE podcast_episodes ADD COLUMN transcript_error TEXT;
CREATE INDEX IF NOT EXISTS idx_podcast_episodes_transcript_status
    ON podcast_episodes(transcript_status);
