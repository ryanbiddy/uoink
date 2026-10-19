"""Darwin refusals happen before settings, index, ledger or destination I/O."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import _platform
import library_mirror
import server
import uoink_mcp_tools

CODE = "library_mirror_unavailable_macos"


def forbidden(*args, **kwargs):
    raise AssertionError("Unsupported operation reached a side effect")


@pytest.fixture
def darwin(monkeypatch):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin"))


@pytest.mark.parametrize("platform,available", [("darwin", False), ("win32", True), ("linux", True)])
def test_platform_capability(monkeypatch, platform, available):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    capability = _platform.library_mirror_capability()
    assert capability["available"] is available
    if not available:
        assert capability["code"] == CODE
        assert "macOS" in capability["reason"]
    else:
        assert _platform.capability_refusal(capability) is None


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_retain_disabled_mirror_behavior(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    mirror = library_mirror.Mirror(None, None, None, data_root=tmp_path, consent=None, enabled=False)
    assert mirror.status()["ok"] is True
    assert mirror.resync() == {"ok": True, "schema_version": 1,
                               "contract_version": "phase4-v1-2026-09-08",
                               "synced": 0, "enabled": False, "state": "disabled"}
    assert mirror.on_committed_event("capture") is None


@pytest.mark.parametrize("operation,args", [("preview", ("/must-not-probe", "all_current_and_future_items")),
    ("status", ()), ("resync", ()), ("purge", ("item",)), ("tombstone", ("item",)),
    ("restore", ("item",)), ("on_committed_event", ("hard_purge",))])
def test_direct_mirror_refuses_before_even_reading_instance(darwin, operation, args):
    # No constructor: any instance-field access before the gate fails.
    result = getattr(object.__new__(library_mirror.Mirror), operation)(*args)
    assert result["ok"] is False
    assert result["enabled"] is False
    assert result["error"]["code"] == result["code"] == CODE


@pytest.mark.parametrize("op", ["preview", "enable", "disable", "resync", "status"])
def test_http_dispatch_refuses_before_operations(darwin, monkeypatch, op):
    probe = object.__new__(server.Handler)
    responses = []
    probe._send_json = lambda status, payload: responses.append((status, payload))
    for method in ("_library_mirror_preview", "_library_mirror_enable", "_library_mirror_disable",
                   "_library_mirror_resync", "_library_mirror_status"):
        monkeypatch.setattr(probe, method, forbidden)
    probe._handle_library_mirror({"op": op})
    assert responses[0][0] == 501
    assert responses[0][1]["error"]["code"] == CODE
    assert responses[0][1]["ok"] is False


@pytest.mark.parametrize("path,body", [
    ("/library/mirror", {"op": "resync"}),
    ("/library/mirror-intent", {"confirmed": True}),
    ("/settings", {"library_mirror_enabled": True}),
])
def test_authenticated_routes_reach_gate(darwin, path, body):
    from tests.test_library_mirror_wiring import post
    response = post(path, body)
    assert response.status == 501
    assert response.payload["code"] == CODE


def test_mcp_initialize_discloses_capability(darwin):
    response = server._mcp_initialize_result({})
    assert CODE in response["instructions"]


@pytest.mark.parametrize("name", ["get_library_activity", "publish_library_brief"])
def test_stdio_budgeted_handlers_disclose_capability(darwin, monkeypatch, name):
    import contextlib
    from mcp import types
    import library_analysis
    import library_resources
    import uoink_mcp
    # Drive the actual SDK dispatch, including handlers that bypass the registry.
    monkeypatch.setattr(library_analysis, "adapter_admission", contextlib.nullcontext)
    monkeypatch.setattr(library_analysis, "get_library_activity", lambda args: {"ok": True})
    monkeypatch.setattr(library_resources, "call_tool", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(server, "_get_index", lambda: SimpleNamespace(_conn=None))
    monkeypatch.setattr(library_resources.LibraryReader, "assert_within_deadline", lambda *args: None)
    handler = uoink_mcp.mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name=name, arguments={}))
    # These local handlers complete synchronously. Avoid asyncio's Windows
    # socketpair so this regression can run with all networking forbidden.
    coroutine = handler(request)
    try:
        coroutine.send(None)
    except StopIteration as done:
        result = done.value.root
    else:
        pytest.fail("Local handler unexpectedly suspended")
    finally:
        coroutine.close()
    text = result.content[0].text
    if library_resources.DOCUMENT_FENCE_OPEN in text:
        text = text.split(library_resources.DOCUMENT_FENCE_OPEN, 1)[1].split(library_resources.DOCUMENT_FENCE_CLOSE, 1)[0]
    envelope = json.loads(text)
    assert envelope["capabilities"]["library_mirror"]["code"] == CODE


def test_settings_and_intent_are_atomic_refusals(darwin, monkeypatch):
    probe = object.__new__(server.Handler)
    responses = []
    probe._send_json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(server, "_read_settings", forbidden)
    monkeypatch.setattr(server, "_write_settings", forbidden)
    monkeypatch.setattr(server, "_validate_mirror_destination_path", forbidden)
    probe._is_dashboard_origin = forbidden
    probe._handle_library_mirror_intent({"confirmed": True})
    probe._handle_settings_post({"library_mirror_enabled": True, "notifications_enabled": False})
    probe._handle_settings_post({"library_mirror_consent": None})
    assert len(responses) == 3
    assert all(status == 501 and payload["code"] == CODE for status, payload in responses)


def test_stale_consent_cannot_start_mirror(darwin, monkeypatch):
    monkeypatch.setattr(server, "_read_settings", forbidden)
    monkeypatch.setattr(library_mirror, "Mirror", forbidden)
    assert server._library_mirror(enabled=True, consent={"destination": "/old-vault"}) is None
    assert server._mirror_event("capture", video_id="item") is None


def test_settings_projects_unavailable_even_with_enabled_saved_state(darwin, monkeypatch):
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    settings = server._public_settings({"library_mirror_enabled": True})
    assert settings["library_mirror_enabled"] is False
    assert settings["library_mirror_capability"]["code"] == CODE


@pytest.mark.parametrize("name", ["get_library_activity", "publish_library_brief"])
def test_mcp_tools_disclose_deferred_mirror_without_changing_inventory(darwin, monkeypatch, name):
    spec = uoink_mcp_tools.TOOL_REGISTRY[name]
    monkeypatch.setitem(uoink_mcp_tools.TOOL_REGISTRY, name,
                        uoink_mcp_tools.ToolSpec(name, spec.description, spec.input_schema,
                                                lambda args: {"ok": True}))
    result = uoink_mcp_tools.call_tool(name, {})
    assert result["capabilities"]["library_mirror"]["available"] is False
    assert result["capabilities"]["library_mirror"]["code"] == CODE
    assert len(uoink_mcp_tools.stdio_tool_names()) == 91
    assert len(uoink_mcp_tools.stdio_tool_names("core")) == 35


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_keep_mcp_results(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    spec = uoink_mcp_tools.TOOL_REGISTRY["get_library_activity"]
    result = {"ok": True, "original": 1}
    monkeypatch.setitem(uoink_mcp_tools.TOOL_REGISTRY, spec.name,
                        uoink_mcp_tools.ToolSpec(spec.name, spec.description, spec.input_schema, lambda args: result))
    assert uoink_mcp_tools.call_tool(spec.name) == {"ok": True, "original": 1}


def test_cli_refusal_and_status(darwin, monkeypatch, capsys):
    monkeypatch.setattr(server, "main", forbidden)
    assert server.run_cli(["mirror", "resync"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == CODE
    monkeypatch.setattr(server, "_helper_health_status", lambda: {"ok": True})
    assert server.run_cli(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["capabilities"]["library_mirror"]["code"] == CODE


def test_media_bundle_gate_never_uses_path(darwin, monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    monkeypatch.setenv("PATH", "/opt/homebrew/bin")
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"
    with pytest.raises(RuntimeError, match="media_requires_ffmpeg"):
        server._run_extraction("https://invalid.example", 5, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
    monkeypatch.setattr(server, "_get_index", forbidden)
    result, status = server._queue_podcast_transcription(1)
    assert status == 501 and result["code"] == "media_requires_ffmpeg"
    for name in ("uoink_video", "uoink_playlist"):
        assert uoink_mcp_tools.call_tool(name, {"url": "https://invalid.example"})["code"] == "media_requires_ffmpeg"
    import podcasts
    import whisper_runner
    assert podcasts.download_episode_audio(None, 1, data_root=tmp_path)["code"] == "media_requires_ffmpeg"
    with pytest.raises(RuntimeError, match="media_requires_ffmpeg"):
        whisper_runner.transcribe_audio(tmp_path / "absent.wav", data_root=tmp_path)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_media_other_platforms_unchanged(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    assert _platform.media_capability()["available"] is True


def test_real_bundle_interpreter_resolution(monkeypatch, tmp_path):
    resources = tmp_path / "Uoink.app/Contents/Resources"
    python = resources.parent / "Frameworks/Python/bin/python3"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(server, "HERE", resources)
    assert server._bundled_interpreter(gui=False) == python


def test_dashboard_gate_disables_controls_and_displays_code():
    from pathlib import Path
    import subprocess
    page = (Path(__file__).resolve().parents[1] / "assets/dashboard/index.html").read_text(encoding="utf-8")
    function = "function renderLibraryMirrorFromSettings()" + page.split(
        "function renderLibraryMirrorFromSettings()", 1)[1].split("async function refreshLibraryMirrorStatus", 1)[0]
    script = """
const assert = require('node:assert/strict');
const controls = Array.from({length: 6}, () => ({disabled: false}));
const media = {textContent: ''};
const els = {libraryMirrorStatus: {textContent: ''}, libraryMirrorCounts: {textContent: 'old'}};
const state = {settings: {library_mirror_enabled: true,
  library_mirror_capability: {available: false, reason: 'Unavailable on macOS', code: 'library_mirror_unavailable_macos'},
  media_capability: {available: false, reason: 'Media features need FFmpeg', code: 'media_requires_ffmpeg'}}};
const document = {querySelectorAll: () => controls, getElementById: () => media};
function refreshLibraryMirrorStatus() { throw new Error('Unavailable mirror must not request status'); }
""" + function + """
renderLibraryMirrorFromSettings();
assert(controls.every(control => control.disabled));
assert(els.libraryMirrorStatus.textContent.includes('library_mirror_unavailable_macos'));
assert(media.textContent.includes('media_requires_ffmpeg'));
assert.equal(els.libraryMirrorCounts.textContent, '');
state.settings = {library_mirror_enabled: false, library_mirror_capability: {available: true}};
renderLibraryMirrorFromSettings();
assert(controls.every(control => !control.disabled));
assert(els.libraryMirrorStatus.textContent.startsWith('Off.'));
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, timeout=20)
