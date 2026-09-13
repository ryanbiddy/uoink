"""Module names only; no lifecycle or model source is executed."""
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
HEAVY = frozenset({"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
                   "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"})
INITIAL = sorted(HEAVY.intersection(name.split(".")[0] for name in sys.modules))
ROWS = []
ATTEMPTS = []


def audit(event, args):
    if event == "import" and args[0].split(".")[0] in HEAVY:
        ATTEMPTS.append(args[0])
        raise RuntimeError("Prohibited import refused")
    if event == "open":
        path, mode, flags = args
        # Read flags: O_WRONLY 1, O_RDWR 2, O_APPEND 8, O_CREAT 256,
        # O_TRUNC 512, O_EXCL 1024 on this Windows runtime. No mode write.
        safe = type(path) is str and path.lower().replace("/", "\\").startswith(("c:\\python314\\lib\\", "c:\\python314\\dlls\\"))
        safe = safe and (mode is None or not any(char in mode for char in "wax+")) and not flags & (1 | 2 | 8 | 256 | 512 | 1024)
        if not safe:
            raise RuntimeError("Non-stdlib content operation refused")
    elif event.startswith(("os.", "ctypes.", "socket.", "subprocess.", "winreg.")):
        raise RuntimeError("Side effect refused: " + event)


sys.addaudithook(audit)
if not INITIAL:
    for name in ("dataclasses", "enum", "hashlib", "json", "math", "os", "pathlib", "sys", "threading", "time", "types"):
        try:
            __import__(name)
        except BaseException as exc:
            ROWS.append({"stage": name, "exception_type": type(exc).__name__, "attempted_heavy": list(ATTEMPTS)})
            break
        heavy = sorted(HEAVY.intersection(key.split(".")[0] for key in sys.modules))
        ROWS.append({"stage": name, "heavy_roots": heavy})
        if heavy:
            break
print(repr({"schema": "uoink.lifecycle-startup-names.v1", "initial_heavy_roots": INITIAL,
            "stages": ROWS, "attempted_heavy_imports": ATTEMPTS, "lifecycle_cases_executed": 0}))
