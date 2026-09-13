"""Fixed hash-bound static and inert symbolic metadata proposal; no model loading.
Root review is required before any actual checkpoint inspection.
"""
from __future__ import annotations

# Pure tracer; only its require helper is renamed.
import json
import pickletools
import time


ALLOWED_OPS = frozenset("""APPEND APPENDS BINFLOAT BINGET BININT BININT1 BININT2
BINPERSID BINPUT BINUNICODE BUILD EMPTY_DICT EMPTY_LIST EMPTY_TUPLE GLOBAL
LONG_BINGET LONG_BINPUT MARK NEWFALSE NEWOBJ NEWTRUE NONE PROTO REDUCE SETITEM
SETITEMS STOP TUPLE TUPLE1 TUPLE2 TUPLE3""".split())
SELECTED_ROOTS = frozenset(("architecture", "hyper_parameters", "pyannote.audio", "specifications", "state_dict"))
DEFAULT_LIMITS = {
    "input_bytes": 2 * 1024 * 1024, "opcodes": 250000, "nodes": 20000,
    "edges": 100000, "stack": 4096, "marks": 128, "memo": 16384,
    "collection": 4096, "depth": 64, "string_bytes": 65536,
    "total_string_bytes": 2 * 1024 * 1024, "global_bytes": 512,
    "descriptors": 256, "output_bytes": 1024 * 1024, "time_ms": 30000,
}
TENSOR_LITERAL = "torch._utils _rebuild_tensor_v2"
TENSOR_ARGUMENT_NAMES = ("storage", "storage_offset", "size", "stride", "requires_grad", "backward_hooks", "metadata")
MARK = -1


class TraceRefusal(Exception):
    pass


def trace_require(condition, reason):
    if not condition:
        raise TraceRefusal(reason)


class _Trace:
    def __init__(self, tight_limits):
        self.limits = DEFAULT_LIMITS.copy()
        if tight_limits is not None:
            trace_require(type(tight_limits) is dict, "Limits must be a plain dictionary")
            for name, value in tight_limits.items():
                trace_require(type(name) is str and name in self.limits, "Unknown limit")
                trace_require(type(value) is int and 1 <= value <= self.limits[name], "Limits may only tighten fixed bounds")
                self.limits[name] = value
        self.started = time.monotonic()
        self.nodes = []
        self.edges = []
        self.edge_count = 0
        self.stack = []
        self.marks = 0
        self.memo = {}
        self.keys = {}
        self.families = {}
        self.item_counts = {}
        self.built = set()
        self.string_bytes = 0
        self.opcode_counts = {}
        self.opcount = 0

    def tick(self):
        trace_require((time.monotonic() - self.started) * 1000 <= self.limits["time_ms"], "Cooperative time limit exceeded")

    def text(self, value, global_literal=False):
        trace_require(type(value) is str, "Nonliteral string argument")
        size = len(value.encode("utf-8"))
        trace_require(size <= self.limits["string_bytes"], "String byte limit exceeded")
        if global_literal:
            trace_require(0 < size <= self.limits["global_bytes"], "GLOBAL literal byte limit exceeded")
        self.string_bytes += size
        trace_require(self.string_bytes <= self.limits["total_string_bytes"], "Total string byte limit exceeded")
        return value

    def node(self, kind, **fields):
        self.tick()
        trace_require(len(self.nodes) < self.limits["nodes"], "Node limit exceeded")
        ref = len(self.nodes)
        self.nodes.append({"id": ref, "kind": kind, **fields})
        self.edges.append([])
        return ref

    def connect(self, parent, children):
        trace_require(self.edge_count + len(children) <= self.limits["edges"], "Edge limit exceeded")
        self.edges[parent].extend(children)
        self.edge_count += len(children)

    def push(self, ref):
        trace_require(len(self.stack) < self.limits["stack"], "Stack limit exceeded")
        self.stack.append(ref)

    def pop(self):
        trace_require(self.stack and self.stack[-1] != MARK, "Stack operand missing or MARK used as value")
        return self.stack.pop()

    def peek(self):
        trace_require(self.stack and self.stack[-1] != MARK, "Stack target missing or MARK used as value")
        return self.stack[-1]

    def marked(self):
        index = len(self.stack) - 1
        while index >= 0 and self.stack[index] != MARK:
            self.tick()
            index -= 1
        trace_require(index >= 0, "MARK missing")
        values = self.stack[index + 1:]
        del self.stack[index:]
        self.marks -= 1
        return values

    def collection(self, kind, values):
        trace_require(len(values) <= self.limits["collection"], "Collection item limit exceeded")
        ref = self.node(kind, items=list(values))
        self.connect(ref, values)
        return ref

    def key(self, ref):
        node = self.nodes[ref]
        kind = node["kind"]
        trace_require(kind in ("str", "int", "float", "bool", "none"), "Unsupported nonprimitive dictionary key")
        if kind == "str":
            return ("str", node["value"])
        if kind == "none":
            return ("none", None)
        # Builtin-only equality unifies True, 1 and 1.0, and also signed zero.
        return ("number", node["value"])

    def capacity(self, target, count):
        updated = self.item_counts.get(target, 0) + count
        trace_require(updated <= self.limits["collection"], "Collection item limit exceeded")
        self.item_counts[target] = updated

    def symbolic_operation(self, target, operation):
        operations = self.nodes[target]["operations"]
        trace_require(len(operations) < self.limits["collection"], "Symbolic operation limit exceeded")
        operations.append(operation)

    def sequence(self, target, values, opcode):
        kind = self.nodes[target]["kind"]
        trace_require(kind in ("list", "reduce", "newobj"), "Sequence mutation target is unsupported")
        self.capacity(target, len(values))
        if kind == "list":
            self.nodes[target]["items"].extend(values)
        else:
            trace_require(self.families.get(target, "sequence") == "sequence", "Mixed symbolic mutation families")
            self.families[target] = "sequence"
            self.symbolic_operation(target, {"opcode": opcode, "item_refs": list(values)})
        self.connect(target, values)

    def mapping(self, target, values, opcode):
        kind = self.nodes[target]["kind"]
        trace_require(kind in ("dict", "reduce", "newobj"), "Mapping mutation target is unsupported")
        trace_require(len(values) % 2 == 0, "Odd mapping item count")
        self.capacity(target, len(values) // 2)
        known = self.keys.setdefault(target, set())
        pairs = []
        for index in range(0, len(values), 2):
            self.tick()
            key_ref, value_ref = values[index:index + 2]
            canonical = self.key(key_ref)
            trace_require(canonical not in known, "Duplicate dictionary key")
            known.add(canonical)
            pairs.append([key_ref, value_ref])
        if kind == "dict":
            self.nodes[target]["entries"].extend(pairs)
        else:
            trace_require(self.families.get(target, "mapping") == "mapping", "Mixed symbolic mutation families")
            self.families[target] = "mapping"
            self.symbolic_operation(target, {"opcode": opcode, "entries": pairs})
        self.connect(target, values)

    def memo_index(self, value):
        trace_require(type(value) is int and 0 <= value < self.limits["memo"], "Memo index outside bound")
        return value

    def apply_opcode(self, name, argument):
        if name == "MARK":
            trace_require(self.marks < self.limits["marks"], "MARK limit exceeded")
            self.push(MARK)
            self.marks += 1
        elif name in ("BININT", "BININT1", "BININT2"):
            trace_require(type(argument) is int and argument.bit_length() <= 64, "Integer outside bound")
            self.push(self.node("int", value=argument))
        elif name == "BINFLOAT":
            trace_require(type(argument) is float and -1.7976931348623157e308 <= argument <= 1.7976931348623157e308,
                    "Nonfinite float refused")
            self.push(self.node("float", value=argument))
        elif name == "BINUNICODE":
            self.push(self.node("str", value=self.text(argument)))
        elif name in ("NEWTRUE", "NEWFALSE"):
            self.push(self.node("bool", value=name == "NEWTRUE"))
        elif name == "NONE":
            self.push(self.node("none", value=None))
        elif name == "GLOBAL":
            self.push(self.node("global", literal=self.text(argument, True)))
        elif name in ("EMPTY_LIST", "EMPTY_TUPLE"):
            self.push(self.collection("list" if name == "EMPTY_LIST" else "tuple", []))
        elif name == "EMPTY_DICT":
            self.push(self.node("dict", entries=[]))
        elif name == "TUPLE":
            self.push(self.collection("tuple", self.marked()))
        elif name in ("TUPLE1", "TUPLE2", "TUPLE3"):
            values = [self.pop() for _ in range(int(name[-1]))]
            self.push(self.collection("tuple", list(reversed(values))))
        elif name == "APPEND":
            value = self.pop()
            self.sequence(self.peek(), [value], name)
        elif name == "APPENDS":
            values = self.marked()
            self.sequence(self.peek(), values, name)
        elif name == "SETITEM":
            value, key = self.pop(), self.pop()
            self.mapping(self.peek(), [key, value], name)
        elif name == "SETITEMS":
            values = self.marked()
            self.mapping(self.peek(), values, name)
        elif name in ("BINPUT", "LONG_BINPUT"):
            index = self.memo_index(argument)
            trace_require(index not in self.memo, "Duplicate memo assignment")
            self.memo[index] = self.peek()
        elif name in ("BINGET", "LONG_BINGET"):
            index = self.memo_index(argument)
            trace_require(index in self.memo, "Missing memo reference")
            self.push(self.memo[index])
        elif name in ("REDUCE", "NEWOBJ"):
            args, target = self.pop(), self.pop()
            trace_require(self.nodes[args]["kind"] == "tuple", "Symbolic arguments must be a literal tuple")
            trace_require(self.nodes[target]["kind"] == "global", "Symbolic target must be a literal GLOBAL")
            ref = self.node("reduce" if name == "REDUCE" else "newobj",
                            target_ref=target, arguments_ref=args, operations=[])
            self.connect(ref, [target, args])
            self.push(ref)
        elif name == "BUILD":
            state = self.pop()
            target = self.peek()
            trace_require(self.nodes[target]["kind"] in ("reduce", "newobj"), "BUILD target must be a symbolic result")
            trace_require(target not in self.built, "Duplicate BUILD state")
            self.built.add(target)
            self.symbolic_operation(target, {"opcode": name, "state_ref": state})
            self.connect(target, [state])
        elif name == "BINPERSID":
            operand = self.pop()
            ref = self.node("persistent_id", operand_ref=operand)
            self.connect(ref, [operand])
            self.push(ref)
        else:
            raise TraceRefusal("Opcode has no supported grammar rule")

    def validate_graph(self):
        colours = [0] * len(self.nodes)
        heights = [0] * len(self.nodes)
        for first in range(len(self.nodes)):
            if colours[first]:
                continue
            colours[first] = 1
            frames = [[first, 0]]
            while frames:
                self.tick()
                trace_require(len(frames) <= self.limits["depth"], "Graph depth limit exceeded")
                ref, index = frames[-1]
                if index < len(self.edges[ref]):
                    child = self.edges[ref][index]
                    frames[-1][1] += 1
                    trace_require(colours[child] != 1, "Reference cycle refused")
                    if not colours[child]:
                        colours[child] = 1
                        frames.append([child, 0])
                else:
                    heights[ref] = 1 + max((heights[child] for child in self.edges[ref]), default=0)
                    trace_require(heights[ref] <= self.limits["depth"], "Graph depth limit exceeded")
                    colours[ref] = 2
                    frames.pop()

    def descriptors(self):
        result = []
        for node in self.nodes:
            self.tick()
            if node["kind"] != "reduce" or self.nodes[node["target_ref"]]["literal"] != TENSOR_LITERAL:
                continue
            arguments = self.nodes[node["arguments_ref"]]["items"]
            trace_require(len(arguments) in (6, 7), "Tensor reducer descriptor arity is unsupported")
            trace_require(len(result) < self.limits["descriptors"], "Tensor descriptor limit exceeded")
            result.append({"node_ref": node["id"], "kind": "symbolic_tensor_reducer_arguments",
                           "target_literal": TENSOR_LITERAL, "arguments_ref": node["arguments_ref"],
                           "argument_refs": dict(zip(TENSOR_ARGUMENT_NAMES, arguments)),
                           "metadata_argument_present": len(arguments) == 7,
                           "tensor_constructed": False, "shape_or_storage_validated": False})
        return result

    def output(self, root):
        selected = []
        omitted = 0
        for key_ref, value_ref in self.nodes[root]["entries"]:
            self.tick()
            key = self.nodes[key_ref]
            if key["kind"] == "str" and key["value"] in SELECTED_ROOTS:
                selected.append({"key": key["value"], "value_ref": value_ref})
            else:
                omitted += 1
        trace_require(selected, "No selected literal root metadata associations")
        wanted = set()
        pending = [entry["value_ref"] for entry in selected]
        while pending:
            self.tick()
            ref = pending.pop()
            if ref in wanted:
                continue
            wanted.add(ref)
            pending.extend(self.edges[ref])
        descriptors = [entry for entry in self.descriptors() if entry["node_ref"] in wanted]
        result = {
            "status": "symbolic_metadata_trace_complete", "protocol": 2,
            "selected_root_associations": selected, "omitted_root_association_count": omitted,
            "nodes": [self.nodes[ref] for ref in sorted(wanted)], "tensor_reducer_descriptors": descriptors,
            "opcode_counts": dict(sorted(self.opcode_counts.items())), "traced_node_count": len(self.nodes),
            "traced_edge_count": self.edge_count, "memo_entry_count": len(self.memo), "limits": self.limits,
            "symbolic_operations_executed": False, "globals_resolved": False, "persistent_ids_resolved": False,
            "objects_or_tensors_constructed": False, "architecture_verified": False,
            "configuration_verified": False, "model_compatibility_verified": False,
            "note": "Final literal-container reference graph and per-object instruction order only; no global event order, historical argument snapshots, evaluated constructor/BUILD state, loader authority or inferred defaults",
        }
        self.tick()
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
        trace_require(len(encoded) <= self.limits["output_bytes"], "Output byte limit exceeded")
        self.tick()
        return result


def trace_pickle_metadata(payload, *, tight_limits=None):
    trace_require(type(payload) is bytes, "Input must be plain immutable bytes")
    trace = _Trace(tight_limits)
    trace_require(3 <= len(payload) <= trace.limits["input_bytes"], "Input byte limit exceeded or input too short")
    root = None
    stopped = False
    try:
        for opcode, argument, position in pickletools.genops(payload):
            trace.tick()
            name = opcode.name
            trace_require(name in ALLOWED_OPS, "Unsupported opcode: " + name)
            trace.opcount += 1
            trace_require(trace.opcount <= trace.limits["opcodes"], "Opcode limit exceeded")
            trace.opcode_counts[name] = trace.opcode_counts.get(name, 0) + 1
            if trace.opcount == 1:
                trace_require(name == "PROTO" and argument == 2 and position == 0, "Exactly one initial PROTO 2 is required")
                continue
            trace_require(name != "PROTO", "Repeated protocol declaration")
            if name == "STOP":
                trace_require(position + 1 == len(payload), "Trailing bytes after STOP")
                trace_require(len(trace.stack) == 1 and trace.marks == 0 and trace.stack[0] != MARK,
                        "STOP requires one complete root and no remaining stack or MARK")
                root = trace.stack[0]
                trace_require(trace.nodes[root]["kind"] == "dict", "Root must be a literal dictionary")
                stopped = True
                break
            trace.apply_opcode(name, argument)
    except (ValueError, UnicodeError, OverflowError) as exc:
        raise TraceRefusal("Malformed pickle syntax: " + type(exc).__name__) from None
    trace_require(stopped, "STOP missing")
    trace.validate_graph()
    return trace.output(root)

# Fixed inventory reader with bounded in-memory symbolic handoff.

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
EXPECTED_ARTIFACT_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
OUTPUT = ROOT / "_scratch/vad-symbolic-adapter-proposal01/results"
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
    def __init__(self, reason, *, directory_entry=None):
        super().__init__(reason)
        self.directory_entry = directory_entry


def require(condition, reason, *, directory_entry=None):
    if not condition:
        raise Refusal(reason, directory_entry=directory_entry)


def require_expected_digest(observed_digest):
    require(observed_digest == EXPECTED_ARTIFACT_SHA256,
            "Allowlisted artifact SHA256 differs from immutable expected digest")


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
        flags, method = struct.unpack_from("<2H", directory, cursor + 8)
        crc, packed, unpacked = struct.unpack_from("<3L", directory, cursor + 16)
        entry = {"ordinal": actual_count + 1, "central_header_offset": cd_offset + cursor,
                 "needed_version": needed, "made_version": struct.unpack_from("<H", directory, cursor + 4)[0],
                 "disk": member_disk, "compression_method": method, "flags": flags,
                 "crc32_u32": crc, "compressed_bytes_u32": packed, "uncompressed_bytes_u32": unpacked,
                 "name_bytes": name_length, "extra_bytes": extra_length, "comment_bytes": comment_length,
                 "local_header_offset_u32": struct.unpack_from("<L", directory, cursor + 42)[0]}
        stored_version_zero = (needed == 0 and entry["made_version"] == 0 and member_disk == 0
                               and method == zipfile.ZIP_STORED and flags == 2056)
        require((10 <= needed <= 45 or stored_version_zero) and member_disk == 0,
                "Unsupported or split ZIP directory entry",
                directory_entry=entry)
        require(0 < name_length <= MAX_NAME and extra_length <= 8192 and comment_length <= 1024,
                "ZIP central-directory member metadata exceeds limit", directory_entry=entry)
        cursor += 46 + name_length + extra_length + comment_length
        require(cursor <= len(directory), "ZIP central-directory entry extends outside directory",
                directory_entry=entry)
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
    tail_samples = []
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
        elif opcode.name in STRING_OPS and isinstance(argument, str):
            if IDENTIFIER.fullmatch(argument):
                if len(samples) < 64 and argument not in samples:
                    samples.append(argument)
                if len(tail_samples) == 64:
                    del tail_samples[0]
                tail_samples.append(argument)
    require(last_name == "STOP" and last_position + 1 == len(payload), "Pickle is truncated or has trailing data")
    symbolic = trace_pickle_metadata(payload)
    clock_check(started)
    return {"member": member.filename, "bytes": length, "sha256": hashlib.sha256(payload).hexdigest(),
            "symbolic_metadata_trace": symbolic,
            "declared_protocols": protocols, "opcode_counts": dict(sorted(histogram.items())),
            "execution_related_opcode_counts": {name: histogram[name] for name in sorted(EXECUTION_OPS) if histogram[name]},
            "global_literals": globals_, "global_literal_limit": 64,
            "identifier_string_samples": samples, "string_sample_limit": 64,
            "identifier_string_tail_samples": tail_samples, "string_tail_sample_limit": 64,
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
        require_expected_digest(result["artifact"]["sha256"])
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
    result = {"scope": "bounded static and inert symbolic metadata inventory only", "started_utc": datetime.now(timezone.utc).isoformat(),
              "architecture_claim": None, "model_load_authorized": False, "conversion_authorized": False,
              "inference_authorized": False, "release_acceptance": False}
    code = 0
    try:
        receipt = contained_unlinked(OUTPUT / (args.run_id + ".json"), existing=False)
        require(not receipt.exists(), "Receipt already exists; no retry or overwrite")
        inspect(result, started)
        clock_check(started)
        result["status"] = "static_symbolic_inventory_complete"
    except (TraceRefusal, Refusal, zipfile.BadZipFile, zlib.error, NotImplementedError, UnicodeError, ValueError, struct.error) as exc:
        code = 2
        result["status"] = "refused"
        result["reason"] = str(exc)[:240]
        if isinstance(exc, Refusal) and exc.directory_entry is not None:
            result["refusal_context"] = {"zip_directory_entry": exc.directory_entry}
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
                      "scope": "bounded static and inert symbolic metadata inventory only", "release_acceptance": False}
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
