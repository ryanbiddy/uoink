"""Freeze approved instrument and installed pytest source bytes only."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
OUT = Path(__file__).resolve().parent / "before"
assert not OUT.exists()
OUT.mkdir()
paths = [(ROOT / "_scratch" / name, "instruments/" + name) for name in (
    "partition_receipt_plugin.py", "partition_exit_contract.py",
    "run_partitioned_mirror_tree09.py", "run_complete_mirror_tree09_durable.py",
    "seal_partitioned_mirror_tree09.py", "test_partition_exit_contract.py",
    "integrator_verify.py", "mirror_state_receipt_plugin.py",
)]
paths += [(ROOT / "docs/library/proof/partition-exit-repair-2026-09-13/SHA256.json", "ORIGINAL-PARTITION-EXIT-REPAIR-SHA256.json")]
pytest_root = Path(r"C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\_pytest")
paths += [(pytest_root / name, "installed-pytest/" + name) for name in (
    "subtests.py", "unittest.py", "reports.py", "main.py", "junitxml.py", "terminal.py", "_version.py",
)]
paths += [(Path(__file__), "freeze_before.py"), (Path(__file__).parent / "BRIEF.md", "BRIEF.md")]
rows = []
for source, relative in paths:
    data = source.read_bytes()
    expected = hashlib.sha256(data).hexdigest()
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert target.read_bytes() == data and hashlib.sha256(source.read_bytes()).hexdigest() == expected
    rows.append({"file": relative, "source": str(source), "bytes": len(data), "sha256": expected})
(OUT / ".gitattributes").write_bytes(b"* -text\n")
rows.append({"file": ".gitattributes", "bytes": 8, "sha256": hashlib.sha256(b"* -text\n").hexdigest()})
(OUT / "SHA256.json").write_text(json.dumps({"payloads": rows, "payload_count": len(rows)}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"payload_count": len(rows), "manifest_sha256": hashlib.sha256((OUT / "SHA256.json").read_bytes()).hexdigest()}))
