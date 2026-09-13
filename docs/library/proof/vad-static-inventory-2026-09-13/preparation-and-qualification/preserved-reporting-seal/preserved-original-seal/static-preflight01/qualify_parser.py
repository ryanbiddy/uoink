"""Synthetic parser checks only. Never invokes reader.main or reader.inspect."""
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


add("valid_stored", base)
add("valid_deflated", archive_bytes([("archive/data.pkl", LITERAL)], zipfile.ZIP_DEFLATED))
add("valid_zip64_end_records", zipped64(base))
add("literal_global_is_reported_without_resolution", archive_bytes([("data.pkl", b"\x80\x02cexample.module\nModel\n.")]))
add("missing_pickle", archive_bytes([("archive/storage", b"opaque")]), "Exactly one")
add("ambiguous_pickle", archive_bytes([("one/data.pkl", LITERAL), ("two/data.pkl", LITERAL)]), "Exactly one")
add("additional_pickle_suffix", archive_bytes([("data.pkl", LITERAL), ("other.PICKLE", LITERAL)]), "Exactly one")
for name in ("../data.pkl", "/data.pkl", "x\\data.pkl", "x:foo/data.pkl", "x//data.pkl", "x/./data.pkl", "x/\x01data.pkl"):
    add("unsafe_name_" + repr(name), archive_bytes([(name, LITERAL)]), "ZIP name")
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
    except (reader.Refusal, zipfile.BadZipFile, ValueError, UnicodeError, struct.error) as exc:
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
