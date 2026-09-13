"""Read-only XML count clarification; no test execution or prior proof edits."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parents[1]
out = root / "_scratch/agw-count-clarification.json"
assert not out.exists()
rows = []
for label, expected in (("agw01", 11), ("agw02", 144)):
    xml = root / "_scratch" / label / "tests.xml"
    suite = ET.fromstring(xml.read_bytes()).find("testsuite")
    rows.append({"label": label, "pytest_passed_cases": expected, "passed_subtests": 13,
                 "junit_tests_attribute": int(suite.attrib["tests"]),
                 "junit_testcase_elements": len(suite.findall("testcase")),
                 "xml_sha256": hashlib.sha256(xml.read_bytes()).hexdigest()})
    assert rows[-1]["junit_tests_attribute"] == expected + 13
    assert rows[-1]["junit_testcase_elements"] == expected
prior = root / "_scratch/agw-proof/SHA256.json"
assert hashlib.sha256(prior.read_bytes()).hexdigest() == "d314a63292d7bc0092c2fc715aeafc6fe65c21de418939f3f4c8b2bf800ee56f"
out.write_text(json.dumps({"rows": rows, "prior_seal_unchanged": True,
                           "rerun": False, "fixture_change": False}, indent=2) + "\n", encoding="utf-8")
print(json.dumps(rows))
