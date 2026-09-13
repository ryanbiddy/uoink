"""New cases use injected Q/B/V/FILES/RECIPE; no models or package imports."""
import ast
import copy
import hashlib
import io
from types import SimpleNamespace
import unittest


class BuilderContracts(unittest.TestCase):
    def test_exact_deterministic_bytes_and_independent_verifier(self):
        first = B["build_bytes"](RECIPE, FILES)
        second = B["build_bytes"](RECIPE, FILES)
        self.assertEqual(first, second)
        receipt = V["verify_bytes"](first, RECIPE, FILES)
        self.assertEqual((receipt["members"], receipt["record_rows"]), (22, 22))
        self.assertTrue(receipt["all_payloads_verified"] and receipt["complete_byte_layout_verified"])
    def test_recipe_mutation_refused(self):
        with self.assertRaises(ValueError): B["build_bytes"](RECIPE + b" ", FILES)
    def test_missing_extra_and_changed_payloads_refused(self):
        name = "after/whisperx/asr.py"
        missing, extra, changed = dict(FILES), dict(FILES), dict(FILES)
        missing.pop(name)
        extra["after/whisperx/assets/model.bin"] = b"generated placeholder"
        changed[name] += b"\n"
        for invalid in (missing, extra, changed):
            with self.assertRaises(ValueError): B["build_bytes"](RECIPE, invalid)
    def test_wrong_types_and_metadata_inputs_refused(self):
        for name, raw in (("after/pyproject.toml", b"[project]\n"),
                          ("after/README-UOINK.md", b"changed"),
                          ("recipe-inputs/METADATA", bytearray(FILES["recipe-inputs/METADATA"]))):
            changed = dict(FILES, **{name: raw})
            with self.assertRaises(ValueError): B["build_bytes"](RECIPE, changed)
    def test_verifier_rejects_changed_truncated_prefixed_and_trailing_bytes(self):
        wheel = B["build_bytes"](RECIPE, FILES)
        changed = bytearray(wheel)
        changed[60] ^= 1
        for invalid in (bytes(changed), wheel[:-1], b"prefix" + wheel, wheel + b"tail"):
            with self.assertRaises(ValueError): V["verify_bytes"](invalid, RECIPE, FILES)
    def test_verifier_rejects_source_or_recipe_substitution(self):
        wheel = B["build_bytes"](RECIPE, FILES)
        changed = dict(FILES)
        changed["after/LICENSE"] += b"\n"
        with self.assertRaises(ValueError): V["verify_bytes"](wheel, RECIPE, changed)
        with self.assertRaises(ValueError): V["verify_bytes"](wheel, RECIPE + b" ", FILES)
    def test_fresh_publication_refuses_overwrite(self):
        path = GENERATED / "owned-text-only.txt"
        B["write_new"](path, b"generated text")
        with self.assertRaises(FileExistsError): B["write_new"](path, b"replacement")
        self.assertEqual(path.read_bytes(), b"generated text")


class LoaderContracts(unittest.TestCase):
    def setUp(self):
        self.runtime = Q.Runtime()
        self.load, self.owned, self.calls, _ = Q.loader(FILES, self.runtime)
        self.kwargs = dict(whisper_arch=self.runtime.path, device="cpu", compute_type="float32", vad_model=self.runtime.vad)
    def test_closed_and_inactive_runtime_precede_constructor(self):
        self.owned["_RUNTIME"] = None
        with self.assertRaises(RuntimeError): self.load(**self.kwargs)
        self.owned["_RUNTIME"] = self.runtime
        self.runtime.active = False
        with self.assertRaises(PermissionError): self.load(**self.kwargs)
        self.assertEqual(self.calls, [])
    def test_accepted_parameters_forwarded_after_binding(self):
        result = self.load(**self.kwargs)
        self.assertEqual(self.runtime.events[-2:], ["parameters", "constructor"])
        self.assertEqual(result.model_path, self.runtime.path)
        self.assertIs(result.vad, self.runtime.vad)
        self.assertEqual(self.calls, [(self.runtime.path, dict(device="cpu", device_index=0, compute_type="float32",
            download_root=None, local_files_only=True, cpu_threads=4, use_auth_token=None))])
    def test_all_runtime_parameter_refusals_precede_constructor(self):
        for override in (dict(device="cuda"), dict(device_index=1), dict(device_index=True),
                         dict(compute_type="default"), dict(compute_type="int8"), dict(threads=8),
                         dict(task="translate"), dict(language="fr"), dict(asr_options={"beam_size": 1}),
                         dict(vad_options={"vad_onset": .7})):
            with self.assertRaises(PermissionError): self.load(**dict(self.kwargs, **override))
        self.assertEqual(self.calls, [])
    def test_changed_accepted_options_are_forwarded_without_replacement(self):
        options = {"beam_size": 3, "hotwords": "owned"}
        self.runtime.expected["asr_options"] = options
        result = self.load(**dict(self.kwargs, asr_options=options))
        self.assertIs(self.runtime.last_parameters["asr_options"], options)
        self.assertEqual((result.options.beam_size, result.options.hotwords), (3, "owned"))
        self.assertEqual(options, {"beam_size": 3, "hotwords": "owned"})
    def test_download_credentials_bypass_and_selectors_refused(self):
        for override in (dict(local_files_only=False), dict(local_files_only=1), dict(download_root="cache"),
                         dict(use_auth_token="synthetic-token"), dict(model=object()), dict(vad_method="pyannote"),
                         dict(vad_method="silero")):
            with self.assertRaises(ValueError): self.load(**dict(self.kwargs, **override))
        self.assertEqual(self.calls, [])
    def test_names_relative_and_unbound_absolute_paths_refused(self):
        for path in ("tiny", "relative/path", None, r"E:\uoink-synthetic-only\other"):
            with self.assertRaises((ValueError, PermissionError)):
                self.load(**dict(self.kwargs, whisper_arch=path))
        self.assertEqual(self.calls, [])
    def test_missing_wrong_type_and_subclass_vad_refused(self):
        class Subclass(Q.FixedVAD): pass
        for vad in (None, object(), Subclass()):
            self.runtime.vad = vad
            with self.assertRaises(ValueError): self.load(**dict(self.kwargs, vad_model=vad))
        self.assertEqual(self.calls, [])
    def test_constructor_exception_has_no_fallback(self):
        problem = RuntimeError("inert constructor failure")
        def fail(*args, **kwargs):
            self.calls.append("failure")
            raise problem
        self.load.__globals__["WhisperModel"] = fail
        with self.assertRaises(RuntimeError) as caught: self.load(**self.kwargs)
        self.assertIs(caught.exception, problem)
        self.assertEqual(self.calls, ["failure"])


class ClosedEntryContracts(unittest.TestCase):
    def test_public_load_refuses_before_lazy_import(self):
        owned = Q.owned_namespace(FILES)
        attempts = []
        imports = {"importlib": SimpleNamespace(import_module=lambda name: attempts.append(name)),
                   "whisperx._uoink_owned": SimpleNamespace(**owned)}
        namespace = Q.execute(FILES["after/whisperx/__init__.py"], "public-init", {}, imports)
        with self.assertRaises(RuntimeError): namespace["load_model"]("tiny", "cpu")
        self.assertEqual(attempts, [])
    def test_public_optional_calls_refuse_without_lazy_import(self):
        attempts = []
        owned = Q.owned_namespace(FILES)
        imports = {"importlib": SimpleNamespace(import_module=lambda name: attempts.append(name)),
                   "whisperx._uoink_owned": SimpleNamespace(**owned)}
        namespace = Q.execute(FILES["after/whisperx/__init__.py"], "public-init", {}, imports)
        for name in ("load_align_model", "align", "load_audio", "assign_word_speakers"):
            with self.assertRaises(NotImplementedError): namespace[name]()
        self.assertEqual(attempts, [])
    def test_direct_guarded_modules_refuse_before_heavy_import(self):
        owned = Q.owned_namespace(FILES)
        imports = {"os": Q.os, "whisperx._uoink_owned": SimpleNamespace(**owned)}
        for name in ("asr.py", "audio.py", "vads/pyannote.py"):
            with self.assertRaises(RuntimeError):
                Q.execute(FILES["after/whisperx/" + name], name, {}, imports)
    def test_disabled_modules_refuse_before_any_import(self):
        for name in ("alignment.py", "diarize.py", "vads/silero.py", "__main__.py", "transcribe.py"):
            with self.assertRaises(NotImplementedError):
                Q.execute(FILES["after/whisperx/" + name], name, {}, {})
    def test_legacy_loaders_refuse_without_asset_operations(self):
        load = Q.selected(FILES["after/whisperx/vads/pyannote.py"], "load_vad_model", {})
        with self.assertRaises(NotImplementedError): load("cpu")
        audio = Q.selected(FILES["after/whisperx/audio.py"], "load_audio", {"SAMPLE_RATE": 16000})
        with self.assertRaises(NotImplementedError): audio("synthetic-do-not-open.wav")


class WaveformContracts(unittest.TestCase):
    def setUp(self):
        self.owned = Q.owned_namespace(FILES)
        self.runtime = Q.Runtime()
        self.owned["_RUNTIME"] = self.runtime
        self.validate = self.owned["validate_waveform"]
    def test_owned_waveform_preserves_identity_and_sample_rate_binding(self):
        audio = Q.Array([0., .25, -.5])
        self.runtime.waveform = audio
        self.assertIs(self.validate(audio, owned_input=True), audio)
        self.assertEqual(self.runtime.events[-1], ("waveform", 16000))
    def test_finite_shape_does_not_replace_owned_decoder_binding(self):
        with self.assertRaises(PermissionError): self.validate(Q.Array([0.]), owned_input=True)
    def test_array_type_shape_endian_and_contiguity_refusals(self):
        class Subclass(Q.Array): pass
        for value in ("file.wav", [0.], Subclass([0.]), Q.Array([0.], dtype="float64"),
                      Q.Array([0.], dtype=">f4"), Q.Array([0.], ndim=2), Q.Array([0.], contiguous=False)):
            with self.assertRaises(ValueError): self.validate(value)
    def test_empty_oversized_and_nonfinite_refusals(self):
        for value in (Q.Array([]), Q.Array([0.] * 17), Q.Array([float("nan")]),
                      Q.Array([float("inf")]), Q.Array([-float("inf")])):
            with self.assertRaises(ValueError): self.validate(value)
    def test_qualified_bound_required(self):
        for bound in (None, 0, -1, True, 1.0):
            self.runtime.max_audio_samples = bound
            with self.assertRaises(RuntimeError): self.validate(Q.Array([0.]))
    def test_filter_shapes_and_finiteness_before_fake_tensor_creation(self):
        calls = []
        namespace = dict(self.owned, np=Q.NP, N_FFT=400,
            torch=SimpleNamespace(from_numpy=lambda array: SimpleNamespace(to=lambda device: calls.append((array, device)))))
        load = Q.selected(FILES["after/whisperx/audio.py"], "mel_filters", namespace)
        for n in (80, 128):
            self.runtime.matrix = Q.Array([0.], shape=(n, 201))
            load("cpu", n)
            self.assertIs(calls[-1][0], self.runtime.matrix)
        count = len(calls)
        for array in (None, Q.Array([0.], shape=(80, 200)), Q.Array([0.], dtype="float64", shape=(80, 201)),
                      Q.Array([float("nan")], shape=(80, 201))):
            self.runtime.matrix = array
            with self.assertRaises((ValueError, PermissionError)): load("cpu", 80)
        self.assertEqual(len(calls), count)
    def test_vad_instance_and_owner_binding_before_fake_parent(self):
        calls = []
        class Model: pass
        class Parent:
            def __init__(self, **kwargs): calls.append(kwargs)
        namespace = dict(self.owned, Model=Model, VoiceActivityDetection=Parent)
        VAD = Q.selected(FILES["after/whisperx/vads/pyannote.py"], "VoiceActivitySegmentation", namespace, method="__init__")
        for value in (None, "repo/model", {}, object()):
            with self.assertRaises(ValueError): VAD(value)
        with self.assertRaises(PermissionError): VAD(Model())
        self.assertEqual(calls, [])
        model = Model()
        self.runtime.segmentation = model
        VAD(model, device="cpu")
        self.assertIs(calls[0]["segmentation"], model)
        with self.assertRaises(ValueError): VAD(model, token="synthetic-token")
        self.assertEqual(len(calls), 1)
