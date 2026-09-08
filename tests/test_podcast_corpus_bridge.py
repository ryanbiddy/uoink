"""Podcast transcript publication, source citations, and transport contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import corpus_contract
import corpus_provider
import index as index_mod
import podcasts
import server
import uoink_mcp_tools


def _seed_episode(tmp_path: Path, *, guid: str = "opaque-guid-42",
                  page_url: str | None = "https://show.example/episodes/42",
                  speakers: bool = True):
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(idx, "https://show.example/feed.xml")
    podcasts.record_feed_meta(
        idx, feed["id"], title="The Grounded Show", description="",
        homepage="https://show.example", etag=None, last_modified=None,
        ok=True)
    podcasts.upsert_episodes(idx, feed["id"], [{
        "guid": guid,
        "title": "Episode Forty Two",
        "audio_url": "https://cdn.example/42.mp3",
        "episode_page_url": page_url,
        "duration_seconds": 90,
        "published_at": "2026-08-01T12:00:00Z",
        "description": "A grounded episode.",
    }])
    episode = podcasts.list_episodes(idx, feed_id=feed["id"])[0]
    transcript_path = tmp_path / "episode.transcript.json"
    segments = [
        {"start": 0.0, "end": 4.5, "text": "A grounded opening."},
        {"start": 64.2, "end": 70.0, "text": "The durable detail."},
    ]
    if speakers:
        segments[0]["speaker"] = "HOST"
        segments[1]["speaker"] = "GUEST"
    transcript_path.write_text(json.dumps({
        "model": "base", "language": "en", "diarization_ran": speakers,
        "segments": segments,
    }), encoding="utf-8")
    with idx.write_transaction() as conn:
        conn.execute(
            "UPDATE podcast_episodes SET transcript_local_path=?, "
            "transcript_status='done', transcript_model_used='base', "
            "diarization_ran=? WHERE id=?",
            (str(transcript_path), int(speakers), episode["id"]))
    return idx, episode["id"], feed["feed_url"], guid


def test_migration_preserves_legacy_youtube_citations_and_relaxes_link(
        tmp_path, monkeypatch):
    real_migrations = index_mod._MIGRATIONS_DIR
    old_migrations = tmp_path / "migrations-through-21"
    old_migrations.mkdir()
    for source in real_migrations.glob("*.sql"):
        if int(source.name.split("_", 1)[0]) <= 21:
            shutil.copy2(source, old_migrations / source.name)
    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", old_migrations)
    db_path = tmp_path / "legacy.db"
    idx = index_mod.Index.open(db_path)
    idx.upsert_yoink({
        "video_id": "legacy-video", "slug": "legacy-video",
        "yoinked_at": "2026-01-01", "corpus_path": "legacy.md",
        "sidecar_path": "legacy.json",
    })
    legacy_link = "https://youtube.com/watch?v=legacy-video&t=12s"
    idx._conn.execute(
        "INSERT INTO citations (video_id, kind, seq, youtube_deep_link) "
        "VALUES (?, 'transcript_chunk', 0, ?)",
        ("legacy-video", legacy_link))
    idx._conn.commit()
    idx.close()

    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", real_migrations)
    idx = index_mod.Index.open(db_path)
    citation = idx.get_citations("legacy-video")[0]
    assert citation["youtube_deep_link"] == legacy_link
    assert citation["source_url"] == legacy_link
    assert citation["source_deep_link"] == legacy_link
    idx.insert_citations("legacy-video", [{
        "kind": "transcript_chunk", "seq": 1,
        "source_url": "https://show.example/episode",
        "source_deep_link": "https://show.example/episode#t=30",
    }])
    assert idx.get_citations("legacy-video")[1]["youtube_deep_link"] is None
    assert idx._conn.execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0] == index_mod.latest_schema_version()
    idx.close()


def test_rss_and_atom_retain_public_episode_page_urls():
    rss = podcasts.parse_feed_body("""
        <rss><channel><title>RSS Show</title>
          <item><guid>opaque-rss-guid</guid><title>RSS episode</title>
            <link>https://rss.example/episode</link>
            <enclosure url="https://cdn.example/rss.mp3" />
          </item>
        </channel></rss>
    """)
    atom = podcasts.parse_feed_body("""
        <feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Show</title>
          <entry><id>tag:example,2026:1</id><title>Atom episode</title>
            <link rel="enclosure" href="https://cdn.example/atom.mp3" />
            <link rel="alternate" href="https://atom.example/episode" />
          </entry>
        </feed>
    """)
    assert rss["episodes"][0]["episode_page_url"] == (
        "https://rss.example/episode")
    assert atom["episodes"][0]["episode_page_url"] == (
        "https://atom.example/episode")


def test_repeat_poll_repairs_page_url_on_an_existing_episode(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed_id = podcasts.add_feed(idx, "https://repair.example/feed.xml")["id"]
    episode = {
        "guid": "existing", "title": "Existing",
        "audio_url": "https://cdn.example/existing.mp3",
    }
    assert podcasts.upsert_episodes(idx, feed_id, [episode]) == (1, 0)
    episode["episode_page_url"] = "https://repair.example/episode"
    assert podcasts.upsert_episodes(idx, feed_id, [episode]) == (0, 1)
    assert podcasts.list_episodes(idx, feed_id=feed_id)[0][
        "episode_page_url"] == "https://repair.example/episode"
    idx.close()


@pytest.mark.parametrize("speakers", [True, False])
def test_episode_bridge_is_stable_searchable_and_source_aware(tmp_path, speakers):
    idx, episode_id, feed_url, guid = _seed_episode(
        tmp_path, speakers=speakers)
    first = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    second = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)

    expected_suffix = hashlib.sha1(
        f"{feed_url}\n{guid}".encode("utf-8")).hexdigest()[:11]
    assert first["video_id"] == second["video_id"] == (
        f"episode_{expected_suffix}")
    assert first["slug"] == second["slug"]
    assert idx.all_video_ids() == {first["video_id"]}
    assert idx._conn.execute(
        "SELECT COUNT(*) FROM yoinks_fts WHERE video_id=?",
        (first["video_id"],)).fetchone()[0] == 1
    assert idx.search("durable detail", 10)[0]["video_id"] == first["video_id"]

    row = idx.get_yoink(first["video_id"])
    assert (row["platform"], row["source_type"]) == ("podcast", "episode")
    facets = idx.corpus_facets()
    assert {x["value"] for x in facets["platform"]} == {"podcast"}
    assert {x["value"] for x in facets["source_type"]} == {"episode"}
    provider = corpus_provider.UoinkCorpusProvider(idx, tmp_path)
    contract_search = provider.search(corpus_contract.SearchRequest(
        q="grounded", platform="podcast", source_type="episode"))
    assert contract_search["page"]["total"] == 1
    assert contract_search["items"][0]["id"] == first["video_id"]
    assert contract_search["items"][0]["source_url"] == (
        "https://show.example/episodes/42")
    contract_get = provider.get(first["video_id"])
    assert contract_get["item"]["platform"] == "podcast"
    contract_facets = provider.facets()["facets"]
    assert contract_facets["platform"] == [
        {"value": "podcast", "label": "Podcast", "count": 1}]
    assembled = provider.assemble(corpus_contract.AssemblyRequest(n_examples=5))
    assert assembled["assembled"][0]["video_id"] == first["video_id"]
    episode = podcasts.get_episode(idx, episode_id)
    assert episode["yoink_video_id"] == first["video_id"]

    corpus_path = Path(first["corpus_path"])
    sidecar = json.loads(Path(first["sidecar_path"]).read_text(encoding="utf-8"))
    markdown = corpus_path.read_text(encoding="utf-8")
    assert corpus_path.parent.name == first["slug"]
    assert sidecar["episode_title"] == "Episode Forty Two"
    assert sidecar["podcast_title"] == "The Grounded Show"
    assert sidecar["source_type"] == "episode"
    assert sidecar["platform"] == "podcast"
    assert sidecar["host"] is None  # the feed does not identify a person
    assert sidecar["speakers"] == (["HOST", "GUEST"] if speakers else [])
    assert "https://show.example/episodes/42#t=64" in markdown
    assert "youtube.com" not in markdown.lower()

    citations = idx.get_citations(first["video_id"])
    assert len(citations) == 2
    assert all(item["youtube_deep_link"] is None for item in citations)
    assert citations[1]["source_deep_link"].endswith("#t=64")
    assert not any("youtube.com" in json.dumps(item) for item in citations)
    idx.close()


def test_bridge_uses_public_feed_homepage_for_opaque_guid_without_episode_link(
        tmp_path):
    idx, episode_id, feed_url, _guid = _seed_episode(
        tmp_path, page_url=None)
    result = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    assert result["source_url"] == "https://show.example"
    assert result["source_url"] != feed_url
    assert idx.get_citations(result["video_id"])[0][
        "source_deep_link"] == "https://show.example#t=0"
    idx.close()


@pytest.mark.parametrize("payload,error", [
    ({"model": "base"}, "segments array"),
    ({"segments": ["bad"]}, "segment 0 must be an object"),
    ({"segments": [{"start": 1, "end": 0, "text": "bad"}]},
     "invalid timing or text"),
    ({"segments": []}, "segments array is empty"),
])
def test_bridge_rejects_malformed_transcript_shapes(tmp_path, payload, error):
    idx, episode_id, _feed_url, _guid = _seed_episode(tmp_path)
    path = Path(podcasts.get_episode(idx, episode_id)["transcript_local_path"])
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    assert idx.count_corpus() == 0
    idx.close()


def test_bridge_repairs_a_crash_between_index_and_episode_link(
        tmp_path, monkeypatch):
    idx, episode_id, _feed_url, _guid = _seed_episode(tmp_path)
    real_link = podcasts._link_episode_to_yoink
    monkeypatch.setattr(
        podcasts, "_link_episode_to_yoink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic link crash")))
    with pytest.raises(RuntimeError, match="synthetic link crash"):
        podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    assert idx.count_corpus() == 1
    assert podcasts.get_episode(idx, episode_id)["yoink_video_id"] is None

    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_diagnose_payload", lambda: {"ok": True})
    monkeypatch.setattr(
        server.migrate_install, "migration_status", lambda: {"ok": True})
    monkeypatch.setattr(server, "_mcp_stdio_selfcheck", lambda: {"ok": True})
    monkeypatch.setattr(
        server, "_path_integrity_status", lambda force=False: {"ok": True})
    doctor = server.doctor_payload()
    reconciliation = doctor["podcast_corpus"]
    assert reconciliation["ok"] is False
    assert (reconciliation["checked"], reconciliation["orphaned"]) == (1, 1)
    assert reconciliation["repairable"] == 1
    assert reconciliation["items"][0]["episode_id"] == episode_id

    monkeypatch.setattr(podcasts, "_link_episode_to_yoink", real_link)
    printed = []
    monkeypatch.setattr(server, "_print_json", printed.append)
    assert server.run_cli(["--reconcile-podcast-corpus"]) == 0
    repaired = printed[0]
    assert repaired["ok"] is True
    assert (repaired["repaired"], repaired["remaining"]) == (1, 0)
    assert idx.count_corpus() == 1
    assert podcasts.get_episode(idx, episode_id)["yoink_video_id"] == (
        repaired["items"][0]["video_id"])
    assert len(idx.get_citations(repaired["items"][0]["video_id"])) == 2
    idx.close()


def test_bridge_missing_episode_and_transcript_are_explicit(tmp_path):
    idx, episode_id, _feed_url, _guid = _seed_episode(tmp_path)
    with pytest.raises(LookupError, match="episode not found"):
        podcasts.episode_to_corpus(idx, 999999, data_root=tmp_path)
    Path(podcasts.get_episode(idx, episode_id)["transcript_local_path"]).unlink()
    with pytest.raises(FileNotFoundError, match="transcript file missing"):
        podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    idx.close()


def test_bridge_is_available_through_http_and_full_mcp(tmp_path, monkeypatch):
    idx, episode_id, _feed_url, _guid = _seed_episode(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    uoink_mcp_tools.bind_backend(server)

    class Probe:
        def _send_json(self, status, payload):
            self.status = status
            self.payload = payload

    probe = Probe()
    server.Handler._handle_podcasts_episode_to_corpus(
        probe, {"episode_id": episode_id})
    assert probe.status == 200
    assert probe.payload["video_id"].startswith("episode_")

    result = uoink_mcp_tools.call_tool(
        "episode_to_corpus", {"episode_id": episode_id})
    assert result["ok"] is True
    corpus = uoink_mcp_tools.get_uoink_corpus({"slug": result["slug"]})
    citation_map = uoink_mcp_tools.get_citation_map({"slug": result["slug"]})
    assert corpus["video_url"] is None
    assert corpus["source_url"] == "https://show.example/episodes/42"
    assert "youtube.com" not in json.dumps(corpus).lower()
    assert citation_map["transcript_citations"][1]["deep_link"] == (
        "https://show.example/episodes/42#t=64")
    assert "youtube.com" not in json.dumps(citation_map).lower()
    assert len(uoink_mcp_tools.TOOL_REGISTRY) == 81  # +6 Living Library tools (run J), +4 Phase 3 source tools (run AM)
    idx.close()
