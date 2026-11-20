"""Save a whole show through the real helper pieces: the download queue,
the retry worker, the bot-check signals and the /shows routes.

Only the capture itself (_run_extraction) and its metadata fetch are fakes;
the queue rows, their modes, back-off and settlement are the real ones.
Nothing reaches the network, yt-dlp or a model.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index  # noqa: E402
import server  # noqa: E402
import show_capture as sc  # noqa: E402

LINKS = "\n".join(f"https://www.youtube.com/watch?v=tp{i:09d}" for i in range(4))
_LOCAL_URLOPEN = urllib.request.urlopen     # the route tests talk to their own loopback server


def vid(i):
    return f"tp{i:09d}"


def inline(fn):
    fn()


@pytest.fixture
def helper(tmp_path, monkeypatch):
    idx = index.Index.open(tmp_path / "index.db")
    state = SimpleNamespace(index=idx, data=tmp_path / "data", calls=[], behaviour={})

    def fake_extract(url, interval, folder, *, long_video_mode, **_kwargs):
        video_id = url.rsplit("=", 1)[-1]
        state.calls.append((video_id, long_video_mode))
        action = state.behaviour.get(video_id)
        if action is not None:
            raise action
        return {"title": f"Episode {video_id}", "folder": str(folder),
                "transcript_source": "captions", "long_video_mode": long_video_mode}

    ownership = SimpleNamespace(ok=True, conflict=None, completed_while_waiting=False,
                                reused=None, error=None)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", state.data)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "captures")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_jobs", {})
    monkeypatch.setattr(server, "_pending_long_video_modes", {})
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda _url: nullcontext(ownership))
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    monkeypatch.setattr(server, "_fetch_metadata", lambda url, cancel_event=None: {
        "id": url.rsplit("=", 1)[-1], "title": "Fixture", "duration": 600})
    monkeypatch.setattr(server, "_classify_topic", lambda _metadata: "Tides")
    monkeypatch.setattr(server, "_run_extraction", fake_extract)
    monkeypatch.setattr(server, "_record_single_extract_job", Mock())
    monkeypatch.setattr(server, "_youtube_bot_check_hits", [])
    monkeypatch.setattr(server, "_youtube_bot_check_until", None)
    monkeypatch.setattr(sc, "_listing", set())
    unexpected = Mock(side_effect=AssertionError("unmocked external I/O"))
    monkeypatch.setattr(server, "_run_subprocess", unexpected)
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected)
    try:
        yield state
    finally:
        idx.close()
    unexpected.assert_not_called()


def make_run(state, text=LINKS, *, asr=False):
    job = sc.create(state.data, text)
    sc.ensure_listing(state.data, job["id"], server._show_backend, spawn=inline)
    return sc.start(state.data, job["id"], server._show_backend, asr=asr)


def tick():
    sc.tick(server.DATA_ROOT, server._show_backend, spawn=inline)


def rows(state):
    return state.index.list_pending(include_terminal=True)


def test_a_show_runs_through_the_real_queue_in_transcript_mode(helper):
    job = make_run(helper)
    for _ in range(12):
        tick()
        server._retry_pending_one()
    job = sc.load(helper.data, job["id"])
    assert job["state"] == sc.DONE
    assert sc.counts(job)["done"] == 4
    assert helper.calls == [(vid(i), "transcript") for i in range(4)]
    assert [r["long_video_mode"] for r in rows(helper)] == ["transcript"] * 4
    assert {r["status"] for r in rows(helper)} == {"succeeded"}


def test_an_asr_run_queues_the_asr_mode(helper, monkeypatch):
    monkeypatch.setattr(server, "_reliability_model_status", lambda *a: {"cached": True})
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    make_run(helper, asr=True)
    tick()
    server._retry_pending_one()
    assert helper.calls == [(vid(0), "transcript_asr")]


def test_an_asr_run_needs_the_model(helper, monkeypatch):
    monkeypatch.setattr(server, "_reliability_model_status", lambda *a: {"cached": False})
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    with pytest.raises(sc.ShowCaptureError) as err:
        make_run(helper, asr=True)
    assert err.value.code == "asr_unavailable"
    assert str(err.value) == server.TRANSCRIPT_NO_MODEL_MESSAGE


def test_failures_and_duplicates_come_back_with_reasons(helper):
    helper.behaviour[vid(1)] = server.ExtractionPhaseError(
        "transcript", server.TRANSCRIPT_NO_CAPTIONS_MESSAGE)
    helper.behaviour[vid(2)] = server.ExtractionPhaseError(
        "metadata", server.TRANSCRIPT_ALREADY_SAVED_MESSAGE)
    job = make_run(helper)
    for _ in range(12):
        tick()
        server._retry_pending_one()
    job = sc.load(helper.data, job["id"])
    by_id = {e["video_id"]: e for e in job["episodes"]}
    assert by_id[vid(1)]["state"] == sc.EP_FAILED
    assert by_id[vid(1)]["reason"] == server.TRANSCRIPT_NO_CAPTIONS_MESSAGE
    assert by_id[vid(2)]["state"] == sc.EP_SKIPPED
    assert by_id[vid(2)]["reason"] == sc.REASON_ALREADY_SAVED
    assert job["state"] == sc.DONE


def test_a_bot_check_on_an_episode_holds_the_run(helper):
    helper.behaviour[vid(0)] = server._transcript_block_error(server.CAPTIONS_BOT_CHECK)
    job = make_run(helper)
    tick()
    server._retry_pending_one()                      # the queue backs off 30 minutes
    row = rows(helper)[0]
    assert row["status"] == "pending" and row["last_error"].startswith("youtube_bot_check")
    for _ in range(4):
        tick()
        server._retry_pending_one()                  # nothing eligible yet
    job = sc.load(helper.data, job["id"])
    assert job["state"] == sc.WAITING and job["reason"] == "bot_check"
    assert job["wait_until"] and len(rows(helper)) == 1   # no new episode asked for
    assert server._show_youtube_waiting()["active"] is True


def test_the_bot_check_cooldown_stops_new_episodes(helper):
    job = make_run(helper)
    for _ in range(server.YOUTUBE_BOT_CHECK_HIT_LIMIT):
        server._note_youtube_bot_check()
    assert server._youtube_bot_check_status()["active"] is True
    tick()
    job = sc.load(helper.data, job["id"])
    assert job["state"] == sc.WAITING and rows(helper) == []


def test_a_users_capture_goes_first(helper):
    user_url = "https://www.youtube.com/watch?v=userpick001"
    helper.index.enqueue_pending_once(user_url, 30, server._now_iso(), "full")
    job = make_run(helper)
    tick()
    assert [r["url"] for r in rows(helper)] == [user_url]
    assert sc.load(helper.data, job["id"])["reason"] == "queue_busy"
    server._retry_pending_one()                     # the user's capture runs
    tick()
    assert len(rows(helper)) == 2
    assert helper.calls[0] == ("userpick001", "full")


def test_a_running_capture_holds_the_show(helper):
    make_run(helper)
    with server._extract_lock:
        tick()
    assert rows(helper) == []
    tick()
    assert len(rows(helper)) == 1


def test_far_off_retries_do_not_block_the_show(helper):
    later = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    helper.index.enqueue_pending_once("https://example.com/clip", 30, later, "full")
    make_run(helper)
    tick()
    assert len(rows(helper)) == 2


def test_cancel_removes_the_queued_row(helper):
    job = make_run(helper)
    tick()
    pending_id = rows(helper)[0]["pending_id"]
    sc.cancel(helper.data, job["id"], server._show_backend)
    assert helper.index.get_pending(pending_id)["status"] == "cancelled"
    assert server._retry_pending_one() is False


def test_a_restart_resumes_from_the_queue(helper):
    job = make_run(helper)
    tick()
    tick()
    assert len(rows(helper)) == 1
    # Restart: listing state and in-memory maps are gone; files and queue stay.
    sc._listing.clear()
    server._pending_long_video_modes.clear()
    for _ in range(12):
        tick()
        server._retry_pending_one()
    job = sc.load(helper.data, job["id"])
    assert job["state"] == sc.DONE and sc.counts(job)["done"] == 4
    assert len(rows(helper)) == 4
    assert sorted(c[0] for c in helper.calls) == [vid(i) for i in range(4)]


def test_a_live_stream_is_left_out(helper):
    job = make_run(helper, "\n".join([f"https://youtu.be/{vid(0)}", f"https://youtu.be/{vid(1)}"]))
    tick()
    later = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    first = rows(helper)[0]["pending_id"]
    helper.index.mark_pending_running(first)
    helper.index.defer_pending(first, later)            # what the worker does for a live stream
    tick()
    job = sc.load(helper.data, job["id"])
    assert job["episodes"][0]["state"] == sc.EP_FAILED
    assert job["episodes"][0]["reason"] == sc.REASON_LIVE
    assert helper.index.get_pending(first)["status"] == "cancelled"
    assert job["episodes"][1]["state"] == sc.EP_RUNNING


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


@pytest.fixture
def http(helper, monkeypatch):
    real = sc.ensure_listing
    monkeypatch.setattr(sc, "ensure_listing",
                        lambda data_root, job_id, backend, spawn=None: real(
                            data_root, job_id, backend, spawn=inline))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = int(httpd.server_address[1])

    def call(method, path, body=None, *, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Uoink-Token"] = server.TOKEN
        data = json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None)
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                         headers=headers, method=method)
        try:
            with _LOCAL_URLOPEN(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_routes(http, helper):
    status, body = http("POST", "/shows/preview", {"text": LINKS})
    assert status == 202 and body["run"]["state"] == sc.LISTING
    run_id = body["run"]["id"]
    status, body = http("GET", f"/shows/{run_id}")
    assert status == 200 and body["run"]["state"] == sc.READY
    assert body["run"]["counts"]["queued"] == 4 and "episodes" not in body["run"]
    assert body["run"]["estimate"]["to_save"] == 4
    status, body = http("GET", f"/shows/{run_id}?episodes=1")
    assert [e["video_id"] for e in body["run"]["episodes"]] == [vid(i) for i in range(4)]
    assert rows(helper) == []                                  # nothing saved by a preview

    assert http("POST", f"/shows/{run_id}/start", {"asr": "yes"})[0] == 400
    status, body = http("POST", f"/shows/{run_id}/start", {"asr": False})
    assert status == 200 and body["run"]["state"] == sc.RUNNING
    assert http("POST", f"/shows/{run_id}/start")[0] == 409
    status, body = http("POST", f"/shows/{run_id}/pause")
    assert body["run"]["state"] == sc.PAUSED
    status, body = http("POST", f"/shows/{run_id}/resume")
    assert body["run"]["state"] == sc.RUNNING
    assert http("POST", f"/shows/{run_id}/retry-failed")[0] == 409
    assert http("POST", f"/shows/{run_id}/explode")[0] == 404
    assert http("POST", "/shows/show_000000000000/pause")[0] == 404
    assert http("POST", f"/shows/{run_id}/dismiss")[0] == 409
    status, body = http("POST", f"/shows/{run_id}/cancel")
    assert body["run"]["state"] == sc.CANCELLED
    status, body = http("GET", "/shows")
    assert [r["id"] for r in body["runs"]] == [run_id]
    assert http("POST", f"/shows/{run_id}/dismiss")[0] == 200
    assert http("GET", "/shows")[1]["runs"] == []

    assert http("POST", "/shows/preview", {"text": ""})[0] == 400
    assert http("POST", "/shows/preview", {"text": 5})[0] == 400
    assert http("GET", "/shows", token=False)[0] in (401, 403)
    assert http("POST", "/shows/preview", {"text": LINKS}, token=False)[0] in (401, 403)
