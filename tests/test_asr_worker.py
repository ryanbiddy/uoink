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
        media, data_root=os.path.join(work, "data"), model_size="base", diarize=False)
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
    # While the backfill job was paused, a capture used the same child.
    assert out["checkpoint_paused_jobs"] == [1]
    assert out["checkpoint_nested"][0] == [0.0, 2.0, "hello from the child"]
    assert out["pid_after_checkpoint"] == out["pid3"]  # no kill for a pause
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
