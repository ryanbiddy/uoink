"""Uoink Relay phone setup: GET /v1/pairing, the /phone page, its manifest,
share target, service worker and icons. Real server, MemoryStore, loopback.
The page's script also runs in Node against a tiny fake DOM."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from tests.test_relay_service import PULL, PUSH, app, relay  # noqa: F401  (relay is a fixture)

ROOT = Path(__file__).resolve().parents[1]


# ---- /v1/pairing ---------------------------------------------------------

def test_pairing_needs_the_pull_token_and_returns_the_push_token(relay):
    status, payload, headers, _ = relay.request("GET", "/v1/pairing", token=PULL)
    assert status == 200 and payload == {"ok": True, "push_token": PUSH}
    assert headers["cache-control"] == "no-store"


@pytest.mark.parametrize("token,status", [(None, 401), ("wrong-" + "x" * 40, 401), (PUSH, 403)])
def test_pairing_rejects_push_wrong_and_missing_tokens(relay, token, status):
    got, payload, _, raw = relay.request("GET", "/v1/pairing", token=token)
    assert got == status and payload["ok"] is False
    assert PUSH.encode() not in raw


def test_pairing_goes_through_the_failed_auth_limiter(relay):
    for _ in range(app.AUTH_FAIL_LIMIT):
        assert relay.request("GET", "/v1/pairing", token="wrong-" + "x" * 40)[0] == 401
    assert relay.request("GET", "/v1/pairing", token="wrong-" + "x" * 40)[0] == 429
    # A valid token is never refused.
    assert relay.request("GET", "/v1/pairing", token=PULL)[0] == 200


# ---- /phone ----------------------------------------------------------------

def test_phone_page_is_served_with_its_own_strict_csp_and_no_token(relay):
    status, _, headers, raw = relay.request("GET", "/phone")
    html = raw.decode("utf-8")
    assert status == 200 and headers["content-type"].startswith("text/html")
    assert PUSH not in html and PULL not in html
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp and "manifest-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "script-src 'sha256-" in csp
    assert headers["cache-control"] == "no-store" and headers["referrer-policy"] == "no-referrer"
    # The hashes in the header match the inline blocks exactly.
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    for text, directive in ((script, "script-src"), (style, "style-src")):
        digest = base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
        assert f"{directive} 'sha256-{digest}'" in csp
    # No outside scripts, styles, fonts, images or analytics.
    assert not re.search(r'(?:src|href)="https?://', html)
    assert " style=" not in html and " onclick=" not in html
    for words in ("Paste a link", "Forget this phone", "Add to Home Screen", "Send from the Share sheet"):
        assert words in html
    assert "history.replaceState" in html and "localStorage" in html


def test_phone_page_is_the_same_static_page_whatever_the_query(relay):
    # Fragments never leave the phone; the server only ever sees /phone.
    a = relay.request("GET", "/phone")[3]
    b = relay.request("GET", "/phone?url=https%3A%2F%2Fexample.com%2Fa")[3]
    assert a == b


def test_manifest_has_a_share_target_and_installable_icons(relay):
    status, _, headers, raw = relay.request("GET", "/phone.webmanifest")
    manifest = json.loads(raw)
    assert status == 200 and "manifest+json" in headers["content-type"]
    assert manifest["start_url"] == "/phone" and manifest["display"] == "standalone"
    assert manifest["share_target"] == {"action": "/phone", "method": "GET",
                                        "enctype": "application/x-www-form-urlencoded",
                                        "params": {"title": "title", "text": "text", "url": "url"}}
    assert manifest["share_target"]["action"].startswith(manifest["scope"])
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    for icon in manifest["icons"]:
        got, _, h, body = relay.request("GET", icon["src"])
        assert got == 200 and h["content-type"] == "image/png" and body.startswith(b"\x89PNG\r\n\x1a\n")


def test_icons_are_valid_pngs_of_the_right_size(relay):
    for size in (180, 192, 512):
        _, _, _, raw = relay.request("GET", f"/phone-icon-{size}.png")
        width, height = struct.unpack(">II", raw[16:24])
        assert (width, height) == (size, size)
        idat = raw[raw.index(b"IDAT") + 4:raw.index(b"IEND") - 8]
        data = zlib.decompress(idat)
        assert len(data) == size * (size * 3 + 1)
        assert bytes([0xFF, 0xD2, 0x3F]) in data   # Uoink yellow
    assert relay.request("GET", "/phone-icon-999.png")[0] == 404


def test_service_worker_is_served_and_caches_nothing(relay):
    status, _, headers, raw = relay.request("GET", "/phone-sw.js")
    assert status == 200 and "javascript" in headers["content-type"]
    assert b"fetch" in raw and b"caches" not in raw


def test_phone_routes_do_not_take_posts(relay):
    assert relay.request("POST", "/phone", {"url": "https://example.com"}, token=PUSH)[0] == 404


# ---- the page's script, run for real in Node under a fake DOM --------------

SCRIPT = re.search(r'_PHONE_SCRIPT = r"""(.*?)"""', (ROOT / "relay" / "app.py").read_text(encoding="utf-8"), re.S).group(1)

HARNESS = r"""
const vm = require('node:vm');
const script = require('node:fs').readFileSync(0, 'utf8');
const cfg = JSON.parse(process.argv[1]);
const els = {};
function el(id) {
  if (els[id]) return els[id];
  return els[id] = { id, hidden: false, textContent: '', className: '', value: '', disabled: false, open: false,
    listeners: {}, addEventListener(t, f) { (this.listeners[t] ||= []).push(f); } };
}
const storage = Object.assign({}, cfg.storage || {});
const history = [];
const calls = [];
const replies = (cfg.replies || []).slice();
const ctx = {
  document: { getElementById: el },
  navigator: { userAgent: cfg.ua || 'Mozilla/5.0 (Linux; Android 14) Chrome/120', maxTouchPoints: 5 },
  window: {
    location: { hash: cfg.hash || '', search: cfg.search || '', pathname: '/phone', origin: 'https://relay.example.test' },
    history: { replaceState: (a, b, url) => history.push(url) },
    localStorage: { getItem: (k) => (k in storage ? storage[k] : null), setItem: (k, v) => { storage[k] = String(v); },
      removeItem: (k) => { delete storage[k]; } },
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms, 5)), clearTimeout,
  },
  fetch: async (url, opts) => {
    calls.push({ url, auth: opts.headers.Authorization, body: JSON.parse(opts.body) });
    const r = replies.shift() || { status: 201, json: { ok: true } };
    if (r.reject) throw new Error('offline');
    return { status: r.status, json: async () => r.json || {} };
  },
  URLSearchParams, AbortController, Promise, JSON, setTimeout, clearTimeout,
};
vm.createContext(ctx);
vm.runInContext(script, ctx);
(async () => {
  const out = {};
  await new Promise((r) => setTimeout(r, 30));
  out.history = history; out.storage = storage; out.calls = calls;
  out.pill = els.pill.textContent; out.unpairedHidden = els.unpaired.hidden; out.sendHidden = els.sendcard.hidden;
  out.shared = els.sharedresult && els.sharedresult.textContent; out.link = els.link && els.link.value;
  if (cfg.submit !== undefined) {
    el('link').value = cfg.submit;
    await els.sendform.listeners.submit[0]({ preventDefault() {} });
    await new Promise((r) => setTimeout(r, 150));
    out.result = els.result.textContent; out.resultClass = els.result.className; out.calls = calls;
  }
  if (cfg.forget) { els.forget.listeners.click[0](); out.afterForget = { storage, pill: els.pill.textContent }; }
  process.stdout.write(JSON.stringify(out));
})();
"""

TOKEN = "T" * 40


def run_page(**cfg):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run([node, "-e", HARNESS, json.dumps(cfg)], input=SCRIPT, text=True, encoding="utf-8",
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_page_stores_the_fragment_token_and_clears_the_address_bar():
    out = run_page(hash="#t=" + TOKEN)
    assert out["storage"] == {"uoink-relay-push-token": TOKEN}
    assert out["history"] == ["/phone"]          # no #t= left in the address bar
    assert out["pill"] == "Paired" and out["unpairedHidden"] is True and out["sendHidden"] is False


def test_page_without_a_token_asks_to_pair_and_sends_nothing():
    out = run_page(submit="https://example.com/a")
    assert out["pill"] == "Not paired" and out["sendHidden"] is True
    assert out["calls"] == [] and "isn't paired" in out["result"]


def test_send_posts_with_the_stored_token_and_reports_success():
    out = run_page(storage={"uoink-relay-push-token": TOKEN}, submit="https://example.com/a")
    assert out["calls"] == [{"url": "/v1/links", "auth": "Bearer " + TOKEN, "body": {"url": "https://example.com/a"}}]
    assert out["result"].startswith("Sent.") and "ok" in out["resultClass"]


@pytest.mark.parametrize("status,words", [(401, "doesn't match"), (403, "can't add"), (429, "busy or full"),
                                          (400, "didn't look like a link")])
def test_send_failures_are_plain(status, words):
    out = run_page(storage={"uoink-relay-push-token": TOKEN}, submit="nope",
                   replies=[{"status": status, "json": {"error": "no http(s) link found"}}])
    assert words in out["result"] and "bad" in out["resultClass"]


def test_a_sleeping_relay_is_retried_automatically_then_succeeds():
    out = run_page(storage={"uoink-relay-push-token": TOKEN}, submit="https://example.com/a",
                   replies=[{"reject": True}, {"status": 503}, {"status": 201, "json": {"ok": True}}])
    assert len(out["calls"]) == 3 and out["result"].startswith("Sent.")


def test_android_share_target_sends_the_shared_url_with_the_stored_token():
    out = run_page(storage={"uoink-relay-push-token": TOKEN},
                   search="?title=A+video&text=Look&url=https%3A%2F%2Fexample.com%2Fv")
    assert out["calls"] == [{"url": "/v1/links", "auth": "Bearer " + TOKEN,
                             "body": {"url": "https://example.com/v", "text": "Look", "title": "A video"}}]
    assert out["shared"].startswith("Sent.") and "/phone" in out["history"]


def test_share_target_on_an_unpaired_phone_keeps_the_text_and_says_so():
    out = run_page(search="?text=Look+https%3A%2F%2Fexample.com%2Fv")
    assert out["calls"] == [] and "isn't paired" in out["shared"] and "example.com/v" in out["link"]


def test_forget_this_phone_clears_the_token():
    out = run_page(storage={"uoink-relay-push-token": TOKEN}, forget=True)
    assert out["afterForget"] == {"storage": {}, "pill": "Not paired"}


# ---- docs and packaging ---------------------------------------------------------

def test_docs_lead_with_the_qr_path_and_say_the_pull_token_reveals_the_push_token():
    docs = (ROOT / "docs" / "relay.md").read_text(encoding="utf-8")
    assert docs.index("The quick way: three steps in Uoink") < docs.index("Manual setup (fallback)")
    assert "pull token now also reveals the push token" in docs
    assert "Manual Deploy" in docs and "Waking your relay" in docs and "/v1/pairing" in docs
    assert "Signing up is free" in docs


def test_the_qr_encoder_and_its_license_ship_everywhere_the_dashboard_does():
    for rel, needle in (("build.ps1", "qrcode-generator-1.4.4-MIT-LICENSE.txt"),
                        ("installer/uoink.iss", "qrcode-generator-1.4.4-MIT-LICENSE.txt"),
                        ("THIRD-PARTY-NOTICES.md", "qrcode-generator 1.4.4"),
                        ("scripts/gen_third_party_notices.py", "qrcode-generator 1.4.4")):
        assert needle in (ROOT / rel).read_text(encoding="utf-8"), rel
    assert (ROOT / "third-party-notices" / "qrcode-generator-1.4.4-MIT-LICENSE.txt").read_text(
        encoding="utf-8").startswith("MIT License")
    payload = json.loads((ROOT / "scripts" / "mac" / "payload.json").read_text(encoding="utf-8"))
    assert "assets/dashboard" in payload["paths"] and "third-party-notices" in payload["paths"]
    assert (ROOT / "assets" / "dashboard" / "qrcode.js").is_file()
