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
    assert modal.count('type="url"') == 1 and 'id="listImportInput"' in modal
    assert 'id="listImportFile" type="file" accept=".csv,.txt"' in modal
    assert 'for="listImportFile">Import a saves file</label>' in modal
    assert 'id="listImportStatus"' in modal and 'aria-live="polite"' in modal
    assert modal.count('class="button primary"') == 1
    assert re.search(r'<button class="button primary" type="button" id="listImportGo" disabled>Import</button>', modal)
    assert 'class="button ghost hidden" type="button" id="listImportNext">Next 50<' in modal
    assert 'class="button ghost" type="button" id="closeListImport"' in modal
    assert "Found" not in modal  # the count comes from the helper's message


def test_dialog_talks_to_the_helper_routes():
    assert 'authFetch("/import-list/preview"' in DASHBOARD
    assert 'authFetch("/import-list"' in DASHBOARD
    assert 'authFetch("/import-list/stage"' in DASHBOARD
    assert "savesUploadChunk(csvText, offset, file.name, uploadId)" in DASHBOARD
    assert 'listImportEl("listImportInput").value = data.url' in DASHBOARD
    assert "limit: 50" in DASHBOARD
    assert "wireListImport();" in DASHBOARD
    assert "trapModalFocus(event, modal, closeListImport)" in DASHBOARD


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_saves_file_upload_chunks_preserve_text_and_fit_body_limit(tmp_path):
    functions = _between("function savesUploadChunk(", "async function runListImport()")
    script = r'''
const assert = require("node:assert/strict");
const window = { clearTimeout() {} };
const listImportState = { seq: 0 };
const fileInput = { files: [], value: "" }, urlInput = { value: "" };
const listImportEl = (id) => id === "listImportFile" ? fileInput : urlInput;
let message, previews = 0, authFetch;
const resetListImportPreview = (text) => { message = text; };
const runListPreview = async () => { ++previews; };
''' + functions + r'''
(async () => {
  const token = "uoink-saves:0123456789abcdef", uploadId = "fedcba9876543210";
  const cases = [
    { text: "Video ID\nsave0000001\n", count: 1 },
    { text: "a".repeat(47999), count: 1 },
    { text: "a".repeat(48000), count: 1 },
    { text: "row\n".repeat(30000), count: 3, lines: true },
    { text: "a".repeat(120001), count: 3 },
    { text: "\u00e9".repeat(47999) },
    { text: "\u0000\"\\".repeat(20000) },
    { text: "a".repeat(47999) + "\ud83d\ude00" + "b".repeat(48000) },
  ];
  for (const example of cases) {
    const requests = [];
    fileInput.files = [{ size: Buffer.byteLength(example.text), name: "watch-later.csv",
                         text: async () => example.text }];
    urlInput.value = "";
    authFetch = async (path, options) => {
      assert.equal(path, "/import-list/stage");
      assert.equal(options.method, "POST");
      assert.ok(Buffer.byteLength(options.body) <= 65536);
      const body = JSON.parse(options.body);
      assert.equal(body.filename, "watch-later.csv");
      assert.ok(body.csv_text.length <= 48000);
      assert.equal(body.upload_id, requests.length ? uploadId : undefined);
      assert.equal(new TextDecoder().decode(new TextEncoder().encode(body.csv_text)), body.csv_text);
      requests.push(body);
      return body.done ? { ok: true, url: token, count: 1, truncated: true }
                       : { ok: true, upload_id: uploadId, received_bytes: 1 };
    };
    const before = previews;
    await stageSavesFile();
    assert.equal(previews, before + 1, message);
    assert.equal(urlInput.value, token);
    assert.equal(fileInput.value, "");
    assert.equal(listImportState.truncated, true);
    assert.equal(requests.map((body) => body.csv_text).join(""), example.text);
    assert.equal(requests.at(-1).done, true);
    for (const body of requests.slice(0, -1)) {
      assert.equal(body.done, false);
      if (example.lines) assert.ok(body.csv_text.endsWith("\n"));
    }
    if (example.count) assert.equal(requests.length, example.count);
  }
  fileInput.files = [{ size: 5 * 1024 * 1024 + 1,
                       text: async () => assert.fail("oversized file was read") }];
  authFetch = async () => assert.fail("oversized file was uploaded");
  const before = previews;
  await stageSavesFile();
  assert.equal(previews, before);
  assert.equal(message, "Saves files must be 5 MB or smaller.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
'''
    path = tmp_path / "saves-upload.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


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
