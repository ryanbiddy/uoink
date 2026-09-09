"""Final operator errors must remain failures and reuse must recheck bindings."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt import browser_checkpoint, cli, scenarios
from install_receipt.oracles import library_meta_matches_schema_default, settings_and_pins_unchanged
from install_receipt.constants import LIBRARY_META_SCHEMA_DEFAULTS
from install_receipt.validation import C22ValidationError


def test_failed_scenario_produces_failed_cli_exit(tmp_path, monkeypatch):
    runner = SimpleNamespace(receipt_root=tmp_path, completed_scenario_ids=lambda: [])
    class Scenarios:
        def __init__(self, *a, **kw): pass
        def prepare_profiles(self): pass
        def run_all(self, **kw): return {"failure": {"status": "fail"}}
        def close(self): pass
    monkeypatch.setattr(cli, "_runner", lambda args: runner)
    monkeypatch.setattr(cli, "ScenarioRunner", Scenarios)
    monkeypatch.setattr(cli, "build_verdict", lambda *a, **kw: {
        "installed_pass_claimed": False, "counts": {"fail": 1}})
    runner.synthetic = True
    result = cli.main(["run", "--installed-app", str(tmp_path), "--package", str(tmp_path / "package.exe"),
        "--package-sha256", "a" * 64, "--isolated-profile", str(tmp_path / "empty"),
        "--isolated-port", "18321", "--receipt-root", str(tmp_path)])
    assert result == 1


def test_browser_continue_revalidates_actual_app_package_and_profile(tmp_path, monkeypatch):
    inputs = {"installed_app": {"path": str(tmp_path / "app")},
              "package": {"path": str(tmp_path / "setup.exe"), "sha256": "a" * 64},
              "isolated_profile": str(tmp_path / "profiles/empty"), "isolated_port": 18321}
    (tmp_path / "inputs.json").write_text(json.dumps(inputs), encoding="utf8")
    captured = {}
    def continued(**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(browser_checkpoint, "sys", SimpleNamespace(flags=SimpleNamespace(no_site=True, isolated=True)))
    monkeypatch.setattr(browser_checkpoint, "OperatorRunner", SimpleNamespace(continue_existing=continued))
    monkeypatch.setattr(browser_checkpoint, "run_checkpoint", lambda *a, **kw: {})
    assert browser_checkpoint.main(["--receipt-root", str(tmp_path)]) == 0
    assert captured.get("installed_app_path") == inputs["installed_app"]["path"]
    assert captured.get("package_path") == inputs["package"]["path"]
    assert captured.get("package_sha256") == inputs["package"]["sha256"]
    assert captured.get("isolated_profile") == inputs["isolated_profile"]
    assert captured.get("isolated_port") == inputs["isolated_port"]


def test_settings_preservation_distinguishes_json_types():
    before = {"settings": {"librarian_apply_enabled": False, "pins": [1]}, "files": {}}
    after = {"settings": {"librarian_apply_enabled": False, "pins": [True]}, "files": {}}
    assert settings_and_pins_unchanged(before, after)["ok"] is False


def test_schema_default_does_not_treat_boolean_as_integer():
    row = dict(LIBRARY_META_SCHEMA_DEFAULTS, singleton=True)
    assert library_meta_matches_schema_default(row) is False


def test_helper_wrapper_requires_affirmed_cleanup(tmp_path, monkeypatch):
    scenario = object.__new__(scenarios.ScenarioRunner)
    scenario.fixture_port = 18322
    scenario.runner = object()
    monkeypatch.setattr(scenario, "_inputs", lambda: {"installed_app": {"path": str(tmp_path / "app")}, "isolated_port": 18321})
    monkeypatch.setattr(scenario, "_profile", lambda name: tmp_path)
    monkeypatch.setattr(scenarios, "read_token_with_note", lambda *a: {"token": "fixture"})
    class Launcher:
        def __init__(self, *a, **kw): pass
        def start(self, **kw): return {"child": {"pid": 123}, "health": {"ok": True}}
        def stop_owned(self, **kw): return {"stopped": False, "port_freed": False}
    monkeypatch.setattr(scenarios, "InstalledHelperLauncher", Launcher)
    with pytest.raises(C22ValidationError, match="cleanup|stop"):
        scenario._with_helper("empty", lambda *args: {"ok": True})
