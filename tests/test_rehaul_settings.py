"""Settings autosave contracts, with real dashboard JS and in-memory I/O only."""
from pathlib import Path
import json
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")


def test_settings_has_one_save_model_and_all_five_sections():
    settings = PAGE.split('id="tab-settings"', 1)[1].split("<script>", 1)[0]
    for section in ("capture", "ai", "library", "agents", "app"):
        assert f'id="settings-{section}"' in settings
        assert f'href="#settings/{section}"' in settings
    for old_button in ("saveKey", "saveOutput", "saveTopics", "saveScreenshotCount", "saveWhisperModel"):
        assert f'id="{old_button}"' not in settings
    for control in ("anthropicKey", "screenshotCount", "screenshotInterval", "commentIntelligenceToggle",
                    "hookTypeToggle", "smartScreenshotPickerToggle", "claimVerificationToggle",
                    "channelHandle", "tasteHooks", "tasteFormats", "tasteAvoid", "tasteUser",
                    "tasteAnchorId", "outputFolder", "mcpConfig", "topicList", "whisperModel"):
        assert f'id="{control}"' in settings
        assert f'aria-describedby="{control}SaveStatus"' in settings
        assert f'id="{control}SaveStatus" role="status" aria-live="polite"' in settings
    assert 'id="clearKey"' in settings
    assert 'id="mcpClient"' in settings
    assert "Chrome setting" in settings  # never imply localStorage updates Chrome sync


def test_autosave_keeps_existing_api_and_does_not_silently_sync_later():
    logic = PAGE.split("const SETTINGS_FIELDS", 1)[1].split("async function postHelper", 1)[0]
    assert 'settingsRequest("/settings", { method: "POST", body: JSON.stringify(patch)' in logic
    assert 'settingsRequest("/memory/taste"' in logic and 'JSON.stringify({ section, content })' in logic
    assert 'settingsRequest("/taste/anchors"' in logic
    assert 'settingsRequest("/settings/mcp-config")' in logic
    assert "cfg.mcp_config" in logic and "payload.claude_desktop" in logic
    assert "syncs later" not in logic and "uoink_settings_pending" not in logic
    assert "refreshSettings();" not in logic
    assert 'body.interval = dashboardScreenshotInterval();' in PAGE
    assert 'if (confirm("Remove the saved Anthropic key' in logic
    assert 'controller.abort()' in logic


def test_folder_feedback_remains_visible_when_manual_path_is_closed():
    manual_path = PAGE.split('<details class="manual-path">', 1)[1].split('</details>', 1)[0]
    assert 'id="outputFolder"' in manual_path
    assert 'id="outputFolderSaveStatus"' not in manual_path
    assert 'id="outputFolderSaveRetry"' not in manual_path
    assert 'aria-describedby="outputFolderSaveStatus" id="pickOutputFolder"' in PAGE


def run_settings_group(group, *args):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/rehaul_settings_test.mjs"), group, *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}" in result.stdout


@pytest.mark.parametrize("group", ["wiring", "save", "screenshot", "races", "errors", "http_errors", "hydrate", "key", "empty_key", "key_test", "interval", "taste", "anchor_draft", "mcp",
                                  "folder_cancel", "reload_races", "mirror_errors", "taste_reload"])
def test_settings_autosave_behaviour(group):
    run_settings_group(group)


@pytest.mark.parametrize("control,field,value", [
    ("defaultTargetLength", "default_target_length", "15m"),
    ("defaultWorkspaceFormat", "default_workspace_format", "obsidian"),
    ("styleAnchorsSource", "style_anchors_source", "both"),
    ("mirrorScriptsToggle", "mirror_scripts_to_obsidian", True),
    ("defaultEvidenceSources", "default_evidence_sources", ["https://example.test/source"]),
])
def test_unsupported_setting_reports_the_actual_helper_response(monkeypatch, control, field, value):
    import server

    def no_settings_access(*_args, **_kwargs):
        pytest.fail("An unsupported field must be rejected before reading or writing settings")

    monkeypatch.setattr(server, "_read_settings", no_settings_access)
    monkeypatch.setattr(server, "_write_settings", no_settings_access)
    handler = server.Handler.__new__(server.Handler)
    responses = []
    handler._send_json = lambda status, body: responses.append((status, body))
    handler._handle_settings_post({field: value})
    assert responses == [(400, {"ok": False, "error": "settings field required"})]
    status, body = responses[0]
    run_settings_group("unsupported", json.dumps({
        "control": control, "field": field, "value": value, "status": status, "body": body,
    }))
