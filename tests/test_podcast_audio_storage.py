import json

import pytest

import index
import podcasts
import server
from tests.test_library_adapters import post


@pytest.mark.parametrize("state", ["done", "queued", "missing", "empty", "shared", "outside", "locked"])
def test_cleanup_requires_owned_audio_and_finished_transcript(tmp_path, state, monkeypatch):
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.example.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode"}])
        episode = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
        folder = tmp_path if state == "outside" else tmp_path / "Podcasts" / "show"
        folder.mkdir(exist_ok=True, parents=True)
        audio = folder / "episode.mp3"
        audio.write_bytes(b"audio")
        transcript = audio.with_suffix(".transcript.json")
        if state != "missing":
            segments = [] if state == "empty" else [{"start": 0, "end": 2, "text": "Intro"}]
            transcript.write_text(json.dumps({"segments": segments}), encoding="utf-8")
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=?, transcript_local_path=?, transcript_status=?",
                       (str(audio), str(transcript), "queued" if state == "queued" else "done"))
        if state == "shared":
            podcasts.upsert_episodes(idx, feed["id"], [{"guid": "two", "title": "Episode"}])
            with idx.write_transaction() as db:
                db.execute("UPDATE podcast_episodes SET audio_local_path=? WHERE id!=?", (str(audio), episode))
        untracked = tmp_path / "Podcasts" / "old-show" / "old-episode.wav"
        untracked.parent.mkdir(parents=True, exist_ok=True)
        untracked.write_bytes(b"old")
        usage = podcasts.audio_storage(idx, tmp_path)
        assert usage["bytes"] == (3 if state == "outside" else 8)
        if state == "locked":
            def locked_file(path, **kwargs):
                assert path == audio
                raise PermissionError("File is in use")

            monkeypatch.setattr(type(audio), "unlink", locked_file)
        assert podcasts.delete_transcribed_audio(idx, tmp_path, episode) == (state == "done")
        assert audio.exists() == (state != "done")
        assert untracked.is_file()
        assert transcript.exists() == (state != "missing")
        row = podcasts.get_episode(idx, episode)
        assert bool(row["audio_local_path"]) == (state != "done")
        assert server._default_settings()["keep_podcast_audio"] is True


def test_cleanup_http_action_requires_explicit_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(podcasts, "delete_transcribed_audio", lambda idx, root, ident: calls.append(ident) or True)
    for confirmed in (None, False, "true"):
        assert post("/podcasts/audio-storage/delete", {"episode_id": 1, "confirmed": confirmed}).status == 400
    assert calls == []
    result = post("/podcasts/audio-storage/delete", {"episode_id": 1, "confirmed": True})
    assert result.status == 200 and result.payload["removed"] and calls == [1]
