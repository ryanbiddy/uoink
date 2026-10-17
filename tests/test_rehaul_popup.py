"""Reader popup zones, routing, worker hand-off, step states and SSE. No network."""
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "extension/popup.html").read_text(encoding="utf-8-sig")


def test_popup_zones_and_keyboard_controls():
    assert HTML.index('class="popup-header"') < HTML.index('id="this-tab-heading"')
    assert HTML.index('id="this-tab-heading"') < HTML.index('id="captures-heading"') < HTML.index('<footer')
    assert 'height: 600px; max-height: 600px' in HTML
    assert 'width: 360px; max-width: 100%' in HTML
    assert 'overflow-y: auto' in HTML
    assert '<label for="paste-url">or paste a link</label>' in HTML
    assert 'id="paste-form"' in HTML and 'type="submit">Add</button>' in HTML
    assert 'id="current-source-thumbnail"' in HTML
    assert 'id="current-source-origin"' in HTML
    assert '/dashboard#library' in HTML and '/dashboard#settings/capture' in HTML
    assert 'role="alert"' in HTML and 'role="status"' in HTML
    assert 'tabindex="-1"' not in HTML
    for removed in ('mode-selector-wrap', 'mode-single', 'mode-playlist', 'pairwise-calibration-card',
                    'active-uoink-hook-container', 'destination-panel', 'quick-prompts', 'resurface-card', 'more-options'):
        assert f'id="{removed}"' not in HTML


@pytest.mark.parametrize("group", ["steps", "merge", "render", "routing", "worker", "playlist_primary", "podcast_primary", "podcast_feedback", "source_labels", "current_tab_queue", "x_primary", "x_feedback", "x_posts", "stream", "picker", "sessions"])
def test_popup_behaviour(group):
    result = subprocess.run(["node", str(ROOT / "tests/js/rehaul_popup_test.mjs"), group],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}:" in result.stdout


@pytest.mark.parametrize("group", ["hooks", "destinations", "prompts"])
def test_saved_capture_actions_stay_reachable(group):
    result = subprocess.run(["node", str(ROOT / "tests/js/rehaul_popup_actions_test.mjs"), group],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}:" in result.stdout
