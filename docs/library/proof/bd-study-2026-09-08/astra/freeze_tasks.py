"""Preregister BD targets using sealed inputs only; imports no project code."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parent
ROOT = HERE.parents[4]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = HERE / "task-manifest.json"
    if target.exists():
        raise SystemExit("Frozen manifest already exists; do not overwrite it.")
    seals = {}
    for line in (INPUTS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(None, 1)
        path = (INPUTS / name.strip()).resolve()
        assert path.is_relative_to(INPUTS)
        assert digest(path) == expected, name
        seals[name.strip()] = expected
    manifest_path = INPUTS / "study-inputs-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unique = {}
    for item in sorted(manifest["items"], key=lambda x: (x["video_id"], x["corpus_relpath"])):
        held = json.loads((INPUTS / "items" / item["video_id"] / "chapters.json").read_text(encoding="utf-8"))
        if held["_provenance"]["source_sha256"] != item["metadata_sha256"]:
            continue
        unique.setdefault(item["video_id"], item)
    eligible = [x for x in unique.values() if x["in_measured_index"]
                and x["clip_count"] >= 1 and x["chapter_count"] >= 2]
    selected = [x for x in eligible if x["chapter_count"] >= 5][:10]
    tasks, items = [], []
    for item in selected:
        vid = item["video_id"]
        chapter_path = INPUTS / "items" / vid / "chapters.json"
        clip_path = chapter_path.with_name("clips-pre-phase6.json")
        chapter_input = json.loads(chapter_path.read_text(encoding="utf-8"))
        clip_rows = json.loads(clip_path.read_text(encoding="utf-8"))
        clip_output_hash = hashlib.sha256(json.dumps(clip_rows, sort_keys=True).encode()).hexdigest()
        assert clip_output_hash == item["clips_sha256"]
        assert chapter_input["_provenance"]["source_sha256"] == item["metadata_sha256"]
        chapters = chapter_input["chapters"]
        indices = [i * (len(chapters) - 1) // 4 for i in range(5)]
        items.append({"video_id": vid, "title": chapter_input["title"],
                      "corpus_relpath_provenance_only": item["corpus_relpath"],
                      "source_date": item["yoinked_at"],
                      "held_metadata_sha256": item["metadata_sha256"],
                      "chapter_input_sha256": digest(chapter_path),
                      "pre_phase6_clip_output_sha256": item["clips_sha256"],
                      "pre_phase6_clip_file_sha256": digest(clip_path),
                      "selected_chapter_indices": indices})
        for seq in indices:
            chapter = chapters[seq]
            tasks.append({"task_id": f"BD-{len(tasks) + 1:02d}", "video_id": vid,
                          "chapter_seq": seq, "target_chapter": chapter["title"],
                          "source_start": chapter["start_time"],
                          "acceptable_interval": {"start": chapter["start_time"],
                                                  "end": chapter["end_time"],
                                                  "bounds": "[start,end)"}})
    assert len(items) == 10 and len(tasks) == 50
    frozen = {
        "schema": "phase6-bd-independent-navigation-tasks-v1",
        "annotator": "Astra (codex), independent of BC implementation workers",
        "frozen_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "execution_candidate_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sealed_manifest_candidate_sha": manifest["candidate_sha"],
        "sealed_input_manifest_sha256": digest(manifest_path),
        "sealed_sha256sums_sha256": digest(INPUTS / "SHA256SUMS"),
        "verified_sealed_file_count": len(seals),
        "clip_hash_encoding": "Manifest clips_sha256 hashes json.dumps(rows, sort_keys=True) UTF-8, with default separators and ensure_ascii. SHA256SUMS instead hashes actual pretty-printed file bytes; both are recorded.",
        "measured_copy_sha256": manifest["measured_index_copy"]["sha256"],
        "independence": "Selected and hashed before any Phase 6 code or tests were executed in BD. Only source chapter and identity fields were inspected for annotation; no Phase 6 outcomes informed selection.",
        "selection": "Deduplicate exact video_id using the manifest entry whose metadata hash matches the sealed chapter file provenance (D_FCYsshMI4 uses _sessions/test/Computer_use_in_Codex). Eligible means >=2 source chapters, present in measured index, >=1 pre-Phase 6 clip. Among eligible items with >=5 chapters, take first 10 in case-sensitive video_id order. For n chapters select indices floor(k*(n-1)/4), k=0..4. This convenience sample is not randomized or population-representative.",
        "population": {"sealed_rows": len(manifest["items"]), "unique_items": len(unique),
                       "eligible_unique_items": len(eligible), "selected_items": 10, "tasks": 50},
        "annotation_basis": "Chapter-start navigation only. Acceptable passage is the exact supplied chapter [start,end); error is distance from its start, not distance to the interval. No audio, transcript, or semantic-onset verification is claimed. Source-supplied placeholder titles are preserved verbatim.",
        "baseline_rule": "Sort unchanged clips by (start,seq,clip_id). Choose first clip with start <= target < end. In a gap choose first clip with start > target, or last preceding clip when none follows. Use floor(chosen clip.start) on the same YouTube player as Phase 6.",
        "phase6_rule": "Run chapters_from_metadata and the owning Index publication path on a disposable measured-index duplicate with every stored path rebound within worktree scratch. Read the published source chapter and its supported YouTube seek; use floor(chapter.start). Do not replace missing/failed output with the annotated target.",
        "metric": "abs(player_seek_seconds - source_start), paired for every task. Report exact decimal sums and means. Require Phase 6 MAE <=15 seconds and (baseline sum - Phase 6 sum)/baseline sum >=0.8 with baseline sum >0. Failed/unsupported tasks remain in denominator and fail the numeric gate; no imputed success.",
        "player_observation": "Pending coordinator observation; no external URL will be opened by annotator.",
        "speaker_gate": "blocked: no held diarization run output and independent human annotations",
        "items": items, "tasks": tasks,
    }
    target.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    receipt = f"{digest(target)}  task-manifest.json\n"
    (HERE / "TASK-MANIFEST.sha256").write_text(receipt, encoding="ascii", newline="\n")
    print(receipt, end="")


if __name__ == "__main__":
    main()
