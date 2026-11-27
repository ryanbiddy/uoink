"""Timed cues read contract (uoink.cues.read v1) over synthetic saves.

Fixtures cover each timing source: uploaded captions, automatic captions,
local ASR on a video (with word timings) and a locally transcribed podcast
episode with attributed speakers. Also the HTTP routes, the OpenAPI
document, `uoink cues`, and a byte-for-byte check that corpus read v1
answers the same once these new sidecar fields exist.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import corpus_contract  # noqa: E402
import index as index_mod  # noqa: E402
import regenerate_corpus_contract_v1_fixture as regenerate  # noqa: E402
import server  # noqa: E402
import timed_cues  # noqa: E402
import uoink_cli as cli  # noqa: E402

SHOW = "The Tidepool Hour"


def _seg(start, end, text, video_id="tpcaptions1"):
    link = f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s"
    return {"start": start, "end": end, "text": text, "source_url": None,
            "source_deep_link": link, "youtube_deep_link": link}


ITEMS = {
    "tpcaptions1": {
        "row": {"channel": SHOW, "title": "Captions episode", "yoinked_at": "2026-11-02T09:00:00",
                "meta": {"url": "https://www.youtube.com/watch?v=tpcaptions1", "duration_seconds": 95,
                         "platform": "youtube", "published_at": "2025-03-04T15:00:00Z"}},
        "sidecar": {"title": "Captions episode", "url": "https://www.youtube.com/watch?v=tpcaptions1",
                    "duration_seconds": 95, "upload_date": "20250304",
                    "published_at": "2025-03-04T15:00:00Z", "description": "Tide tables, read aloud.",
                    "transcript_source": "captions", "caption_kind": "captions",
                    "transcript": [_seg(30.0, 34.5, "Low tide at noon."),
                                   _seg(0.0, 4.25, "Welcome back to the pool."),
                                   _seg(4.25, 9.0, "Today: anemones.")]},
    },
    "tpautocaps01": {
        "row": {"channel": SHOW, "title": "Auto captions episode", "yoinked_at": "2026-11-03T09:00:00",
                "meta": {"url": "https://www.youtube.com/watch?v=tpautocaps01", "duration_seconds": 60,
                         "platform": "youtube", "upload_date": "20240110"}},
        "sidecar": {"title": "Auto captions episode", "upload_date": "20240110",
                    "url": "https://www.youtube.com/watch?v=tpautocaps01",
                    "transcript_source": "captions", "caption_kind": "auto_captions",
                    "transcript": [_seg(1.0, 2.0, "uh so crabs", "tpautocaps01")]},
    },
    "tpasrvideo1": {
        "row": {"channel": "Other Show", "title": "ASR episode", "yoinked_at": "2026-11-04T09:00:00",
                "meta": {"url": "https://www.youtube.com/watch?v=tpasrvideo1", "duration_seconds": 12,
                         "platform": "youtube", "published_at": "2023-06-01T00:00:00Z"}},
        "sidecar": {"title": "ASR episode", "url": "https://www.youtube.com/watch?v=tpasrvideo1",
                    "published_at": "2023-06-01T00:00:00Z", "transcript_source": "asr",
                    "transcript": [{"start": 0.0, "end": 2.0, "text": "Hello reef",
                                    "words": [{"word": "Hello", "start": 0.0, "end": 0.6},
                                              {"word": "reef", "start": 0.7, "end": 1.4}]},
                                   [2.0, 5.5, "No word timings here."]]},
    },
    "tppodcast01": {
        "row": {"channel": SHOW, "title": "Podcast episode", "yoinked_at": "2026-11-05T09:00:00",
                "source_type": "episode", "platform": "podcast",
                "meta": {"url": "https://tidepool.example.com/ep/1", "platform": "podcast",
                         "upload_date": "Mon, 03 Mar 2025 10:00:00 +0000"}},
        "sidecar": {"episode_title": "Podcast episode", "source_type": "episode",
                    "source_url": "https://tidepool.example.com/ep/1",
                    "published_at": "Mon, 03 Mar 2025 10:00:00 +0000", "transcript_model": "small",
                    "transcript": [{"start": 0.0, "end": 3.0, "text": "I'm the host.",
                                    "speaker": "Host", "speaker_provenance": {"method": "fixture"}},
                                   {"start": 3.0, "end": 6.0, "text": "And I'm the guest.",
                                    "speaker": "SPEAKER_01"}]},
    },
    "tpoldcaps01": {
        "row": {"channel": "Other Show", "title": "Older captions save", "yoinked_at": "2026-01-05T09:00:00",
                "meta": {"url": "https://www.youtube.com/watch?v=tpoldcaps01", "platform": "youtube"}},
        "sidecar": {"title": "Older captions save", "transcript_source": "captions",
                    "transcript": [_seg(0.0, 1.0, "Saved before caption kinds.", "tpoldcaps01")]},
    },
}


def _build(root: Path):
    idx = index_mod.Index.open(root / "index.db")
    for video_id, spec in ITEMS.items():
        folder = root / "saves" / video_id
        folder.mkdir(parents=True)
        sidecar_path = folder / f"{video_id}.json"
        sidecar_path.write_text(json.dumps(spec["sidecar"]), encoding="utf-8")
        corpus = folder / f"{video_id}.md"
        corpus.write_text(f"# {spec['row']['title']}\n", encoding="utf-8")
        row = spec["row"]
        idx.upsert_yoink({
            "video_id": video_id, "slug": video_id, "channel": row["channel"], "title": row["title"],
            "topic": "Tides", "yoinked_at": row["yoinked_at"], "corpus_path": str(corpus),
            "sidecar_path": str(sidecar_path), "metadata_json": json.dumps(row["meta"]),
            "source_type": row.get("source_type", "youtube"), "platform": row.get("platform", "youtube"),
            "author": row["channel"],
        }, content=" ".join(seg["text"] if isinstance(seg, dict) else seg[2]
                            for seg in spec["sidecar"]["transcript"]))
    return idx


@pytest.fixture
def idx(tmp_path):
    index = _build(tmp_path)
    try:
        yield index
    finally:
        index.close()


# ---------------------------------------------------------------------------
# One item
# ---------------------------------------------------------------------------

def test_uploaded_captions(idx):
    data = timed_cues.get_item(idx, "tpcaptions1")
    assert data["timing"] == {"source": "captions", "caption_kind_known": True, "word_timings": False}
    assert [c["start"] for c in data["cues"]] == [0.0, 4.25, 30.0]
    assert data["cues"][0] == {"start": 0.0, "end": 4.25, "text": "Welcome back to the pool.",
                               "deep_link": "https://www.youtube.com/watch?v=tpcaptions1&t=0s"}
    assert data["cue_count"] == 3
    item = data["item"]
    assert item["published_at"] == "2025-03-04T15:00:00Z"
    assert item["captured_at"] == "2026-11-02T09:00:00"
    assert item["duration_seconds"] == 95
    assert item["source_url"] == "https://www.youtube.com/watch?v=tpcaptions1"
    assert item["description"] == "Tide tables, read aloud."
    assert item["channel"] == SHOW


def test_automatic_captions(idx):
    data = timed_cues.get_item(idx, "tpautocaps01")
    assert data["timing"]["source"] == "auto_captions"
    assert data["cues"] == [{"start": 1.0, "end": 2.0, "text": "uh so crabs",
                             "deep_link": "https://www.youtube.com/watch?v=tpautocaps01&t=0s"}]
    assert data["item"]["published_at"] == "2024-01-10"     # from yt-dlp's YYYYMMDD


def test_local_asr_with_word_timings(idx):
    data = timed_cues.get_item(idx, "tpasrvideo1")
    assert data["timing"] == {"source": "local_asr", "caption_kind_known": True, "word_timings": True}
    assert data["cues"] == [
        {"start": 0.0, "end": 2.0, "text": "Hello reef",
         "words": [{"start": 0.0, "end": 0.6, "text": "Hello"}, {"start": 0.7, "end": 1.4, "text": "reef"}]},
        {"start": 2.0, "end": 5.5, "text": "No word timings here."},
    ]


def test_podcast_episode_asr_and_speakers(idx):
    data = timed_cues.get_item(idx, "tppodcast01")
    assert data["timing"]["source"] == "local_asr"
    assert data["item"]["published_at"] == "2025-03-03"
    assert data["item"]["title"] == "Podcast episode"
    assert data["item"]["source_url"] == "https://tidepool.example.com/ep/1"
    # Only a speaker with provenance is passed on as a fact.
    assert data["cues"][0]["speaker"] == "Host"
    assert "speaker" not in data["cues"][1]


def test_older_captions_say_the_kind_is_unknown(idx):
    timing = timed_cues.get_item(idx, "tpoldcaps01")["timing"]
    assert timing == {"source": "captions", "caption_kind_known": False, "word_timings": False}
    assert timed_cues.get_item(idx, "tpoldcaps01")["item"]["published_at"] is None


def test_time_window(idx):
    data = timed_cues.get_item(idx, "tpcaptions1", {"start": ["4"], "end": ["8"]})
    assert [c["text"] for c in data["cues"]] == ["Welcome back to the pool.", "Today: anemones."]
    assert data["range"] == {"start": 4.0, "end": 8.0}


@pytest.mark.parametrize("item_id, query, code, status", [
    ("tpcaptions1", {"surprise": ["1"]}, "invalid_request", 400),
    ("tpcaptions1", {"start": ["9"], "end": ["2"]}, "invalid_request", 400),
    ("tpcaptions1", {"start": ["-1"]}, "invalid_request", 400),
    ("tpcaptions1", {"start": ["1", "2"]}, "invalid_request", 400),
    ("", {}, "invalid_request", 400),
    ("missing-item", {}, "not_found", 404),
])
def test_item_errors(idx, item_id, query, code, status):
    with pytest.raises(timed_cues.CuesError) as raised:
        timed_cues.get_item(idx, item_id, query)
    assert (raised.value.code, raised.value.status) == (code, status)


def _sidecar_item(tmp_path, idx, video_id, sidecar, meta=None):
    folder = tmp_path / "extra" / re.sub(r"[^A-Za-z0-9]", "_", video_id)
    folder.mkdir(parents=True)
    path = folder / "item.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    idx.upsert_yoink({"video_id": video_id, "slug": folder.name, "channel": SHOW, "title": video_id,
                      "topic": "Tides", "yoinked_at": "2026-11-06T09:00:00", "corpus_path": str(folder / "item.md"),
                      "sidecar_path": str(path), "metadata_json": json.dumps(meta or {}),
                      "source_type": "youtube", "platform": "youtube"}, content="extra")


def test_word_timings_are_never_backwards_and_only_count_when_valid(tmp_path, idx):
    _sidecar_item(tmp_path, idx, "tpwordbad01", {"transcript_source": "asr", "transcript": [
        {"start": 0.0, "end": 3.0, "text": "Tide pool",
         "words": [{"word": "pool", "start": 1.0, "end": 0.4}, {"word": "Tide", "start": 0.2, "end": 0.9}]}]})
    _sidecar_item(tmp_path, idx, "tpwordjunk1", {"transcript_source": "asr", "transcript": [
        {"start": 0.0, "end": 3.0, "text": "Tide pool", "words": [{"start": "soon"}, "pool", {"word": " "}]}]})
    data = timed_cues.get_item(idx, "tpwordbad01")
    assert data["cues"][0]["words"] == [{"start": 0.2, "end": 0.9, "text": "Tide"},
                                        {"start": 1.0, "end": 1.0, "text": "pool"}]
    junk = timed_cues.get_item(idx, "tpwordjunk1")
    assert "words" not in junk["cues"][0]
    assert junk["timing"]["word_timings"] is False


def test_item_cues_come_in_pages_and_words_can_be_left_out(tmp_path, idx):
    transcript = [{"start": float(i), "end": i + 0.9, "text": f"Line {i}",
                   "words": [{"word": "Line", "start": float(i), "end": i + 0.4}]} for i in range(12)]
    _sidecar_item(tmp_path, idx, "tplongasr01", {"transcript_source": "asr", "transcript": transcript})
    first = timed_cues.get_item(idx, "tplongasr01", {"limit": ["5"]})
    assert [c["text"] for c in first["cues"]] == [f"Line {i}" for i in range(5)]
    assert first["cue_count"] == 5
    assert first["page"] == {"limit": 5, "offset": 0, "total": 12, "next_offset": 5}
    last = timed_cues.get_item(idx, "tplongasr01", {"limit": ["5"], "offset": ["10"]})
    assert [c["text"] for c in last["cues"]] == ["Line 10", "Line 11"]
    assert last["page"]["next_offset"] is None
    window = timed_cues.get_item(idx, "tplongasr01", {"start": ["3"], "end": ["6"], "limit": ["2"]})
    assert [c["text"] for c in window["cues"]] == ["Line 3", "Line 4"]
    assert window["page"]["total"] == 4                 # 3, 4, 5 and 6 overlap the window
    bare = timed_cues.get_item(idx, "tplongasr01", {"include_words": ["0"]})
    assert not any("words" in c for c in bare["cues"]) and bare["timing"]["word_timings"] is True
    default = timed_cues.get_item(idx, "tplongasr01")
    assert default["page"]["limit"] == timed_cues.CUE_DEFAULT_LIMIT and len(default["cues"]) == 12
    for query in ({"limit": ["0"]}, {"limit": [str(timed_cues.CUE_MAX_LIMIT + 1)]}, {"offset": ["-1"]},
                  {"limit": ["lots"]}, {"include_words": ["maybe"]}):
        with pytest.raises(timed_cues.CuesError) as raised:
            timed_cues.get_item(idx, "tplongasr01", query)
        assert raised.value.status == 400


def test_odd_ids_are_quoted_and_zero_durations_kept(tmp_path, idx):
    _sidecar_item(tmp_path, idx, "tp odd/id?x", {"duration_seconds": 0, "transcript": []},
                  meta={"duration_seconds": 0})
    ref = next(i for i in timed_cues.search(idx, {"q": ["extra"]})["items"] if i["id"] == "tp odd/id?x")
    assert ref["cues_url"] == "/api/cues/v1/items/tp%20odd%2Fid%3Fx"
    assert ref["duration_seconds"] == 0.0
    row = idx.get_yoink("tp odd/id?x")
    assert timed_cues.item_of(row, {})["duration_seconds"] == 0.0
    bare_row = {"video_id": "tpzerolen01", "metadata_json": "{}"}
    assert timed_cues.item_of(bare_row, {"duration_seconds": 0})["duration_seconds"] == 0.0


@pytest.mark.parametrize("path, status", [
    ("/api/cues/v1/items/..", 404),
    ("/api/cues/v1/items/..%2F..%2Fsecrets", 400),
    ("/api/cues/v1/items/tpcaptions1%2F..", 400),
    ("/api/cues/v1/items/..%5C..%5Cindex.db", 404),
    ("/api/cues/v1/items/%00", 404),
])
def test_http_ids_never_reach_a_path(http, path, status):
    got, raw = _get(http, path)
    assert got == status
    assert "sidecar_path" not in raw.decode() and "\\\\" not in raw.decode()


# ---------------------------------------------------------------------------
# Lists by show and publish date
# ---------------------------------------------------------------------------

def _ids(data):
    return [item["id"] for item in data["items"]]


def test_list_by_show_and_publish_date(idx):
    show = timed_cues.search(idx, {"channel": [SHOW]})
    assert set(_ids(show)) == {"tpcaptions1", "tpautocaps01", "tppodcast01"}
    assert show["page"]["total"] == 3
    in_2025 = timed_cues.search(idx, {"channel": [SHOW], "published_from": ["2025-01-01"],
                                      "published_to": ["2025-12-31"]})
    assert set(_ids(in_2025)) == {"tpcaptions1", "tppodcast01"}
    march_4 = timed_cues.search(idx, {"published_from": ["2025-03-04"], "published_to": ["2025-03-04"]})
    assert _ids(march_4) == ["tpcaptions1"]
    ref = march_4["items"][0]
    assert ref["cues_url"] == "/api/cues/v1/items/tpcaptions1"
    assert ref["published_at"] == "2025-03-04T15:00:00Z"
    # Items with no known publish date never match a publish range.
    older = timed_cues.search(idx, {"published_to": ["2030-01-01"]})
    assert "tpoldcaps01" not in _ids(older) and len(_ids(older)) == 4


def test_list_paging_and_words(idx):
    page = timed_cues.search(idx, {"limit": ["2"]})
    assert len(page["items"]) == 2 and page["page"]["next_offset"] == 2
    assert timed_cues.search(idx, {"q": ["anemones"]})["items"][0]["id"] == "tpcaptions1"


@pytest.mark.parametrize("query", [
    {"published_from": ["2025-13-01"]},
    {"published_from": ["2025-02-01"], "published_to": ["2025-01-01"]},
    {"limit": ["0"]},
    {"limit": ["many"]},
    {"surprise": ["1"]},
])
def test_list_errors(idx, query):
    with pytest.raises(timed_cues.CuesError) as raised:
        timed_cues.search(idx, query)
    assert raised.value.code == "invalid_request"


# ---------------------------------------------------------------------------
# HTTP, OpenAPI and the CLI
# ---------------------------------------------------------------------------

class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def _get(port, path, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


@pytest.fixture
def http(idx, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield int(httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_routes(http):
    status, raw = _get(http, "/api/cues/v1/items/tpcaptions1?start=0&end=5")
    payload = json.loads(raw)
    assert status == 200
    assert payload["contract"] == "uoink.cues.read" and payload["version"] == 1
    assert payload["operation"] == "get"
    assert [c["text"] for c in payload["data"]["cues"]] == ["Welcome back to the pool.", "Today: anemones."]
    assert "sidecar_path" not in raw.decode() and "corpus_path" not in raw.decode()

    status, raw = _get(http, f"/api/cues/v1/items?channel={SHOW.replace(' ', '%20')}"
                             "&published_from=2025-01-01")
    assert status == 200
    assert set(_ids(json.loads(raw)["data"])) == {"tpcaptions1", "tppodcast01"}

    status, raw = _get(http, "/api/cues/v1/items/missing")
    assert status == 404 and json.loads(raw)["error"]["code"] == "not_found"
    status, raw = _get(http, "/api/cues/v1/items?bogus=1")
    assert status == 400 and json.loads(raw)["error"]["code"] == "invalid_request"
    status, _raw = _get(http, "/api/cues/v1/items/tpcaptions1", token=False)
    assert status in (401, 403)


def test_openapi_lists_the_cue_reads(http):
    import uoink_mcp_tools
    status, raw = _get(http, "/openapi/v1/spec.json")
    spec = json.loads(raw)
    assert status == 200
    get_one = spec["paths"]["/api/cues/v1/items/{id}"]["get"]
    assert get_one["operationId"] == "get_timed_cues"
    assert spec["paths"]["/api/cues/v1/items"]["get"]["operationId"] == "list_timed_cue_items"
    tool_paths = [p for p in spec["paths"] if p.startswith("/tools/")]
    assert len(tool_paths) == len(uoink_mcp_tools.TOOL_REGISTRY)
    assert len(spec["paths"]) == len(uoink_mcp_tools.TOOL_REGISTRY) + 2


def test_cli_cues(idx, monkeypatch, capsys):
    monkeypatch.setattr(cli, "backend", lambda: SimpleNamespace(_get_index=lambda: idx))
    assert cli.main(["cues", "tpautocaps01"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == timed_cues.envelope("get", timed_cues.get_item(idx, "tpautocaps01"))

    assert cli.main(["cues", "tpcaptions1", "--start", "4", "--end", "8", "--text"]) == 0
    text = capsys.readouterr().out
    assert "Timing: uploaded captions | 2 cues" in text
    assert "Published: 2025-03-04T15:00:00Z" in text

    assert cli.main(["cues", "--channel", SHOW, "--from", "2025-01-01"]) == 0
    assert set(_ids(json.loads(capsys.readouterr().out)["data"])) == {"tpcaptions1", "tppodcast01"}

    assert cli.main(["cues", "missing"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_found"
    assert cli.main(["cues", "tpcaptions1", "--channel", SHOW]) == 2
    assert cli.main(["cues", "--start", "3"]) == 2


def test_cli_cues_pages_with_offset(idx, monkeypatch, capsys):
    monkeypatch.setattr(cli, "backend", lambda: SimpleNamespace(_get_index=lambda: idx))
    assert cli.main(["cues", "--limit", "2"]) == 0
    first = json.loads(capsys.readouterr().out)["data"]
    assert first["page"]["next_offset"] == 2
    assert cli.main(["cues", "--limit", "2", "--offset", "2"]) == 0
    second = json.loads(capsys.readouterr().out)["data"]
    assert second["page"]["offset"] == 2
    assert not set(_ids(first)) & set(_ids(second))
    assert cli.main(["cues", "--limit", "2", "--text"]) == 0
    assert "More items: add --offset 2." in capsys.readouterr().out
    assert cli.main(["cues", "tpcaptions1", "--limit", "1", "--offset", "1"]) == 0
    one = json.loads(capsys.readouterr().out)["data"]
    assert [c["text"] for c in one["cues"]] == ["Today: anemones."] and one["page"]["next_offset"] == 2


# ---------------------------------------------------------------------------
# Corpus read v1 stays byte-for-byte the same
# ---------------------------------------------------------------------------

def _v1_bytes(port):
    out = {}
    for path in ("/api/corpus/v1/items/video-contract", "/api/corpus/v1/search?limit=20",
                 "/api/corpus/v1/search?q=saved%20hour&limit=10", "/api/corpus/v1/facets"):
        status, raw = _get(port, path)
        assert status == 200
        out[path] = raw
    return out


def test_corpus_v1_unchanged_by_new_fields(tmp_path, monkeypatch):
    idx, _provider = regenerate.build_provider(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = int(httpd.server_address[1])
    try:
        before = _v1_bytes(port)
        # What a 3.18 save adds: publish date, description, caption kind and
        # timed cues in the sidecar, and the publish date in the index row.
        row = idx.get_yoink("video-contract")
        sidecar_path = Path(row["sidecar_path"])
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar.update(published_at="2029-12-31T08:00:00Z", description="A new field.",
                       caption_kind="auto_captions", transcript_source="captions",
                       transcript=[_seg(0.0, 2.0, "saved hour", "video-contract")])
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        meta = json.loads(row["metadata_json"])
        meta["published_at"] = "2029-12-31T08:00:00Z"
        with idx._lock:
            idx._conn.execute("UPDATE yoinks SET metadata_json=? WHERE video_id=?",
                              (json.dumps(meta), "video-contract"))
            idx._conn.commit()
        after = _v1_bytes(port)
        assert after == before
        # And the new read sees the new fields.
        status, raw = _get(port, "/api/cues/v1/items/video-contract")
        data = json.loads(raw)["data"]
        assert status == 200 and data["item"]["published_at"] == "2029-12-31T08:00:00Z"
        assert data["timing"]["source"] == "auto_captions"
    finally:
        httpd.shutdown()
        httpd.server_close()
        idx.close()


def test_corpus_v1_fixture_still_matches():
    expected = json.loads(regenerate.FIXTURE_PATH.read_text(encoding="utf-8"))
    assert regenerate.generate_fixture() == expected
    assert expected["_fixture"]["contract"] == corpus_contract.CONTRACT_NAME
