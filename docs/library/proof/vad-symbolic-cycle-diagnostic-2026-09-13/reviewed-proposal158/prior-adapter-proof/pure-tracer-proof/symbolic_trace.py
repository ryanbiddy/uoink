"""Strict protocol-2 syntax-to-data tracing. No unpickling or target execution."""
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


def require(condition, reason):
    if not condition:
        raise TraceRefusal(reason)


class _Trace:
    def __init__(self, tight_limits):
        self.limits = DEFAULT_LIMITS.copy()
        if tight_limits is not None:
            require(type(tight_limits) is dict, "Limits must be a plain dictionary")
            for name, value in tight_limits.items():
                require(type(name) is str and name in self.limits, "Unknown limit")
                require(type(value) is int and 1 <= value <= self.limits[name], "Limits may only tighten fixed bounds")
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
        require((time.monotonic() - self.started) * 1000 <= self.limits["time_ms"], "Cooperative time limit exceeded")

    def text(self, value, global_literal=False):
        require(type(value) is str, "Nonliteral string argument")
        size = len(value.encode("utf-8"))
        require(size <= self.limits["string_bytes"], "String byte limit exceeded")
        if global_literal:
            require(0 < size <= self.limits["global_bytes"], "GLOBAL literal byte limit exceeded")
        self.string_bytes += size
        require(self.string_bytes <= self.limits["total_string_bytes"], "Total string byte limit exceeded")
        return value

    def node(self, kind, **fields):
        self.tick()
        require(len(self.nodes) < self.limits["nodes"], "Node limit exceeded")
        ref = len(self.nodes)
        self.nodes.append({"id": ref, "kind": kind, **fields})
        self.edges.append([])
        return ref

    def connect(self, parent, children):
        require(self.edge_count + len(children) <= self.limits["edges"], "Edge limit exceeded")
        self.edges[parent].extend(children)
        self.edge_count += len(children)

    def push(self, ref):
        require(len(self.stack) < self.limits["stack"], "Stack limit exceeded")
        self.stack.append(ref)

    def pop(self):
        require(self.stack and self.stack[-1] != MARK, "Stack operand missing or MARK used as value")
        return self.stack.pop()

    def peek(self):
        require(self.stack and self.stack[-1] != MARK, "Stack target missing or MARK used as value")
        return self.stack[-1]

    def marked(self):
        index = len(self.stack) - 1
        while index >= 0 and self.stack[index] != MARK:
            self.tick()
            index -= 1
        require(index >= 0, "MARK missing")
        values = self.stack[index + 1:]
        del self.stack[index:]
        self.marks -= 1
        return values

    def collection(self, kind, values):
        require(len(values) <= self.limits["collection"], "Collection item limit exceeded")
        ref = self.node(kind, items=list(values))
        self.connect(ref, values)
        return ref

    def key(self, ref):
        node = self.nodes[ref]
        kind = node["kind"]
        require(kind in ("str", "int", "float", "bool", "none"), "Unsupported nonprimitive dictionary key")
        if kind == "str":
            return ("str", node["value"])
        if kind == "none":
            return ("none", None)
        # Builtin-only equality unifies True, 1 and 1.0, and also signed zero.
        return ("number", node["value"])

    def capacity(self, target, count):
        updated = self.item_counts.get(target, 0) + count
        require(updated <= self.limits["collection"], "Collection item limit exceeded")
        self.item_counts[target] = updated

    def symbolic_operation(self, target, operation):
        operations = self.nodes[target]["operations"]
        require(len(operations) < self.limits["collection"], "Symbolic operation limit exceeded")
        operations.append(operation)

    def sequence(self, target, values, opcode):
        kind = self.nodes[target]["kind"]
        require(kind in ("list", "reduce", "newobj"), "Sequence mutation target is unsupported")
        self.capacity(target, len(values))
        if kind == "list":
            self.nodes[target]["items"].extend(values)
        else:
            require(self.families.get(target, "sequence") == "sequence", "Mixed symbolic mutation families")
            self.families[target] = "sequence"
            self.symbolic_operation(target, {"opcode": opcode, "item_refs": list(values)})
        self.connect(target, values)

    def mapping(self, target, values, opcode):
        kind = self.nodes[target]["kind"]
        require(kind in ("dict", "reduce", "newobj"), "Mapping mutation target is unsupported")
        require(len(values) % 2 == 0, "Odd mapping item count")
        self.capacity(target, len(values) // 2)
        known = self.keys.setdefault(target, set())
        pairs = []
        for index in range(0, len(values), 2):
            self.tick()
            key_ref, value_ref = values[index:index + 2]
            canonical = self.key(key_ref)
            require(canonical not in known, "Duplicate dictionary key")
            known.add(canonical)
            pairs.append([key_ref, value_ref])
        if kind == "dict":
            self.nodes[target]["entries"].extend(pairs)
        else:
            require(self.families.get(target, "mapping") == "mapping", "Mixed symbolic mutation families")
            self.families[target] = "mapping"
            self.symbolic_operation(target, {"opcode": opcode, "entries": pairs})
        self.connect(target, values)

    def memo_index(self, value):
        require(type(value) is int and 0 <= value < self.limits["memo"], "Memo index outside bound")
        return value

    def apply_opcode(self, name, argument):
        if name == "MARK":
            require(self.marks < self.limits["marks"], "MARK limit exceeded")
            self.push(MARK)
            self.marks += 1
        elif name in ("BININT", "BININT1", "BININT2"):
            require(type(argument) is int and argument.bit_length() <= 64, "Integer outside bound")
            self.push(self.node("int", value=argument))
        elif name == "BINFLOAT":
            require(type(argument) is float and -1.7976931348623157e308 <= argument <= 1.7976931348623157e308,
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
            require(index not in self.memo, "Duplicate memo assignment")
            self.memo[index] = self.peek()
        elif name in ("BINGET", "LONG_BINGET"):
            index = self.memo_index(argument)
            require(index in self.memo, "Missing memo reference")
            self.push(self.memo[index])
        elif name in ("REDUCE", "NEWOBJ"):
            args, target = self.pop(), self.pop()
            require(self.nodes[args]["kind"] == "tuple", "Symbolic arguments must be a literal tuple")
            require(self.nodes[target]["kind"] == "global", "Symbolic target must be a literal GLOBAL")
            ref = self.node("reduce" if name == "REDUCE" else "newobj",
                            target_ref=target, arguments_ref=args, operations=[])
            self.connect(ref, [target, args])
            self.push(ref)
        elif name == "BUILD":
            state = self.pop()
            target = self.peek()
            require(self.nodes[target]["kind"] in ("reduce", "newobj"), "BUILD target must be a symbolic result")
            require(target not in self.built, "Duplicate BUILD state")
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
                require(len(frames) <= self.limits["depth"], "Graph depth limit exceeded")
                ref, index = frames[-1]
                if index < len(self.edges[ref]):
                    child = self.edges[ref][index]
                    frames[-1][1] += 1
                    require(colours[child] != 1, "Reference cycle refused")
                    if not colours[child]:
                        colours[child] = 1
                        frames.append([child, 0])
                else:
                    heights[ref] = 1 + max((heights[child] for child in self.edges[ref]), default=0)
                    require(heights[ref] <= self.limits["depth"], "Graph depth limit exceeded")
                    colours[ref] = 2
                    frames.pop()

    def descriptors(self):
        result = []
        for node in self.nodes:
            self.tick()
            if node["kind"] != "reduce" or self.nodes[node["target_ref"]]["literal"] != TENSOR_LITERAL:
                continue
            arguments = self.nodes[node["arguments_ref"]]["items"]
            require(len(arguments) in (6, 7), "Tensor reducer descriptor arity is unsupported")
            require(len(result) < self.limits["descriptors"], "Tensor descriptor limit exceeded")
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
        require(selected, "No selected literal root metadata associations")
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
        require(len(encoded) <= self.limits["output_bytes"], "Output byte limit exceeded")
        self.tick()
        return result


def trace_pickle_metadata(payload, *, tight_limits=None):
    require(type(payload) is bytes, "Input must be plain immutable bytes")
    trace = _Trace(tight_limits)
    require(3 <= len(payload) <= trace.limits["input_bytes"], "Input byte limit exceeded or input too short")
    root = None
    stopped = False
    try:
        for opcode, argument, position in pickletools.genops(payload):
            trace.tick()
            name = opcode.name
            require(name in ALLOWED_OPS, "Unsupported opcode: " + name)
            trace.opcount += 1
            require(trace.opcount <= trace.limits["opcodes"], "Opcode limit exceeded")
            trace.opcode_counts[name] = trace.opcode_counts.get(name, 0) + 1
            if trace.opcount == 1:
                require(name == "PROTO" and argument == 2 and position == 0, "Exactly one initial PROTO 2 is required")
                continue
            require(name != "PROTO", "Repeated protocol declaration")
            if name == "STOP":
                require(position + 1 == len(payload), "Trailing bytes after STOP")
                require(len(trace.stack) == 1 and trace.marks == 0 and trace.stack[0] != MARK,
                        "STOP requires one complete root and no remaining stack or MARK")
                root = trace.stack[0]
                require(trace.nodes[root]["kind"] == "dict", "Root must be a literal dictionary")
                stopped = True
                break
            trace.apply_opcode(name, argument)
    except (ValueError, UnicodeError, OverflowError) as exc:
        raise TraceRefusal("Malformed pickle syntax: " + type(exc).__name__) from None
    require(stopped, "STOP missing")
    trace.validate_graph()
    return trace.output(root)
