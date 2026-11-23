"""Tidy Uncategorized over HTTP: propose, accept a group, undo, bulk move.

Real index, real files on disk, no meaning vectors (local search is off),
so this is the path every user has. Made-up saves only.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import index as index_mod
import server
import shelf_router

COOKING = [("Sourdough starter day three", "feeding the sourdough starter, crumb and proofing"),
           ("Cast iron pan sauce", "brown butter pan sauce in the cast iron skillet"),
           ("Weeknight ramen broth", "ramen broth with miso and quick dumplings"),
           ("Knife skills for onions", "knife skills, dice and julienne for the recipe")]
LOOSE = ([("Sourdough crumb shot", "proofing the sourdough went long"),
          ("Starter rescue", "my sourdough starter smelled odd, feeding it twice")]
         + [(f"Tomato seedlings week {i}", "raised beds and tomato seedlings, hardening off") for i in range(5)]
         + [("A quiet harbor at dawn", "")])


def write_save(root, topic, slug, title, text):
    folder = root / topic / slug
    folder.mkdir(parents=True)
    sidecar = folder / "sidecar.json"
    sidecar.write_text(json.dumps({"video_id": slug, "title": title, "topic": topic}), encoding="utf-8")
    note = folder / f"{slug}.md"
    note.write_text(f"# {title}\n\n**Topic:** {topic}\n**Channel:** Test Kitchen\n\n{text}\n", encoding="utf-8")
    return sidecar, note


@pytest.fixture
def lib(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
    monkeypatch.setattr(server, "INDEX_PATH", tmp_path / "index.db")
    monkeypatch.setattr(server, "_local_search_singleton", None)
    server._shelf_library_cache.update(key=None, at=0.0, library=None)
    (tmp_path / "data").mkdir()
    files = {}
    rows = [("Cooking", f"cook{i}", t, x) for i, (t, x) in enumerate(COOKING)]
    rows += [("Uncategorized", f"loose{i}", t, x) for i, (t, x) in enumerate(LOOSE)]
    for n, (topic, slug, title, text) in enumerate(rows):
        sidecar, note = write_save(tmp_path / "library", topic, slug, title, text)
        files[slug] = (sidecar, note)
        idx.upsert_yoink({"video_id": slug, "slug": slug, "title": title,
                          "channel": "Test Kitchen" if topic == "Cooking" else f"Reader {n}",
                          "topic": topic, "yoinked_at": f"2026-01-{n + 1:02d}T00:00:00",
                          "corpus_path": str(note), "sidecar_path": str(sidecar), "source_type": "page"},
                         content=note.read_text(encoding="utf-8"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield idx, files, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    idx.close()


def call(port, path, body=None, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def where(idx, files, video_id):
    """The shelf as the index, the search row, the sidecar and the note see it."""
    with idx._lock:
        fts = idx._conn.execute("SELECT topic FROM yoinks_fts WHERE video_id=?", (video_id,)).fetchone()[0]
    on_disk = shelf_router.files_topic(*files[video_id])
    return {idx.get_yoink(video_id)["topic"], fts, on_disk["sidecar"], on_disk["corpus"]}


def test_propose_accept_group_and_undo_keep_files_and_index_together(lib):
    idx, files, port = lib
    assert call(port, "/library/shelves/tidy", token=False)[0] in (401, 403)
    status, tidy = call(port, "/library/shelves/tidy")
    assert status == 200 and tidy["ok"] and tidy["meaning"] == "off"
    assert tidy["total"] == len(LOOSE) and tidy["stays"] >= 1
    groups = {g["shelf"]: g for g in tidy["groups"]}
    cooking = groups["Cooking"]
    assert cooking["new"] is False
    assert sorted(i["video_id"] for i in cooking["items"]) == ["loose0", "loose1"]
    assert all(i["reason"] for i in cooking["items"])
    new = [g for g in tidy["groups"] if g["new"]]
    assert new and new[0]["shelf"].lower().startswith("tomato") and new[0]["count"] == 5

    status, applied = call(port, "/library/shelves/apply",
                           {"moves": [{"video_id": i["video_id"], "shelf": "Cooking"} for i in cooking["items"]]})
    assert status == 200 and applied["moved"] == 2 and applied["batch_id"]
    for vid in ("loose0", "loose1"):
        assert where(idx, files, vid) == {"Cooking"}
    status, again = call(port, "/library/shelves/tidy")
    assert "Cooking" not in {g["shelf"] for g in again["groups"]}
    assert again["undo"]["count"] == 2

    status, undone = call(port, "/library/shelves/undo", {})
    assert status == 200 and undone["restored"] == 2
    for vid in ("loose0", "loose1"):
        assert where(idx, files, vid) == {"Uncategorized"}
    assert call(port, "/library/shelves/undo", {"batch_id": applied["batch_id"]})[0] == 409


def test_new_shelf_and_bulk_move_with_undo_by_id(lib):
    idx, files, port = lib
    ids = [f"loose{i}" for i in range(2, 7)]
    status, moved = call(port, "/library/shelves/move", {"video_ids": ids + ids[:1], "shelf": "Garden"})
    assert status == 200 and moved["moved"] == 5
    assert all(where(idx, files, vid) == {"Garden"} for vid in ids)
    # One save moves again before the undo: it stays where the user put it.
    assert call(port, "/library/shelves/move", {"video_ids": ["loose2"], "shelf": "Seeds"})[1]["moved"] == 1
    status, undone = call(port, "/library/shelves/undo", {"batch_id": moved["batch_id"]})
    assert status == 200 and undone["restored"] == 4 and len(undone["skipped"]) == 1
    assert where(idx, files, "loose2") == {"Seeds"}
    assert all(where(idx, files, vid) == {"Uncategorized"} for vid in ids[1:])


def test_a_big_move_in_parts_is_one_undo(lib, monkeypatch):
    idx, files, port = lib
    ids = [f"loose{i}" for i in range(8)]
    status, first = call(port, "/library/shelves/move", {"video_ids": ids[:3], "shelf": "Garden"})
    assert status == 200 and first["moved"] == 3
    status, second = call(port, "/library/shelves/move",
                          {"video_ids": ids[3:6], "shelf": "Garden", "append_to": first["batch_id"]})
    assert status == 200 and second["batch_id"] == first["batch_id"] and second["undo"]["count"] == 6
    monkeypatch.setattr(shelf_router, "MAX_MOVES", 7)
    status, over = call(port, "/library/shelves/move",
                        {"video_ids": ids[6:], "shelf": "Garden", "append_to": first["batch_id"]})
    assert status == 409 and over["code"] == "stale_batch"
    assert where(idx, files, "loose6") == {"Uncategorized"}, "a refused part moves nothing"
    status, undone = call(port, "/library/shelves/undo", {})
    assert status == 200 and undone["restored"] == 6
    status, stale = call(port, "/library/shelves/move",
                         {"video_ids": ids[6:], "shelf": "Garden", "append_to": first["batch_id"]})
    assert status == 409, "an undone batch takes no more parts"


def test_bad_requests_move_nothing(lib, monkeypatch):
    idx, files, port = lib
    monkeypatch.setattr(shelf_router, "MAX_MOVES", 50)
    for path, body in [("/library/shelves/apply", {"moves": []}),
                       ("/library/shelves/apply", {"moves": [{"video_id": "loose0", "shelf": ""}]}),
                       ("/library/shelves/apply", {"moves": [{"video_id": "loose0", "shelf": "x" * 65}]}),
                       ("/library/shelves/apply", {"moves": "loose0"}),
                       ("/library/shelves/move", {"video_ids": "loose0", "shelf": "Garden"}),
                       ("/library/shelves/move", {"video_ids": [""], "shelf": "Garden"}),
                       ("/library/shelves/move", {"video_ids": ["loose0"], "shelf": "???"}),
                       ("/library/shelves/move", {"video_ids": [f"v{i}" for i in range(shelf_router.MAX_MOVES + 1)],
                                                  "shelf": "Garden"}),
                       ("/library/shelves/apply", {"moves": [{"video_id": f"v{i}", "shelf": "G"}
                                                             for i in range(shelf_router.MAX_MOVES + 1)]}),
                       ("/library/shelves/move", {"video_ids": ["loose0"], "shelf": "G", "append_to": 5}),
                       ("/library/shelves/undo", {"batch_id": 5})]:
        status, data = call(port, path, body)
        assert status == 400 and not data["ok"], (path, body, data)
    assert call(port, "/library/shelves/undo", {})[0] == 404
    assert call(port, "/library/shelves/move", {"video_ids": ["loose0"], "shelf": "Garden"}, token=False)[0] in (401, 403)
    status, data = call(port, "/library/shelves/move", {"video_ids": ["gone"], "shelf": "Garden"})
    assert status == 200 and data["moved"] == 0 and data["skipped"][0]["video_id"] == "gone"
    assert where(idx, files, "loose0") == {"Uncategorized"}


def test_agent_classify_topic_also_moves_the_files(lib):
    idx, files, port = lib
    status, data = call(port, "/facets/classify", {"video_id": "loose7", "topic": "Harbors"})
    assert status == 200 and data["ok"]
    assert where(idx, files, "loose7") == {"Harbors"}
    # An agent's topic is not a Tidy batch, so there is nothing to undo.
    assert shelf_router.find_batch(server.DATA_ROOT, None) is None
