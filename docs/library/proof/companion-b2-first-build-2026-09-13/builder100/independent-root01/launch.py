"""Retain commands and actual child exits for bounded synthetic qualification."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

out = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument("label", choices=("bw01", "bw02", "bw03"))
label = p.parse_args().label
if label == "bw02":
    assert (out / "REPAIR-BEFORE-BW02.md").is_file()
if label == "bw03":
    assert (out / "REPAIR-BEFORE-BW03.md").is_file()
destination = out / ("launch-" + label)
destination.mkdir(exist_ok=False)
env = os.environ.copy()
removed = []
for key in list(env):
    upper = key.upper()
    if (re.search("API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL", upper)
        or upper.startswith(("ANTHROPIC_", "OPENAI_", "GOOGLE_API_", "GEMINI_API_", "XAI_", "GROK_", "CLAUDE_CODE_USE_"))
        or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "PYTHONPATH", "PYTHONHOME"}):
        removed.append(key)
        env.pop(key)
env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1",
           IG_FORBIDDEN_LIVE=r"C:\Users\hello\AppData\Local\Uoink\index.db")
command = [r"C:\Python314\python.exe", "-I", "-S", "-B", str(out / "run-synthetic.py"), label]
paths = [out / name for name in ("build_faster_whisper_localassets_wheel.py", "tests-synthetic.py", "run-synthetic.py", "launch.py")]
paths.extend(path for name in ("recipe", "fixtures") for path in sorted((out / name).rglob("*")) if path.is_file())
hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
(destination / "plan.json").write_text(json.dumps({"command": command, "cwd": str(out), "input_hashes": hashes,
    "scrubbed_variable_names": sorted(removed), "started_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8", newline="\n")
with (destination / "console.log").open("w", encoding="utf-8", newline="\n") as log:
    completed = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
unchanged = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
(destination / "result.json").write_text(json.dumps({"exit": completed.returncode, "inputs_unchanged": unchanged,
    "finished_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8", newline="\n")
print((destination / "console.log").read_text(encoding="utf-8"))
raise SystemExit(completed.returncode if unchanged else 99)
