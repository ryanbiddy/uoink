"""Seal fixed scratch source and saved receipts; no actual artifact access."""
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
PROPOSAL = ROOT / "vad-selected-root-projection-proposal01"
PRIOR = ROOT / "vad-symbolic-cycle-diagnostic-final-proof01"
REFUSED = ROOT / "vad-symbolic-cycle01-launch"
REFUSED_RECEIPT = ROOT / "vad-symbolic-adapter-proposal01/results/symbolic-cycle01.json"
REVIEW = ROOT / "vad-symbolic-review01/SELECTED-PROJECTION-FINAL-REVIEW.md"
TARGET = ROOT / "vad-selected-root-projection-final-proof01"
SOURCE_SHA = "0b62dcac9962ee0620ed8c8af6deca169ce5aeab215994b637f5902dd79ddb73"
HARNESS_SHA = "6e0a19710f0a899f3d68dbff9d5d741118879d7c94fa0f42114b37208109e01a"
PRIOR_SHA = "94f3bddc87892b013f67eb989be4d060791e91bea1f8106c029d6a135c5f56f5"
REVIEW_SHA = "1adcf5ed8fc1d5ae67d60b18a09d70f0494d28f7912afc9440804f1ad53b7638"


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
parser.add_argument("--independent-dir", required=True)
parser.add_argument("--wrapper", required=True)
parser.add_argument("--generator")
args = parser.parse_args()
independent = Path(args.independent_dir)
assert independent.parent == ROOT and independent.name.startswith("astra-") and "projection" in independent.name
assert not TARGET.exists(), "Fresh seal directory required"
assert sha(read_plain(PROPOSAL / "read_symbolic_inventory.py")) == SOURCE_SHA
assert sha(read_plain(PROPOSAL / "qualify_projection.py")) == HARNESS_SHA
assert sha(read_plain(REVIEW)) == REVIEW_SHA
assert sha(read_plain(PRIOR / "SHA256.json")) == PRIOR_SHA
prior_manifest = parsed(PRIOR / "SHA256.json")
assert prior_manifest["payload_count"] == len(prior_manifest["payloads"]) == 158
for entry in prior_manifest["payloads"]:
    data = read_plain(PRIOR / entry["path"])
    assert len(data) == entry["bytes"] and sha(data) == entry["sha256"]
assert {path.relative_to(PRIOR).as_posix() for path in PRIOR.rglob("*") if path.is_file()} == {entry["path"] for entry in prior_manifest["payloads"]} | {"SHA256.json"}

case_ids = None
for directory, receipt_name in ((PROPOSAL / "projection-preflight01", "launch-receipt.json"), (independent, "exit.json")):
    outcome, receipt = parsed(directory / "stdout.json"), parsed(directory / receipt_name)
    assert (outcome["passed"], outcome["failed"]) == (63, 0)
    assert receipt["actual_qualification_exit"] == 0
    assert outcome["source_sha256"] == SOURCE_SHA
    assert outcome["forbidden_live_startup_binding_asserted"] is True
    assert outcome["actual_checkpoint_opened"] is False and outcome["actual_main_input_output_paths_used"] is False
    assert not read_plain(directory / "stderr.log")
    ids = [item["case"] for item in outcome["cases"]]
    assert len(ids) == len(set(ids)) == 63
    if case_ids is None:
        case_ids = ids
    else:
        assert ids == case_ids
    if receipt_name == "exit.json":
        assert receipt["inputs_unchanged"] is True
        plan = parsed(directory / "plan.json")
        assert plan["IG_FORBIDDEN_LIVE_set_before_startup"] is True
        assert len(plan["input_sha256"]) == 5
        for name, expected in plan["input_sha256"].items():
            assert sha(read_plain(directory / name)) == expected
    else:
        assert receipt["source_sha256_before"] == receipt["source_sha256_after"] == SOURCE_SHA
        assert receipt["harness_sha256_before"] == receipt["harness_sha256_after"] == HARNESS_SHA
        assert receipt["forbidden_live_binding_set_before_startup"] is True

refused = parsed(REFUSED_RECEIPT)
assert refused["status"] == "refused" and refused["reason"] == "Reference cycle refused" and refused["reader_exit"] == 2
assert refused["artifact"]["bytes"] == 17719103 and refused["artifact"]["sha256"] == "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
assert refused["zip_directory"]["members"] == 131 and refused["release_acceptance"] is False
witness = refused["refusal_context"]["reference_cycle"]
assert witness["cycle_node_count"] == 5
assert witness["detected_entry_path"] == {"category": "known_training_root"}
assert witness["entry_path_is_exclusive_ownership"] is False
assert "selected_root_projection" not in refused["refusal_context"]
refused_exit = parsed(REFUSED / "exit.json")
assert refused_exit["actual_process_exit"] == 2 and refused_exit["reader_unchanged"] is True
assert refused_exit["reader_sha256_after"] == "15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd"

payloads = []
for directory, prefix in ((PROPOSAL, "projection-proposal"), (PRIOR, "prior-cycle-proof"),
                           (independent, "independent-qualification"), (REFUSED, "preserved-symbolic-cycle01/launch")):
    for path in sorted(directory.rglob("*")):
        if path.is_dir():
            assert not path.is_symlink() and not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
            continue
        payloads.append((prefix + "/" + path.relative_to(directory).as_posix(), read_plain(path)))
extra = [(REVIEW, "independent-review/FINAL-REVIEW.md"),
         (REFUSED_RECEIPT, "preserved-symbolic-cycle01/symbolic-cycle01.json"),
         (ROOT / "launch_vad_cycle01.py", "preserved-symbolic-cycle01/launch_vad_cycle01.py"),
         (ROOT / "projection-root-launch-console01.log", "independent-qualification/projection-root-launch-console01.log"),
         (Path(args.wrapper), "independent-qualification/" + Path(args.wrapper).name)]
if args.generator:
    extra.append((Path(args.generator), "independent-qualification/" + Path(args.generator).name))
for source, name in extra:
    payloads.append((name, read_plain(source)))
payloads.append((".gitattributes", b"* -text\n"))
assert len(payloads) < 300 and len({name for name, _ in payloads}) == len(payloads)
TARGET.mkdir()
records = []
for name, data in sorted(payloads):
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data)
    assert destination.read_bytes() == data
    records.append({"path": name, "sha256": sha(data), "bytes": len(data)})
manifest = {"scope": "Partial untrusted selected-root projection preparation, synthetic checks only; strict artifact refusals remain; no actual projection or model acceptance",
            "payload_count": len(records), "payloads": records}
encoded = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
with (TARGET / "SHA256.json").open("xb") as stream:
    stream.write(encoded)
for entry in records:
    assert sha((TARGET / entry["path"]).read_bytes()) == entry["sha256"]
assert sha(read_plain(PRIOR / "SHA256.json")) == PRIOR_SHA
print(json.dumps({"target": str(TARGET), "payload_count": len(records), "manifest_sha256": sha(encoded),
                  "all_payload_hashes_verified": True, "original_158_seal_unchanged": True,
                  "actual_checkpoint_read_by_sealer": False}, indent=2))
