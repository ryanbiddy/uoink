"""Unexecuted source proposal. No Torch import or real application entry exists."""
import math
import os
import struct
from types import ModuleType
import weakref

from state_bridge import CHUNK_BYTES, DATA_BYTES, FIXED_SHAPES, TensorFacts

BRIDGE_SHA256 = 'b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2'
TORCH_SOURCE_COMMIT = 'cf30153c4c131c8164ee7798e5022d810682e2cb'
MAX_ALLOCATIONS = 54
_ALLOWED_SHAPES = frozenset(shape for _, shape in FIXED_SHAPES)


class TensorPortRefusal(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise TensorPortRefusal(reason)


def open_real_tensor_port(*args, **kwargs):
    """Profiles, modules and approval-shaped arguments cannot enable this entry."""
    raise TensorPortRefusal('real_authority_absent')


class _Owner:
    __slots__ = ('tensor', 'storage', 'shape', 'start', 'size')

    def __init__(self, tensor, storage, shape, start, size):
        self.tensor = tensor
        self.storage = storage  # Pin the original allocation until retirement.
        self.shape = shape
        self.start = start
        self.size = size

    def forget(self):
        self.tensor = None
        self.storage = None


class _OwnedCPUTorchPortProposal:
    """Concrete private implementation for a separately admitted native trial.

    Constructing this class is not an authority check. A future launcher must
    authenticate its already imported Torch module and all startup conditions.
    The port has one caller, no concurrent mutation, and no untrusted callbacks.
    No production or synthetic bridge entry is wired to this implementation.
    """

    def __init__(self, trusted_torch):
        _require(type(trusted_torch) is ModuleType
                 and trusted_torch.__name__ == 'torch', 'module_shape')
        # Necessary current state only; never evidence of pre-import ordering.
        _require(os.environ.get('TORCH_DEVICE_BACKEND_AUTOLOAD') == '0',
                 'backend_autoload_current_state')
        self._torch = trusted_torch
        self._live = {}
        self._retired = {}  # Weak refs permit idempotence without retaining data.
        self._allocated = 0
        self._live_bytes = 0
        self._context()

    def _context(self):
        torch = self._torch
        _require(os.environ.get('TORCH_DEVICE_BACKEND_AUTOLOAD') == '0',
                 'backend_autoload_current_state')
        _require(torch.get_default_dtype() is torch.float32, 'default_dtype')
        _require(torch.__future__.get_swap_module_params_on_conversion() is False
                 and torch.__future__.get_overwrite_module_params_on_conversion() is False,
                 'module_conversion_flags')

    def _shape(self, shape):
        _require(type(shape) is tuple and 1 <= len(shape) <= 3
                 and all(type(n) is int and n > 0 for n in shape)
                 and shape in _ALLOWED_SHAPES, 'fixed_shape')
        return math.prod(shape) * 4

    def _storage_facts(self, tensor, shape):
        torch = self._torch
        _require(type(tensor) is torch.Tensor, 'ordinary_tensor')
        _require(tensor.dtype is torch.float32 and tensor.device.type == 'cpu'
                 and tensor.device.index is None and tensor.layout is torch.strided,
                 'cpu_f32_strided')
        _require(tuple(tensor.shape) == shape and tensor.numel() == math.prod(shape)
                 and tensor.element_size() == 4 and tensor.is_contiguous() is True
                 and tensor.requires_grad is False and tensor.is_conj() is False
                 and tensor.is_neg() is False, 'tensor_shape_flags')
        _require(type(tensor.storage_offset()) is int and tensor.storage_offset() == 0,
                 'zero_offset')
        storage = tensor.untyped_storage()
        _require(type(storage) is torch.UntypedStorage, 'ordinary_storage')
        start, size = storage.data_ptr(), storage.nbytes()
        _require(type(start) is int and 0 < start < 2**64 and start % 4 == 0
                 and type(size) is int and size == math.prod(shape) * 4
                 and start + size <= 2**64 and tensor.data_ptr() == start,
                 'complete_storage')
        return storage, start, size

    def _lookup(self, tensor):
        _require(type(tensor) is self._torch.Tensor, 'foreign_handle')
        owner = self._live.get(id(tensor))
        _require(owner is not None and owner.tensor is tensor, 'foreign_handle')
        return owner

    def _recheck(self, owner):
        storage, start, size = self._storage_facts(owner.tensor, owner.shape)
        # Native storage wrappers need not have the same Python identity.
        # Holding owner.storage pins the original allocation across this check.
        _require(owner.storage.data_ptr() == owner.start
                 and owner.storage.nbytes() == owner.size
                 and start == owner.start and size == owner.size, 'storage_identity_changed')
        return storage

    def _disjoint(self, start, size):
        for owner in self._live.values():
            self._recheck(owner)
            _require(start + size <= owner.start or owner.start + owner.size <= start,
                     'overlapping_storage')

    def allocate_owned_cpu_f32(self, shape):
        self._context()
        size = self._shape(shape)
        _require(self._allocated < MAX_ALLOCATIONS
                 and self._live_bytes + size <= DATA_BYTES, 'allocation_bound')
        tensor = storage = owner = None
        published = False
        accounted = False
        self._allocated += 1  # Bound attempts, including failures before return.
        try:
            with self._torch.no_grad():
                tensor = self._torch.empty(shape, dtype=self._torch.float32,
                                           device='cpu', requires_grad=False)
            storage, start, measured = self._storage_facts(tensor, shape)
            self._disjoint(start, measured)
            _require(id(tensor) not in self._live, 'duplicate_allocation')
            # Create the eventual weak reference now so retirement cannot fail
            # merely because this Tensor binding does not support weakrefs.
            retired_ref = weakref.ref(tensor)
            owner = _Owner(tensor, storage, shape, start, measured)
            self._live[id(tensor)] = owner
            self._retired[id(tensor)] = retired_ref
            self._live_bytes += measured
            accounted = True
            published = True
            return tensor
        finally:
            if not published:
                # Before publication, no owner exists in the bridge cleanup list.
                # Drop internal references; no native allocator-free claim follows.
                if owner is not None:
                    if self._live.get(id(tensor)) is owner:
                        del self._live[id(tensor)]
                    if accounted:
                        self._live_bytes -= owner.size
                    retired = self._retired.get(id(tensor))
                    if retired is not None and retired() is tensor:
                        del self._retired[id(tensor)]
                    owner.forget()
                owner = storage = tensor = None

    def inspect_owned(self, tensor):
        self._context()
        owner = self._lookup(tensor)
        self._recheck(owner)
        return TensorFacts(owner.shape, 'F32', 'cpu', 'strided', True, True,
                           False, 0, owner.start, owner.size, True, True)

    def _range(self, owner, offset, count):
        _require(type(offset) is int and type(count) is int
                 and offset >= 0 and offset % 4 == 0
                 and 0 < count <= CHUNK_BYTES and count % 4 == 0
                 and offset + count <= owner.size, 'bounded_range')

    def _view(self, owner, offset, count):
        self._recheck(owner)
        view = owner.tensor.view(-1).narrow(0, offset // 4, count // 4)
        _require(type(view) is self._torch.Tensor
                 and view.dtype is self._torch.float32 and view.device.type == 'cpu'
                 and view.device.index is None and view.layout is self._torch.strided
                 and tuple(view.shape) == (count // 4,)
                 and view.is_contiguous() is True and view.requires_grad is False
                 and view.is_conj() is False and view.is_neg() is False
                 and view.storage_offset() * 4 == offset
                 and view.untyped_storage().data_ptr() == owner.start
                 and view.untyped_storage().nbytes() == owner.size
                 and view.data_ptr() == owner.start + offset, 'destination_view')
        return view

    def copy_owned_f32le(self, tensor, byte_offset, chunk):
        self._context()
        owner = self._lookup(tensor)
        _require(type(chunk) is bytes, 'immutable_chunk')
        self._range(owner, byte_offset, len(chunk))
        _require(all(word[0] & 0x7f800000 != 0x7f800000
                     for word in struct.iter_unpack('<I', chunk)), 'nonfinite_chunk')
        values = staging = storage = destination = None
        try:
            # All finite F32 numbers are exactly representable as Python doubles.
            # Native conversion back to F32 is still checked by bridge readback.
            values = [value[0] for value in struct.iter_unpack('<f', chunk)]
            with self._torch.no_grad():
                staging = self._torch.tensor(values, dtype=self._torch.float32,
                                             device='cpu', requires_grad=False)
                storage, start, size = self._storage_facts(staging, (len(values),))
                self._disjoint(start, size)
                destination = self._view(owner, byte_offset, len(chunk))
                destination.copy_(staging)
            self._recheck(owner)
        finally:
            # Views never escape the method; staging never wraps immutable bytes.
            destination = staging = storage = values = None

    def read_owned_f32le(self, tensor, byte_offset, byte_count):
        self._context()
        owner = self._lookup(tensor)
        self._range(owner, byte_offset, byte_count)
        view = values = None
        try:
            view = self._view(owner, byte_offset, byte_count)
            values = view.tolist()
            _require(type(values) is list and len(values) == byte_count // 4
                     and all(type(value) is float and math.isfinite(value)
                             for value in values), 'native_readback_values')
            result = struct.pack('<' + str(len(values)) + 'f', *values)
            _require(type(result) is bytes and len(result) == byte_count,
                     'native_readback_length')
            self._recheck(owner)
            return result
        finally:
            view = values = None

    def release_owned(self, tensor):
        _require(type(tensor) is self._torch.Tensor, 'foreign_handle')
        identity = id(tensor)
        owner = self._live.get(identity)
        if owner is None:
            retired = self._retired.get(identity)
            _require(retired is not None and retired() is tensor, 'foreign_handle')
            return
        _require(owner.tensor is tensor, 'foreign_handle')
        try:
            # Never write a replacement storage after an identity failure.
            self._recheck(owner)
            with self._torch.no_grad():
                tensor.zero_()
            self._recheck(owner)
        finally:
            # Retire even if zeroing/inspection raises. The bridge records failure
            # and withholds success; a normal repeated retirement is idempotent.
            del self._live[identity]
            self._live_bytes -= owner.size
            owner.forget()
