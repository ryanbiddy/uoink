#!/usr/bin/env python3
"""Write the stage 2 pre-execution record: every identity the gate requires Fable to name
before the measured pass starts, measured from the checkout at that moment.

    python scripts/librarian/stage2_execution_record.py --out docs/library/proof/stage2-execution-record-2026-09-05.json

Reads files and runs `git rev-parse` and `claude --version`; opens no database, helper or
model. Refuses to write if ANTHROPIC_API_KEY is set (the pass is subscription-only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_STAGE2 = ROOT / "docs/library/proof/manifest-stage2-2026-09-05.json"
GUARD_RULE_V2 = dict(
    identifier="distinct-failed-completions-v2",
    version=2,
    amendment="AO-G1",
    n_min=20,
    numerator=(
        "union of rejected/errored completed attempt ids and completed ids with a "
        "transport event by that timestamp, plus unique anonymous transport events "
        "(attempt_id is None) by that timestamp"
    ),
    abort_when="N >= n_min and 10 * numerator > N",
    comparison="integer",
    unique_event_ids=True,
    timestamp_field="occurred_monotonic_ns",
)

STAGES = {
    2: dict(manifest="docs/library/proof/manifest-stage2-2026-09-05.json",
            approval_record="docs/library/INDUCTION-AUDIT-14-2026-09-06.md",
            packet="docs/library/proof/holdout-v2-labelling-packet-12-2026-09-06.json",
            packet_note="INDUCTION-AUDIT-13: packet 12 (decision 3 nodes) and packet 13 (decision 4 nodes) carry identical candidate nodes; decision 5 nodes are byte-identical; packet-12 labels carried forward by that ruling",
            labellers=["gemini-3.8-flash-high (blind, run AD, packet 12)", "grok-4.6 (blind, run AD, packet 12)"],
            labeller_files={n: f"docs/library/proof/labels/holdout-v2-labels-12-{n}-2026-09-06.json" for n in ("gemini", "grok")},
            adjudicator="gpt-6-astra (blind, run AG)",
            decision="docs/library/proof/taxonomy-v2-revision-decision-5-2026-09-06.json",
            model="claude-sonnet-5"),
    3: dict(manifest="docs/library/proof/manifest-stage3-2026-09-07.json",
            approval_record="docs/library/INDUCTION-AUDIT-16-2026-09-07.md",
            packet="docs/library/proof/holdout-v3-labelling-packet-2026-09-07.json",
            packet_note="packet built from the frozen hold-out v3 and the taxonomy v3 candidate nodes (identical to the approved nodes; see INDUCTION-AUDIT-16)",
            labellers=["gemini-3.8-flash-high (blind, run AJ)", "grok-4.6 (blind, run AJ)"],
            labeller_files={n: f"docs/library/proof/labels/holdout-v3-labels-{n}-2026-09-07.json" for n in ("gemini", "grok")},
            adjudicator="gpt-6-astra (blind, run AK)",
            decision="docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json",
            model="claude-sonnet-5"),
    4: dict(manifest="docs/library/proof/manifest-stage4-2026-09-07.json",
            approval_record="docs/library/INDUCTION-AUDIT-16-2026-09-07.md",
            packet="docs/library/proof/holdout-v3-stage4-labelling-packet-2026-09-07.json",
            packet_note="new packet from card contract v2; relabel all 60 original v3 identities; do not carry sealed v3 labels forward as stage 4 gold",
            labellers=["gemini-3.8-flash-high (blind, stage 4)", "grok-4.6 (blind, stage 4)"],
            labeller_files={n: f"docs/library/proof/labels/holdout-v3-stage4-labels-{n}-2026-09-07.json" for n in ("gemini", "grok")},
            adjudicator="gpt-6-astra (blind, stage 4)",
            decision="docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json",
            model="claude-opus-5",
            effort=None,
            bindings="docs/library/proof/holdout-v3-stage4-bindings-2026-09-07.json",
            diff_ledger="docs/library/proof/card-contract-v2-diff-2026-09-07.json",
            probe_receipt="docs/library/proof/stage4-probe-receipts-2026-09-07.json",
            probe_wall_budget_ms=900000,
            probe_n=16,
            probe_batch=8,
            probe_concurrency=4),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_identity(relative: str) -> dict:
    path = ROOT / relative
    raw = path.read_bytes()
    return dict(path=relative, bytes=len(raw), sha256=sha(raw),
                sha256_lf=sha(raw.replace(b"\r\n", b"\n")))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", type=int, choices=(2, 3, 4), default=2)
    parser.add_argument("--approval-record", default=None)
    parser.add_argument("--authorization", required=True,
                        help="Who authorized the execution and when (Ryan's standing stage 2 authorization)")
    parser.add_argument("--budget-note", required=True)
    parser.add_argument("--model", default=None,
                        help="Subscription model; default claude-sonnet-5 (stages 2/3) or claude-opus-5 (stage 4)")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--port", type=int, default=5180)
    parser.add_argument("--effort", default=None, help="Declared reasoning effort for assignment calls (stage 3: high; stage 4: omit for CLI default)")
    args = parser.parse_args(argv)
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is set; the measured pass is subscription-only", file=sys.stderr)
        return 1
    stage = STAGES[args.stage]
    if args.model is None:
        args.model = stage.get("model") or "claude-sonnet-5"
    if args.approval_record is None:
        args.approval_record = stage["approval_record"]
    if args.stage == 4:
        for key in ("bindings", "diff_ledger", "packet"):
            if not (ROOT / stage[key]).is_file():
                print(f"stage 4 identity missing: {stage[key]}", file=sys.stderr)
                return 1
    manifest = json.loads((ROOT / stage["manifest"]).read_text(encoding="utf-8"))
    files = manifest["files"]
    taxonomy = json.loads((ROOT / files["taxonomy"]["path"]).read_text(encoding="utf-8"))
    mapping = json.loads((ROOT / files["mapping"]["path"]).read_text(encoding="utf-8"))
    gold = json.loads((ROOT / files["gold"]["path"]).read_text(encoding="utf-8"))
    holdout = json.loads((ROOT / files["holdout"]["path"]).read_text(encoding="utf-8"))
    dirty = git("status", "--porcelain")
    claude_exe = shutil.which("claude")
    claude_version = subprocess.run([claude_exe or "claude", "--version"], capture_output=True, text=True).stdout.strip()
    record = dict(
        schema_version=1,
        kind="stage2-execution-record",
        written_at=datetime.now(timezone.utc).isoformat(),
        integrated_candidate=dict(git_sha=git("rev-parse", "HEAD"), branch=git("rev-parse", "--abbrev-ref", "HEAD"),
                                  working_tree_clean=(dirty == ""), dirty_entries=dirty.splitlines()),
        stage=args.stage,
        stage_manifest=dict(file_identity(stage["manifest"]),
                             manifest_hash=manifest["manifest_hash"], contract_version=manifest["contract_version"],
                             targets=len(manifest["items"]), exclusions=len(manifest["exclusions"])),
        source=dict(manifest["source"], upgrade=manifest["upgrade"]),
        cards_and_heads=dict(cards_hash=manifest["cards_hash"], corpus_heads_hash=manifest["corpus_heads_hash"],
                             card_profile_hash=manifest["hashes"]["card_profile_hash"],
                             card_profile=manifest.get("card_profile"),
                             card_builder=file_identity(files["card_builder"]["path"])),
        evaluation_identity=dict(holdout=file_identity(files["holdout"]["path"]),
                                 holdout_version=holdout["version"],
                                 strata={k: len(v) for k, v in holdout["strata"].items()},
                                 labelling_packet=file_identity(stage["packet"]),
                                 labelling_packet_note=stage["packet_note"]),
        sealed_labels_and_mapping=dict(
            gold=file_identity(files["gold"]["path"]), mapping=file_identity(files["mapping"]["path"]),
            adjudicated=dict(path=mapping.get("adjudicated_file") or files.get("adjudication", {}).get("path"),
                             sha256=mapping["adjudicated_sha256"]),
            gold_items=len(gold), sealed=all(item.get("sealed") is True for item in gold),
            scorable=sum(1 for row in mapping["items"].values() if row["scorable"]),
            labellers=stage["labellers"],
            labeller_files={name: file_identity(path) for name, path in stage["labeller_files"].items()},
            adjudicator=stage["adjudicator"],
            scoring_version=mapping["scoring_version"],
            rule="NFC + trimmed segments, case preserved, deepest unambiguous approved ancestor, strict primary equality"),
        approved_taxonomy=dict(file_identity(files["taxonomy"]["path"]), version_id=taxonomy["version_id"],
                               decision=dict(path=stage["decision"], sha256=sha((ROOT / stage["decision"]).read_bytes())),
                               service_returned_revision_hash="pending observation: recorded by the harness in receipts.before.taxonomy_revision_hash on the disposable duplicate",
                               parent_version_id=taxonomy["parent_version_id"],
                               parent_revision_hash=taxonomy["parent_revision_hash"],
                               revision_hash=taxonomy["revision_hash"], nodes=len(taxonomy["nodes"]),
                               approval=taxonomy["approval"], approval_record=args.approval_record,
                               lineage={key: file_identity(entry["path"]) for key, entry in files.items() if key.startswith("parent_taxonomy")}),
        assignment_prompt=dict(file_identity(files["prompt"]["path"]),
                               prompt_sha256_text_mode=manifest["hashes"]["prompt_sha256"],
                               renderer="proof_run.render_prompt: {{TAXONOMY}} then {{CARDS}}, template read in text mode (universal newlines)"),
        installed_client=dict(name="Claude Code CLI (subscription)", version=claude_version, executable=claude_exe,
                              executable_sha256=sha(Path(claude_exe).read_bytes()) if claude_exe and Path(claude_exe).is_file() else None,
                              model=args.model,
                              effort=args.effort if args.effort is not None else (None if args.stage == 4 else "CLI default"),
                              effort_flag=bool(args.effort),
                              tools="disabled (--tools \"\")", session_persistence="disabled",
                              api_key="ANTHROPIC_API_KEY unset at record time; proof_run.py refuses to start if it is present and records anthropic_api_key_unset in the receipts"),
        corpus_egress=dict(authorization=args.authorization,
                           permitted="librarian-profile evidence cards (title, channel, platform, source type, hashes, summary hint, up to six excerpts of 240 characters) rendered into the frozen assignment prompt and sent to the subscription client",
                           forbidden="labels, gold, mapping, holdout membership, predictions from earlier runs, corpus files beyond the bounded heads"),
        budget_and_isolation=dict(budget=args.budget_note, wall_budget_ms=manifest["execution"]["wall_budget_ms"],
                                  concurrency=args.concurrency, batch=args.batch, max_retries=manifest["execution"]["max_retries"],
                                  error_rate_limit=manifest["execution"]["error_rate_limit"],
                                  error_rate_min_attempts=manifest["execution"]["error_rate_min_attempts"],
                                  guard_rule=dict(GUARD_RULE_V2),
                                  port=args.port, apply_enabled=False, live_index="never opened; isolated helper on a disposable duplicate"),
        implementation=dict(implementation_hash=manifest["hashes"]["implementation_hash"],
                            files={name: file_identity(entry["path"]) for name, entry in files.items()},
                            runner=file_identity("scripts/librarian/proof_run.py"),
                            validator=file_identity("tests/validate_proof_receipts.py"),
                            scorer=file_identity("scripts/librarian/proof_score.py")),
    )
    if args.stage == 4:
        probe_path = ROOT / stage["probe_receipt"]
        record["stage4_identities"] = dict(
            bindings=file_identity(stage["bindings"]),
            diff_ledger=file_identity(stage["diff_ledger"]),
            card_profile=manifest.get("card_profile"),
            guard_rule=dict(GUARD_RULE_V2),
            model=args.model,
            effort=None if args.effort is None else args.effort,
            probe=dict(
                n=stage["probe_n"],
                wall_budget_ms=stage["probe_wall_budget_ms"],
                batch=stage["probe_batch"],
                concurrency=stage["probe_concurrency"],
                max_retries=1,
                require_whole_manifest=False,
                whole_manifest_checked=False,
                receipt=file_identity(stage["probe_receipt"]) if probe_path.is_file() else dict(
                    path=stage["probe_receipt"], pending=True,
                    note="16-item real probe; written after the probe; cannot establish P2-7",
                ),
                note="validator partial API, whole_manifest_checked=false; a 16-item success cannot establish P2-7",
            ),
        )
        record["evaluation_identity"]["stage4_bindings"] = file_identity(stage["bindings"])
        record["cards_and_heads"]["diff_ledger"] = file_identity(stage["diff_ledger"])
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="EXECUTION_RECORD_WRITTEN", out=str(args.out), sha256=sha(text.encode("utf-8")),
                          git_sha=record["integrated_candidate"]["git_sha"], clean=record["integrated_candidate"]["working_tree_clean"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
