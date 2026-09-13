"""Inert wrapper receipt source. No ASR cases or package imports."""
import json
import os
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2", "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy"}
assert not HEAVY.intersection(name.split(".")[0] for name in sys.modules)
def audit(event, args):
    if event in ("open", "import") or event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        raise AssertionError("Inert wrapper child boundary refused " + event)
sys.addaudithook(audit)
print("Intentional inert child failure; no ASR qualification")
sys.exit(1)
