"""Embedded command/import compatibility; no installed acceptance or network probe."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt import launcher
from install_receipt.guards import SITECUSTOMIZE_SOURCE


def test_provenance_resolves_only_explicit_app_without_cwd_or_pythonpath(tmp_path, monkeypatch):
    app = tmp_path / "Explicit App"
    app.mkdir()
    names = ("server", "source_subscriptions", "index", "uoink_mcp", "source_manifest", "podcasts", "library_work")
    for name in names:
        (app / (name + ".py")).write_text("MARKER = 'unit-only-original-path'\n", encoding="utf8")
    monkeypatch.setattr(launcher, "resolve_interpreter", lambda *a, **k: Path(sys.executable))
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(launcher.provenance_argv(app, synthetic=True), cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert all(Path(payload["modules"][name]["file"]) == app / (name + ".py") for name in names)


def _guarded_probe(tmp_path, code, inject=""):
    guard = tmp_path / "receipt_guard.py"
    guard.write_text(SITECUSTOMIZE_SOURCE, encoding="utf8")
    probe = tmp_path / "probe.py"
    probe.write_text("import runpy\nrunpy.run_path(" + repr(str(guard)) + ")\n" + code, encoding="utf8")
    env = os.environ.copy()
    env.update(C22_INJECT=inject, C22_EVENTS_PATH=str(tmp_path / "events.jsonl"), C22_ALLOWED_PORTS="18381")
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(probe)], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf8").splitlines()]
    return result, events


@pytest.mark.parametrize("inject", ["", "spawn_child", "launch_interrupt", "registration_failure"])
def test_guard_preserves_popen_class_and_windows_asyncio(tmp_path, inject):
    result, events = _guarded_probe(tmp_path, """import subprocess, os
assert isinstance(subprocess.Popen, type), 'Popen must remain subclassable'
class Compatible(subprocess.Popen):
    pass
if os.name == 'nt':
    import asyncio.windows_utils
    assert issubclass(asyncio.windows_utils.Popen, subprocess.Popen)
print('class-compatible')
""", inject)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "class-compatible"
    assert not any(e["event"] == "subprocess_attempt" for e in events)


@pytest.mark.parametrize("declared", [True, False])
def test_ipv6_query_is_still_refused_and_callsite_is_accounted(tmp_path, declared):
    query = """import socket
def _has_ipv6(host):
    sock = socket.socket(socket.AF_INET6)
    try:
        try:
            sock.bind((host, 0))
        except PermissionError:
            return False
        raise AssertionError('the bind must never execute')
    finally:
        sock.close()
assert _has_ipv6('::1') is False
"""
    if declared:
        path = tmp_path / "urllib3" / "util" / "connection.py"
        path.parent.mkdir(parents=True)
        path.write_text(query, encoding="utf8")
        code = ("import importlib.util, sys\n"
                "spec=importlib.util.spec_from_file_location('urllib3.util.connection', " + repr(str(path)) + ")\n"
                "module=importlib.util.module_from_spec(spec)\n"
                "sys.modules[spec.name]=module\nspec.loader.exec_module(module)\n")
    else:
        code = query
    result, events = _guarded_probe(tmp_path, code)
    assert result.returncode == 0, result.stdout + result.stderr
    expected = "blocked_capability_probe" if declared else "forbidden_attempt"
    assert sum(e["event"] == expected for e in events) == 1
    assert sum(e["event"] == "network_attempt" for e in events) == 1
    if declared:
        assert not any(e["event"] == "forbidden_attempt" for e in events)
