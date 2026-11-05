"""Normal captures remain readable after their background corpus writers finish."""
import json
from pathlib import Path
import sqlite3
import re
import threading

import pytest

import index as index_mod
import library_cards
import library_resources
import uoink_cli
import library_media as media
import research
from tests.test_phase6_bc2 import _seed_index, _server_namespace, _youtube_sidecar
from tests.test_phase6_evaluation import _fixture, _function
from tests.test_research_evidence import evidence, make_run, rig


def capture_video(rig, *, platform="youtube", long=False):
    video_id = "talk0000001" if platform == "youtube" else "1820000000000000000"
    entries = [(0.0, 22.0, "Evals catch regressions before shipping.")]
    if long:
        entries += [(float(n * 25), float(n * 25 + 20), "Stored transcript about evals. " * 60)
                    for n in range(1, 10)]
    capture = _youtube_sidecar(rig, video_id, transcript=entries)
    scope = _server_namespace(rig.idx)
    if platform == "x":
        capture.url = "https://x.com/example/status/" + video_id
        capture.sidecar.update(url=capture.url, platform="x", source_type="short_video",
                               transcript_source="asr", source_chapters=[])
        capture.sidecar["transcript"] = scope["_transcript_entries_with_links"](capture.sidecar, entries)
    plan = scope["_capture_media_plan"](capture.sidecar, capture.folder)
    corpus = scope["_build_yoink_md"](
        metadata=capture.metadata, url=capture.url, entries=entries, shots=[], interval=30,
        channel_ctx={}, yoinked_at=capture.sidecar["yoinked_at"], topic="Tests",
        media_sections=plan["markdown"])
    capture.corpus_path.write_text(corpus, encoding="utf-8")
    capture.sidecar_path.write_text(json.dumps(capture.sidecar), encoding="utf-8")
    assert scope["_index_yoink"](capture.folder, capture.sidecar, capture.corpus_path, capture.sidecar_path)
    scope.update(re=re, _corpus_update_lock=threading.Lock())
    _function("server.py", "_replace_comments_section", scope)
    capture.replace_comments = lambda: scope["_replace_comments_section"](
        capture.corpus_path, "*Comments could not be retrieved.*")
    capture.video_id = video_id
    capture.candidate = {"key": "lib:" + video_id, "video_id": video_id, "in_library": True,
                         "kind": "library", "url": capture.url, "title": capture.sidecar["title"]}
    return capture


@pytest.mark.parametrize("platform", ["youtube", "x"])
@pytest.mark.parametrize("long", [False, True], ids=["comments-in-head", "comments-after-head"])
def test_research_evidence_after_normal_capture_comments(rig, platform, long):
    capture = capture_video(rig, platform=platform, long=long)
    run = make_run(rig, [capture.candidate])
    assert evidence(run)["ready_items"] == 1
    before = media._read_snapshot(rig.idx._conn, capture.video_id)
    capture.replace_comments()
    assert capture.corpus_path.read_bytes() != before.corpus_bytes
    head = capture.corpus_path.read_bytes()[:library_cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
    assert (head == before.head) is long
    result = evidence(run)
    assert result["ready_items"] == 1, result
    assert result["excerpts"]
    assert research.read_source(rig.idx, capture.video_id) is not None


@pytest.mark.parametrize("long", [False, True], ids=["source-revision", "corpus-revision"])
def test_media_snapshot_after_normal_capture_comments(rig, long):
    capture = capture_video(rig, long=long)
    capture.replace_comments()
    assert research.read_source(rig.idx, capture.video_id) is not None
    snap = media._read_snapshot(rig.idx._conn, capture.video_id)
    assert snap.cues and snap.materialized


@pytest.fixture
def published(rig):
    fixture = _fixture(rig, key="saved-media", publication_conn=rig.idx._conn)
    assert _seed_index(rig.idx, fixture)["ok"]
    return fixture


def media_row(rig, video_id):
    return dict(rig.idx._conn.execute("SELECT * FROM media_depth WHERE video_id=?", (video_id,)).fetchone())


def enrich(published):
    path = Path(published.item["corpus_path"])
    path.write_bytes(path.read_bytes() + b"\nBackground enrichment completed.\n")


def test_existing_stale_library_heals_durably_and_preserves_attribution(rig, published):
    video_id = published.item["video_id"]
    before = media_row(rig, video_id)
    enrich(published)
    corpus = Path(published.item["corpus_path"]).read_bytes()
    with index_mod.Index.open(rig.root / "index.db") as reopened:
        source = research.read_source(reopened, video_id)
        assert source is not None
        snap = media._read_snapshot(reopened._conn, video_id)
        assert snap.block["chapters"] == published.block["chapters"]
        assert snap.block["runs"] == published.block["runs"]
        assert snap.block["cues"] == published.block["cues"]
        assert snap.block["cue_revision"] == before["cue_revision"]
        assert snap.source_revision != before["source_revision"]
        assert snap.block["provenance"]["corpus_revision"] == media._sha256(corpus)
        assert snap.block["media_revision"] != before["media_revision"]
        assert reopened.refresh_media_bindings(video_id) is False
    stored = json.loads(Path(published.item["sidecar_path"]).read_bytes())
    assert stored["media_depth"] == snap.block
    assert Path(published.item["corpus_path"]).read_bytes() == corpus
    assert rig.idx.rebuild_media_item(video_id, sidecar=stored)["ok"]
    ledger = json.loads(media._ledger_path(Path(published.item["corpus_path"]).parent).read_bytes())
    assert ledger["media_revision"] == snap.block["media_revision"]
    assert ledger["history"] == [before["media_revision"]]


@pytest.mark.parametrize("by_slug", [False, True])
def test_uoink_get_repairs_media_and_returns_usable_revision(rig, published, by_slug):
    # Other items keep SQLite from reusing the repaired item's old clip IDs.
    other = _fixture(rig, key="other-media", publication_conn=rig.idx._conn)
    assert _seed_index(rig.idx, other)["ok"]
    video_id = published.item["video_id"]
    enrich(published)
    args = ["get", published.item["slug"] if by_slug else video_id]
    if by_slug:
        args.append("--slug")
    name, arguments = uoink_cli.friendly_call(uoink_cli.parser().parse_args(args), None)
    assert name == "get_library_item"
    result = library_resources.LibraryReader(rig.idx, data_root=rig.root).get_item(**arguments)
    assert result["ok"], result
    # Inspect the durable rows before research gets a chance to repair them.
    snap = media._read_snapshot(rig.idx._conn, video_id)
    assert snap.source_revision == result["card"]["source_revision"]
    export = media.export_cited_range(rig.idx._conn, {
        "video_id": video_id, "start": 60, "end": 125,
        "source_revision": result["card"]["source_revision"]})
    assert export["ok"], export
    for pin in ("source_revision", "media_revision"):
        refused = media.export_cited_range(rig.idx._conn, {
            "video_id": video_id, "start": 60, "end": 125, pin: published.block[pin]})
        assert refused["error"]["code"] == "revision_unavailable"
    assert research.read_source(rig.idx, video_id) is not None


def test_topic_classification_is_rebound_but_availability_does_not_change_revision(rig, published):
    video_id = published.item["video_id"]
    rig.idx.record_availability(video_id, status="available", last_checked_at="2026-11-05T12:00:00Z")
    assert rig.idx.refresh_media_bindings(video_id) is False
    assert media_row(rig, video_id)["media_revision"] == published.block["media_revision"]
    rig.idx.set_facets(video_id, topic="Databases")
    with pytest.raises(media.MediaError) as error:
        media._read_snapshot(rig.idx._conn, video_id)
    assert error.value.details["reason"] == "source_revision_changed"
    assert research.read_source(rig.idx, video_id) is not None
    assert media._read_snapshot(rig.idx._conn, video_id).source_revision != published.block["source_revision"]


def concurrent_change(rig, published, mutation):
    video_id = published.item["video_id"]
    if mutation == "corpus":
        enrich(published)
        return
    if mutation == "artifact":
        digest = published.block["provenance"]["transcript_source"]["artifact_sha256"]
        media._artifact_path(Path(published.item["corpus_path"]).parent, digest).write_bytes(b"{}")
        return
    if mutation == "sidecar":
        path = Path(published.item["sidecar_path"])
        data = json.loads(path.read_bytes())
        data["transcript"][0]["text"] = "Newer transcript must survive."
        path.write_text(json.dumps(data), encoding="utf-8")
        return
    statements = {
        "topic": "UPDATE yoinks SET topic='Changed during read' WHERE video_id=?",
        "metadata": "UPDATE yoinks SET metadata_json='{}' WHERE video_id=?",
        "cues": "UPDATE citations SET text='Changed during read' WHERE video_id=? AND kind='transcript_chunk'",
        "clips": "UPDATE clips SET text='Changed during read' WHERE video_id=?",
        "media": "UPDATE media_depth SET media_revision='eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee' WHERE video_id=?",
        "deleted": "UPDATE yoinks SET deleted_at='2026-11-05' WHERE video_id=?",
    }
    with sqlite3.connect(rig.root / "index.db") as writer:
        writer.execute(statements[mutation], (video_id,))


@pytest.mark.parametrize("stale_at_entry", [False, True])
@pytest.mark.parametrize("mutation", ["corpus", "topic", "metadata", "cues", "clips", "media", "deleted"])
def test_research_rejects_concurrent_change_after_snapshot(rig, published, monkeypatch, mutation, stale_at_entry):
    if stale_at_entry:
        enrich(published)
    original = media._read_snapshot
    changed = []

    def read_then_change(conn, video_id, **kwargs):
        snap = original(conn, video_id, **kwargs)
        if not kwargs.get("allow_stale_bindings"):
            concurrent_change(rig, published, mutation)
            changed.append(True)
        return snap

    monkeypatch.setattr(media, "_read_snapshot", read_then_change)
    assert research.read_source(rig.idx, published.item["video_id"]) is None
    assert changed == [True]


@pytest.mark.parametrize("mutation", ["corpus", "topic", "cues", "artifact", "sidecar"])
def test_repair_refuses_concurrent_dependency_change(rig, published, monkeypatch, mutation):
    video_id = published.item["video_id"]
    enrich(published)
    before = media_row(rig, video_id)
    original = media.begin_publication

    def mint_then_change(*args, **kwargs):
        ticket = original(*args, **kwargs)
        concurrent_change(rig, published, mutation)
        return ticket

    monkeypatch.setattr(media, "begin_publication", mint_then_change)
    assert research.read_source(rig.idx, video_id) is None
    assert media_row(rig, video_id) == before
    assert not rig.idx._conn.in_transaction
    stored = json.loads(Path(published.item["sidecar_path"]).read_bytes())
    assert stored["media_depth"] == published.block
    if mutation == "sidecar":
        assert stored["transcript"][0]["text"] == "Newer transcript must survive."


@pytest.mark.parametrize("mutation", ["artifact", "sidecar", "cues"])
def test_stale_binding_does_not_mask_invalid_evidence(rig, published, mutation):
    video_id = published.item["video_id"]
    enrich(published)
    concurrent_change(rig, published, mutation)
    before = media_row(rig, video_id)
    assert research.read_source(rig.idx, video_id) is None
    assert media_row(rig, video_id) == before


def test_repair_contention_leaves_stale_snapshot_recoverable(rig, published):
    video_id = published.item["video_id"]
    enrich(published)
    before = media_row(rig, video_id)
    rig.idx._conn.execute("PRAGMA busy_timeout=1")
    with sqlite3.connect(rig.root / "index.db") as writer:
        writer.execute("BEGIN IMMEDIATE")
        assert research.read_source(rig.idx, video_id) is None
        assert not rig.idx._conn.in_transaction
        assert media_row(rig, video_id) == before
    assert research.read_source(rig.idx, video_id) is not None
