"""C22 receipt kit tests. New file only. Labeled synthetic instrument checks.

Does not execute Inno, the production default helper, live index, or port 5179
(including negative probes). Scratch lives under the worktree _scratch/c22-kit.
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
SCRATCH = ROOT / "_scratch" / "c22-kit"
SCRIPTS = ROOT / "scripts"
KIT = SCRIPTS / "install_receipt"
sys.path.insert(0, str(SCRIPTS))

from install_receipt.constants import (  # noqa: E402
    FORBIDDEN_PORT,
    ISOLATED_PORT_FLAG,
    ISOLATED_PROFILE_FLAG,
    LEGACY_FIXTURE_VERSION,
    SCENARIO_IDS,
)
from install_receipt.evidence import build_verdict, collect_snapshot, integrity_report  # noqa: E402
from install_receipt.fixtures import (  # noqa: E402
    FixtureFeed,
    build_empty_profile,
    build_populated_legacy,
)
from install_receipt.guards import SITECUSTOMIZE_SOURCE, guard_env, write_sitecustomize  # noqa: E402
from install_receipt.hashes import sha256_file  # noqa: E402
from install_receipt.launcher import launch_argv  # noqa: E402
from install_receipt.manifest import (  # noqa: E402
    example_manifest,
    require_sealed_package_hash,
    upgrade_kind,
)
from install_receipt.runner import OperatorRunner  # noqa: E402
from install_receipt.scenarios import ScenarioRunner  # noqa: E402
from install_receipt.validation import (  # noqa: E402
    C22ValidationError,
    assert_isolation_flags,
    child_env_forbidden_resolution,
    validate_not_ordinary_user,
    validate_package,
    validate_port,
    validate_receipt_root,
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


def _install(scratch: Path) -> Path:
    app = scratch / "Uoink Installed"
    app.mkdir(exist_ok=True)
    (app / "server.py").write_bytes((KIT / "stub_helper.py").read_bytes())
    (app / "VERSION").write_text("3.8.0-synthetic\n", encoding="utf-8")
    return app


def _runner(scratch: Path, **kwargs) -> OperatorRunner:
    receipt = scratch / "receipt"
    package, digest = _package(scratch)
    app = _install(scratch)
    profile = receipt / "profiles" / "empty"
    port = kwargs.pop("port", _free_port())
    return OperatorRunner.create(
        receipt_root=receipt,
        installed_app_path=app,
        package_path=package,
        package_sha256=digest,
        isolated_profile=profile,
        isolated_port=port,
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
        skip_ordinary_user_check=True,
        **kwargs,
    )


def test_port_5179_is_rejected_without_probing():
    with pytest.raises(C22ValidationError, match="5179"):
        validate_port(5179)
    with pytest.raises(C22ValidationError, match="5179"):
        validate_port("5179")


def test_relative_receipt_root_rejected(scratch):
    with pytest.raises(C22ValidationError, match="absolute"):
        validate_receipt_root("relative/receipt")


def test_package_hash_mismatch_rejected(scratch):
    path, digest = _package(scratch)
    with pytest.raises(C22ValidationError, match="differs"):
        validate_package(path, "0" * 64)
    assert validate_package(path, digest)["matched_supplied_digest"] is True


def test_unsealed_manifest_hash_is_not_invented():
    with pytest.raises(C22ValidationError, match="unsealed"):
        require_sealed_package_hash(example_manifest())
    with pytest.raises(C22ValidationError, match="unsealed"):
        require_sealed_package_hash({"expected_package_sha256": None})


def test_same_version_reinstall_is_not_cross_version():
    manifest = example_manifest()
    assert upgrade_kind(manifest, installed_version="3.8.0",
                        package_version="3.8.0") == "same_version_reinstall"
    assert upgrade_kind(manifest, installed_version="3.8.0",
                        package_version="3.9.0") == "cross_version_upgrade"


def test_launch_argv_requires_isolation_flags_and_skips_default_helper(scratch):
    app = _install(scratch)
    profile = scratch / "profile"
    profile.mkdir()
    port = _free_port()
    argv = launch_argv(app, isolated_profile=profile, isolated_port=port,
                       synthetic=True)
    assert ISOLATED_PROFILE_FLAG in argv
    assert ISOLATED_PORT_FLAG in argv
    assert str(port) in argv
    assert str(FORBIDDEN_PORT) not in argv
    assert argv[argv.index(ISOLATED_PROFILE_FLAG) + 1] == str(profile)
    assert_isolation_flags(argv)
    assert "start_server.ps1" not in " ".join(argv)
    with pytest.raises(C22ValidationError):
        assert_isolation_flags([sys.executable, str(app / "start_server.ps1")])


def test_child_env_rejects_checkout_root_and_api_key():
    env = {"PYTHONNOUSERSITE": "1", "PYTHONPATH": str(ROOT)}
    with pytest.raises(C22ValidationError, match="checkout root"):
        child_env_forbidden_resolution(env, checkout=ROOT)
    env = {"PYTHONNOUSERSITE": "1", "PYTHONPATH": str(KIT),
           "ANTHROPIC_API_KEY": "sk-secret"}
    with pytest.raises(C22ValidationError, match="ANTHROPIC_API_KEY"):
        child_env_forbidden_resolution(env, checkout=ROOT)


def test_ordinary_user_check_matches_runbook():
    if os.path.normcase(os.path.normpath(os.environ.get("USERPROFILE", ""))) == \
            os.path.normcase(os.path.normpath(r"C:\Users\hello")):
        with pytest.raises(C22ValidationError, match="throwaway"):
            validate_not_ordinary_user()


def test_runner_refuses_overwrite(scratch):
    runner = _runner(scratch)
    with pytest.raises(C22ValidationError, match="already exists"):
        _runner(scratch)


def test_runner_records_command_exit_identity_and_hashes(scratch):
    runner = _runner(scratch)
    record = runner.run_command(
        [sys.executable, "-B", "-c", "print('c22-ok')"],
        name="echo",
    )
    assert record["exit"] == 0
    assert record["child"]["pid"] > 0
    assert record["stdout_sha256"]
    stdout = Path(record["stdout_path"]).read_text(encoding="utf-8")
    assert "c22-ok" in stdout
    journal = runner.journal_path.read_text(encoding="utf-8")
    assert "command" in journal
    assert runner.summary_path.is_file()


def test_runner_preserves_partial_output_on_failure(scratch):
    runner = _runner(scratch)
    record = runner.run_command(
        [sys.executable, "-B", "-c", "import sys; print('kept'); sys.exit(3)"],
        name="failing",
    )
    assert record["exit"] == 3
    assert "kept" in Path(record["stdout_path"]).read_text(encoding="utf-8")
    assert runner.journal_path.is_file()
    assert (runner.receipt_root / "inputs.json").is_file()


def test_plan_inno_does_not_execute(scratch):
    runner = _runner(scratch)
    plan = runner.plan_inno(example_manifest(), execute=False)
    assert plan["execute"] is False
    joined = " ".join(plan["argv"])
    assert "/ISOLATED=1" in joined
    assert "/PROFILE=" in joined
    assert "/PORT=" in joined
    assert str(FORBIDDEN_PORT) not in joined
    with pytest.raises(C22ValidationError, match="Inno"):
        runner.plan_inno(example_manifest(), execute=True)


def test_sitecustomize_source_forbids_5179_and_models():
    assert "5179" in SITECUSTOMIZE_SOURCE
    assert "whisperx" in SITECUSTOMIZE_SOURCE
    assert "live index forbidden" in SITECUSTOMIZE_SOURCE


def test_guard_env_refuses_to_allow_5179(scratch):
    with pytest.raises(C22ValidationError):
        guard_env(
            isolated_profile=scratch,
            allowed_ports=[FORBIDDEN_PORT],
            forbidden_live=scratch / "nope.db",
        )


def test_write_sitecustomize_hash(scratch):
    info = write_sitecustomize(scratch / "injection")
    assert Path(info["path"]).is_file()
    assert info["sha256"] == sha256_file(info["path"])


def test_fixture_feed_loopback_non_5179(scratch):
    port = _free_port()
    feed = FixtureFeed(scratch, port)
    base = feed.start()
    try:
        assert "127.0.0.1" in base
        assert str(FORBIDDEN_PORT) not in base
        assert feed.port != FORBIDDEN_PORT
        import urllib.request
        with urllib.request.urlopen(feed.audio_url, timeout=2) as response:
            assert response.read() == b"C22 SYNTHETIC AUDIO PLACEHOLDER"
    finally:
        feed.stop()


def test_empty_and_versioned_populated_profiles(scratch):
    empty = build_empty_profile(scratch / "empty")
    assert empty["librarian_apply_enabled"] is False
    assert empty["index_present"] is False
    populated = build_populated_legacy(scratch / "populated")
    assert populated["fixture_version"] == LEGACY_FIXTURE_VERSION
    assert populated["schema_version"] == 27
    assert populated["librarian_apply_enabled"] is False
    index = scratch / "populated" / "index.db"
    report = integrity_report(index)
    assert report["present"] is True
    assert report["integrity"] == "ok"
    snap = collect_snapshot(scratch / "populated", label="t")
    assert snap["settings"]["librarian_apply_enabled"] is False
    assert snap["schema_version"] == 27


def test_synthetic_helper_scenarios_and_verdict(scratch, monkeypatch):
    """Labeled non-installed synthetic instrument check. Not installed credit."""
    helper_port = _free_port()
    fixture_port = _free_port()
    # Current scenarios measure original child methods and module provenance.
    # Use the existing source-runtime fixture with synthetic acquisition;
    # the stand-alone HTTP stub cannot provide that evidence.
    from install_receipt.source_runtime import provision
    app = scratch / "Uoink Source Fixture"
    provision(dest=app, profile=scratch / "receipt" / "profiles" / "empty",
              port=helper_port)
    monkeypatch.setattr(sys.modules[__name__], "_install", lambda root: app)
    runner = _runner(scratch, port=helper_port)
    scenarios = ScenarioRunner(runner, fixture_port=fixture_port)
    try:
        scenarios.prepare_profiles()
        for scenario_id in (
            "install",
            "empty_migration_replay",
            "populated_legacy_replay",
            "one_off_capture",
            "manual_first",
            "standing_first",
            "whole_helper_relaunch",
            "registered_child_lifetime",
            "launch_interruption",
            "registration_failure",
            "browser_state_checkpoint",
            "protected_phase2_state",
            "upgrade_operator_step",
            "installed_provenance",
        ):
            scenarios.run_one(scenario_id)
    finally:
        scenarios.close()
    outcomes = scenarios.outcomes
    assert set(SCENARIO_IDS) == set(outcomes)
    assert outcomes["install"]["status"] == "unexecuted"
    assert outcomes["upgrade_operator_step"]["status"] == "unexecuted"
    assert outcomes["upgrade_operator_step"]["same_version_label"] == \
        "same_version_reinstall"
    for key in (
        "empty_migration_replay",
        "populated_legacy_replay",
        "one_off_capture",
        "manual_first",
        "standing_first",
        "whole_helper_relaunch",
        "registered_child_lifetime",
        "launch_interruption",
        "registration_failure",
        "protected_phase2_state",
    ):
        assert outcomes[key]["status"] == "pass", (key, outcomes[key])
    assert outcomes["one_off_capture"]["standing_charges"] == []
    assert outcomes["standing_first"]["standing_charges"] == 1
    assert outcomes["standing_first"]["deduped"] is True
    assert outcomes["launch_interruption"]["injection"] == "launch_interrupt"
    assert outcomes["registration_failure"]["injection"] == "registration_failure"
    assert outcomes["registration_failure"]["distinct_from"] == "launch_interrupt"
    first = outcomes["whole_helper_relaunch"]["first_identity"]
    second = outcomes["whole_helper_relaunch"]["second_identity"]
    assert first["pid"] != second["pid"] or first.get("created_ms") != second.get("created_ms")
    verdict = build_verdict(runner.receipt_root, outcomes, synthetic=True)
    assert verdict["installed_pass_claimed"] is False
    assert verdict["synthetic_instrument"] is True
    assert verdict["counts"]["fail"] == 0
    assert (runner.receipt_root / "evidence" / "verdict.json").is_file()
    protocol = json.loads(
        (runner.receipt_root / "evidence" /
         "browser_observation_protocol.json").read_text(encoding="utf-8"))
    assert protocol["screenshot"] is None


def test_cli_list_scenarios():
    from install_receipt.cli import main
    assert main(["list-scenarios"]) == 0
