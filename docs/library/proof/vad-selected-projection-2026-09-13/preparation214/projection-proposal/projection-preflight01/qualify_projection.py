"""Synthetic bytes and inert receipt fixtures only; actual input access forbidden."""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import time
import types
import zipfile

HERE = Path(__file__).absolute().parent
SOURCE = HERE / "read_symbolic_inventory.py"
BEFORE = HERE / "before/read_checkpoint_inventory.py"
TRACER = HERE / "before/symbolic_trace.py"


def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.fsdecode(args[0]).lower().endswith((".bin", ".pkl", ".pickle", ".pt", ".pth", ".npz", "index.db")):
            raise RuntimeError("Artifact and database access forbidden")
    if event.startswith(("socket.", "subprocess.", "os.system", "ctypes.")):
        raise RuntimeError("Network, process and native actions forbidden")
    if event == "import" and str(args[0]).split(".", 1)[0] in ("torch", "numpy", "pyannote", "whisperx", "transformers"):
        raise RuntimeError("Model imports forbidden")


sys.addaudithook(audit)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
source_bytes, before_bytes, tracer_bytes = SOURCE.read_bytes(), BEFORE.read_bytes(), TRACER.read_bytes()
assert hashlib.sha256(before_bytes).hexdigest() == "67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5"
assert hashlib.sha256(tracer_bytes).hexdigest() == "f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127"


def definitions(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old, new = definitions("old_static_reader", BEFORE), definitions("new_static_symbolic_adapter", SOURCE)


def S(value):
    encoded = value.encode("utf-8")
    return b"X" + struct.pack("<I", len(encoded)) + encoded


def I(value):
    return b"J" + struct.pack("<i", value)


def G(module, target):
    return b"c" + module.encode("ascii") + b"\n" + target.encode("ascii") + b"\n"


def D(pairs):
    return b"}(" + b"".join(S(key) + value for key, value in pairs) + b"u"


def document(value=b"}"):
    return b"\x80\x02" + D([("hyper_parameters", value)]) + b"."


def packed(payload, method=zipfile.ZIP_STORED, names=None, storage=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=method) as archive:
        for name in names or ("archive/data.pkl",):
            archive.writestr(name, payload)
        if storage:
            archive.writestr("archive/data/0", b"opaque_storage_marker_" * 5000, compress_type=zipfile.ZIP_STORED)
    return stream.getvalue()


class ReadLog(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.reads = []

    def read(self, count=-1):
        position = self.tell()
        result = super().read(count)
        self.reads.append((position, position + len(result)))
        return result


def inventory(module, raw, keep_reads=False):
    stream = ReadLog(raw)
    started = time.monotonic()
    bounds = module.directory_bounds(stream, len(raw))
    with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
        entries, total, member = module.member_inventory(stream, archive, bounds, len(raw), started)
        payload_read_start = len(stream.reads)
        result = module.parse_pickle(archive, member, started)
    return (result, stream.reads, entries, payload_read_start) if keep_reads else result


def refusal(operation, reason, exception=None):
    try:
        operation()
    except (exception or (new.Refusal, new.TraceRefusal, zipfile.BadZipFile, ValueError)) as exc:
        assert reason in str(exc), (reason, str(exc))
        return
    raise AssertionError("Expected refusal: " + reason)


cases = []


def case(name):
    def register(operation):
        cases.append((name, operation))
        return operation
    return register


def original_composition_not_applicable(operation):
    return operation


@original_composition_not_applicable
def ast_composition():
    before_tree = ast.parse(before_bytes)
    tracer_tree = ast.parse(tracer_bytes)
    after_tree = ast.parse(source_bytes)
    def header(node):
        return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and type(node.value.value) is str) or (isinstance(node, ast.ImportFrom) and node.module == "__future__")
    class TracerRename(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == "require":
                node.id = "trace_require"
            return node
        def visit_FunctionDef(self, node):
            if node.name == "require":
                node.name = "trace_require"
            return self.generic_visit(node)
    expected_tracer = TracerRename().visit(copy.deepcopy(tracer_tree))
    class ReaderDelta(ast.NodeTransformer):
        def visit_Constant(self, node):
            changes = {"_scratch/vad-static-inventory-proposal01/results": "_scratch/vad-symbolic-adapter-proposal01/results",
                       "bounded static inventory only": "bounded static and inert symbolic metadata inventory only",
                       "static_inventory_complete": "static_symbolic_inventory_complete"}
            if type(node.value) is str and node.value in changes:
                node.value = changes[node.value]
            return node
        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if node.name == "parse_pickle":
                assert isinstance(node.body[-1], ast.Return) and isinstance(node.body[-1].value, ast.Dict)
                node.body[-1].value.keys.insert(3, ast.Constant("symbolic_metadata_trace"))
                node.body[-1].value.values.insert(3, ast.Name("symbolic", ast.Load()))
                node.body[-1:-1] = ast.parse("symbolic = trace_pickle_metadata(payload)\nclock_check(started)").body
            if node.name == "main":
                for item in node.body:
                    if isinstance(item, ast.Try) and item.handlers and isinstance(item.handlers[0].type, ast.Tuple):
                        item.handlers[0].type.elts.insert(0, ast.Name("TraceRefusal", ast.Load()))
                        assert isinstance(item.body[-1], ast.Assign)
                        item.body[-1:-1] = ast.parse("clock_check(started)").body
            return node
    expected_reader = ReaderDelta().visit(copy.deepcopy(before_tree))
    expected = [item for tree in (expected_tracer, expected_reader) for item in tree.body if not header(item)]
    actual = [item for item in after_tree.body if not header(item)]
    assert ast.dump(ast.Module(body=expected, type_ignores=[]), include_attributes=False) == ast.dump(ast.Module(body=actual, type_ignores=[]), include_attributes=False)


@case("fixed_path_digest_and_output_bounds_unchanged")
def fixed_bounds():
    assert new.INPUT == old.INPUT
    assert new.EXPECTED_ARTIFACT_SHA256 == old.EXPECTED_ARTIFACT_SHA256 == "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
    for name in ("MAX_FILE", "MAX_CD", "MAX_MEMBERS", "MAX_MEMBER", "MAX_TOTAL", "MAX_PICKLE", "MAX_NAME", "MAX_OPS", "MAX_OUTPUT", "MAX_SECONDS"):
        assert vars(new)[name] == vars(old)[name]
    assert new.MAX_OUTPUT == 256 * 1024 and new.DEFAULT_LIMITS["output_bytes"] == 1024 * 1024


for method, name in ((zipfile.ZIP_STORED, "stored"), (zipfile.ZIP_DEFLATED, "deflated")):
    def compare(method=method):
        raw = packed(document(D([("stride", I(10)), ("label", S("literal"))])), method)
        prior, current = inventory(old, raw), inventory(new, raw)
        symbolic = current.pop("symbolic_metadata_trace")
        assert prior == current
        assert symbolic["status"] == "symbolic_metadata_trace_complete"
        assert symbolic["selected_root_associations"][0]["key"] == "hyper_parameters"
        assert not symbolic["objects_or_tensors_constructed"]
    cases.append((name + "_unchanged_inventory_plus_inert_trace", compare))


@case("malicious_target_remains_data")
def malicious_target():
    result = inventory(new, packed(document(G("os", "system") + b"(" + S("NEVER_EXECUTE") + b"tR")))
    symbolic = result["symbolic_metadata_trace"]
    assert any(node.get("literal") == "os system" for node in symbolic["nodes"])
    assert not symbolic["symbolic_operations_executed"] and not symbolic["globals_resolved"]


@case("no_selected_storage_member_payload_read")
def storage_not_read():
    raw = packed(document(), storage=True)
    _, reads, _, payload_read_start = inventory(new, raw, True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member = archive.getinfo("archive/data/0")
        name_len, extra_len = struct.unpack_from("<HH", raw, member.header_offset + 26)
        start = member.header_offset + 30 + name_len + extra_len
        end = start + member.compress_size
    assert any(right > start and left < end for left, right in reads[:payload_read_start])
    assert all(right <= start or left >= end for left, right in reads[payload_read_start:]), reads[payload_read_start:]


def before_symbolic_refusal(raw, reason):
    original = new.trace_pickle_metadata
    calls = []
    def forbidden_symbolic(payload, **kwargs):
        calls.append(True)
        raise AssertionError("Symbolic tracing must follow all earlier guards")
    try:
        new.trace_pickle_metadata = forbidden_symbolic
        refusal(lambda: inventory(new, raw), reason)
        assert calls == []
    finally:
        new.trace_pickle_metadata = original


@case("crc_rejected_before_symbolic")
def crc_before_symbolic():
    raw = bytearray(packed(document()))
    central = raw.index(b"PK\x01\x02")
    struct.pack_into("<I", raw, central + 16, 0)
    struct.pack_into("<I", raw, 14, 0)
    before_symbolic_refusal(bytes(raw), "CRC")


@case("actual_payload_size_rejected_before_symbolic")
def payload_size_before_symbolic():
    raw = bytearray(packed(document(), zipfile.ZIP_DEFLATED))
    central = raw.index(b"PK\x01\x02")
    original_size = struct.unpack_from("<I", raw, central + 24)[0]
    struct.pack_into("<I", raw, central + 24, original_size + 1)
    struct.pack_into("<I", raw, 22, original_size + 1)
    before_symbolic_refusal(bytes(raw), "Actual pickle size differs")


@case("trailing_pickle_rejected_before_symbolic")
def trailing_before_symbolic():
    before_symbolic_refusal(packed(document() + b"extra"), "trailing data")


@case("duplicate_metadata_key_refused")
def duplicate_metadata():
    refusal(lambda: inventory(new, packed(document(D([("x", I(1)), ("x", I(2))])))), "Duplicate dictionary key", new.TraceRefusal)


@case("omitted_training_cycle_refused")
def cycle_refused():
    payload = b"\x80\x02" + D([("hyper_parameters", b"}"), ("optimizer_states", b"]q\x00h\x00a")]) + b"."
    refusal(lambda: inventory(new, packed(payload)), "Reference cycle", new.TraceRefusal)


@case("unsupported_symbolic_opcode_refused")
def opcode_refused():
    refusal(lambda: inventory(new, packed(document(b"\x8f"))), "Unsupported opcode", new.TraceRefusal)


@case("escaping_zip_member_refused_before_symbolic")
def escaping_member():
    before_symbolic_refusal(packed(document(), names=("../data.pkl",)), "Non-contained ZIP name")


@case("ambiguous_pickle_members_refused_before_symbolic")
def ambiguous_member():
    before_symbolic_refusal(packed(document(), names=("a/data.pkl", "b/data.pkl")), "one")


@case("reader_deadline_checked_after_symbolic")
def deadline_after_symbolic():
    original_trace, original_clock = new.trace_pickle_metadata, new.clock_check
    trace_done = [False]
    def traced(payload, **kwargs):
        result = original_trace(payload, **kwargs)
        trace_done[0] = True
        return result
    def clock(started):
        if trace_done[0]:
            raise new.Refusal("Static inventory exceeded its cooperative time budget")
        return original_clock(started)
    try:
        new.trace_pickle_metadata, new.clock_check = traced, clock
        refusal(lambda: inventory(new, packed(document())), "cooperative time budget")
        assert trace_done[0]
    finally:
        new.trace_pickle_metadata, new.clock_check = original_trace, original_clock


@case("wrong_digest_refused_before_directory_and_symbolic")
def digest_before_parsing():
    raw = packed(document())
    metadata = types.SimpleNamespace(st_dev=1, st_ino=1, st_size=len(raw), st_mtime_ns=1, st_mode=0o100600)
    class InertPath:
        def stat(self):
            return metadata
    class InertStream(io.BytesIO):
        def fileno(self):
            return 31
    original = {key: vars(new)[key] for key in ("contained_unlinked", "os", "directory_bounds", "trace_pickle_metadata")}
    downstream = []
    def forbidden(*args, **kwargs):
        downstream.append(True)
        raise AssertionError("Digest gate was bypassed")
    try:
        new.contained_unlinked = lambda path, existing: InertPath()
        new.os = types.SimpleNamespace(O_RDONLY=0, O_BINARY=0, O_NOFOLLOW=0,
                                      open=lambda path, flags: 31, fstat=lambda fd: metadata,
                                      fdopen=lambda fd, mode, closefd: InertStream(raw))
        new.directory_bounds = new.trace_pickle_metadata = forbidden
        result = {}
        refusal(lambda: new.inspect(result, time.monotonic()), "immutable expected digest")
        assert result["artifact"]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert downstream == []
    finally:
        for key, value in original.items():
            setattr(new, key, value)


class MemoryReceipt:
    def __init__(self, existing=False, write_fail=False):
        self.existing, self.write_fail = existing, write_fail
        self.data = None
        self.parent = self
    def exists(self):
        return self.existing
    def mkdir(self, **kwargs):
        return None
    def open(self, mode):
        assert mode == "xb"
        if self.existing or self.write_fail:
            raise FileExistsError("Synthetic receipt cannot be written")
        owner = self
        class Capture(io.BytesIO):
            def close(self):
                owner.data = self.getvalue()
                super().close()
        return Capture()


def inert_main(effect, *, existing=False, write_fail=False, cap=None, final_clock=False):
    keys = ("inspect", "contained_unlinked", "argparse", "MAX_OUTPUT", "clock_check")
    original = {key: vars(new)[key] for key in keys}
    receipt = MemoryReceipt(existing, write_fail)
    inspected = []
    class Parser:
        def __init__(self, **kwargs): pass
        def add_argument(self, *args, **kwargs): pass
        def parse_args(self): return types.SimpleNamespace(inspect=True, run_id="synthetic-only")
    def inspect(result, started):
        inspected.append(True)
        effect(result)
    try:
        new.inspect = inspect
        new.contained_unlinked = lambda path, existing: receipt
        new.argparse = types.SimpleNamespace(ArgumentParser=Parser)
        if cap is not None:
            assert 1 <= cap <= original["MAX_OUTPUT"]
            new.MAX_OUTPUT = cap
        if final_clock:
            def expired(started):
                raise new.Refusal("Synthetic expired overall reader budget")
            new.clock_check = expired
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = new.main()
        return code, json.loads(receipt.data) if receipt.data is not None else None, inspected, out.getvalue(), err.getvalue()
    finally:
        for key, value in original.items():
            setattr(new, key, value)


@case("inert_main_success_status_and_return_zero")
def main_success():
    code, result, inspected, out, err = inert_main(lambda result: result.update(pickle_static_inventory={"synthetic": True}))
    assert code == result["reader_exit"] == 0 and result["status"] == "static_symbolic_inventory_complete"
    assert inspected == [True] and not err and not result["release_acceptance"]


@case("inert_main_trace_refusal_status_and_return_two")
def main_trace_refusal():
    def fail(result): raise new.TraceRefusal("Synthetic cycle refused")
    code, result, *_ = inert_main(fail)
    assert code == result["reader_exit"] == 2 and result["status"] == "refused"
    assert result["reason"] == "Synthetic cycle refused"


@case("inert_main_unexpected_error_return_three")
def main_error():
    def fail(result): raise RuntimeError("Synthetic reader error")
    code, result, *_ = inert_main(fail)
    assert code == result["reader_exit"] == 3 and result["status"] == "reader_error"


@case("inert_main_receipt_failure_return_four")
def main_receipt_error():
    code, result, *_ = inert_main(lambda result: None, write_fail=True)
    assert code == 4 and result is None


@case("fresh_receipt_refused_before_inert_inspection")
def main_fresh_path():
    code, result, inspected, out, err = inert_main(lambda result: None, existing=True)
    assert code == 4 and result is None and inspected == []
    assert "receipt_write_failed" in err


@case("final_receipt_cap_refuses_without_widening")
def main_output_cap():
    code, result, *_ = inert_main(lambda result: result.update(oversized="x" * 600), cap=512)
    assert code == result["reader_exit"] == 2 and result["status"] == "refused"
    assert result["reason"] == "Inventory output exceeded its byte limit"
    assert "oversized" not in result and new.MAX_OUTPUT == 256 * 1024


@case("overall_clock_refuses_before_accepted_completion")
def main_clock():
    code, result, *_ = inert_main(lambda result: None, final_clock=True)
    assert code == result["reader_exit"] == 2 and result["status"] == "refused"
    assert result["reason"] == "Synthetic expired overall reader budget"


@case("source_imports_and_no_dynamic_loader_boundary")
def imports_boundary():
    tree = ast.parse(source_bytes)
    actual = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert actual == {"json", "pickletools", "time", "argparse", "hashlib", "os", "re", "stat", "struct", "sys", "zipfile", "zlib"}
    prohibited = {"eval", "exec", "compile", "__import__", "load", "loads", "exec_module", "find_class", "persistent_load"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" and node.func.attr == "compile":
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            assert name not in prohibited


@original_composition_not_applicable
def reporting_delta():
    original = ast.parse((HERE / "before/read_symbolic_inventory.py").read_bytes())
    current = ast.parse(source_bytes)
    assert hashlib.sha256((HERE / "before/read_symbolic_inventory.py").read_bytes()).hexdigest() == "0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc"
    old_class = next(node for node in original.body if isinstance(node, ast.ClassDef) and node.name == "TraceRefusal")
    modified = copy.deepcopy(current)
    modified.body = [node for node in modified.body if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("CYCLE_WITNESS_NODE_LIMIT", "CYCLE_WITNESS_BYTE_LIMIT"))]
    for index, node in enumerate(modified.body):
        if isinstance(node, ast.ClassDef) and node.name == "TraceRefusal":
            modified.body[index] = copy.deepcopy(old_class)
        elif isinstance(node, ast.ClassDef) and node.name == "_Trace":
            node.body = [item for item in node.body if not (isinstance(item, ast.FunctionDef) and item.name in ("cycle_edge", "cycle_witness"))]
            validation = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "validate_graph")
            assert [arg.arg for arg in validation.args.args] == ["self", "root"]
            validation.args.args.pop()
            class RestoreCycle(ast.NodeTransformer):
                def visit_If(self, item):
                    if ast.dump(item.test, include_attributes=False) == ast.dump(ast.parse("colours[child] == 1", mode="eval").body, include_attributes=False):
                        return ast.parse('trace_require(colours[child] != 1, "Reference cycle refused")').body[0]
                    return self.generic_visit(item)
            RestoreCycle().visit(validation)
        elif isinstance(node, ast.FunctionDef) and node.name == "trace_pickle_metadata":
            calls = [item for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "validate_graph"]
            assert len(calls) == 1 and len(calls[0].args) == 1
            calls[0].args.clear()
        elif isinstance(node, ast.FunctionDef) and node.name == "main":
            for item in ast.walk(node):
                if isinstance(item, ast.ExceptHandler) and isinstance(item.type, ast.Tuple):
                    last = item.body[-1]
                    assert isinstance(last, ast.If)
                    assert ast.dump(last.test, include_attributes=False) == ast.dump(ast.parse("isinstance(exc, TraceRefusal) and exc.cycle_witness is not None", mode="eval").body, include_attributes=False)
                    item.body.pop()
    assert ast.dump(modified, include_attributes=False) == ast.dump(original, include_attributes=False)
    assert new.CYCLE_WITNESS_NODE_LIMIT == 12 and new.CYCLE_WITNESS_BYTE_LIMIT == 4096


def captured_cycle(payload):
    try:
        new.trace_pickle_metadata(payload)
    except new.TraceRefusal as exc:
        assert str(exc) == "Reference cycle refused"
        assert exc.cycle_witness is not None
        return exc
    raise AssertionError("Expected unchanged cycle refusal")


def witness(payload):
    return captured_cycle(payload).cycle_witness


@case("self_loop_occurrence_and_selected_entry")
def self_loop():
    observed = witness(document(b"]q\x00h\x00a"))
    assert observed["cycle_node_count"] == 1 and len(observed["path_prefix"]) == 1
    closing = observed["closing_edge"]
    assert closing["from_ref"] == closing["to_ref"]
    assert closing["edge_index"] == 0 and closing["role"] == "list.item"
    assert observed["detected_entry_path"] == {"category": "selected_metadata_root", "selected_root": "hyper_parameters"}
    assert not observed["path_truncated"]


@case("two_node_cycle_keeps_actual_path_and_closing_edge")
def two_node_cycle():
    observed = witness(document(b"]q\x00]h\x00aa"))
    assert observed["cycle_node_count"] == 2 and len(observed["path_edges"]) == 1
    edge, closing = observed["path_edges"][0], observed["closing_edge"]
    assert edge["from_ref"] == closing["to_ref"] and edge["to_ref"] == closing["from_ref"]


@case("fixed_parent_role_without_key_or_value_disclosure")
def parent_role():
    payload = document(b"}q\x00" + S("SECRET_FIELD") + S("SECRET_VALUE") + b"s" + S("_parent") + b"h\x00s")
    observed = witness(payload)
    assert observed["closing_edge"]["role"] == "dict.parent_field_value"
    text = json.dumps(observed)
    assert "SECRET_FIELD" not in text and "SECRET_VALUE" not in text and "_parent" not in text


@case("edge_role_helper_uses_given_duplicate_occurrence")
def edge_occurrence_helper():
    # Direct data-record helper check, not a claim that DFS reaches the second duplicate.
    trace = new._Trace(None)
    trace.nodes = [{"kind": "dict", "entries": [[1, 3], [2, 3]]},
                   {"kind": "str", "value": "_parent"}, {"kind": "str", "value": "_content"}, {"kind": "list", "items": []}]
    assert trace.cycle_edge(0, 3, 1)["role"] == "dict.parent_field_value"
    assert trace.cycle_edge(0, 3, 3)["role"] == "dict.content_field_value"
    assert trace.cycle_edge(0, 3, 3)["edge_index"] == 3


@case("cycle_prefix_truncation_and_separate_closing_edge")
def prefix_truncation():
    payload = document(b"]q\x00" + b"]" * 19 + b"h\x00" + b"a" * 20)
    observed = witness(payload)
    assert observed["cycle_node_count"] == 20 and len(observed["path_prefix"]) == 12
    assert len(observed["path_edges"]) == 11 and observed["path_truncated"]
    assert observed["closing_edge_is_separate_from_truncated_prefix"]
    assert observed["closing_edge"]["from_ref"] != observed["path_prefix"][-1]["node_ref"]
    assert len(json.dumps(observed, separators=(",", ":")).encode()) <= 4096


@case("tightened_witness_byte_cap_keeps_refusal")
def byte_cap():
    original = new.CYCLE_WITNESS_BYTE_LIMIT
    try:
        new.CYCLE_WITNESS_BYTE_LIMIT = 128
        observed = witness(document(b"]q\x00h\x00a"))
        assert observed == {"status": "truncated", "reason": "cycle_witness_byte_limit"}
        assert len(json.dumps(observed, separators=(",", ":")).encode()) <= 128
    finally:
        new.CYCLE_WITNESS_BYTE_LIMIT = original


@case("root_self_loop_context_is_unavailable")
def unavailable_root():
    observed = witness(b"\x80\x02}q\x00" + S("hyper_parameters") + b"h\x00s.")
    assert observed["detected_entry_path"] == {"category": "unavailable"}


@case("training_entry_with_selected_alias_is_nonexclusive")
def alias_category():
    payload = b"\x80\x02" + D([("optimizer_states", b"]q\x00h\x00a"), ("hyper_parameters", b"h\x00")]) + b"."
    observed = witness(payload)
    assert observed["detected_entry_path"] == {"category": "known_training_root"}
    assert not observed["entry_path_is_exclusive_ownership"]
    assert "optimizer_states" not in json.dumps(observed)


@case("unknown_omitted_root_name_is_not_disclosed")
def omitted_root():
    payload = b"\x80\x02" + D([("SECRET_ROOT_NAME", b"]q\x00h\x00a"), ("hyper_parameters", b"}")]) + b"."
    observed = witness(payload)
    assert observed["detected_entry_path"] == {"category": "other_omitted_root"}
    assert "SECRET_ROOT_NAME" not in json.dumps(observed)


@case("witness_generation_error_preserves_cycle_refusal")
def witness_error():
    original = new._Trace.cycle_witness
    def broken(*args): raise ValueError("SECRET_DIAGNOSTIC_ERROR")
    try:
        new._Trace.cycle_witness = broken
        observed = witness(document(b"]q\x00h\x00a"))
        assert observed == {"status": "unavailable", "reason": "cycle_witness_generation_error"}
        assert "SECRET" not in json.dumps(observed)
    finally:
        new._Trace.cycle_witness = original


@case("refused_graph_never_calls_output_or_descriptors")
def no_output_after_refusal():
    original_output, original_descriptors = new._Trace.output, new._Trace.descriptors
    called = []
    def forbidden(*args):
        called.append(True)
        raise AssertionError("Refused graph output was called")
    try:
        new._Trace.output = new._Trace.descriptors = forbidden
        witness(document(b"]q\x00h\x00a"))
        assert called == []
    finally:
        new._Trace.output, new._Trace.descriptors = original_output, original_descriptors


@case("inert_main_records_cycle_context_and_refusal_two")
def main_cycle_context():
    refusal_value = captured_cycle(document(b"]q\x00h\x00a"))
    def fail(result): raise refusal_value
    code, result, *_ = inert_main(fail)
    assert code == result["reader_exit"] == 2 and result["status"] == "refused"
    assert result["reason"] == "Reference cycle refused"
    assert result["refusal_context"] == {"reference_cycle": refusal_value.cycle_witness}
    assert "pickle_static_inventory" not in result and not result["release_acceptance"]


@case("projection_scope_preserves_other_ast")
def projection_ast():
    original = ast.parse((HERE / "before/read_symbolic_inventory.py").read_bytes())
    modified = ast.parse(source_bytes)
    assert hashlib.sha256((HERE / "before/read_symbolic_inventory.py").read_bytes()).hexdigest() == "15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd"
    modified.body = [node for node in modified.body if not ((isinstance(node, ast.ClassDef) and node.name == "ProjectionRefusal") or (isinstance(node, ast.FunctionDef) and node.name == "projection_require"))]
    for node in modified.body:
        if isinstance(node, ast.ClassDef) and node.name == "TraceRefusal":
            constructor = node.body[0]
            assert isinstance(constructor.body[-1], ast.Assign) and constructor.body[-1].targets[0].attr == "selected_root_projection"
            constructor.body.pop()
        elif isinstance(node, ast.ClassDef) and node.name == "_Trace":
            node.body = [item for item in node.body if not (isinstance(item, ast.FunctionDef) and item.name in ("selected_projection", "build_selected_projection"))]
        elif isinstance(node, ast.FunctionDef) and node.name == "trace_pickle_metadata":
            assert [arg.arg for arg in node.args.kwonlyargs] == ["tight_limits", "project_selected", "projection_deadline"]
            node.args.kwonlyargs = node.args.kwonlyargs[:1]
            node.args.kw_defaults = node.args.kw_defaults[:1]
            assert isinstance(node.body[-2], ast.Try)
            node.body[-2] = ast.parse("trace.validate_graph(root)").body[0]
        elif isinstance(node, ast.FunctionDef) and node.name == "parse_pickle":
            calls = [item for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "trace_pickle_metadata"]
            assert len(calls) == 1 and [item.arg for item in calls[0].keywords] == ["project_selected", "projection_deadline"]
            calls[0].keywords.clear()
        elif isinstance(node, ast.FunctionDef) and node.name == "main":
            for item in node.body:
                if not isinstance(item, ast.Try):
                    continue
                for handler in item.handlers:
                    handler.body = [part for part in handler.body if not (isinstance(part, ast.If) and any(isinstance(child, ast.Attribute) and child.attr == "selected_root_projection" for child in ast.walk(part.test)))]
                kept = []
                for part in item.body:
                    if isinstance(part, ast.Assign) and isinstance(part.targets[0], ast.Name) and part.targets[0].id == "attached_projection":
                        continue
                    if isinstance(part, ast.If):
                        if any(isinstance(child, ast.Name) and child.id == "attached_projection" for child in ast.walk(part.test)):
                            continue
                        if any(isinstance(child, ast.Constant) and child.value == "Reference cycle refused" for child in ast.walk(part.test)):
                            continue
                    kept.append(part)
                item.body = kept
    assert ast.dump(modified, include_attributes=False) == ast.dump(original, include_attributes=False)


def T(values):
    return b"(" + b"".join(values) + b"t"


def training_and_selected(selected, other=()):
    return b"\x80\x02" + D([("optimizer_states", b"]q\x00" + S("OMITTED_TRAINING_SECRET") + b"ah\x00a")] + list(selected) + list(other)) + b"."


def projected_exception(payload, *, limits=None, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + 30
    try:
        new.trace_pickle_metadata(payload, tight_limits=limits, project_selected=True, projection_deadline=deadline)
    except new.TraceRefusal as exc:
        assert str(exc) == "Reference cycle refused"
        assert exc.cycle_witness is not None and exc.selected_root_projection is not None
        return exc
    raise AssertionError("Projection must never replace the strict cycle refusal")


def projection(payload, **kwargs):
    return projected_exception(payload, **kwargs).selected_root_projection


def projection_refused(payload, reason, **kwargs):
    value = projection(payload, **kwargs)
    assert value == {"status": "projection_refused", "reason": reason}
    assert "nodes" not in value and "selected_root_associations" not in value


@case("separate_selected_closure_is_partial_untrusted_and_omits_training")
def separate_selected():
    value = projection(training_and_selected([("hyper_parameters", D([("stride", I(10))]))]))
    assert value["status"] == "partial_untrusted_selected_root_projection"
    assert value["artifact_remains_refused"] and value["partial_and_untrusted"]
    assert not value["whole_artifact_graph_accepted"] and not value["provenance_verified"]
    assert "OMITTED_TRAINING_SECRET" not in json.dumps(value)
    assert {item["key"] for item in value["selected_root_associations"]} == {"hyper_parameters"}


@case("selected_alias_into_training_cycle_refuses_all_projection")
def selected_alias_cycle():
    projection_refused(training_and_selected([("hyper_parameters", b"h\x00")]), "selected_reference_cycle")


@case("selected_roots_share_one_validated_acyclic_node")
def shared_selected():
    value = projection(training_and_selected([("hyper_parameters", D([("x", I(1))]) + b"q\x01"), ("architecture", b"h\x01")]))
    assert len({item["value_ref"] for item in value["selected_root_associations"]}) == 1
    ids = [item["id"] for item in value["nodes"]]
    assert len(ids) == len(set(ids)) == value["selected_node_count"]


@case("acyclic_value_shared_with_omitted_root_has_unknown_ownership")
def shared_omitted():
    payload = b"\x80\x02" + D([("optimizer_states", b"]q\x00h\x00a"), ("OTHER_OMITTED_ROOT", S("SHARED_LITERAL") + b"q\x01"), ("hyper_parameters", b"h\x01")]) + b"."
    value = projection(payload)
    assert "SHARED_LITERAL" in json.dumps(value) and "OTHER_OMITTED_ROOT" not in json.dumps(value)
    assert value["aliases_may_share_values_with_omitted_roots"]
    assert not value["semantic_ownership_verified"] and not value["provenance_verified"]


@case("selected_build_state_cycle_is_not_pruned")
def selected_build_cycle():
    raw = G("fixture", "Class") + b")\x81q\x01}" + S("_parent") + b"h\x01sb"
    projection_refused(training_and_selected([("hyper_parameters", raw)]), "selected_reference_cycle")


@case("selected_argument_cycle_is_not_pruned")
def selected_argument_cycle():
    raw = b"]q\x01" + G("fixture", "Class") + b"(h\x01tRa"
    projection_refused(training_and_selected([("hyper_parameters", raw)]), "selected_reference_cycle")


@case("selected_persistent_operand_cycle_is_not_pruned")
def selected_persistent_cycle():
    projection_refused(training_and_selected([("hyper_parameters", b"]q\x01h\x01Qa")]), "selected_reference_cycle")


@case("selected_recorded_mutation_cycle_is_not_pruned")
def selected_mutation_cycle():
    raw = G("fixture", "Class") + b")Rq\x01" + S("parent") + b"h\x01s"
    projection_refused(training_and_selected([("hyper_parameters", raw)]), "selected_reference_cycle")


@case("selected_diamond_depth_includes_original_root")
def selected_depth():
    common = D([("leaf", I(1))]) + b"q\x01"
    diamond = D([("short", common), ("long", D([("wrapper", D([("shared", b"h\x01")]))]))])
    raw = training_and_selected([("hyper_parameters", diamond)])
    value = projection(raw, limits={"depth": 6})
    assert value["depth_includes_original_root"] and value["selected_closure_acyclic"]
    projection_refused(raw, "selected_depth_limit_including_root", limits={"depth": 5})


@case("no_selected_roots_refuses_projection")
def no_selected_projection():
    projection_refused(training_and_selected([]), "no_selected_roots")


def tensor_record(arity=6):
    arguments = [S("INERT_STORAGE_REFERENCE"), I(0), T([I(2)]), T([I(1)]), b"\x89", G("collections", "OrderedDict") + b")R"]
    if arity == 7:
        arguments.append(D([("literal", I(1))]))
    return G("torch._utils", "_rebuild_tensor_v2") + T(arguments[:arity]) + b"R"


@case("selected_tensor_descriptor_arity_refuses_all_values")
def selected_bad_descriptor():
    projection_refused(training_and_selected([("state_dict", D([("weight", tensor_record(5))]))]), "selected_tensor_descriptor_arity")


@case("selected_tensor_descriptor_limit_refuses_all_values")
def descriptor_limit():
    projection_refused(training_and_selected([("state_dict", D([("a", tensor_record()), ("b", tensor_record())]))]), "selected_tensor_descriptor_limit", limits={"descriptors": 1})


@case("selected_descriptors_keep_hooks_and_optional_metadata")
def selected_descriptor_fields():
    for arity in (6, 7):
        value = projection(training_and_selected([("state_dict", D([("weight", tensor_record(arity))]))]))
        descriptor = value["tensor_reducer_descriptors"][0]
        assert "backward_hooks" in descriptor["argument_refs"]
        assert ("metadata" in descriptor["argument_refs"]) is (arity == 7)
        assert not descriptor["tensor_constructed"] and not descriptor["shape_or_storage_validated"]


@case("omitted_invalid_descriptor_and_value_are_not_scanned_or_emitted")
def omitted_descriptor():
    raw = training_and_selected([("hyper_parameters", b"}")], [("OMITTED_DESCRIPTOR", tensor_record(5)), ("SECRET_ROOT", S("SECRET_OMITTED_VALUE"))])
    value = projection(raw)
    assert value["status"] == "partial_untrusted_selected_root_projection"
    assert value["tensor_reducer_descriptors"] == []
    text = json.dumps(value)
    assert "_rebuild_tensor_v2" not in text and "SECRET_OMITTED_VALUE" not in text and "OMITTED_DESCRIPTOR" not in text


@case("selected_compact_output_cap_refuses_entire_graph")
def selected_output_cap():
    projection_refused(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT"))]), "selected_compact_output_limit", limits={"output_bytes": 1})


def post_parse_limit_refusal(name, reason):
    original = new._Trace.selected_projection
    def tightened(self, root, deadline):
        self.limits[name] = 1
        return original(self, root, deadline)
    try:
        new._Trace.selected_projection = tightened
        projection_refused(training_and_selected([("hyper_parameters", D([("x", I(1))]))]), reason)
    finally:
        new._Trace.selected_projection = original


@case("inert_post_parse_selected_node_limit_refuses_all_values")
def selected_node_limit():
    post_parse_limit_refusal("nodes", "selected_node_limit")


@case("inert_post_parse_selected_edge_limit_refuses_all_values")
def selected_edge_limit():
    post_parse_limit_refusal("edges", "selected_edge_limit")


@case("expired_original_reader_deadline_refuses_projection")
def expired_reader():
    projection_refused(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT"))]), "original_reader_deadline_exceeded", deadline=0)


@case("missing_reader_deadline_does_not_create_new_budget")
def missing_reader_deadline():
    try:
        new.trace_pickle_metadata(training_and_selected([("hyper_parameters", b"}")]), project_selected=True)
    except new.TraceRefusal as exc:
        assert str(exc) == "Reference cycle refused"
        assert exc.selected_root_projection == {"status": "projection_refused", "reason": "missing_or_invalid_original_reader_deadline"}
    else:
        raise AssertionError("Strict refusal must survive")


@case("expired_original_trace_budget_refuses_projection")
def expired_trace():
    original = new._Trace.selected_projection
    def expire(self, root, deadline):
        self.started -= 31
        return original(self, root, deadline)
    try:
        new._Trace.selected_projection = expire
        projection_refused(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT"))]), "original_trace_budget_exceeded")
    finally:
        new._Trace.selected_projection = original


@case("projection_internal_error_never_emits_prefix_or_error_text")
def projection_error():
    original = new._Trace.build_selected_projection
    def broken(*args): raise RuntimeError("SECRET_ERROR_TEXT")
    try:
        new._Trace.build_selected_projection = broken
        projection_refused(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT"))]), "projection_internal_error")
    finally:
        new._Trace.build_selected_projection = original


@case("projection_does_not_call_general_output_or_all_node_descriptors")
def no_general_output():
    original_output, original_descriptors = new._Trace.output, new._Trace.descriptors
    called = []
    def forbidden(*args):
        called.append(True)
        raise AssertionError("All-node projection operation forbidden")
    try:
        new._Trace.output = new._Trace.descriptors = forbidden
        value = projection(training_and_selected([("hyper_parameters", b"}")]))
        assert value["status"] == "partial_untrusted_selected_root_projection" and called == []
    finally:
        new._Trace.output, new._Trace.descriptors = original_output, original_descriptors


@case("strict_grammar_failure_never_triggers_projection")
def strict_before_projection():
    raw = training_and_selected([("hyper_parameters", D([("duplicate", I(1)), ("duplicate", I(2))]))])
    try:
        new.trace_pickle_metadata(raw, project_selected=True, projection_deadline=time.monotonic() + 30)
    except new.TraceRefusal as exc:
        assert str(exc) == "Duplicate dictionary key" and exc.selected_root_projection is None
    else:
        raise AssertionError("Grammar refusal must survive")


@case("fixed_reader_handoff_requests_partial_projection_without_acceptance")
def fixed_reader_projection():
    raw = packed(training_and_selected([("hyper_parameters", b"}")]))
    try:
        inventory(new, raw)
    except new.TraceRefusal as exc:
        assert str(exc) == "Reference cycle refused"
        assert exc.selected_root_projection["status"] == "partial_untrusted_selected_root_projection"
    else:
        raise AssertionError("Reader must retain strict refusal")


@case("inert_main_partial_projection_still_returns_refusal_two")
def main_partial():
    error = projected_exception(training_and_selected([("hyper_parameters", D([("value", I(1))]))]))
    def fail(result): raise error
    code, result, *_ = inert_main(fail)
    assert code == result["reader_exit"] == 2 and result["status"] == "refused" and result["reason"] == "Reference cycle refused"
    assert result["refusal_context"]["selected_root_projection"]["partial_and_untrusted"]
    assert not result["release_acceptance"]


@case("final_receipt_cap_discards_projection_preserves_strict_cycle")
def main_projection_cap():
    error = projected_exception(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT_GRAPH" * 40))]))
    def fail(result): raise error
    code, result, *_ = inert_main(fail, cap=512)
    assert code == result["reader_exit"] == 2 and result["reason"] == "Reference cycle refused"
    assert result["refusal_context"]["selected_root_projection"] == {"status": "projection_refused", "reason": "final_receipt_byte_limit"}
    assert "nodes" not in json.dumps(result) and "DO_NOT_EMIT_GRAPH" not in json.dumps(result)
    assert len((json.dumps(result, indent=2) + "\n").encode()) <= 512


@case("deadline_crossed_during_serialization_discards_all_projection_values")
def serialization_deadline():
    error = projected_exception(training_and_selected([("hyper_parameters", S("DO_NOT_EMIT_AFTER_DEADLINE"))]))
    original_time, original_json = new.time, new.json
    clock_value = [1000.0]
    serialized_full_graph = []
    def dumps(value, **kwargs):
        result = json.dumps(value, **kwargs)
        if isinstance(value, dict) and value.get("reason") == "Reference cycle refused" and value.get("refusal_context", {}).get("selected_root_projection", {}).get("status") == "partial_untrusted_selected_root_projection":
            serialized_full_graph.append(True)
            clock_value[0] = 1031.0
        return result
    def fail(result): raise error
    try:
        new.time = types.SimpleNamespace(monotonic=lambda: clock_value[0])
        new.json = types.SimpleNamespace(dumps=dumps)
        code, result, *_ = inert_main(fail)
        assert serialized_full_graph == [True]
        assert code == result["reader_exit"] == 2 and result["reason"] == "Reference cycle refused"
        assert result["refusal_context"]["selected_root_projection"] == {"status": "projection_refused", "reason": "original_reader_deadline_exceeded"}
        assert "DO_NOT_EMIT_AFTER_DEADLINE" not in json.dumps(result) and "nodes" not in json.dumps(result)
    finally:
        new.time, new.json = original_time, original_json


started = time.monotonic()
results = []
for name, operation in cases:
    try:
        operation()
        results.append({"case": name, "status": "passed"})
    except Exception as exc:
        results.append({"case": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:250]})
failed = sum(item["status"] == "failed" for item in results)
print(json.dumps({"label": sys.argv[1], "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                  "passed": len(results) - failed, "failed": failed,
                  "forbidden_live_startup_binding_asserted": True,
                  "actual_checkpoint_opened": False, "actual_main_input_output_paths_used": False,
                  "objects_or_tensors_constructed": False,
                  "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results}, indent=2))
raise SystemExit(1 if failed else 0)
