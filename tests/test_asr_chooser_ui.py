"""The Settings model chooser (3.18) runs its real dashboard code in node
against a tiny DOM stand-in. No helper, no network."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const cut = (a, b) => page.slice(page.indexOf(a), page.indexOf(b));
const code = cut('    // 3.18 transcription model chooser', '    async function refreshSettings()')
  + cut('    function transcriptModelLabel(', '    function transcriptModelDownloadMb(');
const nodes = {asrModelList: {innerHTML: '', textContent: ''}, asrModelMachine: {textContent: ''}};
const timers = [];
const ctx = {
  document: {getElementById: (id) => nodes[id] || null},
  htmlEscape: (v) => String(v).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])),
  humanLabel: (v) => v, state: {}, setTimeout: (fn) => { timers.push(fn); return timers.length; },
  clearTimeout: () => {}, Math, Number, Array, String, Boolean, JSON,
};
vm.createContext(ctx);
vm.runInContext(code, ctx);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
ctx.renderAsrModels(input);
process.stdout.write(JSON.stringify({html: nodes.asrModelList.innerHTML, text: nodes.asrModelList.textContent,
  machine: nodes.asrModelMachine.textContent, polling: timers.length}));
"""


def render(data):
    result = subprocess.run(["node", "-e", HARNESS], input=json.dumps(data), cwd=ROOT, text=True,
                            capture_output=True, timeout=20, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def row(model, **extra):
    base = {"id": model, "note": "A note.", "languages": "99 languages", "download_bytes": 486_212_372,
            "speed": "About 9 min per hour of audio", "state": "missing", "bytes_on_disk": 0,
            "recommended": False, "selected": False}
    return {**base, **extra}


def rows_by_model(html):
    parts = html.split('<article class="asr-model" data-asr-row="')[1:]
    return {part.split('"', 1)[0]: part for part in parts}


def test_each_model_shows_size_speed_languages_and_the_right_buttons():
    out = render({"machine": {"cpu_cores": 8, "threads_used": 4, "gpu": True}, "models": [
        row("base", state="bundled", selected=True, download_bytes=148_000_000),
        row("distil-large-v3.5", recommended=True, languages="English only", download_bytes=1_516_479_656),
        row("small", state="partial", bytes_on_disk=200_000_000),
        row("medium", state="ready"),
        row("large", download={"state": "downloading", "done": 1_545_417_851, "total": 3_090_835_702}),
    ]})
    cards = rows_by_model(out["html"])
    assert "Balanced" in cards["base"] and "In use" in cards["base"] and "Works offline" in cards["base"]
    assert 'data-asr-action="download"' not in cards["base"] and 'data-asr-action="delete"' not in cards["base"]
    best = cards["distil-large-v3.5"]
    assert "English, best" in best and "Best for English on this computer" in best
    assert "1.5 GB" in best and "English only" in best and 'data-asr-action="download"' in best
    assert "Resume download" in cards["small"] and 'data-asr-action="delete"' in cards["small"]
    assert 'data-asr-action="use"' in cards["medium"] and 'data-asr-action="delete"' in cards["medium"]
    large = cards["large"]
    assert 'data-asr-action="cancel"' in large and 'aria-valuenow="50"' in large and "Downloading, 50%" in large
    assert 'data-asr-action="delete"' not in large
    assert "8 processor cores, 4 used" in out["machine"] and "graphics card stays free" in out["machine"]
    assert out["polling"] == 1          # polls only while a download runs


def test_no_polling_when_nothing_downloads_and_text_is_escaped():
    out = render({"machine": {"cpu_cores": 1, "threads_used": 1}, "models": [
        row("tiny", note="<b>bold</b>", download={"state": "failed", "error": "network <down>"})]})
    assert out["polling"] == 0 and "<b>" not in out["html"] and "&lt;b&gt;" in out["html"]
    assert "Download again to resume" in out["html"] and "1 processor core," in out["machine"]


def test_an_empty_list_says_so():
    assert render({"models": []})["text"] == "No models to show."


def test_the_chooser_copy_names_hugging_face_and_the_bundled_default():
    block = PAGE.split('id="asrModelChooser"', 1)[1].split("</section>", 1)[0]
    assert "huggingface.co" in block and "works offline" in block
    assert 'authFetch(`/asr/models/${action}`' in PAGE and 'authFetch("/asr/models")' in PAGE


def test_the_detail_button_names_the_model_and_posts_the_real_route():
    assert "`Re-transcribe with ${transcriptModelLabel(" in PAGE
    assert 'authFetch("/transcription/retranscribe"' in PAGE
    retranscribe = PAGE.split("async function requestRetranscription()", 1)[1].split("async function ", 1)[0]
    assert "diarize: false" in retranscribe and "not ready in this build" not in retranscribe
