"""Offline Lane S tests. All libraries and models live in pytest temp folders."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from uoink_core import local_search as ls


class TinyIndex:
    """Only the current tables read by the adapter, with a thread-safe snapshot."""

    def __init__(self, root):
        self._path = root / "index.db"
        self.db = sqlite3.connect(self._path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
            CREATE TABLE yoinks(video_id TEXT PRIMARY KEY, title TEXT, deleted_at TEXT,
              channel TEXT, topic TEXT, hook_type TEXT, platform TEXT, source_type TEXT,
              author TEXT, yoinked_at TEXT);
            CREATE TABLE yoinks_fts(video_id TEXT PRIMARY KEY, content TEXT);
            CREATE TABLE clips(clip_id INTEGER PRIMARY KEY, video_id TEXT, seq INTEGER,
              start REAL, end REAL, text TEXT, media_revision TEXT);
            CREATE TABLE citations(video_id TEXT, kind TEXT, seq INTEGER, text TEXT,
              timestamp_start REAL, timestamp_end REAL);
        """)

    @contextmanager
    def read_snapshot(self):
        with self.lock:
            yield self.db

    def seed(self, identity="mars", content="Mars has rusty red soil", **fields):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO yoinks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (identity, fields.get("title", identity), fields.get("deleted_at"),
                             fields.get("channel", "science"), fields.get("topic", "space"),
                             fields.get("hook_type", "question"), fields.get("platform", "web"),
                             fields.get("source_type", "article"), fields.get("author", "Ada"),
                             fields.get("yoinked_at", "2026-10-21T12:00:00")))
            self.db.execute("INSERT OR REPLACE INTO yoinks_fts VALUES (?, ?)", (identity, content))


@pytest.fixture
def index(tmp_path):
    result = TinyIndex(tmp_path)
    yield result
    result.db.close()


@pytest.fixture
def tiny_files(monkeypatch):
    data = b"verified model fixture"
    files = (("onnx/model_quantized.onnx", len(data), hashlib.sha256(data).hexdigest()),)
    monkeypatch.setattr(ls, "MODEL_FILES", files)
    monkeypatch.setattr(ls, "DOWNLOAD_BYTES", len(data))
    return data


def install(manager, data):
    manager.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    for name, _, _ in ls.MODEL_FILES:
        target = manager.directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def vector(axis):
    result = [0.0] * ls.DIMENSIONS
    result[axis] = 1.0
    return result


class FakeModel:
    def __init__(self, manager):
        manager.verify()
        self.calls = []

    def embed(self, texts, *, wait=True):
        self.calls.append(list(texts))
        return [vector(0 if any(word in text.split(" | text: ")[-1].lower()
                               for word in ("mars", "rust")) else 1)
                for text in texts]


@pytest.fixture
def engine(tmp_path, index, tiny_files):
    search = ls.LocalSearch(tmp_path, index, model_factory=FakeModel)
    install(search.manager, tiny_files)
    yield search
    assert search.pause(timeout=5)


def ready(engine):
    assert engine.start()
    assert engine.wait(5)
    assert engine.status()["state"] == "ready", engine.status()


def test_download_refuses_before_terms_and_without_network(tmp_path, monkeypatch):
    manager = ls.ModelManager(tmp_path)
    monkeypatch.setattr(ls, "urlopen", lambda *a, **kw: pytest.fail("Network used before consent"))
    with pytest.raises(ls.TermsRequired):
        manager.download()
    assert not manager.directory.exists()
    for value in (False, "true", 1, None):
        with pytest.raises(ls.TermsRequired):
            manager.accept_terms(accepted=value, terms_version=ls.TERMS_VERSION)
    with pytest.raises(ls.TermsRequired):
        manager.accept_terms(accepted=True, terms_version="old")


@pytest.mark.parametrize("record", [None, {}, {"accepted": True},
    {"accepted": True, "terms_version": ls.TERMS_VERSION, "policy_version": ls.POLICY_VERSION,
     "accepted_at": "2026-10-21"},
    {"accepted": True, "terms_version": "old", "policy_version": ls.POLICY_VERSION,
     "accepted_at": "2026-10-21T00:00:00+00:00"}])
def test_missing_outdated_or_undated_record_refuses(tmp_path, record):
    manager = ls.ModelManager(tmp_path)
    manager.terms_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ls.TermsRequired):
        manager.download()


@pytest.mark.parametrize("payload", [b"x", b"x" * 22, b"x" * 23])
def test_size_and_sha_mismatches_never_replace(tmp_path, tiny_files, monkeypatch, payload):
    manager = ls.ModelManager(tmp_path)
    install(manager, tiny_files)
    target = manager.directory / ls.MODEL_FILES[0][0]
    target.write_bytes(b"previous file")
    monkeypatch.setattr(ls, "urlopen", lambda *a, **kw: io.BytesIO(payload))
    with pytest.raises(ls.IntegrityError):
        manager.download()
    assert target.read_bytes() == b"previous file"
    assert not target.with_name(target.name + ".part").exists()


def test_atomic_download_restart_reuse_and_consent_timestamp(tmp_path, tiny_files, monkeypatch):
    manager = ls.ModelManager(tmp_path)
    record = manager.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    assert record["accepted_at"].endswith("+00:00")
    target = manager.directory / ls.MODEL_FILES[0][0]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(b"interrupted")
    calls, phases = [], []

    def response(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(tiny_files)

    def progress(phase, received):
        phases.append((phase, received))
        if phase == "downloading":
            assert target.read_bytes() == b"old"

    monkeypatch.setattr(ls, "urlopen", response)
    manager.download(progress=progress)
    manager.download()
    assert target.read_bytes() == tiny_files
    assert not temporary.exists()
    assert calls == [ls.MODEL_BASE + ls.MODEL_FILES[0][0]]
    assert ("downloading", len(tiny_files)) in phases
    assert phases[-1] == ("verifying", len(tiny_files))


def test_failed_atomic_replace_keeps_target(tmp_path, tiny_files, monkeypatch):
    manager = ls.ModelManager(tmp_path)
    install(manager, tiny_files)
    target = manager.directory / ls.MODEL_FILES[0][0]
    target.write_bytes(b"old")
    monkeypatch.setattr(ls, "urlopen", lambda *a, **kw: io.BytesIO(tiny_files))
    monkeypatch.setattr(Path, "replace", lambda *a: (_ for _ in ()).throw(OSError("in use")))
    with pytest.raises(OSError):
        manager.download()
    assert target.read_bytes() == b"old"
    assert not target.with_name(target.name + ".part").exists()


def test_edit_soft_delete_hard_delete_restore_and_restart(engine, index):
    index.seed()
    index.seed("bread", "Knead sourdough bread", topic="food")
    ready(engine)
    assert [hit.source_id for hit in engine.embedding_search("rust")] == ["mars", "bread"]
    before = engine.store.fingerprints()
    index.seed(content="Changed Mars content")
    # No hook required to suppress obsolete vectors.
    assert "mars" not in [hit.source_id for hit in engine.embedding_search("rust")]
    assert "mars" not in engine.store.fingerprints()
    assert engine.update_source("mars")
    assert engine.wait(5)
    assert engine.store.fingerprints()["mars"] != before["mars"]
    index.seed(deleted_at="2026-10-21")
    assert "mars" not in [hit.source_id for hit in engine.embedding_search("rust")]
    index.seed()
    engine.update_source("mars")
    assert engine.wait(5)
    assert engine.embedding_search("rust")[0].source_id == "mars"
    with index.db:
        index.db.execute("DELETE FROM yoinks WHERE video_id='mars'")
    engine.update_source("mars")
    assert engine.wait(5)
    assert set(engine.store.fingerprints()) == {"bread"}
    other = ls.LocalSearch(engine.root, index, model_factory=FakeModel)
    ready(other)
    assert other._model.calls == []  # unchanged sources reuse persisted vectors
    assert other.embedding_search("bread")[0].source_id == "bread"


def test_clip_spans_timestamps_max_per_source_and_metadata_changes(engine, index):
    index.seed(content="Transcript")
    with index.db:
        index.db.executemany("INSERT INTO clips VALUES (?, 'mars', ?, ?, ?, ?, ?)", [
            (14, 0, 12.5, 50, "Bread recipe", "revision-a"),
            (15, 1, 50, 90, "Mars rusty surface", "revision-a")])
    ready(engine)
    hit, = engine.embedding_search("rust")
    assert isinstance(hit, tuple)
    assert hit.passage_id == "clip:15"
    assert hit.span == {"kind": "clip", "clip_id": 15, "seq": 1, "start": 50.0,
                        "end": 90.0, "media_revision": "revision-a"}
    assert hit.timestamp_seconds == 50
    with index.db:
        index.db.execute("UPDATE clips SET start=51 WHERE clip_id=15")
    assert engine.embedding_search("rust") == []


def test_citation_fallback_and_word_offsets(index):
    index.seed()
    with index.db:
        index.db.execute("INSERT INTO citations VALUES ('mars', 'transcript_chunk', 3, 'Mars', 9.5, 15)")
    source, = ls.IndexSources(index).snapshot()
    assert source.passages[0].passage_id == "citation:transcript_chunk:3"
    assert source.passages[0].timestamp_seconds == 9.5
    text = "  " + " \n".join(f"word{i}" for i in range(460)) + "  "
    passages = ls.word_passages(text)
    assert [len(p.text.split()) for p in passages] == [230, 230, 80]
    assert passages[0].text.split()[-40:] == passages[1].text.split()[:40]
    for passage in passages:
        assert passage.text == text[passage.span["char_start"]:passage.span["char_end"]]
        assert passage.timestamp_seconds is None


def test_filters_apply_before_limit_and_date_to_is_inclusive(engine, index):
    index.seed()
    index.seed("bread", "Bread", topic="food", yoinked_at="2026-10-22T00:00:00")
    ready(engine)
    assert engine.embedding_search("rust", limit=1, filters={"topic": "food"})[0].source_id == "bread"
    assert engine.embedding_search("rust", filters={"date_to": "2026-10-21"})[0].source_id == "mars"
    for field in ("channel", "topic", "hook_type", "platform", "source_type", "author"):
        assert engine.embedding_search("rust", filters={field: "no match"}) == []
    assert engine.embedding_search("rust", filters={"date_from": "2026-10-23"}) == []
    with pytest.raises(ValueError):
        engine.embedding_search("rust", filters={"unsafe SQL": "x"})


def test_edit_during_inference_cannot_publish_or_return(engine, index):
    index.seed()
    ready(engine)
    original = engine._model.embed

    def edit_during_query(texts, **kwargs):
        result = original(texts, **kwargs)
        index.seed(content="Edit made while the query is running")
        return result

    engine._model.embed = edit_during_query
    assert engine.embedding_search("rust") == []
    engine._model.embed = original
    first = True

    def delete_during_build(texts, **kwargs):
        nonlocal first
        result = original(texts, **kwargs)
        if first:
            index.seed(deleted_at="2026-10-21")
            first = False
        return result

    engine._model.embed = delete_during_build
    ready(engine)
    assert engine.store.fingerprints() == {}


def test_status_download_error_recovery_pause_rebuild_remove(tmp_path, index, tiny_files, monkeypatch):
    engine = ls.LocalSearch(tmp_path, index, model_factory=FakeModel)
    assert engine.status()["state"] == "not_installed"
    with pytest.raises(ls.TermsRequired):
        engine.download()
    assert engine.status()["state"] == "terms_needed"
    engine.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    seen = []
    original = engine._set

    def observe(phase, **values):
        seen.append(phase)
        original(phase, **values)

    monkeypatch.setattr(engine, "_set", observe)
    monkeypatch.setattr(ls, "urlopen", lambda *a, **kw: io.BytesIO(b"bad"))
    engine.download()
    assert engine.wait(5)
    assert engine.status()["state"] == "error"
    assert "SHA-256" in engine.status()["message"]
    monkeypatch.setattr(ls, "urlopen", lambda *a, **kw: io.BytesIO(tiny_files))
    index.seed()
    engine.download()
    assert engine.wait(5)
    assert {"downloading", "verifying", "indexing", "ready", "error"} <= set(seen)
    assert engine.status()["done"] == engine.status()["total"] == 1
    assert engine.status()["disk_bytes"] > len(tiny_files)
    assert engine.pause(timeout=5)
    index.seed(content="Mars edit")
    engine.update_source("mars")
    assert engine.status()["paused"]
    assert engine._worker is None
    ready(engine)
    engine.rebuild()
    assert engine.wait(5)
    main_bytes = index._path.read_bytes()
    unrelated = tmp_path / "models" / "whisper"
    unrelated.mkdir()
    (unrelated / "keep").write_text("keep")
    engine.remove()
    engine.remove()
    assert engine._model is None
    assert engine.status()["state"] == "not_installed"
    assert engine.status()["disk_bytes"] == 0
    assert not engine.manager.terms_path.exists()
    assert not engine.store.path.exists()
    assert (unrelated / "keep").exists()
    assert index._path.read_bytes() == main_bytes


def test_pause_during_batch_and_queued_capture(engine, index):
    entered, release = threading.Event(), threading.Event()
    index.seed()

    class WaitingModel(FakeModel):
        def embed(self, texts, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().embed(texts, **kwargs)

    engine.model_factory = WaitingModel
    engine.start()
    try:
        assert entered.wait(5)
        assert not engine.pause(timeout=0.01)
        index.seed("new", "New Mars source")
        engine.update_source("new")
    finally:
        release.set()
    assert engine.wait(5)
    assert engine.store.fingerprints() == {}
    ready(engine)
    assert set(engine.store.fingerprints()) == {"mars", "new"}


def test_profile_paths_and_wrong_root_refusal(tmp_path, tiny_files):
    from uoink_install_isolation import IsolationBinding

    a = IsolationBinding(tmp_path / "profile-a", 15180)
    b = IsolationBinding(tmp_path / "profile-b", 15181)
    first, second = ls.ModelManager(a.profile), ls.ModelManager(b.profile)
    install(first, tiny_files)
    assert first.directory != second.directory
    assert first.terms_path != second.terms_path
    assert second.acceptance() is None
    assert not second.directory.exists()
    a.profile.mkdir(exist_ok=True)
    idx = TinyIndex(a.profile)
    try:
        with pytest.raises(ValueError):
            ls.LocalSearch(b.profile, idx)
    finally:
        idx.db.close()


def test_rrf_math_depth_duplicates_and_stable_ties():
    ranked = ls.rrf_merge(["a", "b", "cut"], ["b", "c", "cut"], depth=2)
    assert ranked == [("b", 1 / 62 + 1 / 61), ("a", 1 / 61), ("c", 1 / 62)]
    assert ls.rrf_merge(["z"], ["a"]) == [("z", 1 / 61), ("a", 1 / 61)]
    assert ls.rrf_merge(["z", "a"], ["a", "z"])[0][0] == "z"
    assert ls.rrf_merge(["a", "a", "b"], [], depth=2) == [("a", 1 / 61)]
    assert ls.rrf_merge([{"video_id": "a"}], [ls.SearchHit("a", "p", {}, None, 0.2)]) == [("a", 2 / 61)]
    assert ls.rrf_merge(range(200), [], depth=100)[-1] == (99, 1 / 160)
    assert ls.rrf_merge(["a"], ["b"], depth=0) == []
    with pytest.raises(ValueError):
        ls.rrf_merge([], [], k=-1)


def test_main_index_cannot_be_used_as_vector_store(tmp_path, index):
    index._path = tmp_path / "search-vectors.db"
    with pytest.raises(ValueError, match="separate"):
        ls.LocalSearch(tmp_path, index)


def test_corrupt_cache_has_error_status_and_rebuild_recovers(engine, index):
    index.seed()
    ready(engine)
    engine.store.path.write_bytes(b"not a sqlite database")
    with pytest.raises(ls.SearchUnavailable):
        engine.embedding_search("rust")
    assert engine.status()["state"] == "error"
    engine.rebuild()
    assert engine.wait(5)
    assert engine.status()["state"] == "ready"
    assert engine.embedding_search("rust")[0].source_id == "mars"


def test_bad_model_bytes_never_reach_session_factory(tmp_path, index, tiny_files):
    manager = ls.ModelManager(tmp_path)
    install(manager, tiny_files)
    (manager.directory / ls.MODEL_FILES[0][0]).write_bytes(b"tampered")
    search = ls.LocalSearch(tmp_path, index, model_factory=lambda _: pytest.fail("Loaded bad model"))
    search.start()
    assert search.wait(5)
    assert search.status()["state"] == "error"
    assert "SHA-256" in search.status()["message"]


def test_runtime_failure_does_not_echo_document_or_local_path(engine, index):
    index.seed()
    ready(engine)

    def fail(*a, **kw):
        raise RuntimeError("private document contents and local path")

    engine._model.embed = fail
    with pytest.raises(ls.SearchUnavailable):
        engine.embedding_search("rust")
    assert engine.status()["state"] == "error"
    assert "private" not in engine.status()["message"]


def test_import_starts_no_thread_and_loads_no_runtime(tmp_path):
    code = """
import sys, threading
def forbidden(*args, **kwargs):
    raise AssertionError('Thread started at import')
threading.Thread.start = forbidden
import uoink_core.local_search
assert not {'numpy', 'onnxruntime', 'tokenizers'} & sys.modules.keys()
assert len(threading.enumerate()) == 1
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], env=os.environ.copy(),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_onnx_session_cpu_prefixes_normalization_and_thread_bound(tmp_path, tiny_files, monkeypatch):
    np = pytest.importorskip("numpy")
    manager = ls.ModelManager(tmp_path)
    install(manager, tiny_files)
    calls, options = [], []

    class Tokenizer:
        @staticmethod
        def from_file(path):
            return Tokenizer()

        def enable_truncation(self, **kwargs):
            assert kwargs == {"max_length": 2048}

        def enable_padding(self, **kwargs):
            assert kwargs == {"pad_id": 0, "pad_token": "<pad>"}

        def encode(self, text):
            calls.append(text)
            return SimpleNamespace(ids=[1] * len(text.split()), attention_mask=[1] * len(text.split()))

    class Options:
        def add_session_config_entry(self, *args):
            options.append(args)

    class Session:
        def __init__(self, path, sess_options, providers):
            assert providers == ["CPUExecutionProvider"]
            assert sess_options.intra_op_num_threads == 2
            assert sess_options.inter_op_num_threads == 1
            assert sess_options.execution_mode == "sequential"

        def run(self, names, inputs):
            assert names == ["sentence_embedding"]
            assert inputs["input_ids"].shape[0] <= ls.BATCH_SIZE
            return [np.full((inputs["input_ids"].shape[0], ls.DIMENSIONS), 2.0)]

    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=Tokenizer))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=Options, InferenceSession=Session,
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential")))
    model = ls.EmbeddingGemma(manager, threads=999, batch_size=999)
    result = model.embed([ls.QUERY_PREFIX + "rust", "title: none | text: Mars"] * 7)
    assert result.shape == (14, ls.DIMENSIONS)
    assert np.allclose(np.linalg.norm(result, axis=1), 1)
    assert result.dtype == np.float32
    assert ("session.intra_op.allow_spinning", "0") in options
    assert calls[0] == "task: search result | query: rust"


def test_adapter_reads_actual_current_schema(tmp_path):
    from index import Index

    with Index.open(tmp_path / "schema-test.db") as idx:
        with idx.write_transaction() as db:
            db.execute("INSERT INTO yoinks(video_id,title,slug,yoinked_at,corpus_path,sidecar_path) "
                       "VALUES ('mars','Mars','mars','2026-10-21T12:00:00','unused.md','unused.json')")
            db.execute("INSERT INTO yoinks_fts(video_id,content) VALUES ('mars','Mars surface')")
            db.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES ('mars',0,1,2,'Mars surface')")
        source, = ls.IndexSources(idx).snapshot()
        assert source.source_id == "mars"
        assert source.passages[0].span["kind"] == "clip"
        assert source.passages[0].timestamp_seconds == 1
