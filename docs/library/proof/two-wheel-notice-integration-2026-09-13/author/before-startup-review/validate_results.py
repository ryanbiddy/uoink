"""Use the existing pure partition contract on saved notice-test receipts."""
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OVERLAY = HERE / "overlay"
SAVED = OVERLAY / "_scratch"
spec = importlib.util.spec_from_file_location("notice_partition_contract", SAVED / "partition_exit_contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def record(path):
    return json.loads(path.read_bytes())


actual = record(HERE / "pytest-native-exit01.json")
partition = SAVED / "notice01-partition"
selected = record(partition / "membership.json")
assert selected == record(HERE / "EXPECTED-PYTEST-MEMBERSHIP.json")
reports = [json.loads(line) for line in (partition / "reports.jsonl").read_text(encoding="utf8").splitlines()]
result = contract.validate_partition(selected=selected, reports=reports,
    session=record(partition / "session.json"), verifier_results=record(SAVED / "notice01/results.json"),
    outer_exit=actual["native_exit"], junit_xml=(SAVED / "notice01/tests.xml").read_bytes())
guard = contract.validate_heavy_guard(record(SAVED / "notice01-heavy.json"), result["pytest_exit"])
assert guard["blocked_attempt_count"] == 0
result["heavy_guard"] = guard
result["full_build_or_model_execution"] = False
with (HERE / "pytest-validated01.json").open("x", encoding="utf8") as output:
    json.dump(result, output, indent=2)
print(json.dumps({"case_count": result["case_count"], "counts": result["counts"], "pytest_exit": result["pytest_exit"], "outer_exit": result["outer_exit"], "heavy_import_attempts": 0}))
raise SystemExit(result["outer_exit"])
