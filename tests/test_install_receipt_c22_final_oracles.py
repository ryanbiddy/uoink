"""C22 final-oracle regressions. New file only.

Does not execute Inno, the production default helper, live index, or port 5179
(including negative probes). Scratch lives under the worktree _scratch/c22-f.
The three imported kit test files remain frozen.
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
SCRATCH = ROOT / "_scratch" / "c22-f"
SCRIPTS = ROOT / "scripts"
KIT = SCRIPTS / "install_receipt"
sys.path.insert(0, str(SCRIPTS))

from install_receipt.cli import operator_commands  # noqa: E402
from install_receipt.constants import (  # noqa: E402
    CAPTURE_PROFILE_NAMES,
    FORBIDDEN_PORT,
    LIBRARY_META_SCHEMA_DEFAULTS,
    SCENARIO_IDS,
    SYNTHETIC_HOSTNAME,
)
from install_receipt.guards import (  # noqa: E402
    SITECUSTOMIZE_SOURCE,
    pth_import_site_is_active,
    prove_guard_rejects_canary,
    require_automatic_site_loading,
    restore_guard_install,
    write_sitecustomize,
)
from install_receipt.launcher import (  # noqa: E402
    PROVENANCE_CODE,
    InstalledHelperLauncher,
    provenance_argv,
)
from install_receipt.manifest import load_candidate_package_02  # noqa: E402
from install_receipt.oracles import (  # noqa: E402
    child_recovery_oracles,
    derive_phase2_allowed,
    interrupt_oracle,
    library_meta_matches_schema_default,
    parse_provenance_json,
    phase2_compare,
    registration_failure_oracle,
    require_measured_pass,
    settings_and_pins_unchanged,
)
from install_receipt.runner import OperatorRunner  # noqa: E402
from install_receipt.scenarios import ScenarioRunner  # noqa: E402
from install_receipt.source_runtime import provision  # noqa: E402
from install_receipt.validation import C22ValidationError  # noqa: E402


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
    path = Path(tempfile.mkdtemp(prefix="f-", dir=str(SCRATCH))).resolve()
    yield path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _package(scratch: Path) -> tuple[Path, str]:
    path = scratch / "Uoink-Setup-synthetic.exe"
    path.write_bytes(b"C22-SYNTHETIC-PACKAGE")
    return path, _sha(path.read_bytes())


def test_final_sitecustomize_keeps_frozen_guard_strings():
    assert "5179" in SITECUSTOMIZE_SOURCE
    assert "whisperx" in SITECUSTOMIZE_SOURCE
    assert "live index forbidden" in SITECUSTOMIZE_SOURCE
    assert "IG_FORBIDDEN_LIVE" in SITECUSTOMIZE_SOURCE
    assert SYNTHETIC_HOSTNAME in SITECUSTOMIZE_SOURCE


def test_final_pth_commented_import_site_is_inactive():
    assert pth_import_site_is_active("#import site\n") is False
    assert pth_import_site_is_active("python311.zip\n.\n#import site\n") is False
    assert pth_import_site_is_active("python311.zip\n.\nimport site\n") is True
    assert pth_import_site_is_active("import site\n") is True


def test_final_commented_pth_refuses_automatic_loading(scratch):
    app = scratch / "Uoink Installed"
    python_dir = app / "python"
    python_dir.mkdir(parents=True)
    (python_dir / "python._pth").write_text(
        "python311.zip\n.\n#import site\n", encoding="utf-8")
    with pytest.raises(C22ValidationError, match="automatically load"):
        require_automatic_site_loading(app)


def test_final_canary_does_not_exec_guard_and_auto_loads(scratch):
    injection = scratch / "injection"
    write_sitecustomize(injection)
    canary = scratch / "canary" / "index.canary"
    proof = prove_guard_rejects_canary(injection=injection, canary_file=canary)
    assert proof["rejected"] is True
    assert proof["explicit_exec"] is False
    assert proof["automatic_sitecustomize"] is True
    assert proof["opened_live_index"] is False
    from install_receipt import guards
    source = Path(guards.__file__).read_text(encoding="utf-8")
    assert "exec(compile" not in source


def test_final_canary_refuses_live_index_path(scratch, monkeypatch):
    live = r"C:\Users\hello\AppData\Local\Uoink\index.db"
    monkeypatch.setenv("IG_FORBIDDEN_LIVE", live)
    injection = scratch / "injection"
    write_sitecustomize(injection)
    with pytest.raises(C22ValidationError, match="live index"):
        prove_guard_rejects_canary(
            injection=injection, canary_file=Path(live))


def test_final_restore_refuses_conflicting_bytes(scratch):
    path = scratch / "sitecustomize.py"
    owned = b"owned-guard\n"
    path.write_bytes(owned)
    with pytest.raises(C22ValidationError, match="conflicting"):
        restore_guard_install(
            path, original=None, owned_sha256=_sha(b"other"),
            children_stopped=True, descendants_stopped=True)
    assert path.read_bytes() == owned
    restore_guard_install(
        path, original=None, owned_sha256=_sha(owned),
        children_stopped=True, descendants_stopped=True)
    assert path.exists() is False


def test_final_restore_unknown_descendant_fails(scratch):
    path = scratch / "sitecustomize.py"
    path.write_bytes(b"owned\n")
    with pytest.raises(C22ValidationError, match="unknown"):
        restore_guard_install(
            path, original=None, owned_sha256=_sha(b"owned\n"),
            children_stopped=True, descendants_stopped=True,
            descendants_unknown=True)
    assert path.read_bytes() == b"owned\n"


def test_final_provenance_code_is_structured_json_and_exits_nonzero():
    assert "importlib.import_module" in PROVENANCE_CODE
    assert "source_subscriptions" in PROVENANCE_CODE
    assert "sha256" in PROVENANCE_CODE
    assert "json.dumps" in PROVENANCE_CODE
    assert "c22-provenance-v1" in PROVENANCE_CODE
    assert "SystemExit(0 if not errors else 2)" in PROVENANCE_CODE
    assert "print('module'" not in PROVENANCE_CODE


def test_final_parse_provenance_json_roundtrip():
    payload = {
        "schema": "c22-provenance-v1",
        "executable": r"C:\app\python\python.exe",
        "modules": {"server": {"ok": True}},
        "import_errors": [],
    }
    parsed = parse_provenance_json("noise\n" + json.dumps(payload) + "\n")
    assert parsed["executable"] == payload["executable"]
    assert parse_provenance_json("module server ERROR ImportError") is None


def test_final_candidate_package_02_seal_is_consumed_not_invented():
    sealed = load_candidate_package_02()
    assert sealed["invented"] is False
    assert len(sealed["installer_source_sha"]) == 40
    assert len(sealed["package_sha256"]) == 64
    assert sealed["package_bytes"] > 0
    assert "server.py" in sealed["files_by_path"]
    server = sealed["files_by_path"]["server.py"]
    assert len(server["source_git_blob"]) == 40
    assert len(server["checkout_and_staged_sha256"]) == 64


def test_final_library_meta_defaults_come_from_schema_not_observed():
    assert library_meta_matches_schema_default(dict(LIBRARY_META_SCHEMA_DEFAULTS))
    mutated = dict(LIBRARY_META_SCHEMA_DEFAULTS)
    mutated["projection_revision"] = 9
    assert library_meta_matches_schema_default(mutated) is False
    before = {"phase2": {"library_meta": []}}
    after = {"phase2": {"library_meta": [mutated]}}
    allowed = derive_phase2_allowed(
        before=before, after=after, admitted=None, profile_name="empty")
    cmp = phase2_compare(before, after, allowed)
    assert cmp["ok"] is False


def test_final_protected_does_not_self_authorize_unknown_work():
    before = {"phase2": {"library_work": []}}
    after = {"phase2": {"library_work": [{
        "work_id": "wk-unexpected",
        "run_id": "run-x",
        "video_id": "not-admitted",
        "kind": "assign",
        "state": "ready",
        "packet_json": "{}",
        "packet_hash": "a" * 64,
        "created_at": "t",
        "updated_at": "t",
    }]}}
    allowed = derive_phase2_allowed(
        before=before, after=after,
        admitted={"ledger": {"video_ids": ["admitted-only"], "yoinks": []}},
        profile_name="one-off",
    )
    cmp = phase2_compare(before, after, allowed)
    assert cmp["ok"] is False


def test_final_altered_pins_and_settings_fail():
    before = {
        "settings": {"librarian_apply_enabled": False, "pins": ["a"]},
        "files": {"taxonomy.json": {"sha256": "aa"}},
    }
    after = {
        "settings": {"librarian_apply_enabled": False, "pins": ["mutated"]},
        "files": {"taxonomy.json": {"sha256": "aa"}},
    }
    result = settings_and_pins_unchanged(before, after)
    assert result["ok"] is False
    after_apply = {
        "settings": {"librarian_apply_enabled": True, "pins": ["a"]},
        "files": {"taxonomy.json": {"sha256": "aa"}},
    }
    assert settings_and_pins_unchanged(before, after_apply)["ok"] is False


def test_final_child_oracles_reject_unknown_and_status_flags():
    unknown = child_recovery_oracles(
        children=[{"pid": 1, "created_ms": 1, "executable": "x", "liveness": "unknown"}],
        helper_terminated_while_child_alive=True,
        relaunched=True, charge_delta=0, publication_delta=0,
        unknown=[{"pid": 1}], child_exited=True, duplicate_launch=False,
    )
    assert unknown["ok"] is False
    interrupt = interrupt_oracle(
        unresolved=[{"unresolved_launch": True, "children": []}],
        spawned_alive=[], unknown=[], injection="launch_interrupt",
    )
    assert interrupt["ok"] is True
    interrupt_any = interrupt_oracle(
        unresolved=[{"unresolved_launch": "yes"}],
        spawned_alive=[], unknown=[], injection="launch_interrupt",
    )
    assert interrupt_any["ok"] is False
    reg = registration_failure_oracle(
        unresolved=[{"unresolved_launch": True}],
        surviving=[{"pid": 2, "liveness": "unknown"}],
        unknown=[{"pid": 2}],
        injection="registration_failure",
        child_exited=False,
    )
    assert reg["ok"] is False
    assert reg["unknown_cannot_pass"] is True


def test_final_owned_children_unknown_is_not_stopped():
    launcher = InstalledHelperLauncher.__new__(InstalledHelperLauncher)
    launcher.proc_record = {"popen": None}
    launcher.owned_child_records = [{"pid": "bad"}]
    assert launcher._owned_children_stopped() is False
    launcher.owned_child_records = []
    assert launcher._owned_children_stopped() is True


def test_final_prepare_before_install_creates_profile_dirs_and_commands(scratch):
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
    for name in CAPTURE_PROFILE_NAMES:
        assert (receipt / "profiles" / name).is_dir()
    commands = operator_commands(
        receipt_root=receipt, intended_app=intended, package=package,
        package_sha256=digest, isolated_profile=receipt / "profiles" / "empty",
        isolated_port=18081, synthetic=True,
    )
    assert "-I" in commands["preinstall_stdlib"]
    assert "-S" in commands["preinstall_stdlib"]
    assert commands["install_unexecuted_until_ryan"] is True
    assert commands["same_version_reinstall_is_not_upgrade"] is True
    assert commands["installed_credit"] is False
    scenarios = ScenarioRunner(runner, fixture_port=_free_port())
    try:
        first = scenarios.prepare_profiles()
        first_hash = json.loads(
            (receipt / "evidence" / "phase2-baselines.json").read_text(
                encoding="utf-8"))
        second = scenarios.prepare_profiles()
        second_hash = json.loads(
            (receipt / "evidence" / "phase2-baselines.json").read_text(
                encoding="utf-8"))
    finally:
        scenarios.close()
    assert first["immutable_baselines"] is True
    assert second["resumed_without_regeneration"] is True
    assert first_hash == second_hash
    assert (receipt / "evidence" / "phase2-baselines.full.json").is_file()


def test_final_continue_refuses_synthetic_promotion(scratch):
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    intended = scratch / "Uoink Installed"
    OperatorRunner.prepare_before_install(
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
    with pytest.raises(C22ValidationError, match="promote"):
        OperatorRunner.continue_existing(
            receipt_root=receipt,
            synthetic=False,
            require_space=False,
            require_bundled_python=False,
        )


def test_final_continue_does_not_skip_bundled_validation_for_installed(scratch):
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    intended = scratch / "Uoink Installed"
    OperatorRunner.prepare_before_install(
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
    inputs_path = receipt / "inputs.json"
    stored = json.loads(inputs_path.read_text(encoding="utf-8"))
    stored["synthetic"] = False
    stored["mode"] = "installed"
    inputs_path.write_text(json.dumps(stored, indent=2) + "\n", encoding="utf-8")
    intended.mkdir()
    (intended / "server.py").write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(C22ValidationError, match="bundled interpreter"):
        OperatorRunner.continue_existing(
            receipt_root=receipt,
            installed_app_path=intended,
            package_sha256=digest,
            synthetic=False,
            require_space=False,
            require_bundled_python=True,
        )


def test_final_nine_profiles_are_named():
    assert len(CAPTURE_PROFILE_NAMES) == 9
    assert "relaunch" in CAPTURE_PROFILE_NAMES
    assert "child-regfail" in CAPTURE_PROFILE_NAMES


def test_final_source_runtime_corrected_oracles(scratch):
    """Source-runtime synthetic check of the five corrected sequences.

    Not installed credit. Stub status flags are not acceptance.
    """
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    profile = receipt / "profiles" / "empty"
    helper_port = _free_port()
    fixture_port = _free_port()
    app = scratch / "Uoink Installed"
    provisioned = provision(dest=app, profile=profile, port=helper_port)
    assert provisioned["installed_credit"] is False
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
    scenarios = ScenarioRunner(runner, fixture_port=fixture_port)
    try:
        prepared = scenarios.prepare_profiles()
        assert prepared["synthetic_host"] == SYNTHETIC_HOSTNAME
        resumed = scenarios.prepare_profiles()
        assert resumed["resumed_without_regeneration"] is True
        for scenario_id in SCENARIO_IDS:
            scenarios.run_one(scenario_id)
    finally:
        scenarios.close()
    outcomes = scenarios.outcomes
    assert outcomes["install"]["status"] == "unexecuted"
    assert outcomes["upgrade_operator_step"]["status"] == "unexecuted"
    assert outcomes["browser_state_checkpoint"]["status"] == "unexecuted"
    provenance = outcomes["installed_provenance"]
    assert provenance.get("installed_credit") is False
    assert provenance.get("provenance_json") or provenance.get("source_runtime")
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
    manual = outcomes["manual_first"]
    assert manual.get("extra_standing_charge") == 0
    standing = outcomes["standing_first"]
    assert standing.get("pubs_before_manual") == 1
    assert standing.get("manual_counted_as_standing") is not True
    child = outcomes["registered_child_lifetime"]
    assert (child.get("recovery") or {}).get("helper_terminated_while_child_alive") is True
    assert ((child.get("instrument") or {}).get("instrument") or {}).get(
        "helper_driven") is True
    interrupt = outcomes["launch_interruption"]
    assert (interrupt.get("interrupt_oracle") or {}).get("unknown_cannot_pass") is False
    reg = outcomes["registration_failure"]
    assert (reg.get("registration_failure_oracle") or {}).get("unknown_cannot_pass") is False
    protected = outcomes["protected_phase2_state"]
    assert protected["compared_profiles"] == list(CAPTURE_PROFILE_NAMES)
    assert protected["self_authorized_after_state"] is False
    assert protected["empty_compare"]["ok"] is True
    argv = provenance_argv(app, synthetic=True)
    assert "-c" in argv
    assert "importlib.import_module" in argv[argv.index("-c") + 1]
