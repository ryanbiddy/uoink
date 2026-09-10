"""Exercise the receipt probe with script-directory and site imports disabled."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/install_receipt"))
import p4_common as common

NAMES = ("uoink_mcp", "server", "index", "library_cards", "library_work",
         "library_prompts", "mcp")


def make_app(tmp_path):
    app = tmp_path / "installed app"
    app.mkdir()
    for name in NAMES:
        (app / (name + ".py")).write_text('VERSION = "bound-fixture"\n', encoding="utf8")
    return app


def run_probe(app, source, arguments):
    script = app / "probe.py"
    script.write_text(source, encoding="utf8")
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(script), *arguments],
                          cwd=app, capture_output=True, text=True, timeout=15)


def test_isolated_runtime_needs_explicit_app_bootstrap(tmp_path):
    app = make_app(tmp_path)
    bare = run_probe(app, "import uoink_mcp\n", [])
    assert bare.returncode != 0
    assert "ModuleNotFoundError" in bare.stderr
    bound = run_probe(app, common.RUNTIME_PROBE_SOURCE, [str(app)])
    assert bound.returncode == 0, bound.stderr
    receipt = json.loads(bound.stdout)
    assert receipt["flags"]["isolated"] and receipt["flags"]["no_user_site"]
    assert Path(receipt["sys_path"][0]) == app
    assert set(receipt["modules"]) == set(NAMES)
    for name in NAMES:
        assert receipt["modules"][name]["ok"]
        assert Path(receipt["modules"][name]["file"]) == app / (name + ".py")
        assert receipt["dependency_versions"][name] == "bound-fixture"


@pytest.mark.parametrize("arguments", [[], ["relative-app"]])
def test_probe_refuses_unbound_or_relative_app(tmp_path, arguments):
    app = make_app(tmp_path)
    result = run_probe(app, common.RUNTIME_PROBE_SOURCE, arguments)
    assert result.returncode != 0
    assert "requires an absolute installed app directory" in result.stderr
    assert not result.stdout


def test_bound_probe_still_rejects_checkout_imports(tmp_path):
    app = make_app(tmp_path)
    result = run_probe(app, common.RUNTIME_PROBE_SOURCE, [str(app)])
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    receipt["ok"] = True
    reasons = common.evaluate_probe_for_installed(
        receipt, app=app, interpreter=Path(sys.executable),
        forbid_checkout=app, user_site=None)
    assert any("resolved inside the checkout" in reason for reason in reasons)
