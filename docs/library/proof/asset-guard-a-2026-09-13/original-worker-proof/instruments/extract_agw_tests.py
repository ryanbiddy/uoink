"""Extract the authorized synthetic product tests without executing source."""
import ast
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
proposal = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-asset-guard-proposal01")
manifest = proposal / "SHA256.json"
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"
seal = json.loads(manifest.read_text(encoding="utf-8"))
for row in seal["payloads"]:
    data = (proposal / row["file"]).read_bytes()
    assert len(data) == row["bytes"]
    assert hashlib.sha256(data).hexdigest() == row["sha256"]

source = (proposal / "tests-proposed.py.txt").read_text(encoding="utf-8")
tree = ast.parse(source)
selected = [node for node in tree.body if (
    isinstance(node, ast.FunctionDef) and node.name in {"blocked", "runner_functions"}
) or (isinstance(node, ast.ClassDef) and node.name == "ProductGuardContracts")]
assert len(selected) == 3
header = '''"""Synthetic ASR cache/consent contracts; never import the runner or a model.

Derived from the reviewed product-A proposal's eleven ProductGuardContracts.
The selected runner function bodies execute only with fake runtime seams and
temporary placeholder files. No model, decoder or download code is exercised.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RUNNER_SOURCE = Path(__file__).resolve().parents[1] / "whisper_runner.py"


'''
output = header + "\n\n\n".join(ast.get_source_segment(source, node) for node in selected) + "\n"
target = root / "tests/test_whisper_cache_consent.py"
assert not target.exists()
target.write_text(output, encoding="utf-8", newline="\n")
extracted = ast.parse(output)
original_class = next(node for node in selected if isinstance(node, ast.ClassDef))
new_class = next(node for node in extracted.body if isinstance(node, ast.ClassDef))
assert ast.dump(original_class, include_attributes=False) == ast.dump(new_class, include_attributes=False)
for node in selected[:2]:
    matching = next(item for item in extracted.body if isinstance(item, ast.FunctionDef) and item.name == node.name)
    assert ast.dump(node, include_attributes=False) == ast.dump(matching, include_attributes=False)
methods = [node.name for node in original_class.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
assert len(methods) == 11
assert "CompanionConstructorContracts" not in output
assert "whisper_constructor_prefix" not in output
record = {
    "source": str(proposal / "tests-proposed.py.txt"),
    "source_sha256": hashlib.sha256((proposal / "tests-proposed.py.txt").read_bytes()).hexdigest(),
    "target": "tests/test_whisper_cache_consent.py",
    "target_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    "unchanged_ast_test_methods": methods,
    "entire_product_class_ast_unchanged": True,
    "helper_asts_unchanged": ["blocked", "runner_functions"],
    "setup_changes": [
        "RUNNER_SOURCE is the worktree file derived from the new test path; no CLI selection.",
        "Removed FW_SOURCE, companion constructor helper/class and CLI execution block.",
        "Kept only imports used by ProductGuardContracts and its two helpers.",
        "Added a synthetic-scope module docstring; no assertion body changed.",
    ],
    "sealed_proposal_payloads_verified": len(seal["payloads"]),
    "source_executed_during_extraction": False,
}
(root / "_scratch/agw-test-extraction.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
