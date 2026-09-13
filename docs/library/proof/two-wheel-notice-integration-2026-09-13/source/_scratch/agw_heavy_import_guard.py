"""Explicit guard for synthetic tests; grants no native/model qualification."""
import importlib.abc
import json
import os
from pathlib import Path
import sys

BLOCKED = frozenset({
    "whisperx", "whisper", "faster_whisper", "torch", "torchaudio", "pyannote",
    "transformers", "ctranslate2", "tokenizers", "huggingface_hub",
})
already_loaded = sorted(name for name in sys.modules if name.split(".")[0] in BLOCKED)
if already_loaded:
    raise RuntimeError("Heavy imports occurred before guard startup: " + ", ".join(already_loaded))
attempts = []


class HeavyImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            attempts.append(fullname)
            raise ImportError("Synthetic guard forbids actual heavy import: " + fullname)
        return None


_finder = HeavyImportBlocker()
sys.meta_path.insert(0, _finder)


def pytest_sessionfinish(session, exitstatus):
    destination = Path(os.environ["AGW_HEAVY_GUARD_RECEIPT"])
    destination.write_text(json.dumps({
        "profile": "synthetic-import-blocked-no-native-model-credit",
        "already_loaded_at_startup": already_loaded,
        "blocked_import_attempts": attempts,
        "pytest_exitstatus": int(exitstatus),
        "guard_installed_at_finish": _finder in sys.meta_path,
    }, indent=2) + "\n", encoding="utf-8")
