"""Offline capture/status contracts against a disposable real queue and library."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta
import asyncio
import json
import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import jsonschema
import pytest

import index as index_mod
import research
import uoink_mcp_tools as tools
from tests.test_unique_capture_folders import capture as extraction_fixture


@pytest.fixture
def helper(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "app").mkdir()
    for name, value in {
        "UOINK_ISOLATED_PROFILE": tmp_path / "profile",
        "UOINK_ISOLATED_APP_DIR": tmp_path / "app",
        "UOINK_ISOLATED_PORT": "18124",
        "UOINK_OUTPUT_DIR": tmp_path / "output",
    }.items():
        monkeypatch.setenv(name, str(value))
    import server
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "output")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(tools, "_backend", server)
    for name in ("research_start", "research_capture", "research_status"):
        monkeypatch.setattr(tools.TOOL_REGISTRY[name].rate_limiter, "_calls", [])
    forbidden = Mock(side_effect=AssertionError("capture/status must not fetch or start workers"))
    monkeypatch.setattr(server, "_run_subprocess", forbidden)
    monkeypatch.setattr(server, "get_transcript_cascade", forbidden)
    monkeypatch.setattr(server.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    yield SimpleNamespace(server=server, idx=idx, root=tmp_path)
    idx.close()
    forbidden.assert_not_called()


def candidate(n, *, captions=True, score=0, duration=2700, **extra):
    video_id = f"talk{n:07d}"
    return {"key": "yt:" + video_id, "kind": "youtube", "title": f"Talk {n}",
            "channel": "Test channel", "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration_s": duration, "has_captions": captions, "score": score,
            "capturable": True, "in_library": False, **extra}


def run_with(helper, candidates, budget=120):
    run = research.create_run(helper.root, {"question": "Test question", "max_asr_minutes": budget})
    run["candidates"] = candidates
    run["candidates_pool"] = candidates
    research.save_run(helper.root, run)
    return run


def capture(run, **kwargs):
    return tools.call_tool("research_capture", {"run_id": run["run_id"], **kwargs})


def status(run):
    return tools.call_tool("research_status", {"run_id": run["run_id"]})


def save_library(helper, item, *, source="captions", transcript=True, deleted=False, video_id=None,
                 sidecar_fields=None):
    video_id = video_id or item["key"].split(":", 1)[1]
    folder = helper.root / "output" / video_id
    folder.mkdir(parents=True, exist_ok=True)
    sidecar = folder / f"{video_id}.json"
    sidecar.write_text(json.dumps({"video_id": video_id, "url": item["url"],
        "title": item["title"], "transcript_source": source,
        "transcript": [{"start": 0, "end": 3, "text": "Fixture transcript"}] if transcript else [],
        **(sidecar_fields or {})}), encoding="utf-8")
    corpus = folder / f"{video_id}.md"
    corpus.write_text("# Fixture\n", encoding="utf-8")
    helper.idx.upsert_yoink({"video_id": video_id, "slug": video_id,
        "title": item["title"], "channel": item["channel"], "topic": "Test",
        "yoinked_at": "2026-11-03T12:00:00", "corpus_path": str(corpus),
        "sidecar_path": str(sidecar), "metadata_json": json.dumps({"url": item["url"]}),
        "deleted_at": "2026-11-03T12:01:00" if deleted else None}, content="Fixture transcript")
    if deleted:
        helper.idx.soft_delete_yoink(video_id)


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("transcript_only,mode", [(True, "lite"), (False, "full")])
def test_order_modes_persistence_and_eta(helper, top, transcript_only, mode):
    candidates = [candidate(1, score=1), candidate(2, score=3), candidate(3, score=2)]
    run = run_with(helper, candidates)
    keys = [candidates[n]["key"] for n in ((1, 2, 0) if top else (2, 0, 1))]
    result = capture(run, transcript_only=transcript_only, **({"top": 3} if top else {"keys": keys}))
    assert result["ok"] and "untrusted_content" in result
    jsonschema.validate(result, tools.OUTPUT_SCHEMAS["research_capture"])
    assert [q["key"] for q in result["queued"]] == keys
    rows = [helper.idx.get_pending(q["pending_id"]) for q in result["queued"]]
    assert [r["url"] for r in rows] == [q["url"] for q in result["queued"]]
    assert all(r["long_video_mode"] == mode for r in rows)
    for row in rows:
        assert helper.idx.next_pending(helper.server._now_iso())["pending_id"] == row["pending_id"]
        helper.idx.mark_pending_running(row["pending_id"])
        helper.idx.mark_pending_succeeded(row["pending_id"], "fixture")
    assert result["eta"] == {"min_minutes": 1.5, "max_minutes": 3.0}
    saved = research.load_run(helper.root, run["run_id"])
    assert list(saved["captures"]) == keys
    assert all(c["transcript_only"] == transcript_only and c["queued_at"]
               for c in saved["captures"].values())


def test_asr_budget_and_repeat_reservation(helper):
    run = run_with(helper, [candidate(n, captions=False) for n in range(3)], budget=20)
    first = capture(run, top=3)
    assert len(first["queued"]) == 2
    assert first["skipped"] == [{"key": run["candidates"][2]["key"], "reason": "asr_budget"}]
    assert (first["asr_minutes_committed"], first["asr_minutes_left"]) == (18, 2)
    assert first["eta"] == {"min_minutes": 15.0, "max_minutes": 22.4}
    again = capture(run, top=3)
    assert [q["pending_id"] for q in first["queued"]] == [q["pending_id"] for q in again["queued"]]
    assert all(q["already_queued"] for q in again["queued"])
    assert again["asr_minutes_committed"] == 18


def test_zero_budget_library_recheck_and_deleted_row(helper):
    candidates = [candidate(1), candidate(2, captions=False), candidate(3, captions=None),
                  candidate(4, captions=False, in_library=True)]
    run = run_with(helper, candidates, budget=0)
    save_library(helper, candidates[2], source="asr")
    save_library(helper, candidates[3], deleted=True)
    result = capture(run, top=4)
    assert [q["key"] for q in result["queued"]] == [candidates[0]["key"]]
    assert [q["key"] for q in result["already"]] == [candidates[2]["key"]]
    assert {q["key"] for q in result["skipped"]} == {candidates[1]["key"], candidates[3]["key"]}
    assert all(q["reason"] == "asr_budget" for q in result["skipped"])
    assert len(helper.idx.list_pending()) == 1
    assert status(run)["ready_count"] == 1


@pytest.mark.parametrize("pending_state", ["pending", "running", "publishing"])
def test_external_queue_reuse_and_default_lite(helper, pending_state):
    item = candidate(1, captions=False)
    run = run_with(helper, [item])
    pid = helper.idx.enqueue_pending(item["url"], 30, helper.server._now_iso())
    if pending_state != "pending":
        helper.idx.mark_pending_running(pid)
    if pending_state == "publishing":
        helper.idx.mark_pending_publishing(pid)
    result = capture(run, top=1)
    assert result["queued"][0]["pending_id"] == pid and result["queued"][0]["already_queued"]
    assert result["asr_minutes_committed"] == 9
    saved = research.load_run(helper.root, run["run_id"])["captures"][item["key"]]
    assert helper.idx.get_pending(pid)["long_video_mode"] == "full"
    assert saved["transcript_only"] is False  # Reused rows keep the original mode.
    assert len(helper.idx.list_pending(include_terminal=True)) == 1
    other = run_with(helper, [candidate(2)])
    fresh = capture(other, top=1)["queued"][0]
    assert helper.idx.get_pending(fresh["pending_id"])["long_video_mode"] == "lite"


def test_unknown_duration_assumption_and_podcast_reasons(helper):
    unknown = candidate(1, captions=None, duration=None)
    podcast = candidate(2, key="pod:012345abcdef", kind="podcast", url="https://audio.example/episode.mp3")
    page = candidate(3, key="hn:123", kind="podcast", capturable=False)
    run = run_with(helper, [unknown, podcast, page], budget=15)
    result = capture(run, keys=[unknown["key"], podcast["key"], page["key"], "yt:unknown0001"])
    assert result["asr_minutes_committed"] == 15 and len(result["queued"]) == 1
    assert [s["reason"] for s in result["skipped"]] == ["podcast_capture_later", "not_capturable", "unknown_key"]
    assert result["eta"] == {"min_minutes": 12.5, "max_minutes": 18.8}
    save_library(helper, podcast, source="asr", video_id="ep_fixture")
    assert capture(run, keys=[podcast["key"]])["already"][0]["video_id"] == "ep_fixture"


@pytest.mark.parametrize("args", [
    {}, {"keys": ["yt:talk0000001"], "top": 1}, {"keys": []}, {"keys": ["invalid"]},
    {"keys": ["yt:talk0000001"] * 2}, {"keys": ["yt:talk0000001"] * 31},
    {"top": 0}, {"top": 31}, {"top": True}, {"top": 1, "transcript_only": 1},
    {"top": 1, "extra": True}, {"keys": ["yt:talk0000001\n"]},
])
def test_strict_capture_validation(helper, args, monkeypatch):
    run = run_with(helper, [candidate(1)])
    backend = Mock(side_effect=AssertionError("invalid input reached backend"))
    monkeypatch.setattr(helper.server, "_research_capture", backend)
    result = capture(run, **args)
    assert not result["ok"] and result["code"] == "invalid_arguments"
    backend.assert_not_called()


def test_status_states_sources_counts_and_reservation_reconciliation(helper):
    candidates = [candidate(n, captions=n not in (2, 4, 5, 6)) for n in range(9)]
    run = run_with(helper, candidates)
    queued = capture(run, top=9)["queued"]
    ids = [q["pending_id"] for q in queued]
    for n in (1, 2, 3, 4, 5, 7, 8):
        helper.idx.mark_pending_running(ids[n])
    helper.idx.mark_pending_publishing(ids[1])
    for n, source in ((3, "captions"), (4, "asr")):
        helper.idx.mark_pending_succeeded(ids[n], "fixture")
        save_library(helper, candidates[n], source=source)
    helper.idx.mark_pending_failed(ids[5], "private path and credential text", helper.server._now_iso(), force_final=True)
    helper.idx.cancel_pending(ids[6])  # No attempt: does not spend ASR minutes.
    helper.idx.mark_pending_succeeded(ids[7], "no-transcript")
    save_library(helper, candidates[7], transcript=False)
    helper.idx.mark_pending_succeeded(ids[8], "deleted")
    save_library(helper, candidates[8], deleted=True)
    path = helper.root / "research" / run["run_id"] / "run.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    result = status(run)
    jsonschema.validate(result, tools.OUTPUT_SCHEMAS["research_status"])
    assert [r["state"] for r in result["items"]] == [
        "queued", "capturing", "asr_running", "captioned", "ready", "failed", "failed", "failed", "failed"]
    assert result["counts"] == {"queued": 1, "capturing": 1, "asr_running": 1, "captioned": 1, "ready": 1, "failed": 4}
    assert result["ready_count"] == 2 and result["asr_minutes_used"] == 9
    assert result["asr_minutes_left"] == 102 and not result["done"]
    assert [r["transcript_source"] for r in result["items"]][3:5] == ["captions", "whisper"]
    assert result["items"][5]["error"] == "capture_failed" and result["items"][6]["error"] == "cancelled"
    assert path.read_bytes() != before[0]
    assert research.load_run(helper.root, run["run_id"])["asr_minutes_committed"] == 18
    reconciled = (path.read_bytes(), path.stat().st_mtime_ns)
    assert status(run) == result
    assert (path.read_bytes(), path.stat().st_mtime_ns) == reconciled
    for n in (0, 1, 2):
        helper.idx.mark_pending_failed(ids[n], "HTTP Error 429", helper.server._now_iso(), force_final=True,
                                       expected_status=helper.idx.pending_status(ids[n]))
    assert status(run)["done"]
    assert status(run)["items"][0]["error"] == "rate_limited"


def test_status_empty_and_missing_pending(helper, monkeypatch):
    run = run_with(helper, [candidate(1)])
    assert status(run)["done"] and status(run)["ready_count"] == 0
    capture(run, top=1)
    monkeypatch.setattr(helper.idx, "get_pending", lambda pid: None)
    assert status(run)["items"][0]["error"] == "pending_not_found"
    assert status(run)["done"]


def test_ready_with_unknown_saved_provenance(helper):
    item = candidate(1)
    run = run_with(helper, [item])
    save_library(helper, item, source=None)
    capture(run, top=1)
    result = status(run)
    assert result["items"][0]["state"] == "ready"
    assert result["items"][0]["transcript_source"] is None
    assert result["ready_count"] == 1 and result["done"]


def test_concurrent_capture_cannot_overspend(helper):
    run = run_with(helper, [candidate(1, captions=False), candidate(2, captions=False)], budget=9)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: helper.server._research_capture(
            {"run_id": run["run_id"], "keys": [c["key"]]}), run["candidates"]))
    assert sum(len(r["queued"]) for r in results) == 1
    assert research.load_run(helper.root, run["run_id"])["asr_minutes_committed"] == 9


def test_cancel_after_running_releases_estimate_without_worker_run_writes(helper, monkeypatch):
    run = run_with(helper, [candidate(1, captions=False)])
    pid = capture(run, top=1)["queued"][0]["pending_id"]
    server = helper.server
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    ownership = SimpleNamespace(ok=True, conflict=None, completed_while_waiting=False, reused=None)
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda url: nullcontext(ownership))
    monkeypatch.setattr(server, "_fetch_metadata", lambda *a, **k: {"title": "Fixture"})
    monkeypatch.setattr(server, "_classify_topic", lambda metadata: "Test")
    monkeypatch.setattr(server, "_video_capture_folder", lambda *a: helper.root / "output")

    def cancelled(*args, **kwargs):
        helper.idx.cancel_pending(pid)
        return {"ok": False}

    monkeypatch.setattr(server, "_run_extraction", cancelled)
    path = helper.root / "research" / run["run_id"] / "run.json"
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert server._retry_pending_one() is True
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert helper.idx.get_pending(pid)["attempt_count"] == 0
    result = status(run)
    assert result["done"] and result["asr_minutes_used"] == 0
    assert result["asr_minutes_left"] == 120
    assert research.load_run(helper.root, run["run_id"])["asr_minutes_committed"] == 0
    assert result["items"][0]["error"] == "cancelled"
    assert server._retry_pending_last_outcome == (pid, "failed")


def test_active_ids_cache_expiry_and_changes(helper, monkeypatch):
    run = run_with(helper, [candidate(1), candidate(2, captions=False)])
    first = capture(run, keys=[run["candidates"][0]["key"]])["queued"][0]["pending_id"]
    now = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    assert research.active_research_pending_ids(helper.root, now=now) == {first: False}
    original_load = research.load_run
    monkeypatch.setattr(research, "load_run", Mock(side_effect=AssertionError("unchanged cache should not reload")))
    assert research.active_research_pending_ids(helper.root, now=now) == {first: False}
    assert research.active_research_pending_ids(helper.root, now=now + timedelta(days=8)) == {}
    monkeypatch.setattr(research, "load_run", original_load)
    second = capture(run, keys=[run["candidates"][1]["key"]])["queued"][0]["pending_id"]
    assert research.active_research_pending_ids(helper.root, now=now) == {first: False, second: True}
    (helper.root / "research" / run["run_id"] / "run.json").unlink()
    assert research.active_research_pending_ids(helper.root, now=now) == {}


@pytest.mark.parametrize("outcome,next_id,consecutive,expected", [
    ((1, "succeeded"), 2, 0, (2, 1)), ((1, "rate_limited"), 2, 0, (30, 0)),
    ((1, "failed"), 2, 0, (30, 0)), ((1, "succeeded"), 2, 9, (30, 0)),
    ((1, "succeeded"), 2, 8, (2, 9)), ((9, "succeeded"), 2, 0, (30, 0)),
    ((1, "succeeded"), 3, 0, (30, 0)), ((1, "succeeded"), 9, 0, (30, 0)),
    ((None, "idle"), 2, 0, (30, 0)), ((1, "succeeded"), None, 0, (30, 0)),
    ((1, "succeeded_degraded"), 2, 0, (30, 0)), ((1, "succeeded"), 4, 0, (2, 1)),
])
def test_burst_decision_without_threads_or_sleep(helper, outcome, next_id, consecutive, expected):
    next_row = {"pending_id": next_id} if next_id is not None else None
    assert helper.server._retry_pending_delay(outcome, consecutive, {1: True, 2: False, 3: True, 4: None}, next_row) == expected


def test_flat_discovery_unknown_captions_reserve_burst_and_release(helper):
    items = research.parse_ytsearch({"entries": [
        {"id": f"talk{n:07d}", "title": f"Talk {n}", "duration": 2700} for n in (1, 2)]})
    assert all(item["has_captions"] is None for item in items)
    run = run_with(helper, items, budget=18)
    result = capture(run, top=2)
    ids = [item["pending_id"] for item in result["queued"]]
    assert result["asr_minutes_committed"] == 18
    saved = research.load_run(helper.root, run["run_id"])
    assert all(entry["asr_expected"] is None for entry in saved["captures"].values())
    active = research.active_research_pending_ids(helper.root)
    assert active == dict.fromkeys(ids)
    assert helper.server._retry_pending_delay((ids[0], "succeeded"), 0, active,
                                              {"pending_id": ids[1]}) == (2, 1)
    helper.idx.mark_pending_running(ids[0])
    helper.idx.mark_pending_succeeded(ids[0], "fixture")
    save_library(helper, items[0])
    result = status(run)
    assert result["items"][0]["state"] == "captioned"
    assert result["asr_minutes_used"] == 0 and result["asr_minutes_left"] == 9
    saved = research.load_run(helper.root, run["run_id"])
    assert saved["asr_minutes_committed"] == 9
    assert saved["captures"][items[0]["key"]]["asr_minutes_reserved"] == 0
    assert capture(run, top=2)["asr_minutes_committed"] == 9


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
@pytest.mark.parametrize("poll_first", [False, True])
def test_recapture_replaces_terminal_reservation(helper, terminal, poll_first):
    items = [candidate(n, captions=None) for n in (1, 2)]
    run = run_with(helper, items, budget=18)
    first = capture(run, top=2)
    pid = first["queued"][0]["pending_id"]
    if terminal == "failed":
        helper.idx.mark_pending_running(pid)
        helper.idx.mark_pending_failed(pid, "download_failed", helper.server._now_iso(), force_final=True)
    else:
        helper.idx.cancel_pending(pid)
    if poll_first:
        result = status(run)
        assert result["asr_minutes_used"] == 0 and result["asr_minutes_left"] == 9
    result = capture(run, keys=[items[0]["key"]])
    assert len(result["queued"]) == 1 and result["skipped"] == []
    assert result["queued"][0]["pending_id"] != pid
    assert result["asr_minutes_committed"] == 18
    saved = research.load_run(helper.root, run["run_id"])
    assert len(saved["captures"]) == 2
    assert saved["asr_minutes_committed"] == sum(c["asr_minutes_reserved"] for c in saved["captures"].values())


@pytest.mark.parametrize("fields,source", [
    ({"transcript_source": "asr"}, "whisper"),
    ({"media_depth": {"transcript_kind": "local_asr"}}, "whisper"),
    ({"source_type": "episode", "platform": "podcast", "media_depth": {"transcript_kind": "local_asr"}}, "whisper"),
    ({"source_type": "episode"}, "whisper"),
    ({"platform": "podcast"}, "whisper"),
    ({"transcript_source": "captions"}, "captions"),
    ({"media_depth": {"transcript_kind": "captions"}}, "captions"),
    ({}, None), ({"transcript_source": "unrecognized"}, None),
])
def test_status_provenance_from_saved_sidecars(helper, monkeypatch, fields, source):
    item = candidate(1, captions=None)
    run = run_with(helper, [item])
    pid = capture(run, top=1)["queued"][0]["pending_id"]
    helper.idx.mark_pending_running(pid)
    helper.idx.mark_pending_succeeded(pid, "fixture")
    save_library(helper, item, source=None, sidecar_fields=fields)
    monkeypatch.setattr(helper.server, "_library_transcript", Mock(
        side_effect=AssertionError("research must not use get_transcript's provenance default")))
    result = status(run)
    assert result["items"][0]["transcript_source"] == source
    assert result["items"][0]["state"] == ("captioned" if source == "captions" else "ready")
    assert result["asr_minutes_used"] == (9 if source == "whisper" else 0)
    assert research.load_run(helper.root, run["run_id"])["asr_minutes_committed"] == (0 if source == "captions" else 9)


@pytest.mark.parametrize("settlement", ["failed", "succeeded"])
def test_publication_handoff_stays_capturing_until_receipt_settles(helper, settlement):
    item = candidate(1, captions=None)
    run = run_with(helper, [item])
    pid = capture(run, top=1)["queued"][0]["pending_id"]
    helper.idx.mark_pending_running(pid)
    helper.idx.mark_pending_publishing(pid)
    queue = index_mod.PublicationRetryQueue(helper.root / "publication-retries")
    receipt = queue.enqueue({"pending_id": pid, "sidecar": {"video_id": item["key"][3:]}})
    helper.idx.mark_pending_failed(pid, "publication_failed", helper.server._now_iso(),
                                   force_final=True, expected_status="publishing")
    assert queue.claim(receipt) and queue.has_pending_id(pid)
    before = {p.name: p.read_bytes() for p in queue.root.iterdir()}
    result = status(run)
    assert result["items"][0]["state"] == "capturing"
    assert result["items"][0]["error"] is None and not result["done"]
    assert result["asr_minutes_left"] == 111
    assert {p.name: p.read_bytes() for p in queue.root.iterdir()} == before
    assert capture(run, top=1)["queued"][0]["pending_id"] == pid
    assert len(helper.idx.list_pending(include_terminal=True)) == 1
    if settlement == "succeeded":
        save_library(helper, item)
        helper.idx.mark_pending_succeeded(pid, "published")
    queue.settle(receipt, error="publication_failed" if settlement == "failed" else None)
    assert not queue.has_pending_id(pid)
    result = status(run)
    assert result["items"][0]["state"] == ("failed" if settlement == "failed" else "captioned")
    assert result["done"] and result["asr_minutes_left"] == 120


@pytest.mark.parametrize("prefix", ["ep_", "episode_"])
def test_podcast_library_ids_and_audio_url_join(helper, prefix):
    import podcasts
    audio = "https://cdn.example/42.mp3"
    page = "https://show.example/episode/42"
    video_id = prefix + "fixture"
    parsed = research.parse_library([{"video_id": video_id, "url": page, "enclosure_url": audio,
                                      "title": "Episode", "channel": "Show"}])[0]
    assert parsed["kind"] == "podcast" and parsed["key"].startswith("pod:")
    assert parsed["url"] == audio and parsed["video_id"] == video_id
    assert research.parse_library([{"video_id": video_id}])[0]["kind"] == "podcast"
    save_library(helper, {**parsed, "url": page}, source=None, video_id=video_id,
                 sidecar_fields={"source_type": "episode", "platform": "podcast"})
    feed = podcasts.add_feed(helper.idx, "https://show.example/feed.xml")
    podcasts.upsert_episodes(helper.idx, feed["id"], [{"guid": "episode-42", "audio_url": audio,
                                                     "title": "Episode", "episode_page_url": page}])
    with helper.idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_episodes SET yoink_video_id=? WHERE feed_id=?", (video_id, feed["id"]))
    # Discovery has no corpus ID and the saved metadata contains only the page URL.
    item = {**parsed, "video_id": None, "in_library": False}
    run = run_with(helper, [item], budget=0)
    result = capture(run, top=1)
    assert result["queued"] == [] and result["skipped"] == []
    assert result["already"][0]["video_id"] == video_id
    assert status(run)["items"][0]["transcript_source"] == "whisper"
    helper.idx.soft_delete_yoink(video_id)
    assert helper.server._research_library_lookup(item) is None


@pytest.mark.parametrize("budget", [0, 9])
def test_transcriptless_library_entry_is_requeued_subject_to_budget(helper, budget):
    item = candidate(1, captions=None, in_library=True)
    run = run_with(helper, [item], budget=budget)
    save_library(helper, item, transcript=False)
    result = capture(run, top=1)
    assert result["already"] == []
    if budget:
        assert len(result["queued"]) == 1 and result["asr_minutes_committed"] == 9
        assert status(run)["items"][0]["state"] == "queued"
    else:
        assert result["skipped"] == [{"key": item["key"], "reason": "asr_budget"}]
        assert helper.idx.list_pending() == []


@pytest.mark.parametrize("source", ["asr", None])
def test_extraction_surfaces_caption_refusal_and_effective_source(extraction_fixture, source):
    fixture = extraction_fixture
    fixture.scope["_fetch_video_subtitles"] = lambda *a, **k: True
    resolve = Mock(return_value=([(0, 3, "Words")] if source else [], source,
                                 {"status": "succeeded" if source else "disabled"}))
    fixture.scope["_resolve_video_transcript"] = resolve
    result = fixture.run("https://www.youtube.com/watch?v=aaaaaaaaaaa")
    assert result["ok"] is True and result["captions_refused"] is True
    assert result["transcript_source"] == source
    assert resolve.call_args.kwargs["captions_refused"] is True


@pytest.mark.parametrize("source,refused,outcome", [
    ("captions", False, "succeeded"), ("captions", True, "succeeded_degraded"),
    ("asr", False, "succeeded_degraded"), ("asr", True, "succeeded_degraded"),
    (None, True, "succeeded_degraded"), (None, False, "succeeded_degraded"),
])
def test_only_unrefused_caption_success_authorizes_burst(helper, monkeypatch, source, refused, outcome):
    server = helper.server
    run = run_with(helper, [candidate(1, captions=None), candidate(2, captions=None)])
    ids = [q["pending_id"] for q in capture(run, top=2)["queued"]]
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    ownership = SimpleNamespace(ok=True, conflict=None, completed_while_waiting=False, reused=None)
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda url: nullcontext(ownership))
    monkeypatch.setattr(server, "_fetch_metadata", lambda *a, **k: {"title": "Fixture"})
    monkeypatch.setattr(server, "_classify_topic", lambda metadata: "Test")
    monkeypatch.setattr(server, "_video_capture_folder", lambda *a: helper.root / "output")
    monkeypatch.setattr(server, "_record_single_extract_job", Mock())
    monkeypatch.setattr(server, "_run_extraction", Mock(return_value={
        "ok": True, "transcript_source": source, "captions_refused": refused}))
    path = helper.root / "research" / run["run_id"] / "run.json"
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert server._retry_pending_one() is True
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert helper.idx.pending_status(ids[0]) == "succeeded"
    assert server._retry_pending_last_outcome == (ids[0], outcome)
    delay = server._retry_pending_delay(server._retry_pending_last_outcome, 0,
        research.active_research_pending_ids(helper.root), helper.idx.next_pending(server._now_iso()))
    assert delay == ((2, 1) if outcome == "succeeded" else (30, 0))


@pytest.mark.parametrize("replacement", ["unchanged", "unknown", "asr", "unrelated", "empty"])
def test_burst_rechecks_head_after_pause_without_threads(helper, replacement):
    server = helper.server
    items = [candidate(1), candidate(2, captions=None), candidate(3, captions=replacement != "asr")]
    if replacement == "unknown":
        items[2]["has_captions"] = None
    run = run_with(helper, items)
    ids = [q["pending_id"] for q in capture(run, top=2 if replacement == "unrelated" else 3)["queued"]]
    if replacement == "unrelated":
        ids.append(helper.idx.enqueue_pending(items[2]["url"], 30, server._now_iso()))
    helper.idx.mark_pending_running(ids[0])
    helper.idx.mark_pending_succeeded(ids[0], "captions")
    delay, consecutive = server._retry_pending_delay((ids[0], "succeeded"), 0,
        research.active_research_pending_ids(helper.root), helper.idx.next_pending(server._now_iso()))
    assert (delay, consecutive) == (2, 1)
    clock = SimpleNamespace(now=0.0)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds
        if len(sleeps) == 1 and replacement != "unchanged":
            helper.idx.cancel_pending(ids[1])
            if replacement == "empty":
                helper.idx.cancel_pending(ids[2])

    result = server._retry_pending_wait(delay, consecutive, ids[1], sleep=sleep, clock=lambda: clock.now)
    guarded = replacement in {"asr", "unrelated", "empty"}
    assert sleeps == ([2, 28] if guarded else [2])
    assert result == (0 if guarded else 1)
    assert clock.now == (30 if guarded else 2)
    assert all(row["status"] != "running" for row in helper.idx.list_pending(include_terminal=True))


@pytest.mark.parametrize("running", [False, True])
def test_capture_warns_when_resident_helper_is_not_running(helper, monkeypatch, running):
    import uoink_agent_runtime
    monkeypatch.setattr(uoink_agent_runtime, "helper_running", lambda backend: running)
    run = run_with(helper, [candidate(1)])
    result = uoink_agent_runtime.call_tool("research_capture", {"run_id": run["run_id"], "top": 1}, helper.server)
    assert result["ok"] and len(result["queued"]) == 1
    assert helper.idx.pending_status(result["queued"][0]["pending_id"]) == "pending"
    if running:
        assert "warnings" not in result
    else:
        assert result["warnings"] == ["helper_not_running"]
        assert "start when Uoink is running" in result["message"]


@pytest.mark.parametrize("name", ["research_capture", "research_status"])
@pytest.mark.parametrize("active_request", [False, True])
def test_stdio_capture_status_keep_event_loop_responsive(helper, monkeypatch, name, active_request):
    import uoink_mcp
    from tests.test_discovery_queue import _run_stdio
    monkeypatch.setattr(uoink_mcp, "STDIO_TOOLSET", "research")
    monkeypatch.setattr(uoink_mcp, "_helper_running", lambda: False)
    run = run_with(helper, [candidate(1)])
    release = threading.Event()
    original = getattr(helper.server, "_" + name)

    async def exercise():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        main_thread = threading.get_ident()

        def blocked(args):
            assert threading.get_ident() != main_thread
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3), "research worker was not released"
            return original(args)

        monkeypatch.setattr(helper.server, "_" + name, blocked)
        token = uoink_mcp._active_stdio_request.set(object() if active_request else None)
        args = {"run_id": run["run_id"], **({"top": 1} if name == "research_capture" else {})}
        pending = asyncio.create_task(uoink_mcp.mcp.call_tool(name, args))
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert not pending.done()
            assert await asyncio.wait_for(uoink_mcp.mcp.list_tools(), 1)
            release.set()
            result = json.loads((await asyncio.wait_for(pending, 2)).content[0].text)
            assert result["ok"]
            if name == "research_capture":
                assert result["warnings"] == ["helper_not_running"]
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)
            uoink_mcp._active_stdio_request.reset(token)

    _run_stdio(exercise())


def test_tool_contracts_and_missing_runs(helper):
    for name, rate, readonly, world in (("research_capture", 10, False, True), ("research_status", 60, True, False)):
        spec = tools.TOOL_REGISTRY[name]
        assert spec.annotations == {"readOnlyHint": readonly, "destructiveHint": False,
                                    "idempotentHint": readonly, "openWorldHint": world}
        assert spec.rate_limiter.max_calls == rate
        assert spec.input_schema["additionalProperties"] is False and "oneOf" not in spec.input_schema
        assert name in tools.UNTRUSTED_CONTENT_TOOL_NAMES
        args = {"run_id": "rr_20261103000000_deadbeef"}
        if name == "research_capture":
            args["top"] = 1
        assert tools.call_tool(name, args)["code"] == "not_found"
        assert tools.call_tool(name, {**args, "run_id": "../outside"})["code"] == "invalid_arguments"
