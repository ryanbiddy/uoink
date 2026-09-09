"""Keep transport counts and public probe docs tied to live code."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import server
import uoink_mcp
import uoink_mcp_tools


ROOT = Path(__file__).resolve().parents[1]


def _documented_count(label: str) -> int:
    text = (ROOT / "docs" / "v2-mcp.md").read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(label)}:\s+\*\*(\d+) tools\*\*", text)
    assert match is not None, f"missing documented count for {label}"
    return int(match.group(1))


def test_documented_transport_counts_match_both_live_registries() -> None:
    stdio_tools = asyncio.run(uoink_mcp.mcp.list_tools())

    assert _documented_count("Supported stdio registry") == len(stdio_tools)
    assert _documented_count("Local HTTP/OpenAPI registry") == len(
        uoink_mcp_tools.TOOL_REGISTRY
    )


def test_documented_ping_keys_match_the_real_handler(monkeypatch) -> None:
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(
        server.whisper_runner, "is_whisperx_available", lambda: False
    )
    monkeypatch.setattr(
        server.whisper_runner, "is_model_downloaded", lambda *_args: False
    )
    monkeypatch.setattr(
        server,
        "_path_integrity_status",
        lambda: {"ok": True, "checked": 0, "missing": 0},
    )
    monkeypatch.setattr(server, "_index_recovering", False)
    monkeypatch.setattr(server, "_OUTPUT_ROOT_FALLBACK", False)

    class Probe:
        path = "/ping"
        client_address = ("127.0.0.1", 1)

        @staticmethod
        def _reject_bad_host() -> bool:
            return False

        def _send_json(self, status: int, payload: dict) -> None:
            self.status = status
            self.payload = payload

    probe = Probe()
    server.Handler.do_GET(probe)

    assert probe.status == 200
    documents = (
        (
            ROOT / "README_server.md",
            r"### `GET /ping`.*?```json\s*(\{.*?\})\s*```",
        ),
        (
            ROOT / "docs" / "v2-api.md",
            r"### GET /health and GET /ping.*?```json\s*(\{.*?\})\s*```",
        ),
    )
    for path, pattern in documents:
        text = path.read_text(encoding="utf-8")
        match = re.search(pattern, text, re.DOTALL)
        assert match is not None, f"{path.name} has no public-probe JSON schema"
        documented = json.loads(match.group(1))
        assert set(documented) == set(probe.payload), path
        assert set(documented["path_integrity"]) == set(
            probe.payload["path_integrity"]
        ), path


def test_security_model_names_public_probe_disclosure() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    assert "They reveal only `{ok:true, version}`." not in security
    for field in (
        "whisper model",
        "index recovery",
        "output-root fallback",
        "path-integrity counts",
    ):
        assert field in security.lower()


def test_security_model_lists_every_public_get_surface() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    public = security.split("## Public endpoints", 1)[1].split(
        "## Token-gated endpoints", 1
    )[0]
    for route in (
        "/health",
        "/ping",
        "/index/backfill-status",
        "/diagnose",
        "/sources/manifest",
        "/creators/manifest",
        "/hooks/guide",
        "/developers/manifest",
        "/openapi/v1/spec.json",
        "/.well-known/uoink-mcp.json",
        "/.well-known/suite-service.json",
        "/api/suite/v1/health",
        "/dashboard",
        "/splash",
        "/token",
    ):
        assert f"`GET {route}`" in public


def test_local_server_runbook_matches_live_auth_response_and_cors() -> None:
    readme = (ROOT / "README_server.md").read_text(encoding="utf-8")
    extract = readme.split("### `POST /extract`", 1)[1].split(
        "## CORS", 1
    )[0]
    cors = readme.split("## CORS", 1)[1]
    cors_words = " ".join(cors.split())

    assert "[REQUIREMENTS.md](REQUIREMENTS.md)" in readme
    assert "win11toast` is not used" in readme
    assert "pip install yt-dlp" not in readme
    assert "X-Uoink-Token" in extract
    assert '"yoink_md"' in extract
    assert '"corpus_md_paste"' in extract
    assert '"combined_md"' not in extract
    examples = [
        json.loads(raw)
        for raw in re.findall(r"```json\s*(\{.*?\})\s*```", extract, re.DOTALL)
    ]
    assert len(examples) == 2
    success, failure = examples
    assert success["ok"] is True
    assert isinstance(success["yoink_md"], str)
    assert isinstance(success["corpus_md_paste"], str)
    assert failure["ok"] is False
    assert isinstance(failure["error"], str)
    assert isinstance(failure["error_detail"], str)
    assert isinstance(failure["failure_phase"], str)

    for origin in server.ALLOWED_ORIGINS:
        assert f"`{origin}`" in cors
    assert "Chromium extension origins" in cors
    for method in ("GET", "POST", "DELETE", "OPTIONS"):
        assert f"`{method}`" in cors
    for header in (
        "Content-Type",
        "X-Uoink-Token",
        "X-Uoink-Client",
        "X-Yoink-Token",
        "X-Yoink-Client",
    ):
        assert f"`{header}`" in cors
    assert "Private Network Access" in cors_words


def test_windows_source_launchers_prefer_the_repo_venv() -> None:
    batch = (ROOT / "start_server.bat").read_text(encoding="utf-8")
    powershell = (ROOT / "start_server.ps1").read_text(encoding="utf-8")

    assert r".venv\Scripts\pythonw.exe" in batch
    assert r"%~dp0server.py" in batch
    assert r".venv\Scripts\pythonw.exe" in powershell
    assert "Start-Process -FilePath $py" in powershell


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
def test_powershell_launcher_selects_repo_venv_at_runtime(tmp_path: Path) -> None:
    script = tmp_path / "start_server.ps1"
    shutil.copy2(ROOT / "start_server.ps1", script)
    venv_pythonw = tmp_path / ".venv" / "Scripts" / "pythonw.exe"
    venv_pythonw.parent.mkdir(parents=True)
    venv_pythonw.touch()

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    assert powershell is not None
    escaped_script = str(script).replace("'", "''")
    command = (
        "function Start-Process { "
        "param($FilePath, $ArgumentList, $WindowStyle); "
        "Write-Output ('SELECTED=' + $FilePath) "
        "}; "
        f". '{escaped_script}'"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-Command", command],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"SELECTED={venv_pythonw}" in result.stdout


def test_historical_auth_docs_do_not_claim_stale_exclusive_route_lists() -> None:
    tier_2 = (ROOT / "docs" / "tier-2-contracts.md").read_text(encoding="utf-8")
    prelaunch = (ROOT / "docs" / "v2-prelaunch-review.md").read_text(
        encoding="utf-8"
    )
    tier_2_words = " ".join(tier_2.split())
    prelaunch_words = " ".join(prelaunch.split())

    assert "**except** the public" not in tier_2_words
    assert "Status: **HISTORICAL**" in tier_2
    assert "complete public-route inventory" in tier_2_words
    assert "[`docs/security.md`](security.md)" in tier_2

    assert "are the only unauthenticated GET paths" not in prelaunch
    assert "At the time of this v2 review" in prelaunch_words
    assert "current, tested inventory" in prelaunch_words
    assert "[`docs/security.md`](security.md)" in prelaunch


def test_security_model_does_not_promise_removed_live_aliases() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    extension_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "extension").rglob("*.js")
    )

    assert "removed in v3" not in security
    assert "through Uoink v2.5" not in security
    assert "No removal version is promised" in security
    for identifier in ("X-Yoink-Token", "X-Yoink-Client"):
        assert identifier in server_source
        assert identifier in extension_source


def test_mcp_docs_do_not_restore_removed_tool_aliases() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    removed = {
        "yoink_video",
        "yoink_playlist",
        "list_recent_yoinks",
        "search_yoinks",
        "get_yoink_corpus",
        "get_yoink_health",
    }

    assert removed.isdisjoint(uoink_mcp_tools.TOOL_REGISTRY)
    for name in removed:
        assert uoink_mcp_tools.call_tool(name, {}) == {
            "ok": False,
            "error": "tool not found",
        }
    assert "no longer listed or accepted" in security
    assert "aliases resolve to the canonical" not in security


def test_reliability_download_docs_name_the_live_backend_and_request() -> None:
    api = (ROOT / "docs" / "v2-api.md").read_text(encoding="utf-8")
    section = api.split("### POST /reliability/model/download", 1)[1].split(
        "### GET /reliability/<video_id>", 1
    )[0]

    assert "`faster-whisper`" in section
    assert "`whisper-timestamped`" not in section
    assert '"model": "tiny"' in section
    assert "omitted" in section
    for model in server._WHISPER_MODELS:
        assert f"`{model}`" in section


def test_installer_guide_dependency_snapshot_matches_build_script() -> None:
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "build-installer.md").read_text(encoding="utf-8")

    ffmpeg_url = re.search(
        r'^\$FFMPEG_URL\s*=\s*"([^"]+)"$', build, re.MULTILINE
    )
    assert ffmpeg_url is not None
    assert ffmpeg_url.group(1) in guide
    assert "BtbN" in guide
    assert "win64 LGPL" in guide
    assert 'gyan.dev "release essentials"' not in guide
    assert "~80 MB" not in guide

    for variable in (
        "PYTHON_VERSION",
        "FFMPEG_VERSION",
        "YTDLP_VERSION",
        "PILLOW_VERSION",
        "MCP_VERSION",
        "KEYRING_VERSION",
        "PYSTRAY_VERSION",
        "PYWEBVIEW_VERSION",
        "PYTHONNET_VERSION",
        "FASTER_WHISPER_VERSION",
        "WHISPERX_VERSION",
    ):
        match = re.search(
            rf"^\${variable}\s*=\s*'([^']+)'$", build, re.MULTILINE
        )
        assert match is not None, variable
        assert match.group(1) in guide, variable

    for package in (
        "yt-dlp",
        "Pillow",
        "mcp",
        "keyring",
        "pystray",
        "pywebview",
        "pythonnet",
        "faster-whisper",
        "whisperx",
    ):
        assert f"`{package}`" in guide, package
    assert "120 MB" not in guide
    assert "yt-dlp/Pillow/MCP/keyring" not in guide
    assert "`installer\\staging`" in guide
    assert "measure" in guide.lower()
    assert "explicit build.ps1 subset" in guide
    assert 'SmartScreen will show "Windows protected your PC"' not in guide
    assert "clears SmartScreen instantly" not in guide
    assert "~$" not in guide
    assert "Acceptable for v2" not in guide
    prompts = json.loads(
        (ROOT / "extension" / "prompts.json").read_text(encoding="utf-8")
    )
    assert f"{len(prompts)} starter prompts" in guide
    assert "Prompts library is read-only in v1" not in guide
    assert "Tracked as a v1.1 task" not in guide
    installer = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
    assert "Copy-Item" in build and "'extension'" in build
    assert 'Source: "staging\\extension\\*"' in installer
    assert "%LOCALAPPDATA%\\Uoink\\extension\\prompts.json" in guide
    assert "do not have that extension source tree" not in guide
    assert "therefore remains dev-only" not in guide
    assert "Packaged prompts are read-only" not in guide
    assert "Installed prompts have no in-product editor" in guide


def test_security_docs_do_not_claim_unbuilt_macos_or_removed_asr() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    mac_map = (
        ROOT / "docs" / "surface-maps" / "mac-build.md"
    ).read_text(encoding="utf-8")
    mac_plan = (ROOT / "docs" / "MAC-BUILD-PLAN.md").read_text(
        encoding="utf-8"
    )
    reliability = (ROOT / "uoink_reliability.py").read_text(encoding="utf-8")

    assert "`whisper-timestamped`" not in security
    assert "`faster-whisper`" in security
    assert "There is no current macOS build" in security
    assert "The `.dmg` packaging pipeline codesigns" not in security
    assert "macOS product ships" not in mac_map
    assert "describes the intended shipped experience" not in mac_plan
    assert "from faster_whisper import WhisperModel" in reliability


def test_documented_path_integrity_variants_match_live_code(
    monkeypatch, tmp_path
) -> None:
    class MissingIndex:
        @staticmethod
        def list_content_paths() -> list[dict]:
            return [{"corpus_path": str(tmp_path / "missing.md")}]

    monkeypatch.setattr(server, "_get_index", lambda: MissingIndex())
    missing = server._path_integrity_status(force=True)

    def unavailable_index():
        raise RuntimeError("synthetic unavailable index")

    monkeypatch.setattr(server, "_get_index", unavailable_index)
    unavailable = server._path_integrity_status(force=True)

    readme = (ROOT / "README_server.md").read_text(encoding="utf-8")
    ping_section = readme.split("### `GET /ping`", 1)[1].split(
        "### `POST /extract`", 1
    )[0]

    assert set(missing) == {"ok", "checked", "missing", "hint"}
    assert set(unavailable) == {"ok", "checked", "missing", "error"}
    assert unavailable["error"] == "index unavailable; see server.log"
    assert "synthetic" not in unavailable["error"]
    assert all(f"`{key}`" in ping_section for key in ("hint", "error"))
