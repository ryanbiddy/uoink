"""Independent stdlib arithmetic, source-link, and stored-row checks for BD."""
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen_hash = (HERE / "TASK-MANIFEST.sha256").read_text().split()[0]
    assert digest(HERE / "task-manifest.json") == frozen_hash
    frozen, raw = load(HERE / "task-manifest.json"), load(HERE / "raw-results.json")
    published, receipt = load(HERE / "published-chapters.json"), load(HERE / "study-receipt.json")
    assert len(raw["tasks"]) == len(frozen["tasks"]) == 50
    assert len({t["video_id"] for t in frozen["tasks"]}) == 10
    db = (ROOT / receipt["disposable_path"]).resolve()
    assert db.is_relative_to(ROOT / "_scratch")
    conn = sqlite3.connect(db)
    baseline_sum = Decimal(0)
    phase6_sum = Decimal(0)
    links = []
    try:
        for task, result in zip(frozen["tasks"], raw["tasks"]):
            assert all(result[key] == value for key, value in task.items())
            vid = task["video_id"]
            start = Decimal(str(task["source_start"]))
            source = load(HERE.parent / "items" / vid / "chapters.json")
            chapter = source["chapters"][task["chapter_seq"]]
            assert chapter["title"] == task["target_chapter"]
            assert Decimal(str(chapter["start_time"])) == start
            assert task["acceptable_interval"] == {"start": chapter["start_time"], "end": chapter["end_time"], "bounds": "[start,end)"}
            clips = load(HERE.parent / "items" / vid / "clips-pre-phase6.json")
            clips.sort(key=lambda c: (c["start"], c["seq"], c["clip_id"]))
            chosen = next((c for c in clips if Decimal(str(c["start"])) <= start < Decimal(str(c["end"]))), None)
            if chosen is None:
                chosen = next((c for c in clips if Decimal(str(c["start"])) > start), clips[-1])
            assert chosen["clip_id"] == result["baseline_clip_id"]
            old_url = urlsplit(chosen["source_deep_link"])
            old_params = parse_qs(old_url.query)
            assert old_url.scheme == "https" and old_url.hostname in {"youtube.com", "www.youtube.com"}
            assert old_params["v"] == [vid]
            old_seek = int(old_params["t"][0].rstrip("s"))
            assert old_seek == math.floor(chosen["start"]) == result["baseline_player_seek_seconds"]
            stored = conn.execute("SELECT start,end,title FROM chapters WHERE video_id=? AND seq=?",
                                  (vid, task["chapter_seq"])).fetchone()
            assert stored == (chapter["start_time"], chapter["end_time"], chapter["title"])
            assert result["phase6_ok"]
            new_url = urlsplit(result["phase6_seek_link"])
            new_params = parse_qs(new_url.query)
            assert new_url.scheme == "https" and new_url.hostname in {"youtube.com", "www.youtube.com"}
            assert new_params["v"] == [vid]
            new_seek = int(new_params["t"][0].rstrip("s"))
            assert new_seek == math.floor(stored[0]) == result["phase6_player_seek_seconds"]
            baseline_error, phase6_error = abs(Decimal(old_seek) - start), abs(Decimal(new_seek) - start)
            assert baseline_error == Decimal(result["baseline_absolute_error_seconds"])
            assert phase6_error == Decimal(result["phase6_absolute_error_seconds"])
            assert baseline_error - phase6_error == Decimal(result["paired_error_reduction_seconds"])
            baseline_sum += baseline_error
            phase6_sum += phase6_error
            links.append({"task_id": task["task_id"], "baseline_original_seek_link": chosen["source_deep_link"],
                          "phase6_published_seek_link": result["phase6_seek_link"]})
        assert baseline_sum == Decimal(raw["aggregate"]["baseline_sum_seconds"])
        assert phase6_sum == Decimal(raw["aggregate"]["phase6_sum_seconds"])
        for entry in frozen["items"]:
            vid = entry["video_id"]
            source_path = HERE.parent / "items" / vid / "chapters.json"
            assert digest(source_path) == entry["chapter_input_sha256"]
            assert digest(HERE.parent / "items" / vid / "clips-pre-phase6.json") == entry["pre_phase6_clip_file_sha256"]
            folder = Path(conn.execute("SELECT corpus_path FROM yoinks WHERE video_id=?", (vid,)).fetchone()[0]).parent
            artifact = folder / ".media-inputs" / (published[vid]["artifact_sha256"] + ".json")
            assert artifact.read_bytes() == source_path.read_bytes()
    finally:
        conn.close()
    sealed = 0
    for line in (HERE.parent / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split(None, 1)
        assert digest(HERE.parent / name.strip()) == expected
        sealed += 1
    result = {"ok": True, "verified_tasks": 50, "sealed_input_files_unchanged": sealed,
              "original_baseline_links_verified": len(links), "published_database_chapter_rows_verified": 50,
              "baseline_sum_seconds": str(baseline_sum), "phase6_sum_seconds": str(phase6_sum),
              "task_manifest_sha256": frozen_hash, "links": links}
    (HERE / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "links"}))


if __name__ == "__main__":
    main()
