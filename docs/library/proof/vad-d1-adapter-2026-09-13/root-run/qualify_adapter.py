"""D1 generated-archive qualification only; no real artifact or profile access."""
import ast
import dataclasses
import encodings.cp437
import encodings.utf_8_sig
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
import types
import typing
import zipfile
import zlib

HERE = Path(__file__).parent
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
INPUTS = ("inspect_adapter.py", "fixed_converter.py", "zip_bounds.py", "buffer_basis.py",
          "synthetic_zip.py", "known-inventory.json", "reviewed_converter_harness.txt", "qualify_adapter.py")
READS = {os.path.normcase(str(HERE / name)) for name in INPUTS}
MODULES = ("zip_bounds", "fixed_converter", "buffer_basis", "synthetic_zip", "inspect_adapter")
IMPORTS = set(sys.modules) | set(MODULES)
events = []


def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if (not isinstance(path, (str, bytes, os.PathLike))
                or os.path.normcase(os.path.abspath(os.fsdecode(path))) not in READS
                or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            events.append("open")
            raise AssertionError("Unapproved file access")
    elif event == "import" and args[0] not in IMPORTS:
        events.append("import")
        raise AssertionError("Unapproved import")
    elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in {"os.system", "os.startfile", "os.spawn", "os.fork", "os.exec"}:
        events.append(event)
        raise AssertionError("Unapproved native/network operation")


sys.addaudithook(audit)
raw_inputs = {name: (HERE / name).read_bytes() for name in INPUTS}
hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in raw_inputs.items()}
for name in MODULES:
    module = types.ModuleType(name)
    module.__file__ = str(HERE / (name + ".py"))
    sys.modules[name] = module
    exec(compile(raw_inputs[name + ".py"], module.__file__, "exec"), module.__dict__)
adapter, archive, basis, builder = (sys.modules[name] for name in ("inspect_adapter", "fixed_converter", "buffer_basis", "synthetic_zip"))
forbidden_calls = []


def forbidden_conversion(*args, **kwargs):
    forbidden_calls.append("conversion or other-storage scalar scan")
    raise AssertionError("D1 reached forbidden conversion path")


for name in ("convert_bytes", "convert_reviewed_real_file", "load_fixed_plan", "reject_nonfinite", "encode_safetensors"):
    setattr(archive, name, forbidden_conversion)


def generated_payloads(endian="<"):
    window = b"".join(struct.pack(endian + "f", 0.54 - 0.46 * math.cos(2 * math.pi * i / 250)) for i in range(125))
    time_vector = b"".join(struct.pack(endian + "f", 2 * math.pi * k / 16000) for k in range(-125, 0))
    contents = {"archive/data/" + str(i): struct.pack("<I", 0x7FC00001) for i in range(129)}
    contents.update({"archive/data.pkl": b"\x80\x02cos\nsystem\nU\x0bnever-run!!\x85R.",
                     "archive/version": b"3\n", "archive/data/4": window, "archive/data/5": time_vector})
    return [(name, contents[name]) for name in adapter.EXPECTED_NAMES]


PAYLOADS = generated_payloads()
BASE, POS = builder.make_zip(PAYLOADS)
PAYLOAD_MAP = dict(PAYLOADS)
BASE_MEMBERS = tuple((name, len(payload), zlib.crc32(payload) & 0xFFFFFFFF) for name, payload in PAYLOADS)


def profile(raw, payloads=PAYLOADS, **changes):
    members = tuple(sorted((name, len(payload), zlib.crc32(payload) & 0xFFFFFFFF) for name, payload in payloads))
    item = adapter.InspectionProfile("synthetic", "generated-d1-v1", hashlib.sha256(raw).hexdigest(), len(raw), members)
    return dataclasses.replace(item, **changes)


def call(raw=BASE, payloads=PAYLOADS, selected_profile=None):
    encoded, exit_code = adapter.inspect_snapshot(raw, selected_profile if selected_profile is not None else profile(raw, payloads))
    assert len(encoded) <= adapter.MAX_RECEIPT
    return json.loads(encoded), exit_code, encoded


def accepted(raw=BASE, payloads=PAYLOADS, orientation="little"):
    result, code, encoded = call(raw, payloads)
    assert code == 0 and result["status"] == "static_inspection_complete_unqualified", result
    assert result["zip"] == {"members": 131, "all_member_crc_verified": True, "exact_inventory_verified": True}
    assert result["version_actual_hex"] == "330a" and result["interpreted_payload_bytes"] == 1002
    assert result["buffer_basis"]["orientation"] == orientation and result["buffer_basis"]["word_count"] == 250
    expected = dict(payloads)
    for member in result["selected_members"]:
        assert member["name"] in {"archive/data/4", "archive/data/5", "archive/version"}
        assert member["bytes"] == len(expected[member["name"]])
        assert member["sha256"] == hashlib.sha256(expected[member["name"]]).hexdigest()
    assert len(result["selected_members"]) == 3
    for field in ("model_or_tensor_constructed", "pickle_interpreted", "other_storage_values_interpreted", "conversion_performed", "conversion_profile_activated", "release_approved", "historical_writer_authenticated"):
        assert result[field] is False
    assert not forbidden_calls and not events
    return result


def refused(raw=BASE, payloads=PAYLOADS, selected_profile=None, reason=""):
    result, code, _ = call(raw, payloads, selected_profile)
    assert code == 2 and result["status"] == "refused", result
    assert reason in result.get("reason", ""), result
    assert result.get("conversion_profile_activated", False) is False
    return result


def alter_payload(name, replacement):
    return [(key, replacement if key == name else payload) for key, payload in PAYLOADS]


CASES = []


def case(name):
    def register(callback):
        CASES.append((name, callback))
        return callback
    return register


@case("all_131_members_only_1002_bytes_interpreted_little")
def full_little():
    accepted()


@case("big_endian_consistency_does_not_activate_conversion")
def full_big():
    payloads = generated_payloads(">")
    raw, _ = builder.make_zip(payloads)
    accepted(raw, payloads, "big")


@case("opaque_pickle_and_other_127_storages_not_evaluated")
def opaque():
    payloads = alter_payload("archive/data.pkl", b"__import__('os').system('must never execute'); not a pickle")
    raw, _ = builder.make_zip(payloads)
    result = accepted(raw, payloads)
    assert result["selected_members"] == accepted()["selected_members"]


for name, options in (("zip64_and_descriptor64", {"zip64_end": True, "local_zip64": True, "central_zip64": True, "flags": 8, "descriptor64": True}),
                      ("observed_writer_version_zero_shape", {"needed": 0, "flags": 2056}),
                      ("stored_alignment_padding", {"padding": b"ZZZZZZZZ"})):
    def supported(options=options):
        raw, _ = builder.make_zip(PAYLOADS, **options)
        accepted(raw)
    case(name)(supported)


@case("known_inventory_canonical_hash_and_selected_lengths")
def known_inventory():
    raw = raw_inputs["known-inventory.json"]
    inventory = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == adapter.KNOWN_INVENTORY_SHA256
    assert json.dumps(inventory, ensure_ascii=True, separators=(",", ":")).encode("ascii") == raw
    assert tuple(row[0] for row in inventory) == adapter.EXPECTED_NAMES
    sizes = {row[0]: row[1] for row in inventory}
    assert [sizes[name] for name, _ in adapter.SELECTED] == [500, 500, 2]


@case("digest_gate_before_zip_or_comparator")
def digest_first():
    old = archive.inspect_stored_zip
    calls = []
    def trap(*args):
        calls.append(True)
        raise AssertionError("Parser called before digest")
    archive.inspect_stored_zip = trap
    try:
        result = refused(selected_profile=profile(BASE, archive_sha256="1" * 64), reason="SHA256 differs")
        assert not calls and "input" not in result
    finally:
        archive.inspect_stored_zip = old


@case("real_wrapper_refuses_before_any_path_call")
def real_closed():
    old = archive.contained_unlinked
    calls = []
    def trap(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Real path reached")
    archive.contained_unlinked = trap
    try:
        assert adapter.D1_OWNER_APPROVAL is None and archive.REAL_PROFILE is None
        try:
            adapter.inspect_reviewed_real_file("not-created.json")
        except archive.Refusal as error:
            assert "awaits owner approval" in str(error)
        else:
            raise AssertionError("Real wrapper did not refuse")
        assert not calls
    finally:
        archive.contained_unlinked = old


for name, changes, reason in (
    ("original_digest_cannot_be_synthetic", {"archive_sha256": adapter.ORIGINAL_SHA256}, "cannot authorize original"),
    ("real_purpose_unapproved", {"purpose": "real"}, "owner approval is absent"),
    ("unknown_purpose", {"purpose": "anything"}, "owner approval is absent"),
    ("wrong_size", {"archive_size": len(BASE) + 1}, "snapshot size differs"),
    ("bool_size", {"archive_size": True}, "size bound"),
    ("size_over_bound", {"archive_size": adapter.MAX_INPUT + 1}, "size bound"),
    ("invalid_digest", {"archive_sha256": "bad"}, "digest refused"),
    ("invalid_profile_name", {"profile_id": "../bad"}, "field refused"),
    ("missing_inventory_member", {"members": BASE_MEMBERS[:-1]}, "131-member"),
    ("unordered_inventory", {"members": BASE_MEMBERS[::-1]}, "exact ordered inventory"),
    ("mutable_inventory", {"members": list(BASE_MEMBERS)}, "131-member"),
):
    def invalid_profile(changes=changes, reason=reason):
        refused(selected_profile=profile(BASE, **changes), reason=reason)
    case(name)(invalid_profile)


for label, name, field, new_value, reason in (
    ("selected_declared_short", "archive/data/4", 1, 499, "500/500/2"),
    ("version_declared_long", "archive/version", 1, 3, "500/500/2"),
    ("bool_inventory_size", "archive/data/0", 1, True, "size/CRC type"),
    ("negative_inventory_size", "archive/data/0", 1, -1, "size/CRC type"),
    ("crc_over_bound", "archive/data/0", 2, 0x100000000, "size/CRC type"),
    ("wrong_declared_other_size", "archive/data/0", 1, 5, "differs from exact inventory"),
    ("wrong_declared_crc", "archive/data/0", 2, 0, "differs from exact inventory"),
    ("unsafe_inventory_name", "archive/data/0", 0, "archive/../data/0", "name refused"),
):
    def member_profile(name=name, field=field, new_value=new_value, reason=reason):
        rows = [list(row) for row in BASE_MEMBERS]
        index = next(i for i, row in enumerate(rows) if row[0] == name)
        rows[index][field] = new_value
        refused(selected_profile=profile(BASE, members=tuple(tuple(row) for row in rows)), reason=reason)
    case(label)(member_profile)


@case("mutable_input_refused")
def mutable_input():
    refused(bytearray(BASE), selected_profile=profile(BASE), reason="immutable snapshot")


@case("version_mismatch_before_comparator_no_false_observation")
def wrong_version():
    payloads = alter_payload("archive/version", b"4\n")
    raw, _ = builder.make_zip(payloads)
    old, calls = basis.compare_buffers, []
    def trap(*args):
        calls.append(True)
        raise AssertionError("Comparator ran after rejected version")
    basis.compare_buffers = trap
    try:
        result = refused(raw, payloads, reason="Archive version bytes differ")
        assert not calls and "version_actual_hex" not in result and "selected_members" not in result
        assert result["version_expected_is_source_prediction"] is True
    finally:
        basis.compare_buffers = old


@case("actual_selected_member_length_differs_from_inventory")
def actual_short():
    payloads = alter_payload("archive/data/4", PAYLOAD_MAP["archive/data/4"][:-1])
    raw, _ = builder.make_zip(payloads)
    refused(raw, payloads, selected_profile=profile(raw), reason="differs from exact inventory")


for label, name, payload in (
    ("window_nan", "archive/data/4", struct.pack("<I", 0x7FC00001) + PAYLOAD_MAP["archive/data/4"][4:]),
    ("n_infinity", "archive/data/5", struct.pack("<I", 0xFF800000) + PAYLOAD_MAP["archive/data/5"][4:]),
    ("wrong_window_order", "archive/data/4", b"".join(PAYLOAD_MAP["archive/data/4"][i:i+4] for i in range(496, -1, -4))),
    ("opposite_buffer_orientations", "archive/data/5", dict(generated_payloads(">"))["archive/data/5"]),
):
    def bad_buffer(name=name, payload=payload):
        payloads = alter_payload(name, payload)
        raw, _ = builder.make_zip(payloads)
        result = refused(raw, payloads, reason="Neither or both")
        assert len(result["selected_members"]) == 3 and result["version_actual_hex"] == "330a"
        assert "buffer_basis" not in result
    case(label)(bad_buffer)


for name in ("archive/data/4", "archive/data/128", "archive/data.pkl"):
    def wrong_crc(name=name):
        raw = bytearray(BASE)
        position = next(entry for entry in POS["entries"] if entry["name"] == name)
        raw[position["data"]] ^= 1
        refused(bytes(raw), reason="payload CRC mismatch")
    case("opaque_or_selected_crc_" + name.replace("/", "_"))(wrong_crc)


@case("missing_archive_member")
def missing_member():
    raw, _ = builder.make_zip(PAYLOADS[:-1])
    refused(raw, reason="pinned member inventory")


@case("extra_archive_member")
def extra_member():
    raw, _ = builder.make_zip(PAYLOADS + [("archive/data/129", b"x")])
    refused(raw, reason="pinned member inventory")


@case("duplicate_archive_member")
def duplicate_member():
    raw, _ = builder.make_zip([PAYLOADS[0], PAYLOADS[0], *PAYLOADS[2:]])
    refused(raw, reason="name/path or duplicate")


@case("escaping_archive_member")
def escaping_member():
    raw, _ = builder.make_zip([("../data.pkl", PAYLOADS[0][1]), *PAYLOADS[1:]])
    refused(raw, reason="name/path or duplicate")


for label, delta, fmt, value, reason in (
    ("unsupported_compression", 10, "<H", 8, "stored ZIP"),
    ("encrypted_flag", 8, "<H", 1, "flags refused"),
    ("unsupported_needed_version", 6, "<H", 46, "Unsupported or split"),
    ("bad_local_pointer", 42, "<I", len(BASE), "local extent bound"),
):
    def bad_header(delta=delta, fmt=fmt, value=value, reason=reason):
        raw = bytearray(BASE)
        struct.pack_into(fmt, raw, POS["entries"][0]["central"] + delta, value)
        refused(bytes(raw), reason=reason)
    case(label)(bad_header)


@case("overlapping_payload_with_recomputed_crc")
def overlap():
    raw = bytearray(BASE)
    first, second = POS["entries"][:2]
    length = second["data_end"] - first["data"]
    crc = zlib.crc32(memoryview(raw)[first["data"]:first["data"] + length]) & 0xFFFFFFFF
    struct.pack_into("<III", raw, first["local"] + 14, crc, length, length)
    struct.pack_into("<III", raw, first["central"] + 16, crc, length, length)
    refused(bytes(raw), reason="Overlapping ZIP member extents")


@case("unreferenced_zip_gap")
def gap():
    raw, _ = builder.make_zip(PAYLOADS, gap_after_first=b"gap")
    refused(raw, reason="Unreferenced ZIP gap")


@case("output_cap_discards_all_partial_facts")
def receipt_cap():
    old = basis.compare_buffers
    def oversized(*args):
        result = old(*args)
        result["inert_test_padding"] = "x" * (adapter.MAX_RECEIPT + 1)
        return result
    basis.compare_buffers = oversized
    try:
        result = refused(reason="receipt limit or deadline")
        assert "buffer_basis" not in result and "input" not in result
    finally:
        basis.compare_buffers = old


@case("deadline_after_comparison_refuses")
def comparison_deadline():
    old_compare, old_clock = basis.compare_buffers, archive.clock_check
    late = [False]
    def compared(*args):
        result = old_compare(*args)
        late[0] = True
        return result
    def clock(started):
        if late[0]:
            raise archive.Refusal("Conversion time bound exceeded")
        old_clock(started)
    basis.compare_buffers, archive.clock_check = compared, clock
    try:
        result = refused(reason="receipt limit or deadline")
        assert "buffer_basis" not in result
    finally:
        basis.compare_buffers, archive.clock_check = old_compare, old_clock


@case("deadline_crossed_during_receipt_serialization_refuses")
def serialization_deadline():
    selected_profile = profile(BASE)
    old_dump, old_clock = adapter.json.dumps, archive.clock_check
    late = [False]
    def dumped(value, *args, **kwargs):
        result = old_dump(value, *args, **kwargs)
        if type(value) is dict and value.get("scope") == "D1 static version and two fixed buffers only":
            late[0] = True
        return result
    def clock(started):
        if late[0]:
            raise archive.Refusal("Conversion time bound exceeded")
        old_clock(started)
    adapter.json.dumps, archive.clock_check = dumped, clock
    try:
        result = refused(selected_profile=selected_profile, reason="receipt limit or deadline")
        assert "buffer_basis" not in result
    finally:
        adapter.json.dumps, archive.clock_check = old_dump, old_clock


@case("unexpected_parser_failure_is_error_exit1")
def unexpected():
    old = archive.inspect_stored_zip
    def error(*args):
        raise RuntimeError("untrusted values must not appear")
    archive.inspect_stored_zip = error
    try:
        result, code, encoded = call()
        assert code == 1 and result["status"] == "error" and result["error_class"] == "RuntimeError"
        assert b"untrusted values" not in encoded
    finally:
        archive.inspect_stored_zip = old


@case("exact_frozen_helpers_and_builder_ast")
def frozen_sources():
    assert hashes["fixed_converter.py"] == "b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b"
    assert hashes["zip_bounds.py"] == "bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6"
    assert hashes["buffer_basis.py"] == "bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373"
    assert hashes["reviewed_converter_harness.txt"] == "11f9addddf9b349c4ee249c000cc60c4986b989de2e11ec990ba940d6b7949a9"
    trees = [ast.parse(raw_inputs[name].decode("utf-8-sig")) for name in ("synthetic_zip.py", "reviewed_converter_harness.txt")]
    functions = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "make_zip") for tree in trees]
    assert ast.dump(functions[0], include_attributes=False) == ast.dump(functions[1], include_attributes=False)


@case("adapter_no_conversion_calls_and_real_guard_first")
def source_scope():
    tree = ast.parse(raw_inputs["inspect_adapter.py"])
    forbidden = {"convert_bytes", "convert_reviewed_real_file", "encode_safetensors", "load_fixed_plan", "reject_nonfinite", "loads", "load", "persistent_load", "find_class"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden for node in ast.walk(tree))
    assert not any(isinstance(node, (ast.Assign, ast.AnnAssign)) and any(isinstance(target, ast.Attribute) and target.attr == "REAL_PROFILE" for target in (node.targets if isinstance(node, ast.Assign) else [node.target])) for node in ast.walk(tree))
    wrapper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inspect_reviewed_real_file")
    assert isinstance(wrapper.body[1], ast.Expr) and isinstance(wrapper.body[1].value, ast.Call) and wrapper.body[1].value.func.id == "require"
    assert "awaits owner approval" in ast.dump(wrapper.body[1])
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "open" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "xb" for node in ast.walk(wrapper))
    assert adapter.D1_OWNER_APPROVAL is None and archive.REAL_PROFILE is None


started = time.monotonic()
results = []
for name, callback in CASES:
    try:
        callback()
        results.append({"case": name, "passed": True})
    except Exception as error:
        results.append({"case": name, "passed": False, "error": type(error).__name__ + ": " + str(error)[:300]})
assert len({result["case"] for result in results}) == len(results)
failed = sum(not result["passed"] for result in results)
report = {"scope": "D1 generated-archive inspection qualification only",
          "input_sha256": hashes, "startup_binding_asserted": True,
          "passed": len(results) - failed, "failed": failed, "qualification_exit": 1 if failed else 0,
          "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results,
          "unexpected_audit_events": events, "forbidden_conversion_calls": forbidden_calls,
          "actual_artifact_or_storage_read": False, "real_owner_profile_approved": False,
          "conversion_profile_activated": False}
assert not events and not forbidden_calls
encoded = json.dumps(report, indent=2)
assert len(encoded.encode("utf-8")) <= 32768
print(encoded)
raise SystemExit(report["qualification_exit"])
