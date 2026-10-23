"""Settings writers preserve saved consent even in a process forced off."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import server
import uoink_mcp_tools as tools
import uoink_usage as usage
from tests.test_usage_sharing import store  # noqa: F401


@pytest.fixture
def settings(store, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_PATH", store / "settings.json")
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", lambda: "")
    monkeypatch.setattr(server, "_store_saved_anthropic_key", Mock())
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    monkeypatch.setattr(tools, "_b", lambda: server)
    handler = object.__new__(server.Handler)
    replies = []
    handler._send_json = lambda status, body: replies.append((status, body))
    server._write_settings({}, usage_choice=True)
    usage.count("searches")
    usage._queue.join()
    return SimpleNamespace(path=store / "settings.json", handler=handler, replies=replies)


WRITERS = (
    "partial_dict", "whole_dict", "settings_post", "output_folder", "role",
    "anthropic_invalid", "scrapecreators_invalid", "key_migration",
    "usage_prompt", "mirror_enable", "mirror_disable", "migration_toast",
)


def exercise_writer(name, settings, monkeypatch):
    handler = settings.handler
    if name == "partial_dict":
        server._write_settings({"notifications_enabled": False})
    elif name == "whole_dict":
        data = server._read_settings()
        data.update(notifications_enabled=False, usage_sharing=False)
        server._write_settings(data)
    elif name == "settings_post":
        handler._handle_settings_post({"notifications_enabled": False})
    elif name == "output_folder":
        output = settings.path.parent / "output"
        monkeypatch.setattr(server, "sys", SimpleNamespace(platform="win32"))
        monkeypatch.setattr(server, "_pick_output_folder", lambda _: str(output))
        handler._handle_settings_output_folder_pick({})
        assert json.loads(settings.path.read_text())["output_dir"] == str(output)
    elif name == "role":
        assert tools.set_user_role({"role": "researcher"})["ok"]
        assert json.loads(settings.path.read_text())["role"] == "researcher"
    elif name == "anthropic_invalid":
        server._mark_anthropic_key_invalid()
        assert json.loads(settings.path.read_text())["anthropic_key_invalid"]
    elif name == "scrapecreators_invalid":
        server._mark_scrapecreators_key_invalid()
        assert json.loads(settings.path.read_text())["scrapecreators_key_invalid"]
    elif name == "key_migration":
        data = json.loads(settings.path.read_text())
        data["anthropic_key"] = "synthetic-key"
        settings.path.write_text(json.dumps(data))
        server._migrate_plaintext_anthropic_key()
        server._store_saved_anthropic_key.assert_called_once_with("synthetic-key")
        assert "anthropic_key" not in json.loads(settings.path.read_text())
    elif name == "usage_prompt":
        handler._handle_usage_prompt()
        assert json.loads(settings.path.read_text())["usage_sharing_prompt_seen"]
    elif name in ("mirror_enable", "mirror_disable"):
        monkeypatch.setattr(server._platform, "capability_refusal", lambda _: None)
        if name == "mirror_disable":
            handler._library_mirror_disable()
        else:
            destination = str(settings.path.parent / "mirror")
            body = {"destination": destination, "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
                    "allowlist": [], "user_intent_token": "synthetic-intent"}
            payload = server._mirror_op_payload(destination, body["scope"], [])
            monkeypatch.setattr(server, "_validate_mirror_destination_path", lambda _: (destination, None))
            monkeypatch.setattr(server, "_mirror_preview_matches", lambda _: True)
            monkeypatch.setattr(server, "_library_session_hash", lambda: "synthetic-session")
            monkeypatch.setattr(server, "_read_volume_marker", lambda _: "synthetic-marker")
            monkeypatch.setattr(server, "_library_mirror", lambda: None)
            monkeypatch.setattr(server, "_mirror_intents", {
                server._mirror_token_hash(body["user_intent_token"]): {
                    "session_hash": "synthetic-session", "op_hash": server._mirror_op_hash(payload),
                    "expires_ms": server._mirror_now_ms() + 60000,
                }})
            handler._library_mirror_enable(body)
        assert json.loads(settings.path.read_text())["library_mirror_enabled"] is (name == "mirror_enable")
    elif name == "migration_toast":
        monkeypatch.setattr(server.migrate_install, "migration_marker_present", lambda _: True)
        monkeypatch.setattr(server, "maybe_toast", Mock())
        monkeypatch.setattr(server, "_bundled_icon_path", lambda: None)
        assert server._maybe_post_migration_toast()
        assert json.loads(settings.path.read_text())["post_migration_toast_shown"]
    else:
        raise AssertionError(name)
    for status, reply in settings.replies:
        assert status == 200 and reply["ok"], reply


@pytest.mark.parametrize("forced_off", [False, True])
@pytest.mark.parametrize("writer", WRITERS)
def test_every_non_consent_writer_preserves_opt_in(settings, monkeypatch, forced_off, writer):
    before = usage._read_state()
    if forced_off:
        monkeypatch.setenv("UOINK_USAGE_SHARING", "0")
    # All callers must reach the real writer without touching usage storage.
    with monkeypatch.context() as guard:
        write = Mock(wraps=server._write_settings)
        guard.setattr(server, "_write_settings", write)
        guard.setattr(usage, "set_enabled", Mock(side_effect=AssertionError("unrelated consent update")))
        exercise_writer(writer, settings, monkeypatch)
        write.assert_called_once()
        usage.set_enabled.assert_not_called()
    assert json.loads(settings.path.read_text())["usage_sharing"] is True
    assert server._read_settings()["usage_sharing"] is (not forced_off)
    assert usage._read_state() == before
    server._sync_usage_sharing()
    assert usage._read_state() == before
    if forced_off:
        usage.count("searches")
        usage._queue.join()
        assert not usage.send_due()
        assert usage._read_state() == before
    usage._post.assert_not_called()
    monkeypatch.delenv("UOINK_USAGE_SHARING", raising=False)
    server._sync_usage_sharing()
    payload = usage.disclosure()["next_payload"]
    assert payload["install_id"] == before["install_id"]
    assert payload["searches"] == 1


@pytest.mark.parametrize("forced_off", [False, True])
def test_explicit_settings_choice_changes_saved_consent(settings, monkeypatch, forced_off):
    first = usage._read_state()["install_id"]
    if forced_off:
        monkeypatch.setenv("UOINK_USAGE_SHARING", "0")
    for choice in (False, True, False, True):
        settings.handler._handle_settings_post({"usage_sharing": choice})
        status, reply = settings.replies[-1]
        assert status == 200 and reply["ok"]
        assert json.loads(settings.path.read_text())["usage_sharing"] is choice
        assert reply["settings"]["usage_sharing"] is (choice and not forced_off)
        assert reply["settings"]["usage_sharing_forced_off"] is forced_off
        server._sync_usage_sharing()
        state = usage._read_state()
        if choice:
            assert state["install_id"] != first
            first = state["install_id"]
            assert state["counts"] == {}
        else:
            assert "install_id" not in state and "counts" not in state
    usage._post.assert_not_called()


@pytest.mark.parametrize("forced_off", [False, True])
@pytest.mark.parametrize("saved", [{}, {"usage_sharing": False}, {"usage_sharing": True},
                                   {"usage_sharing": None}, {"usage_sharing": "true"},
                                   {"usage_sharing": 1}])
def test_non_consent_write_preserves_exact_saved_value(settings, monkeypatch, forced_off, saved):
    settings.path.write_text(json.dumps(saved))
    if forced_off:
        monkeypatch.setenv("UOINK_USAGE_SHARING", "0")
    # A stale or caller-supplied opt-in cannot change the current saved value.
    server._write_settings({"usage_sharing": True, "notifications_enabled": False})
    after = json.loads(settings.path.read_text())
    assert {k: v for k, v in after.items() if k == "usage_sharing"} == saved
    if "usage_sharing" in saved:
        assert type(after["usage_sharing"]) is type(saved["usage_sharing"])


@pytest.mark.parametrize("forced_off", [False, True])
@pytest.mark.parametrize("current", [False, True])
def test_stdio_writer_preserves_choice_changed_after_read(settings, monkeypatch, forced_off, current):
    server._write_settings({}, usage_choice=not current)
    script = r'''
import json, sys
from pathlib import Path
import server, uoink_mcp_tools as tools, uoink_usage as usage
root = Path(sys.argv[1])
server.SETTINGS_PATH = root / "settings.json"
usage.configure(lambda: root, "3.11.0")
tools.bind_backend(server)
stale = server._read_settings()
print("ready", flush=True)
sys.stdin.readline()
server._read_settings = lambda: dict(stale)
print(json.dumps(tools.set_user_role({"role": "researcher"})), flush=True)
'''
    env = dict(os.environ)
    if forced_off:
        env["UOINK_USAGE_SHARING"] = "0"
    child = subprocess.Popen([sys.executable, "-c", script, str(settings.path.parent)],
                             env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        server._write_settings({}, usage_choice=current)
        before = usage._read_state()
        out, err = child.communicate("continue\n", timeout=15)
        assert child.returncode == 0, err
        assert json.loads(out)["ok"], out
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    saved = json.loads(settings.path.read_text())
    assert saved["usage_sharing"] is current
    assert saved["role"] == "researcher"
    server._sync_usage_sharing()
    assert usage._read_state() == before


@pytest.mark.parametrize("seen", [True, False, "true", 1, None])
def test_prompt_seen_still_requires_saved_json_true(settings, seen):
    settings.path.write_text(json.dumps({"usage_sharing_prompt_seen": seen}))
    server._write_settings({"usage_sharing_prompt_seen": False})
    assert server._read_settings()["usage_sharing_prompt_seen"] is (seen is True)
