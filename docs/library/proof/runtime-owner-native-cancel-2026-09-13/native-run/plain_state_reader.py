"""Inert fixed-schema VAD reader proposal. No file, package or model loading API."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import struct
import time

MAX_OUTPUT = 6 * 1024 * 1024
MAX_HEADER = 32 * 1024
MAX_JSON_DEPTH = 3  # Root object, tensor descriptor, then shape/offset array.
MAX_SECONDS = 30.0
DATA_BYTES = 5_891_996
ELEMENTS = 1_472_999
PLAN_SHA256 = '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf'
ORIGINAL_SHA256 = '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'
REAL_PROFILE = None  # No actual converted artifact or accepted real trust anchor.
_HEX = re.compile(r'[0-9a-f]{64}\Z')


class Refusal(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Refusal(message)


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


@dataclass(frozen=True, slots=True)
class ApprovalProfile:
    purpose: str
    profile_id: str
    output_sha256: str
    output_size: int
    evidence_sha256: str
    plan_sha256: str


@dataclass(frozen=True, slots=True)
class TensorSlice:
    key: str
    dtype: str
    shape: tuple
    elements: int
    start: int  # Absolute byte offsets into VerifiedState.snapshot.
    stop: int


@dataclass(frozen=True, slots=True)
class VerifiedState:
    snapshot: bytes
    tensors: tuple
    data_start: int
    sha256: str
    profile_id: str
    description_json: bytes

    def tensor_bytes(self, key):
        _require(type(key) is str, 'Tensor key must be an exact string')
        for tensor in self.tensors:
            if tensor.key == key:
                return memoryview(self.snapshot)[tensor.start:tensor.stop]
        raise Refusal('Unknown fixed tensor')


class _Budget:
    def __init__(self, seconds):
        _require(type(seconds) in (int, float) and 0 < seconds <= MAX_SECONDS
            and math.isfinite(seconds), 'Cooperative deadline bound')
        self.started = time.monotonic()
        self.expires = self.started + seconds
        self.check()

    def check(self):
        _require(time.monotonic() <= self.expires, 'Reader cooperative deadline exceeded')


def _approved_profile(profile):
    _require(type(profile) is ApprovalProfile, 'Explicit approval profile required')
    # Real approval is deliberately refused before snapshot type/size/hash/parse.
    _require(type(profile.purpose) is str and profile.purpose == 'synthetic',
        'Real plain-state approval remains absent')
    _require(type(profile.profile_id) is str and re.fullmatch(r'synthetic:[a-z0-9-]{1,80}', profile.profile_id),
        'Reviewed synthetic profile ID required')
    for digest in (profile.output_sha256, profile.evidence_sha256, profile.plan_sha256):
        _require(type(digest) is str and _HEX.fullmatch(digest), 'Approval digest field invalid')
    _require(profile.output_sha256 != ORIGINAL_SHA256, 'Synthetic profile cannot authorize original checkpoint')
    _require(profile.plan_sha256 == PLAN_SHA256, 'Approval fixed-plan binding mismatch')
    _require(type(profile.output_size) is int and 8 < profile.output_size <= MAX_OUTPUT,
        'Approval output size bound')


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(type(key) is str and key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def _json_integer(text):
    # The largest permitted number is below 6 MiB; bound lexical conversion first.
    _require(len(text) <= 10, 'JSON integer overflow bound')
    return int(text)


def _reject_json_number(text):
    raise Refusal('Floating/nonfinite JSON number refused')


def _check_json_depth(encoded, budget):
    budget.check()
    depth, quoted, escaped = 0, False, False
    for index, byte in enumerate(encoded):
        if index % 1024 == 0:
            budget.check()
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:  # Backslash protects the next string byte.
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (123, 91):  # Opening brace or bracket outside a string.
            depth += 1
            _require(depth <= MAX_JSON_DEPTH, 'Malformed UTF-8 JSON header: nesting depth bound')
        elif byte in (125, 93):
            depth -= 1
            _require(depth >= 0, 'Malformed UTF-8 JSON header: unmatched closing structure')
    budget.check()


def _header_document(encoded, budget):
    budget.check()
    _require(encoded.startswith(b'{'), 'Header must start with ASCII opening brace')
    _check_json_depth(encoded, budget)
    try:
        document = json.loads(encoded.decode('utf-8'), object_pairs_hook=_strict_pairs,
            parse_int=_json_integer, parse_float=_reject_json_number, parse_constant=_reject_json_number)
    except Refusal:
        raise
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refusal('Malformed UTF-8 JSON header') from error
    budget.check()
    _require(type(document) is dict, 'Header object required')
    return document


def _descriptors(document, data_start, budget):
    _require(len(FIXED_SHAPES) == 54 and len(document) == 54
        and set(document) == {name for name, _ in FIXED_SHAPES}, 'Fixed 54-key tensor schema mismatch')
    cursor, total, tensors = 0, 0, []
    for key, expected_shape in FIXED_SHAPES:
        budget.check()
        item = document[key]
        _require(type(item) is dict and set(item) == {'dtype', 'shape', 'data_offsets'},
            'Tensor descriptor fields mismatch')
        _require(type(item['dtype']) is str and item['dtype'] == 'F32', 'Only fixed F32 dtype supported')
        shape = item['shape']
        _require(type(shape) is list and len(shape) == len(expected_shape)
            and all(type(value) is int and 0 < value <= ELEMENTS for value in shape)
            and tuple(shape) == expected_shape, 'Fixed tensor shape/type mismatch')
        count = math.prod(expected_shape)
        total += count
        end = cursor + count * 4
        offsets = item['data_offsets']
        _require(type(offsets) is list and len(offsets) == 2
            and all(type(value) is int and 0 <= value <= DATA_BYTES for value in offsets),
            'Integer data offset bound')
        _require(offsets == [cursor, end], 'Dense tensor offsets gap/overlap/alias mismatch')
        _require(end <= DATA_BYTES and total <= ELEMENTS, 'Dense tensor element/byte overflow')
        tensors.append(TensorSlice(key, 'F32', expected_shape, count, data_start+cursor, data_start+end))
        cursor = end
    _require(cursor == DATA_BYTES and total == ELEMENTS, 'Exact dense tensor coverage mismatch')
    return tuple(tensors)


def verify_bytes(snapshot, profile, *, deadline_seconds=MAX_SECONDS):
    """Verify an approved synthetic immutable snapshot; no filesystem or imports from data."""
    _approved_profile(profile)
    budget = _Budget(deadline_seconds)
    _require(type(snapshot) is bytes and 8 < len(snapshot) <= MAX_OUTPUT, 'Immutable bounded bytes required')
    _require(len(snapshot) == profile.output_size, 'Approved output size mismatch')
    view = memoryview(snapshot)
    digest = hashlib.sha256()
    for begin in range(0, len(snapshot), 65536):
        budget.check()
        digest.update(view[begin:begin+65536])
    actual_sha = digest.hexdigest()
    budget.check()
    _require(actual_sha == profile.output_sha256, 'Approved output SHA256 mismatch')

    header_size = struct.unpack_from('<Q', snapshot, 0)[0]
    _require(0 < header_size <= MAX_HEADER and header_size % 8 == 0, 'Header length/padding bound')
    data_start = 8 + header_size
    _require(data_start + DATA_BYTES == len(snapshot), 'Exact output coverage/trailing/truncation mismatch')
    encoded = snapshot[8:data_start]
    document = _header_document(encoded, budget)
    tensors = _descriptors(document, data_start, budget)
    budget.check()
    canonical = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode('utf-8')
    canonical += b' ' * (-len(canonical) % 8)
    budget.check()
    _require(encoded == canonical, 'Noncanonical header encoding/order/whitespace/padding refused')

    for begin in range(data_start, len(snapshot), 65536):
        budget.check()
        for (bits,) in struct.iter_unpack('<I', view[begin:begin+65536]):
            _require(bits & 0x7F800000 != 0x7F800000, 'Nonfinite binary32 tensor encoding refused')
    budget.check()
    description = json.dumps({'schema': 'uoink.fixed-vad.verified-plain-state.v1',
        'purpose': 'synthetic', 'profile_id': profile.profile_id, 'output_sha256': actual_sha,
        'output_bytes': len(snapshot), 'data_start': data_start, 'dense_data_bytes': DATA_BYTES,
        'elements': ELEMENTS, 'tensor_count': len(tensors), 'plan_sha256': PLAN_SHA256,
        'native_or_model_qualified': False, 'release_approved': False},
        ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    budget.check()
    result = VerifiedState(snapshot, tensors, data_start, actual_sha, profile.profile_id, description)
    budget.check()
    return result
