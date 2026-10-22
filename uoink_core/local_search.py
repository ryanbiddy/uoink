"""Opt-in CPU retrieval, with no work or optional dependency imports at import time.

Construct LocalSearch with the helper's resolved DATA_ROOT and its existing Index.
Only the derived database is written here. See _scratch/embed/INTEGRATION.md for
the transport hooks deferred to the next pass.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import struct
import threading
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
from typing import NamedTuple
from urllib.request import Request, urlopen

MODEL_REVISION = "5090578d9565bb06545b4552f76e6bc2c93e4a66"
MODEL_ID = "embeddinggemma-300m-onnx-q8-v1"
MODEL_BASE = f"https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX/resolve/{MODEL_REVISION}/"
MODEL_FILES = (
    ("onnx/model_quantized.onnx", 567874, "172efde319fe1542dc41f31be6154910b05b78f7a861c265c4600eec906bd6d8"),
    ("onnx/model_quantized.onnx_data", 308890624, "705626e28e4c23c82ade34566b4197d97f534c12275fa406dfb71e9937d388c0"),
    ("tokenizer.json", 20323312, "4dda02faaf32bc91031dc8c88457ac272b00c1016cc679757d1c441b248b9c47"),
)
DOWNLOAD_BYTES = sum(size for _, size, _ in MODEL_FILES)
TERMS_VERSION = "gemma-2026-04-01"
POLICY_VERSION = "gemma-prohibited-use-2024-02-21"
DIMENSIONS = 768
BATCH_SIZE = 8
MAX_THREADS = 2
QUERY_PREFIX = "task: search result | query: "
FILTERS = frozenset({"channel", "topic", "hook_type", "platform", "source_type", "author", "date_from", "date_to"})
_CACHE_VERSION = "clips-or-windows-v1:" + MODEL_REVISION


class TermsRequired(ValueError):
    """Explicit acceptance of the current terms is required."""


class IntegrityError(ValueError):
    """Pinned model bytes did not match."""


class SearchUnavailable(RuntimeError):
    """The transport may fall back to keyword search."""


class _Paused(Exception):
    pass


def verified(path: Path, size: int, checksum: str) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == checksum
    except OSError:
        return False


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ModelManager:
    """One installation's persistent model and dated consent record.

    No paths default to the production profile. Downloads restart a failed file
    and reuse already verified files. The caller must serialize manager writes
    (LocalSearch does so), and must never record acceptance on a user's behalf.
    """

    def __init__(self, data_root):
        self.root = Path(data_root).resolve()
        self.directory = self.root / "models" / MODEL_ID
        self.terms_path = self.root / "embeddinggemma-terms.json"

    def _check_paths(self):
        for path in (self.terms_path, self.terms_path.with_name(self.terms_path.name + ".part"),
                     self.directory, self.directory / "onnx"):
            if path.resolve() != path:
                raise ValueError("Model paths must stay inside the active data root")

    def acceptance(self):
        try:
            record = json.loads(self.terms_path.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(record["accepted_at"])
            if (record.get("terms_version") == TERMS_VERSION
                    and record.get("policy_version") == POLICY_VERSION
                    and record.get("accepted") is True and stamp.utcoffset() is not None):
                return record
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        return None

    def accept_terms(self, *, accepted: bool, terms_version: str):
        if accepted is not True or terms_version != TERMS_VERSION:
            raise TermsRequired("Accept the current Gemma terms and use policy first")
        self._check_paths()
        record = {"accepted": True, "terms_version": TERMS_VERSION,
                  "policy_version": POLICY_VERSION,
                  "accepted_at": datetime.now(timezone.utc).isoformat()}
        _atomic_json(self.terms_path, record)
        return record

    def require_terms(self):
        if self.acceptance() is None:
            raise TermsRequired("Accept the current Gemma terms and use policy first")

    def present(self):
        return all((self.directory / name).is_file() for name, _, _ in MODEL_FILES)

    def verify(self):
        self.require_terms()
        self._check_paths()
        for name, size, checksum in MODEL_FILES:
            if not verified(self.directory / name, size, checksum):
                raise IntegrityError("Model size or SHA-256 mismatch: " + name)

    def download(self, *, progress=lambda phase, received: None, checkpoint=lambda: None):
        # Enforced here, not just in a route or UI checkbox.
        self.require_terms()
        self._check_paths()
        received = 0
        for name, size, checksum in MODEL_FILES:
            checkpoint()
            target = self.directory / name
            if target.resolve() != target or target.with_name(target.name + ".part").is_symlink():
                raise ValueError("Model file must not be a symlink")
            progress("verifying", received)
            if verified(target, size, checksum):
                received += size
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            try:
                progress("downloading", received)
                request = Request(MODEL_BASE + name, headers={"User-Agent": "Uoink-local-search/1"})
                with urlopen(request, timeout=30) as response, temporary.open("wb") as out:
                    count = 0
                    while chunk := response.read(1024 * 1024):
                        checkpoint()
                        count += len(chunk)
                        if count > size:
                            raise IntegrityError("Model download exceeded pinned size: " + name)
                        out.write(chunk)
                        progress("downloading", received + count)
                    out.flush()
                    os.fsync(out.fileno())
                progress("verifying", received + count)
                if not verified(temporary, size, checksum):
                    raise IntegrityError("Model size or SHA-256 mismatch: " + name)
                checkpoint()
                temporary.replace(target)
                received += size
            finally:
                temporary.unlink(missing_ok=True)
        progress("verifying", received)
        self.verify()

    def remove(self):
        # Only this fixed child can be removed, never an arbitrary supplied path.
        self._check_paths()
        parent = self.root / "models"
        if parent.resolve() != parent or self.directory.resolve().parent != parent:
            raise ValueError("Model path must stay inside the active data root")
        if self.directory.is_symlink():
            raise ValueError("Model directory must not be a symlink")
        if self.directory.exists():
            shutil.rmtree(self.directory)
        self.terms_path.unlink(missing_ok=True)


class EmbeddingGemma:
    """Verified local tokenizer and ONNX graph, CPU only, bounded batches/threads."""

    def __init__(self, manager: ModelManager, *, threads=MAX_THREADS, batch_size=BATCH_SIZE):
        manager.verify()
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.batch_size = max(1, min(BATCH_SIZE, int(batch_size)))
        self.tokenizer = Tokenizer.from_file(str(manager.directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=2048)
        self.tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(MAX_THREADS, int(threads)))
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        self.session = ort.InferenceSession(str(manager.directory / "onnx/model_quantized.onnx"),
                                           sess_options=options, providers=["CPUExecutionProvider"])
        self.lock = threading.Lock()

    def embed(self, texts, *, wait=True):
        texts = list(texts)
        if not texts:
            return self.np.empty((0, DIMENSIONS), dtype="float32")
        if not self.lock.acquire(blocking=wait):
            raise SearchUnavailable("The search model is busy; use keyword search")
        try:
            batches = []
            for start in range(0, len(texts), self.batch_size):
                # Serial encoding avoids the tokenizers global Rayon worker pool.
                batch = [self.tokenizer.encode(text) for text in texts[start:start + self.batch_size]]
                width = max(len(item.ids) for item in batch)
                inputs = {"input_ids": self.np.asarray([
                    item.ids + [0] * (width - len(item.ids)) for item in batch], dtype="int64"),
                    "attention_mask": self.np.asarray([
                        item.attention_mask + [0] * (width - len(item.ids)) for item in batch], dtype="int64")}
                output = self.session.run(["sentence_embedding"], inputs)[0]
                if output.shape != (len(batch), DIMENSIONS) or not self.np.isfinite(output).all():
                    raise ValueError("Invalid embedding output")
                norms = self.np.linalg.norm(output, axis=1, keepdims=True)
                if (norms <= 1e-12).any():
                    raise ValueError("Zero embedding output")
                batches.append((output / norms).astype("float32"))
            return self.np.vstack(batches)
        finally:
            self.lock.release()


@dataclass(frozen=True)
class Passage:
    passage_id: str
    text: str
    span: dict
    timestamp_seconds: float | None = None


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    content: str
    passages: tuple[Passage, ...]

    @property
    def fingerprint(self):
        # Includes all content and citation coordinates, even if a clip is reused.
        payload = json.dumps([_CACHE_VERSION, asdict(self)], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def word_passages(text):
    """230 words / 40 overlap, with exact half-open character and word spans."""
    words = list(re.finditer(r"\S+", text))
    result = []
    for start in range(0, len(words), 190):
        end = min(start + 230, len(words))
        lo, hi = words[start].start(), words[end - 1].end()
        result.append(Passage(f"text:{start}", text[lo:hi],
                              {"kind": "text", "char_start": lo, "char_end": hi,
                               "word_start": start, "word_end": end}))
        if end == len(words):
            break
    return tuple(result)


class IndexSources:
    """Read current Index snapshots; never opens captures or writes the main DB."""

    def __init__(self, index):
        self.index = index

    def snapshot(self, *, source_id=None, filters=None):
        filters = dict(filters or {})
        if filters.keys() - FILTERS:
            raise ValueError("Unknown embedding search filter")
        clauses, params = ["y.deleted_at IS NULL"], []
        if source_id is not None:
            clauses.append("y.video_id = ?")
            params.append(source_id)
        for key in sorted(FILTERS - {"date_from", "date_to"}):
            if filters.get(key):
                clauses.append(f"y.{key} = ?")
                params.append(filters[key])
        if filters.get("date_from"):
            datetime.strptime(filters["date_from"], "%Y-%m-%d")
            clauses.append("y.yoinked_at >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            end = datetime.strptime(filters["date_to"], "%Y-%m-%d") + timedelta(days=1)
            clauses.append("y.yoinked_at < ?")
            params.append(end.strftime("%Y-%m-%d"))
        sources = []
        with self.index.read_snapshot() as db:
            rows = db.execute("SELECT y.video_id, y.title, COALESCE(f.content, '') AS content "
                              "FROM yoinks y LEFT JOIN yoinks_fts f ON f.video_id=y.video_id "
                              "WHERE " + " AND ".join(clauses) + " ORDER BY y.video_id", params).fetchall()
            for row in rows:
                identity, title, content = row["video_id"], row["title"] or "", row["content"]
                clips = db.execute("SELECT clip_id, seq, start, end, text, media_revision "
                                   "FROM clips WHERE video_id=? ORDER BY seq, clip_id", (identity,)).fetchall()
                passages = tuple(Passage(f"clip:{clip['clip_id']}", clip["text"],
                                         {"kind": "clip", "clip_id": clip["clip_id"], "seq": clip["seq"],
                                          "start": clip["start"], "end": clip["end"],
                                          "media_revision": clip["media_revision"]}, clip["start"])
                                 for clip in clips if clip["text"].strip())
                if not passages:
                    citations = db.execute(
                        "SELECT kind, seq, text, timestamp_start, timestamp_end FROM citations "
                        "WHERE video_id=? AND kind != 'screenshot' ORDER BY kind, seq", (identity,)).fetchall()
                    passages = tuple(Passage(f"citation:{c['kind']}:{c['seq']}", c["text"],
                                             {"kind": "citation", "citation_kind": c["kind"], "seq": c["seq"],
                                              "start": c["timestamp_start"], "end": c["timestamp_end"]},
                                             c["timestamp_start"])
                                     for c in citations if (c["text"] or "").strip())
                sources.append(Source(identity, title, content, passages or word_passages(content or title)))
        return sources


class SearchHit(NamedTuple):
    source_id: str
    passage_id: str
    span: dict
    timestamp_seconds: float | None
    score: float


def _unit_vector(vector):
    values = [float(value) for value in vector]
    if len(values) != DIMENSIONS or not all(math.isfinite(value) for value in values):
        raise ValueError("Invalid embedding vector")
    norm = math.sqrt(math.fsum(value * value for value in values))
    if norm <= 1e-12:
        raise ValueError("Zero embedding vector")
    return [value / norm for value in values]


class VectorStore:
    """Disposable SQLite cache. Each connection closes before returning."""

    def __init__(self, path):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS vectors (source_id TEXT NOT NULL, passage_id TEXT NOT NULL, "
                       "fingerprint TEXT NOT NULL, span TEXT NOT NULL, timestamp_seconds REAL, vector BLOB NOT NULL, "
                       "PRIMARY KEY(source_id, passage_id), FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE)")
            return db
        except BaseException:
            db.close()
            raise

    def fingerprints(self):
        if not self.path.exists():
            return {}
        with closing(self._connect()) as db:
            return dict(db.execute("SELECT source_id, fingerprint FROM sources"))

    def invalidate(self, live, *, only=None):
        if not self.path.exists():
            return
        with closing(self._connect()) as db, db:
            for identity, fingerprint in db.execute("SELECT source_id, fingerprint FROM sources").fetchall():
                if (only is None or identity == only) and live.get(identity) != fingerprint:
                    db.execute("DELETE FROM sources WHERE source_id=?", (identity,))

    def replace(self, source, vectors):
        if len(vectors) != len(source.passages):
            raise ValueError("Passage and embedding counts differ")
        fingerprint = source.fingerprint
        rows = [(source.source_id, p.passage_id, fingerprint, json.dumps(p.span, sort_keys=True),
                 p.timestamp_seconds, struct.pack("<768f", *_unit_vector(v)))
                for p, v in zip(source.passages, vectors)]
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sources WHERE source_id=?", (source.source_id,))
            db.execute("INSERT INTO sources VALUES (?, ?)", (source.source_id, fingerprint))
            db.executemany("INSERT INTO vectors VALUES (?, ?, ?, ?, ?, ?)", rows)

    def search(self, vector, live, limit):
        if not self.path.exists():
            return []
        query = _unit_vector(vector)
        best = {}
        with closing(self._connect()) as db:
            for identity, passage, fingerprint, span, timestamp, blob in db.execute(
                    "SELECT * FROM vectors ORDER BY source_id, passage_id"):
                if live.get(identity) != fingerprint:
                    continue
                values = struct.unpack("<768f", blob)
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("Invalid stored embedding")
                score = math.fsum(a * b for a, b in zip(query, values))
                if identity not in best or score > best[identity].score:
                    best[identity] = SearchHit(identity, passage, json.loads(span), timestamp, score)
        return sorted(best.values(), key=lambda hit: (-hit.score, hit.source_id))[:limit]

    def remove(self):
        for suffix in ("", "-wal", "-shm", "-journal"):
            self.path.with_name(self.path.name + suffix).unlink(missing_ok=True)


def rrf_merge(keyword_ranked, embedding_ranked, k=60, depth=100):
    """Return (source_id, RRF score) pairs, one vote per source per input list.

    Inputs may contain IDs, SearchHits, tuples beginning with an ID, or mappings
    with source_id/video_id. Ranks start at 1. Depth cuts input rows before
    deduplication. Exact ties retain first encounter order, keyword list first.
    """
    if not isinstance(k, int) or k < 0 or not isinstance(depth, int) or depth < 0:
        raise ValueError("k and depth must be nonnegative integers")
    scores = {}
    for ranking in (keyword_ranked, embedding_ranked):
        seen = set()
        for rank, item in enumerate(islice(ranking, depth), 1):
            identity = (item.get("source_id", item.get("video_id")) if isinstance(item, dict)
                        else item[0] if isinstance(item, (tuple, list)) else item)
            if identity is None:
                raise ValueError("Ranked result has no source id")
            if identity not in seen:
                scores[identity] = scores.get(identity, 0.0) + 1.0 / (k + rank)
                seen.add(identity)
    return sorted(scores.items(), key=lambda item: -item[1])


class LocalSearch:
    """One helper-owned instance. Mutations schedule one cooperative worker.

    start() scans for changes without downloading. download() explicitly fetches
    the model, then indexes. pause() stops at a batch boundary; start() resumes.
    update_source(id) queues an incremental upsert or deletion. remove() waits
    for work to stop, unloads the model, and deletes model, consent and vectors.
    """

    def __init__(self, data_root, index, *, model_factory=EmbeddingGemma):
        self.root = Path(data_root).resolve()
        main_path = Path(index._path).resolve()
        if main_path.parent != self.root:
            raise ValueError("Pass the active index's data root")
        self.manager = ModelManager(self.root)
        self.sources = IndexSources(index)
        self.store = VectorStore(self.root / "search-vectors.db")
        if (self.store.path.resolve() != self.store.path or self.store.path == main_path
                or (self.store.path.exists() and main_path.exists()
                    and self.store.path.samefile(main_path))):
            raise ValueError("Vector database must be separate from the main index")
        self.model_factory = model_factory
        self._model = None
        self._state_lock = threading.RLock()
        self._control = threading.RLock()
        self._activity = threading.RLock()
        self._stop = threading.Event()
        self._worker = None
        self._pending = set()
        self._full = self._download = False
        self._paused = False
        self._state = "not_installed"
        self._error = ""
        self._done = self._total = self._received = 0

    def _set(self, phase, **values):
        with self._state_lock:
            self._state = phase
            for name, value in values.items():
                setattr(self, "_" + name, value)

    def status(self):
        with self._state_lock:
            def disk_bytes(paths):
                total = 0
                for path in paths:
                    try:
                        if path.is_file():
                            total += path.stat().st_size
                    except FileNotFoundError:
                        pass  # A download replace or remove can run during polling.
                return total

            model_bytes = disk_bytes(self.manager.directory.rglob("*"))
            vector_bytes = disk_bytes(self.root.glob("search-vectors.db*"))
            return {"state": self._state, "message": self._error, "paused": self._paused,
                    "done": self._done, "total": self._total, "bytes": self._received,
                    "download_bytes": DOWNLOAD_BYTES, "terms_version": TERMS_VERSION,
                    "acceptance": self.manager.acceptance(), "model": MODEL_ID,
                    "model_bytes": model_bytes, "vector_bytes": vector_bytes,
                    "disk_bytes": model_bytes + vector_bytes}

    progress = status

    def accept_terms(self, *, accepted, terms_version):
        with self._control:
            record = self.manager.accept_terms(accepted=accepted, terms_version=terms_version)
            self._set("not_installed", error="")
            return record

    def _require_terms(self):
        try:
            self.manager.require_terms()
        except TermsRequired:
            self._set("terms_needed")
            raise

    def _launch(self):
        # Caller owns _state_lock. Publishing None on exit uses the same lock,
        # so a capture arriving as a worker exits cannot be lost.
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="embeddinggemma-index", daemon=True)
            self._worker.start()

    def start(self, *, download=False):
        with self._control:
            self._require_terms()
            if not download and not self.manager.present():
                self._set("not_installed")
                return False
            with self._state_lock:
                self._stop.clear()
                self._paused = False
                self._full = True
                self._download = self._download or download
                self._error = ""
                self._launch()
            return True

    def download(self):
        return self.start(download=True)

    def update_source(self, source_id):
        with self._control:
            if not self.manager.acceptance() or not self.manager.present():
                return False
            with self._state_lock:
                self._pending.add(str(source_id))
                if not self._paused:
                    self._launch()
            return True

    def wait(self, timeout=None):
        with self._state_lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout)
            return not worker.is_alive()
        return True

    def pause(self, *, timeout=30):
        with self._control:
            with self._state_lock:
                self._paused = True
                self._stop.set()
            return self.wait(timeout)

    def rebuild(self):
        with self._control:
            if not self.pause():
                raise SearchUnavailable("Wait for the current model batch to stop")
            with self._activity:
                self.store.remove()
            return self.start()

    def remove(self):
        with self._control:
            if not self.pause():
                raise SearchUnavailable("Wait for the model operation to stop, then remove again")
            with self._activity:
                self._model = None
                self.manager.remove()
                self.store.remove()
            with self._state_lock:
                self._pending.clear()
                self._full = self._download = self._paused = False
                self._set("not_installed", error="", done=0, total=0, received=0)

    def _checkpoint(self):
        if self._stop.is_set():
            raise _Paused()

    def _download_progress(self, phase, received):
        self._set(phase, received=received)

    def _sync(self, identities):
        documents = self.sources.snapshot() if identities is None else [
            doc for identity in sorted(identities) for doc in self.sources.snapshot(source_id=identity)]
        live = {doc.source_id: doc.fingerprint for doc in documents}
        if identities is None:
            self.store.invalidate(live)
        else:
            for identity in identities:
                self.store.invalidate(live, only=identity)
        existing = self.store.fingerprints()
        self._set("indexing", done=0, total=len(documents))
        for done, doc in enumerate(documents, 1):
            self._checkpoint()
            if existing.get(doc.source_id) != doc.fingerprint:
                vectors = []
                for offset in range(0, len(doc.passages), BATCH_SIZE):
                    self._checkpoint()
                    texts = [f"title: {doc.title or 'none'} | text: {p.text}"
                             for p in doc.passages[offset:offset + BATCH_SIZE]]
                    with self._activity:
                        vectors.extend(self._model.embed(texts))
                self._checkpoint()
                # A capture can change while inference runs. Never publish it
                # under an obsolete fingerprint or resurrect a deleted source.
                current = self.sources.snapshot(source_id=doc.source_id)
                if current and current[0].fingerprint == doc.fingerprint:
                    self.store.replace(doc, vectors)
                else:
                    with self._state_lock:
                        self._pending.add(doc.source_id)
            self._set("indexing", done=done)

    def _run(self):
        try:
            while True:
                with self._state_lock:
                    full, download, identities = self._full, self._download, self._pending
                    self._full = self._download = False
                    self._pending = set()
                self._checkpoint()
                if download:
                    with self._activity:
                        self._model = None
                    self.manager.download(progress=self._download_progress, checkpoint=self._checkpoint)
                if self._model is None:
                    self._set("verifying")
                    self.manager.verify()
                    with self._activity:
                        self._model = self.model_factory(self.manager)
                self._sync(None if full else identities)
                with self._state_lock:
                    if not (self._pending or self._full or self._download):
                        self._set("ready")
                        self._worker = None
                        return
        except _Paused:
            pass
        except Exception as exc:
            message = (str(exc) if isinstance(exc, (TermsRequired, IntegrityError))
                       else "Local search failed. Retry setup or rebuild the derived index.")
            self._set("error", error=message)
        finally:
            with self._state_lock:
                # A new worker can have started after the ready transition.
                if self._worker is threading.current_thread():
                    self._worker = None

    def embedding_search(self, query, limit=100, filters=None):
        if not isinstance(query, str):
            raise TypeError("query must be text")
        filters = dict(filters or {})
        if filters.keys() - FILTERS:
            raise ValueError("Unknown embedding search filter")
        for key in ("date_from", "date_to"):
            if filters.get(key):
                datetime.strptime(filters[key], "%Y-%m-%d")
        limit = max(0, min(100, int(limit)))
        if not query.strip() or not limit:
            return []
        self._require_terms()
        if not self._activity.acquire(blocking=False):
            raise SearchUnavailable("The search model is busy; use keyword search")
        try:
            if self._model is None:
                raise SearchUnavailable("Start local search before querying")
            # Full snapshot for invalidation, filtered snapshot for eligibility.
            live = {doc.source_id: doc.fingerprint for doc in self.sources.snapshot()}
            self.store.invalidate(live)
            eligible = ({doc.source_id: doc.fingerprint for doc in self.sources.snapshot(filters=filters)}
                        if filters else live)
            vector = self._model.embed([QUERY_PREFIX + query], wait=False)[0]
            hits = self.store.search(vector, eligible, limit)
            # Recheck after inference so edits/deletes during the query cannot
            # escape through a vector read from the earlier snapshot.
            current = {doc.source_id: doc.fingerprint for doc in self.sources.snapshot(filters=filters)}
            return [hit for hit in hits if current.get(hit.source_id) == eligible.get(hit.source_id)]
        except SearchUnavailable:
            raise
        except Exception:
            message = "Local search failed. Retry setup or rebuild the derived index."
            self._set("error", error=message)
            raise SearchUnavailable(message) from None
        finally:
            self._activity.release()
