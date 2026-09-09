"""Windows capability queries stay blocked; only the exact stdlib origin is classified."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt.guards import SITECUSTOMIZE_SOURCE


@pytest.mark.skipif(os.name != "nt", reason="Windows shell audit command shape")
@pytest.mark.parametrize("declared", [True, False])
def test_version_query_never_spawns_and_only_stdlib_origin_is_classified(tmp_path, declared):
    guard = tmp_path / "guard.py"
    guard.write_text(SITECUSTOMIZE_SOURCE, encoding="utf8")
    code = "import runpy\nrunpy.run_path(" + repr(str(guard)) + ")\n"
    if declared:
        code += "import platform\nassert platform._syscmd_ver() == ('', '', '')\n"
    else:
        code += """import subprocess
try:
    subprocess.check_output('ver', shell=True)
except PermissionError:
    pass
else:
    raise AssertionError('version subprocess must stay blocked')
"""
    events_file = tmp_path / "events.jsonl"
    env = os.environ.copy()
    env.update(C22_PROVENANCE_ONLY="1", C22_EVENTS_PATH=str(events_file))
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
                            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in events_file.read_text(encoding="utf8").splitlines()]
    attempts = [e for e in events if e['event'] == 'subprocess_attempt']
    probes = [e for e in events if e['event'] == 'blocked_capability_probe']
    forbidden = [e for e in events if e['event'] == 'forbidden_attempt']
    assert len(attempts) == (3 if declared else 1)
    if declared:
        assert len(probes) == 3
        assert all(e['spawned'] is False and e['dependency'] == 'platform._syscmd_ver' for e in probes)
        assert not forbidden
    else:
        assert forbidden
        assert not probes
