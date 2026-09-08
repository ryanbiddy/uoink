#!/usr/bin/env python3
"""Stage 4 label checks, agreement, and sealing in the STAGE4-BINDINGS shapes.

  --check <labels.json>       mechanical checks (packet/bindings hashes, ids, strata, card
                              references, quotes, cues) for a labeller or adjudication file
  --compare <a> <b> --out     agreement table
  --seal <adjudication.json>  write gold (rows + sealed:true) and the mapping document

No model, helper or database is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "librarian"))
import check_labels as cl  # noqa: E402

PROOF = ROOT / "docs/library/proof"
PACKET = PROOF / "holdout-v3-stage4-labelling-packet-2026-09-07.json"
BINDINGS = PROOF / "holdout-v3-stage4-bindings-2026-09-07.json"
SUBJECT_RULE = "admissible-excerpts-only"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_packet(packet_path: Path):
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    shim = dict(packet, taxonomy_candidate=dict(nodes=packet["taxonomy"]["nodes"]))
    cards = {entry["video_id"]: entry for entry in packet["cards"]}
    nodes = {node["shelf_id"]: node for node in packet["taxonomy"]["nodes"]}
    return packet, shim, cards, nodes


def check(labels: dict, packet_path: Path, bindings_path: Path) -> list[str]:
    packet, shim, cards, nodes = load_packet(packet_path)
    problems = cl.check_labels(labels, shim, cards, nodes)
    if labels.get("packet_sha256") != sha(packet_path.read_bytes()):
        problems.append("packet_sha256 does not match the packet file")
    if labels.get("bindings_sha256") != sha(bindings_path.read_bytes()):
        problems.append("bindings_sha256 does not match the bindings file")
    if labels.get("taxonomy_revision_hash") != packet["taxonomy"]["revision_hash"]:
        problems.append("taxonomy_revision_hash differs from the packet taxonomy")
    if labels.get("subject_rule") != SUBJECT_RULE:
        problems.append("subject_rule is not admissible-excerpts-only")
    if not str(labels.get("prior_v3_exposure") or "").strip():
        problems.append("prior_v3_exposure declaration missing")
    for item in labels.get("items") or []:
        entry = cards.get(item.get("video_id"))
        if entry is None:
            continue
        card = entry["card"]
        if item.get("source_revision") != card["source_revision"] or item.get("card_hash") != card["card_hash"]:
            problems.append(f"{item.get('video_id')}: source_revision/card_hash differ from the packet card")
    return problems


def seal(adjudication_path: Path, packet_path: Path, bindings_path: Path, labels_paths: dict, gold_out: Path,
         mapping_out: Path) -> dict:
    packet, shim, cards, nodes = load_packet(packet_path)
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    problems = check(adjudication, packet_path, bindings_path)
    expected_label_hashes = {key: sha(path.read_bytes()) for key, path in labels_paths.items()}
    if adjudication.get("label_file_sha256") != expected_label_hashes:
        problems.append(f"label_file_sha256 differs from the collected label files: {adjudication.get('label_file_sha256')} != {expected_label_hashes}")
    if not str(adjudication.get("sealed_at") or "").strip():
        problems.append("sealed_at missing")
    if problems:
        raise SystemExit(json.dumps(dict(problems=problems), ensure_ascii=False, indent=2))
    tax_nodes = [n for n in packet["taxonomy"]["nodes"] if not n.get("retired")]
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    binding_rows = {r["video_id"]: r for rows in bindings["strata"].values() for r in rows}
    gold = [dict(row, sealed=True) for row in adjudication["items"]]
    gold_text = json.dumps(gold, ensure_ascii=False, indent=2) + "\n"
    mapping_items = {}
    for row in adjudication["items"]:
        vid = row["video_id"]
        path = [unicodedata.normalize("NFC", segment).strip() for segment in (row.get("shelf_path") or [])]
        ancestors = [n for n in tax_nodes if n["path"] == path[:len(n["path"])]] if row["outcome"] != "unsupported" else []
        deepest = max((len(n["path"]) for n in ancestors), default=0)
        matches = [n for n in ancestors if len(n["path"]) == deepest]
        node = matches[0] if len(matches) == 1 else None
        mapping_items[vid] = dict(source_revision=binding_rows[vid]["source_revision"], card_hash=binding_rows[vid]["new_card_hash"],
                                  stratum=binding_rows[vid]["stratum"], gold_path=row.get("shelf_path") or [],
                                  outcome=row["outcome"], mapped_path=node["path"] if node else None,
                                  mapped_shelf_id=node["shelf_id"] if node else None, scorable=bool(node))
    mapping = dict(schema_version=1, kind="holdout-v3-stage4-mapping", scoring_version="strict-mapped-primary-v2",
                   holdout_version=packet["holdout_version"], bindings_sha256=sha(bindings_path.read_bytes()),
                   gold_sha256=sha(gold_text.encode("utf-8")), adjudicated_sha256=sha(adjudication_path.read_bytes()),
                   taxonomy_revision_hash=packet["taxonomy"]["revision_hash"],
                   rule="NFC + trimmed segments, case preserved, deepest unambiguous approved ancestor, strict primary equality",
                   sealed_at=datetime.now(timezone.utc).isoformat(), items=mapping_items)
    mapping_text = json.dumps(mapping, ensure_ascii=False, indent=2) + "\n"
    for path, text in ((gold_out, gold_text), (mapping_out, mapping_text)):
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise SystemExit(f"REFUSED: {path} exists and differs; sealed files are immutable")
        path.write_text(text, encoding="utf-8", newline="\n")
    from collections import Counter
    return dict(status="SEALED", gold=str(gold_out.relative_to(ROOT)), gold_sha256=sha(gold_text.encode("utf-8")),
                mapping=str(mapping_out.relative_to(ROOT)), mapping_sha256=sha(mapping_text.encode("utf-8")),
                outcomes=dict(Counter(r["outcome"] for r in gold)), scorable=sum(1 for r in mapping_items.values() if r["scorable"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--bindings", type=Path, default=BINDINGS)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--compare", type=Path, nargs=2)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--labels-gemini", type=Path, default=PROOF / "labels/holdout-v3-stage4-labels-gemini-2026-09-07.json")
    parser.add_argument("--labels-grok", type=Path, default=PROOF / "labels/holdout-v3-stage4-labels-grok-2026-09-07.json")
    parser.add_argument("--gold-out", type=Path, default=PROOF / "labels/holdout-v3-stage4-gold-2026-09-07.json")
    parser.add_argument("--mapping-out", type=Path, default=PROOF / "labels/holdout-v3-stage4-mapping-2026-09-07.json")
    args = parser.parse_args(argv)
    if args.check:
        labels = json.loads(args.check.read_text(encoding="utf-8"))
        problems = check(labels, args.packet, args.bindings)
        print(json.dumps(dict(file=str(args.check), labeller=labels.get("labeller"), problems=problems,
                              summary=cl.summarize(labels)), ensure_ascii=False, indent=2))
        return 1 if problems else 0
    if args.compare:
        a, b = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        table = cl.compare(a, b)
        table["labellers"] = [a.get("labeller"), b.get("labeller")]
        if args.out:
            args.out.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({k: v for k, v in table.items() if k != "rows"}, ensure_ascii=False, indent=2))
        return 0
    if args.seal:
        result = seal(args.seal, args.packet, args.bindings, dict(labels_gemini=args.labels_gemini, labels_grok=args.labels_grok),
                      args.gold_out, args.mapping_out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    parser.error("choose --check, --compare or --seal")
    return 2


if __name__ == "__main__":
    sys.exit(main())
