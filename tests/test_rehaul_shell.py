"""UI re-haul: the dashboard shell (SPEC "Dashboard IA").

Nav (5): Library, Activity (badge "N failed" when > 0), Generate, Sources,
Settings. The helper status sits at the bottom of the sidebar ("Running on
this PC" with a dot; offline says what to do on this OS). About and Star on
GitHub moved into Settings > App > About, Stop Uoink into Settings > App with
its confirm. The dead Build/Script panels and the hidden Features tab are
gone. Hash routes: #library, #item/<id>, #activity, #generate, #sources,
#settings/<section>, and Back works.

The static checks below read assets/dashboard/index.html. The behaviour runs
in tests/js/rehaul_shell_test.mjs, which loads the REAL dashboard script
(everything before init()) into a node:vm context over a fake page built
from the markup, with a fake window.history that records pushState and fires
popstate/hashchange on Back and Forward:

  routes  -- every SPEC route and older link names one screen and hash
  history -- one history entry per move; Back/Forward re-show screens
             without new entries; #item/<id> and #settings/<section> open on
             load; the item view's Back uses history.back() or goes to
             Library from a fresh deep link
  deeplink -- a fresh #item/<id> looks its saved Library row up first
             (folder, topic): by its title when it is older, however many
             items share it, else by reading Library to the end; the
             helper's "no item under this id" settles a missing one; a
             failed page, a shrinking Library or a lasting rate limit is
             "couldn't open", never "not found"; a 429 waits and carries
             on; every action stays off; moving elsewhere meanwhile wins
  links   -- in-app hash links push once; "#", unknown hashes and
             ctrl-clicks are left to the browser
  badge   -- "N failed" counts failed jobs plus failed queue rows (one per
             video, cancelled excluded) and hides at zero
  status  -- "Running on this PC/Mac/computer"; offline copy per OS (the
             Start menu on Windows; Mac and Linux, where no build ships,
             name the source run)

No network: fetch is a stub inside the harness.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
MARKUP = DASHBOARD.split("<script>", 1)[0]
SCRIPT = DASHBOARD.split("<script>", 1)[1]
CSS = DASHBOARD.split("<style>", 1)[1].split("</style>", 1)[0]
HARNESS = ROOT / "tests" / "js" / "rehaul_shell_test.mjs"

SECTIONS = [
    ("capture", "Capture"),
    ("ai", "AI features"),
    ("library", "Library and export"),
    ("agents", "Agents (MCP)"),
    ("app", "App"),
]


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"marker missing: {start}"
    body = text.split(start, 1)[1]
    assert end in body, f"end marker missing after {start}: {end}"
    return body.split(end, 1)[0]


def _panel(name: str) -> str:
    """The markup of one tab panel, up to its own closing </section>."""
    match = re.search(rf'<section\b[^>]*\bdata-tab-panel="{re.escape(name)}"[^>]*>', MARKUP)
    assert match, f"no {name} panel"
    depth = 0
    for tag in re.finditer(r"</?section\b", MARKUP[match.start():]):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return MARKUP[match.start():match.start() + tag.start()]
    raise AssertionError(f"the {name} panel never closes")


def _sidebar() -> str:
    return _between(MARKUP, '<aside class="sidebar"', "</aside>")


def _settings_section(key: str) -> str:
    return _between(_panel("settings"), f'id="settings-{key}"', "</section>")


def test_nav_is_the_five_spec_items_in_order():
    nav = _between(MARKUP, '<nav class="nav" aria-label="Sections">', "</nav>")
    buttons = re.findall(
        r'<button class="nav-button[^"]*" type="button" data-tab-button="([^"]+)" data-nav-label="([^"]+)"', nav)
    assert buttons == [
        ("library", "Library"),
        ("activity", "Activity"),
        ("writing", "Generate"),
        ("sources", "Sources"),
        ("settings", "Settings"),
    ], buttons
    assert nav.count("<button") == 5
    # Library opens first and says so to assistive tech too.
    assert 'data-tab-button="library" data-nav-label="Library" aria-current="page"' in nav
    # The nav is the only tab switcher left (About, For You and the sidebar
    # Activity button are gone from it).
    assert MARKUP.count("data-tab-button=") == 5
    assert 'btn.addEventListener("click", () => switchTab(btn.dataset.tabButton))' in SCRIPT
    switch = _between(SCRIPT, "function switchTab(tab, options = {})", "function applyRoute(route)")
    assert 'btn.setAttribute("aria-current", "page")' in switch
    assert 'btn.removeAttribute("aria-current")' in switch


def test_activity_nav_item_says_how_many_failed():
    activity = re.search(r'<button[^>]*data-tab-button="activity".*?</button>', MARKUP, re.S).group(0)
    assert '<span class="nav-failed hidden" id="activityFailedBadge"></span>' in activity
    assert 'id="activityNavCount"' in activity
    badge = _between(SCRIPT, "function setActivityFailedBadge(count)", "function setLibraryEmptyState(")
    assert "`${failed} failed`" in badge
    assert 'el.classList.toggle("hidden", failed === 0)' in badge
    assert 'button.setAttribute("aria-label", failed ? `${base}, ${failed} failed` : base)' in badge
    render = _between(SCRIPT, "function renderQueue(data)", "function completedTodayRows()")
    assert ('setActivityFailedBadge(failedJobs.filter((job) => normalizedStatus(job) === "failed").length'
            " + queueFailedDeduped.length)") in render
    # The word carries the state; the badge text uses the small-text accent
    # and its outline the --fail token (status is never colour alone).
    rule = _between(CSS, ".nav-failed {", "}")
    assert "color: var(--rust-bright);" in rule
    assert "border: 1px solid var(--fail);" in rule


def test_helper_status_sits_at_the_bottom_with_os_copy():
    sidebar = _sidebar()
    bottom = _between(sidebar, '<div class="sidebar-bottom">', "</div>\n      </div>")
    assert '<div class="helper-status" id="runningPill" role="status">' in bottom
    assert '<span class="pip" aria-hidden="true"></span><span id="helperStatusText">' in bottom
    assert '<span class="helper-status-fix hidden" id="helperOfflineFix"></span>' in bottom
    copy = _between(SCRIPT, "const HELPER_STATUS_COPY = {", "function helperPlatform()")
    for phrase in (
        '"Running on this PC"',
        '"Running on this Mac"',
        '"Running on this computer"',
        "Start Uoink from the Start menu.",
    ):
        assert phrase in copy, phrase
    # Only Windows ships a launcher (docs/mac-install.md: no Mac build, no
    # Uoink.app), so Mac and Linux offline copy names the source run and
    # never sends people to an app or command that does not exist.
    source_fix = _between(SCRIPT, "const HELPER_SOURCE_FIX = ", ";\n")
    assert "Uoink ships for Windows only." in source_fix
    assert "start python server.py again." in source_fix
    assert copy.count("fix: HELPER_SOURCE_FIX,") == 2
    for wrong in ("Applications", "uoink-helper"):
        assert wrong not in copy and wrong not in source_fix, wrong
    # About, Star on GitHub and Stop Uoink left the sidebar for Settings.
    for gone in ("Stop Uoink", "Star on GitHub", "About", "More controls", "Private local app"):
        assert gone not in sidebar, gone
    # The status dot does not pulse: only the reader, toasts and the step
    # strip move (SPEC motion).
    for rule in (".helper-status .pip {", ".helper-status.online .pip {", ".helper-status.offline .pip {"):
        assert "animation" not in _between(CSS, rule, "}")
    assert ".running-pill" not in CSS


def test_about_star_and_stop_live_in_settings_app():
    app = _settings_section("app")
    assert 'id="settings-helper"' in app and "<h2>Local app</h2>" in app
    assert '<button class="button danger" type="button" id="stopHelperSettings">Stop Uoink</button>' in app
    assert 'id="settings-about"' in app and "<h2>About Uoink</h2>" in app
    assert '<button class="button" type="button" id="starGithub">Star on GitHub</button>' in app
    for marker in ('id="aboutVersion"', 'id="librarianStatus"', 'id="aboutPort"', "Advanced: local address",
                   'id="versionLine"', 'id="checkUpdates"'):
        assert marker in app, marker
    for link in ('href="/splash"', "https://uoink.app/how", "https://uoink.app/hooks",
                 "https://uoink.app/agents", "https://github.com/ryanbiddy/uoink/blob/main/CHANGELOG.md",
                 "https://github.com/ryanbiddy/uoink/releases", "https://github.com/ryanbiddy/uoink/issues",
                 "https://uoink.app/privacy"):
        assert link in app, link
    # Stop keeps its confirm dialog; Star still opens the repository.
    assert 'getElementById("stopHelperSettings").addEventListener("click", stopHelperWithConfirm)' in SCRIPT
    assert "focusFirstIn(els.stopHelperConfirm, els.cancelStopHelper);" in _between(
        SCRIPT, "function openStopHelperConfirm(trigger)", "function closeStopHelperConfirm()")
    assert 'postHelper("/helper/quit")' in _between(
        SCRIPT, "function confirmStopHelper()", "function stopHelperWithConfirm(")
    assert 'id="stopHelperConfirm" role="dialog" aria-modal="true"' in DASHBOARD
    assert ('getElementById("starGithub").addEventListener("click", () => '
            'openExternal("https://github.com/ryanbiddy/uoink"))') in SCRIPT
    # No emoji in the re-hauled controls.
    assert "⭐" not in DASHBOARD


def test_settings_has_the_five_spec_sections_in_order():
    settings = _panel("settings")
    index = _between(settings, '<nav class="settings-index" aria-label="Settings sections">', "</nav>")
    assert re.findall(r'<a href="#settings/([a-z]+)">([^<]+)</a>', index) == SECTIONS
    positions = [settings.index(f'id="settings-{key}"') for key, _title in SECTIONS]
    assert positions == sorted(positions)
    for key, title in SECTIONS:
        heading = re.search(
            rf'<section class="settings-section" id="settings-{key}" aria-labelledby="([^"]+)">\s*'
            r'<h2 class="settings-section-title" id="\1" tabindex="-1">([^<]+)</h2>', settings)
        assert heading and heading.group(2) == title, key
    blocks = {
        "capture": ("Auto-uoink playlists", "Taste-aware auto-uoink", "Podcast feeds", "Sites Uoink works on",
                    "Clipboard screenshots", "Transcript checker"),
        "ai": ("AI writing key", "Claim verification", "Entity extraction", "Writing Studio"),
        "library": ("Output folder", "Library Mirror", "Topics", "Your role", "Your channels"),
        "agents": ("Agent connection",),
        "app": ("Local app", "Updates", "About Uoink", "Help and releases"),
    }
    for key, titles in blocks.items():
        section = _settings_section(key)
        for title in titles:
            assert f"<h2>{title}</h2>" in section, (key, title)
            assert settings.count(f"<h2>{title}</h2>") == 1, title


def test_every_settings_control_is_still_in_settings():
    settings = _panel("settings")
    for control in (
        "anthropicKey", "saveKey", "testKey", "stopHelperSettings", "autostartToggle", "notificationsEnabled",
        "rolePicker", "channelHandle", "addChannel", "recognizeChannels", "playlistUrl", "addPlaylist",
        "autoUoinkToggle", "autoUoinkScan", "podcastFeedUrl", "addPodcastFeed", "podcastAutoIngest",
        "allowedSitePattern", "addAllowedSite", "pickOutputFolder", "openOutput", "outputFolder", "saveOutput",
        "libraryMirrorDestination", "libraryMirrorScope", "libraryMirrorAllowlist", "libraryMirrorPreview",
        "libraryMirrorEnable", "libraryMirrorDisable", "libraryMirrorResync", "topicList", "addTopic",
        "saveTopics", "undoTopicRemove", "settingsAgentSetupCard", "mcpConfig", "copyMcp", "versionLine",
        "checkUpdates", "screenshotCount", "saveScreenshotCount", "claimVerificationToggle",
        "entityExtractionToggle", "voiceWarningsEnabled", "voiceWarningsPerGeneration",
        "writingScreenshotPickerToggle", "reliabilityAutoCheck", "asrFallbackEnabled", "whisperModel",
        "saveWhisperModel", "downloadReliabilityModel", "aboutVersion", "aboutPort", "librarianStatus",
        "starGithub",
    ):
        assert settings.count(f'id="{control}"') == 1, control
        assert DASHBOARD.count(f'id="{control}"') == 1, control


def test_dead_panels_and_the_features_tab_are_gone():
    for name in ("build", "script", "features", "about"):
        assert f'data-tab-panel="{name}"' not in DASHBOARD, name
        assert f'data-tab-button="{name}"' not in DASHBOARD, name
    for gone in ('id="workspaceForm"', 'id="scriptForm"', 'id="featureRows"', 'id="sidebarControls"',
                 "function loadBuild(", "function loadScripts(", "function loadFeatures(",
                 "function syncSidebarControlsDensity(", "FALLBACK_FEATURES"):
        assert gone not in DASHBOARD, gone
    # Nothing reaches for uoink.app's feature manifest, on load or later, and
    # the page fetches nothing remote by itself.
    assert "features-manifest" not in DASHBOARD
    assert not re.search(r"fetch\(\s*[\"'`]https?://", SCRIPT)
    init = _between(SCRIPT, "async function init()", "init().catch(")
    assert "loadFeatures" not in init
    # Generate's script mode no longer reads the removed Script Studio form.
    normalize = _between(SCRIPT, "function normalizeScriptDraft(payload, request = {})", "function evidenceStatusChip(")
    assert "els.script" not in normalize
    assert "normalizeScriptDraft(agentDraft, body)" in SCRIPT


def test_hash_routes_and_back_are_wired():
    tabs = _between(SCRIPT, "const ROUTE_TABS = {", "};")
    for head, tab in (("library", "library"), ("activity", "activity"), ("generate", "writing"),
                      ("sources", "sources"), ("settings", "settings")):
        assert f'{head}: "{tab}",' in tabs, head
    parse = _between(SCRIPT, "function parseRoute(hash)", "function routeForTab(")
    assert 'if (head === "item")' in parse and 'if (head === "settings")' in parse
    init = _between(SCRIPT, "async function init()", "init().catch(")
    assert init.index("wireRoutes();") < init.index("applyHashRoute();")
    wire = _between(SCRIPT, "function wireRoutes()", "function wireEvents()")
    assert 'window.addEventListener("hashchange", applyHashRoute);' in wire
    assert 'window.addEventListener("popstate", applyHashRoute);' in wire
    assert "target.closest('a[href^=\"#\"]')" in wire
    assert 'els.yoinkBack.addEventListener("click", goBack);' in wire
    assert 'hist.pushState({ uoinkDepth: historyDepth() + 1 }, "", hash);' in SCRIPT
    opener = _between(SCRIPT, "async function openYoinkDetail(row, options = {})", "async function requestRetranscription()")
    assert 'switchTab("yoink", { fromRoute: Boolean(options && options.fromRoute) });' in opener
    # A fresh #item/<id> looks its saved Library row up before the item
    # renders (never an id-only stand-in with no folder or topic).
    apply = _between(SCRIPT, "function applyRoute(route)", "function applyHashRoute()")
    assert "const row = knownLibraryRow(route.id);" in apply
    assert "else openItemFromRoute(route.id);" in apply
    lookup = _between(SCRIPT, "async function openItemFromRoute(id)", "async function openYoinkDetail(")
    assert "const wanted = () => state.selectedYoinkRequest === request && currentRoute === hash;" in lookup
    assert "row = await findLibraryRow(id, wanted);" in lookup
    assert "if (!wanted()) return;" in lookup
    assert '<button class="button ghost" type="button" id="yoinkBack">&larr; Back</button>' in _panel("yoink")
    # Generate can name a mode (#generate/<mode>): research playbooks add
    # theirs beside a mode picker later.
    assert 'const GENERATE_MODES = ["write"];' in SCRIPT
    assert 'data-tab-panel="writing"' in MARKUP
    # D13: Sources' "View in Activity" link names the Activity route.
    assert 'href="#activity"' in SCRIPT
    assert 'href="#tab-activity"' not in DASHBOARD


def test_item_lookup_never_reads_a_partial_search_as_not_found():
    # Review finding: a page bound (the newest 2,000 rows, the first 50
    # title matches) made an older item with a common title read as "not
    # found". Absence now comes only from the helper's answer for the id or
    # from reading every page; anything short of that is an error.
    assert "ITEM_LOOKUP_PAGES" not in SCRIPT
    find = _between(SCRIPT, "async function findLibraryRow(id, wanted = () => true)", "async function openItemFromRoute(id)")
    assert "if (itemNotSaved(err)) return null;" in find
    assert "const byTitle = await scanLibraryFor(id, { q: title }, 0, wanted);" in find
    assert "return scanLibraryFor(id, {}, ITEM_LOOKUP_PAGE, wanted, first.total);" in find
    # A short page is not the end (Library leaves out rows it cannot show).
    assert "first.rows.length" not in find and "limit: 50" not in find
    scan = _between(SCRIPT, "async function scanLibraryFor(id, params, offset, wanted, total = null)", "function itemNotSaved(err)")
    assert "offset += ITEM_LOOKUP_PAGE;" in scan and "if (offset >= total) return null;" in scan
    assert 'throw new Error("Library changed during the lookup");' in scan
    not_saved = _between(SCRIPT, "function itemNotSaved(err)", "async function findLibraryRow(")
    assert 'err.data.error === "uoink not found"' in not_saved and "!err.data.state" in not_saved
    page = _between(SCRIPT, "async function itemLookupPage(params, wanted)", "async function scanLibraryFor(")
    assert "err.status !== 429 || attempt >= ITEM_LOOKUP_RETRIES" in page
    assert "setTimeout(resolve, ITEM_LOOKUP_RETRY_MS)" in page
    # Only an id the helper's index has no row for reads as "uoink not found".
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    details = _between(server, "def _handle_yoink_details(self, bare: str):", "sidecar_raw = ")
    assert 'row = _get_index().get_yoink(video_id)' in details
    assert '"error": "uoink not found"' in details


def test_panels_without_a_nav_item_stay_reachable():
    library = _panel("library")
    assert ('<a class="route-link" href="#for-you" data-nav-label="For You">For You '
            '<span class="nav-count" id="forYouNavCount"') in library
    for name in ("for-you", "evidence", "yoink", "sources", "writing", "activity"):
        assert f'data-tab-panel="{name}"' in MARKUP, name
    assert 'const NAV_OWNER = { yoink: "library", evidence: "library", "for-you": "library" };' in SCRIPT
    # setSidebarBadge names the For You link as it names nav buttons.
    assert 'const button = el.closest("button, a");' in SCRIPT


GROUPS = ["routes", "history", "deeplink", "links", "badge", "status"]


@pytest.mark.parametrize("group", GROUPS)
def test_shell_behaviour(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 5, output
