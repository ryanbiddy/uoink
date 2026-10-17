"""UI re-haul: Library (search-or-paste, type chips, list rows) and the Reader.

SPEC "Library": one box, "Search your library or paste a link to uoink it"
(a link starts a capture through the existing capture API, playlist links
included; other text searches, keeping D1's sequencing); type chips All,
Videos, Posts, Notes, Podcasts; a topic list with counts in the sidebar; one
sort control; list rows with the real thumbnail and one state line; the
Reader with a breadcrumb, H1 title, meta and "watch on source", actions, the
Whisper / missing-captions note, the whole transcript as paragraphs with
times in a 44px gutter and screenshots at their times, comments and AI
analysis collapsible below, deep link #item/<id>; "Library activity" moves
into a collapsed Insights section below the list.

Three kinds of check:
  * the markup and stylesheet of assets/dashboard/index.html;
  * server.py's /memory/search (type groups and an order over every match)
    and /yoinks/<id>/details (the Reader's fields, bounded) over a
    throwaway index;
  * tests/js/rehaul_library_reader_test.mjs, which runs the REAL dashboard
    script in a node:vm context (groups paste, kinds, rows, reader, split,
    live, saves, reconcile, retry, errors).
"""
from __future__ import annotations

import contextlib
import json
import re
import subprocess
from pathlib import Path

import pytest

import index as index_mod
import server

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
SCRIPT = DASHBOARD[DASHBOARD.index("<script>"):]
MARKUP = DASHBOARD[:DASHBOARD.index("<script>")]
STYLE_RAW = DASHBOARD[DASHBOARD.index("<style>"):DASHBOARD.index("</style>")]
STYLE = re.sub(r"/\*.*?\*/", "", STYLE_RAW, flags=re.S)
HARNESS = ROOT / "tests" / "js" / "rehaul_library_reader_test.mjs"


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"marker missing: {start}"
    head = text.index(start)
    assert end in text[head:], f"marker missing after {start!r}: {end}"
    return text[head:text.index(end, head)]


def _panel(name: str) -> str:
    """One tab panel's markup, up to its own closing </section>."""
    match = re.search(rf'<section\b[^>]*\bdata-tab-panel="{re.escape(name)}"[^>]*>', MARKUP)
    assert match, f"no {name} panel"
    depth, pos = 0, match.start()
    for tag in re.finditer(r"</?section\b", MARKUP[pos:]):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return MARKUP[pos:pos + tag.start()]
    raise AssertionError(f"{name} panel never closes")


def _rule(selector: str) -> str:
    match = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", STYLE)
    assert match, f"no CSS rule for {selector}"
    return match.group(1)


# ---- Library markup -----------------------------------------------------------

def test_library_opens_on_one_search_or_paste_box():
    library = _panel("library")
    box = ('<input class="control" id="searchInput" type="search" '
           'placeholder="Search your library or paste a link to uoink it" '
           'aria-label="Search your library or paste a link to uoink it"')
    assert box in library
    assert library.count('type="search"') == 1, "Library has one box"
    assert 'id="libraryCaptureButton"' in library
    assert re.search(r'id="libraryCaptureNote" role="status" aria-live="polite"', library)
    # The box comes first: nothing analytical sits above it.
    assert library.index('id="searchInput"') < library.index('id="libraryGrid"') < library.index('id="libraryInsights"')
    assert library.index('id="searchInput"') < library.index('id="libraryActivityPanel"')
    # Sources keeps its own paste box; the Library box is a separate control.
    assert 'id="universalCaptureInput"' not in library


def test_type_chips_are_all_videos_posts_notes_podcasts():
    library = _panel("library")
    chips = re.findall(r'<button class="kind-chip" type="button" data-library-kind="([^"]*)" aria-pressed="(true|false)">([^<]+)</button>', library)
    assert [(kind, label) for kind, _, label in chips] == [
        ("", "All"), ("videos", "Videos"), ("posts", "Posts"), ("notes", "Notes"), ("podcasts", "Podcasts")]
    assert [pressed for _, pressed, _ in chips] == ["true", "false", "false", "false", "false"]
    assert 'id="libraryKinds" role="group"' in library
    # The helper groups source types the same way.
    assert server._LIBRARY_KINDS == {
        "videos": ("video", "short_video"),
        "posts": ("x_thread", "x_article", "reddit_thread", "page"),
        "notes": ("note", "image"),
        "podcasts": ("episode",),
    }


def test_sort_is_one_control_answered_by_the_helper():
    library = _panel("library")
    sort = re.search(r'<select class="control" id="sortFilter" aria-label="Sort Library">(.*?)</select>', library, re.S)
    assert sort, "one sort control"
    assert re.findall(r'<option value="([^"]+)">', sort.group(1)) == ["newest", "oldest", "title", "relevance"]
    assert library.count('aria-label="Sort Library"') == 1
    params = _between(SCRIPT, "function paramsFromFilters(extra = {})", "function hasLibraryFilters()")
    assert 'params.set("sort", state.filters.sort || "newest");' in params
    assert 'if (state.filters.kind) params.set("kind", state.filters.kind);' in params
    # Never a re-sort of only the rows on screen (D26).
    assert "function sortRows" not in SCRIPT
    render = _between(SCRIPT, "function renderLibrary()", "function transcriptKind(source)")
    assert "const rows = state.library.slice();" in render


def test_topic_list_with_counts_sits_in_the_sidebar():
    sidebar = _between(MARKUP, '<aside class="sidebar"', "</aside>")
    topics = _between(sidebar, '<div class="sidebar-topics hidden" id="sidebarTopics">', '<div class="sidebar-bottom">')
    assert 'id="topicOverview"' in topics and 'aria-labelledby="sidebarTopicsTitle"' in topics
    assert 'id="topicOverview"' not in _panel("library")
    overview = _between(SCRIPT, "function renderTopicOverview()", "function facetSourceKeys")
    assert "<span>${count}</span>" in overview, "each topic shows its count"
    assert "syncSidebarTopics();" in overview
    sync = _between(SCRIPT, "function syncSidebarTopics()", "function renderTopicOverview()")
    assert '["library", "yoink"].includes(tab)' in sync


def test_library_activity_is_a_collapsed_insights_section_below_the_list():
    library = _panel("library")
    insights = re.search(r'<details class="library-insights" id="libraryInsights"( open)?>', library)
    assert insights and not insights.group(1), "Insights starts collapsed"
    section = library[library.index('<details class="library-insights" id="libraryInsights">'):]
    assert '<summary class="library-insights-summary">Insights' in section
    assert 'id="libraryActivityPanel"' in section and 'id="activityEvidenceModal"' in section
    assert library.index('id="loadMore"') < library.index('id="libraryInsights"')


def test_saved_rows_hold_a_thumbnail_title_source_line_and_one_state_line():
    card = _between(SCRIPT, "function cardHtml(row)", "async function loadThumbnail")
    for marker in ('<div class="row-thumb" aria-hidden="true">', '<img alt="" data-thumb-for="${id}" class="hidden">',
                   '<div class="card-title">${title}</div>', '<div class="card-source">${author} &middot; ${platformLabel}',
                   '<div class="row-state">${savedStateLine(row)}${healthException(row.health)}</div>'):
        assert marker in card
    detail = _between(SCRIPT, "function savedRowDetail(row)", "function savedStateLine(row)")
    assert "captions`" in detail and '"transcript by Whisper"' in detail
    # The state is a word; the dot only repeats it.
    line = _between(SCRIPT, "function savedStateLine(row)", "function cardHtml(row)")
    assert '<i class="state-dot" aria-hidden="true"></i>Done</span>' in line
    thumb = _between(SCRIPT, "async function loadThumbnail(row)", "function revokeThumbs()")
    assert "row.thumbnail_path" in thumb and "/file?path=" in thumb


def test_capture_rows_use_the_five_step_strip_with_words():
    steps = re.search(r"const CAPTURE_STEPS = \[([^\]]+)\];", SCRIPT)
    assert steps and [s.strip().strip('"') for s in steps.group(1).split(",")] == [
        "details", "waiting for YouTube", "video", "transcript", "screenshots and save"]
    strip = _between(SCRIPT, "function captureStripHtml(index", "function captureAdvanced(key, index)")
    assert '<span class="step-strip" aria-hidden="true">' in strip, "the strip repeats the words; it is not read out"
    items = _between(SCRIPT, "function libraryCaptureItems()", "function libraryCaptureRowHtml(item)")
    for words in ('"Capturing"', '"Waiting"', '"one YouTube capture at a time"', "`Failed at ${CAPTURE_STEPS[index]}`",
                  "Retries ${at}", "(HTTP 429)"):
        assert words in items, words
    line = _between(SCRIPT, "function captureStepLine(index)", "const LIBRARY_FAILURE_WINDOW_MS")
    assert "(${index + 1} of 5)" in line


def test_a_link_in_the_box_goes_through_detect_and_the_capture_routes():
    box = _between(SCRIPT, "const libraryCapture = {", "function dropLibraryRun(run)")
    assert "await detectCaptureUrl(raw)" in box, "the same /detect brain as Sources' box"
    assert 'body.interval = dashboardScreenshotInterval()' in box and '"/playlist/start"' in box
    assert "authFetch(detected.endpoint, { method: \"POST\"" in box
    wire = _between(SCRIPT, "function wireEvents()", "function upsertJob(job)")
    assert 'els.searchInput.addEventListener("keydown", (event) => {' in wire
    assert "startLibraryCapture();" in wire
    assert 'if (syncLibraryBox() && !state.filters.q) return;' in wire
    # D1: a link is never a search query; text keeps the sequenced path.
    assert 'state.filters.q = looksLikeLink(els.searchInput.value) ? "" : els.searchInput.value;' in wire
    assert "state.libraryRequest++;" in wire and "state.libraryResetPending = true;" in wire


# ---- Reader markup and style ------------------------------------------------

def test_reader_is_a_landmark_with_breadcrumb_title_meta_and_actions():
    reader = _panel("yoink")
    assert re.search(r'<section class="tab-panel reader" id="tab-yoink" data-tab-panel="yoink" aria-labelledby="yoinkHeading">', MARKUP)
    crumbs = _between(reader, '<nav class="reader-crumbs" aria-label="Breadcrumb">', "</nav>")
    assert '<li><a href="#library">Library</a></li>' in crumbs
    assert 'id="yoinkCrumbTopic"' in crumbs and 'aria-current="page"' in crumbs
    assert '<h1 id="yoinkHeading" tabindex="-1">' in reader
    assert 'id="yoinkSubhead"' in reader and 'id="yoinkSourceLink"' in reader
    actions = _between(reader, '<div class="inline-row yoink-actions">', "</details>")
    for label in ("Copy as Markdown", "Send to Claude", "Open folder"):
        assert f">{label}</button>" in actions
    assert '<p class="reader-note hidden" id="yoinkTranscriptNote" role="note"></p>' in reader
    body = reader[reader.index('<div class="reader-body">'):]
    doc = body.index('<article class="reader-doc" id="yoinkDetail"')
    assert doc < body.index('<details class="reader-section hidden" id="yoinkCommentsSection">')
    assert doc < body.index('<details class="reader-section hidden" id="yoinkAnalysisSection">')
    # No italic-serif word swaps in the reader or Library heads.
    assert "<em" not in _between(reader, '<div class="page-head reader-head">', '<div class="reader-body">')
    assert "<em" not in _between(_panel("library"), '<div class="page-head library-head">', '<div class="control-grid">')


def test_reader_layout_uses_the_gutter_width_and_motion_tokens():
    assert re.search(r"--time-gutter:\s*44px;", STYLE) and re.search(r"--reader-width:\s*700px;", STYLE)
    assert "grid-template-columns: var(--time-gutter) minmax(0, var(--reader-width));" in _rule(".reader-row")
    assert "max-width: calc(var(--reader-width)" in _rule(".tab-panel.reader")
    assert "animation: reader-enter var(--dur-enter) var(--ease-enter);" in _rule(".tab-panel.reader.active")
    assert "animation: step-advance var(--dur-enter) var(--ease-enter);" in _rule(".step.now.advanced")
    assert "border-radius: var(--radius-figure);" in _rule(".reader-shot-frame")
    assert "border-radius: var(--radius-thumb);" in _rule(".row-thumb")
    assert "min-height: var(--target-primary);" in _rule("#tab-library .omnibox-row .control")
    assert "min-height: var(--target-chip);" in _rule(".kind-chip")
    # Reduced motion stops both animations (the shared rule zeroes them).
    reduced = _between(STYLE_RAW, "@media (prefers-reduced-motion: reduce)", "/* Dashboard-only colour names")
    assert "animation-duration: 0.01ms !important;" in reduced
    # Status is never colour alone: the strip and the dots are hidden from
    # assistive tech because the words beside them carry the state.
    assert '<i class="state-dot" aria-hidden="true"></i>' in SCRIPT


def test_reader_transcript_never_invents_times_and_links_only_real_ones():
    time = _between(SCRIPT, "function readerTimeHtml(seconds, url)", "function readerShotHtml(row, shot, seconds, url)")
    assert "time not stored" in time
    link = _between(SCRIPT, "function sourceTimeUrl(url, seconds)", "const READER_PARAGRAPH_SEGMENTS")
    assert "youtube\\.com|youtu\\.be" in link, "only YouTube takes a time in its link"
    note = _between(SCRIPT, "function transcriptNoteText(row, sidecar = {})", "function readerDocumentHtml(row, sidecar = {})")
    for status in ('"disabled"', '"model_not_downloaded"', '"failed"', '"skipped_chunked_mode"'):
        assert status in note
    assert 'source === "asr"' in note
    # Reader screenshots load lazily, not through the page-wide loader.
    assert 'data-reader-img="' in SCRIPT
    loader = _between(SCRIPT, "async function loadDetailFileImages()", "function rowFromCard(card)")
    assert "data-reader-img" not in loader


def test_reader_screenshots_never_wait_on_the_transcript():
    # Review finding: readerTranscriptHtml returns "" with no transcript and
    # the Markdown fallback drops image lines, so the screenshots render on
    # their own whenever there is no timed transcript to sit them in.
    doc = _between(SCRIPT, "function readerDocumentHtml(row, sidecar = {})", "function commentStatusCopy(status)")
    assert "const shots = readerShotsHtml(row, sidecar);" in doc
    assert doc.index("const shots = readerShotsHtml(row, sidecar);") < doc.index("const prose = readerMarkdownHtml(")
    assert "return `${prose}${shots}`;" in doc
    assert doc.count("${shots}`;") == 4, "every fallback ends with the screenshots"
    shots = _between(SCRIPT, "function readerShotsHtml(row, sidecar = {})", "function readerTranscriptHtml(row, sidecar = {})")
    assert "readerShotList(sidecar)" in shots and "readerShotHtml(row, item.shot, item.seconds, url)" in shots


def test_live_steps_saves_and_one_row_per_failure_are_wired():
    # Review findings 2-4, as the page wires them (the harness groups live,
    # saves and reconcile run them).
    box = _between(SCRIPT, "async function startLibraryCapture()", "function dropLibraryRun(run)")
    assert "if (run.ref) body.capture_ref = run.ref;" in box and "pollLibraryRuns();" in box
    items = _between(SCRIPT, "function libraryCaptureItems()", "function libraryCaptureRowHtml(item)")
    assert "const live = failed ? null : liveCaptureFor(run);" in items
    assert "captureStepIndex(live.phase)" in items
    jobs = _between(SCRIPT, "async function refreshJobs(", "async function loadLibrary(")
    assert "state.liveCaptures = Array.isArray(data.live_captures) ? data.live_captures : [];" in jobs
    # The paste poll reads only the live phases; the job list stays the
    # stream's, so a late poll answer never puts an older job state back (D20).
    poll = _between(SCRIPT, "async function refreshLiveCaptures()", "function trackCaptureSaves(")
    assert "state.liveCaptures = Array.isArray(data.live_captures) ? data.live_captures : [];" in poll
    assert "state.jobs" not in poll and "await refreshLiveCaptures();" in poll
    # A render with no step known is not a step: the first reported one never animates.
    advanced = _between(SCRIPT, "function captureAdvanced(key, index)", "function captureStepLine(index)")
    assert "if (index < 0) return false;" in advanced
    render = _between(SCRIPT, "function renderQueue(data)", "function completedTodayRows()")
    assert "trackCaptureSaves();" in render
    track = _between(SCRIPT, "function trackCaptureSaves(", "function libraryCaptureItems()")
    assert "loadLibrary({ reset: true, jobs: false })" in track and "loadLibraryFacets()" in track
    assert "setTimeout" not in track, "an open jobs stream schedules nothing (D20)"
    fail = _between(SCRIPT, "function failLibraryRun(run, err)", "function dropLibraryCaptureRow(key)")
    assert 'run.jobId = typeof data.job_id === "string" ? data.job_id : "";' in fail
    captures = _between(SCRIPT, "function renderLibraryCaptures()", "function markOpenLibraryRow()")
    assert captures.index("reconcileLibraryRuns();") < captures.index("libraryCaptureItems()")


def test_no_features_manifest_fetch_and_no_remote_assets():
    assert "features-manifest" not in DASHBOARD
    assert not re.search(r"fetch\(\s*[\"'`]https?://", SCRIPT)


# ---- Helper: /memory/search type groups and order -------------------------

@pytest.fixture
def library(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "isolated.db")
    root = tmp_path / "output"
    root.mkdir()
    rows = [
        ("v1", "video", "youtube", "2026-01-01T10:00:00", "Banana talk", "bananas grow"),
        ("v2", "x_thread", "x", "2026-02-01T10:00:00", "Apple thread", "apple orchards"),
        ("v3", "note", "note", "2026-03-01T10:00:00", "Cherry note", "cherry picking"),
        ("v4", "short_video", "tiktok", "2026-04-01T10:00:00", "apple short", "apple pie"),
        ("v5", "episode", "podcast", "2026-05-01T10:00:00", "Durian pod", "durian smell"),
    ]
    for vid, source_type, platform, when, title, content in rows:
        folder = root / vid
        folder.mkdir()
        idx.upsert_yoink({
            "video_id": vid, "slug": vid, "yoinked_at": when, "title": title,
            "source_type": source_type, "platform": platform,
            "corpus_path": str(folder / f"{vid}.md"), "sidecar_path": str(folder / f"{vid}.json"),
        }, content=content)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: True)
    try:
        yield idx
    finally:
        idx.close()


def _search(query: str):
    handler = server.Handler.__new__(server.Handler)
    handler.path = "/memory/search?" + query
    sent = []
    handler._send_json = lambda status, data: sent.append((status, data))
    handler._handle_memory_search()
    assert sent, "no answer"
    return sent[-1]


def _ids(answer):
    status, data = answer
    assert status == 200, data
    return [row["video_id"] for row in data["results"]]


def test_type_chips_and_sort_are_answered_over_every_match(library):
    assert _ids(_search("kind=videos&sort=oldest")) == ["v1", "v4"]
    assert _ids(_search("kind=videos")) == ["v4", "v1"]
    assert _ids(_search("kind=posts&sort=newest")) == ["v2"]
    assert _ids(_search("kind=notes&sort=newest")) == ["v3"]
    assert _ids(_search("kind=podcasts&sort=newest")) == ["v5"]
    assert _ids(_search("sort=title")) == ["v4", "v2", "v1", "v3", "v5"]
    assert _ids(_search("sort=oldest")) == ["v1", "v2", "v3", "v4", "v5"]
    # Paging walks the whole ordered set, not one page re-sorted.
    status, data = _search("sort=oldest&limit=2&offset=2")
    assert [row["video_id"] for row in data["results"]] == ["v3", "v4"] and data["total"] == 5
    # A search keeps its matches under any order.
    assert _ids(_search("q=apple&sort=oldest")) == ["v2", "v4"]
    assert _ids(_search("q=apple&kind=videos&sort=newest")) == ["v4"]
    status, data = _search("kind=notes&q=banana&sort=newest")
    assert status == 200 and data["results"] == [] and data["state"] == "no_matches"


def test_a_bad_kind_is_refused(library):
    status, data = _search("kind=movies")
    assert status == 400 and "kind must be one of" in data["error"]


def test_an_unknown_sort_keeps_the_order_the_route_always_gave(library):
    # Callers older than the sort control send their own values (the
    # popup's resurfacing card asks for sort=engagement); /memory/search
    # ignored them before the re-haul and still answers them.
    assert _ids(_search("sort=engagement")) == ["v5", "v4", "v3", "v2", "v1"]
    assert _ids(_search("sort=random&q=apple")) == _ids(_search("q=apple"))
    assert _ids(_search("sort=engagement&kind=videos")) == ["v4", "v1"]


def test_requests_the_index_already_orders_keep_the_index_path(library, monkeypatch):
    calls = []
    original = library.search_yoinks_for_memory

    def spy(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(library, "search_yoinks_for_memory", spy)
    assert _ids(_search("limit=10")) == ["v5", "v4", "v3", "v2", "v1"]
    assert _ids(_search("sort=newest")) == ["v5", "v4", "v3", "v2", "v1"]
    _search("q=apple&sort=relevance")
    _search("sort=engagement")
    assert len(calls) == 4
    _search("q=apple&sort=newest")
    _search("kind=videos")
    assert len(calls) == 4, "a group or another order is answered by _library_search"


def test_rows_carry_where_the_transcript_came_from(tmp_path):
    idx = index_mod.Index.open(tmp_path / "isolated.db")
    try:
        folder = tmp_path / "output" / "v9"
        folder.mkdir(parents=True)
        sidecar = folder / "v9.json"
        sidecar.write_text(json.dumps({
            "url": "https://www.youtube.com/watch?v=v9", "platform": "youtube", "title": "Nine",
            "transcript": [{"start": 0, "end": 2, "text": "hello"}],
            "transcript_source": "asr", "asr_fallback": {"status": "completed", "model": "base"},
        }), encoding="utf-8")
        idx.upsert_yoink({"video_id": "v9", "slug": "v9", "yoinked_at": "2026-10-01T10:00:00", "title": "Nine",
                          "source_type": "video", "platform": "youtube",
                          "corpus_path": str(folder / "v9.md"), "sidecar_path": str(sidecar)})
        row = server._enrich_yoink_rows(idx, [idx.get_yoink("v9")])[0]
        assert row["transcript_source"] == "asr"
        assert row["asr_fallback_status"] == "completed"
        assert row["has_transcript"] is True
    finally:
        idx.close()


# ---- Helper: /yoinks/<id>/details carries the Reader's fields, bounded ------

@pytest.fixture
def item(tmp_path, monkeypatch):
    root = tmp_path / "output"
    root.mkdir()
    idx = index_mod.Index.open(tmp_path / "isolated.db")
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    path = root / "media.json"
    idx.upsert_yoink({"video_id": "saved-media", "slug": "saved-media", "yoinked_at": "2026-09-12T00:00:00Z",
                      "title": "Synthetic item", "sidecar_path": str(path), "corpus_path": str(root / "media.md"),
                      "source_type": "video", "platform": "youtube"})
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = lambda status, data: (status, data)

    def request(sidecar: dict):
        path.write_text(json.dumps(sidecar), encoding="utf-8")
        return handler._handle_yoink_details("/yoinks/saved-media/details")

    try:
        yield request
    finally:
        idx.close()


def test_details_carry_the_transcript_source_and_why_whisper_ran(item):
    status, data = item({
        "transcript_source": None,
        "asr_fallback": {"status": "failed", "model": "small", "error": "x" * 900,
                         "estimated_minutes_min": 1, "private": "DO_NOT_RETURN"},
        "yoinked_at": "2026-09-12T00:00:00Z", "upload_date": "20260901",
    })
    assert status == 200
    details = data["details"]
    assert details["transcript_source"] is None
    assert details["asr_fallback"]["status"] == "failed" and details["asr_fallback"]["model"] == "small"
    assert len(details["asr_fallback"]["error"]) == 300
    assert set(details["asr_fallback"]) == {"status", "model", "error"}
    assert details["yoinked_at"] == "2026-09-12T00:00:00Z" and details["upload_date"] == "20260901"
    assert "DO_NOT_RETURN" not in json.dumps(data)


def test_details_carry_bounded_comments_and_analysis(item):
    comments = [{"author": f"user{n}", "text": "y" * 5000, "like_count": n, "reply_count": 2,
                 "time_text": "1 day ago", "is_pinned": n == 0, "author_id": "DO_NOT_RETURN"}
                for n in range(server.READER_COMMENT_LIMIT + 20)]
    comments.append({"author": "blank", "text": "   "})
    status, data = item({
        "comments": comments, "comments_status": "fetched",
        "hook_type": "question", "hook_type_confidence": 4, "hook_type_status": "completed",
        "hook_explanation": "Opens on a question.",
        "comment_intelligence_status": "completed",
        "comment_intelligence": {
            "top_themes": [{"label": "Pricing", "count": 4, "description": "Cost questions.",
                            "quotes": ["How much?", 7, "  "], "internal": "DO_NOT_RETURN"}],
            "mentioned_products_tools": [{"name": "Notion", "frequency": 3}, {"name": ""}],
            "notable_disagreements": [{"description": "Free tier", "sample_comments": ["No way."]}],
            "raw_prompt": "DO_NOT_RETURN",
        },
    })
    assert status == 200
    details = data["details"]
    saved = details["comments"]
    assert len(saved) == server.READER_COMMENT_LIMIT
    assert all(len(c["text"]) == server.READER_COMMENT_CHARS for c in saved)
    assert set(saved[0]) == {"author", "text", "like_count", "reply_count", "time_text", "is_pinned"}
    assert saved[0]["is_pinned"] is True and saved[1]["is_pinned"] is False
    assert details["comments_status"] == "fetched"
    assert details["hook_type"] == "question" and details["hook_type_confidence"] == 4
    assert details["hook_explanation"] == "Opens on a question."
    ci = details["comment_intelligence"]
    assert ci["top_themes"] == [{"label": "Pricing", "count": 4, "description": "Cost questions.", "quotes": ["How much?"]}]
    assert ci["mentioned_products_tools"] == [{"name": "Notion", "frequency": 3}]
    assert ci["notable_disagreements"] == [{"description": "Free tier", "sample_comments": ["No way."]}]
    assert "DO_NOT_RETURN" not in json.dumps(data)


# ---- Helper: a pasted video's live phase and the job its failure names ------

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def extract(tmp_path, monkeypatch):
    """/extract over fakes: the shape test_long_video_v324 drives it in."""
    class FakeHandler:
        _validate_url_interval = server.Handler._validate_url_interval
        _handle_extract = server.Handler._handle_extract

        def _send_json(self, status, payload):
            self.response = (status, payload)
            return self.response

    @contextlib.contextmanager
    def ownership(_url):
        yield server._ManualOwnership()

    recorded = []

    def record(url, started_at, **kwargs):
        recorded.append({"url": url, "started_at": started_at, **kwargs})
        return {"id": "job_20261016_120000_abc123"}

    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_manual_extraction_ownership", ownership)
    monkeypatch.setattr(server, "_fetch_metadata", lambda *_a, **_k: {"id": "abcdefghijk", "title": "Live phases"})
    monkeypatch.setattr(server, "_classify_topic", lambda *_a, **_k: "Test")
    monkeypatch.setattr(server, "_record_single_extract_job", record)
    yield FakeHandler(), recorded
    assert server._live_extracts_public() == [], "every entry ends with its request"


def _live():
    return [(entry["capture_ref"], entry["phase"]) for entry in server._live_extracts_public()]


def test_a_pasted_video_reports_each_phase_until_it_answers(extract, monkeypatch):
    handler, recorded = extract
    seen = []

    def run(_url, _interval, folder, **kwargs):
        seen.append(_live())
        kwargs["phase_callback"]("download")
        seen.append(_live())
        kwargs["phase_callback"]("transcript")
        seen.append(_live())
        return {"ok": True, "folder": str(folder), "title": "Live phases", "screenshot_count": 0}

    monkeypatch.setattr(server, "_run_extraction", run)
    handler._handle_extract({"url": VIDEO, "interval": 30, "capture_ref": "libk2x9ab12cd"})
    status, payload = handler.response
    assert status == 200 and payload["title"] == "Live phases"
    assert seen == [[("libk2x9ab12cd", "metadata")], [("libk2x9ab12cd", "download")],
                    [("libk2x9ab12cd", "transcript")]]
    assert _live() == [], "the saved capture is no longer live"
    assert len(recorded) == 1 and "error" not in recorded[0], "the job is still recorded once, at the end"


def test_a_pasted_video_waiting_for_its_turn_says_so(extract, monkeypatch):
    handler, _ = extract
    seen = []

    @contextlib.contextmanager
    def ownership(_url):
        seen.append(_live())  # another capture holds the lock
        yield server._ManualOwnership()

    monkeypatch.setattr(server, "_manual_extraction_ownership", ownership)
    monkeypatch.setattr(server, "_run_extraction",
                        lambda _u, _i, folder, **_k: {"folder": str(folder), "title": "T", "screenshot_count": 0})
    handler._handle_extract({"url": VIDEO, "interval": 30, "capture_ref": "not a ref!"})
    assert handler.response[0] == 200
    # A reference that is not a plain token is dropped, never echoed.
    assert seen == [[(None, "waiting")]]


def test_a_failed_paste_names_the_job_it_recorded(extract, monkeypatch):
    handler, recorded = extract

    def broken(_url, _interval, _folder, **kwargs):
        kwargs["phase_callback"]("download")
        raise RuntimeError("ERROR: [youtube] abcdefghijk: Video unavailable")

    monkeypatch.setattr(server, "_run_extraction", broken)
    handler._handle_extract({"url": VIDEO, "interval": 30, "capture_ref": "libfail01"})
    status, payload = handler.response
    assert status == 200 and payload["ok"] is False
    assert payload["job_id"] == "job_20261016_120000_abc123", "the dashboard hands its row over to this job"
    assert payload["failure_phase"] == "download" == recorded[0]["failure_phase"]
    assert _live() == []


def test_a_rejected_paste_never_goes_live(extract):
    handler, recorded = extract
    handler._handle_extract({"url": "https://example.com/not-a-video", "interval": 30, "capture_ref": "libx"})
    assert handler.response[0] == 400 and recorded == []
    assert server.Handler._handle_extract.__name__ == "_handle_extract"


def test_jobs_list_carries_the_live_captures():
    handler = server.Handler.__new__(server.Handler)
    sent = []
    handler._send_json = lambda status, data: sent.append((status, data))
    server._live_extract_begin(VIDEO, "libjobs01")
    try:
        server._live_extract_phase("screenshots")
        handler.path = "/jobs"
        handler._handle_jobs_list()
        handler.path = "/jobs?kind=playlist"
        handler._handle_jobs_list()
    finally:
        server._live_extract_end()
    handler.path = "/jobs"
    handler._handle_jobs_list()
    (status, everything), (_, playlists), (_, after) = sent
    assert status == 200 and isinstance(everything["jobs"], list)
    assert [(e["capture_ref"], e["phase"], e["source_url"]) for e in everything["live_captures"]] == [
        ("libjobs01", "screenshots", VIDEO)]
    assert playlists["live_captures"] == [], "a playlist listing carries no single-video captures"
    assert after["live_captures"] == []


# ---- The real dashboard script: behaviour ---------------------------------

GROUPS = ["paste", "kinds", "rows", "reader", "split", "live", "saves", "reconcile", "retry", "errors"]


@pytest.mark.parametrize("group", GROUPS)
def test_library_and_reader_behaviour(group):
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
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 5, output
