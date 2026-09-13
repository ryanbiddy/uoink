"""Reviewed-only future inert qualification. Source preparation is not a run."""
import ast
import builtins
import collections
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import sys
import time
import types
import unittest

# Preload only stdlib dependencies used by the owned builder/verifier before
# installing the stricter source-file guard. -I -S excludes site packages.
import base64
import binascii
import csv
import email.parser
import email.policy
import stat
import struct
import tomllib
import zipfile
import math

BASE = Path(__file__).resolve().parent
assert sys.argv[1:] == ["qualification01"]
assert sys.version_info[:2] == (3, 14)
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert "site" not in sys.modules
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
assert os.environ.get("PYANNOTE_METRICS_ENABLED") == "0"
RUN = BASE / "runs" / "qualification01"
RUN.mkdir(parents=True, exist_ok=False)
GENERATED = RUN / "generated"
GENERATED.mkdir()
START = time.monotonic()

manifest_raw = (BASE / "INPUT-HASHES.json").read_bytes()
assert len(manifest_raw) <= 262144
manifest = json.loads(manifest_raw)
assert type(manifest) is list and 1 <= len(manifest) <= 100
expected = {}
for row in manifest:
    name = row["path"]
    assert type(name) is str and "\\" not in name and not name.startswith("/")
    assert all(p not in {"", ".", ".."} for p in name.split("/"))
    path = BASE.joinpath(*name.split("/"))
    assert path not in expected and not path.is_symlink()
    expected[path] = row
expected[BASE / "INPUT-HASHES.json"] = {"path": "INPUT-HASHES.json",
    "bytes": len(manifest_raw), "sha256": hashlib.sha256(manifest_raw).hexdigest()}

HEAVY = {"whisper_runner", "server", "whisper", "whisperx", "faster_whisper", "ctranslate2", "torch",
         "torchaudio", "pyannote", "tokenizers", "transformers", "huggingface_hub", "safetensors",
         "numpy", "scipy", "nltk", "torchcodec"}
preloaded = sorted(n for n in sys.modules if n.split(".")[0] in HEAVY)
assert not preloaded
violations, observations, forbidden_calls = [], [], []
forbidden_code = {}
calls = collections.Counter()
tracked = {}
stdlib = Path(sys.base_prefix).resolve()


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in HEAVY or root not in sys.stdlib_module_names | set(sys.builtin_module_names):
            violations.append({"event": "import", "name": fullname})
            raise ImportError("Non-stdlib package import is forbidden")


finder = Finder()
sys.meta_path.insert(0, finder)


def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "ctypes.dlopen", "sqlite3.connect"}:
        violations.append({"event": event})
        raise PermissionError("Network, child processes, native libraries and databases are forbidden")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        mode, flags = args[1], args[2]
        writing = isinstance(mode, str) and any(c in mode for c in "wax+") or isinstance(flags, int) and bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        allowed = inside(path, RUN) if writing else path in expected or inside(path, RUN) or inside(path, stdlib)
        blocked_suffix = path.suffix.lower() in {".whl", ".npz", ".bin", ".pt", ".pth", ".db", ".pkl",
                                               ".pickle", ".onnx", ".safetensors", ".dll", ".pyd"}
        if not allowed or blocked_suffix:
            violations.append({"event": event, "path": str(path), "writing": bool(writing)})
            raise PermissionError("File access outside fixed text inputs/fresh synthetic output")
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink"}:
        values = args[:2] if event in {"os.rename", "os.link", "os.symlink"} else args[:1]
        for value in values:
            if isinstance(value, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(value)).absolute()
                if not inside(path, RUN) or event in {"os.link", "os.symlink"}:
                    violations.append({"event": event, "path": str(path)})
                    raise PermissionError("Mutation outside fresh synthetic run")


sys.addaudithook(audit)


def profile(frame, event, arg):
    if event == "call":
        code = frame.f_code
        if code in forbidden_code:
            forbidden_calls.append(forbidden_code[code])
            raise RuntimeError("Unbriefed initializer/main execution")
        if code in tracked:
            calls[tracked[code]] += 1


sys.setprofile(profile)


def bound(name):
    path = BASE / name
    row = expected[path]
    raw = path.read_bytes()
    assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    return raw


def namespace(name):
    result = {"__name__": "owned_inert_" + name.replace(".", "_"), "__file__": str(BASE / name)}
    exec(compile(bound(name), str(BASE / name), "exec"), result)
    return result


class Result(unittest.TextTestResult):
    def _exc_info_to_string(self, error, test):
        kind, value, trace = error
        frames = []
        while trace is not None:
            frames.append({"file": trace.tb_frame.f_code.co_filename, "line": trace.tb_lineno,
                           "function": trace.tb_frame.f_code.co_name})
            trace = trace.tb_next
        return json.dumps({"type": kind.__name__, "message": str(value), "frames": frames})
    def addSuccess(self, test):
        super().addSuccess(test)
        observations.append({"id": test.id(), "status": "passed"})
    def addFailure(self, test, error):
        super().addFailure(test, error)
        observations.append({"id": test.id(), "status": "failed", "detail": self._exc_info_to_string(error, test)})
    def addError(self, test, error):
        super().addError(test, error)
        observations.append({"id": test.id(), "status": "error", "detail": self._exc_info_to_string(error, test)})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        observations.append({"id": test.id(), "status": "skipped", "reason": reason})


fatal = None
result = None
diagnostic = None
case_ids = []
before = {}
after = {}
try:
    for path, row in expected.items():
        before[row["path"]] = hashlib.sha256(bound(row["path"])).hexdigest()
    B = namespace("build_wheel.py")
    V = namespace("verify_wheel.py")
    forbidden_code.update({B["main"].__code__: "builder.main", V["main"].__code__: "verifier.main"})
    Q = types.SimpleNamespace(**namespace("qualification_seams.py"))
    recipe_raw = bound("inputs/WHEEL-RECIPE.json")
    recipe = json.loads(recipe_raw)
    names = {r["input"] for r in recipe["fixed_members"]} | {"after/pyproject.toml", "after/README-UOINK.md"}
    files = {n: bound("inputs/" + n) for n in names}
    # Verify the retained tests and selected bodies before defining/running them.
    assert hashlib.sha256(bound("pipeline/tests.py")).hexdigest() == "c49215e080c1d6687f20b9e5128cce60e5ef543dab2d0c7985ca1ff44077ba63"
    assert hashlib.sha256(bound("pipeline/seams.py")).hexdigest() == "a649c31edf1584a8641c5e409d802da73264d0aaee1ff4b2231715183c252b09"
    assert bound("pipeline/inputs/asr.py.txt") == files["after/whisperx/asr.py"]
    binding = json.loads(bound("pipeline/SOURCE-BINDINGS.json"))
    trees = {r["file"]: ast.parse(bound("pipeline/inputs/" + r["file"])) for r in binding["bindings"]}
    for row in binding["selected_bodies"]:
        nodes = trees[row["file"]].body
        if row["class"] is not None:
            nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == row["class"]).body
        fn = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == row["method"])
        body = ast.dump(ast.Module(body=fn.body, type_ignores=[]), include_attributes=False).encode()
        assert hashlib.sha256(body).hexdigest() == row["body_ast_sha256"]
    seams = types.SimpleNamespace(**namespace("pipeline/seams.py"))
    selected = seams.load_selected(BASE / "pipeline")
    forbidden_code[selected["Pipeline"].__init__.__code__] = "captured Pipeline.__init__"
    for cls, name in selected["selected_methods"]:
        method = getattr(selected[cls], name)
        method = getattr(method, "__wrapped__", method)
        tracked[method.__code__] = cls + "." + name
    old = {"__name__": "synthetic_pipeline_contracts", "S": seams, "N": selected}
    exec(compile(bound("pipeline/tests.py"), str(BASE / "pipeline/tests.py"), "exec"), old)
    new = {"__name__": "owned_builder_contracts", "Q": Q, "B": B, "V": V,
           "FILES": files, "RECIPE": recipe_raw, "GENERATED": GENERATED}
    exec(compile(bound("tests_contracts.py"), str(BASE / "tests_contracts.py"), "exec"), new)
    classes = [old[n] for n in ("PipelineContracts", "ParameterContracts", "IteratorContracts")]
    classes += [new[n] for n in ("BuilderContracts", "LoaderContracts", "ClosedEntryContracts", "WaveformContracts")]
    suites = [unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in classes]
    case_ids = [test.id() for suite in suites for test in suite]
    assert len(case_ids) == 50 and len(set(case_ids)) == 50
    with (RUN / "tests.log").open("x", encoding="utf-8", newline="\n") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(unittest.TestSuite(suites))
    # Retain the optional direct-list observation separately; no pass credit.
    pipeline = old["make_pipeline"]()[0]
    try:
        value = pipeline([])
        diagnostic = {"scope": "direct empty list", "status": "RETURNED_DIAGNOSTIC_ONLY", "value": repr(value)}
    except Exception as error:
        diagnostic = {"scope": "direct empty list", "status": "UNACCEPTED_OPTIONAL_API_DEFECT",
                      "type": type(error).__name__, "message": str(error)}
    for path, row in expected.items():
        after[row["path"]] = hashlib.sha256(bound(row["path"])).hexdigest()
except Exception as error:
    fatal = {"type": type(error).__name__, "message": str(error)}

postloaded = sorted(n for n in sys.modules if n.split(".")[0] in HEAVY)
elapsed = time.monotonic() - START
guard = {"preloaded_heavy": preloaded, "postloaded_heavy": postloaded, "violations": violations,
         "forbidden_calls": forbidden_calls, "finder_installed": finder in sys.meta_path,
         "profile_installed": sys.getprofile() is profile, "startup_binding": True}
guard["valid"] = not preloaded and not postloaded and not violations and not forbidden_calls and guard["finder_installed"] and guard["profile_installed"]
success = (result is not None and result.wasSuccessful() and result.testsRun == 50
           and len(observations) == 50 and before == after and bool(before)
           and guard["valid"] and fatal is None and elapsed <= 60)
receipt = {"status": "PASS" if success else "FAIL", "exit": 0 if success else 1,
           "tests_run": result.testsRun if result else 0, "passed": sum(r["status"] == "passed" for r in observations),
           "failed": len(result.failures) if result else 0, "errors": len(result.errors) if result else 0,
           "skipped": len(result.skipped) if result else 0, "subtests": 0,
           "case_ids": case_ids, "observations": observations, "fatal": fatal, "guard": guard,
           "input_hashes_before": before, "input_hashes_after": after, "inputs_unchanged": before == after and bool(before),
           "selected_method_calls": dict(calls), "optional_diagnostic": diagnostic,
           "elapsed_seconds": elapsed, "finished_utc": datetime.now(timezone.utc).isoformat(),
           "scope": "50 planned inert contracts; exact selected AST bodies, unchanged23 Pipeline assertions, fake arrays/tensors/ports; generated text wheel bytes only in memory. No package/model/native-runtime execution, installation or real asset read."}
with (RUN / "result.json").open("xb") as stream:
    stream.write((json.dumps(receipt, indent=2) + "\n").encode())
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps({k: receipt[k] for k in ("status", "exit", "tests_run", "passed", "failed", "errors", "skipped", "fatal", "guard", "elapsed_seconds")}))
raise SystemExit(receipt["exit"])
