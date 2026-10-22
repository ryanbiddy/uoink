"""Separate offline inference smoke. Never downloads or records acceptance."""
import json
import time
from pathlib import Path

import pytest

from uoink_core import local_search as ls

SCRATCH = Path(__file__).resolve().parents[1] / "_scratch"
MANAGER = ls.ModelManager(SCRATCH)
HAS_VERIFIED_MODEL = MANAGER.acceptance() is not None and all(
    ls.verified(MANAGER.directory / name, size, sha) for name, size, sha in ls.MODEL_FILES)
pytestmark = pytest.mark.skipif(not HAS_VERIFIED_MODEL,
                                reason="Requires accepted terms and verified files under _scratch/models")


def test_real_onnx_mars_and_100_passage_timing():
    import numpy as np

    start = time.perf_counter()
    model = ls.EmbeddingGemma(MANAGER)
    load_seconds = time.perf_counter() - start
    docs = ["title: Mars | text: Iron oxide coats the surface of Mars and gives the planet its rusty red color.",
            "title: Bread | text: Knead the sourdough bread, let the dough rise, and bake it in a hot oven."]
    query = model.embed([ls.QUERY_PREFIX + "Why does Mars look rusty?"])[0]
    vectors = model.embed(docs)
    scores = vectors @ query
    assert scores[0] > scores[1]
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    # Exactly 100 non-cached, 230-word synthetic passages, excluding model load.
    passage = " ".join(("Mars iron oxide creates rusty red soil and dust across the rocky planet. " * 24).split()[:230])
    benchmark = [f"title: Mars {i} | text: {passage}" for i in range(100)]
    start = time.perf_counter()
    matrix = model.embed(benchmark)
    seconds = time.perf_counter() - start
    assert matrix.shape == (100, 768)
    result = {"load_seconds": load_seconds, "passages": 100, "words_per_passage": 230,
              "inference_seconds": seconds, "passages_per_second": 100 / seconds,
              "mars_score": float(scores[0]), "bread_score": float(scores[1]),
              "threads": ls.MAX_THREADS, "batch_size": ls.BATCH_SIZE,
              "model_revision": ls.MODEL_REVISION, "provider": "CPUExecutionProvider"}
    directory = SCRATCH / "embed"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "inference.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
