import index
import server
from uoink_core.local_search import IndexSources


def test_uncategorized_facet_matches_every_library_filter(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        for n, topic in enumerate((None, "", "Uncategorized", "Science", "   ", "\t\u2003")):
            idx.upsert_yoink(dict(video_id=str(n), slug=str(n), topic=topic, title="Note",
                                  yoinked_at="2026-01-02", corpus_path="", sidecar_path=""))
        assert idx.corpus_facets()["topic"][0] == {"value": "Uncategorized", "count": 5}
        assert idx.search_yoinks_for_memory(topic="Uncategorized")["total"] == 5
        assert len(idx.query_by_facets(topic="Uncategorized")) == 5
        assert server._library_search(idx, q="", kind=None, filters={"topic": "Uncategorized"},
                                      sort="title", limit=10, offset=0)["total"] == 5
        assert len(IndexSources(idx).snapshot(filters={"topic": "Uncategorized"})) == 5
