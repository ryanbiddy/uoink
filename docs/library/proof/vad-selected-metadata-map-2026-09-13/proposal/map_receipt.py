"""Fixed safe-JSON reporting only. Never reads model artifacts or imports model code."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
ROOT = BASE / "_scratch/vad-selected-metadata-map01"
INPUT = BASE / "_scratch/vad-symbolic-adapter-proposal01/results/symbolic-projection01.json"
BINDINGS = BASE / "_scratch/vad-fixed-loader-proposal01/source-bindings.json"
SOURCE_ROOT = BASE / "_scratch/vad-fixed-loader-proposal01"
EXPECTED = "60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d"
EXPECTED_BINDINGS = "8dbd83213bceac5012bc342e001826902ce3a88fd420fa64f8f8d9a65366fa9c"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
SOURCE_KEYS = {"PYANNET", "SINCNET", "SINC_FB", "TASK", "MODEL", "INFERENCE", "WXVAD", "WXASR", "GETTER", "LOCK"}
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
started = time.monotonic()


def norm(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


allowed_reads = {norm(INPUT), norm(BINDINGS)}
allowed_writes = {norm(ROOT / name) for name in ("mapping.json", "tensor-table.md", "map-run01.json")}


def audit(event, args):
    if event == "open":
        path, mode, flags = args
        assert not isinstance(path, int), "Unapproved file descriptor"
        key = norm(path)
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        assert key in (allowed_writes if writing else allowed_reads), "Unapproved file access"
    elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in {"os.system", "os.startfile", "os.spawn", "import"}:
        raise AssertionError("Non-reporting operation refused")


sys.addaudithook(audit)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, "Duplicate JSON key"
        result[key] = value
    return result


def read_json(path, expected, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    assert len(raw) <= limit
    assert hashlib.sha256(raw).hexdigest() == expected
    return json.loads(raw, object_pairs_hook=strict_pairs), len(raw)


receipt, byte_count = read_json(INPUT, EXPECTED, 256 * 1024)
assert byte_count == 190182
assert receipt["status"] == "refused" and receipt["reason"] == "Reference cycle refused" and receipt["reader_exit"] == 2
projection = receipt["refusal_context"]["selected_root_projection"]
assert projection["status"] == "partial_untrusted_selected_root_projection"
assert projection["selected_closure_acyclic"] and not projection["architecture_verified"]
nodes = {node["id"]: node for node in projection["nodes"]}
assert len(nodes) == len(projection["nodes"]) == 1069


def node(ref, kind):
    record = nodes[ref]
    assert record["kind"] == kind, (ref, kind)
    return record


def scalar(ref, kind):
    value = node(ref, kind)["value"]
    assert type(value) is {"str": str, "int": int, "bool": bool, "float": float}[kind]
    return value


def ints(ref):
    refs = node(ref, "tuple")["items"]
    assert len(refs) <= 8
    values = [scalar(item, "int") for item in refs]
    assert all(0 <= item <= 10**9 for item in values)
    return {"ref": ref, "item_refs": refs, "values": values}


descriptors = {item["node_ref"]: item for item in projection["tensor_reducer_descriptors"]}
state = node(10, "reduce")
assert state["target_ref"] == 8 and node(8, "global")["literal"] == "collections OrderedDict"
assert node(state["arguments_ref"], "tuple")["items"] == []
assert [op["opcode"] for op in state["operations"]] == ["SETITEMS", "BUILD"]
pairs = state["operations"][0]["entries"]
assert len(pairs) == len(descriptors) == 54
assert len({pair[0] for pair in pairs}) == 54
assert {pair[1] for pair in pairs} == set(descriptors)
members = {member["name"]: member for member in receipt["members"]}
assert len(members) == len(receipt["members"]) == 131
rows = []
for key_ref, reducer_ref in pairs:
    desc = descriptors[reducer_ref]
    reducer = node(reducer_ref, "reduce")
    assert reducer["operations"] == []
    assert desc["target_literal"] == node(reducer["target_ref"], "global")["literal"] == "torch._utils _rebuild_tensor_v2"
    args = desc["argument_refs"]
    assert node(desc["arguments_ref"], "tuple")["items"] == [args[key] for key in ("storage", "storage_offset", "size", "stride", "requires_grad", "backward_hooks")]
    assert not desc["metadata_argument_present"]
    persistent = node(args["storage"], "persistent_id")
    operand = node(persistent["operand_ref"], "tuple")
    assert len(operand["items"]) == 5
    tag_ref, type_ref, storage_key_ref, location_ref, elements_ref = operand["items"]
    assert scalar(tag_ref, "str") == "storage"
    storage_key = scalar(storage_key_ref, "str")
    assert storage_key.isascii() and storage_key.isdecimal() and len(storage_key) <= 3
    storage_count = scalar(elements_ref, "int")
    size, stride = ints(args["size"]), ints(args["stride"])
    assert len(size["values"]) == len(stride["values"]) > 0
    offset = scalar(args["storage_offset"], "int")
    hooks = node(args["backward_hooks"], "reduce")
    hook_args = node(hooks["arguments_ref"], "tuple")
    # Preserve the recorded hook invocation; never construct an OrderedDict.
    assert node(hooks["target_ref"], "global")["literal"] == "collections OrderedDict"
    assert hook_args["items"] == [] and hooks["operations"] == []
    count = math.prod(size["values"])
    extent = offset + 1 + sum((dim - 1) * step for dim, step in zip(size["values"], stride["values"]))
    contiguous_stride = []
    running = 1
    for dim in reversed(size["values"]):
        contiguous_stride.insert(0, running)
        running *= dim
    member_name = "archive/data/" + storage_key
    candidate_member = members.get(member_name)
    rows.append({
        "key_ref": key_ref, "key": scalar(key_ref, "str"), "reducer_ref": reducer_ref,
        "raw_descriptor": desc, "reducer_record": reducer,
        "storage": {"persistent_record": persistent, "operand_record": operand,
                    "tag_ref": tag_ref, "tag_literal": "storage", "type_ref": type_ref,
                    "type_global_literal": node(type_ref, "global")["literal"],
                    "key_ref": storage_key_ref, "key_literal": storage_key,
                    "location_ref": location_ref, "location_literal": scalar(location_ref, "str"),
                    "elements_ref": elements_ref, "elements_literal": storage_count},
        "size": size, "stride": stride,
        "storage_offset": {"ref": args["storage_offset"], "value": offset},
        "requires_grad": {"ref": args["requires_grad"], "value": scalar(args["requires_grad"], "bool")},
        "backward_hooks": {"ref": args["backward_hooks"], "record": hooks, "arguments_record": hook_args},
        "metadata_argument_present": False,
        "declaration_arithmetic_only": {"shape_product": count, "exclusive_max_element": extent,
                                       "shape_product_equals_declared_storage_elements": count == storage_count,
                                       "extent_within_declared_storage": 0 <= offset and extent <= storage_count,
                                       "stride_equals_row_major_product": stride["values"] == contiguous_stride},
        "candidate_member_name_association_not_storage_resolution": candidate_member,
        "candidate_member_bytes_equal_declared_elements_times_four": candidate_member is not None and candidate_member["uncompressed_bytes"] == storage_count * 4,
        "storage_bytes_read_or_validated": False,
    })

bindings, _ = read_json(BINDINGS, EXPECTED_BINDINGS, 32 * 1024)
source_facts = []
for item in bindings["bindings"]:
    if item["key"] not in SOURCE_KEYS:
        continue
    saved = SOURCE_ROOT / item["saved_file"]
    assert item["saved_file"].startswith("source/") and ".." not in item["saved_file"]
    allowed_reads.add(norm(saved))
    with saved.open("rb") as stream:
        raw = stream.read(128 * 1024 + 1)
    assert len(raw) == item["bytes"] <= 128 * 1024
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    source_facts.append({"key": item["key"], "saved_file": item["saved_file"], "bytes": len(raw), "sha256": item["sha256"]})
assert len(source_facts) == len(SOURCE_KEYS)

metadata_refs = [ref for ref in nodes if ref >= 3022]
state_metadata_refs = [ref for ref in nodes if 899 <= ref <= 987]
report = {
    "status": "receipt_only_static_mapping_not_loader_approval",
    "input_receipt": {"path": str(INPUT), "sha256": EXPECTED, "bytes": byte_count},
    "original_artifact_status": receipt["status"], "original_artifact_reason": receipt["reason"], "original_reader_exit": receipt["reader_exit"],
    "artifact_claims_from_receipt": receipt["artifact"],
    "projection_status": projection["status"], "selected_roots": projection["selected_root_associations"],
    "selected_nodes": len(nodes), "selected_examined_edges": projection["examined_edge_count_including_root_entries"],
    "state_dict_record": state, "state_dict_target_record": nodes[8], "state_dict_arguments_record": nodes[9],
    "state_metadata_records": [nodes[ref] for ref in state_metadata_refs],
    "recorded_config_metadata_nodes": [nodes[ref] for ref in metadata_refs],
    "tensor_rows": rows, "tensor_row_count": len(rows),
    "summary_of_declarations_only": {
        "storage_type_literals": sorted({row["storage"]["type_global_literal"] for row in rows}),
        "location_literals": sorted({row["storage"]["location_literal"] for row in rows}),
        "distinct_storage_key_literals": len({row["storage"]["key_literal"] for row in rows}),
        "sum_shape_products": sum(row["declaration_arithmetic_only"]["shape_product"] for row in rows),
        "sum_candidate_member_advertised_bytes": sum(row["candidate_member_name_association_not_storage_resolution"]["uncompressed_bytes"] for row in rows),
        "all_offsets_zero": all(row["storage_offset"]["value"] == 0 for row in rows),
        "all_requires_grad_false": all(row["requires_grad"]["value"] is False for row in rows),
        "all_declaration_arithmetic_checks_true": all(all(value for key, value in row["declaration_arithmetic_only"].items() if key not in {"shape_product", "exclusive_max_element"}) for row in rows),
        "all_candidate_bytes_equal_elements_times_four": all(row["candidate_member_bytes_equal_declared_elements_times_four"] for row in rows),
        "alias_semantics_resolved": False, "dtype_or_byte_order_validated": False,
    },
    "retained_source_bindings_sha256": EXPECTED_BINDINGS, "retained_source_hashes_rechecked": source_facts,
    "models_or_tensors_constructed": False, "checkpoint_opened": False,
    "note": "Final reference graph and tagged operations only. No historical argument snapshots, evaluated BUILD state, inferred defaults, artifact provenance or numerical qualification.",
}
serialized = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
assert len(serialized.encode("utf-8")) < 256 * 1024
table = ["# Recorded tensor descriptor associations", "", "All values below come from the safe JSON projection. Storage is a symbolic persistent-ID declaration; member bytes are ZIP advertised lengths from that same receipt. No tensor or storage payload was read. Full argument and node references are in mapping.json.", "", "| Key (key ref) | Tensor ref | Storage key | Size refs: values | Stride refs: values | Declared elements | Advertised bytes |", "| --- | ---: | --- | --- | --- | ---: | ---: |"]
for row in rows:
    table.append("| `" + row["key"] + "` (" + str(row["key_ref"]) + ") | " + str(row["reducer_ref"]) + " | " + row["storage"]["key_literal"] + " | " + str(row["size"]["ref"]) + ": " + str(row["size"]["values"]) + " | " + str(row["stride"]["ref"]) + ": " + str(row["stride"]["values"]) + " | " + str(row["storage"]["elements_literal"]) + " | " + str(row["candidate_member_name_association_not_storage_resolution"]["uncompressed_bytes"]) + " |")
assert time.monotonic() - started < 10
for name, text in (("mapping.json", serialized), ("tensor-table.md", "\n".join(table) + "\n")):
    with (ROOT / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
receipt_out = {"status": "completed_receipt_only_mapping", "exit": 0, "input_sha256": EXPECTED, "input_bytes": byte_count, "tensor_rows": len(rows), "source_hashes_rechecked": len(source_facts), "startup_binding": True, "isolated_no_site_no_bytecode": True, "elapsed_seconds": round(time.monotonic() - started, 6), "mapping_sha256": hashlib.sha256(serialized.encode()).hexdigest(), "mapping_bytes": len(serialized.encode())}
with (ROOT / "map-run01.json").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(json.dumps(receipt_out, indent=2) + "\n")
print(json.dumps(receipt_out))
