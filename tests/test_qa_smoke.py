"""Guards for the dev-only QA smoke harness (scripts/qa_smoke.py, tests/e2e/).

The harness must never touch the normal library or port 5179, must seed a
realistic library with no network, must fail when something breaks, and must
stay out of the shipped app.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
E2E = ROOT / "tests" / "e2e"
sys.path.insert(0, str(E2E))
sys.path.insert(0, str(ROOT / "scripts"))

import qa_helper  # noqa: E402
import qa_smoke  # noqa: E402

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _seed_env(profile: Path, port: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("UOINK_ISOLATED_")}
    env.update({"UOINK_DISABLE_AVAILABILITY_CHECK": "1", "UOINK_USAGE_SHARING": "0",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
                "LOCALAPPDATA": str(profile.parent / "localappdata")})
    if port is not None:
        env["UOINK_ISOLATED_PROFILE"] = str(profile)
        env["UOINK_ISOLATED_PORT"] = port
    return env


def _run_seed(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(E2E / "qa_seed.py"), *args], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, creationflags=NO_WINDOW)


def test_seeder_refuses_without_an_isolated_profile(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    proc = _run_seed(_seed_env(profile, None), "--state", "seeded")
    assert proc.returncode != 0
    assert "refusing" in (proc.stdout + proc.stderr)
    assert not any(profile.iterdir())


def test_seeder_refuses_the_production_port(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    proc = _run_seed(_seed_env(profile, "5179"), "--state", "seeded")
    assert proc.returncode != 0
    assert not (profile / "index.db").exists()


def test_seeder_builds_a_mixed_library_offline(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    proc = _run_seed(_seed_env(profile, "18198"), "--state", "seeded")
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{"))
    result = json.loads(line)
    assert 35 <= result["items"] <= 45
    for kind in ("video", "episode", "x_thread", "reddit_thread", "page", "note"):
        assert result["kinds"].get(kind, 0) >= 1, kind
    assert result["uncategorized"] >= 1
    expect = result["expect"]
    assert expect["total"] == result["items"]
    assert len(expect["shelves"]) >= 3
    assert Path(result["profile"]).resolve() == profile.resolve()
    # Everything stays inside the isolated profile.
    assert (profile / "token.txt").exists() or (profile / "output").exists()


def test_fixture_fetch_reaches_only_the_fixture_host():
    opener = qa_helper.fixture_opener({"fixture.uoink.test": 1})
    for url in ("https://www.youtube.com/watch?v=abc", "https://x.com/someone/status/1",
                "http://127.0.0.1:5179/health"):
        with pytest.raises(urllib.error.URLError):
            opener(url)


def test_break_options_are_the_documented_ones():
    assert set(qa_helper.FAULTS) == set(qa_smoke.FAULTS) == {"search-500", "search-hidden"}
    assert "#searchInput" in qa_helper.HIDE_SEARCH_CSS


def test_qa_smoke_never_picks_the_production_port():
    with pytest.raises(SystemExit):
        qa_smoke.pick_port(5179)
    assert qa_smoke.free_port() != 5179


def test_failed_playwright_test_turns_the_run_red(tmp_path):
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"suites": [{"file": "dashboard.spec.mjs", "specs": [
        {"title": "search", "tests": [{"projectName": "light-1280", "annotations": [], "results": [
            {"status": "failed", "duration": 10, "annotations": [],
             "error": {"message": "\x1b[31mError: search box hidden\x1b[39m\n+   \"x\","}}]}]},
        {"title": "load", "tests": [{"projectName": "light-1280", "annotations": [], "results": [
            {"status": "passed", "duration": 10, "annotations": [
                {"type": "known-issue", "description": "KI-01: thing"}]}]}]}]}]}), encoding="utf-8")
    rows = qa_smoke.read_report(report, qa_smoke.suite_of)
    assert [r["ok"] for r in rows] == [False, True]
    assert rows[0]["detail"] == 'Error: search box hidden -> "x"'
    assert rows[1]["known"] == ["KI-01: thing"]
    missing = qa_smoke.read_report(tmp_path / "missing.json", qa_smoke.suite_of)
    assert missing and not missing[0]["ok"]


def test_known_issues_are_well_formed():
    entries = json.loads((E2E / "known-issues.json").read_text(encoding="utf-8"))
    for entry in entries:
        assert set(entry) == {"id", "check", "match", "note"}, entry
        assert entry["note"].strip()


def test_harness_is_not_shipped():
    shipped = [ROOT / "build.ps1", ROOT / "installer" / "uoink.iss", ROOT / "scripts" / "mac" / "payload.json"]
    for path in shipped:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "qa_smoke" not in text and "tests/e2e" not in text and "tests\\e2e" not in text, path
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert "http://fixture.uoink.test/*" not in manifest.get("host_permissions", [])
