CREATE TABLE IF NOT EXISTS media_depth (
    video_id TEXT PRIMARY KEY NOT NULL,
    source_revision TEXT NOT NULL CHECK (
        length(source_revision)=64 AND source_revision NOT GLOB '*[^0-9a-f]*'),
    cue_revision TEXT NOT NULL CHECK (
        length(cue_revision)=64 AND cue_revision NOT GLOB '*[^0-9a-f]*'),
    media_revision TEXT NOT NULL CHECK (
        length(media_revision)=64 AND media_revision NOT GLOB '*[^0-9a-f]*'),
    chapter_state TEXT NOT NULL CHECK (
        chapter_state IN ('present','absent','invalid','unsupported')),
    speaker_state TEXT NOT NULL CHECK (
        speaker_state IN ('present','partial','absent','invalid','unsupported')),
    diarization_state TEXT NOT NULL CHECK (
        diarization_state IN ('not_requested','succeeded','failed','legacy_reported')),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json)='object'),
    playback_json TEXT NOT NULL CHECK (
        json_valid(playback_json) AND json_type(playback_json)='object'),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE,
    UNIQUE (video_id, source_revision)
);

CREATE TABLE IF NOT EXISTS diarization_runs (
    video_id TEXT NOT NULL,
    run_id TEXT NOT NULL CHECK (
        length(run_id) BETWEEN 1 AND 96 AND run_id NOT GLOB '*[^A-Za-z0-9_-]*'),
    cue_revision TEXT NOT NULL CHECK (
        length(cue_revision)=64 AND cue_revision NOT GLOB '*[^0-9a-f]*'),
    status TEXT NOT NULL CHECK (status IN ('succeeded','failed','legacy_reported')),
    producer TEXT NOT NULL,
    producer_version TEXT,
    model TEXT,
    generated_at TEXT,
    input_media_sha256 TEXT CHECK (input_media_sha256 IS NULL OR (
        length(input_media_sha256)=64 AND input_media_sha256 NOT GLOB '*[^0-9a-f]*')),
    artifact_sha256 TEXT NOT NULL CHECK (
        length(artifact_sha256)=64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'),
    parameters_json TEXT NOT NULL CHECK (
        json_valid(parameters_json) AND json_type(parameters_json)='object'),
    PRIMARY KEY (video_id, run_id),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
    video_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    start REAL NOT NULL CHECK (start >= 0 AND start <= 31536000),
    end REAL NOT NULL CHECK (end > start AND end <= 31536000),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json)='object'),
    PRIMARY KEY (video_id, source_revision, seq),
    FOREIGN KEY (video_id, source_revision)
        REFERENCES media_depth(video_id, source_revision) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chapters_video_time ON chapters(video_id, start, end);

ALTER TABLE citations ADD COLUMN speaker TEXT;
ALTER TABLE citations ADD COLUMN speaker_provenance_json TEXT CHECK (
    speaker_provenance_json IS NULL OR
    (json_valid(speaker_provenance_json) AND json_type(speaker_provenance_json)='object'));

ALTER TABLE clips ADD COLUMN media_revision TEXT CHECK (media_revision IS NULL OR (
    length(media_revision)=64 AND media_revision NOT GLOB '*[^0-9a-f]*'));
ALTER TABLE clips ADD COLUMN speaker_state TEXT NOT NULL DEFAULT 'absent'
    CHECK (speaker_state IN ('present','partial','absent','invalid','unsupported'));
ALTER TABLE clips ADD COLUMN speaker_labels_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(speaker_labels_json) AND json_type(speaker_labels_json)='array');
ALTER TABLE clips ADD COLUMN speaker_spans_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(speaker_spans_json) AND json_type(speaker_spans_json)='array');
ALTER TABLE clips ADD COLUMN chapter_seq INTEGER CHECK (chapter_seq IS NULL OR chapter_seq >= 0);
ALTER TABLE clips ADD COLUMN chapter_seqs_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(chapter_seqs_json) AND json_type(chapter_seqs_json)='array');
CREATE INDEX IF NOT EXISTS idx_clips_chapter ON clips(video_id, chapter_seq);
CREATE INDEX IF NOT EXISTS idx_clips_speaker ON clips(video_id, speaker);
CREATE INDEX IF NOT EXISTS idx_citations_speaker ON citations(video_id, speaker);
