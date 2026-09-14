"""Literal inert fake APIs copied from qualified CPU harness 93d724b4; no Torch import."""
from contextlib import contextmanager
import math
import struct
import types
import weakref

class FakeStorage:
    def __init__(self, size, address):
        self.data = bytearray(size)
        self.address = address
        self.advertised = size

    def data_ptr(self):
        return self.address

    def nbytes(self):
        return self.advertised


class FakeTensor:
    def __init__(self, runtime, shape, storage, offset=0):
        self.runtime = runtime
        self.shape = tuple(shape)
        self.storage = storage
        self.offset = offset
        self.dtype = runtime.float32
        self.device = types.SimpleNamespace(type='cpu', index=None)
        self.layout = runtime.strided
        self.requires_grad = False
        self.contiguous = True
        self.conjugate = self.negative = False

    def numel(self): return math.prod(self.shape)
    def element_size(self): return 4
    def is_contiguous(self): return self.contiguous
    def is_conj(self): return self.conjugate
    def is_neg(self): return self.negative
    def storage_offset(self): return self.offset
    def untyped_storage(self): return self.storage
    def data_ptr(self): return self.storage.address + self.offset * 4

    def view(self, shape):
        assert shape == -1
        return FakeTensor(self.runtime, (self.numel(),), self.storage, self.offset)

    def narrow(self, dim, start, count):
        assert dim == 0 and 0 <= start <= self.numel() - count
        result = FakeTensor(self.runtime, (count,), self.storage, self.offset + start)
        if self.runtime.view_hook is not None:
            return self.runtime.view_hook(result)
        return result

    def copy_(self, other):
        self.runtime.copy_calls += 1
        assert type(other) is FakeTensor and self.numel() == other.numel()
        if self.runtime.copy_hook is not None:
            self.runtime.copy_hook(self, other, 'before')
        start, stop = self.offset * 4, (self.offset + self.numel()) * 4
        begin = other.offset * 4
        self.storage.data[start:stop] = other.storage.data[begin:begin + self.numel() * 4]
        if self.runtime.copy_hook is not None:
            self.runtime.copy_hook(self, other, 'after')
        return self

    def tolist(self):
        self.runtime.read_calls += 1
        start, stop = self.offset * 4, (self.offset + self.numel()) * 4
        values = [row[0] for row in struct.iter_unpack('<f', self.storage.data[start:stop])]
        if self.runtime.read_hook is not None:
            return self.runtime.read_hook(values)
        return values

    def zero_(self):
        self.runtime.zero_calls += 1
        if self.runtime.zero_hook is not None:
            self.runtime.zero_hook(self)
        start, stop = self.offset * 4, (self.offset + self.numel()) * 4
        self.storage.data[start:stop] = bytes(stop - start)
        return self


def fake_torch():
    runtime = types.ModuleType('torch')  # Deliberately never installed as torch.
    runtime.Tensor = FakeTensor
    runtime.UntypedStorage = FakeStorage
    runtime.float32 = object()
    runtime.strided = object()
    runtime.default_dtype = runtime.float32
    runtime.get_default_dtype = lambda: runtime.default_dtype
    runtime.swap = runtime.overwrite = False
    runtime.__future__ = types.SimpleNamespace(
        get_swap_module_params_on_conversion=lambda: runtime.swap,
        get_overwrite_module_params_on_conversion=lambda: runtime.overwrite)
    runtime.address = 0x100000
    runtime.empty_calls = runtime.tensor_calls = runtime.copy_calls = 0
    runtime.read_calls = runtime.zero_calls = 0
    runtime.empty_hook = runtime.tensor_hook = runtime.view_hook = None
    runtime.copy_hook = runtime.read_hook = runtime.zero_hook = None
    runtime.created = []  # Weakrefs only; do not manufacture lifetime retention.

    @contextmanager
    def no_grad():
        yield
    runtime.no_grad = no_grad

    def fresh(shape):
        size = math.prod(shape) * 4
        storage = FakeStorage(size, runtime.address)
        runtime.address += size + 64
        tensor = FakeTensor(runtime, shape, storage)
        runtime.created.append(weakref.ref(tensor))
        return tensor
    runtime.fresh = fresh

    def empty(shape, *, dtype, device, requires_grad):
        runtime.empty_calls += 1
        assert dtype is runtime.float32 and device == 'cpu' and requires_grad is False
        if runtime.empty_hook is not None:
            return runtime.empty_hook(shape)
        return fresh(shape)
    runtime.empty = empty

    def tensor(values, *, dtype, device, requires_grad):
        runtime.tensor_calls += 1
        assert type(values) is list and all(type(v) is float for v in values)
        assert dtype is runtime.float32 and device == 'cpu' and requires_grad is False
        assert 0 < len(values) <= 16384
        if runtime.tensor_hook is not None:
            return runtime.tensor_hook(values)
        result = fresh((len(values),))
        result.storage.data[:] = struct.pack('<' + str(len(values)) + 'f', *values)
        return result
    runtime.tensor = tensor
    return runtime


