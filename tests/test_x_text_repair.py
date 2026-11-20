"""3.18.0 "Fix cut-off X posts": the user-started repair job, against a
real index and real save files in a temp folder. Network answers come from
made-up fixtures (tests/fixtures/x_fulltext_cases.json).

Acceptance: kill and restart mid-run, then resume. Never clobber a save
whose text is already whole. Never lose notes, tags, opens or shelves."""
import copy
import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import index as index_mod
import page_extractor
import x_extractor
import x_text_repair

CASES = json.loads((Path(__file__).parent / "fixtures" / "x_fulltext_cases.json")
                   .read_text(encoding="utf-8"))["cases"]
FX = "https://api.fxtwitter.com/"
GONE_ID = "1900000000000000010"
WHOLE_ID = "1900000000000000011"
MEDIA = CASES["long_post_media"]
LONG = CASES["long_post"]


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def fresh_fxtwitter_state():
    x_extractor.reset_fxtwitter_state()
    yield
    x_extractor.reset_fxtwitter_state()


@pytest.fixture
def net(monkeypatch):
    """Answers by post id. A missing id is a 404 (the post is gone)."""
    whole_text = ("A whole post that happens to be long enough to look cut. " * 5).strip()[:276]
    state = {
        "log": [],
        "syndication": {
            LONG["tweet_id"]: LONG["syndication"],
            MEDIA["tweet_id"]: MEDIA["syndication"],
            WHOLE_ID: {"__typename": "Tweet", "id_str": WHOLE_ID, "text": whole_text,
                       "created_at": "2026-11-05T10:00:00.000Z",
                       "user": {"name": "Example Writer", "screen_name": "example_writer"},
                       "entities": {"urls": []}},
        },
        "fxtwitter": {LONG["tweet_id"]: LONG["fxtwitter"], MEDIA["tweet_id"]: MEDIA["fxtwitter"]},
        "whole_text": whole_text,
    }

    def urlopen(request, timeout=None, **_kwargs):
        url = request.full_url
        if url.startswith(x_extractor.SYNDICATION_URL):
            host, tweet_id = "syndication", parse_qs(urlparse(url).query)["id"][0]
        elif url.startswith(FX):
            host, tweet_id = "fxtwitter", url.rstrip("/").rsplit("/", 1)[-1]
        else:
            pytest.fail(f"unexpected request {url}")
        state["log"].append((host, tweet_id))
        answer = state[host].get(tweet_id)
        if answer is None:
            raise urllib.error.HTTPError(url, 404, "fixture", {}, None)
        if isinstance(answer, BaseException):
            raise answer
        return _Resp(answer)

    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", urlopen)
    return state


@pytest.fixture
def lib(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    yield idx, tmp_path / "out", tmp_path / "data"
    idx.close()


def thread_save(idx, out, syndication, handle="example_writer"):
    """Save a post the way /extract/x does, from X's cut-off copy."""
    tweet_id = syndication["id_str"]
    result = x_extractor.extract_x_thread(
        f"https://x.com/{handle}/status/{tweet_id}",
        _fetch=lambda _tid, **_kw: copy.deepcopy(syndication))
    assert result["ok"], result
    return page_extractor.persist_page_yoink(idx, result, data_root=out, source_type="x_thread",
                                             subfolder="X", slug_prefix="x")


def video_save(idx, out, video_id, tweet_id, description, *, title, yoinked_at="2026-11-02T10:00:00"):
    """An X video saved by an older Uoink: yt-dlp's cut-off description."""
    folder = out / "X" / video_id
    folder.mkdir(parents=True)
    corpus = folder / f"{video_id}.md"
    url = f"https://x.com/example_maker/status/{tweet_id}"
    corpus.write_text(
        f"# {title}\n\n**Source:** {url}\n\n## Description\n\n{description}\n\n"
        "## Tags\n\n*No tags.*\n\n## Transcript\n\n[00:00] TRANSCRIPT-KEEP the desk tour starts here.\n",
        encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps({
        "title": title, "description": description, "url": url, "video_id": video_id,
        "transcript": "TRANSCRIPT-KEEP the desk tour starts here."}, indent=2), encoding="utf-8")
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": "example_maker", "title": title,
        "topic": None, "hook_type": None, "yoinked_at": yoinked_at,
        "corpus_path": str(corpus), "sidecar_path": str(folder / "metadata.json"),
        "metadata_json": json.dumps({"url": url}), "schema_version": 2,
        "source_type": "video", "platform": "x", "author": "example_maker",
    }, content=corpus.read_text(encoding="utf-8"))
    return video_id


def row_of(idx, video_id):
    return next(r for r in idx.x_text_rows() if r["video_id"] == video_id)


def files_of(row):
    paths = [Path(row["corpus_path"]), Path(row["sidecar_path"])]
    return {str(p): p.read_bytes() for p in paths}


def keepers(idx, video_id):
    """Everything a person added to a save that the job must leave alone."""
    with idx._lock:
        conn = idx._conn
        return {
            "tags": sorted(r[0] for r in conn.execute(
                "SELECT tag FROM yoink_tags WHERE video_id=?", (video_id,)).fetchall()),
            "opens": conn.execute("SELECT COUNT(*) FROM item_opens WHERE video_id=?", (video_id,)).fetchone()[0],
            "shelves": sorted(r[0] for r in conn.execute(
                "SELECT shelf_id FROM item_shelves WHERE video_id=?", (video_id,)).fetchall()),
            "topic": conn.execute("SELECT topic FROM yoinks WHERE video_id=?", (video_id,)).fetchone()[0],
        }


def personalize(idx, video_id):
    idx.add_tags(video_id, ["keep-me"], source="user")
    assert idx.mark_opened(video_id)
    with idx._lock:
        conn = idx._conn
        conn.execute("INSERT OR IGNORE INTO shelf_versions (version_id, revision_hash, status, created_at) "
                     "VALUES ('v-test', ?, 'active', '2026-11-01T00:00:00Z')", ("a" * 64,))
        conn.execute("INSERT OR IGNORE INTO shelves (shelf_id, created_at) VALUES ('reading', '2026-11-01T00:00:00Z')")
        conn.execute("INSERT OR IGNORE INTO shelf_nodes (version_id, shelf_id, parent_shelf_id, name, path_json, "
                     "definition, include_json, exclude_json, retired) "
                     "VALUES ('v-test', 'reading', NULL, 'reading', '[\"reading\"]', 'definition', '[]', '[]', 0)")
        conn.execute(
            "INSERT INTO item_shelves (video_id, shelf_id, version_id, source_revision, source, locked, "
            "is_primary, confidence, evidence_json, assigned_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (video_id, "reading", "v-test", "rev", "user", 1, 1, None, "{}", "2026-11-01T00:00:00Z"))
        conn.commit()


def job_for(idx, data, *, fxtwitter=True, **kwargs):
    kwargs.setdefault("sleep", lambda _s: None)
    kwargs.setdefault("pace", 0)
    return x_text_repair.RepairJob(data_root=data, index_getter=lambda: idx,
                                   fxtwitter_getter=lambda: fxtwitter, **kwargs)


def build_library(idx, out, net):
    gone = copy.deepcopy(LONG["syndication"])
    gone["id_str"] = GONE_ID
    whole = net["whole_text"]
    ids = {
        "thread": thread_save(idx, out, LONG["syndication"]),
        "video": video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"],
                            title="Studio changes"),
        "gone": thread_save(idx, out, gone),
        "whole_video": video_save(idx, out, "x_video_whole", WHOLE_ID, whole, title="Whole already",
                                  yoinked_at="2026-11-01T10:00:00"),
        "short": thread_save(idx, out, CASES["short_post"]["syndication"]),
    }
    corpus = Path(row_of(idx, ids["thread"])["corpus_path"])
    corpus.write_text(corpus.read_text(encoding="utf-8") + "\n## My notes\n\nKEEP-THIS-LINE\n", encoding="utf-8")
    return ids


# ---- the run ---------------------------------------------------------------------
def test_run_fixes_cut_off_saves_and_keeps_everything_else(lib, net):
    idx, out, data = lib
    ids = build_library(idx, out, net)
    for key in ("thread", "video"):
        personalize(idx, ids[key])
    before = {key: keepers(idx, vid) for key, vid in ids.items()}
    untouched = {key: files_of(row_of(idx, ids[key])) for key in ("gone", "whole_video", "short")}
    assert not idx.search("checker") and not idx.search("tray")

    job = job_for(idx, data)
    job.refresh_scan(wait=True)
    status = job.status()
    assert status["candidates"] == 4  # thread, video, gone, whole_video (short is whole)
    reply = job.start()
    assert reply["ok"] is True
    job.wait(20)
    status = job.status()
    assert status["status"] == "done", status
    assert status["run"]["fixed"] == 2 and status["run"]["gone"] == 1 and status["run"]["already_full"] == 1

    # The post save: whole text in the file, the record and search.
    row = row_of(idx, ids["thread"])
    corpus = Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert "FULL-TEXT-END" in corpus and "KEEP-THIS-LINE" in corpus
    assert corpus.count("from scratch. The first version") == 1  # replaced, not appended
    sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    post = sidecar["metadata"]["x_capture"]["posts"][-1]
    assert post["text"].endswith("FULL-TEXT-END") and post["text_completeness"] == "complete"
    assert post["text_repair"]["original_text"] == LONG["syndication"]["text"]
    assert sidecar["metadata"]["text_cut_off"] is None  # the reader stops offering a fix
    assert json.loads(row["metadata_json"])["x_capture"]["posts"][-1]["text"].endswith("FULL-TEXT-END")
    assert [r["video_id"] for r in idx.search("checker")] == [ids["thread"]]

    # The video save: Description replaced, transcript and metadata kept.
    row = row_of(idx, ids["video"])
    corpus = Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert "MEDIA-TEXT-END" in corpus and "TRANSCRIPT-KEEP" in corpus
    meta = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert meta["description"].startswith(MEDIA["full_text"][:40]) and "MEDIA-TEXT-END" in meta["description"]
    assert meta["x_text_repair"]["original_description"] == MEDIA["syndication"]["text"]
    assert meta["x_text"]["text_completeness"] == "complete" and meta["transcript"].startswith("TRANSCRIPT-KEEP")
    assert [r["video_id"] for r in idx.search("tray")] == [ids["video"]]

    # Gone, whole and short saves are byte for byte as they were.
    for key, files in untouched.items():
        assert files_of(row_of(idx, ids[key])) == files, key
    # Tags, opens, shelves and topic are untouched everywhere.
    assert {key: keepers(idx, vid) for key, vid in ids.items()} == before

    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 0


def test_only_long_posts_reach_fxtwitter(lib, net):
    idx, out, data = lib
    build_library(idx, out, net)
    job = job_for(idx, data)
    job.start()
    job.wait(20)
    asked = {tweet_id for host, tweet_id in net["log"] if host == "fxtwitter"}
    assert asked == {LONG["tweet_id"], MEDIA["tweet_id"]}  # never the gone or whole posts


# ---- the switch ------------------------------------------------------------------
def test_with_the_switch_off_it_counts_explains_and_does_nothing(lib, monkeypatch):
    idx, out, data = lib
    gone = copy.deepcopy(LONG["syndication"])
    thread_save(idx, out, gone)
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")

    def forbidden(*_args, **_kwargs):
        pytest.fail("nothing may leave the computer with the switch off")
    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", forbidden)

    job = job_for(idx, data, fxtwitter=False)
    job.refresh_scan(wait=True)
    status = job.status()
    assert status["candidates"] == 2 and status["fxtwitter"] is False
    assert {item["url"] for item in status["sample"]} == {
        f"https://x.com/example_writer/status/{LONG['tweet_id']}",
        f"https://x.com/i/status/{MEDIA['tweet_id']}"}
    reply = job.start()
    assert reply["ok"] is False and reply["code"] == "needs_fxtwitter"
    assert "Settings" in reply["error"]
    assert job._thread is None and job.status()["status"] == "idle"
    assert job.fix_one("x_video_media")["code"] == "needs_fxtwitter"


def test_turning_the_switch_off_mid_run_stops_the_run(lib, net):
    idx, out, data = lib
    build_library(idx, out, net)
    switch = {"on": True}
    seen = []

    def fetch(tweet_id):
        seen.append(tweet_id)
        switch["on"] = False  # the person turns it off while the first post is fetched
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    job = x_text_repair.RepairJob(data_root=data, index_getter=lambda: idx, fxtwitter_getter=lambda: switch["on"],
                                  fetch=fetch, sleep=lambda _s: None, pace=0)
    job.start()
    job.wait(20)
    status = job.status()
    assert len(seen) == 1 and status["status"] == "paused"
    assert status["reason"] == x_text_repair.NEEDS_SWITCH


# ---- kill and restart ------------------------------------------------------------
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_mid_run_then_restart_resumes_without_asking_again(lib, net):
    idx, out, data = lib
    ids = build_library(idx, out, net)
    asked = []

    def killing_fetch(tweet_id):
        asked.append(tweet_id)
        if len(asked) == 2:
            raise SystemExit("helper killed")  # the process dies mid-run
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    first = job_for(idx, data, fetch=killing_fetch)
    first.start()
    first.wait(20)
    state = json.loads((data / x_text_repair.STATE_NAME).read_text(encoding="utf-8"))
    assert state["status"] == "running"  # nobody got to write "stopped"
    finished_first = [vid for vid, item in state["items"].items() if item["status"] in x_text_repair.SETTLED]
    assert len(finished_first) == 1

    asked_after = []

    def fetch(tweet_id):
        asked_after.append(tweet_id)
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    second = job_for(idx, data, fetch=fetch)  # a new helper process
    assert second.resume_if_interrupted() is True
    second.wait(20)
    status = second.status()
    assert status["status"] == "done", status
    assert asked[0] not in asked_after  # the finished save is never asked about again
    assert status["run"]["fixed"] == 2 and status["run"]["gone"] == 1 and status["run"]["already_full"] == 1
    assert "FULL-TEXT-END" in Path(row_of(idx, ids["thread"])["corpus_path"]).read_text(encoding="utf-8")
    assert "MEDIA-TEXT-END" in Path(row_of(idx, ids["video"])["corpus_path"]).read_text(encoding="utf-8")


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_between_file_and_search_text_is_finished_on_restart(lib, net, monkeypatch):
    idx, out, data = lib
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"],
                       title="Studio changes")
    real_update = idx.update_corpus_text
    calls = {"n": 0}

    def dies_once(video_id, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit("helper killed after the corpus write")
        return real_update(video_id, **kwargs)
    monkeypatch.setattr(idx, "update_corpus_text", dies_once)
    first = job_for(idx, data)
    first.start()
    first.wait(20)
    row = row_of(idx, video)
    assert "MEDIA-TEXT-END" in Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert not idx.search("tray")  # search text not written yet
    assert "x_text" not in json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))

    second = job_for(idx, data)
    assert second.resume_if_interrupted() is True
    second.wait(20)
    assert second.status()["status"] == "done"
    assert [r["video_id"] for r in idx.search("tray")] == [video]
    meta = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert meta["x_text"]["text_completeness"] == "complete"
    assert meta["x_text_repair"]["original_description"] == MEDIA["syndication"]["text"]
    corpus = Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert corpus.count("Three things I changed") == 1


def test_pause_and_stop_are_kept_and_a_finished_run_does_not_restart(lib, net):
    idx, out, data = lib
    build_library(idx, out, net)
    job = job_for(idx, data)

    def pausing_fetch(tweet_id):
        job.pause()
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    job._fetch = pausing_fetch
    job.start()
    job.wait(20)
    assert job.status()["status"] == "paused"
    assert job.resume_if_interrupted() is False  # a paused run waits for the person
    job._fetch = None
    job.start()
    job.wait(20)
    assert job.status()["status"] == "done"
    assert job_for(idx, data).resume_if_interrupted() is False


# ---- never clobber ---------------------------------------------------------------
def test_never_rewrites_a_save_that_does_not_match_the_post(lib, net):
    idx, out, data = lib
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"],
                       "Someone edited this description by hand and it no longer matches the post at all, "
                       "which is fine, it is their library and their words stay exactly as they wrote them "
                       "down. It is long enough to look like X's cut-off copy, but the job must check first.",
                       title="Studio changes")
    files = files_of(row_of(idx, video))
    job = job_for(idx, data)
    job.start()
    job.wait(20)
    assert job.status()["run"]["skipped"] == 1
    assert files_of(row_of(idx, video)) == files


def test_a_post_whose_whole_text_is_already_saved_is_left_alone(lib, net):
    idx, out, data = lib
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["full_text"], title="Studio changes")
    # Whole already: the scan does not even list it.
    job = job_for(idx, data)
    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 0
    files = files_of(row_of(idx, video))
    job.start()
    job.wait(20)
    assert files_of(row_of(idx, video)) == files
    assert net["log"] == []


# ---- back-off --------------------------------------------------------------------
def test_rate_limits_back_off_and_then_pause(lib, net):
    idx, out, data = lib
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")
    net["fxtwitter"][MEDIA["tweet_id"]] = urllib.error.HTTPError(FX, 429, "fixture", {"Retry-After": "45"}, None)
    clock = {"t": 1000.0}
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds
        x_extractor.reset_fxtwitter_state()  # the service's own cool-down ends with the wait

    job = job_for(idx, data, sleep=sleep, clock=lambda: clock["t"])
    job.start()
    job.wait(20)
    status = job.status()
    assert status["status"] == "paused" and "slow down" in status["reason"]
    waits = [s for s in sleeps if s > 0]
    assert len(waits) == x_text_repair.MAX_RATE_LIMIT_STRIKES - 1
    assert all(w >= 45 for w in waits)
    assert sum(1 for host, _ in net["log"] if host == "fxtwitter") == x_text_repair.MAX_RATE_LIMIT_STRIKES
    # Nothing was written, and the save is still waiting to be fixed.
    assert "MEDIA-TEXT-END" not in Path(row_of(idx, "x_video_media")["corpus_path"]).read_text(encoding="utf-8")
    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 1


# ---- one save at a time ----------------------------------------------------------
def test_fix_one_fixes_a_single_save(lib, net):
    idx, out, data = lib
    ids = build_library(idx, out, net)
    job = job_for(idx, data)
    reply = job.fix_one(ids["thread"])
    assert reply["ok"] is True and reply["outcome"] == "fixed"
    assert "FULL-TEXT-END" in Path(row_of(idx, ids["thread"])["corpus_path"]).read_text(encoding="utf-8")
    assert job.fix_one(ids["short"])["code"] == "not_cut_off"
    assert job.fix_one(ids["gone"])["outcome"] == "gone"


def test_article_link_post_saves_the_article_as_its_own_item(lib, net):
    idx, out, data = lib
    case = CASES["article_only"]
    net["syndication"][case["tweet_id"]] = case["syndication"]
    net["fxtwitter"][case["tweet_id"]] = case["fxtwitter"]
    post = thread_save(idx, out, case["syndication"], handle="example_author")
    saved = []

    def persist(result):
        saved.append(result)
        return page_extractor.persist_page_yoink(idx, result, data_root=out, source_type="x_article",
                                                 subfolder="X", slug_prefix="x-article")
    job = job_for(idx, data, persist_article=persist)
    job.refresh_scan(wait=True)
    status = job.status()
    assert status["candidates"] == 1 and status["articles"] == 1
    job.start()
    job.wait(20)
    assert job.status()["run"]["fixed"] == 1
    assert len(saved) == 1 and "ARTICLE-BODY-END" in saved[0]["markdown"]
    sidecar = json.loads(Path(row_of(idx, post)["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["metadata"]["text_cut_off"]["saved_as"].startswith("x-article_")
    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 0


# ---- the reader's prompt and the dashboard block ------------------------------------
def test_details_name_a_cut_off_save_until_it_is_whole():
    import server
    long_cut = {"metadata": {"text_cut_off": {"reason": "long_post",
                                              "open_url": "https://x.com/example_writer/status/1900000000000000002"}}}
    assert server._x_cut_off_detail(long_cut) == {
        "reason": "long_post", "open_url": "https://x.com/example_writer/status/1900000000000000002"}
    article = {"metadata": {"text_cut_off": {"reason": "article", "title": "Build notes",
                                             "open_url": "https://x.com/i/article/1900000000000000777"}}}
    assert server._x_cut_off_detail(article)["title"] == "Build notes"
    saved = {"metadata": {"text_cut_off": dict(article["metadata"]["text_cut_off"], saved_as="x-article_1")}}
    assert server._x_cut_off_detail(saved) is None
    assert server._x_cut_off_detail({"metadata": {"text_cut_off": {"reason": "long_post",
                                                                  "open_url": "javascript:alert(1)"}}}) is None
    video = {"url": "https://x.com/example_maker/status/1900000000000000003",
             "x_text": {"long_post": True, "text_completeness": "truncated"}}
    assert server._x_cut_off_detail(video)["open_url"] == "https://x.com/i/status/1900000000000000003"
    video["x_text"]["text_completeness"] = "complete"
    assert server._x_cut_off_detail(video) is None
    assert server._x_cut_off_detail({"metadata": {"text_cut_off": None}}) is None


def test_dashboard_block_and_prompt_js():
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    script = Path(__file__).parent / "js" / "x_text_repair_ui_test.mjs"
    proc = subprocess.run([node, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
