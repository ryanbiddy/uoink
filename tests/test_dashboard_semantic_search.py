"""Offline tests of semantic search copy and the shipped dashboard controls."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'assets/dashboard/index.html').read_text(encoding='utf-8')


def test_semantic_search_settings_copy_and_local_notices():
    section = PAGE.split('id="settings-search"', 1)[1].split('id="settings-connected-services"', 1)[0]
    for text in ('Semantic search (optional)', '330 MB', 'Hugging Face', 'runs on this computer',
                 'works offline', "Google's Gemma Terms of Use", 'must accept', 'Keyword search keeps working.'):
        assert text in section
    assert '\u2014' not in section
    assert 'id="semanticAccept" type="checkbox"' in section
    assert 'checkbox" checked' not in section
    for name in ('EmbeddingGemma-NOTICE.md', 'Gemma-Terms-of-Use.txt', 'Gemma-Prohibited-Use-Policy.txt'):
        assert '/search/notices/' + name in section
    assert 'role="status" aria-live="polite"' in section
    assert 'params.set("mode", reset ? "auto"' in PAGE
    assert 'actualMode !== state.searchMode' in PAGE
    assert 'id="searchModeLabel"' in PAGE


def test_semantic_search_dashboard_actions():
    result = subprocess.run(['node', str(ROOT / 'tests/js/dashboard_semantic_search_test.cjs')],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
