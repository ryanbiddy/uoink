"""Dashboard surfaces for Import a list, the For You imports panel and the
Card image setting. Static checks over assets/dashboard/index.html, plus a
node syntax check of the inline scripts when node is available."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    i = DASHBOARD.index(start)
    return DASHBOARD[i:DASHBOARD.index(end, i)]


def test_sources_entry_opens_the_dialog_without_a_second_primary():
    card = _between('id="listImportCard"', 'id="noteCapture"')
    assert 'id="openListImport"' in card
    assert 'class="button primary"' not in card
    # The Sources view keeps exactly one primary (Uoink it).
    sources = _between('id="tab-sources"', 'id="getExtensionCard"')
    assert sources.count('class="button primary"') == 1


def test_dialog_has_one_paste_field_a_preview_count_and_one_primary_import():
    modal = _between('id="listImportModal"', 'id="stopHelperConfirm"')
    assert 'role="dialog"' in modal and 'aria-modal="true"' in modal
    assert modal.count("<input") == 1 and 'id="listImportInput"' in modal
    assert 'id="listImportStatus"' in modal and 'aria-live="polite"' in modal
    assert modal.count('class="button primary"') == 1
    assert re.search(r'<button class="button primary" type="button" id="listImportGo" disabled>Import</button>', modal)
    assert 'class="button ghost hidden" type="button" id="listImportNext">Next 50<' in modal
    assert 'class="button ghost" type="button" id="closeListImport"' in modal
    assert "Found" not in modal  # the count comes from the helper's message


def test_dialog_talks_to_the_helper_routes():
    assert 'authFetch("/import-list/preview"' in DASHBOARD
    assert 'authFetch("/import-list"' in DASHBOARD
    assert "limit: 50" in DASHBOARD
    assert "wireListImport();" in DASHBOARD
    assert "trapModalFocus(event, modal, closeListImport)" in DASHBOARD


def test_for_you_imports_panel_and_card_images():
    panel = _between('id="importsPanel"', 'id="worthCards"')
    assert "From lists you imported" in panel and 'id="importCards"' in panel
    assert "renderImports(payload);" in DASHBOARD
    assert 'data-card-thumb="${htmlEscape(row.thumbnail_path)}"' in DASHBOARD
    assert "async function loadCardImages(container)" in DASHBOARD
    # Imported cards must open in the reader like other For You cards.
    assert "state.resurface.from_imports" in DASHBOARD
    # No primary on the For You cards: Write from this stays a plain button.
    card = _between("function importCard(row)", "function renderImports(")
    assert 'class="button primary' not in card
    assert "origin.credit" in card and "origin.note" in card


def test_reader_and_library_show_the_import_origin():
    assert 'id="yoinkImportNote"' in DASHBOARD
    assert "function importOriginText(row)" in DASHBOARD
    assert "row.import_origin && row.import_origin.label" in DASHBOARD


def test_card_image_setting_defaults_to_middle():
    block = _between('id="settings-card-image"', 'Creator defaults')
    assert '<option value="middle">Middle of the video</option>' in block
    assert '<option value="thumbnail">Original thumbnail</option>' in block
    assert 'id="cardImageSaveStatus"' in block and 'data-setting-retry="cardImage"' in block
    assert 'cardImage: ["card_image", "middle"],' in DASHBOARD
    assert 'if (field === "card_image")' in DASHBOARD


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_inline_scripts_parse(tmp_path):
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.bodies, self._inside = [], False

        def handle_starttag(self, tag, attrs):
            self._inside = tag == "script" and not dict(attrs).get("src")
            if self._inside:
                self.bodies.append("")

        def handle_endtag(self, tag):
            if tag == "script":
                self._inside = False

        def handle_data(self, data):
            if self._inside:
                self.bodies[-1] += data

    parser = Scripts()
    parser.feed(DASHBOARD)
    scripts = parser.bodies
    assert scripts
    for i, body in enumerate(scripts):
        path = tmp_path / f"inline_{i}.js"
        path.write_text(body, encoding="utf-8")
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
