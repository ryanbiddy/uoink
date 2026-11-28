"""Pinned moments on an isolated index. All acquisitions are fixtures."""
import contextlib
import json
import subprocess
from unittest.mock import patch

import pytest

import index
import moments
import server
import uoink_cli
import uoink_mcp_tools as tools

VID = "loom0000001"
URL = "https://www.youtube.com/watch?v=" + VID


@pytest.fixture
def library(tmp_path, monkeypatch):
    idx = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_get_existing_index", lambda **kwargs: idx)
    monkeypatch.setattr(server, "INDEX_PATH", idx._path)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(tools, "_b", lambda: server)
    yield idx
    idx.close()


def seed(idx, video_id=VID):
    url = "https://www.youtube.com/watch?v=" + video_id
    folder = idx._path.parent / video_id
    folder.mkdir(exist_ok=True)
    corpus = folder / f"{video_id}.md"
    sidecar = folder / f"{video_id}.json"
    corpus.write_text("# Handloom\n\n## Transcript\n\nWatch the shuttle.", encoding="utf-8")
    sidecar.write_text(json.dumps({"video_id": video_id, "url": url, "platform": "youtube"}))
    idx.upsert_yoink(dict(video_id=video_id, slug=video_id, title="Handloom", platform="youtube",
                          source_type="video", yoinked_at="2026-11-26", corpus_path=str(corpus),
                          metadata_json=json.dumps({"url": url}), sidecar_path=str(sidecar)),
                     content="Watch the shuttle.")


def add_cues(idx, video_id=VID):
    url = "https://www.youtube.com/watch?v=" + video_id
    cues = [(0, 2, "Opening."), (50.5, 58, "Watch the shuttle."), (110, 115, "The thread."),
            (147, 155, "Outside the window.")]
    idx.insert_citations(video_id, [
        dict(seq=i, kind="transcript_chunk", timestamp_start=start, timestamp_end=end,
             text=text, source_url=url, source_deep_link=url + f"&t={int(end)}s")
        for i, (start, end, text) in enumerate(cues)])


@pytest.mark.parametrize(("raw", "expected"), [
    ("", None), ("?t=0", 0), ("?start=8", 8), ("?t=1h2m3s", 3723),
    ("?t=-1", None), ("?t=nope", None), ("?t=9999999999999", None)])
def test_explicit_url_times(raw, expected):
    assert moments.requested_time("https://youtu.be/" + VID + raw) == expected


def test_link_uses_line_start_is_idempotent_and_leaves_coordinates_alone():
    link = moments.citation_link(URL + "&start=90&t=100#comment", 50.9, youtube=True)
    assert link == URL + "&t=48s"
    assert moments.cited_url(link, 50.9) == link
    assert moments.citation_link("https://audio.example.test/track#old", 1.9).endswith("#t=0")
    label = "### [00:00:50.900–00:01:03.000]"
    doc = "## Transcript\n\n" + label + "(" + URL + "&t=63s)"
    notes = "\n## Notes\n" + label + "(" + URL + "&t=63s)"
    assert moments.export_links(doc + notes) == "## Transcript\n\n" + label + "(" + link + ")" + notes


def test_storage_survives_reopen_refresh_and_late_transcript(library):
    seed(library)
    moments.add(library, VID, 100)
    waiting, = library.get_pins(VID)
    assert waiting["transcript_ready"] is False and waiting["deep_link"].endswith("&t=100s")
    add_cues(library)
    seed(library)
    with contextlib.closing(index.Index.open(library._path)) as reopened:
        pin, = reopened.get_pins(VID)
        assert pin["seconds"] == 100 and pin["pinned_at"] and pin["note"] is None
        assert [line["start"] for line in pin["lines"]] == [50.5, 110]
        assert pin["deep_link"].endswith("&t=98s")  # the pin itself, 2 s early
        moments.add(reopened, VID, 100)
    assert library.get_pins(VID) == [pin]
    for n in range(20):
        moments.add(library, VID, n)
    assert [p["seconds"] for p in library.get_pins(VID)] == list(range(20))
    moments.remove(library, VID, 7)
    assert len(library.get_pins(VID)) == 19


def test_save_again_skips_acquisition_and_keeps_time_local(library, monkeypatch):
    class Probe:
        _validate_url_interval = server.Handler._validate_url_interval
        def _send_json(self, status, data):
            assert status == 200
            self.response = data
            return data

    @contextlib.contextmanager
    def ownership(url):
        yield server._ManualOwnership()

    def acquire(url, interval, folder, **kwargs):
        assert url == URL
        seed(library)
        return {"ok": True, "screenshot_count": 0, "folder": str(folder)}

    monkeypatch.setattr(server, "_manual_extraction_ownership", ownership)
    monkeypatch.setattr(server, "_record_single_extract_job", lambda *a, **k: None)
    monkeypatch.setattr(server, "_route_topic", lambda *a, **k: "Craft")
    with patch.object(server, "_fetch_metadata", return_value={"id": VID, "title": "Handloom"}) as fetch, \
         patch.object(server, "_run_extraction", side_effect=acquire) as capture:
        handler = Probe()
        for t in (8, 872, 872):
            server.Handler._handle_extract(handler, {"url": URL + f"&t={t}s"})
            assert handler.response["pinned_seconds"] == t
        fetch.assert_called_once_with(URL)
        assert capture.call_count == 1
    assert [p["seconds"] for p in library.get_pins(VID)] == [8, 872]


def test_pins_are_available_even_if_sidecar_exceeds_reader_limit(library, monkeypatch):
    seed(library)
    add_cues(library)
    moments.add(library, VID, 56)
    monkeypatch.setattr(server, "MAX_SIDECAR_BYTES", 12)
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = lambda status, data: (status, data)
    status, result = handler._handle_yoink_details(f"/yoinks/{VID}/details")
    assert status == 400 and result["error"] == "sidecar file too large"
    assert result["pins"] == library.get_pins(VID)


def test_saved_session_member_gets_another_pin_without_a_second_capture(library, monkeypatch):
    seed(library)
    moments.add(library, VID, 25)
    session = {"status": "open", "videos": [{"url": URL}]}
    monkeypatch.setattr(server, "_read_session", lambda sid: session)
    monkeypatch.setattr(server, "_session_folder", lambda sid: library._path.parent)
    owner = server._ManualOwnership()
    owner.already_captured = VID
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda url: contextlib.nullcontext(owner))
    handler = server.Handler.__new__(server.Handler)
    handler._validate_session_id = lambda body: ("craft", None)
    handler._send_json = lambda status, data: (status, data)
    with patch.object(server, "_run_extraction") as capture:
        status, result = handler._handle_session_add({"session_id": "craft", "url": URL + "&t=225s"})
        capture.assert_not_called()
    assert status == 200 and result["video_count"] == 1 and result["pinned_seconds"] == 225
    assert [p["seconds"] for p in library.get_pins(VID)] == [25, 225]


def test_queued_pin_follows_completed_item_and_cancel_clears_it(library):
    pending_id = library.enqueue_pending(URL, 30, "2026-11-27")
    moments.add(library, VID, 9, pending_id=pending_id)
    assert moments.pending_capture(library, URL)["pending_id"] == pending_id
    assert library.cancel_pending(pending_id)
    moments.add(library, VID, 11, pending_id=pending_id)
    assert not library.get_pins(VID)
    pending_id = library.enqueue_pending(URL, 30, "2026-11-27")
    moments.add(library, VID, 12, pending_id=pending_id)
    seed(library)
    moments.add(library, VID, 30, pending_id=pending_id)
    with library._conn as db:
        db.execute("DELETE FROM pending_yoinks WHERE pending_id=?", (pending_id,))
    assert [p["seconds"] for p in library.get_pins(VID)] == [12, 30]


def test_repin_at_capacity_keeps_the_requested_second(library):
    seed(library)
    for second in range(20):
        moments.add(library, VID, second)
    with library._conn as db:
        db.execute("UPDATE item_moments SET note='Opening' WHERE video_id=? AND seconds=0", (VID,))
    oldest, *others = library.get_pins(VID)
    assert moments.add(library, VID, 0) == {"pinned_seconds": 0}
    assert library.get_pins(VID) == [oldest, *others]
    moments.add(library, VID, 20)
    pins = library.get_pins(VID)
    assert [pin["seconds"] for pin in pins] == [0, *range(2, 21)]
    assert pins[0] == oldest


@pytest.mark.parametrize("cancelled", [False, True], ids=["missing", "cancelled"])
def test_unstored_pending_pin_is_not_reported(library, cancelled):
    pending_id = 42
    if cancelled:
        pending_id = library.enqueue_pending(URL, 30, "2026-11-27")
        assert library.cancel_pending(pending_id)
    assert moments.add(library, VID, 0, pending_id=pending_id) == {}
    assert library.get_pins(VID) == []


@pytest.mark.parametrize("path", ["already_queued", "live", "429"])
def test_queued_extract_acknowledges_the_stored_pin(library, monkeypatch, path):
    owner = server._ManualOwnership()
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda url: contextlib.nullcontext(owner))
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    if path == "already_queued":
        library.enqueue_pending(URL, 30, "2026-11-27")

    def metadata(url):
        assert url == URL
        if path == "429":
            raise subprocess.CalledProcessError(1, ["yt-dlp"], stderr="ERROR: unable to download video data: HTTP Error 429")
        assert path == "live"
        return {"id": VID, "live_status": "is_live"}

    monkeypatch.setattr(server, "_fetch_metadata", metadata)
    handler = server.Handler.__new__(server.Handler)
    replies = []
    handler._send_json = lambda status, data: replies.append((status, data))
    handler._handle_extract({"url": URL + "&t=872s"})
    (status, response), = replies
    assert status == 200 and response["queued"]
    assert response["pending_id"] == moments.pending_capture(library, URL)["pending_id"]
    if path != "already_queued":
        assert response["reason"] == ("live_stream" if path == "live" else "youtube_rate_limit")
    assert [pin["seconds"] for pin in library.get_pins(VID)] == [872]
    assert response["pinned_seconds"] == 872


@pytest.mark.parametrize("failed_read", ["get_pins", "get_citations"])
def test_corpus_loads_pins_and_citations_independently(library, monkeypatch, failed_read):
    seed(library)
    add_cues(library)
    moments.add(library, VID, 56)
    baseline = tools.call_tool("get_uoink_corpus", {"slug": VID})
    assert baseline["pins"] and baseline["citations"]

    def unavailable(video_id):
        raise RuntimeError("read unavailable")

    monkeypatch.setattr(library, failed_read, unavailable)
    result = tools.call_tool("get_uoink_corpus", {"slug": VID})
    assert result["ok"] and result["corpus_md"] == baseline["corpus_md"]
    for field in ("pins", "citations"):
        assert result[field] == ([] if failed_read == "get_" + field else baseline[field])


def test_pinned_window_breaks_keyword_tie(library):
    for video_id in (VID, "loom0000002"):
        seed(library, video_id)
        add_cues(library, video_id)

    def hits():
        response = tools.call_tool("search_library", {"query": "shuttle", "mode": "keyword", "match": "forgiving"})
        assert response["ok"], response
        return [(hit["item_id"], hit["start"]) for hit in response["hits"]]

    first, second = hits()
    assert second[1] is not None
    moments.add(library, second[0], 950)
    assert hits() == [first, second]
    moments.add(library, second[0], 65)
    assert hits() == [second, first]


def test_agent_and_cli_outputs(library, monkeypatch, capsys):
    seed(library)
    add_cues(library)
    moments.add(library, VID, 56)
    pin, = library.get_pins(VID)
    for name, args, key in [
        ("get_library_item", {"video_id": VID}, None),
        ("get_evidence_card", {"video_id": VID}, None),
        ("get_uoink_corpus", {"slug": VID}, None),
        ("search_library", {"query": "shuttle"}, "hits"),
        ("search_uoinks", {"query": "shuttle"}, "results"),
        ("search_clips", {"query": "shuttle"}, "results"),
    ]:
        response = tools.call_tool(name, args)
        assert response["ok"], response
        row = response[key][0] if key else response
        assert row["pins"] == [pin]
    monkeypatch.setattr(uoink_cli, "backend", lambda: server)
    assert uoink_cli.main(["get", VID]) == 0
    assert json.loads(capsys.readouterr().out)["pins"] == [pin]
    assert uoink_cli.main(["get", VID, "--text"]) == 0
    text = capsys.readouterr().out
    assert "Pinned 0:56" in text and pin["deep_link"] in text and "Watch the shuttle." in text
