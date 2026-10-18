"""Re-render a proof receipts document under a receipt-contract mapping that
the harness applied late, without touching any measurement.

The only transformation: attempt outcome "error" -> "rejected" (PROOF-PLAN
"Receipt JSON contract": a service outcome error maps to receipt outcome
rejected; the raw result and response retain "error"). Everything else is
byte-identical. The original file's sha256 and the rule are recorded under
audit_extensions.rerender so an auditor can diff the two documents.

Usage: python scripts/librarian/proof_rerender.py <in.json> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    raw = src.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    changed = []
    for attempt in doc.get("attempts", []):
        if attempt.get("outcome") == "error":
            attempt["outcome"] = "rejected"
            changed.append(attempt.get("attempt_id") or attempt.get("video_id"))
    ext = doc.setdefault("audit_extensions", {})
    ext["rerender"] = {
        "from_file": src.name,
        "from_sha256": hashlib.sha256(raw).hexdigest(),
        "rule": "PROOF-PLAN receipt contract: service outcome error -> receipt outcome rejected",
        "attempts_changed": changed,
        "measurements_changed": False,
    }
    dst.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"rerendered": str(dst), "attempts_changed": len(changed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
