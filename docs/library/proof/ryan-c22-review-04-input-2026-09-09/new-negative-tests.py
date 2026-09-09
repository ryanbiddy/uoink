"""Independent false-positive regressions; synthetic dictionaries only."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt.constants import LIBRARY_META_SCHEMA_DEFAULTS
from install_receipt.oracles import (
    derive_phase2_allowed, library_meta_matches_schema_default,
    modules_inside_app, phase2_compare, settings_and_pins_unchanged,
)
from install_receipt.scenarios import ScenarioRunner


def compare_new(table, rows, admitted=None):
    before = {"phase2": {table: []}}
    after = {"phase2": {table: rows}}
    allowed = derive_phase2_allowed(before=before, after=after,
        admitted=admitted, profile_name="standing-first")
    return phase2_compare(before, after, allowed)


def test_meta_requires_complete_schema_shape():
    assert library_meta_matches_schema_default({"singleton": 1}) is False


def test_meta_extra_field_is_not_a_default():
    assert compare_new("library_meta", [dict(LIBRARY_META_SCHEMA_DEFAULTS, extra=1)])["ok"] is False


def test_duplicate_meta_is_not_one_singleton():
    assert compare_new("library_meta", [dict(LIBRARY_META_SCHEMA_DEFAULTS)] * 2)["ok"] is False


def test_known_video_does_not_authorize_classification_work():
    row = {"work_id": "injected", "run_id": "unapproved", "video_id": "admitted",
           "kind": "assign", "state": "accepted", "packet_json": "invented", "attempts": 99}
    assert compare_new("library_work", [row], {"ledger": {"video_ids": ["admitted"]}})["ok"] is False


@pytest.mark.parametrize("row", [
    {"capture_key": "unrelated", "video_id": "admitted", "state": "pending"},
    {"capture_key": "known", "video_id": "wrong", "state": "pending"},
    {"capture_key": "known", "video_id": "admitted", "state": "enqueued", "run_id": "invented"},
])
def test_outbox_cannot_authorize_itself_from_ledger_id(row):
    assert compare_new("source_classification_outbox", [row],
        {"ledger": {"video_ids": ["admitted"], "capture_keys": ["known"]}})["ok"] is False


@pytest.mark.parametrize("after_files", [{}, {"taxonomy.json.migrated": {"sha256": "different"}}])
def test_taxonomy_disappearance_is_not_migration(after_files):
    settings = {"librarian_apply_enabled": False, "pins": []}
    before = {"settings": settings, "files": {"taxonomy.json": {"sha256": "original"}}}
    after = {"settings": settings, "files": after_files}
    assert settings_and_pins_unchanged(before, after)["ok"] is False


def test_provenance_does_not_accept_sibling_prefix(tmp_path):
    app = tmp_path / "app"
    report = {"modules": {"server": {"ok": True, "file": str(tmp_path / "app-other" / "server.py")}}}
    assert modules_inside_app(report, app)["ok"] is False


def test_empty_module_report_does_not_pass(tmp_path):
    assert modules_inside_app({"modules": {}}, tmp_path / "app")["ok"] is False


def test_child_status_flags_without_raw_settlement_do_not_pass(tmp_path, monkeypatch):
    scenario = object.__new__(ScenarioRunner)
    monkeypatch.setattr(scenario, "_profile", lambda name: tmp_path)
    monkeypatch.setattr(scenario, "_inputs", lambda: {"isolated_port": 18321})
    result = {"children": [{"pid": 123, "created_ms": 456, "executable": "fixture.exe", "liveness": "alive"}],
              "helper_killed_while_child_alive": True, "second_identity": {"pid": 789},
              "child_exited": True, "duplicate_launch": False,
              "instrument": {"instrument": {"product_module": "source_subscriptions.py"}}}
    monkeypatch.setattr(scenario, "_with_helper", lambda *args, **kwargs: result)
    monkeypatch.setattr(scenario, "record", lambda sid, status, **fields: {"id": sid, "status": status, **fields})
    assert scenario._child_lifetime()["status"] == "fail"
