"""Generated constants only; no checkpoint or model access."""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import types

HERE = Path(__file__).parent
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
NAMES = ("buffer_basis.py", "qualify_basis.py")
READS = {os.path.normcase(str(HERE / name)) for name in NAMES}
IMPORTS = set(sys.modules)
events = []


def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if (not isinstance(path, (str, bytes, os.PathLike))
                or os.path.normcase(os.path.abspath(os.fsdecode(path))) not in READS
                or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            events.append("open")
            raise AssertionError("Unapproved file access")
    elif event == "import" and args[0] not in IMPORTS:
        events.append("import")
        raise AssertionError("Unapproved import")
    elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in {"os.system", "os.startfile", "os.spawn", "os.fork", "os.exec"}:
        events.append(event)
        raise AssertionError("Unapproved native/network operation")


sys.addaudithook(audit)
raw = {name: (HERE / name).read_bytes() for name in NAMES}
hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
basis = types.ModuleType("buffer_basis")
exec(compile(raw["buffer_basis.py"], str(HERE / "buffer_basis.py"), "exec"), basis.__dict__)


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


DIRECT = tuple(bits(0.54 - 0.46 * math.cos(2 * math.pi * i / 250)) for i in range(125))
CENTERED = tuple(bits(0.54 + 0.46 * math.cos(math.pi * n / 250)) for n in range(-250, 0, 2))
IDEAL_N = tuple(bits(2 * math.pi * k / 16000) for k in range(-125, 0))
N_DIV_FIRST = tuple(bits(f32(k / 16000) * (2 * math.pi)) for k in range(-125, 0))
N_SCALAR_ROUNDED = tuple(bits(f32(k / 16000) * f32(2 * math.pi)) for k in range(-125, 0))
N_DOUBLE = tuple(bits((k / 16000) * (2 * math.pi)) for k in range(-125, 0))


def packed(words, endian="<"):
    return b"".join(struct.pack(endian + "I", value) for value in words)


def accept(window=DIRECT, time_vector=IDEAL_N, endian="<"):
    result = basis.compare_buffers(packed(window, endian), packed(time_vector, endian))
    assert result["orientation"] == ("little" if endian == "<" else "big")
    assert result["word_count"] == 250 and result["ulp_limit"] == 8
    assert not result["writer_authenticated"] and not result["real_profile_approved"] and not result["other_storages_validated"]


def refuse(window, time_vector, expected):
    try:
        basis.compare_buffers(window, time_vector)
    except basis.BasisRefusal as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError("Expected refusal")


def changed(words, index, value):
    result = list(words)
    result[index] = value
    return tuple(result)


cases = []


def register(name, callback):
    cases.append((name, callback))


register("all_250_generated_words_little", lambda: accept())
register("all_250_generated_words_big", lambda: accept(endian=">"))
register("centered_hamming_formula", lambda: accept(window=CENTERED))
register("n_division_rounded_first", lambda: accept(time_vector=N_DIV_FIRST))
register("n_scalar_and_division_rounded", lambda: accept(time_vector=N_SCALAR_ROUNDED))
register("n_double_intermediate", lambda: accept(time_vector=N_DOUBLE))
for buffer_index, buffer_name in ((0, "window"), (1, "time_vector")):
    for delta in (-8, 8):
        pair = [DIRECT, IDEAL_N]
        pair[buffer_index] = tuple(value + delta for value in pair[buffer_index])
        register(buffer_name + "_inclusive_ulp_" + str(delta), lambda pair=pair: accept(*pair))
    for delta in (-9, 9):
        pair = [DIRECT, IDEAL_N]
        pair[buffer_index] = changed(pair[buffer_index], 37, pair[buffer_index][37] + delta)
        register(buffer_name + "_outside_ulp_" + str(delta), lambda pair=pair: refuse(packed(pair[0]), packed(pair[1]), "Neither or both"))
    for label, value in (("positive_inf", 0x7F800000), ("negative_inf", 0xFF800000), ("quiet_nan", 0x7FC00001), ("sign_flip", (DIRECT if buffer_index == 0 else IDEAL_N)[0] ^ 0x80000000)):
        pair = [DIRECT, IDEAL_N]
        pair[buffer_index] = changed(pair[buffer_index], 0, value)
        register(buffer_name + "_" + label, lambda pair=pair: refuse(packed(pair[0]), packed(pair[1]), "Neither or both"))
register("opposite_orientations_disagree", lambda: refuse(packed(DIRECT), packed(IDEAL_N, ">"), "Neither or both"))
register("window_order_changed", lambda: refuse(packed(DIRECT[::-1]), packed(IDEAL_N), "Neither or both"))
register("time_order_changed", lambda: refuse(packed(DIRECT), packed(IDEAL_N[::-1]), "Neither or both"))
register("all_zero_buffers", lambda: refuse(bytes(500), bytes(500), "Neither or both"))
register("missing_window", lambda: refuse(None, packed(IDEAL_N), "immutable"))
register("mutable_window", lambda: refuse(bytearray(packed(DIRECT)), packed(IDEAL_N), "immutable"))
register("view_time_vector", lambda: refuse(packed(DIRECT), memoryview(packed(IDEAL_N)), "immutable"))
register("window_short", lambda: refuse(packed(DIRECT)[:-1], packed(IDEAL_N), "500 bytes"))
register("window_long", lambda: refuse(packed(DIRECT) + b"x", packed(IDEAL_N), "500 bytes"))
register("time_short", lambda: refuse(packed(DIRECT), packed(IDEAL_N)[:-1], "500 bytes"))
register("time_long", lambda: refuse(packed(DIRECT), packed(IDEAL_N) + b"x", "500 bytes"))


def decision_refusal(first, second):
    try:
        basis.exactly_one(first, second)
    except basis.BasisRefusal:
        return
    raise AssertionError("Decision guard did not refuse")


register("direct_helper_both_refuses_no_full_fixture_claim", lambda: decision_refusal(True, True))
register("direct_helper_neither_refuses", lambda: decision_refusal(False, False))
register("direct_helper_nonboolean_refuses", lambda: decision_refusal(1, False))


def static_scope():
    tree = ast.parse(raw["buffer_basis.py"])
    assert [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names] == ["math", "struct"]
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec", "compile", "__import__"} for node in ast.walk(tree))
    assert basis.ULP_LIMIT == 8 and basis.COUNT == 125 and basis.BYTE_COUNT == 500


register("static_scope_fixed_limits_no_io_or_target_execution", static_scope)
started = time.monotonic()
results = []
for name, callback in cases:
    try:
        callback()
        results.append({"case": name, "passed": True})
    except Exception as error:
        results.append({"case": name, "passed": False, "error": type(error).__name__ + ": " + str(error)[:200]})
assert len({item["case"] for item in results}) == len(results)
failed = sum(not item["passed"] for item in results)
report = {
    "scope": "Generated analytic constants only; no actual storage or model access",
    "input_sha256": hashes,
    "startup_binding_asserted": True,
    "passed": len(results) - failed,
    "failed": failed,
    "qualification_exit": 1 if failed else 0,
    "elapsed_seconds": round(time.monotonic() - started, 6),
    "cases": results,
    "synthetic_operation_order_maximum_ulp": {
        "centered_hamming_vs_direct": max(abs(a - b) for a, b in zip(CENTERED, DIRECT)),
        "n_division_rounded_vs_ideal": max(abs(a - b) for a, b in zip(N_DIV_FIRST, IDEAL_N)),
        "n_division_and_scalar_rounded_vs_ideal": max(abs(a - b) for a, b in zip(N_SCALAR_ROUNDED, IDEAL_N)),
        "n_double_intermediate_vs_ideal": max(abs(a - b) for a, b in zip(N_DOUBLE, IDEAL_N)),
    },
    "historical_backend_bound_proven": False,
    "real_profile_approved": False,
    "actual_storage_read": False,
    "unexpected_audit_events": events,
}
assert not events
encoded = json.dumps(report, indent=2)
assert len(encoded.encode("utf-8")) < 32768
print(encoded)
raise SystemExit(report["qualification_exit"])
