import assert from "node:assert/strict";
import { makeEnv, jsonResponse, settle } from "./ext_fake_env.mjs";
import { popupEnv } from "./rehaul_popup_env.mjs";
const url = "https://www.youtube.com/watch?v=abc123def45";
const playlist = "https://www.youtube.com/playlist?list=PL_example";
const sender = { id: "test-extension-id", url: "chrome-extension://test-extension-id/popup.html" };
const plain = value => JSON.parse(JSON.stringify(value));
function model() {
  const env = makeEnv(); env.load("lib/extract.js"); env.load("lib/popup-captures.js");
  return { env, model: env.ctx.PopupCaptures };
}
const groups = {
  async steps() {
    const { model: m } = model();
    for (const [phase, index] of [["metadata", 0], ["rate_limit", 1], ["download", 2], ["captions", 3], ["whisper", 3], ["screenshots", 4], ["write", 4]]) {
      const row = m.steps({ state: "failed", failure_phase: phase, current_video_phase: "done" });
      assert.equal(row.index, index); assert.equal(row.segments[index], "fail");
      assert.match(row.label, new RegExp(`${index + 1} of 5`));
    }
    assert.match(m.steps({ state: "pending" }).label, /Waiting · one YouTube/);
    assert.equal(m.steps({ state: "pending", last_error: "youtube_rate_limit" }).failed, true);
    assert.equal(m.steps({ state: "running", phase: "future-phase" }).index, -1);
    assert.equal(m.steps({ state: "running", phase: "future-phase" }).label, "Capturing");
    assert.equal(m.steps({ state: "failed" }).label, "Failed");
    assert.equal(m.steps({ state: "failed" }).segments.join(","), "todo,todo,todo,todo,todo");
    assert.equal(m.steps({ state: "completed" }).segments.join(","), "done,done,done,done,done");
    const reason = m.safeError({ error_detail: "Command: private\nERROR: old\nERROR: HTTP 429 https://secret.example/ api_key=private" });
    assert.match(reason, /HTTP 429/); assert.doesNotMatch(reason, /secret.example|private|old/);
  },
  async merge() {
    const { model: m } = model();
    const now = Date.now();
    const worker = { busy: true, current: { id: "worker", kind: "extract", url, startedAt: now - 2000 } };
    const live = [{ source_url: url, phase: "transcript", started_at: new Date(now - 1000).toISOString() }];
    let rows = m.merge({ worker, live }); assert.equal(rows.length, 1); assert.equal(rows[0].model.index, 3);
    rows = m.merge({ worker, live: [{ ...live[0], started_at: new Date(Math.floor((now - 2000) / 1000) * 1000).toISOString() }] });
    assert.equal(rows[0].model.index, 3, "second-rounded live timestamps keep the helper's phase");
    rows = m.merge({ jobs: [{ id: "helper", source_url: url, state: "failed", failure_phase: "download", error_detail: "ERROR: 429", updated_at: new Date(now - 2000).toISOString() }],
      pending: [{ pending_id: 12, url, status: "pending", updated_at: new Date(now).toISOString() }] });
    assert.equal(rows.length, 1); assert.equal(rows[0].model.failed, true); assert.equal(rows[0].pending.pending_id, 12);
    rows = m.merge({ failures: [{ url, failed_at: new Date(now - 1000).toISOString(), error: "old" }], worker });
    // A later failure must supersede a stopped worker's older request.
    assert.equal(rows[0].model.failed, true);
    rows = m.merge({ worker: { busy: true, current: { ...worker.current, startedAt: now } }, failures: [{ url, error: "old", failed_at: new Date(now - 2000).toISOString() }] });
    assert.equal(rows[0].model.failed, false); assert.equal(rows[0].state, "running");
    rows = m.merge({ failures: [{ url, failed_at: new Date(now - 2000).toISOString(), failure_phase: "download", error_detail: "ERROR: old" }],
      jobs: [{ id: "complete", source_url: url, state: "completed", completed_at: new Date(now - 1000).toISOString() }],
      pending: [{ url, pending_id: 9, status: "pending", created_at: new Date(now).toISOString() }] });
    assert.equal(rows[0].model.failed, false, "a new pending capture doesn't inherit an error from before the last save");
    rows = m.merge({ worker: { popup_capture_results: [{ id: "worker-id", url, ok: true, finishedAt: now, folder: "C:/Fixture/saved" }] },
      recent: [{ video_id: "abc123def45", folder: "C:/Fixture/saved", title: "Saved title" }] });
    assert.equal(rows.length, 1); assert.equal(rows[0].video_id, "abc123def45");
    rows = m.merge({ worker: { popup_capture_results: [{ id: "w", url: "https://example.com/page", ok: true, folder: "/fixture/page", finishedAt: now }] },
      recent: [{ video_id: "page-1", folder: "/fixture/page", title: "Page" }] });
    assert.equal(rows.length, 1, "a page's URL and saved folder join one row");
    assert.equal(rows[0].video_id, "page-1");
    assert.equal(m.itemId({ id: "job-123" }), "");
    assert.equal(m.slug({ folder: "C:\\Fixture\\slug" }), "slug");
    assert.equal(m.merge({ jobs: Array.from({ length: 10 }, (_, i) => ({ id: i, state: "running" })) }).length, 6);
  },
  async render() {
    const env = await popupEnv();
    assert.equal(env.el("status").textContent, "Running");
    assert.equal(env.el("uoink-current-btn").textContent, "Uoink this video");
    env.setData({ jobs: [{ id: "j", source_url: url, title: "<script>untrusted</script>", state: "failed", failure_phase: "download", error_detail: "ERROR: HTTP 429" }] });
    const row = env.rows()[0]; assert.match(row.textContent, /Failed at video \(3 of 5\)/); assert.match(row.textContent, /429/);
    assert.equal(row.querySelectorAll("i").length, 5);
    const button = row.querySelector("button"); assert.equal(button.textContent, "Retry now"); button.focus();
    env.ctx.renderCaptures(); assert.equal(env.document.activeElement, button); assert.equal(env.rows()[0], row);
    env.setData({ jobs: [], recent: [{ video_id: "a/b", url, folder: "/fixture/example", title: "Saved" }] });
    assert.match(env.rows()[0].querySelector("a").href, /#item\/a%2Fb$/);
    assert.equal(env.copyButton().textContent, "Copy Markdown");
    env.setData({ jobs: [{ id: "j", source_url: url, state: "pending" }], recent: [] });
    assert.match(env.rows()[0].textContent, /Waiting · one YouTube capture at a time/);
    for (const state of ["running", "failed"]) {
      env.setData({ jobs: [{ id: "unknown", source_url: url, state, phase: "future-phase" }], recent: [] });
      const text = env.rows()[0].textContent;
      assert.match(text, state === "failed" ? /Failed/ : /Capturing/);
      assert.doesNotMatch(text, /not reported|Capturing ·|Failed ·|Transcript:/, "unknown step and transcript source are omitted");
    }
    const offline = await popupEnv({ platform: "Linux", routes: { "/health": () => { throw new TypeError("offline"); } } });
    assert.equal(offline.el("status").textContent, "Offline"); assert.match(offline.el("status-help").textContent, /Terminal/);
    assert.doesNotMatch(offline.el("status-help").textContent, /Start Menu/);
    const unsupported = await popupEnv({ tab: { id: 1, url: "chrome://extensions", title: "Extensions" } });
    assert.match(unsupported.el("current-source-preview").textContent, /isn't supported/);
    assert.equal(unsupported.el("paste-add").disabled, false);
  },
  async routing() {
    const calls = [];
    const env = await popupEnv({ onSend: msg => { calls.push(msg); return { ok: true, id: "accepted" }; } });
    for (const [value, route] of [[playlist, "playlist"], [url + "&list=PL_example", "video"], [url, "video"], ["https://example.com/article", "page"], ["https://example.com/feed.xml", "podcast"], ["https://x.com/a/status/1720000000000000000", "x_post"]]) {
      env.el("paste-url").value = value;
      await env.ctx.submitPaste({ preventDefault() {} });
      assert.equal(calls.at(-1).job.route, route);
      assert.equal(calls.at(-1).job.url, env.ctx.STC.classifyCaptureUrl(value).canonical);
      assert.equal(env.el("paste-url").value, "");
    }
    const count = calls.length;
    env.el("paste-url").value = "javascript:alert(1)"; await env.ctx.submitPaste({ preventDefault() {} });
    assert.equal(calls.length, count); assert.equal(env.el("paste-url").getAttribute("aria-invalid"), "true");
    const retried = [];
    const retry = await popupEnv({ routes: { "/queue/retry-now": (_u, init) => { retried.push(JSON.parse(init.body)); return jsonResponse({ ok: true }); } } });
    retry.setData({ pending: [{ pending_id: 42, url, status: "failed", failure_phase: "transcript" }] });
    retry.rows()[0].querySelector("button").click(); await settle();
    assert.deepEqual(retried, [{ pending_id: 42 }]);
    env.setData({ jobs: [{ id: "watch-in-playlist", source_url: url + "&list=PL_example", state: "failed" }] });
    env.rows()[0].querySelector("button").click(); await settle();
    assert.equal(calls.at(-1).job.route, "video", "Retry also classifies a watch link as a video");
    assert.equal(calls.at(-1).job.url, url);
  },
  async worker() {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const requests = [];
    const env = makeEnv({ fetch: (u, init) => {
      const p = new URL(u).pathname; requests.push(p);
      if (p === "/token") return jsonResponse({ token: "fixture" });
      if (p === "/health") return jsonResponse({ ok: true });
      if (p === "/playlist/start") { assert.equal(JSON.parse(init.body).url, playlist); return gate; }
      throw new TypeError("fixture");
    }}); env.load("background.js"); await settle();
    const answer = await env.dispatch({ type: "popupCapture", job: { route: "playlist", url: playlist, title: "Playlist" } }, sender);
    assert.equal(answer.ok, true); await settle();
    assert.equal(env.store.session.busy, true);
    const duplicate = await env.dispatch({ type: "popupCapture", job: { route: "playlist", url: playlist } }, sender);
    assert.equal(duplicate.duplicate, true);
    release(jsonResponse({ ok: true, job_id: "playlist-job" })); await settle();
    assert.equal(requests.filter(p => p === "/playlist/start").length, 1);
    assert.equal(env.store.session.popup_capture_results[0].job_id, "playlist-job");
    assert.equal(env.store.session.popup_capture_results[0].queued, true);
    assert.equal(env.notifications.length, 0);
  },
  async playlist_primary() {
    for (const outcome of ["success", "failure", "throw"]) {
      let release, reject;
      const gate = new Promise((resolve, fail) => { release = resolve; reject = fail; });
      const worker = makeEnv({ fetch: (u, init) => {
        const path = new URL(u).pathname;
        if (path === "/token") return jsonResponse({ token: "fixture" });
        if (path === "/health") return jsonResponse({ ok: true });
        if (path === "/playlist/start") { assert.equal(JSON.parse(init.body).url, playlist); return gate; }
        throw new Error(`Unexpected worker request: ${path}`);
      }});
      worker.load("background.js"); await settle();
      const options = { store: worker.store, tab: { id: 7, url: playlist, title: "A playlist" },
        routes: { "/playlist/start": () => gate },
        onSend: msg => worker.dispatch(msg, sender) };
      const popup = await popupEnv(options);
      let returned = false;
      const request = popup.ctx.runPopupUoinkCurrent().then(() => { returned = true; });
      await settle();
      assert.equal(returned, true, "primary playlist capture returns before the preview responds");
      assert.equal(popup.sent.filter(m => m.type === "popupCapture").length, 1);
      assert.equal(worker.store.session.current.usePlaylist, true);
      assert.equal(worker.store.session.busy, true);
      assert.equal(popup.fetches.some(u => new URL(u).pathname === "/playlist/start"), false);
      await popup.ctx.refreshQueue();
      assert.equal(popup.el("uoink-current-btn").disabled, true);
      assert.equal(popup.rows().length, 1);
      assert.match(popup.rows()[0].textContent, /Capturing/);
      popup.events.unload(); // Nothing in this popup runs when the preview answers.
      const reopened = await popupEnv(options);
      assert.equal(reopened.el("uoink-current-btn").disabled, true);
      reopened.events.unload();
      if (outcome === "throw") reject(new TypeError("Failed to fetch"));
      else release(jsonResponse(outcome === "success" ? { ok: true, job_id: "playlist-job" }
        : { ok: false, error: "Playlist preview unavailable", failure_phase: "metadata" }));
      await request; await settle();
      const result = worker.store.session.popup_capture_results[0];
      assert.equal(result.route, "playlist");
      assert.equal(result.ok, outcome === "success");
      const after = await popupEnv(options);
      assert.equal(after.rows().length, 1);
      if (outcome === "success") {
        assert.equal(result.job_id, "playlist-job"); assert.equal(result.queued, true);
        assert.match(after.rows()[0].textContent, /Waiting/);
      } else {
        assert.equal(after.rows()[0].querySelector("button").textContent, "Retry now");
        if (outcome === "failure") assert.match(after.rows()[0].textContent, /Playlist preview unavailable/);
      }
      after.events.unload();
    }
  },
  async x_primary() {
    const postUrl = "https://x.com/a/status/1720000000000000000";
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const worker = makeEnv({ fetch: u => {
      const path = new URL(u).pathname;
      if (path === "/token") return jsonResponse({ token: "fixture" });
      if (path === "/health") return jsonResponse({ ok: true });
      if (path === "/extract/x") return gate;
      throw new Error(`Unexpected worker request: ${path}`);
    } });
    worker.load("background.js"); await settle();
    const options = { store: worker.store, tab: { id: 7, url: postUrl, title: "An X post" },
      routes: { "/extract/x": () => gate }, onSend: msg => worker.dispatch(msg, sender) };
    const popup = await popupEnv(options);
    let returned = false;
    const request = popup.ctx.runPopupUoinkCurrent().then(() => { returned = true; });
    await settle();
    assert.equal(returned, true, "current-tab X capture returns before the text request answers");
    assert.equal(worker.store.session.current.useXPost, true);
    assert.equal(popup.fetches.some(u => new URL(u).pathname === "/extract/x"), false);
    assert.equal(popup.el("uoink-current-btn").disabled, true);
    // A paste of this same post joins the current-tab request.
    popup.el("paste-url").value = postUrl;
    await popup.ctx.submitPaste({ preventDefault() {} });
    assert.equal(worker.store.session.queue.length, 0);
    popup.events.unload();
    const reopened = await popupEnv(options);
    assert.equal(reopened.el("uoink-current-btn").disabled, true);
    reopened.events.unload();
    release(jsonResponse({ ok: true, video_id: "x-post-1", title: "Saved thread", tweets_captured: 2 }));
    await request; await settle();
    assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/extract/x").length, 1);
    assert.equal(worker.store.session.popup_capture_results[0].ok, true);
    const after = await popupEnv(options);
    assert.equal(after.el("uoink-current-btn").disabled, false);
    assert.match(after.rows()[0].querySelector("a").href, /#item\/x-post-1$/);
    after.events.unload();
  },
  async x_feedback() {
    const postUrl = "https://x.com/a/status/1720000000000000000";
    for (const outcome of ["failure", "full", "empty", "disabled"]) {
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      const worker = makeEnv({ fetch: u => {
        const path = new URL(u).pathname;
        if (path === "/token") return jsonResponse({ token: "fixture" });
        if (path === "/health") return jsonResponse({ ok: true });
        if (path === "/extract/x") return jsonResponse(["empty", "disabled"].includes(outcome)
          ? { ok: false, code: outcome }
          : { ok: true, video_id: "x-post-1", tweets_captured: 2, metadata: { has_video: true } });
        if (path === "/queue/status") return gate;
        if (path === "/extract") return jsonResponse({ ok: false, error: "Video unavailable", failure_phase: "download" });
        throw new Error(`Unexpected worker request: ${path}`);
      } });
      worker.load("background.js"); await settle();
      const popup = await popupEnv({ store: worker.store, tab: { id: 7, url: postUrl, title: "An X post" },
        onSend: msg => worker.dispatch(msg, sender) });
      await popup.ctx.runPopupUoinkCurrent(); await settle();
      assert.equal(worker.fetches.some(u => new URL(u).pathname === "/extract"), false,
        "video requests wait for the helper's queue-room check, including text-disabled/empty posts");
      release(jsonResponse({ ok: true, pending_count: outcome === "failure" ? 0 : 5 }));
      await settle(); await popup.ctx.refreshQueue(); await settle();
      const toast = popup.el("popup-toast").textContent;
      if (outcome === "failure") assert.match(toast, /Saved 2 posts\. Video:.*Video unavailable/);
      else {
        assert.match(toast, /queue (?:is )?full/i);
        assert.equal(worker.fetches.some(u => new URL(u).pathname === "/extract"), false);
      }
      if (["failure", "full"].includes(outcome)) {
        assert.match(toast, /Saved 2 posts/);
        const textResult = worker.store.session.popup_capture_results.find(r => r.route === "x_post");
        assert.equal(textResult.ok, true);
        assert.equal(textResult.video_id, "x-post-1");
      }
      popup.events.unload();
    }
  },
  async x_posts() {
    const postUrl = "https://x.com/a/status/1720000000000000000";
    const text = { ok: true, video_id: "x-post-1", title: "Saved thread",
      tweets_captured: 2, metadata: { has_video: true } };
    for (const entry of ["paste", "primary"]) for (const outcome of ["success", "failure", "throw", "full", "text_only", "text_failed", "disabled", "empty"]) {
      let release, reject;
      const gate = new Promise((resolve, fail) => { release = resolve; reject = fail; });
      const worker = makeEnv({ fetch: u => {
        const path = new URL(u).pathname;
        if (path === "/token") return jsonResponse({ token: "fixture" });
        if (path === "/health") return jsonResponse({ ok: true });
        if (path === "/queue/status") return jsonResponse({ ok: true, pending_count: outcome === "full" ? 5 : 0 });
        if (path === "/extract/x") return jsonResponse(outcome === "text_only" ? { ...text, metadata: {} }
          : outcome === "text_failed" ? { ok: false, error: "X refused the post" }
          : ["disabled", "empty"].includes(outcome) ? { ok: false, code: outcome } : text);
        if (path === "/extract") return gate;
        throw new Error(`Unexpected worker request: ${path}`);
      }});
      worker.load("background.js"); await settle();
      const popup = await popupEnv({ store: worker.store, tab: { id: 7, url: postUrl, title: "An X post" },
        onSend: msg => worker.dispatch(msg, sender) });
      if (entry === "primary") await popup.ctx.runPopupUoinkCurrent();
      else {
        popup.el("paste-url").value = postUrl;
        await popup.ctx.submitPaste({ preventDefault() {} });
      }
      popup.events.unload();
      await settle();
      const textSaved = !["text_failed", "disabled", "empty"].includes(outcome);
      const resultForText = () => worker.store.session.popup_capture_results?.find(r => r.route === "x_post");
      if (textSaved) {
        assert.equal(resultForText()?.ok, true, "the saved posts finish before their video");
        assert.equal(resultForText().video_id, text.video_id);
        assert.equal(resultForText().folder, text.folder);
        assert.match(resultForText().message, /Saved 2 posts/);
      }
      if (["success", "failure", "throw"].includes(outcome)) {
        assert.equal(worker.store.session.current.saveOnly, true);
        assert.equal(worker.ctx.STC.queueJobRoute(worker.store.session.current), "video");
      }
      if (outcome === "throw") reject(new TypeError("Failed to fetch"));
      else release(jsonResponse(outcome === "failure"
        ? { ok: false, error: "Video unavailable", failure_phase: "download", error_detail: "ERROR: Video unavailable" }
        : { ok: true, video_id: "x-video-1", folder: "/fixture/x-video-1", title: "Saved video" }));
      await settle();
      assert.equal(worker.store.session.busy, false);
      assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/extract/x").length, 1);
      assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/extract").length,
        ["full", "text_only", "text_failed"].includes(outcome) ? 0 : 1);
      if (!textSaved) {
        assert.equal(resultForText().ok, outcome !== "text_failed");
        continue;
      }
      assert.equal(resultForText().ok, true, "video failures cannot turn saved text into a failed capture");
      assert.equal(resultForText().video_id, text.video_id);
      assert.equal(resultForText().error_detail, undefined);
      assert.equal(worker.sent.some(m => m.type === "copyToClipboard"), false);
      assert.equal(worker.tabsCreated.length, 0);
      const failures = worker.store.local.yoink_recent_failures || [];
      assert.equal(failures.some(f => f.route === "x_post"), false);
      if (outcome === "failure") {
        assert.equal(failures.length, 1); assert.equal(failures[0].route, "video"); assert.equal(failures[0].saveOnly, true);
      }
      const reopened = await popupEnv({ store: worker.store, onSend: msg => worker.dispatch(msg, sender), routes: {
        "/recent": () => jsonResponse({ ok: true, recent: [{ video_id: text.video_id,
          title: text.title, source_type: "x_thread", url: postUrl, folder: "/fixture/x-post-1" }] }),
        "/mcp/v1/tools/call": (_u, init) => {
          assert.deepEqual(JSON.parse(init.body), { name: "get_uoink_corpus", arguments: { slug: "x-post-1" } });
          return jsonResponse({ result: { structuredContent: { ok: true, corpus_md: "# Saved thread" } } });
        },
      } });
      const savedRow = reopened.rows().find(row => row.querySelector("a")?.href.endsWith("#item/x-post-1"));
      assert.ok(savedRow, "Read stays available for the saved posts after their video fails");
      assert.match(savedRow.textContent, /Done/);
      assert.equal(savedRow.querySelector("button").textContent, "Copy Markdown");
      assert.equal(savedRow.querySelector("button").disabled, false);
      savedRow.querySelector("button").click(); await settle();
      assert.equal(reopened.clipboard.at(-1), "# Saved thread");
      if (["failure", "throw", "full"].includes(outcome)) {
        const failedRow = reopened.rows().find(row => row.querySelector("button")?.textContent === "Retry now");
        assert.ok(failedRow, "the video has its own retry");
        failedRow.querySelector("button").click(); await settle();
        const retry = reopened.sent.find(m => m.type === "popupCapture").job;
        assert.equal(retry.route, "video"); assert.equal(retry.saveOnly, true);
        assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/extract/x").length, 1);
      }
      reopened.events.unload();
    }
  },
  async source_labels() {
    for (const [value, expected] of [
      [url, "video"], [playlist, "playlist"],
      ["https://www.youtube.com/shorts/abc123def45", "short video"],
      ["https://www.reddit.com/r/test/comments/abc123/a_thread/", "thread"],
      ["https://x.com/a/status/1720000000000000000", "post"],
      ["https://x.com/a/article/1900000000001", "article"],
      ["https://example.com/feed.xml", "podcast"], ["https://example.com/story", "page"],
    ]) {
      const env = await popupEnv({ tab: { id: 7, url: value, title: "Fixture source" } });
      const source = env.ctx.STC.classifyCaptureUrl(value);
      assert.equal(source.label, expected);
      assert.equal(env.el("uoink-current-btn").textContent, `Uoink this ${expected}`);
      const route = source.action === "x_video" ? "x_post" : source.action === "x_article" ? "page" : source.action;
      const flags = { page: "usePage", reddit: "useReddit", playlist: "usePlaylist", podcast: "usePodcast", x_post: "useXPost" };
      const job = { kind: "extract", url: source.canonical, startedAt: Date.now() };
      if (flags[route]) job[flags[route]] = true;
      env.ctx.applyCaptureQueueState({ busy: true, current: job, queue: [] });
      assert.equal(env.el("uoink-current-btn").disabled, true);
      env.ctx.applyCaptureQueueState({ busy: false, current: null, queue: [] });
      assert.equal(env.el("uoink-current-btn").textContent, `Uoink this ${expected}`);
      assert.equal(env.el("uoink-current-btn").disabled, false);
      env.events.unload();
    }
  },
  async current_tab_queue() {
    for (const [value, flag] of [
      ["https://x.com/a/status/1720000000000000000", "useXPost"],
      ["https://example.com/feed.xml", "usePodcast"],
    ]) {
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      const env = await popupEnv({ tab: { id: 7, url: value, title: "Current tab" }, onSend: () => gate });
      env.el("paste-url").value = value;
      const adding = env.ctx.submitPaste({ preventDefault() {} });
      await settle();
      assert.equal(env.el("uoink-current-btn").disabled, true, "hold the current button while paste awaits worker acknowledgement");
      await env.ctx.ping();
      assert.equal(env.el("uoink-current-btn").disabled, true, "health checks cannot release an in-flight hand-off");
      env.el("uoink-current-btn").click();
      assert.equal(env.sent.filter(m => m.type === "popupCapture").length, 1);
      const current = { kind: "extract", url: value, startedAt: Date.now(), [flag]: true };
      Object.assign(env.store.session, { busy: true, current, queue: [] });
      release({ ok: true, id: "accepted" }); await adding;
      assert.equal(env.el("uoink-current-btn").disabled, true);
      Object.assign(env.store.session, { busy: false, current: null, queue: [current] });
      await env.ctx.refreshQueue();
      assert.equal(env.el("uoink-current-btn").disabled, true, "a waiting capture also holds this tab");
      Object.assign(env.store.session, { queue: [] }); await env.ctx.refreshQueue();
      assert.equal(env.el("uoink-current-btn").disabled, false);
      env.events.unload();
    }
  },
  async podcast_primary() {
    const feed = "https://example.com/feed.xml";
    for (const outcome of ["success", "failure", "throw"]) {
      let release, reject;
      const gate = new Promise((resolve, fail) => { release = resolve; reject = fail; });
      const worker = makeEnv({ fetch: (u, init) => {
        const path = new URL(u).pathname;
        if (path === "/token") return jsonResponse({ token: "fixture" });
        if (path === "/health") return jsonResponse({ ok: true });
        if (path === "/podcasts/feeds") {
          assert.deepEqual(JSON.parse(init.body), { feed_url: feed });
          return gate;
        }
        throw new Error(`Unexpected worker request: ${path}`);
      }});
      worker.load("background.js"); await settle();
      const options = { store: worker.store, tab: { id: 7, url: feed, title: "A podcast" },
        onSend: msg => worker.dispatch(msg, sender) };
      const popup = await popupEnv(options);
      let returned = false;
      const request = popup.ctx.runPopupUoinkCurrent().then(() => { returned = true; });
      await settle();
      assert.equal(returned, true, "primary feed action returns while the helper is still working");
      assert.equal(worker.store.session.current.usePodcast, true);
      assert.equal(popup.el("uoink-current-btn").disabled, true);
      assert.equal(popup.fetches.some(u => new URL(u).pathname === "/podcasts/feeds"), false);
      popup.events.unload();
      const reopened = await popupEnv(options);
      assert.equal(reopened.el("uoink-current-btn").disabled, true);
      reopened.events.unload();
      if (outcome === "throw") reject(new TypeError("Failed to fetch"));
      else release(jsonResponse(outcome === "success" ? { ok: true, feed_url: feed }
        : { ok: false, error: "Feed unavailable", failure_phase: "metadata" }));
      await request; await settle();
      const result = worker.store.session.popup_capture_results[0];
      assert.equal(result.route, "podcast"); assert.equal(result.ok, outcome === "success");
      assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/podcasts/feeds").length, 1);
      const after = await popupEnv(options);
      assert.equal(after.el("uoink-current-btn").disabled, false);
      if (outcome !== "success") assert.equal(after.rows()[0].querySelector("button").textContent, "Retry now");
      after.events.unload();
    }
  },
  async podcast_feedback() {
    const savedMessage = "Podcast feed saved. Uoink will watch metadata; audio stays off.";
    for (const entry of ["primary", "discovered", "paste"]) {
      // Discovered RSS/Atom links are authoritative even without URL hints.
      const feed = entry === "discovered" ? "https://example.com/syndication" : "https://example.com/feed.xml";
      for (const success of [true, false]) {
        let release;
        const gate = new Promise(resolve => { release = resolve; });
        const worker = makeEnv({ fetch: (u, init) => {
          const path = new URL(u).pathname;
          if (path === "/token") return jsonResponse({ token: "fixture" });
          if (path === "/health") return jsonResponse({ ok: true });
          if (path === "/podcasts/feeds") {
            assert.deepEqual(JSON.parse(init.body), { feed_url: feed });
            return gate;
          }
          throw new Error(`Unexpected worker request: ${path}`);
        }});
        worker.load("background.js"); await settle();
        const popup = await popupEnv({ store: worker.store,
          tab: { id: 7, url: entry === "primary" ? feed : "https://example.com/show", title: "A podcast" },
          onSend: msg => worker.dispatch(msg, sender) });
        if (entry === "discovered") {
          popup.ctx.chrome.scripting = { executeScript: async () => [{ result: feed }] };
          await popup.ctx.detectCurrentSource();
          assert.equal(popup.el("uoink-podcast-btn").classList.contains("hidden"), false);
          await popup.ctx.runAddPodcastFeed();
        } else if (entry === "paste") {
          popup.el("paste-url").value = feed;
          await popup.ctx.submitPaste({ preventDefault() {} });
        } else await popup.ctx.runPopupUoinkCurrent();
        await settle();
        assert.doesNotMatch(popup.el("popup-toast").textContent, /Podcast feed saved/,
          `${entry}: handing off a request is not a saved feed`);
        assert.equal(popup.fetches.some(u => new URL(u).pathname === "/podcasts/feeds"), false);
        release(jsonResponse(success ? { ok: true, feed_url: feed }
          : { ok: false, error: "Feed unavailable", failure_phase: "metadata" }));
        await settle(); await popup.ctx.refreshQueue(); await settle();
        const result = worker.store.session.popup_capture_results[0];
        assert.equal(result.ok, success);
        assert.equal(worker.fetches.filter(u => new URL(u).pathname === "/podcasts/feeds").length, 1);
        if (success) {
          assert.equal(result.message, savedMessage, `${entry}: the persisted worker result describes metadata watching`);
          assert.equal(popup.el("popup-toast").textContent, savedMessage);
        } else {
          assert.match(popup.el("popup-toast").textContent, /Feed unavailable/);
          assert.doesNotMatch(popup.el("popup-toast").textContent, /Podcast feed saved/);
          assert.equal(popup.rows()[0].querySelector("button").textContent, "Retry now");
        }
        popup.events.unload();
      }
    }
  },
  async stream() {
    for (const outcome of ["eof", "http", "throw"]) {
      const { env, model: m } = model(); env.ctx.TextDecoder = TextDecoder;
      const events = [], states = []; let calls = 0, signal;
      const stream = m.stream({ connect: async sig => {
        calls++; signal = sig;
        if (outcome === "throw") throw new TypeError("offline");
        if (outcome === "http") return { ok: false, status: 503 };
        let chunk = 0;
        const frames = ["event: snapshot\r\ndata: {\"active\":[],", "\"recent\":[]}\r\n\r\nevent: job\ndata: {\"id\":\"j\"}\n\n"];
        return { ok: true, body: { getReader: () => ({ read: async () => chunk < frames.length ? { value: new TextEncoder().encode(frames[chunk++]), done: false } : { done: true }, cancel: async () => {} }) } };
      }, onEvent: (e, d) => events.push([e, d]), onState: s => states.push(s) });
      stream.start(); stream.start(); await settle(); assert.equal(calls, 1);
      assert.equal(env.timeouts.size, 1); assert.equal(states.at(-1), "reconnecting");
      if (outcome === "eof") assert.deepEqual(events.map(e => e[0]), ["snapshot", "job"]);
      const timer = [...env.timeouts.values()][0]; stream.stop(); assert.equal(env.timeouts.size, 0);
      await timer(); assert.equal(calls, 1);
      stream.start(); await settle(); assert.equal(calls, 2); stream.stop();
    }
    const env = await popupEnv();
    env.ctx.handleSseEvent("snapshot", { active: [{ id: "j", source_url: url, state: "running", phase: "download" }], recent: [] });
    env.ctx.handleSseEvent("job", { id: "j", source_url: url, state: "failed", failure_phase: "transcript" });
    assert.match(env.rows()[0].textContent, /Failed at transcript/);
    env.events.unload(); assert.equal(env.intervals.size, 0);
  },
  async picker() {
    const payload = { title: "Choose", folder: "/fixture/choose", yoink_md: "# Text\n![one](/fixture/one.jpg)\n![two](/fixture/two.jpg)", corpus_md_paste: "# Text\n![one](data:image/png;base64,ONE)\n![two](data:image/png;base64,TWO)" };
    const env = await popupEnv({ store: { local: { pending_picker: payload }, sync: {}, session: {} } });
    const host = env.el("pending-picker"); assert.match(host.textContent, /Choose screenshots/);
    host.querySelectorAll("input")[1].checked = false; host.querySelector("button").click(); await settle();
    assert.match(env.clipboard[0], /ONE/); assert.doesNotMatch(env.clipboard[0], /TWO/);
    assert.equal(env.store.local.pending_picker, undefined);
    assert.ok(env.el("open-library"));
  },
  async sessions() {
    let active = null; const calls = [];
    const env = await popupEnv({ routes: {
      "/session/active": () => jsonResponse({ ok: true, session: active }),
      "/session/list": () => jsonResponse({ ok: true, sessions: [] }),
      "/session/start": (_u, init) => { calls.push(JSON.parse(init.body)); active = {session_id:"research-1",name:"Research",video_count:2}; return jsonResponse({ok:true}); },
      "/session/close": (_u, init) => { calls.push(JSON.parse(init.body)); active = null; return jsonResponse({ok:true,corpus_md:"# Research corpus"}); },
      "/session/cancel": (_u, init) => { calls.push(JSON.parse(init.body)); active = null; return jsonResponse({ok:true}); },
    }});
    env.el("session-name").value = "Research";
    await env.ctx.researchSessionAction("start");
    assert.deepEqual(calls[0], {name:"Research"}); assert.equal(env.el("session-active").hidden, false);
    assert.match(env.el("session-active-name").textContent, /2 videos/);
    await env.ctx.researchSessionAction("end");
    assert.deepEqual(calls[1], {session_id:"research-1"}); assert.equal(env.clipboard.at(-1), "# Research corpus");
    assert.equal(env.el("session-start-form").hidden, false);
    await env.ctx.researchSessionAction("start");
    env.ctx.confirm = () => false;
    await env.ctx.researchSessionAction("cancel"); assert.equal(calls.length, 3);
    env.ctx.confirm = () => true;
    await env.ctx.researchSessionAction("cancel"); assert.equal(calls.length, 4);
    assert.match(env.el("session-status").textContent, /Files kept/);
  },
};
for (const name of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(groups)) {
  await groups[name](); console.log(`PASS ${name}: popup checks`);
}
