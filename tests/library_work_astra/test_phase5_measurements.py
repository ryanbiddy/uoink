"""Reproduce AZ's benchmark and compare its recorded fixture with the report."""
import re
from pathlib import Path

import library_analysis
from tests import test_library_analysis_fixtures as az


def test_phase5_measurement_548_journal_matches_report(tmp_path, monkeypatch):
    real_read = library_analysis.get_library_activity
    records = []

    def measured_read(args, **kwargs):
        conn = kwargs["db"]
        record = {
            "items": conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0],
            "memberships": conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM source_items").fetchone()[0],
            "applies": conn.execute("SELECT COUNT(*) FROM library_applies").fetchone()[0],
            "journal_bytes": conn.execute("SELECT SUM(LENGTH(CAST(forward_json AS BLOB)) + LENGTH(CAST(inverse_json AS BLOB))) FROM library_applies").fetchone()[0],
        }
        result = real_read(args, **kwargs)
        record["ok"] = result["ok"]
        if result["ok"]:
            record["display_rows"] = {
                "events": len(result["events"]["rows"]),
                "creators": len(result["items"]["by_creator_hint"]),
                "joint": len(result["items"]["by_type_creator_hint"]),
                "sources": len(result["sources"]["details"]),
                "shelves": len(result["shelf_activity"]["shelves"]),
            }
            record["baseline_reason"] = result["coverage"]["cov_shelf_activity"].get("reasons")
        records.append(record)
        return result

    library_analysis.reset_rate_limiter()
    monkeypatch.setattr(library_analysis, "get_library_activity", measured_read)
    az.test_activity_cost_548_and_10000(tmp_path)
    print("BA observed fixture dimensions:", records)
    doc = (Path(__file__).resolve().parents[2] / "docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md").read_text(encoding="utf-8")
    cell = re.search(r"\*\*Combined Journal Deltas\*\*\s*\|\s*([\d.]+) KiB", doc)
    assert cell, "Measurement report must record its 548-item journal size"
    measured_kib = records[0]["journal_bytes"] / 1024
    discrepancies = []
    if abs(float(cell[1]) - measured_kib) > 0.1:
        discrepancies.append(f"548-item journal: report={cell[1]} KiB, observed={measured_kib} KiB")
    if "shedder dropped" in doc and records[1]["display_rows"] == {"events": 20, "creators": 20, "joint": 20, "sources": 1, "shelves": 1}:
        discrepancies.append("10k response retains all initial display pages; report says the shedder dropped arrays")
    assert not discrepancies, discrepancies
