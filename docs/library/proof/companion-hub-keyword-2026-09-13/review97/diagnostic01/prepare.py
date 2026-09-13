"""Preserve original proof and add denied-path diagnostics to a fresh harness."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
original = out.parent / "companion-hub-keyword01"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
copies = []
for source in sorted(original.rglob("*")):
    if not source.is_file():
        continue
    assert source.stat().st_size < 256 * 1024
    raw = source.read_bytes()
    relative = source.relative_to(original)
    target = out / "original" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    copies.append({"file": str(relative).replace("\\", "/"), "bytes": len(raw), "sha256": sha(raw)})
before = (original / "qualify.py").read_text(encoding="utf-8")
assert sha((original / "qualify.py").read_bytes()) == "46bbaabe69e31729bec5171bb28a6167846d070d29d1df87a4c9e7ae5b055c16"
after = before.replace("('baseline02', 'patched02')", "('diagnostic01', 'unused-patched')").replace("label == 'baseline02'", "label == 'diagnostic01'").replace("'INPUT-SHA256-02.json'", "'INPUT-DIAGNOSTIC.json'")
old = "blocked.append('open:outside-scope')"
new = "blocked.append({'event': 'open:outside-scope', 'path': str(path)})"
assert after.count(old) == 1
after = after.replace(old, new)
def contracts(text):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Contracts")
    return ast.dump(node, include_attributes=False)
assert contracts(before) == contracts(after)
for name in ("utils-before.py.txt", "utils-after.py.txt", "hub-signature-source.py.txt", "patch.txt"):
    with (out / name).open("xb") as stream:
        stream.write((original / name).read_bytes())
(out / "qualify.py").write_text(after, encoding="utf-8", newline="\n")
(out / "diagnostic-only.patch.txt").write_text("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="original/qualify.py", tofile="diagnostic/qualify.py")), encoding="utf-8", newline="\n")
(out / "original-copy-manifest.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "payloads": copies, "contract_class_ast_unchanged": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
rows = []
for path in sorted(out.iterdir()):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({"file": path.name, "bytes": len(raw), "sha256": sha(raw)})
(out / "INPUT-DIAGNOSTIC.json").write_text(json.dumps({"payloads": rows}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"original_files_preserved": len(copies), "contract_class_ast_unchanged": True}))
