"""Retained Windows journal mechanics; no imports of ctypes or native startup."""
from dataclasses import dataclass
from threading import RLock
from reservation_file_port import RetainedJournal, PersistenceUnconfirmed, MAX_JOURNAL
from snapshot_reservations import (GeneratedGateRegistry, PhysicalSnapshot,
    ReservationRefused, decode_journal)
from win32_worker_connection import (Win32API, FileIdentity, ReadSet, GENERIC_READ,
    OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, _absolute_local_path)

GENERIC_WRITE = 0x40000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
FILE_BEGIN = 0
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33
MAX_CHUNK = 65536


def real_windows_reservation_service(*args, **kwargs):
    raise ReservationRefused("real_registry_namespace_and_recovery_admission_absent")


def declare_journal_bindings(api, kernel32):
    """Explicit proposed Windows x64 ABI; trusted bootstrap must review/bind it.

    The return value must be supplied to both file primitives and pipe ports.
    No DLL is loaded and no function is invoked by this declaration function.
    """
    ffi = api.ffi
    if ffi.sizeof(ffi.c_void_p) != 8:
        raise PersistenceUnconfirmed("journal_requires_reviewed_x64_abi")
    ptr, u32, i32, i64 = ffi.c_void_p, ffi.c_uint32, ffi.c_int32, ffi.c_int64
    prototypes = {
        "SetFilePointerEx": (i32, [ptr, i64, ffi.POINTER(i64), u32]),
        "ReadFile": (i32, [ptr, ptr, u32, ffi.POINTER(u32), ptr]),
        "WriteFile": (i32, [ptr, ptr, u32, ffi.POINTER(u32), ptr]),
        "FlushFileBuffers": (i32, [ptr]),
    }
    functions = dict(api.functions)
    for name, (result, arguments) in prototypes.items():
        function = getattr(kernel32, name)
        function.restype, function.argtypes = result, arguments
        functions[name] = function
    return Win32API(ffi, functions, api.structs)


@dataclass(frozen=True)
class DirectoryScope:
    path: str
    read_set: object


@dataclass(frozen=True)
class JournalBinding:
    physical: PhysicalSnapshot
    snapshot: DirectoryScope
    journal_identity: FileIdentity


@dataclass
class GateAttempt:
    token: object
    binding: JournalBinding
    handle: object = None
    stream: object = None
    journal: object = None
    failure: str | None = None


def _need(condition, reason):
    if not condition:
        raise PersistenceUnconfirmed(reason)


def gate_name(physical):
    _need(type(physical) is PhysicalSnapshot, "exact_physical_key_required")
    physical.wire()
    return f"{physical.volume:016x}-{physical.file_id}.journal"


def _prefixes(path):
    _absolute_local_path(path)
    return tuple([path[:3]] + [path[:3] + "\\".join(path[3:].split("\\")[:n])
        for n in range(1, len(path[3:].split("\\")) + 1)]) if len(path) > 3 else (path,)


def _check_scope(primitives, scope):
    _need(type(scope) is DirectoryScope and type(scope.read_set) is ReadSet,
          "exact_retained_directory_scope_required")
    owned = scope.read_set
    _need(any(item is owned for item in primitives.read_sets) and not owned.unconfirmed
          and not owned.released and not owned.worker_reserved, "directory_scope_not_owned")
    paths = _prefixes(scope.path)
    _need(len(paths) == len(owned.members) == len(owned.identities) <= 128,
          "entire_directory_ancestor_chain_required")
    for path, handle, expected in zip(paths, owned.members, owned.identities):
        actual = primitives.identity(handle)
        _need(type(expected) is FileIdentity and actual == expected and actual.directory
              and actual.final_path.casefold() == ("\\\\?\\" + path).casefold(),
              "directory_identity_or_final_path_changed")
    return owned.identities[-1]


class WindowsJournalStream:
    """Synchronous retained-handle stream. Flush latency is not hard-bounded.

    No destructor closes ownership. After uncertain I/O the exclusive handle is
    retained, even if bytes are readable. Only the registry's clean release may
    close it; process teardown is an external supervisor responsibility.
    """
    def __init__(self, primitives, handle, expected, check_ancestors):
        self.primitives, self.handle, self.expected = primitives, handle, expected
        self.check_ancestors = check_ancestors
        self.poisoned = False
        self.write_revision = 0
        self._lock = RLock()
        self.calls = []

    def identity(self):
        try:
            _need(not self.poisoned, "native_journal_poisoned")
            self.check_ancestors()
            actual = self.primitives.identity(self.handle)
            expected = self.expected
            _need(type(actual) is FileIdentity and not actual.directory and actual.links == 1
                  and 0 <= actual.size <= MAX_JOURNAL and actual.volume_serial == expected.volume_serial
                  and actual.file_id == expected.file_id and actual.final_path == expected.final_path,
                  "native_journal_identity_changed")
            return actual.volume_serial, actual.file_id, actual.final_path
        except BaseException:
            self.poisoned = True
            raise

    def _call(self, name, *args):
        try:
            self.identity()
            value = self.primitives.api.call(name, self.primitives._owned(self.handle), *args)
            self.calls.append((name, bool(value)))
            if not value:
                raise OSError(self.primitives.api.ffi.get_last_error(), name + " unconfirmed")
            self.identity()
            return value
        except BaseException:
            self.poisoned = True
            raise

    def seek(self, offset):
        _need(type(offset) is int and 0 <= offset <= MAX_JOURNAL, "journal_seek_bound")
        with self._lock:
            ffi = self.primitives.api.ffi
            actual = ffi.c_int64()
            try:
                self._call("SetFilePointerEx", offset, ffi.byref(actual), FILE_BEGIN)
                _need(actual.value == offset, "journal_seek_result")
                return offset
            except BaseException:
                self.poisoned = True
                raise

    def read(self, count):
        _need(type(count) is int and 0 < count <= MAX_CHUNK, "journal_read_bound")
        with self._lock:
            ffi = self.primitives.api.ffi
            buffer, actual = ffi.create_string_buffer(count), ffi.c_uint32()
            try:
                self._call("ReadFile", buffer, count, ffi.byref(actual), None)
                _need(type(actual.value) is int and 0 <= actual.value <= count, "journal_read_length")
                return bytes(buffer.raw[:actual.value])
            except BaseException:
                self.poisoned = True
                raise

    def write(self, payload):
        _need(type(payload) is bytes and 0 < len(payload) <= MAX_CHUNK, "journal_write_bound")
        with self._lock:
            self.write_revision += 1
            ffi = self.primitives.api.ffi
            buffer, actual = ffi.create_string_buffer(payload, len(payload)), ffi.c_uint32()
            try:
                self._call("WriteFile", buffer, len(payload), ffi.byref(actual), None)
                _need(type(actual.value) is int and 0 < actual.value <= len(payload), "journal_write_length")
                return actual.value
            except BaseException:
                self.poisoned = True
                raise

    def flush(self):
        # There is no Python buffering in this stream. The RetainedJournal sync
        # callback below performs the actual Windows flush, not this method.
        self.identity()

    def sync(self):
        with self._lock:
            self._call("FlushFileBuffers")
            return True


class ConfirmedWindowsJournal(RetainedJournal):
    """Retains only the latest exact successful confirmation for release."""
    def __init__(self, stream):
        expected = stream.identity()
        super().__init__(stream, lambda current: current.identity(), expected,
                         lambda current: current.sync())
        self.confirmed_bytes = None
        self.confirmed_revision = None

    def append_confirmed(self, before, frame):
        self.confirmed_bytes = self.confirmed_revision = None
        after = super().append_confirmed(before, frame)
        self.confirmed_bytes, self.confirmed_revision = after, self._stream.write_revision
        return after

    def confirm_current(self, expected):
        self.confirmed_bytes = self.confirmed_revision = None
        after = super().confirm_current(expected)
        self.confirmed_bytes, self.confirmed_revision = after, self._stream.write_revision
        return after

    def confirmed_clean_head(self):
        _need(not self._poisoned and not self._stream.poisoned
              and self.confirmed_revision == self._stream.write_revision
              and self.confirmed_bytes is not None, "native_clean_confirmation_absent")
        rows, head = decode_journal(self.confirmed_bytes)
        _need(rows[-1]["phase"] in ("INITIALIZED", "CLEARED"), "native_head_not_clean")
        return head


class WindowsGateRegistry(GeneratedGateRegistry):
    """One trusted registry root; no profile supplies a second root or binding.

    Existing journals must be created/identified by the trusted generated
    bootstrap. OPEN_EXISTING never turns an arbitrary empty file into creation
    authority. Parent directories stay retained through the registry lifetime.
    """
    def __init__(self, primitives, registry_scope, confirm_creation, confirm_restart):
        super().__init__(confirm_creation, confirm_restart)
        self.primitives, self.registry_scope = primitives, registry_scope
        self.registry_identity = _check_scope(primitives, registry_scope)
        self.bindings, self.attempts = {}, {}

    def bind_snapshot(self, binding):
        _need(type(binding) is JournalBinding and type(binding.journal_identity) is FileIdentity,
              "exact_journal_binding_required")
        observed = _check_scope(self.primitives, binding.snapshot)
        _need(binding.physical == PhysicalSnapshot(observed.volume_serial, observed.file_id.hex()),
              "snapshot_physical_binding_mismatch")
        expected = binding.journal_identity
        path = self.registry_scope.path.rstrip("\\") + "\\" + gate_name(binding.physical)
        _absolute_local_path(path)
        _need(not expected.directory and expected.links == 1 and len(expected.file_id) == 16
              and 0 <= expected.size <= MAX_JOURNAL
              and expected.final_path.casefold() == ("\\\\?\\" + path).casefold(),
              "fixed_journal_identity_path_required")
        with self._lock:
            _need(binding.physical not in self.bindings and binding.physical not in self._held,
                  "duplicate_physical_registration_refused")
            self.bindings[binding.physical] = binding

    def _ancestors(self, binding):
        _need(_check_scope(self.primitives, self.registry_scope) == self.registry_identity,
              "registry_root_identity_changed")
        actual = _check_scope(self.primitives, binding.snapshot)
        _need(binding.physical == PhysicalSnapshot(actual.volume_serial, actual.file_id.hex()),
              "snapshot_identity_changed")

    def acquire(self, physical):
        with self._lock:
            _need(physical in self.bindings, "physical_snapshot_not_registered")
            binding = self.bindings[physical]
            token = super().acquire(physical)
            attempt = GateAttempt(token, binding)
            self.attempts[physical] = attempt
        try:
            self._ancestors(binding)
            path = self.registry_scope.path.rstrip("\\") + "\\" + gate_name(physical)
            api = self.primitives.api
            value = api.call("CreateFileW", path, GENERIC_READ | GENERIC_WRITE, 0, None,
                             OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_WRITE_THROUGH, None)
            if value in (None, 0, api.ffi.c_void_p(-1).value):
                error = api.ffi.get_last_error()
                if error in (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION):
                    # No journal handle was returned and no content was read or
                    # changed. Persistent ancestor handles belong to bootstrap.
                    with self._lock:
                        self.require(physical, token)
                        del self._held[physical]
                        del self.attempts[physical]
                    raise ReservationRefused("native_physical_snapshot_busy")
                raise OSError(error, "Exclusive journal open unconfirmed")
            attempt.handle = self.primitives._retain(value, "reservation-journal")
            stream = WindowsJournalStream(self.primitives, attempt.handle, binding.journal_identity,
                                          lambda: self._ancestors(binding))
            attempt.stream = stream
            attempt.journal = ConfirmedWindowsJournal(stream)
            return token
        except BaseException as error:
            attempt.failure = type(error).__name__
            # Partial acquisition stays accessible to the trusted bootstrap via
            # attempts. No destructor or guessed PID can clear it.
            raise

    def open_journal(self, physical):
        with self._lock:
            attempt = self.attempts.get(physical)
            _need(attempt is not None and attempt.journal is not None and attempt.failure is None,
                  "exact_live_journal_attempt_required")
            self.require(physical, attempt.token)
            return attempt.journal

    def release(self, physical, token, clean_head):
        with self._lock:
            self.require(physical, token)
            attempt = self.attempts.get(physical)
            _need(attempt is not None and attempt.token is token and attempt.journal is not None
                  and attempt.failure is None, "exact_native_gate_release_required")
            try:
                actual_head = attempt.journal.confirmed_clean_head()
                _need(actual_head == clean_head,
                      "durable_clean_head_mismatch")
                self.primitives._close(attempt.handle)
                super().release(physical, token, clean_head)
                del self.attempts[physical]
            except BaseException as error:
                attempt.failure = type(error).__name__
                raise
