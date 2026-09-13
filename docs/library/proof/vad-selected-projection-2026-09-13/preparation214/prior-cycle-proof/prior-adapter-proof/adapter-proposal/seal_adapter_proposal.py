"""Seal fixed scratch evidence only; never runs or reads a model artifact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
PROPOSAL = ROOT / "vad-symbolic-adapter-proposal01"
PURE = ROOT / "vad-symbolic-metadata-proposal-final-proof01"
INDEPENDENT = ROOT / "astra-symbolic-adapter01"
WRAPPER = ROOT / "qualify_symbolic_adapter_astra01.py"
TARGET = ROOT / "vad-symbolic-adapter-proposal-final-proof01"
EXPECTED_SOURCE = "0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc"
EXPECTED_PURE_SEAL = "44c7923436adb5d54655c8990b12c42c8b34c8c9960bfcbf271bc0aa4866d98f"


def read_plain(path):
    assert path.is_relative_to(ROOT)
    cursor = ROOT
    for component in path.relative_to(ROOT).parts:
        assert component not in ("", ".", "..")
        cursor /= component
        observed = cursor.lstat()
        assert not stat.S_ISLNK(observed.st_mode)
        assert not (getattr(observed, "st_file_attributes", 0) & 0x400)
    assert stat.S_ISREG(observed.st_mode) and observed.st_size <= 2 * 1024 * 1024
    assert path.name == ".gitattributes" or path.suffix.lower() in (".py", ".ps1", ".md", ".json", ".diff", ".log")
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parsed(path):
    return json.loads(read_plain(path).decode("utf-8-sig"))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--review-file", required=True)
parser.add_argument("--review-sha256", required=True)
args = parser.parse_args()
review_path = Path(args.review_file)
assert review_path.suffix == ".md"
assert len(args.review_sha256) == 64 and set(args.review_sha256) <= set("0123456789abcdef")
assert sha(read_plain(review_path)) == args.review_sha256
assert not TARGET.exists(), "Fresh proof directory required"
assert sha(read_plain(PROPOSAL / "read_symbolic_inventory.py")) == EXPECTED_SOURCE
assert sha(read_plain(PURE / "SHA256.json")) == EXPECTED_PURE_SEAL
pure_manifest = parsed(PURE / "SHA256.json")
assert pure_manifest["payload_count"] == len(pure_manifest["payloads"]) == 53
for entry in pure_manifest["payloads"]:
    data = read_plain(PURE / entry["path"])
    assert len(data) == entry["bytes"] and sha(data) == entry["sha256"]

case_ids = None
for directory, counts, code, receipt_name in ((PROPOSAL / "adapter-preflight01", (23, 1), 1, "launch-receipt.json"),
                                             (PROPOSAL / "adapter-preflight02", (24, 0), 0, "launch-receipt.json"),
                                             (INDEPENDENT, (24, 0), 0, "exit.json")):
    outcome = parsed(directory / "stdout.json")
    receipt = parsed(directory / receipt_name)
    assert (outcome["passed"], outcome["failed"]) == counts
    assert receipt["actual_qualification_exit"] == code
    assert outcome["source_sha256"] == EXPECTED_SOURCE
    assert outcome["forbidden_live_startup_binding_asserted"] is True
    assert outcome["actual_checkpoint_opened"] is False
    assert outcome["actual_main_input_output_paths_used"] is False
    assert not read_plain(directory / "stderr.log")
    observed_ids = [item["case"] for item in outcome["cases"]]
    assert len(observed_ids) == len(set(observed_ids)) == 24
    if case_ids is None:
        case_ids = observed_ids
    else:
        assert observed_ids == case_ids
    if receipt_name == "exit.json":
        assert receipt["inputs_unchanged"] is True
        plan = parsed(directory / "plan.json")
        assert plan["IG_FORBIDDEN_LIVE_set_before_startup"] is True
        for name, expected in plan["input_sha256"].items():
            assert sha(read_plain(directory / name)) == expected
    else:
        assert receipt["source_sha256_before"] == receipt["source_sha256_after"] == EXPECTED_SOURCE
        assert receipt["harness_sha256_before"] == receipt["harness_sha256_after"]
        assert receipt["forbidden_live_binding_set_before_startup"] is True

payloads = []
for directory, prefix in ((PROPOSAL, "adapter-proposal"), (PURE, "pure-tracer-proof"), (INDEPENDENT, "independent-qualification")):
    for path in sorted(directory.rglob("*")):
        if path.is_dir():
            assert not path.is_symlink() and not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
            continue
        payloads.append((prefix + "/" + path.relative_to(directory).as_posix(), read_plain(path)))
payloads.append(("independent-review/FINAL-REVIEW.md", read_plain(review_path)))
payloads.append(("independent-qualification/qualify_symbolic_adapter_astra01.py", read_plain(WRAPPER)))
payloads.append((".gitattributes", b"* -text\n"))
assert len(payloads) < 200 and len({name for name, _ in payloads}) == len(payloads)
TARGET.mkdir()
records = []
for name, data in sorted(payloads):
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data)
    assert destination.read_bytes() == data
    records.append({"path": name, "sha256": sha(data), "bytes": len(data)})
manifest = {"scope": "Pure tracer and fixed adapter proposals with synthetic and independent qualification only; no actual checkpoint trace or model acceptance",
            "payload_count": len(records), "payloads": records}
encoded = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
with (TARGET / "SHA256.json").open("xb") as stream:
    stream.write(encoded)
for entry in records:
    assert sha((TARGET / entry["path"]).read_bytes()) == entry["sha256"]
assert sha(read_plain(PURE / "SHA256.json")) == EXPECTED_PURE_SEAL
print(json.dumps({"target": str(TARGET), "payload_count": len(records), "manifest_sha256": sha(encoded),
                  "all_payload_hashes_verified": True, "original_pure_seal_unchanged": True,
                  "actual_checkpoint_read": False}, indent=2))
