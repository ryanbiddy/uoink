"""Darwin refusals happen before settings, index, ledger or destination I/O."""
from __future__ import annotations

from tests.mcp_sdk import handler_for

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
    handler = handler_for(uoink_mcp.mcp, "tools/call")
    request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name=name, arguments={}))
    # These local handlers complete synchronously. Avoid asyncio's Windows
    # socketpair so this regression can run with all networking forbidden.
    coroutine = handler(request)
    try:
        coroutine.send(None)
    except StopIteration as done:
        result = done.value
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
    monkeypatch.setattr(_platform.sys, "executable",
        str(tmp_path / "Uoink.app/Contents/Resources/Python/bin/python3"), raising=False)
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    monkeypatch.setenv("PATH", "/opt/homebrew/bin")
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"
    with pytest.raises(RuntimeError, match="media_requires_ffmpeg"):
        server._run_extraction("https://www.youtube.com/watch?v=aaaaaaaaaaa", 5, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
    audio = tmp_path / "audio.wav"
    audio.touch()
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server.podcasts, "get_episode", lambda *args: {"audio_local_path": str(audio)})
    result, status = server._queue_podcast_transcription(1)
    assert status == 501 and result["code"] == "media_requires_ffmpeg"
    for name, url in (("uoink_video", "https://www.youtube.com/watch?v=aaaaaaaaaaa"),
                      ("uoink_playlist", "https://www.youtube.com/playlist?list=PLtest")):
        assert uoink_mcp_tools.call_tool(name, {"url": url})["code"] == "media_requires_ffmpeg"
    import podcasts
    import whisper_runner
    monkeypatch.setattr(podcasts, "get_episode", lambda *args: {
        "id": 1, "feed_id": 1, "audio_url": "https://example.test/audio.m4a"})
    monkeypatch.setattr(podcasts, "get_feed", lambda *args: {"id": 1, "title": "feed"})
    assert podcasts.download_episode_audio(None, 1, data_root=tmp_path,
        resolve_url=lambda url, **kwargs: url)["code"] == "media_requires_ffmpeg"
    with pytest.raises(RuntimeError, match="media_requires_ffmpeg"):
        whisper_runner.transcribe_audio(audio, data_root=tmp_path)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_media_other_platforms_unchanged(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    monkeypatch.setattr(_platform, "Path", forbidden)
    assert _platform.media_capability()["available"] is True
    _platform.require_media()


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_settings_and_transcription_fields_are_darwin_only(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    settings = server._public_settings({"library_mirror_enabled": True})
    assert settings["library_mirror_enabled"] is (platform != "darwin")
    assert ("library_mirror_capability" in settings) is (platform == "darwin")
    assert ("media_capability" in settings) is (platform == "darwin")
    monkeypatch.setattr(uoink_mcp_tools, "_b", lambda: server)
    result = uoink_mcp_tools.get_whisperx_status({})
    assert ("media_capability" in result) is (platform == "darwin")


@pytest.fixture
def missing_media(darwin, monkeypatch, tmp_path):
    monkeypatch.setattr(_platform.sys, "executable",
        str(tmp_path / "Uoink.app/Contents/Resources/Python/bin/python3"), raising=False)
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    monkeypatch.setenv("PATH", "/opt/homebrew/bin")
    monkeypatch.setattr(server, "_run_subprocess", forbidden)
    monkeypatch.setattr(server, "_fetch_metadata", forbidden)
    monkeypatch.setattr(server.source_subscriptions, "check_public_http_url", lambda url: url)
    return _platform.capability_refusal(_platform.media_capability())


@pytest.mark.parametrize("method,args", [
    ("_handle_extract", ({"url": "--exec=bad"},)),
    ("_handle_extract", ({"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "long_video_mode": "bad"},)),
    ("_handle_playlist_preview", ({"url": "--exec=bad"},)),
    ("_handle_playlist_start", ({"url": "https://www.youtube.com/playlist?list=PLtest", "interval": "bad"},)),
    ("_handle_session_add", ({"session_id": "../escape", "url": "--exec=bad"},)),
    ("_handle_session_add", ({"session_id": "test", "url": "--exec=bad"},)),
    ("_handle_extract_any", ({"url": "file:///private/media"},)),
    ("_handle_reliability_compute", ("aaaaaaaaaaa", {"threshold": "bad"})),
])
def test_input_errors_precede_media_gate(missing_media, monkeypatch, method, args):
    monkeypatch.setattr(_platform, "media_capability", forbidden)
    probe = object.__new__(server.Handler)
    replies = []
    probe._send_json = lambda status, payload: replies.append((status, payload))
    getattr(probe, method)(*args)
    assert replies[0][0] == 400


@pytest.mark.parametrize("name", ["uoink_video", "uoink_playlist"])
def test_mcp_input_errors_precede_media_gate(missing_media, monkeypatch, name):
    monkeypatch.setattr(_platform, "media_capability", forbidden)
    result = getattr(uoink_mcp_tools, name)({"url": "--exec=bad"})
    assert result["ok"] is False and "media_requires_ffmpeg" not in str(result)


@pytest.mark.parametrize("url", ["--exec=bad", "http://127.0.0.1/private"])
def test_podcast_security_checks_precede_media_gate(missing_media, monkeypatch, tmp_path, url):
    import podcasts
    monkeypatch.setattr(_platform, "media_capability", forbidden)
    monkeypatch.setattr(podcasts, "get_episode", lambda *a: {
        "id": 1, "feed_id": 1, "audio_url": url})
    monkeypatch.setattr(podcasts, "get_feed", lambda *a: {"id": 1, "title": "feed"})
    monkeypatch.setattr(podcasts, "_record_audio_result", lambda *a, **k: None)

    def refuse(url, **kwargs):
        raise ValueError("private address refused")

    result = podcasts.download_episode_audio(None, 1, data_root=tmp_path, resolve_url=refuse)
    assert result["ok"] is False and "media_requires_ffmpeg" not in str(result)


def test_transcription_and_preflight_validate_before_media(missing_media, monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "media_capability", forbidden)
    with pytest.raises(FileNotFoundError):
        server.whisper_runner.transcribe_audio(tmp_path / "absent.wav", data_root=tmp_path)
    backend = object.__new__(server._ServerCaptureBackend)
    assert backend.preflight({}, {"kind": "youtube_channel"}).code == "invalid_identity"
    assert backend.preflight({}, {"kind": "podcast_rss"}).code == "missing_episode_row"
    assert backend.preflight({"legacy_episode_id": 1}, {"kind": "podcast_rss"}).code == "no_audio_url"


def test_public_url_admission_precedes_bundle_media_self_test(missing_media, monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "media_capability", forbidden)

    def refuse(url):
        raise server.source_subscriptions.ServiceError("validation_error", "private address refused")

    monkeypatch.setattr(server.source_subscriptions, "check_public_http_url", refuse)
    probe = object.__new__(server.Handler)
    replies = []
    probe._send_json = lambda status, payload: replies.append((status, payload))
    probe._handle_extract_any({"url": "http://127.0.0.1/private"})
    assert replies[0][0] == 400
    with pytest.raises(server.source_subscriptions.ServiceError, match="private address"):
        server._download_reliability_audio("http://127.0.0.1/private", tmp_path)
    backend = object.__new__(server._ServerCaptureBackend)
    item = {"legacy_episode_id": 1, "metadata_json": json.dumps({"audio_url": "http://127.0.0.1/private"})}
    assert backend.preflight(item, {"kind": "podcast_rss"}).code == "validation_error"


def test_missing_local_inputs_precede_media_gate(missing_media, monkeypatch):
    monkeypatch.setattr(_platform, "media_capability", forbidden)
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server.podcasts, "get_episode", lambda *a: None)
    assert server._queue_podcast_transcription(1)[1] == 404
    monkeypatch.setattr(server, "_folder_for_video_id", lambda video_id: (None, None))
    assert server._compute_transcript_reliability("aaaaaaaaaaa")["error"] == "uoink not found"
    monkeypatch.setattr(server, "_read_session", lambda session_id: None)
    probe = object.__new__(server.Handler)
    replies = []
    probe._send_json = lambda status, payload: replies.append((status, payload))
    probe._handle_session_add({"session_id": "test", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"})
    assert replies[0][0] == 404


@pytest.mark.parametrize("method,args", [
    ("_handle_extract", ({"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},)),
    ("_handle_playlist_preview", ({"url": "https://www.youtube.com/playlist?list=PLtest"},)),
    ("_handle_playlist_start", ({"url": "https://www.youtube.com/playlist?list=PLtest"},)),
    ("_handle_session_add", ({"session_id": "test", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},)),
    ("_handle_extract_any", ({"url": "https://example.test/video"},)),
    ("_handle_reliability_compute", ("aaaaaaaaaaa", {})),
])
def test_media_routes_refuse_before_metadata_or_job_start(missing_media, monkeypatch, method, args):
    monkeypatch.setattr(server, "_create_playlist_job", forbidden)
    monkeypatch.setattr(server, "_fetch_playlist_preview", forbidden)
    monkeypatch.setattr(server, "_read_session", lambda session_id: {"status": "open"})
    monkeypatch.setattr(server, "_compute_transcript_reliability", lambda *a, **k: missing_media)
    probe = object.__new__(server.Handler)
    replies = []
    probe._send_json = lambda status, payload: replies.append((status, payload))
    getattr(probe, method)(*args)
    assert replies == [(501, missing_media)]


def test_media_helpers_fail_before_subprocess_or_capture_io(missing_media, monkeypatch, tmp_path):
    assert server._fetch_playlist_preview("https://www.youtube.com/playlist?list=PLtest") == (
        None, "media_requires_ffmpeg", 501)
    monkeypatch.setattr(server, "_folder_for_video_id", lambda video_id: (tmp_path, {}))
    monkeypatch.setattr(server, "_read_sidecar_for_folder", lambda folder: (None, {"video_id": "aaaaaaaaaaa"}))
    assert server._compute_transcript_reliability("aaaaaaaaaaa") == missing_media
    with pytest.raises(_platform.MediaUnavailableError) as exc:
        server._download_reliability_audio("https://example.test/video", tmp_path)
    assert exc.value.code == "media_requires_ffmpeg"
    assert server.friendly_error(exc.value).startswith("media_requires_ffmpeg:")
    monkeypatch.setattr(server, "_make_job_id", forbidden)
    with pytest.raises(_platform.MediaUnavailableError):
        server._create_playlist_job({}, 30)


def test_playlist_worker_records_gate_before_folder_or_metadata(missing_media, monkeypatch, tmp_path):
    updates = []
    monkeypatch.setattr(server, "_get_public_job", lambda job_id: {"id": job_id})
    monkeypatch.setattr(server, "_job_cancel_event", forbidden)
    monkeypatch.setattr(server, "_update_job", lambda job_id, **values: updates.append(values))
    server._playlist_worker("blocked-playlist")
    assert len(updates) == 1
    assert updates[0]["state"] == "failed"
    assert updates[0]["error"] == "media_requires_ffmpeg"
    assert updates[0]["result"] == missing_media
    assert not list(tmp_path.iterdir())


def test_standing_preflight_reports_media_gate(missing_media, monkeypatch):
    backend = object.__new__(server._ServerCaptureBackend)
    item = {"legacy_episode_id": 1, "entry_id": "aaaaaaaaaaa",
            "metadata_json": json.dumps({"audio_url": "https://example.test/audio.m4a"})}
    for kind in ("youtube_channel", "podcast_rss"):
        outcome = backend.preflight(item, {"kind": kind})
        assert outcome.status == "preflight_failed"
        assert outcome.code == "media_requires_ffmpeg"
        assert outcome.terminal is True
    monkeypatch.setattr(backend, "holds_execution", lambda start: True)
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server.source_subscriptions, "process_incarnation",
                        lambda root: SimpleNamespace(identity="test-incarnation"))
    monkeypatch.setattr(server.podcasts, "download_episode_audio", lambda *a, **k: missing_media)
    outcome = backend._run_podcast({"start_id": "test-start"}, item, {})
    assert outcome.code == "media_requires_ffmpeg" and outcome.terminal
    outcome = backend._run_youtube({}, item, {})
    assert outcome.code == "media_requires_ffmpeg" and outcome.terminal


def test_standing_worker_settles_with_media_code(missing_media, monkeypatch):
    from unittest.mock import Mock
    # Defensive worker check: availability can change after thread admission.
    missing = _platform.media_capability()
    monkeypatch.setattr(_platform, "media_capability", Mock(side_effect=[
        {"available": True, "code": None, "reason": None}, missing]))
    service = SimpleNamespace(
        claim_execution=Mock(return_value={"outcome": "active"}),
        fail_capture=Mock(return_value={"outcome": "failed"}),
        complete_capture=Mock())
    backend = SimpleNamespace(kind="test", _pacing=SimpleNamespace(),
                              _ensure_ownership=Mock(), holds_execution=lambda start: True,
                              release=Mock())
    monkeypatch.setattr(server, "_source_service", lambda: service)
    monkeypatch.setattr(server, "threading", SimpleNamespace(
        Thread=lambda *, target, **kwargs: SimpleNamespace(start=target)))
    monkeypatch.setattr(server.source_subscriptions, "process_incarnation", forbidden)
    monkeypatch.setattr(server.source_subscriptions, "settlement_releases_dispatcher_locks", lambda result: True)
    start = {"start_id": "test-start", "owner_token": "test-owner"}
    outcome = server._ServerCaptureBackend._run_youtube(
        backend, start, {"entry_id": "aaaaaaaaaaa"}, {})
    assert outcome.status == "in_flight"
    args, kwargs = service.fail_capture.call_args
    assert args == ("test-start", "test-owner", "media_requires_ffmpeg")
    assert kwargs["terminal"] is True
    assert kwargs["proof"].start_id == "test-start"
    service.fail_capture.assert_called_once()
    service.complete_capture.assert_not_called()
    backend.release.assert_called_once_with(start)
    assert "test-start" not in server._source_capture_threads


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_status_cli_retains_main_fallthrough(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    calls = []
    monkeypatch.setattr(server, "main", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(server, "_helper_health_status", forbidden)
    assert server.run_cli(["status"]) == 0
    assert calls == [{"show_dashboard": False, "quiet": False}]


def test_real_bundle_interpreter_resolution(monkeypatch, tmp_path):
    resources = tmp_path / "Uoink.app/Contents/Resources"
    python = resources.parent / "Resources/Python/bin/python3"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="darwin", executable=str(python)))
    monkeypatch.setattr(_platform, "sys", server.sys)
    monkeypatch.setattr(server, "HERE", resources)
    assert server._bundled_interpreter(gui=False) == python
    monkeypatch.setattr(server.sys, "executable", str(tmp_path / "external-python"))
    assert server._bundled_interpreter(gui=False) is None


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
