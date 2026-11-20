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

    def read(self, amount=-1):
        return self._body if amount is None or amount < 0 else self._body[:amount]


HELPER_GATE = {}


@pytest.fixture(autouse=True)
def fresh_fxtwitter_state(monkeypatch):
    # The helper registers its own reader of the switch when it is imported,
    # so import it first and put the test's switch on top.
    import server  # noqa: F401
    HELPER_GATE.setdefault("gate", x_extractor._fxtwitter_gate)
    x_extractor.reset_fxtwitter_state()
    # The user's switch as x_extractor reads it before each FxTwitter request.
    switch = {"on": True}
    monkeypatch.setattr(x_extractor, "_fxtwitter_gate", lambda: switch["on"])
    yield switch
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

    monkeypatch.setattr(x_extractor, "_urlopen", urlopen)
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
    monkeypatch.setattr(x_extractor, "_urlopen", forbidden)

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


def shared_job(idx, data, switch, **kwargs):
    """A job reading the same switch x_extractor reads, as in the helper."""
    kwargs.setdefault("sleep", lambda _s: None)
    kwargs.setdefault("pace", 0)
    return x_text_repair.RepairJob(data_root=data, index_getter=lambda: idx,
                                   fxtwitter_getter=lambda: switch["on"], **kwargs)


def fx_asks(net):
    return [tweet_id for host, tweet_id in net["log"] if host == "fxtwitter"]


def test_turning_the_switch_off_mid_run_stops_the_run(lib, net, fresh_fxtwitter_state):
    idx, out, data = lib
    ids = build_library(idx, out, net)
    switch = fresh_fxtwitter_state

    def fetch(tweet_id):
        switch["on"] = False  # the person turns it off while X answers about the first post
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    job = shared_job(idx, data, switch, fetch=fetch)
    job.start()
    job.wait(20)
    status = job.status()
    assert status["status"] == "paused"
    # Deliberately changed in review: a run the switch stopped says so and how to go on.
    assert status["reason"] == x_text_repair.SWITCHED_OFF
    assert fx_asks(net) == []  # FxTwitter was never asked once the switch was off
    # The post it was on waits for Resume, it is not counted as tried.
    switch["on"] = True
    job._fetch = None
    job.start()
    job.wait(20)
    assert job.status()["status"] == "done"
    assert "FULL-TEXT-END" in Path(row_of(idx, ids["thread"])["corpus_path"]).read_text(encoding="utf-8")


def test_turning_the_switch_off_during_a_back_off_wait_sends_nothing_more(lib, net, fresh_fxtwitter_state):
    idx, out, data = lib
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")
    net["fxtwitter"][MEDIA["tweet_id"]] = urllib.error.HTTPError(FX, 429, "fixture", {"Retry-After": "45"}, None)
    switch = fresh_fxtwitter_state
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        if seconds >= 45:
            switch["on"] = False  # turned off while Uoink waits out the slow-down
            x_extractor.reset_fxtwitter_state()
    job = shared_job(idx, data, switch, sleep=sleep)
    job.start()
    job.wait(20)
    status = job.status()
    assert status["status"] == "paused" and status["reason"] == x_text_repair.SWITCHED_OFF
    assert any(w >= 45 for w in waits)
    assert fx_asks(net) == [MEDIA["tweet_id"]]  # only the request before the wait


def test_turning_the_switch_off_between_posts_of_one_thread(lib, net, fresh_fxtwitter_state):
    idx, out, data = lib
    switch = fresh_fxtwitter_state
    seen = []

    def fetch(tweet_id):
        seen.append(tweet_id)
        record = x_extractor.post_text_record(tweet_id, fxtwitter=True)
        switch["on"] = False
        return record
    job = shared_job(idx, data, switch, fetch=fetch)
    outcome = job._fetch_item({"video_id": "x_two", "kind": "thread", "title": "",
                               "tweet_ids": [LONG["tweet_id"], MEDIA["tweet_id"]]})
    assert outcome["outcome"] == "disabled" and seen == [LONG["tweet_id"]]
    assert fx_asks(net) == [LONG["tweet_id"]]


def test_every_fxtwitter_request_reads_the_switch_even_if_a_caller_skips_it(lib, net, fresh_fxtwitter_state):
    """The choke point: x_extractor.fetch_fxtwitter_status reads the switch
    before each request, so a caller that passes fxtwitter=True, or a job
    whose own check is stale, still sends nothing to FxTwitter."""
    idx, out, data = lib
    ids = build_library(idx, out, net)
    article = CASES["article_only"]
    net["syndication"][article["tweet_id"]] = article["syndication"]
    net["fxtwitter"][article["tweet_id"]] = article["fxtwitter"]
    fresh_fxtwitter_state["on"] = False
    for case in (LONG, MEDIA, CASES["quoted_post"]):
        net["syndication"].setdefault(case["tweet_id"], case["syndication"])
        x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
        x_extractor.extract_x_thread(f"https://x.com/example_writer/status/{case['tweet_id']}", fxtwitter=True)
    result = x_extractor.extract_x_thread(f"https://x.com/example_author/status/{article['tweet_id']}",
                                          fxtwitter=True)
    assert result["ok"] and "source_type" not in result  # saved as the marked post
    assert x_extractor.fetch_fxtwitter_status_json(LONG["tweet_id"]) is None
    with pytest.raises(x_extractor.XFetchError) as caught:
        x_extractor.article_capture(article["tweet_id"])
    assert caught.value.kind == "disabled"
    stale = job_for(idx, data, fxtwitter=True)  # its own getter says on
    stale.start()
    stale.wait(20)
    assert stale.status()["reason"] == x_text_repair.SWITCHED_OFF
    assert stale.fix_one(ids["thread"])["ok"] is True
    stale.wait_fix(ids["thread"], 20)
    assert stale.item_status(ids["thread"])["code"] == "disabled"
    assert fx_asks(net) == []


def test_the_helper_reads_the_settings_switch_before_each_request(monkeypatch):
    import server
    assert HELPER_GATE["gate"] is server._fxtwitter_switch_on  # registered at import
    monkeypatch.setattr(x_extractor, "_fxtwitter_gate", server._fxtwitter_switch_on)
    for settings, allowed in (({}, False), ({"fxtwitter_enrichment_enabled": True}, True),
                              ({"fxtwitter_enrichment_enabled": "yes"}, False)):
        monkeypatch.setattr(server, "_read_settings", lambda s=settings: s)
        assert x_extractor.fxtwitter_allowed() is allowed

    def broken():
        raise OSError("settings file locked")
    monkeypatch.setattr(server, "_read_settings", broken)
    assert x_extractor.fxtwitter_allowed() is False
    monkeypatch.setattr(x_extractor, "_fxtwitter_gate", None)
    assert x_extractor.fxtwitter_allowed() is False  # nothing registered: off


def test_only_one_function_talks_to_fxtwitter():
    """Every FxTwitter request in the helper goes through the one function
    that reads the switch. Fails if a new caller builds its own request."""
    import ast
    root = Path(__file__).resolve().parent.parent
    runtime = [p for p in root.glob("*.py")] + list((root / "uoink_core").glob("*.py"))

    def code_strings(path):
        """String values in the code (comments and docstrings left out)."""
        module = ast.parse(path.read_text(encoding="utf-8"))
        docs = {id(n.value) for n in ast.walk(module) if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Constant)}
        return [n.value for n in ast.walk(module) if isinstance(n, ast.Constant)
                and isinstance(n.value, str) and id(n) not in docs]
    hits = [p.name for p in runtime if any("fxtwitter.com" in s.lower() for s in code_strings(p))]
    assert hits == ["x_extractor.py"]
    tree = ast.parse((root / "x_extractor.py").read_text(encoding="utf-8"))
    users, openers = set(), set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id == "FXTWITTER_STATUS_URL":
                users.add(fn.name)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_urlopen":
                openers.add(fn.name)
            if (isinstance(node, ast.Attribute) and node.attr == "urlopen"
                    and isinstance(node.value, ast.Attribute) and node.value.attr == "request"):
                pytest.fail(f"{fn.name} calls urllib.request.urlopen directly")
    assert users == {"fetch_fxtwitter_status"}
    assert openers == {"fetch_syndication_json", "fetch_fxtwitter_status"}
    source = ast.get_source_segment((root / "x_extractor.py").read_text(encoding="utf-8"),
                                    next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                                         and n.name == "fetch_fxtwitter_status"))
    body = source.split('"""', 2)[-1]
    assert body.index("fxtwitter_allowed()") < body.index("_urlopen(")


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
@pytest.fixture
def clock(monkeypatch):
    """One made-up clock for the job and for x_extractor's FxTwitter
    cool-down. A wait moves it forward; nothing resets the cool-down."""
    now = {"t": 1000.0, "sleeps": []}

    def sleep(seconds):
        now["sleeps"].append(seconds)
        now["t"] += seconds
    monkeypatch.setattr(x_extractor, "_fx_clock", lambda: now["t"])
    now["sleep"] = sleep
    now["read"] = lambda: now["t"]
    return now


def test_rate_limits_back_off_and_then_pause(lib, net, clock):
    # Deliberately changed in review: the test used to reset FxTwitter's
    # cool-down inside its fake sleep, which hid a job that woke too early.
    # It now shares one clock, and a post is tried at most MAX_ITEM_ATTEMPTS
    # times (the old run could retry a slowed-down post without end).
    idx, out, data = lib
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")
    net["fxtwitter"][MEDIA["tweet_id"]] = urllib.error.HTTPError(FX, 429, "fixture", {"Retry-After": "200"}, None)
    job = job_for(idx, data, sleep=clock["sleep"], clock=clock["read"])
    job.start()
    job.wait(20)
    status = job.status()
    assert status["status"] == "paused" and "slow down" in status["reason"]
    waits = [s for s in clock["sleeps"] if s > 0]
    assert len(waits) == x_text_repair.MAX_ITEM_ATTEMPTS - 1
    assert all(w >= 200 for w in waits)  # never shorter than the service asked
    # Every try reached FxTwitter: the job never woke inside the cool-down.
    assert fx_asks(net) == [MEDIA["tweet_id"]] * x_text_repair.MAX_ITEM_ATTEMPTS
    # Nothing was written, and the save is still waiting to be fixed.
    assert "MEDIA-TEXT-END" not in Path(row_of(idx, "x_video_media")["corpus_path"]).read_text(encoding="utf-8")
    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 1


def test_a_tiny_retry_after_still_backs_off_in_steps(lib, net, clock):
    idx, out, data = lib
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")
    # X itself asks for a one-second wait: the job still steps up its waits.
    net["syndication"][MEDIA["tweet_id"]] = urllib.error.HTTPError(
        x_extractor.SYNDICATION_URL, 429, "fixture", {"Retry-After": "1"}, None)
    job = job_for(idx, data, sleep=clock["sleep"], clock=clock["read"])
    job.start()
    job.wait(20)
    waits = [s for s in clock["sleeps"] if s > 0]
    assert waits == list(x_text_repair.BACKOFF_SEC[:x_text_repair.MAX_ITEM_ATTEMPTS - 1])


def test_slow_downs_mixed_with_short_posts_still_pause(lib, net, clock):
    """A post FxTwitter keeps slowing down is not retried forever just
    because other posts in between answered fine."""
    idx, out, data = lib
    video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"], title="Studio changes")
    net["fxtwitter"][MEDIA["tweet_id"]] = urllib.error.HTTPError(FX, 429, "fixture", {"Retry-After": "30"}, None)
    for n in range(8):  # whole posts that only ask X
        tweet_id = f"19000000000000005{n:02d}"
        net["syndication"][tweet_id] = dict(net["syndication"][WHOLE_ID], id_str=tweet_id)
        video_save(idx, out, f"x_video_whole_{n}", tweet_id, net["whole_text"], title=f"Whole {n}")
    job = job_for(idx, data, sleep=clock["sleep"], clock=clock["read"])
    job.start()
    job.wait(20)
    assert job.status()["status"] == "paused"
    assert len(fx_asks(net)) <= x_text_repair.MAX_ITEM_ATTEMPTS


def test_article_rate_limit_and_tombstone_are_typed(lib, net, clock):
    idx, out, data = lib
    case = CASES["article_only"]
    net["syndication"][case["tweet_id"]] = case["syndication"]
    net["fxtwitter"][case["tweet_id"]] = urllib.error.HTTPError(FX, 429, "fixture", {"Retry-After": "200"}, None)
    thread_save(idx, out, case["syndication"], handle="example_author")
    job = job_for(idx, data, sleep=clock["sleep"], clock=clock["read"], persist_article=lambda _r: None)
    outcome = job._fetch_article_item(job._candidates()[0])
    assert outcome["outcome"] == "rate_limited" and outcome["retry_after"] >= 200
    x_extractor.reset_fxtwitter_state()
    net["fxtwitter"][case["tweet_id"]] = {"code": 200, "status": {"type": "tombstone", "id": case["tweet_id"]}}
    assert job._fetch_article_item(job._candidates()[0])["outcome"] == "gone"
    del net["syndication"][case["tweet_id"]]  # gone from X as well
    assert job._fetch_article_item(job._candidates()[0])["outcome"] == "gone"


# ---- one save at a time ----------------------------------------------------------
def fix_and_wait(job, video_id):
    reply = job.fix_one(video_id)
    if reply.get("queued"):
        job.wait_fix(video_id, 20)
    return reply, job.item_status(video_id)


def test_fix_one_fixes_a_single_save(lib, net):
    # Deliberately changed in review: the reader's button no longer holds
    # the request open. It answers "queued" and the reader polls the item.
    idx, out, data = lib
    ids = build_library(idx, out, net)
    job = job_for(idx, data)
    reply, item = fix_and_wait(job, ids["thread"])
    assert reply == {"ok": True, "queued": True, "video_id": ids["thread"], "status": "working"}
    assert item["status"] == "fixed"
    assert "FULL-TEXT-END" in Path(row_of(idx, ids["thread"])["corpus_path"]).read_text(encoding="utf-8")
    assert job.fix_one(ids["short"])["code"] == "not_cut_off"
    assert fix_and_wait(job, ids["gone"])[1]["status"] == "gone"


def test_fix_one_never_holds_the_request_and_shares_the_worker(lib, net):
    """The reader's button returns at once, and a save is worked by one
    thread at a time even while a run is going."""
    import threading
    idx, out, data = lib
    ids = build_library(idx, out, net)
    gate, inside, overlap = threading.Event(), [], []

    def slow_fetch(tweet_id):
        inside.append(tweet_id)
        if len(inside) > 1 and not gate.is_set():
            overlap.append(tweet_id)
        gate.wait(5)
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    job = job_for(idx, data, fetch=slow_fetch)
    job.start()
    reply = job.fix_one(ids["thread"])  # answers while the run's first fetch is still waiting
    assert reply["queued"] is True and job.item_status(ids["thread"])["status"] == "working"
    for _ in range(50):  # give the fix's thread time to reach a fetch, if it could
        if len(inside) > 1:
            break
        threading.Event().wait(0.01)
    gate.set()
    job.wait(20)
    job.wait_fix(ids["thread"], 20)
    assert overlap == []
    assert job.item_status(ids["thread"])["status"] == "fixed"
    corpus = Path(row_of(idx, ids["thread"])["corpus_path"]).read_text(encoding="utf-8")
    assert corpus.count("FULL-TEXT-END") == 1


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


# ---- review fixes: quoted posts --------------------------------------------------
def test_a_short_post_quoting_a_cut_off_post_is_fixed(lib, net):
    """The reader offers the fix for a cut-off quoted post, so the fix has
    to find it and complete the quote (it used to say "isn't cut off")."""
    import server
    idx, out, data = lib
    case = CASES["quoted_post"]
    net["syndication"][case["tweet_id"]] = case["syndication"]
    net["fxtwitter"][case["tweet_id"]] = case["fxtwitter"]
    video_id = thread_save(idx, out, case["syndication"], handle="example_reader")
    sidecar_path = Path(row_of(idx, video_id)["sidecar_path"])
    assert server._x_cut_off_detail(json.loads(sidecar_path.read_text(encoding="utf-8")))  # the prompt shows
    own_words = case["syndication"]["text"].split(" https://")[0][:40]
    before = Path(row_of(idx, video_id)["corpus_path"]).read_text(encoding="utf-8").count(own_words)
    job = job_for(idx, data)
    reply, item = fix_and_wait(job, video_id)
    assert reply["queued"] is True and item["status"] == "fixed", item
    corpus = Path(row_of(idx, video_id)["corpus_path"]).read_text(encoding="utf-8")
    assert corpus.count("QUOTE-TEXT-END") == 1
    assert corpus.count(own_words) == before  # the post's own words are not repeated
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    post = sidecar["metadata"]["x_capture"]["posts"][-1]
    assert post["quote"]["text"].endswith("QUOTE-TEXT-END")
    assert post["text_repair"]["original_quote_text"] == case["syndication"]["quoted_tweet"]["text"]
    assert server._x_cut_off_detail(sidecar) is None  # the prompt goes away
    assert [r["video_id"] for r in idx.search("QUOTE-TEXT-END")] == [video_id]
    job.refresh_scan(wait=True)
    assert job.status()["candidates"] == 0


def quoting_video(idx, out, net):
    """A 3.18.0 X video of a long post that quotes another post: the
    Description holds the cut text and the quote, and X marked it long."""
    data = copy.deepcopy(LONG["syndication"])
    data["quoted_tweet"] = copy.deepcopy(CASES["short_post"]["syndication"])
    net["syndication"][LONG["tweet_id"]] = data
    record = x_extractor.post_text_record(LONG["tweet_id"])  # FxTwitter not asked
    assert "Quoting @" in record["description"] and record["long_post"] and not record["complete"]
    video_id = video_save(idx, out, "x_video_quoting", LONG["tweet_id"], record["description"],
                          title="Quoting video")
    meta_path = Path(row_of(idx, video_id)["sidecar_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["x_text"] = x_text_repair.text_marker(record)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return video_id, record


def test_a_long_post_video_with_a_quote_is_fixed(lib, net):
    import server
    idx, out, data = lib
    video_id, cut = quoting_video(idx, out, net)
    meta_path = Path(row_of(idx, video_id)["sidecar_path"])
    assert server._x_cut_off_detail(json.loads(meta_path.read_text(encoding="utf-8")) | {
        "url": f"https://x.com/example_maker/status/{LONG['tweet_id']}"})
    job = job_for(idx, data)
    reply, item = fix_and_wait(job, video_id)
    assert item["status"] == "fixed", item
    corpus = Path(row_of(idx, video_id)["corpus_path"]).read_text(encoding="utf-8")
    assert "FULL-TEXT-END" in corpus and corpus.count("Quoting @") == 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["description"].count("Quoting @") == 1 and "FULL-TEXT-END" in meta["description"]
    assert meta["x_text_repair"]["original_description"] == cut["description"]
    assert meta["x_text"]["text_completeness"] == "complete"
    assert server._x_cut_off_detail(meta | {"url": f"https://x.com/example_maker/status/{LONG['tweet_id']}"}) is None


# ---- review fixes: never lose words, finish every write --------------------------
def test_a_longer_description_in_metadata_is_never_shortened(lib, net):
    """The person added to the description in metadata.json: the corpus gets
    the whole post, their longer description stays as they wrote it."""
    idx, out, data = lib
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"],
                       title="Studio changes")
    meta_path = Path(row_of(idx, video)["sidecar_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mine = MEDIA["full_text"] + "\n\nMY OWN NOTE: the second shelf came from a friend."
    meta["description"] = mine
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    job = job_for(idx, data)
    job.start()
    job.wait(20)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["description"] == mine and "x_text_repair" not in meta
    assert meta["x_text"]["text_completeness"] == "complete"
    assert "MEDIA-TEXT-END" in Path(row_of(idx, video)["corpus_path"]).read_text(encoding="utf-8")


def test_a_corpus_already_longer_than_the_post_is_left_alone(lib, net):
    idx, out, data = lib
    longer = MEDIA["full_text"] + " And one more line the person typed in."
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"],
                       title="Studio changes")
    corpus = Path(row_of(idx, video)["corpus_path"])
    corpus.write_text(corpus.read_text(encoding="utf-8").replace(MEDIA["syndication"]["text"], longer),
                      encoding="utf-8")
    meta_path = Path(row_of(idx, video)["sidecar_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_path.write_text(json.dumps(dict(meta, description=longer)), encoding="utf-8")
    record = x_extractor.post_text_record(MEDIA["tweet_id"], fxtwitter=True)
    outcome = x_text_repair.rewrite_video(row_of(idx, video), record, index=idx)
    assert outcome["outcome"] == "already_full"
    assert longer in corpus.read_text(encoding="utf-8")
    assert json.loads(meta_path.read_text(encoding="utf-8"))["description"] == longer


def killed_once(monkeypatch, target, name):
    """Make target.name raise SystemExit (a killed helper) on its first call."""
    real = getattr(target, name)
    calls = {"n": 0}

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit(f"helper killed in {name}")
        return real(*args, **kwargs)
    monkeypatch.setattr(target, name, wrapper)
    return calls


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_during_the_readers_fix_is_finished_on_restart(lib, net, monkeypatch):
    idx, out, data = lib
    video = video_save(idx, out, "x_video_media", MEDIA["tweet_id"], MEDIA["syndication"]["text"],
                       title="Studio changes")
    killed_once(monkeypatch, idx, "update_corpus_text")
    first = job_for(idx, data)
    first.fix_one(video)
    first.wait_fix(video, 20)
    row = row_of(idx, video)
    assert "MEDIA-TEXT-END" in Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert not idx.search("tray")  # the search text was not written yet
    entry = json.loads((data / x_text_repair.STATE_NAME).read_text(encoding="utf-8"))["items"][video]
    assert entry["status"] == "writing" and entry["journal"]["kind"] == "video"
    asked = len(net["log"])

    second = job_for(idx, data)  # a new helper process
    second.resume_if_interrupted()
    assert len(net["log"]) == asked  # finished from the journal, nothing asked again
    assert [r["video_id"] for r in idx.search("tray")] == [video]
    meta = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert meta["x_text"]["text_completeness"] == "complete"
    assert meta["x_text_repair"]["original_description"] == MEDIA["syndication"]["text"]
    assert second.item_status(video)["status"] == "fixed"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_between_a_post_file_and_its_record_is_finished_on_restart(lib, net, monkeypatch):
    idx, out, data = lib
    video_id = thread_save(idx, out, LONG["syndication"])
    killed_once(monkeypatch, idx, "update_corpus_text")
    first = job_for(idx, data)
    first.start()
    first.wait(20)
    row = row_of(idx, video_id)
    assert "FULL-TEXT-END" in Path(row["corpus_path"]).read_text(encoding="utf-8")
    sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["metadata"]["x_capture"]["posts"][-1]["text_completeness"] == "truncated"
    asked = len(net["log"])

    second = job_for(idx, data)
    assert second.resume_if_interrupted() is True
    second.wait(20)
    assert second.status()["status"] == "done"
    assert len(net["log"]) == asked
    row = row_of(idx, video_id)
    corpus = Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert corpus.count("FULL-TEXT-END") == 1 and corpus.count("from scratch. The first version") == 1
    sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["metadata"]["x_capture"]["posts"][-1]["text_completeness"] == "complete"
    assert sidecar["metadata"]["text_cut_off"] is None
    assert json.loads(row["metadata_json"])["x_capture"]["posts"][-1]["text"].endswith("FULL-TEXT-END")
    assert [r["video_id"] for r in idx.search("checker")] == [video_id]


def article_library(idx, out, net):
    case = CASES["article_only"]
    net["syndication"][case["tweet_id"]] = case["syndication"]
    net["fxtwitter"][case["tweet_id"]] = case["fxtwitter"]
    post = thread_save(idx, out, case["syndication"], handle="example_author")
    saved = []

    def persist(result):
        saved.append(result)
        return page_extractor.persist_page_yoink(idx, result, data_root=out, source_type="x_article",
                                                 subfolder="X", slug_prefix="x-article")
    return post, saved, persist


def article_rows(idx):
    with idx._lock:
        return idx._conn.execute("SELECT video_id, metadata_json FROM yoinks WHERE source_type='x_article'").fetchall()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_after_saving_the_article_is_finished_without_a_second_copy(lib, net, monkeypatch):
    idx, out, data = lib
    post, saved, persist = article_library(idx, out, net)
    killed_once(monkeypatch, x_text_repair, "finish_article")
    first = job_for(idx, data, persist_article=persist)
    first.start()
    first.wait(20)
    assert len(saved) == 1 and len(article_rows(idx)) == 1
    asked = len(net["log"])

    second = job_for(idx, data, persist_article=persist)
    second.resume_if_interrupted()
    second.wait(20)
    assert len(saved) == 1 and len(article_rows(idx)) == 1  # no second copy
    assert len(net["log"]) == asked
    article_id = article_rows(idx)[0][0]
    row = row_of(idx, post)
    sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["metadata"]["text_cut_off"]["saved_as"] == article_id
    # The index row agrees with the file.
    assert json.loads(row["metadata_json"])["text_cut_off"]["saved_as"] == article_id


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_while_saving_the_article_reuses_the_saved_copy(lib, net, monkeypatch):
    idx, out, data = lib
    post, saved, persist = article_library(idx, out, net)

    def persist_then_die(result):
        persist(result)
        raise SystemExit("helper killed right after the Article was saved")
    first = job_for(idx, data, persist_article=persist_then_die)
    first.start()
    first.wait(20)
    assert len(article_rows(idx)) == 1

    second = job_for(idx, data, persist_article=persist)
    assert second.resume_if_interrupted() is True
    second.wait(20)
    assert second.status()["status"] == "done"
    assert len(article_rows(idx)) == 1 and len(saved) == 1  # found the saved one, no second copy
    sidecar = json.loads(Path(row_of(idx, post)["sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["metadata"]["text_cut_off"]["saved_as"] == article_rows(idx)[0][0]


def test_article_post_without_a_saved_link_uses_a_status_link(lib, net):
    idx, out, data = lib
    post, saved, persist = article_library(idx, out, net)
    row = row_of(idx, post)
    sidecar_path = Path(row["sidecar_path"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar.pop("url", None)
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with idx._lock:
        idx._conn.execute("UPDATE yoinks SET metadata_json=? WHERE video_id=?", ("{}", post))
        idx._conn.commit()
    item = x_text_repair.find_candidates([row_of(idx, post)])[0]
    assert item["url"] == f"https://x.com/i/status/{CASES['article_only']['tweet_id']}"
    job = job_for(idx, data, persist_article=persist)
    job.start()
    job.wait(20)
    assert job.status()["run"]["fixed"] == 1 and len(saved) == 1


def test_listed_posts_only_ever_link_to_x(lib, net):
    """The Settings list renders these as links: a stored javascript: or
    other-site URL never reaches it."""
    idx, out, data = lib
    video_id = thread_save(idx, out, LONG["syndication"])
    for bad in ("javascript:alert(1)", "https://evil.test/status/1", "data:text/html,hi",
                f"https://x.com/a/status/{LONG['tweet_id']}?x=\"><b>"):
        with idx._lock:
            idx._conn.execute("UPDATE yoinks SET metadata_json=? WHERE video_id=?",
                              (json.dumps({"url": bad}), video_id))
            idx._conn.commit()
        job = job_for(idx, data)
        job.refresh_scan(wait=True)
        urls = [item["url"] for item in job.status()["sample"]]
        assert urls and all(x_text_repair._OPEN_URL_RE.match(u) for u in urls), urls


def test_stop_ends_the_run_and_the_next_start_is_a_new_one(lib, net):
    idx, out, data = lib
    build_library(idx, out, net)
    job = job_for(idx, data)

    def stopping_fetch(tweet_id):
        job.stop()
        return x_extractor.post_text_record(tweet_id, fxtwitter=True)
    job._fetch = stopping_fetch
    job.start()
    job.wait(20)
    state = json.loads((data / x_text_repair.STATE_NAME).read_text(encoding="utf-8"))
    first_run = state["run_id"]
    assert job.status()["status"] == "stopped" and state["finished_at"]
    assert job.resume_if_interrupted() is False  # a stopped run never restarts itself
    assert all(item["status"] != "writing" for item in state["items"].values())
    # A leftover "writing" mark with nothing written is dropped by Stop.
    with job._lock:
        state = job._load()
        state["status"] = "paused"
        state["items"]["x_deleted_since"] = {"status": "writing", "run_id": first_run}
        job._save(state)
    job.stop()
    assert "x_deleted_since" not in json.loads((data / x_text_repair.STATE_NAME).read_text(encoding="utf-8"))["items"]
    job._fetch = None
    job.start()
    job.wait(20)
    state = json.loads((data / x_text_repair.STATE_NAME).read_text(encoding="utf-8"))
    assert state["run_id"] != first_run and job.status()["status"] == "done"


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
