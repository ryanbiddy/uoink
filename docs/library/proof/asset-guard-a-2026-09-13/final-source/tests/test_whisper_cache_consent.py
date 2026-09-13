"""Synthetic ASR cache/consent contracts; never import the runner or a model.

Derived from the reviewed product-A proposal's eleven ProductGuardContracts.
The selected runner function bodies execute only with fake runtime seams and
temporary placeholder files. No model, decoder or download code is exercised.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RUNNER_SOURCE = Path(__file__).resolve().parents[1] / "whisper_runner.py"


def blocked(*args, **kwargs):
    raise AssertionError("unexpected runtime or download call")


def runner_functions(source):
    functions = {
        "normalize_model", "_model_cache_root", "_model_repo_root",
        "_checked_model_snapshot", "_cached_model_snapshot", "is_model_downloaded",
        "_model_dir", "_prepare_model_snapshot", "transcribe_audio", "_shape_segments",
    }
    constants = {
        "MODEL_TINY", "MODEL_BASE", "MODEL_SMALL", "MODEL_MEDIUM", "MODEL_LARGE",
        "MODEL_LARGE_V3_TURBO", "_MODELS", "_MODEL_REPOSITORIES", "_ASR_CACHE_FILES",
    }
    tree = ast.parse(Path(source).read_text(encoding="utf-8-sig"))
    nodes = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in functions
    ) or (
        isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in constants for target in node.targets)
    )]
    assert functions == {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    scope = {
        "Path": Path, "re": re, "_WHISPERX_AVAILABLE": True,
        "_download_model_snapshot": blocked, "_runtime_device": lambda: "cpu",
        "_compute_type": lambda device: "int8", "_now_iso": lambda: "synthetic-time",
    }
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, str(source), "exec"), scope)
    return scope


class ProductGuardContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="uoink-asset-guard-synthetic-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.scope = runner_functions(RUNNER_SOURCE)
        self.events = []
        self.audio = self.root / "never-decoded.wav"
        self.audio.write_bytes(b"not real audio; never decoded")

    def cached(self, model="base", missing=()):
        repo = self.scope["_model_repo_root"](self.root, model)
        snapshot = repo / "snapshots" / ("a" * 40)
        snapshot.mkdir(parents=True, exist_ok=True)
        (repo / "refs").mkdir(exist_ok=True)
        (repo / "refs/main").write_text("a" * 40, encoding="ascii")
        for name in self.scope["_ASR_CACHE_FILES"]:
            if name not in missing:
                (snapshot / name).write_bytes(b"synthetic placeholder; never loaded")
        return snapshot

    def transcribe(self, **kwargs):
        def factory(path, **options):
            self.events.append(("factory", path, options))
            return SimpleNamespace(transcribe=lambda *args, **kw: {
                "language": "en", "segments": [{"start": 0, "end": 1, "text": "Synthetic"}]})
        with patch.dict(sys.modules, {"whisperx": SimpleNamespace(load_model=factory)}):
            return self.scope["transcribe_audio"](self.audio, data_root=self.root, **kwargs)

    def test_readiness_does_not_create_a_cache(self):
        self.assertFalse(self.scope["is_model_downloaded"](self.root))
        self.assertFalse((self.root / "whisper_models").exists())

    def test_arbitrary_file_does_not_authorize_download(self):
        cache = self.root / "whisper_models/base"
        cache.mkdir(parents=True)
        (cache / "unfinished.part").write_bytes(b"partial")
        self.assertFalse(self.scope["is_model_downloaded"](self.root))
        with self.assertRaises(PermissionError):
            self.transcribe()
        self.assertEqual(self.events, [])

    def test_each_missing_required_file_refuses_before_factory(self):
        for name in self.scope["_ASR_CACHE_FILES"]:
            with self.subTest(file=name):
                snapshot = self.cached()
                (snapshot / name).unlink()
                self.assertFalse(self.scope["is_model_downloaded"](self.root))
                with self.assertRaises(PermissionError):
                    self.transcribe()
                self.assertEqual(self.events, [])

    def test_empty_tokenizer_is_not_ready(self):
        (self.cached() / "tokenizer.json").write_bytes(b"")
        self.assertFalse(self.scope["is_model_downloaded"](self.root))

    def test_all_six_current_model_options_reuse_cache_without_download(self):
        self.assertEqual(set(self.scope["_MODEL_REPOSITORIES"]), set(self.scope["_MODELS"]))
        for model in self.scope["_MODELS"]:
            with self.subTest(model=model):
                expected = self.cached(model)
                self.assertTrue(self.scope["is_model_downloaded"](self.root, model))
                self.assertEqual(self.scope["_prepare_model_snapshot"](
                    self.root, model, consent_given=False), expected)

    def test_consent_resolves_then_passes_local_snapshot_to_factory(self):
        def downloader(model, cache):
            self.events.append(("download", model, cache))
            return self.cached(model)
        self.scope["_download_model_snapshot"] = downloader
        result = self.transcribe(consent_given=True)
        self.assertEqual([event[0] for event in self.events], ["download", "factory"])
        self.assertEqual(self.events[0][1], "base")
        self.assertEqual(self.events[1][1], str(self.cached()))
        self.assertTrue(self.events[1][2]["local_files_only"])
        self.assertEqual(result["model"], "base")
        self.assertFalse(result["diarization_ran"])
        self.assertEqual(result["segments"][0]["text"], "Synthetic")

    def test_bad_download_result_refuses_before_factory(self):
        def downloader(model, cache):
            self.events.append(("download", model, cache))
            return self.cached(model, missing=("tokenizer.json",))
        self.scope["_download_model_snapshot"] = downloader
        with self.assertRaisesRegex(RuntimeError, "tokenizer.json"):
            self.transcribe(consent_given=True)
        self.assertEqual([event[0] for event in self.events], ["download"])

    def test_unknown_or_path_shaped_reference_is_not_ready(self):
        snapshot = self.cached()
        reference = snapshot.parent.parent / "refs/main"
        for text in ("../outside", "a" * 39, "g" * 40, "a" * 100):
            with self.subTest(reference=text):
                reference.write_text(text, encoding="ascii")
                self.assertFalse(self.scope["is_model_downloaded"](self.root))

    def test_snapshot_change_during_device_selection_refuses_before_factory(self):
        snapshot = self.cached()
        def device():
            (snapshot / "tokenizer.json").unlink()
            return "cpu"
        self.scope["_runtime_device"] = device
        with self.assertRaisesRegex(RuntimeError, "changed before model construction"):
            self.transcribe()
        self.assertEqual(self.events, [])

    def test_resolved_blob_inside_repo_is_allowed_but_outside_file_is_not(self):
        snapshot = self.cached()
        repo = snapshot.parent.parent
        blob = repo / "blobs/synthetic-tokenizer"
        blob.parent.mkdir()
        blob.write_bytes(b"synthetic blob")
        outside = self.root / "outside-tokenizer.json"
        outside.write_bytes(b"synthetic outside")
        actual_resolve = Path.resolve
        resolved_target = blob
        def resolve(path, *args, **kwargs):
            if path == snapshot / "tokenizer.json":
                return resolved_target
            return actual_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            self.assertTrue(self.scope["is_model_downloaded"](self.root))
            resolved_target = outside
            self.assertFalse(self.scope["is_model_downloaded"](self.root))

    def test_damaged_runtime_does_not_start_a_consented_download(self):
        self.scope["_WHISPERX_AVAILABLE"] = False
        with self.assertRaisesRegex(RuntimeError, "runtime is broken"):
            self.transcribe(consent_given=True)
        self.assertEqual(self.events, [])
