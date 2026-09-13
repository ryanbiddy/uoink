"""Mechanical source assembly only; never reads a checkpoint or runs a reader."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
HERE = Path(__file__).absolute().parent
reader_bytes = (HERE / "before/read_checkpoint_inventory.py").read_bytes()
tracer_bytes = (HERE / "before/symbolic_trace.py").read_bytes()
assert hashlib.sha256(reader_bytes).hexdigest() == "67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5"
assert hashlib.sha256(tracer_bytes).hexdigest() == "f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127"
reader = reader_bytes.decode("utf-8").replace("\r\n", "\n")
tracer = tracer_bytes.decode("utf-8").replace("\r\n", "\n")


def without_headers(text):
    parsed = ast.parse(text)
    excluded = set()
    for item in parsed.body:
        if (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and type(item.value.value) is str) or (isinstance(item, ast.ImportFrom) and item.module == "__future__"):
            excluded.update(range(item.lineno, item.end_lineno + 1))
        else:
            break
    return "".join(line for index, line in enumerate(text.splitlines(keepends=True), 1) if index not in excluded)


tracer = without_headers(tracer).replace("require(", "trace_require(")
reader = without_headers(reader)
old_stop = '    require(last_name == "STOP" and last_position + 1 == len(payload), "Pickle is truncated or has trailing data")\n'
assert reader.count(old_stop) == 1
reader = reader.replace(old_stop, old_stop + '    symbolic = trace_pickle_metadata(payload)\n    clock_check(started)\n')
old_return = '    return {"member": member.filename, "bytes": length, "sha256": hashlib.sha256(payload).hexdigest(),\n'
assert reader.count(old_return) == 1
reader = reader.replace(old_return, old_return + '            "symbolic_metadata_trace": symbolic,\n')
reader = reader.replace('OUTPUT = ROOT / "_scratch/vad-static-inventory-proposal01/results"',
                        'OUTPUT = ROOT / "_scratch/vad-symbolic-adapter-proposal01/results"')
reader = reader.replace('except (Refusal, zipfile.BadZipFile,', 'except (TraceRefusal, Refusal, zipfile.BadZipFile,')
reader = reader.replace('        result["status"] = "static_inventory_complete"',
                        '        clock_check(started)\n        result["status"] = "static_symbolic_inventory_complete"')
reader = reader.replace('"bounded static inventory only"', '"bounded static and inert symbolic metadata inventory only"')
assembled = ('"""Fixed hash-bound static and inert symbolic metadata proposal; no model loading.\n'
             'Root review is required before any actual checkpoint inspection.\n"""\n'
             'from __future__ import annotations\n\n# Pure tracer; only its require helper is renamed.\n'
             + tracer + '\n# Fixed inventory reader with bounded in-memory symbolic handoff.\n' + reader)
ast.parse(assembled)
destination = HERE / "read_symbolic_inventory.py"
with destination.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(assembled)
print(json.dumps({"source": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                  "checkpoint_read": False, "source_definitions_executed": False}, indent=2))
