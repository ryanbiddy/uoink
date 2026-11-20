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
from datetime import datetime, timedelta, timezone
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


@pytest.mark.parametrize("retry_after", [
    (datetime.now() + timedelta(minutes=20)).isoformat(timespec="seconds"),      # how rows store it
    (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(timespec="seconds"),
])
def test_a_rate_limited_row_holds_youtube_runs_and_says_why(helper, retry_after):
    pending_id, _ = helper.index.enqueue_pending_once(
        "https://www.youtube.com/watch?v=tpwaiting01", 30, server._now_iso(), "transcript")
    with helper.index.write_transaction() as conn:
        conn.execute("UPDATE pending_yoinks SET last_error=?, retry_after=? WHERE pending_id=?",
                     ("youtube_rate_limit: HTTP Error 429", retry_after, pending_id))
    status = server._show_youtube_waiting()
    assert status["active"] is True and status["reason"] == "rate_limited"
    assert 18 * 60 < status["seconds_left"] <= 20 * 60


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


def test_cancel_lets_a_publishing_row_finish_and_records_it(helper):
    job = make_run(helper)
    tick()
    pending_id = rows(helper)[0]["pending_id"]
    helper.index.mark_pending_running(pending_id)
    assert helper.index.mark_pending_publishing(pending_id)    # past the point of no return
    job = sc.cancel(helper.data, job["id"], server._show_backend)
    first = job["episodes"][0]
    assert job["state"] == sc.CANCELLED and first["state"] == sc.EP_RUNNING
    helper.index.mark_pending_succeeded(pending_id, None)
    tick()
    job = sc.load(helper.data, job["id"])
    assert job["episodes"][0]["state"] == sc.EP_DONE
    assert len(rows(helper)) == 1                              # nothing new after cancel


# ---------------------------------------------------------------------------
# Podcast feeds through the real podcast tables
# ---------------------------------------------------------------------------

FEED_URL = "https://feeds.example.com/tidepool.xml"


def podcast_rss(n: int = 6) -> bytes:
    items = "".join(
        f"<item><title>Tidepool {i}</title><guid>tidepool-{i}</guid>"
        f"<link>https://tidepool.example.com/ep/{i}</link>"
        f"<pubDate>Mon, 03 Mar 2025 10:00:00 +0000</pubDate>"
        f'<enclosure url="https://media.example.com/tidepool/{i}.mp3" type="audio/mpeg" length="1"/>'
        "</item>" for i in range(n))
    return (f'<?xml version="1.0"?><rss version="2.0"><channel><title>The Tidepool Hour</title>'
            f"<link>https://tidepool.example.com</link>{items}</channel></rss>").encode("utf-8")


@pytest.fixture
def pod(helper, monkeypatch):
    """Podcast downloads and transcription jobs are fakes; the feed and
    episode tables, the show backend and the scheduler are real. Episode
    threads run only when the test says so (run_threads)."""
    state = SimpleNamespace(downloads=[], transcribed=[], spawned=[], download_error=None,
                            during_download=None)

    def fake_download(idx, episode_id, *, data_root, **_kwargs):
        state.downloads.append(episode_id)
        if state.during_download:
            state.during_download(episode_id)
        if state.download_error:
            return {"ok": False, "episode_id": episode_id, "error": state.download_error}
        return {"ok": True, "episode_id": episode_id, "local_path": "audio.mp3"}

    def fake_transcribe(episode_id, *, model, diarize, consent_given=False, publish_to_corpus=True):
        job_id = f"pod-job-{episode_id}"
        server._jobs[job_id] = {"id": job_id, "kind": "podcast_transcribe", "episode_id": episode_id,
                                "state": "running", "updated_at": server._now_iso()}
        state.transcribed.append(episode_id)
        return {"ok": True, "job_id": job_id}, 202

    def publish(episode_id):
        """What a finished transcription does: a library row, linked."""
        video_id = f"podcast{episode_id:05d}"
        helper.index.upsert_yoink({
            "video_id": video_id, "slug": video_id, "channel": "The Tidepool Hour",
            "title": f"Tidepool {episode_id}", "topic": "Tides", "yoinked_at": "2026-11-20T09:00:00",
            "corpus_path": str(helper.data / f"{video_id}.md"),
            "sidecar_path": str(helper.data / f"{video_id}.json"),
            "metadata_json": "{}", "source_type": "episode", "platform": "podcast",
            "author": "The Tidepool Hour"}, content="tides")
        with helper.index.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET yoink_video_id=? WHERE id=?", (video_id, episode_id))
        server._jobs[f"pod-job-{episode_id}"]["state"] = "completed"
        return video_id

    def run_threads():
        while state.spawned:
            target, args = state.spawned.pop(0)
            target(*args)

    monkeypatch.setattr(server.podcasts, "fetch_feed", lambda row, **_k: (podcast_rss(), {}))
    monkeypatch.setattr(server.podcasts, "download_episode_audio", fake_download)
    monkeypatch.setattr(server.podcasts, "list_episodes",
                        Mock(side_effect=AssertionError("register looks the episode up directly")))
    monkeypatch.setattr(server, "_queue_podcast_transcription", fake_transcribe)
    monkeypatch.setattr(server, "_podcast_suggestion_setup_problem", lambda: None)
    monkeypatch.setattr(server, "_show_spawn", lambda target, *args: state.spawned.append((target, args)))
    monkeypatch.setattr(server, "_show_podcast_runs", {})
    state.publish, state.run_threads = publish, run_threads
    return state


def ptick(now):
    sc.tick(server.DATA_ROOT, server._show_backend, now=now, spawn=inline)


T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def test_a_podcast_show_saves_each_episode_through_the_podcast_job(helper, pod):
    job = make_run(helper, FEED_URL, asr=True)
    assert job["state"] == sc.RUNNING and sc.counts(job)["queued"] == 6
    for step in range(30):
        ptick(T0)
        pod.run_threads()
        for episode_id in list(pod.transcribed):
            if server._jobs[f"pod-job-{episode_id}"]["state"] == "running":
                pod.publish(episode_id)
    job = sc.load(helper.data, job["id"])
    assert job["state"] == sc.DONE and sc.counts(job)["done"] == 6
    assert len(pod.downloads) == len(set(pod.downloads)) == 6     # each once, one at a time
    feed = server._show_podcast_feed(helper.index, FEED_URL)
    assert not feed["enabled"]                                    # the show is not followed
    first = server.podcasts.get_episode(helper.index, pod.downloads[0])
    assert first["guid"] == "tidepool-0"
    assert first["episode_page_url"] == "https://tidepool.example.com/ep/0"
    assert server._show_podcast_runs == {}                        # settled entries are dropped


def test_cancel_during_a_podcast_download_transcribes_nothing(helper, pod):
    job = make_run(helper, FEED_URL, asr=True)
    ptick(T0)
    assert len(pod.spawned) == 1
    assert server._show_backend.queue_busy() is True              # a download in flight
    cancelled = {}

    def cancel_now(_episode_id):
        cancelled["job"] = sc.cancel(helper.data, job["id"], server._show_backend)

    pod.during_download = cancel_now
    pod.run_threads()                                             # cancelled mid-download
    assert cancelled["job"]["state"] == sc.CANCELLED
    assert sc.counts(cancelled["job"])["running"] == 0
    assert len(pod.downloads) == 1 and pod.transcribed == []
    assert server._show_backend.queue_busy() is False
    for _ in range(3):
        ptick(T0)
        pod.run_threads()
    assert len(pod.downloads) == 1                                # nothing new started


def test_cancel_before_the_episode_thread_runs_downloads_nothing(helper, pod):
    job = make_run(helper, FEED_URL, asr=True)
    ptick(T0)
    sc.cancel(helper.data, job["id"], server._show_backend)
    pod.run_threads()
    assert pod.downloads == [] and pod.transcribed == []


def test_cancel_during_a_podcast_transcription_lets_it_finish_and_stops(helper, pod):
    job = make_run(helper, FEED_URL, asr=True)
    ptick(T0)
    pod.run_threads()
    episode_id = pod.transcribed[0]
    job = sc.cancel(helper.data, job["id"], server._show_backend)
    assert job["state"] == sc.CANCELLED and sc.counts(job)["running"] == 1
    ptick(T0)
    pod.run_threads()
    assert pod.downloads == [episode_id]                          # nothing new meanwhile
    pod.publish(episode_id)
    ptick(T0)
    job = sc.load(helper.data, job["id"])
    assert sc.counts(job)["done"] == 1 and sc.counts(job)["running"] == 0
    assert job["state"] == sc.CANCELLED
    ptick(T0)
    pod.run_threads()
    assert pod.downloads == [episode_id]


def test_a_busy_podcast_host_is_backed_off_then_the_run_pauses(helper, pod):
    pod.download_error = "ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests"
    job = make_run(helper, FEED_URL, asr=True)
    now = T0
    waits = []
    for _ in range(sc.MAX_HOST_FAILURES):
        ptick(now)                    # starts the episode
        pod.run_threads()
        ptick(now)                    # records the refusal
        job = sc.load(helper.data, job["id"])
        if job["state"] == sc.WAITING:
            until = sc._parse_iso(job["wait_until"])
            waits.append((until - now).total_seconds())
            ptick(now + timedelta(seconds=30))                    # still waiting: no new request
            pod.run_threads()
            now = until + timedelta(seconds=1)
    assert len(pod.downloads) == sc.MAX_HOST_FAILURES
    assert waits == [120, 240, 480, 960]                          # doubled each time
    assert job["state"] == sc.PAUSED and "5 episodes in a row" in job["reason"]
    assert sc.counts(job)["queued"] == 6 and sc.counts(job)["failed"] == 0
    ptick(now + timedelta(hours=2))
    pod.run_threads()
    assert len(pod.downloads) == sc.MAX_HOST_FAILURES             # paused means paused
    sc.resume(helper.data, job["id"])
    assert sc.load(helper.data, job["id"])["host_failures"] == 0


def test_a_failing_podcast_host_fails_episodes_with_a_reason_then_pauses(helper, pod):
    pod.download_error = "ERROR: HTTP Error 404: Not Found"
    job = make_run(helper, FEED_URL, asr=True)
    now = T0
    for _ in range(12):
        ptick(now)
        pod.run_threads()
        now += timedelta(hours=1)
    job = sc.load(helper.data, job["id"])
    failed = [e for e in job["episodes"] if e["state"] == sc.EP_FAILED]
    assert len(failed) == sc.MAX_HOST_FAILURES == len(pod.downloads)
    assert {e["reason"] for e in failed} == {"Couldn't download the audio from the show's host."}
    assert job["state"] == sc.PAUSED


def test_a_removed_podcast_episode_is_not_saved_again(helper, pod):
    job = make_run(helper, FEED_URL, asr=True)
    ptick(T0)
    pod.run_threads()
    episode_id = pod.transcribed[0]
    video_id = pod.publish(episode_id)
    ptick(T0)
    sc.cancel(helper.data, job["id"], server._show_backend)
    helper.index.soft_delete_yoink(video_id)
    again = make_run(helper, FEED_URL, asr=True)
    first = next(e for e in again["episodes"] if e["guid"] == "tidepool-0")
    assert first["state"] == sc.EP_SKIPPED and first["reason"] == sc.REASON_REMOVED
    # A link to a removed item never reads as done while a new save runs.
    server._show_podcast_runs[episode_id] = {"state": "downloading"}
    status = server._show_backend.episode_status(
        {"kind": sc.KIND_PODCAST}, {"episode_id": episode_id})
    assert status == {"state": "running"}


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
