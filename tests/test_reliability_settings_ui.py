"""Dashboard transcript-model labels, sizes, confirm, and download POST.

Exercises extracted product JavaScript in a Node VM with fake DOM/fetch/confirm.
No browser, helper, or network. Run: python tests/test_reliability_settings_ui.py
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');

function sliceBlock(startNeedle, endNeedle) {
  const start = page.indexOf(startNeedle);
  const end = page.indexOf(endNeedle, start + 1);
  if (start < 0 || end < 0 || end <= start) {
    throw new Error('missing block ' + startNeedle);
  }
  return page.slice(start, end);
}

const human = sliceBlock('    function humanLabel(value) {', '    function sourceStatusLabel(value)');
const helpers = sliceBlock(
  '    const TRANSCRIPT_MODEL_DOWNLOAD_MB = {',
  '    async function refreshSettings()'
);

const fetchCalls = [];
const confirmMessages = [];
const toasts = [];
let refreshed = 0;
const els = {
  whisperModel: { value: input.model || 'tiny' },
  downloadReliabilityModel: { disabled: false },
  reliabilityStatus: { textContent: '' },
};
const context = {
  els,
  confirm(message) {
    confirmMessages.push(message);
    return input.confirm !== false;
  },
  async authFetch(url, opts) {
    fetchCalls.push({ url, opts: opts || {} });
    if (input.fetchOk === false) {
      return { ok: false, error: 'download failed' };
    }
    return { ok: true };
  },
  fetch() { throw new Error('network forbidden'); },
  showToast(message) { toasts.push(message); },
  refreshSettings() { refreshed += 1; },
  console,
};
vm.createContext(context);
vm.runInContext(human + '\n' + helpers, context, { timeout: 1000 });

const action = input.action;
let result;
if (action === 'label') {
  result = context.transcriptModelLabel(input.model);
} else if (action === 'size') {
  result = context.transcriptModelDownloadMb(input.model);
} else if (action === 'sizeCopy') {
  result = context.transcriptModelSizeCopy(input.model, input.serverMb);
} else if (action === 'confirm') {
  result = context.transcriptModelConfirmMessage(input.model);
} else if (action === 'status') {
  result = context.reliabilityStatusText(input.selected, input.relModel || {});
} else if (action === 'download') {
  Promise.resolve(context.downloadSelectedReliabilityModel()).then(() => {
    process.stdout.write(JSON.stringify({
      confirmMessages,
      fetchCalls,
      toasts,
      refreshed,
      disabled: els.downloadReliabilityModel.disabled,
      status: els.reliabilityStatus.textContent,
    }));
  }).catch((err) => {
    process.stderr.write(String(err && err.stack || err));
    process.exit(1);
  });
} else {
  throw new Error('unknown action ' + action);
}
if (action !== 'download') {
  process.stdout.write(JSON.stringify({ result }));
}
"""


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _run(payload: dict) -> dict:
    result = subprocess.run(
        ["node", "-e", HARNESS],
        input=json.dumps(payload),
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"node harness failed: {result.stderr or result.stdout}"
        )
    return json.loads(result.stdout)


def test_one_label_function_covers_all_six_choices():
    _assert(DASHBOARD.count("function transcriptModelLabel(") == 1,
            "dashboard must declare transcriptModelLabel once")
    _assert("function transcriptModelLabel(model)" in DASHBOARD,
            "G-25 label signature must remain")
    _assert("large-v3-turbo" in DASHBOARD, "turbo must be labeled")
    _assert('FALLBACK_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large", "large-v3-turbo"]'
            in DASHBOARD,
            "fallback list must include all six choices")
    _assert("It's about 150 MB and stays on this machine." not in DASHBOARD,
            "confirmation must not hardcode 150 MB")
    _assert("estimated_download_mb || 150" not in DASHBOARD,
            "status must not silently borrow 150 MB")
    labels = {
        "tiny": "Fast",
        "base": "Balanced",
        "small": "Careful",
        "medium": "Deep",
        "large": "Max accuracy",
        "large-v3-turbo": "Turbo",
    }
    for model, label in labels.items():
        got = _run({"action": "label", "model": model})["result"]
        _assert(got == label, f"{model} label: {got}")
    turbo = _run({"action": "label", "model": "large-v3-turbo"})["result"]
    _assert(turbo != "Balanced", f"turbo must not reuse Balanced: {turbo}")
    print("ok  one label function covers six choices")


def test_per_choice_sizes_and_unknown_metadata():
    expected = {
        "tiny": 80,
        "base": 150,
        "small": 490,
        "medium": 1540,
        "large": 3100,
        "large-v3-turbo": 1630,
    }
    for model, size in expected.items():
        got = _run({"action": "size", "model": model})["result"]
        _assert(got == size, f"{model} size: {got}")
        copy = _run({"action": "sizeCopy", "model": model})["result"]
        _assert(copy == f"~{size} MB", copy)
        confirm = _run({"action": "confirm", "model": model})["result"]
        _assert(f"It's about {size} MB and stays on this machine." in confirm,
                confirm)
        _assert("150 MB" not in confirm or size == 150, confirm)
    unknown = _run({"action": "size", "model": "mystery"})["result"]
    _assert(unknown is None, unknown)
    unknown_copy = _run({
        "action": "sizeCopy", "model": "mystery",
    })["result"]
    _assert(unknown_copy == "size unknown", unknown_copy)
    unknown_confirm = _run({"action": "confirm", "model": "mystery"})["result"]
    _assert("download size is unknown" in unknown_confirm.lower(), unknown_confirm)
    borrowed = _run({
        "action": "sizeCopy", "model": "mystery", "serverMb": 150,
    })["result"]
    _assert(borrowed == "~150 MB", "server-supplied size may be shown when listed metadata is missing")
    print("ok  per-choice sizes; unknown metadata is honest")


def test_unsaved_selection_uses_its_own_size():
    ready_tiny = _run({
        "action": "status",
        "selected": "tiny",
        "relModel": {"model": "tiny", "cached": True, "estimated_download_mb": 80},
    })["result"]
    _assert("ready on this device" in ready_tiny, ready_tiny)
    unsaved_large = _run({
        "action": "status",
        "selected": "large",
        "relModel": {"model": "tiny", "cached": True, "estimated_download_mb": 80},
    })["result"]
    _assert("not downloaded yet (~3100 MB)" in unsaved_large, unsaved_large)
    _assert("150 MB" not in unsaved_large, unsaved_large)
    turbo_status = _run({
        "action": "status",
        "selected": "large-v3-turbo",
        "relModel": {"model": "tiny", "cached": False},
    })["result"]
    _assert("Turbo" in turbo_status, turbo_status)
    _assert("1630 MB" in turbo_status, turbo_status)
    missing = _run({
        "action": "status",
        "selected": "mystery",
        "relModel": {"model": "tiny", "cached": False},
    })["result"]
    _assert("size unknown" in missing, missing)
    print("ok  unsaved selection uses its own size")


def test_download_confirms_then_posts_selected_model():
    cancelled = _run({
        "action": "download",
        "model": "large-v3-turbo",
        "confirm": False,
    })
    _assert(cancelled["fetchCalls"] == [], cancelled)
    _assert(cancelled["refreshed"] == 0, cancelled)
    _assert("Turbo" in cancelled["confirmMessages"][0], cancelled)
    _assert("1630 MB" in cancelled["confirmMessages"][0], cancelled)

    posted = _run({
        "action": "download",
        "model": "medium",
        "confirm": True,
    })
    _assert(len(posted["fetchCalls"]) == 1, posted)
    call = posted["fetchCalls"][0]
    _assert(call["url"] == "/reliability/model/download", call)
    body = json.loads(call["opts"]["body"])
    _assert(body == {"model": "medium"}, body)
    _assert(call["opts"]["method"] == "POST", call)
    _assert(posted["refreshed"] == 1, posted)
    _assert("1540 MB" in posted["confirmMessages"][0], posted)
    print("ok  confirm precedes POST of the exact selected model")


def main() -> int:
    test_one_label_function_covers_all_six_choices()
    test_per_choice_sizes_and_unknown_metadata()
    test_unsaved_selection_uses_its_own_size()
    test_download_confirms_then_posts_selected_model()
    print("\nall green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
