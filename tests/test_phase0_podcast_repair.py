from __future__ import annotations

from datetime import datetime, timezone

import index as index_mod
import podcasts


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _episode(number: int) -> dict:
    return {
        "guid": f"episode-{number}",
        "title": f"Episode {number}",
        "audio_url": f"https://cdn.example/{number}.mp3",
        "published_at": f"2026-08-{(number % 28) + 1:02d}T12:00:00Z",
    }


def test_scheduler_repairs_existing_backlog_with_both_caps(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        feed = podcasts.add_feed(idx, "https://show.example/feed.xml")
        podcasts.upsert_episodes(idx, feed["id"], [_episode(i) for i in range(40)])
        podcasts.set_feed_auto_ingest(idx, feed["id"], True)

        repair = podcasts.repair_stranded_auto_ingest(
            idx, feed_id=feed["id"], now=NOW
        )
        assert repair["stranded_before"] == 40
        assert repair["marked_eligible"] == 25
        assert repair["eligible_after"] == 25
        assert repair["schedulable_today"] == 10
        assert len(podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=NOW
        )) == 10

        podcasts.set_feed_auto_ingest(idx, feed["id"], False)
        assert podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=NOW
        ) == []
    finally:
        idx.close()


def test_first_opted_in_poll_enrolls_only_bounded_backlog(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        feed = podcasts.add_feed(
            idx, "https://new.example/feed.xml", auto_ingest=True
        )
        podcasts.upsert_episodes(idx, feed["id"], [_episode(i) for i in range(50)])
        assert idx._conn.execute(
            "SELECT COUNT(*) FROM podcast_episodes WHERE auto_ingest_requested=1"
        ).fetchone()[0] == 0
        repair = podcasts.repair_stranded_auto_ingest(idx, feed_id=feed["id"])
        assert repair["marked_eligible"] == 25
    finally:
        idx.close()


def test_daily_cap_counts_durable_ingest_evidence(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        feed = podcasts.add_feed(idx, "https://daily.example/feed.xml")
        podcasts.upsert_episodes(idx, feed["id"], [_episode(i) for i in range(12)])
        podcasts.set_feed_auto_ingest(idx, feed["id"], True)
        podcasts.repair_stranded_auto_ingest(idx, feed_id=feed["id"])
        with idx.write_transaction() as conn:
            rows = conn.execute(
                "SELECT id FROM podcast_episodes ORDER BY id LIMIT 10"
            ).fetchall()
            conn.executemany(
                "UPDATE podcast_episodes SET status='transcribed', "
                "yoink_video_id=?, audio_downloaded_at='2026-09-04T01:00:00Z' "
                "WHERE id=?",
                [(f"done-{row['id']}", row["id"]) for row in rows],
            )
        assert podcasts.count_daily_ingest_starts(idx, feed["id"], now=NOW) == 10
        assert podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=NOW
        ) == []

        with idx.write_transaction() as conn:
            conn.execute(
                "UPDATE podcast_episodes SET audio_downloaded_at="
                "'2026-09-03T23:00:00Z' WHERE id=?",
                (rows[0]["id"],),
            )
        assert len(podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=NOW
        )) == 1
    finally:
        idx.close()


def test_later_discoveries_are_eligible_after_backlog_enrollment(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        feed = podcasts.add_feed(idx, "https://future.example/feed.xml")
        podcasts.upsert_episodes(idx, feed["id"], [_episode(i) for i in range(30)])
        podcasts.set_feed_auto_ingest(idx, feed["id"], True)
        podcasts.repair_stranded_auto_ingest(idx, feed_id=feed["id"])
        podcasts.upsert_episodes(idx, feed["id"], [_episode(99)])
        row = idx._conn.execute(
            "SELECT auto_ingest_requested FROM podcast_episodes WHERE guid='episode-99'"
        ).fetchone()
        assert row[0] == 1
    finally:
        idx.close()
