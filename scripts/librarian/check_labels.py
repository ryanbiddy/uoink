#!/usr/bin/env python3
"""Mechanical checks for hold-out v2 label files, labeller agreement, and sealing.

Modes:
  --check <labels.json>            validate one labeller (or adjudicated) file against the packet
  --compare <a.json> <b.json>      agreement table between two label files (adjudication input)
  --seal <adjudicated.json>        write the sealed gold list and the frozen mapping table from
                                   an adjudicated label file and the approved taxonomy

Quote rule (shared with the service, validator and scorer): NFC, whitespace collapsed,
1 to 24 words, case and punctuation preserved, occurring in the one named excerpt.
No database, helper, or model is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "docs/library/proof/holdout-v2-labelling-packet-2026-09-05.json"
TAXONOMY_V2 = ROOT / "docs/library/taxonomy-v2-2026-09-05.json"
OUTCOMES = {"assigned", "unmappable", "unsupported"}
ELIGIBLE_TEXT = {"page", "x_article", "x_thread", "reddit_thread", "note"}


def normalize_quote(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_path(path) -> list[str]:
    return [unicodedata.normalize("NFC", part).strip() for part in path]


def load_packet(path: Path = PACKET) -> tuple[dict, dict, dict]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    cards = {entry["video_id"]: entry for entry in packet["cards"]}
    nodes = {node["shelf_id"]: node for node in packet["taxonomy_candidate"]["nodes"]}
    return packet, cards, nodes


def check_labels(labels: dict, packet: dict, cards: dict, nodes: dict) -> list[str]:
    problems: list[str] = []
    order = [entry["video_id"] for entry in packet["cards"]]
    items = labels.get("items")
    if not isinstance(items, list):
        return ["items is not a list"]
    seen = [item.get("video_id") for item in items]
    if seen != order:
        missing = sorted(set(order) - set(seen))
        extra = sorted(set(seen) - set(order))
        dupes = sorted(k for k, n in Counter(seen).items() if n > 1)
        problems.append(f"video_id sequence differs from the packet: missing={missing} extra={extra} dupes={dupes} "
                        f"reordered={not missing and not extra and not dupes}")
    for item in items:
        vid = item.get("video_id")
        tag = f"{vid}"
        entry = cards.get(vid)
        if entry is None:
            continue
        card = entry["card"]
        if item.get("stratum") != entry["stratum"]:
            problems.append(f"{tag}: stratum {item.get('stratum')!r} != packet {entry['stratum']!r}")
        outcome = item.get("outcome")
        if outcome not in OUTCOMES:
            problems.append(f"{tag}: bad outcome {outcome!r}")
            continue
        shelf_id = item.get("shelf_id")
        path = item.get("shelf_path")
        if outcome == "assigned":
            node = nodes.get(shelf_id)
            if node is None:
                problems.append(f"{tag}: assigned shelf_id {shelf_id!r} not in taxonomy")
            elif norm_path(path or []) != norm_path(node["path"]):
                problems.append(f"{tag}: shelf_path {path} != node path {node['path']}")
            conf = item.get("confidence")
            if not isinstance(conf, (int, float)) or not 0.60 <= conf <= 1.0:
                problems.append(f"{tag}: assigned confidence {conf!r} outside [0.60, 1.0]")
            for sec in item.get("secondary_shelf_ids") or []:
                if sec not in nodes or sec == shelf_id:
                    problems.append(f"{tag}: bad secondary {sec!r}")
            if len(item.get("secondary_shelf_ids") or []) > 2:
                problems.append(f"{tag}: more than two secondaries")
        elif outcome == "unmappable":
            if shelf_id is not None:
                problems.append(f"{tag}: unmappable with shelf_id {shelf_id!r}")
            if not isinstance(path, list) or not path or not all(isinstance(p, str) and p.strip() for p in path):
                problems.append(f"{tag}: unmappable needs a proposed shelf_path")
            elif tuple(norm_path(path)) in {tuple(norm_path(n["path"])) for n in nodes.values()}:
                problems.append(f"{tag}: unmappable but shelf_path equals an approved node path {path}")
        else:  # unsupported
            excerpts = card.get("excerpts") or []
            has_timed = any(e.get("evidence_kind") == "timed_clip" for e in excerpts)
            eligible = has_timed or (card.get("source_type") in ELIGIBLE_TEXT and any(
                normalize_quote(e.get("text", "")) for e in excerpts))
            if eligible:
                problems.append(f"{tag}: unsupported but the card has eligible evidence")
        if outcome in ("assigned", "unmappable"):
            evidence = item.get("evidence") or {}
            excerpt_id = evidence.get("excerpt_id")
            quote = evidence.get("quote")
            excerpt = next((e for e in card.get("excerpts") or [] if e.get("excerpt_id") == excerpt_id), None)
            if excerpt is None:
                problems.append(f"{tag}: excerpt_id {excerpt_id!r} not on this card")
            elif not isinstance(quote, str) or not quote.strip():
                problems.append(f"{tag}: empty quote")
            else:
                nq = normalize_quote(quote)
                words = len(nq.split())
                if not 1 <= words <= 24:
                    problems.append(f"{tag}: quote has {words} words")
                if nq not in normalize_quote(excerpt.get("text", "")):
                    problems.append(f"{tag}: quote is not verbatim in excerpt {excerpt_id[:12]}")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 200:
            problems.append(f"{tag}: rationale missing or over 200 characters")
    return problems


def summarize(labels: dict) -> dict:
    items = labels.get("items") or []
    return dict(outcomes=dict(Counter(item.get("outcome") for item in items)),
                shelves=dict(Counter(item.get("shelf_id") or "<none>" for item in items if item.get("outcome") == "assigned")),
                unmappable_paths=dict(Counter(" / ".join(item.get("shelf_path") or []) for item in items
                                              if item.get("outcome") == "unmappable")))


def compare(a: dict, b: dict) -> dict:
    by_a = {item["video_id"]: item for item in a["items"]}
    by_b = {item["video_id"]: item for item in b["items"]}
    rows, agree_primary, agree_outcome = [], 0, 0
    for vid in by_a:
        ia, ib = by_a[vid], by_b.get(vid, {})
        same_outcome = ia.get("outcome") == ib.get("outcome")
        same_primary = same_outcome and (ia.get("shelf_id") == ib.get("shelf_id")) and (
            ia.get("outcome") != "unmappable" or norm_path(ia.get("shelf_path") or []) == norm_path(ib.get("shelf_path") or []))
        agree_outcome += same_outcome
        agree_primary += same_primary
        rows.append(dict(video_id=vid, stratum=ia.get("stratum"), a=dict(outcome=ia.get("outcome"), shelf_id=ia.get("shelf_id"),
                                                                         path=ia.get("shelf_path"), confidence=ia.get("confidence")),
                         b=dict(outcome=ib.get("outcome"), shelf_id=ib.get("shelf_id"), path=ib.get("shelf_path"),
                                confidence=ib.get("confidence")),
                         agree=same_primary))
    return dict(total=len(rows), agree_outcome=agree_outcome, agree_primary=agree_primary,
                disagreements=[row for row in rows if not row["agree"]], rows=rows)


def deepest_approved_ancestor(path: list[str], tax_paths: set[tuple[str, ...]]) -> list[str] | None:
    normalized = norm_path(path)
    for depth in range(len(normalized), 0, -1):
        prefix = tuple(normalized[:depth])
        if prefix in tax_paths:
            return list(prefix)
    return None


def seal(adjudicated: dict, packet: dict, cards: dict, taxonomy: dict) -> tuple[list[dict], dict]:
    tax_paths = {tuple(norm_path(node["path"])) for node in taxonomy["nodes"] if not node.get("retired")}
    by_path = {tuple(norm_path(node["path"])): node["shelf_id"] for node in taxonomy["nodes"]}
    gold, mapping = [], {}
    for item in adjudicated["items"]:
        vid = item["video_id"]
        card = cards[vid]["card"]
        outcome = item["outcome"]
        shelf_path = item.get("shelf_path") or []
        mapped = deepest_approved_ancestor(shelf_path, tax_paths) if outcome in ("assigned", "unmappable") else None
        if outcome == "assigned" and mapped != norm_path(shelf_path):
            raise SystemExit(f"{vid}: assigned path is not an approved node")
        gold.append(dict(video_id=vid, slug=card.get("slug"), title=card.get("title"), channel=card.get("channel"),
                         platform=card.get("platform"), source_type=card.get("source_type"),
                         source_revision=card["source_revision"], card_hash=card["card_hash"], stratum=cards[vid]["stratum"],
                         outcome=outcome, shelf_id=item.get("shelf_id"), shelf_path=norm_path(shelf_path) if shelf_path else [],
                         secondary_shelf_ids=item.get("secondary_shelf_ids") or [],
                         confidence=item.get("confidence"), evidence=item.get("evidence"), rationale=item.get("rationale"),
                         adjudication=item.get("adjudication"), sealed=True))
        mapping[vid] = dict(gold_path=norm_path(shelf_path) if shelf_path else [], outcome=outcome,
                            mapped_path=mapped, mapped_shelf_id=by_path.get(tuple(mapped)) if mapped else None,
                            scorable=mapped is not None,
                            rule="deepest unambiguous approved ancestor; no ancestor means any assignment is incorrect")
    return gold, mapping


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_V2)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--compare", type=Path, nargs=2)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--gold-out", type=Path, default=ROOT / "docs/library/proof/labels/holdout-v2-gold-2026-09-05.json")
    parser.add_argument("--mapping-out", type=Path, default=ROOT / "docs/library/proof/labels/holdout-v2-mapping-2026-09-05.json")
    parser.add_argument("--out", type=Path, help="Where --compare writes its JSON table")
    args = parser.parse_args(argv)
    packet, cards, nodes = load_packet(args.packet)
    if args.check:
        labels = json.loads(args.check.read_text(encoding="utf-8"))
        problems = check_labels(labels, packet, cards, nodes)
        if labels.get("packet_sha256") != sha(args.packet.read_bytes()):
            problems.append(f"packet_sha256 {labels.get('packet_sha256')} != actual {sha(args.packet.read_bytes())}")
        print(json.dumps(dict(file=str(args.check), labeller=labels.get("labeller"), blind=labels.get("blind"),
                              files_opened=labels.get("files_opened"), problems=problems, summary=summarize(labels)),
                         ensure_ascii=False, indent=2))
        return 1 if problems else 0
    if args.compare:
        a, b = (json.loads(path.read_text(encoding="utf-8")) for path in args.compare)
        table = compare(a, b)
        table["labellers"] = [a.get("labeller"), b.get("labeller")]
        text = json.dumps(table, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8", newline="\n")
        print(json.dumps({k: v for k, v in table.items() if k != "rows"}, ensure_ascii=False, indent=2))
        return 0
    if args.seal:
        adjudicated = json.loads(args.seal.read_text(encoding="utf-8"))
        problems = check_labels(adjudicated, packet, cards, nodes)
        if problems:
            print(json.dumps(dict(problems=problems), ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
        if taxonomy.get("status") != "approved":
            print("Taxonomy is not approved", file=sys.stderr)
            return 1
        gold, mapping = seal(adjudicated, packet, cards, taxonomy)
        gold_text = json.dumps(gold, ensure_ascii=False, indent=2) + "\n"
        mapping_doc = dict(schema_version=1, kind="holdout-v2-mapping", holdout_version="holdout-v2-2026-09-05",
                           taxonomy_version_id=taxonomy["version_id"], taxonomy_revision_hash=taxonomy["revision_hash"],
                           adjudicated_file=str(args.seal.resolve().relative_to(ROOT)).replace("\\", "/"),
                           adjudicated_sha256=sha(args.seal.read_bytes()), gold_sha256=sha(gold_text.encode("utf-8")),
                           scoring_version="strict-mapped-primary-v2", items=mapping)
        mapping_text = json.dumps(mapping_doc, ensure_ascii=False, indent=2) + "\n"
        for path, text in ((args.gold_out, gold_text), (args.mapping_out, mapping_text)):
            if path.exists() and path.read_text(encoding="utf-8") != text:
                print(f"REFUSED: {path} exists and differs; sealed files are immutable", file=sys.stderr)
                return 1
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        counts = Counter(row["outcome"] for row in gold)
        scorable = sum(1 for row in mapping.values() if row["scorable"])
        print(json.dumps(dict(status="SEALED", gold=str(args.gold_out), gold_sha256=sha(gold_text.encode("utf-8")),
                              mapping=str(args.mapping_out), mapping_sha256=sha(mapping_text.encode("utf-8")),
                              outcomes=dict(counts), scorable=scorable), ensure_ascii=False, indent=2))
        return 0
    parser.error("choose --check, --compare or --seal")
    return 2


if __name__ == "__main__":
    sys.exit(main())
