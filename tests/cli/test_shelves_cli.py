"""uoink shelves (tidy, apply, move, undo) and uoink capture --shelf, offline."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import index as index_mod
import server
import shelf_router
import uoink_cli as cli

COOKING = ["Sourdough starter day three", "Cast iron pan sauce", "Weeknight ramen broth",
           "Knife skills for onions"]
TEXT = {"Sourdough starter day three": "feeding the sourdough starter, crumb and proofing",
        "Cast iron pan sauce": "brown butter pan sauce in the cast iron skillet",
        "Weeknight ramen broth": "ramen broth with miso and quick dumplings",
        "Knife skills for onions": "knife skills, dice and julienne for the recipe",
        "Sourdough crumb shot": "proofing the sourdough went long",
        "Starter rescue": "my sourdough starter smelled odd, feeding it twice",
        "A quiet harbor at dawn": ""}


@pytest.fixture
def lib(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "INDEX_PATH", tmp_path / "index.db")
    monkeypatch.setattr(server, "_local_search_singleton", None)
    monkeypatch.setattr(cli, "backend", lambda: server)
    server._shelf_library_cache.update(key=None, at=0.0, library=None)
    (tmp_path / "data").mkdir()
    rows = [(f"cook{i}", "Cooking", t) for i, t in enumerate(COOKING)]
    rows += [("loose0", "Uncategorized", "Sourdough crumb shot"), ("loose1", "Uncategorized", "Starter rescue"),
             ("loose2", "Uncategorized", "A quiet harbor at dawn")]
    for n, (vid, topic, title) in enumerate(rows):
        idx.upsert_yoink({"video_id": vid, "slug": vid, "title": title, "topic": topic,
                          "channel": "Test Kitchen" if topic == "Cooking" else f"Reader {n}",
                          "yoinked_at": f"2026-01-{n + 1:02d}T00:00:00", "corpus_path": "", "sidecar_path": "",
                          "source_type": "page"}, content=f"# {title}\n\n{TEXT[title]}\n")
    yield idx
    idx.close()


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr().out
    return code, (json.loads(out) if "--text" not in argv else out)


def topic(idx, vid):
    return idx.get_yoink(vid)["topic"]


def test_tidy_apply_and_undo(lib, capsys):
    code, tidy = run(capsys, "shelves", "tidy")
    assert code == 0 and tidy["total"] == 3
    assert {g["shelf"] for g in tidy["groups"]} == {"Cooking"}
    code, text = run(capsys, "shelves", "tidy", "--text")
    assert "Cooking (2)" in text and "stay where they are" in text
    assert 'uoink shelves apply "Cooking"' in text

    code, moved = run(capsys, "shelves", "apply", "cooking", "--only", "loose1")
    assert code == 0 and moved["moved"] == 1
    assert topic(lib, "loose1") == "Cooking" and topic(lib, "loose0") == "Uncategorized"
    code, undone = run(capsys, "shelves", "undo", "--text")
    assert code == 0 and "Put back 1 save." in undone
    assert topic(lib, "loose1") == "Uncategorized"

    code, missing = run(capsys, "shelves", "apply", "Gardening")
    assert code == 1 and "No proposed group" in missing["error"]
    code, wrong = run(capsys, "shelves", "apply", "Cooking", "--only", "loose2")
    assert code == 1 and "loose2" in wrong["error"]


def test_move_names_a_new_shelf(lib, capsys):
    code, text = run(capsys, "shelves", "move", "Harbor walks", "loose2", "loose2", "--text")
    assert code == 0 and text.startswith("Moved 1 save.") and "uoink shelves undo mv_" in text
    assert topic(lib, "loose2") == "Harbor walks"


@pytest.mark.parametrize("argv", [["shelves", "move", "???", "a"], ["shelves", "move", "x" * 65, "a"],
                                  ["shelves", "tidy", "--limit", "0"], ["shelves", "tidy", "--limit", "5001"],
                                  ["shelves"], ["capture", "https://example.com/a", "--shelf", ""]])
def test_usage_errors_stop_before_the_backend(monkeypatch, capsys, argv):
    monkeypatch.setattr(cli, "backend", lambda: pytest.fail("backend must not load"))
    assert cli.main(argv) == 2
    assert capsys.readouterr().err.startswith("uoink: ")


def test_capture_shelf_is_remembered_for_the_capture(tmp_path):
    fake = SimpleNamespace(DATA_ROOT=tmp_path, _classify_capture_url=lambda url: {
        "ok": True, "source": "youtube_video", "canonical": "https://www.youtube.com/watch?v=abcdefghijk"})
    ns = cli.parser().parse_args(["capture", "https://youtu.be/abcdefghijk", "--shelf", "Synth patches"])
    assert cli.friendly_call(ns, fake) == ("uoink_video", {"url": "https://www.youtube.com/watch?v=abcdefghijk"})
    assert shelf_router.hint_for(tmp_path, "https://youtu.be/abcdefghijk") == "Synth patches"
    playlist = SimpleNamespace(DATA_ROOT=tmp_path, _classify_capture_url=lambda url: {
        "ok": True, "source": "youtube_playlist", "canonical": "https://www.youtube.com/playlist?list=PLx"})
    with pytest.raises(cli.UsageError):
        cli.friendly_call(cli.parser().parse_args(["capture", "https://x.test/p", "--shelf", "A"]), playlist)
    plain = cli.parser().parse_args(["capture", "https://youtu.be/bbbbbbbbbbb"])
    cli.friendly_call(plain, SimpleNamespace(DATA_ROOT=tmp_path, _classify_capture_url=lambda url: {
        "ok": True, "source": "youtube_video", "canonical": url}))
    assert shelf_router.hint_for(tmp_path, "https://youtu.be/bbbbbbbbbbb") is None
