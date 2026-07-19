"""Regression tests for native and cross-product engagement age decay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import index as index_mod


def _seed(idx: index_mod.Index, root: Path, video_id: str) -> None:
    folder = root / video_id
    folder.mkdir()
    idx.upsert_yoink({
        "video_id": video_id,
        "slug": video_id,
        "title": video_id,
        "channel": "Test",
        "yoinked_at": "2026-01-01T00:00:00",
        "corpus_path": str(folder / "corpus.md"),
        "sidecar_path": str(folder / "uoink.json"),
        "source_type": "youtube",
    }, content="test")


def test_aware_suite_events_decay_like_naive_native_events(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        _seed(idx, tmp_path, "suite-event")
        _seed(idx, tmp_path, "native-event")

        aware_old = datetime.now(timezone.utc) - timedelta(days=30)
        occurred_at = aware_old.isoformat(
            timespec="seconds").replace("+00:00", "Z")
        result = idx.ingest_suite_engagement([{
            "event_id": "ff7-aware-suite-event",
            "item_ref": "uoink://item/suite-event",
            "event_type": "opened",
            "source_product": "writer",
            "occurred_at": occurred_at,
        }])
        assert result["accepted"] == 1

        naive_old = datetime.now() - timedelta(days=30)
        idx.log_engagement(
            "native-event",
            "opened",
            "dashboard",
            ts_utc=naive_old.isoformat(timespec="seconds"),
        )

        suite_score = idx.engagement_signal("suite-event")["value_score"]
        native_score = idx.engagement_signal("native-event")["value_score"]

        assert 0.49 <= suite_score <= 0.51
        assert 0.49 <= native_score <= 0.51
        assert abs(suite_score - native_score) <= 0.001
    finally:
        idx.close()
