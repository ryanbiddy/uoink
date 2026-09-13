"""Fixed-plan stdlib converter proposal. Synthetic execution only at this stage.

No model, tensor, pickle, reducer, dynamic target, archive extraction or package load.
The real file function refuses before I/O because no real protocol profile is accepted.
"""
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import time
import zlib

from zip_bounds import Refusal, directory_bounds, require

MIB = 1024 * 1024
MAX_INPUT = 32 * MIB
MAX_MEMBER = 32 * MIB
MAX_TOTAL = 32 * MIB
MAX_HEADER = 32 * 1024
MAX_OUTPUT = 6 * MIB
MAX_PLAN = 64 * 1024
MAX_SECONDS = 30.0
ORIGINAL_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
ORIGINAL_SIZE = 17719103
PLAN_SHA256 = "37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf"
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
REAL_INPUT = ROOT / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"
REAL_OUTPUT_ROOT = ROOT / "_scratch/vad-fixed-converter-approved-output"
REAL_PROFILE = None  # No guessed byte order, archive/version, or conversion approval.
NAME = re.compile(r"archive/(?:data\.pkl|version|data/(?:0|[1-9][0-9]{0,2}))\Z")
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ProtocolProfile:
    purpose: str
    profile_id: str
    archive_sha256: str
    archive_size: int
    source_byte_order: str
    scalar_encoding: str
    archive_version: bytes
    expected_member_names: tuple
    protocol_evidence_sha256: str


@dataclass(frozen=True)
class TensorRange:
    key: str
    shape: tuple
    stride: tuple
    storage_key: str
    offset: int
    elements: int


@dataclass(frozen=True)
class Plan:
    rows: tuple
    storages: tuple
    data_bytes: int


def clock_check(started):
    require(time.monotonic() - started <= MAX_SECONDS, "Conversion time bound exceeded")


def integer(value, minimum=0, maximum=MAX_TOTAL):
    require(type(value) is int and minimum <= value <= maximum, "Invalid integer or integer bound")
    return value


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(type(key) is str and key not in result, "Duplicate or non-string JSON key")
        result[key] = value
    return result


def _validate_plan(document):
    require(type(document) is dict and document.get("schema") == "uoink.fixed-vad.converter-plan.v1", "Plan schema mismatch")
    require(document.get("proposed_output_dtype") == "F32" and document.get("recorded_storage_global") == "torch FloatStorage", "Plan dtype mismatch")
    raw_rows, raw_storages = document.get("rows"), document.get("storages")
    require(type(raw_rows) is list and len(raw_rows) == 54, "Fixed tensor count mismatch")
    require(type(raw_storages) is list and len(raw_storages) == 23, "Fixed storage count mismatch")
    storages = {}
    for record in raw_storages:
        require(type(record) is dict, "Storage plan record type")
        key = record.get("key")
        require(type(key) is str and re.fullmatch(r"(?:0|[1-9][0-9]{0,2})", key) is not None and key not in storages, "Storage plan key mismatch")
        elements = integer(record.get("elements"), 1, MAX_TOTAL // 4)
        require(integer(record.get("bytes"), 4) == elements * 4, "Storage plan byte length mismatch")
        storages[key] = elements
    rows, names, ranges = [], set(), {key: [] for key in storages}
    for record in raw_rows:
        require(type(record) is dict, "Tensor plan record type")
        key, storage_key = record.get("key"), record.get("storage_key")
        require(type(key) is str and KEY.fullmatch(key) and key not in names, "Tensor plan key mismatch")
        require(type(storage_key) is str and storage_key in storages, "Tensor storage reference mismatch")
        shape, stride = record.get("shape"), record.get("stride")
        require(type(shape) is list and type(stride) is list and 1 <= len(shape) <= 3 and len(shape) == len(stride), "Shape or stride rank mismatch")
        shape = tuple(integer(x, 1, MAX_TOTAL // 4) for x in shape)
        stride = tuple(integer(x, 1, MAX_TOTAL // 4) for x in stride)
        expected, running = [], 1
        for dimension in reversed(shape):
            expected.insert(0, running)
            running *= dimension
            require(running <= MAX_TOTAL // 4, "Shape element bound")
        require(stride == tuple(expected), "Only exact dense row-major strides are supported")
        offset = integer(record.get("offset_elements"))
        require(offset + running <= storages[storage_key], "Tensor range outside storage")
        ranges[storage_key].append((offset, offset + running))
        rows.append(TensorRange(key, shape, stride, storage_key, offset, running))
        names.add(key)
    for key, spans in ranges.items():
        cursor = 0
        for start, end in sorted(spans):
            require(start == cursor, "Storage ranges overlap or leave gaps")
            cursor = end
        require(cursor == storages[key], "Storage ranges do not cover the declared storage")
    require(sum(row.elements for row in rows) == document.get("total_elements") == 1472999, "Fixed element total mismatch")
    require(sum(storages.values()) * 4 == document.get("total_output_data_bytes") == 5891996, "Fixed output data length mismatch")
    return Plan(tuple(sorted(rows, key=lambda row: row.key)), tuple(sorted(storages.items())), 5891996)


def load_fixed_plan(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PLAN, "Plan byte bound")
    require(hashlib.sha256(raw).hexdigest() == PLAN_SHA256, "Fixed plan SHA256 mismatch")
    try:
        doc = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=strict_pairs)
    except (ValueError, UnicodeError) as exc:
        raise Refusal("Malformed fixed plan JSON") from exc
    return _validate_plan(doc)


def _profile(profile):
    require(type(profile) is ProtocolProfile, "Explicit pinned protocol profile required")
    for value in (profile.purpose, profile.profile_id, profile.archive_sha256, profile.source_byte_order,
                  profile.scalar_encoding, profile.protocol_evidence_sha256):
        require(type(value) is str, "Protocol profile field type")
    require(HEX.fullmatch(profile.archive_sha256) and HEX.fullmatch(profile.protocol_evidence_sha256), "Protocol digest field invalid")
    require(0 < len(profile.profile_id) <= 96, "Protocol profile ID bound")
    integer(profile.archive_size, 22, MAX_INPUT)
    require(profile.source_byte_order == "little", "Pinned little-endian evidence required")
    require(profile.scalar_encoding == "IEEE754-binary32", "Pinned binary32 encoding evidence required")
    require(type(profile.archive_version) is bytes and 1 <= len(profile.archive_version) <= 16, "Pinned archive version bytes required")
    names = profile.expected_member_names
    require(type(names) is tuple and 25 <= len(names) <= 256, "Pinned exact member inventory required")
    require(all(type(name) is str and len(name.encode("utf-8")) <= 256 and NAME.fullmatch(name) for name in names), "Protocol member name refused")
    require(len(set(names)) == len(names) and {"archive/data.pkl", "archive/version"} <= set(names), "Protocol member inventory ambiguous")
    if profile.purpose == "synthetic":
        require(profile.archive_sha256 != ORIGINAL_SHA256, "Synthetic profile cannot authorize the real artifact")
    else:
        require(profile.purpose == "real" and REAL_PROFILE is not None and profile is REAL_PROFILE,
                "Real protocol profile is not accepted")
        require(profile.archive_sha256 == ORIGINAL_SHA256 and profile.archive_size == ORIGINAL_SIZE,
                "Real artifact identity is fixed")


def extras(raw, allowed):
    fields, cursor = {}, 0
    require(len(raw) <= 8192, "ZIP extra field bound")
    while cursor < len(raw):
        require(cursor + 4 <= len(raw), "Truncated ZIP extra field")
        tag, size = struct.unpack_from("<HH", raw, cursor)
        cursor += 4
        require(tag in allowed and tag not in fields and cursor + size <= len(raw), "Unknown, duplicate or truncated ZIP extra field")
        fields[tag] = raw[cursor:cursor + size]
        cursor += size
    return fields


def _zip64_values(fields, values, widths):
    wanted = [(index, width) for index, (value, width) in enumerate(zip(values, widths)) if value == (1 << width) - 1]
    if not wanted:
        require(1 not in fields, "Unnecessary ZIP64 extra field refused")
        return values
    require(1 in fields, "Required ZIP64 extra field missing")
    raw = fields[1]
    # ZIP64 stores even 32-bit size/offset replacements as 64-bit values; disk is 32-bit.
    expected = sum(4 if index == 3 else 8 for index, _ in wanted)
    require(len(raw) == expected, "ZIP64 extra field length mismatch")
    cursor, result = 0, list(values)
    for index, _ in wanted:
        width = 4 if index == 3 else 8
        result[index] = struct.unpack_from("<I" if width == 4 else "<Q", raw, cursor)[0]
        cursor += width
    return result


def inspect_stored_zip(raw, profile, started):
    stream = io.BytesIO(raw)
    bounds = directory_bounds(stream, len(raw))
    cd_offset, cd_size = bounds["central_directory_offset"], bounds["central_directory_bytes"]
    directory = memoryview(raw)[cd_offset:cd_offset + cd_size]
    cursor, members, intervals, total = 0, {}, [], 0
    while cursor < len(directory):
        clock_check(started)
        require(cursor + 46 <= len(directory), "Truncated central record")
        fields = struct.unpack_from("<4s6H3I5H2I", directory, cursor)
        sig, made, needed, flags, method, stamp, date, crc, packed, unpacked, nlen, xlen, clen, disk, internal, external, local = fields
        require(sig == b"PK\x01\x02" and method == 0, "Only stored ZIP members are supported")
        require(flags in (0, 8, 0x800, 0x808), "ZIP flags refused")
        require(clen == 0 and internal == 0, "ZIP comments or internal attributes refused")
        require(stat.S_IFMT(external >> 16) in (0, stat.S_IFREG), "ZIP non-regular member refused")
        end = cursor + 46 + nlen + xlen + clen
        require(end <= len(directory), "Truncated central variable metadata")
        name_raw = bytes(directory[cursor + 46:cursor + 46 + nlen])
        try:
            name = name_raw.decode("utf-8" if flags & 0x800 else "cp437")
        except UnicodeError as exc:
            raise Refusal("ZIP member name encoding refused") from exc
        require(NAME.fullmatch(name) and name not in members and b"\0" not in name_raw, "ZIP member name/path or duplicate refused")
        extra = extras(bytes(directory[cursor + 46 + nlen:end]), {1})
        unpacked, packed, local, disk = _zip64_values(extra, [unpacked, packed, local, disk], [32, 32, 32, 16])
        require(disk == 0 and 0 <= packed == unpacked <= MAX_MEMBER, "ZIP storage length or disk mismatch")
        total += unpacked
        require(total <= MAX_TOTAL and local + 30 <= cd_offset, "ZIP total or local extent bound")
        header = struct.unpack_from("<4s5H3I2H", raw, local)
        hsig, hneeded, hflags, hmethod, hstamp, hdate, hcrc, hpacked, hunpacked, hnlen, hxlen = header
        require(hsig == b"PK\x03\x04" and (hflags, hmethod, hstamp, hdate) == (flags, method, stamp, date), "Local/central ZIP fields disagree")
        require(hneeded == needed, "Local/central ZIP versions disagree")
        require(hnlen == nlen and hxlen <= 8192, "Local ZIP metadata length refused")
        data_start = local + 30 + hnlen + hxlen
        data_end = data_start + packed
        require(data_end <= cd_offset and data_start <= cd_offset, "Member payload overlaps ZIP directory")
        require(raw[local + 30:local + 30 + hnlen] == name_raw, "Local/central ZIP names disagree")
        local_extra = extras(raw[local + 30 + hnlen:data_start], {1, 0x4246})
        if 0x4246 in local_extra:
            require(all(byte == 0x5A for byte in local_extra[0x4246]), "ZIP alignment padding refused")
        hunpacked, hpacked = _zip64_values(local_extra, [hunpacked, hpacked], [32, 32])
        if flags & 8:
            require(hcrc in (0, crc) and hpacked in (0, packed) and hunpacked in (0, unpacked), "Descriptor local size or CRC mismatch")
        else:
            require((hcrc, hpacked, hunpacked) == (crc, packed, unpacked), "Local/central CRC or sizes disagree")
        members[name] = (data_start, data_end, crc, flags)
        intervals.append((local, data_end, name))
        cursor = end
    require(cursor == len(directory) and len(members) == bounds["members"], "ZIP parsed count mismatch")
    require(set(members) == set(profile.expected_member_names), "ZIP differs from pinned member inventory")
    intervals.sort()
    require(intervals[0][0] == 0, "Unreferenced ZIP prefix refused")
    for index, (local, end, name) in enumerate(intervals):
        clock_check(started)
        limit = intervals[index + 1][0] if index + 1 < len(intervals) else cd_offset
        start, _, crc, flags = members[name]
        require(local < start <= end <= limit, "Overlapping ZIP member extents")
        trailer = memoryview(raw)[end:limit]
        if flags & 8:
            require(len(trailer) in (12, 16, 20, 24), "ZIP data descriptor extent refused")
            if bytes(trailer[:4]) == b"PK\x07\x08":
                trailer = trailer[4:]
            require(len(trailer) in (12, 20), "ZIP descriptor signature or length refused")
            actual = struct.unpack("<III" if len(trailer) == 12 else "<IQQ", trailer)
            require(actual == (crc, end - start, end - start), "ZIP data descriptor disagrees")
        else:
            require(len(trailer) == 0, "Unreferenced ZIP gap refused")
        require(zlib.crc32(memoryview(raw)[start:end]) & 0xFFFFFFFF == crc, "ZIP payload CRC mismatch")
        clock_check(started)
    version_start, version_end, _, _ = members["archive/version"]
    require(raw[version_start:version_end] == profile.archive_version, "Archive version bytes differ from pinned profile")
    return members


def reject_nonfinite(view, started):
    require(len(view) % 4 == 0, "Binary32 storage alignment mismatch")
    for begin in range(0, len(view), 65536):
        clock_check(started)
        for (bits,) in struct.iter_unpack("<I", view[begin:begin + 65536]):
            require(bits & 0x7F800000 != 0x7F800000, "Nonfinite binary32 storage encoding refused")


def encode_safetensors(plan, storages, started):
    header, offset = {}, 0
    for row in plan.rows:
        length = row.elements * 4
        header[row.key] = {"dtype": "F32", "shape": list(row.shape), "data_offsets": [offset, offset + length]}
        offset += length
    require(offset == plan.data_bytes and offset <= MAX_OUTPUT, "Output data bound")
    encoded = json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 8)
    require(0 < len(encoded) <= MAX_HEADER and 8 + len(encoded) + offset <= MAX_OUTPUT, "Safetensors header or output byte bound")
    output = bytearray(8 + len(encoded) + offset)
    output[:8] = struct.pack("<Q", len(encoded))
    output[8:8 + len(encoded)] = encoded
    cursor = 8 + len(encoded)
    for row in plan.rows:
        clock_check(started)
        start, length = row.offset * 4, row.elements * 4
        source = storages[row.storage_key][start:start + length]
        require(len(source) == length, "Output range length mismatch")
        output[cursor:cursor + length] = source
        cursor += length
    require(cursor == len(output), "Output data coverage mismatch")
    result = bytes(output)
    clock_check(started)
    return result


def convert_bytes(raw, profile, plan_bytes):
    started = time.monotonic()
    _profile(profile)
    require(type(raw) is bytes and 22 <= len(raw) <= MAX_INPUT, "Immutable input bytes or size bound required")
    require(len(raw) == profile.archive_size, "Pinned artifact size mismatch")
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == profile.archive_sha256, "Pinned artifact SHA256 mismatch")
    require(digest != ORIGINAL_SHA256 or profile is REAL_PROFILE, "Real artifact has no accepted protocol profile")
    clock_check(started)
    plan = load_fixed_plan(plan_bytes)
    members = inspect_stored_zip(raw, profile, started)
    storages = {}
    for key, elements in plan.storages:
        name = "archive/data/" + key
        require(name in members, "Required fixed storage member missing")
        start, end, _, _ = members[name]
        require(end - start == elements * 4, "Fixed storage member byte length mismatch")
        view = memoryview(raw)[start:end]
        reject_nonfinite(view, started)
        storages[key] = view
    result = encode_safetensors(plan, storages, started)
    output_sha = hashlib.sha256(result).hexdigest()
    clock_check(started)
    report = {"status": "synthetic_conversion_complete" if profile.purpose == "synthetic" else "conversion_bytes_produced_unqualified",
              "profile_id": profile.profile_id, "input_sha256": digest, "input_bytes": len(raw),
              "output_sha256": output_sha, "output_bytes": len(result), "tensor_entries": 54,
              "selected_storages": 23, "dense_data_bytes": plan.data_bytes,
              "model_or_tensor_constructed": False, "pickle_interpreted": False,
              "model_compatibility_qualified": False, "release_approved": False,
              "elapsed_seconds": round(time.monotonic() - started, 6)}
    return result, report


def contained_unlinked(path, root, *, must_exist):
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    require(path.is_relative_to(root), "Path outside the fixed allowed root")
    for current in (root, *(root / Path(*path.relative_to(root).parts[:index]) for index in range(1, len(path.relative_to(root).parts) + 1))):
        try:
            observed = current.lstat()
        except FileNotFoundError:
            require(not must_exist, "Required path missing")
            continue
        require(not stat.S_ISLNK(observed.st_mode) and not getattr(observed, "st_file_attributes", 0) & 0x400, "Linked or reparse path refused")
    return path


def convert_reviewed_real_file(output_name, plan_bytes):
    # This guard precedes path resolution, stat, open or any real artifact access.
    require(REAL_PROFILE is not None, "Real byte-order/version/conversion profile remains unaccepted")
    wrapper_started = time.monotonic()
    _profile(REAL_PROFILE)
    require(type(output_name) is str and re.fullmatch(r"[a-z0-9-]{1,64}\.safetensors", output_name), "Output basename refused")
    source = contained_unlinked(REAL_INPUT, ROOT, must_exist=True)
    destination = contained_unlinked(REAL_OUTPUT_ROOT / output_name, REAL_OUTPUT_ROOT, must_exist=False)
    with source.open("rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == ORIGINAL_SIZE, "Real input file type or size mismatch")
        snapshot = stream.read(MAX_INPUT + 1)
        after = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Input changed during snapshot")
    clock_check(wrapper_started)
    result, report = convert_bytes(snapshot, REAL_PROFILE, plan_bytes)
    clock_check(wrapper_started)
    # Quiescent, user-owned output root is a precondition; no overwrites or extraction.
    # An incomplete write leaves an unaccepted file; a future attempt needs a fresh name.
    with destination.open("xb") as stream:
        require(stream.write(result) == len(result), "Short output write")
        stream.flush()
        os.fsync(stream.fileno())
    clock_check(wrapper_started)
    report["whole_file_elapsed_seconds"] = round(time.monotonic() - wrapper_started, 6)
    return report
