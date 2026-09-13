"""Stdlib-only scoped fake tensor, loader, model and class scaffolding."""
import ast
from collections import UserDict
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import types

events, loaders, mel_calls = [], [], []
def reset():
    events.clear()
    loaders.clear()
    mel_calls.clear()

class Device:
    def __init__(self, value):
        self.name = str(value)
        self.type = self.name.split(':')[0]
    def __repr__(self): return self.name
    def __eq__(self, other): return isinstance(other, Device) and self.name == other.name

def shape(value):
    return (len(value),) + (shape(value[0]) if value and isinstance(value[0], list) else ())
class Tensor:
    def __init__(self, values, device=None):
        self.values = copy.deepcopy(values)
        self.device = device or Device('cpu')
        self.shape = shape(self.values)
    def __getitem__(self, index):
        value = self.values[index]
        return Tensor(value if isinstance(value, list) else [value], self.device)
    def unsqueeze(self, axis):
        if axis != 0: raise AssertionError('Only leading-axis fake expansion is in scope')
        return Tensor([self.values], self.device)
    def to(self, device):
        events.append(('to', self.device.name, device.name))
        return Tensor(self.values, device)
class Array:
    def __init__(self, values): self.values, self.shape = copy.deepcopy(values), shape(values)
    def __getitem__(self, index):
        value = self.values[index]
        return Array(value) if isinstance(value, list) else value
class Audio:
    def __init__(self, identity, length=10): self.identity, self.shape = identity, (length,)
class ModelOutput(dict):
    def to_tuple(self): return tuple(self.values())
class Dataset: pass
class IterableDataset: pass
class KeyDataset: pass
class ScikitCompat: pass
class PushToHubMixin: pass
class ChunkPipeline: pass
class Chat:
    def __init__(self, *args): raise AssertionError('Chat input is outside these contracts')
def is_valid_message(value):
    if isinstance(value, dict) and ('role' in value or 'content' in value):
        raise AssertionError('Chat classification is outside the non-chat audio scope')
    return False

@contextmanager
def no_grad():
    events.append(('no_grad', 'enter'))
    try: yield
    finally: events.append(('no_grad', 'exit'))
@contextmanager
def device_context(device):
    events.append(('device', device.name, 'enter'))
    try: yield
    finally: events.append(('device', device.name, 'exit'))

class DataLoader:
    def __init__(self, dataset, *, num_workers, batch_size, collate_fn):
        if not isinstance(batch_size, int) or batch_size < 1:
            raise AssertionError('This loader seam covers normalized positive batching only')
        self.dataset, self.num_workers, self.batch_size, self.collate_fn = dataset, num_workers, batch_size, collate_fn
        self.batch_lengths = []
        loaders.append(self)
    def __iter__(self):
        batch = []
        for item in self.dataset:
            batch.append(item)
            if len(batch) == self.batch_size:
                self.batch_lengths.append(len(batch))
                yield self.collate_fn(batch)
                batch = []
        if batch:
            self.batch_lengths.append(len(batch))
            yield self.collate_fn(batch)
    def __len__(self): return (len(self.dataset) + self.batch_size - 1) // self.batch_size

torch = types.SimpleNamespace(device=Device, Tensor=Tensor, stack=lambda values: Tensor([value.values for value in values]),
    no_grad=no_grad, cuda=types.SimpleNamespace(device=device_context),
    utils=types.SimpleNamespace(data=types.SimpleNamespace(DataLoader=DataLoader)))
np = types.SimpleNamespace(ndarray=Array, expand_dims=lambda value, axis: Array([value.values]) if axis == 0 else (_ for _ in ()).throw(AssertionError('Axis outside scope')))
def mel(audio, *, n_mels, padding):
    mel_calls.append({'identity': audio.identity, 'n_mels': n_mels, 'padding': padding})
    return Tensor([[audio.identity]])
def first_scalar(value):
    while isinstance(value, list): value = value[0]
    return value
class Model:
    def __init__(self, feature_size=80):
        self.feat_kwargs = {} if feature_size is None else {'feature_size': feature_size}
        self.calls = []
        self.error = None
    def generate_segment_batched(self, features, tokenizer, options):
        self.calls.append({'features': features, 'tokenizer': tokenizer, 'options': options})
        if self.error is not None: raise self.error
        identities = [first_scalar(value) for value in features.values]
        return {'text': ['item' + str(value) for value in identities], 'avg_logprob': [-0.5] * len(identities)}

def load_selected(directory):
    binding = json.loads((directory / 'SOURCE-BINDINGS.json').read_text(encoding='utf-8'))
    trees = {}
    for row in binding['bindings']:
        raw = (directory / 'inputs' / row['file']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        trees[row['file']] = ast.parse(raw)
    namespace = {'__name__': 'selected_pipeline_contract_code', 'torch': torch, 'np': np, 'types': types,
        'os': os, 'contextmanager': contextmanager, 'UserDict': UserDict, 'ModelOutput': ModelOutput,
        'Dataset': Dataset, 'IterableDataset': IterableDataset, 'KeyDataset': KeyDataset,
        '_ScikitCompat': ScikitCompat, 'PushToHubMixin': PushToHubMixin, 'ChunkPipeline': ChunkPipeline,
        'Chat': Chat, 'is_valid_message': is_valid_message, 'is_torch_available': lambda: True,
        'logger': types.SimpleNamespace(warning=lambda *args: None, warning_once=lambda *args: None),
        'log_mel_spectrogram': mel, 'N_SAMPLES': 480000}
    def clean(node):
        node = copy.deepcopy(node)
        for sub in ast.walk(node):
            if isinstance(sub, ast.arg): sub.annotation = None
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)): sub.returns = None
        return node
    mapping = []
    for filename, class_name, names in [
        ('base.py.txt', 'Pipeline', ['__init__', 'device_placement', '_ensure_tensor_on_device', 'get_inference_context', 'forward', '__call__', 'run_single']),
        ('pt_utils.py.txt', 'PipelineIterator', None),
        ('asr.py.txt', 'FasterWhisperPipeline', ['__init__', '_sanitize_parameters', 'preprocess', '_forward', 'postprocess', 'get_iterator'])]:
        parent = next(node for node in trees[filename].body if isinstance(node, ast.ClassDef) and node.name == class_name)
        methods = [node for node in parent.body if isinstance(node, ast.FunctionDef) and (names is None or node.name in names)]
        selected = ast.ClassDef(name=class_name, bases=copy.deepcopy(parent.bases), keywords=[], body=[clean(node) for node in methods], decorator_list=[], type_params=[])
        for before, after in zip(methods, selected.body):
            # Bodies remain exact; only signatures' annotations differ.
            assert ast.dump(ast.Module(body=before.body, type_ignores=[]), include_attributes=False) == ast.dump(ast.Module(body=after.body, type_ignores=[]), include_attributes=False)
            mapping.append((class_name, before.name))
        module = ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))
        exec(compile(module, str(directory / 'inputs' / filename), 'exec'), namespace)
    reform = next(node for node in trees['base.py.txt'].body if isinstance(node, ast.FunctionDef) and node.name == '_reform_generator')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[clean(reform)], type_ignores=[])), str(directory / 'inputs/base.py.txt'), 'exec'), namespace)
    namespace['selected_methods'] = mapping
    return namespace
