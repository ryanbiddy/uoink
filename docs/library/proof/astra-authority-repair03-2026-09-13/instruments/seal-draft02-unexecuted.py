"""Unexecuted documentary seal draft. Run only after the integrator supplies exits.

This program copies source, tests and receipts. It never imports product code,
runs a test, starts/stops a process, stages Git content, or performs network I/O.
An existing destination is a refusal; a failed partial seal is left intact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET


CHECKOUT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
WORKER = Path(r"C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a5e7ba0d-26f\grok")
DEST = WORKER / "docs/library/proof/astra-authority-repair03-2026-09-13"
SOURCE_SHA = "67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23"
HISTORY = CHECKOUT / "docs/library/proof/astra-authority-a5-review-2026-09-13"
HISTORY_COMMIT = "e8b5d8e0cc03e84982853e92a74bc7bcd32bd613"
HISTORY_MANIFEST_SHA = "e95ce31779ed9820b874f1bc91e81ee1c7a384684775091a28a427d5d2703b06"
ROOTS = (CHECKOUT, WORKER)
PAYLOADS = {}
ORIGINS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, *, must_exist=True):
    """Reject links/reparse points before reading any explicitly scoped input."""
    path = Path(os.path.abspath(path))
    owner = next((root for root in ROOTS if path.is_relative_to(root)), None)
    if owner is None:
        raise RuntimeError("Input is outside the two authorized repositories")
    current = owner
    for part in path.relative_to(owner).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise RuntimeError("Linked/reparse input refused: " + str(current))
    if must_exist and not path.is_file():
        raise RuntimeError("Required input is missing: " + str(path))
    return path


def read(path):
    return checked(path).read_bytes()


def add(path, relative):
    relative = str(relative).replace("\\", "/")
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise RuntimeError("Unsafe archive member")
    if relative in PAYLOADS:
        raise RuntimeError("Duplicate archive member: " + relative)
    data = read(path)
    PAYLOADS[relative] = data
    ORIGINS[relative] = {"source": str(path), "bytes": len(data), "sha256": digest(data)}


def add_tree(source, prefix):
    source = checked(source, must_exist=False)
    if not source.is_dir():
        raise RuntimeError("Required input directory is missing: " + str(source))
    for parent, dirs, files in os.walk(source, followlinks=False):
        for name in dirs:
            checked(Path(parent) / name, must_exist=False)
        for name in files:
            item = Path(parent) / name
            add(item, prefix + "/" + item.relative_to(source).as_posix())


def emit_json(relative, value):
    if relative in PAYLOADS:
        raise RuntimeError("Duplicate generated member")
    PAYLOADS[relative] = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def inspect_run(root, label, expected_exit):
    if not re.fullmatch(r"[a-z0-9-]+", label):
        raise RuntimeError("Invalid run label")
    folder = root / "_scratch" / label
    results = json.loads(read(folder / "results.json"))
    if not isinstance(results, list) or len(results) != 1 or results[0].get("name") != "tests":
        raise RuntimeError("Unexpected verifier result shape: " + label)
    actual_exit = results[0].get("exit")
    if not isinstance(actual_exit, int) or actual_exit != expected_exit:
        raise RuntimeError("Missing or unexpected verifier exit: " + label)
    command = results[0].get("command", [])
    if "--runxfail" not in command:
        raise RuntimeError("Run did not include frozen expected-failure assertions")
    document = ET.fromstring(read(folder / "tests.xml"))
    cases = document.findall(".//testcase")
    counts = {"total": len(cases), "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for case in cases:
        if case.find("failure") is not None:
            counts["failed"] += 1
        elif case.find("error") is not None:
            counts["errors"] += 1
        elif case.find("skipped") is not None:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    if not cases:
        raise RuntimeError("Empty test receipt: " + label)
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    for xml_name, count_name in (("tests", "total"), ("failures", "failed"), ("errors", "errors"), ("skipped", "skipped")):
        if sum(int(suite.attrib.get(xml_name, "0")) for suite in suites) != counts[count_name]:
            raise RuntimeError("XML counts do not match its cases: " + label)
    if actual_exit == 0 and counts["failed"] + counts["errors"]:
        raise RuntimeError("Zero exit conflicts with failing XML: " + label)
    add_tree(folder, "runs/" + label)
    return {"label": label, "root": str(root), "verifier_exit": actual_exit, "counts": counts,
            "junit_seconds": sum(float(suite.attrib.get("time", "0")) for suite in suites),
            "command": command}


def collect(args):
    if digest(read(WORKER / "library_mirror.py")) != SOURCE_SHA:
        raise RuntimeError("The 49-pass source changed; preserve/rebind this draft before sealing")
    audit_path = WORKER / "_scratch/astra-authority-repair03/review-input-audit.json"
    audit = json.loads(read(audit_path))
    if not audit.get("all_checks_passed"):
        raise RuntimeError("Frozen behavior audit did not pass")
    for relative, expected in audit["sha256"].items():
        source = WORKER / relative
        if digest(read(source)) != expected:
            raise RuntimeError("Reviewed source/test bytes changed: " + relative)
        add(source, "source/" + relative)

    add_tree(WORKER / "_scratch/astra-authority-repair03", "repair-history")
    add(WORKER / "docs/library/MIRROR-AUTHORITY-ASTRA-REPAIR03-2026-09-13.md", "reviews/repair03-worker-report.md")
    add(CHECKOUT / "_scratch/AUTHORITY-REPAIR03-INTEGRATOR-QUALIFICATION-2026-09-13.md", "reviews/integrator-qualification.md")
    add(CHECKOUT / "_scratch/AUTHORITY-REPAIR03-PATH-QUALIFICATION-REPAIR-2026-09-13.md", "reviews/path-budget-repair.md")
    add(CHECKOUT / "docs/library/MIRROR-AUTHORITY-ASTRA-REPAIR03-BRIEF-2026-09-13.md", "reviews/repair03-brief.md")
    add(CHECKOUT / "docs/library/ASTRA-AUTHORITY-A5-REVIEW-2026-09-13.md", "reviews/historical-a5-held-review.md")
    add(CHECKOUT / "_scratch/run_process_authority_repair03_verification.ps1", "instruments/run_process_authority_repair03_verification.ps1")
    add(CHECKOUT / "_scratch/integrator_verify.py", "instruments/integrator_verify.py")
    add(Path(__file__), "instruments/seal_astra_authority_repair03.py")
    add(WORKER / "_scratch/seal_astra_authority_repair03.draft01-unexecuted.py", "instruments/seal-draft01-unexecuted.py")

    runs = []
    for label, expected_count in (("astra-authority-a5-repair01", 39),
                                  ("astra-authority-repair03-01", 44),
                                  ("astra-authority-repair03-02", 46),
                                  ("astra-authority-repair03-03", 49),
                                  ("astra-authority-repair03-independent01", 49)):
        result = inspect_run(WORKER, label, 0)
        if result["counts"] != {"total": expected_count, "passed": expected_count, "failed": 0, "errors": 0, "skipped": 0}:
            raise RuntimeError("Synthetic receipt differs from the reported count: " + label)
        result["scope"] = "synthetic only; no full-tree or release acceptance"
        runs.append(result)

    original_phase4 = inspect_run(WORKER, "astra-authority-repair03-worker-phase4-01", 1)
    if original_phase4["counts"] != {"total": 233, "passed": 174, "failed": 59, "errors": 0, "skipped": 0}:
        raise RuntimeError("Original failed Phase4 receipt differs from the observed counts")
    original_phase4["scope"] = "original real Phase4 FAIL; overlong verifier temporary path diagnosed"
    runs.append(original_phase4)
    first_case = WORKER / "_scratch/astra-authority-repair03-worker-phase4-01-0/a0"
    add(first_case / "d/reach/mirror/ledger.json", "path-budget-evidence/original-a0-ledger.json")
    add(first_case / "v/Uoink/.uoink-mirror/manifest.json", "path-budget-evidence/original-a0-manifest.json")

    worker_phase4 = inspect_run(WORKER, "a3w02", args.worker_exit)
    worker_phase4["scope"] = "real Phase 4 qualification"
    runs.append(worker_phase4)
    checkout_phase4 = None
    if args.checkout_exit is not None:
        checkout_source = read(CHECKOUT / "library_mirror.py")
        worker_source = read(WORKER / "library_mirror.py")
        if checkout_source.replace(b"\r\n", b"\n") != worker_source.replace(b"\r\n", b"\n"):
            raise RuntimeError("Checkout source differs beyond Git line endings")
        add(CHECKOUT / "library_mirror.py", "source-checkout/library_mirror.py")
        checkout_phase4 = inspect_run(CHECKOUT, "a3c01", args.checkout_exit)
        checkout_phase4["source_sha256"] = digest(checkout_source)
        checkout_phase4["worker_comparison"] = "identical after CRLF/LF normalization; original bytes retained"
        checkout_phase4["scope"] = "real Phase 4 qualification after integration"
        runs.append(checkout_phase4)
    elif not args.checkout_not_run_reason:
        raise RuntimeError("Record why checkout qualification was not run")

    history_manifest = read(HISTORY / "SHA256.json")
    if digest(history_manifest) != HISTORY_MANIFEST_SHA:
        raise RuntimeError("Committed historical manifest changed")
    history = json.loads(history_manifest)
    for relative, record in history["files"].items():
        data = read(HISTORY / relative)
        if digest(data) != record["sha256"] or len(data) != record["bytes"]:
            raise RuntimeError("Committed historical archive mismatch: " + relative)
    add(HISTORY / "SHA256.json", "historical-references/a5-SHA256.json")
    emit_json("historical-references/a5-reference.json", {
        "commit": HISTORY_COMMIT, "archive": "docs/library/proof/astra-authority-a5-review-2026-09-13",
        "manifest_sha256": HISTORY_MANIFEST_SHA, "manifest_members_verified": len(history["files"]),
        "measurements": {"astra-worker01": "35 passed; historical proposed source",
                         "astra-boundary01": "2 passed, 2 failed; held proposal"},
        "status": "Historical rejected proposal and failed boundaries; never current acceptance",
        "provisional39": "The distinct-writer/use-count repair's separate 39-pass receipt is copied in this seal"})

    qualified = bool(worker_phase4["verifier_exit"] == 0 and checkout_phase4 is not None
                     and checkout_phase4["verifier_exit"] == 0)
    emit_json("QUALIFICATION.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": SOURCE_SHA,
        "phase4_state": "both-root Phase4 checks passed" if qualified else "held",
        "checkout_not_run_reason": args.checkout_not_run_reason if checkout_phase4 is None else None,
        "release_acceptance": False, "full_tree_acceptance": False,
        "tree08_failure_cause_claim": False, "runs": runs})
    PAYLOADS[".gitattributes"] = b"* -text\n"
    PAYLOADS["README.md"] = (
        "# Authority repair03 evidence\n\n"
        "This archive preserves the 39-pass intermediate stage, 44/46/49-pass\n"
        "repair stages, independent 49-case review, and the completed Phase 4\n"
        "qualification receipts listed in QUALIFICATION.json. Missing checkout\n"
        "qualification is recorded explicitly. Failures retain their original\n"
        "counts; synthetic passes do not grant full-tree or release acceptance.\n\n"
        "The earlier Grok proposal and failed review are historical evidence,\n"
        "referenced by their committed archive and verified manifest.\n\n"
        "SHA256.json hashes every sealed payload except itself. Original copied\n"
        "bytes and their source paths are recorded in ARCHIVE-ORIGINAL-SHA256.json.\n"
    ).encode("utf-8")
    emit_json("ARCHIVE-ORIGINAL-SHA256.json", {"algorithm": "sha256", "files": ORIGINS})
    return runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-exit", type=int, required=True, help="Integrator-observed completed worker Phase4 exit")
    parser.add_argument("--checkout-exit", type=int)
    parser.add_argument("--checkout-not-run-reason")
    parser.add_argument("--seal", action="store_true", help="Only after the integrator authorizes final sealing")
    args = parser.parse_args()
    if args.checkout_exit is not None and args.checkout_not_run_reason:
        parser.error("Checkout cannot be both measured and not run")
    checked(DEST, must_exist=False)
    if DEST.exists():
        raise RuntimeError("Fresh destination required; retain any existing partial seal")
    runs = collect(args)
    if not args.seal:
        print(json.dumps({"unexecuted_write_plan": True, "destination": str(DEST), "payloads": len(PAYLOADS), "runs": runs}, indent=2))
        return
    DEST.mkdir(parents=True, exist_ok=False)
    for relative, data in sorted(PAYLOADS.items()):
        output = DEST / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    verification = {}
    for relative, record in ORIGINS.items():
        copied = checked(DEST / relative).read_bytes()
        if digest(copied) != record["sha256"] or len(copied) != record["bytes"]:
            raise RuntimeError("Copied bytes differ: " + relative)
        # A source changing during this copy must not receive a successful seal.
        if digest(read(Path(record["source"]))) != record["sha256"]:
            raise RuntimeError("Source changed during copy: " + relative)
        verification[relative] = {"matched": True, "sha256": record["sha256"]}
    check = (json.dumps({"all_copies_match": True, "files": verification}, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (DEST / "COPY-VERIFICATION.json").write_bytes(check)
    PAYLOADS["COPY-VERIFICATION.json"] = check
    manifest = {"algorithm": "sha256", "files": {
        name: {"bytes": len(data), "sha256": digest(data)} for name, data in sorted(PAYLOADS.items())}}
    (DEST / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for relative, record in manifest["files"].items():
        if digest(read(DEST / relative)) != record["sha256"]:
            raise RuntimeError("Final manifest mismatch: " + relative)
    print(json.dumps({"sealed": True, "destination": str(DEST), "payloads": len(PAYLOADS),
                      "manifest_sha256": digest(read(DEST / "SHA256.json"))}, indent=2))


if __name__ == "__main__":
    main()
