"""Source-only exact-handle buffer namespace; no model or path I/O at import.

This implements Python-side closed membership. Native CTranslate2 files-reader
closure, memory use and real model authority remain unqualified and disabled.
"""
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType

FOUR = frozenset(("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"))
FIVE = frozenset(("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"))
CHUNK = 65536
MAX_MODEL_BYTES = 4 * 1024 * 1024 * 1024
REAL_NATIVE_FILES_READER_BINDING = None


class NamespaceRefusal(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise NamespaceRefusal(reason)


def declare_read_calls(api, kernel32):
    # Future trusted bootstrap provides the same already-bound system DLL/FFI.
    # This function does not load a DLL or import ctypes, and is not run here.
    ffi = api.ffi
    read = kernel32.ReadFile
    read.restype = ffi.c_int32
    read.argtypes = [ffi.c_void_p, ffi.c_void_p, ffi.c_uint32, ffi.POINTER(ffi.c_uint32), ffi.c_void_p]
    seek = kernel32.SetFilePointerEx
    seek.restype = ffi.c_int32
    seek.argtypes = [ffi.c_void_p, ffi.c_int64, ffi.POINTER(ffi.c_int64), ffi.c_uint32]
    api.functions["ReadFile"], api.functions["SetFilePointerEx"] = read, seek


@dataclass(frozen=True)
class BufferAsset:
    name: str
    size: int
    sha256: str
    handle: object


class PinnedBufferNamespace:
    """One materialization of exact approved names from owned retained handles.

    Asset values must be derived from the existing admitted manifest by trusted
    bootstrap code. Constructing BufferAsset records does not authenticate them.
    A real loader is never invoked by this class.
    """

    def __init__(self, primitives, read_set, assets, payload_budget):
        _require(any(item is read_set for item in primitives.read_sets) and not read_set.unconfirmed
                 and not read_set.released and not read_set.worker_reserved, "fresh_owned_read_set_required")
        _require(type(assets) is tuple and len(assets) in (4, 5), "complete_asset_schema")
        names = [asset.name for asset in assets if type(asset) is BufferAsset]
        _require(len(names) == len(assets) and len(set(names)) == len(names) and frozenset(names) in (FOUR, FIVE),
                 "exact_asset_names_required")
        _require(type(payload_budget) is int and 0 < payload_budget <= MAX_MODEL_BYTES, "explicit_payload_budget")
        subtotal = 0
        seen_handles = []
        for asset in assets:
            _require(type(asset.size) is int and 0 < asset.size <= MAX_MODEL_BYTES, "asset_size")
            _require(type(asset.sha256) is str and len(asset.sha256) == 64
                     and all(char in "0123456789abcdef" for char in asset.sha256), "asset_sha256")
            _require(any(handle is asset.handle for handle in read_set.members)
                     and not any(handle is asset.handle for handle in seen_handles), "asset_handle_ownership")
            seen_handles.append(asset.handle)
            subtotal += asset.size
        _require(subtotal <= payload_budget, "model_payload_budget")
        self._primitives, self._read_set, self._assets = primitives, read_set, assets
        # Payload size only: chunks plus join can temporarily duplicate a file.
        # Python object overhead and any later native copies are additional.
        # This is not a process working-set/RAM cap or real loader admission.
        self._payload_budget = payload_budget
        self._started = False
        self._ready = False
        self._buffers = None
        self.namespace_sha256 = None

    def materialize(self):
        _require(not self._started and not self._read_set.unconfirmed and not self._read_set.released,
                 "namespace_single_materialization")
        self._started = True
        primitives, ffi = self._primitives, self._primitives.api.ffi
        buffers = {}
        try:
            for asset in self._assets:
                before = primitives.identity(asset.handle)
                _require(not before.directory and before.links == 1 and before.size == asset.size, "owned_file_identity")
                position = ffi.c_int64()
                primitives.api.checked("SetFilePointerEx", primitives._owned(asset.handle), 0, ffi.byref(position), 0)
                _require(position.value == 0, "owned_file_position")
                chunks, total = [], 0
                digest = hashlib.sha256()
                while True:
                    # Read at most the remaining approved length plus one byte.
                    # Allocate one fixed-size scratch buffer, not a growing read.
                    requested = min(CHUNK, asset.size - total + 1)
                    scratch = ffi.create_string_buffer(requested)
                    count = ffi.c_uint32()
                    primitives.api.checked("ReadFile", primitives._owned(asset.handle), scratch,
                                           requested, ffi.byref(count), None)
                    _require(0 <= count.value <= requested, "read_count_bound")
                    if count.value == 0:
                        break
                    total += count.value
                    _require(total <= asset.size, "asset_grew_during_read")
                    chunk = bytes(scratch.raw[:count.value])
                    digest.update(chunk)
                    chunks.append(chunk)
                _require(total == asset.size and digest.hexdigest() == asset.sha256, "owned_asset_digest")
                _require(primitives.identity(asset.handle) == before, "owned_asset_identity_changed")
                buffers[asset.name] = b"".join(chunks)
            # Immutable bytes plus a nonmutable membership view. The eventual
            # B3 caller needs a fresh dictionary because it pops two entries.
            self._buffers = MappingProxyType(buffers)
            binding = [[asset.name, asset.size, asset.sha256] for asset in sorted(self._assets, key=lambda item: item.name)]
            self.namespace_sha256 = hashlib.sha256(json.dumps(binding, separators=(",", ":")).encode("ascii")).hexdigest()
            self._ready = True
            return self
        except BaseException:
            self._read_set.unconfirmed = True
            self._buffers = None
            self._ready = False
            raise

    def lookup(self, name):
        _require(self._ready and not self._read_set.unconfirmed and not self._read_set.released, "namespace_not_live")
        _require(type(name) is str and name in self._buffers, "unknown_model_filename")
        return self._buffers[name]

    def proposed_loader_arguments(self):
        _require(self._ready and not self._read_set.unconfirmed and not self._read_set.released, "namespace_not_live")
        # This creates reviewable data only; it does not invoke any constructor.
        # Four-file models require a separately reviewed no-preprocessor path;
        # no fabricated preprocessor is silently added to their approved set.
        _require("preprocessor_config.json" in self._buffers, "four_file_preprocessor_path_requires_review")
        return {"model_size_or_path": "uoink-memory-" + self.namespace_sha256,
                "local_files_only": True, "files": dict(self._buffers)}

    def activate_real_loader(self, *args, **kwargs):
        # A caller cannot set the module variable to bypass missing authority.
        raise NamespaceRefusal("native_files_reader_and_model_stack_are_not_admitted")


def acquire_real_read_namespace(*args, **kwargs):
    # Current source proves neither Windows child-name exclusion nor native
    # CTranslate2 files-map closure. Refuse before any artifact operation.
    raise NamespaceRefusal("complete_native_loader_namespace_unproved")
