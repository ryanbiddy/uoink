"""Write inert metadata and expected-member text; never construct a wheel."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path

out = Path(__file__).resolve().parent
inventory = json.loads((out / "inventory.json").read_bytes())
old_dist = "faster_whisper-1.2.1.dist-info"
new_dist = "faster_whisper-1.2.1+uoink.localassets1.dist-info"
proposed = out / "proposed-distribution-text"
proposed.mkdir(exist_ok=False)
source = out / "inputs/upstream-wheel-text"
metadata = (source / (old_dist + "/METADATA.txt")).read_bytes()
assert metadata.count(b"Version: 1.2.1\n") == 1
metadata = metadata.replace(b"Version: 1.2.1\n", b"Version: 1.2.1+uoink.localassets1\n")
wheel_meta = (source / (old_dist + "/WHEEL.txt")).read_bytes()
assert wheel_meta.count(b"Generator: bdist_wheel (0.45.1)\n") == 1
wheel_meta = wheel_meta.replace(b"Generator: bdist_wheel (0.45.1)\n", b"Generator: uoink-localassets-wheel (1)\n")
notice = b'''Uoink local derivative: faster-whisper 1.2.1+uoink.localassets1
Based on faster-whisper 1.2.1 by SYSTRAN; original MIT license retained.

Local change: prepare available tokenizer input before CTranslate2 construction
and refuse a missing tokenizer when local_files_only=True. The explicit
non-local fallback is retained. The package version and distribution metadata
identify this modification separately from upstream.

Patch SHA-256: ef6e3ea49d4a30279ec6a37dc5d737db5ea8d8d1191af25c578f6411c407b764
This notice does not claim upstream endorsement, advisory clearance, model
quality, speaker attribution, or complete runtime/release acceptance.
'''
replacements = {
    "faster_whisper/transcribe.py": (out / "inputs/proposal/companion-B.py.txt").read_bytes(),
    "faster_whisper/version.py": (out / "proposed-version.py.txt").read_bytes(),
    new_dist + "/METADATA": metadata,
    new_dist + "/WHEEL": wheel_meta,
    new_dist + "/UOINK-LOCALASSETS-NOTICE.txt": notice,
}
for name, raw in (("METADATA.txt", metadata), ("WHEEL.txt", wheel_meta), ("UOINK-LOCALASSETS-NOTICE.txt", notice)):
    (proposed / name).write_bytes(raw)
members = []
for row in inventory["members"]:
    original = row["member"]
    if original.endswith("/RECORD"):
        continue
    name = original.replace(old_dist + "/", new_dist + "/", 1)
    if name in replacements:
        raw = replacements[name]
        digest = hashlib.sha256(raw).digest()
        size = len(raw)
        scope = "Proposed exact text bytes only; not packaged"
    else:
        digest = base64.urlsafe_b64decode(row["record_hash"].split("=", 1)[1] + "=")
        size = int(row["record_bytes"])
        scope = "Upstream RECORD declaration; model member not read" if original.endswith(".onnx") else "Verified original text bytes; proposed unchanged"
    members.append({"member": name, "bytes": size, "sha256": digest.hex(), "basis": scope,
                    "record_hash": "sha256=" + base64.urlsafe_b64encode(digest).decode().rstrip("=")})
digest = hashlib.sha256(notice).digest()
members.append({"member": new_dist + "/UOINK-LOCALASSETS-NOTICE.txt", "bytes": len(notice),
                "sha256": digest.hex(), "basis": "Proposed new notice bytes only; not packaged",
                "record_hash": "sha256=" + base64.urlsafe_b64encode(digest).decode().rstrip("=")})
members.sort(key=lambda row: row["member"])
stream = io.StringIO(newline="")
writer = csv.writer(stream, lineterminator="\n")
for row in members:
    writer.writerow([row["member"], row["record_hash"], row["bytes"]])
record_name = new_dist + "/RECORD"
writer.writerow([record_name, "", ""])
record_bytes = stream.getvalue().encode()
(proposed / "RECORD.csv.txt").write_bytes(record_bytes)
members.append({"member": record_name, "bytes": len(record_bytes), "sha256": hashlib.sha256(record_bytes).hexdigest(),
                "basis": "Proposed RECORD text from declared/planned members; not verified against an output wheel", "record_hash": ""})
assert len(members) == 16
manifest = {"status": "PROPOSED_ONLY", "distribution": "faster-whisper", "version": "1.2.1+uoink.localassets1",
    "filename": "faster_whisper-1.2.1+uoink.localassets1-py3-none-any.whl", "output_wheel_sha256": None,
    "output_wheel_built": False, "member_count": len(members), "members": members,
    "zip": {"compression": "ZIP_STORED", "timestamp": [2026, 9, 13, 0, 0, 0], "create_system": 3,
            "file_mode": "0o100644", "order": "sorted non-RECORD members, then RECORD", "comments": "empty"}}
(out / "proposed-member-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"planned_members": len(members), "wheel_built": False,
                  "new_model_or_dependency_read": False, "metadata_record_text_only": True}))
