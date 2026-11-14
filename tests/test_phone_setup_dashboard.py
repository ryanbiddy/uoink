"""Dashboard Settings > Phone inbox guided setup: the three steps, the
connected / not connected pill, the QR code (only when connected), the old
relay path, and the collapsed summary.

Same approach as tests/test_relay_dashboard.py: the product's own JavaScript
in a Node vm with a small fake DOM and a stub for the helper. The vendored
QR encoder is loaded into the vm the way the page loads it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const scriptCode = page.slice(page.indexOf('<script>') + 8, page.indexOf('    init().catch('));
const qrSource = fs.readFileSync('assets/dashboard/qrcode.js', 'utf8');

function element(id) {
  const classes = new Set();
  return {
    id, value: '', checked: false, disabled: false, textContent: '', innerHTML: '', placeholder: '',
    dataset: {}, attributes: {}, style: {}, listeners: {},
    classList: {
      add: (...n) => n.forEach((x) => classes.add(x)), remove: (...n) => n.forEach((x) => classes.delete(x)),
      contains: (n) => classes.has(n),
      toggle: (n, force) => { const on = force === undefined ? !classes.has(n) : Boolean(force);
        if (on) classes.add(n); else classes.delete(n); return on; },
    },
    setAttribute(k, v) { this.attributes[k] = String(v); }, getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; },
    removeAttribute(k) { delete this.attributes[k]; },
    querySelectorAll: () => [], querySelector: () => null, closest: () => null,
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }, focus() {}, click() { (this.listeners.click || []).forEach((f) => f()); },
  };
}
const elements = {};
const getEl = (id) => (elements[id] = elements[id] || element(id));
const timers = [];
const store = {};
const context = {
  document: { getElementById: getEl, querySelector: () => null, querySelectorAll: () => [], activeElement: null },
  window: { addEventListener() {}, setTimeout: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimeout() {} },
  navigator: { clipboard: { writeText: async (t) => { context.copied = t; } } },
  console, URL, Set, Map, Promise, JSON, Date, AbortController,
  fetch: () => Promise.reject(new Error('network forbidden')),
  setTimeout: () => 0, clearTimeout: () => {},
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
};
vm.createContext(context);
if (!process.env.NO_QR) vm.runInContext(qrSource, context);
vm.runInContext(scriptCode + '\n;globalThis.state = state;', context);
context.getEl = getEl; context.timers = timers; context.store = store; context.requests = [];
context.hidden = (id) => getEl(id).classList.contains('hidden');
context.authFetch = async (path, opts = {}) => {
  context.requests.push({ path, body: opts.body ? JSON.parse(opts.body) : null });
  return context.reply(path, opts.body ? JSON.parse(opts.body) : null);
};
const code = fs.readFileSync(0, 'utf8');
Promise.resolve(vm.runInContext(code, context)).then(
  (result) => process.stdout.write(JSON.stringify({ result })),
  (error) => { process.stderr.write(String(error && error.stack || error)); process.exit(1); },
);
"""

PUSH = "push-token-from-relay-0123456789abcdef-xyz"

PRELUDE = f"""
const PUSH = {json.dumps(PUSH)};
const nowIso = (minAgo) => new Date(Date.now() - minAgo * 60000).toISOString();
const okStatus = (extra = {{}}) => ({{ ok: true, enabled: true, configured: true, last_poll_at: nowIso(2), last_ok_at: nowIso(2),
  last_error: null, last_capture_error: null, picked_up_total: 0, last_pending_count: 0, polling: false, ...extra }});
const settings = (extra = {{}}) => ({{ relay_url: 'https://my-relay.onrender.com', relay_enabled: true, relay_poll_minutes: 5,
  relay_token_set: true, ...extra }});
const view = () => ({{ pill: getEl('phoneConnPill').textContent, pillState: getEl('phoneConnPill').dataset.state,
  locked: !hidden('phoneLocked'), loading: !hidden('phoneLoading'), old: !hidden('phoneOld'), error: !hidden('phoneError'),
  qr: !hidden('phoneQrWrap'), summary: !hidden('phoneSummary'), steps: !hidden('phoneSteps'),
  svg: getEl('phoneQr').innerHTML }});
"""


def run_js(code: str, *, qr: bool = True):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    env = None
    if not qr:
        import os
        env = {**os.environ, "NO_QR": "1"}
    result = subprocess.run([node, "-e", HARNESS], input=PRELUDE + code, cwd=ROOT, text=True, encoding="utf-8",
                            capture_output=True, timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["result"]


# ---- markup -----------------------------------------------------------------

def _card() -> str:
    start = DASHBOARD.index('id="phone-inbox"')
    return DASHBOARD[start:DASHBOARD.index('id="settings-', start) if 'id="settings-' in DASHBOARD[start:] else None]


def test_card_explains_the_flow_cost_and_privacy_then_shows_three_numbered_steps():
    card = DASHBOARD[DASHBOARD.index('id="phone-inbox"'):DASHBOARD.index('id="phoneQrWrap"')]
    assert "Your phone &rarr; your relay &rarr; Uoink on this computer." in card
    assert "free account is enough" in card and "holds links only" in card and "7 days" in card
    titles = re.findall(r'<h3 id="phoneStep\dTitle"><span class="phone-step-num" aria-hidden="true">(\d)</span>([^<]+)', card)
    assert titles == [("1", "Make your relay"), ("2", "Connect it "), ("3", "Set up your phone")]
    assert "You need a Render account first. Signing up is free." in card
    assert "up to a minute" in card


def test_deploy_button_is_an_allowed_product_link_and_the_qr_encoder_loads_first():
    link = re.search(r'<a class="button" href="(https://render\.com/deploy\?repo=[^"]+)"([^>]*)>Deploy to Render</a>', DASHBOARD)
    assert link and link.group(1) == "https://render.com/deploy?repo=https://github.com/ryanbiddy/uoink"
    assert "data-product-link" in link.group(2)
    product = DASHBOARD.split("function isProductUrl(target)", 1)[1].split("function isSourceUrl", 1)[0]
    assert link.group(1) in product
    assert DASHBOARD.index('<script src="/dashboard/qrcode.js"></script>') < DASHBOARD.index("<script>")
    assert (ROOT / "assets" / "dashboard" / "qrcode.js").is_file()
    assert 'bare == "/dashboard/qrcode.js"' in (ROOT / "server.py").read_text(encoding="utf-8")


def test_no_outside_qr_service_is_used():
    script = DASHBOARD[DASHBOARD.index("// Guided phone setup"):DASHBOARD.index("function applyPhonePushToken")]
    for banned in ("qrserver", "chart.googleapis", "api.qrcode", "goqr"):
        assert banned not in DASHBOARD


# ---- states -------------------------------------------------------------------

def test_not_configured_shows_step_three_locked_and_no_qr_or_pairing_request():
    out = run_js("""
state.settings = { relay_url: '', relay_enabled: false, relay_poll_minutes: 5, relay_token_set: false };
renderRelaySettings();
({ v: view(), requests: requests.length });
""")
    v = out["v"]
    assert (v["pill"], v["pillState"]) == ("Not connected", "off")
    assert v["locked"] and not (v["qr"] or v["loading"] or v["old"] or v["error"] or v["summary"]) and v["steps"]
    assert v["svg"] == "" and out["requests"] == 0


def test_a_failed_check_says_not_connected_with_the_reason_and_never_shows_the_qr():
    out = run_js("""
state.settings = settings();
relayStatusData = okStatus({ last_error: "The relay didn't accept the pull token. Copy RELAY_PULL_TOKEN from Render again and save it here.", last_ok_at: null });
renderRelayStatus();
({ v: view(), text: getEl('relayStatus').textContent, title: getEl('phoneConnPill').attributes.title, timers: timers.slice() });
""")
    assert (out["v"]["pill"], out["v"]["pillState"]) == ("Not connected", "error")
    assert out["v"]["locked"] and not out["v"]["qr"] and out["v"]["svg"] == ""
    assert out["text"].startswith("The relay didn't accept the pull token") and out["title"].startswith("The relay didn't accept")
    assert 0 not in out["timers"]       # no pairing request was even scheduled


def test_checking_a_sleeping_relay_says_so():
    out = run_js("""
state.settings = settings();
relayStatusData = okStatus({ polling: true });
renderRelayStatus();
({ v: view(), text: getEl('relayStatus').textContent });
""")
    assert out["v"]["pill"] == "Checking…" and out["v"]["locked"]
    assert "can take about a minute" in out["text"]


def test_connected_asks_the_helper_for_the_pairing_key_then_shows_a_local_qr_code():
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus();
renderRelayStatus();
const first = view();
const scheduled = timers.includes(0);
const before = requests.length;
globalThis.reply = () => ({ ok: true, state: 'paired', push_token: PUSH });
await startPhonePairing();
return { first, scheduled, before, request: requests[0], v: view(), url: phonePairingUrl() };
})()
""")
    assert out["v"]["pill"] == "Connected"
    assert out["first"]["loading"] and not out["first"]["qr"]
    assert out["scheduled"] is True and out["before"] == 0
    assert out["request"] == {"path": "/relay/pairing", "body": {}}
    assert out["v"]["qr"] and not out["v"]["locked"] and not out["v"]["loading"]
    svg = out["v"]["svg"]
    assert svg.startswith("<svg") and "<path" in svg and 'fill="#fff"' in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert out["url"] == f"https://my-relay.onrender.com/phone#t={PUSH}"


def test_the_qr_code_decodes_to_the_pairing_url():
    """Rebuild the module matrix from the SVG path and compare it with a second
    encoding of the same text, so the drawing is the code for exactly that URL."""
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus();
globalThis.reply = () => ({ ok: true, state: 'paired', push_token: PUSH });
renderRelayStatus();
await startPhonePairing();
const svg = getEl('phoneQr').innerHTML;
const size = Number(/viewBox="0 0 (\\d+)/.exec(svg)[1]);
const dark = new Set([...svg.matchAll(/M(\\d+) (\\d+)h1v1h-1z/g)].map((m) => m[1] + ',' + m[2]));
const qr = qrcode(0, 'M'); qr.addData(phonePairingUrl()); qr.make();
const n = qr.getModuleCount();
let mismatches = 0;
for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c) !== dark.has((c + 4) + ',' + (r + 4))) mismatches++;
return { size, n, mismatches, count: dark.size };
})()
""")
    assert out["size"] == out["n"] + 8 and out["mismatches"] == 0 and out["count"] > 100


def test_an_old_relay_says_update_and_offers_the_paste_the_push_token_fallback():
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus();
globalThis.reply = () => ({ ok: true, state: 'old_relay', message: 'Update your relay: Render > uoink-relay > Manual Deploy.' });
renderRelayStatus();
await startPhonePairing();
const old = view();
const text = getEl('phoneOldText').textContent;
getEl('phonePushToken').value = 'short';
applyPhonePushToken();
const bad = { status: getEl('phonePushStatus').textContent, v: view() };
getEl('phonePushToken').value = '  ' + PUSH + '  ';
applyPhonePushToken();
return { old, bad, v: view(), url: phonePairingUrl(), kept: getEl('phonePushToken').value,
  note: getEl('phoneStep3Status').textContent };
})()
""")
    assert out["old"]["old"] and not out["old"]["qr"] and out["old"]["svg"] == ""
    assert out["bad"]["status"].startswith("That doesn't look like RELAY_PUSH_TOKEN") and not out["bad"]["v"]["qr"]
    assert out["v"]["qr"] and not out["v"]["old"] and out["kept"] == ""
    assert out["url"] == f"https://my-relay.onrender.com/phone#t={PUSH}"
    assert "Manual Deploy" in out["note"]
    html_text = DASHBOARD[DASHBOARD.index('id="phoneOldText"'):DASHBOARD.index('id="phonePushToken"')]
    assert "Manual Deploy" in html_text and "RELAY_PUSH_TOKEN" in html_text


def test_a_pairing_error_shows_its_reason_and_try_again_asks_again():
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus();
globalThis.reply = () => ({ ok: true, state: 'error', message: "Couldn't reach the relay. Check the address and your connection." });
renderRelayStatus();
await startPhonePairing();
const err = { v: view(), text: getEl('phoneErrorText').textContent };
getEl('phoneRetry').listeners.click[0]();
return { err, after: view(), scheduled: timers.filter((t) => t === 0).length };
})()
""")
    assert out["err"]["v"]["error"] and not out["err"]["v"]["qr"]
    assert out["err"]["text"].startswith("Couldn't reach the relay")
    assert out["after"]["loading"] and not out["after"]["error"]


def test_the_qr_never_shows_when_the_encoder_is_missing():
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus();
globalThis.reply = () => ({ ok: true, state: 'paired', push_token: PUSH });
renderRelayStatus();
await startPhonePairing();
return { v: view(), text: getEl('phoneErrorText').textContent };
})()
""", qr=False)
    assert out["v"]["error"] and not out["v"]["qr"] and out["v"]["svg"] == ""
    assert "Couldn't draw the QR code" in out["text"]


def test_everything_connected_collapses_to_a_summary_and_can_expand_again():
    out = run_js("""
(async () => {
wireRelaySettings();
state.settings = settings();
relayStatusData = okStatus({ picked_up_total: 3, last_pickup_at: nowIso(7) });
renderRelayStatus();
const collapsed = { v: view(), text: getEl('phoneSummaryText').textContent };
getEl('phoneShowSetup').listeners.click[0]();
const shown = view();
// Without any pickup, the summary waits for "I scanned it".
relayStatusData = okStatus();
phoneSetupExpanded = false;
renderRelayStatus();
const waiting = view();
globalThis.reply = () => ({ ok: true, state: 'paired', push_token: PUSH });
await startPhonePairing();
getEl('phoneDone').listeners.click[0]();
return { collapsed, shown, waiting, afterDone: view(), flag: store['uoink.phoneSetupDone'],
  text: getEl('phoneSummaryText').textContent };
})()
""")
    assert out["collapsed"]["v"]["summary"] and not out["collapsed"]["v"]["steps"]
    assert out["collapsed"]["text"] == "Last link picked up 7 min ago · last checked 2 min ago"
    assert out["shown"]["steps"] and not out["shown"]["summary"]
    assert out["waiting"]["steps"] and not out["waiting"]["summary"]
    assert out["afterDone"]["summary"] and not out["afterDone"]["steps"] and out["flag"] == "1"
    assert out["text"].startswith("No links picked up yet")


def test_summary_and_card_titles_read_plainly():
    assert "Phone inbox is on" in DASHBOARD and "Show phone setup again" in DASHBOARD


def test_first_save_with_an_address_and_token_turns_the_inbox_on():
    out = run_js("""
(async () => {
globalThis.reply = (path, body) => ({ ok: true, settings: { relay_url: body.relay_url, relay_enabled: body.relay_enabled,
  relay_poll_minutes: body.relay_poll_minutes, relay_token_set: true } });
state.settings = { relay_token_set: false };
getEl('relayUrl').value = 'https://my-relay.onrender.com';
getEl('relayToken').value = 'pull-token-from-render-0123456789abcdef';
getEl('relayEnabled').checked = false;
getEl('relayPollMinutes').value = '5';
await saveRelaySettings();
await settingsWriteQueue;
return { body: requests[0].body, checked: getEl('relayEnabled').checked };
})()
""")
    assert out["body"]["relay_enabled"] is True and out["checked"] is True


def test_a_credential_store_that_does_not_answer_shows_in_step_two_and_turns_nothing_on():
    message = "The system credential store didn't answer. Unlock it or allow access, then select Save again."
    out = run_js("""
(async () => {
globalThis.reply = () => ({ ok: false, code: 'credential_store_unavailable', error: %s });
state.settings = { relay_token_set: false };
getEl('relayUrl').value = 'https://my-relay.onrender.com';
getEl('relayToken').value = 'pull-token-from-render-0123456789abcdef';
getEl('relayEnabled').checked = false;
getEl('relayPollMinutes').value = '5';
const saved = await saveRelaySettings();
await settingsWriteQueue;
const failed = { saved, sent: requests[0].body.relay_enabled, status: getEl('relayUrlSaveStatus').textContent,
  kind: getEl('relayUrlSaveStatus').dataset.state, retry: !hidden('relayUrlSaveRetry'),
  checked: getEl('relayEnabled').checked, token: getEl('relayToken').value, settings: { ...state.settings } };
// The user unlocks the store and retries: the same save goes through and the box follows it.
globalThis.reply = (path, body) => ({ ok: true, settings: { relay_url: body.relay_url, relay_enabled: body.relay_enabled,
  relay_poll_minutes: body.relay_poll_minutes, relay_token_set: true } });
await settingEdit('relayUrl').retry();
await settingsWriteQueue;
return { failed, retried: { sent: requests[1].body.relay_enabled, status: getEl('relayUrlSaveStatus').textContent,
  checked: getEl('relayEnabled').checked, token: getEl('relayToken').value } };
})()
""" % json.dumps(message))
    failed, retried = out["failed"], out["retried"]
    assert failed["saved"] is False and failed["sent"] is True
    assert failed["status"] == f"Not saved: {message}"
    assert failed["kind"] == "error" and failed["retry"] is True
    # Nothing was saved, so the inbox isn't shown as on, and the pasted token
    # stays in the field for the next Save.
    assert failed["checked"] is False
    assert failed["token"] == "pull-token-from-render-0123456789abcdef"
    assert failed["settings"] == {"relay_token_set": False}
    assert retried == {"sent": True, "status": "Saved", "checked": True, "token": ""}
