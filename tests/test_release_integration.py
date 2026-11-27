"""Offline regression checks for the merged release."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import agent_config_writer as config
import library_media
import podcasts
import server
import timed_cues
import transcript_review
import yt_extract
from tests.test_caption_repair import ROLLING, VID, library as caption_library
from tests.test_library_path_policy import directories
from tests.test_podcast_job_transports import episode
from tests.test_transcript_review import add_talk, library as review_library

FIXTURES = Path(__file__).parent / "fixtures"


def test_caption_repair_after_library_move(caption_library, monkeypatch, tmp_path):
    _, save = caption_library
    side, corpus, plain = save(legacy=True)
    before = {p: p.read_bytes() for p in (side, corpus, plain)}
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "moved-library")
    for preview in (True, False):
        with pytest.raises((OSError, ValueError)):
            server.repair_rolling_captions(VID, dry_run=preview)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list(side.parent.glob("*.bak"))


def test_repair_uses_selected_linked_library(caption_library, directories, monkeypatch):
    _, save = caption_library
    _, physical, alias = directories
    selected = alias("selected")
    monkeypatch.setattr(server, "DESKTOP_ROOT", selected)
    side, _, _ = save(legacy=True)
    result = server.repair_rolling_captions(VID, dry_run=False)
    assert result["removed_words"] == 16
    assert (physical / side.relative_to(selected)).read_bytes() == side.read_bytes()
    assert Path(result["original_sidecar"]).is_file()


@pytest.mark.parametrize("edited", [False, True])
def test_frozen_3180_caption_section(caption_library, edited):
    _, save = caption_library
    rows = [(s + 60, e + 60, text) for s, e, text in ROLLING]
    side, corpus, _ = save(entries=rows, legacy=True)
    data = json.loads(side.read_bytes())
    data.update(source_chapters=[], duration_seconds=90)
    for row in data["transcript"]:
        link = f"https://youtube.com/watch?v={VID}&t={row['start']}s"
        row.update(source_url=data["url"], source_deep_link=link, youtube_deep_link=link)
    side.write_text(json.dumps(data), "utf-8")
    corpus.write_bytes((FIXTURES / "3180-captions.md").read_bytes())
    server._publish_capture_media(caption_library[0], side.parent, data, corpus, side)
    if edited:
        before = corpus.read_bytes().replace(b"sky above", b"sky over", 1)
        corpus.write_bytes(before)
        with pytest.raises(ValueError, match="edits were kept"):
            server.repair_rolling_captions(VID, dry_run=False)
        assert corpus.read_bytes() == before and not list(side.parent.glob("*.bak"))
        return
    assert server.repair_rolling_captions(VID, dry_run=False)["removed_words"] == 16
    assert "&t=58s" in corpus.read_text("utf-8")


@pytest.mark.parametrize("edited", [False, True])
def test_frozen_3180_tidy_section(review_library, edited):
    path = add_talk(review_library, [(60, 63, "The tide is rising."), (65, 67, "[Music]")])
    side = json.loads(path.read_bytes())
    side.update(source_chapters=[], duration_seconds=90)
    path.write_text(json.dumps(side), "utf-8")
    corpus = path.with_suffix(".md")
    corpus.write_bytes((FIXTURES / "3180-tidy.md").read_bytes())
    if edited:
        before = corpus.read_bytes().replace(b"[Music]", b"[Music] My note")
        corpus.write_bytes(before)
        result = transcript_review.tidy(server, apply=True)
        assert not result["ok"] and "edits" in str(result["errors"])
        assert corpus.read_bytes() == before
        return
    result = transcript_review.tidy(server, apply=True)
    assert result["ok"], result
    assert result["changed"] == 1
    after = corpus.read_text("utf-8")
    assert "&t=58s" in after and "[Music]" not in after


def test_unfinished_discovery_refuses_redirected_metadata(directories, monkeypatch):
    root, other, alias = directories
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    folder = alias("sample")
    (other / "metadata.json").write_text(json.dumps({"webpage_url": "https://example.test/a"}))
    monkeypatch.setattr(server, "_transcript_backfill_identity_busy", lambda url: False)
    assert server._transcript_backfill_half_item(folder, {"metadata.json"}) is None


def test_transcript_cache_stays_in_app_storage(directories, monkeypatch):
    root, other, alias = directories
    monkeypatch.setattr(server, "DATA_ROOT", root)
    alias(server.TRANSCRIPT_CACHE_DIRNAME)
    record = {"version": server._TRANSCRIPT_CACHE_VERSION, "video_id": VID, "segments": [[1, 2, "Saved"]]}
    cache = other / f"{VID}__default.json"
    before = json.dumps(record).encode()
    cache.write_bytes(before)
    assert server._read_transcript_cache(VID, None) is None
    server._write_transcript_cache(dict(record, segments=[(1, 2, "New")]), None)
    assert cache.read_bytes() == before


def test_cues_refuse_redirected_item(directories, monkeypatch):
    root, other, alias = directories
    folder = alias("sample")
    (other / "sample.json").write_text(json.dumps({"transcript": [{"start": 1, "end": 2, "text": "Other"}]}))
    idx = Mock()
    idx.get_yoink.return_value = {"video_id": "sample", "sidecar_path": str(folder / "sample.json")}
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    assert timed_cues.get_item(idx, "sample")["cues"] == []


def test_config_planning_refuses_redirected_settings(directories, monkeypatch):
    root, other, alias = directories
    monkeypatch.setattr(config, "roaming_dir", lambda: root)
    folder = alias("Code")
    with pytest.raises(config.ConfigError):
        config.plan_edit(folder / "User" / "mcp.json", "VS Code", "servers", {})


def test_config_rechecks_directory_before_staging(directories, monkeypatch):
    root, other, alias = directories
    monkeypatch.setattr(config, "roaming_dir", lambda: root)
    plan = config.plan_edit(root / "Code" / "User" / "mcp.json", "VS Code", "servers", {})
    alias("Code")
    with pytest.raises(config.ConfigError):
        config.apply_edits([plan], "VS Code")
    assert not list(other.iterdir())


@pytest.mark.parametrize("linked", ["Podcasts", "Podcasts/show"])
def test_podcast_feed_path_refused_before_download_staging(directories, linked):
    import index

    root, other, alias = directories
    (root / linked).parent.mkdir(parents=True, exist_ok=True)
    alias(linked)
    with index.Index.open(root / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.test/rss", title="Show")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode",
                                                    "audio_url": "https://audio.test/one.mp3"}])
        row, = podcasts.list_episodes(idx)
        policy = Mock(side_effect=ValueError("fixture offline"))
        result = podcasts.download_episode_audio(idx, row["id"], data_root=root, resolve_url=policy)
        assert not result["ok"]
        policy.assert_not_called()
        assert not list(other.iterdir())


def test_failed_audio_publication_leaves_episode_retryable(tmp_path, monkeypatch):
    import index
    import subprocess
    import uoink_processes

    def download(command, **kwargs):
        target = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp3"))
        target.write_bytes(b"recording")
        return subprocess.CompletedProcess(command, 0)

    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.test/rss", title="Show")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode",
                                                    "audio_url": "https://audio.test/one.mp3"}])
        row, = podcasts.list_episodes(idx)
        monkeypatch.setattr(subprocess, "run", download)
        monkeypatch.setattr(uoink_processes, "run_owned", download)
        monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
        publish = Mock(side_effect=PermissionError("fixture storage failure"))
        monkeypatch.setattr(podcasts, "atomic_output", publish, raising=False)
        result = podcasts.download_episode_audio(idx, row["id"], data_root=tmp_path, ytdlp_cmd=["fixture"],
                                                 resolve_url=lambda url, **kw: url)
        assert not result["ok"]
        saved = podcasts.get_episode(idx, row["id"])
        assert saved["status"] == podcasts.EPISODE_STATUS_NEW and saved["audio_download_error"]
        assert not saved["audio_local_path"] and not list((tmp_path / "Podcasts").rglob("*.mp3"))


def test_podcast_admission_refuses_stale_recording_path(tmp_path, monkeypatch):
    from tests.test_podcast_background_jobs import _seed_downloaded_episodes
    import index

    with index.Index.open(tmp_path / "index.db") as idx:
        episode_id, = _seed_downloaded_episodes(idx, tmp_path, 1)
        other = tmp_path / "outside.mp3"
        other.write_bytes(b"fixture")
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=? WHERE id=?", (str(other), episode_id))
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        capability = Mock(side_effect=AssertionError("unexpected media access"))
        monkeypatch.setattr(server._platform, "media_capability", capability)
        result, status = server._admit_podcast_transcription(episode_id)
        assert status == 400 and not result["ok"]
        capability.assert_not_called()


def test_legacy_transcript_requires_one_episode_owner(tmp_path):
    import index

    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.test/rss", title="Show")
        podcasts.upsert_episodes(idx, feed["id"], [
            {"guid": key, "title": "Episode", "audio_url": f"https://audio.test/{key}"} for key in ("one", "two")])
        transcript = tmp_path / "Podcasts" / "show" / "episode.transcript.json"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "Saved."}]}))
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET transcript_local_path=?, transcript_status='done'", (str(transcript),))
        first, second = podcasts.list_episodes(idx)
        with pytest.raises(ValueError, match="also claims"):
            podcasts.episode_to_corpus(idx, first["id"], data_root=tmp_path)
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET transcript_local_path=NULL WHERE id=?", (second["id"],))
        assert podcasts.episode_to_corpus(idx, first["id"], data_root=tmp_path)["ok"]


def test_restored_podcast_job_rechecks_its_recording(episode, monkeypatch, tmp_path):
    result, status = server._queue_podcast_transcription(episode, defer_worker=True)
    assert status == 202
    idx = server._get_index()
    saved = podcasts.saved_transcription_job(idx, result["job_id"])
    other = tmp_path / "restored.mp3"
    other.write_bytes(b"fixture")
    saved["audio_path"] = str(other)
    with idx.write_transaction() as db:
        db.execute("UPDATE podcast_episodes SET audio_local_path=? WHERE id=?", (str(other), episode))
    transcribe = Mock(return_value={"model": "base", "segments": []})
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", transcribe)
    server._start_waiting_podcast_job(saved)
    server._podcast_transcription_queue.join()
    assert server._jobs[result["job_id"]]["state"] == "failed"
    transcribe.assert_not_called()
    assert not other.with_suffix(".transcript.json").exists()


def test_episode_identity_checked_before_corpus_read(tmp_path, monkeypatch):
    from tests.test_podcast_corpus_bridge import _seed_episode
    import uoink_mcp_tools as mcp

    idx, episode_id, _, _ = _seed_episode(tmp_path)
    try:
        published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
        monkeypatch.setattr(mcp, "_backend", server)
        monkeypatch.setattr(server, "_get_existing_index", lambda **kwargs: idx)
        args = {"video_id": published["video_id"], "start": 0, "end": 4.5}
        assert mcp.get_uoink_corpus({"slug": published["slug"]})["ok"]
        saved = idx.get_yoink(published["video_id"])
        assert mcp._byo_source_text(server, saved)
        assert library_media.export_cited_range_tool(args, server)["ok"]
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET guid=? WHERE id=?", ("different", episode_id))
        assert not mcp.get_uoink_corpus({"slug": published["slug"]})["ok"]
        assert mcp._byo_source_text(server, saved) == ""
        assert not library_media.export_cited_range_tool(args, server)["ok"]
        assert server.Handler._yoink_markdown_path(None, published["video_id"])[0] is None
    finally:
        idx.close()


@pytest.mark.parametrize("entry", ["track", "fallback", "standalone", "cached"])
def test_url_admission_precedes_dispatch(entry, tmp_path, monkeypatch):
    url = "https://media.example.test/movie"
    denied = Mock(side_effect=ValueError("fixture refused"))
    dispatch = Mock(side_effect=AssertionError("unexpected dispatch"))
    monkeypatch.setattr(server.source_subscriptions, "check_public_http_url", denied)
    monkeypatch.setattr(server, "_run_subprocess", dispatch)
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    with pytest.raises(ValueError, match="fixture refused"):
        if entry == "standalone":
            monkeypatch.setattr(sys, "argv", ["yt_extract.py", url, "--out", str(tmp_path)])
            monkeypatch.setattr(yt_extract.subprocess, "check_output", dispatch)
            yt_extract.main()
        elif entry == "fallback":
            server._fetch_video_subtitles(url, tmp_path, long_video_mode="full")
        elif entry == "cached":
            monkeypatch.setattr(server, "_route_topic", dispatch)
            server._run_extraction(url, 30, tmp_path, metadata={"title": "Cached"}, finish_on_disk=True)
        else:
            server._download_caption_track(url, {"key": "en", "kind": "captions"}, tmp_path, 5)
    denied.assert_called_with(url)
    dispatch.assert_not_called()
