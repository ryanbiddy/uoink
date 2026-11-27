"""Upgrades and public podcast reads on a library with mixed date formats."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import index
import podcasts
import source_subscriptions as ss
import uoink_mcp_tools as mcp
from source_subscriptions_fixtures import Clock, FakeAdapter, items, make_service, register, status, turn_on
from tests.test_dashboard_runthrough_fixes import run_js


DATES = {
    "old": "Wed, 30 Sep 2026 12:00:00 GMT",
    "new": "2026-10-01T02:30:00+02:00",
    "middle": "Wed, 30 Sep 2026 18:30:00 -0500",
    "missing": None,
    "broken": "yesterday-ish",
    "early": "1969-12-31T23:59:59Z",
}
ORDER = ["new", "middle", "old", "early", "broken", "missing"]


def old_feed(index_db, consent=False):
    with index_db.write_transaction() as db:
        return db.execute(
            "INSERT INTO podcast_feeds(feed_url,title,added_at,last_polled_at,auto_ingest) "
            "VALUES ('https://radio.test/rss','Test radio','2026-08-01','2026-08-02',?)",
            (int(consent),)).lastrowid


@pytest.mark.parametrize("old_schema", [True, False])
def test_projected_episode_keeps_its_identity_and_corrected_date(tmp_path, monkeypatch, old_schema):
    if old_schema:
        migrations = [(n, p) for n, p in index._discover_migrations() if n <= 28]
        monkeypatch.setattr(index, "_discover_migrations", lambda: migrations)
    with index.Index.open(tmp_path / "pod.db") as idx:
        clock = Clock()
        snapshots = []
        for raw in (DATES["old"], DATES["new"], DATES["new"]):
            observation = ss.Observation(
                entry_id="one", title="Episode one",
                metadata={"identity_method": "guid", "published_raw": raw,
                          "audio_url": "https://radio.test/one.mp3"},
            )
            snapshots.append(ss.AdapterResult("snapshot", observations=[observation], coverage="complete"))
        service = make_service(idx, clock=clock, adapter=FakeAdapter(snapshots))
        sid = register(service, kind="podcast_rss", url="https://radio.test/feed")["source_id"]
        turn_on(service, sid)
        for raw in (DATES["old"], DATES["new"]):
            service.detection_pass()
            item, = items(service, sid)
            episode, = idx._conn.execute("SELECT * FROM podcast_episodes")
            assert episode["id"] == item["legacy_episode_id"] and episode["published_at"] == raw
            if not old_schema:
                assert episode["published_at_ms"] == ss.parse_published_ms(raw)
            clock.advance(61 * 60_000)
        # Prior polls could retain the observation without creating its episode.
        with idx.write_transaction() as db:
            db.execute("UPDATE source_items SET legacy_episode_id=NULL WHERE item_id=?", (item["item_id"],))
            db.execute("DELETE FROM podcast_episodes WHERE id=?", (episode["id"],))
        service.detection_pass()
        recovered, = items(service, sid)
        episode, = idx._conn.execute("SELECT * FROM podcast_episodes")
        assert recovered["item_id"] == item["item_id"]
        assert recovered["legacy_episode_id"] == episode["id"] and episode["published_at"] == DATES["new"]


def test_feed_and_episodes_sort_by_publish_instant(tmp_path):
    with index.Index.open(tmp_path / "pod.db") as idx:
        fid = old_feed(idx)
        podcasts.upsert_episodes(idx, fid, [
            {"guid": k, "title": k, "published_at": v} for k, v in DATES.items()])
        assert [r["guid"] for r in podcasts.list_episodes(idx)] == ORDER
        feed, = podcasts.list_feeds(idx)
        assert (feed["last_episode_title"], feed["latest_episode_published_at"]) == ("new", DATES["new"])


def test_legacy_auto_ingest_sorts_real_dates_before_undated(tmp_path, monkeypatch):
    with index.Index.open(tmp_path / "pod.db") as idx:
        fid = old_feed(idx, consent=True)
        podcasts.upsert_episodes(idx, fid, [
            {"guid": k, "title": k, "published_at": v} for k, v in DATES.items()])
        monkeypatch.setattr(ss, "tables_present", lambda conn: False)
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET auto_ingest_requested=1")
        assert [r["guid"] for r in podcasts.list_auto_ingest_candidates(idx, limit=10)] == ORDER


def test_migration_backfills_dates_and_already_imported_follows(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    migrations = [(n, p) for n, p in index._discover_migrations() if n <= 39]
    clock = Clock()
    with monkeypatch.context() as old:
        old.setattr(index, "_discover_migrations", lambda: migrations)
        with index.Index.open(path) as idx:
            fid = old_feed(idx)
            with idx.write_transaction() as db:
                db.executemany(
                    "INSERT INTO podcast_episodes(feed_id,guid,published_at,discovered_at) "
                    "VALUES (?,?,?,'2026-08-02')", [(fid, k, v) for k, v in DATES.items()])
            service = make_service(idx, clock=clock)
            service.import_legacy_registries()
            # The subscription that the previous release left behind.
            idx._conn.execute("UPDATE source_subscriptions SET follow_feed=0")
            idx._conn.commit()
    with index.Index.open_existing(path) as reader:
        assert [ep["guid"] for ep in podcasts.list_episodes(reader)] == ORDER
        assert podcasts.list_feeds(reader)[0]["latest_episode_published_at"] == DATES["new"]
    with index.Index.open(path) as idx:
        service = make_service(idx, clock=clock)
        assert service.due_poll_ids() == [ss.legacy_source_id(idx._conn, feed_id=fid)]
        episodes = podcasts.list_episodes(idx)
        assert [ep["guid"] for ep in episodes] == ORDER
        for ep in episodes:
            assert ep["published_at"] == DATES[ep["guid"]]
            assert ep["published_at_ms"] == ss.parse_published_ms(ep["published_at"])
        sid = ss.legacy_source_id(idx._conn, feed_id=fid)
        with idx.write_transaction() as db:
            db.execute("UPDATE source_items SET state='committed' WHERE entry_id='old'")
        assert status(service, sid)["source"]["latest_episode"]["entry_id"] == "new"


@pytest.mark.parametrize("capture", [False, True])
def test_imported_feed_gets_hourly_checks_and_persists_last_success(tmp_path, capture):
    with index.Index.open(tmp_path / "pod.db") as idx:
        fid = old_feed(idx, consent=capture)
        clock = Clock()
        adapter = FakeAdapter([ss.AdapterResult("snapshot", coverage="complete"),
                               ss.AdapterResult("not_modified")])
        service = make_service(idx, clock=clock, adapter=adapter)
        service.import_legacy_registries()
        sid = ss.legacy_source_id(idx._conn, feed_id=fid)
        for outcome in ("snapshot", "not_modified"):
            assert [r["outcome"] for r in service.detection_pass()] == [outcome]
            stamp = podcasts.get_feed(idx, fid)["last_polled_at"]
            assert datetime.fromisoformat(stamp.replace("Z", "+00:00")) == datetime.fromtimestamp(
                clock.now / 1000, timezone.utc)
            assert not service.due_poll_ids()
            clock.advance(61 * 60_000)
        assert status(service, sid)["source"]["consent_state"] == ("on" if capture else "off")


def test_archived_feed_absent_from_mcp_while_paused_feed_and_history_survive(tmp_path, monkeypatch):
    with index.Index.open(tmp_path / "pod.db") as idx:
        monkeypatch.setattr(mcp, "_b", lambda: SimpleNamespace(_get_index=lambda: idx))
        gone = podcasts.add_feed(idx, "https://gone.test/rss")
        paused = podcasts.add_feed(idx, "https://paused.test/rss", enabled=False)
        assert mcp.remove_podcast_feed({"feed_id": gone["id"]})["removed"]
        assert [r["id"] for r in mcp.list_podcast_feeds({})["feeds"]] == [paused["id"]]
        assert podcasts.get_feed(idx, gone["id"])["enabled"] == 0
        assert not podcasts.list_feeds(idx, enabled_only=True)


def test_sources_and_settings_explain_metadata_checks_and_preserve_the_feed_error():
    html = run_js("""(() => {
      const message = "The host could not send the first episodes within the size limit.";
      state.standingSources = [{source_id: "one", kind: "podcast_rss", consent_state: "off",
        follow_feed: true, canonical_url: "https://radio.test/path", detection: {}}];
      renderStandingSubscriptions();
      const following = els.standingSubscriptionList.innerHTML;
      state.standingSources[0].detection = {error: {code: "feed_too_large", message},
        consecutive_failures: 3};
      renderStandingSubscriptions();
      renderPodcastFeedList([{id: 2, feed_url: "https://radio.test/path", last_error: message}]);
      return {following, failed: els.standingSubscriptionList.innerHTML,
        settings: els.podcastFeedList.innerHTML, message};
    })()""")
    assert "Turn on automatic capture to check" not in html["following"]
    assert ">radio.test<" in html["following"] and ">radio.test<" in html["settings"]
    assert html["message"] in html["failed"] and html["message"] in html["settings"]


def test_sources_subscribe_uses_the_same_feed_validation_as_settings():
    result = run_js("""(async () => {
      const calls = [];
      const link = "https://podcasts.apple.com/podcast/example/id123?i=456";
      els.standingAddKind.value = "podcast_rss";
      els.standingAddUrl.value = link;
      els.standingAddDisplayName.value = "My show";
      authFetch = async (path, req) => { calls.push([path, JSON.parse(req.body)]);
        return {ok:true, episode_id:7}; };
      loadStandingSubscriptions = async () => {};
      await registerStandingSource();
      return {calls, message:els.toast.textContent, link};
    })()""")
    assert result["calls"] == [["/podcasts/feeds", {"feed_url": result["link"], "display_name": "My show"}]]
    assert result["message"] == "Podcast episode queued."
