"""Inert seams for exact selected source; no real package imports or assets."""
import ast
import builtins
import copy
import math
import os
from types import SimpleNamespace


class Array:
    def __init__(self, values, *, dtype="float32", ndim=1, contiguous=True, shape=None):
        self.values = list(values)
        self.dtype, self.ndim = dtype, ndim
        self.size = len(self.values)
        self.shape = shape or (self.size,)
        self.flags = SimpleNamespace(c_contiguous=contiguous)
    def __getitem__(self, key):
        return Array(self.values[key], dtype=self.dtype, ndim=self.ndim,
                     contiguous=self.flags.c_contiguous)


def finite(value):
    def flatten(items):
        for item in items:
            if isinstance(item, list):
                yield from flatten(item)
            else:
                yield item
    return SimpleNamespace(all=lambda: all(math.isfinite(x) for x in flatten(value.values)))


NP = SimpleNamespace(ndarray=Array, dtype=lambda value: value, isfinite=finite)


def execute(raw, filename, namespace, imports=None):
    namespace = dict(namespace)
    namespace.setdefault("__name__", "inert_selected_source")
    if imports is not None:
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in imports:
                return imports[name]
            raise AssertionError("Unbriefed selected-source import: " + name)
        namespace["__builtins__"] = dict(vars(builtins), __import__=safe_import)
    exec(compile(raw, filename, "exec"), namespace)
    return namespace


def selected(raw, name, namespace, *, method=None):
    tree = ast.parse(raw)
    original = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    node = copy.deepcopy(original)
    if method is not None:
        node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method]
        assert len(node.body) == 1
    # Same annotation-only seam as the retained Pipeline qualification.
    for item in ast.walk(node):
        if isinstance(item, ast.arg):
            item.annotation = None
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            item.returns = None
    originals = [original] if method is None else [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == method]
    adapted = [node] if method is None else node.body
    for before, after in zip(originals, adapted):
        if isinstance(before, ast.FunctionDef):
            assert ast.dump(ast.Module(body=before.body, type_ignores=[]), include_attributes=False) == ast.dump(
                ast.Module(body=after.body, type_ignores=[]), include_attributes=False)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    result = dict(namespace, __name__="inert_selected_source")
    exec(compile(module, "selected-" + name, "exec"), result)
    return result[name]


class FixedVAD:
    pass


class Runtime:
    def __init__(self):
        self.events = []
        self.path = r"E:\uoink-synthetic-only\tiny\immutable-revision"
        self.vad = FixedVAD()
        self.waveform = None
        self.segmentation = None
        self.matrix = None
        self.max_audio_samples = 16
        self.active = True
        self.expected = dict(device="cpu", device_index=0, compute_type="float32", threads=4,
            language=None, task="transcribe", asr_options=None, vad_options=None,
            local_files_only=True, download_root=None, use_auth_token=None, model=None, vad_method=None)
    def assert_active(self):
        self.events.append("active")
        if not self.active:
            raise PermissionError("inactive synthetic session")
    def assert_model_binding(self, path, vad):
        self.events.append("binding")
        if path != self.path or vad is not self.vad:
            raise PermissionError("unbound synthetic model or VAD")
    def assert_load_parameters(self, **values):
        self.events.append("parameters")
        self.last_parameters = values
        if values.pop("model_path") != self.path or values.pop("vad_model") is not self.vad:
            raise PermissionError("parameter identity mismatch")
        if set(values) != set(self.expected) or any(type(values[k]) is not type(v) or values[k] != v
                                                   for k, v in self.expected.items()):
            raise PermissionError("unqualified synthetic parameters")
    def assert_waveform_binding(self, audio, *, sample_rate):
        self.events.append(("waveform", sample_rate))
        if audio is not self.waveform or sample_rate != 16000:
            raise PermissionError("unbound synthetic waveform")
    def assert_vad_model_binding(self, model):
        self.events.append("vad-model")
        if model is not self.segmentation:
            raise PermissionError("unbound synthetic segmentation")
    def get_mel_filters(self, n_mels):
        self.events.append(("filters", n_mels))
        if self.matrix is None:
            raise PermissionError("no synthetic filter asset")
        return self.matrix


def owned_namespace(files):
    return execute(files["after/whisperx/_uoink_owned.py"], "owned-source", {}, {"os": os, "numpy": NP})


def loader(files, runtime):
    owned = owned_namespace(files)
    owned["_RUNTIME"] = runtime
    calls = []
    def constructor(path, **kwargs):
        runtime.events.append("constructor")
        calls.append((path, kwargs))
        return SimpleNamespace(hf_tokenizer=object(), model=SimpleNamespace(is_multilingual=True))
    namespace = dict(owned, VoiceActivitySegmentation=FixedVAD, WhisperModel=constructor,
        Tokenizer=lambda *args, **kwargs: SimpleNamespace(**kwargs),
        TranscriptionOptions=lambda **kwargs: SimpleNamespace(**kwargs),
        FasterWhisperPipeline=lambda **kwargs: SimpleNamespace(**kwargs),
        logger=SimpleNamespace(info=lambda *args: None))
    function = selected(files["after/whisperx/asr.py"], "load_model", namespace)
    return function, owned, calls, namespace
