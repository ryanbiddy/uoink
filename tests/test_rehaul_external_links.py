"""Dashboard URL boundary and the retired remote features manifest.

Run the shipped JavaScript and event handlers with Node's URL parser and
recording browser/native openers. No helper, browser profile, network, or
generated harness files.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
SCRIPT = DASHBOARD.split("<script>", 1)[1].split("</script>", 1)[0]


def _function(name: str) -> str:
    match = re.search(rf"^    (?:async )?function {name}\(.*?^    }}", SCRIPT, re.M | re.S)
    assert match, f"Missing dashboard function: {name}"
    return match.group(0)


def _run_js(body: str) -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "-"],
        input="import assert from 'node:assert/strict';\nimport vm from 'node:vm';\n" + body,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout, result.stdout + result.stderr


# Cases are independent of the implementation: the caller's provenance, not
# the destination alone, determines which policy applies.
REMOTE_ALLOWED = [
    "https://uoink.app", "https://uoink.app/how?from=dashboard#first-capture",
    "https://www.uoink.app/features/writing-studio",
    "https://docs.preview.uoink.app/guide", "HTTPS://UOINK.APP:443/privacy",
]
PRODUCT_ALLOWED = [
    "https://github.com/ryanbiddy/uoink",
    "https://github.com/ryanbiddy/uoink/blob/main/CHANGELOG.md",
    "https://github.com/ryanbiddy/uoink/releases",
    "https://github.com/ryanbiddy/uoink/issues",
    "https://claude.ai/new", "https://claude.ai/download", "https://youtube.com",
    "https://twitter.com/intent/tweet",
    "https://twitter.com/intent/tweet?text=Hello%20world",
    "https://twitter.com/intent/tweet?url=https%3A%2F%2Fexample.test%2Farticle",
    "https://twitter.com/intent/tweet?text=Hello&url=https%3A%2F%2Fexample.test",
    "HTTPS://CLAUDE.AI:443/new",
    "http://127.0.0.1:43123/splash",
]
SOURCE_ALLOWED = [
    "https://www.youtube.com/watch?v=abcdefghijk&t=42s",
    "https://x.com/example/status/123", "http://example.test/article",
    "https://example.test/podcast/episode?part=2#notes",
    "http://example.test:80/article", "https://example.test:443/article",
    "https://uoink.app/how", "https://docs.uoink.app/guide",
    "https://example.test./article", "https://notlocalhost.test/article",
]
COMMON_DENIED = [
    None, 42, {}, ["https://uoink.app"], "", "not a URL",
    "javascript:alert(1)", "data:text/html,test", "file:///C:/Windows/test.txt",
    "mailto:hi@uoink.app", "ftp://uoink.app/file", "uoink://launch",
    "/features/writing-studio", "//uoink.app/how", "#library",
    "https:uoink.app", "https:/uoink.app", "https:///uoink.app", "https://",
    "https://uoink.app@evil.test", "https://user@uoink.app",
    "https://user:password@docs.uoink.app", "https://@uoink.app",
    "https://user@github.com/ryanbiddy/uoink", "https://uoink.app:bad",
    " https://uoink.app", "https://uoink.app\n", "https://uo\tink.app",
    "https://uoink.app\\@evil.test", "https://uoink.app/\x00path",
    "https://uoink.app/\x7fpath", "https://uoink.app/\x85path",
    "https://user:password@example.test", "https://@example.test",
    "https://example.test\n", "https://exa\tmple.test", "https://example.test\\other",
]
LOCAL_DENIED = [
    "http://127.0.0.1:5179/token",
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/latest/meta-data/",
    "http://localhost/token", "http://child.localhost/token", "http://LOCALHOST./token",
    "http://child.localhost./token", "http://127.1/token", "http://127.255.255.255/token",
    "http://2130706433/token", "http://0x7f000001/token", "http://0177.0.0.1/token",
    "http://%31%32%37.0.0.1/token", "http://0.0.0.0/", "http://0/",
    "http://10.1.2.3/", "http://172.16.0.1/", "http://172.31.255.254/",
    "http://192.168.0.1/", "http://[::1]/", "http://[::]/",
    "http://[fc00::1]/", "http://[fdff::1]/", "http://[fe80::1]/", "http://[febf::1]/",
    "http://[::ffff:127.0.0.1]/", "http://[2001:4860:4860::8888]/",
    "https://8.8.8.8/", "https://192.0.2.1/", "http://printer.local/",
    "https://service.internal/", "https://nested.service.internal./",
    "https://LOCAL./", "http://internal/", "http://printer\u3002local/",
    "https://example.test:444/", "http://example.test:443/", "https://example.test:80/",
]
REMOTE_DENIED = [
    "http://uoink.app/how", "http://docs.uoink.app",
    "https://uoink.app.evil.test", "https://eviluoink.app", "https://uoink-app.test",
    "https://evil.test/uoink.app", "https://evil.test/?next=https://uoink.app",
    "https://uoink.app.", "https://u\u043eink.app",
] + PRODUCT_ALLOWED + SOURCE_ALLOWED[:6]
PRODUCT_DENIED = [
    "https://github.com/other/repository", "https://github.com/ryanbiddy/uoink-evil",
    "https://github.com.evil.test/ryanbiddy/uoink", "https://claude.ai.evil.test/new",
    "http://claude.ai/new", "https://claude.ai/unlisted", "https://claude.ai/new/",
    "https://claude.ai/new?next=https://evil.com", "https://claude.ai/new#https://evil.com",
    "https://claude.ai:444/new", "https://claude.ai/new?", "https://claude.ai/new#",
    "https://www.youtube.com", "https://youtube.com/watch?v=abcdefghijk",
    "https://twitter.com/intent/tweet#https://evil.com", "https://twitter.com/intent/tweet#",
    "https://twitter.com/intent/tweet?text=Hello&next=https://evil.com",
    "https://twitter.com/intent/tweet?url=https://example.test&via=elsewhere",
    "https://twitter.com/intent/tweet?text=one&text=two",
    "https://twitter.com/intent/tweet?url=one&url=two", "https://x.com/intent/tweet?text=Hi",
    "http://127.0.0.1:43124/splash", "http://localhost:43123/splash",
    "http://127.0.0.1:43123/settings", "http://127.0.0.1:43123/splash?next=elsewhere",
    "http://127.0.0.1:43123/splash#other",
] + REMOTE_ALLOWED + SOURCE_ALLOWED
# No fixed URL acquires an unlisted query or fragment by being a product URL.
PRODUCT_DENIED += [url + suffix for url in PRODUCT_ALLOWED[:7]
                   for suffix in ("?next=https://evil.com", "#other")]


@pytest.mark.parametrize("native", [False, True], ids=["browser", "native"])
@pytest.mark.parametrize("kind,allowed,denied", [
    ("remote", REMOTE_ALLOWED, REMOTE_DENIED),
    ("product", PRODUCT_ALLOWED, PRODUCT_DENIED),
    ("source", SOURCE_ALLOWED, ["http://127.0.0.1:43123/splash"]),
], ids=["remote", "product", "source"])
def test_open_external_enforces_each_kind(native, kind, allowed, denied):
    code = "\n".join(_function(name) for name in (
        "nativeApi", "parseExternalUrl", "isProductUrl", "isSourceUrl", "openExternal"))
    _run_js(f"""
const opened = [], messages = [];
const native = {json.dumps(native)};
const context = vm.createContext({{
  URL,
  window: {{
    location: new URL('http://127.0.0.1:43123/dashboard'),
    open: (...args) => opened.push(['browser', ...args]),
    pywebview: native ? {{ api: {{ open_url: url => opened.push(['native', url]) }} }} : undefined,
  }},
  showToast: message => messages.push(message),
}});
vm.runInContext({json.dumps(code)}, context);
const kind = {json.dumps(kind)};
for (const url of {json.dumps(allowed)}) {{
  opened.length = messages.length = 0;
  assert.equal(context.openExternal(url, kind), true, url);
  assert.deepEqual(opened, native
    ? [['native', new URL(url).href]]
    : [['browser', new URL(url).href, '_blank', 'noopener,noreferrer']], url);
  assert.deepEqual(messages, [], url);
}}
const denied = {json.dumps(COMMON_DENIED + LOCAL_DENIED + denied)};
denied.push(undefined, {{ toString: () => 'https://uoink.app' }});
for (const url of denied) {{
  opened.length = messages.length = 0;
  assert.equal(context.openExternal(url, kind), false, String(url));
  assert.deepEqual(opened, [], String(url));
  assert.equal(messages.length, 1, String(url));
  assert.match(messages[0], /blocked/i, String(url));
}}
// No automatic promotion of an unclassified server URL to a product/source.
for (const url of ['https://claude.ai/new', 'https://example.test/article']) {{
  opened.length = messages.length = 0;
  assert.equal(context.openExternal(url), false);
  assert.deepEqual(opened, []);
  assert.match(messages[0], /blocked/i);
}}
opened.length = messages.length = 0;
assert.equal(context.openExternal('https://uoink.app/how'), true);
for (const unknown of [null, false, '', 'unknown', {{source: true}}, {{kind: 'product'}}]) {{
  opened.length = messages.length = 0;
  assert.equal(context.openExternal('https://uoink.app', unknown), false);
  assert.deepEqual(opened, []);
  assert.match(messages[0], /blocked/i);
}}
console.log('PASS ' + kind + ' URL policy');
""")


# A small DOM for the shipped wireEvents(), including bubbling from a child,
# raw href attributes and the URL-normalized href property. All IDs and static
# anchors come from the page. Nothing in this harness decides URL permission.
CLICK_DOM = r"""
const opened = [], copied = [], requests = [];
const location = new URL('http://127.0.0.1:43123/dashboard');
function decode(value) {
  return value.replace(/&quot;/g, '"').replace(/&#039;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
class Element {
  constructor(tag = 'DIV', attrs = {}) {
    this.tagName = tag.toUpperCase(); this.attrs = attrs; this.parent = null;
    this.id = attrs.id || ''; this.value = ''; this.textContent = '';
    this.innerHTML = ''; this.style = {}; this.listeners = {}; this.dataset = {};
    this.options = []; this.files = [];
    const classes = new Set((attrs.class || '').split(/\s+/));
    this.classList = {
      add: (...names) => names.forEach(n => classes.add(n)),
      remove: (...names) => names.forEach(n => classes.delete(n)),
      contains: name => classes.has(name),
      toggle: (name, on = !classes.has(name)) => on ? classes.add(name) : classes.delete(name),
    };
    for (const [name, value] of Object.entries(attrs)) {
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    }
  }
  get href() { return new URL(this.attrs.href || '', location).href; }
  set href(value) { this.attrs.href = value; }
  getAttribute(name) { return this.attrs[name] ?? null; }
  hasAttribute(name) { return name in this.attrs; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  matches(selector) {
    const match = /^([a-z]*)\[([^=\]]+)(?:=['"]([^'"]*)['"])?\]$/i.exec(selector);
    if (match) return (!match[1] || this.tagName === match[1].toUpperCase())
      && this.hasAttribute(match[2]) && (match[3] === undefined || this.getAttribute(match[2]) === match[3]);
    return selector === '#' + this.id;
  }
  closest(selector) {
    for (let el = this; el; el = el.parent) {
      if (selector.split(',').some(part => el.matches(part.trim()))) return el;
    }
    return null;
  }
  focus() {} scrollIntoView() {} setCustomValidity() {}
}
function elementsFrom(html) {
  return [...html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)].map(([, tag, raw]) => {
    const attrs = {};
    for (const [, name, value = ''] of raw.matchAll(/([^\s=<>/]+)(?:="([^"]*)")?/g)) attrs[name] = decode(value);
    return new Element(tag, attrs);
  });
}
const elements = elementsFrom(markup);
const ids = new Map(elements.filter(el => el.id).map(el => [el.id, el]));
const docListeners = {};
const document = {
  getElementById: id => ids.get(id) || null,
  querySelectorAll: selector => elements.filter(el => el.matches(selector)),
  querySelector: () => null,
  addEventListener: (type, fn) => (docListeners[type] ||= []).push(fn),
  documentElement: new Element('html'), body: new Element('body'),
};
const window = {
  location, addEventListener() {}, matchMedia: () => ({ matches: false }),
  open: (...args) => opened.push(['browser', ...args]),
  pywebview: native ? { api: { open_url: url => opened.push(['native', url]) } } : undefined,
};
const context = vm.createContext({
  URL, URLSearchParams, document, window, location, console,
  navigator: { platform: 'Win32', clipboard: { writeText: async text => copied.push(text) } },
  localStorage: { getItem: () => null, setItem() {} },
  sessionStorage: { getItem: () => null, setItem() {} },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  CSS: { escape: value => value },
  fetch: async (...args) => { requests.push(args); throw new Error('Network disabled in test'); },
});
vm.runInContext(script, context);
context.wireEvents();
const state = vm.runInContext('state', context);
async function click(target, type = 'click', button = 0) {
  const event = { target, type, button, defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} };
  for (let el = target; el; el = el.parent) {
    for (const fn of el.listeners[type] || []) await fn(event);
  }
  for (const fn of docListeners[type] || []) await fn(event);
  return event;
}
function reset() { opened.length = copied.length = 0; ids.get('toast').textContent = ''; }
function expectOpen(url) {
  assert.deepEqual(opened, native ? [['native', new URL(url).href]]
    : [['browser', new URL(url).href, '_blank', 'noopener,noreferrer']], url);
  assert.doesNotMatch(ids.get('toast').textContent, /blocked/i);
}
function expectBlocked(url) {
  assert.deepEqual(opened, [], url);
  assert.match(ids.get('toast').textContent, /blocked/i, url);
}
function anchor(html) {
  const el = elementsFrom(html).find(el => el.tagName === 'A');
  assert.ok(el, 'renderer must build a link');
  return el;
}
"""


@pytest.mark.parametrize("native", [False, True], ids=["browser", "native"])
def test_shipped_actions_and_rendered_sources_use_their_own_policy(native):
    _run_js(
        f"const native = {json.dumps(native)};\n"
        f"const markup = {json.dumps(DASHBOARD.split('<script>', 1)[0])};\n"
        f"const script = {json.dumps(SCRIPT.split('    init().catch(', 1)[0])};\n"
        f"const localDenied = {json.dumps(LOCAL_DENIED)};\n"
        + CLICK_DOM + r"""
// Click all shipped help and About links, including nested spans and middle clicks.
const staticLinks = elements.filter(el => el.tagName === 'A' && el.attrs.target === '_blank' && el.attrs.href !== '#');
assert.ok(staticLinks.length >= 20);
assert.ok(staticLinks.some(el => el.attrs.href === '/splash'));
for (const link of staticLinks) for (const type of ['click', 'auxclick']) {
  reset();
  const child = new Element('span'); child.parent = link;
  assert.equal((await click(child, type, type === 'auxclick' ? 1 : 0)).defaultPrevented, true, link.href);
  expectOpen(link.href);
}
reset(); await click(ids.get('starGithub')); expectOpen('https://github.com/ryanbiddy/uoink');
// The agent setup button is rendered after startup, outside the reader.
state.agentDetectionLoaded = true;
const claudeButton = elementsFrom(context.agentSetupMarkup()).find(el => el.dataset.openExternal);
assert.ok(claudeButton, 'Install Claude Desktop is reachable');
reset(); await click(claudeButton); expectOpen('https://claude.ai/download');
state.selectedYoink = { video_id: 'fixture', title: 'Saved source', source_url: 'https://x.com/example/status/123' };
state.selectedYoinkMarkdown = '# Saved source\n\nThe saved text.';
reset(); await click(ids.get('yoinkSendClaude')); expectOpen('https://claude.ai/new');
assert.deepEqual(copied, [state.selectedYoinkMarkdown]);
assert.equal(ids.get('toast').textContent, 'Copied. Paste it into the new Claude chat.');
reset(); await click(ids.get('yoinkCopyMarkdown'));
assert.deepEqual(opened, []); assert.deepEqual(copied, [state.selectedYoinkMarkdown]);
assert.equal(ids.get('toast').textContent, 'Copied as Markdown.');
ids.get('writingOutput').dataset.rawText = 'A fixture draft & link?';
state.writingDrafts = ['A fixture draft & link?'];
reset(); await click(ids.get('openWritingInX'));
expectOpen('https://twitter.com/intent/tweet?text=A%20fixture%20draft%20%26%20link%3F');

// Every YouTube entry point must pass the shared boundary even when the
// helper would successfully open/focus a window. No helper request is needed.
const savedAuthFetch = context.authFetch;
for (const outcome of ['focused_existing', 'opened_new', 'offline']) {
  const helperCalls = [];
  context.authFetch = async path => {
    helperCalls.push(path);
    if (outcome === 'offline') throw new Error('offline');
    return {ok: true, action: outcome, url: 'https://www.youtube.com'};
  };
  for (const button of [ids.get('newYoink'), ids.get('openYouTubeForYou'),
    new Element('button', {'data-open-youtube': ''})]) {
    reset(); await click(button); expectOpen('https://youtube.com');
    assert.deepEqual(helperCalls, [], 'no helper-side opening bypass');
  }
}
context.authFetch = savedAuthFetch;

// A failed open must remain visible after a successful copy (and YouTube CTA).
const realOpen = context.openExternal;
context.openExternal = (url, kind) => realOpen('http://127.0.0.1:5179/token', kind);
reset(); await click(ids.get('yoinkSendClaude')); expectBlocked('Claude');
assert.deepEqual(copied, [state.selectedYoinkMarkdown]);
assert.notEqual(ids.get('toast').textContent, 'Copied. Paste it into the new Claude chat.');
reset(); await click(ids.get('newYoink')); expectBlocked('YouTube');
context.openExternal = realOpen;

// All four captured-content renderers declare their provenance.
context.renderYoinkDetail();
const timestamp = anchor(context.readerTimeHtml(42, 'https://www.youtube.com/watch?v=abcdefghijk'));
assert.ok(timestamp.hasAttribute('data-source-link'));
reset(); await click(timestamp); expectOpen('https://www.youtube.com/watch?v=abcdefghijk&t=42s');
for (const url of ['https://www.youtube.com/watch?v=abcdefghijk', 'https://example.test/article',
  'http://example.test/episode', 'https://x.com/example/status/123', 'https://docs.uoink.app/guide',
  ...localDenied]) {
  state.selectedYoink.source_url = url;
  context.renderYoinkDetail();
  context.renderActivitySources([{ canonical_url: url, display_name: 'Saved source', kind: 'page' }]);
  const links = [ids.get('yoinkSourceLink'),
    anchor(context.readerMarkdownHtml('[Read the source](' + url + ')')),
    anchor(ids.get('activitySourcesBody').innerHTML)];
  for (const link of links) for (const type of ['click', 'auxclick']) {
    assert.ok(link.hasAttribute('data-source-link'), 'source provenance: ' + url);
    reset();
    const child = new Element('span'); child.parent = link;
    assert.equal((await click(child, type, type === 'auxclick' ? 1 : 0)).defaultPrevented, true);
    if (localDenied.includes(url)) expectBlocked(url);
    else expectOpen(url);
  }
}
// Raw source attributes are checked even without target=_blank.
for (const url of ['http://127.0.0.1:5179/token', 'http://169.254.169.254/latest/meta-data/']) {
  reset();
  assert.equal((await click(new Element('a', {href: url, 'data-source-link': ''}))).defaultPrevented, true);
  expectBlocked(url);
}
// Browser href normalization must not erase malformed input before validation.
for (const attrs of [{}, {'data-source-link': ''}, {'data-product-link': ''}]) for (const raw of [
  'https://uo\tink.app/how', 'https://uoink.app\n/how', 'https://uoink.app\\how',
  'https://user:pass@uoink.app/how', 'https://@uoink.app/how',
  'javascript:alert(1)', 'file:///C:/secret.txt',
]) {
  const link = new Element('a', { href: raw, target: '_blank', ...attrs });
  for (const type of ['click', 'auxclick']) {
    reset();
    assert.equal((await click(link, type, type === 'auxclick' ? 1 : 0)).defaultPrevented, true);
    expectBlocked(raw);
  }
}
for (const raw of ['https://uo\tink.app/how', 'https://uoink.app\\how', 'https://user@example.test']) {
  assert.equal(context.sanitizeHttpUrl(raw), null, 'activity sources reject before normalization');
}
// Fetched/server buttons and anchors default to remote, even if the URL
// resembles a fixed product destination. A source attribute on a button
// cannot grant the more permissive source-link policy.
for (const url of ['https://evil.test', 'http://127.0.0.1:5179/token',
  'http://169.254.169.254/latest/meta-data/', 'https://claude.ai/new',
  'https://claude.ai/new?next=https://evil.com', 'https://github.com/ryanbiddy/uoink']) {
  reset(); await click(new Element('button', { 'data-open-external': url, 'data-source-link': '' }));
  expectBlocked(url);
  reset(); await click(new Element('a', { href: url, target: '_blank' })); expectBlocked(url);
}
for (const url of ['https://claude.ai/new?next=https://evil.com',
  'https://twitter.com/intent/tweet?text=Hi&redirect=https://evil.com', 'https://evil.test']) {
  reset(); await click(new Element('button', { 'data-open-external': url, 'data-product-link': '' }));
  expectBlocked(url);
  reset(); await click(new Element('a', { href: url, target: '_blank', 'data-product-link': '' }));
  expectBlocked(url);
}
const helpUrl = 'https://docs.uoink.app/guide';
reset(); await click(new Element('button', { 'data-open-external': helpUrl })); expectOpen(helpUrl);
reset(); await click(new Element('a', { href: helpUrl, target: '_blank' })); expectOpen(helpUrl);
assert.ok(requests.every(([url]) => String(url).startsWith('/')), 'no external fetch');
console.log('PASS shipped action and reader click handlers');
""")


def test_manifest_loader_cache_and_features_view_are_absent():
    for retired in (
        "features-manifest", "loadFeatures", "FALLBACK_FEATURES", "featuresManifest",
        "data-open-feature", 'data-tab-panel="features"', 'data-tab-button="features"',
    ):
        assert retired not in DASHBOARD, retired
    assert not re.search(r"fetch\(\s*[\"'`]https?://", SCRIPT)


def test_dashboard_init_does_not_request_remote_features():
    # Execute the real init sequence, with its local loaders stubbed. A new
    # manifest loader call must fail this test, even if it catches fetch errors.
    local_steps = [
        "hydrateMarks", "wireEvents", "wireLibraryActivityEvents", "wireRoutes",
        "applyHashRoute", "refreshHealth", "loadLibraryFacets", "refreshJobs",
        "loadLibrary", "loadLibraryActivity", "startLibraryActivityTimer",
        "loadResume", "loadForYou", "loadWriting", "renderSources",
        "refreshActivity", "connectJobsStream",
    ]
    _run_js(f"""
const calls = [], requests = [];
const context = vm.createContext({{
  fetch: (...args) => {{ requests.push(args); return Promise.resolve({{ok: true, json: async () => ({{}})}}); }},
  setInterval: () => 0,
}});
for (const name of {json.dumps(local_steps)}) context[name] = () => calls.push(name);
vm.runInContext({json.dumps(_function('init'))}, context);
await context.init();
assert.deepEqual(requests, []);
assert.ok(calls.includes('loadLibrary'));
assert.ok(calls.includes('connectJobsStream'));
console.log('PASS dashboard init without remote requests');
""")


@pytest.mark.parametrize("document", ["privacy-policy.md", "security.md"])
def test_docs_disclose_that_no_manifest_request_is_made(document):
    text = " ".join((ROOT / "docs" / document).read_text(encoding="utf-8").split())
    assert "dashboard makes no features-manifest request" in text
    assert "https://uoink.app/api/features-manifest" in text
    assert "on load or when switching views" in text
    for kind in ("Remote or server-supplied URLs", "Fixed product links", "Captured-content source links"):
        assert kind in text
    for boundary in ("uoink.app", "subdomain", "exact origin", "text", "url", "non-default port",
                     "127.0.0.0/8", "::1", "0.0.0.0", "10/8", "172.16/12", "192.168/16",
                     "fc00::/7", "169.254/16", "fe80::/10", "localhost", ".local", ".internal",
                     "credentials", "blocked", "/splash"):
        assert boundary in text
