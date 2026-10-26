"""Dashboard run-through fixes (3.11.2 new-user pass).

U1: a page that hits the allowlist wall offers "Allow <host>" on its row.
U2: Settings' site box saves on Enter, and a pasted link saves its host.
U3: health badges name the problem, open a drawer with Re-uoink, and only
    fixable problems flag; a saved article no longer reads "Done" beside
    "Needs attention".
U4: Clear filters hides with no filter; the Generate and Sources badges count
    the user's own drafts and subscriptions, so an empty library shows none.

The dashboard checks execute the product's own JavaScript in a Node vm with a
small fake DOM, the way tests/test_note_readiness_truth.py does.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

import index as index_mod
import page_extractor
import server

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const scriptCode = page.slice(page.indexOf('<script>') + 8, page.indexOf('    init().catch('));

function element(id) {
  const classes = new Set();
  return {
    id, value: '', disabled: false, textContent: '', innerHTML: '', title: '', dataset: {},
    attributes: {}, style: {}, open: false, focused: 0,
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
    querySelectorAll: () => [], querySelector: () => null, closest: () => null,
    addEventListener() {}, focus() { this.focused += 1; },
    showModal() { this.open = true; }, close() { this.open = false; },
  };
}

const elements = {};
const getEl = (id) => (elements[id] = elements[id] || element(id));
const context = {
  document: { getElementById: getEl, querySelector: () => null, querySelectorAll: () => [], activeElement: null },
  window: { addEventListener() {} },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  console, URL, Set, Map, Promise, JSON, Date,
  fetch: () => Promise.reject(new Error('network forbidden')),
  setTimeout: () => 0, clearTimeout: () => {},
  localStorage: { getItem: () => null, setItem() {} },
};
vm.createContext(context);
vm.runInContext(scriptCode + '\n;globalThis.state = state; globalThis.els = els;', context);
context.getEl = getEl;

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


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


# ---- U3: the helper only reports sections a source can have -------------------

@pytest.mark.parametrize("source_type", ["page", "x_article", "x_thread", "reddit_thread", "image"])
def test_text_sources_skip_transcript_screenshots_and_comments(source_type):
    health = server.compute_health({"source_type": source_type, "title": "Saved"})
    assert health == {"transcript": "skipped", "screenshots": "skipped", "comments": "skipped",
                      "hook": "skipped", "comment_intelligence": "skipped"}


def test_podcast_episode_keeps_its_transcript_check_only():
    assert server.compute_health({"source_type": "episode", "transcript": []})["transcript"] == "missing"
    health = server.compute_health({"source_type": "episode", "transcript": [{"text": "hi"}]})
    assert health["transcript"] == "ok"
    assert health["screenshots"] == health["comments"] == "skipped"


@pytest.mark.parametrize(("status", "expected"), [
    ("disabled", "disabled"), ("skipped", "skipped"), ("skipped_generic", "skipped"),
    ("pending", "pending"), ("unavailable", "missing"), (None, "missing"),
])
def test_video_comments_only_flag_when_a_fetch_failed(status, expected):
    sidecar = {"source_type": "video", "transcript": [1], "screenshots": [1], "comments": []}
    if status:
        sidecar["comments_status"] = status
    assert server.compute_health(sidecar)["comments"] == expected


def test_video_without_audio_is_not_a_missing_transcript():
    health = server.compute_health({"source_type": "video", "transcript": [], "screenshots": [1],
                                    "asr_fallback": {"status": "no_audio"}})
    assert health["transcript"] == "no audio"
    # Whisper ran and heard nothing to transcribe: music or silence.
    health = server.compute_health({"source_type": "video", "transcript": [], "screenshots": [1],
                                    "asr_fallback": {"status": "no_speech"}})
    assert health["transcript"] == "no speech"
    # Captions that are merely absent still flag: Re-uoink or local
    # transcription can fix those.
    health = server.compute_health({"source_type": "video", "transcript": [], "screenshots": [1],
                                    "asr_fallback": {"status": "disabled"}})
    assert health["transcript"] == "missing"


def test_music_only_video_reads_done_with_no_speech():
    shown = run_js("""
      const row = {video_id: "m1", source_type: "video", platform: "x", has_transcript: false,
                   transcript_source: null, asr_fallback_status: "no_speech",
                   health: {transcript: "no speech", screenshots: "ok", comments: "skipped"}};
      ({line: savedStateLine(row), badge: healthException(row.health, row),
        note: transcriptNoteText(row, {asr_fallback: {status: "no_speech", model: "base"}})})
    """)
    assert ">Done</span>" in shown["line"] and "no speech found" in shown["line"]
    assert shown["badge"] == ""
    assert "found no speech, so there is no transcript." in shown["note"]


def test_usage_card_leaves_a_gap_above_the_scrolling_content():
    rule = _between(DASHBOARD, ".main > #usageOptInCard {", "}")
    assert "margin: 24px 28px 12px;" in rule


@pytest.mark.parametrize("source_type", ["x_thread", "reddit_thread"])
def test_video_post_keeps_its_transcript_and_screenshot_checks(source_type):
    # The library fills in the index's source type, which names an X or Reddit
    # post with a video by its URL. The video path's sidecar still reports.
    video = {"source_type": source_type, "transcript": [], "transcript_source": None,
             "interval_seconds": 2, "screenshots": [], "comments_status": "disabled",
             "asr_fallback": {"status": "model_not_downloaded"}}
    health = server.compute_health(video)
    assert health["transcript"] == "missing" and health["screenshots"] == "missing"
    assert health["comments"] == "disabled"
    video["asr_fallback"] = {"status": "no_speech"}
    assert server.compute_health(video)["transcript"] == "no speech"
    # A text post saved by the page path still skips both.
    text = server.compute_health({"source_type": source_type, "title": "Saved",
                                  "screenshot_path": None})
    assert text["transcript"] == text["screenshots"] == "skipped"


def test_video_post_row_says_how_its_transcript_came_out():
    shown = run_js("""({
      noSpeech: savedRowDetail({source_type: "x_thread", platform: "x", has_transcript: false,
                                transcript_source: null, asr_fallback_status: "no_speech"}),
      whisper: savedRowDetail({source_type: "x_thread", platform: "x", has_transcript: true,
                               transcript_source: "asr", asr_fallback_status: "completed"}),
      text: savedRowDetail({source_type: "x_thread", platform: "x", has_transcript: false,
                            transcript_source: null, asr_fallback_status: null}),
      reddit: savedRowDetail({source_type: "reddit_thread", platform: "reddit", has_transcript: false}),
    })""")
    assert shown == {"noSpeech": "no speech found", "whisper": "transcript by Whisper",
                     "text": "post and thread", "reddit": "thread and comments"}


def test_generic_capture_has_no_screenshots_to_miss():
    health = server.compute_health({"extraction_mode": "generic", "transcript": [1], "screenshots": [],
                                    "comments_status": "skipped_generic"})
    assert health["screenshots"] == "skipped"
    assert health["comments"] == "skipped"


def test_saved_article_row_reads_done_without_a_badge(tmp_path):
    idx = index_mod.Index.open(tmp_path / "isolated.db")
    try:
        result = {"ok": True, "url": "https://www.example.com/post", "title": "An article",
                  "markdown": "Body text. " * 40, "metadata": {"title": "An article"},
                  "extraction_engine": "readability_stdlib", "extracted_at": "2026-10-26T00:00:00Z"}
        video_id = page_extractor.persist_page_yoink(idx, result, data_root=tmp_path / "out")
        row = server._enrich_yoink_rows(idx, [idx.get_yoink(video_id)])[0]
    finally:
        idx.close()
    assert row["source_type"] == "page"
    assert set(row["health"].values()) == {"skipped"}
    card = run_js(f"cardHtml({json.dumps(row)})")
    assert "data-health-open" not in card
    assert '<i class="state-dot" aria-hidden="true"></i>Done</span>' in card
    assert "Needs attention" not in card


# ---- U3: the badge, the state line and the drawer -----------------------------

def test_badge_names_the_problem():
    badges = run_js("""({
      one: healthException({transcript: "missing", screenshots: "ok", comments: "ok", hook: "completed", comment_intelligence: "fetched"}, {video_id: "v1", source_type: "video"}),
      many: healthException({transcript: "missing", comments: "missing", hook: "failed"}, {video_id: "v2"}),
      working: healthException({comments: "pending"}, {video_id: "v3"}),
      workingMany: healthException({comments: "pending", hook: "pending"}, {video_id: "v4"}),
      mixed: healthException({transcript: "missing", hook: "pending"}, {video_id: "v5"}),
      note: healthException({transcript: "missing"}, {video_id: "n1", source_type: "note"}),
      clean: healthException({transcript: "ok", screenshots: "skipped", comments: "disabled", hook: "skipped", comment_intelligence: "not_run"}, {video_id: "v6"}),
      noAudio: healthException({transcript: "no audio", screenshots: "ok", comments: "ok"}, {video_id: "v7"}),
      noSpeech: healthException({transcript: "no speech", screenshots: "ok", comments: "ok"}, {video_id: "v8"}),
    })""")
    one = badges["one"]
    assert one.startswith('<button class="health-exception fail" type="button" data-health-open="v1" aria-haspopup="dialog"')
    assert ">No transcript</button>" in one
    assert 'aria-label="Needs attention: No transcript. Show why"' in one
    assert ">3 issues</button>" in badges["many"]
    assert 'class="health-exception warn"' in badges["working"] and ">Comments pending</button>" in badges["working"]
    assert ">2 steps pending</button>" in badges["workingMany"]
    # A failure outranks a step still running; the drawer lists both.
    assert ">No transcript</button>" in badges["mixed"] and "health-exception fail" in badges["mixed"]
    assert ">No text</button>" in badges["note"]
    assert badges["clean"] == "" and badges["noAudio"] == "" and badges["noSpeech"] == ""


def test_done_never_sits_beside_a_problem():
    lines = run_js("""({
      problem: savedStateLine({source_type: "video", has_transcript: false, health: {transcript: "missing"}}),
      working: savedStateLine({source_type: "video", transcript_source: "captions", health: {comments: "pending"}}),
      healthy: savedStateLine({source_type: "page", health: {transcript: "skipped"}}),
    })""")
    for key in ("problem", "working"):
        assert ">Saved</span>" in lines[key] and "state-word done" not in lines[key]
    assert '<span class="state-word done"><i class="state-dot" aria-hidden="true"></i>Done</span>' in lines["healthy"]


def test_health_drawer_says_why_and_reuoinks_the_same_link():
    result = run_js("""(() => {
      const video = {video_id: "v1", title: "A video", source_type: "video", source_url: "https://www.youtube.com/watch?v=abc",
        asr_fallback_status: "disabled", health: {transcript: "missing", comments: "missing"}};
      const note = {video_id: "n1", title: "A note", source_type: "note", health: {transcript: "missing"}};
      const busy = {video_id: "v2", title: "Busy", source_type: "video", source_url: "https://youtu.be/x", health: {comments: "pending"}};
      state.library = [video, note, busy];
      const retried = [];
      retryLibraryCapture = (url, key) => retried.push([url, key || ""]);
      const out = {};
      openItemHealth("v1", null);
      out.video = {
        open: els.itemHealthDrawer.open,
        label: getEl("itemHealthLabel").textContent,
        issues: getEl("itemHealthIssues").innerHTML,
        reuoinkHidden: getEl("reuoinkItemHealth").classList.contains("hidden"),
        note: getEl("itemHealthNote").textContent,
      };
      reuoinkFromItemHealth();
      out.retried = retried;
      out.closedAfterReuoink = !els.itemHealthDrawer.open;
      openItemHealth("n1", null);
      out.noteReuoinkHidden = getEl("reuoinkItemHealth").classList.contains("hidden");
      closeItemHealth();
      openItemHealth("v2", null);
      out.busy = {label: getEl("itemHealthLabel").textContent, reuoinkHidden: getEl("reuoinkItemHealth").classList.contains("hidden")};
      closeItemHealth();
      openItemHealth("gone", null);
      out.unknownStaysClosed = !els.itemHealthDrawer.open;
      return out;
    })()""")
    video = result["video"]
    assert video["open"] is True
    assert video["label"] == "Needs attention"
    assert "<strong>No transcript</strong>" in video["issues"] and "<strong>Comments failed</strong>" in video["issues"]
    assert "local transcription is turned off" in video["issues"]
    assert video["reuoinkHidden"] is False
    assert "refreshes this item in place" in video["note"]
    assert result["retried"] == [["https://www.youtube.com/watch?v=abc", ""]]
    assert result["closedAfterReuoink"] is True
    assert result["noteReuoinkHidden"] is True
    assert result["busy"] == {"label": "Still working", "reuoinkHidden": True}
    assert result["unknownStaysClosed"] is True


def test_badge_click_opens_the_drawer_before_the_card_opens_the_reader():
    handler = _between(DASHBOARD, 'const hookExplain = event.target.closest("[data-hook-explain]");',
                       'const card = event.target.closest("[data-folder]");')
    assert 'const healthOpen = event.target.closest("[data-health-open]");' in handler
    assert 'openItemHealth(healthOpen.dataset.healthOpen || "", healthOpen);' in handler
    markup = _between(DASHBOARD, '<dialog class="activity-drawer" id="itemHealthDrawer"', "</dialog>")
    for marker in ('id="itemHealthTitle" tabindex="-1"', 'id="itemHealthIssues"',
                   'id="reuoinkItemHealth">Re-uoink</button>', 'id="closeItemHealth">Close</button>'):
        assert marker in markup
    assert 'document.getElementById("reuoinkItemHealth").addEventListener("click", reuoinkFromItemHealth);' in DASHBOARD
    assert "trapModalFocus(event, els.itemHealthDrawer, closeItemHealth);" in DASHBOARD


# ---- U1: Allow <host> from the failed row ------------------------------------

ALLOW_SETUP = """
      const calls = [];
      authFetch = async (path, opts = {}) => {
        calls.push([path, opts.method || "GET", opts.body ? JSON.parse(opts.body) : null]);
        if (globalThis.failAdd && opts.method === "POST") { const err = new Error("allowlist write failed"); err.data = {}; throw err; }
        return path === "/extract/page/allowlist" && !opts.method ? {ok: true, sites: []} : {ok: true};
      };
      refreshActivity = () => {};
      const retried = [];
      retryLibraryCapture = (url, key) => retried.push([url, key]);
      const run = {id: "run1", url: "https://www.example.com/post", label: "Article / web page", state: "running",
        startedAt: new Date().toISOString(), jobIdsAtStart: new Set(), jobId: "", ref: ""};
      state.libraryRuns = [run];
      failLibraryRun(run, {data: {ok: false, code: "host_not_allowed",
        error: "host 'www.example.com' is not in the allowlist. Add it via /extract/page/allowlist or the Sites Settings panel."}});
      const row = libraryCaptureItems().find((item) => item.key === "run1");
"""


def test_allowlist_wall_row_offers_allow_host_then_recaptures():
    result = run_js("(async () => {" + ALLOW_SETUP + """
      await allowLibraryRunSite("run1", null);
      return {actions: row.actions, detail: row.detail, calls, retried};
    })()""")
    assert '<button class="button" type="button" data-library-allow-site="run1">Allow www.example.com</button>' in result["actions"]
    assert "data-library-retry" not in result["actions"]
    assert "data-library-dismiss" in result["actions"]
    assert result["detail"] == "That site isn't on your allowed pages list yet. Allow it to capture this page."
    # The same call Settings' Add makes, then the Settings list reloads.
    assert result["calls"][0] == ["/extract/page/allowlist", "POST", {"action": "add", "url_pattern": "www.example.com"}]
    assert ["/extract/page/allowlist", "GET", None] in result["calls"]
    assert result["retried"] == [["https://www.example.com/post", "run1"]]


def test_allow_host_failure_keeps_the_row_and_says_so():
    result = run_js("(async () => { globalThis.failAdd = true;" + ALLOW_SETUP + """
      await allowLibraryRunSite("run1", null);
      return {retried, note: els.libraryCaptureNote.textContent, runs: state.libraryRuns.length};
    })()""")
    assert result["retried"] == []
    assert result["runs"] == 1
    assert result["note"].startswith("Couldn't allow www.example.com: allowlist write failed")


def test_row_click_routes_allow_before_retry():
    handler = _between(DASHBOARD, 'const libraryAllow = event.target.closest("[data-library-allow-site]");',
                       'const libraryRetry = event.target.closest("[data-library-retry]");')
    assert 'allowLibraryRunSite(libraryAllow.dataset.libraryAllowSite || "", libraryAllow);' in handler


# ---- U2: Settings' site box ---------------------------------------------------

def test_site_box_saves_hosts_from_links_and_keeps_patterns():
    result = run_js("""(async () => {
      const calls = [];
      authFetch = async (path, opts = {}) => {
        calls.push([path, opts.method || "GET", opts.body ? JSON.parse(opts.body) : null]);
        return {ok: true, sites: []};
      };
      const patterns = ["https://Docs.Example.org/guide?x=1", "example.com/path", "*.docs.example.com", "  news.example.net  ", ""]
        .map(allowedSitePatternFrom);
      els.allowedSitePattern.value = "https://www.example.com/a/b";
      await addAllowedSite();
      return {patterns, calls, value: els.allowedSitePattern.value,
        status: getEl("allowedSitePatternSaveStatus").textContent};
    })()""")
    assert result["patterns"] == ["docs.example.org", "example.com", "*.docs.example.com", "news.example.net", ""]
    assert result["calls"][0] == ["/extract/page/allowlist", "POST", {"action": "add", "url_pattern": "www.example.com"}]
    assert result["value"] == ""


def test_site_box_submits_on_enter():
    wiring = _between(DASHBOARD, 'document.getElementById("addAllowedSite").addEventListener("click", addAllowedSite);',
                      "els.writingShowWarnings.addEventListener")
    assert 'els.allowedSitePattern.addEventListener("keydown", (event) => {' in wiring
    assert 'if (event.key !== "Enter" || event.isComposing) return;' in wiring
    assert "addAllowedSite();" in wiring
    assert 'id="allowedSitePattern" type="text" placeholder="example.com or *.docs.example.com"' in DASHBOARD


# ---- U4: Clear filters and the nav badges --------------------------------------

def test_clear_filters_shows_only_while_a_filter_is_on():
    result = run_js("""(() => {
      const seen = {};
      renderLibraryFilterChips();
      seen.none = els.clearFilters.classList.contains("hidden");
      state.filters.kind = "videos";
      renderLibraryFilterChips();
      seen.kind = els.clearFilters.classList.contains("hidden");
      state.filters.kind = "";
      state.filters.topic = "AI";
      renderLibraryFilterChips();
      seen.topic = els.clearFilters.classList.contains("hidden");
      state.filters.topic = "";
      state.filters.sort = "oldest";
      renderLibraryFilterChips();
      seen.sortOnly = els.clearFilters.classList.contains("hidden");
      return seen;
    })()""")
    assert result == {"none": True, "kind": False, "topic": False, "sortOnly": True}
    assert '<button class="button ghost hidden" type="button" id="clearFilters">Clear filters</button>' in DASHBOARD


def test_sources_badge_counts_subscriptions_and_hides_at_zero():
    result = run_js("""(async () => {
      const out = {};
      callRegistryTool = async () => ({sources: []});
      await loadStandingSubscriptions();
      out.empty = {hidden: els.sourcesNavCount.classList.contains("hidden"), text: els.sourcesNavCount.textContent};
      callRegistryTool = async () => ({sources: [
        {source_id: "s1", kind: "podcast_rss", display_name: "One", consent_state: "off"},
        {source_id: "s2", kind: "youtube_channel", display_name: "Two", consent_state: "on"}]});
      await loadStandingSubscriptions();
      out.two = {hidden: els.sourcesNavCount.classList.contains("hidden"), text: els.sourcesNavCount.textContent,
        title: els.sourcesNavCount.title};
      return out;
    })()""")
    assert result["empty"] == {"hidden": True, "text": ""}
    assert result["two"] == {"hidden": False, "text": "2", "title": "2 subscribed sources"}


def test_generate_badge_counts_saved_drafts_not_seeded_anchors():
    writing = _between(DASHBOARD, "    async function loadWriting() {", "      renderSuggestionDatalists();")
    assert "state.styleAnchors.length" not in writing
    assert 'setSidebarBadge(els.writingNavCount, state.writingPieces.length, "saved drafts", { hideWhenZero: true });' in writing
    for badge in ('id="writingNavCount" title="0 saved drafts"', 'id="sourcesNavCount" title="0 subscribed sources"'):
        assert f'<span class="nav-count hidden" {badge}' in DASHBOARD
