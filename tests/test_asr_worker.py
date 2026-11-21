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
    out["state_after_crash"] = asr_worker.status()["state"]
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
    out["pid_after_cancel"] = asr_worker.status()["pid"]
    rel.transcribe_media(media, model_name="tiny")
    out["pid3"] = asr_worker.status()["pid"]

    # Checkpoint (transcript backfill): the job pauses after each segment.
    # At segment 2 a "capture" transcribes in the same child while the
    # backfill job is paused; at segment 4 the backfill is told to stop.
    class Paused(Exception):
        pass

    seen, nested, states = [], {}, []

    def capture():
        nested["entries"] = [list(e) for e in rel.transcribe_media(media, model_name="tiny")]

    def checkpoint(segment):
        seen.append(segment["end"])
        if len(seen) == 2:
            states.append(asr_worker.status()["paused_jobs"])
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
    out["checkpoint_paused_jobs"] = states
    out["pid_after_checkpoint"] = asr_worker.status()["pid"]
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
            asr_worker._inactivity_seconds = lambda _: 0.5
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
    asr_worker.STOP_GRACE_SECONDS = 1.0
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
                          capture_output=True, text=True, timeout=120)
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
    assert out["state_after_crash"] == "not_loaded"


def test_cancel_stops_the_job_and_keeps_the_warm_child(harness_result):
    out, _log = harness_result
    assert out["cancelled"] is True
    assert out["cancel_seconds"] < 6
    assert out["pid_after_cancel"] and out["pid_after_cancel"] == out["pid3"]


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
    assert out["checkpoint_paused_jobs"] == [1]
    assert out["checkpoint_nested"][0] == [0.0, 2.0, "hello from the child"]
    assert out["pid_after_checkpoint"] != out["pid3"]  # preemption reclaims the old model
    assert out["checkpoint_full"] == [f"step {i}" for i in range(5)]


def test_child_exits_after_the_idle_period(harness_result):
    out, log = harness_result
    assert out["final_state"] == "not_loaded"
    assert out["final_exit"]["reason"] == "idle"
    assert out["final_exit"]["code"] == 0
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
        monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda duration: 0.25, raising=False)
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
        monkeypatch.setattr(asr_worker, "STOP_GRACE_SECONDS", 0.1)
        try:
            with pytest.raises(asr_worker.WorkerCrashed, match="progress"):
                asr_worker.call("quiet", {}, cancel_event=cancel)
        finally:
            timer.cancel()
        assert len(stalled) == 1 and stalled[0].returncode is not None
        assert asr_worker._proc is None and asr_worker._compute_handle is None
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
        assert (tmp_path / asr_worker.LOCK_NAME).stat().st_size <= 1
    finally:
        asr_worker.disable_offload()


def test_idle_child_is_reaped_on_pipe_eof(tmp_path):
    import time
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    try:
        asr_worker.call("ping", {})
        child = asr_worker._proc
        child.kill()
        end = time.monotonic() + 2
        while asr_worker._proc is child and time.monotonic() < end:
            time.sleep(0.02)
        assert asr_worker._proc is None and child.returncode is not None
    finally:
        asr_worker.disable_offload()


def test_foreground_timeout_preserves_paused_background_job(harness_result):
    out, _ = harness_result
    assert "progress" in out["isolated_timeout"] and out["surviving_steps"] == 5


def test_watchdog_allows_long_silences_with_a_finite_ceiling():
    short = asr_worker._inactivity_seconds(None)
    long = asr_worker._inactivity_seconds(7200)
    assert short == long == asr_worker._inactivity_seconds(86400) == 300
    assert short >= 10 * asr_worker.HEARTBEAT_SECONDS


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
    monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda _: 0.25, raising=False)
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        with pytest.raises(asr_worker.WorkerCrashed, match="progress"):
            asr_worker.call("blocked_write", {})
        assert asr_worker.call("ping", {})["pid"]
    finally:
        guard.set()
        asr_worker.disable_offload()


@pytest.mark.parametrize(("platform", "diarize", "bundled"), [
    ("darwin", False, False), ("darwin", True, True),
    ("linux", True, False), ("win32", True, False),
])
def test_whisperx_pinned_api(monkeypatch, tmp_path, platform, diarize, bundled):
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
    if bundled:
        import subprocess
        import struct
        monkeypatch.setattr(_platform, "media_binary", lambda name: str(tmp_path / name))

        def decode(command, *, check, capture_output, timeout):
            assert command[0] == str(tmp_path / "ffmpeg") and str(audio) in command
            assert check and capture_output and timeout
            return types.SimpleNamespace(stdout=struct.pack("<ff", 0.25, -0.5))
        monkeypatch.setattr(subprocess, "run", decode)
    monkeypatch.setattr(_platform, "alignment_capability", lambda: {"available": True})
    monkeypatch.setattr(_platform, "require_media", lambda: None)
    monkeypatch.setattr(whisper_runner, "_bundled_snapshot", lambda _: tmp_path)
    stages = []

    class Model:
        def transcribe(self, audio, batch_size=None, num_workers=0, language=None, task=None,
                       chunk_size=30, print_progress=False, combined_progress=False,
                       verbose=False, progress_callback=None):
            if bundled:
                assert audio.tolist() == [0.25, -0.5]
            else:
                assert audio == str(tmp_path / "clip.wav")
            stages.append("transcribe")
            if progress_callback:
                progress_callback(50)
            return {"language": "en", "segments": [{"start": 0, "end": 1, "text": "Hello"}]}

    def load_model(whisper_arch, device, device_index=0, compute_type="default", asr_options=None,
                   language=None, vad_model=None, vad_method="pyannote", vad_options=None,
                   model=None, task="transcribe", download_root=None, local_files_only=False,
                   threads=4, use_auth_token=None):
        assert whisper_arch == str(tmp_path) and local_files_only and device == "cpu"
        assert asr_options == {"initial_prompt": "Title"}
        stages.append("load")
        return Model()

    def load_align_model(language_code, device, model_name=None, model_dir=None, model_cache_only=False):
        stages.append("load_align")
        return object(), {"language": language_code}

    def align(transcript, model, align_model_metadata, audio, device, interpolate_method="nearest",
              return_char_alignments=False, print_progress=False, combined_progress=False,
              progress_callback=None):
        stages.append("align")
        return {"segments": transcript}

    class Diarizer:
        def __init__(self, model_name=None, token=None, device="cpu", cache_dir=None):
            stages.append("load_diarizer")

        def __call__(self, audio, num_speakers=None, min_speakers=None, max_speakers=None,
                     return_embeddings=False, progress_callback=None):
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
    assert seen
    if diarize:
        assert result["segments"][0]["speaker"] == "speaker"


def test_worker_pipe_separates_stdout_and_cleans_numbers(monkeypatch, tmp_path):
    code = """import os, sys
os.write(1, b'during startup\\n')
import asr_worker as w
def noisy(*args):
    os.write(1, b'stray library output\\n')
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


def test_child_heartbeat_survives_quiet_decode(monkeypatch, tmp_path):
    code = """import time, asr_worker as w
w.HEARTBEAT_SECONDS = 0.05
def quiet(*args):
    time.sleep(1.3)
    return 'done'
w._run_op = quiet
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", code])
    monkeypatch.setattr(asr_worker, "_inactivity_seconds", lambda _: 0.7)
    asr_worker.enable_offload(log_dir=tmp_path)
    try:
        assert asr_worker.call("quiet", {}) == "done"
    finally:
        asr_worker.disable_offload()



def test_foreground_preempts_running_item_with_bounded_restarts(tmp_path, monkeypatch):
    """Real PIDs and concurrent callers. A third capture waits for this item."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    script = """import time, os, asr_worker as w
def run(op, args, progress, stop, checkpoint):
    if op == 'foreground':
        return os.getpid()
    for i in range(8):
        checkpoint({'end': i + 1})
        time.sleep(.08)
    return 'complete'
w._run_op = run
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", script])
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    reached = threading.Event()
    checkpoints, children = [], []
    def step(seg):
        with asr_worker._state_lock:
            children.append(next(s["proc"] for s in asr_worker._active.values() if s["op"] == "item"))
        checkpoints.append(seg["end"])
        reached.set()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            bg = pool.submit(asr_worker.call, "item", {}, checkpoint=step)
            for i in range(3):
                assert reached.wait(5)
                old = children[-1]
                fg = pool.submit(asr_worker.call, "foreground", {})
                fg.result(timeout=8)
                if i < 2:
                    assert not bg.done() and old.poll() is not None
                else:
                    assert bg.done()
                reached.clear()
            assert bg.result() == "complete" and checkpoints == list(range(1, 9))
    finally:
        asr_worker.disable_offload()


def test_idle_poll_is_cancellable_after_first_tick(tmp_path):
    import time
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    try:
        asr_worker.call("ping", {})
        time.sleep(.4)
        assert asr_worker._idle_timer.is_alive()
        thread = asr_worker._idle_timer
        asr_worker.shutdown()
        thread.join(1)
        assert not thread.is_alive()
    finally:
        asr_worker.disable_offload()


def test_paused_callback_can_wait_for_cross_process_foreground(tmp_path, monkeypatch):
    script = """import os, asr_worker as w
def run(op, args, progress, stop, checkpoint):
    checkpoint({'end': 1})
    return os.getpid()
w._run_op = run
w._child_main([])
"""
    monkeypatch.setattr(asr_worker, "_python_command", lambda: [sys.executable, "-B", "-c", script])
    asr_worker.enable_offload(log_dir=tmp_path, idle_seconds=30)
    retired = []
    def checkpoint(_):
        with asr_worker._state_lock:
            child = next(s["proc"] for s in asr_worker._active.values())
        foreign = ("import sys, asr_worker as w; w.enable_offload(log_dir=sys.argv[1]); "
                   "print(w.call('ping', {})['pid']); w.shutdown()")
        done = subprocess.run([sys.executable, "-B", "-c", foreign, str(tmp_path)], cwd=ROOT,
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert done.returncode == 0 and int(done.stdout) > 0
        assert child.poll() is not None
        retired.append(child.pid)
    try:
        assert asr_worker.call("item", {}, checkpoint=checkpoint) not in retired
        assert len(retired) == 1
    finally:
        asr_worker.disable_offload()


def test_one_shot_preemption_releases_model_and_suppresses_replay(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import _platform
    import uoink_install_isolation as isolation
    monkeypatch.setattr(_platform, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(isolation, "data_root", lambda _: tmp_path)
    requested, running = threading.Event(), threading.Event()
    original_wait = asr_worker._wait_file

    def wait(path, cancel):
        lease = original_wait(path, cancel)
        if path == asr_worker._role_file(tmp_path, False):
            requested.set()
        return lease
    monkeypatch.setattr(asr_worker, "_wait_file", wait)
    checkpoints, models = [], []

    @asr_worker.model_operation
    def transcribe_audio(*, checkpoint):
        models.append("loaded")
        try:
            running.set()
            assert requested.wait(4)
            checkpoint(1)
            checkpoint(2)
        finally:
            models.pop()
        return "complete"

    @asr_worker.model_operation
    def capture():
        assert not models

    with ThreadPoolExecutor(max_workers=2) as pool:
        job = pool.submit(transcribe_audio, checkpoint=checkpoints.append)
        assert running.wait(4)
        pool.submit(capture).result(timeout=5)
        assert job.result(timeout=5) == "complete"
    assert checkpoints == [1, 2]
