"""Model routes and "Re-transcribe with <model>" (3.18).

No real model, no network: transcription and the audio fetch are mocked and
the downloads come from a local fake source. Run through safe.sh.
"""
from __future__ import annotations

import functools
import json
import queue
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
import uoink_reliability as rel  # noqa: E402
from tests.phase4_fixtures import seed_yoink_item  # noqa: E402
from tests.test_asr_models import FAKE, FakeHub  # noqa: E402

VID = "talk0000001"
OLD = [(0.0, 1.0, "old line one"), (1.0, 2.0, "old line two")]


@pytest.fixture
def settings_file(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(server, "_settings_path", lambda: path)
    return path


# ---- model routes ----------------------------------------------------------
@pytest.fixture
def models_root(monkeypatch, tmp_path, settings_file):
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setattr(server, "RELIABILITY_MODEL_ROOT", root)
    monkeypatch.setitem(server.asr_models._BY_ID, "tiny", FAKE)
    monkeypatch.setitem(rel._MODEL_REPOSITORIES, "tiny", FAKE["repo"])
    monkeypatch.setattr(rel, "bundled_model_info", lambda *a, **k: {
        "model": "base", "revision": "0" * 40, "path": str(tmp_path / "no-bundled-copy")})
    monkeypatch.setattr(server, "_asr_downloads", {})
    return root


def _wait_for(model, states=("done", "failed", "cancelled")):
    assert server.asr_models.wait_until(
        lambda: (server._asr_downloads.get(model) or {}).get("state") in states, 20)
    return server._asr_downloads[model]


def test_download_use_and_delete_through_the_helper(models_root, monkeypatch):
    hub = FakeHub()
    try:
        monkeypatch.setattr(server.asr_models, "download", functools.partial(
            server.asr_models.download, base_url=hub.url, timeout=10))
        rows = {row["id"]: row for row in server.asr_models_payload()["models"]}
        assert rows["tiny"]["state"] == "missing" and rows["base"]["state"] == "bundled"
        assert server.use_asr_model("tiny")[1] == 409          # not downloaded yet
        payload, status = server.start_asr_model_download("tiny")
        assert status == 202 and payload["download"]["state"] == "downloading"
        assert "cancel" not in payload["download"]
        assert _wait_for("tiny")["state"] == "done"
        rows = {row["id"]: row for row in server.asr_models_payload()["models"]}
        assert rows["tiny"]["state"] == "ready"
        assert server.use_asr_model("tiny") == ({"ok": True, "model": "tiny", "selected": True}, 200)
        assert server._read_settings()["whisper_model"] == "tiny"
        result, status = server.delete_asr_model("tiny")
        assert status == 200 and result["selected_reset_to"] == "base"
        assert server._read_settings()["whisper_model"] == "base"
        assert server.asr_models.state("tiny", models_root)["state"] == "missing"
    finally:
        hub.close()


def test_cancel_stops_a_download_and_delete_waits_for_it(models_root, monkeypatch):
    started = threading.Event()

    def slow_download(model_id, root, *, cancel_event, progress, **_kw):
        started.set()
        progress(10, 100)
        cancel_event.wait(10)
        raise server.asr_models.DownloadCancelled("download cancelled")

    monkeypatch.setattr(server.asr_models, "download", slow_download)
    server.start_asr_model_download("tiny")
    assert started.wait(5)
    again, status = server.start_asr_model_download("tiny")
    assert status == 202 and again["already_running"] is True
    assert server.delete_asr_model("tiny")[1] == 409
    assert server.cancel_asr_model_download("tiny")[0]["cancelled"] is True
    assert _wait_for("tiny")["state"] == "cancelled"


def _post(path, body, *, token=True):
    import io
    handler = object.__new__(server.Handler)
    handler.path = path
    handler._reject_bad_host = lambda: False
    handler._send_json = lambda status, payload: (status, payload)
    handler._require_token = lambda: token
    raw = json.dumps(body).encode()
    handler.headers = {"Content-Type": "application/json", "Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    return handler.do_POST()


def test_http_routes_are_token_gated_and_reach_the_same_functions(models_root, monkeypatch):
    seen = []
    for name in ("start_asr_model_download", "cancel_asr_model_download", "delete_asr_model", "use_asr_model"):
        monkeypatch.setattr(server, name, lambda model, _n=name: (seen.append((_n, model)) or ({"ok": True}, 200)))
    monkeypatch.setattr(server, "queue_retranscribe", lambda body: (seen.append(("queue", body["video_id"]))
                                                                   or ({"ok": True}, 202)))
    assert _post("/asr/models/download", {"model": "tiny"}, token=False) is None
    assert seen == []
    for action in ("download", "cancel", "delete", "use"):
        assert _post(f"/asr/models/{action}", {"model": "tiny"}) == (200, {"ok": True})
    assert _post("/transcription/retranscribe", {"video_id": VID}) == (202, {"ok": True})
    assert seen == [("start_asr_model_download", "tiny"), ("cancel_asr_model_download", "tiny"),
                    ("delete_asr_model", "tiny"), ("use_asr_model", "tiny"), ("queue", VID)]


def test_cli_models_matches_the_helper(models_root, monkeypatch, capsys):
    import uoink_cli as cli
    hub = FakeHub()
    try:
        monkeypatch.setattr(server.asr_models, "download", functools.partial(
            server.asr_models.download, base_url=hub.url, timeout=10))
        assert cli.main(["models"]) == 0
        listed = json.loads(capsys.readouterr().out)
        assert listed["source"] == "huggingface.co" and {"tiny", "distil-small.en"} <= {
            row["id"] for row in listed["models"]}
        assert cli.main(["models", "use", "tiny"]) == 1          # not downloaded yet
        assert json.loads(capsys.readouterr().out)["model_missing"] is True
        assert cli.main(["models", "download", "tiny"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["ok"] and "huggingface.co" in captured.err
        assert cli.main(["models", "use", "tiny"]) == 0
        assert server._read_settings()["whisper_model"] == "tiny"
        capsys.readouterr()
        assert cli.main(["models", "delete", "tiny"]) == 0
        assert json.loads(capsys.readouterr().out)["selected_reset_to"] == "base"
        assert cli.main(["models", "download"]) == 2               # names no model
    finally:
        hub.close()


def test_model_routes_refuse_unknown_models(models_root):
    for action in (server.start_asr_model_download, server.cancel_asr_model_download,
                   server.delete_asr_model, server.use_asr_model):
        assert action("not-a-model")[1] == 400
        assert action(None)[1] == 400


# ---- Re-transcribe ---------------------------------------------------------
@pytest.fixture
def saved(monkeypatch, tmp_path, settings_file):
    import index
    idx = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    item = seed_yoink_item(idx, tmp_path, video_id=VID, slug=VID, title="Daylight", channel="Example")
    side = {"video_id": VID, "url": "https://www.youtube.com/watch?v=" + VID,
            "transcript_source": "asr", "yoinked_at": "2026-01-01T00:00:00Z",
            "duration_seconds": 9, "source_chapters": [], "title": "Daylight", "channel": "Example"}
    side["transcript"] = server._transcript_entries_with_links(side, OLD)
    corpus = Path(item["corpus_path"])
    sidecar = Path(item["sidecar_path"])
    corpus.write_text("Personal note\n" + server._capture_media_plan(side, tmp_path)["markdown"],
                      encoding="utf-8")
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    server._publish_capture_media(idx, tmp_path, side, corpus, sidecar)
    plain = tmp_path / "transcript.txt"
    plain.write_text("\n".join(t for _s, _e, t in OLD), encoding="utf-8")

    def fake_audio(url, tmp_dir, cancel_event=None):
        path = Path(tmp_dir) / "audio.m4a"
        path.write_bytes(b"audio")
        return path

    calls = []

    def fake_asr(path, **kwargs):
        calls.append(kwargs)
        return [rel.TranscriptEntry(0.0, 1.5, "new line one", [{"word": "new", "start": 0.0, "end": 0.4}]),
                (1.5, 3.0, "new line two")]

    monkeypatch.setattr(server, "_download_reliability_audio", fake_audio)
    monkeypatch.setattr(server, "_media_has_audio", lambda path, cancel=None: True)
    monkeypatch.setattr(server, "_reliability_model_status", lambda name=None: {"cached": True})
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", fake_asr)
    files = {"corpus": corpus, "sidecar": sidecar, "plain": plain}
    before = {name: path.read_bytes() for name, path in files.items()}
    return type("Saved", (), {"idx": idx, "files": files, "before": before, "calls": calls,
                              "folder": tmp_path})


def _unchanged(saved):
    return {name: path.read_bytes() for name, path in saved.files.items()} == saved.before


def test_a_new_transcript_replaces_the_old_one_with_word_timings(saved):
    result = server.retranscribe_item(VID, "small")
    assert result["segments"] == 2 and result["model"] == "small"
    assert saved.calls[0]["model_name"] == "small"
    side = json.loads(saved.files["sidecar"].read_text(encoding="utf-8"))
    assert [row["text"] for row in side["transcript"]] == ["new line one", "new line two"]
    assert side["transcript"][0]["words"] == [{"word": "new", "start": 0.0, "end": 0.4}]
    assert "transcribed again with the small model" in side["transcript_note"]
    assert saved.files["plain"].read_text(encoding="utf-8") == "new line one\nnew line two"
    corpus = saved.files["corpus"].read_text(encoding="utf-8")
    assert corpus.startswith("Personal note") and "new line one" in corpus and "old line one" not in corpus
    backups = list((saved.folder / ".media-inputs").glob("transcript-before-*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_bytes())["transcript"][0]["text"] == "old line one"


def test_a_failed_transcription_keeps_the_old_transcript(saved, monkeypatch):
    def broken(path, **kwargs):
        raise RuntimeError("model crashed halfway")

    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", broken)
    with pytest.raises(ValueError):
        server.retranscribe_item(VID, "small")
    assert _unchanged(saved)


def test_a_failed_save_keeps_the_old_transcript(saved, monkeypatch):
    import library_media

    def refuse(*args, **kwargs):
        raise library_media.MediaError("library_unavailable")

    monkeypatch.setattr(saved.idx, "publish_media_snapshot", refuse)
    with pytest.raises(ValueError, match="old one was kept"):
        server.retranscribe_item(VID, "small")
    assert _unchanged(saved)


def test_an_edited_transcript_file_is_never_overwritten(saved):
    saved.files["plain"].write_text("My own edit", encoding="utf-8")
    saved.before["plain"] = saved.files["plain"].read_bytes()
    with pytest.raises(ValueError, match="edits were kept"):
        server.retranscribe_item(VID, "small")
    assert _unchanged(saved)


def test_cancel_before_saving_keeps_the_old_transcript(saved):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(server.PlaylistJobCancelled):
        server.retranscribe_item(VID, "small", cancel_event=cancel)
    assert _unchanged(saved)


@pytest.fixture
def job_queue(monkeypatch):
    jobs = queue.Queue()
    monkeypatch.setattr(server, "_jobs", {})
    monkeypatch.setattr(server, "_podcast_transcription_queue", jobs)
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", lambda: None)
    return jobs


def test_the_button_route_queues_one_job_on_the_transcription_queue(saved, job_queue):
    payload, status = server.queue_retranscribe({"video_id": VID, "model": "small", "diarize": False})
    assert status == 202 and payload["job"]["kind"] == "retranscribe"
    assert job_queue.get_nowait() == payload["job_id"]
    again, status = server.queue_retranscribe({"video_id": VID, "model": "small"})
    assert status == 202 and again["reused_existing"] and again["job_id"] == payload["job_id"]
    server._run_retranscribe_job(payload["job_id"])
    job = server._public_job(server._jobs[payload["job_id"]])
    assert job["state"] == "completed" and job["model"] == "small" and job["video_id"] == VID
    assert "new line one" in saved.files["plain"].read_text(encoding="utf-8")


def test_a_failed_job_is_reported_and_keeps_the_transcript(saved, job_queue, monkeypatch):
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media",
                        lambda path, **kw: (_ for _ in ()).throw(RuntimeError("child exited")))
    payload, _status = server.queue_retranscribe({"video_id": VID, "model": "small"})
    server._run_retranscribe_job(payload["job_id"])
    job = server._jobs[payload["job_id"]]
    assert job["state"] == "failed" and "unchanged" in job["message"]
    assert _unchanged(saved)


def test_the_route_refuses_missing_items_and_models(saved, job_queue, monkeypatch):
    assert server.queue_retranscribe({"video_id": "nope0000000"})[1] == 404
    assert server.queue_retranscribe({"video_id": VID, "model": "bogus"})[1] == 400
    monkeypatch.setattr(server, "_reliability_model_status", lambda name=None: {"cached": False})
    payload, status = server.queue_retranscribe({"video_id": VID, "model": "small"})
    assert status == 409 and payload["model_missing"]
    assert job_queue.empty()


def test_a_queued_job_comes_back_after_a_restart():
    restored = server._validate_persisted_job({
        "id": "job-1", "kind": "retranscribe", "state": "running", "video_id": VID, "model": "small"})
    assert restored["state"] == "queued" and restored["video_id"] == VID


def test_the_worker_runs_retranscribe_jobs_on_the_same_queue():
    import inspect
    source = inspect.getsource(server._podcast_transcription_worker)
    assert "_run_retranscribe_job(job_id)" in source
