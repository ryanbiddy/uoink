"""Speech models run in a child process that exits when idle (3.18).

A fresh "helper" Python blocks every heavy runtime import (torch, whisperx,
pyannote, Lightning, CTranslate2, faster-whisper, onnxruntime, PyAV) for its
whole life, turns on offload and runs transcriptions. The child it starts
loads a fake faster-whisper and a fake whisperx from a temp folder, so no
model or inference ever runs. Checks: results come back, the child stays warm
between jobs, a crash is a failed job, a cancel stops the child, and the child
exits after the idle period. Run through safe.sh.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asr_worker  # noqa: E402
import uoink_reliability as rel  # noqa: E402
import whisper_runner  # noqa: E402

FAKE_FASTER_WHISPER = textwrap.dedent('''
    import os, time

    class _Segment:
        def __init__(self, start, end, text):
            self.start, self.end, self.text, self.words = start, end, text, None

    class _Info:
        language = "en"
        language_probability = 0.98
        duration = 4.0

    class WhisperModel:
        def __init__(self, model, **kwargs):
            self.model = str(model)

        def transcribe(self, audio, **kwargs):
            name = os.path.basename(str(audio))
            if "crash" in name:
                os._exit(7)
            if "slow" in name:
                def slow():
                    for i in range(120):
                        time.sleep(0.25)
                        yield _Segment(float(i), float(i) + 1, "still talking")
                return slow(), _Info()
            if "stuck" in name:
                def stuck():
                    time.sleep(60)
                    yield _Segment(0.0, 1.0, "never")
                return stuck(), _Info()
            if "steps" in name:
                return iter([_Segment(float(i), float(i) + 1, "step %d" % i)
                             for i in range(5)]), _Info()
            return iter([_Segment(0.0, 2.0, "hello from the child"),
                         _Segment(2.0, 4.0, "pid %d" % os.getpid())]), _Info()
''')

FAKE_WHISPERX = textwrap.dedent('''
    def load_model(*args, **kwargs):
        raise AssertionError("WhisperX must not run for a transcript-only job")
''')

HARNESS = textwrap.dedent('''
    import json, os, sys, threading, time
    sys.path.insert(0, os.environ["UOINK_TEST_REPO"])
    BLOCK = {"torch", "whisperx", "pyannote", "lightning", "pytorch_lightning",
             "ctranslate2", "faster_whisper", "onnxruntime", "av"}
    attempts = []

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCK:
                attempts.append(name)
                raise ImportError("blocked in the helper: " + name)
            return None

    sys.meta_path.insert(0, Blocker())
    import asr_worker, uoink_reliability as rel, whisper_runner
    startup = list(attempts)
    attempts.clear()
    work = os.environ["UOINK_TEST_WORK"]
    asr_worker.enable_offload(log_dir=work, idle_seconds=1.0)
    out = {"startup_attempts": startup}
    media = os.path.join(work, "clip.wav")
    info = {}
    out["entries"] = [list(e) for e in rel.transcribe_media(
        media, model_name="tiny", model_root=os.path.join(work, "models"), info=info)]
    out["info"] = info
    out["pid1"] = asr_worker.status()["pid"]
    out["state_after_job"] = asr_worker.status()["state"]
    rel.transcribe_media(media, model_name="tiny", model_root=os.path.join(work, "models"))
    out["pid2"] = asr_worker.status()["pid"]
    out["podcast"] = whisper_runner.transcribe_audio(
        media, data_root=os.path.join(work, "data"), model_size="base", diarize=False) if sys.platform != "darwin" else None
    try:
        rel.transcribe_media(os.path.join(work, "crash.wav"), model_name="tiny")
        out["crash"] = None
    except RuntimeError as exc:
        out["crash"] = [type(exc).__name__, str(exc)]
    out["foreground_after_crash"] = asr_worker._slots["foreground"].child is not None
    cancel = threading.Event()
    threading.Timer(1.5, cancel.set).start()
    began = time.monotonic()
    try:
        rel.transcribe_media(os.path.join(work, "slow.wav"), model_name="tiny",
                             cancel_event=cancel)
        out["cancelled"] = False
    except asr_worker.TranscriptionCancelled:
        out["cancelled"] = True
    out["cancel_seconds"] = time.monotonic() - began
    out["foreground_after_cancel"] = asr_worker._slots["foreground"].child is not None
    rel.transcribe_media(media, model_name="tiny")
    out["pid3"] = asr_worker.status()["pid"]

    # Checkpoint (transcript backfill): the job pauses after each segment.
    # At segment 2 a capture runs in its own child. At segment 4 the owner pauses.
    class Paused(Exception):
        pass

    seen, nested = [], {}

    def capture():
        nested["entries"] = [list(e) for e in rel.transcribe_media(media, model_name="tiny")]

    def checkpoint(segment):
        seen.append(segment["end"])
        if len(seen) == 2:
            worker = threading.Thread(target=capture)
            worker.start()
            worker.join(30)
        if len(seen) == 4:
            raise Paused("backfill paused")

    try:
        rel.transcribe_media(os.path.join(work, "steps.wav"), model_name="tiny",
                             checkpoint=checkpoint)
        out["checkpoint_stop"] = None
    except Paused as exc:
        out["checkpoint_stop"] = str(exc)
    out["checkpoint_seen"] = seen
    out["checkpoint_nested"] = nested.get("entries")
    out["background_released"] = asr_worker._slots["background"].child is None
    full = rel.transcribe_media(os.path.join(work, "steps.wav"), model_name="tiny",
                                checkpoint=lambda seg: None)
    out["checkpoint_full"] = [row[2] for row in full]

    # A second background job cannot enter the first job's paused stack.
    outside = threading.Event()
    inside = threading.Event()
    errors = []
    def other_background():
        try:
            rel.transcribe_media(media, model_name="tiny", checkpoint=lambda _: inside.set())
        except Exception as exc:
            errors.append(str(exc))
    bg = threading.Thread(target=other_background)
    def paused_first(_):
        if not outside.is_set():
            outside.set()
            bg.start()
            out["second_entered_while_paused"] = inside.wait(0.4)
    rel.transcribe_media(media, model_name="tiny", checkpoint=paused_first)
    bg.join(10)
    out["both_finished"] = inside.is_set() and not bg.is_alive() and not errors

    # A foreground native stall must not take its parked caller down with it.
    def interrupt_with_stall(segment):
        if "isolated_timeout" in out:
            return
        original = getattr(asr_worker, "_inactivity_seconds", None)
        if original is None:
            out["isolated_timeout"] = "no inactivity watchdog"
            return
        guard = threading.Event()
        timer = threading.Timer(2, guard.set)
        timer.start()
        try:
            asr_worker._inactivity_seconds = lambda *_: 0.5
            rel.transcribe_media(os.path.join(work, "stuck.wav"), model_name="tiny", cancel_event=guard)
        except asr_worker.TranscriptionCancelled:
            out["isolated_timeout"] = "manual cancellation"
        except asr_worker.WorkerCrashed as exc:
            out["isolated_timeout"] = str(exc)
        finally:
            timer.cancel()
            asr_worker._inactivity_seconds = original
    out["surviving_steps"] = len(rel.transcribe_media(os.path.join(work, "steps.wav"),
                                  model_name="tiny", checkpoint=interrupt_with_stall))

    # A child that cannot answer a stop in time is killed.
    stuck = threading.Event()
    threading.Timer(1.0, stuck.set).start()
    try:
        rel.transcribe_media(os.path.join(work, "stuck.wav"), model_name="tiny",
                             cancel_event=stuck)
        out["stuck_cancelled"] = False
    except asr_worker.TranscriptionCancelled:
        out["stuck_cancelled"] = True
    out["stuck_exit"] = asr_worker.status()["last_exit"]
    rel.transcribe_media(media, model_name="tiny")
    out["line_loaded"] = asr_worker.status_line()
    time.sleep(3.0)
    final = asr_worker.status()
    out["final_state"] = final["state"]
    out["final_exit"] = final["last_exit"]
    out["line_idle"] = asr_worker.status_line()
    out["attempts"] = attempts
    out["heavy_in_helper"] = sorted(m for m in sys.modules if m.split(".")[0] in BLOCK)
    print("RESULT " + json.dumps(out))
''')


def _make_snapshot(cache_root: Path, repo_id: str) -> None:
    repo = cache_root / ("models--" + repo_id.replace("/", "--"))
    revision = "a" * 40
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text(revision, encoding="ascii")
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (snapshot / name).write_bytes(b"fake")


@pytest.fixture(scope="module")
def harness_result(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("asr-worker")
    fakes = tmp_path / "fakes"
    (fakes / "faster_whisper").mkdir(parents=True)
    (fakes / "faster_whisper" / "__init__.py").write_text(FAKE_FASTER_WHISPER, encoding="utf-8")
    (fakes / "whisperx").mkdir()
    (fakes / "whisperx" / "__init__.py").write_text(FAKE_WHISPERX, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    for name in ("clip.wav", "crash.wav", "slow.wav", "stuck.wav", "steps.wav"):
        (work / name).write_bytes(b"RIFF fake audio")
    _make_snapshot(work / "data" / "whisper_models" / "base", "Systran/faster-whisper-base")
    script = tmp_path / "helper_harness.py"
    script.write_text(HARNESS, encoding="utf-8")
    env = dict(os.environ, UOINK_TEST_REPO=str(ROOT), UOINK_TEST_WORK=str(work),
               PYTHONPATH=str(fakes))
    env.pop(asr_worker.ENV_CHILD, None)
    done = subprocess.run([sys.executable, "-B", str(script)], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=120,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert done.returncode == 0 and lines, done.stdout + done.stderr
    log = (work / asr_worker.LOG_NAME)
    return json.loads(lines[-1][len("RESULT "):]), (log.read_text("utf-8", "replace") if log.exists() else "")


def test_helper_never_imports_a_model_runtime(harness_result):
    out, _log = harness_result
    assert out["attempts"] == [], out["attempts"]
    assert out["heavy_in_helper"] == []
    # Startup imports nothing heavy either. (On this base whisper_runner still
    # probes `import whisperx` at import; the polish lane's find_spec probe
    # removes that attempt. It is blocked here and loads nothing.)
    assert set(out["startup_attempts"]) <= {"whisperx"}


def test_results_come_back_from_a_warm_child(harness_result):
    out, _log = harness_result
    assert out["entries"][0] == [0.0, 2.0, "hello from the child"]
    assert out["entries"][1][2] == f"pid {out['pid1']}"
    assert out["info"]["language"] == "en"
    assert out["state_after_job"] == "loaded"
    assert out["pid1"] and out["pid1"] == out["pid2"]  # one warm child for back-to-back jobs


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS uses the separately tested native route")
def test_transcript_only_podcast_skips_whisperx(harness_result):
    out, _log = harness_result
    podcast = out["podcast"]
    assert podcast["engine"] == "faster-whisper"
    assert podcast["diarization_ran"] is False
    assert podcast["segments"][0]["text"] == "hello from the child"


def test_a_child_crash_is_a_failed_job(harness_result):
    out, _log = harness_result
    kind, message = out["crash"]
    assert kind == "WorkerCrashed"
    assert "stopped unexpectedly" in message and "exit code 7" in message
    assert not out["foreground_after_crash"]


def test_cancel_reaps_the_job_and_allows_another_save(harness_result):
    out, _log = harness_result
    assert out["cancelled"] is True
    assert out["cancel_seconds"] < 6
    assert not out["foreground_after_cancel"] and out["pid3"]


def test_a_child_that_ignores_a_stop_is_killed(harness_result):
    out, _log = harness_result
    assert out["stuck_cancelled"] is True
    assert out["stuck_exit"]["reason"] == "cancelled"


def test_checkpoint_pauses_between_segments_and_frees_the_engine(harness_result):
    out, _log = harness_result
    # The caller saw segments in order, and its exception stopped the job.
    assert out["checkpoint_seen"] == [1.0, 2.0, 3.0, 4.0]
    assert out["checkpoint_stop"] == "backfill paused"
    # While the backfill job was paused, the foreground capture completed.
    assert out["checkpoint_nested"][0] == [0.0, 2.0, "hello from the child"]
    assert out["background_released"]
    assert out["checkpoint_full"] == [f"step {i}" for i in range(5)]


def test_child_exits_after_the_idle_period(harness_result):
    out, log = harness_result
    assert out["final_state"] == "not_loaded"
    assert out["final_exit"]["reason"] == "idle"
    assert isinstance(out["final_exit"]["code"], int)
    assert out["line_loaded"].startswith("Transcription engine: loaded, frees its memory after 1 minute")
    assert out["line_idle"] == "Transcription engine: idle (not loaded)."
    assert "transcription process start" in log


def test_offload_is_off_unless_a_process_turns_it_on(monkeypatch, tmp_path):
    assert not asr_worker.offload_active()
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")
    rows = rel.transcribe_media(media, _transcribe=lambda _p: [{"start": 0, "end": 1, "text": "x"}])
    assert rows == [(0.0, 1.0, "x")]
    monkeypatch.setenv(asr_worker.ENV_CHILD, "1")
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        assert not asr_worker.offload_active()  # the child never offloads again
    finally:
        asr_worker.disable_offload()


def test_errors_keep_their_type_across_the_process_boundary():
    assert isinstance(asr_worker._rebuild_error({"error_type": "IndexError", "message": "m"}), IndexError)
    assert isinstance(asr_worker._rebuild_error({"error_type": "PermissionError", "message": "m"}),
                      PermissionError)
    assert isinstance(asr_worker._rebuild_error({"error_type": "ReliabilityUnavailableError", "message": "m"}),
                      rel.ReliabilityUnavailableError)
    other = asr_worker._rebuild_error({"error_type": "SomethingNative", "message": "boom"})
    assert type(other) is RuntimeError and str(other) == "boom"
    memory = asr_worker._rebuild_error({"error_type": "MemoryError", "message": ""})
    assert "out of memory" in str(memory)


def test_plain_engine_only_without_speaker_labels(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(whisper_runner, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(whisper_runner.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(whisper_runner, "transcription_engine", lambda: "whisperx")
    assert whisper_runner.plain_engine_for(False) is True
    assert whisper_runner.plain_engine_for(True) is False
    monkeypatch.setattr(whisper_runner, "transcription_engine", lambda: None)
    assert whisper_runner.plain_engine_for(False) is False


def test_status_line_wording():
    assert asr_worker.status_line({"offloaded": True, "state": "not_loaded",
                                   "idle_release_seconds": 120}) == "Transcription engine: idle (not loaded)."
    assert asr_worker.status_line({"offloaded": True, "state": "loaded", "idle_release_seconds": 120}) == (
        "Transcription engine: loaded, frees its memory after 2 minutes idle.")
    assert "working now" in asr_worker.status_line({"offloaded": True, "state": "running",
                                                     "idle_release_seconds": 120})


def test_complete_bounded_frames():
    import io
    class Short(io.BytesIO):
        def write(self, data):
            return super().write(data[:3107])
    stream = Short()
    msg = {"id": "1", "text": "word " * 300000}
    asr_worker._write_frame(stream, msg)
    stream.seek(0)
    assert list(asr_worker._frames(stream)) == [msg]
    with pytest.raises(ValueError):
        list(asr_worker._frames(io.BytesIO(b"x" * 20), limit=10))


def test_inactive_child_fails_just_one_job(monkeypatch, tmp_path):
    import threading
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda *_: 0.25)
        # The fake child accepts the job and emits no progress. Keep the test bounded.
        real_send = asr_worker._send
        stalled = []
        def silent(proc, message):
            if message.get("op") == "quiet":
                stalled.append(proc)
                return
            return real_send(proc, message)
        monkeypatch.setattr(asr_worker, "_send", silent)
        cancel = threading.Event()
        timer = threading.Timer(2, cancel.set)
        timer.start()
        try:
            with pytest.raises(asr_worker.WorkerCrashed, match="progress"):
                asr_worker.call("quiet", {}, cancel_event=cancel)
        finally:
            timer.cancel()
        assert len(stalled) == 1 and stalled[0].returncode is not None
        assert asr_worker._slots["foreground"].child is None
        assert asr_worker.status()["last_exit"]["reason"] == "timeout"
        assert asr_worker.call("ping", {})["pid"]
    finally:
        asr_worker.disable_offload()


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_plain_fast_path_preserves_native_route(monkeypatch, platform):
    from types import SimpleNamespace
    monkeypatch.setattr(whisper_runner, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(whisper_runner, "transcription_engine", lambda: "whisperx")
    monkeypatch.setattr(whisper_runner.importlib.util, "find_spec", lambda _: object())
    assert whisper_runner.plain_engine_for(False) is (platform == "linux")


def test_two_checkpoint_jobs_cannot_nest(harness_result):
    out, _ = harness_result
    assert not out["second_entered_while_paused"] and out["both_finished"]


def test_warm_owner_hands_process_lock_to_next_process(tmp_path):
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    try:
        first = asr_worker.call("ping", {})["pid"]
        script = ("import asr_worker as w, sys; w.enable_offload(log_dir=sys.argv[1]); "
                  "print(w.call('ping', {})['pid'], flush=True); sys.stdin.readline(); w.shutdown()")
        with subprocess.Popen([sys.executable, "-B", "-c", script, str(tmp_path)],
                              cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as other:
            try:
                second = int(other.stdout.readline().strip())
                assert second != first and asr_worker.status()["pid"] is None
            finally:
                other.communicate("\n", timeout=10)
        assert (tmp_path / "asr-foreground.model.lock").stat().st_size <= 1
    finally:
        asr_worker.disable_offload()


def test_local_waiter_does_not_block_idle_handoff(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    slot = asr_worker._slots["foreground"]
    try:
        pid = asr_worker.call("ping", {})["pid"]
        child = slot.child.proc
        path = tmp_path / "asr-foreground.request.lock"
        waiting = threading.Event()
        original = asr_worker._try_file
        def probe(file):
            lease = original(file)
            if file == path and lease is None and threading.current_thread().name.startswith("waiter"):
                waiting.set()
            return lease
        monkeypatch.setattr(asr_worker, "_try_file", probe)
        with ThreadPoolExecutor(1, thread_name_prefix="waiter") as pool:
            with original(path):
                next_job = pool.submit(asr_worker.call, "ping", {})
                assert waiting.wait(2)
                child.wait(timeout=2)  # foreign owner can take the model before dropping its request
            assert next_job.result(5)["pid"] != pid
    finally:
        asr_worker.disable_offload()


def test_idle_child_is_reaped_on_pipe_eof(tmp_path):
    import time
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    try:
        asr_worker.call("ping", {})
        slot = asr_worker._slots["foreground"]
        child = slot.child.proc
        child.kill()
        end = time.monotonic() + 2
        while slot.child is not None and time.monotonic() < end:
            time.sleep(0.02)
        assert slot.child is None and child.returncode is not None
    finally:
        asr_worker.disable_offload()


def test_foreground_timeout_preserves_paused_background_job(harness_result):
    out, _ = harness_result
    assert "progress" in out["isolated_timeout"] and out["surviving_steps"] == 5


class TimedReplies:
    """Advance a fake monotonic clock through scheduled child messages."""

    def __init__(self, monkeypatch, schedule):
        self.now = 0
        self.events = iter(schedule)
        self.next_event = next(self.events, None)
        monkeypatch.setattr(asr_worker, "time", SimpleNamespace(monotonic=lambda: self.now))
        monkeypatch.setattr(asr_worker, "_config", {"closing": False})

    def get(self, timeout):
        # Simulate polling once per minute to cover hours without wall-clock sleeps.
        wake = self.now + (60 if timeout else 0)
        if self.next_event and self.next_event[0] <= wake:
            self.now, message = self.next_event
            self.next_event = next(self.events, None)
            return {"id": "job", **message}
        self.now = wake
        raise asr_worker.queue.Empty


def test_segments_every_twenty_minutes_for_twelve_hours(monkeypatch):
    schedule = [(n * 1200, {"type": "segment", "segment": n}) for n in range(1, 37)]
    replies = TimedReplies(monkeypatch, [*schedule, (12 * 3600, {"type": "result"})])
    monkeypatch.setattr(asr_worker, "_send", lambda *_: None)
    segments = []
    child = SimpleNamespace(messages=replies, proc=object())
    assert asr_worker._await(child, "job", 300, None, None, segments.append)["type"] == "result"
    assert segments == list(range(1, 37))


@pytest.mark.parametrize(("duration", "reported", "limit"), [
    (60, None, 1800), (None, None, 86400), (None, 10800, 43200), (60, 86400, 345600),
])
def test_silent_child_times_out_at_audio_limit(monkeypatch, duration, reported, limit):
    replies = TimedReplies(monkeypatch, [(120, {"type": "phase", "name": "batch transcription",
                                               "duration_seconds": reported})])
    with pytest.raises(asr_worker.WorkerCrashed, match="batch transcription"):
        asr_worker._await(SimpleNamespace(messages=replies), "job", duration, None, None, None)
    assert replies.now == 120 + limit


@pytest.mark.parametrize("podcast", [True, False])
def test_download_bytes_keep_job_alive_for_an_hour(monkeypatch, tmp_path, podcast):
    schedule = []
    def phase(name, **fields):
        schedule.append((fields["downloaded_bytes"] * 1200, {"type": "phase", "name": name, **fields}))
    monkeypatch.setattr(asr_worker, "_phase_callback", phase)
    def download(*args, progress=None, **kwargs):
        for done in (1, 2, 3):
            if progress:
                progress(done, 3)
    monkeypatch.setattr(whisper_runner.asr_models, "download", download)
    if podcast:
        whisper_runner._download_model_snapshot("tiny", tmp_path)
    else:
        rel.ensure_model("tiny", tmp_path)
    replies = TimedReplies(monkeypatch, [*schedule, (3600, {"type": "result"})])
    assert asr_worker._await(SimpleNamespace(messages=replies), "job", 60, None,
                             lambda *_: pytest.fail("bytes sent as audio progress"), None)["type"] == "result"


def test_capture_and_podcast_share_the_same_cached_snapshot(monkeypatch, tmp_path):
    import uoink_reliability as rel
    loads = []
    def load(name, root, **kwargs):
        loads.append(name)
        return object()
    monkeypatch.setattr(rel, "_load_model", load)
    monkeypatch.setattr(rel, "resolve_model", lambda *args: (rel.SOURCE_BUNDLED, tmp_path))
    asr_worker._install_model_cache()
    by_name = rel._load_model("base", None)
    by_path = rel._load_model(str(tmp_path), None)
    assert by_name is by_path and loads == ["base"]


def test_stalled_request_write_has_a_watchdog(monkeypatch, tmp_path):
    import threading
    guard = threading.Event()
    original = asr_worker._send
    def write(proc, message):
        if message.get("op") == "blocked_write":
            if not guard.wait(3):
                raise AssertionError("The caller waited for a blocked pipe")
            return
        return original(proc, message)
    monkeypatch.setattr(asr_worker, "_send", write)
    monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda *_: 0.25)
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        with pytest.raises(asr_worker.WorkerCrashed, match="progress"):
            asr_worker.call("blocked_write", {})
        assert asr_worker.call("ping", {})["pid"]
    finally:
        guard.set()
        asr_worker.disable_offload()


@pytest.mark.parametrize("supports_callback", [True, False])
@pytest.mark.parametrize(("platform", "diarize", "bundled"), [
    ("darwin", False, False), ("darwin", True, True),
    ("linux", True, False), ("win32", True, False),
])
def test_whisperx_pinned_api(monkeypatch, tmp_path, platform, diarize, bundled, supports_callback):
    """Exercise the 3.8.6 call chain and its submodule-only diarizer export."""
    import types
    import _platform
    audio = tmp_path / "clip.wav"
    audio.touch()
    monkeypatch.setattr(whisper_runner, "_WHISPERX_AVAILABLE", True)
    monkeypatch.setattr(whisper_runner, "_runtime_device", lambda: "cpu")
    monkeypatch.setattr(whisper_runner, "_hf_token", lambda: None)
    monkeypatch.setattr(whisper_runner, "sys", types.SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: tmp_path if bundled else None)
    offloaded = platform == "win32"
    monkeypatch.setattr(asr_worker, "in_child", lambda: offloaded)
    decoded_audio = bundled or offloaded
    if decoded_audio:
        import subprocess
        import struct
        monkeypatch.setattr(_platform, "media_binary", lambda name: str(tmp_path / name))

        def decode(command, *, check, capture_output, timeout, **kwargs):
            assert command[0] == str(tmp_path / "ffmpeg") and str(audio) in command
            assert check and capture_output and timeout == (None if offloaded else 600)
            if offloaded and os.name == "nt":
                assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
            import weakref
            nonlocal decoded_ref
            decoded = subprocess.CompletedProcess(command, 0, stdout=struct.pack("<ff", 0.25, -0.5))
            decoded_ref = weakref.ref(decoded)
            return decoded
        monkeypatch.setattr(subprocess, "run", decode)
    monkeypatch.setattr(_platform, "alignment_capability", lambda: {"available": True})
    monkeypatch.setattr(_platform, "require_media", lambda: None)
    monkeypatch.setattr(whisper_runner, "_bundled_snapshot", lambda _: tmp_path)
    stages, phases = [], []
    decoded_ref = None
    def phase(name, **details):
        phases.append(name)
        if name == "batch transcription" and decoded_audio:
            assert details["duration_seconds"] == 2 / 16000
    monkeypatch.setattr(asr_worker, "_phase_callback", phase)

    class Model:
        def transcribe(self, audio, batch_size=None, num_workers=0, language=None, task=None,
                       chunk_size=30, print_progress=False, combined_progress=False,
                       verbose=False, progress_callback=None):
            if decoded_audio:
                assert decoded_ref() is None
                assert audio.tolist() == [0.25, -0.5]
            else:
                assert audio == str(tmp_path / "clip.wav")
            stages.append("transcribe")
            if progress_callback:
                progress_callback(50)
                progress_callback(50)  # a repeated percentage is not forward progress
            return {"language": "en", "segments": [{"start": 0, "end": 1, "text": "Hello"}]}

    def load_model(whisper_arch, device, device_index=0, compute_type="default", asr_options=None,
                   language=None, vad_model=None, vad_method="pyannote", vad_options=None,
                   model=None, task="transcribe", download_root=None, local_files_only=False,
                   threads=4, use_auth_token=None):
        assert whisper_arch == str(tmp_path) and local_files_only and device == "cpu"
        assert asr_options == {"initial_prompt": "Title"}
        stages.append("load")
        model = Model()
        if supports_callback:
            return model
        def transcribe(audio, *, language):
            return model.transcribe(audio, language=language)
        return types.SimpleNamespace(transcribe=transcribe)

    def load_align_model(language_code, device, model_name=None, model_dir=None, model_cache_only=False):
        stages.append("load_align")
        return object(), {"language": language_code}

    def align(transcript, model, align_model_metadata, audio, device, interpolate_method="nearest",
              return_char_alignments=False, print_progress=False, combined_progress=False):
        stages.append("align")
        return {"segments": transcript}

    class Diarizer:
        def __init__(self, model_name=None, token=None, device="cpu", cache_dir=None):
            stages.append("load_diarizer")

        def __call__(self, audio, num_speakers=None, min_speakers=None, max_speakers=None,
                     return_embeddings=False):
            stages.append("diarize")
            return "speaker"

    def assign_word_speakers(diarize_df, transcript_result, speaker_embeddings=None, fill_nearest=False):
        stages.append("assign")
        transcript_result["segments"][0]["speaker"] = diarize_df
        return transcript_result

    fake = types.ModuleType("whisperx")
    fake.load_model, fake.load_align_model, fake.align = load_model, load_align_model, align
    fake.assign_word_speakers = assign_word_speakers
    monkeypatch.setitem(sys.modules, "whisperx", fake)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", types.SimpleNamespace(DiarizationPipeline=Diarizer))
    seen = []
    result = whisper_runner.transcribe_audio(audio, data_root=tmp_path, diarize=diarize,
        initial_prompt="Title", checkpoint=lambda _: None, progress=lambda *args: seen.append(args))
    assert result["diarization_ran"] is diarize
    assert result["segments"][0]["text"] == "Hello"
    assert stages == ["load", "transcribe"] + (
        ["load_align", "align", "load_diarizer", "diarize", "assign"] if diarize else [])
    assert seen == ([(50, 100)] if supports_callback else [])
    assert phases == ["model load"] + (["ffmpeg"] if decoded_audio else []) + ["batch transcription"] + (
        ["alignment", "diarization"] if diarize else [])
    if diarize:
        assert result["segments"][0]["speaker"] == "speaker"


def test_worker_pipe_separates_stdout_and_cleans_numbers(monkeypatch, tmp_path):
    code = """import os, sys
os.write(1, b'during startup\\n')
import asr_worker as w
def noisy(*args):
    os.write(1, b'stray library output\\n')
    os.write(1, b'O' * 2000000)
    os.write(2, b'E' * 2000000)
    print('python library output', flush=True)
    return {'large': 'a' * 1500000, 'nested': [float('inf'), float('nan')], float('nan'): 'invalid key'}
w._run_op = noisy
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", code])
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        value = asr_worker.call("noisy", {})
        assert value == {"large": "a" * 1500000, "nested": [None, None]}
        assert "stray library output" in (tmp_path / asr_worker.LOG_NAME).read_text()
    finally:
        asr_worker.disable_offload()


@pytest.fixture
def fake_engine(tmp_path, monkeypatch):
    # The parent uses the real process launcher, pipes, watchdog and OS ownership.
    script = """import os, subprocess, sys, time
from pathlib import Path
import asr_worker as w

def run(op, args, progress, *controls):
    checkpoint = controls[-1]
    root = Path(args['root']) if 'root' in args else Path(args.get('media_path') or args['audio_path']).parent
    if op == 'silent':
        if hasattr(w, 'report_phase'):
            w.report_phase('alignment')
        wait = ("import sys, time; from pathlib import Path; "
                "end = time.monotonic() + 90\\n"
                "while not Path(sys.argv[1]).exists() and time.monotonic() < end: time.sleep(.05)")
        kid = subprocess.Popen([sys.executable, '-c', wait, str(root / 'cleanup')],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (root / 'pids').write_text(f'{os.getpid()} {kid.pid}')
        time.sleep(90)
    if op == 'segments':
        from types import SimpleNamespace
        import uoink_reliability as rel
        def segments():
            for n in range(12):
                time.sleep(.12)
                yield {'start': n * 900, 'end': (n + 1) * 900, 'text': f'segment {n}'}
        model = SimpleNamespace(transcribe=lambda *a, **kw: (segments(), SimpleNamespace(duration=10800)))
        rel._load_model = lambda *a, **kw: model
        audio = root / 'clip.wav'
        audio.touch()
        return len(rel.transcribe_media(audio, model_name='tiny', progress=progress))
    if op == 'transcribe_media':
        return {'entries': [[0, 1, str(os.getpid())]], 'info': {}}
    if op == 'transcribe_audio':
        with (root / 'starts').open('a') as f:
            f.write(str(os.getpid()) + '\\n')
        checkpoint({'end': 1})
        deadline = time.monotonic() + 12
        while not (root / 'finish').exists() and time.monotonic() < deadline:
            time.sleep(.025)
        checkpoint({'end': 2})
        return {'pid': os.getpid()}
    if op == 'crash':
        os._exit(37)
    if op == 'percent':
        progress(35, 100)
        checkpoint({'percent': 35})
        progress(62, 100)
        checkpoint({'percent': None})
    return os.getpid()
w._run_op = run
w._child_main([])
"""
    command = [sys.executable, "-B", "-c", script]
    monkeypatch.setattr(asr_worker, "_python_command", lambda: command.copy())
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    try:
        yield {"root": str(tmp_path)}, script
    finally:
        (tmp_path / "cleanup").touch()  # also releases the fixture grandchild on a regression
        asr_worker.disable_offload()


def test_sleeping_model_cannot_keep_itself_alive(monkeypatch, tmp_path):
    script = """import time, asr_worker as w
# Accelerate the old timer if a blind pulse is ever reintroduced.
w.HEARTBEAT_SECONDS = .04
def run(op, *args):
    if op == 'sleep':
        time.sleep(2)
    return 'ok'
w._run_op = run
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", script])
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        assert asr_worker.call("warm", {}) == "ok"
        monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda *_: .6)
        with pytest.raises(asr_worker.WorkerCrashed, match="progress"):
            asr_worker.call("sleep", {})
        assert asr_worker.call("next", {}) == "ok"
    finally:
        asr_worker.disable_offload()


def test_idle_watcher_ends_promptly_on_shutdown(fake_engine):
    import threading
    args, _ = fake_engine
    before = set(threading.enumerate())
    asr_worker.call("warm", args)
    watcher, = [t for t in threading.enumerate() if t.name == "asr-idle" and t not in before]
    asr_worker.shutdown()
    watcher.join(1)
    assert not watcher.is_alive()


def test_stdin_watcher_starts_before_isolation(monkeypatch, tmp_path):
    script = """import threading
import asr_worker as w, uoink_install_isolation as isolation
def check(argv):
    assert any(t.name == 'uoink-asr-input' and t.is_alive() for t in threading.enumerate())
isolation.apply_from_process = check
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", script])
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        assert asr_worker.call("ping", {})["pid"]
    finally:
        asr_worker.disable_offload()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object fallback")
@pytest.mark.parametrize("failure", ["create", "assign"])
def test_failed_job_object_still_transcribes_and_reaps_tree(fake_engine, tmp_path, monkeypatch, caplog, failure):
    import library_mirror as mirror
    import threading
    from concurrent.futures import ThreadPoolExecutor
    args, _ = fake_engine
    if failure == "create":
        monkeypatch.setattr(mirror, "_win_create_kill_job", lambda: None)
    else:
        monkeypatch.setattr(mirror, "_win_assign_job", lambda *_: False)
    audio = tmp_path / "clip.wav"
    audio.touch()
    entries = rel.transcribe_media(audio)
    child = asr_worker._slots["foreground"].child
    assert entries[0][2] == str(child.proc.pid)
    assert child.win_job is None
    assert sum("Job Object" in record.message for record in caplog.records) == 1
    event = threading.Event()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(asr_worker.call, "silent", args, cancel_event=event)
        pids = _wait_pids(tmp_path / "pids")
        event.set()
        with pytest.raises(asr_worker.TranscriptionCancelled):
            pending.result(timeout=6)
    _assert_dead(pids)
    assert child.lease.handle.closed
    assert asr_worker._slots["foreground"].child is None


def test_retire_terminates_job_before_close_and_bounds_every_wait(monkeypatch):
    import library_mirror as mirror
    from unittest.mock import Mock
    calls = []
    proc = Mock()
    proc.wait.side_effect = [subprocess.TimeoutExpired("worker", 2), 1]
    child = SimpleNamespace(proc=proc, win_job=123, closed=Mock(), lease=Mock())
    slot = asr_worker._Slot("foreground")
    slot.child = child
    monkeypatch.setattr(asr_worker, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(mirror, "_win_terminate_job", lambda job: calls.append(("terminate", job)))
    monkeypatch.setattr(mirror, "_win_close_handle", lambda job: calls.append(("close", job)))
    asr_worker._retire(slot, child, "cancelled")
    assert calls == [("terminate", 123), ("close", 123)]
    assert all(0 < call.kwargs["timeout"] <= 2 for call in proc.wait.call_args_list)
    proc.kill.assert_called_once_with()
    child.lease.close.assert_called_once_with()


def test_checkpoint_error_releases_model_for_deletion(fake_engine, tmp_path):
    args, _ = fake_engine
    def pause(segment):
        raise ValueError("owner paused backfill")
    with pytest.raises(ValueError, match="owner paused backfill"):
        asr_worker.call("percent", args, background=True, checkpoint=pause)
    with asr_worker.deletion_slot(tmp_path):
        pass
    assert asr_worker.call("next", args, background=True) > 0


def test_long_decode_renews_deadline_with_segments(fake_engine, monkeypatch):
    args, _ = fake_engine
    durations = []
    def limit(duration):
        durations.append(duration)
        return .8
    monkeypatch.setattr(asr_worker, "_inactivity_seconds", limit)
    seen = []
    assert asr_worker.call("segments", args, progress=lambda n, total: seen.append(n)) == 12
    assert seen == [n * 900 for n in range(13)]
    assert durations[0] is None and durations[-1] == 10800


def test_save_runs_during_podcast_without_restarting_either(fake_engine, tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    audio = tmp_path / "clip.wav"
    audio.touch()
    seen = []
    ready = threading.Event()

    def checkpoint(segment):
        seen.append(segment["end"])
        ready.set()

    with ThreadPoolExecutor(2) as pool:
        podcast = pool.submit(whisper_runner.transcribe_audio, audio, data_root=tmp_path, checkpoint=checkpoint)
        try:
            assert ready.wait(5)
            save = int(pool.submit(rel.transcribe_media, audio).result(4)[0][2])
            assert not podcast.done()
            assert int(pool.submit(rel.transcribe_media, audio).result(4)[0][2]) == save
        finally:
            (tmp_path / "finish").touch()
        bg = podcast.result(5)["pid"]
    assert save != bg and seen == [1, 2]
    assert (tmp_path / "starts").read_text().splitlines() == [str(bg)]


def test_each_slot_serves_queued_jobs_fifo(fake_engine):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    args, _ = fake_engine
    for name, slot in asr_worker._slots.items():
        order = []
        ready, release = threading.Event(), threading.Event()
        def run(n):
            def checkpoint(_):
                if n not in order:
                    order.append(n)
                    ready.set()
                    assert release.wait(6)
            return asr_worker.call("percent", args, background=name == "background", checkpoint=checkpoint)
        with ThreadPoolExecutor(4) as pool:
            jobs = [pool.submit(run, 0)]
            assert ready.wait(5)
            try:
                for n in (1, 2, 3):
                    jobs.append(pool.submit(run, n))
                    until = time.monotonic() + 2
                    while len(slot.waiting) != n and time.monotonic() < until:
                        time.sleep(.01)
                    assert len(slot.waiting) == n
            finally:
                release.set()
            assert len({j.result(5) for j in jobs}) == 1
        assert order == [0, 1, 2, 3]


def test_percent_checkpoints_preserve_whisperx_progress(fake_engine):
    args, _ = fake_engine
    seen, checkpoints = [], []
    asr_worker.call("percent", args, progress=lambda *pair: seen.append(pair),
                    checkpoint=checkpoints.append)
    assert seen == [(35, 100), (62, 100)]
    assert checkpoints == [{"percent": 35}, {"percent": None}]


def _wait_pids(path):
    import time
    until = time.monotonic() + 8
    while time.monotonic() < until:
        if path.exists():
            pids = path.read_text().split()
            if len(pids) == 2:
                return [int(pid) for pid in pids]
        time.sleep(.025)
    pytest.fail("silent phase did not start")


def _assert_dead(pids):
    import time
    if os.name == "nt":
        import _winapi
        for pid in pids:
            try:
                handle = _winapi.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            except OSError as exc:
                assert exc.winerror == 87  # process no longer exists
            else:
                try:
                    assert _winapi.WaitForSingleObject(handle, 2000) == 0
                finally:
                    _winapi.CloseHandle(handle)
    else:
        for pid in pids:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                stat = Path(f"/proc/{pid}/stat")
                if stat.exists() and stat.read_text().split(") ")[1].startswith("Z"):
                    break
                time.sleep(.025)
            else:
                pytest.fail(f"descendant {pid} is still running")


@pytest.mark.parametrize("cancel", [False, True], ids=["watchdog", "cancel"])
def test_silent_phase_reaps_tree_and_next_job_works(fake_engine, tmp_path, monkeypatch, cancel):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    args, _ = fake_engine
    event = threading.Event()
    if not cancel:
        asr_worker.call("warm", args)
        monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda *_: .6)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(asr_worker.call, "silent", args, cancel_event=event)
        pids = _wait_pids(tmp_path / "pids")
        started = time.monotonic()
        if cancel:
            event.set()
        with pytest.raises(asr_worker.TranscriptionCancelled if cancel else asr_worker.WorkerCrashed,
                           match="cancelled" if cancel else "progress during alignment"):
            pending.result(timeout=3)
        assert time.monotonic() - started < 3
    _assert_dead(pids)
    assert asr_worker.call("next", args) not in pids


def test_posix_reap_kills_the_group_even_after_leader_exit(monkeypatch):
    import threading
    from types import SimpleNamespace
    from unittest.mock import Mock
    proc = Mock(pid=123, returncode=7)
    proc.wait.return_value = 7
    child = SimpleNamespace(proc=proc, closed=threading.Event(), lease=Mock())
    slot = asr_worker._Slot("background")
    slot.child = child
    killpg = Mock()
    monkeypatch.setattr(asr_worker, "os", SimpleNamespace(name="posix", killpg=killpg))
    monkeypatch.setattr(asr_worker.signal, "SIGKILL", 9, raising=False)
    with slot.condition:
        asr_worker._retire(slot, child, "crashed")
    killpg.assert_called_once_with(proc.pid, 9)
    proc.wait.assert_called_once_with(timeout=2)
    child.lease.close.assert_called_once_with()
    assert slot.child is None and child.closed.is_set()


def test_hard_helper_exit_releases_descendants_and_model_locks(fake_engine, tmp_path):
    args, script = fake_engine
    helper = """import asr_worker as w, sys
w._python_command = lambda: [sys.executable, '-B', '-c', sys.argv[1]]
w.enable_offload(log_dir=sys.argv[2])
w.call('silent', {'root':sys.argv[2]})
"""
    # Target the actual helper interpreter, including when pytest uses a venv launcher.
    env = os.environ.copy()
    executable = sys.executable
    if os.name == "nt" and sys.prefix != sys.base_prefix:
        env["__PYVENV_LAUNCHER__"] = executable
        executable = sys._base_executable
    with subprocess.Popen([executable, "-B", "-c", helper, script, str(tmp_path)], cwd=ROOT, env=env,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as owner:
        try:
            pids = _wait_pids(tmp_path / "pids")
        finally:
            owner.kill()
            owner.wait(timeout=3)
    _assert_dead(pids)
    assert asr_worker.call("next", args) not in pids


def test_broken_request_pipe_reports_a_worker_crash(fake_engine, monkeypatch):
    args, _ = fake_engine
    send = asr_worker._send
    def broken(proc, message):
        if message.get("op") == "broken":
            proc.kill()
            proc.wait()
            raise BrokenPipeError("pipe closed")
        send(proc, message)
    monkeypatch.setattr(asr_worker, "_send", broken)
    with pytest.raises(asr_worker.WorkerCrashed, match="stopped unexpectedly"):
        asr_worker.call("broken", args)
    assert asr_worker.call("next", args) > 0


def test_crash_only_fails_one_request(fake_engine):
    args, _ = fake_engine
    warm = asr_worker.call("next", args)
    with pytest.raises(asr_worker.WorkerCrashed, match="stopped unexpectedly"):
        asr_worker.call("crash", args)
    assert asr_worker.call("next", args) != warm


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_in_process_uses_original_whisperx_route_without_engine_locks(tmp_path, monkeypatch, platform):
    from types import SimpleNamespace
    import _platform
    audio = tmp_path / "input.wav"
    audio.touch()
    monkeypatch.setattr(whisper_runner, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(whisper_runner, "_WHISPERX_AVAILABLE", True)
    monkeypatch.setattr(whisper_runner, "_runtime_device", lambda: "cpu")
    monkeypatch.setattr(_platform, "require_media", lambda: None)
    monkeypatch.setattr(_platform, "alignment_capability", lambda: {"available": True})
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: None)
    monkeypatch.setattr(whisper_runner, "_bundled_snapshot", lambda _: tmp_path)
    monkeypatch.setattr(asr_worker, "_try_file", lambda *_: pytest.fail("locked a direct call"))
    monkeypatch.setattr(asr_worker, "call", lambda *_a, **_k: pytest.fail("offloaded a direct call"))
    monkeypatch.setattr(whisper_runner.importlib.util, "find_spec", lambda _: object())
    calls = []
    def transcribe(path, *, language):
        calls.append((path, language))
        return {"language": "es", "segments": [{"start": 0, "end": 2, "text": "Hola"}]}
    monkeypatch.setitem(sys.modules, "whisperx", SimpleNamespace(
        load_model=lambda *a, **kw: SimpleNamespace(transcribe=transcribe)))
    result = whisper_runner.transcribe_audio(audio, data_root=tmp_path)
    assert calls == [(str(audio), None)]
    assert result["language"] == "es" and result["segments"] == [{"start": 0, "end": 2, "text": "Hola"}]
    assert not list(tmp_path.rglob("*.lock"))
