"""Retain the actual process exit and exact command for each planned arm."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

out = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument("label", choices=("b1-boundary01", "b2-candidate01"))
a = p.parse_args()
launch = out / ("launch-" + a.label)
launch.mkdir(exist_ok=False)
if a.label == "b2-candidate01":
    assert (out / "B1-BOUNDARY-REPAIR-REASON-2026-09-13.md").is_file()
env = os.environ.copy()
removed = []
for key in list(env):
    upper = key.upper()
    if (re.search("API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL", upper)
            or upper.startswith(("ANTHROPIC_", "OPENAI_", "GOOGLE_API_", "GEMINI_API_", "XAI_", "GROK_", "CLAUDE_CODE_USE_"))
            or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "PYTHONPATH", "PYTHONHOME"}):
        removed.append(key)
        env.pop(key)
env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1",
           PYTHONDONTWRITEBYTECODE="1", IG_FORBIDDEN_LIVE=r"C:\Users\hello\AppData\Local\Uoink\index.db")
command = [r"C:\Python314\python.exe", "-I", "-S", "-B", str(out / "harness.py"), a.label]
sources = [out / name for name in ("harness.py", "constructor-contracts.py.txt", "source-mapping.json", "launch.py")]
hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
(launch / "plan.json").write_text(json.dumps({"command": command, "cwd": str(out), "input_hashes": hashes,
                                              "scrubbed_variable_names": sorted(removed),
                                              "started_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8", newline="\n")
with (launch / "console.log").open("w", encoding="utf-8", newline="\n") as log:
    result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == hashes[str(path)] for path in sources)
(launch / "result.json").write_text(json.dumps({"exit": result.returncode, "inputs_unchanged": unchanged,
                                                "finished_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8", newline="\n")
print((launch / "console.log").read_text(encoding="utf-8"))
raise SystemExit(result.returncode if unchanged else 99)
