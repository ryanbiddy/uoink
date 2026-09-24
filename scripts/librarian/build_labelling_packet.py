#!/usr/bin/env python3
"""Build a blind labelling packet for hold-out v2 from the archived stage 1 cards and a
candidate taxonomy proposal. The packet holds the 60 frozen cards (last archived attempt's
packet card, bound to the hold-out rows by card hash and source revision) and the candidate
nodes with sibling cues. It carries no predictions, no prior reasons, no labels.

    python scripts/librarian/build_labelling_packet.py \
        --proposal docs/library/proof/induction-run-7-2026-09-05/proposal.json \
        --out docs/library/proof/holdout-v2-labelling-packet-7-2026-09-05.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOLDOUT = ROOT / "docs/library/proof/holdout-v2-2026-09-05.json"
ARCHIVE = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--status", default="candidate; approval pending Astra audit of the induction receipts")
    parser.add_argument("--holdout", type=Path, default=HOLDOUT, help="Frozen hold-out file (default: hold-out v2)")
    args = parser.parse_args(argv)
    holdout_path = args.holdout
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    rows = {row["video_id"]: (stratum, row) for stratum, entries in holdout["strata"].items() for row in entries}
    archive_raw = ARCHIVE.read_bytes()
    archived = json.loads(archive_raw.decode("utf-8"))
    last = {}
    for attempt in archived["attempts"]:
        if attempt["video_id"] in rows:
            last[attempt["video_id"]] = attempt
    if set(last) != set(rows):
        print("Archived attempts do not cover the hold-out", file=sys.stderr)
        return 1
    proposal_raw = args.proposal.read_bytes()
    proposal = json.loads(proposal_raw.decode("utf-8"))
    if proposal.get("kind") == "taxonomy-v2-revision-decision":
        proposal = proposal["proposal"]  # reviewer-authored composition; the file hash binds the whole decision
    cards = []
    for vid in sorted(rows):
        stratum, row = rows[vid]
        card = last[vid]["packet"]["card"]
        if card["card_hash"] != row["card_hash"] or card["source_revision"] != row["source_revision"]:
            print(f"Card binding mismatch for {vid}", file=sys.stderr)
            return 1
        cards.append(dict(video_id=vid, stratum=stratum, card=card))
    packet = dict(
        schema_version=1, kind="holdout-v2-labelling-packet", holdout_version=holdout["version"],
        holdout_file_sha256=hashlib.sha256(holdout_path.read_bytes()).hexdigest(),
        archived_receipts_sha256=hashlib.sha256(archive_raw).hexdigest(),
        card_source="Last archived attempt packet card per selected identity; card_hash and source_revision equal the frozen holdout rows",
        taxonomy_candidate=dict(version_id=proposal["version_id"], parent_version_id=proposal["parent_version_id"],
                                status=args.status,
                                proposal_path=str(args.proposal.resolve().relative_to(ROOT)).replace("\\", "/"),
                                proposal_sha256=hashlib.sha256(proposal_raw).hexdigest(),
                                nodes=[{k: node[k] for k in ("shelf_id", "path", "definition", "include", "exclude", "sibling_cues")
                                        if k in node} for node in proposal["nodes"]]),
        counts={stratum: len(entries) for stratum, entries in holdout["strata"].items()}, cards=cards)
    text = json.dumps(packet, ensure_ascii=False, indent=1) + "\n"
    if args.out.exists() and args.out.read_text(encoding="utf-8") != text:
        print("REFUSED: packet exists and differs", file=sys.stderr)
        return 1
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="PACKET_WRITTEN", out=str(args.out), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                          cards=len(cards), nodes=len(packet["taxonomy_candidate"]["nodes"]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
