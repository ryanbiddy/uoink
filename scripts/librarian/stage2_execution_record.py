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
    parser.add_argument("--approval-record", default="docs/library/INDUCTION-AUDIT-7-2026-09-05.md")
    parser.add_argument("--authorization", required=True,
                        help="Who authorized the execution and when (Ryan's standing stage 2 authorization)")
    parser.add_argument("--budget-note", required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--port", type=int, default=5180)
    args = parser.parse_args(argv)
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is set; the measured pass is subscription-only", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_STAGE2.read_text(encoding="utf-8"))
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
        stage2_manifest=dict(file_identity("docs/library/proof/manifest-stage2-2026-09-05.json"),
                             manifest_hash=manifest["manifest_hash"], contract_version=manifest["contract_version"],
                             targets=len(manifest["items"]), exclusions=len(manifest["exclusions"])),
        source=dict(manifest["source"], upgrade=manifest["upgrade"]),
        cards_and_heads=dict(cards_hash=manifest["cards_hash"], corpus_heads_hash=manifest["corpus_heads_hash"],
                             card_profile_hash=manifest["hashes"]["card_profile_hash"],
                             card_builder=file_identity(files["card_builder"]["path"])),
        evaluation_identity=dict(holdout=file_identity(files["holdout"]["path"]),
                                 holdout_version=holdout["version"],
                                 strata={k: len(v) for k, v in holdout["strata"].items()},
                                 labelling_packet=file_identity("docs/library/proof/holdout-v2-labelling-packet-7-2026-09-05.json")),
        sealed_labels_and_mapping=dict(
            gold=file_identity(files["gold"]["path"]), mapping=file_identity(files["mapping"]["path"]),
            adjudicated=dict(path=mapping["adjudicated_file"], sha256=mapping["adjudicated_sha256"]),
            gold_items=len(gold), sealed=all(item.get("sealed") is True for item in gold),
            scorable=sum(1 for row in mapping["items"].values() if row["scorable"]),
            labellers=["gemini-3.8-flash-high (blind, run Y)", "grok-4.6 (blind, run Y)"],
            adjudicator="gpt-6-astra (blind, run Z)",
            scoring_version=mapping["scoring_version"],
            rule="NFC + trimmed segments, case preserved, deepest unambiguous approved ancestor, strict primary equality"),
        approved_taxonomy=dict(file_identity(files["taxonomy"]["path"]), version_id=taxonomy["version_id"],
                               parent_version_id=taxonomy["parent_version_id"],
                               parent_revision_hash=taxonomy["parent_revision_hash"],
                               revision_hash=taxonomy["revision_hash"], nodes=len(taxonomy["nodes"]),
                               approval=taxonomy["approval"], approval_record=args.approval_record,
                               parent_file=file_identity(files["parent_taxonomy"]["path"])),
        assignment_prompt=dict(file_identity(files["prompt"]["path"]),
                               prompt_sha256_text_mode=manifest["hashes"]["prompt_sha256"],
                               renderer="proof_run.render_prompt: {{TAXONOMY}} then {{CARDS}}, template read in text mode (universal newlines)"),
        installed_client=dict(name="Claude Code CLI (subscription)", version=claude_version, executable=claude_exe,
                              executable_sha256=sha(Path(claude_exe).read_bytes()) if claude_exe and Path(claude_exe).is_file() else None,
                              model=args.model, tools="disabled (--tools \"\")", session_persistence="disabled",
                              api_key="ANTHROPIC_API_KEY unset at record time; the harness asserts it per process"),
        corpus_egress=dict(authorization=args.authorization,
                           permitted="librarian-profile evidence cards (title, channel, platform, source type, hashes, summary hint, up to six excerpts of 240 characters) rendered into the frozen assignment prompt and sent to the subscription client",
                           forbidden="labels, gold, mapping, holdout membership, predictions from earlier runs, corpus files beyond the bounded heads"),
        budget_and_isolation=dict(budget=args.budget_note, wall_budget_ms=manifest["execution"]["wall_budget_ms"],
                                  concurrency=args.concurrency, batch=args.batch, max_retries=manifest["execution"]["max_retries"],
                                  error_rate_limit=manifest["execution"]["error_rate_limit"],
                                  error_rate_min_attempts=manifest["execution"]["error_rate_min_attempts"],
                                  port=args.port, apply_enabled=False, live_index="never opened; isolated helper on a disposable duplicate"),
        implementation=dict(implementation_hash=manifest["hashes"]["implementation_hash"],
                            files={name: file_identity(entry["path"]) for name, entry in files.items()},
                            runner=file_identity("scripts/librarian/proof_run.py"),
                            validator=file_identity("tests/validate_proof_receipts.py"),
                            scorer=file_identity("scripts/librarian/proof_score.py")),
    )
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="EXECUTION_RECORD_WRITTEN", out=str(args.out), sha256=sha(text.encode("utf-8")),
                          git_sha=record["integrated_candidate"]["git_sha"], clean=record["integrated_candidate"]["working_tree_clean"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
