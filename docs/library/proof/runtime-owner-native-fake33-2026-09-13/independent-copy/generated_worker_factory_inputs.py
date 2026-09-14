"""Fixed generated factory inputs; no channel, file read or native import.

The bridge retains this object BEFORE prepare(), including partial preparation.
There is deliberately no context-manager cleanup, release or forget operation.
"""
from collections import OrderedDict
import hashlib
import math
import struct
import types

import state_bridge as bridge
import owned_cpu_tensor_port as cpu
import model_binding_registry as registry_module
import owned_factory_port as factory_module
import owned_guard as guard
import fake_torch_support as support
import fixed_schema_helpers as helpers

PATTERN = struct.pack('<12I', 0, 0x80000000, 1, 0x80000001,
    0x007fffff, 0x807fffff, 0x00800000, 0x80800000,
    0x7f7fffff, 0xff7fffff, 0x3f800000, 0xbf800000)
GENERATED_PCM = b'\0' * 16


def pattern(size):
    return (PATTERN * ((size + len(PATTERN) - 1) // len(PATTERN)))[:size]


class GeneratedFactoryInputs:
    """One private generated allocation attempt, retained through worker exit."""
    def __init__(self):
        self.attempted = self.prepared = False
        self.runtime = self.fixed = self.port = self.state_binding = None
        self.state = {}
        self.digests = []

    def prepare(self):
        if self.attempted:
            raise RuntimeError('generated_inputs_single_attempt')
        self.attempted = True
        runtime = self.runtime = support.fake_torch()
        runtime.events = []
        runtime.hooks = {}

        def act(name, *args):
            hook = runtime.hooks.get(name)
            if hook is not None:
                hook(*args)
        runtime.act = act

        class Device:
            def __init__(self, name):
                assert name == 'cpu'
                self.type = name
            def __enter__(self): return self
            def __exit__(self, *args): return False
        runtime.device = Device

        def isfinite(tensor):
            answer = all(math.isfinite(value) for value in tensor.tolist())
            return types.SimpleNamespace(all=lambda: types.SimpleNamespace(item=lambda: answer))
        runtime.isfinite = isfinite

        class FakePyanNet:
            def __init__(self, **kwargs):
                self.runtime, self.arguments, self.state = runtime, kwargs, {}
                self.build_count = self.load_count = self.state_dict_count = 0
                self.evaluated = False
                for name in factory_module._STATE_HOOKS:
                    setattr(self, name, OrderedDict())
                runtime.events.append('model_constructor')
                runtime.act('model_constructor', self)
            def modules(self): yield self
            def build(self):
                self.build_count += 1
                runtime.events.append('model_build')
                runtime.act('build_before', self)
                for key, shape in bridge.FIXED_SHAPES:
                    self.state[key] = runtime.fresh(shape)
                runtime.act('build_after', self)
            def state_dict(self):
                self.state_dict_count += 1
                runtime.act('state_dict', self)
                return dict(self.state)
            def load_state_dict(self, state, *, strict, assign):
                self.load_count += 1
                self.load_arguments = (strict, assign)
                runtime.events.append('strict_load')
                runtime.act('load_before', self, state)
                for key in state:
                    self.state[key].copy_(state[key])
                runtime.act('load_after', self, state)
                return types.SimpleNamespace(missing_keys=[], unexpected_keys=[])
            def requires_grad_(self, value):
                assert value is False
                for tensor in self.state.values():
                    tensor.requires_grad = False
                return self
            def eval(self):
                self.evaluated = True
                return self

        class FakeVoiceParent:
            def __init__(self, *, segmentation, fscore, token, **inference_kwargs):
                self.segmentation, self.runtime = segmentation, segmentation.runtime
                self.runtime.events.append('vad_parent_after_owned_guard')
                self.runtime.act('vad_constructor', self)
                self.arguments, self.fscore, self.token = dict(inference_kwargs), fscore, token
            def instantiate(self, thresholds):
                self.runtime.events.append('vad_instantiate')
                self.thresholds = dict(thresholds)
                self.runtime.act('vad_instantiate', self)

        class FakeVoiceActivitySegmentation(FakeVoiceParent):
            def __init__(self, segmentation, fscore=False, token=None, **inference_kwargs):
                if not isinstance(segmentation, FakePyanNet) or token is not None:
                    raise ValueError('An owned Model instance is required; names, paths and tokens are refused')
                guard.require_owned_runtime().assert_vad_model_binding(segmentation)
                super().__init__(segmentation=segmentation, fscore=fscore, token=token, **inference_kwargs)

        fixed = self.fixed = types.ModuleType('generated_worker_fixed_factory')
        fixed.torch, fixed.PyanNet = runtime, FakePyanNet
        fixed.Problem = types.SimpleNamespace(MULTI_LABEL_CLASSIFICATION=object())
        fixed.Resolution = types.SimpleNamespace(FRAME=object())
        fixed.Specifications = lambda **kwargs: types.SimpleNamespace(**kwargs)
        fixed.VoiceActivitySegmentation = FakeVoiceActivitySegmentation
        for helper in (helpers._fixed_shapes, helpers._check_plain_state):
            fixed.__dict__[helper.__name__] = types.FunctionType(helper.__code__, fixed.__dict__, helper.__name__)
        self.port = cpu._OwnedCPUTorchPortProposal(runtime)
        for key, shape in bridge.FIXED_SHAPES:
            tensor = self.port.allocate_owned_cpu_f32(shape)
            self.state[key] = tensor  # Retain before filling or hashing.
            tensor.storage.data[:] = pattern(math.prod(shape) * 4)
            self.digests.append((key, shape, hashlib.sha256(bytes(tensor.storage.data)).digest()))
        self.state_binding = registry_module._StateBindingProposal(
            hashlib.sha256(b'inert generated state').hexdigest(),
            hashlib.sha256(b'inert admitted profile').hexdigest(), tuple(self.digests))
        self.prepared = True
