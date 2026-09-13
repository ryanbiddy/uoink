"""Stdlib synthetic comparison only; neither input/main path may execute."""
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import time
import zipfile


HERE = Path(__file__).absolute().parent
CHECKPOINT = os.path.normcase(os.path.abspath(
    HERE.parent.parent / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"))
BEFORE = HERE / "before/read_checkpoint_inventory.py"
AFTER = HERE / "read_checkpoint_inventory.py"
BEFORE_HASH = "f27b91e610284e26975038ff6826f2190758b1d4c53a402db3c2d0386cc4d40d"


def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.normcase(os.path.abspath(os.fsdecode(args[0]))) == CHECKPOINT:
            raise RuntimeError("Actual checkpoint access is forbidden in this qualification")
    if event.startswith(("socket.", "subprocess.", "os.system", "ctypes.")):
        raise RuntimeError("Network/process/native actions are forbidden in this qualification")


sys.addaudithook(audit)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
before_bytes = BEFORE.read_bytes()
after_bytes = AFTER.read_bytes()
assert hashlib.sha256(before_bytes).hexdigest() == BEFORE_HASH


def forbidden(*args, **kwargs):
    raise AssertionError("The reader inspect/main path must never execute")


def load_definitions(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.inspect = forbidden
    module.main = forbidden
    return module


old = load_definitions("approved_static_reader", BEFORE)
new = load_definitions("tail_static_reader", AFTER)


def archive_bytes(payload, method=zipfile.ZIP_STORED, name="archive/data.pkl"):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=method) as archive:
        archive.writestr(name, payload)
    return target.getvalue()


def literal_string(value):
    encoded = value.encode("utf-8")
    return b"X" + struct.pack("<L", len(encoded)) + encoded


def literal_list(tokens):
    # Construct pickle syntax as bytes only; never deserialize it.
    return b"\x80\x02](" + b"".join(literal_string(token) for token in tokens) + b"e."


def parse_memory(reader, raw):
    stream = io.BytesIO(raw)
    started = time.monotonic()
    bounds = reader.directory_bounds(stream, len(raw))
    with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
        entries, total, member = reader.member_inventory(stream, archive, bounds, len(raw), started)
        pickle_inventory = reader.parse_pickle(archive, member, started)
    return {"directory": bounds, "members": entries, "advertised_total": total, "pickle": pickle_inventory}


def compare_outputs(payload, first, tail, method=zipfile.ZIP_STORED):
    raw = archive_bytes(payload, method)
    approved = parse_memory(old, raw)
    revised = parse_memory(new, raw)
    actual_tail = revised["pickle"].pop("identifier_string_tail_samples")
    tail_limit = revised["pickle"].pop("string_tail_sample_limit")
    assert tail_limit == 64
    assert actual_tail == tail, (actual_tail, tail)
    assert len(actual_tail) <= 64 and all(len(token) <= 96 for token in actual_tail)
    assert revised["pickle"]["identifier_string_samples"] == first
    assert revised == approved, "An output other than the two tail fields changed"
    assert not revised["pickle"]["objects_constructed"]
    assert not revised["pickle"]["stack_globals_resolved"]
    assert not revised["pickle"]["persistent_ids_resolved"]
    return revised


def compare_refusal(raw):
    outcomes = []
    for reader in (old, new):
        try:
            parse_memory(reader, raw)
        except (reader.Refusal, zipfile.BadZipFile, ValueError, UnicodeError, struct.error) as exc:
            outcomes.append((type(exc).__name__, str(exc), getattr(exc, "directory_entry", None)))
        else:
            raise AssertionError("Both readers must retain the same refusal")
    assert outcomes[0] == outcomes[1], outcomes


tokens100 = ["token_" + str(number) for number in range(100)]
tokens64 = tokens100[:64]
cases = [
    ("more_than_64_first_unchanged_tail_order", lambda: compare_outputs(
        literal_list(tokens100), tokens100[:64], tokens100[36:])),
    ("exactly_64_tokens", lambda: compare_outputs(literal_list(tokens64), tokens64, tokens64)),
    ("short_tail", lambda: compare_outputs(literal_list(["one", "two"]), ["one", "two"], ["one", "two"])),
    ("empty_tail", lambda: compare_outputs(literal_list([]), [], [])),
    ("duplicates_after_first_limit", lambda: compare_outputs(
        literal_list(tokens100 + ["repeat"] * 70), tokens100[:64], ["repeat"] * 64)),
    ("duplicate_occurrences_keep_order", lambda: compare_outputs(
        literal_list(tokens100 + ["token_0", "token_99", "token_0"]),
        tokens100[:64], tokens100[39:] + ["token_0", "token_99", "token_0"])),
    ("repeated_token_counts_as_occurrences", lambda: compare_outputs(
        literal_list(["same"] * 100), ["same"], ["same"] * 64)),
    ("deflated_tail_same_outputs", lambda: compare_outputs(
        literal_list(tokens100), tokens100[:64], tokens100[36:], zipfile.ZIP_DEFLATED)),
]

limit96 = "_" + "a" * 95
invalid97 = "_" + "a" * 96
mixed_tokens = ["good", "", "two words", "123", ".", "line\nbreak", limit96,
                invalid97, "name[0]", "bad:thing", "good", "nonascii_\u00e9"]
cases.append(("same_regex_and_96_character_bound", lambda: compare_outputs(
    literal_list(mixed_tokens), ["good", limit96, "name[0]"], ["good", limit96, "name[0]", "good"])))
cases.append(("non_string_opcode_arguments_ignored", lambda: compare_outputs(
    b"\x80\x02](" + literal_string("good") + b"K*e.", ["good"], ["good"])))


def global_counts_unchanged():
    result = compare_outputs(b"\x80\x02cexample.module\nModel\n)R}b.", [], [])
    assert result["pickle"]["execution_related_opcode_counts"] == {"BUILD": 1, "GLOBAL": 1, "REDUCE": 1}
    assert result["pickle"]["global_literals"][0]["literal"] == "example.module Model"


def stack_global_tokens_unresolved():
    result = compare_outputs(b"\x80\x04" + literal_string("example.module") + literal_string("Model") + b"\x93.",
                             ["example.module", "Model"], ["example.module", "Model"])
    assert result["pickle"]["execution_related_opcode_counts"] == {"STACK_GLOBAL": 1}
    assert not result["pickle"]["stack_globals_resolved"]


cases.append(("global_opcode_and_literal_outputs_unchanged", global_counts_unchanged))
cases.append(("stack_global_tokens_are_not_resolved", stack_global_tokens_unresolved))
cases.append(("trailing_pickle_refusal_unchanged", lambda: compare_refusal(archive_bytes(literal_list(tokens100) + b"extra"))))
cases.append(("malformed_opcode_refusal_unchanged", lambda: compare_refusal(archive_bytes(b"\x80\x02\xff."))))
cases.append(("unsupported_protocol_refusal_unchanged", lambda: compare_refusal(archive_bytes(b"\x80\x06."))))
cases.append(("missing_pickle_refusal_unchanged", lambda: compare_refusal(archive_bytes(b"opaque", name="archive/storage"))))


def exact_reporting_ast_delta():
    expected = before_bytes.decode("utf-8")
    replacements = (
        ("    samples = []\n", "    samples = []\n    tail_samples = []\n"),
        ("        elif opcode.name in STRING_OPS and isinstance(argument, str) and len(samples) < 64:\n"
         "            if IDENTIFIER.fullmatch(argument) and argument not in samples:\n"
         "                samples.append(argument)\n",
         "        elif opcode.name in STRING_OPS and isinstance(argument, str):\n"
         "            if IDENTIFIER.fullmatch(argument):\n"
         "                if len(samples) < 64 and argument not in samples:\n"
         "                    samples.append(argument)\n"
         "                if len(tail_samples) == 64:\n"
         "                    del tail_samples[0]\n"
         "                tail_samples.append(argument)\n"),
        ('            "identifier_string_samples": samples, "string_sample_limit": 64,\n',
         '            "identifier_string_samples": samples, "string_sample_limit": 64,\n'
         '            "identifier_string_tail_samples": tail_samples, "string_tail_sample_limit": 64,\n'),
    )
    for before, after in replacements:
        assert expected.count(before) == 1
        expected = expected.replace(before, after, 1)
    assert ast.dump(ast.parse(expected), include_attributes=False) == ast.dump(ast.parse(after_bytes), include_attributes=False), (
        "Reader changed outside the exact two-field tail reporting addition")


cases.append(("exact_ast_delta_preserves_reads_bounds_hash_and_model_behavior", exact_reporting_ast_delta))
started = time.monotonic()
results = []
for name, operation in cases:
    try:
        operation()
        results.append({"case": name, "status": "passed"})
    except Exception as exc:
        results.append({"case": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:240]})
failed = sum(result["status"] == "failed" for result in results)
print(json.dumps({"label": sys.argv[1], "before_reader_sha256": hashlib.sha256(before_bytes).hexdigest(),
                  "reader_sha256": hashlib.sha256(after_bytes).hexdigest(), "isolated": bool(sys.flags.isolated),
                  "no_site": bool(sys.flags.no_site), "dont_write_bytecode": bool(sys.flags.dont_write_bytecode),
                  "actual_checkpoint_opened": False, "reader_main_called": False, "reader_inspect_called": False,
                  "passed": len(results) - failed, "failed": failed,
                  "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results}, indent=2))
raise SystemExit(1 if failed else 0)
