"""local_embed: the bundled static embedding model, and the shelf tier it feeds.

A tiny made-up model (a word-level tokenizer and a 4-number table) stands in
for potion-base-8M, so no weights are downloaded and nothing real runs. The
same tests check that everything still works when the weights are absent.
"""
from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy")
tokenizers = pytest.importorskip("tokenizers")

import local_embed  # noqa: E402
import shelf_router as sr  # noqa: E402

# Bread words point one way, wood words another. "the" is nearly nothing.
WORDS = {
    "[UNK]": [9.0, 9.0, 9.0, 9.0],
    "crust": [1.0, 0.0, 0.0, 0.1], "loaf": [0.9, 0.1, 0.0, 0.1], "levain": [1.0, 0.05, 0.0, 0.0],
    "boule": [0.95, 0.0, 0.05, 0.0], "crumb": [1.0, 0.0, 0.1, 0.0], "hydration": [0.9, 0.0, 0.0, 0.2],
    "chisel": [0.0, 1.0, 0.0, 0.1], "mortise": [0.1, 0.9, 0.0, 0.0], "tenon": [0.0, 1.0, 0.1, 0.0],
    "walnut": [0.0, 0.95, 0.0, 0.1], "rasp": [0.05, 1.0, 0.0, 0.0], "spokeshave": [0.0, 0.9, 0.1, 0.0],
    "the": [0.01, 0.01, 0.01, 0.01], "hearth": [1.0, 0.0, 0.0, 0.0], "joinery": [0.0, 1.0, 0.0, 0.0],
}


def write_safetensors(path, matrix, dtype="F32"):
    data = matrix.astype("<f4" if dtype == "F32" else "<f2").tobytes()
    header = json.dumps({"__metadata__": {"format": "pt"},
                         "embeddings": {"dtype": dtype, "shape": list(matrix.shape),
                                        "data_offsets": [0, len(data)]}}).encode()
    header += b" " * (-len(header) % 8)
    path.write_bytes(len(header).to_bytes(8, "little") + header + data)


def make_model(folder):
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers
    folder.mkdir(parents=True, exist_ok=True)
    vocab = {word: i for i, word in enumerate(WORDS)}
    tokenizer = Tokenizer(models.WordLevel(vocab=vocab, unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.Lowercase()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.save(str(folder / "tokenizer.json"))
    write_safetensors(folder / "model.safetensors", np.array(list(WORDS.values()), dtype=np.float32))
    return folder


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv(local_embed.ENV_DIR, str(tmp_path / "no-model"))
    local_embed.release()
    yield
    local_embed.release()
    if local_embed._timer is not None:
        local_embed._timer.cancel()
        local_embed._timer = None


@pytest.fixture
def model(tmp_path, monkeypatch):
    folder = make_model(tmp_path / "potion")
    monkeypatch.setenv(local_embed.ENV_DIR, str(folder))
    return folder


# ---- the module ------------------------------------------------------------

def test_absent_weights_mean_unavailable_and_a_clear_error():
    assert local_embed.is_available() is False
    assert local_embed.model_dir() is None
    with pytest.raises(local_embed.EmbedUnavailable):
        local_embed.embed(["anything"])
    assert local_embed.status() == {"model": "potion-base-8m", "available": False, "loaded": False}


def test_embed_averages_word_rows_into_unit_vectors(model):
    assert local_embed.is_available()
    assert not local_embed.is_loaded()  # lazy: nothing loads until the first call
    out = local_embed.embed(["crust loaf", "levain boule", "chisel mortise", "", "zzz qqq"])
    assert out.shape == (5, 4) and out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out[:3], axis=1), 1.0, atol=1e-5)
    assert float(out[0] @ out[1]) > 0.95
    assert float(out[0] @ out[2]) < 0.2
    assert not out[3].any() and not out[4].any()  # no known words: a row of zeros
    assert local_embed.is_loaded() and local_embed.dimension() == 4


def test_unknown_word_pieces_are_dropped_not_averaged(model):
    plain, padded = local_embed.embed(["crumb", "crumb zzz yyy xxx"])
    assert np.allclose(plain, padded, atol=1e-6)


def test_model_is_released_when_idle_and_loads_again(model):
    local_embed.embed(["crust"])
    assert local_embed.is_loaded()
    local_embed._last_used -= local_embed.IDLE_SECONDS + 1
    local_embed._idle_check()
    assert not local_embed.is_loaded()
    assert local_embed.embed(["crust"]).shape == (1, 4)
    assert local_embed.is_loaded()


def test_half_precision_weights_load(model):
    write_safetensors(model / "model.safetensors", np.array(list(WORDS.values())), dtype="F16")
    assert float(local_embed.embed(["crust"])[0][0]) > 0.99


@pytest.mark.parametrize("damage", ["header", "short", "empty"])
def test_damaged_weights_fail_cleanly(model, damage):
    path = model / "model.safetensors"
    if damage == "header":
        path.write_bytes((10 ** 9).to_bytes(8, "little") + b"{}")
    elif damage == "short":
        path.write_bytes(path.read_bytes()[:-8])
    else:
        path.write_bytes(b"")
    if damage == "empty":
        assert not local_embed.is_available()
    with pytest.raises(local_embed.EmbedUnavailable):
        local_embed.embed(["crust"])


# ---- the shelf tier ----------------------------------------------------------

def row(vid, topic, title, text=""):
    return {"video_id": vid, "topic": topic, "title": title, "text": text, "author": "",
            "tags": [], "source_type": "x_thread", "duration_seconds": None}


LIBRARY = [
    row("h1", "Hearth", "Crust and crumb", "hydration crust"),
    row("h2", "Hearth", "Loaf crust", "the crumb"),
    row("h3", "Hearth", "Levain loaf", "crust hydration"),
    row("j1", "Joinery", "Chisel mortise", "tenon walnut"),
    row("j2", "Joinery", "Tenon walnut", "the chisel"),
    row("j3", "Joinery", "Mortise rasp", "walnut chisel"),
]


@pytest.fixture
def server_mod(monkeypatch, tmp_path):
    import server
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_local_search_singleton", None)
    return server


def _route_with(server, library, monkeypatch, title):
    monkeypatch.setattr(server, "_shelf_library", lambda: library)
    return server._shelf_decision({"title": title, "description": ""}, url="https://example.com/p/1",
                                  source_type="x_thread")


def test_static_tier_shelves_by_meaning_when_words_differ(server_mod, model, monkeypatch):
    library = server_mod._shelf_build_library(LIBRARY)
    assert (library.tier, library.has_vectors()) == ("static", True)
    decision = _route_with(server_mod, library, monkeypatch, "Boule")
    assert (decision.shelf, decision.source) == ("Hearth", "embedding")
    assert _route_with(server_mod, library, monkeypatch, "Spokeshave").shelf == "Joinery"
    # Nothing it knows: stays put.
    assert _route_with(server_mod, library, monkeypatch, "Zzz qqq").shelf == "Uncategorized"


def test_without_the_weights_the_same_saves_stay_on_uncategorized(server_mod, monkeypatch):
    assert not local_embed.is_available()
    library = server_mod._shelf_build_library(LIBRARY)
    assert not library.has_vectors()
    assert _route_with(server_mod, library, monkeypatch, "Boule").shelf == "Uncategorized"
    assert _route_with(server_mod, library, monkeypatch, "Spokeshave").shelf == "Uncategorized"


def test_tidy_uses_the_static_tier_too(server_mod, model):
    library = server_mod._shelf_build_library(LIBRARY)
    candidates = [row("u1", "Uncategorized", "Boule"), row("u2", "Uncategorized", "Spokeshave"),
                  row("u3", "Uncategorized", "Zzz")]
    found = server_mod._static_query_vectors([sr._doc_text(c) for c in candidates])
    vectors = {c["video_id"]: v for c, v in zip(candidates, found) if v is not None}
    assert set(vectors) == {"u1", "u2"}
    result = sr.propose(candidates, topics={"topics": []}, library=library, vectors=vectors)
    placed = {item["video_id"]: g["shelf"] for g in result["groups"] for item in g["items"]}
    assert placed == {"u1": "Hearth", "u2": "Joinery"}
    assert result["stays"] == 1


def test_gemma_vectors_win_over_the_static_model(server_mod, model, monkeypatch):
    monkeypatch.setattr(server_mod, "_shelf_vectors",
                        lambda ids: {i: [1.0, 0.0] for i in ids})
    assert server_mod._shelf_build_library(LIBRARY).tier == "gemma"


def test_a_shelf_known_only_by_name_needs_a_closer_match():
    names = {"Hearth": [1.0, 0.0, 0.0]}
    by_name = sr.Library([], names=names, tier="static")
    by_items = sr.Library([row(f"h{i}", "Hearth", f"x{i}") for i in range(3)],
                          vectors={f"h{i}": [1.0, 0.0, 0.0] for i in range(3)}, tier="static")
    near = [0.58, 0.8146, 0.0]  # cosine 0.58: above the strong bar, below it plus the name-only lift
    assert sr.route({"title": "x"}, topics={}, library=by_items, vector=near).shelf == "Hearth"
    assert sr.route({"title": "x"}, topics={}, library=by_name, vector=near).shelf == "Uncategorized"
    assert sr.route({"title": "x"}, topics={}, library=by_name, vector=[1.0, 0.0, 0.0]).shelf == "Hearth"


def test_meaning_text_leaves_out_links_handles_and_the_author():
    sig = sr.signals_from_metadata({"title": "Crust notes", "description": "see https://example.com/x @someone",
                                    "channel": "Made Up Bakery"}, transcript="levain " * 400)
    text = sr.meaning_text(sig)
    assert "example.com" not in text and "@someone" not in text and "Bakery" not in text
    assert text.startswith("Crust notes") and text.count("levain") == 300


def test_shelf_names_carry_topic_words():
    cfg = {"fallback": "Uncategorized",
           "topics": [{"name": "Cooking", "keywords": ["recipe", "kitchen"]}]}
    names = sr.shelf_name_texts(["Hearth", "Uncategorized", "Clips"], cfg)
    assert names == {"Hearth": "Hearth", "Cooking": "Cooking: recipe, kitchen"}
