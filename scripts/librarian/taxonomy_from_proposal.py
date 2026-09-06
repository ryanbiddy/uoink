#!/usr/bin/env python3
"""Project a validated induction proposal onto an approved, immutable taxonomy document.

The approved revision is the proposal's nodes restricted to the service contract fields
(`shelf_id`, `path`, `definition`, `include`, `exclude`, plus derived `name`,
`parent_shelf_id`, `retired`). Sibling cues, the coverage ledger, the diff and the rejected
proposals stay in the archived proposal; they are evidence, not part of the revision.
The output is deterministic for a given proposal file, and records the proposal's sha256,
the projection rule, and the revision hash the service will compute on approval.

Usage:
    python scripts/librarian/taxonomy_from_proposal.py \
        --proposal docs/library/proof/induction-run-2026-09-05/proposal.json \
        --out docs/library/taxonomy-v2-2026-09-05.json \
        --approved-by "..." --approval-record docs/library/INDUCTION-AUDIT-2026-09-05.md

Nothing here opens a database, the helper, or a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FIELDS = ("shelf_id", "path", "definition", "include", "exclude")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def project_nodes(nodes: list[dict]) -> list[dict]:
    projected = []
    for node in nodes:
        out = {key: node[key] for key in CONTRACT_FIELDS}
        out["path"] = [unicodedata.normalize("NFC", part) for part in out["path"]]
        out["name"] = out["path"][-1]
        out["retired"] = bool(node.get("retired", False))
        projected.append(out)
    by_path = {tuple(node["path"]): node["shelf_id"] for node in projected}
    for node in projected:
        parent = by_path.get(tuple(node["path"][:-1])) if len(node["path"]) > 1 else None
        if len(node["path"]) > 1 and parent is None:
            raise SystemExit(f"Node {node['shelf_id']} has no parent for path {node['path']}")
        node["parent_shelf_id"] = parent
    projected.sort(key=lambda node: (len(node["path"]), node["path"], node["shelf_id"]))
    ids = [node["shelf_id"] for node in projected]
    if len(ids) != len(set(ids)) or len(by_path) != len(projected):
        raise SystemExit("Duplicate shelf id or path in the proposal")
    return projected


def revision_hash(projected: list[dict]) -> str:
    """The service's revision hash: digest of the normalized node list (mirrors
    tests/validate_proof_receipts.normalized_taxonomy)."""
    return digest(projected)


def build(proposal_path: Path, *, approved_by: str, approval_record: str, parent_doc: Path) -> dict:
    raw = proposal_path.read_bytes()
    proposal = json.loads(raw.decode("utf-8"))
    if proposal.get("kind") == "taxonomy-v2-revision-decision":
        proposal = proposal["proposal"]  # reviewer-authored composition; the file hash binds the whole decision
    parent = json.loads(parent_doc.read_text(encoding="utf-8"))
    if proposal["parent_version_id"] != parent["version_id"]:
        raise SystemExit("Proposal parent does not match the parent taxonomy document")
    projected = project_nodes(proposal["nodes"])
    parent_nodes = {node["shelf_id"]: node for node in parent["nodes"]}
    preserved, added = [], []
    for node in projected:
        old = parent_nodes.get(node["shelf_id"])
        if old is None:
            added.append(node["shelf_id"])
            continue
        same = all(node[key] == old[key] for key in CONTRACT_FIELDS)
        if not same:
            raise SystemExit(f"Preserved node changed its contract fields: {node['shelf_id']}")
        preserved.append(node["shelf_id"])
    missing = sorted(set(parent_nodes) - {node["shelf_id"] for node in projected})
    if missing:
        raise SystemExit(f"Parent nodes missing from the proposal: {missing}")
    return dict(
        schema_version=1,
        version_id=proposal["version_id"],
        name="Living Library Taxonomy v2",
        description=("Taxonomy v2 induced from the 225 terminal-unmapped cards of the archived stage 1 proof; "
                     "the proposal's nodes projected to the service contract fields."),
        status="approved",
        parent_version_id=proposal["parent_version_id"],
        created_at="2026-09-05T00:00:00Z",
        approval=dict(
            approved_by=approved_by,
            approval_record=approval_record,
            proposal_path=str(proposal_path.relative_to(ROOT)).replace("\\", "/"),
            proposal_sha256=hashlib.sha256(raw).hexdigest(),
            projection="nodes restricted to shelf_id, path (NFC), definition, include, exclude; name=path[-1]; "
                       "parent_shelf_id derived from path; retired=false; sibling_cues, coverage_ledger, diff, "
                       "pin_impact_report and rejected_proposals remain in the archived proposal",
            preserved_shelf_ids=preserved,
            added_shelf_ids=added,
        ),
        parent_revision_hash=revision_hash(project_nodes(parent["nodes"])),
        revision_hash=revision_hash(projected),
        nodes=projected,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parent", type=Path, default=ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-record", required=True, help="Path of the approval/audit document")
    parser.add_argument("--check", action="store_true", help="Verify --out matches the deterministic build; write nothing")
    args = parser.parse_args(argv)
    document = build(args.proposal.resolve(), approved_by=args.approved_by,
                     approval_record=args.approval_record, parent_doc=args.parent)
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        existing = args.out.read_text(encoding="utf-8")
        if existing != text:
            print("MISMATCH: approved taxonomy differs from the deterministic projection", file=sys.stderr)
            return 1
        print(json.dumps(dict(status="APPROVED_TAXONOMY_MATCHES", version_id=document["version_id"],
                              revision_hash=document["revision_hash"], nodes=len(document["nodes"]))))
        return 0
    if args.out.exists() and args.out.read_text(encoding="utf-8") != text:
        print("REFUSED: an approved taxonomy already exists and differs; approved revisions are immutable", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="APPROVED_TAXONOMY_WRITTEN", version_id=document["version_id"],
                          revision_hash=document["revision_hash"], nodes=len(document["nodes"]),
                          added=document["approval"]["added_shelf_ids"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
