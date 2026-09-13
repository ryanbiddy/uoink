"""Seal fixed diagnostic source/receipt evidence; no artifact or model access."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
PROPOSAL = ROOT / "vad-symbolic-cycle-diagnostic-proposal01"
PRIOR = ROOT / "vad-symbolic-adapter-proposal-final-proof01"
INDEPENDENT = ROOT / "astra-cycle-diagnostic01"
REFUSED = ROOT / "vad-symbolic-run01-launch"
REFUSED_RECEIPT = ROOT / "vad-symbolic-adapter-proposal01/results/symbolic-run01.json"
REVIEW = ROOT / "vad-symbolic-review01/CYCLE-DIAGNOSTIC-FINAL-REVIEW.md"
TARGET = ROOT / "vad-symbolic-cycle-diagnostic-final-proof01"
SOURCE_SHA = "15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd"
PRIOR_SHA = "09f3affc4738efe4ae6e3b825cd616ac85c0c4adc3569ef008aa59ad832cc499"
REVIEW_SHA = "918405d3bb987bfbc9112cc7e2a43b7fbd8ccec6b4fa576d25a42e1632e26b04"


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


assert not TARGET.exists(), "Fresh seal directory required"
assert sha(read_plain(PROPOSAL / "read_symbolic_inventory.py")) == SOURCE_SHA
assert sha(read_plain(REVIEW)) == REVIEW_SHA
assert sha(read_plain(PRIOR / "SHA256.json")) == PRIOR_SHA
prior_manifest = parsed(PRIOR / "SHA256.json")
assert prior_manifest["payload_count"] == len(prior_manifest["payloads"]) == 108
for entry in prior_manifest["payloads"]:
    data = read_plain(PRIOR / entry["path"])
    assert len(data) == entry["bytes"] and sha(data) == entry["sha256"]
assert {path.relative_to(PRIOR).as_posix() for path in PRIOR.rglob("*") if path.is_file()} == {entry["path"] for entry in prior_manifest["payloads"]} | {"SHA256.json"}

case_ids = None
for directory, receipt_name in ((PROPOSAL / "cycle-diagnostic-preflight01", "launch-receipt.json"), (INDEPENDENT, "exit.json")):
    outcome = parsed(directory / "stdout.json")
    receipt = parsed(directory / receipt_name)
    assert (outcome["passed"], outcome["failed"]) == (36, 0)
    assert receipt["actual_qualification_exit"] == 0
    assert outcome["source_sha256"] == SOURCE_SHA
    assert outcome["forbidden_live_startup_binding_asserted"] is True
    assert outcome["actual_checkpoint_opened"] is False
    assert outcome["actual_main_input_output_paths_used"] is False
    assert not read_plain(directory / "stderr.log")
    ids = [item["case"] for item in outcome["cases"]]
    assert len(ids) == len(set(ids)) == 36
    if case_ids is None:
        case_ids = ids
    else:
        assert ids == case_ids
    if receipt_name == "exit.json":
        assert receipt["inputs_unchanged"] is True
        plan = parsed(directory / "plan.json")
        assert plan["IG_FORBIDDEN_LIVE_set_before_startup"] is True
        for name, expected in plan["input_sha256"].items():
            assert sha(read_plain(directory / name)) == expected
    else:
        assert receipt["source_sha256_before"] == receipt["source_sha256_after"] == SOURCE_SHA
        assert receipt["harness_sha256_before"] == receipt["harness_sha256_after"]
        assert receipt["forbidden_live_binding_set_before_startup"] is True

refused = parsed(REFUSED_RECEIPT)
assert refused["status"] == "refused" and refused["reason"] == "Reference cycle refused" and refused["reader_exit"] == 2
assert refused["artifact"]["bytes"] == 17719103
assert refused["artifact"]["sha256"] == "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
assert refused["zip_directory"]["members"] == 131
assert "pickle_static_inventory" not in refused and refused["release_acceptance"] is False
refused_exit = parsed(REFUSED / "exit.json")
assert refused_exit["actual_process_exit"] == 2 and refused_exit["reader_unchanged"] is True
assert refused_exit["reader_sha256_after"] == "0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc"

payloads = []
for directory, prefix in ((PROPOSAL, "cycle-diagnostic-proposal"), (PRIOR, "prior-adapter-proof"),
                           (INDEPENDENT, "independent-qualification"), (REFUSED, "preserved-symbolic-run01/launch")):
    for path in sorted(directory.rglob("*")):
        if path.is_dir():
            assert not path.is_symlink() and not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
            continue
        payloads.append((prefix + "/" + path.relative_to(directory).as_posix(), read_plain(path)))
for source, name in ((REVIEW, "independent-review/FINAL-REVIEW.md"),
                     (REFUSED_RECEIPT, "preserved-symbolic-run01/symbolic-run01.json"),
                     (ROOT / "launch_vad_symbolic_run01.py", "preserved-symbolic-run01/launch_vad_symbolic_run01.py"),
                     (ROOT / "VAD-SYMBOLIC-RUN01-BRIEF-2026-09-13.md", "preserved-symbolic-run01/BRIEF-2026-09-13.md"),
                     (ROOT / "qualify_cycle_astra01.py", "independent-qualification/qualify_cycle_astra01.py"),
                     (ROOT / "prepare_cycle_qualifier01.py", "independent-qualification/prepare_cycle_qualifier01.py")):
    payloads.append((name, read_plain(source)))
payloads.append((".gitattributes", b"* -text\n"))
assert len(payloads) < 250 and len({name for name, _ in payloads}) == len(payloads)
TARGET.mkdir()
records = []
for name, data in sorted(payloads):
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data)
    assert destination.read_bytes() == data
    records.append({"path": name, "sha256": sha(data), "bytes": len(data)})
manifest = {"scope": "Bounded cycle refusal diagnostic preparation; synthetic checks only; prior actual cycle refusal remains refused; no model acceptance",
            "payload_count": len(records), "payloads": records}
encoded = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
with (TARGET / "SHA256.json").open("xb") as stream:
    stream.write(encoded)
for entry in records:
    assert sha((TARGET / entry["path"]).read_bytes()) == entry["sha256"]
assert sha(read_plain(PRIOR / "SHA256.json")) == PRIOR_SHA
print(json.dumps({"target": str(TARGET), "payload_count": len(records), "manifest_sha256": sha(encoded),
                  "all_payload_hashes_verified": True, "original_108_seal_unchanged": True,
                  "actual_checkpoint_read_by_sealer": False}, indent=2))
