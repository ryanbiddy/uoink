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


def standing_fixture():
    import hashlib
    from datetime import datetime, timezone
    feed, guid = "http://c22-fixture.invalid/standing-first/feed.xml", "c22-standing-ep-1"
    identity = (feed + "\n" + guid).encode()
    key, video = "podcast:" + hashlib.sha256(identity).hexdigest(), "episode_" + hashlib.sha1(identity).hexdigest()[:11]
    row = {"capture_key": key, "video_id": video, "committed_at_ms": 2000,
           "state": "pending", "run_id": None, "version_id": None, "prompt_hash": None,
           "source_revision": None, "work_id": None, "last_error_code": None, "updated_at_ms": 2000}
    outcome = {"episode_guid": guid, "synthetic_url": feed, "ledger": {
        "starts": [{"capture_key": key, "video_id": video, "state": "succeeded", "started_at_ms": 1000, "finished_at_ms": 2000}],
        "standing_charge_count": 1, "publication_count": 1}}
    before = {"phase2": {"source_classification_outbox": []}}
    after = {"phase2": {"source_classification_outbox": [row]}, "utc": datetime.fromtimestamp(4, timezone.utc).isoformat()}
    return before, after, outcome


@pytest.mark.parametrize("field,value", [("capture_key", "wrong"), ("video_id", "wrong"), ("run_id", "injected"),
    ("state", "enqueued"), ("committed_at_ms", 2001), ("updated_at_ms", 5000), ("extra", 1)])
def test_declared_capture_still_rejects_invalid_outbox_fields(field, value):
    b, a, outcome = standing_fixture()
    a["phase2"]["source_classification_outbox"][0][field] = value
    allowed = derive_phase2_allowed(before=b, after=a, admitted=outcome, profile_name="standing-first")
    assert phase2_compare(b, a, allowed)["ok"] is False


@pytest.mark.parametrize("waiting", [False, True])
def test_exact_declared_outbox_matches_supported_no_policy_transition(waiting):
    b, a, outcome = standing_fixture()
    if waiting:
        a["phase2"]["source_classification_outbox"][0].update(state="waiting_configuration", last_error_code="no_policy", updated_at_ms=3000)
    allowed = derive_phase2_allowed(before=b, after=a, admitted=outcome, profile_name="standing-first")
    assert phase2_compare(b, a, allowed)["ok"] is True


def test_renamed_taxonomy_requires_same_bytes():
    settings = {"librarian_apply_enabled": False}
    b = {"settings": settings, "files": {"taxonomy.json": {"sha256": "same"}}}
    a = {"settings": settings, "files": {"taxonomy.json.migrated": {"sha256": "same"}}}
    assert settings_and_pins_unchanged(b, a)["ok"] is True


@pytest.mark.parametrize("fail_observer", [False, True])
def test_browser_guard_and_helper_span_observation_then_stop(tmp_path, monkeypatch, fail_observer):
    import json
    from types import SimpleNamespace
    from install_receipt import browser_checkpoint as browser
    (tmp_path / "evidence").mkdir()
    (tmp_path / "artifacts").mkdir()
    runner = SimpleNamespace(receipt_root=tmp_path, load_inputs=lambda: {
        "installed_app": {"path": str(tmp_path / "app")}, "isolated_port": 18321})
    events = []
    class Launcher:
        def __init__(self, r): pass
        def start(self, **kwargs):
            events.append("start")
            return {"child": {"pid": 1}, "health": {"ok": True}}
        def stop_owned(self, **kwargs):
            events.append("stop")
            return {"stopped": True, "port_freed": True}
    monkeypatch.setattr(browser, "InstalledHelperLauncher", Launcher)
    monkeypatch.setattr(browser, "read_token_with_note", lambda *a: {"token": "fixture"})
    monkeypatch.setattr(browser, "snapshot_with_measured_ids", lambda *a, **kw: {"label": kw["label"]})
    def observe(record):
        assert events == ["start"]
        events.append("observe")
        if fail_observer:
            raise RuntimeError("interrupted observation")
    if fail_observer:
        with pytest.raises(RuntimeError, match="interrupted observation"):
            browser.run_checkpoint(runner, observe=observe)
    else:
        assert browser.run_checkpoint(runner, observe=observe)["status"] == "unobserved"
    assert events == ["start", "observe", "stop"]
    retained = json.loads((tmp_path / "evidence/browser-held-observation.json").read_text())
    assert retained["installed_credit"] is False
    assert retained["screenshot"] is None
    assert retained["stop"]["stopped"] is True


def test_binding_checks_reject_missing_or_escaping_compiler_inputs(tmp_path):
    from install_receipt.receipt_integrity import verify_installed_bindings
    result = verify_installed_bindings(tmp_path, {"files_by_path": {"../escape.py": {}}})
    assert result["ok"] is False
    assert any("escapes" in issue for issue in result["problems"])


def test_missing_handle_never_sends_quit_http(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from install_receipt import launcher as module
    launcher = module.InstalledHelperLauncher(SimpleNamespace(record_event=lambda *a, **kw: None))
    monkeypatch.setattr(module, "wait_port_freed", lambda *a: True)
    def forbidden(*a, **kw):
        raise AssertionError("HTTP cannot be authorized without the held process")
    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
    result = launcher.stop_owned(port=18321, identity={"pid": 1}, token="fixture", record={})
    assert result["stopped"] is False
    assert result["refused_pid_only"] is True
