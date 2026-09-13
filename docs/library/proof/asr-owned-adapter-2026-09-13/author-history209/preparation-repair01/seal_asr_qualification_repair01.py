"""Seal current source-only preparation; no proposal imports or execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-production-adapter-qualification-repair01")


def write(name, value):
    with (ROOT / name).open("xb") as stream:
        stream.write(json.dumps(value, indent=2).encode() + b"\n")


write("SOURCE-PREPARATION-TOOL-RESULTS.json", {
    "source_preparation": {"chunk_id": "1bab06", "actual_exit_code": 0, "wall_time_seconds": 0.1475179,
        "operation": "C:\\Python314\\python.exe -I -S -B _scratch\\prepare_asr_qualification_repair01.py",
        "scope": "Text copy, hashes, source derivation and AST comparison only"},
    "powershell_syntax": {"chunk_id": "dfce34", "actual_exit_code": 0, "wall_time_seconds": 0.1138627,
        "operation": "PowerShell Parser.ParseFile plus receipt serialization", "parse_errors": 0},
    "qualification_cases_executed": 0, "prepared_sources_executed": False})
names = ["asr_loading_adapter.py", "review-inputs/trusted_asr_resolver.py", "qualify_adapter.py", "run_preflight02.ps1",
         "BRIEF.md", "QUALIFICATION02-PROTOCOL.md", "WRAPPER-OUTCOME-QUALIFICATION-PLAN.md",
         "original-proposal/PREPARATION-SHA256.json", "NATIVE-RECEIPT-BLOCK.ps1.txt"]
write("INPUT-BINDINGS.json", {"date": "2026-09-13", "execution_admitted": False,
      "files": [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                 "bytes": len((ROOT / name).read_bytes())} for name in names]})
with (ROOT / "seal_asr_qualification_repair01.py").open("xb") as stream:
    stream.write(Path(__file__).read_bytes())
rows = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
assert not any(row["path"] == "SHA256.json" for row in rows)
write("SHA256.json", {"schema": "uoink.asr-qualification-repair-preparation.v1", "date": "2026-09-13",
      "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
      "planned_asr_cases": 58, "qualification_executed": False, "real_approval_available": False, "files": rows})
print(json.dumps({"payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
      "manifest_sha256": hashlib.sha256((ROOT / "SHA256.json").read_bytes()).hexdigest()}))
