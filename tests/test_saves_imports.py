"""Platform saves use synthetic files and patched extractors, never the network."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import socket

import pytest

import index as index_mod
import list_imports as li
import server
import uoink_mcp_tools as mcp

FIX = Path(__file__).parent / "fixtures" / "list_imports"
POST = "https://www.reddit.com/r/synthetic/comments/abc123/a_test_post/"
COMMENT = POST + "def456/"
X_URL = "https://x.com/synthetic/status/10001"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("saves tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(li, "http_get_json", refuse)


@pytest.fixture
def helper(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "_classify_topic", lambda _: "Testing")
    monkeypatch.setattr(server, "_save_x_video_poster", lambda *a: None)
    monkeypatch.setattr(mcp, "_b", lambda: server)
    (tmp_path / "data").mkdir()
    server.SETTINGS_PATH.write_text('{"x_text_capture_enabled": false}', encoding="utf-8")
    yield idx
    idx.close()


def stage(source, values):
    return li.stage_saves(server.DATA_ROOT, source, li.parse_save_items(source, values))["url"]


def registry():
    return li.load_registry(server.DATA_ROOT)["items"]


def pending(idx):
    with idx._lock:
        return idx._conn.execute("SELECT url FROM pending_yoinks ORDER BY pending_id").fetchall()


def capture_result(url):
    return {"ok": True, "url": url, "title": "A synthetic post", "markdown": "Synthetic words.",
            "metadata": {"author": "synthetic", "author_handle": "synthetic"},
            "tweets_captured": 1, "comments_captured": 1}


@pytest.mark.parametrize("fixture", ["watch_later_current.csv", "watch_later_legacy.csv"])
@pytest.mark.parametrize("bom_crlf", [False, True])
def test_takeout_formats(fixture, bom_crlf):
    text = (FIX / fixture).read_text(encoding="utf-8")
    if bom_crlf:
        text = "\ufeff" + text.replace("\n", "\r\n")
    items = li.parse_watch_later_csv(text)
    assert [row["video_id"] for row in items] == [f"save{i:07d}" for i in range(1, 4)]
    assert all(row["kind"] == "video" and row["item_key"] == row["video_id"] for row in items)


def test_takeout_finds_video_column_and_reads_url_lines():
    items = li.parse_watch_later_csv("Time Added, VIDEO ID \r\nnow,save0000001\r\n"
                                    "https://youtu.be/save0000002\r\n")
    assert [row["video_id"] for row in items] == ["save0000001", "save0000002"]


def test_reddit_csv_posts_comments_and_library_hash():
    text = "\ufeff" + (FIX / "reddit_saved.csv").read_text(encoding="utf-8").replace("\n", "\r\n")
    items = li.parse_reddit_saved_csv(text)
    assert [row["item_key"] for row in items] == ["reddit:abc123", "reddit:abc123:def456", "reddit:xyz789"]
    assert items[0]["url"] == POST and items[1]["url"] == COMMENT
    expected = "reddit_" + hashlib.sha1(POST.encode()).hexdigest()[:11]
    assert items[0]["video_id"] == items[1]["video_id"] == expected
    assert items[2]["url"].endswith("/another_test/")


@pytest.mark.parametrize("source,values,keys", [
    ("watch_later", ["save0000001", {"id": "save0000002", "title": "Second", "channel": "Demo"},
                     "https://youtu.be/save0000001", "bad", None], ["save0000001", "save0000002"]),
    ("x_bookmarks", [X_URL, "https://twitter.com/Synthetic/status/10001?x=1", {"id": "10002", "author": "Demo"},
                     "https://x.com/synthetic/status/12bad", "https://x.com.evil/synthetic/status/1"],
     ["x:10001", "x:10002"]),
    ("reddit_saved", [POST, COMMENT + "?context=1", {"url": POST, "title": "duplicate"},
                      "https://reddit.com/r/synthetic/", "https://reddit.com.evil/r/s/comments/a/b/"],
     ["reddit:abc123", "reddit:abc123:def456"]),
])
def test_extension_items(source, values, keys):
    items = li.parse_save_items(source, values)
    assert [row["item_key"] for row in items] == keys
    if source == "x_bookmarks":
        assert items[0]["url"] == X_URL
        assert items[1]["url"] == "https://x.com/i/status/10002"
        assert items[1]["channel"] == "Demo"
        assert items[0]["video_id"] == "x_" + hashlib.sha1(X_URL.encode()).hexdigest()[:11]
    elif source == "watch_later":
        assert items[1]["title"] == "Second" and items[1]["channel"] == "Demo"


def test_parse_cap_and_stage_truncation(tmp_path):
    items = li.parse_save_items("watch_later", [f"save{i:07d}" for i in range(5002)])
    assert len(items) == 5000
    staged = li.stage_saves(tmp_path, "watch_later", items)
    assert staged["truncated"] and staged["count"] == 5000
    text = "Video ID,Time Added\n" + "\n".join(f"save{i:07d},now" for i in range(5001))
    assert li.stage_saves_text(tmp_path, text)["truncated"]
    assert not li.stage_saves(tmp_path, "watch_later", items[:5000])["truncated"]


def test_staging_classification_atomic_write_and_paging(tmp_path, monkeypatch):
    replaced = []
    replace = os.replace
    def observe(src, dst):
        assert json.loads(Path(src).read_text(encoding="utf-8"))["source"] == "watch_later"
        replaced.append((src, dst))
        replace(src, dst)
    monkeypatch.setattr(li.os, "replace", observe)
    staged = li.stage_saves(tmp_path, "watch_later", [f"save{i:07d}" for i in range(103)])
    assert len(replaced) == 1 and not replaced[0][0].exists()
    spec = li.classify(staged["url"], data_root=tmp_path)
    assert spec["kind"] == "watch_later" and len(spec["stage_id"]) == 16
    assert li.classify(staged["url"])["stage_id"] == spec["stage_id"]
    for offset, count, next_offset in [(0, 50, 50), (50, 50, 100), (100, 3, None), (103, 0, None)]:
        batch = li.fetch_source(spec, offset=offset, limit=50, data_root=tmp_path)
        preview = li.build_preview(spec, batch, offset=offset, limit=50, in_library=lambda _: False)
        assert preview["found"] == count and preview["next_offset"] == next_offset
        assert preview["total"] == 103 and preview["source"]["url"] == staged["url"]
    assert len(li.fetch_source(spec, offset=0, limit=500, data_root=tmp_path)["items"]) == 50


def test_only_twenty_stages_are_kept(tmp_path):
    tokens = []
    for i in range(22):
        staged = li.stage_saves(tmp_path, "watch_later", ["save0000001"])
        tokens.append(staged)
        os.utime(tmp_path / "saves-staged" / f"{staged['stage_id']}.json", (i + 1, i + 1))
    assert len(list((tmp_path / "saves-staged").glob("*.json"))) == 20
    with pytest.raises(li.ImportListError, match="wasn't found") as err:
        li.classify(tokens[0]["url"], tmp_path)
    assert err.value.code == "not_found"
    assert li.classify(tokens[-1]["url"], tmp_path)["kind"] == "watch_later"


@pytest.mark.parametrize("token", ["uoink-saves:../bad", "uoink-saves:abc", "uoink-saves:" + "a" * 17,
                                   "uoink-saves:" + "g" * 16, "uoink-saves:" + "a" * 16 + "/x"])
def test_bad_stage_tokens(tmp_path, token):
    with pytest.raises(li.ImportListError) as err:
        li.classify(token, tmp_path)
    assert err.value.code == "invalid_url"


@pytest.mark.parametrize("text,source", [
    ("Video ID,Time Added\nsave0000001,now", "watch_later"),
    ("https://youtu.be/save0000001", "watch_later"),
    ("id,permalink\nabc123,/r/synthetic/comments/abc123/a_test_post/", "reddit_saved"),
    (COMMENT, "reddit_saved"), (X_URL, "x_bookmarks"),
])
def test_file_and_text_auto_detection(tmp_path, text, source):
    path = tmp_path / "saves.CSV"
    path.write_text(text, encoding="utf-8-sig")
    assert li.stage_saves_file(tmp_path, path)["source"] == source
    assert li.stage_saves_text(tmp_path, text)["source"] == source


def test_file_refusals_and_empty_inputs(tmp_path):
    path = tmp_path / "saves.txt"
    path.write_text("no saves here", encoding="utf-8")
    for fn, code in [
        (lambda: li.stage_saves_file(tmp_path, tmp_path / "missing.txt"), "not_found"),
        (lambda: li.stage_saves_file(tmp_path, tmp_path / "unsupported.json"), "unsupported"),
        (lambda: li.stage_saves_file(tmp_path, path), "empty_file"),
        (lambda: li.stage_saves_text(tmp_path, "invalid", source="watch_later"), "empty_file"),
        (lambda: li.stage_saves_text(tmp_path, "save0000001", source="unknown"), "unsupported"),
        (lambda: li.classify("uoink-saves:0123456789abcdef", tmp_path), "not_found"),
        (lambda: li.parse_save_items("watch_later", "save0000001"), "invalid_items"),
    ]:
        with pytest.raises(li.ImportListError) as err:
            fn()
        assert err.value.code == code
    path.write_bytes(b"x" * (li.SAVES_FILE_MAX_BYTES + 1))
    with pytest.raises(li.ImportListError) as err:
        li.stage_saves_file(tmp_path, path)
    assert err.value.code == "too_large"
    with pytest.raises(li.ImportListError) as err:
        li.stage_saves_text(tmp_path, "x" * (li.SAVES_FILE_MAX_BYTES + 1))
    assert err.value.code == "too_large"


def test_preview_dedupe_by_library_and_captured_registry(helper):
    token = stage("reddit_saved", [COMMENT])
    item = li.parse_save_items("reddit_saved", [COMMENT])[0]
    server._persist_reddit_thread(capture_result(POST))
    preview = server._list_import_preview(token)
    assert preview["already"] == 1 and preview["videos"][0]["in_library"]
    assert item["video_id"] == preview["videos"][0]["video_id"]
    x_token = stage("x_bookmarks", [X_URL])
    preview = server._list_import_preview(x_token)
    li.record_import(server.DATA_ROOT, preview, preview["videos"])
    with li._registry_lock:
        data = json.loads(json.dumps(li.load_registry(server.DATA_ROOT)))
        next(row for row in data["items"].values() if row["kind"] == "post").update(
            status="captured", captured_video_id="x_best_effort_changed")
        li._save_registry(server.DATA_ROOT, data)
    differently_cased = stage("x_bookmarks", [X_URL.replace("synthetic", "Synthetic")])
    assert server._list_import_preview(differently_cased)["already"] == 1


def test_start_routes_videos_and_posts_and_dedupes_queue(helper):
    videos = stage("watch_later", ["save0000001", "save0000002"])
    assert server._list_import_start(videos)["queued"] == 2
    assert len(pending(helper)) == 2
    for source, values in [("x_bookmarks", [X_URL]), ("reddit_saved", [POST, COMMENT])]:
        token = stage(source, values)
        result = server._list_import_start(token)
        assert result["queued"] == 1
        assert result["already_queued"] == len(values) - 1
        assert "They capture one at a time in the background." in result["message"]
        again = server._list_import_start(token)
        assert again["queued"] == 0 and again["already_queued"] == len(values)
    assert len(pending(helper)) == 2
    assert len([row for row in registry().values() if row.get("status") == "queued"]) == 2


@pytest.mark.parametrize("source,url,canonical,tag", [
    ("x_bookmarks", X_URL, X_URL.replace("synthetic", "Synthetic"), "x bookmarks"),
    ("reddit_saved", COMMENT, POST, "reddit saved"),
])
def test_capture_success_persists_tags_and_dedupes(helper, monkeypatch, source, url, canonical, tag):
    server.SETTINGS_PATH.write_text('{"x_text_capture_enabled": true}', encoding="utf-8")
    calls, posters = [], []
    def extract(value):
        calls.append(value)
        return capture_result(canonical)
    module, name = ((server.x_extractor, "extract_x_thread") if source == "x_bookmarks"
                    else (server.reddit_extractor, "extract_reddit_thread"))
    monkeypatch.setattr(module, name, extract)
    monkeypatch.setattr(server, "_save_x_video_poster", lambda vid, result: posters.append(vid))
    token = stage(source, [url])
    server._list_import_start(token)
    assert server._saves_capture_one(now=100)
    row = next(iter(registry().values()))
    assert row["status"] == "captured" and row["error"] is None
    assert calls == [url] and helper.get_yoink(row["captured_video_id"])
    assert helper.get_tags(row["captured_video_id"]) == [tag]
    assert li.lookup(server.DATA_ROOT, row["captured_video_id"])["source"] == source
    assert row["captured_video_id"] in li.imported_video_ids(server.DATA_ROOT)
    with helper._lock:
        assert helper._conn.execute("SELECT source FROM yoink_tags WHERE video_id = ?", (row["captured_video_id"],)).fetchone()[0] == li.TAG_SOURCE
    assert posters == ([row["captured_video_id"]] if source == "x_bookmarks" else [])
    assert not pending(helper) and not server._saves_capture_one(now=200)
    result = server._list_import_start(token)
    assert result["queued"] == 0 and result["skipped"] == 1


def test_capture_between_preview_and_import_is_not_queued_again(helper, monkeypatch):
    token = stage("reddit_saved", [COMMENT])
    stale = server._list_import_preview(token)
    server._list_import_start(token)
    monkeypatch.setattr(server.reddit_extractor, "extract_reddit_thread", lambda _: capture_result(POST))
    assert server._saves_capture_one(now=100)
    monkeypatch.setattr(server, "_list_import_preview", lambda *args: stale)
    result = server._list_import_start(token)
    assert result["queued"] == 0 and result["skipped"] == 1
    assert next(iter(registry().values()))["status"] == "captured"


def test_failure_backoff_preserved_on_reimport_then_final_failure(helper, monkeypatch):
    monkeypatch.setattr(server.reddit_extractor, "extract_reddit_thread",
                        lambda _: {"ok": False, "code": "rate_limited", "error": "Synthetic refusal"})
    token = stage("reddit_saved", [COMMENT])
    server._list_import_start(token)
    for now, attempts, due, status in [(100, 1, 160, "queued"), (160, 2, 460, "queued"), (460, 3, 1360, "failed")]:
        assert server._saves_capture_one(now=now)
        row = next(iter(registry().values()))
        assert (row["attempts"], row["retry_after"], row["status"], row["error"]) == (attempts, due, status, "rate_limited")
        assert not server._saves_capture_one(now=due - 1)
        if status == "queued":
            assert server._list_import_start(token)["already_queued"] == 1
            assert next(iter(registry().values()))["attempts"] == attempts
    assert not server._saves_capture_one(now=2000)
    assert server._list_import_start(token)["queued"] == 1
    assert next(iter(registry().values()))["attempts"] == 0


def test_x_capture_disabled_waits_without_extraction(helper, monkeypatch):
    monkeypatch.setattr(server.x_extractor, "extract_x_thread", lambda _: pytest.fail("disabled X must not fetch"))
    server._list_import_start(stage("x_bookmarks", [X_URL]))
    assert not server._saves_capture_one(now=100)
    row = next(iter(registry().values()))
    assert row["status"] == "queued" and row.get("attempts", 0) == 0


def test_stage_token_prefix_is_case_insensitive(helper):
    token = stage("watch_later", ["dQw4w9WgXcQ"])
    spec = li.classify(token.upper().replace("UOINK-SAVES:", "Uoink-Saves:"), data_root=server.DATA_ROOT)
    assert spec["url"] == token.lower()


def test_registry_cap_never_evicts_queued_posts(helper, monkeypatch):
    monkeypatch.setattr(li, "REGISTRY_ITEM_CAP", 1)
    server._list_import_start(stage("x_bookmarks", [X_URL, X_URL.replace("10001", "10002")]))
    server._list_import_start(stage("watch_later", ["save0000001"]))
    assert len(registry()) == 2 and all(row["status"] == "queued" for row in registry().values())


def test_worker_takes_one_oldest_due_item_and_is_guarded_under_tests(helper, monkeypatch):
    calls = []
    monkeypatch.setattr(server.reddit_extractor, "extract_reddit_thread",
                        lambda url: calls.append(url) or capture_result(url))
    server._list_import_start(stage("reddit_saved", [POST, POST.replace("abc123", "xyz789")]))
    assert server._saves_capture_one(now=100) and calls == [POST]
    assert [row["status"] for row in registry().values()] == ["captured", "queued"]
    monkeypatch.setattr(server.threading, "Thread", lambda **kwargs: pytest.fail("worker started under tests"))
    server._start_saves_thread()


def test_stage_handler_uses_shared_parsers_and_errors(helper):
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: (status, payload)
    status, data = handler._handle_import_list({"csv_text": COMMENT, "filename": "saved_comments.csv"}, stage=True)
    assert status == 200 and data["ok"] and data["source"] == "reddit_saved"
    assert data["label"] == "Reddit saved" and data["count"] == 1 and not data["truncated"]
    assert server._list_import_preview(data["url"])["found"] == 1
    status, data = handler._handle_import_list({"items": [{"url": X_URL}], "source": "x_bookmarks"}, stage=True)
    assert status == 200 and data["source"] == "x_bookmarks"
    for body, code in [({"items": [X_URL]}, "unsupported"), ({"csv_text": "bad"}, "empty_file"),
                       ({"items": X_URL, "source": "x_bookmarks"}, "invalid_items"),
                       ({"csv_text": "", "items": []}, "invalid_items")]:
        status, data = handler._handle_import_list(body, stage=True)
        assert status == 400 and data["code"] == code
    assert handler._handle_import_list([], stage=True)[0] == 400
    assert not pending(helper)


def test_stage_http_route_auth_and_large_file_body(helper):
    handler = object.__new__(server.Handler)
    handler.path = "/import-list/stage"
    handler._reject_bad_host = lambda: False
    handler._send_json = lambda status, payload: (status, payload)
    handler._require_token = lambda: False
    # Rejected authentication must not even read a body.
    assert handler.do_POST() is None
    handler._require_token = lambda: True
    text = "Video ID,Time Added\n" + "save0000001,synthetic timestamp\n" * 3000
    raw = json.dumps({"csv_text": text, "filename": "watch-later.csv"}).encode()
    assert len(raw) > server.MAX_BODY_BYTES
    handler.headers = {"Content-Type": "application/json", "Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    status, data = handler.do_POST()
    assert status == 200 and data["count"] == 1 and data["source"] == "watch_later"
    handler.path = "/import-list/preview"
    handler.rfile = io.BytesIO(raw)
    assert handler.do_POST()[0] == 413  # Other routes retain their original cap.


def test_mcp_import_file_items_and_token_paging(helper, tmp_path):
    path = tmp_path / "saves.txt"
    path.write_text("\n".join(f"https://youtu.be/save{i:07d}" for i in range(51)), encoding="utf-8")
    preview = mcp.import_list({"file": str(path), "preview_only": True})
    assert preview["ok"] and preview["queued"] == 0 and preview["next_offset"] == 50
    assert preview["stage_url"] == preview["source"]["url"] and not pending(helper)
    result = mcp.import_list({"url": preview["stage_url"], "offset": 50})
    assert result["queued"] == 1 and result["next_offset"] is None and "stage_url" not in result
    result = mcp.import_list({"source": "x_bookmarks", "items": [X_URL]})
    assert result["ok"] and result["queued"] == 1 and result["stage_url"]
    assert len(pending(helper)) == 1
    for args in ({}, {"items": [X_URL]}, {"file": 4}, {"items": "bad", "source": "x_bookmarks"},
                 {"url": X_URL, "file": str(path)}, {"items": [X_URL] * 5001, "source": "x_bookmarks"}):
        assert not mcp.import_list(args)["ok"]
    spec = mcp.TOOL_REGISTRY["import_list"]
    assert "url" not in spec.input_schema.get("required", [])
    assert spec.input_schema["properties"]["items"]["maxItems"] == 5000
    assert "stage_url" in mcp.OUTPUT_SCHEMAS["import_list"]["properties"]
