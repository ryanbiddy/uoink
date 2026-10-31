"""Dashboard copy never asks for a model this device already has (3.12).

Since 3.12 the default transcription model ships with Uoink. A capture saved
before the model was there still says model_not_downloaded; once the model is
ready the drawer and the reader say Re-uoink / Re-transcribe instead of
"download it". When a model really is missing, the drawer's "Download it in
Settings" is a link to the transcription-model control.

Runs the product's own JavaScript in the Node vm harness from
test_dashboard_runthrough_fixes.py.
"""
from __future__ import annotations

from tests.test_dashboard_runthrough_fixes import DASHBOARD, _between, run_js

ROW = ('{video_id: "v1", title: "Clip", source_type: "video", platform: "x", '
       'source_url: "https://x.com/a/status/1", asr_fallback_status: "model_not_downloaded", '
       'health: {transcript: "missing", screenshots: "ok"}}')
LINK = '<a href="#settings/transcription-model" data-health-settings>Download it in Settings</a>'


def drawer_issues(settings: str) -> str:
    return run_js(f"""(() => {{
      state.settings = {settings};
      state.library = [{ROW}];
      openItemHealth("v1", null);
      return getEl("itemHealthIssues").innerHTML;
    }})()""")


def test_missing_model_links_to_the_transcription_model_setting():
    for settings in ("null", '{transcript_reliability_model: {model: "small", cached: false, bundled_model: "base"}}'):
        issues = drawer_issues(settings)
        assert LINK in issues, issues
        assert "isn&#39;t downloaded yet" in issues or "isn't downloaded yet" in issues, issues
        assert issues.count("<a ") == 1


def test_ready_model_says_reuoink_not_download():
    issues = drawer_issues('{transcript_reliability_model: {model: "base", cached: true, source: "bundled"}}')
    assert "Download" not in issues and "<a " not in issues, issues
    assert "ready now, so Re-uoink to transcribe it" in issues, issues


def test_other_reasons_stay_escaped_text():
    html = run_js("""healthIssueReasonHtml({key: "transcript", failed: true},
                     {source_type: "video", asr_fallback_status: "disabled"})""")
    assert "<a " not in html and "&quot;Transcribe videos locally" in html


def test_link_route_reaches_the_model_control_and_closes_the_drawer():
    route = run_js('parseRoute("#settings/transcription-model")')
    assert route == {"tab": "settings", "section": "transcription-model",
                     "hash": "#settings/transcription-model"}
    settings = _between(DASHBOARD, 'id="tab-settings"', '<section class="settings-section" id="settings-ai"')
    block = _between(settings, '<div class="setting-block" id="transcription-model">', "</div>\n")
    assert "<h2>Transcript checker</h2>" in block
    picker = _between(settings, '<select class="field" id="whisperModel"', "</select>")
    assert "data-reveal-focus" in picker
    assert settings.index('id="transcription-model"') < settings.index('id="whisperModel"')
    reveal = _between(DASHBOARD, "function revealSettingsSection(section, loaded = null) {", "function revealSourcesDiscover")
    assert 'target.querySelector("[data-reveal-focus]")' in reveal
    wiring = _between(DASHBOARD, 'document.getElementById("reuoinkItemHealth").addEventListener',
                      'els.itemHealthDrawer.addEventListener("cancel"')
    assert 'closest("[data-health-settings]")' in wiring and "closeItemHealth()" in wiring


def test_reader_note_matches_the_drawer():
    note = """transcriptNoteText({video_id: "v1", source_type: "video", platform: "youtube"},
                                {asr_fallback: {status: "model_not_downloaded", model: "small"}})"""
    missing = run_js(f"(() => {{ state.settings = null; return {note}; }})()")
    assert "Download it in Settings, Capture" in missing
    ready = run_js(f"""(() => {{
      state.settings = {{transcript_reliability_model: {{model: "base", cached: true, source: "bundled"}}}};
      return {note};
    }})()""")
    assert "Download" not in ready and "It's ready now: Re-transcribe" in ready, ready
