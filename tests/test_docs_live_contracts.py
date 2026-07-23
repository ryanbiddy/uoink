"""Keep transport counts and public probe docs tied to live code."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

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
