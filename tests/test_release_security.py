"""Release security contracts. External viewers, workers and peers are stubbed."""
from unittest.mock import Mock

import pytest

import server


@pytest.mark.parametrize(("name", "data"), [("saved.txt", b"notes"), ("saved.md", b"\xff"), ("saved.md", b"header\0field")])
def test_open_markdown_refuses_non_markdown_or_invalid_text(tmp_path, monkeypatch, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    index = Mock()
    index.get_yoink.return_value = {"corpus_path": str(path)}
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: index)
    viewer = Mock()
    monkeypatch.setattr(server._platform, "open_in_os", viewer)
    handler = object.__new__(server.Handler)
    handler._send_json = lambda code, payload: payload
    result = handler._handle_yoink_open_markdown("/yoinks/example/open-markdown")
    viewer.assert_not_called()
    assert not result["ok"] and result["error"]


def test_reliability_admits_url_and_terminates_options(tmp_path, monkeypatch):
    url = "https://example.com/recording"
    admit = Mock(return_value=url)
    run = Mock()
    monkeypatch.setattr(server.source_subscriptions, "check_public_http_url", admit)
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    monkeypatch.setattr(server, "_run_subprocess", run)
    (tmp_path / "audio.test").touch()
    server._download_reliability_audio(url, tmp_path)
    admit.assert_called_once_with(url)
    assert run.call_args.args[0][-2:] == ["--", url]


def test_playlist_url_follows_end_of_options():
    import mobile_playlists
    url = "https://example.com/playlist"
    run = Mock(return_value=Mock(returncode=0, stdout=""))
    mobile_playlists._fetch_playlist_video_ids(url, ytdlp_cmd=["yt-dlp"], run_subprocess=run)
    assert run.call_args.args[0][-2:] == ["--", url]


def test_public_diagnose_does_no_probes(monkeypatch):
    build = Mock(return_value={"ok": True})
    monkeypatch.setattr(server, "_build_diagnose_payload", build)
    monkeypatch.setattr(server, "_diagnose_cache", None)
    assert not server._public_diagnose_payload()["ok"]
    build.assert_not_called()


def test_atomic_writer_exclusively_creates_temp(tmp_path, monkeypatch):
    import os
    from uoink_core import storage
    observed = Mock(wraps=os.open)
    monkeypatch.setattr(os, "open", observed)
    storage._atomic_write_text(tmp_path / "save.md", "text")
    assert any(call.args[1] & os.O_CREAT and call.args[1] & os.O_EXCL
               for call in observed.call_args_list)


def test_delete_empty_corpus_refuses_before_changing_index(monkeypatch):
    index = Mock()
    index.get_yoink.return_value = {"video_id": "sample", "corpus_path": ""}
    index.soft_delete_yoink.side_effect = AssertionError("changed index before checking ownership")
    monkeypatch.setattr(server, "_get_index", lambda: index)
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, body: status
    assert handler._handle_memory_delete({"video_id": "sample"}) == 409
    index.soft_delete_yoink.assert_not_called()


@pytest.mark.parametrize("kind", ["relative", "outside", "wrong_folder", "missing_markdown"])
def test_delete_requires_an_owned_markdown_file(kind, tmp_path, monkeypatch):
    library = tmp_path / "Library"
    folder = library / "sample"
    folder.mkdir(parents=True)
    path = {"relative": "sample/note.md", "outside": str(tmp_path / "note.md"),
            "wrong_folder": str(folder / "note.md"), "missing_markdown": str(folder / "missing.md")}[kind]
    (folder / "note.md").write_text("Sample")
    monkeypatch.chdir(library)
    index = Mock()
    index.get_yoink.return_value = {"slug": "other" if kind == "wrong_folder" else "sample",
                                    "corpus_path": path}
    index.soft_delete_yoink.side_effect = AssertionError("changed index before checking ownership")
    monkeypatch.setattr(server, "DESKTOP_ROOT", library)
    monkeypatch.setattr(server, "_get_index", lambda: index)
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, body: status
    assert handler._handle_memory_delete({"video_id": "sample"}) == 409
    index.soft_delete_yoink.assert_not_called()


@pytest.mark.parametrize("path", [r"\\server\share\saves.csv", "//server/share/saves.csv"])
def test_mcp_saves_rejects_network_names_before_filesystem_access(path, tmp_path, monkeypatch):
    from pathlib import Path
    import list_imports
    monkeypatch.setattr(Path, "stat", Mock(side_effect=AssertionError("accessed network path")))
    with pytest.raises(list_imports.ImportListError, match="on this computer"):
        list_imports.stage_saves_file(tmp_path, path, source="watch_later")


def test_saves_import_refuses_private_profile(tmp_path):
    import list_imports
    root = tmp_path / "profile"
    root.mkdir()
    sample = root / "token.txt"
    sample.write_text("https://youtu.be/save0000001")
    with pytest.raises(list_imports.ImportListError, match="private"):
        list_imports.stage_saves_file(root, sample, source="watch_later")


def test_page_capture_supplies_redirect_allowlist(monkeypatch):
    import page_extractor as pages
    first = "https://example.com/story"
    monkeypatch.setattr(pages, "host_is_allowed", lambda idx, url: url == first)
    transport = Mock(side_effect=OSError("offline fixture"))
    pages.extract_page(None, first, http_open=transport)
    allowed = transport.call_args.kwargs["redirect_allowed"]
    assert allowed(first)
    assert not allowed("https://another.example/story")


@pytest.mark.parametrize("address", [
    "https://member:sample@example.com/item?signature=fixture-credential",
    "/item?view=brief&X-Amz-Credential=fixture-credential",
    "//member:sample@example.com/item?sig=fixture-credential",
    "https://example.com/item?apiKey=fixture-credential",
    "https://example.com/item?expiresAt=fixture-credential",
])
def test_signed_url_is_redacted_by_log_handler(address):
    import logging
    marker = "fixture-credential"
    record = logging.LogRecord("uoink", logging.WARNING, "", 1, "item %s",
                               (address,), None)
    output = server._server_log_handler.format(record)
    assert marker not in output and "member:sample@" not in output


def test_existing_token_repairs_posix_permissions(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    path = tmp_path / "token.txt"
    path.write_text("fixture")
    monkeypatch.setattr(server, "TOKEN_PATH", path)
    repair = Mock()
    posix = SimpleNamespace(name="posix", getuid=lambda: 123,
                            fstat=lambda fd: SimpleNamespace(st_mode=0o100644, st_uid=123, st_nlink=1),
                            fchmod=repair)
    monkeypatch.setattr(server, "os", posix)
    assert server._read_token_file() == "fixture"
    assert repair.call_count == 1 and repair.call_args.args[1] == 0o600


def test_new_token_created_with_owner_only_mode(tmp_path, monkeypatch):
    import os
    path = tmp_path / "token.txt"
    monkeypatch.setattr(server, "TOKEN_PATH", path)
    calls = Mock(wraps=os.open)
    monkeypatch.setattr(os, "open", calls)
    server._persist_token("fixture-value")
    assert any(c.args[1] & os.O_EXCL and c.args[2] == 0o600 for c in calls.call_args_list)


def test_article_suffix_has_bounded_work(monkeypatch):
    from time import perf_counter
    from uoink_core import x_evidence
    import x_article_extractor
    text = ("ordinary article sentence. " * 42000) + "... https://t.co/example"
    original = x_evidence.re.search
    def bounded_search(pattern, value, *args, **kwargs):
        if r"t\.co" in str(pattern):
            assert len(value) < 256, "suffix regex scanned the full article"
        return original(pattern, value, *args, **kwargs)
    monkeypatch.setattr(x_evidence.re, "search", bounded_search)
    start = perf_counter()
    assert x_evidence.shape({"text": text})["text_completeness"] == "truncated"
    article = x_article_extractor.build_extract_result({"url": "https://x.com/i/article/12345", "markdown": text})
    assert article["ok"]
    assert perf_counter() - start < 0.8


def test_legacy_html_scan_has_bounded_work():
    from time import perf_counter
    import page_extractor
    text = "ordinary article sentence. " * 42000
    start = perf_counter()
    assert page_extractor._html_to_markdown("<p>" + text + "</p><script>unfinished") == text.strip()
    assert perf_counter() - start < 0.8


def test_writer_status_uses_redirect_refusing_transport(monkeypatch):
    import writer_peer
    import urllib.error
    from urllib import request
    open_url = Mock(side_effect=urllib.error.HTTPError("http://localhost", 403, "", {}, None))
    maker = Mock(return_value=Mock(open=open_url))
    monkeypatch.setattr(request, "urlopen", open_url)
    monkeypatch.setattr(request, "build_opener", maker)
    with pytest.raises(writer_peer.WriterPeerError):
        writer_peer._get_writer_status("http://localhost", "fixture", timeout=1)
    handlers = maker.call_args.args if maker.called else ()
    assert any(isinstance(handler, request.HTTPRedirectHandler) and
               handler.redirect_request(None, None, 302, "", {}, "") is None for handler in handlers)
