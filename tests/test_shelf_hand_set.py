"""3.18 shelves: a shelf the user set by hand stays set.

Re-capturing a link, re-importing it with a folder, a late transcript, an old
hint and a stale Tidy suggestion must never move a save the user placed. The
mark lives in the index (shelf_by_hand) and the sidecar, so a rebuild keeps
it. Also: undo order and newer moves, the move log's size, a move that stops
halfway, the cross-process lock, case and Unicode duplicates, and the CLI
handing moves to a running helper. Made-up saves only, no network.
"""
from __future__ import annotations

import json
import multiprocessing
import socket
import time
import unicodedata
from types import SimpleNamespace

import pytest

import index as index_mod
import list_imports as li
import page_extractor
import server
import shelf_router
import uoink_cli as cli

PAGE = "https://example.com/notes/bread-crumb"
X_URL = "https://x.com/synthetic/status/20001"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("shelf tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def helper(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
    monkeypatch.setattr(server, "INDEX_PATH", tmp_path / "index.db")
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "_settings_path", lambda: server.SETTINGS_PATH)
    monkeypatch.setattr(server, "_save_x_video_poster", lambda *a: None)
    monkeypatch.setattr(server, "_local_search_singleton", None)
    server._shelf_library_cache.update(key=None, at=0.0, library=None)
    (tmp_path / "data").mkdir()
    server.SETTINGS_PATH.write_text('{"x_text_capture_enabled": true}', encoding="utf-8")
    yield idx
    idx.close()


def page_result(url=PAGE, title="Bread crumb notes", text="Sourdough crumb and the levain."):
    return {"ok": True, "url": url, "title": title, "markdown": text,
            "metadata": {"author": "synthetic"}}


def capture_page(url=PAGE, *, topic=None, **kw):
    return page_extractor.persist_page_yoink(server._get_index(), page_result(url, **kw), topic=topic,
                                             data_root=server.DESKTOP_ROOT, topic_classifier=server._route_topic)


def move(vid, shelf):
    result = server._reshelve([(vid, shelf)], label="Move")
    assert result["ok"] and result["moved"] == 1, result
    return result


def topic(idx, vid):
    return idx.get_yoink(vid)["topic"]


def sidecar(idx, vid):
    return json.loads(open(idx.get_yoink(vid)["sidecar_path"], encoding="utf-8").read())


# ---- P1-1: one choke point keeps a hand-set shelf ---------------------------

def test_recapturing_a_page_keeps_the_shelf_set_by_hand(helper):
    vid = capture_page()
    move(vid, "Reading list")
    assert helper.shelf_hand_seq(vid) == 1
    assert capture_page() == vid
    assert topic(helper, vid) == "Reading list"
    # The capture rewrote the sidecar; the user's shelf is back in it.
    data = sidecar(helper, vid)
    assert data["topic"] == "Reading list" and data["shelf_by_hand"] is True


def test_a_shelf_set_by_hand_on_uncategorized_or_clips_stays_too(helper):
    vid = capture_page(title="Cooking with cast iron", text="cast iron recipe kitchen cooking")
    move(vid, "Bread")
    for shelf in ("Uncategorized", "Clips"):
        move(vid, shelf)
        capture_page(title="Cooking with cast iron", text="cast iron recipe kitchen cooking")
        assert topic(helper, vid) == shelf


def test_reimporting_with_a_folder_keeps_the_shelf_set_by_hand(helper, monkeypatch):
    monkeypatch.setattr(server.x_extractor, "extract_x_thread", lambda url: {
        "ok": True, "url": X_URL, "title": "LLM fine-tuning notes", "markdown": "LLM fine-tuning notes.",
        "metadata": {"author": "synthetic", "author_handle": "synthetic"}, "tweets_captured": 1})
    vid = server._persist_x_thread(server.x_extractor.extract_x_thread(X_URL))
    move(vid, "Mine")
    # Force the import to capture the post again (as when it does not
    # recognise the saved copy), so the write goes through the choke point.
    monkeypatch.setattr(server, "_list_import_in_library", lambda video_id: False)
    token = li.stage_saves(server.DATA_ROOT, "x_bookmarks", [X_URL], folder="Tools to try")["url"]
    server._list_import_start(token)
    assert server._saves_capture_one(now=100)
    assert topic(helper, vid) == "Mine"


def test_an_old_import_hint_never_pulls_a_save_back(helper):
    shelf_router.remember_hints(server.DATA_ROOT, [(PAGE, "Old folder")])
    vid = capture_page()
    assert topic(helper, vid) == "Old folder"
    move(vid, "Uncategorized")
    # The move dropped the hint, and the index keeps the hand shelf anyway.
    assert shelf_router.hint_for(server.DATA_ROOT, PAGE) is None
    shelf_router.remember_hints(server.DATA_ROOT, [(PAGE, "Old folder")])
    capture_page()
    assert topic(helper, vid) == "Uncategorized"


def test_a_late_transcript_never_moves_a_save_placed_while_it_ran(helper, tmp_path):
    folder = tmp_path / "library" / "Uncategorized" / "talk"
    folder.mkdir(parents=True)
    note = folder / "corpus.md"
    note.write_text("# A talk\n\n**Topic:** Uncategorized\n", encoding="utf-8")
    side = {"video_id": "vid00000001", "title": "A talk", "topic": "Uncategorized",
            "url": "https://www.youtube.com/watch?v=vid00000001"}
    (folder / "sidecar.json").write_text(json.dumps(side), encoding="utf-8")
    assert server._index_yoink(folder, side, note, folder / "sidecar.json")
    move("vid00000001", "Talks I liked")  # while the transcript was still running
    # The capture finishes: its transcript pass picked a shelf, and it writes.
    later = {**side, "topic": "AI and ML"}
    (folder / "sidecar.json").write_text(json.dumps(later), encoding="utf-8")
    assert server._index_yoink(folder, later, note, folder / "sidecar.json")
    assert topic(helper, "vid00000001") == "Talks I liked"
    assert shelf_router.files_topic(folder / "sidecar.json", note) == {
        "sidecar": "Talks I liked", "corpus": "Talks I liked"}


def test_the_users_own_pick_at_capture_replaces_a_hand_shelf(helper):
    vid = capture_page()
    move(vid, "Reading list")
    name, error = server._shelf_from_body({"shelf": "Bread"}, remember_url=PAGE)
    assert (name, error) == ("Bread", None)
    capture_page(topic=name)
    assert topic(helper, vid) == "Bread" and helper.shelf_hand_seq(vid) == 2
    # An import folder is not the user's pick for this capture.
    name, _ = server._shelf_from_body({"folder": "Imported"}, remember_url=PAGE)
    capture_page(topic=name)
    assert topic(helper, vid) == "Bread"


def test_a_rebuild_keeps_a_shelf_named_at_capture(helper, tmp_path):
    folder = tmp_path / "library" / "Bread" / "vid"
    folder.mkdir(parents=True)
    side = {"video_id": "vid00000002", "title": "Crumb", "topic": "Bread", "shelf_by_hand": True,
            "url": "https://www.youtube.com/watch?v=vid00000002"}
    (folder / "sidecar.json").write_text(json.dumps(side), encoding="utf-8")
    assert server._index_yoink(folder, side, None, folder / "sidecar.json")
    assert helper.shelf_hand_seq("vid00000002") == 1
    # Indexing the same sidecar again (a rescan) is not a new hand move.
    assert server._index_yoink(folder, side, None, folder / "sidecar.json")
    assert helper.shelf_hand_seq("vid00000002") == 1


def test_a_stale_tidy_suggestion_does_not_move_a_save_moved_since(helper):
    vid = capture_page()
    other = capture_page("https://example.com/notes/other", title="Other")
    move(vid, "Cooking")  # after Tidy proposed "Bread" for it on Uncategorized
    result = server._reshelve([(vid, "Bread"), (other, "Bread")], label="Tidy",
                              expect={vid: "Uncategorized", other: "Uncategorized"}, skip_by_hand=True)
    assert topic(helper, vid) == "Cooking"
    assert [s["video_id"] for s in result["skipped"]] == [vid]
    # A round trip back to Uncategorized by hand is still the user's choice.
    move(vid, "Uncategorized")
    server._reshelve([(vid, "Bread")], label="Tidy", expect={vid: "Uncategorized"}, skip_by_hand=True)
    assert topic(helper, vid) == "Uncategorized"
    assert vid not in {c["video_id"] for c in server._shelf_rows(helper, only_fallback=True)
                       if not c["by_hand"]}


def test_facets_classify_tidies_the_topic_and_keeps_a_hand_shelf(helper):
    vid = capture_page()
    handler = object.__new__(server.Handler)
    handler._require_token = lambda: True
    sent = []
    handler._send_json = lambda status, payload: sent.append((status, payload))
    handler._handle_facets_classify({"video_id": vid, "topic": "  AI/ML  notes "})
    status, data = sent[-1]
    assert status == 200 and data["facets"]["topic"] == "AI ML notes"
    assert topic(helper, vid) == "AI ML notes"
    assert helper.shelf_hand_seq(vid) == 0  # an agent's topic is not a hand move
    move(vid, "Mine")
    handler._handle_facets_classify({"video_id": vid, "topic": "Elsewhere"})
    status, data = sent[-1]
    assert status == 200 and data["topic_kept"] == "Mine" and topic(helper, vid) == "Mine"


# ---- P1-6: undo -------------------------------------------------------------

def test_undo_restores_the_first_state_when_a_batch_repeats_a_save(helper):
    vid = capture_page()
    first = server._reshelve([(vid, "A")], label="Move")
    server._reshelve([(vid, "B")], label="Move", append_to=first["batch_id"])
    assert topic(helper, vid) == "B"
    undo = server._shelf_undo(first["batch_id"])
    assert undo["restored"] == 2
    assert topic(helper, vid) == "Uncategorized" and helper.shelf_hand_seq(vid) == 0


def test_undo_never_overrides_a_newer_move_even_back_to_the_same_shelf(helper):
    vid = capture_page()
    tidy = server._reshelve([(vid, "Cooking")], label="Tidy")
    move(vid, "Baking")
    move(vid, "Cooking")
    undo = server._shelf_undo(tidy["batch_id"])
    assert undo["restored"] == 0 and undo["skipped"][0]["reason"].startswith("Moved again")
    assert topic(helper, vid) == "Cooking"


def test_the_dashboard_reads_the_last_undo_from_the_helper(helper):
    vid = capture_page()
    moved = server._reshelve([(vid, "Cooking")], label="Tidy")
    handler = object.__new__(server.Handler)
    handler._require_token = lambda: True
    handler._send_json = lambda status, payload: (status, payload)
    status, data = handler._handle_shelves_last_undo()
    assert status == 200 and data["undo"]["id"] == moved["batch_id"] and data["undo"]["count"] == 1
    assert data["fallback"] == "Uncategorized"


# ---- P1-3: a stopped move, the lock, the CLI --------------------------------

def test_a_move_that_stops_halfway_is_finished_from_the_log(helper, monkeypatch):
    ids = [capture_page(f"https://example.com/notes/{n}", title=f"Note {n}") for n in range(3)]
    real = server._shelf_sync_one
    calls = []

    def stop_after_one(row, shelf, by_hand):
        calls.append(row["video_id"])
        if len(calls) == 2:
            raise KeyboardInterrupt("power cut")
        return real(row, shelf, by_hand)
    monkeypatch.setattr(server, "_shelf_sync_one", stop_after_one)
    with pytest.raises(KeyboardInterrupt):
        server._reshelve([(vid, "Bread") for vid in ids], label="Move")
    monkeypatch.setattr(server, "_shelf_sync_one", real)
    # Two index rows moved, one sidecar is behind, and the batch is unfinished.
    assert [topic(helper, v) for v in ids] == ["Bread", "Bread", "Uncategorized"]
    assert shelf_router.unfinished_batches(server.DATA_ROOT)
    batch_id = server._shelf_recover()[0]
    assert not shelf_router.unfinished_batches(server.DATA_ROOT)
    assert [sidecar(helper, v)["topic"] for v in ids[:2]] == ["Bread", "Bread"]
    assert server._shelf_undo(batch_id)["restored"] == 2
    assert [topic(helper, v) for v in ids] == ["Uncategorized"] * 3


def test_a_file_that_cannot_be_written_is_reported(helper, monkeypatch):
    vid = capture_page()

    def refuse(*a, **k):
        raise PermissionError("locked by another program")
    monkeypatch.setattr(shelf_router, "sync_files", refuse)
    result = server._reshelve([(vid, "Bread")], label="Move")
    assert result["ok"] and result["files_not_updated"] == [vid]
    assert topic(helper, vid) == "Bread"


def _hold_lock(root, ready, release):
    import shelf_router as sr
    with sr.locked(root):
        ready.set()
        release.wait(20)


def test_the_move_log_lock_holds_across_processes(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=_hold_lock, args=(str(tmp_path), ready, release))
    proc.start()
    try:
        assert ready.wait(60)
        done = []

        def write():
            shelf_router.record_batch(tmp_path, [{"video_id": "a", "from": None, "to": "B"}])
            done.append(time.monotonic())
        import threading
        writer = threading.Thread(target=write)
        start = time.monotonic()
        writer.start()
        time.sleep(0.5)
        assert not done  # waiting for the other process
        release.set()
        writer.join(30)
        assert done and done[0] - start >= 0.5
    finally:
        release.set()
        proc.join(30)
    assert len(shelf_router.batches(tmp_path)) == 1


def test_the_cli_hands_moves_to_a_running_helper(helper, monkeypatch, capsys):
    import uoink_agent_runtime
    vid = capture_page()
    sent = []
    monkeypatch.setattr(cli, "backend", lambda: server)
    monkeypatch.setattr(uoink_agent_runtime, "helper_running", lambda backend: True)
    monkeypatch.setattr(cli, "_helper_shelves", lambda srv, path, body: sent.append((path, body)) or {
        "ok": True, "moved": len(body.get("moves") or []), "skipped": [], "moves": [], "batch_id": "mv_000000000001"})
    monkeypatch.setattr(server, "_reshelve", lambda *a, **k: pytest.fail("moved in the CLI process"))
    many = [vid] + [f"page_{n:011d}" for n in range(1200)]
    assert cli.main(["shelves", "move", "Bread", *many]) == 0
    capsys.readouterr()
    assert {path for path, _ in sent} == {"/library/shelves/apply"}
    assert len(sent) > 1 and all("append_to" in body for _, body in sent[1:])
    assert all(len(json.dumps(body).encode()) < 64 * 1024 for _, body in sent)
    assert cli.main(["shelves", "undo"]) == 0
    assert sent[-1][0] == "/library/shelves/undo"


# ---- P2-9 and P2-10 -----------------------------------------------------------

def test_case_and_unicode_spellings_land_on_one_shelf(helper):
    a = capture_page("https://example.com/a", title="A")
    b = capture_page("https://example.com/b", title="B")
    c = capture_page("https://example.com/c", title="C")
    move(a, "Café")
    server._reshelve([(b, unicodedata.normalize("NFD", "café"))], label="Move")
    server._reshelve([(c, "CAFÉ")], label="Move")
    assert {topic(helper, v) for v in (a, b, c)} == {"Café"}
    assert server._shelf_from_body({"shelf": "café"})[0] == "Café"


def test_the_move_log_stays_small(helper, monkeypatch):
    monkeypatch.setattr(shelf_router, "MAX_LOG_MOVES", 50)
    for n in range(8):
        shelf_router.record_batch(server.DATA_ROOT, [{"video_id": f"v{n}_{i}", "from": None, "to": "B"}
                                                     for i in range(20)])
    kept = shelf_router.batches(server.DATA_ROOT)
    assert sum(len(b["moves"]) for b in kept) <= 50 and len(kept) == 2
    shelf_router.mark_undone(server.DATA_ROOT, kept[-1]["id"])
    undone = shelf_router.batches(server.DATA_ROOT)[-1]
    assert undone["moves"] == [] and shelf_router.batch_summary(undone)["count"] == 20
    raw = shelf_router.move_log_path(server.DATA_ROOT).read_text(encoding="utf-8")
    assert "\n" not in raw and ", " not in raw  # compact JSON


# ---- P2-7: the helper sees a move made in another process ---------------------

def test_a_move_from_another_process_reaches_the_cached_library(helper, tmp_path):
    for n in range(3):
        vid = capture_page(f"https://example.com/n/{n}", title=f"Crumb {n}", text="sourdough crumb levain")
        move(vid, "Bread")
    first = server._shelf_library()
    assert server._shelf_library() is first  # cached
    other = index_mod.Index.open(tmp_path / "index.db")  # the CLI's own connection
    try:
        other.set_shelf(vid, "Baking", hand_seq=2)
    finally:
        other.close()
    fresh = server._shelf_library()
    assert fresh is not first and "Baking" in fresh.shelves


# ---- P2-13: x-article, capture --shelf on a save already shelved -------------

def test_x_article_refuses_a_bad_shelf_name_like_the_other_routes(helper):
    sent = []
    fake = SimpleNamespace(_send_json=lambda status, payload: sent.append((status, payload)))
    server.Handler._handle_extract_x_article(fake, {
        "url": "https://x.com/someone/article/1", "title": "t", "markdown": "m", "shelf": "CON"})
    assert sent and sent[0][0] == 400 and not sent[0][1]["ok"]
    assert shelf_router.hint_for(server.DATA_ROOT, "https://x.com/someone/article/1") is None


def test_capture_shelf_moves_a_save_already_on_a_hand_shelf(helper):
    video = "https://www.youtube.com/watch?v=abcdefghijk"
    vid = capture_page(video)
    move(vid, "Bread")
    record = {**helper.get_yoink(vid), "topic": "Baking"}
    # A re-capture with no shelf named keeps the user's shelf.
    helper.upsert_yoink(record, content="crumb")
    assert topic(helper, vid) == "Bread"
    # `uoink capture URL --shelf Baking` writes a hint the user named, and
    # the capture that follows is that user's pick.
    shelf_router.remember_hints(server.DATA_ROOT, [(video, "Baking")], by_hand=True)
    assert server._explicit_shelf_hint({}, video) == "Baking"
    helper.upsert_yoink(record, content="crumb")
    assert topic(helper, vid) == "Baking" and helper.shelf_hand_seq(vid) == 2
    # An import folder is never the user's pick.
    shelf_router.remember_hints(server.DATA_ROOT, [(video, "Watch later")])
    assert server._explicit_shelf_hint({}, video) is None


def test_capture_shelf_from_the_cli_is_the_users_pick(tmp_path):
    fake = SimpleNamespace(DATA_ROOT=tmp_path, _classify_capture_url=lambda url: {
        "ok": True, "source": "youtube_video", "canonical": "https://www.youtube.com/watch?v=abcdefghijk"})
    cli.friendly_call(cli.parser().parse_args(["capture", "https://youtu.be/abcdefghijk", "--shelf", "Baking"]), fake)
    entry = shelf_router.hint_entry(tmp_path, "https://www.youtube.com/watch?v=abcdefghijk")
    assert entry == {"shelf": "Baking", "by_hand": True}
