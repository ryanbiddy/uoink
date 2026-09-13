"""Validate only this fixed ordinary-test partition; no outcome rewriting."""
from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SAVED = HERE / "pytest-receipts01"
def record(path):
    return json.loads(path.read_bytes())

actual = record(HERE / "pytest-native-exit01.json")
bootstrap = record(HERE / "pytest-bootstrap01.json")
partition = SAVED / "notice01-partition"
selected = record(partition / "membership.json")
assert selected == record(HERE / "EXPECTED-PYTEST-MEMBERSHIP.json")
assert len(selected) == len(set(selected)) == 20
session = record(partition / "session.json")
reports = [json.loads(line) for line in (partition / "reports.jsonl").read_text(encoding="utf8").splitlines()]
assert [row["report_index"] for row in reports] == list(range(len(reports)))
counts = Counter(passed=0, failed=0, skipped=0)
for row in reports:
    assert row["nodeid"] in selected and row["report_type"] == "TestReport"
    assert row["subtest"] is None and row["wasxfail"] is None
    assert row["outcome"] == row["outcome_before_hooks"]
    assert row["outcome_transition_reason"] is None
    assert row["outcome"] in {"passed", "failed", "skipped"}
for nodeid in selected:
    rows = [row for row in reports if row["nodeid"] == nodeid]
    assert rows and rows[0]["when"] == "setup"
    assert [row["when"] for row in rows] == (["setup", "call", "teardown"]
        if rows[0]["outcome"] == "passed" else ["setup", "teardown"])
    outcomes = {row["outcome"] for row in rows}
    counts["failed" if "failed" in outcomes else "skipped" if "skipped" in outcomes else "passed"] += 1
failed_reports = sum(row["outcome"] == "failed" for row in reports)
assert session == {"exit": actual["native_exit"], "tests_collected": 20,
                   "tests_failed": failed_reports, "reports": len(reports)}
assert actual["native_exit"] == bootstrap["pytest_exit"] == int(bool(failed_reports))
assert bootstrap["entry"] == "pytest.main(arguments, plugins=[heavy])"
assert all(bootstrap[key] is True for key in ("isolated", "no_site", "no_bytecode", "heavy_guard_present", "forbidden_live_binding"))
assert bootstrap["added_import_roots"] == [str(HERE.parents[1]), r"C:\Users\hello\AppData\Roaming\Python\Python314\site-packages"]
guard = record(SAVED / "notice01-heavy.json")
assert guard["already_loaded_at_startup"] == guard["blocked_import_attempts"] == []
assert guard["guard_installed_at_finish"] is True
assert guard["pytest_exitstatus"] == actual["native_exit"]
suites = list(ET.fromstring((SAVED / "notice01.xml").read_bytes()).iter("testsuite"))
assert sum(int(suite.attrib["tests"]) for suite in suites) == 20
assert sum(int(suite.attrib["failures"]) + int(suite.attrib["errors"]) for suite in suites) == failed_reports
assert sum(int(suite.attrib["skipped"]) for suite in suites) == counts["skipped"]
result = {"case_count": 20, "counts": dict(counts), "pytest_exit": actual["native_exit"],
          "ordinary_reports": len(reports), "heavy_import_attempts": 0,
          "full_build_or_model_execution": False}
with (HERE / "pytest-validated01.json").open("x", encoding="utf8") as output:
    json.dump(result, output, indent=2)
print(json.dumps(result))
raise SystemExit(actual["native_exit"])
