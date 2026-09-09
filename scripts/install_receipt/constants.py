"""Fail-closed constants for the C22 operator kit."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_PORT = 5179
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})
ORDINARY_USERPROFILE = r"C:\Users\hello"
LIVE_INDEX_TAIL = ("Uoink", "index.db")
YOINK_INDEX_TAIL = ("Yoink", "index.db")
# Conventional live index string. Never opened or hashed by this kit.
ORDINARY_LIVE_INDEX = str(
    Path(ORDINARY_USERPROFILE) / "AppData" / "Local" / "Uoink" / "index.db"
)
SYNTHETIC_HOSTNAME = "c22-fixture.invalid"

ISOLATED_PROFILE_FLAG = "--isolated-profile"
ISOLATED_PORT_FLAG = "--isolated-port"
ISOLATED_FROM_INSTALL_FLAG = "--isolated-from-install-dir"
INNO_ISOLATED_FLAG = "/ISOLATED=1"
INNO_PROFILE_FLAG = "/PROFILE="
INNO_PORT_FLAG = "/PORT="
INNO_DIR_FLAG = "/DIR="
INNO_NOCLOSE_FLAG = "/NOCLOSEAPPLICATIONS"
INNO_NORESTARTAPPS_FLAG = "/NORESTARTAPPLICATIONS"
INNO_FORBIDDEN_OVERRIDES = frozenset({
    "/CLOSEAPPLICATIONS",
    "/FORCECLOSEAPPLICATIONS",
    "/RESTARTAPPLICATIONS",
})
MARKER_FILENAME = "isolated-install.json"
TOKEN_FILENAME = "token.txt"

# Dedicated data identities for the three capture orderings plus child cases.
CAPTURE_PROFILE_NAMES = (
    "empty",
    "populated",
    "one-off",
    "manual-first",
    "standing-first",
    "child-life",
    "child-interrupt",
    "child-regfail",
    "relaunch",
)

DEFAULT_HELPER_NAMES = frozenset({
    "start_server.ps1",
    "start_server.bat",
    "launch.bat",
})

MODEL_PROCESS_STEMS = frozenset({
    "claude", "codex", "gemini", "grok", "whisperx", "anthropic",
})

REQUIRED_OPERATOR_INPUTS = (
    "installed_app_path",
    "package_path",
    "package_sha256",
    "isolated_profile",
    "isolated_port",
    "receipt_root",
)

# AS-7 C22 list plus the kit brief's executable scenario set.
SCENARIO_IDS = (
    "install",
    "installed_provenance",
    "empty_migration_replay",
    "populated_legacy_replay",
    "one_off_capture",
    "manual_first",
    "standing_first",
    "whole_helper_relaunch",
    "registered_child_lifetime",
    "launch_interruption",
    "registration_failure",
    "browser_state_checkpoint",
    "protected_phase2_state",
    "upgrade_operator_step",
)

LEGACY_FIXTURE_VERSION = "c22-legacy-populated-v1-schema27"
LEGACY_SCHEMA_VERSION = 27
CURRENT_SCHEMA_TARGET = 30

SYNTHETIC_AUDIO = b"C22 SYNTHETIC AUDIO PLACEHOLDER"
SYNTHETIC_TRANSCRIPT = {
    "model": "synthetic-C22",
    "language": "en",
    "diarization_ran": False,
    "segments": [
        {
            "start": 12.5,
            "end": 21.75,
            "text": "C22 fixture: durable capture waits for complete publication.",
        }
    ],
}

PROTECTED_PHASE2_TABLES = (
    "library_meta",
    "library_runs",
    "library_manifest",
    "library_work",
    "library_attempts",
    "shelves",
    "shelf_versions",
    "shelf_nodes",
    "item_shelves",
    "source_classification_policy",
    "source_classification_outbox",
)

LEDGER_TABLES = (
    "source_subscriptions",
    "source_consent_receipts",
    "source_user_intents",
    "source_detection_cursors",
    "source_items",
    "source_capture_starts",
)

PHASE2_FILES = (
    "settings.json",
    "taxonomy.json",
    "taxonomy.json.migrated",
    "index.db",
)

# Schema 0027 library_meta defaults. Do not copy an observed singleton.
LIBRARY_META_SCHEMA_DEFAULTS = {
    "singleton": 1,
    "projection_revision": 0,
    "active_version_id": None,
    "last_operation_sequence": 0,
    "recovery_state": "ready",
}

LIBRARY_WORK_STATES = frozenset({
    "ready", "leased", "accepted", "unmapped", "unsupported", "blocked",
    "cancelled",
})
OUTBOX_STATES = frozenset({
    "pending", "waiting_configuration", "enqueued", "blocked",
})

# Already-committed Astra seal. This kit consumes it; it does not invent one.
CANDIDATE_PACKAGE_02_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs" / "library" / "proof" / "candidate-package-02-2026-09-09"
)

REQUIRED_PROVENANCE_MODULES = (
    "server",
    "source_subscriptions",
    "index",
    "uoink_mcp",
    "source_manifest",
    "podcasts",
    "library_work",
)

INJECTION_ENV = {
    "C22_ALLOWED_PORTS": "declared loopback helper and fixture ports",
    "C22_ISOLATED_PROFILE": "absolute isolated data root",
    "C22_FORBIDDEN_LIVE": "ordinary live index path that must never open",
    "IG_FORBIDDEN_LIVE": "integrator live-index string retained even if LOCALAPPDATA changes",
    "C22_INJECT": "empty | launch_interrupt | registration_failure | spawn_child",
    "C22_SYNTHETIC": "1 when this is a labeled non-installed instrument check",
    "C22_SYNTHETIC_HOST": "c22-fixture.invalid",
    "C22_FIXTURE_LOOPBACK": "declared loopback fixture base http://127.0.0.1:<port>",
}
