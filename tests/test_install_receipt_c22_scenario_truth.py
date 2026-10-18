"""C22 scenario-truth regressions. New file only.

Does not execute Inno, the production default helper, live index, or port 5179
(including negative probes). Scratch lives under the worktree _scratch/c22-t.
Original kit test files remain frozen.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "_scratch" / "c22-t"
SCRIPTS = ROOT / "scripts"
KIT = SCRIPTS / "install_receipt"
sys.path.insert(0, str(SCRIPTS))

from install_receipt.constants import (  # noqa: E402
    FORBIDDEN_PORT,
    INNO_NOCLOSE_FLAG,
    INNO_NORESTARTAPPS_FLAG,
    SCENARIO_IDS,
    SYNTHETIC_HOSTNAME,
)
from install_receipt.guards import (  # noqa: E402
    SITECUSTOMIZE_SOURCE,
    prove_guard_rejects_canary,
    write_sitecustomize,
)
from install_receipt.launcher import launch_argv, provenance_argv  # noqa: E402
from install_receipt.manifest import example_manifest  # noqa: E402
from install_receipt.oracles import (  # noqa: E402
    capture_ledger,
    live_index_guard,
    phase2_compare,
    require_measured_pass,
)
from install_receipt.runner import OperatorRunner  # noqa: E402
from install_receipt.scenarios import ScenarioRunner  # noqa: E402
from install_receipt.source_runtime import provision, write_install_marker  # noqa: E402
from install_receipt.validation import (  # noqa: E402
    C22ValidationError,
    forbidden_live_path_string,
    validate_inno_argv,
    validate_port,
)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    if port == FORBIDDEN_PORT:
        return _free_port()
    return port


@pytest.fixture
def scratch():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="t-", dir=str(SCRATCH))).resolve()
    yield path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _package(scratch: Path) -> tuple[Path, str]:
    path = scratch / "Uoink-Setup-synthetic.exe"
    path.write_bytes(b"C22-SYNTHETIC-PACKAGE")
    return path, _sha(path.read_bytes())


def test_truth_sitecustomize_keeps_frozen_guard_strings():
    assert "5179" in SITECUSTOMIZE_SOURCE
    assert "whisperx" in SITECUSTOMIZE_SOURCE
    assert "live index forbidden" in SITECUSTOMIZE_SOURCE
    assert "IG_FORBIDDEN_LIVE" in SITECUSTOMIZE_SOURCE
    assert SYNTHETIC_HOSTNAME in SITECUSTOMIZE_SOURCE


def test_truth_live_index_guard_is_string_only(tmp_path, monkeypatch):
    target = tmp_path / "must-not-open.db"
    target.write_bytes(b"secret")

    def boom(*args, **kwargs):
        raise AssertionError("live index must not be opened or hashed")

    monkeypatch.setattr(Path, "stat", boom)
    monkeypatch.setattr(Path, "read_bytes", boom)
    record = live_index_guard(target)
    assert record["path"] == str(target)
    assert record["opened"] is False
    assert record["hashed"] is False
    assert record["sha256"] is None


def test_truth_forbidden_live_string_ignores_redirected_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\redirected-not-live")
    monkeypatch.setenv("IG_FORBIDDEN_LIVE", r"C:\Users\hello\AppData\Local\Uoink\index.db")
    assert forbidden_live_path_string() == r"C:\Users\hello\AppData\Local\Uoink\index.db"


def test_truth_port_validated_before_probe():
    with pytest.raises(C22ValidationError, match="5179"):
        validate_port(5179)


def test_truth_inno_requires_noclose_and_rejects_positive_overrides():
    argv = [
        r"C:\pkg\Uoink-Setup.exe",
        "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES",
        r'/DIR=C:\Uoink Installed',
        "/ISOLATED=1", "/PROFILE=C:\\receipt\\profiles\\empty",
        "/PORT=18081",
        INNO_NOCLOSE_FLAG, INNO_NORESTARTAPPS_FLAG,
    ]
    validate_inno_argv(argv)
    with pytest.raises(C22ValidationError, match="CLOSEAPPLICATIONS"):
        validate_inno_argv(argv + ["/CLOSEAPPLICATIONS"])
    with pytest.raises(C22ValidationError, match="FORCECLOSE"):
        validate_inno_argv(argv + ["/FORCECLOSEAPPLICATIONS"])
    with pytest.raises(C22ValidationError, match="RESTARTAPPLICATIONS"):
        validate_inno_argv(argv + ["/RESTARTAPPLICATIONS"])
    missing = [p for p in argv if p not in {INNO_NOCLOSE_FLAG, INNO_NORESTARTAPPS_FLAG}]
    with pytest.raises(C22ValidationError, match="NOCLOSE"):
        validate_inno_argv(missing)


def test_truth_plan_inno_records_required_switches(scratch):
    receipt = scratch / "receipt"
    package, digest = _package(scratch)
    app = scratch / "Uoink Installed"
    app.mkdir()
    (app / "server.py").write_text("# placeholder\n", encoding="utf-8")
    runner = OperatorRunner.create(
        receipt_root=receipt,
        installed_app_path=app,
        package_path=package,
        package_sha256=digest,
        isolated_profile=receipt / "profiles" / "empty",
        isolated_port=_free_port(),
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
        skip_ordinary_user_check=True,
    )
    plan = runner.plan_inno(example_manifest(), execute=False)
    joined = " ".join(plan["argv"])
    assert INNO_NOCLOSE_FLAG in joined
    assert INNO_NORESTARTAPPS_FLAG in joined
    assert "/ISOLATED=1" in joined


def test_truth_charge_oracle_uses_started_at_ms_not_origin(scratch):
    profile = scratch / "profile"
    profile.mkdir()
    index = profile / "index.db"
    import sqlite3
    conn = sqlite3.connect(str(index))
    conn.execute(
        "CREATE TABLE source_capture_starts ("
        "start_id TEXT PRIMARY KEY, capture_key TEXT, started_at_ms INTEGER, "
        "video_id TEXT)")
    conn.execute(
        "INSERT INTO source_capture_starts VALUES ('s1','k1',NULL,'v1')")
    conn.execute(
        "INSERT INTO source_capture_starts VALUES ('s2','k2',1000,'v2')")
    conn.commit()
    conn.close()
    ledger = capture_ledger(profile)
    assert ledger["standing_charge_count"] == 1
    assert ledger["standing_starts"][0]["start_id"] == "s2"
    blob = json.dumps(ledger)
    assert "origin" not in blob or ledger["schema_note"].startswith("source_capture_starts")


def test_truth_phase2_compare_rejects_named_table_without_exact_rows():
    before = {
        "phase2_hash": "a",
        "phase2": {"library_work": [{"work_id": "old", "state": "ready"}]},
    }
    after = {
        "phase2_hash": "b",
        "phase2": {"library_work": [
            {"work_id": "old", "state": "mutated"},
            {"work_id": "new", "state": "ready"},
        ]},
    }
    named_only = phase2_compare(before, after, [{"table": "library_work"}])
    assert named_only["ok"] is False
    exact_but_prior_mutated = phase2_compare(before, after, [{
        "table": "library_work",
        "new_rows": [{"work_id": "new", "state": "ready"}],
    }])
    assert exact_but_prior_mutated["ok"] is False
    unchanged_prior = {
        "phase2_hash": "c",
        "phase2": {"library_work": [
            {"work_id": "old", "state": "ready"},
            {"work_id": "new", "state": "ready"},
        ]},
    }
    ok = phase2_compare(before, unchanged_prior, [{
        "table": "library_work",
        "new_rows": [{"work_id": "new", "state": "ready"}],
    }])
    assert ok["ok"] is True


def test_truth_guard_canary_rejects_without_opening_live(scratch):
    injection = scratch / "injection"
    write_sitecustomize(injection)
    canary = scratch / "canary" / "index.canary"
    proof = prove_guard_rejects_canary(injection=injection, canary_file=canary)
    assert proof["rejected"] is True
    assert proof["opened_live_index"] is False


def test_truth_marker_not_rewritten_to_switch_profiles(scratch):
    app = scratch / "Uoink Installed"
    app.mkdir()
    first = write_install_marker(app, profile=scratch / "p1", port=18081)
    assert first["unchanged"] is False
    same = write_install_marker(app, profile=scratch / "p1", port=18081,
                                overwrite=False)
    assert same["unchanged"] is True
    with pytest.raises(C22ValidationError, match="switch profiles"):
        write_install_marker(app, profile=scratch / "p2", port=18082,
                             overwrite=False)


def test_truth_prepare_before_install_and_continue(scratch):
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    intended = scratch / "Uoink Installed"
    runner = OperatorRunner.prepare_before_install(
        receipt_root=receipt,
        intended_app_path=intended,
        package_path=package,
        package_sha256=digest,
        isolated_profile=receipt / "profiles" / "empty",
        isolated_port=18081,
        synthetic=True,
        require_space=False,
        skip_ordinary_user_check=True,
    )
    inputs = runner.load_inputs()
    assert inputs["prepare_before_install"] is True
    assert inputs["installed_app"]["intended_before_install"] is True
    plan = runner.plan_inno(example_manifest(), execute=False)
    assert INNO_NOCLOSE_FLAG in " ".join(plan["argv"])
    intended.mkdir()
    (intended / "server.py").write_text("print(1)\n", encoding="utf-8")
    continued = OperatorRunner.continue_existing(
        receipt_root=receipt,
        installed_app_path=intended,
        package_sha256=digest,
        isolated_port=18081,
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
    )
    assert continued.receipt_root == runner.receipt_root
    with pytest.raises(C22ValidationError, match="binding mismatch"):
        OperatorRunner.continue_existing(
            receipt_root=receipt,
            package_sha256="0" * 64,
            synthetic=True,
        )


def test_truth_continue_refuses_overwrite_of_completed_scenario(scratch):
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    app = scratch / "Uoink Installed"
    app.mkdir()
    (app / "server.py").write_text("# x\n", encoding="utf-8")
    runner = OperatorRunner.create(
        receipt_root=receipt,
        installed_app_path=app,
        package_path=package,
        package_sha256=digest,
        isolated_profile=receipt / "profiles" / "empty",
        isolated_port=_free_port(),
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
        skip_ordinary_user_check=True,
    )
    evidence = receipt / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "install.json").write_text(json.dumps({
        "id": "install", "status": "unexecuted",
    }) + "\n", encoding="utf-8")
    scenarios = ScenarioRunner(runner, fixture_port=_free_port())
    with pytest.raises(C22ValidationError, match="overwrite completed"):
        scenarios.record("install", "pass")


def test_truth_provenance_argv_imports_modules(scratch):
    app = scratch / "Uoink Installed"
    app.mkdir()
    (app / "server.py").write_text("print('x')\n", encoding="utf-8")
    argv = provenance_argv(app, synthetic=True)
    assert "-c" in argv
    code = argv[argv.index("-c") + 1]
    assert "importlib.import_module" in code
    assert "source_subscriptions" in code
    assert "sha256" in code


def test_truth_instrument_must_not_accept_fail_as_pass():
    with pytest.raises(C22ValidationError, match="not pass"):
        require_measured_pass({"id": "manual_first", "status": "fail"},
                              scenario_id="manual_first")
    with pytest.raises(C22ValidationError, match="not pass"):
        require_measured_pass({"id": "manual_first", "status": "unexecuted"},
                              scenario_id="manual_first")
    require_measured_pass({"id": "manual_first", "status": "pass"},
                          scenario_id="manual_first")


def test_truth_source_runtime_measured_scenarios(scratch):
    """Source-runtime synthetic check. Not installed credit.

    Asserts measured pass for repaired capture/guard/child/protected flows.
    Operator-only Inno/browser boundaries stay unexecuted.
    """
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    profile = receipt / "profiles" / "empty"
    helper_port = _free_port()
    fixture_port = _free_port()
    app = scratch / "Uoink Installed"
    provisioned = provision(dest=app, profile=profile, port=helper_port)
    assert provisioned["opened_live_index"] is False
    runner = OperatorRunner.create(
        receipt_root=receipt,
        installed_app_path=app,
        package_path=package,
        package_sha256=digest,
        isolated_profile=profile,
        isolated_port=helper_port,
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
        skip_ordinary_user_check=True,
    )
    (receipt / "source_runtime.json").write_text(
        json.dumps(provisioned, indent=2, default=str) + "\n", encoding="utf-8")
    scenarios = ScenarioRunner(runner, fixture_port=fixture_port)
    try:
        prepared = scenarios.prepare_profiles()
        assert prepared["synthetic_host"] == SYNTHETIC_HOSTNAME
        assert scenarios.phase2_baselines["empty"]["phase2_hash"]
        for scenario_id in SCENARIO_IDS:
            scenarios.run_one(scenario_id)
    finally:
        scenarios.close()
    outcomes = scenarios.outcomes
    assert outcomes["install"]["status"] == "unexecuted"
    assert outcomes["upgrade_operator_step"]["status"] == "unexecuted"
    assert outcomes["browser_state_checkpoint"]["status"] == "unexecuted"
    assert outcomes["install"]["agreed_inno_shape"] is True
    guards = json.loads((receipt / "guards.json").read_text(encoding="utf-8"))
    assert guards.get("opened_live_index") is False
    assert "previous_bytes" not in json.dumps(guards)
    require_measured_pass(outcomes["empty_migration_replay"],
                          scenario_id="empty_migration_replay")
    require_measured_pass(outcomes["populated_legacy_replay"],
                          scenario_id="populated_legacy_replay")
    require_measured_pass(outcomes["one_off_capture"],
                          scenario_id="one_off_capture")
    require_measured_pass(outcomes["manual_first"], scenario_id="manual_first")
    require_measured_pass(outcomes["standing_first"],
                          scenario_id="standing_first")
    require_measured_pass(outcomes["whole_helper_relaunch"],
                          scenario_id="whole_helper_relaunch")
    require_measured_pass(outcomes["registered_child_lifetime"],
                          scenario_id="registered_child_lifetime")
    require_measured_pass(outcomes["launch_interruption"],
                          scenario_id="launch_interruption")
    require_measured_pass(outcomes["registration_failure"],
                          scenario_id="registration_failure")
    require_measured_pass(outcomes["protected_phase2_state"],
                          scenario_id="protected_phase2_state")
    one = outcomes["one_off_capture"]
    assert one["standing_charges"] == [] or one["ledger_delta"]["standing_charge_delta"] == 0
    assert SYNTHETIC_HOSTNAME in str(one.get("synthetic_url") or "")
    standing = outcomes["standing_first"]
    assert standing["standing_charges"] >= 1
    assert standing.get("manual_counted_as_standing") is not True
    child = outcomes["registered_child_lifetime"]
    product = ((child.get("instrument") or {}).get("instrument") or {}).get(
        "product_module", "")
    assert "source_subscriptions" in str(product)
    assert ((child.get("instrument") or {}).get("instrument") or {}).get(
        "helper_driven") is True
    protected = outcomes["protected_phase2_state"]
    assert protected["baseline_recorded_before_scenarios"] is True
    assert protected["empty_compare"]["ok"] is True
    helpers = list(receipt.glob("helper-*.json"))
    blob = "\n".join(p.read_text(encoding="utf-8") for p in helpers)
    assert "previous_bytes" not in blob
    assert '"opened_live_index": false' in blob.lower() or "opened_live_index" in blob
