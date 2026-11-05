"""Launch capture status, episode identity, and plain failure presentation.

Execute the shipped dashboard script with a fake DOM and helper; no user data.
"""
import ast
import json
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const script = html.split('<script>')[1].split('    init().catch(')[0];
const elements = new Map();
function element(id) {
  const classes = new Set();
  return { id, value: '', textContent: '', innerHTML: '', hidden: false, disabled: false,
    dataset: {}, style: {}, attributes: {}, open: false,
    classList: { add: (s) => classes.add(s), remove: (s) => classes.delete(s),
      contains: (s) => classes.has(s), toggle: (s, on) => on ? classes.add(s) : classes.delete(s) },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return this.attributes[k] || null; }, removeAttribute(k) { delete this.attributes[k]; },
    querySelectorAll: () => [], querySelector: () => null, closest: () => null,
    addEventListener() {}, focus() {}, showModal() { this.open = true; }, close() { this.open = false; } };
}
const get = (id) => { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
const ctx = { document: { getElementById: get, querySelector: () => null, querySelectorAll: () => [], activeElement: null },
  window: { addEventListener() {} }, navigator: {}, URL, URLSearchParams, console,
  localStorage: { getItem: () => null, setItem() {} }, setTimeout: () => 1, clearTimeout() {},
  fetch: () => { throw Error('Network forbidden'); } };
vm.createContext(ctx);
vm.runInContext(script, ctx);
Promise.resolve(vm.runInContext(fs.readFileSync(0, 'utf8'), ctx)).then(
  result => process.stdout.write(JSON.stringify(result)),
  err => { process.stderr.write(String(err.stack || err)); process.exitCode = 1; });
"""


def run_js(code):
    result = subprocess.run(["node", "-e", HARNESS], input=code, cwd=ROOT,
                            text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(("phase", "label"), [
    ("metadata", "Getting details"), ("download", "Downloading video"),
    ("transcript", "Getting transcript"), ("transcribing", "Getting transcript"),
    ("screenshots", "Saving screenshots"), ("writing", "Saving"),
    ("waiting", "Waiting"), ("queued", "Waiting"), ("rate_limit", "Waiting"),
])
def test_live_capture_and_activity_use_plain_stage(phase, label):
    result = run_js("""(() => {
      const phase = %s;
      const run = {id: 'r1', ref: 'capture1', url: 'https://youtu.be/abcdefghijk',
        label: 'YouTube video', state: 'running', startedAt: new Date().toISOString()};
      state.libraryRuns = [run];
      state.liveCaptures = [{capture_ref: run.ref, phase}];
      const item = libraryCaptureItems()[0];
      return {word: item.word, html: libraryCaptureRowHtml(item),
        activity: activitySteps({state: 'running', phase}).label};
    })()""" % json.dumps(phase))
    assert result["word"] == label
    assert result["activity"] == (f"{label} · one YouTube capture at a time" if label == "Waiting" else label)
    assert "of 5" not in result["html"] and "Capturing ·" not in result["html"]


@pytest.mark.parametrize("comments", ["pending", "processing", "failed", "ok"])
def test_background_comments_do_not_hold_ready_card(comments):
    result = run_js("""(() => {
      const row = {video_id: 'abcdefghijk', title: 'Saved video', source_type: 'video',
        transcript_source: 'captions', health: {transcript: 'ok', screenshots: 'ok',
          comments: %s, hook: 'pending', comment_intelligence: 'pending'}};
      return {card: cardHtml(row), activity: activitySteps({state: 'completed'}).label,
        issues: healthIssues(row.health)};
    })()""" % json.dumps(comments))
    assert ">Ready</span>" in result["card"] and result["activity"] == "Ready"
    assert "Comments pending" not in result["card"]
    assert "steps pending" not in result["card"]
    # Optional work is still available to the existing health drawer.
    assert any(issue["key"] == "hook" for issue in result["issues"])


@pytest.mark.parametrize("background", [False, True])
def test_last_save_card_refreshes_after_capture(background):
    result = run_js("""(async () => {
      let resumeReads = 0;
      authFetch = async (path) => {
        if (path !== '/resume') throw Error('Unexpected helper request: ' + path);
        resumeReads++;
        return {resume: {last_source: {video_id: resumeReads === 1 ? 'old' : 'new',
          title: resumeReads === 1 ? 'Older capture' : 'Latest capture'}}};
      };
      loadLibrary = loadLibraryFacets = refreshActivity = async () => {};
      await loadResume();
      if (%s) {
        trackCaptureSaves();
        state.jobs = [{id: 'background', state: 'completed', videos_done: 1}];
        trackCaptureSaves();
      } else {
        finishLibraryRun({id: 'run1', endpoint: '/extract', label: 'YouTube video'}, {title: 'Latest capture'});
      }
      for (let i = 0; i < 8; i++) await Promise.resolve();
      const countAfterSave = resumeReads;
      trackCaptureSaves();
      for (let i = 0; i < 8; i++) await Promise.resolve();
      return {card: els.resumeCard.innerHTML, countAfterSave, resumeReads};
    })()""" % str(background).lower())
    assert "Latest capture" in result["card"] and 'data-write-from="new"' in result["card"]
    assert result["countAfterSave"] >= 2
    assert result["resumeReads"] == result["countAfterSave"]


def test_last_save_card_ignores_older_inflight_reply():
    result = run_js("""(async () => {
      const replies = [];
      authFetch = () => new Promise(resolve => replies.push(resolve));
      const older = loadResume(), newer = loadResume();
      replies[1]({resume: {last_source: {video_id: 'new', title: 'Newest'}}});
      await newer;
      replies[0]({resume: {last_source: {video_id: 'old', title: 'Stale'}}});
      await older;
      return els.resumeCard.innerHTML;
    })()""")
    assert "Newest" in result and "Stale" not in result


@pytest.mark.parametrize("capture", ["note", "image", "source"])
def test_last_save_card_refreshes_for_other_dashboard_saves(capture):
    result = run_js("""(async () => {
      let saved = false;
      authFetch = async (path, options = {}) => {
        if (options.method === 'POST') { saved = true; return {ok: true}; }
        if (path !== '/resume') throw Error('Unexpected request: ' + path);
        return {resume: {last_source: {video_id: saved ? 'new' : 'old', title: saved ? 'New save' : 'Old save'}}};
      };
      loadLibrary = loadLibraryFacets = refreshActivity = async () => {};
      showToast = () => {};
      await loadResume();
      const capture = %s;
      if (capture === 'note') {
        els.noteTextInput.value = 'A synthetic note';
        await saveNote();
      } else if (capture === 'image') {
        imageState.file = {name: 'fixture.png', type: 'image/png'};
        await saveImage();
      } else {
        Object.assign(universalState, {endpoint: '/extract/page', canonical: 'https://example.test/article', label: 'Web page'});
        await runUniversalCapture();
      }
      for (let i = 0; i < 8; i++) await Promise.resolve();
      return {saved, card: els.resumeCard.innerHTML};
    })()""" % json.dumps(capture))
    assert result["saved"]
    assert "New save" in result["card"] and 'data-write-from="new"' in result["card"]


def test_activity_merges_podcast_job_with_saved_episode_not_feed_url():
    result = run_js("""(() => {
      const now = new Date().toISOString();
      state.jobs = [1, 2].map(n => ({id: 'job' + n, kind: 'podcast_transcribe',
        episode_id: n, title: 'Episode ' + n, state: 'completed', completed_at: now,
        source_url: 'https://example.test/episode/' + n,
        result: {episode_id: n, corpus: {video_id: 'podcast_' + n}}}));
      state.library = [1, 2].map(n => ({video_id: 'podcast_' + n, source_type: 'episode',
        title: 'Episode ' + n, source_url: 'https://example.test/feed.xml', yoinked_at: now}));
      renderQueue({pending: []});
      return {entries: state.activityEntries.map(e => ({id: e.row.id, saved: e.saved && e.saved.video_id})),
        count: els.completedToday.textContent};
    })()""")
    assert len(result["entries"]) == 2
    assert {entry["saved"] for entry in result["entries"]} == {"podcast_1", "podcast_2"}
    assert result["count"] == "2"


def test_activity_podcast_retry_replaces_old_attempt_without_hiding_other_episode():
    result = run_js("""(() => {
      const base = {kind: 'podcast_transcribe', source_url: 'https://example.test/show'};
      state.jobs = [
        {...base, id: 'old', episode_id: 1, state: 'failed', updated_at: '2026-11-04T10:00:00Z'},
        {...base, id: 'new', episode_id: 1, state: 'running', updated_at: '2026-11-04T11:00:00Z'},
        {...base, id: 'other', episode_id: 2, state: 'failed', updated_at: '2026-11-04T09:00:00Z'}];
      return activityEntries({}).map(e => e.row.id).sort();
    })()""")
    assert result == ["new", "other"]


def test_podcast_retry_joins_saved_episode_after_original_job_ages_out():
    result = run_js("""(() => {
      state.jobs = [{id: 'retry', kind: 'podcast_transcribe', episode_id: 12, state: 'running',
        source_url: 'https://example.test/episode/12', current_video_phase: 'transcribing'}];
      state.library = [{video_id: 'podcast12', source_type: 'episode', source_url: 'https://example.test/feed.xml',
        metadata_json: JSON.stringify({episode_id: 12, platform: 'podcast'})}];
      return activityEntries({}).map(e => ({id: e.row.id, saved: e.saved && e.saved.video_id, group: e.group}));
    })()""")
    assert result == [{"id": "retry", "saved": "podcast12", "group": "progress"}]


@pytest.mark.parametrize(("active", "failed"), [(0, 0), (1, 0), (0, 1), (1, 1), (2, 3)])
def test_activity_sidebar_has_one_count_and_headline_acknowledges_failures(active, failed):
    result = run_js("""(() => {
      const nav = document.getElementById('fixtureActivityNav');
      nav.dataset.navLabel = 'Activity';
      els.activityNavCount.closest = () => nav;
      state.jobs = Array.from({length: %s}, (_, n) => ({id: 'failure' + n, state: 'failed'}))
        .concat(Array.from({length: %s}, (_, n) => ({id: 'running' + n, state: 'running'})));
      renderQueue({pending: []});
      return {count: els.activityNavCount.textContent, title: els.activityNavCount.title,
        label: nav.getAttribute('aria-label'), failed: els.activityNavCount.classList.contains('nav-failed'),
        headline: els.activityHeadline.innerHTML};
    })()""" % (failed, active))
    total = active + failed
    label = f"{total} {'capture' if total == 1 else 'captures'} in progress or needing attention"
    if failed:
        label += f", {failed} failed"
        assert "attention" in result["headline"]
        assert "Nothing uoinking" not in result["headline"]
    assert result["count"] == str(total)
    assert result["title"] == label
    assert result["label"] == f"Activity, {label}"
    assert result["failed"] == bool(failed)
    html = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
    nav = re.search(r'<button[^>]*data-tab-button="activity".*?</button>', html, re.S).group(0)
    assert re.findall(r'<span[^>]*id="([^"]+)"', nav) == ["activityNavCount"]


@pytest.mark.parametrize("label", ["YouTube video", "X post", "Reddit thread"])
def test_failed_capture_note_preserves_source_capitalization(label):
    result = run_js("""(() => {
      refreshActivity = async () => {};
      failLibraryRun({id: 'r1', label: %s}, {data: {error: 'This link is unavailable.'}});
      return els.libraryCaptureNote.textContent;
    })()""" % json.dumps(label))
    assert result.startswith(f"That {label} didn't save.")


def test_failure_drawer_leads_with_reason_and_discloses_raw_error():
    result = run_js("""(() => {
      state.jobs = [{id: 'unavailable', state: 'failed', source_url: 'https://youtu.be/abcdefghijk',
        error: 'This video is unavailable.', failure_phase: 'download',
        error_detail: 'ERROR: [youtube] abcdefghijk: Video is unavailable'}];
      renderQueue({pending: []});
      openCaptureFailure('job:unavailable');
      return {reason: document.getElementById('captureFailureReason').textContent,
        detail: document.getElementById('captureFailureError').textContent};
    })()""")
    assert result["reason"] == "This video is unavailable."
    assert result["detail"].startswith("ERROR: [youtube]")
    html = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
    drawer = html.split('id="captureFailureDrawer"', 1)[1].split("</dialog>", 1)[0]
    assert drawer.index('id="captureFailureReason"') < drawer.index('id="captureFailureSteps"')
    disclosure = drawer.split("<summary>Details</summary>", 1)[1].split("</details>", 1)[0]
    assert 'id="captureFailureError"' in disclosure


@pytest.fixture(scope="module")
def plain_error_from_text():
    # Load just the error translators, without importing server startup state.
    names = {"_source_name_from_error", "_plain_error_from_text"}
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    scope = {}
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                                  and n.name in names], type_ignores=[]), "server.py", "exec"), scope)
    return scope["_plain_error_from_text"]


@pytest.mark.parametrize("message", [
    "Video unavailable", "Video is unavailable", "This video is not available",
    "This video has been removed by the uploader", "This video isn't available",
    "This video is no longer available",
])
def test_unavailable_video_is_not_misclassified_as_ffmpeg_failure(message, plain_error_from_text):
    diagnostic = f"Command: yt-dlp --cookies browser.txt --ffmpeg-location bundled/bin\nERROR: [youtube] abcdefghijk: {message}"
    assert plain_error_from_text(diagnostic) == "This video is unavailable."
    shown = run_js("""(() => {
      const raw = %s;
      return {translated: translateMachineMessage(raw), failure: libraryFailureCopy({error_detail: raw}).reason};
    })()""" % json.dumps(diagnostic))
    assert shown == {"translated": "This video is unavailable.", "failure": "This video is unavailable."}


@pytest.mark.parametrize("phase", ["media", "classify", "write"])
@pytest.mark.parametrize("summary", [
    "The source came down, but the local media step tripped.",
    "YouTube did not expose a usable video for this source.",
])
@pytest.mark.parametrize(("message", "expected"), [
    ("HTTP Error 429: Too Many Requests", "YouTube kept refusing this one. Give it a few minutes, then retry it yourself."),
    ("Sign in to continue", "YouTube wouldn't hand this one over without a login. Retry with cookies?"),
    ("Members-only video", "YouTube kept this one behind members-only access."),
    ("This video is private", "This video is private or unavailable in your region."),
    ("Video is unavailable", "This video is unavailable."),
    ("This video is live", "YouTube is still live. Try again once the broadcast becomes a replay."),
    ("Requested format is not available", "Requested format is not available"),
])
def test_failure_cause_wins_over_phase_and_generic_summary(phase, summary, message, expected):
    data = {"source_url": "https://youtu.be/abcdefghijk", "failure_phase": phase, "error": summary,
            "error_detail": f"Command: yt-dlp --cookies browser.txt --ffmpeg-location bundled/bin\nERROR: [youtube] abcdefghijk: {message}"}
    result = run_js(f"libraryFailureCopy({json.dumps(data)})")
    assert result["reason"] == expected
    assert "ERROR: [youtube]" in result["detail"]


@pytest.mark.parametrize("diagnostic", [
    "ERROR: [youtube] abcdefghijk: Sign in to continue",
    "Command: yt-dlp https://youtu.be/abcdefghijk?token=fixture-secret\nERROR: Sign in to continue",
])
def test_failure_translation_keeps_extractor_or_url_context_without_exposing_it(diagnostic):
    result = run_js("""(() => {
      const data = {error_detail: %s};
      state.jobs = [{...data, id: 'context', state: 'failed'}];
      renderQueue({pending: []});
      openCaptureFailure('job:context');
      return {library: libraryFailureCopy(data), drawer: {
        reason: document.getElementById('captureFailureReason').textContent,
        detail: document.getElementById('captureFailureError').textContent}};
    })()""" % json.dumps(diagnostic))
    for surface in result.values():
        assert surface["reason"] == "YouTube wouldn't hand this one over without a login. Retry with cookies?"
        assert "fixture-secret" not in surface["detail"]
        assert "https://" not in surface["detail"]


@pytest.mark.parametrize("source", ["YouTube", "X", "Vimeo"])
def test_error_only_server_summary_keeps_source_name(source):
    summary = f"{source} wouldn't hand this one over without a login. Retry with cookies?"
    result = run_js("""(() => {
      const summary = %s;
      return {activity: activityErrorMessage(summary, 'media', {terminal: true}),
        library: libraryFailureCopy({error: summary, failure_phase: 'media'}).reason};
    })()""" % json.dumps(summary))
    assert result == {"activity": summary, "library": summary}


def test_failure_translation_does_not_treat_paths_or_url_parameters_as_the_cause():
    data = {"error": "The source came down, but the local media step tripped.", "failure_phase": "media",
            "error_detail": r"ERROR: [youtube] abcdefghijk: Requested format is not available at C:\Users\PrivateFixture\clip.mp4 https://example.test/media?cookies=fixture-secret"}
    result = run_js(f"libraryFailureCopy({json.dumps(data)})")
    assert result["reason"] == "Requested format is not available at <path> <url>"
    assert "PrivateFixture" not in result["detail"] and "fixture-secret" not in result["detail"]


def test_local_failure_uses_run_url_when_helper_omits_source_context():
    result = run_js("""(() => {
      refreshActivity = async () => {};
      const run = {id: 'local', label: 'YouTube video', url: 'https://youtu.be/abcdefghijk'};
      failLibraryRun(run, {data: {error_detail: 'ERROR: Sign in to continue'}});
      return run.reason;
    })()""")
    assert result == "YouTube wouldn't hand this one over without a login. Retry with cookies?"


@pytest.mark.parametrize("message", ["This video is private", "This video is blocked in your region"])
def test_private_or_region_error_survives_server_to_dashboard_translation(message, plain_error_from_text):
    summary = plain_error_from_text(f"ERROR: [youtube] abcdefghijk: {message}")
    expected = "This video is private or unavailable in your region."
    assert summary == expected
    result = run_js("""(() => {
      const summary = %s;
      return {activity: activityErrorMessage(summary, 'media', {terminal: true}),
        library: libraryFailureCopy({error: summary, failure_phase: 'media'}).reason};
    })()""" % json.dumps(summary))
    assert result == {"activity": expected, "library": expected}
