"""Verify only sealed source/document bytes and static ASTs. Executes no proposal."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent


def check_rows(base, rows):
    for row in rows:
        name = row["path"]
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        raw = (base / name).read_bytes()
        assert len(raw) == row["bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"], name


seal = json.loads((ROOT / "SHA256.json").read_bytes())
check_rows(ROOT, seal["files"])
expected = {row["path"] for row in seal["files"]} | {"SHA256.json"}
actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
assert actual == expected, (sorted(actual - expected), sorted(expected - actual))
original = json.loads((ROOT / "original-proposal/PREPARATION-SHA256.json").read_bytes())
check_rows(ROOT / "original-proposal", original["files"])
before = ast.parse((ROOT / "original-proposal/qualify_adapter.py").read_bytes())
after = ast.parse((ROOT / "qualify_adapter.py").read_bytes())
for kind in (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assert):
    assert ([ast.dump(n, include_attributes=False) for n in ast.walk(before) if isinstance(n, kind)]
            == [ast.dump(n, include_attributes=False) for n in ast.walk(after) if isinstance(n, kind)])
assert (ROOT / "asr_loading_adapter.py").read_bytes() == (ROOT / "original-proposal/asr_loading_adapter.py").read_bytes()
resolver = ast.parse((ROOT / "review-inputs/trusted_asr_resolver.py").read_bytes())
approvals = [n for n in resolver.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "REAL_APPROVAL" for t in n.targets)]
assert len(approvals) == 1 and isinstance(approvals[0].value, ast.Constant) and approvals[0].value.value is None
runner = (ROOT / "run_preflight02.ps1").read_text(encoding="utf-8")
block = runner.split("# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split("# END EXACT NATIVE RECEIPT BLOCK", 1)[0]
assert block.encode() == (ROOT / "NATIVE-RECEIPT-BLOCK.ps1.txt").read_bytes()
assert runner.index("$taskNativeStream.Flush($true)") < runner.index("$taskAfter=@()")
assert "68eaeeaaa3d32d6c97102aae17e4f7490702a495b9e2cb72adf38aab438ff545" in runner
assert (ROOT / ".gitattributes").read_bytes() == b"* -text\n"
assert "ROOT-ADMISSION.md" not in actual
print(json.dumps({"all_sealed_bytes_verified": True, "payload_count": len(seal["files"]),
                  "original_payloads_verified": len(original["files"]), "all_function_assertion_asts_unchanged": True,
                  "real_approval_literal_none": True, "static_only": True, "qualification_cases_executed": 0}))
