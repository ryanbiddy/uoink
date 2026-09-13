"""Seal only this scratch proposal, its synthetic receipts and fixed review."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys


assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
SOURCE = ROOT / "vad-symbolic-metadata-proposal01"
TARGET = ROOT / "vad-symbolic-metadata-proposal-final-proof01"
REVIEW = ROOT / "vad-symbolic-review01/FINAL-REVIEW.md"
EXPECTED_SOURCE = "f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127"
EXPECTED_REVIEW = "88b5489c14c91dfd4bfbf6ddc2a76c9ea0de2f6dc46ea2423d06d80d58fed5d8"


def read_plain(path):
    assert path.is_relative_to(ROOT)
    cursor = ROOT
    for component in path.relative_to(ROOT).parts:
        cursor /= component
        observed = cursor.lstat()
        assert not stat.S_ISLNK(observed.st_mode)
        assert not (getattr(observed, "st_file_attributes", 0) & 0x400)
    assert stat.S_ISREG(observed.st_mode) and observed.st_size <= 2 * 1024 * 1024
    assert path.suffix.lower() in (".py", ".ps1", ".md", ".json", ".diff", ".log")
    return path.read_bytes()


def digest(data):
    return hashlib.sha256(data).hexdigest()


assert not TARGET.exists(), "Fresh proof required"
assert digest(read_plain(SOURCE / "symbolic_trace.py")) == EXPECTED_SOURCE
assert digest(read_plain(REVIEW)) == EXPECTED_REVIEW
case_ids = None
for label, counts, code in (("symbolic-preflight01", (56, 1), 1),
                            ("symbolic-preflight02", (57, 0), 0),
                            ("symbolic-preflight03", (57, 0), 0)):
    outcome = json.loads(read_plain(SOURCE / label / "stdout.json").decode("utf-8-sig"))
    receipt = json.loads(read_plain(SOURCE / label / "launch-receipt.json").decode("utf-8-sig"))
    assert (outcome["passed"], outcome["failed"]) == counts
    assert receipt["actual_reader_exit"] == code
    assert outcome["source_sha256"] == EXPECTED_SOURCE
    assert receipt["source_sha256_before"] == receipt["source_sha256_after"] == EXPECTED_SOURCE
    assert receipt["harness_sha256_before"] == receipt["harness_sha256_after"]
    assert outcome["target_side_effect_count"] == 0
    assert outcome["checkpoint_opened"] is False and outcome["model_imported"] is False
    observed_ids = [item["case"] for item in outcome["cases"]]
    assert len(observed_ids) == len(set(observed_ids)) == 57
    if case_ids is None:
        case_ids = observed_ids
    else:
        assert observed_ids == case_ids
    if label == "symbolic-preflight03":
        assert outcome["forbidden_live_startup_binding_asserted"] is True
        assert receipt["forbidden_live_binding_set_before_startup"] is True
    assert not read_plain(SOURCE / label / "stderr.log")

payloads = []
for path in sorted(SOURCE.rglob("*")):
    if path.is_dir():
        assert not path.is_symlink() and not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
        continue
    data = read_plain(path)
    payloads.append((path.relative_to(SOURCE).as_posix(), data))
assert len(payloads) < 150
payloads.append(("independent-review/FINAL-REVIEW.md", read_plain(REVIEW)))
payloads.append((".gitattributes", b"* -text\n"))
assert len({name for name, _ in payloads}) == len(payloads)
TARGET.mkdir()
records = []
for name, data in sorted(payloads):
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data)
    assert destination.read_bytes() == data
    records.append({"path": name, "sha256": digest(data), "bytes": len(data)})
manifest = {"scope": "Pure bounded symbolic tracer proposal and synthetic qualification only; no checkpoint trace, artifact adapter or model acceptance",
            "payload_count": len(records), "payloads": records}
encoded = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
with (TARGET / "SHA256.json").open("xb") as stream:
    stream.write(encoded)
for entry in records:
    assert digest((TARGET / entry["path"]).read_bytes()) == entry["sha256"]
print(json.dumps({"target": str(TARGET), "payload_count": len(records),
                  "manifest_sha256": digest(encoded), "all_payload_hashes_verified": True,
                  "actual_checkpoint_read": False, "source_sha256": EXPECTED_SOURCE}, indent=2))
