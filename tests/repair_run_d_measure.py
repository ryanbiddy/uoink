"""Reproduce run D copy-only measurements. No helper or model execution.

Usage: python tests/repair_run_d_measure.py --source <named-copy> --out <new-dir>
The source fingerprint is checked before SQLite opens any disposable duplicate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import index
import library_cards
import uoink_mcp_tools

EXPECTED_HASH = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def script(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def counts(conn):
    return dict(zip(("clips", "over_120_seconds", "over_180_seconds", "max_seconds"), conn.execute(
        'SELECT count(*), sum("end"-start>120), sum("end"-start>180), max("end"-start) FROM clips').fetchone()))


def compare(conn, path):
    dryrun, cost = script("scripts/librarian/dryrun.py"), script("scripts/library/cost_model.py")
    idx = index.Index(conn, path)
    uoink_mcp_tools.bind_backend(SimpleNamespace(_get_index=lambda: idx))
    result = {}
    for profile, n in (("full", 10), ("librarian", 6)):
        first = dryrun.build_cards(conn, per_item=n, profile=profile)
        second = cost.build_cards(conn, n_clips=n, profile=profile)
        different = 0
        for card, other in zip(first, second):
            live_handler = uoink_mcp_tools.get_evidence_card({"video_id": card["video_id"], "profile": profile})
            assert live_handler.pop("ok")
            different += card != other or card != live_handler
        assert len(first) == len(second) == 548
        assert different == 0
        max_bytes = max(len(library_cards.card_text(c).encode("utf-8")) for c in first)
        if profile == "librarian":
            assert max_bytes <= library_cards.LIBRARIAN_BYTE_BUDGET
        result[profile] = {"items": len(first), "caller_mismatches": different,
                           "evidence_kinds": dict(Counter(c["evidence_kind"] for c in first)),
                           "max_serialized_bytes": max_bytes,
                           "cards_hash": hashlib.sha256(library_cards.serialize_card(first).encode()).hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    # An arbitrary index, including a live one, is never accepted.
    if source.name != "uoink-index-copy-2026-09-04-upgraded.db":
        raise ValueError("only the dispatched named copy is permitted")
    assert digest(source) == EXPECTED_HASH
    out = args.out.resolve()
    assert out.is_relative_to(ROOT) and not out.exists()
    out.mkdir(parents=True)
    frozen, writable = out / "frozen.db", out / "rebuild.db"
    shutil.copyfile(source, frozen)
    shutil.copyfile(source, writable)
    assert digest(frozen) == digest(writable) == EXPECTED_HASH
    conn = sqlite3.connect(frozen.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        report = {"source_date": "2026-09-04", "source_sha256": EXPECTED_HASH,
                  "before": counts(conn), "cards_before": compare(conn, frozen)}
    finally:
        conn.close()
    with index.Index.open(writable) as idx:
        report["after_upgrade"] = counts(idx._conn)
        report["schema"] = idx.schema_version()
        report["rebuild"] = idx.rebuild_clips()
        first = idx._conn.execute('SELECT video_id, seq, start, end, text, cue_count, source_deep_link FROM clips ORDER BY video_id, seq').fetchall()
        report["repeat_rebuild"] = idx.rebuild_clips()
        second = idx._conn.execute('SELECT video_id, seq, start, end, text, cue_count, source_deep_link FROM clips ORDER BY video_id, seq').fetchall()
        assert first == second
        report["rebuild_payload_sha256"] = hashlib.sha256(json.dumps([list(r) for r in first], ensure_ascii=False).encode()).hexdigest()
        report["after"] = counts(idx._conn)
        report["cards_after"] = compare(idx._conn, writable)
        assert idx._conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not idx._conn.execute("PRAGMA foreign_key_check").fetchall()
        idx._conn.execute("INSERT INTO clips_fts(clips_fts, rank) VALUES('integrity-check', 1)")
        idx._conn.commit()
        report["integrity"] = "quick_check, foreign_key_check, FTS external-content integrity passed"
        report["oversize_fine_windows"] = idx._conn.execute(
            'SELECT count(*) FROM clips WHERE "end"-start>120 AND (cue_count>1 OR length(text)>1200)').fetchone()[0]
        assert report["oversize_fine_windows"] == 0
    case = out / "precedence.db"
    shutil.copyfile(source, case)
    conn = sqlite3.connect(case)
    target = conn.execute("SELECT video_id FROM yoinks ORDER BY video_id LIMIT 1").fetchone()[0]
    conn.execute("UPDATE yoinks SET platform='x', source_type='x_thread', metadata_json=? WHERE video_id=?",
                 (json.dumps({"source_type": "x_article", "url": "https://x.com/fixture/status/1"}), target))
    conn.commit()
    conn.close()
    with index.Index.open(case) as idx:
        report["copy_x_article_case"] = idx.get_yoink(target)["source_type"]
        assert report["copy_x_article_case"] == "x_article"
    assert digest(source) == EXPECTED_HASH
    report["source_unchanged"] = True
    (out / "measurements.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
