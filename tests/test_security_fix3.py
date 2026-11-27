"""Round-three release regressions, using only temporary library data."""
import io
import logging
import os
from pathlib import Path
import subprocess
import threading
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

import list_imports
import server
from tests.test_unique_capture_folders import URL_A, capture
from uoink_core import storage


def link_directory(root, target):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(root))
    else:
        root.symlink_to(target, target_is_directory=True)


@pytest.fixture
def linked_library(tmp_path, monkeypatch):
    target = tmp_path / "volume"
    target.mkdir()
    root = tmp_path / "Uoink"
    link_directory(root, target)
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    monkeypatch.setattr(server, "SESSIONS_ROOT", root / "_sessions")
    return root, target


def handler():
    result = object.__new__(server.Handler)
    result._send_json = Mock(side_effect=lambda status, body: (status, body))
    return result


@pytest.mark.parametrize("action", ["startup", "save", "read", "export", "open", "delete", "clipboard"])
def test_linked_library_operations(action, linked_library, tmp_path, monkeypatch):
    root, target = linked_library
    row = {"video_id": "sample", "slug": "sample", "corpus_path": str(root / "Topic/sample/sample.md")}
    path = Path(row["corpus_path"])
    path.parent.mkdir(parents=True)
    path.write_text("linked library fixture", encoding="utf-8")
    idx = Mock()
    idx.get_yoink.return_value = row
    idx.soft_delete_yoink.return_value = dict(row, deleted_at="2026-01-01T12:00:00")
    idx.export_payload.return_value = {"tables": {}}
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    viewer = Mock()
    monkeypatch.setattr(server._platform, "open_in_os", viewer)
    h = handler()
    if action == "startup":
        monkeypatch.setattr(server._install_isolation, "current_binding", lambda: None)
        monkeypatch.setattr(server, "_LOCALAPPDATA_OUTPUT", tmp_path / "fallback")
        server._apply_output_root_fallback()
        assert server.DESKTOP_ROOT == root and not (tmp_path / "fallback").exists()
    elif action == "save":
        server._write_reliability_to_sidecar(path.parent, {"status": "pending"})
        assert (target / "Topic/sample/sample.json").is_file()
    elif action == "read":
        code, response = h._handle_yoink_markdown("/yoinks/sample/markdown")
        assert code == 200 and response["markdown"] == "linked library fixture"
    elif action == "export":
        result = server.export_corpus_data()
        assert Path(result["path"]).resolve().parent == target / "_exports"
    elif action == "open":
        assert h._handle_yoink_open_markdown("/yoinks/sample/open-markdown")[0] == 200
        viewer.assert_called_once_with(path)
    elif action == "clipboard":
        assert "linked library fixture" in server._generate_paste_corpus(path.parent)
    else:
        monkeypatch.setattr(server, "_source_service", Mock())
        monkeypatch.setattr(server, "_mirror_event", Mock())
        h._handle_memory_delete({"video_id": "sample"})
        assert h._send_json.call_args.args[0] == 200 and not path.exists()
        idx.get_yoink.return_value = idx.soft_delete_yoink.return_value
        h._handle_memory_restore({"video_id": "sample"})
        assert h._send_json.call_args.args[0] == 200 and path.is_file()


def test_local_saves_import_behind_linked_parent(linked_library, tmp_path):
    root, target = linked_library
    (target / "exports").mkdir()
    path = root / "exports/saves.csv"
    path.write_text("Video ID,Title\nsave0000001,Sample\n", encoding="utf-8")
    assert list_imports.stage_saves_file(tmp_path / "stage", path)["source"] == "watch_later"


def test_physical_corpus_path_from_an_older_index(linked_library):
    root, target = linked_library
    (target / "old.md").write_text("older save", encoding="utf-8")
    assert storage.checked_path(root, target / "old.md") == root / "old.md"
    assert storage.read_export_markdown(target / "old.md", root=root) == "older save"


def test_video_capture_writes_markdown_to_linked_root(linked_library, capture):
    root, target = linked_library
    capture.scope.update(DESKTOP_ROOT=root, _atomic_write_text=server._atomic_write_text)
    result = capture.run(URL_A, parent=root / "Topic")
    assert result["ok"]
    folder = Path(result["folder"])
    assert (target / folder.relative_to(root) / (folder.name + ".md")).is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows mapped drive")
def test_saves_refuses_remote_parent_before_open(tmp_path, monkeypatch):
    import ctypes
    from pathlib import PureWindowsPath
    remote = PureWindowsPath("Z:/exports")
    monkeypatch.setattr(Path, "resolve", lambda self: remote)
    monkeypatch.setattr(ctypes.windll.kernel32, "GetDriveTypeW", lambda anchor: 4 if anchor == remote.anchor else 3)
    monkeypatch.setattr(storage, "open_regular", Mock(side_effect=AssertionError("file opened")))
    with pytest.raises(list_imports.ImportListError, match="on this computer"):
        list_imports.stage_saves_file(tmp_path, tmp_path / "saves.csv")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction")
def test_saves_checks_junction_target_before_resolving_it(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace
    parent = tmp_path / "exports"
    lstat = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda self: SimpleNamespace(st_mode=stat.S_IFLNK)
                        if self == parent else lstat(self))
    monkeypatch.setattr(Path, "readlink", lambda self: Path("//share.example.test/data"))
    monkeypatch.setattr(Path, "resolve", Mock(side_effect=AssertionError("dereferenced before local check")))
    with pytest.raises(list_imports.ImportListError, match="on this computer"):
        list_imports.stage_saves_file(tmp_path, parent / "saves.csv")


@pytest.mark.parametrize("action", ["index", "reliability", "poster"])
@pytest.mark.parametrize("redirected", [False, True], ids=["outside-root", "linked-child"])
def test_refused_corpus_is_never_consumed(action, redirected, linked_library, tmp_path, monkeypatch):
    root, _ = linked_library
    outside = tmp_path / "other"
    outside.mkdir()
    parent = outside
    if redirected:
        parent = root / "topic"
        link_directory(parent, outside)
    path = parent / "fixture.md"
    path.write_text("fixture")
    idx = Mock()
    idx.get_yoink.return_value = {"corpus_path": str(path)}
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    if action == "index":
        idx.upsert_yoink.side_effect = AssertionError("unchecked corpus supplied to index")
        with pytest.raises(OSError):
            server._index_yoink(path.parent, {"video_id": "sample"}, path, path.with_suffix(".json"))
        idx.upsert_yoink.assert_not_called()
    elif action == "reliability":
        render = Mock(return_value="updated")
        monkeypatch.setattr(server, "_render_reliability_summary", render)
        server._replace_reliability_section(path, {})
        render.assert_not_called()
    else:
        monkeypatch.setattr(server, "_x_video_poster_url", lambda _: "https://example.test/image")
        download = Mock()
        monkeypatch.setattr(server, "_download_thumbnail", download)
        assert server._save_x_video_poster("sample", {}) is None
        download.assert_not_called()


def test_log_keeps_unsigned_query_parameters():
    url = ("https://member:fixture@example.test/item?author=ada&token=secret"
           "&experiment=a%2Fb;X-Amz-Date=fixture&article-token=word&tokenizer=on&api%4Bey=hidden&id=12#part")
    record = logging.LogRecord("uoink", logging.WARNING, "", 1, "%s", (url,), None)
    assert server._LogFormatter("%(message)s").format(record) == (
        "https://example.test/item?author=ada&token=[redacted]&experiment=a%2Fb;"
        "X-Amz-Date=[redacted]&article-token=word&tokenizer=on&api%4Bey=[redacted]&id=12#part")


@pytest.mark.parametrize("url,expected", [
    ("/article?x-uoink-token=private&author=ada#access_token=private&view=full",
     "/article?x-uoink-token=[redacted]&author=ada#access_token=[redacted]&view=full"),
    ("https://relay.example.test/phone#t=private", "https://relay.example.test/phone#t=[redacted]"),
    ("https://example.test/video#t=12", "https://example.test/video#t=12"),
])
def test_log_preserves_public_url_fields_in_fragments(url, expected):
    record = logging.LogRecord("uoink", logging.WARNING, "", 1, "%s", (url,), None)
    assert server._LogFormatter("%(message)s").format(record) == expected


def test_thumbnail_failure_keeps_scrubbed_stderr(tmp_path, monkeypatch, caplog):
    failure = subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"Invalid data found. token=fixture-secret")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_run_subprocess", Mock(side_effect=failure))
    data = io.BytesIO(b"\xff\xd8\xff" + b"0" * 16)
    assert server._download_thumbnail({"thumbnail": "https://example.test/image"}, tmp_path,
                                      http_open=lambda *args, **kwargs: data) is None
    messages = [r.getMessage() for r in caplog.records if "ffmpeg thumbnail" in r.getMessage()]
    assert len(messages) == 1 and "Invalid data found" in messages[0]
    assert "fixture-secret" not in messages[0]


def test_startup_populates_token_free_diagnostics(monkeypatch):
    started, finish = threading.Event(), threading.Event()
    def build(*, public):
        assert public
        started.set()
        assert finish.wait(5)
        return {"ok": False, "checks": [{"name": "ffmpeg_available", "status": "error"}]}
    probe = Mock(side_effect=build)
    monkeypatch.setattr(server, "_build_diagnose_payload", probe)
    monkeypatch.setattr(server, "_diagnose_lock", threading.Lock())
    monkeypatch.setattr(server, "_diagnose_cache", None)
    with server._YoinkHTTPServer((server.HOST, 0), server.Handler) as helper:
        worker = threading.Thread(target=helper.serve_forever, daemon=True)
        worker.start()
        try:
            from urllib.request import urlopen
            import json
            def diagnosis():
                with urlopen(f"http://{server.HOST}:{helper.server_port}/diagnose", timeout=2) as res:
                    return json.load(res)
            assert started.wait(2)
            pending = diagnosis()
            assert pending["refreshing"] and not pending["ok"]
            finish.set()
            assert server._diagnose_lock.acquire(timeout=3)
            server._diagnose_lock.release()
            assert diagnosis()["checks"] == [{"name": "ffmpeg_available", "status": "error"}]
            assert not diagnosis()["refreshing"]
            probe.assert_called_once_with(public=True)
        finally:
            finish.set()
            helper.shutdown()
            worker.join(3)


def test_failed_diagnose_thread_start_releases_lock(monkeypatch):
    lock = threading.Lock()
    monkeypatch.setattr(server, "_diagnose_lock", lock)
    monkeypatch.setattr(threading.Thread, "start", Mock(side_effect=OSError("fixture")))
    try:
        server._public_diagnose_payload(refresh=True)
    except OSError:
        pass
    assert not lock.locked()


def test_public_startup_probes_skip_legacy_password(tmp_path, monkeypatch):
    migration = server.migrate_install
    for name in ("_new_data_root", "_old_data_root", "_desktop_dir"):
        monkeypatch.setattr(migration, name, lambda: tmp_path)
    password = Mock(return_value=True)
    monkeypatch.setattr(migration, "_legacy_keyring_key_present", password)
    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": True})
    monkeypatch.setattr(server, "_probe_command", lambda *args, **kwargs: ("ok", "fixture"))
    payload = server._build_diagnose_payload(public=True)
    assert payload["migration"]["app_data"]["new_exists"]
    assert any(c["name"] == "ffmpeg_available" for c in payload["checks"])
    password.assert_not_called()
    assert migration.migration_status()["keyring_legacy_present"] is True


def test_restore_rechecks_destination_before_moving(tmp_path, monkeypatch):
    root = tmp_path
    dst = root / "topic/item"
    row = {"video_id": "sample", "slug": "item", "corpus_path": str(dst / "item.md"), "deleted_at": "2026-01-01"}
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    trash = server._trash_folder_for(row)
    trash.mkdir(parents=True)
    idx = Mock()
    idx.get_yoink.return_value = row
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_mirror_event", Mock())
    held = set()
    open_parent = storage._parent_directory
    @contextmanager
    def track_parent(root, path, **kwargs):
        with open_parent(root, path, **kwargs) as fd:
            held.add(path.parent)
            try:
                yield fd
            finally:
                held.remove(path.parent)
    monkeypatch.setattr(storage, "_parent_directory", track_parent)
    original = storage.checked_path
    def check(root, path):
        if path == dst and held == {trash.parent, dst.parent}:
            raise OSError("Destination unavailable at move")
        return original(root, path)
    monkeypatch.setattr(storage, "checked_path", check)
    h = handler()
    h._handle_memory_restore({"video_id": "sample"})
    assert h._send_json.call_args.args[0] >= 400
    assert trash.is_dir() and not dst.exists()
    idx.restore_yoink.assert_not_called()


@pytest.mark.parametrize("source,error,status", [
    ("disk", PermissionError("fixture-detail"), 500),
    ("viewer", RuntimeError("fixture-detail"), 500),
    ("utf8", None, 400),
])
def test_open_markdown_errors_are_specific_and_private(tmp_path, monkeypatch, source, error, status):
    path = tmp_path / "saved.md"
    path.write_bytes(b"\xff" if source == "utf8" else b"text")
    h = handler()
    idx = Mock()
    idx.get_yoink.return_value = {"video_id": "sample", "corpus_path": str(path)}
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    if source == "disk":
        monkeypatch.setattr(server, "open_regular", Mock(side_effect=error))
    monkeypatch.setattr(server._platform, "open_in_os", Mock(side_effect=error))
    code, payload = h._handle_yoink_open_markdown("/yoinks/sample/open-markdown")
    assert code == status and payload["ok"] is False and "fixture-detail" not in payload["error"]
    assert ("UTF-8" in payload["error"]) == (source == "utf8")


def test_open_markdown_stat_permission_is_a_storage_error(tmp_path, monkeypatch):
    path = tmp_path / "file.md"
    idx = Mock()
    idx.get_yoink.return_value = {"corpus_path": str(path)}
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "checked_path", lambda root, value: value)
    monkeypatch.setattr(type(path), "stat", Mock(side_effect=PermissionError("private-detail")))
    status, payload = handler()._handle_yoink_open_markdown("/yoinks/sample/open-markdown")
    assert status == 500
    assert "private-detail" not in payload["error"] and "UTF-8" not in payload["error"]


def test_relay_token_at_settings_limit_round_trips_and_clears(monkeypatch):
    from tests.test_relay_inbox import FakeKeyring
    class LimitedKeyring(FakeKeyring):
        def set_password(self, service, username, value):
            if len(value.encode("utf-16le")) > 2560:
                raise ValueError("Credential exceeds the Windows blob limit")
            super().set_password(service, username, value)
    backend = LimitedKeyring()
    url = "https://relay.example.test"
    monkeypatch.setattr(server, "_read_settings", lambda: {"relay_url": url})
    monkeypatch.setattr(server, "_credential_store_mode", lambda: "keyring")
    monkeypatch.setattr(server, "_keyring", backend)
    monkeypatch.setattr(server, "_keyring_service_name", lambda: "test-relay")
    backend.set_password("test-relay", server.KEYRING_RELAY_USERNAME, "plain-fixture")
    assert server._get_saved_relay_token() == "plain-fixture"
    for char in ("a", "b"):
        server._store_saved_relay_token(char * 4096, relay_url=url)
        assert server._get_saved_relay_token() == char * 4096
    url = "https://second.example.test"
    assert server._get_saved_relay_token() == ""
    server._store_saved_relay_token("")
    assert not backend.values


def test_interrupted_large_token_update_preserves_last_complete_value(monkeypatch):
    from tests.test_relay_inbox import FakeKeyring
    backend = FakeKeyring()
    service = "fixture-store"
    prior = "a" * 4096
    assert server._set_relay_password(backend, service, prior)
    write = backend.set_password
    def fail_part(target, username, value):
        if target.endswith(".b.1"):
            raise OSError("store unavailable")
        write(target, username, value)
    monkeypatch.setattr(backend, "set_password", fail_part)
    with pytest.raises(OSError):
        server._set_relay_password(backend, service, "b" * 4096)
    header = backend.get_password(service, server.KEYRING_RELAY_USERNAME)
    assert server._decode_relay_password(backend, service, header) == prior
    assert server._set_relay_password(backend, service, "")
    assert not backend.values
