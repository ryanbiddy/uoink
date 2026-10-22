"""Synthetic-only contract tests for the offline search benchmark."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/bench/search_benchmark.py"
spec = importlib.util.spec_from_file_location("search_benchmark", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def document(url="https://x.com/synthetic/status/1", title="Copper telescope"):
    return {"id": bench.source_id(url), "url": url, "title": title,
            "topic": "Synthetic", "text": title + "\nA synthetic telescope observes the moon.",
            "captured_at": "2026-01-01", "has_transcript": True,
            # Must remain inert metadata, even when it names a forbidden path.
            "source_path": "E:/Uoink/never-open-this.md"}


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def synthetic_corpus(path, docs=None):
    path.mkdir()
    if docs is None:
        undated = document("https://youtube.com/watch?v=synthetic", "Violet kettle")
        undated["captured_at"] = None
        docs = [document(), undated]
    queries = [{"id": f"Q{i + 1:02}", "group": bench.GROUPS[i // 10],
                "query": docs[i % len(docs)]["title"], "targets": [docs[i % len(docs)]["id"]]}
               for i in range(30)]
    (path / "documents.jsonl").write_text("".join(json.dumps(doc) + "\n" for doc in docs), encoding="utf-8")
    (path / "passages.jsonl").write_text("", encoding="utf-8")
    write_json(path / "queries.json", queries)
    write_json(path / "manifest.json", {
        "documents": len(docs), "passages": 0,
        "documents_sha256": bench.digest((path / "documents.jsonl").read_bytes()),
        "passages_sha256": bench.digest(b""),
    })
    write_json(path / "protocol.json", {
        "queries_sha256": bench.digest((path / "queries.json").read_bytes())})
    return docs, queries


@pytest.mark.parametrize("path", [
    "E:/Uoink", "e:/uoink/captures/a.md", "E:\\Uoink\\index.db",
    "E:/scratch/../Uoink/a", "\\\\?\\E:\\Uoink\\a", "E:/AI/_keys/secret",
    "somewhere/index.db", "somewhere/INDEX.DB-wal", "somewhere/index.db.backup",
])
def test_protected_paths_are_refused_on_both_platforms(path):
    with pytest.raises(ValueError, match="refusing"):
        bench.safe_path(path)


def test_environment_roots_and_explicit_live_database(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("IG_FORBIDDEN_LIVE", str(tmp_path / "renamed-live.sqlite3"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    for path in (tmp_path / "local/Uoink/capture", tmp_path / "renamed-live.sqlite3",
                 tmp_path / "xdg/Uoink/capture"):
        with pytest.raises(ValueError):
            bench.safe_path(path)
    assert bench.safe_path(tmp_path / "local/Uoink-other/a") == tmp_path / "local/Uoink-other/a"


def test_symlink_to_protected_root_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    protected = tmp_path / "local/Uoink"
    protected.mkdir(parents=True)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(protected, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks requires Windows developer mode or privilege")
    with pytest.raises(ValueError):
        bench.safe_path(alias / "capture.md")


def test_nonempty_workdir_is_preserved(tmp_path):
    marker = tmp_path / "do-not-delete.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="new or empty"):
        bench.fresh_directory(tmp_path)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_audit_guard_blocks_network_live_sqlite_and_external_writes(tmp_path):
    guard = bench.OfflineGuard(tmp_path / "work", tmp_path / "out")
    for event, args in (
        ("open", ("E:/Uoink/capture.md", "r", 0)),
        ("os.scandir", ("E:/Uoink",)),
        ("os.listdir", ("E:/AI/_keys",)),
        ("sqlite3.connect", (str(tmp_path / "other.sqlite3"),)),
        ("open", (str(tmp_path / "other.txt"), "w", os.O_WRONLY)),
        ("os.rename", (str(tmp_path / "work/a"), str(tmp_path / "outside"))),
    ):
        with pytest.raises(ValueError):
            guard(event, args)
    for event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
        with pytest.raises(RuntimeError, match="offline benchmark"):
            guard(event, ())
    guard("sqlite3.connect", (str(tmp_path / "work/benchmark.sqlite3"),))
    guard("sqlite3.connect", (":memory:",))
    guard("open", (str(tmp_path / "out/metrics.json"), "w", os.O_WRONLY))


def test_frozen_checksums_and_allowlist(tmp_path):
    corpus = tmp_path / "corpus"
    docs, queries = synthetic_corpus(corpus)
    loaded_docs, loaded_queries, _ = bench.load_corpus(corpus)
    assert loaded_docs == docs and loaded_queries == queries
    (corpus / "passages.jsonl").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        bench.load_corpus(corpus)
    other = tmp_path / "other"
    synthetic_corpus(other, [document("https://x.com.evil.example/private")])
    with pytest.raises(ValueError, match="allowlist"):
        bench.load_corpus(other)


def test_invalid_ids_and_targets_are_refused(tmp_path):
    bad = document()
    bad["id"] = "invented"
    corpus = tmp_path / "bad-id"
    synthetic_corpus(corpus, [bad])
    with pytest.raises(ValueError, match="source id"):
        bench.load_corpus(corpus)
    corpus = tmp_path / "bad-target"
    _, queries = synthetic_corpus(corpus)
    queries[0]["targets"] = ["missing"]
    write_json(corpus / "queries.json", queries)
    write_json(corpus / "protocol.json", {
        "queries_sha256": bench.digest((corpus / "queries.json").read_bytes())})
    with pytest.raises(ValueError, match="target outside"):
        bench.load_corpus(corpus)


def test_exact_url_identity_mapping_and_deduplication():
    first = document()
    second = document(first["url"] + "/", "Other")
    assert first["id"] != second["id"]
    assert bench.source_id("abc") == "ba7816bf8f01"
    rows = [{"video_id": first["id"]}, {"metadata_json": json.dumps({"url": first["url"]})},
            {"source_url": second["url"]}]
    assert bench.map_results({"results": rows}, [first, second]) == [first["id"], second["id"]]
    with pytest.raises(ValueError, match="unmapped"):
        bench.map_results([{"video_id": "unknown", "title": first["title"]}], [first])
    with pytest.raises(ValueError, match="ambiguous"):
        bench.map_results([{"video_id": first["id"], "url": second["url"]}], [first, second])


@pytest.mark.parametrize("rank", [1, 5, 6, 10, 11, 30, 31])
def test_metric_cutoffs_and_mrr(rank):
    ranking = ["other"] * (rank - 1) + ["target"]
    result = bench.rank_metrics(ranking, ["target", "also-target"])
    assert result["target_rank"] == (rank if rank <= 30 else None)
    assert result["mrr30"] == (1 / rank if rank <= 30 else 0)
    assert result["zero_results"] == 0
    for cutoff in (1, 5, 10, 30):
        assert result[f"hit{cutoff}"] == int(rank <= cutoff)
    assert bench.rank_metrics([], ["target"])["zero_results"] == 1
    assert bench.rank_metrics(["also-target", "target"], ["target", "also-target"])["target_rank"] == 1


def test_aggregate_math_counts_queries_once_and_pools_latency():
    rows = [dict(bench.rank_metrics(["target"], ["target"]), seconds=[1, 2]),
            dict(bench.rank_metrics(["other", "target"], ["target"]), seconds=[3, 4]),
            dict(bench.rank_metrics([], ["target"]), seconds=[5, 6])]
    result = bench.aggregate(rows)
    assert result["n"] == 3 and result["hit1"] == 1 and result["hit5"] == 2
    assert result["zero_results"] == 1 and result["mrr30"] == .5
    assert result["latency_samples"] == 6
    assert result["p50_seconds"] == 3.5
    assert result["p95_seconds"] == 5.75
    assert bench.percentile([7], .95) == 7
    assert bench.percentile([], .95) is None


def test_mode_detection_does_not_invent_support():
    class OldIndex:
        def search(self, query, limit=10, **kwargs):
            return [query, limit]

    index = OldIndex()
    assert bench.mode_search(index, "strict")("test") == ["test", 30]
    for mode in ("forgiving", "embedding", "hybrid"):
        assert bench.mode_search(index, mode) is None

    class LaterIndex:
        def search(self, query, limit=10, *, mode="strict"):
            if mode not in ("strict", "forgiving"):
                raise ValueError(mode)
            return [query, limit, mode]

        def search_embedding(self, query, limit=10):
            return ["embedding", query, limit]

    assert bench.mode_search(LaterIndex(), "forgiving")("test") == ["test", 30, "forgiving"]
    assert bench.mode_search(LaterIndex(), "embedding")("test") == ["embedding", "test", 30]
    assert bench.mode_search(LaterIndex(), "hybrid") is None


def test_warmup_repeats_titles_and_group_breakdown():
    doc = document()
    calls = []
    queries = [{"id": str(i), "query": group, "group": group, "targets": [doc["id"]]}
               for i, group in enumerate(bench.GROUPS)]

    def search(query):
        calls.append(query)
        return [{"video_id": doc["id"]}] if query != "paraphrase" else []

    metrics, records = bench.evaluate(search, [doc], queries, "strict", 3)
    assert len(calls) == 3 * 4 + 1  # warm-up + timed passes + exact title
    assert metrics["all"]["hit5"] == 2
    assert metrics["groups"]["paraphrase"]["zero_results"] == 1
    assert metrics["all"]["latency_samples"] == 9
    assert metrics["exact_title"] == {"passed": 1, "n": 1}
    assert len(records) == 4


def test_changing_rankings_fail_instead_of_mixing_quality_and_timings():
    doc = document()
    answers = iter([[{"video_id": doc["id"]}], []])
    with pytest.raises(RuntimeError, match="ranking changed"):
        bench.evaluate(lambda q: next(answers), [doc], [
            {"id": "Q", "query": "q", "group": "keyword", "targets": [doc["id"]]}], "strict", 1)


def test_repo_import_isolated_from_cached_modules(tmp_path, monkeypatch):
    (tmp_path / "index.py").write_text("import bench_dependency\nMARKER = bench_dependency.MARKER\n", encoding="utf-8")
    (tmp_path / "bench_dependency.py").write_text("MARKER = 'selected checkout'\n", encoding="utf-8")
    original = SimpleNamespace(MARKER="wrong checkout")
    monkeypatch.setitem(sys.modules, "index", original)
    monkeypatch.setitem(sys.modules, "bench_dependency", original)
    with bench.checkout_index(tmp_path) as selected:
        assert selected.MARKER == "selected checkout"
        assert Path(selected.__file__) == tmp_path / "index.py"
    assert sys.modules["index"] is original
    assert sys.modules["bench_dependency"] is original


def run_cli(tmp_path, *extra):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(REPO),
                           "--corpus", str(tmp_path / "corpus"),
                           "--out", str(tmp_path / "out"),
                           "--workdir", str(tmp_path / "work"), "--repeats", "2", *extra],
                          env=env, cwd=tmp_path, capture_output=True, text=True, timeout=90)


def test_cli_real_ingestion_and_skip_with_synthetic_corpus(tmp_path):
    docs, _ = synthetic_corpus(tmp_path / "corpus")
    result = run_cli(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    metrics = json.loads((tmp_path / "out/metrics.json").read_text(encoding="utf-8"))
    strict = metrics["modes"]["strict"]
    assert strict["all"]["hit1"] == 30 and strict["all"]["latency_samples"] == 60
    assert strict["exact_title"] == {"passed": 2, "n": 2}
    assert metrics["index_sha256"] == bench.digest((REPO / "index.py").read_bytes())
    # Later checkouts gain modes (3.11 adds forgiving); each is either measured or cleanly skipped.
    for mode in ("forgiving", "embedding", "hybrid"):
        skipped = metrics["modes"][mode].get("status") == "skipped"
        assert (f"{mode}: not available in this checkout" in result.stdout) == skipped
        if not skipped:
            assert metrics["modes"][mode]["all"]["latency_samples"] == 60
    assert (tmp_path / "work/benchmark.sqlite3").is_file()
    assert (tmp_path / "work/sources" / (docs[0]["id"] + ".md")).read_text(encoding="utf-8") == docs[0]["text"]
    measured = 1 + sum(metrics["modes"][m].get("status") != "skipped" for m in ("forgiving", "embedding", "hybrid"))
    assert len((tmp_path / "out/per-query.jsonl").read_text(encoding="utf-8").splitlines()) == 32 * measured
    assert "strict / constraints" in (tmp_path / "out/summary.md").read_text(encoding="utf-8")
    # A second invocation cannot reuse or replace a prior index/output.
    again = run_cli(tmp_path)
    assert again.returncode != 0 and "new or empty" in again.stderr


def test_cli_refuses_output_inside_corpus(tmp_path):
    synthetic_corpus(tmp_path / "corpus")
    result = run_cli(tmp_path, "--out", str(tmp_path / "corpus/results"))
    assert result.returncode != 0 and "overlap the frozen corpus" in result.stderr
    assert not (tmp_path / "corpus/results").exists()
