"""Model chooser catalog and the pinned downloader (3.18).

A local fake HTTP source serves made-up model files (no real model, no
network). Run through safe.sh.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asr_models  # noqa: E402
import uoink_reliability as rel  # noqa: E402

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---- catalog ---------------------------------------------------------------
def test_every_model_is_pinned_to_a_revision_with_sizes_and_hashes():
    for entry in asr_models.CATALOG:
        assert HEX40.match(entry["revision"]), entry["id"]
        assert {"model.bin", "config.json", "tokenizer.json"} <= set(entry["files"])
        for name, (size, kind, digest) in entry["files"].items():
            assert size > 0
            assert (kind, bool(HEX64.match(digest) if kind == "sha256" else HEX40.match(digest))) \
                in (("sha256", True), ("git_sha1", True)), (entry["id"], name)
        assert entry["files"]["model.bin"][1] == "sha256"
        assert entry["note"] and len(entry["note"]) < 90


def test_catalog_matches_what_the_loader_reads():
    assert set(asr_models.ids()) == set(rel._MODEL_REPOSITORIES)
    for entry in asr_models.CATALOG:
        assert entry["repo"] == rel._MODEL_REPOSITORIES[entry["id"]]
    assert {e["id"] for e in asr_models.CATALOG if e["english_only"]} == set(rel.ENGLISH_ONLY_MODELS)
    pin = json.loads((ROOT / "scripts" / "whisper_model_pin.json").read_text(encoding="utf-8"))
    base = asr_models.get("base")
    assert base["revision"] == pin["revision"]
    assert {name: (spec["size"], "sha256", spec["sha256"]) for name, spec in pin["files"].items()} \
        == base["files"]


def test_speed_and_recommendation_follow_this_computer():
    assert asr_models.minutes_per_hour("base", 8) == 4
    assert asr_models.minutes_per_hour("base", 2) == 8       # fewer threads, slower
    assert asr_models.minutes_per_hour("base", 32) == 4      # 4 threads is the default ceiling
    order = [asr_models.minutes_per_hour(i, 4) for i in ("tiny", "base", "small", "large")]
    assert order == sorted(order)
    assert asr_models.recommended_english(8) == "distil-large-v3.5"
    assert asr_models.recommended_english(1) == "distil-small.en"
    assert asr_models.speed_copy(22) == "About 22 min per hour of audio"
    assert asr_models.speed_copy(112) == "About 1.9 hours per hour of audio"


def test_listing_marks_bundled_recommended_and_selected(tmp_path):
    data = asr_models.listing(tmp_path, bundled_model="base", selected="small",
                              info={"cpu_cores": 8, "gpu": False, "threads_used": 4})
    rows = {row["id"]: row for row in data["models"]}
    assert data["source"] == "huggingface.co" and data["recommended"] == "distil-large-v3.5"
    assert rows["base"]["state"] == "bundled"
    assert rows["small"]["selected"] and rows["small"]["state"] == "missing"
    assert rows["distil-large-v3.5"]["recommended"]
    assert rows["distil-small.en"]["languages"] == "English only"
    assert rows["large"]["download_mb"] == 3091


# ---- fake Hugging Face -----------------------------------------------------
FILES = {
    "config.json": b'{"fake": true}',
    "tokenizer.json": b'{"tokens": []}',
    "model.bin": bytes(range(256)) * (3 * 4096 + 17),   # about 3 MB
}


def _git_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


FAKE = {
    "id": "tiny", "label": "Fast", "repo": "Example/fake-whisper-tiny",
    "revision": "1" * 40, "english_only": False, "cost": 0.5, "note": "Test model.",
    "files": {
        "config.json": (len(FILES["config.json"]), "git_sha1", _git_sha1(FILES["config.json"])),
        "model.bin": (len(FILES["model.bin"]), "sha256", hashlib.sha256(FILES["model.bin"]).hexdigest()),
        "tokenizer.json": (len(FILES["tokenizer.json"]), "git_sha1", _git_sha1(FILES["tokenizer.json"])),
    },
}


class FakeHub:
    def __init__(self):
        self.requests: list[tuple[str, str | None]] = []
        self.cut_after: int | None = None    # drop model.bin after this many bytes, once
        self.ignore_range = False
        self.corrupt = False
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                name = self.path.rsplit("/", 1)[-1]
                rng = self.headers.get("Range")
                hub.requests.append((self.path, rng))
                if f"/{FAKE['repo']}/resolve/{FAKE['revision']}/" not in self.path or name not in FILES:
                    self.send_error(404)
                    return
                data = FILES[name]
                if hub.corrupt and name == "model.bin":
                    data = b"x" + data[1:]
                start = 0
                if rng and not hub.ignore_range:
                    start = int(rng.split("=")[1].rstrip("-"))
                    self.send_response(206)
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if hub.cut_after is not None and name == "model.bin":
                    cut, hub.cut_after = hub.cut_after, None
                    self.wfile.write(body[:cut])
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setitem(asr_models._BY_ID, "tiny", FAKE)
    server = FakeHub()
    yield server
    server.close()


def _download(root, hub, **kwargs):
    return asr_models.download("tiny", root, base_url=hub.url, timeout=10, **kwargs)


def test_download_verifies_and_installs_the_hub_layout(tmp_path, hub):
    seen = []
    result = _download(tmp_path, hub, progress=lambda done, total: seen.append((done, total)))
    assert result["ok"] and result["bytes"] == sum(map(len, FILES.values()))
    snapshot = tmp_path / "models--Example--fake-whisper-tiny" / "snapshots" / FAKE["revision"]
    assert (snapshot / "model.bin").read_bytes() == FILES["model.bin"]
    assert (tmp_path / "models--Example--fake-whisper-tiny" / "refs" / "main").read_text() == FAKE["revision"]
    assert (tmp_path / "tiny.pt").is_file()
    assert not (tmp_path / "models--Example--fake-whisper-tiny" / asr_models.PARTIAL_DIR).exists()
    assert asr_models.state("tiny", tmp_path)["state"] == "ready"
    assert seen[-1] == (result["bytes"], result["bytes"])
    assert all(b <= t for b, t in seen)


def test_an_interrupted_download_resumes_with_a_range_request(tmp_path, hub):
    hub.cut_after = 1_000_000
    with pytest.raises(Exception):
        _download(tmp_path, hub)
    disk = asr_models.state("tiny", tmp_path)
    assert disk["state"] == "partial" and disk["bytes_on_disk"] >= 1_000_000
    hub.requests.clear()
    _download(tmp_path, hub)
    model_requests = [rng for path, rng in hub.requests if path.endswith("model.bin")]
    assert model_requests == ["bytes=1000000-"]
    assert asr_models.state("tiny", tmp_path)["state"] == "ready"
    snapshot = asr_models._snapshot_dir(tmp_path, FAKE)
    assert (snapshot / "model.bin").read_bytes() == FILES["model.bin"]


def test_cancel_keeps_the_partial_file_and_a_later_download_finishes(tmp_path, hub):
    cancel = threading.Event()

    def progress(done, total):
        if done > 1_500_000:
            cancel.set()

    with pytest.raises(asr_models.DownloadCancelled):
        _download(tmp_path, hub, cancel_event=cancel, progress=progress)
    assert asr_models.state("tiny", tmp_path)["state"] == "partial"
    assert not (tmp_path / "tiny.pt").exists()
    _download(tmp_path, hub)
    assert asr_models.state("tiny", tmp_path)["state"] == "ready"


def test_a_file_that_fails_its_checksum_is_deleted_and_not_ready(tmp_path, hub):
    hub.corrupt = True
    with pytest.raises(ValueError, match="checksum"):
        _download(tmp_path, hub)
    assert not (asr_models._partial_dir(tmp_path, FAKE) / "model.bin.part").exists()
    assert not (asr_models._snapshot_dir(tmp_path, FAKE) / "model.bin").exists()
    assert not rel.is_model_ready("tiny", tmp_path)


def test_a_server_that_ignores_the_range_still_gives_a_correct_file(tmp_path, hub):
    hub.cut_after = 500_000
    with pytest.raises(Exception):
        _download(tmp_path, hub)
    hub.ignore_range = True
    _download(tmp_path, hub)
    assert (asr_models._snapshot_dir(tmp_path, FAKE) / "model.bin").read_bytes() == FILES["model.bin"]


def test_delete_removes_the_model_and_its_marker(tmp_path, hub):
    _download(tmp_path, hub)
    freed = asr_models.delete("tiny", tmp_path)
    assert freed["freed_bytes"] >= sum(map(len, FILES.values()))   # plus refs/main
    assert asr_models.state("tiny", tmp_path)["state"] == "missing"
    assert not (tmp_path / "tiny.pt").exists()
    assert asr_models.delete("tiny", tmp_path)["freed_bytes"] == 0   # deleting twice is fine


def test_two_downloads_of_one_model_never_write_at_once(tmp_path, hub):
    with asr_models._exclusive(tmp_path / ".tiny.download.lock"):
        with pytest.raises(asr_models.DownloadBusy):
            _download(tmp_path, hub)


def test_a_downloaded_model_is_what_the_loader_finds(tmp_path, hub, monkeypatch):
    # The real catalog id "tiny" maps to the real repository name in the
    # loader; point both at the fake one for this check.
    monkeypatch.setitem(rel._MODEL_REPOSITORIES, "tiny", FAKE["repo"])
    _download(tmp_path, hub)
    assert rel.is_model_ready("tiny", tmp_path)
    assert rel._cached_reliability_snapshot(tmp_path, "tiny") == asr_models._snapshot_dir(tmp_path, FAKE)
