"""Transcribe saves that have no words: a user-started, resumable backfill.

The helper (server.py) hands this module three callables:

* ``scan()`` lists saves that have, or can fetch again, media but no
  transcript, plus captures that never finished. Each item is a dict with
  ``key``, ``title``, ``duration``, ``saved_at``, ``media`` ("on_disk",
  "download" or "gone") and ``host`` ("youtube", "x" or "other").
* ``work(item, checkpoint, stop_event, network_ok)`` transcribes one item
  through the existing capture and local ASR path and returns an outcome:
  transcribed, no_speech, no_audio, gone, failed, skipped, blocked (no
  model), busy (another capture holds it), yielded (it let a capture run),
  backoff (a site refused) or wait_network (it needs a site that is resting).
  ``network_ok`` lists hosts that answered normally, which resets their
  strikes.
* ``capture_busy()`` says whether the user is capturing something now.

This module owns the order, the durable progress file, pause and resume,
back-off after a site refuses requests, and the rough time estimate. It never
deletes anything and never starts by itself: only ``start`` (or a Finish
request for one item) begins work, and a run the user started carries on
after a helper restart.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = "transcript-backfill.json"
STATE_VERSION = 1
ORDERS = ("longest", "newest")
DEFAULT_ORDER = "longest"

# Seconds of work per second of media until this run has measured its own
# rate. Uoink's local ASR guidance is 10-15 minutes per source hour, so this
# takes the slow end, plus a little for fetching media again.
DEFAULT_RATE = 0.27
# Length assumed for a save whose duration was never recorded.
UNKNOWN_DURATION_SEC = 120.0
# Waits after a site refuses requests, by strike (same steps as captures).
RATE_LIMIT_BACKOFF_SEC = (5 * 60, 20 * 60, 60 * 60)
BOT_CHECK_BACKOFF_SEC = (30 * 60, 60 * 60, 4 * 60 * 60)
# How long to wait before trying an item another capture is holding. Each
# try waits twice as long, up to BUSY_RETRY_SEC * 30 (15 minutes), and after
# MAX_BUSY_TRIES the item is set aside as failed for this run.
BUSY_RETRY_SEC = 30.0
MAX_BUSY_TRIES = 12
# Starts per item. A start is counted before the work begins and cleared when
# it ends, so one still counted means Uoink stopped (a crash, a kill) during
# it. After this many, the item is skipped instead of stopping Uoink again.
MAX_ATTEMPTS = 2
STOPPED_REASON = ("Uoink stopped while transcribing this one, twice, so it was skipped. "
                  "Start again to give it another try.")
BUSY_REASON = "Another capture kept this save busy, so it was skipped for now."
# A site's strikes are forgotten this long after its last wait ended.
STRIKE_MEMORY_SEC = 6 * 60 * 60
# How often the worker looks again while a capture runs.
CAPTURE_POLL_SEC = 0.5
# How long a scan stays fresh for status reads.
SCAN_TTL_SEC = 60.0
# Outcomes that settle an item for good (until the user starts over).
SETTLED = {"gone"}
WORDS_FOUND = "transcribed"
NO_WORDS = {"no_speech", "no_audio"}
STATUSES = ("idle", "running", "paused", "done")


class Paused(Exception):
    """Raised at a checkpoint when the user paused the run."""


class YieldToCapture(Exception):
    """Raised at a checkpoint called with ``wait=False`` while a capture runs.

    The caller holds a save's capture lock, which a capture may be waiting
    for, so it must let go instead of waiting (captures lock first)."""


def _now() -> float:
    return time.time()


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _duration(item: dict) -> float:
    try:
        value = float(item.get("duration") or 0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else UNKNOWN_DURATION_SEC


def order_items(items: list[dict], order: str) -> list[dict]:
    """Longest first (unknown lengths last), or newest saved first."""
    if order == "newest":
        return sorted(items, key=lambda i: (str(i.get("saved_at") or ""), i["key"]), reverse=True)

    def longest(item):
        try:
            seconds = float(item.get("duration") or 0)
        except (TypeError, ValueError):
            seconds = 0.0
        return (-seconds, _neg_text(str(item.get("saved_at") or "")), item["key"])
    return sorted(items, key=longest)


def _neg_text(text: str) -> tuple:
    # Newer saves first among equal lengths, without reversing the whole key.
    return tuple(-ord(ch) for ch in text)


def _empty_run() -> dict:
    return {"started_at": None, "finished_at": None, "total": 0, "done": 0,
            "transcribed": 0, "no_words": 0, "gone": 0, "failed": 0,
            "work_seconds": 0.0, "media_seconds": 0.0}


class TranscriptBackfill:
    """One library's backfill. Thread-safe; one worker thread at a time."""

    def __init__(self, state_dir, *, scan, work, capture_busy,
                 model_ready=lambda: (True, ""), clock=_now,
                 lower_priority=None, capture_poll=CAPTURE_POLL_SEC,
                 busy_retry=BUSY_RETRY_SEC, scan_ttl=SCAN_TTL_SEC):
        self.path = Path(state_dir) / STATE_FILE
        self._scan = scan
        self._work = work
        self._capture_busy = capture_busy
        self._model_ready = model_ready
        self._clock = clock
        self._lower_priority = lower_priority
        self._capture_poll = capture_poll
        self._busy_retry = busy_retry
        self._scan_ttl = scan_ttl
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._relaunch = False
        self._wake_refill = False
        self._queue: list[dict] = []
        self._items: dict[str, dict] = {}
        self._retry_at: dict[str, float] = {}
        self._busy_tries: dict[str, int] = {}
        # Items whose last try needed the network: they wait out a back-off.
        self._needs_network: set[str] = set()
        self._current: dict | None = None
        self._scan_cache: tuple[float, dict] | None = None
        self._state = self._load()

    # ---- durable state --------------------------------------------------
    def _load(self) -> dict:
        state = {"version": STATE_VERSION, "status": "idle", "order": DEFAULT_ORDER,
                 "run": _empty_run(), "results": {}, "settled": {}, "backoff": {},
                 "attempts": {}, "requested": [], "message": None}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return state
        if not isinstance(raw, dict):
            return state
        if raw.get("status") in STATUSES:
            state["status"] = raw["status"]
        if raw.get("order") in ORDERS:
            state["order"] = raw["order"]
        for key in ("run", "results", "settled", "backoff", "attempts"):
            if isinstance(raw.get(key), dict):
                state[key] = {**state[key], **raw[key]} if key == "run" else raw[key]
        if isinstance(raw.get("requested"), list):
            state["requested"] = [k for k in raw["requested"] if isinstance(k, str)]
        if isinstance(raw.get("message"), str):
            state["message"] = raw["message"]
        return state

    def _save(self) -> None:
        """Atomic write; a crash mid-write keeps the previous file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".part")
        data = json.dumps(self._state, ensure_ascii=False, indent=1, sort_keys=True)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            for delay in (0.05, 0.2, 0.5, None):
                try:
                    temporary.replace(self.path)
                    break
                except PermissionError:
                    if delay is None:
                        raise
                    time.sleep(delay)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    # ---- scanning -------------------------------------------------------
    def invalidate(self) -> None:
        with self._lock:
            self._scan_cache = None

    def _scan_now(self, *, fresh: bool = False) -> dict:
        with self._lock:
            cached = self._scan_cache
            if not fresh and cached and self._clock() - cached[0] < self._scan_ttl:
                return cached[1]
        result = self._scan() or {}
        result.setdefault("items", [])
        with self._lock:
            self._scan_cache = (self._clock(), result)
        return result

    def _workable(self, scan: dict) -> list[dict]:
        settled = self._state["settled"]
        return [item for item in scan["items"]
                if item.get("media") in ("on_disk", "download") and item["key"] not in settled]

    # ---- controls -------------------------------------------------------
    def start(self, order: str | None = None) -> dict:
        """Begin a fresh run over every save that still has no words."""
        if order is not None and order not in ORDERS:
            raise ValueError("order must be longest or newest")
        ready, why = self._model_ready()
        if not ready:
            return {"ok": False, "error": why, **self.status()}
        with self._lock:
            if self._alive() and self._state["status"] == "running":
                if order and order != self._state["order"]:
                    self._state["order"] = order
                    self._reorder()
                    self._save()
                return {"ok": True, **self.status()}
            self._state.update(status="running", message=None, results={})
            if order:
                self._state["order"] = order
            self._state["run"] = {**_empty_run(), "started_at": _iso(self._clock())}
            # A fresh Start gives every item its tries back and forgets
            # back-offs that already ran out. A restart never does.
            self._state["attempts"] = {}
            self._state["backoff"] = {host: entry for host, entry in self._state["backoff"].items()
                                      if self._backoff_active(host) > 0}
            self._queue = []
            self._retry_at = {}
            self._busy_tries = {}
            self._needs_network = set()
            self._wake_refill = True
            self._save()
            self._launch()
        return {"ok": True, **self.status()}

    def pause(self) -> dict:
        """Stop at the next safe point. The item in hand starts over later."""
        with self._lock:
            if self._state["status"] == "running":
                self._state["status"] = "paused"
            self._state["requested"] = []
            self._relaunch = False
            self._save()
            self._stop.set()
            self._wake.set()
        return {"ok": True, **self.status()}

    def resume(self) -> dict:
        ready, why = self._model_ready()
        if not ready:
            return {"ok": False, "error": why, **self.status()}
        with self._lock:
            if self._state["status"] != "paused":
                return {"ok": True, **self.status()}
            self._state.update(status="running", message=None)
            self._wake_refill = True
            self._save()
            self._launch()
        return {"ok": True, **self.status()}

    def finish(self, key: str) -> dict:
        """Do this one item next, whether or not a run is going."""
        ready, why = self._model_ready()
        if not ready:
            return {"ok": False, "error": why, **self.status()}
        scan = self._scan_now(fresh=True)
        item = next((i for i in scan["items"] if i["key"] == key), None)
        if item is None:
            return {"ok": False, "error": "That save is not waiting for words any more.",
                    **self.status()}
        with self._lock:
            self._state["settled"].pop(key, None)
            if key not in self._state["requested"]:
                self._state["requested"].append(key)
            self._items[key] = item
            self._save()
            self._launch()
        return {"ok": True, **self.status()}

    def resume_after_restart(self) -> bool:
        """Carry on a run the user started before the helper stopped."""
        with self._lock:
            if self._state["status"] == "running" or self._state["requested"]:
                self._launch()
                return True
        return False

    def wait(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    # ---- worker ---------------------------------------------------------
    def _alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _launch(self) -> None:
        # Caller holds the lock.
        if self._alive():
            if self._stop.is_set():
                # The old worker is still winding down after a pause. Start a
                # new one as soon as it exits instead of waking it.
                self._relaunch = True
            self._wake.set()
            return
        self._relaunch = False
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, name="transcript-backfill",
                                        daemon=True)
        self._thread.start()

    def _reorder(self) -> None:
        self._queue = order_items(self._queue, self._state["order"])

    def _fill_queue(self, scan: dict) -> None:
        # Caller holds the lock.
        done = set(self._state["results"])
        workable = self._workable(scan)
        for item in workable:
            self._items[item["key"]] = item
        if self._state["status"] != "running":
            self._queue = []
            return
        self._queue = order_items([i for i in workable if i["key"] not in done],
                                  self._state["order"])
        run = self._state["run"]
        run["total"] = int(run.get("done") or 0) + len(self._queue)

    def _backoff_active(self, host: str) -> float:
        entry = self._state["backoff"].get(host)
        if not isinstance(entry, dict):
            return 0.0
        left = float(entry.get("until") or 0) - self._clock()
        return left if left > 0 else 0.0

    def network_ok(self, host: str) -> bool:
        with self._lock:
            return self._backoff_active(host) <= 0

    def _next(self):
        """(item, wait_seconds). item None with wait 0 means nothing is left."""
        with self._lock:
            requested = []
            for key in list(self._state["requested"]):
                item = self._items.get(key)
                if item is None:
                    self._state["requested"].remove(key)
                else:
                    requested.append(item)
            pool = requested + (self._queue if self._state["status"] == "running" else [])
            soonest = None
            now = self._clock()
            for item in pool:
                wait = max(0.0, self._retry_at.get(item["key"], 0.0) - now)
                if item.get("media") == "download" or item["key"] in self._needs_network:
                    wait = max(wait, self._backoff_active(item.get("host") or "other"))
                if wait <= 0:
                    return item, 0.0
                soonest = wait if soonest is None else min(soonest, wait)
            return None, (soonest or 0.0)

    def _sleep(self, seconds: float) -> None:
        self._wake.wait(timeout=max(0.05, seconds))
        self._wake.clear()

    def _wait_for_captures(self) -> None:
        while self._capture_busy():
            if self._stop.is_set():
                raise Paused()
            self._stop.wait(self._capture_poll)

    def _checkpoint(self, position=None, *, wait: bool = True) -> None:
        """Between ASR segments: stop when paused, yield while capturing.

        With ``wait=False`` (the caller holds a capture lock) a running
        capture raises YieldToCapture instead of waiting for it."""
        if self._stop.is_set():
            raise Paused()
        if self._capture_busy():
            if not wait:
                raise YieldToCapture()
            with self._lock:
                if self._current is not None:
                    self._current["waiting"] = True
            self._wait_for_captures()
            with self._lock:
                if self._current is not None:
                    self._current["waiting"] = False
        if position is not None:
            with self._lock:
                if self._current is not None:
                    try:
                        self._current["position"] = max(0.0, float(position))
                    except (TypeError, ValueError):
                        pass

    def _run(self) -> None:
        if self._lower_priority is not None:
            try:
                self._lower_priority()
            except Exception:
                pass
        try:
            filled = False
            while not self._stop.is_set():
                if not filled or self._wake_refill:
                    # Scan outside the lock: a large library takes a moment.
                    self._wake_refill = False
                    scan = self._scan_now(fresh=True)
                    with self._lock:
                        self._fill_queue(scan)
                        self._save()
                    filled = True
                item, wait = self._next()
                if item is None:
                    if wait > 0:
                        self._sleep(min(wait, 60.0))
                        continue
                    with self._lock:
                        # A Finish request or a refill may have arrived after
                        # _next looked: take it instead of exiting.
                        if self._wake_refill or self._state["requested"]:
                            continue
                        if self._state["status"] == "running":
                            self._state["status"] = "done"
                            self._state["run"]["finished_at"] = _iso(self._clock())
                            self._save()
                    return
                self._wait_for_captures()
                self._do(item)
        except Paused:
            pass
        finally:
            with self._lock:
                self._current = None
                if self._thread is threading.current_thread():
                    self._thread = None
                self._scan_cache = None
                if self._relaunch:
                    self._launch()

    def _do(self, item: dict) -> None:
        key = item["key"]
        started = self._clock()
        with self._lock:
            tries = int(self._state["attempts"].get(key) or 0)
            if tries >= MAX_ATTEMPTS:
                # Started this many times and Uoink stopped each time before
                # it ended: skip it rather than stop Uoink again.
                self._state["attempts"].pop(key, None)
                try:
                    self._settle(item, key, {"outcome": "failed", "reason": STOPPED_REASON}, 0.0)
                finally:
                    self._save()
                return
            # Counted before the work starts and cleared when it ends; only a
            # helper that dies mid-item leaves it counted.
            self._state["attempts"][key] = tries + 1
            self._save()
            self._current = {"key": key, "title": item.get("title"),
                             "duration": item.get("duration"), "started": started,
                             "position": 0.0, "waiting": False}
        try:
            result = self._work(item, self._checkpoint, self._stop, self.network_ok) or {}
        except Paused:
            with self._lock:
                self._current = None
                self._state["attempts"].pop(key, None)
                self._save()
            raise
        except Exception as exc:  # one item never stops the run
            result = {"outcome": "failed", "reason": str(exc)[:300] or type(exc).__name__}
        elapsed = max(0.0, self._clock() - started)
        with self._lock:
            self._current = None
            self._state["attempts"].pop(key, None)
            try:
                self._settle(item, key, result, elapsed)
            finally:
                self._save()

    def _settle(self, item: dict, key: str, result: dict, elapsed: float) -> None:
        # Caller holds the lock and saves afterwards.
        outcome = result.get("outcome") or "failed"
        if outcome == "paused":
            raise Paused()
        requested = key in self._state["requested"]
        if outcome == "blocked":
            # Nothing can run (no transcription model): stop and say why.
            if self._state["status"] == "running":
                self._state["status"] = "paused"
            self._state["message"] = result.get("reason")
            self._state["requested"] = []
            self._stop.set()
            return
        if outcome == "yielded":
            # It let go so a capture could run. The loop waits for the
            # capture before trying it again. Not the item's fault: no count.
            self._retry_at[key] = self._clock() + min(1.0, self._busy_retry)
            return
        if outcome == "busy":
            # Another capture holds this save. Wait longer each time, and set
            # it aside after a while so the run can end.
            tries = self._busy_tries.get(key, 0) + 1
            if tries < MAX_BUSY_TRIES:
                self._busy_tries[key] = tries
                # The rest of the queue goes first.
                self._queue = ([q for q in self._queue if q["key"] != key]
                               + [q for q in self._queue if q["key"] == key])
                self._retry_at[key] = self._clock() + min(
                    self._busy_retry * 30, self._busy_retry * 2 ** (tries - 1))
                return
            self._busy_tries.pop(key, None)
            result, outcome = {"outcome": "failed", "reason": BUSY_REASON}, "failed"
        if outcome in ("backoff", "wait_network"):
            # It needs a site that is resting (or just refused): it waits for
            # that back-off like a download does, never in a tight loop.
            host = result.get("host") or item.get("host") or "other"
            if outcome == "backoff":
                self._strike(host, result.get("kind"), result.get("retry_after"))
            self._needs_network.add(key)
            self._retry_at[key] = self._clock() + self._busy_retry
            return
        self._busy_tries.pop(key, None)
        self._needs_network.discard(key)
        refused = result.get("refused")
        if isinstance(refused, dict):
            # Its captions were refused but the copy on disk still gave
            # words: rest that site anyway before asking it again.
            self._strike(refused.get("host") or item.get("host") or "other",
                         refused.get("kind"), refused.get("retry_after"))
        elif item.get("media") == "download" and outcome != "failed":
            self._state["backoff"].pop(item.get("host") or "other", None)
        for host in result.get("network_ok") or ():
            # That site answered normally: its strikes start over.
            if not (isinstance(refused, dict) and refused.get("host") == host):
                self._state["backoff"].pop(host, None)
        in_run = any(q["key"] == key for q in self._queue)
        self._queue = [q for q in self._queue if q["key"] != key]
        self._retry_at.pop(key, None)
        if requested:
            self._state["requested"].remove(key)
        entry = {"outcome": outcome, "at": _iso(self._clock()), "title": item.get("title")}
        if result.get("reason"):
            entry["reason"] = str(result["reason"])[:300]
        self._state["results"][key] = entry
        if outcome in SETTLED:
            self._state["settled"][key] = dict(entry)
        if in_run:
            run = self._state["run"]
            run["done"] = int(run.get("done") or 0) + 1
            counter = {WORDS_FOUND: "transcribed", "no_speech": "no_words",
                       "no_audio": "no_words", "gone": "gone", "failed": "failed"}.get(outcome)
            if counter:
                run[counter] = int(run.get(counter) or 0) + 1
            if outcome in (WORDS_FOUND, *NO_WORDS) and result.get("media_seconds"):
                run["work_seconds"] = float(run.get("work_seconds") or 0) + elapsed
                run["media_seconds"] = (float(run.get("media_seconds") or 0)
                                        + float(result["media_seconds"]))
        if item.get("half") or not in_run:
            self._scan_cache = None

    def _strike(self, host: str, kind: str | None, retry_after=None) -> None:
        # Caller holds the lock. Each strike waits longer, like the capture's
        # own YouTube back-off (5, 20, 60 minutes; bot checks 30 min to 4 h).
        # Strikes from a wait that ended long ago are forgotten.
        entry = self._state["backoff"].get(host) or {}
        strikes = int(entry.get("strikes") or 0)
        if float(entry.get("until") or 0) + STRIKE_MEMORY_SEC < self._clock():
            strikes = 0
        steps = BOT_CHECK_BACKOFF_SEC if kind == "bot_check" else RATE_LIMIT_BACKOFF_SEC
        try:
            asked = float(retry_after or 0)
        except (TypeError, ValueError):
            asked = 0.0
        delay = max(steps[min(strikes, len(steps) - 1)], asked)
        self._state["backoff"][host] = {"until": self._clock() + delay,
                                        "strikes": strikes + 1,
                                        "reason": kind or "rate_limited"}

    # ---- reporting ------------------------------------------------------
    def _rate(self) -> float:
        run = self._state["run"]
        media = float(run.get("media_seconds") or 0)
        if media >= 60:
            return max(0.01, float(run.get("work_seconds") or 0) / media)
        return DEFAULT_RATE

    def status(self) -> dict:
        try:
            scan = self._scan_now()
        except Exception as exc:  # the library can be briefly unreadable
            scan = {"items": [], "error": str(exc)}
        with self._lock:
            state = self._state
            settled = state["settled"]
            # The scan is cached for a minute; saves this run already settled
            # (words, no speech, gone) drop out of the count right away.
            resolved = {k for k, v in state["results"].items() if v.get("outcome") != "failed"}
            workable = [i for i in self._workable(scan) if i["key"] not in resolved]
            on_disk = sum(1 for i in workable if i.get("media") == "on_disk")
            download = sum(1 for i in workable if i.get("media") == "download")
            gone_keys = {i["key"] for i in scan["items"] if i.get("media") == "gone"}
            gone_keys.update(k for k, v in settled.items() if v.get("outcome") == "gone")
            running = state["status"] == "running"
            left_items = list(self._queue) if running and self._alive() else workable
            current = dict(self._current) if self._current else None
            remaining = sum(_duration(i) for i in left_items if not current or i["key"] != current["key"])
            if current:
                remaining += max(0.0, _duration(current) - float(current.get("position") or 0))
            eta = int(remaining * self._rate()) if (left_items or current) else 0
            run = dict(state["run"])
            backoff = {}
            for host in list(state["backoff"]):
                left = self._backoff_active(host)
                if left > 0:
                    backoff[host] = {"seconds_left": int(left),
                                     "reason": state["backoff"][host].get("reason")}
            failed = [{"key": k, "title": v.get("title"), "reason": v.get("reason")}
                      for k, v in state["results"].items() if v.get("outcome") == "failed"]
            half = [dict(i, settled=settled.get(i["key"], {}).get("outcome"))
                    for i in scan["items"] if i.get("half")]
            if current:
                fraction = None
                if current.get("duration"):
                    try:
                        fraction = min(1.0, float(current.get("position") or 0)
                                       / float(current["duration"]))
                    except (TypeError, ValueError, ZeroDivisionError):
                        fraction = None
                current = {"key": current["key"], "title": current.get("title"),
                           "fraction": fraction, "waiting_for_capture": bool(current.get("waiting"))}
            return {
                "state": state["status"],
                "pausing": state["status"] == "paused" and self._alive(),
                "order": state["order"],
                "message": state.get("message"),
                "count": len(workable),
                "on_disk": on_disk,
                "download": download,
                "gone": len(gone_keys),
                "no_words": int(scan.get("no_words") or 0),
                "progress": {
                    "done": int(run.get("done") or 0),
                    "left": len(left_items),
                    "total": int(run.get("total") or 0),
                    "transcribed": int(run.get("transcribed") or 0),
                    "no_words": int(run.get("no_words") or 0),
                    "gone": int(run.get("gone") or 0),
                    "failed": int(run.get("failed") or 0),
                    "eta_seconds": eta,
                    "started_at": run.get("started_at"),
                    "finished_at": run.get("finished_at"),
                },
                "current": current,
                "requested": list(state["requested"]),
                "backoff": backoff,
                "failed_items": failed[:20],
                "half_captures": half[:200],
                "half_capture_count": len(half),
                **({"scan_error": scan["error"]} if scan.get("error") else {}),
            }
