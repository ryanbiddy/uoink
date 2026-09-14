"""Source-only fixed factory transaction; no native imports or real entry."""
from collections import OrderedDict
import hashlib
import math
import os
import struct
from time import monotonic
from types import ModuleType
import weakref

from state_bridge import CHUNK_BYTES, DATA_BYTES, FIXED_SHAPES, TensorFacts
from model_binding_registry import _FactoryModelCapability

FACTORY_SHA256 = '69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b'
CPU_PORT_SHA256 = 'ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964'
MAX_SECONDS = 30.0
_STATE_HOOKS = ('_state_dict_hooks', '_state_dict_pre_hooks',
                '_load_state_dict_pre_hooks', '_load_state_dict_post_hooks')


class FactoryPortRefusal(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise FactoryPortRefusal(reason)


def open_real_factory_port(*args, **kwargs):
    raise FactoryPortRefusal('real_authority_absent')


class _FactoryOwner:
    __slots__ = ('model', 'vad', 'model_state', 'model_lease')

    def __init__(self):
        self.model = None
        self.vad = None
        self.model_state = ()
        self.model_lease = None

    def forget(self):
        # Retire this owner's references, not an invented native close operation.
        self.model_state = ()
        self.model_lease = None
        self.vad = None
        self.model = None


class _OwnedFactoryPortProposal:
    """Private implementation; dependencies and native execution need D4 admission.

    fixed_factory is the already imported, independently source-bound module
    containing the reviewed classes/enums and _check_plain_state helper. Its
    type and this constructor are not authority. The supplied tensor port is
    the exact owned CPU implementation paired with the same bridge invocation.
    A trusted caller must serialize construction, binding, build and release;
    the attempt flag is not a concurrent-entry lock. Registry generation
    revocation is separately synchronized and does not cancel native work.
    """

    def __init__(self, fixed_factory, tensor_port, owned_runtime_module):
        _require(type(fixed_factory) is ModuleType, 'factory_module_shape')
        _require(type(owned_runtime_module) is ModuleType, 'owned_runtime_module_shape')
        self._factory = fixed_factory
        self._torch = fixed_factory.torch
        self._tensor_port = tensor_port
        self._owned_runtime_module = owned_runtime_module
        self._model_capability = None
        self._quarantined_owner = None
        self._attempted = False
        self._completed = None
        self._retired = None
        self._context()

    def _bind_model_capability(self, capability):
        _require(self._attempted is False and self._model_capability is None
                 and type(capability) is _FactoryModelCapability, 'model_capability_binding')
        capability.assert_factory_and_runtime(self, self._owned_runtime_module)
        self._model_capability = capability

    def _context(self):
        torch = self._torch
        _require(os.environ.get('TORCH_DEVICE_BACKEND_AUTOLOAD') == '0'
                 and os.environ.get('PYANNOTE_METRICS_ENABLED') == '0', 'current_import_settings')
        _require(torch.get_default_dtype() is torch.float32, 'default_dtype')
        _require(torch.__future__.get_swap_module_params_on_conversion() is False
                 and torch.__future__.get_overwrite_module_params_on_conversion() is False,
                 'module_conversion_flags')

    @staticmethod
    def _clock(expires):
        _require(monotonic() < expires, 'factory_deadline_exceeded')

    def _state_hooks(self, model, expires):
        # Restrict instance state/load hooks before calling state_dict or load.
        # Source-defined methods and global/native import behavior remain trusted
        # runtime prerequisites; this is not a whole-module certification.
        for index, child in enumerate(model.modules()):
            self._clock(expires)
            _require(index < 256, 'module_count_bound')
            for name in _STATE_HOOKS:
                hooks = getattr(child, name)
                _require(type(hooks) in (dict, OrderedDict) and not hooks, 'state_hooks_present')

    def _native_storage(self, tensor, shape):
        torch = self._torch
        _require(type(tensor) is torch.Tensor and tensor.dtype is torch.float32
                 and tensor.device.type == 'cpu' and tensor.device.index is None
                 and tensor.layout is torch.strided and tuple(tensor.shape) == shape
                 and tensor.requires_grad is False and tensor.is_contiguous() is True
                 and tensor.is_conj() is False and tensor.is_neg() is False,
                 'model_state_format')
        storage = tensor.untyped_storage()
        _require(type(storage) is torch.UntypedStorage, 'model_storage_type')
        start, size, offset = storage.data_ptr(), storage.nbytes(), tensor.storage_offset()
        count = math.prod(shape) * 4
        _require(type(start) is int and 0 < start < 2**64 and start % 4 == 0
                 and type(size) is int and 0 < size <= DATA_BYTES and size % 4 == 0
                 and start + size <= 2**64 and type(offset) is int and offset >= 0
                 and offset * 4 + count <= size and tensor.element_size() == 4
                 and tensor.numel() == math.prod(shape)
                 and tensor.data_ptr() == start + offset * 4, 'model_storage_range')
        return storage, start, size, offset * 4

    def _native_digest(self, tensor, shape, expires):
        digest = hashlib.sha256()
        total = math.prod(shape) * 4
        view = values = None
        try:
            for offset in range(0, total, CHUNK_BYTES):
                self._clock(expires)
                count = min(CHUNK_BYTES, total - offset) // 4
                view = tensor.view(-1).narrow(0, offset // 4, count)
                values = view.tolist()
                _require(type(values) is list and len(values) == count
                         and all(type(value) is float and math.isfinite(value)
                                 for value in values), 'model_readback_values')
                digest.update(struct.pack('<' + str(count) + 'f', *values))
                view = values = None
            self._clock(expires)
            return digest.digest()
        finally:
            view = values = None

    def _input_digest(self, tensor, shape, expires):
        digest = hashlib.sha256()
        total = math.prod(shape) * 4
        for offset in range(0, total, CHUNK_BYTES):
            self._clock(expires)
            count = min(CHUNK_BYTES, total - offset)
            chunk = self._tensor_port.read_owned_f32le(tensor, offset, count)
            _require(type(chunk) is bytes and len(chunk) == count, 'input_readback')
            digest.update(chunk)
        self._clock(expires)
        return digest.digest()

    def _inputs(self, state, expires):
        self._factory._check_plain_state(state, require_zero_offset=True, require_finite=True)
        records = []
        for key, shape in FIXED_SHAPES:
            self._clock(expires)
            tensor = state[key]
            facts = self._tensor_port.inspect_owned(tensor)
            _require(type(facts) is TensorFacts and facts.shape == shape
                     and facts.owned is True and facts.no_external_aliases is True
                     and facts.storage_offset_bytes == 0
                     and facts.storage_bytes == math.prod(shape) * 4, 'input_owner_facts')
            records.append((key, tensor, shape, facts, self._input_digest(tensor, shape, expires)))
        return records

    def _verify_result(self, owner, inputs, expires):
        self._state_hooks(owner.model, expires)
        state = dict(owner.model.state_dict())
        self._factory._check_plain_state(state, require_zero_offset=False, require_finite=True)
        pinned = []
        try:
            for key, input_tensor, shape, input_facts, expected in inputs:
                self._clock(expires)
                tensor = state[key]
                storage, start, size, offset = self._native_storage(tensor, shape)
                # Hold every observed original storage throughout subsequent
                # comparisons and until the product owner is retired.
                pinned.append((key, tensor, storage, shape, start, size, offset, expected))
                for _, _, _, facts, _ in inputs:
                    _require(start + size <= facts.storage_start
                             or facts.storage_start + facts.storage_bytes <= start,
                             'model_aliases_input_storage')
                _require(self._native_digest(tensor, shape, expires) == expected,
                         'model_value_mismatch')
                _require(self._tensor_port.inspect_owned(input_tensor) == input_facts
                         and self._input_digest(input_tensor, shape, expires) == expected,
                         'input_changed_during_factory')
            for key, tensor, storage, shape, start, size, offset, expected in pinned:
                self._clock(expires)
                current, current_start, current_size, current_offset = self._native_storage(tensor, shape)
                _require(storage.data_ptr() == start and storage.nbytes() == size
                         and (current_start, current_size, current_offset) == (start, size, offset),
                         'model_storage_changed')
                _require(self._native_digest(tensor, shape, expires) == expected,
                         'model_changed_during_verification')
            owner.model_state = tuple(pinned)
        finally:
            state.clear()
            pinned.clear()

    def build_strict_owned(self, state):
        _require(self._attempted is False, 'one_factory_attempt_only')
        _require(self._model_capability is not None, 'model_capability_absent')
        self._attempted = True
        owner = None
        inputs = []
        fresh = None
        published = False
        phase = 'factory_context'
        try:
            self._model_capability.assert_factory_and_runtime(self, self._owned_runtime_module)
            expires = monotonic() + MAX_SECONDS
            self._context()
            owner = _FactoryOwner()
            phase = 'input_validation'
            inputs = self._inputs(state, expires)
            factory = self._factory
            torch = self._torch
            phase = 'model_construction'
            self._clock(expires)
            with torch.device('cpu'):
                owner.model = factory.PyanNet(
                    sample_rate=16000, num_channels=1,
                    sincnet={'stride': 10, 'sample_rate': 16000},
                    lstm={'hidden_size': 128, 'num_layers': 4, 'bidirectional': True,
                          'monolithic': True, 'dropout': 0.5, 'batch_first': True,
                          'bias': True, 'proj_size': 0},
                    linear={'hidden_size': 128, 'num_layers': 2}, task=None)
                _require(type(owner.model) is factory.PyanNet, 'fixed_model_type')
                self._clock(expires)
                owner.model.specifications = factory.Specifications(
                    problem=factory.Problem.MULTI_LABEL_CLASSIFICATION,
                    resolution=factory.Resolution.FRAME, duration=5.0,
                    min_duration=None, powerset_max_classes=None,
                    warm_up=(0.0, 0.0), classes=['speaker#1', 'speaker#2', 'speaker#3'],
                    permutation_invariant=True)
                phase = 'model_build'
                self._state_hooks(owner.model, expires)
                owner.model.build()
            self._clock(expires)
            self._state_hooks(owner.model, expires)
            fresh = dict(owner.model.state_dict())
            factory._check_plain_state(fresh, require_zero_offset=False, require_finite=False)
            fresh.clear(); fresh = None
            phase = 'strict_state_load'
            self._context()
            result = owner.model.load_state_dict(state, strict=True, assign=False)
            _require(not result.missing_keys and not result.unexpected_keys, 'strict_load_keys')
            owner.model.requires_grad_(False)
            owner.model.eval()
            self._context()
            self._verify_result(owner, inputs, expires)
            phase = 'model_registration'
            observed_rows = tuple((key, shape, expected) for key, _, shape, _, expected in inputs)
            owner.model_lease = self._model_capability.register_verified_model(
                self, self._owned_runtime_module, owner.model, observed_rows)
            phase = 'vad_construction'
            owner.vad = factory.VoiceActivitySegmentation(
                segmentation=owner.model, device=torch.device('cpu'), window='sliding',
                duration=5.0, step=0.5, batch_size=32,
                skip_aggregation=False, skip_conversion=False)
            _require(type(owner.vad) is factory.VoiceActivitySegmentation, 'fixed_vad_type')
            owner.model_lease.assert_bound(self, owner.model)
            self._clock(expires)
            phase = 'vad_instantiate'
            owner.vad.instantiate({'onset': 0.500, 'offset': 0.363,
                                   'min_duration_on': 0.1, 'min_duration_off': 0.1})
            self._context()
            self._verify_result(owner, inputs, expires)
            self._clock(expires)
            retired = weakref.ref(owner.vad)
            with owner.model_lease.publication(self, owner.model):
                self._retired = retired
                self._completed = owner
                published = True
                return owner.vad
        except BaseException as error:
            if type(error) is FactoryPortRefusal:
                raise
            raise FactoryPortRefusal(phase) from error
        finally:
            inputs.clear()
            if fresh is not None:
                fresh.clear()
            if not published:
                try:
                    self._model_capability.revoke(self)
                except BaseException as cleanup_error:
                    # Retain owners if revocation cannot be established. A real
                    # bootstrap must quarantine this failed worker/session.
                    self._quarantined_owner = owner
                    raise FactoryPortRefusal('model_revocation_unconfirmed') from cleanup_error
                if self._completed is owner:
                    self._completed = None
                self._retired = None
                if owner is not None:
                    owner.forget()

    def release_product(self, product):
        owner = self._completed
        if owner is None:
            _require(product is not None and self._retired is not None
                     and self._retired() is product, 'foreign_product')
            return
        _require(owner.vad is product, 'foreign_product')
        # Revoke the constructor/runtime capability before retiring references.
        # If this fails, keep the complete owner and propagate the failure.
        owner.model_lease.revoke(self)
        self._completed = None
        owner.forget()
        # The caller/bridge can still hold product. This returns no native-close
        # or OS-reclamation receipt; it confirms retirement by this port only.
