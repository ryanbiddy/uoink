"""local_embed: the bundled static embedding model, and the shelf tier it feeds.

A tiny made-up model (a word-level tokenizer and a 4-number table) stands in
for potion-base-8M, so no weights are downloaded and nothing real runs. The
same tests check that everything still works when the weights are absent.
"""
from __future__ import annotations

import hashlib
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


def pin(monkeypatch, folder):
    """Pin the made-up model's own hashes, as the build pins the real ones."""
    monkeypatch.setattr(local_embed, "PINNED_SHA256", {
        name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for name in ("model.safetensors", "tokenizer.json")}, raising=False)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv(local_embed.ENV_DIR, str(tmp_path / "no-model"))
    monkeypatch.setattr(local_embed, "_failed", {}, raising=False)
    monkeypatch.setattr(local_embed, "_verified", set(), raising=False)
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
    pin(monkeypatch, folder)
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


def test_half_precision_weights_load(model, monkeypatch):
    write_safetensors(model / "model.safetensors", np.array(list(WORDS.values())), dtype="F16")
    pin(monkeypatch, model)
    assert float(local_embed.embed(["crust"])[0][0]) > 0.99


@pytest.mark.parametrize("damage", ["header", "short", "empty"])
def test_damaged_weights_fail_cleanly(model, damage, monkeypatch):
    path = model / "model.safetensors"
    if damage == "header":
        path.write_bytes((10 ** 9).to_bytes(8, "little") + b"{}")
    elif damage == "short":
        path.write_bytes(path.read_bytes()[:-8])
    else:
        path.write_bytes(b"")
    pin(monkeypatch, model)  # past the hash check, so the reader's own checks run
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


def test_a_rebuild_embeds_only_new_saves(server_mod, model, monkeypatch):
    seen = []
    real = server_mod._static_embed
    monkeypatch.setattr(server_mod, "_static_embed", lambda texts: seen.append(len(texts)) or real(texts))
    server_mod._shelf_build_library(LIBRARY)
    server_mod._shelf_build_library(LIBRARY + [row("h4", "Hearth", "Boule crumb")])
    assert seen[-1] == 1
    assert server_mod._shelf_build_library(LIBRARY).has_vectors()


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


# ---- review fixes: the pin, the reader, the idle timer, the vector cache ------

def test_weights_that_do_not_match_the_pin_are_never_loaded(model, monkeypatch):
    monkeypatch.setattr(local_embed, "PINNED_SHA256",
                        {**local_embed.PINNED_SHA256, local_embed.WEIGHTS_FILE: "0" * 64})
    with pytest.raises(local_embed.EmbedUnavailable, match="pinned sha256"):
        local_embed.embed(["crust"])
    # Remembered for this file version: captures stop re-reading it.
    assert not local_embed.is_available()
    reads = []
    monkeypatch.setattr(local_embed, "_sha256", lambda path: reads.append(path) or "x")
    with pytest.raises(local_embed.EmbedUnavailable):
        local_embed.embed(["crust"])
    assert reads == []


def test_the_pin_is_checked_once_per_file_version(model, monkeypatch):
    calls = []
    real = local_embed._sha256
    monkeypatch.setattr(local_embed, "_sha256", lambda path: calls.append(path.name) or real(path))
    local_embed.embed(["crust"])
    local_embed.release()
    local_embed.embed(["loaf"])
    assert sorted(calls) == ["model.safetensors", "tokenizer.json"]


@pytest.mark.parametrize("header", [
    {"embeddings": {"dtype": "F32", "shape": [-4, 4], "data_offsets": [0, 64]}},
    {"embeddings": {"dtype": "F32", "shape": [4, 4], "data_offsets": [64, 0]}},
    {"embeddings": {"dtype": "F32", "shape": [1 << 20, 1 << 10], "data_offsets": [0, 1 << 32]}},
    {"embeddings": {"dtype": "F32", "shape": [4, 4], "data_offsets": [0, 1 << 40]}},
    {"embeddings": {"dtype": "F32", "shape": [4, "4"], "data_offsets": [0, 64]}},
    {"embeddings": {"dtype": "F32", "shape": [4, 4]}},
    {"embeddings": {"dtype": "I8", "shape": [4, 4], "data_offsets": [0, 16]}},
    ["not", "a", "dict"],
])
def test_crafted_headers_fail_cleanly(model, monkeypatch, header):
    raw = json.dumps(header).encode()
    (model / "model.safetensors").write_bytes(len(raw).to_bytes(8, "little") + raw + b"\0" * 64)
    pin(monkeypatch, model)
    with pytest.raises(local_embed.EmbedUnavailable):
        local_embed.embed(["crust"])
    assert not local_embed.is_available()


@pytest.mark.parametrize("damage", ["tiny", "nan", "tokenizer"])
def test_other_damage_fails_cleanly(model, monkeypatch, damage):
    if damage == "tiny":
        (model / "model.safetensors").write_bytes(b"\x01\x02")
    elif damage == "nan":
        table = np.array(list(WORDS.values()), dtype=np.float32)
        table[1][0] = np.inf
        write_safetensors(model / "model.safetensors", table)
    else:
        (model / "tokenizer.json").write_text("{not json", encoding="utf-8")
    pin(monkeypatch, model)
    with pytest.raises(local_embed.EmbedUnavailable):
        local_embed.embed(["crust"])
    assert not local_embed.is_available()


def test_a_linked_model_folder_is_ignored(model, tmp_path, monkeypatch):
    link = tmp_path / "linked"
    try:
        link.symlink_to(model, target_is_directory=True)
    except OSError:
        pytest.skip("making a symlink needs extra rights on this computer")
    monkeypatch.setenv(local_embed.ENV_DIR, str(link))
    assert local_embed.model_dir() is None


def test_idle_release_waits_only_for_what_is_left(model, monkeypatch):
    scheduled = []
    monkeypatch.setattr(local_embed, "_schedule", lambda seconds: scheduled.append(seconds))
    local_embed.embed(["crust"])
    local_embed._last_used -= 400
    used = local_embed._last_used
    local_embed._idle_check()
    assert local_embed.is_loaded()
    assert local_embed._last_used == used  # a check is not a use
    assert local_embed.IDLE_SECONDS - 401 <= scheduled[-1] <= local_embed.IDLE_SECONDS - 399


def test_release_cancels_the_timer_and_runs_the_hooks(model, monkeypatch):
    monkeypatch.setattr(local_embed, "_release_hooks", [])
    ran = []
    local_embed.on_release(lambda: ran.append(1))
    local_embed.embed(["crust"])
    timer = local_embed._timer
    assert timer is not None
    local_embed.release()
    assert local_embed._timer is None and timer.finished.is_set() and ran == [1]


def test_vector_cache_follows_the_weights_and_goes_with_the_model(server_mod, model, monkeypatch):
    server_mod._clear_static_vectors()
    server_mod._shelf_build_library(LIBRARY)
    keys = set(server_mod._static_vector_cache)
    assert keys
    local_embed.release()
    assert not server_mod._static_vector_cache
    server_mod._shelf_build_library(LIBRARY)
    # New weights in the same folder never reuse the old vectors.
    write_safetensors(model / "model.safetensors", np.array(list(WORDS.values())), dtype="F16")
    pin(monkeypatch, model)
    server_mod._shelf_build_library(LIBRARY)
    assert set(server_mod._static_vector_cache) - keys


def test_vector_cache_is_bounded(server_mod, model, monkeypatch):
    monkeypatch.setattr(server_mod, "STATIC_VECTOR_CACHE_MAX", 5)
    server_mod._clear_static_vectors()
    found = server_mod._static_cached_vectors([f"crust {'loaf ' * i}" for i in range(12)])
    assert len(found) == 12 and len(server_mod._static_vector_cache) == 5


def test_too_few_search_vectors_fall_back_to_the_static_model(server_mod, model, monkeypatch):
    monkeypatch.setattr(server_mod, "_shelf_vectors", lambda ids: {"h1": [1.0, 0.0]})
    library = server_mod._shelf_build_library(LIBRARY)
    assert (library.tier, library.has_vectors()) == ("static", True)


def test_the_search_model_hears_a_podcast_transcript(server_mod, monkeypatch):
    heard = []

    class Engine:
        def document_vector(self, title, text):
            heard.append(text)
            return [1.0, 0.0]

        def source_vectors(self, ids):
            return {i: [1.0, 0.0] for i in ids}
    monkeypatch.setattr(server_mod, "_local_search_singleton", Engine())
    library = server_mod._shelf_build_library(LIBRARY)
    monkeypatch.setattr(server_mod, "_shelf_library", lambda: library)
    server_mod._shelf_decision({"title": "Episode 12", "source_type": "podcast",
                                "transcript": "levain crumb and a long talk"}, url="https://example.com/ep/12")
    assert "levain crumb and a long talk" in heard[-1]
