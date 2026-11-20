"""Save a whole show (show_capture.py) against fixture sources.

A made-up show ("The Tidepool Hour") with 320 YouTube videos and a 310-item
podcast feed. The backend is a fake with a durable queue, so a "restart"
is a fresh module state and a fresh backend over the same files and queue.
Nothing touches the network, yt-dlp or a model.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import show_capture as sc  # noqa: E402

SHOW = "The Tidepool Hour"
CHANNEL = "https://www.youtube.com/@tidepoolhour"
FEED = "https://feeds.example.com/tidepool.xml"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def vid(i: int) -> str:
    return f"tp{i:09d}"


def channel_entries(n: int = 320) -> list[dict]:
    entries = [{"_type": "url", "ie_key": "Youtube", "id": vid(i),
                "url": f"https://www.youtube.com/watch?v={vid(i)}",
                "title": f"{SHOW} episode {i}", "channel": SHOW,
                "duration": 1800 + i} for i in range(n)]
    if n > 20:
        entries[10]["title"] = "[Private video]"
        entries[11]["title"] = "[Deleted video]"
        entries[20]["live_status"] = "is_upcoming"
        entries.append(dict(entries[5]))      # listed twice
    return entries


def rss(n: int = 310) -> bytes:
    items = []
    for i in range(n):
        enclosure = (f'<enclosure url="https://media.example.com/tidepool/{i}.mp3" '
                     'type="audio/mpeg" length="1"/>') if i != 7 else ""
        items.append(
            f"<item><title>Tidepool {i}</title><guid>tidepool-{i}</guid>"
            f"<pubDate>Mon, 03 Mar 2025 10:00:00 +0000</pubDate>"
            f"<itunes:duration>45:00</itunes:duration>{enclosure}</item>")
    return ('<?xml version="1.0"?><rss version="2.0" '
            'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
            f"<title>{SHOW}</title><link>https://tidepool.example.com</link>"
            + "".join(items) + "</channel></rss>").encode("utf-8")


class Queue:
    """Stands in for the durable pending_yoinks table."""

    def __init__(self):
        self.rows: dict[int, dict] = {}
        self.next_id = 1

    def enqueue(self, url, mode):
        for pid, row in self.rows.items():
            if row["url"] == url and row["status"] in ("pending", "running"):
                return pid
        pid = self.next_id
        self.next_id += 1
        self.rows[pid] = {"url": url, "mode": mode, "status": "pending", "error": None}
        return pid


class FakeBackend:
    def __init__(self, queue: Queue, *, entries=None, feed=None, saved=()):
        self.queue = queue
        self.entries = entries if entries is not None else channel_entries()
        self.feed = feed
        self.saved = set(saved)
        self.busy = False
        self.bot = {"active": False}
        self.asr_message = None
        self.list_calls: list[tuple[int, int]] = []
        self.starts: list[str] = []
        self.cancelled: list[int] = []
        self.script: dict[str, dict] = {}   # key -> forced status
        self.start_error: dict[str, Exception] = {}

    # listing
    def list_youtube(self, url, start, end):
        self.list_calls.append((start, end))
        return {"title": f"{SHOW} - Videos", "entries": self.entries[start - 1:end]}

    def fetch_feed(self, url):
        return self.feed

    def in_library(self, job, ep):
        return ep.get("video_id") in self.saved or ep.get("guid") in self.saved

    def queue_busy(self):
        return self.busy

    def bot_check(self):
        return self.bot

    def asr_problem(self, kind):
        return self.asr_message

    def start_episode(self, job, ep):
        if ep["key"] in self.start_error:
            raise self.start_error[ep["key"]]
        self.starts.append(ep["key"])
        pid = self.queue.enqueue(ep["url"], "transcript_asr" if job.get("asr") else "transcript")
        return {"pending_id": pid}

    def episode_status(self, job, ep):
        if ep["key"] in self.script:
            return self.script[ep["key"]]
        row = self.queue.rows.get(ep.get("pending_id"))
        if row is None:
            return {"state": "done"} if ep.get("video_id") in self.saved else {"state": "lost"}
        if row["status"] == "succeeded":
            return {"state": "done", "video_id": ep.get("video_id")}
        if row["status"] == "failed":
            return {"state": "failed", "reason": row["error"]}
        return {"state": "running"}

    def cancel_episode(self, job, ep):
        self.cancelled.append(ep.get("pending_id"))
        row = self.queue.rows.get(ep.get("pending_id"))
        if row:
            row["status"] = "cancelled"

    # the fake retry worker: settle every pending row
    def work(self, *, fail=None):
        fail = fail or {}
        for row in self.queue.rows.values():
            if row["status"] in ("pending", "running"):
                video_id = row["url"].rsplit("=", 1)[-1]
                if video_id in fail:
                    row["status"], row["error"] = "failed", fail[video_id]
                else:
                    row["status"] = "succeeded"
                    self.saved.add(video_id)


def inline(fn):
    fn()


@pytest.fixture(autouse=True)
def fresh_module_state(monkeypatch):
    monkeypatch.setattr(sc, "_listing", set())


def listed(tmp_path, backend, text=CHANNEL):
    job = sc.create(tmp_path, text)
    assert job["state"] == sc.LISTING
    assert sc.ensure_listing(tmp_path, job["id"], backend, spawn=inline)
    return sc.load(tmp_path, job["id"])


def run(tmp_path, backend, job_id, ticks, *, start=T0, work=True, fail=None):
    now = start
    for _ in range(ticks):
        sc.tick(tmp_path, backend, now=now, spawn=inline)
        if work:
            backend.work(fail=fail)
        now += timedelta(seconds=15)
    return sc.load(tmp_path, job_id)


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, kind, url", [
    ("https://www.youtube.com/@tidepoolhour", sc.KIND_CHANNEL,
     "https://www.youtube.com/@tidepoolhour/videos"),
    ("youtube.com/@tidepoolhour/streams", sc.KIND_CHANNEL,
     "https://www.youtube.com/@tidepoolhour/streams"),
    ("https://www.youtube.com/@tidepoolhour/featured", sc.KIND_CHANNEL,
     "https://www.youtube.com/@tidepoolhour/videos"),
    ("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv", sc.KIND_CHANNEL,
     "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos"),
    ("https://www.youtube.com/playlist?list=PLtidepool0000000001", sc.KIND_PLAYLIST,
     "https://www.youtube.com/playlist?list=PLtidepool0000000001"),
    (FEED, sc.KIND_PODCAST, FEED),
])
def test_classify_sources(text, kind, url):
    spec = sc.classify(text)
    assert spec["kind"] == kind
    assert spec["url"] == url


def test_classify_pasted_links():
    text = "\n".join(f"https://youtu.be/{vid(i)}" for i in range(5)) + "\nnot a link\n"
    spec = sc.classify(text)
    assert spec["kind"] == sc.KIND_URL_LIST
    assert spec["ids"] == [vid(i) for i in range(5)]
    assert spec["lines"] == 6


@pytest.mark.parametrize("text, code", [
    ("", "empty"),
    ("https://www.youtube.com/watch?v=tp000000001", "unsupported"),
    ("https://podcasts.apple.com/us/podcast/tidepool/id1", "unsupported"),
    ("first line\nsecond line", "unsupported"),
    ("ftp://example.com/feed", "invalid_url"),
])
def test_classify_refusals(text, code):
    with pytest.raises(sc.ShowCaptureError) as err:
        sc.classify(text)
    assert err.value.code == code


# ---------------------------------------------------------------------------
# listing and the estimate
# ---------------------------------------------------------------------------

def test_lists_a_320_video_channel_in_windows_and_saves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "LIST_WINDOW", 100)
    backend = FakeBackend(Queue(), saved={vid(1), vid(2)})
    job = listed(tmp_path, backend)
    assert backend.list_calls == [(1, 100), (101, 200), (201, 300), (301, 400)]
    assert job["state"] == sc.READY
    keys = [e["key"] for e in job["episodes"]]
    assert len(keys) == len(set(keys)) == 317       # 321 listed, 2 gone, 1 upcoming, 1 twice
    assert f"yt:{vid(10)}" not in keys and f"yt:{vid(20)}" not in keys
    counts = sc.counts(job)
    assert counts["skipped"] == 2 and counts["queued"] == 315
    estimate = sc.estimate(job)
    assert estimate["to_save"] == 315
    assert estimate["already_saved"] == 2
    assert estimate["durations_known"] == 315
    assert estimate["hours"] == pytest.approx(315 * 45 / 3600, abs=0.06)
    assert estimate["asr_hours_at_most"] == 0
    assert estimate["audio_download_mb_at_most"] == 0
    assert 0 < estimate["disk_mb"] < 100
    # Listing never starts anything, and neither do ticks before Start.
    run(tmp_path, backend, job["id"], 5)
    assert backend.starts == [] and backend.queue.rows == {}
    assert sc.load(tmp_path, job["id"])["state"] == sc.READY


def test_lists_a_310_episode_feed_past_the_poll_cap(tmp_path):
    backend = FakeBackend(Queue(), feed=rss(310), saved={"tidepool-3"})
    job = listed(tmp_path, backend, FEED)
    assert job["title"] == SHOW
    assert len(job["episodes"]) == 310
    no_audio = next(e for e in job["episodes"] if e["guid"] == "tidepool-7")
    assert no_audio["state"] == sc.EP_SKIPPED and no_audio["reason"] == sc.REASON_NO_AUDIO
    saved = next(e for e in job["episodes"] if e["guid"] == "tidepool-3")
    assert saved["reason"] == sc.REASON_ALREADY_SAVED
    estimate = sc.estimate(job)
    assert estimate["to_save"] == 308 and estimate["needs_asr"] is True
    assert estimate["hours"] == pytest.approx(308 * (45 * 12 / 60 + 1) / 60, abs=0.06)
    assert estimate["disk_mb"] > 308 * 45 * 0.9      # podcast audio is kept


def test_pasted_links_note_what_was_left_out(tmp_path):
    text = "\n".join([f"https://www.youtube.com/watch?v={vid(1)}",
                      "https://example.com/not-video",
                      f"https://youtu.be/{vid(2)}"])
    job = listed(tmp_path, FakeBackend(Queue()), text)
    assert [e["video_id"] for e in job["episodes"]] == [vid(1), vid(2)]
    assert job["listing_note"] == "Found 2 YouTube links in 3 lines. Other lines are left out."


def test_a_listing_failure_leaves_a_reason(tmp_path):
    class Broken(FakeBackend):
        def list_youtube(self, url, start, end):
            raise sc.ShowCaptureError("yt-dlp couldn't list that channel.", "fetch_failed")

    job = listed(tmp_path, Broken(Queue()))
    assert job["state"] == sc.FAILED
    assert job["reason"] == "yt-dlp couldn't list that channel."


def test_a_restart_during_listing_lists_again(tmp_path, monkeypatch):
    backend = FakeBackend(Queue(), entries=channel_entries(30))
    job = sc.create(tmp_path, CHANNEL)
    # The helper stopped before the listing ran; the next pass picks it up.
    sc.tick(tmp_path, backend, now=T0, spawn=inline)
    assert sc.load(tmp_path, job["id"])["state"] == sc.READY


# ---------------------------------------------------------------------------
# running a show
# ---------------------------------------------------------------------------

def test_saves_every_episode_one_at_a_time(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(40))
    job = listed(tmp_path, backend)
    total = len(job["episodes"])
    sc.start(tmp_path, job["id"], backend)
    sc.tick(tmp_path, backend, now=T0)
    assert len(backend.starts) == 1
    sc.tick(tmp_path, backend, now=T0)            # still in flight: nothing new
    assert len(backend.starts) == 1
    assert {r["mode"] for r in backend.queue.rows.values()} == {"transcript"}
    job = run(tmp_path, backend, job["id"], total * 2 + 2)
    assert job["state"] == sc.DONE
    assert sc.counts(job)["done"] == total
    assert len(backend.starts) == len(set(backend.starts)) == total


def test_asr_runs_use_the_asr_mode(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(3))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend, asr=True)
    sc.tick(tmp_path, backend, now=T0)
    assert [r["mode"] for r in backend.queue.rows.values()] == ["transcript_asr"]
    assert sc.estimate(sc.load(tmp_path, job["id"]))["asr_hours_at_most"] > 0


def test_kill_and_restart_mid_run_resumes_without_duplicates(tmp_path, monkeypatch):
    queue = Queue()
    backend = FakeBackend(queue, entries=channel_entries(320))
    job = listed(tmp_path, backend)
    total = len(job["episodes"])
    sc.start(tmp_path, job["id"], backend)
    run(tmp_path, backend, job["id"], 41)
    # Kill: one episode is in flight in the durable queue, unfinished.
    sc.tick(tmp_path, backend, now=T0)
    in_flight = [e for e in sc.load(tmp_path, job["id"])["episodes"] if e["state"] == sc.EP_RUNNING]
    assert len(in_flight) == 1
    before = list(backend.starts)
    saved = set(backend.saved)

    # Restart: fresh module state, a fresh backend over the same queue and files.
    monkeypatch.setattr(sc, "_listing", set())
    after = FakeBackend(queue, entries=channel_entries(320), saved=saved)
    job = run(tmp_path, after, job["id"], total * 2 + 4)
    assert job["state"] == sc.DONE
    assert sc.counts(job)["done"] == total
    started = before + after.starts
    assert len(started) == len(set(started)) == total     # nothing started twice
    assert in_flight[0]["key"] not in after.starts          # the in-flight one finished in place
    assert len(queue.rows) == total                          # one queue row per episode


def test_crash_between_queueing_and_recording_does_not_duplicate(tmp_path, monkeypatch):
    queue = Queue()
    backend = FakeBackend(queue, entries=channel_entries(3))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    real_write = sc._write

    def crash(data_root, record):
        if any(e.get("state") == sc.EP_RUNNING for e in record.get("episodes") or []):
            raise KeyboardInterrupt("helper killed")
        return real_write(data_root, record)

    monkeypatch.setattr(sc, "_write", crash)
    with pytest.raises(KeyboardInterrupt):
        sc.tick(tmp_path, backend, now=T0)
    monkeypatch.setattr(sc, "_write", real_write)
    assert len(queue.rows) == 1                      # queued, but the run never recorded it
    assert sc.load(tmp_path, job["id"])["episodes"][0]["state"] == sc.EP_QUEUED
    sc.tick(tmp_path, backend, now=T0)
    assert len(queue.rows) == 1                      # the queue reused its active row


def test_a_lost_queue_row_is_retried_then_failed(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(1))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    key = job["episodes"][0]["key"]
    backend.script[key] = {"state": "lost"}
    job = run(tmp_path, backend, job["id"], 10, work=False)
    ep = job["episodes"][0]
    assert ep["state"] == sc.EP_FAILED and ep["reason"] == sc.REASON_LOST
    assert backend.starts == [key] * sc.MAX_LOST
    assert job["state"] == sc.DONE


def test_failures_keep_their_reasons_and_can_be_retried(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(6))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    reasons = {vid(1): "No captions for this video, and local transcription is off for this save.",
               vid(4): "YouTube kept refusing this one. Try it again later."}
    backend.start_error[f"yt:{vid(2)}"] = sc.EpisodeError("This one is members only.")
    job = run(tmp_path, backend, job["id"], 20, fail=reasons)
    assert job["state"] == sc.DONE
    view = sc.view(job)
    got = {f["video_id"]: f["reason"] for f in view["failures"]}
    assert got == {vid(1): reasons[vid(1)], vid(2): "This one is members only.",
                   vid(4): reasons[vid(4)]}
    assert view["failures_total"] == 3 and view["counts"]["done"] == 3

    backend.start_error.clear()
    job = sc.retry_failed(tmp_path, job["id"], backend, asr=True)
    assert job["state"] == sc.RUNNING and job["asr"] is True
    assert sc.counts(job)["queued"] == 3
    job = run(tmp_path, backend, job["id"], 10)
    assert job["state"] == sc.DONE and sc.counts(job)["done"] == 6


def test_a_start_blocker_pauses_the_run(tmp_path):
    backend = FakeBackend(Queue(), feed=rss(5))
    job = listed(tmp_path, backend, FEED)
    sc.start(tmp_path, job["id"], backend, asr=True)
    blocked = "Set up transcription in Settings first."
    backend.start_error = {e["key"]: sc.RunBlocked(blocked) for e in job["episodes"]}
    sc.tick(tmp_path, backend, now=T0)
    job = sc.load(tmp_path, job["id"])
    assert job["state"] == sc.PAUSED and job["reason"] == blocked
    assert sc.counts(job)["failed"] == 0


# ---------------------------------------------------------------------------
# being polite: bot checks, a busy queue, pause and cancel
# ---------------------------------------------------------------------------

def test_a_bot_check_pauses_the_run_until_it_clears(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(5))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    backend.bot = {"active": True, "seconds_left": 1800}
    for _ in range(4):
        sc.tick(tmp_path, backend, now=T0)
    job = sc.load(tmp_path, job["id"])
    assert backend.starts == []
    assert job["state"] == sc.WAITING and job["reason"] == "bot_check"
    assert job["wait_until"] == "2026-11-01T12:30:00Z"
    # The cooldown ends, but the run still waits out its recorded time
    # (the cooldown itself is not kept across a restart; this is).
    backend.bot = {"active": False}
    sc.tick(tmp_path, backend, now=T0 + timedelta(minutes=10))
    assert backend.starts == []
    sc.tick(tmp_path, backend, now=T0 + timedelta(minutes=31))
    assert len(backend.starts) == 1
    assert sc.load(tmp_path, job["id"])["state"] == sc.RUNNING


def test_a_requeued_bot_check_row_holds_the_run(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(5))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    sc.tick(tmp_path, backend, now=T0)
    first = backend.starts[0]
    backend.script[first] = {"state": "waiting", "reason": "bot_check",
                             "until": "2026-11-01T13:00:00Z"}
    job = run(tmp_path, backend, job["id"], 6, work=False)
    assert backend.starts == [first]
    assert job["state"] == sc.WAITING and job["wait_until"] == "2026-11-01T13:00:00Z"
    del backend.script[first]
    job = run(tmp_path, backend, job["id"], 12)
    assert job["state"] == sc.DONE


def test_podcast_runs_do_not_wait_on_youtube(tmp_path):
    backend = FakeBackend(Queue(), feed=rss(3))
    job = listed(tmp_path, backend, FEED)
    sc.start(tmp_path, job["id"], backend, asr=True)
    backend.bot = {"active": True, "seconds_left": 600}
    sc.tick(tmp_path, backend, now=T0)
    assert len(backend.starts) == 1


def test_a_busy_queue_goes_first(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(3))
    job = listed(tmp_path, backend)
    sc.start(tmp_path, job["id"], backend)
    backend.busy = True
    job = run(tmp_path, backend, job["id"], 3, work=False)
    assert backend.starts == [] and job["reason"] == "queue_busy"
    backend.busy = False
    sc.tick(tmp_path, backend, now=T0)
    assert len(backend.starts) == 1
    assert sc.load(tmp_path, job["id"])["reason"] is None


def test_pause_resume_and_cancel(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(8))
    job = listed(tmp_path, backend)
    with pytest.raises(sc.ShowCaptureError):
        sc.pause(tmp_path, job["id"])                       # not started yet
    sc.start(tmp_path, job["id"], backend)
    with pytest.raises(sc.ShowCaptureError) as err:
        sc.start(tmp_path, job["id"], backend)
    assert err.value.code == "invalid_state"
    run(tmp_path, backend, job["id"], 2)
    sc.pause(tmp_path, job["id"])
    count = len(backend.starts)
    job = run(tmp_path, backend, job["id"], 6)
    assert len(backend.starts) == count and job["state"] == sc.PAUSED
    sc.resume(tmp_path, job["id"])
    sc.tick(tmp_path, backend, now=T0)
    assert len(backend.starts) == count + 1
    job = sc.cancel(tmp_path, job["id"], backend)
    assert job["state"] == sc.CANCELLED
    assert backend.cancelled == [job["episodes"][count]["pending_id"]]
    run(tmp_path, backend, job["id"], 6)
    assert len(backend.starts) == count + 1
    with pytest.raises(sc.ShowCaptureError):
        sc.resume(tmp_path, job["id"])
    sc.dismiss(tmp_path, job["id"])
    assert sc.list_jobs(tmp_path) == []


def test_podcasts_need_local_transcription(tmp_path):
    backend = FakeBackend(Queue(), feed=rss(3))
    job = listed(tmp_path, backend, FEED)
    with pytest.raises(sc.ShowCaptureError) as err:
        sc.start(tmp_path, job["id"], backend)
    assert err.value.code == "needs_asr"
    backend.asr_message = "Set up transcription in Settings first."
    with pytest.raises(sc.ShowCaptureError) as err:
        sc.start(tmp_path, job["id"], backend, asr=True)
    assert err.value.code == "asr_unavailable"
    assert sc.load(tmp_path, job["id"])["state"] == sc.READY


def test_runs_take_turns_and_only_one_episode_is_in_flight(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(4))
    first = listed(tmp_path, backend)
    second = listed(tmp_path, FakeBackend(Queue(), entries=channel_entries(4)),
                    "https://www.youtube.com/playlist?list=PLtidepool0000000001")
    sc.update(tmp_path, second["id"], lambda j: j.update(created_at="2099-01-01T00:00:00Z"))
    sc.start(tmp_path, first["id"], backend)
    sc.start(tmp_path, second["id"], backend)
    sc.tick(tmp_path, backend, now=T0)
    sc.tick(tmp_path, backend, now=T0)
    assert len(backend.starts) == 1
    run(tmp_path, backend, first["id"], 30)
    assert sc.load(tmp_path, first["id"])["state"] == sc.DONE
    # The playlist has the same videos, now all saved: skipped, not saved twice.
    second = sc.load(tmp_path, second["id"])
    assert second["state"] == sc.DONE
    assert sc.counts(second)["skipped"] == 4


def test_records_are_atomic_json_and_ids_are_checked(tmp_path):
    job = sc.create(tmp_path, CHANNEL)
    path = tmp_path / sc.JOB_DIRNAME / f"{job['id']}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == sc.LISTING
    assert not list(path.parent.glob("*.tmp"))
    for bad in ("../secrets", "show_zz", "show_" + "0" * 11):
        with pytest.raises(sc.ShowCaptureError) as err:
            sc.load(tmp_path, bad)
        assert err.value.code == "not_found"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(sc.ShowCaptureError) as err:
        sc.load(tmp_path, job["id"])
    assert err.value.code == "unreadable"
    assert sc.list_jobs(tmp_path) == []


def test_view_is_bounded(tmp_path):
    backend = FakeBackend(Queue(), entries=channel_entries(30))
    job = listed(tmp_path, backend)
    for ep in job["episodes"]:
        ep.update(state=sc.EP_FAILED, reason="Nope.")
    view = sc.view(job, failures_limit=10)
    assert len(view["failures"]) == 10 and view["failures_total"] == 27
    assert "episodes" not in view
    assert len(sc.view(job, episodes=True)["episodes"]) == 27
    assert "_source" not in view and "pending_id" not in view["failures"][0]
