"""BA-3 contradictions between the measurement record and captured behavior."""
from pathlib import Path
import sys

from test_phase5_acceptance import analysis, db, filed, isolate_reader, report
from test_phase5_measurements2 import benchmark_capture


ROOT = Path(__file__).resolve().parents[2]


def measurement_doc():
    return (ROOT / "docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md").read_text(encoding="utf-8")


def test_phase5_ba3_measurement_record_acknowledges_observed_row_shedding(benchmark_capture):
    doc = measurement_doc()
    primary = benchmark_capture[:2]
    for record, claim in zip(primary, ("without pruning", "row shedding did not occur")):
        if claim in doc:
            assert record["rows"]["events"] == 20 and record["rows"]["joint"] == 20, (claim, record)


def test_phase5_ba3_measurement_record_does_not_claim_replay_was_skipped(db):
    doc = measurement_doc()
    filed(db)
    replayed = []
    previous_profile = sys.getprofile()
    def observe_return(frame, event, arg):
        if event == "return" and frame.f_code is analysis._execute_activity.__code__:
            replayed.append(any(frame.f_locals.get("projected_state", {}).values()))
    try:
        sys.setprofile(observe_return)
        packet = report(db, interval={"start": "2026-09-01T00:00:00Z", "end": "2026-09-02T00:00:00Z"})
    finally:
        sys.setprofile(previous_profile)
    assert packet["ok"] and "interval_precedes_first_apply" in packet["coverage"]["cov_shelf_activity"]["reasons"]
    assert replayed, "The benchmark path was not observed"
    if "baseline replay path was skipped" in doc:
        assert not any(replayed), "The reader populated the replay state before rejecting the early interval"


def test_phase5_ba3_measurement_record_labels_handbuilt_transport_timing():
    doc = measurement_doc()
    row = next(line for line in doc.splitlines() if line.startswith("| **Transport Serialization**"))
    assert "actual stdio adapter" not in row, row
    assert any(label in row.lower() for label in ("hand-built", "handbuilt", "synthetic envelope")), row
