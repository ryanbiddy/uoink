"""Unintegrated stdlib ASR admission proposal. No real approval or loader."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

MIB = 1024 * 1024
MAX_MANIFEST = 64 * 1024
MAX_FILE = 4 * 1024 * MIB
MAX_MODEL = 4 * 1024 * MIB
MAX_ALL = 8 * 1024 * MIB
MAX_SECONDS = 600.0
CHUNK = MIB
SYNTHETIC_MAX_FILE = 4096
SYNTHETIC_PREFIX = b"UOINK-SYNTHETIC-ASR-ASSET\n"
SYNTHETIC_BASE = Path(__file__).parent / "synthetic-assets"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
FOUR = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
FIVE = ("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")
MODEL_SPECS = {
    "tiny": ("Systran/faster-whisper-tiny", "d90ca5fe260221311c53c58e660288d3deb8d356", FOUR),
    "base": ("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66", FOUR),
    "small": ("Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120", FOUR),
    "medium": ("Systran/faster-whisper-medium", "08e178d48790749d25932bbc082711ddcfdfbc4f", FOUR),
    "large": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478", FIVE),
    "large-v3-turbo": ("dropbox-dash/faster-whisper-large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", FIVE),
}


class AdmissionRefusal(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise AdmissionRefusal(reason)


@dataclass(frozen=True)
class ManifestApproval:
    purpose: str
    manifest_sha256: str


# A future real trust anchor needs an explicit reviewed source/decision change.
REAL_APPROVAL = None


@dataclass(frozen=True)
class Asset:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Model:
    choice: str
    repo: str
    revision: str
    assets: tuple


@dataclass(frozen=True)
class TrustedManifest:
    raw: bytes
    approval: ManifestApproval
    models: tuple


@dataclass(frozen=True)
class FileObservation:
    name: str
    size: int
    sha256: str
    identity: tuple
    handle_identity: tuple


@dataclass(frozen=True)
class Admission:
    manifest: TrustedManifest
    choice: str
    private_root: str
    snapshot: str
    directory_identity: tuple
    files: tuple


@dataclass(frozen=True)
class LocalBinding:
    model_path: str
    choice: str
    revision: str
    manifest_sha256: str
    files: tuple
    local_files_only: bool = True
    constructor_called: bool = False
    real_runtime_approved: bool = False


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        require(type(key) is str and key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def exact_keys(obj, names, reason):
    require(type(obj) is dict and set(obj) == set(names), reason)


def load_manifest(raw, approval):
    """Pure bytes validation. Real unapproved input refuses before all I/O."""
    require(type(approval) is ManifestApproval, "Explicit external manifest approval required")
    require(type(approval.purpose) is str and approval.purpose in ("synthetic", "real"), "Approval purpose refused")
    if approval.purpose == "real":
        require(REAL_APPROVAL is not None and approval is REAL_APPROVAL, "Real manifest approval unavailable")
    require(type(approval.manifest_sha256) is str and HEX64.fullmatch(approval.manifest_sha256), "Approval digest refused")
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MANIFEST, "Immutable manifest byte bound")
    require(hashlib.sha256(raw).hexdigest() == approval.manifest_sha256, "Manifest digest mismatch")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(AdmissionRefusal("Nonfinite JSON constant")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, AdmissionRefusal):
            raise
        raise AdmissionRefusal("Malformed manifest JSON") from exc
    exact_keys(doc, ("schema", "purpose", "manifest_accepted", "models"), "Manifest schema keys refused")
    require(doc["schema"] == "uoink.asr-trusted-manifest.v1" and doc["purpose"] == approval.purpose, "Manifest schema or purpose refused")
    require(doc["manifest_accepted"] is True, "Manifest is not accepted")
    require(type(doc["models"]) is list and len(doc["models"]) == 6, "Exactly six model choices required")
    models, seen, total = [], set(), 0
    for item in doc["models"]:
        exact_keys(item, ("choice", "repo", "revision", "manifest_accepted", "files"), "Model manifest keys refused")
        choice = item["choice"]
        require(type(choice) is str and choice in MODEL_SPECS and choice not in seen, "Unknown or duplicate model choice")
        repo, revision, expected_names = MODEL_SPECS[choice]
        require(type(item["repo"]) is str and item["repo"] == repo and type(item["revision"]) is str and item["revision"] == revision, "Immutable model repository or revision mismatch")
        require(item["manifest_accepted"] is True, "Model manifest is not accepted")
        require(type(item["files"]) is list and len(item["files"]) == len(expected_names), "Complete expected asset set required")
        assets, names, subtotal = [], set(), 0
        for entry in item["files"]:
            exact_keys(entry, ("path", "bytes", "sha256"), "Asset record keys refused")
            name, size, digest = entry["path"], entry["bytes"], entry["sha256"]
            require(type(name) is str and name in expected_names and name not in names, "Unknown or duplicate asset name")
            require(type(size) is int and 0 < size <= MAX_FILE, "Asset size refused")
            if approval.purpose == "synthetic":
                require(len(SYNTHETIC_PREFIX) <= size <= SYNTHETIC_MAX_FILE, "Synthetic placeholder size refused")
            require(type(digest) is str and HEX64.fullmatch(digest), "Complete SHA256 required for every asset")
            assets.append(Asset(name, size, digest))
            names.add(name)
            subtotal += size
        require(names == set(expected_names) and subtotal <= MAX_MODEL, "Incomplete or excessive model assets")
        models.append(Model(choice, repo, revision, tuple(sorted(assets, key=lambda a: a.name))))
        seen.add(choice)
        total += subtotal
    require(seen == set(MODEL_SPECS) and total <= MAX_ALL, "Incomplete or excessive manifest")
    return TrustedManifest(raw, approval, tuple(sorted(models, key=lambda m: m.choice)))


def _clock(started):
    require(time.monotonic() - started <= MAX_SECONDS, "Admission time bound exceeded")


def _identity(observed):
    return (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_nlink,
            observed.st_size, observed.st_mtime_ns, observed.st_ctime_ns,
            getattr(observed, "st_birthtime_ns", None))


def _cross_api_identity(observed):
    # Windows lstat/fstat can use different ctime namespaces. Retain both full
    # same-API records; use exact required birthtime for the cross-API comparison.
    if os.name == "nt":
        birthtime = getattr(observed, "st_birthtime_ns", None)
        require(type(birthtime) is int, "Required Windows birthtime unavailable")
        return (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_nlink,
                observed.st_size, observed.st_mtime_ns, birthtime)
    return _identity(observed)


def _unlinked_stat(path, *, directory):
    observed = path.lstat()
    require(not stat.S_ISLNK(observed.st_mode) and not getattr(observed, "st_file_attributes", 0) & 0x400, "Linked or reparse path refused")
    require(stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode), "Non-directory or non-regular path refused")
    if not directory:
        require(observed.st_nlink == 1, "Hard-linked asset refused")
    return observed


def _plain_absolute(value):
    require(type(value) is str or isinstance(value, Path), "Path type refused")
    path = Path(value)
    require(path.is_absolute() and ".." not in path.parts and not str(path).startswith("\\\\"), "Absolute local non-escaping path required")
    return path


def _checked_chain(path, *, directory):
    anchor = Path(path.anchor)
    parts = path.relative_to(anchor).parts
    for count in range(len(parts) + 1):
        current = anchor / Path(*parts[:count])
        _unlinked_stat(current, directory=(directory or current != path))
    # Full ancestor refusal precedes resolution, so aliases cannot redirect reads.
    require(str(path.resolve(strict=True)) == str(path), "Path alias refused")
    return _unlinked_stat(path, directory=directory)


def _inventory(snapshot, expected):
    with os.scandir(snapshot) as entries:
        names = []
        for entry in entries:
            require(len(names) < len(expected), "Extra snapshot entry refused")
            names.append(entry.name)
    require(len(names) == len(expected) and set(names) == set(expected), "Partial or unexpected snapshot inventory")


def _hash_asset(path, asset, synthetic, started):
    before_path = _checked_chain(path, directory=False)
    require(before_path.st_size == asset.size, "Asset size mismatch")
    digest, count, first = hashlib.sha256(), 0, b""
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require(_cross_api_identity(opened) == _cross_api_identity(before_path), "Asset changed before open")
        while True:
            _clock(started)
            chunk = stream.read(min(CHUNK, asset.size - count + 1))
            if not chunk:
                break
            if count == 0:
                first = chunk[:len(SYNTHETIC_PREFIX)]
            count += len(chunk)
            require(count <= asset.size, "Asset grew during read")
            digest.update(chunk)
        require(_identity(os.fstat(stream.fileno())) == _identity(opened), "Asset changed during read")
    after_path = _checked_chain(path, directory=False)
    require(_identity(after_path) == _identity(before_path)
            and _cross_api_identity(after_path) == _cross_api_identity(opened), "Asset replaced after read")
    require(count == asset.size and digest.hexdigest() == asset.sha256, "Asset size or SHA256 mismatch")
    if synthetic:
        require(first == SYNTHETIC_PREFIX, "Generated placeholder prefix required")
    _clock(started)
    return FileObservation(asset.name, asset.size, asset.sha256, _identity(after_path), _identity(opened))


def admit_snapshot(manifest, choice, private_root, snapshot):
    """Admit only an explicit fixed snapshot; no cache discovery or creation."""
    started = time.monotonic()
    require(type(manifest) is TrustedManifest, "Trusted manifest object required")
    # Reparse bounded bytes so a manually forged dataclass is not a trust bypass.
    verified = load_manifest(manifest.raw, manifest.approval)
    require(manifest == verified, "Manifest object differs from approved bytes")
    require(type(choice) is str and choice in MODEL_SPECS, "Exact model choice required")
    model = next(model for model in verified.models if model.choice == choice)
    root, chosen = _plain_absolute(private_root), _plain_absolute(snapshot)
    synthetic = verified.approval.purpose == "synthetic"
    if synthetic:
        require(root.parent == SYNTHETIC_BASE and LABEL.fullmatch(root.name), "Synthetic root outside proposal-owned labels")
    # No real root can reach this point while REAL_APPROVAL is absent.
    require(chosen == root / choice / model.revision, "Snapshot must be the exact choice and immutable revision path")
    try:
        _checked_chain(root, directory=True)
        directory_before = _identity(_checked_chain(chosen, directory=True))
        expected = tuple(asset.name for asset in model.assets)
        _inventory(chosen, expected)
        observations = tuple(_hash_asset(chosen / asset.name, asset, synthetic, started) for asset in model.assets)
        _inventory(chosen, expected)
        require(_identity(_checked_chain(chosen, directory=True)) == directory_before, "Snapshot directory changed during admission")
        for observation in observations:
            require(_identity(_checked_chain(chosen / observation.name, directory=False)) == observation.identity, "Earlier asset changed before admission completed")
        _clock(started)
        return Admission(verified, choice, str(root), str(chosen), directory_before, observations)
    except (OSError, RuntimeError) as exc:
        raise AdmissionRefusal("Filesystem unavailable or changed") from exc


def bind_for_constructor(admission):
    """Recheck the same snapshot; return local-only arguments, never invoke code."""
    require(type(admission) is Admission, "Admission object required")
    current = admit_snapshot(admission.manifest, admission.choice, admission.private_root, admission.snapshot)
    require(current == admission, "Snapshot identity changed since admission")
    model = next(model for model in current.manifest.models if model.choice == current.choice)
    return LocalBinding(current.snapshot, current.choice, model.revision,
                        current.manifest.approval.manifest_sha256, current.files)
