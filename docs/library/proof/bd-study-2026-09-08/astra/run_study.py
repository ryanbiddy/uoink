"""Measure the frozen BD tasks without loading transcripts or media.

Only the sealed extracted chapter metadata and pre-Phase 6 clips are inputs to
navigation. Chapter-only publication replaces selected disposable rows with an
explicit empty transcript; it does not pretend that clips are original cues.
"""
import ast
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parent
ROOT = HERE.parents[4]
SCRATCH = ROOT / "_scratch" / "bd" / "study"
sys.path.insert(0, str(ROOT))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def output(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def rebind_paths(conn):
    """No original corpus or sidecar path is ever opened."""
    counts = {}
    for vid, in conn.execute("SELECT video_id FROM yoinks").fetchall():
        folder = SCRATCH / "items" / sha(vid.encode())
        conn.execute("UPDATE yoinks SET corpus_path=?,sidecar_path=? WHERE video_id=?",
                     (str(folder / "corpus.md"), str(folder / "corpus.json"), vid))
    counts["yoinks"] = conn.execute("SELECT count(*) FROM yoinks").fetchone()[0]
    counts["citation_paths"] = conn.execute("SELECT count(*) FROM citations WHERE file_path IS NOT NULL").fetchone()[0]
    conn.execute("UPDATE citations SET file_path=? WHERE file_path IS NOT NULL",
                 (str(SCRATCH / "unavailable" / "citation-file"),))
    for column in ("audio_local_path", "transcript_local_path"):
        counts[column] = conn.execute(f"SELECT count(*) FROM podcast_episodes WHERE {column} IS NOT NULL").fetchone()[0]
        conn.execute(f"UPDATE podcast_episodes SET {column}=? WHERE {column} IS NOT NULL",
                     (str(SCRATCH / "unavailable" / column),))
    absolute = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
    rewritten = 0

    def transform(value):
        nonlocal rewritten
        if isinstance(value, dict):
            return {key: transform(v) for key, v in value.items()}
        if isinstance(value, list):
            return [transform(v) for v in value]
        if isinstance(value, str) and absolute.match(value):
            rewritten += 1
            return str(SCRATCH / "unavailable" / sha(value.encode()))
        return value

    # Embedded JSON can carry paths independently of explicit SQL path columns.
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql NOT LIKE '%VIRTUAL TABLE%'").fetchall()
    for table, in tables:
        columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for column in [c for c in columns if "json" in c]:
            for rowid, raw in conn.execute(f'SELECT rowid,"{column}" FROM "{table}" WHERE "{column}" IS NOT NULL').fetchall():
                try:
                    before = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                after = transform(before)
                if before != after:
                    conn.execute(f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',
                                 (json.dumps(after, ensure_ascii=False), rowid))
    counts["embedded_json_paths"] = rewritten
    conn.commit()
    for table, columns in (("yoinks", ("corpus_path", "sidecar_path")),
                           ("citations", ("file_path",)),
                           ("podcast_episodes", ("audio_local_path", "transcript_local_path"))):
        for column in columns:
            for value, in conn.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'):
                assert Path(value).resolve().is_relative_to(SCRATCH)
    return counts


def main():
    expected = (HERE / "TASK-MANIFEST.sha256").read_text().split()[0]
    assert sha((HERE / "task-manifest.json").read_bytes()) == expected
    tasks = read_json(HERE / "task-manifest.json")
    inputs = read_json(INPUTS / "study-inputs-manifest.json")
    for line in (INPUTS / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        assert sha((INPUTS / name.strip()).read_bytes()) == digest
    SCRATCH.mkdir(parents=True, exist_ok=True)
    database = SCRATCH / "measured-disposable.db"
    original = Path(inputs["measured_index_copy"]["path"])
    source_hash_before = sha(original.read_bytes())
    assert source_hash_before == tasks["measured_copy_sha256"]
    if not database.exists():
        database.write_bytes(original.read_bytes())
    assert sha(database.read_bytes()) == source_hash_before, "Use a fresh disposable copy; never rerun over study output"
    conn = sqlite3.connect(database)
    observed_items = conn.execute("SELECT count(*) FROM yoinks").fetchone()[0]
    for entry in tasks["items"]:
        vid = entry["video_id"]
        conn.row_factory = sqlite3.Row
        columns = inputs["clips_columns"]
        rows = [dict(r) for r in conn.execute(f"SELECT {','.join(columns)} FROM clips WHERE video_id=? ORDER BY seq", (vid,))]
        assert sha(json.dumps(rows, sort_keys=True).encode()) == entry["pre_phase6_clip_output_sha256"]
        conn.row_factory = None
    rebound = rebind_paths(conn)
    conn.close()
    rebound_hash = sha(database.read_bytes())

    # Import runtime only after preregistration, copy verification, and rebinding.
    # Each default root is inside scratch; guard denies models/network/other DBs.
    for key in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "TEMP", "TMP", "UOINK_OUTPUT_DIR"):
        folder = SCRATCH / "runtime" / key.lower()
        folder.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(folder)
    os.environ["BD_WORKTREE_ROOT"] = str(ROOT)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    import offline_guard  # noqa: F401
    import index
    import library_media as media
    import yt_extract
    from tests.test_phase6_bc2 import _server_namespace

    # The requested library_media symbol does not exist. Use and disclose the
    # actual production helper; do not add an alias or edit the frozen manifest.
    namespace_mismatch = not hasattr(media, "chapters_from_metadata")
    idx = index.Index.open(database)
    published = {}
    try:
        ns = _server_namespace(idx)  # AST-extracted real production functions; no server import.
        for entry in tasks["items"]:
            vid = entry["video_id"]
            raw_path = INPUTS / "items" / vid / "chapters.json"
            metadata = read_json(raw_path)
            assert sha(raw_path.read_bytes()) == entry["chapter_input_sha256"]
            row = idx.get_yoink(vid)
            folder = Path(row["corpus_path"]).parent
            folder.mkdir(parents=True, exist_ok=True)
            sidecar = {"schema_version": 2, "video_id": vid, "source_type": "video", "platform": "youtube",
                       "url": metadata["webpage_url"], "source_url": metadata["webpage_url"],
                       "title": metadata["title"], "channel": metadata.get("channel"),
                       "yoinked_at": entry["source_date"], "duration_seconds": metadata["duration"],
                       "source_chapters": metadata["chapters"], "transcript": [], "screenshots": [],
                       "bd_original_metadata_provenance": metadata["_provenance"]}
            rows = yt_extract.chapters_from_metadata(metadata)
            # Use the sealed extracted bytes directly as the producer artifact.
            # The production planner normally archives a capture record; this
            # study has no authorized transcript and keeps its original metadata
            # hash/size chain in the permitted extracted artifact instead.
            plan = ns["_capture_media_plan"](sidecar, folder, item=row, chapter_rows=rows)
            plan["artifact"] = raw_path.read_bytes()
            plan["digest"] = sha(plan["artifact"])
            Path(row["corpus_path"]).write_text("# " + media._escape_markdown(metadata["title"]) + "\n\n" + plan["markdown"], encoding="utf-8")
            Path(row["sidecar_path"]).write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
            try:
                assert ns["_publish_capture_media"](idx, folder, sidecar, Path(row["corpus_path"]), Path(row["sidecar_path"]), plan)
                block = sidecar["media_depth"]
                actual = media.chapters_for(idx._conn, vid, revision=block["source_revision"])
                published[vid] = {"ok": True, "chapter_state": block["chapter_state"], "chapters": actual,
                                  "playback": block["playback"], "media_revision": block["media_revision"],
                                  "source_revision": block["source_revision"],
                                  "artifact_sha256": plan["digest"], "transcript_cues_supplied": 0}
            except media.MediaError as exc:
                published[vid] = {"ok": False, "code": exc.code, "details": exc.details}
        assert idx._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert idx._conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        idx.close()
    output("published-chapters.json", published)

    results = []
    for task in tasks["tasks"]:
        vid, start = task["video_id"], Decimal(str(task["source_start"]))
        clips = read_json(INPUTS / "items" / vid / "clips-pre-phase6.json")
        ordered = sorted(clips, key=lambda c: (c["start"], c["seq"], c["clip_id"]))
        containing = [c for c in ordered if Decimal(str(c["start"])) <= start < Decimal(str(c["end"]))]
        following = [c for c in ordered if Decimal(str(c["start"])) > start]
        chosen = (containing or following or [ordered[-1]])[0]
        baseline_seek = math.floor(chosen["start"])
        baseline_error = abs(Decimal(baseline_seek) - start)
        result = {**task, "baseline_clip_seq": chosen["seq"], "baseline_clip_id": chosen["clip_id"],
                  "baseline_clip_start": chosen["start"], "baseline_clip_end": chosen["end"],
                  "baseline_rule_applied": "containing" if containing else "next_in_gap" if following else "preceding_last",
                  "baseline_player_seek_seconds": baseline_seek,
                  "baseline_absolute_error_seconds": str(baseline_error)}
        item = published[vid]
        match = next((c for c in item.get("chapters", []) if c["seq"] == task["chapter_seq"]), None)
        if item["ok"] and match is not None:
            link, seek = media._seek_link(item["playback"], vid, match["start"])
        else:
            link, seek = None, None
        ok = seek is not None and link is not None
        if ok:
            assert int(parse_qs(urlsplit(link).query)["t"][0].rstrip("s")) == seek == math.floor(match["start"])
        result.update(phase6_ok=ok, phase6_chapter_start=match["start"] if match else None,
                      phase6_seek_link=link, phase6_player_seek_seconds=seek,
                      phase6_absolute_error_seconds=str(abs(Decimal(seek) - start)) if ok else None,
                      paired_error_reduction_seconds=str(baseline_error - abs(Decimal(seek) - start)) if ok else None)
        results.append(result)
    per_item = []
    for entry in tasks["items"]:
        subset = [r for r in results if r["video_id"] == entry["video_id"]]
        total_b = sum(Decimal(r["baseline_absolute_error_seconds"]) for r in subset)
        failures = sum(not r["phase6_ok"] for r in subset)
        total_p = None if failures else sum(Decimal(r["phase6_absolute_error_seconds"]) for r in subset)
        per_item.append({"video_id": entry["video_id"], "tasks": len(subset), "failures": failures,
                         "baseline_sum_seconds": str(total_b), "baseline_mae_seconds": str(total_b / len(subset)),
                         "phase6_sum_seconds": str(total_p) if total_p is not None else None,
                         "phase6_mae_seconds": str(total_p / len(subset)) if total_p is not None else None})
    total_b = sum(Decimal(r["baseline_absolute_error_seconds"]) for r in results)
    failures = sum(not r["phase6_ok"] for r in results)
    total_p = None if failures else sum(Decimal(r["phase6_absolute_error_seconds"]) for r in results)
    aggregate = {"tasks": len(results), "items": len(per_item), "failed_or_unsupported": failures,
                 "baseline_sum_seconds": str(total_b), "baseline_mae_seconds": str(total_b / len(results)),
                 "phase6_sum_seconds": str(total_p) if total_p is not None else None,
                 "phase6_mae_seconds": str(total_p / len(results)) if total_p is not None else None,
                 "reduction_fraction": str((total_b - total_p) / total_b) if total_p is not None and total_b else None,
                 "numeric_thresholds_pass": total_p is not None and total_b > 0 and total_p <= 15 * len(results) and total_p <= total_b * Decimal("0.2")}
    output("raw-results.json", {"task_manifest_sha256": expected, "tasks": results, "per_item": per_item, "aggregate": aggregate})
    source_hash_after = sha(original.read_bytes())
    assert source_hash_after == source_hash_before
    output("study-receipt.json", {
        "task_manifest_sha256": expected, "candidate_sha": tasks["execution_candidate_sha"],
        "measured_source_sha256_before": source_hash_before, "measured_source_sha256_after": source_hash_after,
        "measured_source_bytes": original.stat().st_size, "measured_item_count": observed_items,
        "disposable_path": str(database.relative_to(ROOT)), "rebound_before_runtime_sha256": rebound_hash,
        "disposable_after_sha256": sha(database.read_bytes()), "rebound_path_counts": rebound,
        "namespace_mismatch": namespace_mismatch,
        "actual_path": "yt_extract.chapters_from_metadata -> server._capture_media_plan / _publish_capture_media (AST-extracted) -> Index.publish_media_snapshot -> library_media.publish_transcript -> chapters_for / _seek_link",
        "publication_scope": "Chapter-only publication of sealed extracted metadata on the actual measured DB duplicate. Selected disposable transcript/clip rows are replaced by an explicit empty transcript. No original corpus, transcript, caption table, or media file was read. No clip was converted into a cue. Baseline uses unchanged sealed clips, verified against the original copied DB before mutation. This does not demonstrate preservation or acoustic validity of the unsupplied original transcripts.",
        "aggregate": aggregate, "player_observation": "pending: coordinator must observe a returned YouTube seek in Chrome",
        "speaker_gate": {"status": "blocked", "required_targets": 30, "required_items": 5,
                         "available_run_outputs": 0, "available_independent_human_annotations": 0},
        "diagnostics": {"ELG": "not run", "SCRP": "not run", "CCSD": "not run",
                        "reason": "Sealed inputs contain neither the task/query sets nor passage annotations for their required denominators; no surrogate word counts are reported."}})
    print(json.dumps(aggregate))


if __name__ == "__main__":
    main()
