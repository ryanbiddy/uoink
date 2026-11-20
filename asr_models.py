"""Speech models Uoink offers, and the pinned model downloader (3.18).

Every choice in the Settings chooser has an exact Hugging Face revision and
the size and hash of each file, a rough speed for this computer (from its
processor count, no benchmark), its language coverage and a one-line note.

``download`` fetches one model from huggingface.co only when a person asks:
it resumes an interrupted file with an HTTP Range request, verifies every
file (SHA-256 for model weights, the git blob hash for small files) before
it counts, can be cancelled at any point (the partial file stays for a
resume) and writes the same Hub cache layout faster-whisper reads offline:
``<root>/models--<org>--<name>/{refs/main, snapshots/<revision>/<files>}``
plus the ``<model>.pt`` ready marker uoink_reliability checks. The bundled
base model ships with the app and is never downloaded or deleted here.

No model library is imported: this is plain HTTP and file work, safe in the
long-lived helper.
"""
from __future__ import annotations

import hashlib
import http.client
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

HF_BASE = "https://huggingface.co"
PARTIAL_DIR = ".uoink-partial"
READY_TEXT = "Uoink faster-whisper model ready\n"
_CHUNK = 1 << 20

# Rough minutes of processing per hour of audio for the bundled base model on
# a computer with 4 or more cores (int8 on the processor, one beam, voice
# detection and word timings on). faster-whisper uses 4 threads by default,
# so more cores than that do not make Uoink faster. Relative costs per model
# come from their published encoder/decoder sizes. Rough by design.
BASE_MINUTES_PER_HOUR = 4.0
_THREADS_USED = 4
RECOMMEND_MAX_MINUTES = 30

S, G = "sha256", "git_sha1"

# Order = how the chooser lists them, smallest first.
CATALOG: tuple[dict, ...] = (
    {"id": "tiny", "label": "Fast", "repo": "Systran/faster-whisper-tiny",
     "revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
     "english_only": False, "cost": 0.5,
     "note": "Quickest, and it misses the most words.",
     "files": {"config.json": (2249, G, "3baa18e2b321a2f489614607852a729fcd516480"),
               "model.bin": (75538270, S, "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"),
               "tokenizer.json": (2203239, G, "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
               "vocabulary.txt": (459861, G, "c9074644d9d1205686f16d411564729461324b75")}},
    {"id": "base", "label": "Balanced", "repo": "Systran/faster-whisper-base",
     "revision": "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
     "english_only": False, "cost": 1.0,
     "note": "Comes with Uoink. Good on clear speech, weaker on names and jargon.",
     "files": {"config.json": (2309, S, "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a"),
               "model.bin": (145217532, S, "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"),
               "tokenizer.json": (2203239, S, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
               "vocabulary.txt": (459861, S, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}},
    {"id": "distil-small.en", "label": "English, quick",
     "repo": "Systran/faster-distil-whisper-small.en",
     "revision": "ef77d90526ccd62cde3808ee70626a01e5cf83e4",
     "english_only": True, "cost": 1.6,
     "note": "Clearer English than Balanced at a similar speed.",
     "files": {"config.json": (2812, G, "cab338fd7cd3a2f484ee8ece80d3c63964d47c4a"),
               "model.bin": (332308257, S, "1187de3982cdcf962a2fb8f797e429fb4651b875b18fe9ce50b58b52fc9072b7"),
               "preprocessor_config.json": (339, G, "91876762a536a746d268353c5cba57286e76b058"),
               "tokenizer.json": (2405466, G, "d7cd7ef030d38ff11df010adc96a29e3a0222151"),
               "vocabulary.json": (825480, G, "b9bc6c16dcfbfc54ab235b55e079d4311f97edf5")}},
    {"id": "small", "label": "Careful", "repo": "Systran/faster-whisper-small",
     "revision": "536b0662742c02347bc0e980a01041f333bce120",
     "english_only": False, "cost": 2.6,
     "note": "A solid step up for any language.",
     "files": {"config.json": (2370, G, "e5047537059bd8f182d9ca64c470201585015187"),
               "model.bin": (483546902, S, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
               "tokenizer.json": (2203239, G, "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
               "vocabulary.txt": (459861, G, "c9074644d9d1205686f16d411564729461324b75")}},
    {"id": "distil-large-v3.5", "label": "English, best",
     "repo": "distil-whisper/distil-large-v3.5-ct2",
     "revision": "9793ccc07920e0f830e1dba0343efcdf0ef8c903",
     "english_only": True, "cost": 5.5,
     "note": "Close to Max accuracy on English, in a fraction of the time.",
     "files": {"config.json": (2690, G, "499468d516090aee836412556ca759be4e9e73f7"),
               "model.bin": (1512927867, S, "c58b88b8585ffcd2135fddaaf421ce72cb223b32edea70d156aed1dea319a119"),
               "preprocessor_config.json": (340, G, "931c77a740890c46365c7ae0c9d350ba3cca908f"),
               "tokenizer.json": (2480645, G, "e08f6459ce450dc8547e6acb2e42fd724f082632"),
               "vocabulary.json": (1068114, G, "0adcd01e7c237205d593b707e66dd5d7bc785d2d")}},
    {"id": "large-v3-turbo", "label": "Turbo",
     # faster-whisper looks this model up under its original name; the files
     # now live under the renamed repository (Hugging Face redirects too).
     "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
     "source_repo": "dropbox-dash/faster-whisper-large-v3-turbo",
     "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
     "english_only": False, "cost": 6.0,
     "note": "Near Max accuracy in any language, much faster than it.",
     "files": {"config.json": (2263, G, "0351d1d6870005e865747b781b5d7c23ea0459cd"),
               "model.bin": (1617884929, S, "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
               "preprocessor_config.json": (340, G, "931c77a740890c46365c7ae0c9d350ba3cca908f"),
               "tokenizer.json": (2710337, G, "17456db595adc78a973f97d69d8cb50bc87c0b1c"),
               "vocabulary.json": (1068114, G, "0adcd01e7c237205d593b707e66dd5d7bc785d2d")}},
    {"id": "medium", "label": "Deep", "repo": "Systran/faster-whisper-medium",
     "revision": "08e178d48790749d25932bbc082711ddcfdfbc4f",
     "english_only": False, "cost": 7.0,
     "note": "Strong on accents and noisy rooms, and slow.",
     "files": {"config.json": (2257, G, "242aa06a480a7b5509375c645097e87af5136774"),
               "model.bin": (1527906378, S, "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae"),
               "tokenizer.json": (2203239, G, "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
               "vocabulary.txt": (459861, G, "c9074644d9d1205686f16d411564729461324b75")}},
    {"id": "large", "label": "Max accuracy", "repo": "Systran/faster-whisper-large-v3",
     "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
     "english_only": False, "cost": 14.0,
     "note": "The most accurate in any language, and the slowest.",
     "files": {"config.json": (2394, G, "75336feae814999bae6ccccdecf177639ffc6f9d"),
               "model.bin": (3087284237, S, "69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1"),
               "preprocessor_config.json": (340, G, "931c77a740890c46365c7ae0c9d350ba3cca908f"),
               "tokenizer.json": (2480617, G, "3a5e2ba63acdcac9a19ba56cf9bd27f185bfff61"),
               "vocabulary.json": (1068114, G, "0adcd01e7c237205d593b707e66dd5d7bc785d2d")}},
)
_BY_ID = {entry["id"]: entry for entry in CATALOG}


class DownloadCancelled(Exception):
    """The person cancelled; finished files and the partial file are kept."""


class DownloadBusy(RuntimeError):
    """Another Uoink process is downloading this model right now."""


def get(model_id: object) -> dict:
    entry = _BY_ID.get(str(model_id or "").strip().lower())
    if entry is None:
        raise ValueError(f"unknown model: {model_id!r}")
    return entry


def ids() -> list[str]:
    return [entry["id"] for entry in CATALOG]


def total_bytes(model_id: str) -> int:
    return sum(size for size, _kind, _digest in get(model_id)["files"].values())


# ---- this computer ---------------------------------------------------------
def machine() -> dict:
    """Processor count and whether a graphics card is visible. Read only:
    no benchmark, no process started."""
    cores = os.cpu_count() or 1
    gpu = bool(shutil.which("nvidia-smi"))
    return {"cpu_cores": cores, "gpu": gpu, "threads_used": min(cores, _THREADS_USED)}


def minutes_per_hour(model_id: str, cores: int) -> int:
    threads = max(1, min(int(cores or 1), _THREADS_USED))
    minutes = BASE_MINUTES_PER_HOUR * get(model_id)["cost"] * (_THREADS_USED / threads)
    return max(1, round(minutes))


def speed_copy(minutes: int) -> str:
    if minutes <= 60:
        return f"About {minutes} min per hour of audio"
    return f"About {minutes / 60:.1f} hours per hour of audio"


def recommended_english(cores: int) -> str:
    """'Best for English on this computer': the most accurate English model
    that still finishes an hour of audio in RECOMMEND_MAX_MINUTES."""
    best = "distil-large-v3.5"
    return best if minutes_per_hour(best, cores) <= RECOMMEND_MAX_MINUTES else "distil-small.en"


# ---- files on disk ---------------------------------------------------------
def _repo_dir(root: Path, entry: dict) -> Path:
    return Path(root) / ("models--" + entry["repo"].replace("/", "--"))


def _snapshot_dir(root: Path, entry: dict) -> Path:
    return _repo_dir(root, entry) / "snapshots" / entry["revision"]


def _partial_dir(root: Path, entry: dict) -> Path:
    return _repo_dir(root, entry) / PARTIAL_DIR / entry["revision"]


def _marker(root: Path, entry: dict) -> Path:
    return Path(root) / f"{entry['id']}.pt"


def _digest_of(path: Path, kind: str, size: int, cancel_event=None) -> str:
    digest = hashlib.sha256() if kind == S else hashlib.sha1(b"blob %d\0" % size)
    with path.open("rb") as handle:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled("download cancelled")
            block = handle.read(_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _file_ok(path: Path, size: int, kind: str, digest: str, cancel_event=None) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
    except OSError:
        return False
    return _digest_of(path, kind, size, cancel_event) == digest


def state(model_id: str, root: Path) -> dict:
    """What is on disk for one model: ready (pinned revision complete with
    its marker), partial (some bytes kept for a resume) or missing. Cheap:
    sizes and the marker only, no hashing."""
    entry = get(model_id)
    root = Path(root)
    snapshot, partial = _snapshot_dir(root, entry), _partial_dir(root, entry)
    have = 0
    complete = True
    for name, (size, _kind, _digest) in entry["files"].items():
        final = snapshot / name
        if final.is_file() and final.stat().st_size == size:
            have += size
            continue
        complete = False
        part = partial / (name + ".part")
        if part.is_file():
            have += min(part.stat().st_size, size)
    ref = _repo_dir(root, entry) / "refs" / "main"
    try:
        pinned = ref.read_text(encoding="ascii").strip() == entry["revision"]
    except OSError:
        pinned = False
    ready = complete and pinned and _marker(root, entry).is_file()
    total = total_bytes(model_id)
    return {"state": "ready" if ready else ("partial" if have else "missing"),
            "bytes_on_disk": have if not ready else total, "total_bytes": total}


@contextmanager
def _exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DownloadBusy("This model is already downloading.") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DownloadBusy("This model is already downloading.") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()


def _fetch(url: str, part: Path, size: int, *, cancel_event, on_bytes, opener, timeout) -> None:
    have = part.stat().st_size if part.is_file() else 0
    if have > size:
        part.unlink()
        have = 0
    if have == size:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Uoink model download"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    try:
        response = opener(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:   # nothing left to send: verify what is here
            return
        raise
    with response:
        status = getattr(response, "status", None) or response.getcode()
        mode = "ab"
        if have and status != 206:     # the server ignored the range: start over
            mode, have = "wb", 0
            on_bytes(-part.stat().st_size)
        with part.open(mode) as out:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise DownloadCancelled("download cancelled")
                try:
                    block = response.read(_CHUNK)
                except http.client.IncompleteRead as exc:
                    # The connection dropped mid-read: keep what arrived so
                    # the next try resumes from exactly here.
                    if exc.partial and have + len(exc.partial) <= size:
                        out.write(exc.partial)
                        on_bytes(len(exc.partial))
                    raise
                if not block:
                    break
                if have + len(block) > size:
                    raise ValueError("The download is larger than the published file.")
                out.write(block)
                have += len(block)
                on_bytes(len(block))
    if have < size:
        # The server closed early. Keep the bytes; the next try resumes.
        raise ConnectionError("The download stopped early. Try again to resume it.")


def download(model_id: str, root: str | Path, *, cancel_event: threading.Event | None = None,
             progress: Callable[[int, int], None] | None = None, base_url: str = HF_BASE,
             opener=urllib.request.urlopen, timeout: float = 60.0) -> dict:
    """Fetch, verify and install one pinned model. Safe to call again after
    a cancel or a crash: finished files are kept and partial ones resume."""
    entry = get(model_id)
    root = Path(root)
    snapshot, partial = _snapshot_dir(root, entry), _partial_dir(root, entry)
    total = total_bytes(model_id)
    source = entry.get("source_repo") or entry["repo"]
    lock = root / f".{entry['id']}.download.lock"
    with _exclusive(lock):
        snapshot.mkdir(parents=True, exist_ok=True)
        partial.mkdir(parents=True, exist_ok=True)
        done = [0]

        def report(delta: int) -> None:
            done[0] += delta
            if progress is not None:
                try:
                    progress(max(0, done[0]), total)
                except Exception:  # noqa: BLE001 - a display never fails a download
                    pass

        for name, (size, _kind, _digest) in entry["files"].items():
            final, part = snapshot / name, partial / (name + ".part")
            if final.is_file() and final.stat().st_size == size:
                report(size)
            elif part.is_file():
                report(min(part.stat().st_size, size))
        for name, (size, kind, digest) in entry["files"].items():
            final, part = snapshot / name, partial / (name + ".part")
            if final.is_file() and final.stat().st_size == size:
                if _file_ok(final, size, kind, digest, cancel_event):
                    continue
                report(-size)
                final.unlink()
            url = f"{base_url.rstrip('/')}/{source}/resolve/{entry['revision']}/{name}"
            _fetch(url, part, size, cancel_event=cancel_event, on_bytes=report,
                   opener=opener, timeout=timeout)
            if not _file_ok(part, size, kind, digest, cancel_event):
                report(-(part.stat().st_size if part.is_file() else 0))
                part.unlink(missing_ok=True)
                raise ValueError(
                    f"{name} did not match its published checksum, so Uoink deleted it. "
                    "Try the download again.")
            os.replace(part, final)
        refs = _repo_dir(root, entry) / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        tmp = refs / "main.tmp"
        tmp.write_text(entry["revision"], encoding="ascii")
        os.replace(tmp, refs / "main")
        _marker(root, entry).write_text(READY_TEXT, encoding="utf-8")
        shutil.rmtree(_repo_dir(root, entry) / PARTIAL_DIR, ignore_errors=True)
    return {"ok": True, "model": entry["id"], "revision": entry["revision"], "bytes": total}


def delete(model_id: str, root: str | Path) -> dict:
    """Remove a downloaded model (and any partial download). The bundled copy
    lives in the app folder and is untouched."""
    entry = get(model_id)
    root = Path(root)
    repo = _repo_dir(root, entry)
    with _exclusive(root / f".{entry['id']}.download.lock"):
        freed = 0
        if repo.is_dir():
            for path in repo.rglob("*"):
                try:
                    if path.is_file() and not path.is_symlink():
                        freed += path.stat().st_size
                except OSError:
                    pass
        _marker(root, entry).unlink(missing_ok=True)
        if repo.exists():
            shutil.rmtree(repo)
    return {"ok": True, "model": entry["id"], "freed_bytes": freed}


def listing(root: str | Path, *, bundled_model: str | None, selected: str | None,
            info: dict | None = None) -> dict:
    """Everything the chooser shows, for this computer."""
    info = info or machine()
    cores = info["cpu_cores"]
    pick = recommended_english(cores)
    models = []
    for entry in CATALOG:
        disk = state(entry["id"], root)
        bundled = entry["id"] == bundled_model
        minutes = minutes_per_hour(entry["id"], cores)
        models.append({
            "id": entry["id"], "label": entry["label"], "note": entry["note"],
            "english_only": entry["english_only"],
            "languages": "English only" if entry["english_only"] else "99 languages",
            "download_bytes": disk["total_bytes"],
            "download_mb": round(disk["total_bytes"] / 1_000_000),
            "minutes_per_hour": minutes, "speed": speed_copy(minutes),
            "state": "bundled" if bundled and disk["state"] != "ready" else disk["state"],
            "bytes_on_disk": disk["bytes_on_disk"],
            "recommended": entry["id"] == pick,
            "selected": entry["id"] == selected,
            "repo": entry.get("source_repo") or entry["repo"],
            "revision": entry["revision"],
        })
    return {"machine": info, "recommended": pick, "source": "huggingface.co",
            "models": models}


def wait_until(predicate: Callable[[], bool], timeout: float) -> bool:
    """Small polling helper for tests and the CLI."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()
