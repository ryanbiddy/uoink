#!/usr/bin/env python3
"""Stage 4 preparation (Fable's adapter over Astra's validator helpers).

    python scripts/librarian/stage4_prepare.py --source <named copy> --date 2026-09-07

1. Stages the named source copy inside the checkout (stage 4 reads archived heads only).
2. Builds the provisional stage 4 manifest with the v2 card builder
   (`freeze_inputs(staged, stage=4, stage4_sealed=False)`), status `awaiting-stage4-seal`.
3. Writes the hold-out v3 stage 4 bindings (`stage4_bindings`), the labelling packet
   (`admissible-excerpts-only`), and the card-contract v2 diff ledger (548 rows, old card
   hash from the archived stage 1 cards, new from the v2 index, with the builder's change
   classification).
4. Prints every hash the labelling brief and the execution record need.

No model, no helper, no database beyond the staged duplicate the validator opens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import library_cards  # noqa: E402
import validate_proof_receipts as v  # noqa: E402

PROOF = ROOT / "docs/library/proof"
ARCHIVE = PROOF / "run-2026-09-05/receipts.json"
INDUCTION = PROOF / "induction-manifest-2026-09-05.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise SystemExit(f"REFUSED: {path} exists and differs")
    path.write_text(text, encoding="utf-8", newline="\n")
    return sha(text.encode("utf-8"))


def old_cards() -> dict:
    archived = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    cards = {}
    for attempt in archived["attempts"]:
        cards.setdefault(attempt["video_id"], attempt["packet"]["card"])
    return cards


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="The named copy uoink-index-copy-2026-09-04-upgraded.db")
    parser.add_argument("--date", required=True)
    parser.add_argument("--staging", type=Path, default=ROOT / "_scratch/proof/stage4")
    args = parser.parse_args(argv)
    args.staging.mkdir(parents=True, exist_ok=True)
    staged = args.staging / args.source.name
    if not staged.exists():
        shutil.copyfile(args.source, staged)
    if sha(staged.read_bytes()) != v.SOURCE_SHA256:
        raise SystemExit("Staged source hash mismatch")
    manifest = v.freeze_inputs(staged, stage=4, stage4_sealed=False)
    if manifest.get("freeze_status") != "awaiting-stage4-seal":
        raise SystemExit(f"Unexpected provisional status {manifest.get('freeze_status')!r}")
    freeze_hash = v.stage4_freeze_hash(manifest)
    original_path = v.HOLDOUT_V3 if hasattr(v, "HOLDOUT_V3") else PROOF / "holdout-v3-2026-09-07.json"
    original_raw = original_path.read_bytes()
    original = json.loads(original_raw.decode("utf-8"))
    bindings = v.stage4_bindings(manifest, original, sha(original_raw))
    bindings_path = PROOF / f"holdout-v3-stage4-bindings-{args.date}.json"
    bindings_sha = write_json(bindings_path, bindings)

    packet_cards = []
    for stratum in ("timed_evidence", "text_only"):
        for row in bindings["strata"][stratum]:
            vid = row["video_id"]
            packet_cards.append(dict(video_id=vid, stratum=stratum, card=manifest["card_payloads"][vid]))
    packet = dict(schema_version=1, kind="holdout-v3-stage4-labelling-packet", bindings_sha256=bindings_sha,
                  stage4_freeze_hash=freeze_hash, card_profile_hash=manifest["hashes"]["card_profile_hash"],
                  holdout_version=original["version"], taxonomy=manifest["taxonomy"],
                  subject_rule="admissible-excerpts-only",
                  card_source="stage 4 manifest card payloads (card contract v2); no labels, outcomes, predictions or rationales",
                  counts={s: len(bindings["strata"][s]) for s in bindings["strata"]}, cards=packet_cards)
    packet_path = PROOF / f"holdout-v3-stage4-labelling-packet-{args.date}.json"
    packet_sha = write_json(packet_path, packet)

    previous = old_cards()
    diff_rows = []
    classify = getattr(library_cards, "classify_card_change", None) or getattr(library_cards, "diff_cards", None)
    for vid, _revision in manifest["items"]:
        old = previous.get(vid)
        new = manifest["card_payloads"][vid]
        row = dict(video_id=vid, source_revision=new["source_revision"], old_card_hash=old["card_hash"] if old else None,
                   new_card_hash=new["card_hash"])
        if old is not None and old["source_revision"] != new["source_revision"]:
            raise SystemExit(f"Source revision changed for {vid}; freeze failure")
        if classify and old is not None:
            try:
                row["change"] = classify(old, new)
            except Exception as exc:  # classification is informational; record the failure
                row["change"] = dict(error=str(exc)[:200])
        diff_rows.append(row)
    diff = dict(schema_version=1, kind="card-contract-v2-diff", stage4_freeze_hash=freeze_hash,
                card_profile_hash=manifest["hashes"]["card_profile_hash"], cards_hash=manifest["cards_hash"],
                old_source="docs/library/proof/run-2026-09-05/receipts.json attempts[].packet.card (stage 1 cards)",
                items=diff_rows)
    diff_path = PROOF / f"card-contract-v2-diff-{args.date}.json"
    diff_sha = write_json(diff_path, diff)
    changed = sum(1 for r in diff_rows if r["old_card_hash"] != r["new_card_hash"])
    kinds = {}
    for r in diff_rows:
        c = r.get("change")
        key = c if isinstance(c, str) else (json.dumps(c, sort_keys=True)[:80] if c else "n/a")
        kinds[key] = kinds.get(key, 0) + 1
    print(json.dumps(dict(status="STAGE4_PREPARED", stage4_freeze_hash=freeze_hash, bindings=str(bindings_path.relative_to(ROOT)),
                          bindings_sha256=bindings_sha, packet=str(packet_path.relative_to(ROOT)), packet_sha256=packet_sha,
                          diff=str(diff_path.relative_to(ROOT)), diff_sha256=diff_sha, cards_hash=manifest["cards_hash"],
                          card_profile_hash=manifest["hashes"]["card_profile_hash"], changed_hashes=changed,
                          probe=manifest["probe"]["target_ids"], change_kinds=kinds), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
