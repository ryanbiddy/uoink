"""Offline contracts for dashboard consent, media inputs and desktop boundaries."""
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

import index
import page_extractor as pages
import server
import uoink_mcp_tools as tools


@pytest.fixture
def sites(tmp_path, monkeypatch):
    db = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: db)
    monkeypatch.setattr(tools, "_backend", server)
    try:
        yield db
    finally:
        db.close()


def dashboard_add(pattern):
    probe = object.__new__(server.Handler)
    probe._send_json = lambda status, body: (status, body)
    return probe._handle_page_allowlist_modify({"action": "add", "url_pattern": pattern})


@pytest.mark.parametrize("pattern", ["com", "*.test", "co.uk", "*.GITHUB.io", "co.uk.", "*.*.org"])
def test_dashboard_refuses_overbroad_or_invalid_rules(sites, pattern):
    before = pages.list_allowed(sites)
    assert dashboard_add(pattern)[0] == 400
    assert pages.list_allowed(sites) == before


def test_existing_suffix_rule_grants_no_access_and_can_be_removed(sites):
    with sites.write_transaction() as conn:
        conn.execute("INSERT INTO allowed_sites (url_pattern, added_at) VALUES (?, ?)",
                     ("*.github.io", "2026-01-01"))
    assert not pages.host_is_allowed(sites, "https://example.github.io/guide")
    saved = {row["url_pattern"]: row for row in pages.list_allowed(sites)}
    assert saved["*.github.io"]["active"] == 0
    assert "*.github.io" not in {row["url_pattern"] for row in pages.list_allowed(sites, active_only=True)}
    assert pages.remove_allowed(sites, "*.github.io")


@pytest.mark.parametrize("pattern", ["*.docs.example.test", "co.uk"])
def test_mcp_add_requires_user_in_dashboard(sites, pattern):
    before = pages.list_allowed(sites)
    result = tools.call_tool("add_allowed_site", {"url_pattern": pattern, "consent_given": True})
    assert result["ok"] is False and result["code"] == "consent_required"
    assert pages.list_allowed(sites) == before
    if pattern.startswith("*."):
        assert "dashboard" in result["error"].lower()
        assert dashboard_add(pattern)[0] == 200
        assert pages.host_is_allowed(sites, "https://api.docs.example.test/guide")
        assert not pages.host_is_allowed(sites, "https://api.other.test/guide")


def test_channel_context_checks_the_final_target_before_starting_media(monkeypatch):
    admission = Mock(side_effect=ValueError("unavailable"))
    run = Mock(return_value=Mock(stdout="{}"))
    monkeypatch.setattr(server.source_subscriptions, "check_public_http_url", admission)
    monkeypatch.setattr(server, "_run_subprocess", run)
    server._fetch_channel_context("https://channel.example.test")
    admission.assert_called_once_with("https://channel.example.test/videos")
    run.assert_not_called()


@pytest.mark.parametrize("data", [b"plain text", b"\xff\xd8\xff" + b"0" * 20])
def test_thumbnail_checks_size_and_type_before_conversion(tmp_path, monkeypatch, data):
    monkeypatch.setattr(server.images, "MAX_IMAGE_BYTES", 16)
    run = Mock()
    monkeypatch.setattr(server, "_run_subprocess", run)
    result = server._download_thumbnail({"thumbnail": "https://media.example.test/cover"},
                                        tmp_path, http_open=lambda *a, **kw: io.BytesIO(data))
    run.assert_not_called()
    assert result is None and not list(tmp_path.iterdir())


@pytest.mark.parametrize(("header", "demuxer"), [
    (b"\xff\xd8\xff", "jpeg_pipe"), (b"\x89PNG\r\n\x1a\n", "png_pipe"), (b"RIFF0000WEBP", "webp_pipe"),
])
def test_thumbnail_limits_the_read_and_selects_the_image_reader(tmp_path, monkeypatch, header, demuxer):
    data = header.ljust(16, b"0")
    response = io.BytesIO(data)
    read = Mock(wraps=response.read)
    monkeypatch.setattr(response, "read", read)
    run = Mock(side_effect=lambda argv, **kwargs: Path(argv[-1]).write_bytes(b"converted"))
    monkeypatch.setattr(server, "_run_subprocess", run)
    path = server._download_thumbnail({"thumbnail": "https://media.example.test/cover"},
                                      tmp_path, http_open=lambda *a, **kw: response)
    read.assert_called_once_with(server.images.MAX_IMAGE_BYTES + 1)
    argv = run.call_args.args[0]
    assert argv[argv.index("-f") + 1] == demuxer
    assert argv[argv.index("-protocol_whitelist") + 1] == "file"
    assert argv[argv.index("-frames:v") + 1] == "1" and run.call_args.kwargs["timeout"] == 30
    assert list(tmp_path.iterdir()) == [path] and path.read_bytes() == b"converted"


def test_failed_preview_conversion_preserves_the_previous_file(tmp_path, monkeypatch):
    preview = tmp_path / "thumbnail.jpg"
    preview.write_bytes(b"previous")

    def timeout(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"partial")
        raise server.subprocess.TimeoutExpired(argv[0], 30)

    monkeypatch.setattr(server, "_run_subprocess", timeout)
    response = io.BytesIO(b"\xff\xd8\xff" + b"0" * 16)
    result = server._download_thumbnail({"thumbnail": "https://media.example.test/cover"},
                                        tmp_path, http_open=lambda *a, **kw: response)
    assert result is None
    assert preview.read_bytes() == b"previous" and list(tmp_path.iterdir()) == [preview]


def test_linux_toast_passes_text_as_operands(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(server._platform.subprocess, "Popen", launch)
    server._platform._linux_toast("Title", "Body")
    assert launch.call_args.args[0] == ["notify-send", "--", "Title", "Body"]


def test_splash_clipboard_fallback_passes_text_outside_the_command(monkeypatch):
    import uoink_splash as splash
    runner = Mock(side_effect=[OSError("clip unavailable"), None])
    monkeypatch.setattr(splash.sys, "platform", "win32")
    monkeypatch.setattr(splash.subprocess, "run", runner)
    assert splash._copy_to_clipboard("Sample folder")
    args, kwargs = runner.call_args
    assert "Sample folder" not in args[0]
    assert kwargs["env"]["UOINK_CLIPBOARD_TEXT"] == "Sample folder"


def test_mcp_generic_capture_only_forwards_public_inputs(monkeypatch):
    monkeypatch.setattr(tools, "_backend", server)
    handler = Mock()
    monkeypatch.setattr(server.Handler, "_handle_extract_any", handler)
    public = {"url": "https://media.example.test/item", "interval": 18, "long_video_mode": "lite"}
    tools.uoink_url({**public, "extra_field": "ignored"})
    assert handler.call_args.args[1] == public


def test_mcp_cannot_confirm_a_model_download(monkeypatch):
    monkeypatch.setattr(tools, "_backend", server)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    queue = Mock(return_value=({"ok": False, "consent_required": True, "error": "Consent required."}, 412))
    monkeypatch.setattr(server, "_queue_podcast_transcription", queue)
    result = tools.transcribe_podcast_episode({"episode_id": 1, "consent_given": True})
    assert queue.call_args.kwargs["consent_given"] is False
    assert result["consent_required"]


def test_mcp_url_anchor_needs_an_allowed_page(sites, monkeypatch):
    extract = Mock(return_value={"ok": True, "markdown": "Sample"})
    monkeypatch.setattr(pages, "extract_page", extract)
    args = {"name": "Sample", "source_type": "url", "source_value": "https://notes.example.test/"}
    result = tools.add_style_anchor(args)
    extract.assert_not_called()
    assert result["code"] == "consent_required"
    assert dashboard_add("notes.example.test")[0] == 200
    assert tools.add_style_anchor(args)["anchor"]["raw_text"] == "Sample"
    assert extract.call_args.kwargs["enforce_allowlist"] is True
    dashboard_fetch = object.__new__(server.Handler)._writing_url_fetcher()
    assert dashboard_fetch("https://other.example.test/") == "Sample"
    assert extract.call_args.kwargs["enforce_allowlist"] is False


@pytest.mark.parametrize("name", ["uoink_page", "uoink_url", "uoink_video", "uoink_x", "uoink_reddit_thread"])
def test_capture_results_carry_the_untrusted_content_notice(name):
    original = {"ok": True, "title": "Fixture"}
    assert tools._label_untrusted(name, original) == {
        "untrusted_content": tools.UNTRUSTED_CONTENT_NOTICE, **original}


def test_file_response_declares_nosniff(tmp_path):
    path = tmp_path / "asset.txt"
    path.write_bytes(b"example")
    probe = Mock(wfile=io.BytesIO())
    server.Handler._send_file(probe, path, "text/plain")
    probe.send_header.assert_any_call("X-Content-Type-Options", "nosniff")
