"""Guarded stdlib-only synthetic ZIP qualification; no actual artifact access."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("label")
label = parser.parse_args().label
if label not in {"b3w01"}:
    raise ValueError("Unbriefed label")
run = out / "runs" / label
run.mkdir(parents=True, exist_ok=False)
temporary = run / "temporary"
temporary.mkdir()
tempfile.tempdir = str(temporary)
heavy = {"whisper_runner", "server", "whisper", "whisperx", "faster_whisper", "ctranslate2", "torch",
         "torchaudio", "pyannote", "tokenizers", "transformers", "huggingface_hub", "safetensors", "numpy", "scipy"}
preloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
assert not preloaded
violations = []
class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in heavy or root not in sys.stdlib_module_names and root not in sys.builtin_module_names:
            violations.append("import:" + fullname)
            raise ImportError("Dependency import forbidden")
finder = Finder()
sys.meta_path.insert(0, finder)
def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "ctypes.dlopen"}:
        violations.append(event)
        raise PermissionError("Network/process/native-library operation forbidden")
    if event in {"open", "sqlite3.connect"} and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0]).replace("\\", "/").lower()
        if ("c:/users/hello/appdata/local/uoink/index.db" in path or "/installer/staging/" in path
                or "/_scratch/python313-graph-01/" in path or "/_scratch/b2-real-wheel-" in path
                or "/_scratch/b2-stdlib313-" in path or path.endswith(".onnx")):
            violations.append(event + ":forbidden-artifact")
            raise PermissionError("Actual artifact/live-index access forbidden")
sys.addaudithook(audit)
source = out / "build_faster_whisper_localassets_wheel.py"
spec = importlib.util.spec_from_file_location("reviewed_synthetic_wheel_builder", source)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
protocol = out / "tests-synthetic.py"
namespace = {"__name__": "synthetic_wheel_contracts", "__file__": str(protocol), "builder": builder, "WORK_DIR": out}
exec(compile(protocol.read_bytes(), str(protocol), "exec"), namespace)
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(namespace[name])
    for name in ("ArchiveContracts", "TransformContracts", "PathAndIdentityContracts"))
observations = []
class Result(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        observations.append({"id": test.id(), "status": "passed"})
    def addFailure(self, test, error):
        super().addFailure(test, error)
        observations.append({"id": test.id(), "status": "failed", "trace": self._exc_info_to_string(error, test)})
    def addError(self, test, error):
        super().addError(test, error)
        observations.append({"id": test.id(), "status": "error", "trace": self._exc_info_to_string(error, test)})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        observations.append({"id": test.id(), "status": "skipped", "reason": reason})
with (run / "tests.log").open("w", encoding="utf-8", newline="\n") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
postloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
guard_valid = not preloaded and not postloaded and not violations and finder in sys.meta_path
status = 0 if result.wasSuccessful() and guard_valid else 1
receipt = {"label": label, "tests_run": result.testsRun, "passed": sum(row["status"] == "passed" for row in observations),
    "failed": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped), "exit": status,
    "observations": observations, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(), "python": sys.version,
    "flags": {"isolated": sys.flags.isolated, "no_site": sys.flags.no_site, "dont_write_bytecode": sys.flags.dont_write_bytecode},
    "guard": {"preloaded_heavy": preloaded, "postloaded_heavy": postloaded, "violations": violations,
              "finder_installed_at_finish": finder in sys.meta_path, "valid": guard_valid},
    "actual_upstream_wheel_or_model_opened": False, "actual_wheel_built": False,
    "scope": "Synthetic ZIP/member/path inputs only, with opaque placeholder asset bytes; no package/model execution.",
    "finished_utc": datetime.now(timezone.utc).isoformat()}
(run / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({key: receipt[key] for key in ("label", "tests_run", "passed", "failed", "errors", "skipped", "exit", "guard")}))
raise SystemExit(status)
