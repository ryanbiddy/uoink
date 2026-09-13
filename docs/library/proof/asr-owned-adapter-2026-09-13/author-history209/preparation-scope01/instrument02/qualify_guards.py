"""Four inert owner-identity checks; never loads the ASR harness or resolver."""
import hashlib
import json
import os
import sys
import types

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ("trap-installation.py.txt", "trap-final.py.txt", "PREPARATION-BINDINGS.json")
READS = {os.path.normcase(os.path.join(HERE, name)) for name in NAMES}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2", "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy"}
assert not HEAVY.intersection(name.split(".")[0] for name in sys.modules)
DENIALS = []


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = isinstance(path, str) and os.path.normcase(os.path.abspath(path)) in READS
        allowed = allowed and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event == "import" or event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    if not allowed:
        DENIALS.append(event)
        raise AssertionError("Guard instrument boundary refused " + event)


sys.addaudithook(audit)
raw = {}
for name in NAMES:
    with open(os.path.join(HERE, name), "rb") as stream:
        raw[name] = stream.read()
bindings = json.loads(raw["PREPARATION-BINDINGS.json"])
hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
assert hashes["trap-installation.py.txt"] == bindings["trap_installation_sha256"]
assert hashes["trap-final.py.txt"] == bindings["trap_final_sha256"]
install = compile(raw["trap-installation.py.txt"], "reviewed-trap-installation", "exec")
final = compile(raw["trap-final.py.txt"], "reviewed-trap-final", "exec")
results = []
for name in ("complete", "replaced", "removed", "missing_registry_entry"):
    context = {"Path": types.SimpleNamespace(), "os": types.SimpleNamespace(), "DENIED": [],
               "heavy_loaded": [], "real_approval_closed": True, "real_functions_unchanged": True,
               "adapter_globals_restored": True}
    try:
        exec(install, context)
        if name == "replaced":
            context["Path"].stat = object()
        elif name == "removed":
            del context["Path"].stat
        elif name == "missing_registry_entry":
            context["METADATA_TRAPS"] = context["METADATA_TRAPS"][:-1]
        exec(final, context)
        expected_ok = name == "complete"
        expected_labels = ["Path.stat"] if name in ("replaced", "removed") else []
        expected_count = 10 if name == "missing_registry_entry" else 11
        assert context["metadata_traps_installed"] is expected_ok
        assert context["guard_valid"] is expected_ok
        assert context["metadata_trap_mismatches"] == expected_labels
        assert len(context["METADATA_TRAPS"]) == expected_count
        assert not context["DENIED"]
        results.append({"name": name, "passed": True, "installed": context["metadata_traps_installed"],
                        "mismatches": context["metadata_trap_mismatches"], "count": len(context["METADATA_TRAPS"])})
    except Exception as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)})
heavy_loaded = sorted(HEAVY.intersection(name.split(".")[0] for name in sys.modules))
passed = sum(row["passed"] for row in results)
valid = not DENIALS and not heavy_loaded
exit_code = 0 if passed == 4 and len(results) == 4 and valid else 1
print(json.dumps({"schema": "uoink.asr-instrument-traps.v1", "cases": results, "passed": passed,
                  "failed": len(results) - passed, "guard_denials": DENIALS, "heavy_roots_loaded": heavy_loaded,
                  "guard_valid": valid, "input_sha256": hashes, "asr_cases_executed": 0,
                  "native_exit": exit_code}, indent=2))
sys.exit(exit_code)
