"""UNEXECUTED Win32 primitive source, not a complete snapshot/kernel port.

No ctypes import, DLL load, filesystem operation or process creation occurs at
module import. A trusted future bootstrap must supply an exact reviewed ctypes
module and kernel32 binding explicitly. The public real entry point stays shut.
"""
from dataclasses import dataclass, field


class KernelUnavailable(RuntimeError):
    pass


class KernelUnconfirmed(RuntimeError):
    pass


def real_kernel_port(*args, **kwargs):
    # No flag, profile record or caller-created dataclass enables this entry.
    raise KernelUnavailable("Real snapshot namespace, worker and recovery admission is absent")


# Values/declarations are bound to Windows SDK 10.0.26100.0 in SDK-BINDINGS.
GENERIC_READ = 0x80000000
FILE_READ_ATTRIBUTES = 0x80
FILE_SHARE_READ = 1
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_STANDARD_INFO_CLASS = 1
FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
FILE_ID_INFO_CLASS = 18
DUPLICATE_SAME_ACCESS = 2
CREATE_SUSPENDED = 0x4
CREATE_UNICODE_ENVIRONMENT = 0x400
EXTENDED_STARTUPINFO_PRESENT = 0x80000
STARTF_USESHOWWINDOW = 1
SW_HIDE = 0
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x20002
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_BASIC_ACCOUNTING_CLASS = 1
JOB_EXTENDED_LIMIT_CLASS = 9
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
WAIT_FAILED = 0xFFFFFFFF
ERROR_INSUFFICIENT_BUFFER = 122
FORBIDDEN_LIVE = r"C:\Users\hello\AppData\Local\Uoink\index.db"


def declare_bindings(ffi, kernel32):
    """Declare actual ABI layout on a supplied module/DLL; not called here.

    The future bootstrap must load the system DLL with use_last_error=True and
    bind the exact interpreter/ABI before calling this. Supplying objects is an
    injection seam, not authorization, sandboxing or provenance verification.
    """
    if ffi.sizeof(ffi.c_void_p) != 8 or ffi.sizeof(ffi.c_wchar) != 2:
        raise KernelUnavailable("Only the proposed Windows x64 ABI is represented")
    U8, U16, U32, U64 = ffi.c_uint8, ffi.c_uint16, ffi.c_uint32, ffi.c_uint64
    I32, I64, SIZE, PTR = ffi.c_int32, ffi.c_int64, ffi.c_size_t, ffi.c_void_p
    WCHARP = ffi.c_wchar_p

    class FILETIME(ffi.Structure):
        _fields_ = [("low", U32), ("high", U32)]

    class FILE_STANDARD_INFO(ffi.Structure):
        _fields_ = [("allocation", I64), ("size", I64), ("links", U32), ("delete_pending", U8), ("directory", U8)]

    class FILE_ATTRIBUTE_TAG_INFO(ffi.Structure):
        _fields_ = [("attributes", U32), ("reparse_tag", U32)]

    class FILE_ID_INFO(ffi.Structure):
        _fields_ = [("volume", U64), ("file_id", U8 * 16)]

    class STARTUPINFOW(ffi.Structure):
        _fields_ = [("cb", U32), ("reserved", WCHARP), ("desktop", WCHARP), ("title", WCHARP),
                    ("x", U32), ("y", U32), ("x_size", U32), ("y_size", U32),
                    ("x_chars", U32), ("y_chars", U32), ("fill", U32), ("flags", U32),
                    ("show", U16), ("reserved_size", U16), ("reserved_bytes", PTR),
                    ("stdin", PTR), ("stdout", PTR), ("stderr", PTR)]

    class STARTUPINFOEXW(ffi.Structure):
        _fields_ = [("startup", STARTUPINFOW), ("attributes", PTR)]

    class PROCESS_INFORMATION(ffi.Structure):
        _fields_ = [("process", PTR), ("thread", PTR), ("pid", U32), ("tid", U32)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ffi.Structure):
        _fields_ = [("process_time", I64), ("job_time", I64), ("flags", U32),
                    ("minimum_working_set", SIZE), ("maximum_working_set", SIZE),
                    ("active_process_limit", U32), ("affinity", SIZE), ("priority", U32), ("scheduling", U32)]

    class IO_COUNTERS(ffi.Structure):
        _fields_ = [(name, U64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ffi.Structure):
        _fields_ = [("basic", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("io", IO_COUNTERS),
                    ("process_memory", SIZE), ("job_memory", SIZE), ("peak_process_memory", SIZE), ("peak_job_memory", SIZE)]

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ffi.Structure):
        _fields_ = [("user_time", I64), ("kernel_time", I64), ("period_user_time", I64), ("period_kernel_time", I64),
                    ("page_faults", U32), ("total_processes", U32), ("active_processes", U32), ("terminated_processes", U32)]

    structs = {cls.__name__: cls for cls in (FILETIME, FILE_STANDARD_INFO, FILE_ATTRIBUTE_TAG_INFO, FILE_ID_INFO,
              STARTUPINFOW, STARTUPINFOEXW, PROCESS_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
              JOBOBJECT_BASIC_ACCOUNTING_INFORMATION)}
    expected_sizes = {"FILETIME": 8, "FILE_STANDARD_INFO": 24, "FILE_ATTRIBUTE_TAG_INFO": 8, "FILE_ID_INFO": 24,
                      "STARTUPINFOW": 104, "STARTUPINFOEXW": 112, "PROCESS_INFORMATION": 24,
                      "JOBOBJECT_EXTENDED_LIMIT_INFORMATION": 144, "JOBOBJECT_BASIC_ACCOUNTING_INFORMATION": 48}
    if any(ffi.sizeof(structs[name]) != size for name, size in expected_sizes.items()):
        raise KernelUnavailable("Win32 ABI structure size mismatch")
    prototypes = {
        "CreateFileW": (PTR, [WCHARP, U32, U32, PTR, U32, U32, PTR]),
        "GetFinalPathNameByHandleW": (U32, [PTR, PTR, U32, U32]),
        "GetFileInformationByHandleEx": (I32, [PTR, I32, PTR, U32]),
        "CloseHandle": (I32, [PTR]),
        "GetCurrentProcess": (PTR, []),
        "DuplicateHandle": (I32, [PTR, PTR, PTR, ffi.POINTER(PTR), U32, I32, U32]),
        "CreateJobObjectW": (PTR, [PTR, WCHARP]),
        "SetInformationJobObject": (I32, [PTR, I32, PTR, U32]),
        "QueryInformationJobObject": (I32, [PTR, I32, PTR, U32, ffi.POINTER(U32)]),
        "AssignProcessToJobObject": (I32, [PTR, PTR]),
        "TerminateJobObject": (I32, [PTR, U32]),
        "TerminateProcess": (I32, [PTR, U32]),
        "WaitForSingleObject": (U32, [PTR, U32]),
        "GetProcessTimes": (I32, [PTR, ffi.POINTER(FILETIME), ffi.POINTER(FILETIME), ffi.POINTER(FILETIME), ffi.POINTER(FILETIME)]),
        "ResumeThread": (U32, [PTR]),
        "InitializeProcThreadAttributeList": (I32, [PTR, U32, U32, ffi.POINTER(SIZE)]),
        "UpdateProcThreadAttribute": (I32, [PTR, U32, SIZE, PTR, SIZE, PTR, PTR]),
        "DeleteProcThreadAttributeList": (None, [PTR]),
        "CreateProcessW": (I32, [WCHARP, PTR, PTR, PTR, I32, U32, PTR, WCHARP, PTR, ffi.POINTER(PROCESS_INFORMATION)]),
    }
    functions = {}
    for name, (result, arguments) in prototypes.items():
        function = getattr(kernel32, name)
        function.restype, function.argtypes = result, arguments
        functions[name] = function
    return Win32API(ffi, functions, structs)


class Win32API:
    def __init__(self, ffi, functions, structs):
        self.ffi, self.functions, self.structs = ffi, functions, structs

    def call(self, name, *args):
        # Names are selected only by the fixed methods below, not IPC input.
        return self.functions[name](*args)

    def checked(self, name, *args):
        if not self.call(name, *args):
            raise OSError(self.ffi.get_last_error(), name + " failed")

    def structure(self, name):
        return self.structs[name]()


@dataclass(frozen=True)
class FileIdentity:
    final_path: str
    volume_serial: int
    file_id: bytes
    size: int
    links: int
    directory: bool


def same_directory_identity(actual, expected):
    """Retained directory identity; its observed byte length may change.

    The native identity query still rejects reparse points and pending deletion.
    Keep FileIdentity equality intact for regular files and recorded evidence.
    """
    return (type(actual) is FileIdentity and type(expected) is FileIdentity
            and actual.directory is True and expected.directory is True
            and type(actual.size) is int and 0 <= actual.size < 1 << 63
            and type(expected.size) is int and 0 <= expected.size < 1 << 63
            and actual.final_path == expected.final_path
            and actual.volume_serial == expected.volume_serial
            and actual.file_id == expected.file_id and actual.links == expected.links)


@dataclass
class HandleRecord:
    value: int
    kind: str
    closed: bool = False
    unconfirmed: bool = False


@dataclass
class ReadSet:
    members: list = field(default_factory=list)
    identities: list = field(default_factory=list)
    unconfirmed: bool = False
    worker_reserved: bool = False
    released: bool = False
    # This never turns True in the proposed primitive implementation.
    complete_namespace_protection: bool = False


@dataclass
class WorkerRecord:
    job: object = None
    process: object = None
    thread: object = None
    inherited_copies: list = field(default_factory=list)
    read_set: object = None
    creation_time: int | None = None
    assigned: bool = False
    resumed: bool = False
    shutdown_started: bool = False
    quiescent: bool = False
    unconfirmed: bool = False
    creation_info: object = None
    child_read_handles: tuple = ()
    child_control_handle: int | None = None


def _absolute_local_path(path):
    # Lexical restriction only. No resolve/stat/query happens in this helper.
    if type(path) is str and path.casefold() == FORBIDDEN_LIVE.casefold():
        raise KernelUnavailable("Fixed live-index path is prohibited")
    if (type(path) is not str or not 3 <= len(path) <= 4096 or path[1:3] != ":\\"
            or path[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            or any(ch in path for ch in ('\x00', '/', '"', '*', '?')) or ':' in path[2:]
            or any(ord(ch) < 32 for ch in path)):
        raise KernelUnavailable("Fixed local DOS path required")
    if len(path) == 3:
        return path
    parts = path[3:].split("\\")
    if any(not part or part in (".", "..") or part.endswith((" ", ".")) for part in parts):
        raise KernelUnavailable("Ambiguous path component refused")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        prefix + suffix for prefix in ("COM", "LPT") for suffix in "123456789¹²³"}
    if any(part.split(".", 1)[0].upper() in reserved for part in parts):
        raise KernelUnavailable("DOS device component refused")
    return path


def _quote_argument(value):
    # Windows CRT command line quoting, without invoking a shell.
    if type(value) is not str or '\x00' in value or len(value) > 4096:
        raise KernelUnavailable("Worker argument refused")
    result, slashes = '"', 0
    for char in value:
        if char == "\\":
            slashes += 1
        elif char == '"':
            result += "\\" * (slashes * 2 + 1) + '"'
            slashes = 0
        else:
            result += "\\" * slashes + char
            slashes = 0
    return result + "\\" * (slashes * 2) + '"'


def _environment_block(pairs):
    # An explicit bootstrap allowlist, never inherited os.environ or credentials.
    required = {"TORCH_DEVICE_BACKEND_AUTOLOAD": "0", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYANNOTE_METRICS_ENABLED": "0",
                "IG_FORBIDDEN_LIVE": FORBIDDEN_LIVE}
    allowed = set(required) | {"SystemRoot", "WINDIR", "TEMP", "TMP"}
    if type(pairs) is not dict or set(pairs) != allowed or any(pairs.get(k) != v for k, v in required.items()):
        raise KernelUnavailable("Exact scrubbed worker environment required")
    for name in allowed - set(required):
        _absolute_local_path(pairs[name])
    block = "\x00".join(name + "=" + pairs[name] for name in sorted(pairs, key=str.upper)) + "\x00\x00"
    if len(block) > 32767:
        raise KernelUnavailable("Worker environment size refused")
    return block


class OwnedWin32Primitives:
    """Concrete handle/process mechanics; no complete acquire_read capability.

    A trusted single-threaded bootstrap owns this object. HandleRecord and
    WorkerRecord instances are also tracked by identity; external lookalikes
    do not authorize operations. Recovery after process death is not supplied.
    """

    def __init__(self, api):
        self.api = api
        self.handles = []
        self.workers = []
        self.read_sets = []

    def _retain(self, value, kind):
        invalid = self.api.ffi.c_void_p(-1).value
        if value is None or value == 0 or value == invalid:
            raise OSError(self.api.ffi.get_last_error(), kind + " returned an invalid handle")
        record = HandleRecord(value, kind)
        self.handles.append(record)
        return record

    def _owned(self, handle):
        if not any(item is handle for item in self.handles) or handle.closed or handle.unconfirmed:
            raise KernelUnconfirmed("Handle ownership is not confirmed")
        return handle.value

    def _close(self, handle):
        value = self._owned(handle)
        try:
            self.api.checked("CloseHandle", value)
        except BaseException:
            handle.unconfirmed = True
            raise
        handle.closed = True

    def _query(self, handle, kind, class_id):
        data = self.api.structure(kind)
        self.api.checked("GetFileInformationByHandleEx", self._owned(handle), class_id,
                         self.api.ffi.byref(data), self.api.ffi.sizeof(data))
        return data

    def identity(self, handle):
        ffi = self.api.ffi
        tags = self._query(handle, "FILE_ATTRIBUTE_TAG_INFO", FILE_ATTRIBUTE_TAG_INFO_CLASS)
        standard = self._query(handle, "FILE_STANDARD_INFO", FILE_STANDARD_INFO_CLASS)
        identity = self._query(handle, "FILE_ID_INFO", FILE_ID_INFO_CLASS)
        if tags.attributes & FILE_ATTRIBUTE_REPARSE_POINT or tags.reparse_tag or standard.delete_pending or standard.size < 0:
            raise KernelUnavailable("Reparse, pending deletion or invalid size refused")
        buffer = ffi.create_unicode_buffer(32768)
        length = self.api.call("GetFinalPathNameByHandleW", self._owned(handle), buffer, len(buffer), 0)
        if not 0 < length < len(buffer):
            raise KernelUnavailable("Final handle path is unavailable or oversized")
        return FileIdentity(buffer.value, int(identity.volume), bytes(identity.file_id), int(standard.size),
                            int(standard.links), bool(standard.directory))

    def pin_exact_members(self, expectations):
        """Open an explicit read set; NOT namespace protection or model approval.

        expectations are trusted proposed bootstrap inputs. This checks known
        identities, but cannot establish a loader's unknown future name set.
        """
        if type(expectations) is not tuple or not 1 <= len(expectations) <= 128:
            raise KernelUnavailable("Bounded exact read set required")
        read_set = ReadSet()
        self.read_sets.append(read_set)  # Retain partial acquisition immediately.
        try:
            seen = set()
            for path, expected in expectations:
                _absolute_local_path(path)
                if path.casefold() in seen or type(expected) is not FileIdentity:
                    raise KernelUnavailable("Read-set input identity refused")
                seen.add(path.casefold())
                access = FILE_READ_ATTRIBUTES if expected.directory else GENERIC_READ
                flags = FILE_FLAG_OPEN_REPARSE_POINT | (FILE_FLAG_BACKUP_SEMANTICS if expected.directory else 0)
                value = self.api.call("CreateFileW", path, access, FILE_SHARE_READ, None, OPEN_EXISTING, flags, None)
                handle = self._retain(value, "read-member")
                read_set.members.append(handle)
                actual = self.identity(handle)
                matched = (same_directory_identity(actual, expected) if expected.directory
                           else actual == expected)
                if not matched or (not actual.directory and actual.links != 1):
                    raise KernelUnavailable("Opened identity differs from the exact approved member")
                read_set.identities.append(actual)
            return read_set
        except BaseException:
            # Deliberately retain partial acquisition. Recovery/release requires
            # a separate owner decision; no destructor silently closes handles.
            read_set.unconfirmed = True
            raise

    def _duplicate_inheritable(self, handle):
        ffi = self.api.ffi
        duplicate = ffi.c_void_p()
        current = self.api.call("GetCurrentProcess")
        self.api.checked("DuplicateHandle", current, self._owned(handle), current,
                         ffi.byref(duplicate), 0, 1, DUPLICATE_SAME_ACCESS)
        return self._retain(duplicate.value, "inheritable-read-member")

    def _creation_time(self, process):
        values = [self.api.structure("FILETIME") for _ in range(4)]
        self.api.checked("GetProcessTimes", self._owned(process), *(self.api.ffi.byref(item) for item in values))
        return int(values[0].low) | int(values[0].high) << 32

    def _adopt_process_outputs(self, worker):
        # The mutable API output structure is retained before CreateProcessW.
        # On a Python interruption, preserve any returned handles for cleanup.
        if worker.creation_info is not None:
            for field_name in ("process", "thread"):
                value = getattr(worker.creation_info, field_name)
                if value and getattr(worker, field_name) is None:
                    setattr(worker, field_name, self._retain(value, field_name))

    def create_suspended_worker(self, read_set, executable, arguments, working_directory, environment,
                                inherited_control_handles=(), include_control_handle_argument=False):
        """Owned suspended process only; no runtime command/resume admission.

        No shell, process-name lookup, ambient environment or breakaway flags.
        Inherited guards protect their corresponding files through child death
        only if a future trusted bootstrap keeps them open. That is unqualified.
        """
        if (not any(item is read_set for item in self.read_sets) or read_set.unconfirmed
                or read_set.released or read_set.worker_reserved
                or len(read_set.members) != len(read_set.identities)):
            raise KernelUnconfirmed("Read-set ownership refused")
        if type(inherited_control_handles) is not tuple or len(inherited_control_handles) not in (0, 1):
            raise KernelUnavailable("One exact inherited duplex control endpoint required")
        for handle in inherited_control_handles:
            if handle.kind != "ipc-client":
                raise KernelUnavailable("Wrong inherited control handle kind")
            self._owned(handle)
        if type(include_control_handle_argument) is not bool or (include_control_handle_argument and len(inherited_control_handles) != 1):
            raise KernelUnavailable("Fixed control argument requires one inherited endpoint")
        _absolute_local_path(executable)
        _absolute_local_path(working_directory)
        if type(arguments) is not tuple or not 1 <= len(arguments) <= 16:
            raise KernelUnavailable("Fixed worker arguments required")
        command = " ".join(_quote_argument(value) for value in (executable,) + arguments)
        if len(command) > 32766:
            raise KernelUnavailable("Worker command size refused")
        environment_text = _environment_block(environment)
        worker = WorkerRecord(read_set=read_set)
        self.workers.append(worker)  # Retain ownership before any allocation.
        read_set.worker_reserved = True
        ffi = self.api.ffi
        attributes = None
        initialized = False
        pending_error = None
        try:
            worker.job = self._retain(self.api.call("CreateJobObjectW", None, None), "job")
            limits = self.api.structure("JOBOBJECT_EXTENDED_LIMIT_INFORMATION")
            limits.basic.flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            limits.basic.active_process_limit = 1
            self.api.checked("SetInformationJobObject", self._owned(worker.job), JOB_EXTENDED_LIMIT_CLASS,
                             ffi.byref(limits), ffi.sizeof(limits))
            for handle in (*read_set.members, *inherited_control_handles):
                worker.inherited_copies.append(self._duplicate_inheritable(handle))
            worker.child_read_handles = tuple(self._owned(handle) for handle in worker.inherited_copies[:len(read_set.members)])
            if inherited_control_handles:
                worker.child_control_handle = self._owned(worker.inherited_copies[-1])
            if include_control_handle_argument:
                # These decimal values identify inherited handles in this exact
                # child. They are not credentials or serialized capabilities.
                command = " ".join(_quote_argument(value) for value in (executable,) + arguments
                                   + ("--control-handle", str(worker.child_control_handle)))
                if len(command) > 32766:
                    raise KernelUnavailable("Worker command size refused")
            size = ffi.c_size_t()
            first = self.api.call("InitializeProcThreadAttributeList", None, 1, 0, ffi.byref(size))
            error = ffi.get_last_error()
            if first or error != ERROR_INSUFFICIENT_BUFFER or not 0 < size.value <= 65536:
                raise KernelUnavailable("Attribute-list size query refused")
            attributes = ffi.create_string_buffer(size.value)
            self.api.checked("InitializeProcThreadAttributeList", attributes, 1, 0, ffi.byref(size))
            initialized = True
            inherited = (ffi.c_void_p * len(worker.inherited_copies))(*(self._owned(h) for h in worker.inherited_copies))
            self.api.checked("UpdateProcThreadAttribute", attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                             inherited, ffi.sizeof(inherited), None, None)
            startup = self.api.structure("STARTUPINFOEXW")
            startup.startup.cb = ffi.sizeof(startup)
            startup.startup.flags = STARTF_USESHOWWINDOW
            startup.startup.show = SW_HIDE
            startup.attributes = ffi.cast(attributes, ffi.c_void_p)
            process = self.api.structure("PROCESS_INFORMATION")
            worker.creation_info = process
            command_buffer = ffi.create_unicode_buffer(command)
            environment_buffer = ffi.create_unicode_buffer(environment_text)
            self.api.checked("CreateProcessW", executable, command_buffer, None, None, 1,
                             CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT,
                             environment_buffer, working_directory, ffi.byref(startup), ffi.byref(process))
            self._adopt_process_outputs(worker)
            if worker.process is None or worker.thread is None:
                raise KernelUnconfirmed("CreateProcessW returned incomplete owned handles")
            self.api.checked("AssignProcessToJobObject", self._owned(worker.job), self._owned(worker.process))
            worker.assigned = True
            worker.creation_time = self._creation_time(worker.process)
            # Child has its own inherited handles. Keep the originals in the
            # read set, but remove temporary inheritable parent duplicates.
            for handle in worker.inherited_copies:
                self._close(handle)
            return worker
        except BaseException as original:
            pending_error = original
            worker.unconfirmed = True
            read_set.unconfirmed = True
            try:
                self._adopt_process_outputs(worker)
                self._stop_partial_worker(worker, 5000)
            except BaseException as cleanup_error:
                original.add_note("Partial worker remains owned/unconfirmed: " + type(cleanup_error).__name__)
            raise
        finally:
            if initialized:
                # Deletes only the local attribute list; not owned process/file
                # handles. The call is void and has no success receipt itself.
                try:
                    self.api.call("DeleteProcThreadAttributeList", attributes)
                except BaseException as cleanup_error:
                    worker.unconfirmed = True
                    read_set.unconfirmed = True
                    if pending_error is None:
                        try:
                            self._adopt_process_outputs(worker)
                            self._stop_partial_worker(worker, 5000)
                        except BaseException as stop_error:
                            cleanup_error.add_note("Worker stop remains unconfirmed: " + type(stop_error).__name__)
                        raise
                    pending_error.add_note("Attribute-list cleanup raised: " + type(cleanup_error).__name__)

    def _stop_partial_worker(self, worker, timeout_ms):
        if worker.process is None:
            return False
        process = self._owned(worker.process)
        if worker.assigned:
            self.api.checked("TerminateJobObject", self._owned(worker.job), 1)
        else:
            # A child created suspended but not assigned cannot be released.
            # Terminate the exact retained process handle, never an integer PID.
            self.api.checked("TerminateProcess", process, 1)
        return self.api.call("WaitForSingleObject", process, timeout_ms) == WAIT_OBJECT_0

    def resume_worker(self, worker):
        # Mechanics are present below for review, but complete worker bootstrap,
        # IPC, namespace and loader admission is not represented by this record.
        raise KernelUnavailable("No real worker bootstrap/load-plan admission exists")

    def _resume_after_future_admission(self, worker):
        if (not any(item is worker for item in self.workers) or worker.unconfirmed or not worker.assigned
                or worker.resumed or worker.shutdown_started or worker.creation_time != self._creation_time(worker.process)):
            raise KernelUnconfirmed("Suspended worker identity/state refused")
        try:
            prior = self.api.call("ResumeThread", self._owned(worker.thread))
            if prior != 1:
                raise KernelUnconfirmed("Suspended thread count was not exactly one")
            worker.resumed = True
        except BaseException:
            worker.unconfirmed = True
            worker.read_set.unconfirmed = True
            raise

    def terminate_and_observe(self, worker, timeout_ms=5000):
        if (not any(item is worker for item in self.workers) or worker.unconfirmed or not worker.assigned
                or type(timeout_ms) is not int or not 0 <= timeout_ms <= 30000):
            raise KernelUnconfirmed("Worker termination scope refused")
        if worker.quiescent:
            return True
        worker.shutdown_started = True
        try:
            if worker.creation_time != self._creation_time(worker.process):
                raise KernelUnconfirmed("Retained process creation identity changed")
            self.api.checked("TerminateJobObject", self._owned(worker.job), 1)
            waited = self.api.call("WaitForSingleObject", self._owned(worker.process), timeout_ms)
            if waited != WAIT_OBJECT_0:
                raise KernelUnconfirmed("Exact process termination was not observed")
            accounting = self.api.structure("JOBOBJECT_BASIC_ACCOUNTING_INFORMATION")
            returned = self.api.ffi.c_uint32()
            self.api.checked("QueryInformationJobObject", self._owned(worker.job), JOB_BASIC_ACCOUNTING_CLASS,
                             self.api.ffi.byref(accounting), self.api.ffi.sizeof(accounting), self.api.ffi.byref(returned))
            if returned.value != self.api.ffi.sizeof(accounting) or accounting.active_processes != 0:
                raise KernelUnconfirmed("Job still has active or unconfirmed work")
            worker.quiescent = True
            return True
        except BaseException:
            worker.unconfirmed = True
            worker.read_set.unconfirmed = True
            raise

    def close_quiescent_worker_handles(self, worker):
        if (not any(item is worker for item in self.workers) or worker.unconfirmed or not worker.quiescent):
            raise KernelUnconfirmed("Worker handle closure requires observed quiescence")
        try:
            for handle in (worker.thread, worker.process, worker.job):
                if handle is not None and not handle.closed:
                    self._close(handle)
        except BaseException:
            worker.unconfirmed = True
            worker.read_set.unconfirmed = True
            raise

    def release_read_set(self, read_set):
        if not any(item is read_set for item in self.read_sets) or read_set.unconfirmed or read_set.released:
            raise KernelUnconfirmed("Read-set release refused")
        owners = [worker for worker in self.workers if worker.read_set is read_set]
        if any(worker.unconfirmed or not worker.quiescent for worker in owners):
            raise KernelUnconfirmed("Owned native lifetime remains unconfirmed")
        try:
            for handle in reversed(read_set.members):
                if not handle.closed:
                    self._close(handle)
            read_set.released = True
            return True
        except BaseException:
            read_set.unconfirmed = True
            raise
