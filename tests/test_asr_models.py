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
    assert asr_models.minutes_per_hour("base", 2) == 16       # fewer threads, slower
    assert asr_models.minutes_per_hour("base", 32) == 4      # four threads at the ceiling
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


def fixture_download(model, root, **kwargs):
    """Run the production verifier and installer using only fixture bytes."""
    import io
    from unittest.mock import patch
    entry = dict(FAKE, id=model)
    def open_fixture(req, **_):
        response = io.BytesIO(FILES[req.full_url.rsplit("/", 1)[1]])
        response.status = 200
        return response
    with patch.dict(asr_models._BY_ID, {model: entry}):
        return _pinned_download(model, root, opener=open_fixture, **kwargs)


_pinned_download = asr_models.download


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
                    self.send_header("Content-Range", getattr(hub, "content_range", f"bytes {start}-{len(data)-1}/{len(data)}"))
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


def test_space_checked_before_first_request(tmp_path, hub, monkeypatch):
    from types import SimpleNamespace
    def space(path):
        assert path == tmp_path
        return SimpleNamespace(free=10)
    monkeypatch.setattr(asr_models.shutil, "disk_usage", space)
    with pytest.raises(OSError, match="space"):
        _download(tmp_path, hub)
    assert not hub.requests


def test_wrong_content_range_keeps_partial(tmp_path, hub):
    hub.cut_after = 23000
    with pytest.raises(Exception):
        _download(tmp_path, hub)
    hub.content_range = "bytes 2-3/4"
    with pytest.raises(ValueError, match="range"):
        _download(tmp_path, hub)
    assert (asr_models._partial_dir(tmp_path, FAKE) / "model.bin.part").stat().st_size == 23000


def test_redirect_policy():
    from urllib.request import Request
    handler = asr_models.ModelRedirectHandler()
    req = Request("https://huggingface.co/model")
    for url in ("http://huggingface.co/file", "https://unrelated.test/file"):
        with pytest.raises(ValueError, match="redirect"):
            handler.redirect_request(req, None, 302, "", {}, url)
    url = "https://cas-bridge.xethub.hf.co/file"
    assert handler.redirect_request(req, None, 302, "", {}, url).full_url == url


def test_core_budget_used_by_loader(monkeypatch):
    monkeypatch.setattr(asr_models, "physical_cores", lambda: 12, raising=False)
    seen = {}
    monkeypatch.setattr(rel, "_import_faster_whisper", lambda: lambda model, **kw: seen.update(kw))
    rel._load_model("base", None)
    assert seen["cpu_threads"] == 4
    assert asr_models.machine()["threads_used"] == seen["cpu_threads"]


def test_turbo_uses_current_repo_and_reads_old_snapshot(tmp_path, monkeypatch):
    from tests.test_asr_worker import _make_snapshot
    model = "large-v3-turbo"
    old = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    new = "dropbox-dash/faster-whisper-large-v3-turbo"
    assert asr_models.get(model)["repo"] == rel._MODEL_REPOSITORIES[model] == new
    _make_snapshot(tmp_path, old)
    (tmp_path / (model + ".pt")).touch()
    calls = []
    monkeypatch.setattr(rel, "_import_faster_whisper", lambda: lambda path, **kw: calls.append(path))
    rel._load_model(model, tmp_path)
    assert Path(calls[0]).is_dir() and "mobiuslabs" in calls[0]
    disk = asr_models.state(model, tmp_path)
    assert disk["state"] == "ready" and disk["bytes_on_disk"] >= 12
    assert asr_models.download(model, tmp_path, opener=lambda *a, **kw: pytest.fail("network"))["ok"]
    assert asr_models.delete(model, tmp_path)["freed_bytes"] >= 12
    assert asr_models.state(model, tmp_path)["state"] == "missing"


def test_repeated_locks_do_not_grow(tmp_path):
    lock = tmp_path / "sample.lock"
    for _ in range(8):
        with asr_models._exclusive(lock):
            pass
    assert lock.stat().st_size <= 1


def test_status_survives_file_disappearing(tmp_path, hub, monkeypatch):
    final = asr_models._snapshot_dir(tmp_path, FAKE) / "config.json"
    final.parent.mkdir(parents=True)
    final.write_bytes(FILES["config.json"])
    original = Path.stat
    def stat(path, *a, **kw):
        if path == final:
            raise FileNotFoundError("concurrent delete")
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, "is_file", lambda p: p == final)
    monkeypatch.setattr(Path, "stat", stat)
    assert asr_models.state("tiny", tmp_path)["state"] == "missing"


def test_configs_and_weights_have_sha256_pins():
    for entry in asr_models.CATALOG:
        for name, (_, algorithm, digest) in entry["files"].items():
            if name != "tokenizer.json" or not entry["english_only"]:
                assert algorithm == "sha256" and HEX64.fullmatch(digest), (entry["id"], name)


def test_legacy_download_buttons_also_verify_the_pinned_files(tmp_path, hub, monkeypatch):
    import types
    import whisper_runner
    # Fail closed if either old entry point tries to start an external download.
    monkeypatch.setattr(rel, "_load_model", lambda *a, **kw: pytest.fail("unverified model loader"))
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", types.SimpleNamespace(
        download_model=lambda *a, **kw: pytest.fail("unverified podcast download")))
    pinned = asr_models.download
    monkeypatch.setattr(asr_models, "download", lambda model, root, **kw:
                        pinned(model, root, base_url=hub.url, timeout=2, **kw))
    destination = tmp_path / "capture"
    result = rel.ensure_model("tiny", destination)
    assert destination.is_dir()
    assert (destination / "tiny.pt").is_file()
    assert result["ready_marker"] == str(destination / "tiny.pt")
    podcast = whisper_runner._download_model_snapshot("tiny", tmp_path / "podcast")
    assert (podcast / "model.bin").read_bytes() == FILES["model.bin"]
    hub.corrupt = True
    with pytest.raises(ValueError, match="checksum"):
        rel.ensure_model("tiny", tmp_path / "broken")
    assert not (tmp_path / "broken" / "tiny.pt").exists()


@pytest.mark.parametrize("host", ["cdn-lfs-us-1.huggingface.co", "cdn-lfs-eu-1.huggingface.co",
                                  "cdn-lfs-ap-1.hf.co", "cas-bridge.xethub.hf.co", "hf.co", "huggingface.co",
                                  "huggingface.co.evil.test", "evil-hf.co"])
def test_download_redirect_hosts(host):
    from urllib.request import Request
    url = "https://" + host + "/file"
    redirect = asr_models.ModelRedirectHandler().redirect_request
    args = (Request("https://huggingface.co/file"), None, 302, "", {}, url)
    if host in ("huggingface.co.evil.test", "evil-hf.co", "hf.co"):
        with pytest.raises(ValueError):
            redirect(*args)
    else:
        assert redirect(*args).full_url == url


@pytest.mark.parametrize("complete", [False, True])
def test_range_416_resume(complete, tmp_path, hub):
    from urllib.error import HTTPError
    from urllib.request import urlopen
    part = asr_models._partial_dir(tmp_path, FAKE) / "model.bin.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(FILES["model.bin"] if complete else FILES["model.bin"][:10])
    ranges = []
    def opener(req, **kw):
        if req.full_url.endswith("model.bin"):
            ranges.append(req.get_header("Range"))
            if ranges[-1]:
                raise HTTPError(req.full_url, 416, "outside range", {}, None)
        return urlopen(req, **kw)
    _download(tmp_path, hub, opener=opener)
    assert ranges == ([] if complete else ["bytes=10-", None])
    assert (asr_models._snapshot_dir(tmp_path, FAKE) / "model.bin").read_bytes() == FILES["model.bin"]


@pytest.mark.parametrize("quota", [False, True])
def test_disk_full_mid_file_cleans_part(quota, monkeypatch, tmp_path, hub):
    import errno
    monkeypatch.setattr(errno, "EDQUOT", 122, raising=False)
    def fail(url, part, size, **kwargs):
        part.write_bytes(b"partial")
        raise OSError(errno.EDQUOT if quota else errno.ENOSPC, "quota")
    monkeypatch.setattr(asr_models, "_fetch", fail)
    with pytest.raises(OSError, match="free disk space"):
        _download(tmp_path, hub)
    assert not list(tmp_path.rglob("*.part"))


def test_physical_cores_honor_topology_affinity_and_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(asr_models.sys, "platform", "linux")
    monkeypatch.setattr(asr_models.os, "process_cpu_count", lambda: 8, raising=False)
    monkeypatch.setattr(asr_models.os, "sched_getaffinity", lambda _: {0, 1, 2, 3}, raising=False)
    for i in range(8):
        path = tmp_path / f"sys/devices/system/cpu/cpu{i}/topology/thread_siblings_list"
        path.parent.mkdir(parents=True)
        path.write_text(f"{i // 2 * 2},{i // 2 * 2 + 1}")
    # Map absolute kernel paths into the fixture. Keep cgroup-relative paths relative.
    monkeypatch.setattr(asr_models, "Path", lambda p: tmp_path / str(p).lstrip("/") if str(p).startswith("/") else Path(p))
    assert asr_models.physical_cores() == 2
    limit = tmp_path / "sys/fs/cgroup/cpu.max"
    limit.parent.mkdir(parents=True)
    limit.write_text("100000 100000")
    assert asr_models.physical_cores() == 1
    assert [asr_models.cpu_threads(c) for c in (1, 2, 4, 8, 64)] == [1, 1, 3, 4, 4]



def test_download_follows_regional_redirect_and_verifies_bytes(tmp_path, monkeypatch):
    from email.message import Message
    from io import BytesIO
    from urllib import request, response
    monkeypatch.setitem(asr_models._BY_ID, "tiny", FAKE)
    seen = []
    class Transport(request.HTTPSHandler):
        def https_open(self, req):
            headers = Message()
            name = req.full_url.rsplit("/", 1)[1]
            if req.full_url.startswith("https://huggingface.co/"):
                headers["Location"] = "https://cdn-lfs-ap-1.hf.co/" + name
                payload, status = b"", 302
            else:
                assert req.full_url == "https://cdn-lfs-ap-1.hf.co/" + name
                seen.append(name)
                payload, status = FILES[name], 200
            result = response.addinfourl(BytesIO(payload), headers, req.full_url, status)
            result.msg = "fixture"
            return result
    build = request.build_opener
    monkeypatch.setattr(request, "build_opener", lambda *handlers: build(Transport(), *handlers))
    assert asr_models.download("tiny", tmp_path)["ok"]
    assert sorted(seen) == sorted(FILES)
    assert asr_models.state("tiny", tmp_path)["state"] == "ready"


def test_turbo_default_hub_cache_is_local_only(tmp_path, monkeypatch):
    import types
    from tests.test_asr_worker import _make_snapshot
    _make_snapshot(tmp_path, asr_models.LEGACY_TURBO_REPO)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", types.SimpleNamespace(HF_HUB_CACHE=str(tmp_path)))
    monkeypatch.setattr(rel, "_import_faster_whisper", lambda: lambda source, **kw: (source, kw))
    source, options = rel._load_model("large-v3-turbo", None)
    assert Path(source).is_dir() and "mobiuslabs" in source
    assert options["local_files_only"]


def test_old_turbo_partial_resumes_from_current_host(tmp_path, monkeypatch, hub):
    model = "large-v3-turbo"
    entry = dict(FAKE, id=model)
    monkeypatch.setitem(asr_models._BY_ID, model, entry)
    old = dict(entry, repo=asr_models.LEGACY_TURBO_REPO)
    part = asr_models._partial_dir(tmp_path, old) / "model.bin.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(FILES["model.bin"][:64])
    assert asr_models.state(model, tmp_path)["bytes_on_disk"] == 64
    asr_models.download(model, tmp_path, base_url=hub.url)
    assert [rng for path, rng in hub.requests if path.endswith("model.bin")] == ["bytes=64-"]
    assert asr_models.state(model, tmp_path)["state"] == "ready"
