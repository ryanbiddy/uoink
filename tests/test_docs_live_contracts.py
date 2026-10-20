"""Keep transport counts and public probe docs tied to live code."""

from __future__ import annotations

import json
import re
from pathlib import Path

import server
import uoink_mcp
import uoink_mcp_tools
from tests.test_phase4_stdio import _complete_local_call


ROOT = Path(__file__).resolve().parents[1]


def _documented_count(label: str) -> int:
    text = (ROOT / "docs" / "v2-mcp.md").read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(label)}:\s+\*\*(\d+) tools\*\*", text)
    assert match is not None, f"missing documented count for {label}"
    return int(match.group(1))


def test_documented_transport_counts_match_both_live_registries() -> None:
    stdio_tools = _complete_local_call(uoink_mcp.mcp.list_tools())

    assert _documented_count("Supported stdio registry") == len(stdio_tools)
    assert _documented_count("Local HTTP/OpenAPI registry") == len(
        uoink_mcp_tools.TOOL_REGISTRY
    )
    # 71 + the six Living Library work-queue tools (Phase 2 stage 1) + the four
    # Phase 3 source-subscription tools (run AM) + get_library_activity (Phase 5 Part A)
    # + three Phase 4 read tools (run AV-1) + two Phase 4 brief tools (run AV-2)
    # + the Phase 6 cited export tool (run BC-2) + local playbook input (T3).
    assert len(uoink_mcp_tools.TOOL_REGISTRY) == 91


def test_discovery_manifest_privacy_security_and_transport_contracts() -> None:
    import source_manifest

    row = next(r for r in source_manifest.build_sources()["sources"]
               if r["slug"] == "scrapecreators-discovery")
    assert "discovery" in source_manifest.build_sources()["categories"]
    assert row["category"] == "discovery" and row["status"] == "in-flight"
    assert row["lands"] == "Nothing until you pick results. Picked posts are captured like any link."
    privacy = (ROOT / "docs/privacy-policy.md").read_text(encoding="utf-8")
    for text in ("ScrapeCreators discovery: only if you turn it on and add your own key",
                 "api.scrapecreators.com", "no library content, transcripts or", "discovery\\runs",
                 "## 3. Your API keys", "Clear the ScrapeCreators key and turn discovery off",
                 "saved discovery rows", "Uoink-isolated-<hash>", "90 days"):
        assert text in privacy
    for section in ("## 2.", "## 3.", "## 5."):
        text = privacy.split(section, 1)[1].split("\n## ", 1)[0]
        assert "connected agent" in text and "ScrapeCreators" in text
    for label in ("ScrapeCreators API key", "Discovery runs"):
        assert f"- **{label}** \u2014 " in privacy
    mcp_docs = (ROOT / "docs/v2-mcp.md").read_text(encoding="utf-8")
    for text in ("`baselines`", "`platform`, `source_type`", "`null` for mixed or empty results",
                 "Creator snapshots take precedence", "failed or cancelled attempt enqueues a fresh row",
                 "GET /discovery/runs/<run_id>", "sidecar `channel_url`", "local author/channel display name"):
        assert text in mcp_docs
    api_docs = (ROOT / "docs/v2-api.md").read_text(encoding="utf-8")
    assert "### GET /discovery/runs/<run_id>" in api_docs
    assert "Returns `{ok:true, run}`" in api_docs
    security = (ROOT / "docs/security.md").read_text(encoding="utf-8")
    for text in ("ScrapeCreators API key disclosure", "API key storage", "scrapecreators_key",
                 "POST /discovery/intent", "POST /playbooks/run", "api.scrapecreators.com",
                 "all redirects are refused", "8-second", "8 MB", "five-minute", "single-use",
                 "25 by default", "24 run files", "GET /discovery/runs/<run_id>"):
        assert text in security
    from mcp import types
    # Exercise tools/list on the wire: the low-level adapter installs the
    # registry's strict schemas over FastMCP's signature-generated defaults.
    handler = uoink_mcp.mcp._mcp_server.request_handlers[types.ListToolsRequest]
    stdio = _complete_local_call(handler(types.ListToolsRequest(method="tools/list"))).root.tools
    assert len(stdio) == 91
    audit = (ROOT / "docs/mcp-tool-annotations.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / ".mcpb/manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.4" and len(manifest["tools"]) == 91
    for name, idempotent in (("discover_candidates", False), ("queue_discovered", True)):
        spec = uoink_mcp_tools.TOOL_REGISTRY[name]
        assert spec.annotations == {"readOnlyHint": False, "destructiveHint": False,
                                    "idempotentHint": idempotent, "openWorldHint": True}
        wire = next(t for t in stdio if t.name == name)
        assert wire.inputSchema == spec.input_schema and wire.description == spec.description
        assert all(getattr(wire.annotations, k) == v for k, v in spec.annotations.items())
        assert f"| `{name}` |" in audit
        bundled = next(t for t in manifest["tools"] if t["name"] == name)
        assert set(bundled) == {"name", "description"}
    assert "All 91 stdio tools" in audit


def test_discovery_docs_disclose_saved_request_and_failure_receipts() -> None:
    for name in ("docs/privacy-policy.md", "docs/security.md", "CHANGELOG.md"):
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        for disclosure in ("query, handle or channel_id", "run identity", "error envelopes",
                           "failed runs", "90 days", "daily purge"):
            assert disclosure in text, (name, disclosure)
    privacy = (ROOT / "docs/privacy-policy.md").read_text(encoding="utf-8")
    assert "Only normalized candidates and their metrics are stored" not in privacy


def test_discovery_docs_describe_http_intent_authority_without_click_proof() -> None:
    for name in ("docs/security.md", "CHANGELOG.md"):
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        for disclosure in ("helper token", "Origin", "fetch metadata", "human click",
                           "No MCP tool can mint an intent"):
            assert disclosure in text, (name, disclosure)
    handler = server.Handler._is_dashboard_origin.__doc__
    assert "does not prove a human clicked" in handler


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
    monkeypatch.setattr(server, "_active_migration_version", 25)
    monkeypatch.setattr(server.index, "latest_schema_version", lambda: 25)
    monkeypatch.setattr(
        server, "_last_successful_tick_at", "2026-09-04T16:30:00Z"
    )

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
