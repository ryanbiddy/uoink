"""Offline status-only checks. No Apple tools, network or real credentials."""
import base64
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import check_notary as check
import sign_notarize as signing

IDS = ["968ac10a-dc40-435f-89a5-85ddfb941ab9", "a85b5ddc-eff7-496a-af76-df93e91632ab"]


@pytest.mark.parametrize("value", ["", " ", "not-an-id", "--help", "../outside", "$(whoami)",
    "968ac10adc40435f89a585ddfb941ab9", "{" + IDS[0] + "}", "urn:uuid:" + IDS[0],
    IDS[0] + "\nanything", IDS[0] + ",", "," + IDS[0], IDS[0] + ",bad", IDS[0][:-1] + "g",
    IDS[0].replace("-", "_"), ",".join(IDS * 3)])
def test_invalid_list_is_rejected_before_key_decode_or_tools(tmp_path, monkeypatch, value):
    monkeypatch.delenv("NOTARY_API_KEY_P8_BASE64", raising=False)
    monkeypatch.setattr(signing, "tool", lambda *a, **kw: pytest.fail("No tool for invalid input"))
    with pytest.raises(ValueError, match="UUID"):
        check.check(value, tmp_path / "private", tmp_path / "evidence", tmp_path / "summary")
    assert not list(tmp_path.iterdir())


def test_parse_uuid_list_strips_space_normalizes_case_and_deduplicates():
    assert check.parse_submission_ids(f" {IDS[0].upper()} , {IDS[1]}, {IDS[0]} ") == IDS


@pytest.mark.parametrize("status", ["In Progress", "Accepted", "Invalid", "Rejected"])
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("info_exit", [0, 1])
def test_checks_once_fetches_terminal_logs_and_removes_only_key(tmp_path, monkeypatch, capsys, status, stream, info_exit):
    decoded = 'fixture-only-key\n"quoted"\\line'
    encoded = base64.b64encode(decoded.encode()).decode()
    values = [decoded, encoded, "fixture-key-id", "fixture-issuer"]
    for name, value in zip(("NOTARY_API_KEY_P8_BASE64", "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID"), values[1:]):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MACOS_CERT_P12_BASE64", raising=False)
    monkeypatch.delenv("MACOS_CERT_PASSWORD", raising=False)
    private, evidence, summary = (tmp_path / name for name in ("private", "evidence", "summary"))
    calls, modes = [], []
    original_chmod = Path.chmod

    def chmod(path, mode, **kw):
        modes.append((path, mode))
        return original_chmod(path, mode, **kw)

    def tool(argv, **kw):
        calls.append(argv)
        assert argv[:2] == ["xcrun", "notarytool"]
        assert argv[2] in ("info", "log") and argv[3] in IDS
        assert kw["timeout"] == 30
        assert argv[4:10] == ["--key", private / "notary.p8", "--key-id", values[2], "--issuer", values[3]]
        assert argv[10:] == (["--output-format", "json"] if argv[2] == "info" else [])
        assert [p.name for p in private.iterdir()] == ["notary.p8"]
        assert (private / "notary.p8").read_text() == decoded
        if os.name != "nt":
            assert private.stat().st_mode & 0o777 == 0o700
            assert (private / "notary.p8").stat().st_mode & 0o777 == 0o600
        response = {"id": argv[3], "status": status, "createdDate": "2026-10-22T03:01:15Z"}
        response["message"] = " ".join(values)
        output = {"stdout": " ".join(values), "stderr": " ".join(values), stream: json.dumps(response)}
        return SimpleNamespace(returncode=info_exit if argv[2] == "info" else 0, **output)

    monkeypatch.setattr(Path, "chmod", chmod)
    monkeypatch.setattr(signing, "tool", tool)
    if info_exit:
        with pytest.raises(RuntimeError, match="Some notary queries failed"):
            check.check(",".join(IDS), private, evidence, summary)
    else:
        check.check(",".join(IDS), private, evidence, summary)
    assert not private.exists()
    check.cleanup(private)  # The workflow's always() cleanup is idempotent.
    assert (private, 0o700) in modes and (private / "notary.p8", 0o600) in modes
    assert [c[2] for c in calls] == (["info", "log"] * 2 if status in check.TERMINAL_STATUSES else ["info"] * 2)
    rows = json.loads((evidence / "submissions.json").read_text())
    assert [r["id"] for r in rows] == IDS
    assert all(r["status"] == status and r["createdDate"] == "2026-10-22T03:01:15Z" for r in rows)
    assert "| ID | Status | Created date |" in summary.read_text()
    summary_status = status + (" (query failed)" if info_exit else "")
    assert all(f"| {ident} | {summary_status} | 2026-10-22T03:01:15Z |" in summary.read_text() for ident in IDS)
    captured = capsys.readouterr()
    public = captured.out + captured.err + summary.read_text() + "".join(p.read_text() for p in evidence.iterdir())
    assert all(v not in public and json.dumps(v)[1:-1] not in public for v in values)


@pytest.mark.parametrize("failure", ["exit", "timeout", "bad-json", "wrong-id", "log", "exception"])
def test_query_failure_keeps_other_ids_summary_and_cleanup(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("NOTARY_API_KEY_P8_BASE64", "Zml4dHVyZQ==")
    monkeypatch.setenv("NOTARY_API_KEY_ID", "fixture-key-id")
    monkeypatch.setenv("NOTARY_API_ISSUER_ID", "fixture-issuer")
    calls = []

    def tool(argv, **kw):
        calls.append(argv)
        if argv[3] == IDS[1]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"id": IDS[1], "status": "In Progress"}), stderr="")
        if failure == "exception":
            raise OSError("private exception detail")
        response = {"id": IDS[1] if failure == "wrong-id" else IDS[0], "status": "Accepted"}
        code = 124 if failure == "timeout" else int(failure == "exit" or argv[2] == "log")
        return SimpleNamespace(returncode=code, stdout="bad JSON" if failure == "bad-json" else json.dumps(response), stderr="")

    monkeypatch.setattr(signing, "tool", tool)
    with pytest.raises(RuntimeError, match="Some notary queries failed"):
        check.check(",".join(IDS), tmp_path / "private", tmp_path / "evidence", tmp_path / "summary")
    assert not (tmp_path / "private").exists()
    rows = json.loads((tmp_path / "evidence/submissions.json").read_text())
    assert "error" in rows[0] and "error" not in rows[1]
    assert rows[1]["status"] == "In Progress"
    assert "query failed" in (tmp_path / "summary").read_text()
    assert "private exception detail" not in json.dumps(rows)
    assert sum(c[2] == "info" for c in calls) == 2


def test_decode_failure_also_removes_private_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTARY_API_KEY_P8_BASE64", "invalid-base64")
    with pytest.raises(ValueError):
        check.check(IDS[0], tmp_path / "private", tmp_path / "evidence", tmp_path / "summary")
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("app,dmg,ok", [(210, 90, True), (240, 60, True), (211, 90, False),
                                       (150, 151, False), (360, 90, False)])
def test_combined_budgets_are_capped_before_key_import(tmp_path, monkeypatch, app, dmg, ok):
    monkeypatch.setenv("NOTARY_APP_TIMEOUT_MINUTES", str(app))
    monkeypatch.setenv("NOTARY_DMG_TIMEOUT_MINUTES", str(dmg))
    monkeypatch.setattr(signing, "prepare_identity", lambda *a: pytest.fail("No key import"))
    if ok:
        assert signing.notary_budget_seconds("app") == app * 60
        assert signing.notary_budget_seconds("dmg") == dmg * 60
    else:
        with pytest.raises(ValueError, match="at most 300"):
            signing.sign_release(tmp_path, tmp_path / "evidence", tmp_path / "private", "TEAM")
        assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", ["bad", "--help", IDS[0] + "," + IDS[1]])
def test_reuse_rejects_non_uuid_before_signing_or_query(tmp_path, monkeypatch, value):
    monkeypatch.setenv("NOTARY_REUSE_SUBMISSION_ID", value)
    monkeypatch.setattr(signing, "prepare_identity", lambda *a: pytest.fail("No key import"))
    monkeypatch.setattr(signing, "tool", lambda *a, **kw: pytest.fail("No query"))
    with pytest.raises(ValueError, match="UUID"):
        signing.sign_release(tmp_path, tmp_path / "evidence", tmp_path / "private", "TEAM")
    with pytest.raises(ValueError, match="UUID"):
        signing.reuse_notarization(tmp_path / "Uoink.app", tmp_path / "private", tmp_path)


def test_workflow_status_job_uses_only_notary_secrets_and_skips_every_other_job():
    # ci.yml's minimal pytest environment has no PyYAML; parse YAML separately offline.
    text = (ROOT / ".github/workflows/mac-qualify.yml").read_text()
    preamble, body = text.split("\njobs:\n", 1)
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\s*$", body)
    jobs = dict(zip(parts[1::2], parts[2::2]))
    check_job = jobs.pop("notary-check")
    header, steps = check_job.split("    steps:\n", 1)
    assert "    if: ${{ inputs.notary_check_ids != '' }}" in header
    assert "    environment: mac-release" in header and "    runs-on: macos-15" in header
    assert "    timeout-minutes: 10" in header and "needs:" not in header
    assert "secrets." not in preamble + header
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", check_job)) == {
        "NOTARY_API_KEY_P8_BASE64", "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID"}
    assert not any(word in check_job for word in ("MACOS_CERT", "keychain", ".p12", "download-artifact", "pip install"))
    steps = re.split(r"(?m)^      - ", steps)[1:]
    query = next(i for i, s in enumerate(steps) if "check_notary.py check" in s)
    cleanup = next(i for i, s in enumerate(steps) if "check_notary.py cleanup" in s)
    upload = next(i for i, s in enumerate(steps) if "upload-artifact" in s)
    assert query < cleanup < upload
    assert "        if: always()\n" in steps[cleanup] and "        if: always()\n" in steps[upload]
    assert "mac-notary-check/*.json" in steps[upload] and "private" not in steps[upload]
    assert sum("secrets." in s for s in steps) == 1
    assert "NOTARY_CHECK_IDS: ${{ inputs.notary_check_ids }}" in steps[query]
    assert not re.search(r"run:.*\$\{\{.*inputs\.", check_job)
    assert "inputs.notary_check_ids != '' && 'notary-check' || 'qualify'" in preamble
    for job in jobs.values():
        header = job.split("    steps:\n", 1)[0]
        condition = re.search(r"(?m)^    if: (.+)$", header)[1]
        assert "inputs.notary_check_ids == ''" in condition and "||" not in condition
    assert "always() && !cancelled() && inputs.notary_check_ids == ''" in jobs["import-smoke"]
    assert "inputs.notary_app_minutes || vars.NOTARY_APP_TIMEOUT_MINUTES || '150'" in jobs["mac-sign"]
    assert "inputs.notary_reuse_submission_id || vars.NOTARY_REUSE_SUBMISSION_ID || ''" in jobs["mac-sign"]
    timeout = int(re.search(r"timeout-minutes: (\d+)", jobs["mac-sign"])[1])
    assert signing.NOTARY_MAX_TOTAL_MINUTES + 50 <= timeout < 360
    for name in ("notary_check_ids", "notary_app_minutes", "notary_reuse_submission_id"):
        assert f"      {name}:\n" in preamble
