"""Regressions for the 2026-09-09 installer isolation review findings.

Does not edit the original isolation cases or the sealed integrator review
file. Never contacts port 5179, never opens the live index, and never runs
Setup.exe or stock stop/uninstall scripts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import uoink_install_isolation as iso

ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
ISO_SRC = (ROOT / "uoink_install_isolation.py").read_text(encoding="utf-8")


def _initialize_setup_body() -> str:
    start = ISS.index("function InitializeSetup(): Boolean;")
    rest = ISS[start:]
    end = rest.index("\nfunction ", 1)
    return rest[:end]


def test_trailing_isolation_flag_is_malformed():
    for flag in (iso.CLI_PROFILE, iso.CLI_PORT, iso.CLI_FROM_INSTALL):
        with pytest.raises(iso.IsolationError) as caught:
            iso.resolve_from_process([flag], environ={})
        assert caught.value.code == "isolated-argument-invalid"


def test_isolation_flag_value_cannot_be_another_flag(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.resolve_from_process(
            [iso.CLI_PROFILE, iso.CLI_PORT, "5180"],
            environ={},
        )
    assert caught.value.code == "isolated-argument-invalid"


def test_unknown_isolated_flag_is_rejected():
    with pytest.raises(iso.IsolationError) as caught:
        iso.resolve_from_process(["--isolated-unknown", "x"], environ={})
    assert caught.value.code == "isolated-argument-invalid"


def test_duplicate_disagreeing_profile_flags_conflict(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    with pytest.raises(iso.IsolationError) as caught:
        iso.resolve_from_process(
            [iso.CLI_PROFILE, str(first), iso.CLI_PROFILE, str(second), iso.CLI_PORT, "5180"],
            environ={"LOCALAPPDATA": str(tmp_path / "user")},
        )
    assert caught.value.code == "isolated-profile-conflict"


def test_exact_creation_identity_of_this_process_is_alive():
    created = iso.current_process_created_ms()
    assert created is not None
    assert iso._pid_liveness(os.getpid(), created) == "alive"


def test_incomplete_identity_never_authorizes_stop(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    binding = iso.validate_binding(profile=profile, port=5180)
    identity = {
        "mode": iso.ISOLATION_MODE,
        "pid": os.getpid(),
        "created_ms": iso.current_process_created_ms(),
        "executable": "",
        "port": 5180,
        "profile": str(binding.profile),
        "host": "127.0.0.1",
        "nonce": "incomplete",
    }
    (profile / iso.IDENTITY_FILENAME).write_text(json.dumps(identity), encoding="utf-8")
    assert iso.stop_owned_helper(binding) == iso.EXIT_STOP_IDENTITY
    assert (profile / iso.IDENTITY_FILENAME).is_file()


def test_write_runtime_identity_requires_complete_fields(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    binding = iso.validate_binding(profile=profile, port=5180)
    with pytest.raises(iso.IsolationError) as caught:
        iso.write_runtime_identity(
            binding,
            pid=os.getpid(),
            executable="",
            script=str(ROOT / "server.py"),
            created_ms=iso.current_process_created_ms(),
            nonce="x",
        )
    assert caught.value.code == "isolated-identity-incomplete"
    with pytest.raises(iso.IsolationError) as caught:
        iso.write_runtime_identity(
            binding,
            pid=os.getpid(),
            executable=sys.executable,
            script=str(ROOT / "server.py"),
            created_ms=None,
            nonce="x",
        )
    assert caught.value.code == "isolated-identity-incomplete"


def test_terminate_rechecks_identity_on_the_same_open_handle():
    terminate = ISO_SRC.split("def _terminate_owned", 1)[1].split(
        "if __name__", 1
    )[0]
    assert "_windows_handle_liveness" in terminate
    assert "TerminateProcess" in terminate
    assert terminate.index("_windows_handle_liveness") < terminate.index("TerminateProcess")
    assert "_windows_wait_handle_exit" in terminate
    assert "_PROCESS_START_TOLERANCE_MS" not in ISO_SRC


def test_owned_stop_waits_for_exit_before_unlinking_identity(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    decoy = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(60)"],
        cwd=str(profile),
    )
    try:
        deadline = time.time() + 5
        created = None
        image = None
        while time.time() < deadline:
            created = None
            image = iso._process_executable(decoy.pid)
            if os.name == "nt":
                handle, error = iso._windows_open_process(
                    decoy.pid, iso._PROCESS_QUERY_LIMITED_INFORMATION
                )
                if handle:
                    try:
                        created = iso._windows_process_created_ms(handle)
                    finally:
                        iso._windows_close_handle(handle)
            else:
                created = iso._posix_process_created_ms(decoy.pid)
            if created is not None and image:
                break
            time.sleep(0.05)
        assert created is not None and image
        binding = iso.validate_binding(profile=profile, port=5180)
        iso.write_runtime_identity(
            binding,
            pid=decoy.pid,
            executable=image,
            script=str(ROOT / "server.py"),
            created_ms=created,
            nonce="owned-stop",
        )
        assert iso.stop_owned_helper(binding) == iso.EXIT_OK
        assert decoy.poll() is not None
        assert not (profile / iso.IDENTITY_FILENAME).exists()
    finally:
        if decoy.poll() is None:
            decoy.kill()
            decoy.wait(timeout=5)


def test_inno_initialize_setup_does_not_use_unready_app_dir():
    body = _initialize_setup_body()
    assert "ExpandConstant('{app}')" not in body
    assert "IsolatedValidateDeclaredInputs" in body
    assert "function NextButtonClick" in ISS
    assert "WizardDirValue" in ISS
    assert "IsolatedValidateTargetDir(AppDir)" in ISS
    assert "IsolatedValidateTargetDir(WizardDirValue)" in ISS


def test_inno_uninstall_mode_is_persisted_before_stop():
    assert "procedure RegisterPreviousData" in ISS
    assert "SetPreviousData(PreviousDataKey, 'Isolated', '1')" in ISS
    assert "GetPreviousData('Isolated', '')" in ISS
    assert "function IsolatedPersisted(): Boolean;" in ISS
    assert "function InitializeUninstall(): Boolean;" in ISS
    uninstall_run = ISS.split("[UninstallRun]", 1)[1].split("[UninstallDelete]", 1)[0]
    assert "stop-server.bat" in uninstall_run
    assert "Check: not IsolatedInstall" in uninstall_run
    assert "Check: IsolatedInstall" in uninstall_run
    assert "--isolated-stop" in uninstall_run
    prepare = ISS.split("function PrepareToInstall", 1)[1].split(
        "procedure VerifyInstalledHelper", 1
    )[0]
    assert "ordinary setup refuses an isolated target before preparation" in ISS
    assert "IsolatedValidateTargetDir(AppDir)" in prepare
    code_start = prepare.index("if not IsolatedValidateTargetDir(AppDir)")
    assert code_start < prepare.index("ExtractTemporaryFile('upgrade_prep.ps1')")


def test_inno_marker_match_is_exact_and_write_failure_aborts():
    assert "function IsolatedMarkerExact" in ISS
    assert "function IsolatedJsonExtractString" in ISS
    assert "function IsolatedJsonExtractInt" in ISS
    assert "Pos(JsonEscape(Profile)" not in ISS
    assert 'Pos(\'"port": \' + IntToStr(Port)' not in ISS
    assert "isolated-install-marker-write-failed" in ISS
    cur_step = ISS.split("procedure CurStepChanged(CurStep: TSetupStep);", 1)[1]
    assert "RaiseException('isolated-install-marker-write-failed" in cur_step
    verify_body = ISS.split("procedure VerifyInstalledHelper();", 1)[1].split(
        "procedure CurStepChanged", 1
    )[0]
    assert "RaiseException" not in verify_body


def test_inno_isolated_names_and_close_applications_stay_bounded():
    assert "Name: \"{group}\\Uoink Isolated\"" in ISS
    assert "Name: \"{group}\\Stop Uoink Isolated\"" in ISS
    assert "Name: \"{autodesktop}\\Uoink Isolated\"" in ISS
    assert "Name: \"{group}\\Uninstall Uoink Isolated\"" in ISS
    assert "function GetInstallAppId" in ISS
    assert "{1CCDA47D-2347-43D1-99F4-BD6E7C231288}" in ISS
    assert "{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}" in ISS
    assert "CloseApplications=force" in ISS
    assert "procedure RegisterExtraCloseApplicationsResources" in ISS
    assert "wpPreparing" in ISS
    assert "Uoink Isolated" in ISS


def test_helper_records_real_process_image():
    server_src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "current_process_executable()" in server_src
    assert "current_process_created_ms()" in server_src
    assert "isolated identity write failed" in server_src
