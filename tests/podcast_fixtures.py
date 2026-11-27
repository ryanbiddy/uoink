"""Synthetic recordings registered under the same paths as downloaded episodes."""
from pathlib import Path

import podcasts


def _seed_downloaded_episodes(idx, tmp_path: Path, count: int = 2) -> list[int]:
    feed_id = podcasts.add_feed(idx, "https://jobs.example/feed.xml")["id"]
    episodes = []
    for number in range(count):
        episodes.append({
            "guid": f"job-episode-{number}", "title": f"Episode {number}",
            "audio_url": f"https://cdn.example/{number}.mp3",
            "episode_page_url": f"https://jobs.example/{number}",
        })
    podcasts.upsert_episodes(idx, feed_id, episodes)
    rows = podcasts.list_episodes(idx, feed_id=feed_id)
    for row in rows:
        audio = podcasts._episode_audio_path(tmp_path, podcasts.get_feed(idx, feed_id), row)
        audio.write_bytes(b"synthetic audio")
        podcasts._record_audio_result(
            idx, row["id"], local_path=str(audio), size_bytes=audio.stat().st_size,
            error=None, status=podcasts.EPISODE_STATUS_DOWNLOADED)
    return [row["id"] for row in rows]
