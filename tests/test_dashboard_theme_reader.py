"""Dashboard Appearance setting and reader Back.

Theme: Settings > App > Appearance picks Match Windows (Match system on a Mac),
Light or Dark. The helper's settings hold the choice (dashboard_theme), so the
Uoink window and a browser tab agree; localStorage caches it for a boot script
in <head> that sets data-theme on <html> before the first paint. The token
CSS keeps the prefers-color-scheme block, guarded off by data-theme="light",
and repeats the dark values under data-theme="dark"
(tests/test_rehaul_foundation.py holds the token blocks themselves).

Reader: the Back row sticks to the top of the scrolling area for the whole
read, Esc closes the reader, and coming back to the Library (Back, Esc or the
browser's Back) restores the list's scroll position.

The dashboard checks execute the product's own JavaScript in a Node vm with a
small fake DOM, the way tests/test_note_readiness_truth.py does.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import shutil
import subprocess

import pytest

import server

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
SCRIPT = DASHBOARD[DASHBOARD.index("<script>"):]

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const scriptCode = page.slice(page.indexOf('<script>') + 8, page.indexOf('    init().catch('));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

function element(id) {
  const classes = new Set();
  return {
    id, value: '', textContent: '', innerHTML: '', title: '', dataset: {}, attributes: {}, style: {},
    scrollTop: 0, scrollHeight: 4000, clientHeight: 800,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : Boolean(force);
        if (on) classes.add(name); else classes.delete(name);
        return on;
      },
    },
    setAttribute(key, value) { this.attributes[key] = String(value); },
    getAttribute(key) { return key in this.attributes ? this.attributes[key] : null; },
    removeAttribute(key) { delete this.attributes[key]; },
    hasAttribute(key) { return key in this.attributes; },
    querySelectorAll: () => [], querySelector: () => null, closest: () => null,
    addEventListener() {}, focus() {},
  };
}

const elements = {};
const getEl = (id) => (elements[id] = elements[id] || element(id));
const content = element('content');
const selectors = { '.content': content };
const storage = new Map(Object.entries(input.storage || {}));
const windowScroll = { y: 0 };
const context = {
  document: {
    addEventListener() {},
    documentElement: element('html'),
    getElementById: getEl,
    querySelector: (selector) => selectors[selector] || null,
    querySelectorAll: (selector) => selectors[selector] ? [selectors[selector]] : [],
  },
  window: {
    addEventListener() {},
    get scrollY() { return windowScroll.y; },
    scrollTo(_x, y) { windowScroll.y = y; },
    history: input.history ? { scrollRestoration: 'auto' } : undefined,
  },
  navigator: { platform: input.platform || 'Win32', clipboard: { writeText: () => Promise.resolve() } },
  localStorage: {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => { if (input.storageThrows) throw new Error('blocked'); storage.set(key, String(value)); },
  },
  console, URL, Set, Map, Promise, JSON, Date,
  fetch: () => Promise.reject(new Error('network forbidden')),
  setTimeout: () => 0, clearTimeout: () => {},
};
vm.createContext(context);
vm.runInContext(scriptCode + '\n;globalThis.state = state; globalThis.els = els;', context);
Object.assign(context, { getEl, content, selectors, storage, windowScroll });
Promise.resolve(vm.runInContext(input.code, context)).then(
  (result) => process.stdout.write(JSON.stringify({ result })),
  (error) => { process.stderr.write(String(error && error.stack || error)); process.exit(1); },
);
"""


def run_js(code: str, **options):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run([node, "-e", HARNESS], input=json.dumps({"code": code, **options}), cwd=ROOT,
                            text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["result"]


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


# ---- Theme: the helper's setting -------------------------------------------

def test_dashboard_theme_setting_defaults_to_system_and_normalizes():
    assert server._default_settings()["dashboard_theme"] == "system"
    assert server._normalize_settings({})["dashboard_theme"] == "system"
    assert server._normalize_settings({"dashboard_theme": "DARK"})["dashboard_theme"] == "dark"
    assert server._normalize_settings({"dashboard_theme": "sepia"})["dashboard_theme"] == "system"


def test_dashboard_theme_saves_through_the_settings_handler(monkeypatch):
    written, responses = [], []
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_write_settings", written.append)
    monkeypatch.setattr(server, "_public_settings", lambda data=None: data or {})

    handler._handle_settings_post({"dashboard_theme": "light"})
    assert written[-1]["dashboard_theme"] == "light"
    assert responses[-1][0] == 200 and responses[-1][1]["settings"]["dashboard_theme"] == "light"

    for bad in ("sepia", 1, None):
        handler._handle_settings_post({"dashboard_theme": bad})
        assert responses[-1] == (400, {"ok": False, "error": "dashboard_theme must be one of ['system', 'light', 'dark']"})
    assert len(written) == 1


def test_public_settings_report_the_theme(monkeypatch):
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    assert server._public_settings({"dashboard_theme": "dark"})["dashboard_theme"] == "dark"
    assert server._public_settings({"dashboard_theme": "neon"})["dashboard_theme"] == "system"


# ---- Theme: applied before the first paint ----------------------------------

BOOT = _between(DASHBOARD, '<script id="themeBoot">', "</script>")[len('<script id="themeBoot">'):]


def _boot(stored, throws=False):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    script = r"""
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const root = { dataset: {} };
const context = { document: { documentElement: root }, localStorage: { getItem: (key) => {
  if (input.throws) throw new Error('storage blocked');
  return key === 'uoink.dashboard.theme' ? input.stored : null;
} } };
vm.runInNewContext(input.boot, context);
process.stdout.write(JSON.stringify(root.dataset.theme || ''));
"""
    result = subprocess.run([node, "-e", script], input=json.dumps({"boot": BOOT, "stored": stored, "throws": throws}),
                            text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_boot_script_applies_the_cached_theme_before_the_styles():
    head = DASHBOARD[:DASHBOARD.index("<body")]
    assert head.index('<script id="themeBoot">') < head.index("<style>")
    # The main script stays the first bare <script> tag the other harnesses find.
    assert DASHBOARD.index("<script>") > DASHBOARD.index("</style>")
    assert _boot("dark") == "dark" and _boot("light") == "light"
    assert _boot("system") == "" and _boot(None) == "" and _boot("<b>") == ""
    assert _boot("dark", throws=True) == ""


def test_apply_theme_sets_data_theme_and_caches_it():
    result = run_js("""({
      dark: (applyDashboardTheme("dark"), [document.documentElement.dataset.theme, storage.get("uoink.dashboard.theme")]),
      light: (applyDashboardTheme("light"), [document.documentElement.dataset.theme, storage.get("uoink.dashboard.theme")]),
      system: (applyDashboardTheme("system"), ["theme" in document.documentElement.dataset, storage.get("uoink.dashboard.theme")]),
      junk: (applyDashboardTheme("purple"), ["theme" in document.documentElement.dataset, storage.get("uoink.dashboard.theme")]),
    })""")
    assert result == {"dark": ["dark", "dark"], "light": ["light", "light"],
                      "system": [False, "system"], "junk": [False, "system"]}
    # Blocked storage never stops the theme from applying.
    assert run_js('applyDashboardTheme("dark"), document.documentElement.dataset.theme', storageThrows=True) == "dark"


@pytest.mark.parametrize(("platform", "label"), [("Win32", "Match Windows"), ("MacIntel", "Match system"), ("Linux x86_64", "Match system")])
def test_system_option_names_the_platform(platform, label):
    assert run_js("""(() => {
      const option = getEl("themeSystemOption");
      document.querySelectorAll = (selector) => selector === "[data-theme-system]" ? [option] : [];
      renderDashboardThemeLabels();
      return option.textContent;
    })()""", platform=platform) == label


def test_startup_sync_takes_the_helpers_choice_unless_an_edit_is_pending():
    result = run_js("""(async () => {
      settingsRequest = async () => ({ ok: true, settings: { dashboard_theme: "dark" } });
      await syncDashboardTheme();
      const synced = [document.documentElement.dataset.theme, els.dashboardTheme.value, storage.get("uoink.dashboard.theme")];
      noteSettingEdit("dashboardTheme");
      settingsRequest = async () => ({ ok: true, settings: { dashboard_theme: "light" } });
      await syncDashboardTheme();
      const kept = document.documentElement.dataset.theme;
      return { synced, kept };
    })()""")
    assert result == {"synced": ["dark", "dark", "dark"], "kept": "dark"}
    # An older helper without the field leaves the cached theme alone.
    assert run_js("""(async () => {
      applyDashboardTheme("light");
      settingsRequest = async () => ({ ok: true, settings: {} });
      await syncDashboardTheme();
      return document.documentElement.dataset.theme;
    })()""") == "light"


def test_appearance_control_is_wired_to_the_helper_setting():
    block = _between(DASHBOARD, '<div class="setting-block" id="settings-appearance">', '<div class="setting-block" id="settings-helper">')
    assert "<h2>Appearance</h2>" in block
    for value, label in (("system", "Match Windows"), ("light", "Light"), ("dark", "Dark")):
        assert re.search(rf'<option value="{value}"[^>]*>{label}</option>', block), value
    assert 'id="dashboardThemeSaveStatus"' in block
    assert 'dashboardTheme: ["dashboard_theme", "system"],' in SCRIPT
    wiring = _between(SCRIPT, "      wireSettingsAutosave();", 'document.getElementById("testKey")')
    assert "renderDashboardThemeLabels();" in wiring
    assert 'els.dashboardTheme.addEventListener("change", () => applyDashboardTheme(els.dashboardTheme.value));' in wiring
    hydrate = _between(SCRIPT, "function hydrateSettings(data, versions)", "renderConnectedServices();")
    assert "applyDashboardTheme(els.dashboardTheme.value)" in hydrate
    init = _between(SCRIPT, "async function init()", "init().catch(")
    assert init.index("await loadLibraryFacets();") < init.index("syncDashboardTheme();")


# ---- Reader: Back stays in reach ----------------------------------------------

def test_back_row_is_a_sticky_child_of_the_reader_panel():
    reader = _between(DASHBOARD, '<section class="tab-panel reader" id="tab-yoink"', "</section>")
    nav = reader.index('<nav class="reader-crumbs" aria-label="Breadcrumb">')
    assert nav < reader.index('<div class="page-head reader-head">'), "the Back row is the panel's own child"
    assert '<button class="button ghost" type="button" id="yoinkBack">&larr; Back</button>' in reader[nav:]
    style = DASHBOARD[:DASHBOARD.index("</style>")]
    crumbs = _between(style, "    .reader-crumbs {", "}")
    for decl in ("position: sticky;", "top: 0;", "flex-wrap: nowrap;", "background: var(--bg);"):
        assert decl in crumbs, decl
    assert ".reader-crumbs.stuck {" in style
    assert "scroll-padding-top: 64px;" in _between(style, ".content:has(#tab-yoink.active),", "}")
    # Under 1080px the page scrolls; clip (not hidden) keeps every ancestor
    # from becoming a scroll container the sticky row would cling to.
    narrow = _between(style, "@media (max-width: 1080px) {", ".app {")
    assert "body { overflow: visible; }" in narrow
    assert "overflow-x: clip;" in narrow and "overflow-x: hidden;" not in narrow
    assert "overflow-y: visible;" in narrow


ESC = """(() => {
  let backs = 0;
  goBack = () => { backs += 1; };
  const press = (target = {}, extra = {}) => {
    const event = { key: "Escape", defaultPrevented: false, target, preventDefault() { this.defaultPrevented = true; }, ...extra };
    closeReaderOnEscape(event);
    return event.defaultPrevented;
  };
  const out = {};
  state.activeTab = "yoink";
  out.reader = [press(), backs];
  const field = { closest: (selector) => selector.includes("input") ? {} : null };
  out.field = [press(field), backs];
  out.handled = [press({}, { defaultPrevented: true }), backs];
  out.otherKey = (closeReaderOnEscape({ key: "Enter", target: {} }), backs);
  const menu = getEl("menu");
  menu.setAttribute("open", "");
  selectors["#tab-yoink details.action-menu[open]"] = menu;
  out.menu = [press(), backs, menu.hasAttribute("open")];
  delete selectors["#tab-yoink details.action-menu[open]"];
  selectors["dialog[open], .modal-backdrop:not(.hidden)"] = getEl("dialog");
  out.dialog = [press(), backs];
  delete selectors["dialog[open], .modal-backdrop:not(.hidden)"];
  state.activeTab = "library";
  out.library = [press(), backs];
  return out;
})()"""


def test_escape_closes_the_reader_unless_something_else_has_it():
    result = run_js(ESC)
    assert result["reader"] == [True, 1]
    assert result["field"] == [False, 1]
    assert result["handled"] == [True, 1]
    assert result["otherKey"] == 1
    assert result["menu"] == [False, 1, False], "Esc closes an open More actions menu first"
    assert result["dialog"] == [False, 1]
    assert result["library"] == [False, 1]
    routes = _between(SCRIPT, "function wireRoutes()", "function wireEvents()")
    assert 'document.addEventListener("keydown", closeReaderOnEscape);' in routes


SCROLL = """(() => {
  for (const name of ["loadLibraryActivity", "startLibraryActivityTimer", "stopLibraryActivityTimer",
    "renderYoinkDetail", "syncSidebarTopics", "markOpenLibraryRow", "refreshSettings", "renderSources",
    "refreshActivity", "loadWriting", "loadForYou", "loadEvidence"]) globalThis[name] = () => {};
  const out = {};
  state.activeTab = "library";
  content.scrollTop = 640;
  windowScroll.y = 120;
  switchTab("yoink", { fromRoute: true });
  out.reader = [content.scrollTop, windowScroll.y];
  content.scrollTop = 900;
  windowScroll.y = 300;
  switchTab("library", { fromRoute: true });
  out.back = [content.scrollTop, windowScroll.y];
  switchTab("settings", { fromRoute: true });
  switchTab("library", { fromRoute: true });
  out.fromSettings = [content.scrollTop, windowScroll.y];
  return out;
})()"""


def test_library_scroll_survives_a_trip_to_the_reader():
    result = run_js(SCROLL)
    assert result["reader"] == [0, 0], "the reader opens at its top"
    assert result["back"] == [640, 120], "back from the reader lands where the list was"
    assert result["fromSettings"] == [0, 0], "other screens still open at the top"


def test_browser_back_keeps_the_restored_scroll():
    # Back/Forward reach switchTab through popstate; with the browser's own
    # restore off, the Library position switchTab sets is the one that stays.
    assert run_js("wireRoutes(), window.history.scrollRestoration", history=True) == "manual"
    routes = _between(SCRIPT, "function wireRoutes()", "function wireEvents()")
    assert 'window.addEventListener("popstate", applyHashRoute);' in routes
    assert 'window.addEventListener("scroll", syncReaderCrumbs, { passive: true });' in routes
