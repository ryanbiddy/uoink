"""Unexecuted Win32 private-pipe mechanics; no DLL, process or I/O at import."""
from dataclasses import dataclass, field
from contextlib import contextmanager
import math
from threading import RLock
from owned_generation_protocol import HEADER, MAX_BODY, BOOTSTRAP

PIPE_ACCESS_DUPLEX = 3
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
PIPE_REJECT_REMOTE_CLIENTS = 8
GENERIC_READ_WRITE = 0xC0000000
ERROR_IO_PENDING = 997
ERROR_OPERATION_ABORTED = 995
ERROR_BROKEN_PIPE = 109
ERROR_NOT_FOUND = 1168
WAIT_OBJECT_0 = 0
IO_CHUNK = 16384


class PipeRefusal(RuntimeError):
    pass


def declare_pipe_calls(api, kernel32):
    # Receives the same future verified FFI/system-DLL pair as the primitives.
    ffi = api.ffi
    class OVERLAPPED(ffi.Structure):
        # The offset union occupies eight bytes on x64. Pipe offsets are zero.
        _fields_ = [("internal", ffi.c_size_t), ("internal_high", ffi.c_size_t),
                    ("offset_union", ffi.c_uint64), ("event", ffi.c_void_p)]
    if ffi.sizeof(OVERLAPPED) != 32:
        raise PipeRefusal("overlapped_x64_layout")
    PTR, U32, BOOL = ffi.c_void_p, ffi.c_uint32, ffi.c_int32
    prototypes = {
        "CreateNamedPipeW": (PTR, [ffi.c_wchar_p, U32, U32, U32, U32, U32, U32, PTR]),
        "ConnectNamedPipe": (BOOL, [PTR, PTR]),
        "CreateEventW": (PTR, [PTR, BOOL, BOOL, ffi.c_wchar_p]),
        "ReadFile": (BOOL, [PTR, PTR, U32, ffi.POINTER(U32), PTR]),
        "WriteFile": (BOOL, [PTR, PTR, U32, ffi.POINTER(U32), PTR]),
        "GetOverlappedResult": (BOOL, [PTR, PTR, ffi.POINTER(U32), BOOL]),
        "CancelIoEx": (BOOL, [PTR, PTR]),
        "GetFileType": (U32, [PTR]),
        "GetHandleInformation": (BOOL, [PTR, ffi.POINTER(U32)]),
        "SetHandleInformation": (BOOL, [PTR, U32, U32]),
    }
    for name, (result, arguments) in prototypes.items():
        function = getattr(kernel32, name)
        function.restype, function.argtypes = result, arguments
        api.functions[name] = function
    api.structs["OVERLAPPED"] = OVERLAPPED


@dataclass
class PendingIO:
    handle: object
    overlapped: object = None
    event: object = None
    buffer: object = None
    submitted: bool = False
    complete: bool = False
    cancelled: bool = False
    unconfirmed: bool = False
    cancellation_attempted: bool = False
    terminal_error: int | None = None


@dataclass
class PipePair:
    server: object = None
    client: object = None
    operations: list = field(default_factory=list)
    unconfirmed: bool = False
    worker: object = None
    read_set: object = None
    role: str = "controller"
    closed: bool = False
    active: bool = False
    lock: object = field(default_factory=RLock)
    forced_stop_attempted: bool = False
    forced_process_stop_observed: bool = False
    forced_stop_error_type: str | None = None


class PrivatePipeController:
    def __init__(self, primitives, monotonic):
        self.primitives = primitives
        self.clock = monotonic  # Fixed trusted bootstrap clock, not frame data.
        self.pairs = []

    @contextmanager
    def _frame_operation(self, pair):
        if not any(item is pair for item in self.pairs):
            raise PipeRefusal("owned_pipe_pair_required")
        with pair.lock:
            if pair.active or pair.closed or pair.unconfirmed:
                raise PipeRefusal("pipe_frame_operation_unavailable")
            pair.active = True
        try:
            yield
        except BaseException:
            # A failure may follow a completed earlier chunk. Never permit a
            # later frame on a possibly desynchronized byte stream.
            self._quarantine(pair)
            raise
        finally:
            with pair.lock:
                pair.active = False

    def _retire_completed(self, pair, operation):
        if (not operation.complete or (operation.event is not None
                and (not operation.event.closed or operation.event.unconfirmed))):
            raise PipeRefusal("pipe_operation_still_owned")
        operation.buffer = None
        pair.operations[:] = [item for item in pair.operations if item is not operation]

    def _remaining_ms(self, expires):
        now = self.clock()
        if (type(expires) not in (int, float) or not math.isfinite(expires)
                or type(now) not in (int, float) or not math.isfinite(now)):
            raise PipeRefusal("clock_bound")
        remaining = expires - now
        if not 0 < remaining <= 30:
            raise PipeRefusal("operation_deadline")
        return min(30000, max(1, int(math.ceil(remaining * 1000))))

    def _new_operation(self, pair, handle, buffer=None):
        p, ffi = self.primitives, self.primitives.api.ffi
        operation = PendingIO(handle=handle, buffer=buffer)
        pair.operations.append(operation)
        try:
            operation.event = p._retain(p.api.call("CreateEventW", None, 1, 0, None), "ipc-event")
            operation.overlapped = p.api.structure("OVERLAPPED")
            operation.overlapped.event = p._owned(operation.event)
            return operation
        except BaseException as original:
            self._quarantine(pair, operation)
            try:
                # No I/O has been submitted. Close the event if its exact
                # owner was recorded, then retire only that confirmed owner.
                if operation.event is not None:
                    p._close(operation.event)
                operation.complete = True
                self._retire_completed(pair, operation)
            except BaseException as error:
                original.add_note("Partial pipe event remains owned: " + type(error).__name__)
            raise

    def _quarantine(self, pair, operation=None):
        pair.unconfirmed = True
        if operation is not None:
            operation.unconfirmed = True
        if pair.read_set is not None:
            pair.read_set.unconfirmed = True
        if pair.worker is not None:
            pair.worker.unconfirmed = True
            if pair.role == "controller" and not pair.forced_stop_attempted:
                pair.forced_stop_attempted = True
                try:
                    # Clean shutdown refuses an uncertain worker. This distinct
                    # bounded route stops the retained process/job, even when
                    # quarantined. A process wait alone is not a clean-release
                    # receipt, so every uncertainty flag and buffer stays held.
                    pair.forced_process_stop_observed = (
                        self.primitives._stop_partial_worker(pair.worker, 5000) is True)
                except BaseException as error:
                    pair.forced_stop_error_type = type(error).__name__

    def _cancel_and_confirm(self, operation):
        p, ffi = self.primitives, self.primitives.api.ffi
        if operation.complete or not operation.submitted:
            return True
        if operation.cancellation_attempted:
            return False
        operation.cancellation_attempted = True
        cancelled = p.api.call("CancelIoEx", p._owned(operation.handle), ffi.byref(operation.overlapped))
        error = ffi.get_last_error()
        if not cancelled and error != ERROR_NOT_FOUND:
            return False
        waited = p.api.call("WaitForSingleObject", p._owned(operation.event), 1000)
        if waited != WAIT_OBJECT_0:
            return False
        count = ffi.c_uint32()
        done = p.api.call("GetOverlappedResult", p._owned(operation.handle), ffi.byref(operation.overlapped), ffi.byref(count), 0)
        error = ffi.get_last_error()
        if done or error in (ERROR_OPERATION_ABORTED, ERROR_BROKEN_PIPE):
            # A waited exact operation may finish with a broken-pipe failure
            # after peer termination. That is terminal, not cancellation or
            # successful I/O. Keep enclosing quarantine and the raised error.
            operation.complete = True
            operation.cancelled = not bool(done) and error == ERROR_OPERATION_ABORTED
            operation.terminal_error = None if done else error
            return True
        return False

    def _finish(self, pair, operation, expires):
        p, ffi = self.primitives, self.primitives.api.ffi
        try:
            waited = p.api.call("WaitForSingleObject", p._owned(operation.event), self._remaining_ms(expires))
            if waited != WAIT_OBJECT_0:
                raise PipeRefusal("overlapped_completion_not_observed")
            count = ffi.c_uint32()
            p.api.checked("GetOverlappedResult", p._owned(operation.handle), ffi.byref(operation.overlapped), ffi.byref(count), 0)
            operation.complete = True
            p._close(operation.event)
            self._retire_completed(pair, operation)
            return int(count.value)
        except BaseException as original:
            self._quarantine(pair, operation)
            try:
                if self._cancel_and_confirm(operation):
                    if not operation.event.closed and not operation.event.unconfirmed:
                        p._close(operation.event)
                    self._retire_completed(pair, operation)
                else:
                    original.add_note("Exact pipe operation cancellation is unconfirmed; owners retained")
            except BaseException as cleanup:
                original.add_note("Pipe cleanup raised; owners retained: " + type(cleanup).__name__)
            raise

    def create_pair(self, random_name_bytes, expires):
        # Entropy must be generated by the future trusted bootstrap. This value
        # is not a provider credential and is never interpreted as a user path.
        if type(random_name_bytes) is not bytes or len(random_name_bytes) != 32:
            raise PipeRefusal("private_pipe_name_material")
        self._remaining_ms(expires)
        p, ffi = self.primitives, self.primitives.api.ffi
        name = "\\\\.\\pipe\\uoink-owned-" + random_name_bytes.hex()
        pair = PipePair()
        self.pairs.append(pair)
        operation = None
        try:
            pair.server = p._retain(p.api.call("CreateNamedPipeW", name,
                PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
                PIPE_REJECT_REMOTE_CLIENTS, 1, 32768, 32768, 5000, None), "ipc-server")
            operation = self._new_operation(pair, pair.server)
            operation.submitted = True
            connected = p.api.call("ConnectNamedPipe", p._owned(pair.server), ffi.byref(operation.overlapped))
            error = ffi.get_last_error()
            # No client existed before this call. An already-connected or
            # unexpected synchronous client is refused as a foreign race.
            if connected or error != ERROR_IO_PENDING:
                raise PipeRefusal("unexpected_pipe_connection")
            pair.client = p._retain(p.api.call("CreateFileW", name, GENERIC_READ_WRITE, 0, None, 3,
                                               FILE_FLAG_OVERLAPPED, None), "ipc-client")
            self._finish(pair, operation, expires)
            return pair
        except BaseException as original:
            self._quarantine(pair, operation)
            if operation is not None and not operation.complete:
                try:
                    if not self._cancel_and_confirm(operation):
                        original.add_note("Pipe connect cancellation unconfirmed; owners retained")
                except BaseException as error:
                    original.add_note("Pipe connect cleanup raised: " + type(error).__name__)
            raise

    def attach_to_suspended_worker(self, pair, read_set, executable, arguments, working_directory, environment):
        if not any(item is pair for item in self.pairs) or pair.unconfirmed or pair.worker is not None:
            raise PipeRefusal("fresh_owned_pipe_pair_required")
        pair.read_set = read_set
        try:
            worker = self.primitives.create_suspended_worker(read_set, executable, arguments, working_directory,
                environment, inherited_control_handles=(pair.client,), include_control_handle_argument=True)
            pair.worker = worker
            # The successful CreateProcess inherited its own duplicate. Close
            # this original parent client endpoint before any future resume.
            self.primitives._close(pair.client)
            return worker
        except BaseException as original:
            self._quarantine(pair)
            if pair.worker is not None and not pair.forced_process_stop_observed:
                original.add_note("Suspended pipe worker stop unconfirmed; owners retained")
            raise

    def adopt_inherited_client(self, value):
        # Called only by the fixed trusted child bootstrap, before parsing any
        # frame. A supplied integer or FILE_TYPE_PIPE check alone is not proof
        # of provenance. No arbitrary handle adoption is exposed over IPC.
        if type(value) is not int or not 0 < value < (1 << 64) - 1 or self.pairs:
            raise PipeRefusal("single_inherited_endpoint_required")
        p, ffi = self.primitives, self.primitives.api.ffi
        pair = PipePair(role="worker")
        self.pairs.append(pair)
        try:
            pair.server = p._retain(value, "ipc-inherited-client")
            if p.api.call("GetFileType", p._owned(pair.server)) != 3:
                raise PipeRefusal("inherited_endpoint_not_pipe")
            flags = ffi.c_uint32()
            p.api.checked("GetHandleInformation", p._owned(pair.server), ffi.byref(flags))
            p.api.checked("SetHandleInformation", p._owned(pair.server), 1, 0)
            p.api.checked("GetHandleInformation", p._owned(pair.server), ffi.byref(flags))
            if flags.value & 1:
                raise PipeRefusal("inherited_endpoint_still_inheritable")
            return pair
        except BaseException:
            self._quarantine(pair)
            raise

    def _io(self, pair, writing, content_or_size, expires):
        if not any(item is pair for item in self.pairs) or pair.unconfirmed or pair.closed or not pair.active:
            raise PipeRefusal("owned_live_pipe_required")
        p, ffi = self.primitives, self.primitives.api.ffi
        if writing:
            if type(content_or_size) is not bytes or not 0 < len(content_or_size) <= IO_CHUNK:
                raise PipeRefusal("write_chunk_bound")
            buffer = ffi.create_string_buffer(content_or_size, len(content_or_size))
            requested = len(content_or_size)
        else:
            if type(content_or_size) is not int or not 0 < content_or_size <= IO_CHUNK:
                raise PipeRefusal("read_chunk_bound")
            requested = content_or_size
            buffer = ffi.create_string_buffer(requested)
        self._remaining_ms(expires)
        operation = self._new_operation(pair, pair.server, buffer)
        try:
            operation.submitted = True
            done = p.api.call("WriteFile" if writing else "ReadFile", p._owned(pair.server), buffer,
                              requested, None, ffi.byref(operation.overlapped))
            error = ffi.get_last_error()
            if not done and error != ERROR_IO_PENDING:
                raise PipeRefusal("pipe_submission_failed")
            count = self._finish(pair, operation, expires)
            if not 0 < count <= requested:
                raise PipeRefusal("pipe_completion_count")
            return count if writing else bytes(buffer.raw[:count])
        except BaseException as original:
            self._quarantine(pair, operation)
            if not operation.complete:
                try:
                    if not self._cancel_and_confirm(operation):
                        original.add_note("Pipe I/O remains unconfirmed; buffers retained")
                except BaseException as error:
                    original.add_note("Pipe cancellation raised: " + type(error).__name__)
            raise

    def write_bytes(self, pair, data, expires):
        if type(data) is not bytes or not 0 < len(data) <= HEADER.size + MAX_BODY + 32:
            raise PipeRefusal("frame_write_bound")
        with self._frame_operation(pair):
            offset = 0
            while offset < len(data):
                offset += self._io(pair, True, data[offset:offset + IO_CHUNK], expires)

    def _read_exact(self, pair, size, expires):
        if type(size) is not int or not 0 < size <= HEADER.size + MAX_BODY + 32:
            raise PipeRefusal("frame_read_bound")
        chunks, received = [], 0
        while received < size:
            data = self._io(pair, False, min(IO_CHUNK, size - received), expires)
            received += len(data)
            chunks.append(data)
        return b"".join(chunks)

    def read_frame(self, pair, expires):
        with self._frame_operation(pair):
            header = self._read_exact(pair, HEADER.size, expires)
            _, _, _, length = HEADER.unpack(header)
            if not 0 < length <= MAX_BODY:
                self._quarantine(pair)
                raise PipeRefusal("frame_declared_length")
            return header + self._read_exact(pair, length + 32, expires)

    def read_private_bootstrap(self, pair, expires):
        if pair.role != "worker":
            raise PipeRefusal("bootstrap_reader_must_be_inherited_worker")
        with self._frame_operation(pair):
            return self._read_exact(pair, BOOTSTRAP.size, expires)

    def retire_endpoint(self, pair):
        # Child retirement means only this endpoint is closed. Only the
        # controller's retained process/job observation proves worker death.
        if not any(item is pair for item in self.pairs):
            raise PipeRefusal("owned_pipe_pair_required")
        if pair.role == "controller" and pair.worker is not None:
            worker = pair.worker
            if (not any(item is worker for item in self.primitives.workers)
                    or worker.unconfirmed or not worker.quiescent):
                raise PipeRefusal("controller_requires_observed_worker_quiescence")
        with self._frame_operation(pair):
            if pair.operations:
                raise PipeRefusal("pending_pipe_operations_retained")
            try:
                for handle in (pair.client, pair.server):
                    if handle is not None and not handle.closed:
                        self.primitives._close(handle)
                pair.closed = True
            except BaseException:
                self._quarantine(pair)
                raise
