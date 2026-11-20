"""Fix cut-off X posts: a user-started, resumable repair job (3.18.0).

X saves can hold X's cut-off copy of long posts (see x_fulltext for why),
and a saved post that only links to an X Article holds just the link and a
preview. This job finds those saves, asks X whether each post is a long
post (the syndication note_tweet marker), gets the full text from
FxTwitter, and rewrites the saved text in place:

- X video saves: the ``## Description`` section of the corpus Markdown,
  ``description`` in metadata.json (the original is kept under
  ``x_text_repair.original_description``) and the row's search text.
- X post saves (x_thread): the cut-off post's body in the corpus Markdown,
  its entry in ``metadata.x_capture`` (sidecar and index row), and the
  row's search text.
- A post that only links to an X Article: the Article is saved as its own
  item (the post stays) and the post records where it went.

Everything else stays: transcript, screenshots, comments, shelves, tags,
opens, topic, title and any line a person added to the file.

Rules the job keeps:
- FxTwitter is a free community service, so the job only runs when the
  person has turned on ``fxtwitter_enrichment_enabled`` and pressed Start.
  With the switch off the dashboard shows the count and both ways to fix
  them (turn the switch on, or open each post and save it with the
  extension, which reads the open tab).
- Progress is saved after every item in ``<data root>/x-text-repair.json``;
  a helper restart picks the run back up, and a finished item is never
  asked about again in the same run.
- A save whose text is already whole is never rewritten. The saved words
  must open the full text (x_fulltext.extends) right before the write.
- A deleted or protected post keeps its saved text.
- One post at a time, a pause between posts, and back-off when a service
  asks Uoink to slow down. Only post IDs leave the computer: to X, and to
  FxTwitter for posts X marked as long.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import x_extractor
import x_fulltext
from uoink_core import x_evidence

log = logging.getLogger("uoink.x_text_repair")

STATE_NAME = "x-text-repair.json"
STATE_VERSION = 1
# Settled items are never asked about again. "unchanged" (X held the text
# back this time) and "failed" are retried by the next run the user starts.
SETTLED = frozenset({"fixed", "already_full", "gone", "skipped"})
PACE_SEC = 3.0  # one post every few seconds; FxTwitter is run by volunteers
SAMPLE_SIZE = 20  # posts listed for the "open it and save with the extension" way
NEEDS_SWITCH = ("Turn on Get full long posts and Articles through FxTwitter "
                "in Settings, Capture first.")
BACKOFF_SEC = (60, 120, 300, 600, 900)
MAX_RATE_LIMIT_STRIKES = len(BACKOFF_SEC)
MAX_NETWORK_STRIKES = 5
MAX_ITEM_ATTEMPTS = 3
SCAN_TTL_SEC = 120
CORPUS_HEAD_BYTES = 256 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---- files -----------------------------------------------------------------
def read_text_keep_newlines(path: Path) -> tuple[str, str]:
    """Text with ``\\n`` line ends plus the file's own line end, so a rewrite
    leaves every untouched byte as it was."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_text_atomic(path: Path, text: str, newline: str = "\n") -> None:
    data = (text.replace("\n", newline) if newline != "\n" else text).encode("utf-8")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.xfix.tmp")
    try:
        tmp.write_bytes(data)
        for delay in (0.05, 0.2, 0.5, None):
            try:
                tmp.replace(path)
                break
            except PermissionError:  # OneDrive can hold the file for a moment
                if delay is None:
                    raise
                time.sleep(delay)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, value) -> None:
    write_text_atomic(path, json.dumps(value, indent=2, ensure_ascii=False))


# ---- reading saves (offline) -------------------------------------------------
# _build_yoink_md always writes Tags right after Description. Anchoring on
# it keeps a "## " line inside a post from ending the section early.
_DESCRIPTION_RE = re.compile(r"^## Description\n\n(.*?)\n\n(?=## Tags\n)", re.DOTALL | re.MULTILINE)


def description_section(text: str):
    """(start, end, body) of the Description body in a video corpus."""
    match = _DESCRIPTION_RE.search(text or "")
    if not match:
        return None
    body = match.group(1)
    if body.strip() == "*No description.*":
        return None
    return match.start(1), match.end(1), body


def _url_of(row: dict, sidecar: dict | None = None) -> str:
    try:
        meta = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        meta = {}
    url = meta.get("url") if isinstance(meta, dict) else None
    if not url and isinstance(sidecar, dict):
        url = sidecar.get("url")
    return str(url or "")


def _status_id(url: str) -> str | None:
    tweet_id = x_extractor.tweet_id_from_url(url)
    if tweet_id:
        return tweet_id
    match = re.match(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/i/(?:web/)?status/(\d+)", url or "")
    return match.group(1) if match else None


def _video_candidate(row: dict) -> dict | None:
    corpus = Path(row.get("corpus_path") or "")
    if not row.get("corpus_path") or not corpus.is_file():
        return None
    tweet_id = _status_id(_url_of(row))
    if not tweet_id:
        return None
    try:
        with corpus.open("rb") as stream:
            head = stream.read(CORPUS_HEAD_BYTES).decode("utf-8", "replace").replace("\r\n", "\n")
    except OSError:
        return None
    section = description_section(head)
    if not section or not x_fulltext.looks_cut_off(section[2]):
        return None
    metadata = _read_json(Path(row.get("sidecar_path") or corpus).parent / "metadata.json")
    marker = metadata.get("x_text") if isinstance(metadata, dict) else None
    if isinstance(marker, dict) and (marker.get("text_completeness") == "complete" or not marker.get("long_post")):
        return None  # captured or repaired by 3.18.0 or later
    return {"video_id": row["video_id"], "kind": "video", "tweet_ids": [tweet_id],
            "title": row.get("title") or "", "yoinked_at": row.get("yoinked_at") or "",
            "url": f"https://x.com/i/status/{tweet_id}"}


def _thread_candidate(row: dict) -> dict | None:
    sidecar_path = Path(row.get("sidecar_path") or "")
    if not row.get("sidecar_path") or not row.get("corpus_path") or not sidecar_path.is_file():
        return None
    sidecar = _read_json(sidecar_path)
    metadata = (sidecar or {}).get("metadata") if isinstance(sidecar, dict) else None
    capture = metadata.get("x_capture") if isinstance(metadata, dict) else None
    posts = capture.get("posts") if isinstance(capture, dict) else None
    if not isinstance(posts, list):
        return None  # saved before X evidence existed: layout unknown, leave it
    base = {"video_id": row["video_id"], "title": row.get("title") or "",
            "yoinked_at": row.get("yoinked_at") or "", "url": _url_of(row, sidecar)}
    ids = []
    for post in posts:
        if not isinstance(post, dict) or not str(post.get("id") or "").isdigit():
            continue
        state = post.get("text_completeness")
        if state == "complete":
            continue
        if state == "truncated" or x_fulltext.looks_cut_off(post.get("text") or ""):
            ids.append(str(post["id"]))
    if ids:
        return dict(base, kind="thread", tweet_ids=ids)
    last = posts[-1] if posts and isinstance(posts[-1], dict) else {}
    cut = metadata.get("text_cut_off") if isinstance(metadata.get("text_cut_off"), dict) else {}
    article = x_extractor.linked_article(last) if last else None
    if article and str(last.get("id") or "").isdigit() and not cut.get("saved_as"):
        return dict(base, kind="article", tweet_ids=[str(last["id"])], url=base["url"] or article["url"])
    return None


def find_candidates(rows: list[dict]) -> list[dict]:
    """Saves that may hold X's cut-off copy, newest first. A hit only means
    "ask X"; the post's own long-post marker decides."""
    out = []
    for row in rows:
        try:
            if row.get("source_type") == "x_thread":
                found = _thread_candidate(row)
            elif row.get("source_type") in ("x_article", "page", "note", "image"):
                found = None
            else:
                found = _video_candidate(row)
        except Exception as exc:  # one odd save never stops the scan
            log.warning("x text scan skipped %s: %s", row.get("video_id"), type(exc).__name__)
            found = None
        if found:
            out.append(found)
    out.sort(key=lambda item: item["yoinked_at"], reverse=True)
    return out


# ---- rewriting (local) -------------------------------------------------------
class RewriteSkipped(Exception):
    """The save changed or does not match; the outcome names why."""

    def __init__(self, outcome: str, note: str):
        super().__init__(note)
        self.outcome = outcome
        self.note = note


def rewrite_video(row: dict, record: dict, *, index=None, lock=None) -> dict:
    """Replace a video save's cut-off Description with the full text.

    Write order is corpus, then index, then metadata.json, whose
    ``x_text`` marker is what tells a later scan the save is done. A kill
    between steps leaves the marker unwritten, so a resumed run finds the
    corpus already full and finishes the index and marker."""
    corpus = Path(row["corpus_path"])
    with (lock or threading.Lock()):
        text, newline = read_text_keep_newlines(corpus)
        section = description_section(text)
        if not section:
            raise RewriteSkipped("skipped", "No Description section to update.")
        start, end, saved = section
        new_body = record["description"] or record["text"]
        if x_fulltext.extends(saved, record["text"]):
            outcome = "fixed"
            text = text[:start] + new_body + text[end:]
            write_text_atomic(corpus, text, newline)
        elif x_fulltext.normalize(saved).startswith(x_fulltext.normalize(record["text"])):
            outcome = "already_full"  # whole already, maybe from a run that was cut short
        else:
            raise RewriteSkipped("skipped", "Saved text doesn't match the post on X.")
        if index is not None:
            index.update_corpus_text(row["video_id"], content=text)
        meta_path = Path(row.get("sidecar_path") or corpus).parent / "metadata.json"
        metadata = _read_json(meta_path)
        if isinstance(metadata, dict) and (outcome == "fixed" or not isinstance(metadata.get("x_text"), dict)):
            original = metadata.get("description", saved if outcome == "fixed" else None)
            if (not isinstance(metadata.get("x_text_repair"), dict) and original
                    and x_fulltext.extends(original, record["text"])):
                # Also when a killed run wrote the corpus but not this file.
                metadata["x_text_repair"] = {"original_description": original,
                                             "repaired_at": _now(), "provider": record["provider"]}
                outcome = "fixed"
            metadata["description"] = new_body
            metadata["x_text"] = text_marker(record)
            _write_json(meta_path, metadata)
    if index is not None:
        _heal_bindings(index, row["video_id"])
    if outcome == "already_full":
        return {"outcome": outcome, "note": "Saved text is already whole."}
    return {"outcome": "fixed", "note": f"Saved {len(record['text'])} characters from {record['provider']}."}


def text_marker(record: dict) -> dict:
    """What metadata.json records about an X video's saved text."""
    return {"provider": record["provider"], "text_completeness": record["text_completeness"],
            "long_post": bool(record["long_post"]), "checked_at": _now()}


def _replace_post_block(text: str, old: dict, new: dict) -> str:
    """Swap one post's rendered body (and its "Text: ..." line) in an
    x_thread corpus. Unchanged when the new body is already there."""
    old_body = x_evidence.expanded_text(old)
    new_body = x_evidence.expanded_text(new)
    if text.count(new_body + "\n") == 1 and text.count(old_body + "\n") != 1:
        return text  # an earlier, cut-short run already wrote this post
    if not old_body.strip() or text.count(old_body + "\n") != 1:
        raise RewriteSkipped("skipped", "Couldn't find the saved post text in the file.")
    start = text.index(old_body + "\n")
    end = start + len(old_body)
    nxt = text.find("\n## ", end)
    segment = text[end: nxt if nxt != -1 else len(text)]
    lines = segment.split("\n")
    out, replaced = [], False
    for line in lines:
        if not replaced and line.startswith("Text: ") and " Provider: " in line:
            out.append(f"Text: {new['text_completeness']}. Provider: {new['capture_provider']}.")
            replaced = True
            continue
        if replaced and line.startswith("Text completeness signal: "):
            continue
        out.append(line)
    return text[:start] + new_body + "\n".join(out) + text[end + len(segment):]


def _repaired_post(old: dict, fresh: dict) -> dict:
    merged = x_evidence.merge(x_evidence.sanitize_urls(old), fresh)
    merged["text_repair"] = {"original_text": old.get("text") or "", "repaired_at": _now(),
                             "provider": fresh["capture_provider"]}
    return merged


def rewrite_thread(row: dict, records: dict, *, index=None, lock=None) -> dict:
    """Replace each cut-off post's body in an x_thread save. ``records``
    maps post id to a post_text_record that extends the saved text.

    Write order is corpus, then index, then the sidecar, whose post record
    is what a later scan reads. A kill between steps is finished by the
    resumed run (the new body is found already in place)."""
    corpus, sidecar_path = Path(row["corpus_path"]), Path(row["sidecar_path"])
    with (lock or threading.Lock()):
        text, newline = read_text_keep_newlines(corpus)
        before = text
        sidecar = _read_json(sidecar_path)
        posts = (((sidecar or {}).get("metadata") or {}).get("x_capture") or {}).get("posts")
        if not isinstance(posts, list):
            raise RewriteSkipped("skipped", "The saved post has no X capture record.")
        fixed = 0
        for i, post in enumerate(posts):
            record = records.get(str(post.get("id") or ""))
            if not isinstance(post, dict) or not record or not x_fulltext.extends(
                    post.get("text") or "", record["text"]):
                continue
            fresh = _repaired_post(post, record["evidence"])
            text = _replace_post_block(text, post, fresh)
            posts[i] = fresh
            fixed += 1
        if not fixed:
            raise RewriteSkipped("already_full", "Saved text is already whole.")
        try:
            row_meta = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            row_meta = {}
        if isinstance(row_meta, dict) and isinstance(row_meta.get("x_capture"), dict):
            row_meta["x_capture"]["posts"] = posts
            metadata_json = json.dumps(row_meta, ensure_ascii=False)
        else:
            metadata_json = None
        if text != before:
            write_text_atomic(corpus, text, newline)
        if index is not None:
            index.update_corpus_text(row["video_id"], content=text[:65000], metadata_json=metadata_json)
        _write_json(sidecar_path, sidecar)
    if index is not None:
        _heal_bindings(index, row["video_id"])
    return {"outcome": "fixed", "note": f"Completed {fixed} post{'s' if fixed != 1 else ''}."}


def _heal_bindings(index, video_id: str) -> None:
    refresh = getattr(index, "refresh_media_bindings", None)
    if refresh is None:
        return
    try:
        refresh(video_id)
    except Exception as exc:  # reads heal stale bindings too
        log.info("x text repair: media bindings for %s heal on next read (%s)", video_id, type(exc).__name__)


# ---- the job -----------------------------------------------------------------
class RepairJob:
    """One per helper. ``fetch(tweet_id) -> post_text_record``,
    ``fetch_article(url) -> extract result``, ``persist_article(result) ->
    video_id`` and ``sleep`` are injectable so tests run offline and fast."""

    def __init__(self, *, data_root: Path, index_getter, fxtwitter_getter=lambda: False,
                 corpus_lock=None, fetch=None, fetch_article=None, persist_article=None,
                 sleep=None, clock=time.time, pace=PACE_SEC):
        self.state_path = Path(data_root) / STATE_NAME
        self._index_getter = index_getter
        self._fxtwitter = fxtwitter_getter
        self._corpus_lock = corpus_lock or threading.Lock()
        self._fetch = fetch
        self._fetch_article = fetch_article
        self._persist_article = persist_article
        self._clock = clock
        self._pace = pace
        self._sleep_impl = sleep
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._pause = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None
        self._scan: dict | None = None
        self._scan_thread: threading.Thread | None = None

    # -- state file
    def _load(self) -> dict:
        state = _read_json(self.state_path)
        if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
            state = {"version": STATE_VERSION, "status": "idle", "items": {}}
        state.setdefault("items", {})
        return state

    def _save(self, state: dict) -> None:
        state["updated_at"] = _now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self.state_path, state)

    # -- waiting that a pause can cut short
    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._sleep_impl is not None:
            self._sleep_impl(seconds)
            return
        self._wake.wait(seconds)
        self._wake.clear()

    # -- counts
    def _candidates(self) -> list[dict]:
        return find_candidates(self._index_getter().x_text_rows())

    def _pending(self, candidates: list[dict], state: dict) -> list[dict]:
        run_id = state.get("run_id")
        out = []
        listed = set()
        for item in candidates:
            listed.add(item["video_id"])
            done = state["items"].get(item["video_id"]) or {}
            if done.get("status") in SETTLED:
                continue
            if (run_id and done.get("run_id") == run_id and done.get("status") != "writing"
                    and state.get("status") in ("running", "paused")):
                continue  # already tried in this run
            out.append(item)
        # A save the helper was writing when it stopped. Its corpus may be
        # whole already (so the scan no longer lists it) while the search
        # text and metadata.json are not: finish it first.
        for video_id, done in state["items"].items():
            if done.get("status") == "writing" and isinstance(done.get("item"), dict) and video_id not in listed:
                out.insert(0, done["item"])
        return out

    def refresh_scan(self, *, wait: bool = False) -> None:
        with self._lock:
            if self._scan_thread is not None and self._scan_thread.is_alive():
                thread = self._scan_thread
            else:
                thread = threading.Thread(target=self._scan_now, name="x-text-scan", daemon=True)
                self._scan_thread = thread
                thread.start()
        if wait:
            thread.join()

    def _scan_now(self) -> None:
        try:
            candidates = self._candidates()
            scan = {"at": self._clock(), "candidates": candidates, "error": None}
        except Exception as exc:
            log.warning("x text scan failed: %s", type(exc).__name__)
            scan = {"at": self._clock(), "candidates": [], "error": "Couldn't read the library."}
        with self._lock:
            self._scan = scan

    def status(self) -> dict:
        with self._lock:
            state = self._load()
            scan = self._scan
            running = self._thread is not None and self._thread.is_alive()
        stale = scan is None or self._clock() - scan["at"] > SCAN_TTL_SEC
        if stale and not running:
            self.refresh_scan()
        counts = state.get("counts") or {}
        status = state.get("status") or "idle"
        if status == "running" and not running:
            status = "interrupted"
        queue = None if scan is None else self._pending(scan["candidates"], state)
        return {
            "ok": True, "status": status, "running": running,
            "counting": scan is None, "candidates": None if queue is None else len(queue),
            "articles": None if queue is None else sum(1 for item in queue if item["kind"] == "article"),
            # A few posts to open and save with the extension instead.
            "sample": [{"video_id": item["video_id"], "title": item["title"], "url": item["url"],
                        "kind": item["kind"]} for item in (queue or [])[:SAMPLE_SIZE]],
            "fixed_total": sum(1 for item in state["items"].values() if item.get("status") == "fixed"),
            "run": {key: counts.get(key, 0) for key in
                    ("checked", "fixed", "already_full", "gone", "unchanged", "skipped", "failed")},
            "total": state.get("total") or 0,
            "current": state.get("current"),
            "reason": state.get("reason"),
            "backoff_until": state.get("backoff_until"),
            "started_at": state.get("started_at"), "finished_at": state.get("finished_at"),
            "fxtwitter": bool(self._fxtwitter()),
        }

    # -- control
    def start(self, *, resume_only: bool = False) -> dict:
        if not self._fxtwitter():
            return dict(self.status(), ok=False, code="needs_fxtwitter", error=NEEDS_SWITCH)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            state = self._load()
            if state.get("status") in ("running", "paused") and state.get("run_id"):
                pass  # resume the same run
            elif resume_only:
                return self.status()
            else:
                state.update(run_id=uuid.uuid4().hex[:12], started_at=_now(), finished_at=None,
                             counts={}, total=0, reason=None, current=None, backoff_until=None)
            state["status"] = "running"
            state["reason"] = None
            self._save(state)
            self._pause.clear()
            self._stop = False
            self._thread = threading.Thread(target=self._run, name="x-text-repair", daemon=True)
            self._thread.start()
        return self.status()

    def pause(self) -> dict:
        with self._lock:
            self._pause.set()
            self._wake.set()
            thread = self._thread
            state = self._load()
            if state.get("status") == "running" and (thread is None or not thread.is_alive()):
                state["status"] = "paused"
                self._save(state)
        return self.status()

    def stop(self) -> dict:
        """End the run. Fixed saves stay fixed; the next Start begins a new
        run that asks again about anything not settled."""
        with self._lock:
            self._stop = True
            self._pause.set()
            self._wake.set()
            thread = self._thread
            state = self._load()
            if state.get("status") in ("running", "paused") and (thread is None or not thread.is_alive()):
                state.update(status="stopped", current=None, finished_at=_now())
                self._save(state)
        return self.status()

    def resume_if_interrupted(self) -> bool:
        """After a helper restart, continue a run the person had started.
        With the FxTwitter switch now off, the run waits as paused."""
        try:
            state = self._load()
            if state.get("status") != "running":
                return False
            if not self._fxtwitter():
                with self._lock:
                    state.update(status="paused", current=None, reason=NEEDS_SWITCH)
                    self._save(state)
                return False
            self.start(resume_only=True)
            return True
        except Exception as exc:  # startup never fails on this
            log.warning("x text repair could not resume: %s", type(exc).__name__)
            return False

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def fix_one(self, video_id: str) -> dict:
        """Fix one save now (the per-item button). Same rules as the run,
        one post's worth of requests, answered in this request."""
        if not self._fxtwitter():
            return {"ok": False, "code": "needs_fxtwitter", "error": NEEDS_SWITCH}
        row = self._row(video_id)
        found = find_candidates([row]) if row else []
        item = found[0] if found else None
        if item is None:
            return {"ok": False, "code": "not_cut_off", "error": "This save isn't cut off."}
        outcome = self._process(item)
        name = outcome["outcome"]
        if name in ("fixed", "already_full", "gone", "skipped", "unchanged", "failed"):
            with self._lock:
                state = self._load()
                state["items"][video_id] = {"status": name, "run_id": "single", "at": _now(),
                                            "attempts": 1, "note": outcome.get("note") or "",
                                            "kind": item["kind"]}
                self._save(state)
                self._scan = None
        if name == "rate_limited":
            return {"ok": False, "code": "rate_limited",
                    "error": "FxTwitter asked Uoink to slow down. Try again in a few minutes."}
        if name == "network":
            return {"ok": False, "code": "network", "error": "Couldn't reach X or FxTwitter. Try again later."}
        reply = {"ok": name in ("fixed", "already_full"), "outcome": name, "note": outcome.get("note") or ""}
        if outcome.get("saved_as"):
            reply["saved_as"] = outcome["saved_as"]
        if not reply["ok"]:
            reply["error"] = outcome.get("note") or "Couldn't get the full text this time."
        return reply

    # -- worker
    def _record_fetch(self, tweet_id: str) -> dict:
        if self._fetch is not None:
            return self._fetch(tweet_id)
        return x_extractor.post_text_record(tweet_id, timeout=15, fxtwitter=True)

    def _article_fetch(self, url: str) -> dict:
        if self._fetch_article is not None:
            return self._fetch_article(url)
        return x_extractor.extract_x_thread(url, timeout=15, fxtwitter=True)

    def _run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:  # never leave a dead "running" job behind
            log.exception("x text repair stopped")
            with self._lock:
                state = self._load()
                state.update(status="paused", reason=f"Stopped on an error ({type(exc).__name__}). Resume to try again.",
                             current=None)
                self._save(state)

    def _halt(self, reason: str) -> None:
        with self._lock:
            state = self._load()
            state.update(status="paused", current=None, reason=reason)
            self._save(state)

    def _run_inner(self) -> None:
        candidates = self._candidates()
        with self._lock:
            self._scan = {"at": self._clock(), "candidates": candidates, "error": None}
            state = self._load()
            queue = self._pending(candidates, state)
            done_here = sum(1 for item in state["items"].values()
                            if item.get("run_id") == state["run_id"] and item.get("status") != "writing")
            state["total"] = done_here + len(queue)
            self._save(state)
        rate_strikes = network_strikes = 0
        for item in queue:
            if self._pause.is_set():
                break
            if not self._fxtwitter():  # switched off mid-run: nothing more leaves
                return self._halt(NEEDS_SWITCH)
            with self._lock:
                state = self._load()
                wait = (state.get("backoff_until") or 0) - self._clock()
                state["current"] = {"video_id": item["video_id"], "title": item["title"]}
                record = state["items"].get(item["video_id"]) or {}
                state["items"][item["video_id"]] = dict(record, status="writing", run_id=state["run_id"],
                                                        item=item, at=_now())
                self._save(state)
            if wait > 0:
                self._sleep(wait)
                if self._pause.is_set():
                    break
            outcome = self._process(item)
            with self._lock:
                state = self._load()
                record = state["items"].get(item["video_id"]) or {}
                attempts = int(record.get("attempts") or 0)
                if outcome["outcome"] == "rate_limited":
                    rate_strikes += 1
                    delay = outcome.get("retry_after") or BACKOFF_SEC[min(rate_strikes, len(BACKOFF_SEC)) - 1]
                    state["backoff_until"] = self._clock() + min(float(delay), BACKOFF_SEC[-1])
                    if rate_strikes >= MAX_RATE_LIMIT_STRIKES:
                        state.update(status="paused", current=None,
                                     reason="X or FxTwitter kept asking Uoink to slow down. Resume later to finish.")
                        self._save(state)
                        return
                    self._save(state)
                    queue.append(item)  # try this one again after the wait
                    continue
                rate_strikes = 0
                if outcome["outcome"] == "network":
                    network_strikes += 1
                    attempts += 1
                    if network_strikes >= MAX_NETWORK_STRIKES:
                        state.update(status="paused", current=None,
                                     reason="Couldn't reach X or FxTwitter. Check the connection, then resume.")
                        self._save(state)
                        return
                    if attempts < MAX_ITEM_ATTEMPTS:
                        state["items"][item["video_id"]] = dict(record, attempts=attempts)
                        self._save(state)
                        queue.append(item)
                        self._sleep(self._pace * 2)
                        continue
                    outcome = {"outcome": "failed", "note": "Couldn't reach X or FxTwitter for this post."}
                else:
                    network_strikes = 0
                name = outcome["outcome"]
                state["items"][item["video_id"]] = {
                    "status": name, "run_id": state["run_id"], "at": _now(),
                    "attempts": attempts, "note": outcome.get("note") or "", "kind": item["kind"]}
                counts = state.setdefault("counts", {})
                counts["checked"] = counts.get("checked", 0) + 1
                counts[name] = counts.get(name, 0) + 1
                self._save(state)
            if not self._pause.is_set():
                self._sleep(self._pace)
        with self._lock:
            state = self._load()
            if self._stop:
                state.update(status="stopped", current=None, finished_at=_now())
            elif self._pause.is_set():
                state.update(status="paused", current=None)
            else:
                state.update(status="done", current=None, finished_at=_now(), backoff_until=None)
            self._save(state)
            self._scan = None

    def _process(self, item: dict) -> dict:
        if item["kind"] == "article":
            return self._process_article(item)
        records = {}
        for tweet_id in item["tweet_ids"]:
            try:
                record = self._record_fetch(tweet_id)
            except x_extractor.XFetchError as exc:
                if exc.kind == "gone":
                    if item["kind"] == "video" or len(item["tweet_ids"]) == 1:
                        return {"outcome": "gone", "note": "The post is gone from X. Kept the saved text."}
                    continue
                if exc.kind == "rate_limited":
                    return {"outcome": "rate_limited", "retry_after": exc.retry_after}
                return {"outcome": "network", "note": str(exc)}
            except Exception as exc:
                log.warning("x text repair fetch failed for %s: %s", item["video_id"], type(exc).__name__)
                return {"outcome": "network", "note": type(exc).__name__}
            status = ((record.get("evidence") or {}).get("provider_status") or {})
            if record["long_post"] and not record["complete"]:
                if status.get("FxTwitter") == "rate limited":
                    return {"outcome": "rate_limited", "retry_after": None}
                if status.get("FxTwitter") == "request failed":
                    return {"outcome": "network", "note": "Couldn't reach FxTwitter."}
            records[tweet_id] = record
        if not records:
            return {"outcome": "gone", "note": "The posts are gone from X. Kept the saved text."}
        long_posts = {key: rec for key, rec in records.items() if rec["long_post"]}
        if not long_posts:
            return {"outcome": "already_full", "note": "X says the saved text is the whole post."}
        usable = {key: rec for key, rec in long_posts.items() if rec["complete"]}
        if not usable:
            return {"outcome": "unchanged", "note": "FxTwitter didn't have the full text this time. Try again later."}
        row = self._row(item["video_id"])
        if row is None:
            return {"outcome": "skipped", "note": "The save was removed."}
        try:
            if item["kind"] == "video":
                return rewrite_video(row, next(iter(usable.values())), index=self._index_getter(),
                                     lock=self._corpus_lock)
            return rewrite_thread(row, usable, index=self._index_getter(), lock=self._corpus_lock)
        except RewriteSkipped as skipped:
            return {"outcome": skipped.outcome, "note": skipped.note}
        except Exception as exc:  # disk, index or an odd file: this save only
            log.warning("x text repair could not rewrite %s: %s", item["video_id"], type(exc).__name__)
            return {"outcome": "failed", "note": "Couldn't write the save's files."}

    def _process_article(self, item: dict) -> dict:
        """A saved post that only links to an X Article: save the Article
        as its own item and note on the post where it went."""
        try:
            result = self._article_fetch(item["url"])
        except Exception as exc:
            log.warning("x text repair article fetch failed for %s: %s", item["video_id"], type(exc).__name__)
            return {"outcome": "network", "note": type(exc).__name__}
        if not result.get("ok"):
            if result.get("code") == "fetch_failed" and "404" in str(result.get("error")):
                return {"outcome": "gone", "note": "The post is gone from X. Kept the saved post."}
            return {"outcome": "network", "note": str(result.get("error") or "")}
        if result.get("source_type") != "x_article":
            return {"outcome": "unchanged", "note": "FxTwitter didn't have the Article this time. Try again later."}
        try:
            new_id = self._persist_article(result) if self._persist_article else None
        except Exception as exc:
            log.warning("x text repair could not save article for %s: %s", item["video_id"], type(exc).__name__)
            new_id = None
        if not new_id:
            return {"outcome": "failed", "note": "Couldn't save the Article."}
        row = self._row(item["video_id"])
        if row is not None and row.get("sidecar_path"):
            with self._corpus_lock:
                path = Path(row["sidecar_path"])
                sidecar = _read_json(path)
                if isinstance(sidecar, dict) and isinstance(sidecar.get("metadata"), dict):
                    cut = sidecar["metadata"].get("text_cut_off")
                    cut = dict(cut) if isinstance(cut, dict) else {"reason": "article"}
                    cut.update(saved_as=new_id, saved_at=_now())
                    sidecar["metadata"]["text_cut_off"] = cut
                    _write_json(path, sidecar)
        return {"outcome": "fixed", "note": "Saved the Article as its own item.", "saved_as": new_id}

    def _row(self, video_id: str) -> dict | None:
        for row in self._index_getter().x_text_rows():
            if row["video_id"] == video_id:
                return row
        return None
