"""Dashboard Settings > Capture > Phone inbox (Uoink Relay).

Markup checks, then the product's own JavaScript in a Node vm with a small
fake DOM, as tests/test_dashboard_runthrough_fixes.py does. No helper, no
network: authFetch is replaced by a recording stub.
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
DOCS_URL = "https://github.com/ryanbiddy/uoink/blob/main/docs/relay.md"

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const scriptCode = page.slice(page.indexOf('<script>') + 8, page.indexOf('    init().catch('));

function element(id) {
  const classes = new Set();
  return {
    id, value: '', checked: false, disabled: false, textContent: '', innerHTML: '', placeholder: '',
    dataset: {}, attributes: {}, style: {}, listeners: {},
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => { const on = force === undefined ? !classes.has(name) : Boolean(force);
        if (on) classes.add(name); else classes.delete(name); return on; },
    },
    setAttribute(key, value) { this.attributes[key] = String(value); },
    getAttribute(key) { return key in this.attributes ? this.attributes[key] : null; },
    removeAttribute(key) { delete this.attributes[key]; },
    querySelectorAll: () => [], querySelector: () => null, closest: () => null,
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    focus() {},
  };
}

const elements = {};
const getEl = (id) => (elements[id] = elements[id] || element(id));
const timers = [];
const context = {
  document: { getElementById: getEl, querySelector: () => null, querySelectorAll: () => [], activeElement: null },
  window: { addEventListener() {}, setTimeout: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimeout() {} },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  console, URL, Set, Map, Promise, JSON, Date, AbortController,
  fetch: () => Promise.reject(new Error('network forbidden')),
  setTimeout: () => 0, clearTimeout: () => {},
  localStorage: { getItem: () => null, setItem() {} },
};
vm.createContext(context);
vm.runInContext(scriptCode + '\n;globalThis.state = state;', context);
context.getEl = getEl;
context.timers = timers;
context.requests = [];
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


def run_js(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run([node, "-e", HARNESS], input=code, cwd=ROOT, text=True,
                            encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["result"]


def _settings_section(key: str) -> str:
    start = DASHBOARD.index(f'id="settings-{key}"')
    return DASHBOARD[start:DASHBOARD.index("</section>", start)]


def _card() -> str:
    start = DASHBOARD.index('id="phone-inbox"')
    return DASHBOARD[start:DASHBOARD.index('id="relayStatus"', start)]


def test_phone_inbox_card_lives_in_settings_capture():
    capture = _settings_section("capture")
    assert 'id="phone-inbox"' in capture and "<h2>Phone inbox</h2>" in capture
    assert DASHBOARD.count('id="phone-inbox"') == 1
    card = _card()
    assert "your own Render account" in card and "7 days" in card
    for control in ("relayUrl", "relayToken", "relayEnabled", "relayPollMinutes", "relaySave",
                    "relayCheck", "relayUrlSaveStatus", "relayUrlSaveRetry"):
        assert DASHBOARD.count(f'id="{control}"') == 1, control
        assert f'id="{control}"' in card, control
    assert '<label for="relayUrl">Relay address</label>' in card
    assert '<label for="relayToken">Pull token</label>' in card
    assert "Pick up links shared from my phone" in card
    assert re.findall(r'<option value="(\d+)"', card.split('id="relayPollMinutes"', 1)[1].split("</select>", 1)[0]) \
        == ["2", "5", "15", "30"]
    assert '>Save</button>' in card and '>Check now</button>' in card


def test_pull_token_input_is_a_password_that_is_never_prefilled():
    tag = re.search(r'<input[^>]*id="relayToken"[^>]*>', DASHBOARD).group(0)
    assert 'type="password"' in tag and 'autocomplete="new-password"' in tag
    assert "value=" not in tag and "placeholder=" not in tag


def test_setup_link_is_an_allowed_product_link():
    link = re.search(r'<a href="' + re.escape(DOCS_URL) + r'"[^>]*>([^<]+)</a>', _card())
    assert link and link.group(1) == "Set up a relay"
    assert "data-product-link" in link.group(0) and 'target="_blank"' in link.group(0)
    product = DASHBOARD.split("function isProductUrl(target)", 1)[1].split("function isSourceUrl", 1)[0]
    assert f'"{DOCS_URL}"' in product


def test_hydrate_fills_the_card_but_never_the_token():
    result = run_js(r"""
state.settings = { relay_url: 'https://my-relay.onrender.com', relay_enabled: true,
  relay_poll_minutes: 15, relay_token_set: true };
renderRelaySettings();
const saved = { token: getEl('relayToken').value, placeholder: getEl('relayToken').placeholder,
  url: getEl('relayUrl').value, enabled: getEl('relayEnabled').checked,
  minutes: getEl('relayPollMinutes').value, check: getEl('relayCheck').disabled,
  status: getEl('relayStatus').textContent };
state.settings = { relay_url: '', relay_enabled: false, relay_poll_minutes: 1, relay_token_set: false };
renderRelaySettings();
({ saved, unset: { token: getEl('relayToken').value, placeholder: getEl('relayToken').placeholder,
  check: getEl('relayCheck').disabled, status: getEl('relayStatus').textContent,
  options: getEl('relayPollMinutes').innerHTML, minutes: getEl('relayPollMinutes').value } });
""")
    assert result["saved"] == {"token": "", "placeholder": "Saved", "url": "https://my-relay.onrender.com",
                               "enabled": True, "minutes": "15", "check": False,
                               "status": "On. Uoink checks every 15 minutes."}
    unset = result["unset"]
    assert unset["token"] == "" and unset["placeholder"] == "Paste the pull token"
    assert unset["check"] is True and unset["status"] == "Off."
    assert '<option value="1">1 minute</option>' in unset["options"] and unset["minutes"] == "1"
    hydrate = DASHBOARD.split("function hydrateSettings(data, versions)", 1)[1].split("function tasteSection", 1)[0]
    assert "renderRelaySettings(versions, previous);" in hydrate


def test_save_sends_the_card_and_clears_the_typed_token():
    result = run_js(r"""
(async () => {
  globalThis.reply = (path, body) => ({ ok: true, settings: { relay_url: body.relay_url.replace(/\/+$/, ''),
    relay_enabled: body.relay_enabled, relay_poll_minutes: body.relay_poll_minutes,
    relay_token_set: true } });
  state.settings = { relay_token_set: false };
  getEl('relayUrl').value = ' https://my-relay.onrender.com/ ';
  getEl('relayToken').value = 'pull-token-from-render-0123456789abcdef';
  getEl('relayEnabled').checked = true;
  getEl('relayPollMinutes').value = '5';
  await saveRelaySettings();
  await settingsWriteQueue;
  const first = { body: requests[0].body, token: getEl('relayToken').value, url: getEl('relayUrl').value,
    placeholder: getEl('relayToken').placeholder, status: getEl('relayUrlSaveStatus').textContent };
  // A later save without typing keeps the stored token: no relay_token sent.
  getEl('relayPollMinutes').value = '30';
  await saveRelaySettings();
  await settingsWriteQueue;
  // Turning it on with no token anywhere is refused before any request.
  state.settings = { relay_token_set: false };
  const before = requests.length;
  await saveRelaySettings();
  return { first, second: requests[1].body, refused: requests.length === before,
    refusal: getEl('relayUrlSaveStatus').textContent };
})()
""")
    assert result["first"]["body"] == {"relay_url": "https://my-relay.onrender.com/", "relay_enabled": True,
                                       "relay_poll_minutes": 5,
                                       "relay_token": "pull-token-from-render-0123456789abcdef"}
    assert result["first"]["token"] == "" and result["first"]["placeholder"] == "Saved"
    assert result["first"]["url"] == "https://my-relay.onrender.com"
    assert result["first"]["status"] == "Saved"
    assert result["second"] == {"relay_url": "https://my-relay.onrender.com", "relay_enabled": True,
                                "relay_poll_minutes": 30}
    assert result["refused"] is True and result["refusal"] == "Not saved: paste the pull token first."


def test_status_line_reads_plainly():
    result = run_js(r"""
(async () => {
  const out = {};
  state.settings = { relay_url: 'https://r.example', relay_enabled: true, relay_poll_minutes: 5, relay_token_set: true };
  globalThis.reply = (path) => ({ ok: true, enabled: true, configured: true,
    last_poll_at: new Date(Date.now() - 3 * 60000).toISOString(),
    last_ok_at: new Date(Date.now() - 3 * 60000).toISOString(), last_error: null,
    last_capture_error: null, picked_up_total: 4, last_pending_count: 0, polling: false });
  await loadRelayStatus();
  out.ok = getEl('relayStatus').textContent;
  out.paths = requests.map(r => r.path);
  globalThis.reply = () => ({ ok: true, last_poll_at: new Date().toISOString(),
    last_error: "The relay didn't accept the pull token. Copy RELAY_PULL_TOKEN from Render again and save it here.",
    picked_up_total: 0, polling: false });
  await checkRelayNow();
  out.error = getEl('relayStatus').textContent;
  out.checkBody = requests.at(-1);
  globalThis.reply = () => ({ ok: true, last_poll_at: new Date().toISOString(), picked_up_total: 1, polling: true });
  await checkRelayNow();
  out.polling = getEl('relayStatus').textContent;
  out.timers = timers.slice();
  state.settings = { relay_enabled: false };
  const before = requests.length;
  await loadRelayStatus();
  out.offRequests = requests.length - before;
  out.off = getEl('relayStatus').textContent;
  return out;
})()
""")
    assert result["ok"] == "Last checked 3 min ago · 4 links picked up"
    assert result["paths"] == ["/relay/status"]
    assert result["error"].startswith("The relay didn't accept the pull token")
    assert result["checkBody"] == {"path": "/relay/check", "body": {}}
    assert result["polling"].startswith("Checking the relay")
    assert 5000 in result["timers"]
    assert result["offRequests"] == 0 and result["off"] == "Off."
