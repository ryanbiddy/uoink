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

import errno
import hashlib
import http.client
import os
import shutil
import subprocess
import sys
import threading
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

HF_BASE = "https://huggingface.co"
PARTIAL_DIR = ".uoink-partial"
READY_TEXT = "Uoink faster-whisper model ready\n"
_CHUNK = 128 * 1024
LEGACY_TURBO_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"

# Rough minutes of processing per hour of audio for the bundled base model on
# four worker threads. Scale this estimate by the same physical-core budget
# the loader uses; relative model costs come from encoder/decoder sizes.
BASE_MINUTES_PER_HOUR = 4.0
_REFERENCE_THREADS = 4
RECOMMEND_MAX_MINUTES = 30

S, G = "sha256", "git_sha1"

# Order = how the chooser lists them, smallest first.
CATALOG: tuple[dict, ...] = (
    {"id": "tiny", "label": "Fast", "repo": "Systran/faster-whisper-tiny",
     "revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
     "english_only": False, "cost": 0.5,
     "note": "Quickest, and it misses the most words.",
     "files": {"config.json": (2249, S, "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8"),
               "model.bin": (75538270, S, "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"),
               "tokenizer.json": (2203239, S, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
               "vocabulary.txt": (459861, S, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}},
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
     "files": {"config.json": (2812, S, "b571ae8022a34c1df50876a65b5f813a5c22e5ee3b87bc0e4db5662dfc9c2c3d"),
               "model.bin": (332308257, S, "1187de3982cdcf962a2fb8f797e429fb4651b875b18fe9ce50b58b52fc9072b7"),
               "preprocessor_config.json": (339, S, "a6a76d28c93edb273669eb9e0b0636a2bddbb1272c3261e47b7ca6dfdbac1b8d"),
               "tokenizer.json": (2405466, G, "d7cd7ef030d38ff11df010adc96a29e3a0222151"),
               "vocabulary.json": (825480, S, "4dadfee7c4a871665f65c06037f5f5ec893fb2d7f5eb4cf11063618e31dbe11a")}},
    {"id": "small", "label": "Careful", "repo": "Systran/faster-whisper-small",
     "revision": "536b0662742c02347bc0e980a01041f333bce120",
     "english_only": False, "cost": 2.6,
     "note": "A solid step up for any language.",
     "files": {"config.json": (2370, S, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
               "model.bin": (483546902, S, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
               "tokenizer.json": (2203239, S, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
               "vocabulary.txt": (459861, S, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}},
    {"id": "distil-large-v3.5", "label": "English, best",
     "repo": "distil-whisper/distil-large-v3.5-ct2",
     "revision": "9793ccc07920e0f830e1dba0343efcdf0ef8c903",
     "english_only": True, "cost": 5.5,
     "note": "Close to Max accuracy on English, in a fraction of the time.",
     "files": {"config.json": (2690, S, "90c55f775cc4e0bb17293d0bf12f96557a486f20dea886fabd8e6075a3588b21"),
               "model.bin": (1512927867, S, "c58b88b8585ffcd2135fddaaf421ce72cb223b32edea70d156aed1dea319a119"),
               "preprocessor_config.json": (340, S, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
               "tokenizer.json": (2480645, G, "e08f6459ce450dc8547e6acb2e42fd724f082632"),
               "vocabulary.json": (1068114, S, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1")}},
    {"id": "large-v3-turbo", "label": "Turbo",
     "repo": "dropbox-dash/faster-whisper-large-v3-turbo",
     "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
     "english_only": False, "cost": 6.0,
     "note": "Near Max accuracy in any language, much faster than it.",
     "files": {"config.json": (2263, S, "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e"),
               "model.bin": (1617884929, S, "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
               "preprocessor_config.json": (340, S, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
               "tokenizer.json": (2710337, S, "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd"),
               "vocabulary.json": (1068114, S, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1")}},
    {"id": "medium", "label": "Deep", "repo": "Systran/faster-whisper-medium",
     "revision": "08e178d48790749d25932bbc082711ddcfdfbc4f",
     "english_only": False, "cost": 7.0,
     "note": "Strong on accents and noisy rooms, and slow.",
     "files": {"config.json": (2257, S, "3622a2ddc41ec0e0fd4e68c13c6830f03b90c38d89aaad184de02c8c642cf807"),
               "model.bin": (1527906378, S, "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae"),
               "tokenizer.json": (2203239, S, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
               "vocabulary.txt": (459861, S, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913")}},
    {"id": "large", "label": "Max accuracy", "repo": "Systran/faster-whisper-large-v3",
     "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
     "english_only": False, "cost": 14.0,
     "note": "The most accurate in any language, and the slowest.",
     "files": {"config.json": (2394, S, "a9306624f5ec14270a014b647e5c316b6e03a662c369758d1b90697a7b0655b9"),
               "model.bin": (3087284237, S, "69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1"),
               "preprocessor_config.json": (340, S, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
               "tokenizer.json": (2480617, S, "6d8cbd7cd0d8d5815e478dac67b85a26bbe77c1f5e0c6d76d1ce2abc0e5f21ca"),
               "vocabulary.json": (1068114, S, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1")}},
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
def _quota_limit(root):
    """Read v2 or v1 CPU bandwidth at this cgroup and its ancestors."""
    paths = {root, root / "cpu", root / "cpu,cpuacct"}
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            _, controllers, relative = line.split(":", 2)
            sub = PurePosixPath(relative.lstrip("/"))
            if ".." in sub.parts:
                continue
            bases = [root] if not controllers else [root / controllers, root / "cpu"]
            if not controllers or "cpu" in controllers.split(","):
                for base in bases:
                    leaf = base / sub
                    paths.update(p for p in (leaf, *leaf.parents) if p.is_relative_to(base))
    except (OSError, ValueError):
        pass
    limits = []
    for path in paths:
        try:
            if (path / "cpu.max").is_file():
                quota, period = (path / "cpu.max").read_text().split()
            else:
                quota = (path / "cpu.cfs_quota_us").read_text()
                period = (path / "cpu.cfs_period_us").read_text()
            if int(quota) > 0 and int(period) > 0:
                limits.append(max(1, int(quota) // int(period)))
        except (OSError, ValueError):
            continue
    return min(limits) if limits else None


def physical_cores() -> int:
    logical = (getattr(os, "process_cpu_count", os.cpu_count)() or os.cpu_count() or 1)
    try:
        if sys.platform == "win32":
            import ctypes
            count = ctypes.c_ulong()
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            mask = ctypes.c_size_t()
            system_mask = ctypes.c_size_t()
            affinity = kernel.GetProcessAffinityMask
            affinity.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
            affinity.restype = ctypes.c_int
            if affinity(ctypes.c_void_p(-1), ctypes.byref(mask), ctypes.byref(system_mask)) and mask.value:
                logical = min(logical, mask.value.bit_count())
            query = kernel.GetLogicalProcessorInformationEx
            query.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            query.restype = ctypes.c_int
            query(0, None, ctypes.byref(count))  # RelationProcessorCore
            buf = ctypes.create_string_buffer(count.value)
            if count.value and query(0, buf, ctypes.byref(count)):
                offset = cores = 0
                while offset + 8 <= count.value:
                    size = int.from_bytes(buf[offset + 4:offset + 8], "little")
                    if size < 8:
                        break
                    cores += 1
                    offset += size
                if cores and offset == count.value:
                    return min(cores, logical)
        elif sys.platform == "darwin":
            return min(logical, max(1, int(subprocess.check_output(
                ["/usr/sbin/sysctl", "-n", "hw.physicalcpu"], timeout=2))))
        else:
            topology = Path("/sys/devices/system/cpu")
            affinity = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else None
            quota = _quota_limit(Path("/sys/fs/cgroup"))
            logical = min(logical, len(affinity) if affinity else logical, quota or logical)
            siblings = {p.read_text().strip() for p in topology.glob("cpu[0-9]*/topology/thread_siblings_list")
                        if affinity is None or int(p.parents[1].name[3:]) in affinity}
            siblings.discard("")
            if siblings:
                return min(len(siblings), logical)
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pass
    return max(1, logical)


def cpu_threads(cores=None) -> int:
    cores = physical_cores() if cores is None else cores
    return max(1, min(4, cores - 1))


def machine() -> dict:
    """Processor count and whether a graphics card is visible. Read only:
    no benchmark, no process started."""
    cores = physical_cores()
    gpu = bool(shutil.which("nvidia-smi"))
    return {"cpu_cores": cores, "gpu": gpu, "threads_used": cpu_threads(cores)}


def minutes_per_hour(model_id: str, cores: int) -> int:
    threads = cpu_threads(cores)
    minutes = BASE_MINUTES_PER_HOUR * get(model_id)["cost"] * (_REFERENCE_THREADS / threads)
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


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _legacy_snapshot(model_id, root):
    if model_id == "large-v3-turbo":
        import uoink_reliability as rel
        return rel._read_reliability_snapshot(root, model_id, legacy=True)
    return None


def state(model_id: str, root: Path) -> dict:
    """What is on disk for one model: ready (pinned revision complete with
    its marker), partial (some bytes kept for a resume) or missing. Cheap:
    sizes and the marker only, no hashing."""
    entry = get(model_id)
    root = Path(root)
    legacy = _legacy_snapshot(model_id, root)
    if legacy:
        import uoink_reliability as rel
        return {"state": "ready" if rel.is_model_ready(model_id, root) else "partial",
                "bytes_on_disk": installed_bytes(model_id, root), "total_bytes": total_bytes(model_id)}
    snapshot, partial = _snapshot_dir(root, entry), _partial_dir(root, entry)
    have = 0
    complete = True
    for name, (size, _kind, _digest) in entry["files"].items():
        final = snapshot / name
        if _size(final) == size:
            have += size
            continue
        complete = False
        part = partial / (name + ".part")
        progress = _size(part)
        if model_id == "large-v3-turbo":
            old_part = _partial_dir(root, dict(entry, repo=LEGACY_TURBO_REPO)) / part.name
            progress = max(progress, _size(old_part))
        have += min(progress, size)
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


class ModelRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        host = target.hostname or ""
        if (target.scheme != "https" or target.username is not None or target.port not in (None, 443)
                or not (host == "huggingface.co" or host.endswith((".huggingface.co", ".hf.co")))):
            # The pinned file hash verifies the bytes. The host check confines redirects.
            raise ValueError("The model download redirected outside Hugging Face.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
        if exc.code == 416 and have:
            exc.close()
            part.unlink()
            on_bytes(-have)
            return _fetch(url, part, size, cancel_event=cancel_event, on_bytes=on_bytes,
                          opener=opener, timeout=timeout)
        raise
    with response:
        status = getattr(response, "status", None) or response.getcode()
        if status == 206 and response.headers.get("Content-Range") != f"bytes {have}-{size - 1}/{size}":
            raise ValueError("The server returned the wrong file range. Try again to resume.")
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
             opener=None, timeout: float = 60.0) -> dict:
    """Fetch, verify and install one pinned model. Safe to call again after
    a cancel or a crash: finished files are kept and partial ones resume."""
    entry = get(model_id)
    root = Path(root)
    snapshot, partial = _snapshot_dir(root, entry), _partial_dir(root, entry)
    total = total_bytes(model_id)
    source = entry["repo"]
    if opener is None:
        opener = urllib.request.build_opener(ModelRedirectHandler()).open
    lock = root / f".{entry['id']}.download.lock"
    with _exclusive(lock):
        legacy = _legacy_snapshot(model_id, root)
        if legacy:
            _marker(root, entry).write_text(READY_TEXT, encoding="utf-8")
            return {"ok": True, "model": model_id, "revision": legacy.name,
                    "bytes": installed_bytes(model_id, root)}
        remaining = max(0, total - state(model_id, root)["bytes_on_disk"])
        if remaining and shutil.disk_usage(root).free < remaining + 16 * 1024**2:
            raise OSError("There is not enough free disk space for this model.")
        snapshot.mkdir(parents=True, exist_ok=True)
        partial.mkdir(parents=True, exist_ok=True)
        if model_id == "large-v3-turbo":
            old = _partial_dir(root, dict(entry, repo=LEGACY_TURBO_REPO))
            for name, (size, _, _) in entry["files"].items():
                src, dst = old / (name + ".part"), partial / (name + ".part")
                if (src.resolve() == src.absolute() and dst.resolve() == dst.absolute()
                        and _size(dst) < _size(src) <= size):
                    os.replace(src, dst)
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
            try:
                _fetch(url, part, size, cancel_event=cancel_event, on_bytes=report,
                       opener=opener, timeout=timeout)
            except OSError as exc:
                if exc.errno not in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
                    raise
                part.unlink(missing_ok=True)
                raise OSError("There is not enough free disk space for this model.") from exc
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


def _installed_repos(root, entry):
    yield _repo_dir(root, entry)
    if entry["id"] == "large-v3-turbo":
        yield _repo_dir(root, {"repo": LEGACY_TURBO_REPO})


def installed_bytes(model_id, root):
    return sum(_size(p) for repo in _installed_repos(root, get(model_id))
               for p in repo.rglob("*") if p.is_file() and not p.is_symlink())


def delete(model_id: str, root: str | Path) -> dict:
    entry = get(model_id)
    root = Path(root)
    with _exclusive(root / f".{entry['id']}.download.lock"):
        freed = installed_bytes(model_id, root)
        for repo in _installed_repos(root, entry):
            if repo.exists():
                shutil.rmtree(repo)
        _marker(root, entry).unlink(missing_ok=True)
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
