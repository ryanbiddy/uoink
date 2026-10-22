"""Offline signing contracts. Apple tools and all payload execution are mocked."""
from __future__ import annotations

import io
from contextlib import contextmanager
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import build_bundle
import sign_archives as archives
import sign_notarize as signing
import verify_signing
import quarantine_smoke
import receipt
from tests.test_mac_receipt import rig  # Existing full installed-receipt harness.

TEAM = "WTGFF582VY"
IDENTITY = f"Developer ID Application: Fixture Owner ({TEAM})"
MACHO = b"\xcf\xfa\xed\xfe" + b"fixture"


def make_app(root):
    app = root / "Uoink.app"
    for name in ("Contents/MacOS/Uoink", "Contents/Helpers/ffmpeg", "Contents/Helpers/ffprobe",
                 "Contents/Resources/Python/bin/python3", "Contents/Resources/Python/lib/native.so"):
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(MACHO)
    (app / "Contents/Helpers/uoink").write_bytes(b"#!/bin/sh\ntrue\n")
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Uoink"}))
    return app


def test_developer_signing_commands_cover_all_code_without_entitlements_or_deep(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    calls = []
    monkeypatch.setattr(signing, "tool", lambda argv, **kw:
                        calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    for path in build_bundle.signing_order(app):
        signing.sign(path, IDENTITY, tmp_path / "fixture-kc", tmp_path)
    assert calls[-1][-1] == app
    assert len(calls) == 7
    for call in calls:
        assert "--deep" not in call and "--entitlements" not in call
        assert call[call.index("--options") + 1] == "runtime"
        assert "--timestamp" in call and "--timestamp=none" not in call
        assert call[call.index("--sign") + 1] == IDENTITY
        assert call[call.index("--keychain") + 1] == tmp_path / "fixture-kc"


@pytest.mark.parametrize("output,ok", [
    (f'1) ABC "{IDENTITY}"\n1 valid identities found', True),
    ('1) ABC "Developer ID Application: Someone (AAAAAAAAAA)"', False),
    ('0 valid identities found', False),
    (f'"{IDENTITY}"\n"{IDENTITY}"', False),
    ('"Apple Development: Fixture (WTGFF582VY)"', False),
])
def test_identity_is_read_from_import_and_team_is_enforced(output, ok):
    if ok:
        assert signing.identity_from_output(output, TEAM) == IDENTITY
    else:
        with pytest.raises(ValueError):
            signing.identity_from_output(output, TEAM)


def test_private_import_and_cleanup_never_print_password_or_read_key_files(tmp_path, monkeypatch, capsys):
    for name in ("MACOS_CERT_P12_BASE64", "NOTARY_API_KEY_P8_BASE64"):
        monkeypatch.setenv(name, "Zml4dHVyZQ==")
    monkeypatch.setenv("MACOS_CERT_PASSWORD", "fixture-import-password")
    monkeypatch.setattr(signing.secrets, "token_hex", lambda _: "random-fixture-password")
    calls = []

    def tool(argv, **kw):
        calls.append(argv)
        out = '"original.keychain-db"' if argv[1] in {"list-keychains", "default-keychain"} else ""
        if "create-keychain" in argv:
            Path(argv[-1]).touch()
        if "find-identity" in argv:
            out = f'1) ABC "{IDENTITY}"'
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(signing, "tool", tool)
    private = tmp_path / "private"
    identity, keychain = signing.prepare_identity(private, TEAM)
    assert identity == IDENTITY
    assert (private / "identity.p12").exists() and (private / "notary.p8").exists()
    imported = next(c for c in calls if private / "identity.p12" in c)
    assert imported[-2:] == ["-T", "/usr/bin/codesign"] and "-A" not in imported
    created = next(i for i, c in enumerate(calls) if "create-keychain" in c)
    assert calls[created + 1] == ["security", "import", signing.DEVELOPER_ID_G2, "-k", keychain]
    assert ["security", "default-keychain", "-d", "user", "-s", keychain] in calls
    assert any("set-key-partition-list" in c for c in calls)
    assert ["security", "set-keychain-settings", "-lut", "21600", keychain] in calls
    assert capsys.readouterr().out == "::add-mask::random-fixture-password\n"
    signing.cleanup(private)
    assert not private.exists()
    assert ["security", "delete-keychain", keychain] in calls
    assert ["security", "list-keychains", "-d", "user", "-s", "original.keychain-db"] in calls
    assert ["security", "default-keychain", "-d", "user", "-s", "original.keychain-db"] in calls


@pytest.mark.parametrize("operation", ["list-keychains", "default-keychain", "delete-keychain"])
def test_cleanup_removes_decoded_files_even_when_security_fails(tmp_path, monkeypatch, operation):
    private = tmp_path / "private"
    private.mkdir()
    (private / "search-list.json").write_text('["original"]')
    (private / "default-keychain.json").write_text('["original"]')
    (private / "signing.keychain-db").touch()
    (private / "notary.p8").touch()
    calls = []
    monkeypatch.setattr(signing, "tool", lambda argv, **kw: calls.append(argv) or SimpleNamespace(
        returncode=1 if operation in argv else 0, stdout="", stderr="private error"))
    with pytest.raises(RuntimeError, match="cleanup failed"):
        signing.cleanup(private)
    assert not private.exists()
    assert [c[1] for c in calls] == ["list-keychains", "default-keychain", "delete-keychain"]


def test_intermediate_is_pinned_and_wrong_file_is_refused_before_private_import(tmp_path, monkeypatch):
    assert signing.verified_intermediate() == signing.DEVELOPER_ID_G2
    wrong = tmp_path / "wrong.cer"
    wrong.write_bytes(b"not the pinned public Apple G2 intermediate")
    monkeypatch.setattr(signing, "DEVELOPER_ID_G2", wrong)
    monkeypatch.setattr(signing, "tool", lambda *a, **kw: pytest.fail("No keychain changes before hash check"))
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        signing.prepare_identity(tmp_path / "private", TEAM)
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("failure", ["intermediate-import", "second-codesign"])
def test_sign_phase_restores_keychain_state_after_failure(tmp_path, monkeypatch, failure):
    app = make_app(tmp_path)
    (app / "Contents/Resources/VERSION").write_text("3.10.0")
    notices = app / "Contents/Resources/notices"
    notices.mkdir()
    (notices / "build.json").write_text('{}')
    for name in ("MACOS_CERT_P12_BASE64", "NOTARY_API_KEY_P8_BASE64"):
        monkeypatch.setenv(name, "Zml4dHVyZQ==")
    monkeypatch.setenv("MACOS_CERT_PASSWORD", "fixture-password")
    monkeypatch.setenv("MACOS_TEAM_ID", TEAM)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    monkeypatch.setattr(signing.platform, "machine", lambda: "arm64")
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(signing.sys, "argv", ["sign_notarize.py", "sign", "--output", str(tmp_path),
                                           "--evidence", str(evidence)])
    monkeypatch.setattr(signing, "sign_archives", lambda *a: None)
    original = ["/Users/runner/Library/Keychains/login with spaces.keychain-db",
                "/Library/Keychains/System.keychain"]
    state = {"list-keychains": list(original), "default-keychain": original[:1]}
    calls = []
    signed = 0

    def tool(argv, **kw):
        nonlocal signed
        calls.append(argv)
        out, code = "", 0
        if argv[0] == "codesign":
            signed += 1
            keychain = str(signing.private_path() / "signing.keychain-db")
            assert state == {"list-keychains": [keychain], "default-keychain": [keychain]}
            assert any(c[:3] == ["security", "import", signing.DEVELOPER_ID_G2] for c in calls[:-1])
            code = int(signed == 2)
        elif argv[1] in state:
            if "-s" in argv:
                state[argv[1]] = [str(p) for p in argv[5:]]
            else:
                out = "\n".join(f'"{p}"' for p in state[argv[1]])
        elif argv[1] == "create-keychain":
            Path(argv[-1]).touch()
        elif argv[1] == "import" and argv[2] == signing.DEVELOPER_ID_G2:
            code = int(failure == "intermediate-import")
        elif argv[1] == "find-identity":
            out = f'1) ABC "{IDENTITY}"'
        return SimpleNamespace(returncode=code, stdout=out, stderr="fixture tool failure" if code else "")

    monkeypatch.setattr(signing, "tool", tool)
    with pytest.raises(RuntimeError, match="failed"):
        signing.main()
    assert signed == (2 if failure == "second-codesign" else 0)
    assert state == {"list-keychains": original, "default-keychain": original[:1]}
    assert not signing.private_path().exists()
    assert calls[-1][1] == "delete-keychain"
    assert (evidence / "codesign-keychain-diagnostics.txt").exists() == (signed == 2)
    # The workflow's always() cleanup is safe after the sign phase's finally.
    signing.cleanup(signing.private_path())


@pytest.mark.parametrize("failure", ["exit", "timeout", "start"])
def test_codesign_failure_diagnostics_are_public_and_complete(tmp_path, monkeypatch, capsys, failure):
    values = {name: "secret-fixture-" + name.lower() for name in (
        "MACOS_CERT_P12_BASE64", "MACOS_CERT_PASSWORD", "NOTARY_API_KEY_P8_BASE64",
        "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID")}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    private_output = " ".join(values.values())
    calls = []
    keychain = tmp_path / "private/signing.keychain-db"

    def run(argv, **kw):
        calls.append(argv)
        if argv[0] == "codesign":
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, 300, output=private_output.encode())
            if failure == "start":
                raise OSError(private_output)
        # Missing certificates must not stop the remaining diagnostic queries.
        if "System.keychain" in argv[-1]:
            raise OSError(private_output)
        return SimpleNamespace(returncode=1, stdout=private_output, stderr=private_output)

    monkeypatch.setattr(signing.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="codesign") as error:
        signing.sign(tmp_path / "native.so", IDENTITY, keychain, tmp_path)
    assert calls[1:] == [
        ["security", "find-identity", "-v", "-p", "codesigning", str(keychain)],
        *[["security", "find-certificate", "-a", "-Z", "-c", "Developer ID Certification Authority", source]
          for source in (str(keychain), "/Library/Keychains/System.keychain",
                         "/System/Library/Keychains/SystemRootCertificates.keychain")],
        ["security", "list-keychains", "-d", "user"],
        ["security", "default-keychain", "-d", "user"],
    ]
    diagnostic = (tmp_path / "codesign-keychain-diagnostics.txt").read_text()
    assert "[redacted]" in diagnostic and "query unavailable (OSError)" in diagnostic
    captured = capsys.readouterr()
    public = "".join(p.read_text() for p in tmp_path.glob("*.txt")) + str(error.value) + captured.out + captured.err
    assert all(value not in public for value in values.values())


@pytest.fixture
def notary_rig(tmp_path, monkeypatch):
    values = {name: "secret-fixture-" + name.lower() for name in (
        "MACOS_CERT_P12_BASE64", "MACOS_CERT_PASSWORD", "NOTARY_API_KEY_P8_BASE64",
        "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID")}
    values["MACOS_CERT_PASSWORD"] += '\n"quoted"\\password'
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in ("NOTARY_APP_TIMEOUT_MINUTES", "NOTARY_DMG_TIMEOUT_MINUTES", "NOTARY_REUSE_SUBMISSION_ID"):
        monkeypatch.delenv(name, raising=False)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    rig = SimpleNamespace(calls=[], replies=[], now=0, evidence=evidence,
                          private=tmp_path / "private", values=values)

    def sleep(seconds):
        rig.now += seconds

    def tool(argv, **kw):
        operation, response, code, stream = rig.replies.pop(0)
        assert argv[2] == operation
        # Every poll sees the durable ID, even when submit returned stderr JSON.
        if operation == "info" and any(call[0][2] == "submit" for call in rig.calls):
            saved = list(evidence.glob("notary-*-submission.json"))
            assert len(saved) == 1 and json.loads(saved[0].read_text())["id"] == argv[3]
        rig.calls.append((argv, kw))
        rig.now += 2
        secret_text = " ".join(values.values())
        if isinstance(response, dict):
            response = json.dumps({**response, "message": secret_text})
        output = {"stdout": "", "stderr": ""}
        output[stream] = response
        output["stderr" if stream == "stdout" else "stdout"] = secret_text
        return SimpleNamespace(returncode=code, **output)

    monkeypatch.setattr(signing, "tool", tool)
    monkeypatch.setattr(signing.time, "monotonic", lambda: rig.now)
    monkeypatch.setattr(signing.time, "sleep", sleep)
    yield rig
    assert not rig.replies
    # Inspect every evidence file, including escaped JSON and both tool streams.
    for path in evidence.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            for value in values.values():
                assert value not in content and json.dumps(value)[1:-1] not in content


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_notary_submit_records_id_from_either_stream_without_wait(notary_rig, stream):
    rig = notary_rig
    rig.replies = [("submit", {"id": "submission-123"}, 1, stream),
                   ("info", {"id": "submission-123", "status": "Accepted"}, 0, stream)]
    signing.notarize(rig.evidence / "app.zip", "app", rig.private, rig.evidence)
    submit, kwargs = rig.calls[0]
    assert submit[:3] == ["xcrun", "notarytool", "submit"]
    assert "--wait" not in submit and "--timeout" not in submit
    assert submit[-2:] == ["--output-format", "json"]
    assert submit[submit.index("--key") + 1] == rig.private / "notary.p8"
    assert submit[submit.index("--key-id") + 1] == rig.values["NOTARY_API_KEY_ID"]
    assert submit[submit.index("--issuer") + 1] == rig.values["NOTARY_API_ISSUER_ID"]
    assert kwargs["timeout"] == 900
    assert rig.calls[1][0][:4] == ["xcrun", "notarytool", "info", "submission-123"]
    assert json.loads((rig.evidence / "notary-app.json").read_text())["status"] == "Accepted"


def test_notary_polls_in_progress_and_transient_errors_until_accepted(notary_rig):
    rig = notary_rig
    rig.replies = [("submit", {"id": "submission-123"}, 0, "stdout"),
                   ("info", {"id": "submission-123", "status": "In Progress"}, 0, "stdout"),
                   ("info", {"id": "submission-123", "status": "In Progress"}, 1, "stderr"),
                   ("info", "temporary service error", 1, "stderr"),
                   ("info", {"id": "submission-123", "status": "Accepted"}, 0, "stdout")]
    signing.notarize(rig.evidence / "app.zip", "app", rig.private, rig.evidence)
    records = [json.loads(line) for line in (rig.evidence / "notary-app-polls.jsonl").read_text().splitlines()]
    assert [r["status"] for r in records] == ["Unknown", "In Progress", "In Progress", "Unknown", "Accepted"]
    assert [r["poll"] for r in records] == list(range(5))
    assert [r["elapsed_seconds"] for r in records] == [2, 4, 66, 128, 190]
    assert records[-1]["budget_seconds"] == 150 * 60
    assert len(list(rig.evidence.glob("notary-app-poll-*-stderr.txt"))) == 4
    assert all(call[0][2] != "log" for call in rig.calls)


@pytest.mark.parametrize("status", ["Invalid", "Rejected"])
def test_notary_terminal_rejection_fetches_log(notary_rig, status):
    rig = notary_rig
    rig.replies = [("submit", {"id": "submission-bad"}, 0, "stdout"),
                   ("info", {"id": "submission-bad", "status": status}, 1, "stderr"),
                   ("log", {"issues": [{"path": "Uoink.app", "message": "bad signature"}]}, 0, "stderr")]
    with pytest.raises(RuntimeError, match=f"submission-bad was {status}"):
        signing.notarize(rig.evidence / "app.zip", "app", rig.private, rig.evidence)
    assert rig.calls[-1][0][:4] == ["xcrun", "notarytool", "log", "submission-bad"]
    assert json.loads((rig.evidence / "notary-app-log.json").read_text())["issues"]


@pytest.mark.parametrize("label,minutes", [("app", 1), ("dmg", 2)])
def test_notary_budget_exhaustion_names_id_and_bounds_calls(notary_rig, monkeypatch, label, minutes):
    rig = notary_rig
    monkeypatch.setenv(f"NOTARY_{label.upper()}_TIMEOUT_MINUTES", str(minutes))
    rig.replies = [("submit", {"id": "submission-pending"}, 0, "stdout")]
    rig.replies += [("info", {"id": "submission-pending", "status": "In Progress"}, 0, "stdout")] * minutes
    with pytest.raises(RuntimeError, match=f"submission-pending exhausted its {minutes}-minute budget") as error:
        signing.notarize(rig.evidence / f"payload.{label}", label, rig.private, rig.evidence)
    assert "notarytool info submission-pending" in str(error.value)
    assert rig.now == minutes * 60
    assert len(rig.calls) == minutes + 1  # No resubmission or log fetch for pending work.
    assert rig.calls[0][1]["timeout"] == minutes * 60
    assert rig.calls[-1][1]["timeout"] <= minutes * 60 - 2
    latest = json.loads((rig.evidence / f"notary-{label}.json").read_text())
    assert latest["id"] == "submission-pending" and latest["elapsed_seconds"] == minutes * 60
    assert latest["budget_exhausted"]
    records = (rig.evidence / f"notary-{label}-polls.jsonl").read_text().splitlines()
    assert len(records) == len(rig.calls)  # Sleeping to the deadline is not another poll.


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid"])
def test_notary_invalid_budgets_fail_before_tools(notary_rig, monkeypatch, value):
    monkeypatch.setenv("NOTARY_APP_TIMEOUT_MINUTES", value)
    with pytest.raises(ValueError, match="positive whole number"):
        signing.notarize(Path("app.zip"), "app", notary_rig.private, notary_rig.evidence)
    assert not notary_rig.calls


def test_notary_default_budgets(notary_rig):
    assert signing.notary_budget_seconds("app") == 150 * 60
    assert signing.notary_budget_seconds("dmg") == 90 * 60


@pytest.mark.parametrize("response", ["not JSON", "[]", {"status": "Accepted"}])
def test_notary_missing_id_fails_without_resubmitting(notary_rig, response):
    rig = notary_rig
    rig.replies = [("submit", response, 1, "stderr")]
    with pytest.raises(RuntimeError, match="no submission id"):
        signing.notarize(Path("app.zip"), "app", rig.private, rig.evidence)
    assert len(rig.calls) == 1


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_tool_timeout_does_not_expose_command_or_credentials(monkeypatch, stream):
    def timeout(*args, **kwargs):
        output = {"output" if stream == "stdout" else "stderr": b'{"id":"123"}'}
        raise subprocess.TimeoutExpired(["security", "private-password"], 1, **output)
    monkeypatch.setattr(signing.subprocess, "run", timeout)
    result = signing.tool(["security", "private-password"], timeout=1)
    assert result.returncode == 124 and "private-password" not in result.stderr
    assert getattr(result, stream) == '{"id":"123"}'


def test_notary_output_redacts_auth_values(monkeypatch):
    monkeypatch.setenv("NOTARY_API_KEY_ID", "fixture-key-id")
    monkeypatch.setenv("MACOS_CERT_PASSWORD", "fixture-password")
    assert signing.public_output("fixture-key-id fixture-password") == "[redacted] [redacted]"


@pytest.mark.parametrize("failure", [None, "staple", "validate"])
def test_stapler_commands_and_failures(tmp_path, monkeypatch, failure):
    calls = []
    monkeypatch.setattr(signing, "tool", lambda argv, **kw: calls.append(argv) or SimpleNamespace(
        returncode=1 if failure in argv else 0, stdout="fixture", stderr=""))
    if failure:
        with pytest.raises(RuntimeError, match="stapler"):
            signing.staple(tmp_path / "Uoink.app", "app", tmp_path)
    else:
        signing.staple(tmp_path / "Uoink.app", "app", tmp_path)
        assert [c[:3] for c in calls] == [["xcrun", "stapler", "staple"], ["xcrun", "stapler", "validate"]]


@pytest.mark.parametrize("reuse", ["off", "accepted", "staple-fails"])
def test_release_sequence_staples_app_before_dmg_and_hashes_final_bytes(tmp_path, monkeypatch, reuse):
    monkeypatch.setenv("NOTARY_API_KEY_ID", "fixture-key-id")
    monkeypatch.setenv("NOTARY_API_ISSUER_ID", "fixture-issuer")
    monkeypatch.delenv("NOTARY_REUSE_SUBMISSION_ID", raising=False)
    if reuse != "off":
        monkeypatch.setenv("NOTARY_REUSE_SUBMISSION_ID", "968ac10a-dc40-435f-89a5-85ddfb941ab9")
    app = make_app(tmp_path)
    (app / "Contents/Resources/VERSION").write_text("3.10.0")
    notices = app / "Contents/Resources/notices"
    notices.mkdir()
    (notices / "build.json").write_text('{}')
    events = []
    monkeypatch.setattr(signing, "prepare_identity", lambda *a: (IDENTITY, tmp_path / "kc"))
    monkeypatch.setattr(signing, "sign_archives", lambda *a: events.append("archives"))
    monkeypatch.setattr(signing, "sign", lambda path, *a: events.append("sign " + path.name))
    monkeypatch.setattr(signing, "notarize", lambda path, label, *a: events.append("notarize " + label))

    def tool(argv, **kw):
        assert argv[:4] == ["xcrun", "notarytool", "info", "968ac10a-dc40-435f-89a5-85ddfb941ab9"]
        events.append("reuse info")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"id": "968ac10a-dc40-435f-89a5-85ddfb941ab9", "status": "Accepted"}),
                               stderr="")

    monkeypatch.setattr(signing, "tool", tool)

    def staple(path, label, evidence):
        events.append("staple " + label)
        if label == "app-reuse" and reuse == "staple-fails":
            raise RuntimeError("stapler staple failed on app-reuse")
        if label == "dmg":
            path.write_bytes(b"final stapled bytes")

    def create(app, output, version, *, signed):
        assert signed and events[-1] == ("staple app-reuse" if reuse == "accepted" else "staple app")
        events.append("create dmg")
        path = output / "fixture.dmg"
        path.write_bytes(b"before signing")
        return path

    monkeypatch.setattr(signing, "staple", staple)
    monkeypatch.setattr(signing, "create_dmg", create)

    def checked(argv, **kw):
        assert reuse != "accepted", "Do not create/upload a ZIP when the old ticket fits"
        events.append("zip app")
        Path(argv[-1]).touch()

    monkeypatch.setattr(signing, "checked", checked)
    signing.sign_release(tmp_path, tmp_path / "evidence", tmp_path / "private", TEAM)
    assert events[-4:] == ["create dmg", "sign fixture.dmg", "notarize dmg", "staple dmg"]
    if reuse == "accepted":
        assert events[-7:-4] == ["sign Uoink.app", "reuse info", "staple app-reuse"]
        assert "notarize app" not in events
    else:
        assert events[-7:-4] == ["zip app", "notarize app", "staple app"]
        if reuse == "staple-fails":
            assert events.index("staple app-reuse") < events.index("zip app")
    assert not (tmp_path / "notary-app.zip").exists()
    assert json.loads((tmp_path / "dmg.json").read_text())["sha256"] == build_bundle.sha256(tmp_path / "fixture.dmg")


@pytest.mark.parametrize("case,expected", [("accepted", True), ("pending", False), ("info-fails", False),
                                          ("staple-fails", False), ("validate-fails", False)])
def test_reuse_requires_accepted_and_matching_validated_ticket(notary_rig, monkeypatch, case, expected):
    rig = notary_rig
    monkeypatch.setenv("NOTARY_REUSE_SUBMISSION_ID", "968ac10a-dc40-435f-89a5-85ddfb941ab9")
    status = "In Progress" if case == "pending" else "Accepted"
    rig.replies = [("info", {"id": "968ac10a-dc40-435f-89a5-85ddfb941ab9", "status": status},
                    1 if case == "info-fails" else 0, "stderr")]
    if case not in ("pending", "info-fails"):
        rig.replies.append(("staple", "ticket output", 1 if case == "staple-fails" else 0, "stdout"))
        if case != "staple-fails":
            rig.replies.append(("validate", "ticket output", 1 if case == "validate-fails" else 0, "stdout"))
    assert signing.reuse_notarization(Path("Uoink.app"), rig.private, rig.evidence) is expected
    assert json.loads((rig.evidence / "notary-app-reuse.json").read_text())["reused"] is expected
    assert rig.calls[0][0][:4] == ["xcrun", "notarytool", "info", "968ac10a-dc40-435f-89a5-85ddfb941ab9"]
    assert all(call[0][2] != "submit" for call in rig.calls)


def test_reuse_is_off_by_default(notary_rig):
    assert not signing.reuse_notarization(Path("Uoink.app"), notary_rig.private, notary_rig.evidence)
    assert not notary_rig.calls and not list(notary_rig.evidence.iterdir())


def zip_bytes(entries):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return result.getvalue()


def mock_archive_tools(monkeypatch):
    # Emulate ditto/tar for portable tests, retaining the real recursive walker,
    # safe preflight, native detection, shared signing order and replacement path.
    def run(argv, **kw):
        if argv[:3] == ["ditto", "-x", "-k"]:
            with zipfile.ZipFile(argv[3]) as source:
                source.extractall(argv[4])
        elif argv[0] == "ditto":
            root, destination = argv[-2:]
            with zipfile.ZipFile(destination, "w") as target:
                for path in root.rglob("*"):
                    if path.is_file():
                        target.write(path, path.relative_to(root).as_posix())
        else:
            destination, root = argv[5], argv[7]
            with tarfile.open(destination, "w") as target:
                target.add(root, arcname=".")
    monkeypatch.setattr(archives, "run", run)


@pytest.mark.parametrize("suffix", [".zip", ".whl", ".egg", ".jar"])
def test_nested_archives_are_signed_inside_out_and_pure_data_is_unchanged(tmp_path, monkeypatch, suffix):
    app = make_app(tmp_path)
    mock_archive_tools(monkeypatch)
    inner = zip_bytes({"Nested.app/Contents/Info.plist": plistlib.dumps({"CFBundleExecutable": "Nested"}),
                       "Nested.app/Contents/MacOS/Nested": MACHO,
                       "Nested.app/Contents/Helpers/shim": b"#!/bin/sh\ntrue"})
    wrapped = io.BytesIO()
    with tarfile.open(fileobj=wrapped, mode="w") as tar:
        entry = tarfile.TarInfo("inner" + suffix)
        entry.size = len(inner)
        tar.addfile(entry, io.BytesIO(inner))
    outer = app / ("outer" + suffix)
    outer.write_bytes(zip_bytes({"middle.tar": wrapped.getvalue(), "libnative.dylib": MACHO}))
    pure = app / "pure.jar"
    pure.write_bytes(zip_bytes({"Example.class": b"\xca\xfe\xba\xbe\x00\x00\x00\x34", "readme": b"data"}))
    before = pure.read_bytes()
    signed = []

    def sign(path):
        signed.append(path.name)
        if path.is_file():
            path.write_bytes(path.read_bytes() + b"signed")

    rows = archives.sign_archives(app, tmp_path / "archives.json", sign)
    assert signed == ["shim", "Nested", "Nested.app", "libnative.dylib"]
    assert pure.read_bytes() == before
    assert len([r for r in rows if r["action"] == "signed-and-repacked"]) == 3
    assert any("!/middle.tar!/inner" in r["path"] for r in rows)
    with zipfile.ZipFile(outer) as result:
        assert result.read("libnative.dylib").endswith(b"signed")
        with tarfile.open(fileobj=io.BytesIO(result.read("middle.tar"))) as middle:
            inner_name = next(m for m in middle if m.name.endswith(suffix))
            with zipfile.ZipFile(io.BytesIO(middle.extractfile(inner_name).read())) as deepest:
                assert deepest.read("Nested.app/Contents/MacOS/Nested").endswith(b"signed")


@pytest.mark.parametrize("name", ["../escape", "/outside", "C:/outside", "a\\..\\outside"])
def test_archive_preflight_refuses_traversal_before_tools(tmp_path, monkeypatch, name):
    path = tmp_path / "unsafe.zip"
    path.write_bytes(zip_bytes({name: MACHO}))
    monkeypatch.setattr(archives, "run", lambda *a, **kw: pytest.fail("Unsafe archive must not extract"))
    with pytest.raises(ValueError, match="Unsafe"):
        archives.unpack(path, tmp_path / "root", "zip", [10000])


def signed_result(argv):
    result = {"exit": 0, "stdout": "", "stderr": ""}
    if "-dv" in argv:
        result["stderr"] = (f"TeamIdentifier={TEAM}\nAuthority={IDENTITY}\n"
                            "CodeDirectory flags=0x10000(runtime)\nTimestamp=Oct 21, 2026\nCDHash=" + "a" * 40 + "\n")
    if "spctl" in str(argv[0]):
        result["stderr"] = f"{argv[-1]}: accepted\nsource=Notarized Developer ID\n"
    return result


@pytest.mark.parametrize("failure", [None, "adhoc", "wrong_team", "app_ticket", "dmg_ticket",
                                      "rejected", "wrong_source", "no_runtime", "no_timestamp", "bad_signature"])
def test_strict_receipt_refusals_and_success_with_existing_checks(rig, tmp_path, monkeypatch, failure):
    original = receipt.command

    def command(argv, **kw):
        base = original(argv, **kw)
        result = {**base, **signed_result(argv)} if any(
            tool in str(argv[0]) for tool in ("codesign", "spctl", "xcrun")) else base
        if "-dv" in argv:
            if failure == "adhoc":
                result["stderr"] += "Signature=adhoc\n"
            if failure == "wrong_team":
                result["stderr"] = result["stderr"].replace(TEAM, "AAAAAAAAAA")
            if failure == "no_runtime":
                result["stderr"] = result["stderr"].replace("runtime", "none")
            if failure == "no_timestamp":
                result["stderr"] = result["stderr"].replace("Timestamp=Oct 21, 2026", "Timestamp=none")
        if "validate" in argv and failure == ("dmg_ticket" if Path(argv[-1]).suffix == ".dmg" else "app_ticket"):
            result["exit"] = 1
        if "spctl" in str(argv[0]):
            if failure == "rejected":
                result.update(exit=3, stderr="rejected")
            if failure == "wrong_source":
                result["stderr"] = result["stderr"].replace("Notarized Developer ID", "Developer ID")
        if "--verify" in argv and failure == "bad_signature":
            result["exit"] = 1
        return result

    monkeypatch.setattr(receipt, "command", command)
    result = receipt.collect(rig.dmg, tmp_path, receipt.sha256(rig.dmg),
                             require_notarized=True, expected_team_id=TEAM)
    assert result["verdict"] == ("fail" if failure else "installed-pass")
    if failure:
        assert result["cleanup"]["refused_before_execution"]
        assert not any("-c" in call or "--remove" in call for call in rig.calls)
    if not failure:
        assert result["notarization"]["ok"] and result["notarization_after_runtime"]["ok"]
        assert result["runtime"]["ok"] and result["cleanup"]["app_gone"]


def test_strict_receipt_requires_team_before_install(rig, tmp_path, monkeypatch):
    monkeypatch.setattr(receipt.dmg_smoke, "installed_dmg", lambda *a: pytest.fail("Do not mount without team"))
    result = receipt.collect(rig.dmg, tmp_path, receipt.sha256(rig.dmg), require_notarized=True)
    assert result["verdict"] == "fail" and "expected-team-id" in result["reasons"][0]


def test_quarantine_refuses_to_execute_while_keys_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    (tmp_path / "uoink-signing-private").mkdir()
    with pytest.raises(ValueError, match="keys must be deleted"):
        quarantine_smoke.smoke(tmp_path / "x.dmg", tmp_path / "output", TEAM)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("quarantine_present", [True, False])
def test_quarantine_copy_assessment_and_launch_sequence(tmp_path, monkeypatch, quarantine_present):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    dmg = tmp_path / "signed.dmg"
    dmg.write_bytes(b"signed final bytes")
    app = make_app(tmp_path / "Applications With Spaces")
    calls, events = [], []

    @contextmanager
    def installed(download, scratch, report):
        assert download != dmg and download.read_bytes() == dmg.read_bytes()
        events.append("install")
        try:
            yield app, app
        finally:
            report["detached"] = True

    def command(argv):
        calls.append(argv)
        result = signed_result(argv)
        if argv[:2] == ["xattr", "-p"]:
            result.update(exit=0 if quarantine_present else 1,
                          stdout="0083;fixture;Safari;id" if quarantine_present else "")
        return result

    original_verify = verify_signing.verify_notarized

    def verify(app, dmg, team, report):
        events.append("assess")
        original_verify(app, dmg, team, report, execute=command)

    monkeypatch.setattr(quarantine_smoke.dmg_smoke, "installed_dmg", installed)
    monkeypatch.setattr(quarantine_smoke, "command", command)
    monkeypatch.setattr(quarantine_smoke, "verify_notarized", verify)
    monkeypatch.setattr(quarantine_smoke.shutil, "which", lambda tool: "/usr/bin/syspolicy_check")
    monkeypatch.setattr(quarantine_smoke, "launch", lambda *a: events.append("launch"))
    output = tmp_path / "output"
    if quarantine_present:
        quarantine_smoke.smoke(dmg, output, TEAM)
        assert events == ["install", "assess", "launch", "assess"]
        assert any(c[:2] == ["/usr/bin/syspolicy_check", "distribution"] for c in calls)
        assert any("context:primary-signature" in c for c in calls)
        assert any("--verbose=2" in c and "--strict" in c and "--deep" in c for c in calls)
    else:
        with pytest.raises(ValueError, match="lost quarantine"):
            quarantine_smoke.smoke(dmg, output, TEAM)
        assert events == ["install"]
    writes = [c for c in calls if c[:2] == ["xattr", "-w"]]
    assert Path(writes[0][-1]).suffix == ".dmg" and ";Safari;" in writes[0][3]
    if quarantine_present:
        # The copied app keeps its quarantine and gains only the user-approved flag (0x40),
        # the state macOS records when a person clicks Open on first launch.
        assert len(writes) == 2 and Path(writes[1][-1]).suffix == ".app"
        assert writes[1][3] == "00c3;fixture;Safari;id"
    else:
        assert len(writes) == 1
    result = json.loads((output / "quarantine.json").read_text())
    assert result["ok"] == quarantine_present and result["install"]["detached"]


def test_quarantined_launch_uses_launchservices_disposable_env_and_bounded_wait(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    (app / "Contents/Resources/VERSION").write_text("3.10.0")
    calls = []

    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def bind(self, address):
            assert address == ("127.0.0.1", 0)
        def getsockname(self):
            return ("127.0.0.1", 18081)

    monkeypatch.setattr(quarantine_smoke.socket, "socket", Socket)
    monkeypatch.setattr(quarantine_smoke.subprocess, "run", lambda argv, **kw:
                        calls.append((argv, kw)) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    clock = iter([0, 121])
    monkeypatch.setattr(quarantine_smoke.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(receipt, "scoped_processes", lambda app: [])
    monkeypatch.setattr(receipt, "no_survivors", lambda *a, **kw: {"ok": True})
    report = {}
    with pytest.raises(RuntimeError, match="within 120s"):
        quarantine_smoke.launch(app, tmp_path, tmp_path, report)
    argv, kwargs = calls[0]
    assert argv[:4] == ["/usr/bin/open", "-n", "-a", str(app)]
    assert "--env" in argv and f"UOINK_ISOLATED_PROFILE={tmp_path / 'profile'}" in argv
    assert "UOINK_ISOLATED_PORT=18081" in argv and kwargs["timeout"] == 30
    assert report["cleanup"]["ok"]


def test_workflow_limits_secrets_and_orders_cleanup_before_every_runtime_step():
    # This guard runs in ci.yml's minimal pytest environment, without PyYAML.
    # YAML parsing is also part of the separate offline static verification.
    text = (ROOT / ".github/workflows/mac-qualify.yml").read_text()
    preamble, body = text.split("\njobs:\n", 1)
    assert "secrets." not in preamble and "mac-release" not in preamble
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\s*$", body)
    jobs = dict(zip(parts[1::2], parts[2::2]))
    job = jobs["mac-sign"]
    for field in ("needs: mac-build", "runs-on: macos-15", "environment: mac-release"):
        assert f"    {field}\n" in job
    assert f"      MACOS_TEAM_ID: {TEAM}\n" in job
    for name, other in jobs.items():
        if name not in ("mac-sign", "notary-check"):
            assert "secrets." not in other and "mac-release" not in other
    header, body = job.split("    steps:\n", 1)
    assert "secrets." not in header
    timeout = int(re.search(r"timeout-minutes: (\d+)", header)[1])
    assert sum(signing.NOTARY_BUDGET_MINUTES.values()) + 90 <= timeout < 360
    for variable in ("NOTARY_APP_TIMEOUT_MINUTES", "NOTARY_DMG_TIMEOUT_MINUTES", "NOTARY_REUSE_SUBMISSION_ID"):
        assert f"vars.{variable}" in header
    steps = re.split(r"(?m)^      - ", body)[1:]
    key_step = next(i for i, step in enumerate(steps) if "secrets." in step)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", steps[key_step])) == {"MACOS_CERT_P12_BASE64", "MACOS_CERT_PASSWORD",
        "NOTARY_API_KEY_P8_BASE64", "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID"}
    assert sum("secrets." in s for s in steps) == 1
    cleanup = next(i for i, step in enumerate(steps) if "sign_notarize.py cleanup" in step)
    assert "        if: always()\n" in steps[cleanup] and key_step < cleanup
    assert [i for i, step in enumerate(steps) if "HOME: ${{ env.UOINK_RUNNER_HOME }}" in step] == [key_step, cleanup]
    runner_env = (ROOT / "scripts/mac/runner-env.sh").read_text()
    assert 'echo "UOINK_RUNNER_HOME=${UOINK_RUNNER_HOME:-$HOME}"' in runner_env
    assert 'echo "HOME=$root/home"' in runner_env
    for i, step in enumerate(steps):
        assert not re.search(r"set\s+[^\n]*-\w*x|set\s+-o\s+xtrace", step)
        if any(script in step for script in ("quarantine_smoke.py", "dmg_smoke.py", "receipt.py")):
            assert i > cleanup and "test ! -e" in step
            assert "        if:" not in step
    uploads = [s for s in steps if "upload-artifact" in s]
    assert not any("private" in p or "keychain" in p or "mac-sign-input" in p for p in uploads)
    assert "--require-notarized" in json.dumps(steps)


def test_ticket_validation_retries_only_a_dropped_network_connection():
    import verify_signing

    def fake(outputs):
        calls = []

        def execute(argv):
            calls.append(argv)
            return outputs[min(len(calls), len(outputs)) - 1]
        return execute, calls

    lost = {"exit": 68, "stdout": "", "stderr": 'Error Domain=NSURLErrorDomain Code=-1005 "The network connection was lost."'}
    ok = {"exit": 0, "stdout": "The validate action worked!", "stderr": ""}
    execute, calls = fake([lost, ok])
    assert verify_signing.validate_ticket("x.dmg", execute=execute)["exit"] == 0 and len(calls) == 2
    missing = {"exit": 65, "stdout": "", "stderr": "does not have a ticket stapled to it"}
    execute, calls = fake([missing, ok])
    assert verify_signing.validate_ticket("x.dmg", execute=execute)["exit"] == 65 and len(calls) == 1
    execute, calls = fake([lost])
    assert verify_signing.validate_ticket("x.dmg", execute=execute)["exit"] == 68 and len(calls) == 3
