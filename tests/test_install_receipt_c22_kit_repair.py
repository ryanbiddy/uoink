"""C22 kit repair regressions. New file only.

Does not execute Inno, the production default helper, live index, or port 5179
(including negative probes). Scratch lives under the worktree _scratch/c22-kit.
Original tests/test_install_receipt_c22_kit.py assertions are not edited.
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
    MARKER_FILENAME,
    SCENARIO_IDS,
)
from install_receipt.evidence import collect_snapshot  # noqa: E402
from install_receipt.launcher import launch_argv, provenance_argv, read_token  # noqa: E402
from install_receipt.manifest import example_manifest  # noqa: E402
from install_receipt.owned_stop import terminate_via_exact_handle  # noqa: E402
from install_receipt.runner import OperatorRunner  # noqa: E402
from install_receipt.scenarios import ScenarioRunner  # noqa: E402
from install_receipt.source_runtime import provision  # noqa: E402
from install_receipt.validation import C22ValidationError, validate_port  # noqa: E402


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
    path = Path(tempfile.mkdtemp(prefix="r-", dir=str(SCRATCH))).resolve()
    yield path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _package(scratch: Path) -> tuple[Path, str]:
    path = scratch / "Uoink-Setup-synthetic.exe"
    path.write_bytes(b"C22-SYNTHETIC-PACKAGE")
    return path, _sha(path.read_bytes())


def test_repair_no_c22_snapshot_route_in_scenarios():
    text = (KIT / "scenarios.py").read_text(encoding="utf-8")
    assert 'request("GET", "/c22/snapshot"' not in text
    assert "or True" not in text


def test_repair_collect_snapshot_does_not_invent_legacy_ids(scratch):
    profile = scratch / "empty"
    profile.mkdir()
    snap = collect_snapshot(profile, label="empty")
    ids = snap["legacy_video_ids"]
    assert ids["yoink_ids"] == []
    assert ids["timed_present"] is False
    assert ids["text_present"] is False
    assert "c22legacytimed000" not in json.dumps(ids)


def test_repair_inno_uses_agreed_isolation_interface(scratch):
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
    assert "/ISOLATED=1" in joined
    assert "/PROFILE=" in joined
    assert "/PORT=" in joined
    assert "/DIR=" in joined
    assert "/ISOLATEDPROFILE=" not in joined
    assert "/ISOLATEDPORT=" not in joined
    assert str(FORBIDDEN_PORT) not in joined
    with pytest.raises(C22ValidationError, match="Inno"):
        runner.plan_inno(example_manifest(), execute=True)


def test_repair_owned_stop_refuses_missing_identity():
    result = terminate_via_exact_handle(
        pid=1, expected={"pid": 1, "created_ms": None, "executable": None})
    assert result["stopped"] is False
    assert result.get("refused") is True
    assert result.get("taskkill") is False


def test_repair_browser_unexecuted_without_image(scratch):
    receipt = scratch / "receipt"
    package, digest = _package(scratch)
    app = scratch / "Uoink Installed"
    app.mkdir()
    (app / "server.py").write_bytes((KIT / "stub_helper.py").read_bytes())
    helper_port = _free_port()
    fixture_port = _free_port()
    runner = OperatorRunner.create(
        receipt_root=receipt,
        installed_app_path=app,
        package_path=package,
        package_sha256=digest,
        isolated_profile=receipt / "profiles" / "empty",
        isolated_port=helper_port,
        synthetic=True,
        require_space=False,
        require_bundled_python=False,
        skip_ordinary_user_check=True,
    )
    scenarios = ScenarioRunner(runner, fixture_port=fixture_port)
    try:
        scenarios.prepare_profiles()
        outcome = scenarios.run_one("browser_state_checkpoint")
    finally:
        scenarios.close()
    assert outcome["status"] == "unexecuted"
    assert outcome["protocol"]["screenshot"] is None


def test_repair_launch_argv_keeps_runtime_flags(scratch):
    app = scratch / "Uoink Installed"
    app.mkdir()
    (app / "server.py").write_text("print('x')\n", encoding="utf-8")
    profile = scratch / "profile"
    profile.mkdir()
    port = _free_port()
    argv = launch_argv(app, isolated_profile=profile, isolated_port=port,
                       synthetic=True, include_from_install=False)
    assert ISOLATED_PROFILE_FLAG in argv
    assert ISOLATED_PORT_FLAG in argv
    assert str(FORBIDDEN_PORT) not in argv
    prov = provenance_argv(app, synthetic=True)
    assert "-c" in prov


def test_repair_source_runtime_provisions_archived_isolation(scratch):
    profile = scratch / "profile"
    profile.mkdir()
    dest = scratch / "Uoink Installed"
    port = _free_port()
    result = provision(dest=dest, profile=profile, port=port)
    assert result["installed_credit"] is False
    assert result["rejected_stop_not_run"] is True
    iso = dest / "uoink_install_isolation.py"
    assert iso.is_file()
    server = (dest / "server.py").read_text(encoding="utf-8")
    assert "apply_from_process()" in server
    assert server.index("apply_from_process()") < server.index("DATA_ROOT")
    assert (dest / MARKER_FILENAME).is_file()
    marker = json.loads((dest / MARKER_FILENAME).read_text(encoding="utf-8"))
    assert marker["profile"] == str(profile)
    assert marker["port"] == port
    assert "--isolated-stop" not in server.split("apply_from_process()")[0]


def test_repair_source_runtime_helper_and_oracles(scratch):
    """Source-runtime synthetic check against actual server.main.

    Not installed credit. Stub is not the helper. Missing evidence must not
    be recorded as pass.
    """
    live = Path(os.environ.get("LOCALAPPDATA") or "") / "Uoink" / "index.db"
    live_before = live.stat().st_mtime_ns if live.is_file() else None
    package, digest = _package(scratch)
    receipt = scratch / "receipt"
    profile = receipt / "profiles" / "empty"
    helper_port = _free_port()
    fixture_port = _free_port()
    # Receipt root must not exist yet.
    app = scratch / "Uoink Installed"
    provisioned = provision(dest=app, profile=profile, port=helper_port)
    assert "stub_helper" not in (app / "server.py").read_text(encoding="utf-8")[:200]
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
        scenarios.prepare_profiles()
        for scenario_id in SCENARIO_IDS:
            scenarios.run_one(scenario_id)
    finally:
        scenarios.close()
    outcomes = scenarios.outcomes
    assert set(outcomes) == set(SCENARIO_IDS)
    assert outcomes["install"]["status"] == "unexecuted"
    assert outcomes["upgrade_operator_step"]["status"] == "unexecuted"
    assert outcomes["browser_state_checkpoint"]["status"] == "unexecuted"
    assert outcomes["browser_state_checkpoint"]["protocol"]["screenshot"] is None
    assert outcomes["install"]["agreed_inno_shape"] is True
    # Stub-only snapshot route must not appear in recorded HTTP evidence.
    blob = json.dumps(outcomes, default=str)
    assert "/c22/snapshot" not in blob
    # A pass requires measured evidence; health failure is fail/unexecuted.
    empty = outcomes["empty_migration_replay"]
    if empty["status"] == "pass":
        assert empty["first_schema"]["ok"] is True
        assert empty["invented_rows"] is False
    else:
        assert empty["status"] in {"fail", "unexecuted"}
    child = outcomes["registered_child_lifetime"]
    if child["status"] == "pass":
        product = ((child.get("instrument") or {}).get("instrument") or {}).get(
            "product_module", "")
        assert "source_subscriptions" in str(product)
    relaunch = outcomes["whole_helper_relaunch"]
    if relaunch["status"] == "pass":
        assert (relaunch.get("terminated") or {}).get("stopped") is True
        handle = (relaunch.get("terminated") or {}).get("handle_stop") or {}
        assert handle.get("taskkill") is not True
    live_after = live.stat().st_mtime_ns if live.is_file() else None
    assert live_before == live_after
    token = read_token(app, receipt / "profiles" / "empty")
    # Token may be absent if helper never reached TOKEN_PATH write; that is
    # not a pass for scenarios that required it.
    if token:
        assert (receipt / "profiles" / "empty" / "token.txt").is_file()


def test_repair_port_5179_still_rejected_without_probe():
    with pytest.raises(C22ValidationError, match="5179"):
        validate_port(5179)
