"""Run receipt preparation in the interpreter that owns its permanent audit hook."""
import json
from pathlib import Path
import subprocess
import sys


def prepare_receipt(binding):
    kit = Path(__file__).resolve().parents[1] / "scripts" / "install_receipt"
    subprocess.run(
        [sys.executable, "-c", "import json, sys, p4_prepare_fixture as p; p.prepare(json.load(sys.stdin))"],
        cwd=kit, input=json.dumps(binding), text=True, check=True, timeout=120,
    )
    return json.loads((Path(binding["isolated_profile"]) / "preparation.json").read_bytes())
