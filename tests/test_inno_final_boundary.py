"""Regressions for the 2026-09-09 Inno process and path boundary repair.

Does not edit existing isolation cases, the sealed integrator review file, or
the isolation-repair static checks. Never contacts port 5179, never opens the
live index, and never runs Setup.exe or uninstall.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    token = f"function {name}"
    start = ISS.index(token)
    rest = ISS[start:]
    end = rest.index("\nfunction ", 1)
    return rest[:end]


def _procedure_body(name: str) -> str:
    token = f"procedure {name}"
    start = ISS.index(token)
    rest = ISS[start:]
    next_fn = rest.find("\nfunction ", 1)
    next_proc = rest.find("\nprocedure ", 1)
    ends = [idx for idx in (next_fn, next_proc) if idx != -1]
    end = min(ends) if ends else len(rest)
    return rest[:end]


def test_isolated_mode_requires_documented_close_switches_and_refuses_overrides():
    setup = _function_body("InitializeSetup(): Boolean;")
    close_sw = _function_body("IsolatedCloseSwitchesValid(): Boolean;")
    assert "IsolatedRequestPresent" in setup
    assert "IsolatedSetupRequested" in setup
    assert "IsolatedCloseSwitchesValid" in setup
    assert "isolated-argument-invalid" in setup
    assert "refuse ordinary setup" in setup
    assert "IsolatedCountSwitch('ISOLATED')" in setup
    assert "NOCLOSEAPPLICATIONS" in close_sw
    assert "NORESTARTAPPLICATIONS" in close_sw
    assert "CLOSEAPPLICATIONS" in close_sw
    assert "FORCECLOSEAPPLICATIONS" in close_sw
    assert "RESTARTAPPLICATIONS" in close_sw
    assert "isolated-close-applications-required" in close_sw
    assert "isolated-close-applications-forbidden" in close_sw
    assert close_sw.index("CLOSEAPPLICATIONS") < close_sw.index("NOCLOSEAPPLICATIONS") or (
        "FORCECLOSEAPPLICATIONS" in close_sw
    )
    prepare = ISS.split("function PrepareToInstall", 1)[1].split(
        "procedure VerifyInstalledHelper", 1
    )[0]
    assert "IsolatedCloseSwitchesValid" in prepare
    assert "CloseApplications=force" in ISS
    skip = _function_body("ShouldSkipPage(PageID: Integer): Boolean;")
    assert "wpPreparing" in skip
    assert "does not disable Restart Manager" in skip
    assert "never calls" in skip
    assert "if IsolatedInstall() and (PageID = wpPreparing)" not in skip
    assert "procedure RegisterExtraCloseApplicationsResources" in ISS


def test_missing_isolated_parameters_do_not_select_ordinary_mode():
    setup = _function_body("InitializeSetup(): Boolean;")
    request = _function_body("IsolatedRequestPresent(): Boolean;")
    assert "IsolatedCmdSwitchPresent('ISOLATED')" in request
    assert "IsolatedCmdSwitchPresent('PROFILE')" in request
    assert "IsolatedCmdSwitchPresent('PORT')" in request
    assert "if IsolatedRequestPresent()" in setup
    assert "if not IsolatedSetupRequested()" in setup
    assert "Result := False;" in setup
    assert "Result := IsolatedValidateDeclaredInputs();" in setup
    ordinary_tail = setup.split("if IsolatedRequestPresent()", 1)[1]
    assert "Result := True;" in ordinary_tail
    assert ordinary_tail.index("IsolatedAbort") < ordinary_tail.index("Result := IsolatedValidateDeclaredInputs();")


def test_initialize_uninstall_checks_persisted_evidence_and_owned_stop():
    uninstall = _function_body("InitializeUninstall(): Boolean;")
    stop = _function_body("IsolatedOwnedStop(const AppDir: String): Boolean;")
    persist = _procedure_body("RegisterPreviousData(PreviousDataKey: Integer);")
    persisted = _function_body("IsolatedPersisted(): Boolean;")
    assert "Result := False;" in uninstall
    assert "GetPreviousData('Isolated', '')" in uninstall
    assert "GetPreviousData('Profile', '')" in uninstall
    assert "GetPreviousData('Port', '')" in uninstall
    assert "GetPreviousData('AppDir', '')" in uninstall
    assert "IsolatedOwnedStop" in uninstall
    assert uninstall.index("IsolatedOwnedStop") < uninstall.rindex("Result := True;")
    assert "isolated-install-marker-mismatch" in uninstall
    assert "isolated-install-marker-missing" in uninstall
    assert "isolated-stop-failed" in uninstall
    assert "refusing deletion" in uninstall
    assert "never fall back to ordinary stop-server.bat" in uninstall
    assert "UninstallRun nonzero exit does not gate deletion" in uninstall
    assert "IsolatedMarkerWellFormed" in uninstall
    assert "IsolatedMarkerExact" in uninstall
    assert "--isolated-stop" in stop
    assert "--isolated-from-install-dir" in stop
    assert "ResultCode <> 0" in stop
    assert "not Executed" in stop
    assert "SetPreviousData(PreviousDataKey, 'Isolated', '1')" in persist
    assert "SetPreviousData(PreviousDataKey, 'Profile', IsolatedProfile())" in persist
    assert "SetPreviousData(PreviousDataKey, 'Port', IntToStr(IsolatedPort()))" in persist
    assert "SetPreviousData(PreviousDataKey, 'AppDir'" in persist
    assert "Flag := GetPreviousData('Isolated', '')" in persisted
    assert "CompareText(Trim(Flag), '1')" in persisted
    write = _function_body("WriteIsolatedMarker(): Boolean;")
    assert "IsolatedMarkerExact" in write
    assert "IsolatedMarkerWellFormed" in write
    assert "persistence verification failed" in write
    uninstall_run = ISS.split("[UninstallRun]", 1)[1].split("[UninstallDelete]", 1)[0]
    assert "stop-server.bat" in uninstall_run
    assert "Check: not IsolatedInstall" in uninstall_run
    assert "Check: IsolatedInstall" in uninstall_run
    assert "--isolated-stop" in uninstall_run


def test_reparse_device_and_ambiguous_paths_are_refused_before_marker_ops():
    guard = _function_body("IsolatedGuardPath(const Path, Kind: String): Boolean;")
    profile = _function_body("IsolatedValidateProfile(const Profile: String): Boolean;")
    target = _function_body("IsolatedValidateTargetDir(const AppDir: String): Boolean;")
    read = _function_body("IsolatedReadMarkerBody(const AppDir: String; var Body: String): Boolean;")
    prepare = ISS.split("function PrepareToInstall", 1)[1].split(
        "procedure VerifyInstalledHelper", 1
    )[0]
    uninstall = _function_body("InitializeUninstall(): Boolean;")
    write = _function_body("WriteIsolatedMarker(): Boolean;")
    abs_fn = _function_body("IsolatedPathIsAbsolute(const Profile: String): Boolean;")
    assert "IsolatedExistingAncestorsHaveReparse" in guard
    assert "GetFileAttributesW" in ISS
    assert "FILE_ATTRIBUTE_REPARSE_POINT" in ISS
    assert "GetFinalPathNameByHandleW" in ISS
    assert "isolated-path-reparse" in guard
    assert "isolated-path-unsupported" in guard
    assert "IsolatedPathLooksDeviceOrUnc" in guard
    assert "IsolatedPathIsAmbiguous" in guard
    assert "IsolatedPathHitsLibrary(Resolved" in guard
    assert "IsolatedGuardPath(Profile, '/PROFILE')" in profile
    assert profile.index("IsolatedGuardPath") < profile.index("DirExists(Profile)")
    assert profile.index("IsolatedPathLooksDeviceOrUnc") < profile.index("IsolatedGuardPath")
    assert "IsolatedGuardPath(AppDir, '/DIR')" in target
    isolated_branch = target.split("Profile := IsolatedProfile();", 1)[1]
    assert isolated_branch.index("IsolatedGuardPath(AppDir, '/DIR')") < isolated_branch.index(
        "IsolatedMarkerFileExists(AppDir)"
    )
    assert isolated_branch.index("IsolatedGuardPath(AppDir, '/DIR')") < isolated_branch.index(
        "IsolatedMarkerWellFormed"
    )
    assert "IsolatedExistingAncestorsHaveReparse(AppDir)" in read
    assert "IsolatedPathLooksDeviceOrUnc(AppDir)" in read
    assert "ISOLATED_MARKER_MAX" in read
    assert "IsolatedValidateDeclaredInputs" in prepare
    assert "IsolatedCloseSwitchesValid" in prepare
    assert "IsolatedExistingAncestorsHaveReparse(AppDir)" in uninstall
    assert uninstall.index("IsolatedExistingAncestorsHaveReparse") < uninstall.index(
        "IsolatedOwnedStop"
    )
    assert "IsolatedExistingAncestorsHaveReparse(AppDir)" in write
    assert write.index("IsolatedExistingAncestorsHaveReparse") < write.index(
        "SaveStringToFile"
    )
    assert "S[1] = '\\'" not in abs_fn or "S[2] = '\\'" not in abs_fn
    assert 'Result := (S[2] = \':\') and (S[3] = \'\\\')' in abs_fn
    assert "IsolatedReservedName" in ISS
    assert "CON" in _function_body("IsolatedReservedName(const Component: String): Boolean;")


def test_marker_parser_is_bounded_and_rejects_pos_prefix_duplicate_nested_keys():
    parser = _function_body("IsolatedParseMarker(")
    extract_s = _function_body("IsolatedJsonExtractString(const Body, Key: String; var Value: String): Boolean;")
    extract_i = _function_body("IsolatedJsonExtractInt(const Body, Key: String; var Value: Integer): Boolean;")
    exact = _function_body("IsolatedMarkerExact(const AppDir, Profile: String; Port: Integer): Boolean;")
    well = _function_body("IsolatedMarkerWellFormed(const AppDir: String): Boolean;")
    target = _function_body("IsolatedValidateTargetDir(const AppDir: String): Boolean;")
    assert "Pos(" not in extract_s
    assert "Pos(" not in extract_i
    assert "Pos(" not in parser
    assert 'Needle := \'"\' + Key + \'":\'' not in ISS
    assert "IsolatedParseMarker" in extract_s
    assert "IsolatedParseMarker" in extract_i
    assert "IsolatedParseMarker" in exact
    assert "IsolatedParseMarker" in well
    assert "SeenMode <> 1" in parser
    assert "SeenProfile <> 1" in parser
    assert "Count > 5" in parser
    assert "Body[I] = '{'" in parser
    assert "Body[I] = '['" in parser
    assert "leading zeros" in _function_body("IsolatedJsonParseInt(") or (
        "Body[I] = '0'" in _function_body("IsolatedJsonParseInt(")
    )
    assert "IntToStr(Value) <> Digits" in _function_body("IsolatedJsonParseInt(")
    assert "ISOLATED_MARKER_MAX" in parser
    assert "trailing comma" in parser or "Body[I] = '}'" in parser
    assert "unknown" in parser.lower() or "else\n        Exit;" in parser or "else\n          Exit;" in parser
    assert "refusing to treat an ordinary installation as isolated" in target
    assert "existing isolated-install.json is damaged" in target
    assert target.index("IsolatedGuardPath(AppDir, '/DIR')") < target.index(
        "IsolatedMarkerWellFormed"
    )
