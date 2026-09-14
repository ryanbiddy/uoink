"""Adapted retained inert factory fixture; actual factory method, no native model."""
from collections import OrderedDict
from contextlib import contextmanager
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
from worker_runtime_owner import _WorkerRuntimeOwnerProposal as Registry

Factory = factory_module._OwnedFactoryPortProposal
Binding = registry_module._StateBindingProposal
PATTERN = struct.pack('<12I', 0, 0x80000000, 1, 0x80000001,
    0x007fffff, 0x807fffff, 0x00800000, 0x80800000,
    0x7f7fffff, 0xff7fffff, 0x3f800000, 0xbf800000)
Model = object
require_owned_runtime = guard.require_owned_runtime


def pattern(size):
    return (PATTERN * ((size + len(PATTERN) - 1) // len(PATTERN)))[:size]


class FakeVoiceParent:
    def __init__(self, *, segmentation, fscore, token, **inference_kwargs):
        self.segmentation = segmentation
        self.runtime = segmentation.runtime
        self.runtime.events.append('vad_parent_after_owned_guard')
        self.runtime.act('vad_constructor', self)
        self.arguments = dict(inference_kwargs)
        self.fscore = fscore
        self.token = token

    def instantiate(self, thresholds):
        self.runtime.events.append('vad_instantiate')
        self.thresholds = dict(thresholds)
        self.runtime.act('vad_instantiate', self)


class FakeVoiceActivitySegmentation(FakeVoiceParent):
    def __init__(self, segmentation, fscore=False, token=None, **inference_kwargs):
        if not isinstance(segmentation, Model) or token is not None:
            raise ValueError("An owned Model instance is required; names, paths and tokens are refused")
        require_owned_runtime().assert_vad_model_binding(segmentation)
        super().__init__(segmentation=segmentation, fscore=fscore, token=token, **inference_kwargs)


@contextmanager
def fixture():
    global Model
    runtime = support.fake_torch()
    runtime.events = []
    runtime.hooks = {}
    def act(name, *args):
        hook = runtime.hooks.get(name)
        if hook is not None: hook(*args)
    runtime.act = act

    class Device:
        def __init__(self, name): assert name == 'cpu'; self.type = name
        def __enter__(self): return self
        def __exit__(self, *args): return False
    runtime.device = Device
    def isfinite(tensor):
        values = tensor.tolist()
        answer = all(math.isfinite(value) for value in values)
        return types.SimpleNamespace(all=lambda: types.SimpleNamespace(item=lambda: answer))
    runtime.isfinite = isfinite

    class FakePyanNet:
        def __init__(self, **kwargs):
            self.runtime = runtime
            self.arguments = kwargs
            self.state = {}
            self.build_count = self.load_count = self.state_dict_count = 0
            self.evaluated = False
            for name in factory_module._STATE_HOOKS: setattr(self, name, OrderedDict())
            runtime.events.append('model_constructor')
            runtime.act('model_constructor', self)
        def modules(self): yield self
        def build(self):
            self.build_count += 1
            runtime.events.append('model_build')
            runtime.act('build_before', self)
            self.state = {key: runtime.fresh(shape) for key, shape in bridge.FIXED_SHAPES}
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
            for key in state: self.state[key].copy_(state[key])
            runtime.act('load_after', self, state)
            return types.SimpleNamespace(missing_keys=[], unexpected_keys=[])
        def requires_grad_(self, value):
            assert value is False
            for tensor in self.state.values(): tensor.requires_grad = False
            return self
        def eval(self): self.evaluated = True; return self

    fixed = types.ModuleType('inert_fixed_factory')
    fixed.torch = runtime
    fixed.PyanNet = FakePyanNet
    fixed.Problem = types.SimpleNamespace(MULTI_LABEL_CLASSIFICATION=object())
    fixed.Resolution = types.SimpleNamespace(FRAME=object())
    fixed.Specifications = lambda **kwargs: types.SimpleNamespace(**kwargs)
    fixed.VoiceActivitySegmentation = FakeVoiceActivitySegmentation
    for helper in (helpers._fixed_shapes, helpers._check_plain_state):
        fixed.__dict__[helper.__name__] = types.FunctionType(helper.__code__, fixed.__dict__, helper.__name__)
    tensor_port = cpu._OwnedCPUTorchPortProposal(runtime)
    state, digests = {}, []
    for key, shape in bridge.FIXED_SHAPES:
        tensor = tensor_port.allocate_owned_cpu_f32(shape)
        tensor.storage.data[:] = pattern(math.prod(shape) * 4)  # Generated fake storage only.
        state[key] = tensor
        digests.append((key, shape, hashlib.sha256(bytes(tensor.storage.data)).digest()))
    binding = Binding(hashlib.sha256(b'inert generated state').hexdigest(),
                      hashlib.sha256(b'inert admitted profile').hexdigest(), tuple(digests))
    bootstrap = object()
    registry = Registry(bootstrap, Factory)
    previous_runtime, previous_model = guard._RUNTIME, Model
    guard._RUNTIME, Model = registry, FakePyanNet
    factory = None
    try:
        with registry.operation(bootstrap, 'issue'):
            namespace = registry.issue_generated_namespace(bootstrap, (b'config', b'generated text', b'preprocessor', b'tokens', b'vocabulary'))
            media = object()
            pcm = registry.issue_generated_pcm(bootstrap, media, struct.pack('<4f', 0.0, 0.25, -0.25, 0.0))
        with registry.operation(bootstrap, 'factory'):
            factory = Factory(fixed, tensor_port, guard)
            capability = registry._issue_for_bootstrap(bootstrap, factory, binding, registry_module.FIXED_RECIPE_SHA256)
            factory._bind_model_capability(capability)
            product = factory.build_strict_owned(state)
            registry.register_vad_product_for_bootstrap(bootstrap, factory, product, guard)
        value = types.SimpleNamespace(runtime=runtime, fixed=fixed, port=tensor_port, state=state,
                                      binding=binding, bootstrap=bootstrap, registry=registry,
                                      factory=factory, capability=capability, product=product,
                                      namespace=namespace, pcm=pcm, media=media)
        yield value
    finally:
        # Fixture teardown only, after assertions. Do not call the factory again
        # or reinterpret a failed cleanup as successful native reclamation.
        registry.revoke_generation(bootstrap)
        if factory is not None and factory._completed is not None:
            factory.release_product(factory._completed.vad)
        if factory is not None and factory._quarantined_owner is not None:
            factory._quarantined_owner.forget()
        for tensor in state.values():
            tensor_port.release_owned(tensor)
        state.clear()
        guard._RUNTIME, Model = previous_runtime, previous_model
