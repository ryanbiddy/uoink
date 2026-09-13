"""Run six reviewed assertions over selected AST code and explicit inert seams."""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

out = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument("label", choices=("b1-boundary01", "b2-candidate01"))
a = p.parse_args()
run = out / "runs" / a.label
run.mkdir(parents=True, exist_ok=False)
temporary = run / "temporary"
temporary.mkdir()
tempfile.tempdir = str(temporary)
heavy = frozenset({"whisper_runner", "server", "whisperx", "whisper", "faster_whisper",
                   "torch", "torchaudio", "pyannote", "transformers", "ctranslate2",
                   "tokenizers", "huggingface_hub", "safetensors", "numpy", "scipy"})
preloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
assert not preloaded, "heavy packages already loaded: " + repr(preloaded)
blocked_imports = []
blocked_audit_events = []


class StdlibOnlyFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        first = fullname.split(".")[0]
        if first in heavy or first not in sys.stdlib_module_names and first not in sys.builtin_module_names:
            blocked_imports.append(fullname)
            raise ImportError("Synthetic harness forbids dependency import: " + fullname)
        return None


finder = StdlibOnlyFinder()
sys.meta_path.insert(0, finder)
forbidden_live = "c:/users/hello/appdata/local/uoink/index.db"


def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "ctypes.dlopen"}:
        blocked_audit_events.append(event)
        raise PermissionError("Synthetic harness forbids network/process/native-library work")
    if event in {"open", "sqlite3.connect"} and isinstance(args[0], (str, bytes, os.PathLike)):
        name = os.fsdecode(args[0]).replace("\\", "/").lower()
        if forbidden_live in name:
            blocked_audit_events.append(event + ":protected-index")
            raise PermissionError("Synthetic harness forbids the live index")


sys.addaudithook(audit)
mapping = json.loads((out / "source-mapping.json").read_text(encoding="utf-8"))
source_key = "input" if a.label == "b1-boundary01" else "derivative"
source = out / mapping[source_key + "_relative_path"]
assert hashlib.sha256(source.read_bytes()).hexdigest() == mapping[source_key + "_sha256"]
tests = out / "constructor-contracts.py.txt"
assert hashlib.sha256(tests.read_bytes()).hexdigest() == mapping["extracted_test_sha256"]
namespace = {"__name__": "companion_b_selected_contracts", "__file__": str(tests)}
exec(compile(tests.read_text(encoding="utf-8"), str(tests), "exec"), namespace)
namespace["FW_SOURCE"] = source
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(namespace[name])
    for name in ("CompanionConstructorContracts", "EmptyBufferContracts"))
assert suite.countTestCases() == 10
observations = []


class Result(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        observations.append({"id": test.id(), "status": "passed", "boundary": getattr(test, "boundary_observation", None)})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        observations.append({"id": test.id(), "status": "failed", "trace": self._exc_info_to_string(error, test), "boundary": getattr(test, "boundary_observation", None)})

    def addError(self, test, error):
        super().addError(test, error)
        observations.append({"id": test.id(), "status": "error", "trace": self._exc_info_to_string(error, test), "boundary": getattr(test, "boundary_observation", None)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        observations.append({"id": test.id(), "status": "skipped", "reason": reason})


with (run / "tests.log").open("w", encoding="utf-8", newline="\n") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
postloaded = sorted(name for name in sys.modules if name.split(".")[0] in heavy)
guard_valid = not preloaded and not postloaded and finder in sys.meta_path
status = 0 if result.wasSuccessful() and guard_valid else 1
receipt = {
    "label": a.label, "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "test_protocol_sha256": hashlib.sha256(tests.read_bytes()).hexdigest(),
    "tests_run": result.testsRun, "passed": sum(row["status"] == "passed" for row in observations),
    "failed": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
    "observations": observations, "exit": status,
    "scope": "Selected constructor prefix only; all model/tokenizer/download seams are inert fakes.",
    "guard": {"preloaded_heavy": preloaded, "postloaded_heavy": postloaded,
              "blocked_imports": blocked_imports, "blocked_audit_events": blocked_audit_events,
              "finder_installed_at_finish": finder in sys.meta_path, "valid": guard_valid},
    "whole_dependency_module_executed": False, "real_tokenizer_or_model_executed": False,
    "python": sys.version, "flags": {"isolated": sys.flags.isolated, "no_site": sys.flags.no_site,
                                      "dont_write_bytecode": sys.flags.dont_write_bytecode},
    "finished_utc": datetime.now(timezone.utc).isoformat(),
}
(run / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({key: receipt[key] for key in ("label", "tests_run", "passed", "failed", "errors", "skipped", "exit", "guard")}))
raise SystemExit(status)
