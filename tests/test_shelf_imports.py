"""3.18 shelves: imports keep the user's own folders and playlists as shelves.

Synthetic files and patched extractors only, never the network."""
from __future__ import annotations

import socket

import pytest

import index as index_mod
import list_imports as li
import server
import shelf_router

X_URL = "https://x.com/synthetic/status/10001"
POST = "https://www.reddit.com/r/synthetic/comments/abc123/a_test_post/"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("shelf import tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(li, "http_get_json", refuse)


@pytest.fixture
def helper(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "_settings_path", lambda: server.SETTINGS_PATH)
    monkeypatch.setattr(server, "_save_x_video_poster", lambda *a: None)
    (tmp_path / "data").mkdir()
    server.SETTINGS_PATH.write_text('{"x_text_capture_enabled": true}', encoding="utf-8")
    yield idx
    idx.close()


def folders(items):
    return [item.get("folder") for item in items]


def test_legacy_takeout_playlist_title_is_the_folder():
    text = ("Playlist Id,Channel Id,Title\nsynthetic-playlist,synthetic-channel,Bread experiments\n\n"
            "Video Id,Time Added\nsave0000001,now\nsave0000002,now\n")
    assert folders(li.parse_watch_later_csv(text)) == ["Bread experiments"] * 2
    watch_later = text.replace("Bread experiments", "Watch later")
    assert folders(li.parse_watch_later_csv(watch_later)) == [None, None]


def test_folder_column_wins_per_row():
    text = "Video ID,Playlist\nsave0000001,Synth patches\nsave0000002,\nsave0000003,Watch later\n"
    assert folders(li.parse_watch_later_csv(text)) == ["Synth patches", None, None]
    reddit = f"id,permalink,folder\nabc123,{POST},Gardening\n"
    assert folders(li.parse_reddit_saved_csv(reddit)) == ["Gardening"]


@pytest.mark.parametrize("filename, expected", [
    ("Bread experiments-videos.csv", "Bread experiments"),
    ("Watch later-videos.csv", None),
    ("watch-later.csv", None),
    ("saved_posts.csv", None),
    (None, None),
])
def test_takeout_file_name_names_the_playlist(tmp_path, filename, expected):
    staged = li.stage_saves_text(tmp_path, "Video ID,Time Added\nsave0000001,now\n", filename=filename)
    items = li._load_stage(tmp_path, staged["stage_id"])["items"]
    assert folders(items) == [expected]


def test_extension_folder_applies_to_every_chunk(tmp_path):
    first = li.stage_saves(tmp_path, "x_bookmarks", [X_URL], folder="Tools to try")
    li.append_stage_items(tmp_path, first["url"], "x_bookmarks", [X_URL.replace("10001", "10002")],
                          folder="Tools to try")
    items = li._load_stage(tmp_path, first["stage_id"])["items"]
    assert folders(items) == ["Tools to try", "Tools to try"]
    # An item that names its own folder keeps it.
    own = li.stage_saves(tmp_path, "x_bookmarks", [{"url": X_URL, "folder": "Mine"}], folder="Other")
    assert folders(li._load_stage(tmp_path, own["stage_id"])["items"]) == ["Mine"]


def test_youtube_playlist_title_is_the_folder_but_threads_are_not():
    def ytdlp(url, start, end):
        return {"title": title, "entries": [{"id": "save0000001", "title": "a"}], "playlist_count": 1}
    for title, expected in (("Synth patches", "Synth patches"), ("Watch later", None)):
        batch = li.fetch_source({"kind": li.SOURCE_PLAYLIST, "url": "https://www.youtube.com/playlist?list=PLx"},
                                offset=0, limit=50, ytdlp_playlist=ytdlp)
        assert folders(batch["items"]) == [expected]
    thread = {"id": 1, "title": "Ask HN: favourite talks", "url": "https://www.youtube.com/watch?v=save0000001",
              "children": []}
    batch = li.fetch_source({"kind": li.SOURCE_HN, "id": "1", "url": "https://news.ycombinator.com/item?id=1"},
                            offset=0, limit=50, fetch_json=lambda url: thread)
    assert folders(batch["items"]) == [None]


def test_imported_video_folder_becomes_the_shelf_hint(helper):
    token = li.stage_saves(server.DATA_ROOT, "watch_later",
                           [{"url": "save0000001", "folder": "Synth patches"}, "save0000002"])["url"]
    result = server._list_import_start(token)
    assert [v["folder"] for v in result["videos"]] == ["Synth patches", None]
    url = "https://www.youtube.com/watch?v=save0000001"
    assert shelf_router.hint_for(server.DATA_ROOT, url) == "Synth patches"
    meta = {"title": "LLM fine-tuning on a laptop", "description": "", "duration": 600}
    assert server._route_topic(meta, url="https://youtu.be/save0000001") == "Synth patches"
    assert server._route_topic(meta, url="https://youtu.be/save0000002") == "AI and ML"


@pytest.mark.parametrize("source, url, module, name", [
    ("x_bookmarks", X_URL, "x_extractor", "extract_x_thread"),
    ("reddit_saved", POST, "reddit_extractor", "extract_reddit_thread"),
])
def test_imported_post_lands_on_its_folder(helper, monkeypatch, source, url, module, name):
    monkeypatch.setattr(getattr(server, module), name, lambda value: {
        "ok": True, "url": url, "title": "LLM fine-tuning notes", "markdown": "LLM fine-tuning notes.",
        "metadata": {"author": "synthetic", "author_handle": "synthetic"},
        "tweets_captured": 1, "comments_captured": 1})
    token = li.stage_saves(server.DATA_ROOT, source, [url], folder="Tools to try")["url"]
    server._list_import_start(token)
    assert next(iter(li.load_registry(server.DATA_ROOT)["items"].values()))["folder"] == "Tools to try"
    assert server._saves_capture_one(now=100)
    row = next(iter(li.load_registry(server.DATA_ROOT)["items"].values()))
    assert helper.get_yoink(row["captured_video_id"])["topic"] == "Tools to try"


def test_stage_route_checks_the_folder(helper):
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: (status, payload)
    status, data = handler._handle_import_list(
        {"items": [X_URL], "source": "x_bookmarks", "folder": "Tools to try"}, stage=True)
    assert status == 200
    assert folders(li._load_stage(server.DATA_ROOT, data["stage_id"])["items"]) == ["Tools to try"]
    for bad in (5, "", "   ", ["x"]):
        status, data = handler._handle_import_list(
            {"items": [X_URL], "source": "x_bookmarks", "folder": bad}, stage=True)
        assert status == 400 and data["code"] == "invalid_items", bad
