"""Compare saved JSON receipts only. Does not import or invoke either reader."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys


HERE = Path(__file__).absolute().parent
BASELINE = HERE / "baseline-run03/run03.json"
CURRENT = HERE / "run04/run04.json"
LAUNCH = HERE / "run04/launch/result.json"
ALLOWED = {os.path.normcase(os.path.abspath(path)) for path in (BASELINE, CURRENT, LAUNCH)}
TAIL_FIELDS = ("identifier_string_tail_samples", "string_tail_sample_limit")
TIME_FIELDS = ("started_utc", "elapsed_seconds")
ARTIFACT_SHA = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
PICKLE_SHA = "5f9180875a42f5279496ecddcde3939caac3b257f66037d338d3865c16a02bf4"
READER_SHA = "67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5"
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.\[\]-]{0,95}\Z")


def audit(event, args):
    if event == "open":
        if not isinstance(args[0], (str, bytes, os.PathLike)) or os.path.normcase(os.path.abspath(os.fsdecode(args[0]))) not in ALLOWED:
            raise RuntimeError("Only the three explicit saved receipts may be opened")
    if event.startswith(("socket.", "subprocess.", "os.system", "ctypes.")):
        raise RuntimeError("Network/process/native actions are prohibited")


assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
sys.addaudithook(audit)
before_bytes, after_bytes, launch_bytes = BASELINE.read_bytes(), CURRENT.read_bytes(), LAUNCH.read_bytes()
before, after, launch = (json.loads(value) for value in (before_bytes, after_bytes, launch_bytes))
assert before["status"] == after["status"] == "static_inventory_complete"
assert before["reader_exit"] == after["reader_exit"] == launch["actual_process_exit"] == 0
assert launch["reader_unchanged"] is True and launch["reader_sha256_after"] == READER_SHA
assert before["artifact"]["sha256"] == after["artifact"]["sha256"] == ARTIFACT_SHA
assert before["artifact"]["bytes"] == after["artifact"]["bytes"] == 17719103
assert before["pickle_static_inventory"]["sha256"] == after["pickle_static_inventory"]["sha256"] == PICKLE_SHA
assert set(after["pickle_static_inventory"]) - set(before["pickle_static_inventory"]) == set(TAIL_FIELDS)
assert set(before["pickle_static_inventory"]) - set(after["pickle_static_inventory"]) == set()
tail = after["pickle_static_inventory"][TAIL_FIELDS[0]]
assert after["pickle_static_inventory"][TAIL_FIELDS[1]] == 64
assert len(tail) == 64 and all(isinstance(token, str) and IDENTIFIER.fullmatch(token) for token in tail)
for field in TAIL_FIELDS:
    assert field not in before["pickle_static_inventory"]
    del after["pickle_static_inventory"][field]
for field in TIME_FIELDS:
    del before[field]
    del after[field]
assert before == after, "Inventory facts differ beyond the exact four excluded field paths"
canonical = json.dumps(before, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
print(json.dumps({
    "scope": "Saved-receipt comparison only; no artifact or reader execution",
    "comparison": "all_remaining_inventory_facts_equal",
    "excluded_paths": ["started_utc", "elapsed_seconds", "pickle_static_inventory.identifier_string_tail_samples",
                       "pickle_static_inventory.string_tail_sample_limit"],
    "baseline_receipt_sha256": hashlib.sha256(before_bytes).hexdigest(),
    "current_receipt_sha256": hashlib.sha256(after_bytes).hexdigest(),
    "current_launch_result_sha256": hashlib.sha256(launch_bytes).hexdigest(),
    "canonical_remaining_facts_sha256": hashlib.sha256(canonical).hexdigest(),
    "artifact_sha256": ARTIFACT_SHA, "pickle_member_sha256": PICKLE_SHA,
    "reader_sha256": READER_SHA, "measured_run04_reader_exit": launch["actual_process_exit"],
    "tail_literal_count": len(tail), "tail_literal_maximum_characters": max(map(len, tail)),
    "tail_literal_observations_in_order": tail,
    "architecture_established": False, "configuration_established": False,
    "objects_constructed_by_comparison": False, "checkpoint_opened_by_comparison": False,
    "comparison_exit": 0
}, indent=2))
