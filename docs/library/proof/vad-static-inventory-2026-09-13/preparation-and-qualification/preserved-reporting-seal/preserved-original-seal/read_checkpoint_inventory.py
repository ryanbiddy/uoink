"""UNEXECUTED PROPOSAL: static metadata only; no checkpoint deserialization.

Review before use. One fixed input, stdlib only, no network or model imports.
Exit 0: bounded inventory completed; 2: refusal; 3: reader error; 4: no receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pickletools
import re
import stat
import struct
import sys
import time
import zipfile
import zlib


ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
INPUT = ROOT / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"
OUTPUT = ROOT / "_scratch/vad-static-inventory-proposal01/results"
MIB = 1024 * 1024
MAX_FILE = 256 * MIB
MAX_CD = 2 * MIB
MAX_MEMBERS = 256
MAX_MEMBER = 256 * MIB
MAX_TOTAL = 512 * MIB
MAX_PICKLE = 2 * MIB
MAX_NAME = 256
MAX_OPS = 250_000
MAX_OUTPUT = 256 * 1024
MAX_SECONDS = 30.0
EXECUTION_OPS = frozenset((
    "GLOBAL", "STACK_GLOBAL", "REDUCE", "BUILD", "NEWOBJ", "NEWOBJ_EX",
    "INST", "OBJ", "EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID",
))
STRING_OPS = frozenset(("UNICODE", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8", "STRING"))
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.\[\]-]{0,95}\Z")


class Refusal(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def clock_check(started):
    require(time.monotonic() - started <= MAX_SECONDS, "Static inventory exceeded its cooperative time budget")


def contained_unlinked(path, *, existing):
    path = Path(os.path.abspath(path))
    require(path.is_relative_to(ROOT), "Path is outside the authorized checkout")
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current = current / part
        try:
            observed = current.lstat()
        except FileNotFoundError:
            require(not existing, "Required allowlisted path is missing")
            continue
        require(not stat.S_ISLNK(observed.st_mode), "Symbolic link refused")
        require(not (getattr(observed, "st_file_attributes", 0) & 0x400), "Reparse point refused")
    return path


def read_exact(stream, position, length, file_size):
    require(position >= 0 and 0 <= length <= MAX_CD, "Invalid or excessive metadata read")
    require(position + length <= file_size, "Metadata points outside the allowlisted file")
    stream.seek(position)
    value = stream.read(length)
    require(len(value) == length, "Truncated metadata read")
    return value


def directory_bounds(stream, file_size):
    tail_size = min(file_size, 65_557)
    tail = read_exact(stream, file_size - tail_size, tail_size, file_size)
    offset = tail.rfind(b"PK\x05\x06")
    require(offset >= 0 and offset + 22 <= len(tail), "A complete ZIP end record is required")
    eocd = file_size - tail_size + offset
    sig, disk, cd_disk, on_disk, count, cd_size, cd_offset, comment = struct.unpack("<4s4H2LH", tail[offset:offset + 22])
    require(eocd + 22 + comment == file_size, "Trailing or ambiguous ZIP end data refused")
    require(disk == cd_disk == 0, "Split ZIP archives are unsupported")
    locator_offset = eocd - 20
    locator = read_exact(stream, locator_offset, 20, file_size) if locator_offset >= 0 else b""
    zip64 = locator.startswith(b"PK\x06\x07")
    sentinel = on_disk == 0xFFFF or count == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF
    require(not sentinel or zip64, "ZIP64 metadata is missing")
    boundary = eocd
    if zip64:
        _, record_disk, record_offset, disks = struct.unpack("<4sLQL", locator)
        require(record_disk == 0 and disks == 1, "Split ZIP64 archives are unsupported")
        raw = read_exact(stream, record_offset, 56, file_size)
        fields = struct.unpack("<4sQ2H2L4Q", raw)
        zsig, record_size, made, needed, zdisk, zcd_disk, zon_disk, zcount, zsize, zoffset = fields
        require(zsig == b"PK\x06\x06" and 44 <= record_size <= 256, "Unsupported ZIP64 end record")
        require(record_offset + 12 + record_size == locator_offset, "ZIP64 end records overlap or disagree")
        require(zdisk == zcd_disk == 0 and zon_disk == zcount, "Split or inconsistent ZIP64 counts")
        for small, full, marker in ((on_disk, zon_disk, 0xFFFF), (count, zcount, 0xFFFF),
                                     (cd_size, zsize, 0xFFFFFFFF), (cd_offset, zoffset, 0xFFFFFFFF)):
            require(small == marker or small == full, "ZIP and ZIP64 directories disagree")
        count, cd_size, cd_offset = zcount, zsize, zoffset
        boundary = record_offset
    else:
        require(on_disk == count, "ZIP directory entry counts disagree")
    require(0 < count <= MAX_MEMBERS, "ZIP member count exceeds the inspection limit or is empty")
    require(0 < cd_size <= MAX_CD, "ZIP central directory exceeds the inspection limit")
    require(cd_offset > 0 and cd_offset + cd_size == boundary, "ZIP central-directory extent is inconsistent")
    require(read_exact(stream, 0, 4, file_size) == b"PK\x03\x04", "Prefixed or non-ZIP checkpoint refused")
    directory = read_exact(stream, cd_offset, cd_size, file_size)
    cursor = actual_count = 0
    while cursor < len(directory):
        require(actual_count < count, "Actual ZIP directory entry count exceeds advertised bound")
        require(cursor + 46 <= len(directory), "Truncated ZIP central-directory header")
        require(directory[cursor:cursor + 4] == b"PK\x01\x02", "Unsupported ZIP central-directory record")
        needed = struct.unpack_from("<H", directory, cursor + 6)[0]
        name_length, extra_length, comment_length, member_disk = struct.unpack_from("<4H", directory, cursor + 28)
        require(10 <= needed <= 45 and member_disk == 0, "Unsupported or split ZIP directory entry")
        require(0 < name_length <= MAX_NAME and extra_length <= 8192 and comment_length <= 1024,
                "ZIP central-directory member metadata exceeds limit")
        cursor += 46 + name_length + extra_length + comment_length
        require(cursor <= len(directory), "ZIP central-directory entry extends outside directory")
        actual_count += 1
    require(actual_count == count, "Actual ZIP directory entry count disagrees with advertised bound")
    return {"zip64": zip64, "members": count, "central_directory_bytes": cd_size, "central_directory_offset": cd_offset}


def member_inventory(stream, archive, bounds, file_size, started):
    members = archive.infolist()
    require(len(members) == bounds["members"], "Parsed ZIP member count disagrees with end record")
    require(archive.start_dir == bounds["central_directory_offset"], "ZIP parser selected a different directory")
    seen = set()
    spans = []
    pickle_members = []
    entries = []
    total = 0
    for info in members:
        clock_check(started)
        name = info.orig_filename
        require(name == info.filename and "\0" not in name, "NUL-containing or ambiguous ZIP name")
        require(0 < len(name.encode("utf-8")) <= MAX_NAME, "ZIP member name exceeds its limit")
        require("\\" not in name and ":" not in name and not name.startswith("/"), "Non-contained ZIP name")
        parts = name.rstrip("/").split("/")
        require(all(part not in ("", ".", "..") for part in parts), "Non-contained ZIP name")
        require(not any(ord(char) < 32 or ord(char) == 127 for char in name), "Control character in ZIP name")
        require(name not in seen, "Duplicate ZIP member names refused")
        seen.add(name)
        require(not (info.flag_bits & (1 | 0x40 | 0x2000)), "Encrypted ZIP member refused")
        require(not (info.flag_bits & ~(0x800 | 8 | 6)), "Unsupported ZIP member flags")
        require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "Unsupported ZIP compression")
        require(0 <= info.file_size <= MAX_MEMBER and 0 <= info.compress_size <= MAX_FILE, "ZIP member exceeds size bound")
        require(stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK, "ZIP symbolic-link member refused")
        require(not info.is_dir() or info.file_size == 0, "Nonempty ZIP directory member refused")
        total += info.file_size
        require(total <= MAX_TOTAL, "ZIP advertised uncompressed total exceeds limit")
        header = read_exact(stream, info.header_offset, 30, file_size)
        hsig, version, flags, method, _, _, crc, packed, unpacked, name_len, extra_len = struct.unpack("<4s5H3L2H", header)
        require(hsig == b"PK\x03\x04" and flags == info.flag_bits and method == info.compress_type, "ZIP local/central headers disagree")
        require(0 < name_len <= MAX_NAME and extra_len <= 8192, "ZIP local metadata exceeds limit")
        raw_name = read_exact(stream, info.header_offset + 30, name_len, file_size)
        local_name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
        require(local_name == name, "ZIP local/central names disagree")
        data_start = info.header_offset + 30 + name_len + extra_len
        data_end = data_start + info.compress_size
        require(data_end <= bounds["central_directory_offset"], "ZIP member overlaps central directory")
        require(info.header_offset >= 0, "Negative ZIP local-header offset")
        if not flags & 8:
            require(packed in (info.compress_size, 0xFFFFFFFF) and unpacked in (info.file_size, 0xFFFFFFFF), "ZIP local sizes disagree")
            require(crc == info.CRC, "ZIP local/central CRC fields disagree")
        spans.append((info.header_offset, data_end))
        if PurePosixPath(name).suffix.lower() in (".pkl", ".pickle"):
            pickle_members.append(info)
        entries.append({"name": name, "compressed_bytes": info.compress_size, "uncompressed_bytes": info.file_size,
                        "compression": info.compress_type, "crc32": f"{info.CRC:08x}"})
    spans.sort()
    require(all(right[0] >= left[1] for left, right in zip(spans, spans[1:])), "Overlapping ZIP member extents")
    require(len(pickle_members) == 1 and PurePosixPath(pickle_members[0].filename).name == "data.pkl",
            "Exactly one unambiguous data.pkl is required")
    return entries, total, pickle_members[0]


def parse_pickle(archive, member, started):
    require(0 < member.file_size <= MAX_PICKLE and member.compress_size <= MAX_PICKLE, "Pickle member exceeds inspection limit")
    require(member.file_size <= max(1, member.compress_size) * 100, "Pickle expansion ratio exceeds limit")
    # ZipExtFile trusts the declared output length and can hide a longer stream.
    # Decode this one bounded member ourselves, without extracting any file.
    header = read_exact(archive.fp, member.header_offset, 30, archive.start_dir)
    name_length, extra_length = struct.unpack_from("<2H", header, 26)
    data_offset = member.header_offset + 30 + name_length + extra_length
    packed = read_exact(archive.fp, data_offset, member.compress_size, archive.start_dir)
    clock_check(started)
    if member.compress_type == zipfile.ZIP_STORED:
        payload = packed
    else:
        require(member.compress_type == zipfile.ZIP_DEFLATED, "Unsupported pickle compression")
        decoder = zlib.decompressobj(-15)
        payload = decoder.decompress(packed, member.file_size + 1)
        require(not decoder.unconsumed_tail, "Actual pickle size exceeds its declared bound")
        require(decoder.eof and not decoder.unused_data, "Incomplete deflate stream or trailing compressed data")
    clock_check(started)
    length = len(payload)
    require(length == member.file_size, "Actual pickle size differs from directory metadata")
    require(zlib.crc32(payload) == member.CRC, "Pickle payload CRC differs from directory metadata")
    histogram = Counter()
    globals_ = []
    samples = []
    protocols = []
    last_position = -1
    last_name = None
    for count, (opcode, argument, position) in enumerate(pickletools.genops(payload), 1):
        clock_check(started)
        require(count <= MAX_OPS, "Pickle opcode count exceeds limit")
        require(opcode.proto <= 5, "Unsupported pickle opcode protocol")
        histogram[opcode.name] += 1
        last_position, last_name = position, opcode.name
        if opcode.name == "PROTO":
            require(isinstance(argument, int) and 0 <= argument <= 5, "Unsupported pickle protocol")
            require(len(protocols) < 8, "Ambiguous repeated pickle protocol declarations")
            protocols.append(argument)
        if opcode.name == "GLOBAL" and len(globals_) < 64:
            require(isinstance(argument, str), "Unexpected GLOBAL argument representation")
            globals_.append({"offset": position, "literal": argument[:160], "truncated": len(argument) > 160})
        elif opcode.name in STRING_OPS and isinstance(argument, str) and len(samples) < 64:
            if IDENTIFIER.fullmatch(argument) and argument not in samples:
                samples.append(argument)
    require(last_name == "STOP" and last_position + 1 == len(payload), "Pickle is truncated or has trailing data")
    return {"member": member.filename, "bytes": length, "sha256": hashlib.sha256(payload).hexdigest(),
            "declared_protocols": protocols, "opcode_counts": dict(sorted(histogram.items())),
            "execution_related_opcode_counts": {name: histogram[name] for name in sorted(EXECUTION_OPS) if histogram[name]},
            "global_literals": globals_, "global_literal_limit": 64,
            "identifier_string_samples": samples, "string_sample_limit": 64,
            "stack_globals_resolved": False, "persistent_ids_resolved": False,
            "pickle_semantics_validated": False, "objects_constructed": False,
            "note": "Literal tokens only; no global is imported or authorized and no architecture is inferred"}


def inspect(result, started):
    source = contained_unlinked(INPUT, existing=True)
    before = source.stat()
    require(stat.S_ISREG(before.st_mode), "Allowlisted input is not a regular file")
    require(22 <= before.st_size <= MAX_FILE, "Allowlisted input exceeds file bound or is too short")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(source, flags)
    with os.fdopen(fd, "rb", closefd=True) as stream:
        opened = os.fstat(stream.fileno())
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        require(identity(before) == identity(opened), "Allowlisted file changed before reading")
        contained_unlinked(INPUT, existing=True)
        sha = hashlib.sha256()
        total = 0
        while True:
            clock_check(started)
            data = stream.read(MIB)
            if not data:
                break
            total += len(data)
            require(total <= MAX_FILE, "Allowlisted file grew beyond size bound")
            sha.update(data)
        require(total == opened.st_size, "Allowlisted file size changed during hashing")
        result["artifact"] = {"allowlisted_path": str(INPUT), "bytes": total, "sha256": sha.hexdigest()}
        bounds = directory_bounds(stream, total)
        result["zip_directory"] = bounds
        with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
            entries, expanded, pickle_member = member_inventory(stream, archive, bounds, total, started)
            result["members"] = entries
            result["advertised_uncompressed_bytes"] = expanded
            result["pickle_static_inventory"] = parse_pickle(archive, pickle_member, started)
        require(identity(os.fstat(stream.fileno())) == identity(opened), "Opened file changed during inspection")
        require(identity(source.stat()) == identity(opened), "Allowlisted path changed during inspection")
        contained_unlinked(INPUT, existing=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Execute only after the reader and static inspection scope are approved")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.inspect or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", args.run_id):
        parser.error("An explicit --inspect and short fresh --run-id are required")
    started = time.monotonic()
    result = {"scope": "bounded static inventory only", "started_utc": datetime.now(timezone.utc).isoformat(),
              "architecture_claim": None, "model_load_authorized": False, "conversion_authorized": False,
              "inference_authorized": False, "release_acceptance": False}
    code = 0
    try:
        receipt = contained_unlinked(OUTPUT / (args.run_id + ".json"), existing=False)
        require(not receipt.exists(), "Receipt already exists; no retry or overwrite")
        inspect(result, started)
        result["status"] = "static_inventory_complete"
    except (Refusal, zipfile.BadZipFile, zlib.error, NotImplementedError, UnicodeError, ValueError, struct.error) as exc:
        code = 2
        result["status"] = "refused"
        result["reason"] = str(exc)[:240]
    except Exception as exc:
        code = 3
        result["status"] = "reader_error"
        result["reason"] = type(exc).__name__ + ": " + str(exc)[:200]
    result["reader_exit"] = code
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    try:
        receipt = contained_unlinked(OUTPUT / (args.run_id + ".json"), existing=False)
        encoded = (json.dumps(result, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
        if len(encoded) > MAX_OUTPUT:
            code = 2
            result = {"status": "refused", "reason": "Inventory output exceeded its byte limit", "reader_exit": code,
                      "scope": "bounded static inventory only", "release_acceptance": False}
            encoded = (json.dumps(result, indent=2) + "\n").encode("utf-8")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        contained_unlinked(receipt.parent, existing=True)
        with receipt.open("xb") as target:
            target.write(encoded)
        print(json.dumps({"status": result["status"], "reader_exit": code, "receipt": str(receipt)}))
    except Exception as exc:
        print(json.dumps({"status": "receipt_write_failed", "reader_exit": 4, "reason": type(exc).__name__}), file=sys.stderr)
        return 4
    return code


if __name__ == "__main__":
    raise SystemExit(main())
