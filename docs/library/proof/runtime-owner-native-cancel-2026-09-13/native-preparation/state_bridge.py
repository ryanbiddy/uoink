"""Synthetic owned-state orchestration only; real native entry is closed."""
from dataclasses import dataclass
import math
from time import monotonic as _now
import plain_state_reader as reader

READER_SHA256 = '3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c'
FACTORY_SHA256 = '69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b'
PLAN_SHA256 = '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf'
MAX_SECONDS = 30.0
CHUNK_BYTES = 65_536
DATA_BYTES = 5_891_996
ELEMENTS = 1_472_999
_NO_PRODUCT = object()


class BridgeRefusal(ValueError):
    def __init__(self, phase, cleanup_failures=0):
        self.phase = phase
        self.cleanup_failures = cleanup_failures
        super().__init__(f'Bridge refused in {phase}; cleanup failures: {cleanup_failures}')


@dataclass(frozen=True, slots=True)
class TensorFacts:
    shape: tuple
    dtype: str
    device: str
    layout: str
    ordinary_tensor: bool
    contiguous: bool
    requires_grad: bool
    storage_offset_bytes: int
    storage_start: int
    storage_bytes: int
    owned: bool
    no_external_aliases: bool


@dataclass(frozen=True, slots=True)
class SyntheticResult:
    product: object
    input_sha256: str
    profile_id: str
    tensor_count: int = 54
    data_bytes: int = DATA_BYTES
    scope: str = 'synthetic_ports_only'
    native_qualified: bool = False
    release_approved: bool = False


def _fixed_shapes():
    shapes = {
        'sincnet.wav_norm1d.weight': (1,),
        'sincnet.wav_norm1d.bias': (1,),
        'sincnet.conv1d.0.filterbank.low_hz_': (40, 1),
        'sincnet.conv1d.0.filterbank.band_hz_': (40, 1),
        'sincnet.conv1d.0.filterbank.window_': (125,),
        'sincnet.conv1d.0.filterbank.n_': (1, 125),
        'sincnet.conv1d.1.weight': (60, 80, 5),
        'sincnet.conv1d.1.bias': (60,),
        'sincnet.conv1d.2.weight': (60, 60, 5),
        'sincnet.conv1d.2.bias': (60,),
        'sincnet.norm1d.0.weight': (80,),
        'sincnet.norm1d.0.bias': (80,),
        'sincnet.norm1d.1.weight': (60,),
        'sincnet.norm1d.1.bias': (60,),
        'sincnet.norm1d.2.weight': (60,),
        'sincnet.norm1d.2.bias': (60,),
        'linear.0.weight': (128, 256),
        'linear.0.bias': (128,),
        'linear.1.weight': (128, 128),
        'linear.1.bias': (128,),
        'classifier.weight': (3, 128),
        'classifier.bias': (3,),
    }
    for layer in range(4):
        for suffix in ('', '_reverse'):
            shapes[f'lstm.weight_ih_l{layer}{suffix}'] = (512, 60 if layer == 0 else 256)
            shapes[f'lstm.weight_hh_l{layer}{suffix}'] = (512, 128)
            shapes[f'lstm.bias_ih_l{layer}{suffix}'] = (512,)
            shapes[f'lstm.bias_hh_l{layer}{suffix}'] = (512,)
    return tuple(sorted(shapes.items()))


FIXED_SHAPES = _fixed_shapes()


def _require(condition, phase):
    if not condition:
        raise BridgeRefusal(phase)


class _Budget:
    def __init__(self, seconds):
        _require(type(seconds) in (int, float) and math.isfinite(seconds)
            and 0 < seconds <= MAX_SECONDS, 'deadline_bound')
        self.expires = _now() + seconds

    def check(self):
        _require(_now() < self.expires, 'deadline_exceeded')

    def remaining(self):
        self.check()
        value = self.expires - _now()
        _require(value > 0, 'deadline_exceeded')
        return min(value, reader.MAX_SECONDS)


def _validate_verified(verified, snapshot, profile):
    _require(type(verified) is reader.VerifiedState and verified.snapshot is snapshot,
        'verified_snapshot_binding')
    _require(verified.sha256 == profile.output_sha256
        and verified.profile_id == profile.profile_id, 'verified_profile_binding')
    _require(type(verified.tensors) is tuple and len(verified.tensors) == 54
        and len(FIXED_SHAPES) == 54, 'fixed_schema')
    cursor = verified.data_start
    _require(type(cursor) is int and cursor > 8
        and len(snapshot) - cursor == DATA_BYTES, 'fixed_coverage')
    elements = 0
    for descriptor, (key, shape) in zip(verified.tensors, FIXED_SHAPES, strict=True):
        _require(type(descriptor) is reader.TensorSlice
            and type(descriptor.key) is str and descriptor.key == key
            and type(descriptor.dtype) is str and descriptor.dtype == 'F32'
            and type(descriptor.shape) is tuple
            and all(type(n) is int for n in descriptor.shape)
            and descriptor.shape == shape, 'fixed_schema')
        count = math.prod(shape)
        _require(type(descriptor.elements) is int and descriptor.elements == count
            and type(descriptor.start) is int and descriptor.start == cursor
            and type(descriptor.stop) is int and descriptor.stop == cursor + count * 4,
            'fixed_coverage')
        cursor = descriptor.stop
        elements += count
    _require(cursor == len(snapshot) and elements == ELEMENTS, 'fixed_coverage')


def _facts(port, handle, shape):
    facts = port.inspect_owned(handle)
    _require(type(facts) is TensorFacts, 'tensor_facts')
    _require(type(facts.shape) is tuple and all(type(n) is int for n in facts.shape)
        and facts.shape == shape, 'tensor_shape')
    _require(type(facts.dtype) is str and facts.dtype == 'F32'
        and type(facts.device) is str and facts.device == 'cpu'
        and type(facts.layout) is str and facts.layout == 'strided', 'tensor_format')
    _require(facts.ordinary_tensor is True and facts.contiguous is True
        and facts.requires_grad is False and facts.owned is True
        and facts.no_external_aliases is True, 'tensor_ownership')
    _require(type(facts.storage_offset_bytes) is int and facts.storage_offset_bytes == 0
        and type(facts.storage_start) is int and 0 < facts.storage_start < 2**64
        and facts.storage_start % 4 == 0
        and type(facts.storage_bytes) is int and facts.storage_bytes == math.prod(shape) * 4
        and facts.storage_start + facts.storage_bytes <= 2**64, 'tensor_storage')
    return facts


def _check_readback(port, handle, byte_offset, chunk):
    observed = port.read_owned_f32le(handle, byte_offset, len(chunk))
    _require(type(observed) is bytes and len(observed) == len(chunk)
        and observed == chunk, 'tensor_readback')


def build_real_vad(*args, **kwargs):
    """No caller profile/token can enable native imports or actual tensor creation."""
    raise BridgeRefusal('real_authority_absent')


def exercise_synthetic_bridge(snapshot, approval, tensor_port, factory_port,
                              *, deadline_seconds=MAX_SECONDS):
    """Only generated bytes and trusted inert ports are admitted to this proposal.

    Port implementations are code-trust prerequisites, not artifact-provided
    callbacks. Real implementations and native module imports are not supplied.
    Returned product ownership transfers to the synthetic caller on success.
    """
    budget = _Budget(deadline_seconds)
    allocations = []
    state = {}
    product = _NO_PRODUCT
    primary = None
    phase = 'reader_validation'
    cleanup_errors = []
    result = None
    try:
        # Never trust externally constructed VerifiedState or description JSON.
        verified = reader.verify_bytes(snapshot, approval, deadline_seconds=budget.remaining())
        budget.check()
        _validate_verified(verified, snapshot, approval)
        phase = 'tensor_allocation'
        for descriptor in verified.tensors:
            budget.check()
            handle = tensor_port.allocate_owned_cpu_f32(descriptor.shape)
            _require(handle is not None and not any(handle is item[0] for item in allocations),
                'duplicate_or_missing_allocation')
            # Own the returned handle before any fallible inspection.
            allocations.append((handle, descriptor, None))
            budget.check()
            phase = 'tensor_inspection'
            facts = _facts(tensor_port, handle, descriptor.shape)
            for _, _, prior in allocations[:-1]:
                _require(facts.storage_start + facts.storage_bytes <= prior.storage_start
                    or prior.storage_start + prior.storage_bytes <= facts.storage_start,
                    'overlapping_allocations')
            allocations[-1] = (handle, descriptor, facts)
            phase = 'tensor_copy'
            for begin in range(descriptor.start, descriptor.stop, CHUNK_BYTES):
                budget.check()
                end = min(begin + CHUNK_BYTES, descriptor.stop)
                # A fresh immutable bounded copy; never pass the snapshot view.
                chunk = memoryview(snapshot)[begin:end].tobytes()
                offset = begin - descriptor.start
                tensor_port.copy_owned_f32le(handle, offset, chunk)
                budget.check()
                _check_readback(tensor_port, handle, offset, chunk)
            _require(_facts(tensor_port, handle, descriptor.shape) == facts, 'tensor_identity_changed')
            state[descriptor.key] = handle
            phase = 'tensor_allocation'

        phase = 'final_state_validation'
        _require(type(state) is dict and len(state) == 54
            and all(type(key) is str for key in state)
            and tuple(state) == tuple(name for name, _ in FIXED_SHAPES), 'fixed_schema')
        # Catch mutations of earlier allocations before handing them to the factory.
        for handle, descriptor, facts in allocations:
            budget.check()
            _require(_facts(tensor_port, handle, descriptor.shape) == facts, 'tensor_identity_changed')
            for begin in range(descriptor.start, descriptor.stop, CHUNK_BYTES):
                budget.check()
                end = min(begin + CHUNK_BYTES, descriptor.stop)
                _check_readback(tensor_port, handle, begin - descriptor.start,
                    memoryview(snapshot)[begin:end].tobytes())

        phase = 'factory_build'
        budget.check()
        product = factory_port.build_strict_owned(dict(state))
        _require(product is not None and product is not _NO_PRODUCT, 'missing_factory_product')
        budget.check()
        result = SyntheticResult(product, verified.sha256, verified.profile_id)
    except BaseException as error:
        primary = error

    # Cleanup must finish its bounded list even after cancellation/deadline expiry.
    state.clear()
    for handle, _, _ in reversed(allocations):
        try:
            tensor_port.release_owned(handle)
        except BaseException as error:
            cleanup_errors.append(error)
    allocations.clear()
    if primary is None:
        try:
            budget.check()
        except BaseException as error:
            primary = error
            phase = 'cleanup_deadline'
    if primary is not None or cleanup_errors:
        if product is not _NO_PRODUCT and product is not None:
            try:
                factory_port.release_product(product)
            except BaseException as error:
                cleanup_errors.append(error)
        failure_phase = primary.phase if type(primary) is BridgeRefusal else phase
        if primary is None:
            failure_phase = 'tensor_cleanup'
        cause = primary if primary is not None else cleanup_errors[0]
        raise BridgeRefusal(failure_phase, len(cleanup_errors)) from cause
    return result
