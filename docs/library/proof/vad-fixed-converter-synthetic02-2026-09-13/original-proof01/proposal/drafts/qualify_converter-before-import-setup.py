"""Synthetic-only converter qualification; stdlib, fixed copied inputs, no artifact I/O."""
import ast
import copy
import dataclasses
import encodings.cp437
import hashlib
import importlib.util
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
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
INPUT_NAMES = ("fixed_converter.py", "zip_bounds.py", "fixed-plan.json", "reviewed_zip_reader.txt", "qualify_converter.py")
READS = {os.path.normcase(str(HERE / name)) for name in INPUT_NAMES}
allowed_imports = set(sys.modules) | {"zip_bounds", "fixed_converter"}
denied_events = []


def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if (not isinstance(path, (str, bytes, os.PathLike))
                or os.path.normcase(os.path.abspath(os.fsdecode(path))) not in READS
                or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            denied_events.append("open")
            raise AssertionError("Unapproved file access in synthetic qualification")
    elif event == "import" and args[0] not in allowed_imports:
        denied_events.append("import:" + str(args[0]))
        raise AssertionError("Unapproved import in synthetic qualification")
    elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in {"os.system", "os.startfile", "os.spawn", "os.fork", "os.exec"}:
        denied_events.append(event)
        raise AssertionError("Native/network operation in synthetic qualification")


sys.addaudithook(audit)
raw_inputs = {name: (HERE / name).read_bytes() for name in INPUT_NAMES}
input_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in raw_inputs.items()}
sys.path.insert(0, str(HERE))
import zip_bounds
import fixed_converter as converter

PLAN_BYTES = raw_inputs["fixed-plan.json"]
DOCUMENT = json.loads(PLAN_BYTES.decode("utf-8-sig"))
PLAN = converter.load_fixed_plan(PLAN_BYTES)
ROWS = DOCUMENT["rows"]
STORAGE_DOC = {record["key"]: record for record in DOCUMENT["storages"]}
EVIDENCE = hashlib.sha256(b"Synthetic fixtures deliberately packed as little-endian IEEE754 binary32; not real evidence").hexdigest()
VERSION = b"synthetic-v1\n"


def generated_payloads():
    stores = {key: bytearray(record["bytes"]) for key, record in STORAGE_DOC.items()}
    for index, row in enumerate(ROWS):
        start, count = row["offset_elements"] * 4, math.prod(row["shape"])
        marker = 0x3F000000 + index * 4096
        content = struct.pack("<I", marker) * count
        stores[row["storage_key"]][start:start + len(content)] = content
        struct.pack_into("<I", stores[row["storage_key"]], start + (count - 1) * 4, marker + 1)
    payloads = [("archive/data.pkl", b"\x80\x02cos\nsystem\nU\x0bnever-run!!\x85R."), ("archive/version", VERSION)]
    payloads += [("archive/data/" + key, bytes(stores[key])) for key in sorted(stores, key=int)]
    return payloads


PAYLOADS = generated_payloads()
PAYLOAD_MAP = dict(PAYLOADS)


def make_zip(payloads, *, flags=0, needed=20, descriptor64=False, descriptor_signature=True,
             zip64_end=False, local_zip64=False, central_zip64=False, padding=b"", gap_after_first=b""):
    body, central, positions = bytearray(), bytearray(), []
    for index, (name, payload) in enumerate(payloads):
        encoded = name.encode("utf-8")
        local = len(body)
        crc, length = zlib.crc32(payload) & 0xFFFFFFFF, len(payload)
        ver = 45 if local_zip64 or central_zip64 else needed
        extra = b""
        local_size = 0 if flags & 8 else length
        if local_zip64:
            extra += struct.pack("<HHQQ", 1, 16, local_size, local_size)
        if padding:
            extra += struct.pack("<HH", 0x4246, len(padding)) + padding
        body += struct.pack("<4s5H3I2H", b"PK\x03\x04", ver, flags, 0, 0, 0,
                            0 if flags & 8 else crc,
                            0xFFFFFFFF if local_zip64 else local_size,
                            0xFFFFFFFF if local_zip64 else local_size, len(encoded), len(extra))
        body += encoded + extra
        data_start = len(body)
        body += payload
        descriptor_start = len(body)
        if flags & 8:
            if descriptor_signature:
                body += b"PK\x07\x08"
            body += struct.pack("<IQQ" if descriptor64 else "<III", crc, length, length)
        if index == 0:
            body += gap_after_first
        central_extra = struct.pack("<HHQQQ", 1, 24, length, length, local) if central_zip64 else b""
        cstart = len(central)
        central += struct.pack("<4s6H3I5H2I", b"PK\x01\x02", ver, ver, flags, 0, 0, 0, crc,
                               0xFFFFFFFF if central_zip64 else length,
                               0xFFFFFFFF if central_zip64 else length,
                               len(encoded), len(central_extra), 0, 0, 0, 0,
                               0xFFFFFFFF if central_zip64 else local)
        central += encoded + central_extra
        positions.append({"name": name, "local": local, "data": data_start, "data_end": descriptor_start, "central_relative": cstart, "length": length})
    cd_offset, cd_size = len(body), len(central)
    body += central
    if zip64_end:
        record_offset = len(body)
        body += struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, len(payloads), len(payloads), cd_size, cd_offset)
        body += struct.pack("<4sLQL", b"PK\x06\x07", 0, record_offset, 1)
    body += struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0,
                        0xFFFF if zip64_end else len(payloads), 0xFFFF if zip64_end else len(payloads),
                        0xFFFFFFFF if zip64_end else cd_size, 0xFFFFFFFF if zip64_end else cd_offset, 0)
    for position in positions:
        position["central"] = cd_offset + position.pop("central_relative")
    return bytes(body), {"entries": positions, "cd_offset": cd_offset, "cd_size": cd_size}


BASE, POS = make_zip(PAYLOADS)
BASE_NAMES = tuple(name for name, _ in PAYLOADS)


def profile(raw, names=BASE_NAMES, **changes):
    item = converter.ProtocolProfile("synthetic", "generated-le-binary32-v1", hashlib.sha256(raw).hexdigest(), len(raw),
                                     "little", "IEEE754-binary32", VERSION, tuple(names), EVIDENCE)
    return dataclasses.replace(item, **changes)


def convert(raw=BASE, names=BASE_NAMES, **changes):
    return converter.convert_bytes(raw, profile(raw, names, **changes), PLAN_BYTES)


def refuse(call, contains):
    try:
        call()
    except converter.Refusal as exc:
        assert contains in str(exc), "Wrong refusal branch: " + str(exc)
    else:
        raise AssertionError("Expected refusal: " + contains)


CASES = []


def case(name):
    def register(fn):
        CASES.append((name, fn))
        return fn
    return register


def inspect_output(blob, payload_map=PAYLOAD_MAP):
    header_size = struct.unpack("<Q", blob[:8])[0]
    assert 0 < header_size <= 32768 and header_size % 8 == 0
    raw_header = blob[8:8 + header_size]
    assert raw_header.startswith(b"{")
    parsed = json.loads(raw_header.decode("utf-8"), object_pairs_hook=converter.strict_pairs)
    assert set(parsed) == {row["key"] for row in ROWS} and len(parsed) == 54
    cursor, shared = 0, 0
    for row in sorted(ROWS, key=lambda item: item["key"]):
        item = parsed[row["key"]]
        assert set(item) == {"dtype", "shape", "data_offsets"}
        assert item["dtype"] == "F32" and item["shape"] == row["shape"]
        count = math.prod(row["shape"]) * 4
        assert item["data_offsets"] == [cursor, cursor + count]
        start = row["offset_elements"] * 4
        expected = payload_map["archive/data/" + row["storage_key"]][start:start + count]
        actual = blob[8 + header_size + cursor:8 + header_size + cursor + count]
        assert actual == expected, "Wrong tensor range: " + row["key"]
        cursor += count
        shared += row["storage_key"] == "16"
    assert shared == 32 and cursor == 5891996 and len(blob) == 8 + header_size + cursor
    return parsed


@case("full_54_tensor_roundtrip_and_32_shared_views")
def full_roundtrip():
    blob, receipt = convert()
    inspect_output(blob)
    assert receipt["tensor_entries"] == 54 and receipt["selected_storages"] == 23
    assert receipt["output_sha256"] == hashlib.sha256(blob).hexdigest()
    assert receipt["status"] == "synthetic_conversion_complete" and not receipt["release_approved"]


@case("deterministic_header_and_data")
def deterministic():
    first, _ = convert()
    second, _ = convert()
    assert first == second


@case("finite_ieee_edge_bits_preserved")
def finite_edges():
    payloads = list(PAYLOADS)
    index = next(i for i, (name, _) in enumerate(payloads) if name == "archive/data/2")
    data = bytearray(payloads[index][1])
    patterns = (0, 0x80000000, 1, 0x80000001, 0x007FFFFF, 0x807FFFFF, 0x7F7FFFFF, 0xFF7FFFFF)
    for i, bits in enumerate(patterns):
        struct.pack_into("<I", data, i * 4, bits)
    payloads[index] = (payloads[index][0], bytes(data))
    raw, _ = make_zip(payloads)
    blob, _ = convert(raw)
    inspect_output(blob, dict(payloads))


@case("malicious_pickle_bytes_never_interpreted")
def inert_pickle():
    alternate = [("archive/data.pkl", b"not even a pickle; __import__('os').system('never')"), *PAYLOADS[1:]]
    raw, _ = make_zip(alternate)
    blob, receipt = convert(raw)
    baseline, _ = convert()
    assert blob == baseline and not receipt["pickle_interpreted"] and denied_events == []


@case("unselected_nonfinite_bytes_are_opaque_crc_only")
def omitted_storage():
    extra = PAYLOADS + [("archive/data/128", struct.pack("<II", 0x7FC00000, 0xFF800000))]
    raw, _ = make_zip(extra)
    blob, _ = convert(raw, tuple(name for name, _ in extra))
    inspect_output(blob)


for name, options in (
    ("signed_descriptor32", {"flags": 8}),
    ("unsigned_descriptor32", {"flags": 8, "descriptor_signature": False}),
    ("signed_descriptor64", {"flags": 8, "descriptor64": True}),
    ("unsigned_descriptor64", {"flags": 8, "descriptor64": True, "descriptor_signature": False}),
    ("zip64_end_record", {"zip64_end": True}),
    ("zip64_local_sizes", {"local_zip64": True}),
    ("zip64_central_sizes_offsets", {"central_zip64": True}),
    ("zip64_local_descriptor64", {"local_zip64": True, "flags": 8, "descriptor64": True, "zip64_end": True}),
    ("narrow_stored_version_zero", {"needed": 0, "flags": 0x808}),
    ("alignment_extra_Z_padding", {"padding": b"ZZZZZZZZ"}),
):
    def positive(options=options):
        raw, _ = make_zip(PAYLOADS, **options)
        blob, _ = convert(raw)
        inspect_output(blob)
    case(name)(positive)


@case("mutable_input_refused")
def mutable_input():
    refuse(lambda: converter.convert_bytes(bytearray(BASE), profile(BASE), PLAN_BYTES), "Immutable input")


@case("hash_mismatch_precedes_zip_parser")
def hash_before_zip():
    old = converter.inspect_stored_zip
    calls = []
    def forbidden(*args):
        calls.append(True)
        raise AssertionError("ZIP parser ran before digest gate")
    converter.inspect_stored_zip = forbidden
    try:
        refuse(lambda: converter.convert_bytes(BASE, profile(BASE, archive_sha256="1" * 64), PLAN_BYTES), "SHA256 mismatch")
        assert calls == []
    finally:
        converter.inspect_stored_zip = old


for name, change, reason in (
    ("profile_wrong_size", {"archive_size": len(BASE) + 1}, "size mismatch"),
    ("profile_big_endian_refused", {"source_byte_order": "big"}, "little-endian"),
    ("profile_unknown_encoding_refused", {"scalar_encoding": "native-float"}, "binary32"),
    ("profile_missing_version_refused", {"archive_version": b""}, "version bytes"),
    ("profile_wrong_version_refused", {"archive_version": b"3\n"}, "Archive version bytes differ"),
    ("profile_bad_evidence_digest", {"protocol_evidence_sha256": "missing"}, "digest field"),
    ("profile_real_unregistered_refused", {"purpose": "real"}, "Real protocol profile is not accepted"),
    ("synthetic_cannot_authorize_original_digest", {"archive_sha256": converter.ORIGINAL_SHA256}, "Synthetic profile cannot"),
    ("profile_escaping_name_refused", {"expected_member_names": ("../data.pkl",) + BASE_NAMES[1:]}, "member name"),
    ("profile_duplicate_name_refused", {"expected_member_names": (BASE_NAMES[1],) + BASE_NAMES[1:]}, "inventory ambiguous"),
):
    case(name)(lambda change=change, reason=reason: refuse(lambda: converter.convert_bytes(BASE, profile(BASE, **change), PLAN_BYTES), reason))


@case("real_file_guard_precedes_path_operations")
def real_guard():
    old = converter.contained_unlinked
    called = []
    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("Dormant real path helper invoked")
    converter.contained_unlinked = forbidden
    try:
        refuse(lambda: converter.convert_reviewed_real_file("never.safetensors", PLAN_BYTES), "profile remains unaccepted")
        assert called == []
    finally:
        converter.contained_unlinked = old


@case("fixed_plan_digest_rejects_changed_shape_or_key")
def plan_hash():
    changed = PLAN_BYTES.replace(b'"sincnet.wav_norm1d.weight"', b'"sincnet.wav_norm1d.WEIGHT"')
    assert changed != PLAN_BYTES
    refuse(lambda: converter.load_fixed_plan(changed), "plan SHA256")


for name, change, reason in (
    ("plan_duplicate_tensor_key", lambda d: d["rows"][1].update(key=d["rows"][0]["key"]), "plan key"),
    ("plan_bool_shape_refused", lambda d: d["rows"][0].update(shape=[True]), "Invalid integer"),
    ("plan_nonrowmajor_stride_refused", lambda d: d["rows"][6].update(stride=[1, 5, 400]), "row-major"),
    ("plan_negative_offset_refused", lambda d: d["rows"][0].update(offset_elements=-1), "Invalid integer"),
    ("plan_range_outside_storage_refused", lambda d: d["rows"][0].update(offset_elements=1), "outside storage"),
    ("plan_overlapping_shared_views_refused", lambda d: d["rows"][17].update(offset_elements=0), "overlap or leave gaps"),
    ("plan_unknown_storage_refused", lambda d: d["rows"][0].update(storage_key="999"), "storage reference"),
    ("plan_missing_buffer_entry_refused", lambda d: d["rows"].pop(4), "tensor count"),
    ("plan_storage_length_mismatch", lambda d: d["storages"][0].update(bytes=8), "byte length"),
):
    def plan_negative(change=change, reason=reason):
        draft = copy.deepcopy(DOCUMENT)
        change(draft)
        refuse(lambda: converter._validate_plan(draft), reason)
    case(name)(plan_negative)


def patch_archive(position, fmt, value, raw=BASE):
    changed = bytearray(raw)
    struct.pack_into(fmt, changed, position, value)
    return bytes(changed)


@case("selected_payload_crc_mismatch")
def selected_crc():
    location = POS["entries"][2]["data"]
    bad = patch_archive(location, "<B", BASE[location] ^ 1)
    refuse(lambda: convert(bad), "payload CRC mismatch")


@case("opaque_pickle_payload_crc_mismatch")
def opaque_crc():
    location = POS["entries"][0]["data"]
    bad = patch_archive(location, "<B", BASE[location] ^ 1)
    refuse(lambda: convert(bad), "payload CRC mismatch")


for name, field_offset, fmt, value, reason in (
    ("central_unsupported_compression", 10, "<H", 8, "Only stored"),
    ("central_encrypted_flag", 8, "<H", 1, "ZIP flags"),
    ("central_unsupported_version", 6, "<H", 99, "Unsupported or split"),
    ("central_huge_storage_size", 24, "<I", converter.MAX_MEMBER + 1, "storage length"),
    ("central_bad_local_offset", 42, "<I", POS["cd_offset"], "local extent"),
    ("central_symbolic_link_mode", 38, "<I", stat.S_IFLNK << 16, "non-regular"),
):
    case(name)(lambda field_offset=field_offset, fmt=fmt, value=value, reason=reason: refuse(lambda: convert(patch_archive(POS["entries"][0]["central"] + field_offset, fmt, value)), reason))


for name, field_offset, fmt, value, reason in (
    ("local_crc_mismatch", 14, "<I", 0, "CRC or sizes"),
    ("local_size_mismatch", 18, "<I", 1, "CRC or sizes"),
    ("local_version_mismatch", 4, "<H", 21, "versions disagree"),
    ("local_name_mismatch", 30 + 8, "<B", ord("z"), "names disagree"),
):
    case(name)(lambda field_offset=field_offset, fmt=fmt, value=value, reason=reason: refuse(lambda: convert(patch_archive(POS["entries"][0]["local"] + field_offset, fmt, value)), reason))


@case("overlapping_members_with_recomputed_crc_refused")
def overlap():
    raw = bytearray(BASE)
    entry = POS["entries"][0]
    length = entry["length"] + 1
    crc = zlib.crc32(memoryview(raw)[entry["data"]:entry["data"] + length]) & 0xFFFFFFFF
    for offset in (entry["local"] + 14, entry["central"] + 16):
        struct.pack_into("<III", raw, offset, crc, length, length)
    refuse(lambda: convert(bytes(raw)), "Overlapping ZIP member extents")


@case("duplicate_zip_member_refused")
def duplicate_member():
    raw, _ = make_zip(PAYLOADS + [PAYLOADS[-1]])
    refuse(lambda: convert(raw), "duplicate refused")


@case("unlisted_zip_member_refused")
def unlisted_member():
    raw, _ = make_zip(PAYLOADS + [("archive/data/129", b"opaque")])
    refuse(lambda: convert(raw), "pinned member inventory")


for name, bad_name in (("zip_escape_name", "../data.pkl"), ("zip_ads_name", "archive/data:evil"),
                       ("zip_backslash_name", "archive\\data.pkl"), ("zip_absolute_name", "/archive/data.pkl"),
                       ("zip_nul_name", "archive/data.pkl\0evil")):
    def bad_member(bad_name=bad_name):
        raw, _ = make_zip([(bad_name, PAYLOADS[0][1]), *PAYLOADS[1:]])
        refuse(lambda: convert(raw), "name/path")
    case(name)(bad_member)


@case("fixed_storage_length_refused_after_valid_crc")
def storage_length():
    changed = list(PAYLOADS)
    changed[2] = (changed[2][0], b"\0" * 8)
    raw, _ = make_zip(changed)
    refuse(lambda: convert(raw), "storage member byte length")


for name, bits in (("positive_infinity", 0x7F800000), ("negative_infinity", 0xFF800000),
                   ("quiet_nan", 0x7FC00000), ("signalling_nan", 0x7F800001)):
    def nonfinite(bits=bits):
        payloads = list(PAYLOADS)
        payloads[2] = (payloads[2][0], struct.pack("<I", bits))
        raw, _ = make_zip(payloads)
        refuse(lambda: convert(raw), "Nonfinite binary32")
    case(name)(nonfinite)


@case("descriptor_crc_mismatch")
def bad_descriptor():
    raw, positions = make_zip(PAYLOADS, flags=8)
    bad = patch_archive(positions["entries"][0]["data_end"] + 4, "<I", 0, raw)
    refuse(lambda: convert(bad), "descriptor disagrees")


@case("descriptor_extent_mismatch")
def descriptor_extent():
    raw, _ = make_zip(PAYLOADS, flags=8, gap_after_first=b"x")
    refuse(lambda: convert(raw), "descriptor extent")


@case("unreferenced_gap_refused")
def gap():
    raw, _ = make_zip(PAYLOADS, gap_after_first=b"x")
    refuse(lambda: convert(raw), "Unreferenced ZIP gap")


@case("nonZ_alignment_extra_refused")
def bad_padding():
    raw, _ = make_zip(PAYLOADS, padding=b"XXXX")
    refuse(lambda: convert(raw), "alignment padding")


@case("zip_trailing_bytes_refused")
def trailing():
    refuse(lambda: convert(BASE + b"trailing"), "Trailing or ambiguous")


@case("zip_member_count_bound_refused")
def count_bound():
    raw = bytearray(BASE)
    struct.pack_into("<HH", raw, len(raw) - 22 + 8, 257, 257)
    refuse(lambda: convert(bytes(raw)), "member count exceeds")


@case("zip_directory_byte_bound_refused")
def cd_bound():
    bad = patch_archive(len(BASE) - 22 + 12, "<I", 2 * 1024 * 1024 + 1)
    refuse(lambda: convert(bad), "central directory exceeds")


for name, variable, value, reason in (
    ("input_byte_limit", "MAX_INPUT", len(BASE) - 1, "integer bound"),
    ("output_header_limit", "MAX_HEADER", 1, "header or output byte bound"),
    ("output_total_limit", "MAX_OUTPUT", 5891995, "Output data bound"),
):
    def cap(variable=variable, value=value, reason=reason):
        old = getattr(converter, variable)
        setattr(converter, variable, value)
        try:
            refuse(lambda: convert(), reason)
        finally:
            setattr(converter, variable, old)
    case(name)(cap)


@case("deadline_after_output_hash_refuses_result")
def final_deadline():
    original_time, original_hash = converter.time.monotonic, converter.hashlib.sha256
    pinned = profile(BASE)
    elapsed, calls = [0.0], [0]
    def hashing(raw=b""):
        result = original_hash(raw)
        calls[0] += 1
        if calls[0] == 3:
            elapsed[0] = 31.0
        return result
    converter.time.monotonic = lambda: elapsed[0]
    converter.hashlib.sha256 = hashing
    try:
        refuse(lambda: converter.convert_bytes(BASE, pinned, PLAN_BYTES), "time bound")
        assert calls[0] == 3
    finally:
        converter.time.monotonic, converter.hashlib.sha256 = original_time, original_hash


def path_case(fault):
    root = converter.ROOT / "_scratch/proposal-owned"
    target = root / "new.safetensors"
    old = Path.lstat
    visited = []
    def synthetic_lstat(current):
        visited.append(str(current))
        if fault == "ancestor_reparse" and current == converter.ROOT / "_scratch":
            return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        if fault == "root_reparse" and current == root:
            return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        if fault == "leaf_symlink" and current == target:
            return types.SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        if fault == "ancestor_file" and current == root.parent:
            return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
        if fault == "missing_parent" and current == root:
            raise FileNotFoundError
        if current == target:
            raise FileNotFoundError
        return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0)
    Path.lstat = synthetic_lstat
    try:
        if fault == "valid":
            assert converter.contained_unlinked(target, root, must_exist=False) == target
            assert str(Path(target.anchor)) in visited
        else:
            message = "reparse" if fault in ("ancestor_reparse", "root_reparse", "leaf_symlink") else "Non-directory" if fault == "ancestor_file" else "parent missing"
            refuse(lambda: converter.contained_unlinked(target, root, must_exist=False), message)
    finally:
        Path.lstat = old


for fault in ("valid", "ancestor_reparse", "root_reparse", "leaf_symlink", "ancestor_file", "missing_parent"):
    case("inert_path_" + fault)(lambda fault=fault: path_case(fault))


@case("zip_boundary_functions_match_reviewed_source_ast")
def boundary_ast():
    before = ast.parse(raw_inputs["reviewed_zip_reader.txt"].decode("utf-8-sig"))
    after = ast.parse(raw_inputs["zip_bounds.py"].decode("utf-8-sig"))
    for name in ("read_exact", "directory_bounds"):
        left = next(node for node in before.body if isinstance(node, ast.FunctionDef) and node.name == name)
        right = next(node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


@case("converter_imports_and_real_profile_static_guard")
def source_guard():
    tree = ast.parse(raw_inputs["fixed_converter.py"].decode("utf-8-sig"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"exec", "eval", "compile", "__import__"}
    assert set(imports) <= {"dataclasses", "hashlib", "io", "json", "math", "os", "pathlib", "re", "stat", "struct", "time", "zlib", "zip_bounds"}
    assert converter.REAL_PROFILE is None


started = time.monotonic()
results = []
assert len({name for name, _ in CASES}) == len(CASES)
for name, fn in CASES:
    try:
        fn()
    except Exception as exc:
        results.append({"case": name, "passed": False, "error_type": type(exc).__name__, "error": str(exc)[:400]})
    else:
        results.append({"case": name, "passed": True})
assert denied_events == [], "Unexpected native, network or file operation was attempted"
after_hashes = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in INPUT_NAMES}
assert after_hashes == input_hashes
failed = sum(not item["passed"] for item in results)
report = {"scope": "generated synthetic archive conversion only; no real artifact or model execution", "passed": len(results) - failed,
          "failed": failed, "cases": results, "elapsed_seconds": round(time.monotonic() - started, 6),
          "startup_binding": True, "isolated_no_site_no_bytecode": True, "input_hashes": input_hashes,
          "input_hashes_unchanged": True, "unexpected_audit_events": denied_events,
          "original_artifact_read": False, "model_or_tensor_constructed": False, "real_profile_accepted": False,
          "qualification_exit": 1 if failed else 0}
encoded = json.dumps(report, indent=2)
assert len(encoded.encode()) <= 128 * 1024
print(encoded)
raise SystemExit(1 if failed else 0)
