"""Dashboard follow-ups to the 3.12 run-through.

F1: an X post with a video saves its poster as thumbnail.jpg, so its Library
    row shows the picture instead of a grey "post" block, and the reader
    treats an X (or Reddit) video post as a video: a timed transcript, the
    transcript note, "Watch on X". Text and photo posts keep their look.
F2: the Sources paste box answers the site allowlist wall with
    "Allow <host>", as a Library capture row does, instead of a toast that
    sends you to Settings.
F3: (tests/test_bundled_whisper_model.py) the model status names no
    download size for the bundled copy.
F4: a jump into Settings from another tab waits for the Settings read, so
    the target lands at the top instead of short by the height of the lists
    that fill in above it (which left the heading under the usage card, or
    below the window in WebKit). Route-named blocks get the sections' scroll
    margin.

The dashboard checks run the product's own JavaScript in the Node vm harness
from test_dashboard_runthrough_fixes.py.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import index as index_mod
import server
import uoink_mcp_tools as tools
import x_extractor
from tests.test_dashboard_runthrough_fixes import DASHBOARD, _between, run_js

POSTER = "https://pbs.twimg.com/ext_tw_video_thumb/1890000000000000001/pu/img/sample.jpg"


def x_payload(tid: str, text: str, *, video: bool = False, gif: bool = False,
              photos: int = 0, parent: dict | None = None) -> dict:
    """A syndication-shaped post by a made-up account."""
    payload = {
        "id_str": tid, "text": text, "created_at": "2026-10-28T16:00:00.000Z",
        "user": {"name": "Example Studio", "screen_name": "example_studio"},
    }
    media = []
    if video or gif:
        media.append({"type": "animated_gif" if gif else "video", "media_url_https": POSTER,
                      "video_info": {"variants": [{"content_type": "video/mp4",
                                                   "url": f"https://video.twimg.com/{tid}.mp4"}]}})
    media += [{"type": "photo", "media_url_https": f"https://pbs.twimg.com/media/p{i}.jpg"}
              for i in range(photos)]
    if media:
        payload["mediaDetails"] = media
    if parent:
        payload.update(in_reply_to_status_id_str=parent["id_str"],
                       in_reply_to_screen_name="example_studio", parent=parent)
    return payload


def extract(payload: dict) -> dict:
    url = f"https://x.com/example_studio/status/{payload['id_str']}"
    result = x_extractor.extract_x_thread(url, _fetch=lambda _tid, timeout=20: payload)
    assert result["ok"], result
    return result


# ---- F1: the poster on the capture side ----------------------------------------

def test_poster_comes_from_the_video_and_never_from_text_or_photos():
    assert server._x_video_poster_url(extract(x_payload("11", "Clip", video=True))) == POSTER
    assert server._x_video_poster_url(extract(x_payload("12", "Loop", gif=True))) == POSTER
    assert server._x_video_poster_url(extract(x_payload("13", "Just words"))) is None
    assert server._x_video_poster_url(extract(x_payload("14", "Two photos", photos=2))) is None
    assert server._x_video_poster_url({"ok": True, "metadata": {}}) is None
    # An earlier post's video still counts when the shared one is text.
    root = x_payload("15", "The clip", video=True)
    assert server._x_video_poster_url(extract(x_payload("16", "Follow-up", parent=root))) == POSTER


@pytest.fixture
def x_route(tmp_path, monkeypatch):
    """POST /extract/x on a throwaway helper with a temp index and output root."""
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "output")
    monkeypatch.setattr(server, "_read_settings", lambda: {"x_text_capture_enabled": True})
    monkeypatch.setattr(server, "_classify_topic", lambda _meta: "Video craft")
    payloads = {}
    original = x_extractor.extract_x_thread
    monkeypatch.setattr(server.x_extractor, "extract_x_thread", lambda url, **_kw: original(
        url, _fetch=lambda tid, timeout=20: payloads[str(tid)]))
    downloads = []

    def post(payload):
        payloads[payload["id_str"]] = payload
        body = json.dumps({"url": f"https://x.com/example_studio/status/{payload['id_str']}"}).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/extract/x", data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Uoink-Token": server.TOKEN})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
        row = idx.get_yoink(data["video_id"]) if data.get("video_id") else None
        enriched = server._enrich_yoink_rows(idx, [row])[0] if row else None
        return data, enriched

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield post, downloads, monkeypatch
    finally:
        httpd.shutdown()
        idx.close()


def test_x_video_post_saves_its_poster_as_the_row_thumbnail(x_route):
    post, downloads, monkeypatch = x_route

    def fake_download(metadata, folder, **_kw):
        downloads.append((metadata, Path(folder)))
        (Path(folder) / "thumbnail.jpg").write_bytes(b"jpeg")
        return Path(folder) / "thumbnail.jpg"

    monkeypatch.setattr(server, "_download_thumbnail", fake_download)
    data, row = post(x_payload("21", "Ninety seconds on storyboards.", video=True))
    assert data["ok"] is True and data["metadata"]["has_video"] is True
    # The video path's own thumbnail download, into the capture's folder.
    assert downloads == [({"thumbnail": POSTER}, Path(row["folder"]))]
    assert row["thumbnail_path"] == str(Path(row["folder"]) / "thumbnail.jpg")
    assert row["source_type"] == "x_thread"

    # Text and photo posts fetch nothing and keep the neutral block.
    for payload in (x_payload("22", "Words only."), x_payload("23", "A photo.", photos=1)):
        data, row = post(payload)
        assert data["ok"] is True and row["thumbnail_path"] is None
    assert len(downloads) == 1


def test_a_poster_that_fails_never_fails_the_post(x_route):
    post, _downloads, monkeypatch = x_route

    def no_ffmpeg(_metadata, folder, **_kw):
        (Path(folder) / "thumbnail.raw").write_bytes(b"partial")
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(server, "_download_thumbnail", no_ffmpeg)
    data, row = post(x_payload("31", "Clip with a broken poster.", video=True))
    assert data["ok"] is True and data["video_id"]
    assert row["thumbnail_path"] is None
    assert not (Path(row["folder"]) / "thumbnail.raw").exists()


def test_mcp_x_capture_saves_the_poster_too(monkeypatch):
    tools.bind_backend(server)
    import page_extractor

    saved = []
    result = {"ok": True, "title": "Post", "tweets_captured": 1, "metadata": {"has_video": True}}
    monkeypatch.setattr(server, "_read_settings", lambda: {"x_text_capture_enabled": True})
    monkeypatch.setattr(x_extractor, "extract_x_thread", lambda _url: result)
    monkeypatch.setattr(page_extractor, "persist_page_yoink", lambda *_a, **_k: "x_1")
    monkeypatch.setattr(server, "_save_x_video_poster", lambda video_id, res: saved.append((video_id, res)))
    assert tools.uoink_x({"url": "https://x.com/a/status/1"})["video_id"] == "x_1"
    assert saved == [("x_1", result)]


# ---- F1: the row and the reader --------------------------------------------------

READER_ROWS = """
  const video = {video_id: "v1", source_type: "x_thread", platform: "x", has_transcript: true,
    transcript_source: "asr", asr_fallback_status: "completed", duration_seconds: 92,
    source_url: "https://x.com/example_studio/status/1", thumbnail_path: "C:/lib/v1/thumbnail.jpg"};
  const videoSidecar = {source_type: null, platform: "twitter", transcript_source: "asr",
    asr_fallback: {status: "completed", model: "base"},
    transcript: [{start: 0, end: 6, text: "Six cards before an editor."},
                 {start: 6, end: 13, text: "One sentence per card."}]};
  const silent = {video_id: "v2", source_type: "x_thread", platform: "x", has_transcript: false,
    transcript_source: null, asr_fallback_status: "model_not_downloaded",
    source_url: "https://x.com/example_studio/status/2"};
  const silentSidecar = {transcript_source: null, asr_fallback: {status: "model_not_downloaded", model: "base"},
    transcript: []};
  const text = {video_id: "x_1", source_type: "x_thread", platform: "x", has_transcript: false,
    transcript_source: null, asr_fallback_status: null, source_url: "https://x.com/example_studio/status/3"};
  const textSidecar = {source_type: "x_thread", platform: "x", metadata: {has_video: true}};
  const photo = {...text, video_id: "x_2", thumbnail_path: null};
  const reddit = {video_id: "r1", source_type: "reddit_thread", platform: "reddit", has_transcript: true,
    transcript_source: "captions", source_url: "https://www.reddit.com/r/example/comments/1/post/"};
"""


def test_x_video_post_reads_as_a_timed_transcript():
    out = run_js("(() => {" + READER_ROWS + """
      state.selectedYoinkMarkdown = "";
      state.selectedYoinkMarkdownState = "ready";
      state.selectedYoinkSidecar = videoSidecar;
      return {
        timed: isTimedMedia(video, videoSidecar),
        kind: mediaLabelFor(video, videoSidecar),
        link: sourceLinkLabel(video, videoSidecar),
        note: transcriptNoteText(video, videoSidecar),
        doc: readerDocumentHtml(video, videoSidecar),
        meta: readerMetaLine(video, videoSidecar),
        // Before the sidecar arrives, the row alone says it is a video.
        rowOnly: isTimedMedia(video, {}),
        // A sidecar alone says so too: the video path always writes
        // transcript_source, even as null.
        sidecarOnly: isTimedMedia({source_type: "x_thread", platform: "x"}, {transcript_source: null}),
        reddit: [isTimedMedia(reddit, {}), mediaLabelFor(reddit, {})],
      };
    })()""")
    assert out["timed"] is True and out["rowOnly"] is True and out["sidecarOnly"] is True
    assert out["kind"] == "x video"
    assert out["link"] == "Watch on X"
    assert out["note"].startswith("X didn't provide captions for this video, so Uoink transcribed the audio")
    assert out["doc"].count('class="reader-row reader-para"') == 1
    assert "Six cards before an editor. One sentence per card." in out["doc"]
    assert "1:32" in out["meta"]
    assert out["reddit"] == [True, "reddit video"]


def test_x_video_without_a_transcript_says_so_like_youtube():
    out = run_js("(() => {" + READER_ROWS + """
      state.settings = null;
      state.selectedYoinkMarkdown = "";
      state.selectedYoinkMarkdownState = "ready";
      state.selectedYoinkSidecar = silentSidecar;
      const youtube = {video_id: "y1", source_type: "video", platform: "youtube", has_transcript: false,
        asr_fallback_status: "model_not_downloaded"};
      return {
        note: transcriptNoteText(silent, silentSidecar),
        youtubeNote: transcriptNoteText(youtube, silentSidecar),
        doc: readerDocumentHtml(silent, silentSidecar),
        line: savedStateLine({...silent, health: {transcript: "missing", screenshots: "ok"}}),
        badge: healthException({transcript: "missing", screenshots: "ok"}, silent),
      };
    })()""")
    assert out["note"] == out["youtubeNote"].replace("YouTube", "X")
    assert "the local transcriber (Balanced) isn't on" in out["note"]
    assert "yet, so there is no transcript. Download it in Settings" in out["note"]
    assert "No transcript saved." in out["doc"]
    assert ">Saved</span>" in out["line"] and "no captions" in out["line"]
    assert ">No transcript</button>" in out["badge"]


def test_text_and_photo_posts_keep_their_look():
    out = run_js("(() => {" + READER_ROWS + """
      state.selectedYoinkMarkdown = "Ninety seconds on storyboards.";
      state.selectedYoinkMarkdownState = "ready";
      return {
        timed: [isTimedMedia(text, textSidecar), isTimedMedia(photo, {})],
        kind: mediaLabelFor(text, textSidecar),
        link: sourceLinkLabel(text, textSidecar),
        note: transcriptNoteText(text, textSidecar),
        doc: readerDocumentHtml(text, textSidecar),
        detail: savedRowDetail(text),
        chips: [sourceTypeLabel(text), sourceTypeLabel(photo), sourceTypeLabel(video), sourceTypeLabel(silent)],
        textCard: cardHtml(text),
        videoCard: cardHtml(video),
      };
    })()""")
    assert out["timed"] == [False, False]
    assert out["kind"] == "post" and out["link"] == "Read on X" and out["note"] == ""
    assert 'class="reader-prose markdown-rendered"' in out["doc"]
    assert out["detail"] == "post and thread"
    assert out["chips"] == ["post", "post", "video", "video"]
    assert '<span class="source-type-chip">post</span>' in out["textCard"]
    # The row's picture is its thumbnail.jpg, loaded by the existing path.
    assert '<img alt="" data-thumb-for="v1" class="hidden">' in out["videoCard"]
    assert '<span class="source-type-chip">video</span>' in out["videoCard"]


# ---- F2: Sources paste box ---------------------------------------------------------

PASTE_SETUP = """
      const calls = [];
      const toasts = [];
      let walls = 1;
      authFetch = async (path, opts = {}) => {
        calls.push([path, opts.method || "GET", opts.body ? JSON.parse(opts.body) : null]);
        if (path === "/extract/page" && walls > 0) {
          walls -= 1;
          const err = new Error("host 'www.example.com' is not in the allowlist.");
          err.data = {ok: false, code: "host_not_allowed"};
          throw err;
        }
        if (globalThis.failAdd && path === "/extract/page/allowlist" && opts.method === "POST") {
          const err = new Error("allowlist write failed"); err.data = {}; throw err;
        }
        return path === "/extract/page/allowlist" && !opts.method ? {ok: true, sites: []} : {ok: true};
      };
      showToast = (message) => toasts.push(message);
      refreshActivity = () => {};
      applyDetection({ok: true, source: "web_page", label: "Article / web page", endpoint: "/extract/page",
        payload_key: "url", canonical: "https://www.example.com/post", note: ""});
      const allow = els.universalCaptureAllow;
      const shown = () => ({text: allow.textContent, hidden: allow.classList.contains("hidden"),
        disabled: allow.disabled, note: els.universalCaptureNote.textContent});
"""


def test_paste_box_offers_allow_host_then_captures_again():
    out = run_js("(async () => {" + PASTE_SETUP + """
      await runUniversalCapture();
      const wall = {...shown(), toasts: [...toasts]};
      await allowUniversalCaptureSite();
      return {wall, after: shown(), calls, toasts};
    })()""")
    wall = out["wall"]
    assert wall["text"] == "Allow www.example.com" and wall["hidden"] is False
    assert wall["note"] == "That site isn't on your allowed pages list yet. Allow it to capture this page."
    assert wall["toasts"] == []
    # The same call Settings' Add makes, then the same link again.
    assert out["calls"] == [
        ["/extract/page", "POST", {"url": "https://www.example.com/post"}],
        ["/extract/page/allowlist", "POST", {"action": "add", "url_pattern": "www.example.com"}],
        ["/extract/page/allowlist", "GET", None],
        ["/extract/page", "POST", {"url": "https://www.example.com/post"}],
    ]
    assert out["toasts"] == ["Uoinking that article / web page. Track it in Activity."]
    assert out["after"]["hidden"] is True


def test_paste_box_allow_failure_keeps_the_offer_and_says_why():
    out = run_js("(async () => { globalThis.failAdd = true;" + PASTE_SETUP + """
      await runUniversalCapture();
      await allowUniversalCaptureSite();
      const failed = shown();
      // A new link takes the offer away.
      applyDetection({ok: true, source: "youtube_video", label: "YouTube video", endpoint: "/extract",
        payload_key: "url", canonical: "https://www.youtube.com/watch?v=abc", note: ""});
      return {failed, next: shown(), captures: calls.filter((c) => c[0] === "/extract/page").length};
    })()""")
    failed = out["failed"]
    assert failed["note"].startswith("Couldn't allow www.example.com: allowlist write failed")
    assert failed["text"] == "Allow www.example.com" and failed["hidden"] is False and failed["disabled"] is False
    assert out["captures"] == 1
    assert out["next"]["hidden"] is True


def test_paste_box_markup_wiring_and_shared_copy():
    row = _between(DASHBOARD, '<div class="universal-capture" id="universalCapture">', "</div>\n          <div")
    assert ('<button class="button hidden" type="button" id="universalCaptureAllow" '
            'aria-describedby="universalCaptureNote"></button>') in row
    assert 'els.universalCaptureAllow.addEventListener("click", allowUniversalCaptureSite);' in DASHBOARD
    # One wording for the wall; "Add it in Settings" is only the no-host fallback.
    assert DASHBOARD.count("Add it in Settings, then try again.") == 1
    assert "run.reason = allowlistWallCopy(run.allowHost);" in DASHBOARD


# ---- F4: Settings jumps --------------------------------------------------------------

REVEAL_SETUP = """
      const timers = [];
      window.setTimeout = (fn, ms) => { timers.push({fn, ms}); return timers.length; };
      window.matchMedia = () => ({matches: true});
      const scrolls = [];
      const picker = {focused: 0, focus() { this.focused += 1; }, hasAttribute: () => true};
      const target = {scrollIntoView: (opts) => scrolls.push(opts),
        querySelector: (sel) => sel === "[data-reveal-focus]" ? picker : null};
      const panel = {contains: (el) => el === target};
      const byId = document.getElementById;
      const fakes = {"tab-settings": panel, "settings-transcription-model": null, "transcription-model": target};
      document.getElementById = (id) => id in fakes ? fakes[id] : byId(id);
      const flush = async () => { for (let i = 0; i < 5; i += 1) await Promise.resolve(); };
      const run = async (ms) => {
        const due = timers.filter((t) => t.ms === ms && !t.done);
        due.forEach((t) => { t.done = true; t.fn(); });
        await flush();
      };
"""


def test_settings_jump_waits_for_the_settings_read():
    out = run_js("(async () => {" + REVEAL_SETUP + """
      let finish;
      revealSettingsSection("transcription-model", new Promise((resolve) => { finish = resolve; }));
      await flush();
      await run(0);
      const early = scrolls.length;
      finish();
      await flush();
      await run(0);
      return {early, scrolls, focused: picker.focused, cap: timers.filter((t) => t.ms === SETTINGS_REVEAL_WAIT_MS).length};
    })()""")
    assert out["early"] == 0
    assert out["scrolls"] == [{"block": "start", "behavior": "auto"}]
    assert out["focused"] == 1 and out["cap"] == 1


def test_settings_jump_never_waits_more_than_a_second_or_at_all_in_page():
    out = run_js("(async () => {" + REVEAL_SETUP + """
      revealSettingsSection("transcription-model", new Promise(() => {}));
      await flush();
      await run(0);
      const beforeCap = scrolls.length;
      await run(SETTINGS_REVEAL_WAIT_MS);
      await run(0);
      const afterCap = scrolls.length;
      // From Settings itself (an index link) nothing is loading.
      revealSettingsSection("transcription-model");
      await flush();
      await run(0);
      return {beforeCap, afterCap, inPage: scrolls.length, wait: SETTINGS_REVEAL_WAIT_MS};
    })()""")
    assert out == {"beforeCap": 0, "afterCap": 1, "inPage": 2, "wait": 1000}


def test_switching_tabs_hands_the_settings_read_to_the_jump():
    switch = _between(DASHBOARD, "function switchTab(tab, options = {}) {", "// Shows the screen a parsed route names")
    assert 'const settingsRead = tab === "settings" ? refreshSettings() : null;' in switch
    assert "revealSettingsSection(options.section, settingsRead);" in switch
    # An in-page jump (already on Settings) has nothing to wait for.
    route = _between(DASHBOARD, "function applyRoute(route) {", "function applyHashRoute()")
    assert 'else if (route.tab === "settings" && route.section) revealSettingsSection(route.section);' in route


def test_route_named_blocks_land_with_the_sections_margin():
    assert "scroll-margin-top: 16px;" in _between(DASHBOARD, ".settings-section {", "}")
    assert "scroll-margin-top: 16px;" in _between(DASHBOARD, "#tab-settings .setting-block[id] {", "}")
