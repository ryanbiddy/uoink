"""Fixed retained synthetic files only; metadata report, no content output."""
import encodings.utf_8_sig
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

HERE = Path(__file__).parent
FIXTURES = HERE.parent / "resolver-preflight01" / "synthetic-assets"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
PREFIX = b"UOINK-SYNTHETIC-ASR-ASSET\n"
FOUR = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
FIVE = ("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")
TINY = "d90ca5fe260221311c53c58e660288d3deb8d356"
CASES = (
    ("success-tiny", "tiny", TINY, FOUR),
    ("success-medium", "medium", "08e178d48790749d25932bbc082711ddcfdfbc4f", FOUR),
    ("success-large", "large", "edaa852ec7e145841d8ffdb056a99866b5f0a478", FIVE),
    ("success-base", "base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66", FOUR),
    ("wrong-hash", "tiny", TINY, FOUR),
    ("wrong-prefix", "tiny", TINY, ("model.bin", "tokenizer.json", "vocabulary.txt")),
    ("earlier-file", "tiny", TINY, FOUR),
    ("changed-between", "tiny", TINY, FOUR),
    ("replaced-same", "tiny", TINY, FOUR),
    ("forged-admission", "tiny", TINY, FOUR),
)
PATHS = tuple(FIXTURES / label / choice / revision / name
              for label, choice, revision, names in CASES for name in names)
assert len(PATHS) == 40 and len(set(PATHS)) == 40
INPUT_NAMES = ("diagnose_identity.py", "run01-plan.json", "run01-exit.json", "run01-stdout.json")
ALLOWED = {os.path.normcase(str(path)) for path in PATHS} | {os.path.normcase(str(HERE / name)) for name in INPUT_NAMES}
ALLOWED_IMPORTS = set(sys.modules)
DENIED = []


def lexical(path):
    assert isinstance(path, (str, bytes, os.PathLike)), "Path type refused"
    result = os.path.normcase(os.path.abspath(os.fsdecode(path)))
    assert os.path.normcase(FORBIDDEN) not in result, "Forbidden lexical path"
    return result


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = lexical(path) in ALLOWED and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS
    if not allowed:
        DENIED.append(event)
        raise AssertionError("Diagnostic boundary refused " + event)


sys.addaudithook(audit)
RAW = {name: (HERE / name).read_bytes() for name in INPUT_NAMES}
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}
PLAN = json.loads(RAW["run01-plan.json"].decode("utf-8-sig"))
EXIT = json.loads(RAW["run01-exit.json"].decode("utf-8-sig"))
RESULT = json.loads(RAW["run01-stdout.json"].decode("utf-8-sig"))
assert RESULT["passed"] == 64 and RESULT["failed"] == 9 and RESULT["qualification_exit"] == 1
assert EXIT["native_exit"] == 1 and EXIT["inputs_unchanged"] is True
assert next(row["sha256"] for row in PLAN["inputs"] if row["name"] == "trusted_asr_resolver.py") == "dab721bde82923010c47bc6ea9242b41a3befc7dd094bab2fb92b3cc1f13f407"
assert next(row["sha256"] for row in PLAN["inputs"] if row["name"] == "qualify_resolver.py") == "d4843c142e6a79d1507fda25b21baf9de6198031d06b6c2b07c978332189a1ed"
FIELDS = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_birthtime_ns")


def values(observed):
    return {key: getattr(observed, key, None) for key in FIELDS}


def checked(path):
    assert lexical(path) in ALLOWED and path in PATHS
    anchor = Path(path.anchor)
    parts = path.relative_to(anchor).parts
    for count in range(len(parts) + 1):
        component = anchor / Path(*parts[:count])
        lexical(component)
        observed = component.lstat()
        assert not stat.S_ISLNK(observed.st_mode) and not getattr(observed, "st_file_attributes", 0) & 0x400, "Linked/reparse path"
        assert stat.S_ISREG(observed.st_mode) if component == path else stat.S_ISDIR(observed.st_mode), "Path kind"
    assert str(path.resolve(strict=True)) == str(path), "Resolved alias"
    observed = path.lstat()
    assert observed.st_nlink == 1 and len(PREFIX) <= observed.st_size <= 4096, "Placeholder size or links"
    return observed


started = time.monotonic()
records = []
for path in PATHS:
    row = {"path": str(path.relative_to(FIXTURES))}
    try:
        assert time.monotonic() - started < 60.0, "Diagnostic cooperative deadline"
        before_path = checked(path)
        with path.open("rb") as stream:
            before_handle = os.fstat(stream.fileno())
            content = stream.read(4097)
            after_handle = os.fstat(stream.fileno())
        after_path = checked(path)
        assert len(PREFIX) <= len(content) <= 4096 and content.startswith(PREFIX), "Synthetic prefix or byte bound"
        row.update(status="observed", prefix_verified=True, bytes_read=len(content),
                   lstat_before=values(before_path), fstat_before=values(before_handle),
                   fstat_after=values(after_handle), lstat_after=values(after_path))
        row["mismatched_fields"] = {
            "lstat_before_vs_fstat_before": [key for key in FIELDS if row["lstat_before"][key] != row["fstat_before"][key]],
            "fstat_before_vs_fstat_after": [key for key in FIELDS if row["fstat_before"][key] != row["fstat_after"][key]],
            "fstat_after_vs_lstat_after": [key for key in FIELDS if row["fstat_after"][key] != row["lstat_after"][key]],
            "lstat_before_vs_lstat_after": [key for key in FIELDS if row["lstat_before"][key] != row["lstat_after"][key]],
        }
        del content
    except Exception as exc:
        row.update(status="refused", exception=type(exc).__name__, reason=str(exc))
    records.append(row)
refused = sum(row["status"] != "observed" for row in records)
output = {"schema": "uoink.synthetic-identity-diagnostic.v1", "input_sha256": HASHES,
          "observed": len(records) - refused, "refused": refused, "records": records,
          "elapsed_seconds": round(time.monotonic() - started, 6), "startup_binding_asserted": True,
          "guard_denials": DENIED, "no_content_output": True,
          "excluded_known_invalid_prefix": "wrong-prefix/tiny/" + TINY + "/config.json",
          "diagnostic_exit": 0 if not refused and not DENIED else 1}
print(json.dumps(output, indent=2))
sys.exit(output["diagnostic_exit"])
