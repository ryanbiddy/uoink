"""Synthetic placeholder files only. Run only after source/protocol review."""
import ast
import contextlib
import copy
import dataclasses
import encodings.utf_8_sig
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

HERE = Path(__file__).parent
INPUTS = ("trusted_asr_resolver.py", "qualify_resolver.py", "six-model-plan.json", "identity_regressions.py", "original73-harness.py")
ASSETS = HERE / "synthetic-assets"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
READS = {os.path.normcase(str(HERE / name)) for name in INPUTS}
ALLOWED_IMPORTS = set(sys.modules)
DENIED, IO_COUNTS = [], {}


def owned(path, include_base=True):
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False
    absolute = os.path.normcase(os.path.abspath(os.fsdecode(path)))
    base = os.path.normcase(str(ASSETS))
    return (include_base and absolute == base) or absolute.startswith(base + os.sep)


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        absolute = os.path.normcase(os.path.abspath(os.fsdecode(path))) if isinstance(path, (str, bytes, os.PathLike)) else ""
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        allowed = owned(path, False) or (absolute in READS and not writing)
    elif event in ("os.scandir", "os.listdir", "os.mkdir", "os.remove", "os.rmdir"):
        allowed = owned(args[0])
    elif event in ("os.rename", "os.link", "os.symlink"):
        allowed = False
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS
    elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in {"os.system", "os.startfile", "os.spawn", "os.fork", "os.exec"}:
        allowed = False
    if event == "open" or event.startswith(("os.", "import", "socket.", "subprocess.", "ctypes.", "winreg.")):
        IO_COUNTS[event] = IO_COUNTS.get(event, 0) + 1
    if not allowed:
        DENIED.append(event)
        raise AssertionError("Unapproved synthetic qualification operation: " + event)


sys.addaudithook(audit)
RAW = {name: (HERE / name).read_bytes() for name in INPUTS}
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}
resolver = types.ModuleType("trusted_asr_resolver")
resolver.__file__ = str(HERE / "trusted_asr_resolver.py")
sys.modules[resolver.__name__] = resolver
exec(compile(RAW["trusted_asr_resolver.py"], resolver.__file__, "exec"), resolver.__dict__)
CAPTURED = json.loads(RAW["six-model-plan.json"].decode("utf-8-sig"))
CHOICES = ("tiny", "base", "small", "medium", "large", "large-v3-turbo")
assert tuple(row["choice"] for row in CAPTURED["models"]) == CHOICES
assert sum(entry["lfs_sha256"] is None for row in CAPTURED["models"] for entry in row["files"]) == 20
assert not ASSETS.exists(), "Fresh synthetic asset directory required"
ASSETS.mkdir()


def payload(choice, name):
    return b"UOINK-SYNTHETIC-ASR-ASSET\n" + (choice + ":" + name + ":placeholder-only").encode("ascii")


def document():
    rows = []
    for observed in CAPTURED["models"]:
        rows.append({"choice": observed["choice"], "repo": observed["repo"],
                     "revision": observed["revision"], "manifest_accepted": True,
                     "files": [{"path": entry["path"], "bytes": len(payload(observed["choice"], entry["path"])),
                                "sha256": hashlib.sha256(payload(observed["choice"], entry["path"])).hexdigest()}
                               for entry in observed["files"]]})
    return {"schema": "uoink.asr-trusted-manifest.v1", "purpose": "synthetic",
            "manifest_accepted": True, "models": rows}


def encode(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def approval(raw, purpose="synthetic"):
    return resolver.ManifestApproval(purpose, hashlib.sha256(raw).hexdigest())


def manifest(doc=None):
    raw = encode(document() if doc is None else doc)
    return resolver.load_manifest(raw, approval(raw))


def fixture(label, choice="tiny", doc=None):
    doc = document() if doc is None else doc
    observed = next(row for row in doc["models"] if row["choice"] == choice)
    root = ASSETS / label
    snapshot = root / choice / observed["revision"]
    snapshot.mkdir(parents=True)
    for entry in observed["files"]:
        (snapshot / entry["path"]).write_bytes(payload(choice, entry["path"]))
    return manifest(doc), root, snapshot


def refuse(call, fragment):
    try:
        call()
    except resolver.AdmissionRefusal as exc:
        assert fragment in str(exc), (fragment, str(exc))
        return
    raise AssertionError("Expected admission refusal: " + fragment)


@contextlib.contextmanager
def patched(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield original
    finally:
        setattr(obj, name, original)


def trap(*args, **kwargs):
    raise AssertionError("Forbidden filesystem/constructor operation reached")


def altered_stat(observed, **changes):
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_file_attributes", "st_birthtime_ns")
    values = {name: getattr(observed, name, 0) for name in fields}
    values.update(changes)
    return types.SimpleNamespace(**values)


CASES = []


def case(name):
    def add(fn):
        CASES.append((name, fn))
        return fn
    return add


@case("source_is_stdlib_only_without_loader_or_fetch")
def source_contract():
    tree = ast.parse(RAW["trusted_asr_resolver.py"])
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"exec", "eval", "compile", "__import__"}
    assert set(imports) == {"dataclasses", "hashlib", "json", "os", "pathlib", "re", "stat", "time"}
    assert resolver.REAL_APPROVAL is None
    assert resolver.SYNTHETIC_BASE == ASSETS


for choice in CHOICES:
    @case("complete_snapshot_and_second_binding_" + choice)
    def success(choice=choice):
        trusted, root, snapshot = fixture("success-" + choice, choice)
        admitted = resolver.admit_snapshot(trusted, choice, root, snapshot)
        result = resolver.bind_for_constructor(admitted)
        assert result.model_path == str(snapshot)
        assert result.choice == choice and result.revision == snapshot.name
        assert result.manifest_sha256 == trusted.approval.manifest_sha256
        assert result.local_files_only is True and result.constructor_called is False
        assert result.real_runtime_approved is False
        expected = next(row["files"] for row in document()["models"] if row["choice"] == choice)
        assert {(r.name, r.size, r.sha256) for r in result.files} == {(r["path"], r["bytes"], r["sha256"]) for r in expected}


@case("public_captured_plan_is_not_a_trusted_manifest")
def captured_raw():
    raw = RAW["six-model-plan.json"]
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.load_manifest(raw, approval(raw)), "Manifest schema keys refused")


@case("captured_false_acceptance_remains_refused_after_schema_mapping")
def captured_false():
    doc = document()
    doc["manifest_accepted"] = False
    for row, observed in zip(doc["models"], CAPTURED["models"]):
        row["manifest_accepted"] = observed["manifest_accepted"]
        for asset, old in zip(row["files"], observed["files"]):
            asset["sha256"] = old["lfs_sha256"]
    refuse(lambda: manifest(doc), "Manifest is not accepted")


@case("twenty_unknown_captured_hashes_cannot_be_approved_by_flags")
def captured_unknown():
    doc = document()
    for row, observed in zip(doc["models"], CAPTURED["models"]):
        for asset, old in zip(row["files"], observed["files"]):
            asset["sha256"] = old["lfs_sha256"]
    assert sum(asset["sha256"] is None for row in doc["models"] for asset in row["files"]) == 20
    refuse(lambda: manifest(doc), "Complete SHA256 required")


@case("real_route_refuses_before_json_or_filesystem")
def real_closed():
    with patched(Path, "lstat", trap), patched(resolver.json, "loads", trap):
        refuse(lambda: resolver.load_manifest(b"not JSON", approval(b"not JSON", "real")), "Real manifest approval unavailable")


@case("missing_external_approval")
def missing_approval():
    refuse(lambda: resolver.load_manifest(encode(document()), None), "Explicit external manifest approval")


@case("wrong_external_digest")
def wrong_approval():
    refuse(lambda: resolver.load_manifest(encode(document()), resolver.ManifestApproval("synthetic", "0" * 64)), "Manifest digest mismatch")


@case("immutable_manifest_bytes_required")
def mutable_manifest():
    raw = encode(document())
    refuse(lambda: resolver.load_manifest(bytearray(raw), approval(raw)), "Immutable manifest byte bound")


@case("manifest_byte_cap")
def manifest_cap():
    raw = b" " * (resolver.MAX_MANIFEST + 1)
    refuse(lambda: resolver.load_manifest(raw, approval(raw)), "Immutable manifest byte bound")


for name, raw, fragment in (
    ("malformed_json", b"{", "Malformed manifest JSON"),
    ("invalid_utf8", b"\xff", "Malformed manifest JSON"),
    ("duplicate_json_key", b'{"schema":1,"schema":2}', "Duplicate JSON key"),
    ("nonfinite_json", b'{"x":NaN}', "Nonfinite JSON constant"),
):
    @case(name)
    def bad_json(raw=raw, fragment=fragment):
        refuse(lambda: resolver.load_manifest(raw, approval(raw)), fragment)


def doc_negative(name, mutate, fragment):
    @case(name)
    def check():
        doc = document()
        mutate(doc)
        refuse(lambda: manifest(doc), fragment)


doc_negative("extra_top_key", lambda d: d.update(extra=1), "Manifest schema keys")
doc_negative("schema_version", lambda d: d.update(schema="v2"), "schema or purpose")
doc_negative("purpose_mismatch", lambda d: d.update(purpose="real"), "schema or purpose")
doc_negative("accepted_boolean_required", lambda d: d.update(manifest_accepted=1), "not accepted")
doc_negative("only_five_models", lambda d: d["models"].pop(), "Exactly six")
doc_negative("duplicate_model", lambda d: d["models"].__setitem__(1, copy.deepcopy(d["models"][0])), "duplicate model")
doc_negative("model_alias_large_v3", lambda d: d["models"][4].update(choice="large-v3"), "Unknown or duplicate")
doc_negative("repository_alias", lambda d: d["models"][0].update(repo="other/faster-whisper-tiny"), "repository or revision")
doc_negative("moving_revision_main", lambda d: d["models"][0].update(revision="main"), "repository or revision")
doc_negative("other_immutable_revision", lambda d: d["models"][0].update(revision="0" * 40), "repository or revision")
doc_negative("model_not_accepted", lambda d: d["models"][0].update(manifest_accepted=False), "Model manifest is not accepted")
doc_negative("missing_expected_asset", lambda d: d["models"][0]["files"].pop(), "Complete expected asset set")
doc_negative("duplicate_asset", lambda d: d["models"][0]["files"].__setitem__(1, copy.deepcopy(d["models"][0]["files"][0])), "duplicate asset")
doc_negative("asset_relative_escape", lambda d: d["models"][0]["files"][0].update(path="../config.json"), "Unknown or duplicate asset")
doc_negative("asset_extra_record_field", lambda d: d["models"][0]["files"][0].update(git_oid="a" * 40), "Asset record keys")
doc_negative("size_boolean", lambda d: d["models"][0]["files"][0].update(bytes=True), "Asset size refused")
doc_negative("size_zero", lambda d: d["models"][0]["files"][0].update(bytes=0), "Asset size refused")
doc_negative("size_float", lambda d: d["models"][0]["files"][0].update(bytes=30.0), "Asset size refused")
doc_negative("size_file_cap", lambda d: d["models"][0]["files"][0].update(bytes=resolver.MAX_FILE + 1), "Asset size refused")
doc_negative("size_synthetic_cap", lambda d: d["models"][0]["files"][0].update(bytes=4097), "Synthetic placeholder size")
doc_negative("sha_unknown", lambda d: d["models"][0]["files"][0].update(sha256=None), "Complete SHA256")
doc_negative("sha_git_oid_is_not_sha256", lambda d: d["models"][0]["files"][0].update(sha256="a" * 40), "Complete SHA256")
doc_negative("sha_uppercase_refused", lambda d: d["models"][0]["files"][0].update(sha256="A" * 64), "Complete SHA256")


@case("per_model_aggregate_bound")
def model_bound():
    with patched(resolver, "MAX_MODEL", 100):
        refuse(manifest, "excessive model assets")


@case("whole_manifest_aggregate_bound")
def whole_bound():
    doc = document()
    largest = max(sum(asset["bytes"] for asset in row["files"]) for row in doc["models"])
    with patched(resolver, "MAX_ALL", largest):
        refuse(lambda: manifest(doc), "excessive manifest")


@case("forged_manifest_object_is_reparsed")
def forged_manifest():
    valid = manifest()
    forged = dataclasses.replace(valid, models=())
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.admit_snapshot(forged, "tiny", "irrelevant", "irrelevant"), "differs from approved bytes")


for value in ("large-v3", "balanced", "TINY", "../tiny"):
    @case("choice_refuses_alias_" + value.replace("/", "-"))
    def choice_alias(value=value):
        with patched(Path, "lstat", trap):
            refuse(lambda: resolver.admit_snapshot(manifest(), value, "irrelevant", "irrelevant"), "Exact model choice")


@case("outside_private_root_refused_before_io")
def outside_root():
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.admit_snapshot(manifest(), "tiny", HERE / "outside", HERE / "outside"), "Synthetic root outside")


@case("wrong_snapshot_refused_before_io")
def wrong_snapshot():
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.admit_snapshot(manifest(), "tiny", ASSETS / "wrong-snapshot", ASSETS / "wrong-snapshot" / "tiny" / "main"), "exact choice and immutable revision")


@case("dotdot_path_refused_before_io")
def dotdot():
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.admit_snapshot(manifest(), "tiny", ASSETS / "label" / ".." / "escape", ASSETS), "Absolute local non-escaping")


for name, mutate, fragment in (
    ("missing_file", lambda p: (p / "config.json").unlink(), "Partial or unexpected"),
    ("extra_file", lambda p: (p / "extra.txt").write_bytes(b"placeholder"), "Extra snapshot entry"),
    ("empty_file", lambda p: (p / "config.json").write_bytes(b""), "Asset size mismatch"),
    ("wrong_hash", lambda p: (p / "config.json").write_bytes(payload("tiny", "config.json")[:-1] + b"X"), "SHA256 mismatch"),
    ("directory_for_file", lambda p: ((p / "config.json").unlink(), (p / "config.json").mkdir()), "Non-directory or non-regular"),
):
    @case(name)
    def filesystem_negative(name=name, mutate=mutate, fragment=fragment):
        trusted, root, snapshot = fixture(name.replace("_", "-"))
        mutate(snapshot)
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), fragment)


@case("matching_hash_without_placeholder_prefix_is_not_synthetic")
def prefix_required():
    doc = document()
    replacement = b"x" * len(payload("tiny", "config.json"))
    doc["models"][0]["files"][0]["sha256"] = hashlib.sha256(replacement).hexdigest()
    trusted, root, snapshot = fixture("wrong-prefix", doc=doc)
    (snapshot / "config.json").write_bytes(replacement)
    refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Generated placeholder prefix")


for name, attr in (("ancestor_reparse", "reparse"), ("ancestor_symlink", "symlink"), ("ancestor_nondirectory", "file")):
    @case(name)
    def bad_ancestor(name=name, attr=attr):
        trusted, root, snapshot = fixture(name.replace("_", "-"))
        original = Path.lstat
        def replaced(path, *args, **kwargs):
            observed = original(path, *args, **kwargs)
            if path == root:
                if attr == "reparse":
                    return altered_stat(observed, st_file_attributes=0x400)
                return altered_stat(observed, st_mode=stat.S_IFLNK if attr == "symlink" else stat.S_IFREG)
            return observed
        with patched(Path, "lstat", replaced):
            refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Non-directory" if attr == "file" else "Linked or reparse")


@case("hardlink_refused_without_creating_links")
def hardlink():
    trusted, root, snapshot = fixture("hardlink")
    original = Path.lstat
    def replaced(path, *args, **kwargs):
        observed = original(path, *args, **kwargs)
        return altered_stat(observed, st_nlink=2) if path == snapshot / "config.json" else observed
    with patched(Path, "lstat", replaced):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Hard-linked asset")


@case("resolved_alias_refused")
def resolved_alias():
    trusted, root, snapshot = fixture("resolved-alias")
    original = Path.resolve
    def replaced(path, *args, **kwargs):
        return path / "alias" if path == root else original(path, *args, **kwargs)
    with patched(Path, "resolve", replaced):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Path alias")


for stage in (1, 2):
    @case("changed_file_identity_at_fstat_" + str(stage))
    def fstat_race(stage=stage):
        trusted, root, snapshot = fixture("fstat-" + str(stage))
        original, calls = os.fstat, [0]
        def replaced(fd):
            observed = original(fd)
            calls[0] += 1
            return altered_stat(observed, st_ino=observed.st_ino + 1) if calls[0] == stage else observed
        with patched(os, "fstat", replaced):
            refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "changed before open" if stage == 1 else "changed during read")
        assert calls[0] == stage


@case("changed_file_identity_after_read")
def after_read():
    trusted, root, snapshot = fixture("after-read")
    original, calls = resolver._checked_chain, [0]
    def replaced(path, **kwargs):
        observed = original(path, **kwargs)
        if path == snapshot / "config.json":
            calls[0] += 1
            if calls[0] == 2:
                return altered_stat(observed, st_ino=observed.st_ino + 1)
        return observed
    with patched(resolver, "_checked_chain", replaced):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "replaced after read")


@case("directory_changed_during_admission")
def directory_race():
    trusted, root, snapshot = fixture("directory-race")
    original, calls = resolver._checked_chain, [0]
    def replaced(path, **kwargs):
        observed = original(path, **kwargs)
        if path == snapshot:
            calls[0] += 1
            if calls[0] == 2:
                return altered_stat(observed, st_ino=observed.st_ino + 1)
        return observed
    with patched(resolver, "_checked_chain", replaced):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Snapshot directory changed")


@case("earlier_file_changed_before_final_admission")
def earlier_file():
    trusted, root, snapshot = fixture("earlier-file")
    original, calls = resolver._checked_chain, [0]
    def replaced(path, **kwargs):
        observed = original(path, **kwargs)
        if path == snapshot / "config.json":
            calls[0] += 1
            if calls[0] == 3:
                return altered_stat(observed, st_ino=observed.st_ino + 1)
        return observed
    with patched(resolver, "_checked_chain", replaced):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Earlier asset changed")


@case("rebind_refuses_modified_bytes")
def changed_between():
    trusted, root, snapshot = fixture("changed-between")
    admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
    (snapshot / "config.json").write_bytes(payload("tiny", "config.json")[:-1] + b"X")
    refuse(lambda: resolver.bind_for_constructor(admitted), "SHA256 mismatch")


@case("rebind_refuses_same_bytes_at_different_identity")
def replaced_same_bytes():
    trusted, root, snapshot = fixture("replaced-same")
    admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
    original_lstat, original_fstat = Path.lstat, os.fstat
    def lstat_replaced(path, *args, **kwargs):
        observed = original_lstat(path, *args, **kwargs)
        return altered_stat(observed, st_ino=observed.st_ino + 1) if path == snapshot / "config.json" else observed
    original_ino = (snapshot / "config.json").lstat().st_ino
    def fstat_replaced(fd):
        observed = original_fstat(fd)
        return altered_stat(observed, st_ino=observed.st_ino + 1) if observed.st_ino == original_ino else observed
    with patched(Path, "lstat", lstat_replaced), patched(os, "fstat", fstat_replaced):
        refuse(lambda: resolver.bind_for_constructor(admitted), "Snapshot identity changed since admission")


@case("forged_admission_path_refused")
def forged_admission():
    trusted, root, snapshot = fixture("forged-admission")
    admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
    forged = dataclasses.replace(admitted, snapshot=str(root / "other"))
    with patched(Path, "lstat", trap):
        refuse(lambda: resolver.bind_for_constructor(forged), "exact choice and immutable revision")


@case("deadline_refuses_before_content_read")
def deadline():
    trusted, root, snapshot = fixture("deadline")
    moments = iter((0.0, resolver.MAX_SECONDS + 1.0))
    with patched(time, "monotonic", lambda: next(moments)):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "time bound exceeded")


@case("final_deadline_refuses_after_all_bytes")
def final_deadline():
    trusted, root, snapshot = fixture("final-deadline")
    original, final_path_calls, expired = resolver._checked_chain, [0], [False]
    def checked(path, **kwargs):
        observed = original(path, **kwargs)
        if path == snapshot / "vocabulary.txt":
            final_path_calls[0] += 1
            if final_path_calls[0] == 3:
                expired[0] = True
        return observed
    with patched(resolver, "_checked_chain", checked), patched(time, "monotonic", lambda: resolver.MAX_SECONDS + 1.0 if expired[0] else 0.0):
        refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "time bound exceeded")
    assert final_path_calls[0] == 3 and expired[0]


ORIGINAL_CASES = tuple(name for name, _ in CASES)
assert len(ORIGINAL_CASES) == 73
regression_namespace = {"__name__": "identity_regressions", "__file__": str(HERE / "identity_regressions.py")}
exec(compile(RAW["identity_regressions.py"], regression_namespace["__file__"], "exec"), regression_namespace)
regression_namespace["register"](globals())
assert tuple(name for name, _ in CASES[:73]) == ORIGINAL_CASES

started = time.monotonic()
results = []
assert len({name for name, _ in CASES}) == len(CASES)
for name, fn in CASES:
    try:
        fn()
        results.append({"name": name, "passed": True})
    except Exception as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)})
passed = sum(row["passed"] for row in results)
failed = len(results) - passed
result = {"schema": "uoink.synthetic-asr-admission-qualification.v1", "passed": passed, "failed": failed,
          "cases": results, "elapsed_seconds": round(time.monotonic() - started, 6),
          "input_sha256": HASHES, "startup_binding_asserted": True, "isolated_no_site_no_bytecode": True,
          "guard_denials": DENIED, "audit_event_counts": IO_COUNTS,
          "generated_placeholder_root": str(ASSETS), "actual_asset_reads": 0,
          "real_approval_available": resolver.REAL_APPROVAL is not None,
          "model_constructor_calls": 0, "network_calls": 0,
          "qualification_exit": 0 if failed == 0 and not DENIED else 1}
print(json.dumps(result, indent=2))
sys.exit(result["qualification_exit"])
