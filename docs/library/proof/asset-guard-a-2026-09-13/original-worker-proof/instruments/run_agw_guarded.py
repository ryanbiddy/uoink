"""Launch only the authorized AST and existing-suite union in the native verifier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

p = argparse.ArgumentParser()
p.add_argument("label", choices=("agw01", "agw02"))
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
checkout = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
assert root == Path(r"E:\AI\projects\uoink\worktrees\asset-guard-a")
native = checkout / "_scratch/ig-native/Scripts/python.exe"
verifier = checkout / "_scratch/integrator_verify.py"
plugin = root / "_scratch/agw_heavy_import_guard.py"
new_test = "tests/test_whisper_cache_consent.py"
regressions = [
    "tests/test_phase6_evaluation.py", "tests/test_podcast_background_jobs.py",
    "tests/test_podcast_watch.py", "tests/test_podcast_workflow_truth.py",
    "tests/test_library_adapters.py", "tests/test_packaged_decoder_loader.py",
    "tests/test_installer_dependency_lock.py",
]
selectors = [new_test] + (regressions if a.label == "agw02" else [])
out = root / "_scratch" / (a.label + "-launch")
out.mkdir(exist_ok=False)
env = os.environ.copy()
scrubbed = []
for key in list(env):
    upper = key.upper()
    if (re.search(r"API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", upper)
            or upper.startswith("CLAUDE_CODE_USE_")
            or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}):
        scrubbed.append(key)
        env.pop(key)
env.update({
    "LOCALAPPDATA": r"C:\Users\hello\AppData\Local",
    "IG_FORBIDDEN_LIVE": r"C:\Users\hello\AppData\Local\Uoink\index.db",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false", "WANDB_MODE": "offline",
    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "AGW_HEAVY_GUARD_RECEIPT": str(out / "heavy-import-guard.json"),
})
command = [str(native), "-B", str(verifier), "--root", str(root), "--label", a.label,
           *selectors, "-p", "_scratch.agw_heavy_import_guard"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


input_hashes = {str(path): digest(path) for path in (
    Path(__file__), verifier, plugin, root / "whisper_runner.py", *(root / s for s in selectors))}
plan = {
    "started_utc": datetime.now(timezone.utc).isoformat(), "command": command,
    "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest(),
    "cwd": str(root), "input_hashes": input_hashes,
    "scrubbed_variable_names": sorted(scrubbed),
    "forbidden_live_string": env["IG_FORBIDDEN_LIVE"],
    "offline_flags": {key: env[key] for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE")},
    "profile": "Real existing suites; explicit heavy-import blocker; no native/model credit.",
}
(out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
print("START", a.label, flush=True)
with (out / "launcher.log").open("w", encoding="utf-8") as log:
    result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
after_hashes = {path: digest(Path(path)) for path in input_hashes}
receipt = {
    "finished_utc": datetime.now(timezone.utc).isoformat(), "exit": result.returncode,
    "inputs_unchanged": after_hashes == input_hashes, "after_input_hashes": after_hashes,
}
(out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print("END", a.label, "exit", result.returncode, "inputs unchanged", receipt["inputs_unchanged"], flush=True)
print("\n".join((out / "launcher.log").read_text(encoding="utf-8").splitlines()[-21:]), flush=True)
raise SystemExit(result.returncode if receipt["inputs_unchanged"] else 99)
