"""Operator statements and unreviewed images are not playback acceptance."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/install_receipt"))
import p4_collect_evidence as collector
from p4_common import OPTIONAL_PLAYER_JUMP, PROTECTED_SENTINEL_BYTES


@pytest.fixture
def receipt(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    (profile / "records").mkdir(parents=True)
    (profile / "client").mkdir()
    (profile / "client/protected-sentinel.bin").write_bytes(PROTECTED_SENTINEL_BYTES)
    expected = {"items": {}, "chapter": {"title": "Synthetic chapter", "start": 34.0},
                "brief": {}, "protected_sentinel": {"path": str(profile / "client/protected-sentinel.bin")}}
    (profile / "expected.json").write_text(json.dumps(expected), encoding="utf8")
    (profile / "preparation.json").write_text(json.dumps({"product_findings": []}), encoding="utf8")
    monkeypatch.setattr(collector, "execute_checks", lambda binding: {"checkpoints": [], "product_findings": []})
    binding = {"isolated_profile": str(profile), "isolated_port": 18081,
               "instrument_only": True, "installed_credit": False}
    return profile, binding


def checkpoint(binding, operator, name):
    result = collector.collect(binding, operator)
    return next(row for row in result["checkpoints"] if row["name"] == name)


def test_matching_chapter_fields_without_an_image_remain_unobserved(receipt):
    profile, binding = receipt
    row = checkpoint(binding, {"chapter": {"title": "Synthetic chapter", "start": 34.0}}, "jump_chapter_fixture")
    assert row["status"] == "unobserved"


def test_player_boolean_and_url_without_an_image_remain_unobserved(receipt):
    profile, binding = receipt
    row = checkpoint(binding, {"optional_player_jump": {"observed": True, "url": OPTIONAL_PLAYER_JUMP["url"]}}, "optional_player_jump")
    assert row["status"] == "unobserved"


def test_unreviewed_image_file_does_not_prove_displayed_player_time(receipt):
    profile, binding = receipt
    image = profile / "not-a-player.png"
    image.write_bytes(b"This file contains no verified player observation.")
    row = checkpoint(binding, {"chapter": {"title": "Synthetic chapter", "start": 34.0,
                                           "screenshot": str(image)}}, "jump_chapter_fixture")
    assert row["status"] != "passed"


def test_completed_instrument_rows_merge_without_duplicate_status_or_client_credit(receipt, monkeypatch):
    profile, binding = receipt
    names = ["hostile_actions", "recall_silent_unavailable", "mirror_disconnect_reconnect",
             "user_edit_preservation", "deletion_cleanup"]
    monkeypatch.setattr(collector, "execute_checks", lambda binding: {
        "checkpoints": [{"name": name, "status": "passed"} for name in names], "product_findings": []})
    result = collector.collect(binding, {})
    rows = {row["name"]: row for row in result["checkpoints"]}
    assert rows["hostile_actions"]["status"] == "unobserved"
    assert rows["hostile_sentinel_instrument"]["status"] == "passed"
    assert all(rows[name]["status"] == "passed" for name in names[1:])


def test_local_attempt_is_not_mislabeled_as_blocked_x(receipt):
    profile, binding = receipt
    row = checkpoint(binding, {"follow_citation": {"attempted": True, "url": "library://items/example"}}, "follow_citation")
    assert row["status"] == "unobserved"


def test_missing_command_bindings_produce_no_executable_commands(receipt):
    profile, binding = receipt
    result = collector.operator_sequence(binding)
    assert result["refused_missing_inputs"]
    assert result["commands"] == []


def test_client_configuration_requires_original_child_with_bound_profile_and_port(tmp_path):
    from p4_prepare_client import validate_original_config
    from p4_common import IsolationError
    app = tmp_path / "App With Spaces"
    binding = {"installed_app": str(app), "installed_interpreter": str(app / "python/python.exe"),
               "isolated_profile": str(tmp_path / "Profile With Spaces"), "isolated_port": 18082}
    command = [binding["installed_interpreter"], "-B", str(app / "uoink_mcp.py"),
               "--isolated-profile", binding["isolated_profile"], "--isolated-port", "18082"]
    config = {"mcpServers": {"uoink": {"command": command[0], "args": [
        "tap.py", "--route-label", "original-installed", "--", *command]}}}
    validate_original_config(config, binding)
    config["mcpServers"]["uoink"]["args"][2] = "fixture-attached"
    with pytest.raises(IsolationError):
        validate_original_config(config, binding)
    config["mcpServers"]["uoink"]["args"][2] = "original-installed"
    config["mcpServers"]["uoink"]["args"][-1] = "18083"
    with pytest.raises(IsolationError):
        validate_original_config(config, binding)


def test_client_driver_requires_explicit_auth_and_credit_acknowledgements(tmp_path):
    from types import SimpleNamespace
    from p4_operator import require_client_acknowledgements
    from p4_common import IsolationError
    args = SimpleNamespace(subscription_confirmed=False, usage_credits_off=False,
                           client_exe=tmp_path / "claude.exe", prompt_file=tmp_path / "prompt.txt")
    with pytest.raises(IsolationError):
        require_client_acknowledgements(args)


def test_mutated_guard_is_preserved_and_restoration_fails(tmp_path):
    import base64
    from p4_common import restore_guard
    path = tmp_path / "sitecustomize.py"
    path.write_bytes(b"changed by another owner")
    result = restore_guard({"mutations": [{"action": "created", "path": str(path),
            "payload_b64": base64.b64encode(b"receipt original").decode()}]})
    assert result["ok"] is False
    assert path.read_bytes() == b"changed by another owner"


def test_provenance_deadline_applies_when_child_keeps_stdout_open(tmp_path):
    import os
    import time
    from p4_common import probe_runtime_provenance
    (tmp_path / "p4-runtime-probe.py").write_text("import time; time.sleep(30)\n", encoding="utf8")
    started = time.monotonic()
    result = probe_runtime_provenance(Path(sys.executable), tmp_path, dict(os.environ),
                                     cwd=tmp_path, timeout_s=0.2)
    assert time.monotonic() - started < 4
    assert result["ok"] is False
    assert result["error"] == "runtime_probe_timeout"
    assert result["cleanup"]["cleaned"] is True
