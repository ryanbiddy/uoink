-- DRAFT ONLY: run F Phase 2 contract, 2026-09-04.
-- Fable must reserve 0027 before copying this into migrations/.
-- Execute inside the existing migration transaction, with foreign_keys=ON.
-- No model calls, taxonomy seed, jobs, assignments, or enabled apply flag.

CREATE TABLE shelves (
    shelf_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE shelf_versions (
    version_id TEXT PRIMARY KEY,
    parent_version_id TEXT REFERENCES shelf_versions(version_id),
    revision_hash TEXT NOT NULL UNIQUE CHECK(length(revision_hash)=64),
    status TEXT NOT NULL CHECK(status IN ('draft','approved','active','superseded','rolled_back')),
    created_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT
);
CREATE UNIQUE INDEX library_one_active_taxonomy ON shelf_versions(status) WHERE status='active';
CREATE TABLE shelf_nodes (
    version_id TEXT NOT NULL REFERENCES shelf_versions(version_id),
    shelf_id TEXT NOT NULL REFERENCES shelves(shelf_id),
    parent_shelf_id TEXT,
    name TEXT NOT NULL,
    path_json TEXT NOT NULL CHECK(json_valid(path_json)),
    definition TEXT NOT NULL,
    include_json TEXT NOT NULL CHECK(json_valid(include_json)),
    exclude_json TEXT NOT NULL CHECK(json_valid(exclude_json)),
    retired INTEGER NOT NULL DEFAULT 0 CHECK(retired IN (0,1)),
    PRIMARY KEY(version_id,shelf_id),
    UNIQUE(version_id,path_json),
    FOREIGN KEY(version_id,parent_shelf_id) REFERENCES shelf_nodes(version_id,shelf_id)
);
CREATE TABLE library_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    projection_revision INTEGER NOT NULL DEFAULT 0 CHECK(projection_revision>=0),
    active_version_id TEXT REFERENCES shelf_versions(version_id),
    last_operation_sequence INTEGER NOT NULL DEFAULT 0,
    recovery_state TEXT NOT NULL DEFAULT 'ready' CHECK(recovery_state IN ('ready','pending','conflict'))
);
INSERT INTO library_meta(singleton) VALUES(1);
CREATE TABLE library_runs (
    run_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES shelf_versions(version_id),
    manifest_hash TEXT NOT NULL CHECK(length(manifest_hash)=64),
    run_revision INTEGER NOT NULL DEFAULT 1 CHECK(run_revision>0),
    state TEXT NOT NULL CHECK(state IN ('preparing','collecting','review','closed','cancelled')),
    policy_json TEXT NOT NULL CHECK(json_valid(policy_json)),
    created_at TEXT NOT NULL
);
CREATE TABLE library_manifest (
    run_id TEXT NOT NULL REFERENCES library_runs(run_id),
    video_id TEXT NOT NULL,
    source_revision TEXT NOT NULL CHECK(length(source_revision)=64),
    disposition TEXT NOT NULL CHECK(disposition IN
        ('waiting','accepted','rejected','unmapped','unsupported','pinned','deleted','changed','cancelled')),
    reason TEXT,
    PRIMARY KEY(run_id,video_id)
    -- Intentionally no yoinks FK: deletion must leave an accounted manifest entry.
);
CREATE TABLE library_work (
    work_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'assign' CHECK(kind='assign'),
    packet_generation INTEGER NOT NULL DEFAULT 1 CHECK(packet_generation>0),
    packet_json TEXT NOT NULL CHECK(json_valid(packet_json)),
    packet_hash TEXT NOT NULL CHECK(length(packet_hash)=64),
    state TEXT NOT NULL CHECK(state IN ('ready','leased','accepted','unmapped','unsupported','blocked','cancelled')),
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id,video_id),
    FOREIGN KEY(run_id,video_id) REFERENCES library_manifest(run_id,video_id)
);
CREATE INDEX library_work_ready ON library_work(state,priority,created_at,work_id);
CREATE TABLE library_attempts (
    attempt_token TEXT PRIMARY KEY CHECK(length(attempt_token)>=43),
    work_id TEXT NOT NULL REFERENCES library_work(work_id),
    attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
    packet_generation INTEGER NOT NULL,
    client_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    taxonomy_revision TEXT NOT NULL,
    lease_expires_ms INTEGER NOT NULL,
    lease_max_ms INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('current','submitted','expired','cancelled','invalidated')),
    UNIQUE(work_id,attempt_number)
);
CREATE UNIQUE INDEX library_one_current_attempt ON library_attempts(work_id) WHERE state='current';
CREATE TABLE library_submissions (
    submission_key TEXT PRIMARY KEY,
    attempt_token TEXT NOT NULL UNIQUE REFERENCES library_attempts(attempt_token),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    outcome TEXT NOT NULL CHECK(outcome IN ('accepted','rejected','unmapped','unsupported','error')),
    result_json TEXT NOT NULL CHECK(json_valid(result_json)),
    response_json TEXT NOT NULL CHECK(json_valid(response_json)),
    usage_json TEXT NOT NULL CHECK(json_valid(usage_json)),
    created_at TEXT NOT NULL
);
CREATE TABLE library_proposals (
    run_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    shelf_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    submission_key TEXT NOT NULL REFERENCES library_submissions(submission_key),
    is_primary INTEGER NOT NULL CHECK(is_primary IN (0,1)),
    confidence REAL NOT NULL CHECK(confidence>=0 AND confidence<=1),
    evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
    PRIMARY KEY(run_id,video_id,shelf_id),
    FOREIGN KEY(run_id,video_id) REFERENCES library_manifest(run_id,video_id),
    FOREIGN KEY(version_id,shelf_id) REFERENCES shelf_nodes(version_id,shelf_id)
);
CREATE UNIQUE INDEX library_one_proposed_primary ON library_proposals(run_id,video_id) WHERE is_primary=1;
CREATE TABLE item_shelves (
    video_id TEXT NOT NULL REFERENCES yoinks(video_id) ON DELETE CASCADE,
    shelf_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('agent','user')),
    locked INTEGER NOT NULL CHECK(locked IN (0,1)),
    is_primary INTEGER NOT NULL CHECK(is_primary IN (0,1)),
    confidence REAL CHECK(confidence>=0 AND confidence<=1),
    evidence_json TEXT CHECK(evidence_json IS NULL OR json_valid(evidence_json)),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY(video_id,shelf_id),
    FOREIGN KEY(version_id,shelf_id) REFERENCES shelf_nodes(version_id,shelf_id),
    CHECK((locked=1 AND source='user' AND confidence IS NULL) OR locked=0),
    CHECK(source='user' OR (confidence IS NOT NULL AND evidence_json IS NOT NULL))
);
CREATE UNIQUE INDEX library_one_primary ON item_shelves(video_id) WHERE is_primary=1;
CREATE TABLE library_item_policy (
    video_id TEXT PRIMARY KEY REFERENCES yoinks(video_id) ON DELETE CASCADE,
    exclusive_move INTEGER NOT NULL DEFAULT 0 CHECK(exclusive_move IN (0,1))
);
CREATE TABLE library_previews (
    preview_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES library_runs(run_id),
    expected_projection_revision INTEGER NOT NULL,
    delta_hash TEXT NOT NULL CHECK(length(delta_hash)=64),
    binding_json TEXT NOT NULL CHECK(json_valid(binding_json)),
    forward_json TEXT NOT NULL CHECK(json_valid(forward_json)),
    inverse_json TEXT NOT NULL CHECK(json_valid(inverse_json)),
    summary_json TEXT NOT NULL CHECK(json_valid(summary_json)),
    expires_ms INTEGER NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    approved_churn_percent INTEGER CHECK(approved_churn_percent BETWEEN 15 AND 100)
);
-- Includes no-change receipts, which advance the durable operation sequence
-- without pretending that the assignment projection changed.
CREATE TABLE library_operation_receipts (
    operation_key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    operation_sequence INTEGER NOT NULL UNIQUE,
    authoritative_record_hash TEXT NOT NULL CHECK(length(authoritative_record_hash)=64),
    receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json))
);
CREATE TABLE library_user_intents (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    kind TEXT NOT NULL CHECK(kind IN ('pin','undo')),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    session_hash TEXT NOT NULL,
    expires_ms INTEGER NOT NULL,
    consumed_by TEXT REFERENCES library_operation_receipts(operation_key)
);
CREATE TABLE library_applies (
    apply_id TEXT PRIMARY KEY,
    operation_key TEXT NOT NULL UNIQUE REFERENCES library_operation_receipts(operation_key),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    kind TEXT NOT NULL CHECK(kind IN ('apply','activate','pin','undo')),
    before_revision INTEGER NOT NULL,
    after_revision INTEGER NOT NULL CHECK(after_revision=before_revision+1),
    operation_sequence INTEGER NOT NULL UNIQUE,
    authoritative_record_hash TEXT NOT NULL CHECK(length(authoritative_record_hash)=64),
    forward_json TEXT NOT NULL CHECK(json_valid(forward_json)),
    inverse_json TEXT NOT NULL CHECK(json_valid(inverse_json)),
    receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json)),
    undo_of TEXT UNIQUE REFERENCES library_applies(apply_id),
    created_at TEXT NOT NULL
);
