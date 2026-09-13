"""Data-only source/seal verification; never executes a proposal or diagnostic."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
seal = json.loads((ROOT / "SHA256.json").read_bytes())
for row in seal["files"]:
    raw = (ROOT / row["path"]).read_bytes()
    assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
runner = (ROOT / "candidate/run_preflight03.ps1").read_bytes()
block = (ROOT / "candidate/NATIVE-RECEIPT-BLOCK.ps1.txt").read_bytes()
assert runner.split(b"# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split(b"# END EXACT NATIVE RECEIPT BLOCK", 1)[0] == block
for name in ("wrapper-missing02.ps1", "wrapper-success02.ps1"):
    wrapper = (ROOT / "instrument02" / name).read_bytes()
    assert wrapper.split(b"# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split(b"# END EXACT NATIVE RECEIPT BLOCK", 1)[0] == block
assert b"$global:LASTEXITCODE=$null" in block and b"$taskNativeExit=$global:LASTEXITCODE" in block
assert block.index(b"Flush($true)") < block.index(b"$taskNativeExit -isnot [int]")
assert (ROOT / "candidate/qualify_adapter.py").read_bytes() == (ROOT / "before/qualify_adapter.py").read_bytes()
assert json.loads((ROOT / "failure01/missing01/native-exit.json").read_bytes())["native_exit"] is None
failed_seal = json.loads((ROOT / "failure01/SHA256.json").read_bytes())
for row in failed_seal["files"]:
    raw = (ROOT / "failure01" / row["path"]).read_bytes()
    assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
print(json.dumps({"payloads_verified": len(seal["files"]), "failure_payloads_verified": len(failed_seal["files"]),
                  "candidate_blocks_identical": True, "old_failure_native_value_preserved": None,
                  "static_only": True, "diagnostic_or_qualification_executed": False}))
