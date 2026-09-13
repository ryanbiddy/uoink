"""Synthetic literal-byte qualification only; no checkpoint or model access."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time
import types


HERE = Path(__file__).absolute().parent
SOURCE = HERE / "symbolic_trace.py"


def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        name = os.fsdecode(args[0]).lower()
        if name.endswith((".bin", ".pkl", ".pickle", ".pt", ".pth", ".npz", "index.db")):
            raise RuntimeError("Artifact/database reads are forbidden")
    if event.startswith(("socket.", "subprocess.", "os.system", "ctypes.")):
        raise RuntimeError("Network/process/native actions are forbidden")
    if event == "import" and str(args[0]).split(".", 1)[0] in ("torch", "numpy", "pyannote", "whisperx", "transformers"):
        raise RuntimeError("Model/native-library imports are forbidden")


sys.addaudithook(audit)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
source_bytes = SOURCE.read_bytes()
spec = importlib.util.spec_from_file_location("inert_symbolic_proposal", SOURCE)
tracer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracer)
trace = tracer.trace_pickle_metadata


def S(value):
    value = value.encode("utf-8")
    return b"X" + struct.pack("<L", len(value)) + value


def I(value):
    return b"J" + struct.pack("<i", value)


def F(value):
    return b"G" + struct.pack(">d", value)


def G(module, name):
    return b"c" + module.encode("ascii") + b"\n" + name.encode("ascii") + b"\n"


def T(values):
    return b"(" + b"".join(values) + b"t"


def L(values):
    return b"](" + b"".join(values) + b"e"


def D(pairs):
    return b"}(" + b"".join((S(key) if isinstance(key, str) else key) + value for key, value in pairs) + b"u"


def R(module, name, arguments):
    return G(module, name) + T(arguments) + b"R"


def document(value, key="hyper_parameters"):
    return b"\x80\x02" + D([(key, value)]) + b"."


def node_map(result):
    return {node["id"]: node for node in result["nodes"]}


def root_ref(result, key):
    return next(entry["value_ref"] for entry in result["selected_root_associations"] if entry["key"] == key)


def dict_items(nodes, ref):
    node = nodes[ref]
    assert node["kind"] == "dict"
    return {nodes[key]["value"]: value for key, value in node["entries"]}


def refuses(payload, reason, limits=None):
    try:
        trace(payload, tight_limits=limits)
    except tracer.TraceRefusal as exc:
        assert reason in str(exc), (reason, str(exc))
        return
    raise AssertionError("Expected refusal containing " + reason)


cases = []


def add_refusal(name, payload, reason, limits=None):
    cases.append((name, lambda payload=payload, reason=reason, limits=limits: refuses(payload, reason, limits)))


trap_calls = []
trap_module = types.ModuleType("symbolic_trap_fixture")


def trap(*args, **kwargs):
    trap_calls.append((args, kwargs))
    raise AssertionError("A checkpoint-selected target was executed")


trap_module.explode = trap
sys.modules[trap_module.__name__] = trap_module


def malicious_targets_stay_data():
    payloads = [G("symbolic_trap_fixture", "explode"), R("symbolic_trap_fixture", "explode", [S("do_not_execute")]),
                G("symbolic_trap_fixture", "explode") + b")\x81" + D([("raw", I(7))]) + b"b"]
    for payload, expected_kind in zip(payloads, ("global", "reduce", "newobj")):
        result = trace(document(payload))
        nodes = node_map(result)
        assert nodes[root_ref(result, "hyper_parameters")]["kind"] == expected_kind
        assert not result["symbolic_operations_executed"] and not result["objects_or_tensors_constructed"]
    assert trap_calls == []


def unknown_object_mutations_are_records():
    reduced = R("symbolic_trap_fixture", "explode", []) + S("field") + I(7) + b"s"
    result = trace(document(reduced))
    node = node_map(result)[root_ref(result, "hyper_parameters")]
    assert node["kind"] == "reduce" and "entries" not in node
    assert node["operations"][0]["opcode"] == "SETITEM"
    newobj = G("symbolic_trap_fixture", "explode") + b")\x81" + I(8) + b"a"
    result = trace(document(newobj))
    node = node_map(result)[root_ref(result, "hyper_parameters")]
    assert node["kind"] == "newobj" and "items" not in node
    assert node["operations"][0]["opcode"] == "APPEND"
    assert trap_calls == []


def alias_mutation_is_visible():
    payload = b"\x80\x02}" + S("hyper_parameters") + b"}q\x00s" + S("architecture") + b"h\x00" + S("later") + I(7) + b"ss."
    result = trace(payload)
    assert root_ref(result, "hyper_parameters") == root_ref(result, "architecture")
    nodes = node_map(result)
    assert nodes[dict_items(nodes, root_ref(result, "hyper_parameters"))["later"]]["value"] == 7


def raw_configuration_and_absence():
    payload = D([("sincnet", D([("stride", I(10))])), ("lstm", D([("batch_first", b"\x89")]))])
    result = trace(document(payload))
    nodes = node_map(result)
    config = dict_items(nodes, root_ref(result, "hyper_parameters"))
    sincnet, lstm = dict_items(nodes, config["sincnet"]), dict_items(nodes, config["lstm"])
    assert set(sincnet) == {"stride"} and "sample_rate" not in sincnet
    assert nodes[lstm["batch_first"]]["value"] is False
    assert not result["configuration_verified"] and not result["architecture_verified"]


def specifications_are_unevaluated_state():
    state = D([("problem", R("pyannote.audio.core.task", "Problem", [I(0)])),
               ("resolution", R("pyannote.audio.core.task", "Resolution", [I(1)])),
               ("duration", F(2.0)), ("classes", T([S("voice"), S("other")])),
               ("permutation_invariant", b"\x88")])
    payload = G("pyannote.audio.core.task", "Specifications") + b")\x81" + state + b"b"
    result = trace(document(payload, "specifications"))
    nodes = node_map(result)
    symbolic = nodes[root_ref(result, "specifications")]
    assert symbolic["kind"] == "newobj" and symbolic["operations"][0]["opcode"] == "BUILD"
    fields = dict_items(nodes, symbolic["operations"][0]["state_ref"])
    assert set(fields) == {"problem", "resolution", "duration", "classes", "permutation_invariant"}
    assert [nodes[ref]["value"] for ref in nodes[fields["classes"]]["items"]] == ["voice", "other"]
    assert "warm_up" not in fields and "min_duration" not in fields and "powerset_max_classes" not in fields


def tensor(metadata=False, arity=None):
    storage = T([S("storage"), G("torch", "FloatStorage"), S("0"), S("cpu"), I(6)]) + b"Q"
    arguments = [storage, I(0), T([I(2), I(3)]), T([I(3), I(1)]), b"\x89", R("collections", "OrderedDict", [])]
    if metadata:
        arguments.append(D([("tag", S("raw"))]))
    if arity is not None:
        arguments = arguments[:arity]
    return R("torch._utils", "_rebuild_tensor_v2", arguments)


def tensor_argument_references_complete():
    for has_metadata in (False, True):
        result = trace(document(D([("weight", tensor(has_metadata))]), "state_dict"))
        descriptor = result["tensor_reducer_descriptors"][0]
        nodes = node_map(result)
        expected = {"storage", "storage_offset", "size", "stride", "requires_grad", "backward_hooks"}
        assert set(descriptor["argument_refs"]) == expected | ({"metadata"} if has_metadata else set())
        assert descriptor["metadata_argument_present"] is has_metadata
        assert nodes[descriptor["argument_refs"]["storage"]]["kind"] == "persistent_id"
        assert nodes[descriptor["argument_refs"]["backward_hooks"]]["kind"] == "reduce"
        assert not descriptor["tensor_constructed"] and not descriptor["shape_or_storage_validated"]


def omitted_training_text_stays_out():
    payload = b"\x80\x02" + D([("hyper_parameters", D([])), ("optimizer_states", S("DO_NOT_OUTPUT_TRAINING_CONTENT"))]) + b"."
    result = trace(payload)
    assert result["omitted_root_association_count"] == 1
    assert "DO_NOT_OUTPUT_TRAINING_CONTENT" not in json.dumps(result)


common = D([("leaf", I(1))]) + b"q\x00"
diamond = document(D([("short", common), ("long", D([("wrapper", D([("shared", b"h\x00")]))]))]))


def diamond_depth_and_shared_refs():
    result = trace(diamond, tight_limits={"depth": 6})
    nodes = node_map(result)
    values = dict_items(nodes, root_ref(result, "hyper_parameters"))
    wrapper = dict_items(nodes, values["long"])["wrapper"]
    assert dict_items(nodes, wrapper)["shared"] == values["short"]
    refuses(diamond, "Graph depth", {"depth": 5})


cases.extend([
    ("malicious_global_reduce_newobj_build_no_side_effect", malicious_targets_stay_data),
    ("unknown_object_mutations_remain_tagged", unknown_object_mutations_are_records),
    ("memo_alias_mutated_after_selected_root", alias_mutation_is_visible),
    ("raw_configuration_and_absence_preserved", raw_configuration_and_absence),
    ("specifications_state_and_order_without_defaults", specifications_are_unevaluated_state),
    ("tensor_hooks_and_optional_metadata_refs_preserved", tensor_argument_references_complete),
    ("optimizer_training_root_content_omitted", omitted_training_text_stays_out),
    ("diamond_dag_depth_uses_completed_child_heights", diamond_depth_and_shared_refs),
])

basic = document(D([]))
add_refusal("unsupported_opcode", document(b"\x8f"), "Unsupported opcode")
add_refusal("too_short_input", b"}.", "Input byte limit exceeded or input too short")
add_refusal("missing_initial_protocol", b"}N.", "initial PROTO 2")
add_refusal("wrong_protocol", b"\x80\x03}.", "initial PROTO 2")
add_refusal("repeated_protocol", b"\x80\x02\x80\x02}.", "Repeated protocol")
add_refusal("post_stop_bytes", basic + b"extra", "Trailing bytes")
add_refusal("missing_stop", basic[:-1], "Malformed pickle syntax")
add_refusal("incomplete_stop_stack", basic[:-1] + I(1) + b".", "STOP requires")
add_refusal("mark_used_as_tuple_value", b"\x80\x02(\x85.", "MARK used as value")
add_refusal("missing_mark", b"\x80\x02]e.", "MARK missing")
add_refusal("odd_mapping_items", document(b"}(" + S("only_key") + b"u"), "Odd mapping")
add_refusal("unsupported_mapping_target", document(b"]" + S("x") + I(1) + b"s"), "Mapping mutation target")
add_refusal("unsupported_sequence_target", document(b"}" + I(1) + b"a"), "Sequence mutation target")
add_refusal("nonprimitive_mapping_key", document(D([(T([]), I(1))])), "nonprimitive dictionary key")
add_refusal("duplicate_string_key", document(D([("same", I(1)), ("same", I(2))])), "Duplicate dictionary key")
add_refusal("boolean_integer_duplicate_key", document(D([(b"\x88", I(1)), (I(1), I(2))])), "Duplicate dictionary key")
add_refusal("integer_float_duplicate_key", document(D([(I(1), I(1)), (F(1.0), I(2))])), "Duplicate dictionary key")
add_refusal("signed_zero_duplicate_key", document(D([(F(-0.0), I(1)), (I(0), I(2))])), "Duplicate dictionary key")
add_refusal("duplicate_memo_assignment", document(b"}q\x00q\x00"), "Duplicate memo")
add_refusal("missing_memo_reference", document(b"h\x00"), "Missing memo")
add_refusal("nonliteral_reducer_target", document(I(1) + b")R"), "literal GLOBAL")
add_refusal("nontuple_reducer_arguments", document(G("os", "system") + I(1) + b"R"), "literal tuple")
add_refusal("duplicate_build", document(G("fixture", "Class") + b")\x81}b}b"), "Duplicate BUILD")
add_refusal("mixed_symbolic_mutation_families", document(R("fixture", "Class", []) + I(1) + b"a" + S("x") + I(2) + b"s"), "Mixed symbolic")
add_refusal("symbolic_duplicate_mapping_key", document(R("fixture", "Class", []) + S("x") + I(1) + b"s" + S("x") + I(2) + b"s"), "Duplicate dictionary key")
add_refusal("direct_memo_cycle", document(b"]q\x00h\x00a"), "Reference cycle")
omitted_cycle = b"\x80\x02" + D([("hyper_parameters", D([])), ("optimizer_states", b"]q\x00h\x00a")]) + b"."
add_refusal("cycle_only_in_omitted_training_root", omitted_cycle, "Reference cycle")
add_refusal("nonfinite_float", document(F(float("nan"))), "Nonfinite float")
add_refusal("no_selected_metadata", b"\x80\x02" + D([("epoch", I(1))]) + b".", "No selected")
add_refusal("symbolic_root_not_literal_dict", b"\x80\x02" + R("collections", "OrderedDict", []) + b".", "literal dictionary")
add_refusal("invalid_tensor_descriptor_arity", document(tensor(arity=5)), "descriptor arity")

for name, payload, reason, limits in (
    ("input", basic, "Input byte", {"input_bytes": len(basic) - 1}),
    ("opcodes", basic, "Opcode limit", {"opcodes": 1}),
    ("nodes", basic, "Node limit", {"nodes": 1}),
    ("edges", basic, "Edge limit", {"edges": 1}),
    ("stack", basic, "Stack limit", {"stack": 1}),
    ("marks", document(T([T([I(1)])])), "MARK limit", {"marks": 1}),
    ("memo", document(b"}q\x01"), "Memo index", {"memo": 1}),
    ("collection", document(L([I(1), I(2)])), "Collection item", {"collection": 1}),
    ("depth", diamond, "Graph depth", {"depth": 5}),
    ("string", basic, "String byte", {"string_bytes": 3}),
    ("total_string", document(S("a")), "Total string", {"total_string_bytes": len("hyper_parameters")}),
    ("global", document(G("fixture", "Class")), "GLOBAL literal", {"global_bytes": 1}),
    ("descriptors", document(L([tensor(), tensor()])), "Tensor descriptor limit", {"descriptors": 1}),
    ("output", basic, "Output byte", {"output_bytes": 1}),
):
    add_refusal("resource_" + name, payload, reason, limits)


def cooperative_time_refusal():
    original = tracer.time.monotonic
    ticks = [0]
    def bounded_fake_clock():
        ticks[0] += 1
        return ticks[0] * 0.002
    try:
        tracer.time.monotonic = bounded_fake_clock
        refuses(basic, "Cooperative time", {"time_ms": 1})
    finally:
        tracer.time.monotonic = original


cases.append(("resource_time_without_sleep", cooperative_time_refusal))
add_refusal("limits_cannot_be_loosened", basic, "only tighten", {"nodes": tracer.DEFAULT_LIMITS["nodes"] + 1})
add_refusal("unknown_limit_refused", basic, "Unknown limit", {"unknown": 1})


def source_boundary_audit():
    tree = ast.parse(source_bytes)
    imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert imports == ["json", "pickletools", "time"]
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))
    prohibited = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "open", "load", "loads", "find_class", "persistent_load"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            assert name not in prohibited, name
    assert len(tracer.ALLOWED_OPS) == 31
    assert trap_calls == []


cases.append(("source_has_only_stdlib_syntax_data_operations", source_boundary_audit))
started = time.monotonic()
results = []
for name, operation in cases:
    try:
        operation()
        results.append({"case": name, "status": "passed"})
    except Exception as exc:
        results.append({"case": name, "status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:220]})
failed = sum(item["status"] == "failed" for item in results)
print(json.dumps({"label": sys.argv[1], "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                  "passed": len(results) - failed, "failed": failed, "target_side_effect_count": len(trap_calls),
                  "checkpoint_opened": False, "model_imported": False,
                  "forbidden_live_startup_binding_asserted": True,
                  "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results}, indent=2))
raise SystemExit(1 if failed else 0)
