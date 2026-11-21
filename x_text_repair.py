"""Fix cut-off X posts: a user-started, resumable repair job (3.18.0).

X saves can hold X's cut-off copy of long posts (see x_fulltext for why),
and a saved post that only links to an X Article holds just the link and a
preview. This job finds those saves, asks X whether each post is a long
post (the syndication note_tweet marker), gets the full text from
FxTwitter, and rewrites the saved text in place:

- X video saves: the ``## Description`` section of the corpus Markdown,
  ``description`` in metadata.json (the original is kept under
  ``x_text_repair.original_description``) and the row's search text.
- X post saves (x_thread): the cut-off post's body (and a cut-off quoted
  post) in the corpus Markdown, its entry in ``metadata.x_capture``
  (sidecar and index row), and the row's search text.
- A post that only links to an X Article: the Article is saved as its own
  item (the post stays) and the post records where it went.

Everything else stays: transcript, screenshots, comments, notes, shelves,
tags, opens, topic, title and any line a person added to the file.

Rules the job keeps:
- FxTwitter is a free community service, so the job only runs when the
  person has turned on ``fxtwitter_enrichment_enabled`` and pressed Start
  (or the reader's button for one save). The switch is read again before
  every FxTwitter request (x_extractor.fetch_fxtwitter_status), and a run
  pauses the moment it is off.
- One item at a time, batch or single, under one lock.
- Progress is saved after every step in ``<data root>/x-text-repair.json``.
  Before any file is written, the fetched text is saved there as the item's
  journal, so a helper killed mid-write finishes the same write on restart
  from the journal, with no new request.
- A save whose text is already whole is never rewritten, and a longer saved
  text is never replaced by a shorter one: the saved words must open the
  full text (x_fulltext.extends) right before the write.
- A deleted or protected post keeps its saved text.
- A pause between posts, and back-off when a service asks Uoink to slow
  down. Only post IDs leave the computer: to X, and to FxTwitter for posts
  X marked as long.
"""
from __future__ import annotations

import hashlib
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
SWITCHED_OFF = ("Paused because FxTwitter was turned off. Turn it back on in "
                "Settings, Capture, then press Resume.")
SLOW_DOWN = "X or FxTwitter kept asking Uoink to slow down. Resume later to finish."
BACKOFF_SEC = (60, 120, 300, 600, 900)
MAX_RATE_LIMIT_STRIKES = len(BACKOFF_SEC)
CALM_TO_RESET = 3  # this many answers in a row without a slow-down reset the back-off
MAX_NETWORK_STRIKES = 5
MAX_ITEM_ATTEMPTS = 3
SCAN_TTL_SEC = 120
CORPUS_HEAD_BYTES = 256 * 1024
ARTICLE_ID_PREFIX = "x-article"  # page_extractor.persist_page_yoink's slug_prefix for Articles

_OPEN_URL_RE = re.compile(r"^https://(?:x|twitter)\.com/(?:i|[A-Za-z0-9_]{1,15})/status/\d{1,25}$")
_QUOTING_RE = re.compile(
    r"\n\nQuoting (?:@[A-Za-z0-9_]{1,15}|another post)(?: \(https?://[^\s()]+\))?:\n")


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


def split_quote(description: str) -> tuple[str, str]:
    """(the post's own text, the quoted post's text) of a Description that
    x_extractor.description_text wrote. Older saves have no quote part."""
    last = None
    for last in _QUOTING_RE.finditer(description or ""):
        pass
    if last is None:
        return description or "", ""
    return description[:last.start()], description[last.end():]


def open_url(url: str, tweet_id: str) -> str | None:
    """The link a person can open for a save: its own x.com status link
    when it is one, else one built from the post id. Never anything else,
    since the dashboard renders it as a link."""
    url = str(url or "").split("?", 1)[0].split("#", 1)[0]
    if _OPEN_URL_RE.match(url) and url.rsplit("/", 1)[-1] == tweet_id:
        return url
    return f"https://x.com/i/status/{tweet_id}" if x_extractor.is_post_id(tweet_id) else None


def article_video_id(article_url: str) -> str:
    """The id persist_page_yoink gives an Article saved from this link."""
    return f"{ARTICLE_ID_PREFIX}_{hashlib.sha1(article_url.encode('utf-8')).hexdigest()[:11]}"


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
    if not tweet_id or not x_extractor.is_post_id(tweet_id):
        return None
    metadata = _read_json(Path(row.get("sidecar_path") or corpus).parent / "metadata.json")
    marker = metadata.get("x_text") if isinstance(metadata, dict) else None
    if isinstance(marker, dict):
        # Captured or repaired by 3.18.0 or later: X said whether it is long.
        main_cut = bool(marker.get("long_post")) and marker.get("text_completeness") != "complete"
        if not main_cut and marker.get("quote_complete") is not False:
            return None
    else:
        try:
            with corpus.open("rb") as stream:
                head = stream.read(CORPUS_HEAD_BYTES).decode("utf-8", "replace").replace("\r\n", "\n")
        except OSError:
            return None
        section = description_section(head)
        if not section or not x_fulltext.looks_cut_off(split_quote(section[2])[0]):
            return None
    return {"video_id": row["video_id"], "kind": "video", "tweet_ids": [tweet_id],
            "title": row.get("title") or "", "yoinked_at": row.get("yoinked_at") or "",
            "url": f"https://x.com/i/status/{tweet_id}"}


def _marked_cut(post: dict) -> bool:
    """X marked this post, or its quoted post, as cut off: the test
    x_extractor.cut_off_help uses for the reader's prompt."""
    quote = post.get("quote") if isinstance(post.get("quote"), dict) else {}
    return post.get("text_completeness") == "truncated" or quote.get("text_completeness") == "truncated"


def _post_is_cut(post: dict) -> bool:
    """X marked it cut off, or (a save from before X evidence said so) its
    text looks like X's cut-off copy."""
    if _marked_cut(post):
        return True
    return post.get("text_completeness") != "complete" and x_fulltext.looks_cut_off(post.get("text") or "")


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
    posts = [post for post in posts if isinstance(post, dict) and x_extractor.is_post_id(post.get("id"))]
    if not posts:
        return None
    last_id = str(posts[-1]["id"])
    link = open_url(_url_of(row, sidecar), last_id)
    base = {"video_id": row["video_id"], "title": row.get("title") or "",
            "yoinked_at": row.get("yoinked_at") or "", "url": link}
    ids = [str(post["id"]) for post in posts if _post_is_cut(post)]
    if ids:
        return dict(base, kind="thread", tweet_ids=ids)
    cut = metadata.get("text_cut_off") if isinstance(metadata.get("text_cut_off"), dict) else {}
    if x_extractor.linked_article(posts[-1]) and not cut.get("saved_as"):
        return dict(base, kind="article", tweet_ids=[last_id])
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
        if found and found.get("url"):
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


def _longer(saved: str, full: str) -> bool:
    """``full`` continues ``saved`` and is not shorter, after normalizing."""
    return x_fulltext.extends(saved, full) and len(x_fulltext.normalize(full)) > len(x_fulltext.normalize(saved))


def description_verdict(saved: str, record: dict) -> str:
    """"longer" when the record's Description is a longer copy of the saved
    one (the post's own text, or a quoted post X cut short), "same" when the
    saved one already holds the whole post, else "mismatch"."""
    saved_main, saved_quote = split_quote(saved)
    if _longer(saved_main, record["text"]):
        return "longer"
    if not x_fulltext.normalize(saved_main).startswith(x_fulltext.normalize(record["text"])):
        return "mismatch"
    new_quote = record.get("quote_text") or ""
    if saved_quote and new_quote and record.get("quote_complete") and _longer(saved_quote, new_quote):
        new_main = split_quote(record.get("description") or "")[0]
        if x_fulltext.normalize(new_main) == x_fulltext.normalize(saved_main) or _longer(saved_main, new_main):
            return "longer"
    return "same"


def text_marker(record: dict) -> dict:
    """What metadata.json records about an X video's saved text."""
    return {"provider": record["provider"], "text_completeness": record["text_completeness"],
            "long_post": bool(record["long_post"]),
            "quote_complete": record.get("quote_complete", True) is not False,
            "checked_at": _now()}


def rewrite_video(row: dict, record: dict, *, index=None, lock=None) -> dict:
    """Replace a video save's cut-off Description with the full text.

    Write order is corpus, then index, then metadata.json, whose
    ``x_text`` marker is what tells a later scan the save is done. Every
    step checks what is there first, so running it again after a kill
    finishes the steps that were left (the corpus is found whole already)."""
    corpus = Path(row["corpus_path"])
    with (lock or threading.Lock()):
        text, newline = read_text_keep_newlines(corpus)
        section = description_section(text)
        if not section:
            raise RewriteSkipped("skipped", "No Description section to update.")
        start, end, saved = section
        new_body = record["description"] or record["text"]
        verdict = description_verdict(saved, record)
        if verdict == "mismatch":
            raise RewriteSkipped("skipped", "Saved text doesn't match the post on X.")
        outcome = "fixed" if verdict == "longer" else "already_full"
        if verdict == "longer":
            text = text[:start] + new_body + text[end:]
            write_text_atomic(corpus, text, newline)
        if index is not None:
            index.update_corpus_text(row["video_id"], content=text)
        meta_path = Path(row.get("sidecar_path") or corpus).parent / "metadata.json"
        metadata = _read_json(meta_path)
        if isinstance(metadata, dict):
            desc = metadata.get("description")
            if not isinstance(desc, str) or not desc.strip():
                metadata["description"] = new_body
            elif description_verdict(desc, record) == "longer":
                if not isinstance(metadata.get("x_text_repair"), dict):
                    # Also when a killed run wrote the corpus but not this file.
                    metadata["x_text_repair"] = {"original_description": desc,
                                                 "repaired_at": _now(), "provider": record["provider"]}
                metadata["description"] = new_body
                outcome = "fixed"
            # Any other description (longer, or edited by hand) stays as it is.
            metadata["x_text"] = text_marker(record)
            _write_json(meta_path, metadata)
        sidecar_path = Path(row.get("sidecar_path") or meta_path)
        if sidecar_path != meta_path:  # the reader's copy of the marker
            sidecar = _read_json(sidecar_path)
            if isinstance(sidecar, dict):
                sidecar["x_text"] = text_marker(record)
                _write_json(sidecar_path, sidecar)
    if index is not None:
        _heal_bindings(index, row["video_id"])
    if outcome == "already_full":
        return {"outcome": outcome, "note": "Saved text is already whole."}
    return {"outcome": "fixed", "note": f"Saved {len(record['text'])} characters from {record['provider']}."}


def _swap_body(text: str, old_body: str, new_body: str, completeness: str, provider: str) -> str:
    """Swap one rendered body (and the "Text: ..." line after it) in an
    x_thread corpus. Unchanged when the new body is already there."""
    if text.count(new_body + "\n") == 1 and text.count(old_body + "\n") != 1:
        return text  # an earlier, cut-short run already wrote this one
    if not old_body.strip() or text.count(old_body + "\n") != 1:
        raise RewriteSkipped("skipped", "Couldn't find the saved post text in the file.")
    start = text.index(old_body + "\n")
    end = start + len(old_body)
    nxt = text.find("\n## ", end)
    segment = text[end: nxt if nxt != -1 else len(text)]
    # Only this body's own disclosure block: its first "Text:" line and the
    # cut-off signal line in the same block. A quoted post's lines below stay.
    out, stage = [], 0
    for line in segment.split("\n"):
        if stage == 0 and line.startswith("Text: ") and " Provider: " in line:
            out.append(f"Text: {completeness}. Provider: {provider}.")
            stage = 1
            continue
        if stage == 1:
            if line.startswith("Text completeness signal: "):
                stage = 2
                continue
            if not line.strip():
                stage = 2
        out.append(line)
    return text[:start] + new_body + "\n".join(out) + text[end + len(segment):]


def _repaired_post(old: dict, fresh: dict) -> dict:
    merged = x_evidence.merge(x_evidence.sanitize_urls(old), fresh)
    repair = {"original_text": old.get("text") or "", "repaired_at": _now(),
              "provider": fresh["capture_provider"]}
    old_quote = old.get("quote") if isinstance(old.get("quote"), dict) else None
    if old_quote and (merged.get("quote") or {}).get("text") != old_quote.get("text"):
        repair["original_quote_text"] = old_quote.get("text") or ""
    merged["text_repair"] = repair
    return merged


def _quote_longer(old: dict, record: dict) -> bool:
    old_quote = old.get("quote") if isinstance(old.get("quote"), dict) else {}
    new_quote = (record.get("evidence") or {}).get("quote") or {}
    return bool(old_quote.get("text") and new_quote.get("text") and record.get("quote_complete")
                and str(old_quote.get("id") or "") == str(new_quote.get("id") or "")
                and _longer(old_quote["text"], new_quote["text"]))


def rewrite_thread(row: dict, records: dict, *, index=None, lock=None) -> dict:
    """Replace each cut-off post's body (and a cut-off quoted post) in an
    x_thread save. ``records`` maps post id to a post_text_record.

    Write order is corpus, then index, then the sidecar, whose post record
    is what a later scan reads. Running it again after a kill finishes the
    steps that were left (the new bodies are found in place already)."""
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
            record = records.get(str(post.get("id") or "")) if isinstance(post, dict) else None
            if not record:
                continue
            main = _longer(post.get("text") or "", record["text"])
            quoted = _quote_longer(post, record)
            if not (main or quoted):
                continue
            fresh = _repaired_post(post, record["evidence"])
            if main:
                text = _swap_body(text, x_evidence.expanded_text(post), x_evidence.expanded_text(fresh),
                                  fresh["text_completeness"], fresh["capture_provider"])
            if quoted:
                old_q, new_q = post["quote"], fresh["quote"]
                text = _swap_body(text, x_evidence.expanded_text(old_q), x_evidence.expanded_text(new_q),
                                  new_q["text_completeness"], new_q["capture_provider"])
                old_line = (f"Quoted post {old_q['id']}: text {old_q['text_completeness']}. "
                            f"Provider: {old_q['capture_provider']}.")
                if text.count(old_line) == 1:
                    text = text.replace(old_line, f"Quoted post {new_q['id']}: text {new_q['text_completeness']}. "
                                                  f"Provider: {new_q['capture_provider']}.")
            posts[i] = fresh
            fixed += 1
        if not fixed:
            raise RewriteSkipped("already_full", "Saved text is already whole.")
        whole = all(isinstance(p, dict) and not _marked_cut(p) for p in posts)
        cut = sidecar["metadata"].get("text_cut_off")
        if whole and isinstance(cut, dict) and cut.get("reason") == "long_post":
            sidecar["metadata"]["text_cut_off"] = None  # the reader stops asking
        try:
            row_meta = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            row_meta = {}
        if isinstance(row_meta, dict) and isinstance(row_meta.get("x_capture"), dict):
            row_meta["x_capture"]["posts"] = posts
            if "text_cut_off" in row_meta:
                row_meta["text_cut_off"] = sidecar["metadata"].get("text_cut_off")
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


def finish_article(row: dict, saved_as: str, *, index=None, lock=None) -> dict:
    """Note on a post that only links to an X Article where the Article was
    saved: the sidecar and the index row both carry ``saved_as``, so the
    reader stops offering the fix and a later scan skips the post."""
    sidecar_path = Path(row["sidecar_path"])
    with (lock or threading.Lock()):
        sidecar = _read_json(sidecar_path)
        if not isinstance(sidecar, dict) or not isinstance(sidecar.get("metadata"), dict):
            raise RewriteSkipped("skipped", "The saved post has no metadata to update.")
        cut = sidecar["metadata"].get("text_cut_off")
        cut = dict(cut) if isinstance(cut, dict) else {"reason": "article"}
        if cut.get("saved_as") != saved_as:
            cut.update(saved_as=saved_as, saved_at=_now())
        sidecar["metadata"]["text_cut_off"] = cut
        try:
            row_meta = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            row_meta = {}
        if index is not None and isinstance(row_meta, dict):
            row_meta["text_cut_off"] = cut
            corpus = Path(row.get("corpus_path") or "")
            content = read_text_keep_newlines(corpus)[0] if row.get("corpus_path") and corpus.is_file() else ""
            index.update_corpus_text(row["video_id"], content=content[:65000],
                                     metadata_json=json.dumps(row_meta, ensure_ascii=False))
        _write_json(sidecar_path, sidecar)
    return {"outcome": "fixed", "note": "Saved the Article as its own item.", "saved_as": saved_as}


def _heal_bindings(index, video_id: str) -> None:
    refresh = getattr(index, "refresh_media_bindings", None)
    if refresh is None:
        return
    try:
        refresh(video_id)
    except Exception as exc:  # reads heal stale bindings too
        log.info("x text repair: media bindings for %s heal on next read (%s)", video_id, type(exc).__name__)


_JOURNAL_KEYS = ("id", "long_post", "complete", "quote_long", "quote_complete", "quote_text", "text",
                 "provider", "text_completeness", "description", "evidence")


def _journal_record(record: dict) -> dict:
    return {key: record.get(key) for key in _JOURNAL_KEYS}


# ---- the job -----------------------------------------------------------------
class RepairJob:
    """One per helper. ``fetch(tweet_id) -> post_text_record``,
    ``fetch_article(tweet_id) -> x_article extract result or None`` (raises
    XFetchError), ``persist_article(result) -> video_id`` and ``sleep`` are
    injectable so tests run offline and fast."""

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
        self._lock = threading.RLock()  # the state file
        self._work_lock = threading.Lock()  # one item at a time, run or single
        self._wake = threading.Event()
        self._pause = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None
        self._scan: dict | None = None
        self._scan_thread: threading.Thread | None = None
        self._fixing: dict[str, threading.Thread] = {}

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

    def _entry(self, video_id: str) -> dict:
        with self._lock:
            return dict(self._load()["items"].get(video_id) or {})

    def _put_entry(self, video_id: str, entry: dict | None) -> None:
        with self._lock:
            state = self._load()
            if entry is None:
                state["items"].pop(video_id, None)
            else:
                state["items"][video_id] = entry
            self._save(state)

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
            if (run_id and done.get("run_id") == run_id and done.get("status") not in ("writing", "waiting")
                    and state.get("status") in ("running", "paused")):
                continue  # already tried in this run
            out.append(item)
        # A save the helper was writing when it stopped. Its corpus may be
        # whole already (so the scan no longer lists it) while the search
        # text and metadata.json are not: finish it first, from its journal.
        for video_id, done in state["items"].items():
            if (done.get("status") == "writing" and isinstance(done.get("journal"), dict)
                    and isinstance(done.get("item"), dict) and video_id not in listed):
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

    def item_status(self, video_id: str) -> dict:
        """Where the reader's one-save fix stands: working, then the outcome."""
        with self._lock:
            thread = self._fixing.get(video_id)
            working = thread is not None and thread.is_alive()
            entry = dict(self._load()["items"].get(video_id) or {})
        out = {"video_id": video_id, "status": "working" if working else (entry.get("status") or "none"),
               "note": entry.get("note") or "", "code": entry.get("code")}
        if entry.get("saved_as") and not working:
            out["saved_as"] = entry["saved_as"]
        return out

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
                        "kind": item["kind"]} for item in (queue or [])[:SAMPLE_SIZE] if item.get("url")],
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
                self._drop_unstarted_writes(state)
                self._save(state)
        return self.status()

    @staticmethod
    def _drop_unstarted_writes(state: dict) -> None:
        """A "writing" item with no journal never wrote a file: forget it
        (a journaled one is finished from its journal instead)."""
        for video_id in [vid for vid, item in state["items"].items()
                         if item.get("status") == "writing" and not isinstance(item.get("journal"), dict)]:
            state["items"].pop(video_id, None)

    def resume_if_interrupted(self) -> bool:
        """After a helper restart: finish any write the helper was in the
        middle of, from its journal (no request is sent), then continue a
        run the person had started. With the FxTwitter switch now off, the
        run waits as paused."""
        try:
            self._finish_journals()
            state = self._load()
            if state.get("status") != "running":
                return False
            if not self._fxtwitter():
                with self._lock:
                    state = self._load()
                    state.update(status="paused", current=None, reason=SWITCHED_OFF)
                    self._save(state)
                return False
            self.start(resume_only=True)
            return True
        except Exception as exc:  # startup never fails on this
            log.warning("x text repair could not resume: %s", type(exc).__name__)
            return False

    def _finish_journals(self) -> None:
        with self._lock:
            state = self._load()
            waiting = [(vid, dict(entry)) for vid, entry in state["items"].items()
                       if entry.get("status") == "writing"]
        for video_id, entry in waiting:
            if not isinstance(entry.get("journal"), dict) or not isinstance(entry.get("item"), dict):
                if entry.get("run_id") == "single":
                    self._put_entry(video_id, None)  # its fetch never finished; nothing was written
                continue
            outcome = self._work(entry["item"], entry.get("run_id") or "single", skip_settled=False)
            self._settle(entry["item"], entry.get("run_id") or "single", outcome, count=True)

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def wait_fix(self, video_id: str, timeout: float | None = None) -> None:
        thread = self._fixing.get(video_id)
        if thread is not None:
            thread.join(timeout)

    def fix_one(self, video_id: str) -> dict:
        """Fix one save (the reader's button). Same rules as the run, on the
        same one-at-a-time worker lock, in the background: the request
        answers at once and the reader polls ``item_status``."""
        if not self._fxtwitter():
            return {"ok": False, "code": "needs_fxtwitter", "error": NEEDS_SWITCH}
        row = self._row(video_id)
        found = find_candidates([row]) if row else []
        item = found[0] if found else None
        if item is None:
            return {"ok": False, "code": "not_cut_off", "error": "This save isn't cut off."}
        with self._lock:
            thread = self._fixing.get(video_id)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=self._fix_worker, args=(item, time.time()),
                                          name="x-text-fix", daemon=True)
                self._fixing[video_id] = thread
                thread.start()
        return {"ok": True, "queued": True, "video_id": video_id, "status": "working"}

    def _fix_worker(self, item: dict, asked_at: float) -> None:
        try:
            outcome = self._work(item, "single", skip_settled=False, settled_since=asked_at)
        except Exception as exc:
            log.warning("x text fix stopped for %s: %s", item["video_id"], type(exc).__name__)
            outcome = {"outcome": "failed", "note": "Couldn't fix this save. Try again later."}
        name = outcome["outcome"]
        if name == "disabled":
            outcome = dict(outcome, note=NEEDS_SWITCH)
        elif name == "rate_limited":
            outcome = dict(outcome, note="FxTwitter asked Uoink to slow down. Try again in a few minutes.")
        elif name == "network" and not outcome.get("note"):
            outcome = dict(outcome, note="Couldn't reach X or FxTwitter. Try again later.")
        if name != "already_done":
            self._settle(item, "single", outcome, count=False)
        with self._lock:
            self._scan = None

    # -- worker
    def _record_fetch(self, tweet_id: str) -> dict:
        if self._fetch is not None:
            return self._fetch(tweet_id)
        return x_extractor.post_text_record(tweet_id, timeout=15, fxtwitter=True)

    def _article_fetch(self, tweet_id: str):
        if self._fetch_article is not None:
            return self._fetch_article(tweet_id)
        return x_extractor.article_capture(tweet_id, timeout=15)

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

    def _set_current(self, item: dict) -> None:
        with self._lock:
            state = self._load()
            state["current"] = {"video_id": item["video_id"], "title": item["title"]}
            self._save(state)

    def _run_inner(self) -> None:
        candidates = self._candidates()
        with self._lock:
            self._scan = {"at": self._clock(), "candidates": candidates, "error": None}
            state = self._load()
            run_id = state["run_id"]
            queue = self._pending(candidates, state)
            done_here = sum(1 for item in state["items"].values()
                            if item.get("run_id") == run_id and item.get("status") not in ("writing", "waiting"))
            state["total"] = done_here + len(queue)
            self._save(state)
        rate_strikes = network_strikes = calm = 0
        for item in queue:
            if self._pause.is_set():
                break
            if not self._fxtwitter():  # switched off mid-run: nothing more leaves
                return self._halt(SWITCHED_OFF)
            self._set_current(item)
            with self._lock:
                wait = (self._load().get("backoff_until") or 0) - self._clock()
            if wait > 0:
                self._sleep(wait)
                if self._pause.is_set():
                    break
                if not self._fxtwitter():  # switched off during the wait
                    return self._halt(SWITCHED_OFF)
            outcome = self._work(item, run_id, skip_settled=True)
            name = outcome["outcome"]
            if name == "already_done":
                continue  # the reader's button settled it meanwhile
            if name == "disabled":  # waits for Resume, not counted as tried
                self._put_entry(item["video_id"], dict(self._entry(item["video_id"]), status="waiting",
                                                       run_id=run_id, item=item, at=_now()))
                return self._halt(SWITCHED_OFF)
            entry = self._entry(item["video_id"])
            attempts = int(entry.get("attempts") or 0) + (1 if name in ("rate_limited", "network") else 0)
            if name == "rate_limited":
                rate_strikes += 1
                calm = 0
                step = BACKOFF_SEC[min(rate_strikes, len(BACKOFF_SEC)) - 1]
                asked = float(outcome.get("retry_after") or 0)
                with self._lock:
                    state = self._load()
                    state["items"][item["video_id"]] = dict(entry, status="waiting", run_id=run_id,
                                                            attempts=attempts, item=item, at=_now())
                    if asked > BACKOFF_SEC[-1] or rate_strikes >= MAX_RATE_LIMIT_STRIKES \
                            or attempts >= MAX_ITEM_ATTEMPTS:
                        state.update(status="paused", current=None, reason=SLOW_DOWN,
                                     backoff_until=self._clock() + min(max(asked, step), BACKOFF_SEC[-1]))
                        self._save(state)
                        return
                    state["backoff_until"] = self._clock() + max(asked, step)
                    self._save(state)
                queue.append(item)  # try this one again after the wait
                continue
            calm += 1
            if calm >= CALM_TO_RESET:
                rate_strikes = 0
            if name == "network":
                network_strikes += 1
                if network_strikes >= MAX_NETWORK_STRIKES:
                    self._put_entry(item["video_id"], dict(entry, status="waiting", run_id=run_id,
                                                           attempts=attempts, item=item, at=_now()))
                    return self._halt("Couldn't reach X or FxTwitter. Check the connection, then resume.")
                if attempts < MAX_ITEM_ATTEMPTS:
                    self._put_entry(item["video_id"], dict(entry, status="waiting", run_id=run_id,
                                                           attempts=attempts, item=item, at=_now()))
                    queue.append(item)
                    self._sleep(self._pace * 2)
                    continue
                outcome = {"outcome": "failed", "note": "Couldn't reach X or FxTwitter for this post."}
            else:
                network_strikes = 0
            self._settle(item, run_id, outcome, count=True, attempts=attempts)
            if not self._pause.is_set():
                self._sleep(self._pace)
        with self._lock:
            state = self._load()
            if self._stop:
                state.update(status="stopped", current=None, finished_at=_now())
                self._drop_unstarted_writes(state)
            elif self._pause.is_set():
                state.update(status="paused", current=None)
            else:
                state.update(status="done", current=None, finished_at=_now(), backoff_until=None)
            self._save(state)
            self._scan = None

    def _settle(self, item: dict, run_id: str, outcome: dict, *, count: bool, attempts: int | None = None) -> None:
        """Write an item's final status (this drops its journal)."""
        name = outcome["outcome"]
        status = name if name in SETTLED or name in ("unchanged", "failed") else "failed"
        with self._lock:
            state = self._load()
            old = state["items"].get(item["video_id"]) or {}
            entry = {"status": status, "run_id": run_id, "at": _now(), "at_ts": time.time(),
                     "attempts": attempts if attempts is not None else int(old.get("attempts") or 0),
                     "note": outcome.get("note") or "", "kind": item["kind"]}
            if status != name:
                entry["code"] = name
            if outcome.get("saved_as"):
                entry["saved_as"] = outcome["saved_as"]
            state["items"][item["video_id"]] = entry
            if count and run_id == state.get("run_id"):
                counts = state.setdefault("counts", {})
                counts["checked"] = counts.get("checked", 0) + 1
                counts[status] = counts.get(status, 0) + 1
            self._save(state)

    def _work(self, item: dict, run_id: str, *, skip_settled: bool, settled_since: float | None = None) -> dict:
        """One item, start to finish, one at a time across the run and the
        reader's button. The journal is saved before any file is written,
        so a write cut short is finished from it, with no new request."""
        video_id = item["video_id"]
        with self._work_lock:
            entry = self._entry(video_id)
            if entry.get("status") in SETTLED and (skip_settled or (
                    settled_since is not None and float(entry.get("at_ts") or 0) >= settled_since)):
                return {"outcome": "already_done"}  # settled while this one waited its turn
            journal = entry.get("journal") if entry.get("status") == "writing" else None
            if not isinstance(journal, dict):
                journal = None
            self._put_entry(video_id, dict(entry, status="writing", run_id=run_id, item=item, at=_now(),
                                           journal=journal))
            if journal is None:
                if not self._fxtwitter():
                    return {"outcome": "disabled", "note": SWITCHED_OFF}
                fetched = self._fetch_item(item)
                if fetched["outcome"] != "apply":
                    return fetched
                journal = fetched["journal"]
                self._put_entry(video_id, dict(self._entry(video_id), journal=journal))
            return self._apply(item, journal)

    def _apply(self, item: dict, journal: dict) -> dict:
        row = self._row(item["video_id"])
        if row is None:
            return {"outcome": "skipped", "note": "The save was removed."}
        try:
            if journal.get("kind") == "article":
                return finish_article(row, journal["saved_as"], index=self._index_getter(), lock=self._corpus_lock)
            if journal.get("kind") == "video":
                return rewrite_video(row, journal["record"], index=self._index_getter(), lock=self._corpus_lock)
            return rewrite_thread(row, journal["records"], index=self._index_getter(), lock=self._corpus_lock)
        except RewriteSkipped as skipped:
            return {"outcome": skipped.outcome, "note": skipped.note}
        except Exception as exc:  # disk, index or an odd file: this save only
            log.warning("x text repair could not rewrite %s: %s", item["video_id"], type(exc).__name__)
            return {"outcome": "failed", "note": "Couldn't write the save's files."}

    @staticmethod
    def _fetch_failure(exc: x_extractor.XFetchError, *, gone_note: str) -> dict:
        if exc.kind == "gone":
            return {"outcome": "gone", "note": gone_note}
        if exc.kind == "rate_limited":
            return {"outcome": "rate_limited", "retry_after": exc.retry_after}
        if exc.kind == "disabled":
            return {"outcome": "disabled", "note": SWITCHED_OFF}
        return {"outcome": "network", "note": str(exc)}

    def _fetch_item(self, item: dict) -> dict:
        """Ask X (and FxTwitter) about the item. Returns a final outcome, or
        {"outcome": "apply", "journal": ...} with what to write."""
        if item["kind"] == "article":
            return self._fetch_article_item(item)
        records = {}
        for tweet_id in item["tweet_ids"]:
            if not self._fxtwitter():
                return {"outcome": "disabled", "note": SWITCHED_OFF}
            try:
                record = self._record_fetch(tweet_id)
            except x_extractor.XFetchError as exc:
                if exc.kind == "gone" and not (item["kind"] == "video" or len(item["tweet_ids"]) == 1):
                    continue
                return self._fetch_failure(exc, gone_note="The post is gone from X. Kept the saved text.")
            except Exception as exc:
                log.warning("x text repair fetch failed for %s: %s", item["video_id"], type(exc).__name__)
                return {"outcome": "network", "note": type(exc).__name__}
            wants = (record["long_post"] and not record["complete"]) or (
                record.get("quote_long") and not record.get("quote_complete"))
            fx = record.get("fxtwitter_status")
            if wants and fx == "switched off":
                return {"outcome": "disabled", "note": SWITCHED_OFF}
            if wants and fx == "rate limited":
                return {"outcome": "rate_limited", "retry_after": record.get("fxtwitter_retry_after")}
            if wants and fx == "request failed":
                return {"outcome": "network", "note": "Couldn't reach FxTwitter."}
            records[tweet_id] = record
        if not records:
            return {"outcome": "gone", "note": "The posts are gone from X. Kept the saved text."}
        cut = {key: rec for key, rec in records.items() if rec["long_post"] or rec.get("quote_long")}
        if not cut:
            return {"outcome": "already_full", "note": "X says the saved text is the whole post."}
        usable = {key: rec for key, rec in cut.items()
                  if (rec["long_post"] and rec["complete"]) or (rec.get("quote_long") and rec.get("quote_complete"))}
        if not usable:
            return {"outcome": "unchanged", "note": "FxTwitter didn't have the full text this time. Try again later."}
        if item["kind"] == "video":
            return {"outcome": "apply", "journal": {"kind": "video",
                                                    "record": _journal_record(next(iter(usable.values())))}}
        return {"outcome": "apply", "journal": {"kind": "thread",
                                                "records": {k: _journal_record(v) for k, v in usable.items()}}}

    def _fetch_article_item(self, item: dict) -> dict:
        """A saved post that only links to an X Article: save the Article
        as its own item (or find the one already saved from the same link)."""
        if not self._fxtwitter():
            return {"outcome": "disabled", "note": SWITCHED_OFF}
        try:
            result = self._article_fetch(item["tweet_ids"][0])
        except x_extractor.XFetchError as exc:
            if exc.kind == "not_article":
                return {"outcome": "skipped", "note": "The post no longer links only to an X Article."}
            return self._fetch_failure(exc, gone_note="The post is gone from X. Kept the saved post.")
        except Exception as exc:
            log.warning("x text repair article fetch failed for %s: %s", item["video_id"], type(exc).__name__)
            return {"outcome": "network", "note": type(exc).__name__}
        if not isinstance(result, dict) or not result.get("ok") or result.get("source_type") != "x_article":
            return {"outcome": "unchanged", "note": "FxTwitter didn't have the Article this time. Try again later."}
        existing = article_video_id(str(result.get("url") or ""))
        row = self._index_getter().get_yoink(existing) if hasattr(self._index_getter(), "get_yoink") else None
        if row and not row.get("deleted_at"):
            new_id = existing  # already in the library (the extension, or an earlier cut-short run)
        else:
            try:
                new_id = self._persist_article(result) if self._persist_article else None
            except Exception as exc:
                log.warning("x text repair could not save article for %s: %s", item["video_id"], type(exc).__name__)
                new_id = None
        if not new_id:
            return {"outcome": "failed", "note": "Couldn't save the Article."}
        return {"outcome": "apply", "journal": {"kind": "article", "saved_as": new_id}}

    def _row(self, video_id: str) -> dict | None:
        for row in self._index_getter().x_text_rows():
            if row["video_id"] == video_id:
                return row
        return None
