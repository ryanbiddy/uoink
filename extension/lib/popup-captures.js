// Pure capture projection shared by the popup's queue, stream and tests.
(function (global) {
  "use strict";
  const STEPS = ["details", "waiting for YouTube", "video", "transcript", "screenshots and save"];
  function stepIndex(phase, state = "") {
    const value = String(phase || "").toLowerCase();
    if (/screenshot|thumb|writ|comment|classif|hook|entity|publish|index|save/.test(value) || value === "done") return 4;
    if (/transcri|caption|asr|whisper/.test(value)) return 3;
    if (/download|media/.test(value) || value === "video") return 2;
    if (/wait|queue|rate/.test(value)) return 1;
    if (/metadata|detail/.test(value) || value === "fetch") return 0;
    return !value && ["queued", "pending"].includes(state) ? 1 : -1;
  }
  function steps(row = {}) {
    const state = String(row.state || row.status || "").toLowerCase();
    const failed = state === "failed" || (state === "pending" && !!(row.failure_phase || row.error_detail
      || (row.last_error && row.last_error !== "capture_ownership_unavailable")));
    const done = ["completed", "succeeded"].includes(state);
    const cancelled = state === "cancelled";
    const phase = (failed && (row.failure_phase || row.error_phase
      || (row.last_error === "youtube_rate_limit" ? "waiting" : ""))) || row.current_video_phase || row.phase;
    const index = done ? 4 : stepIndex(phase, failed || cancelled ? "" : state);
    const waiting = !failed && !done && !cancelled && (["queued", "pending"].includes(state) || index === 1);
    const label = done ? "Done" : cancelled ? "Cancelled" : failed
      ? (index < 0 ? "Failed" : `Failed at ${STEPS[index]} (${index + 1} of 5)`)
      : waiting ? "Waiting · one YouTube capture at a time"
      : ["Capturing", index < 0 ? "" : `${STEPS[index]} (${index + 1} of 5)`].filter(Boolean).join(" · ");
    return { index, failed, done, waiting, cancelled, label,
      segments: STEPS.map((_, i) => done ? "done" : cancelled ? "todo"
        : i < index ? "done" : i !== index ? "todo" : failed ? "fail" : "now") };
  }
  function safeError(row) {
    const raw = row.error_detail || row.last_error || row.error || row.message || "The capture failed. Try again.";
    const text = String(typeof raw === "object" ? raw.message || "The capture failed." : raw)
      .replace(/https?:\/\/[^\s"'<>]+/gi, "<url>")
      .replace(/(["'])(?:[a-z]:[\\/]|\\\\|\/)[^\r\n]*?\1/gi, "<path>")
      .replace(/[a-z]:[\\/][^\s"'<>;]+|\\\\[^\s"'<>;]+/gi, "<path>")
      .replace(/(^|[\s(=])\/[^\s"'<>;]+/gm, "$1<path>")
      .replace(/\b(?:authorization|cookie|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret)\s*[:=][^\r\n]*/gi, "[redacted]")
      .replace(/\b(?:Bearer|Basic)\s+[a-z0-9+/_=.-]+/gi, "[redacted]")
      .replace(/\bsk-[a-z0-9_-]{12,}/gi, "[redacted]");
    const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    return (lines.filter(s => /^ERROR:/i.test(s)).pop()
      || lines.filter(s => !/^(Command|Exit code):/i.test(s)).pop() || "The capture failed. Try again.").slice(0, 600);
  }
  function time(row) {
    const raw = row.finishedAt || row.completed_at || row.updated_at || row.failed_at || row.yoinked_at
      || row.startedAt || row.started_at || row.addedAt || row.queued_at || row.created_at;
    return typeof raw === "number" ? raw : Date.parse(raw) || 0;
  }
  function identity(row) {
    const url = row.source_url || row.url;
    if (url) {
      // Playlist and single-video captures must never coalesce.
      if (row.kind === "playlist" || row.route === "playlist") return global.STC.normalizePlaylistUrl(url) || url;
      // A saved X thread and its video are separate library items. A video
      // retry must not replace the posts' Done / Read / Copy Markdown row.
      if (row.route === "x_post" || row.useXPost || row.source_type === "x_thread") return `x-post:${global.STC.queueUrlKey(url)}`;
      const video = global.STC.extractVideoId(url);
      return video ? `video:${video}` : global.STC.queueUrlKey(url);
    }
    const id = row.video_id || (row.result && row.result.video_id);
    return id ? `video:${id}` : row.folder || (row.result && row.result.folder) || `job:${row.id || row.pending_id}`;
  }
  function itemId(row) {
    // A worker/helper job id is not a library id.
    return String(row.video_id || row.item_id || (row.result && (row.result.video_id || row.result.item_id)) || "");
  }
  function slug(row) {
    const result = row.result || {};
    return row.slug || row.video_slug || result.video_slug
      || String(row.folder || result.folder || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "";
  }
  function merge({ worker = {}, jobs = [], live = [], pending = [], recent = [], failures = [] } = {}) {
    const candidates = [];
    const add = (row, extra = {}) => { if (row) candidates.push({ ...row, ...extra }); };
    recent.forEach(row => add(row, { state: "completed", saved: row, rank: 1 }));
    failures.forEach(row => add(row, { state: "failed", failure: row, rank: 2 }));
    (worker.popup_capture_results || []).forEach(row => add(row, {
      state: row.queued ? "pending" : row.ok ? "completed" : "failed", rank: 3,
    }));
    jobs.forEach(row => add(row, { rank: 4 }));
    pending.forEach(row => add(row, { state: row.state || row.status || "pending", pending: row, rank: 5 }));
    live.forEach(row => add(row, { state: "running", rank: 6 }));
    (worker.queue || []).forEach(row => add(row, { state: "queued", rank: 7 }));
    if (worker.busy && worker.current) add(worker.current, { state: "running", rank: 7 });
    candidates.sort((a, b) => time(a) - time(b) || a.rank - b.rank);
    // /recent can have a library id and folder but no source URL. Attach
    // it to the matching completed request instead of showing a duplicate.
    const aliases = new Map();
    for (const row of candidates) {
      if (!row.source_url && !row.url) continue;
      const key = identity(row), id = itemId(row), folder = row.folder || row.result?.folder;
      if (id) aliases.set(`id:${id}`, key);
      if (folder) aliases.set(`folder:${folder}`, key);
    }
    const bySource = new Map();
    for (const row of candidates) {
      const key = aliases.get(`id:${itemId(row)}`)
        || aliases.get(`folder:${row.folder || row.result?.folder || ""}`) || identity(row);
      const old = bySource.get(key);
      let next = { ...old, ...row, key };
      // A worker is a transport for the helper capture. Use the helper's
      // phase while that request is in flight, even if its event is older.
      // Helper timestamps are rounded to seconds; the worker uses ms.
      if (old && row.rank === 7 && old.rank >= 4 && time(old) + 1000 >= (Number(row.startedAt || row.addedAt) || 0)) {
        next = { ...row, ...old, key };
      }
      // Running retries supersede the old failure, but keep the pending id
      // and saved corpus attached. A waiting retry keeps its real cause.
      if (["running", "queued", "completed", "succeeded", "cancelled"].includes(next.state)) {
        next.failure_phase = ""; next.error_detail = ""; next.last_error = ""; next.error = "";
      }
      if (["completed", "succeeded", "cancelled"].includes(next.state)) {
        next.failure = null; next.pending = null; next.pending_id = null;
      }
      bySource.set(key, next);
    }
    return [...bySource.values()].map(row => {
      const saved = recent.find(r => identity(r) === row.key || (r.folder && r.folder === (row.folder || row.result?.folder)));
      if (saved) row.saved = saved;
      const record = row.saved || {};
      row.video_id = itemId(row) || itemId(record);
      row.folder = row.folder || row.result?.folder || record.folder;
      row.title = row.title || row.playlist_title || row.current_video?.title || record.title || row.source_url || row.url || "Capture";
      row.model = steps(row);
      return row;
    }).sort((a, b) => time(b) - time(a)).slice(0, 6);
  }
  // Fetch SSE with an auth header. EOF, HTTP errors and read failures all
  // reconnect; hide/unload cancels the reader AND the pending reconnect.
  function stream({ connect, onEvent, onState, delay = 3000 }) {
    let controller = null, timer = null, generation = 0, enabled = false;
    async function run() {
      if (!enabled || controller) return;
      const epoch = generation;
      const own = new AbortController();
      controller = own;
      let reader;
      try {
        const response = await connect(own.signal);
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
        if (own.signal.aborted || epoch !== generation) return;
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        onState("live");
        while (!own.signal.aborted && epoch === generation) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
            const frame = buffer.slice(0, boundary.index);
            buffer = buffer.slice(boundary.index + boundary[0].length);
            const event = /^event:\s*(.*)$/m.exec(frame)?.[1].trim();
            const data = [...frame.matchAll(/^data:\s?(.*)$/gm)].map(m => m[1].trimEnd()).join("\n");
            if (event && data && !own.signal.aborted && epoch === generation) {
              try { onEvent(event, JSON.parse(data)); } catch (_) { /* malformed frame; keep listening */ }
            }
          }
        }
      } catch (_) { /* last known rows remain visible */ }
      finally {
        if (reader) { try { await reader.cancel(); } catch (_) {} }
        if (epoch === generation) {
          controller = null;
          if (enabled) { onState("reconnecting"); timer = setTimeout(run, delay); }
        }
      }
    }
    return {
      start() { if (enabled) return; enabled = true; run(); },
      stop() { enabled = false; generation++; clearTimeout(timer); timer = null; controller?.abort(); controller = null; },
    };
  }
  global.PopupCaptures = { STEPS, stepIndex, steps, safeError, time, identity, itemId, slug, merge, stream };
})(globalThis);
