"""Synthetic parser checks only. Never invokes reader.main or reader.inspect."""
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time
import warnings
import zipfile
import zlib


HERE = Path(__file__).absolute().parent
CHECKPOINT = os.path.normcase(os.path.abspath(
    HERE.parent.parent / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"))
READER = HERE / "read_checkpoint_inventory.py"
LITERAL = b"\x80\x02}q\x00."


def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.normcase(os.path.abspath(os.fsdecode(args[0]))) == CHECKPOINT:
            raise RuntimeError("The actual checkpoint is prohibited in this synthetic preflight")
    if event.startswith(("socket.", "subprocess.", "os.system", "ctypes.")):
        raise RuntimeError("Native/network/process actions are outside this preflight")


sys.addaudithook(audit)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
reader_bytes = READER.read_bytes()
spec = importlib.util.spec_from_file_location("static_inventory_proposal", READER)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def forbidden(*args, **kwargs):
    raise AssertionError("Reader input/main execution is forbidden in synthetic preflight")


reader.inspect = forbidden
reader.main = forbidden


def archive_bytes(entries, compression=zipfile.ZIP_STORED):
    target = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(target, "w", compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
    return target.getvalue()


def central_offsets(raw):
    eocd = raw.rfind(b"PK\x05\x06")
    count = struct.unpack_from("<H", raw, eocd + 10)[0]
    position = struct.unpack_from("<L", raw, eocd + 16)[0]
    offsets = []
    for _ in range(count):
        assert raw[position:position + 4] == b"PK\x01\x02"
        offsets.append(position)
        name, extra, comment = struct.unpack_from("<3H", raw, position + 28)
        position += 46 + name + extra + comment
    return offsets, eocd


def patch(raw, changes):
    changed = bytearray(raw)
    for offset, form, value in changes:
        struct.pack_into(form, changed, offset, value)
    return bytes(changed)


def field(raw, local_offset, central_offset, form, value):
    centers, _ = central_offsets(raw)
    local = struct.unpack_from("<L", raw, centers[0] + 42)[0]
    return patch(raw, [(local + local_offset, form, value), (centers[0] + central_offset, form, value)])


def inspect_memory(raw):
    stream = io.BytesIO(raw)
    started = time.monotonic()
    bounds = reader.directory_bounds(stream, len(raw))
    with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
        entries, total, member = reader.member_inventory(stream, archive, bounds, len(raw), started)
        inventory = reader.parse_pickle(archive, member, started)
    assert inventory["objects_constructed"] is False
    assert inventory["stack_globals_resolved"] is False
    return inventory


def oversized_pickle():
    class NoOpen:
        open = staticmethod(forbidden)
    member = zipfile.ZipInfo("data.pkl")
    member.file_size = reader.MAX_PICKLE + 1
    member.compress_size = 1
    return reader.parse_pickle(NoOpen(), member, time.monotonic())


def zipped64(raw):
    _, end = central_offsets(raw)
    values = struct.unpack_from("<4s4H2LH", raw, end)
    _, disk, cd_disk, disk_count, count, size, offset, comment = values
    record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, count, count, size, offset)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, end, 1)
    final = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return raw[:end] + record + locator + final


base = archive_bytes([("archive/data.pkl", LITERAL)])
centers, end = central_offsets(base)
cases = []


def add(name, raw, reason=None):
    cases.append((name, lambda raw=raw: inspect_memory(raw), reason))


def unsafe_archive(name):
    if "\\" not in name:
        return archive_bytes([(name, LITERAL)])
    raw = archive_bytes([(name.replace("\\", "/"), LITERAL)])
    centers, _ = central_offsets(raw)
    changed = bytearray(raw)
    encoded = name.encode("ascii")
    changed[30:30 + len(encoded)] = encoded
    changed[centers[0] + 46:centers[0] + 46 + len(encoded)] = encoded
    return bytes(changed)


add("valid_stored", base)
add("valid_deflated", archive_bytes([("archive/data.pkl", LITERAL)], zipfile.ZIP_DEFLATED))
add("valid_zip64_end_records", zipped64(base))
add("literal_global_is_reported_without_resolution", archive_bytes([("data.pkl", b"\x80\x02cexample.module\nModel\n.")]))
add("missing_pickle", archive_bytes([("archive/storage", b"opaque")]), "Exactly one")
add("ambiguous_pickle", archive_bytes([("one/data.pkl", LITERAL), ("two/data.pkl", LITERAL)]), "Exactly one")
add("additional_pickle_suffix", archive_bytes([("data.pkl", LITERAL), ("other.PICKLE", LITERAL)]), "Exactly one")
for name in ("../data.pkl", "/data.pkl", "x\\data.pkl", "x:foo/data.pkl", "x//data.pkl", "x/./data.pkl", "x/\x01data.pkl"):
    add("unsafe_name_" + repr(name), unsafe_archive(name), "ZIP name")
add("duplicate_names", archive_bytes([("data.pkl", LITERAL), ("data.pkl", LITERAL)]), "Duplicate")
symlink = zipfile.ZipInfo("data.pkl")
symlink.create_system = 3
symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
add("symlink_member", archive_bytes([(symlink, LITERAL)]), "symbolic-link")
add("encrypted_flag", field(base, 6, 8, "<H", 1), "Encrypted")
add("unsupported_flag", field(base, 6, 8, "<H", 16), "Unsupported ZIP member flags")
add("unsupported_compression", field(base, 8, 10, "<H", 12), "Unsupported ZIP compression")
add("oversized_directory", patch(base, [(end + 12, "<L", reader.MAX_CD + 1)]), "central directory exceeds")
add("oversized_member_count", patch(base, [(end + 8, "<H", 257), (end + 10, "<H", 257)]), "member count exceeds")
add("oversized_advertised_member", field(base, 22, 24, "<L", reader.MAX_MEMBER + 1), "member exceeds size")
cases.append(("oversized_pickle_refused_before_open", oversized_pickle, "Pickle member exceeds"))
add("local_central_name_mismatch", base[:30] + b"X" + base[31:], "names disagree")
add("local_central_crc_mismatch", patch(base, [(14, "<L", 1)]), "CRC fields disagree")
add("central_directory_offset_conflict", patch(base, [(end + 16, "<L", 1)]), "extent is inconsistent")
add("split_archive", patch(base, [(end + 4, "<H", 1)]), "Split ZIP")
add("pickle_trailing_bytes", archive_bytes([("data.pkl", LITERAL + b"more")]), "trailing data")
add("pickle_truncated", archive_bytes([("data.pkl", LITERAL[:-1])]), "exhausted before seeing STOP")
add("unsupported_pickle_protocol", archive_bytes([("data.pkl", b"\x80\x06.")]), "Unsupported pickle protocol")
add("non_zip_file", b"not a ZIP file at all" * 4, "ZIP end record")

# The second local record lives inside the first member's payload. Both local
# names and sizes agree with the central directory, so overlap is the boundary.
nested_end = struct.unpack_from("<L", base, end + 16)[0]
nested = base[:nested_end]
overlapping = archive_bytes([("outer.bin", nested), ("archive/data.pkl", LITERAL)])
over_centers, _ = central_offsets(overlapping)
nested_offset = 30 + len("outer.bin")
overlapping = patch(overlapping, [(over_centers[1] + 42, "<L", nested_offset)])
add("overlapping_local_members", overlapping, "Overlapping ZIP member extents")

# A declared pickle length must not hide a longer deflate stream. This remains
# a tiny synthetic payload and is never deserialized.
underreported = archive_bytes([("data.pkl", LITERAL + b"A" * 2048)], zipfile.ZIP_DEFLATED)
underreported = field(underreported, 22, 24, "<L", len(LITERAL))
underreported = field(underreported, 14, 16, "<L", zlib.crc32(LITERAL))
add("underreported_deflate_payload", underreported, "size")

hidden_entries = archive_bytes([("entry" + str(i), b"") for i in range(257)])
_, hidden_end = central_offsets(hidden_entries)
hidden_entries = patch(hidden_entries, [(hidden_end + 8, "<H", 1), (hidden_end + 10, "<H", 1)])
cases.append(("actual_directory_count_checked_before_ZipFile",
              lambda: reader.directory_bounds(io.BytesIO(hidden_entries), len(hidden_entries)), "entry count"))
add("underreported_stored_payload", field(base, 22, 24, "<L", len(LITERAL) - 1), "size")
add("pickle_crc_payload_mismatch", field(base, 14, 16, "<L", 1), "payload CRC")


def assert_numeric_refusal(raw, expected, reason):
    try:
        reader.directory_bounds(io.BytesIO(raw), len(raw))
    except reader.Refusal as exc:
        assert str(exc) == reason, (str(exc), reason)
        assert exc.directory_entry == expected, (exc.directory_entry, expected)
        assert len(exc.directory_entry) == 14
        assert all(type(value) is int for value in exc.directory_entry.values())
        assert len(json.dumps(exc.directory_entry).encode("utf-8")) < 1024
        return
    raise AssertionError("Reporting context must not permit the refused entry")


expected_header = {
    "ordinal": 1, "central_header_offset": centers[0], "needed_version": 20,
    "made_version": struct.unpack_from("<H", base, centers[0] + 4)[0],
    "disk": 0, "compression_method": 0, "flags": 0,
    "crc32_u32": zlib.crc32(LITERAL), "compressed_bytes_u32": len(LITERAL),
    "uncompressed_bytes_u32": len(LITERAL), "name_bytes": len("archive/data.pkl"),
    "extra_bytes": 0, "comment_bytes": 0, "local_header_offset_u32": 0,
}
for needed in (0, 9, 46):
    changed = patch(base, [(centers[0] + 6, "<H", needed)])
    expected = dict(expected_header, needed_version=needed)
    cases.append(("numeric_refusal_needed_" + str(needed),
                  lambda raw=changed, expected=expected: assert_numeric_refusal(
                      raw, expected, "Unsupported or split ZIP directory entry"), None))
changed = patch(base, [(centers[0] + 34, "<H", 1)])
cases.append(("numeric_refusal_split_disk", lambda: assert_numeric_refusal(
    changed, dict(expected_header, disk=1), "Unsupported or split ZIP directory entry"), None))
large_name = patch(base, [(centers[0] + 28, "<H", 257)])
cases.append(("numeric_refusal_metadata_bound", lambda: assert_numeric_refusal(
    large_name, dict(expected_header, name_bytes=257), "ZIP central-directory member metadata exceeds limit"), None))
long_name = patch(base, [(centers[0] + 28, "<H", 256)])
cases.append(("numeric_refusal_entry_extent", lambda: assert_numeric_refusal(
    long_name, dict(expected_header, name_bytes=256), "ZIP central-directory entry extends outside directory"), None))

# COMPATIBILITY SCOPE: retain the 42 behavior/reporting cases above unchanged.
retained_behavior_count = len(cases)
EXPECTED_DIGEST = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"


def legacy_stored_container(raw):
    offsets, final_offset = central_offsets(raw)
    assert len(offsets) == 1
    central = offsets[0]
    value = bytearray(raw)
    struct.pack_into("<H", value, 4, 0)
    struct.pack_into("<H", value, 6, 2056)
    for offset in (14, 18, 22):
        struct.pack_into("<L", value, offset, 0)
    struct.pack_into("<H", value, central + 4, 0)
    struct.pack_into("<H", value, central + 6, 0)
    struct.pack_into("<H", value, central + 8, 2056)
    checksum, packed, unpacked = struct.unpack_from("<3L", value, central + 16)
    descriptor = struct.pack("<4L", 0x08074B50, checksum, packed, unpacked)
    value = value[:central] + descriptor + value[central:]
    struct.pack_into("<L", value, final_offset + len(descriptor) + 16, central + len(descriptor))
    return bytes(value)


legacy = legacy_stored_container(base)
legacy_centers, _ = central_offsets(legacy)
add("compat_exact_stored_version_zero", legacy)
for compat_version in range(1, 10):
    add("compat_other_low_version_" + str(compat_version),
        field(legacy, 4, 6, "<H", compat_version), "Unsupported or split ZIP directory entry")
for compat_version in (46, 65535):
    add("compat_high_version_" + str(compat_version),
        field(legacy, 4, 6, "<H", compat_version), "Unsupported or split ZIP directory entry")
for compat_made in (1, 20, 256, 65535):
    add("compat_changed_made_" + str(compat_made),
        patch(legacy, [(legacy_centers[0] + 4, "<H", compat_made)]), "Unsupported or split ZIP directory entry")
for compat_disk in (1, 65535):
    add("compat_changed_disk_" + str(compat_disk),
        patch(legacy, [(legacy_centers[0] + 34, "<H", compat_disk)]), "Unsupported or split ZIP directory entry")
for compat_method in (8, 12, 99):
    add("compat_nonstored_method_" + str(compat_method),
        field(legacy, 8, 10, "<H", compat_method), "Unsupported or split ZIP directory entry")
for compat_flags in (0, 8, 2048, 2057, 2058, 2060, 2120, 10248, 65535):
    add("compat_changed_flags_" + str(compat_flags),
        field(legacy, 6, 8, "<H", compat_flags), "Unsupported or split ZIP directory entry")
add("compat_crc_rule_retained", patch(legacy, [(legacy_centers[0] + 16, "<L", 1)]), "payload CRC")
add("compat_member_size_rule_retained", patch(legacy, [(legacy_centers[0] + 24, "<L", reader.MAX_MEMBER + 1)]),
    "ZIP member exceeds size bound")
add("compat_name_rule_retained", legacy_stored_container(archive_bytes([("../data.pkl", LITERAL)])), "ZIP name")
add("compat_pickle_stop_rule_retained", legacy_stored_container(archive_bytes([("data.pkl", LITERAL + b"suffix")])),
    "trailing data")
add("compat_stored_size_rule_retained", patch(legacy, [(legacy_centers[0] + 24, "<L", len(LITERAL) - 1)]), "size")
cases.append(("exact_digest_gate_accepts_recorded_digest", lambda: reader.require_expected_digest(EXPECTED_DIGEST), None))
for digest_number, bad_digest in enumerate(("0" * 64, EXPECTED_DIGEST.upper(), EXPECTED_DIGEST[:-1],
                                          EXPECTED_DIGEST + "0", "", None, b"", 0, EXPECTED_DIGEST + " "), 1):
    cases.append(("immutable_digest_gate_refuses_" + str(digest_number),
                  lambda digest=bad_digest: reader.require_expected_digest(digest), "immutable expected digest"))


def static_retained_behavior_source():
    previous = (HERE / "preserved-reporting-seal/qualify_parser.py").read_text(encoding="utf-8")
    current = Path(__file__).read_text(encoding="utf-8")
    assert previous.split("baseline_ast =", 1)[0] == current.split("# COMPATIBILITY SCOPE:", 1)[0]
    assert retained_behavior_count == 42
    assert previous[previous.index("started = time.monotonic()\nresults = []"):] == current[current.index(
        "started = time.monotonic()\nresults = []"):]


def static_exact_authorized_reader_delta():
    before = (HERE / "preserved-reporting-seal/read_checkpoint_inventory.py").read_text(encoding="utf-8")
    substitutions = (
        ('INPUT = ROOT / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"\n',
         'INPUT = ROOT / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"\n'
         'EXPECTED_ARTIFACT_SHA256 = "' + EXPECTED_DIGEST + '"\n'),
        ('def clock_check(started):',
         'def require_expected_digest(observed_digest):\n'
         '    require(observed_digest == EXPECTED_ARTIFACT_SHA256,\n'
         '            "Allowlisted artifact SHA256 differs from immutable expected digest")\n\n\n'
         'def clock_check(started):'),
        ('        require(10 <= needed <= 45 and member_disk == 0, "Unsupported or split ZIP directory entry",\n',
         '        stored_version_zero = (needed == 0 and entry["made_version"] == 0 and member_disk == 0\n'
         '                               and method == zipfile.ZIP_STORED and flags == 2056)\n'
         '        require((10 <= needed <= 45 or stored_version_zero) and member_disk == 0,\n'
         '                "Unsupported or split ZIP directory entry",\n'),
        ('        bounds = directory_bounds(stream, total)\n',
         '        require_expected_digest(result["artifact"]["sha256"])\n'
         '        bounds = directory_bounds(stream, total)\n'),
    )
    expected = before
    for old, new in substitutions:
        assert expected.count(old) == 1, "Authorized delta anchor is ambiguous"
        expected = expected.replace(old, new, 1)
    assert ast.dump(ast.parse(expected), include_attributes=False) == ast.dump(ast.parse(reader_bytes), include_attributes=False), (
        "Reader changes exceed the exact hash gate and stored version-zero exception")


cases.append(("static_original_42_behavior_assertions_unchanged", static_retained_behavior_source, None))
cases.append(("static_exact_authorized_version_and_digest_delta", static_exact_authorized_reader_delta, None))

started = time.monotonic()
results = []
for name, operation, expected_refusal in cases:
    try:
        value = operation()
        if expected_refusal is not None:
            raise AssertionError("Expected a refusal containing " + repr(expected_refusal))
        if name == "literal_global_is_reported_without_resolution":
            assert value["global_literals"][0]["literal"] == "example.module Model"
            assert value["execution_related_opcode_counts"]["GLOBAL"] == 1
        results.append({"case": name, "status": "passed"})
    except (reader.Refusal, zipfile.BadZipFile, zlib.error, ValueError, UnicodeError, struct.error) as exc:
        if expected_refusal is not None and expected_refusal in str(exc):
            results.append({"case": name, "status": "passed", "refusal": str(exc)[:180]})
        else:
            results.append({"case": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:180]})
    except Exception as exc:
        results.append({"case": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:180]})
failed = sum(item["status"] == "failed" for item in results)
print(json.dumps({"label": sys.argv[1], "reader_sha256": hashlib.sha256(reader_bytes).hexdigest(),
                  "isolated": bool(sys.flags.isolated), "no_site": bool(sys.flags.no_site),
                  "dont_write_bytecode": bool(sys.flags.dont_write_bytecode),
                  "actual_checkpoint_opened": False, "reader_main_called": False,
                  "passed": len(results) - failed, "failed": failed,
                  "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results}, indent=2))
raise SystemExit(1 if failed else 0)
