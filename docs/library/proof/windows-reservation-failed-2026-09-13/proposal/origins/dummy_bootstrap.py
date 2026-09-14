"""Unexecuted, fixed generated-only bootstrap awaiting root's exact admission."""
import sys

BASELINE_WINREG = sys.modules.get("winreg")
assert BASELINE_WINREG is not None and getattr(BASELINE_WINREG.__spec__, "origin", None) == "built-in"
assert not hasattr(BASELINE_WINREG, "__file__")
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
DENIALS = []


def deny_registry(*args, **kwargs):
    DENIALS.append("registry_callable")
    raise RuntimeError("Registry operations prohibited")


REGISTRY_TRAPS = tuple((name, value) for name, value in REGISTRY_NAMESPACE.items()
                      if not name.startswith("_") and callable(value))
for name, original in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, deny_registry)


def early_audit(event, args):
    if event.startswith(("winreg.", "socket.", "subprocess.")):
        DENIALS.append(event)
        raise RuntimeError("Early prohibited operation")


sys.addaudithook(early_audit)
import contextlib
import dataclasses
import enum
import hashlib
import hmac
import importlib.machinery
import json
import math
import os
from pathlib import Path
import struct
import sysconfig
import threading
import time
import types
import encodings.utf_16_le
import warnings

PROCESS_ABORT = os._exit  # Retained current-process failure exit; never an IPC operation.

FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
FIXED_RUNS = {'drain': 'E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\generated-actual-adapter-drain01'}
LOCATION = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
MODE = next((mode for mode, path in FIXED_RUNS.items() if os.path.normcase(path) == LOCATION), None)
assert MODE is not None, "fixed_fresh_generated_operation_directory"
CASE = "positive"
EXPECTED_RUN = FIXED_RUNS[MODE]
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert os.path.normcase(os.path.dirname(os.path.abspath(__file__))) == os.path.normcase(EXPECTED_RUN)
assert sys.executable.casefold() == r"C:\Python314\python.exe".casefold()
ROLE = sys.argv[1] if len(sys.argv) >= 2 else None
assert (ROLE == "controller" and len(sys.argv) == 2) or (ROLE == "child" and len(sys.argv) == 4 and sys.argv[2] == "--control-handle")
CONTROL = int(sys.argv[3]) if ROLE == "child" and sys.argv[3].isascii() and sys.argv[3].isdigit() else None
if ROLE == "child":
    assert CONTROL is not None and 0 < CONTROL < (1 << 64) - 1

HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "subprocess", "socket"}
assert not HEAVY.intersection(name.split(".")[0] for name in sys.modules)
assert "ctypes" not in sys.modules and "_ctypes" not in sys.modules
GENERATED_NAMES = ("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")
GENERATED_BYTES = {name: ("Uoink generated adoption fixture: " + name + ". No model data.\n").encode("ascii") for name in GENERATED_NAMES}
GENERATED_PATHS = tuple(os.path.join(EXPECTED_RUN, name) for name in GENERATED_NAMES)
RESULT_PATH = os.path.join(EXPECTED_RUN, ROLE + "-result.json")
KERNEL_PATH = r"C:\Windows\System32\kernel32.dll"
NATIVE = {
    r"C:\Python314\python.exe": (106208, "03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38"),
    r"C:\Python314\python314.dll": (6778592, "fde89cdb5c2d08ae65de7ef4abca1876c93ba3796002f5ac0bf7e4d4f5a94da0"),
    r"C:\Python314\python3.dll": (73952, "22c6e46d8bd563cdb072650901461ef68be2ea6cb1e80af859559d9395a27e39"),
    r"C:\Python314\DLLs\_ctypes.pyd": (142560, "25d9b0be550d428fecc697ca20450343a7c3ce77c9f5283e9aecfd188d609250"),
    r"C:\Python314\DLLs\libffi-8.dll": (39696, "eff52743773eb550fcc6ce3efc37c85724502233b6b002a35496d828bd7b280a"),
    KERNEL_PATH: (844496, "8f8629741558b5df71def4e1dd8ef9645d4f806b949762c47757c50fea1a9e6d"),
    r"C:\Python314\Lib\ctypes\__init__.py": (22814, "8c16b1320357ccfac6cc4b6d08e6d61b5dfb8bc700877b35fb711a840d65aecd"),
    r"C:\Python314\Lib\ctypes\_layout.py": (11772, "13eb492c805248ffd411aa4d61e4de90dbd89ef05b5c85152262847c690a7916"),
    r"C:\Python314\Lib\ctypes\_endian.py": (2635, "f2752ab2425dac9bfaff5aa1a3c6cd66aa342fee0db2f2a42de568fc59d5cbea"),
}
MODULES = ("snapshot_lifecycle", "owned_generation_protocol", "win32_worker_connection",
           "win32_private_pipe", "pinned_buffer_namespace", "inherited_readset", "generated_worker_flow", "generated_operation_flow",
           "trusted_asr_resolver", "asr_loading_adapter", "generated_adapter_flow")
SETUP_NAMES = tuple(name + ".py" for name in MODULES) + ("dummy_bootstrap.py", "SOURCE-INPUTS.json", "ROOT-ADMISSION.json")
SETUP_READS = {os.path.normcase(os.path.join(EXPECTED_RUN, name)) for name in SETUP_NAMES}
SETUP_READS |= {os.path.normcase(path) for path in NATIVE}
# Neither controller nor child opens generated content through Python.
# The exact outer writer records those bytes; native handle reads occur
# only in the child after authenticated adoption. No path reopening.
CONTENT_OPEN = True
DLL_STAGE = "closed"
DLL_EVENTS = []
RESULT_WRITTEN = False
CALL_CONTEXT = None
ALLOWED_IMPORTS = set(sys.modules) | set(MODULES) | {"ctypes", "ctypes._endian", "ctypes._layout", "_ctypes"}


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        if not isinstance(path, str):
            allowed = False
        else:
            normalized = os.path.normcase(os.path.abspath(path))
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = (CONTENT_OPEN and not write and normalized in SETUP_READS)
            allowed = allowed or (not RESULT_WRITTEN and normalized == os.path.normcase(RESULT_PATH)
                                   and write and bool(flags & os.O_EXCL) and bool(flags & os.O_CREAT))
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS and args[0].split(".")[0] not in HEAVY
    elif event.startswith(("os.", "socket.", "subprocess.", "winreg.")):
        allowed = False
    elif event == "ctypes.dlopen":
        allowed = DLL_STAGE == "binding" and args[0] in ("kernel32", KERNEL_PATH) and len(DLL_EVENTS) < 2
        if allowed:
            DLL_EVENTS.append(args[0])
    elif event == "ctypes.dlsym":
        allowed = DLL_STAGE == "binding" and type(args[1]) is str and args[1] in SYMBOLS
    elif event == "ctypes.call_function":
        context = CALL_CONTEXT
        allowed = (context is not None and context["thread"] == threading.get_ident()
                   and len(args) == 2 and type(args[0]) is int and args[0] == context["pointer"]
                   and type(args[1]) is tuple and len(args[1]) == len(context["arguments"])
                   and all(observed is expected for observed, expected in zip(args[1], context["arguments"]))
                   and context["events"] == 0)
        if allowed:
            context["events"] += 1
    elif event == "ctypes.create_string_buffer":
        allowed = type(args[1]) is int and 0 < args[1] <= 65536
    elif event == "ctypes.create_unicode_buffer":
        allowed = type(args[1]) is int and 0 < args[1] <= 32768
    elif event == "ctypes.get_last_error":
        # Required thread-local error bookkeeping, with no target or argument.
        allowed = len(args) == 0
    elif event.startswith("ctypes."):
        allowed = False
    if not allowed:
        detail = event
        if event == "import" and type(args[0]) is str and len(args[0]) <= 128 and all(char.isascii() and (char.isalnum() or char in "._") for char in args[0]):
            detail += ":" + args[0]
        DENIALS.append(detail)
        raise RuntimeError("Fixed dummy boundary refused " + detail)


SYMBOLS = {"GetLastError", "CreateFileW", "GetFinalPathNameByHandleW", "GetFileInformationByHandleEx", "CloseHandle",
           "GetCurrentProcess", "DuplicateHandle", "CreateJobObjectW", "SetInformationJobObject", "QueryInformationJobObject",
           "AssignProcessToJobObject", "TerminateJobObject", "TerminateProcess", "WaitForSingleObject", "GetProcessTimes",
           "ResumeThread", "InitializeProcThreadAttributeList", "UpdateProcThreadAttribute", "DeleteProcThreadAttributeList",
           "CreateProcessW", "CreateNamedPipeW", "ConnectNamedPipe", "CreateEventW", "ReadFile", "WriteFile",
           "GetOverlappedResult", "CancelIoEx", "GetFileType", "GetHandleInformation", "SetHandleInformation",
           "GetExitCodeProcess", "GetModuleFileNameW", "SetFilePointerEx"}
sys.addaudithook(audit)


def read_bounded(path, cap):
    with open(path, "rb") as stream:
        raw = stream.read(cap + 1)
    assert len(raw) <= cap
    return raw


source_map = json.loads(read_bounded(os.path.join(EXPECTED_RUN, "SOURCE-INPUTS.json"), 65536))
admission = json.loads(read_bounded(os.path.join(EXPECTED_RUN, "ROOT-ADMISSION.json"), 65536))
assert admission["root_reviewed"] is True and admission["scope"] == "generated-actual-asr-adapter-only"
assert admission["case"] == CASE and admission["operation_mode"] == MODE and admission["run_path"] == EXPECTED_RUN
assert admission["source_inputs_sha256"] == hashlib.sha256(read_bounded(os.path.join(EXPECTED_RUN, "SOURCE-INPUTS.json"), 65536)).hexdigest()
assert source_map["native_bindings"] == {path: {"bytes": size, "sha256": sha} for path, (size, sha) in NATIVE.items()}
RAW = {}
for name in tuple(module + ".py" for module in MODULES) + ("dummy_bootstrap.py",):
    raw = read_bounded(os.path.join(EXPECTED_RUN, name), 1048576)
    assert hashlib.sha256(raw).hexdigest() == source_map["source_sha256"][name]
    RAW[name] = raw
CTYPES_RAW = {}
for path, (size, sha) in NATIVE.items():
    raw = read_bounded(path, size)
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    if path.endswith(".py"):
        CTYPES_RAW[path] = raw
CONTENT_OPEN = False


def deny_metadata(*args, **kwargs):
    DENIALS.append("metadata")
    raise RuntimeError("Python filesystem metadata prohibited after setup")


METADATA_TRAPS = []
for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),
                     (os, ("stat", "lstat", "fstat", "scandir", "listdir")), (os.path, ("realpath",))):
    for name in names:
        setattr(owner, name, deny_metadata)
        METADATA_TRAPS.append((owner, name, deny_metadata))


class VerifiedCtypesLoader:
    def __init__(self, name, path):
        self.name, self.path = name, path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = self.path
        if self.name == "ctypes":
            module.__path__ = []
        exec(compile(CTYPES_RAW[self.path], self.path, "exec"), module.__dict__)


class FixedFinder:
    def find_spec(self, name, path=None, target=None):
        if name == "_ctypes":
            origin = r"C:\Python314\DLLs\_ctypes.pyd"
            spec = importlib.machinery.ModuleSpec(name, importlib.machinery.ExtensionFileLoader(name, origin), origin=origin)
            spec.has_location = True
            return spec
        if name in ("ctypes", "ctypes._endian", "ctypes._layout"):
            origin = {"ctypes": r"C:\Python314\Lib\ctypes\__init__.py", "ctypes._endian": r"C:\Python314\Lib\ctypes\_endian.py", "ctypes._layout": r"C:\Python314\Lib\ctypes\_layout.py"}[name]
            return importlib.machinery.ModuleSpec(name, VerifiedCtypesLoader(name, origin), origin=origin, is_package=name == "ctypes")
        if name not in ALLOWED_IMPORTS or name.split(".")[0] in HEAVY:
            DENIALS.append("import_finder")
            raise ImportError("Fixed dummy import scope")
        return None


FINDER = FixedFinder()
sys.meta_path.insert(0, FINDER)
for name in MODULES:
    module = types.ModuleType(name)
    module.__file__ = os.path.join(EXPECTED_RUN, name + ".py")
    sys.modules[name] = module
    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)
K, W, NS, ADOPTION, FLOW = (sys.modules[name] for name in ("win32_worker_connection", "win32_private_pipe",
    "pinned_buffer_namespace", "inherited_readset", "generated_adapter_flow"))
REAL_RESOLVER = sys.modules["trusted_asr_resolver"]
ADAPTER = sys.modules["asr_loading_adapter"]
ORIGINAL_REAL_FUNCTIONS = (REAL_RESOLVER.load_manifest, REAL_RESOLVER.admit_snapshot, REAL_RESOLVER.bind_for_constructor)
ORIGINAL_ADAPTER_RELEASE = ADAPTER._release
ADAPTER_GLOBAL_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
assert REAL_RESOLVER.REAL_APPROVAL is None and ADAPTER.resolver is REAL_RESOLVER
assert all(getattr(ADAPTER, name) is None for name in ADAPTER_GLOBAL_NAMES)
assert ADOPTION.NAMES == GENERATED_NAMES and dict(ADOPTION.GENERATED) == GENERATED_BYTES
DLL_STAGE = "binding"
import ctypes
assert ctypes.__file__ == r"C:\Python314\Lib\ctypes\__init__.py"
assert sys.modules["_ctypes"].__file__ == r"C:\Python314\DLLs\_ctypes.pyd"
kernel32 = ctypes.WinDLL(KERNEL_PATH, use_last_error=True, winmode=0x800)
assert ctypes.windll.kernel32._handle == kernel32._handle
api = K.declare_bindings(ctypes, kernel32)
W.declare_pipe_calls(api, kernel32)
FLOW.declare_exit_call(api, kernel32)
NS.declare_read_calls(api, kernel32)
module_name = kernel32.GetModuleFileNameW
module_name.restype = ctypes.c_uint32
module_name.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
api.functions["GetModuleFileNameW"] = module_name
DLL_STAGE = "closed"


class FixedNativeDispatch:
    """Finite source-bound registry; no arbitrary-address or callback interface."""
    def __init__(self, ffi, functions):
        self.ffi = ffi
        self.original_cast = ffi.cast
        self.cast_helper = ffi._cast
        self.cast_address = ffi._cast_addr
        self.bindings = types.MappingProxyType(dict(functions))
        self.signatures = types.MappingProxyType({name: self._signature(fn) for name, fn in self.bindings.items()})
        self.cast_signature = self._signature(self.cast_helper)
        self.addresses = {}
        self.attribute_buffer = None
        self.cast_calls = 0
        self.call_events = 0
        self.completed_calls = 0
        self.invalid_contexts = 0
        self.binding_open = True
        assert type(self.cast_address) is int and self.cast_address > 0
        assert set(self.bindings) == SYMBOLS - {"GetLastError"} and len(self.bindings) == 32
        for name, fn in self.bindings.items():
            pointer = self._helper_cast(fn, ffi.c_void_p, binding=True)
            assert type(pointer.value) is int and pointer.value > 0
            self.addresses[name] = pointer.value
        self.binding_open = False
        self.addresses = types.MappingProxyType(self.addresses)
        self.wrapper = self.cast
        ffi.cast = self.wrapper

    @staticmethod
    def _signature(fn):
        return (type(fn), tuple(fn.argtypes), fn.restype, fn._flags_, getattr(fn, "errcheck", None))

    def _invoke(self, function, pointer, arguments, label):
        global CALL_CONTEXT
        assert CALL_CONTEXT is None and type(arguments) is tuple, "fixed_dispatch_serial_entry"
        assert type(pointer) is int and pointer > 0 and len(arguments) <= 11
        context = {"thread": threading.get_ident(), "pointer": pointer, "arguments": arguments,
                   "function": function, "label": label, "events": 0}
        CALL_CONTEXT = context
        try:
            result = function(*arguments)
        finally:
            verified = CALL_CONTEXT is context and context["events"] == 1
            CALL_CONTEXT = None
            self.call_events += context["events"]
            self.completed_calls += 1
            if not verified:
                self.invalid_contexts += 1
        assert verified, "fixed_dispatch_one_matching_event_required"
        return result

    def _helper_cast(self, obj, target, *, binding=False):
        assert self.ffi._cast is self.cast_helper and self.ffi._cast_addr == self.cast_address
        assert self._signature(self.cast_helper) == self.cast_signature and target is self.ffi.c_void_p
        if binding:
            assert self.binding_open and any(obj is fn for fn in self.bindings.values())
        else:
            assert not self.binding_open and ROLE == "controller" and obj is self.attribute_buffer
            assert obj is not None and isinstance(obj, self.ffi.Array) and obj._type_ is self.ffi.c_char
            assert 0 < self.ffi.sizeof(obj) <= 65536 and self.cast_calls == 0
            self.cast_calls += 1
        return self._invoke(self.cast_helper, self.cast_address, (obj, obj, target), "fixed_cast_helper")

    def cast(self, obj, target):
        return self._helper_cast(obj, target)

    def call(self, name, *arguments):
        assert name in self.bindings and not self.binding_open
        fn = self.bindings[name]
        assert self._signature(fn) == self.signatures[name], "fixed_dispatch_signature"
        return self._invoke(fn, self.addresses[name], arguments, name)

    def valid(self, functions):
        return (CALL_CONTEXT is None and self.invalid_contexts == 0 and not self.binding_open and self.ffi.cast is self.wrapper
                and self.ffi._cast is self.cast_helper and self.ffi._cast_addr == self.cast_address
                and self._signature(self.cast_helper) == self.cast_signature
                and set(functions) == set(self.bindings) == set(self.addresses)
                and all(functions[name] is fn and self._signature(fn) == self.signatures[name]
                        for name, fn in self.bindings.items()))


dispatch = FixedNativeDispatch(ctypes, api.functions)

name_buffer = ctypes.create_unicode_buffer(32768)
name_length = dispatch.call("GetModuleFileNameW", kernel32._handle, name_buffer, len(name_buffer))
assert 0 < name_length < len(name_buffer) and name_buffer.value.casefold() == KERNEL_PATH.casefold()


class NativeMonitor:
    def __init__(self, original):
        self.ffi, self.functions, self.structs = original.ffi, original.functions, original.structs
        self.originals = dict(self.functions)
        self.calls = []
        self.started = time.monotonic()
        self.pipe_name = None
        self.primitives = None
        self.work_budget_closed = False
        self.cleanup_started = None
        self.cleanup_calls = []
        self.cleanup_wait_caps = []
        self.asset_io = {name: {"seeks": 0, "reads": 0, "bytes": 0} for name in GENERATED_NAMES}

    def _cleanup_scope(self, name, args, now):
        if self.cleanup_started is None:
            self.cleanup_started = now
        assert now - self.cleanup_started <= 10 and len(self.cleanup_calls) < 64, "reserved_cleanup_budget"
        p = self.primitives
        assert p is not None and args, "cleanup_requires_exact_owner"
        value = args[0]
        live = [handle for handle in p.handles if handle.value == value and not handle.closed and not handle.unconfirmed]
        assert len(live) == 1, "cleanup_handle_not_exactly_owned"
        if name == "TerminateJobObject":
            assert ROLE == "controller" and any(worker.job is live[0] for worker in p.workers), "cleanup_job_owner"
            assert args[1] == 1, "fixed_cleanup_exit"
        elif name == "TerminateProcess":
            assert ROLE == "controller" and any(worker.process is live[0] for worker in p.workers), "cleanup_process_owner"
            assert args[1] == 1, "fixed_cleanup_exit"
        elif name == "WaitForSingleObject":
            assert type(args[1]) is int and 0 <= args[1] <= 5000, "bounded_cleanup_wait"
            assert live[0].kind == "ipc-event" or any(worker.process is live[0] for worker in p.workers), "cleanup_wait_owner"
            remaining_ms = int((10 - (now - self.cleanup_started)) * 1000)
            assert remaining_ms > 0, "cleanup_wait_budget_exhausted"
            effective = min(args[1], remaining_ms)
            self.cleanup_wait_caps.append({"requested_ms": args[1], "effective_ms": effective})
            args = (args[0], effective)
        elif name in ("CancelIoEx", "GetOverlappedResult"):
            assert live[0].kind in ("ipc-server", "ipc-client", "ipc-inherited-client"), "cleanup_pipe_owner"
            if name == "GetOverlappedResult":
                assert len(args) == 4 and args[3] == 0, "cleanup_result_must_not_block"
        elif name == "CloseHandle":
            assert live[0].kind == "ipc-event", "only_completed_event_closure_in_reserved_cleanup"
        else:
            raise RuntimeError("Work budget closed; operation is outside reserved cleanup")
        self.cleanup_calls.append(name)
        return args

    def structure(self, name):
        return self.structs[name]()

    def checked(self, name, *args):
        if not self.call(name, *args):
            raise OSError(self.ffi.get_last_error(), "Fixed API failed: " + name)

    def _generated_member(self, value):
        assert self.primitives is not None
        matches = [(read_set, index, handle) for read_set in self.primitives.read_sets
                   for index, handle in enumerate(read_set.members)
                   if handle.value == value and handle.kind == "adopted-generated-member" and not handle.closed]
        assert len(matches) == 1, "exact_child_local_generated_member"
        read_set, index, handle = matches[0]
        assert len(read_set.members) == 5 and not handle.unconfirmed, "complete_partial_owner_required"
        return read_set, index, handle

    def _asset_scope(self, name, args):
        if ROLE != "child":
            assert name != "SetFilePointerEx", "only_child_generated_seek"
            return None
        if name in ("GetFileInformationByHandleEx", "GetFinalPathNameByHandleW", "SetFilePointerEx"):
            read_set, index, handle = self._generated_member(args[0])
            if name == "GetFileInformationByHandleEx":
                assert args[1] in (1, 9, 18), "fixed_identity_information_classes"
            elif name == "GetFinalPathNameByHandleW":
                assert len(args) == 4 and args[2] == 32768 and args[3] == 0, "fixed_identity_path_query"
            else:
                assert CASE == "positive" and not read_set.unconfirmed and not read_set.released
                assert len(args) == 4 and args[1] == args[3] == 0
                assert type(getattr(args[2], "_obj", None)) is self.ffi.c_int64, "exact_seek_output"
                asset_name = GENERATED_NAMES[index]
                assert self.asset_io[asset_name]["seeks"] == 0, "one_seek_per_generated_file"
                return asset_name
        if name == "ReadFile" and args[4] is None:
            read_set, index, handle = self._generated_member(args[0])
            asset_name = GENERATED_NAMES[index]
            state = self.asset_io[asset_name]
            assert CASE == "positive" and not read_set.unconfirmed and not read_set.released
            assert state["seeks"] == 1 and state["reads"] < 2, "seek_then_two_bounded_reads"
            assert isinstance(args[1], self.ffi.Array) and args[1]._type_ is self.ffi.c_char
            assert type(args[2]) is int and args[2] == len(GENERATED_BYTES[asset_name]) - state["bytes"] + 1
            assert self.ffi.sizeof(args[1]) == args[2] and 0 < args[2] <= 256
            assert type(getattr(args[3], "_obj", None)) is self.ffi.c_uint32, "exact_read_count_output"
            return asset_name
        return None

    def call(self, name, *args):
        assert name in self.originals, "fixed_native_symbol_required"
        now = time.monotonic()
        if self.work_budget_closed or len(self.calls) >= 2048 or now - self.started > 60:
            self.work_budget_closed = True
            args = self._cleanup_scope(name, args, now)
        if ROLE == "child":
            assert name in {"CreateEventW", "GetFileType", "GetHandleInformation", "SetHandleInformation", "CloseHandle",
                            "ReadFile", "WriteFile", "WaitForSingleObject", "GetOverlappedResult", "CancelIoEx",
                            "GetCurrentProcess", "GetProcessTimes", "SetFilePointerEx",
                            "GetFileInformationByHandleEx", "GetFinalPathNameByHandleW"}
        if name == "CreateNamedPipeW":
            assert ROLE == "controller" and self.pipe_name is None
            assert type(args[0]) is str and args[0].startswith("\\\\.\\pipe\\uoink-owned-")
            assert len(args[0]) == len("\\\\.\\pipe\\uoink-owned-") + 64
            self.pipe_name = args[0]
        if name == "CreateFileW":
            assert ROLE == "controller" and args[0] in (*GENERATED_PATHS, self.pipe_name)
            if args[0] in GENERATED_PATHS:
                assert (args[1], args[2], args[4], args[5]) in ((0x80000000, 1, 3, 0x00200000), (0x40000000, 7, 3, 0x00200000))
            else:
                assert (args[1], args[2], args[4], args[5]) == (0xC0000000, 0, 3, 0x40000000)
        if name == "CreateProcessW":
            assert ROLE == "controller" and sum(item == name for item in self.calls) == 0
            worker = self.primitives.workers[-1]
            expected = (r"C:\Python314\python.exe", "-I", "-S", "-B", __file__, "child", "--control-handle", str(worker.child_control_handle))
            assert args[0] == expected[0] and args[1].value == " ".join(K._quote_argument(value) for value in expected)
        asset_name = self._asset_scope(name, args)
        self.calls.append(name)  # Never record buffers, secrets or API arguments.
        if name == "InitializeProcThreadAttributeList" and args[0] is not None:
            assert dispatch.attribute_buffer is None, "one_attribute_buffer"
        if name == "DeleteProcThreadAttributeList":
            assert args[0] is dispatch.attribute_buffer, "exact_attribute_buffer_retirement"
        result = dispatch.call(name, *args)
        if asset_name is not None and result:
            if name == "SetFilePointerEx":
                assert args[2]._obj.value == 0, "generated_seek_observation"
                self.asset_io[asset_name]["seeks"] += 1
            elif name == "ReadFile":
                count = args[3]._obj.value
                assert 0 <= count <= args[2], "generated_native_read_count"
                self.asset_io[asset_name]["reads"] += 1
                self.asset_io[asset_name]["bytes"] += count
        if name == "InitializeProcThreadAttributeList" and args[0] is not None and result:
            dispatch.attribute_buffer = args[0]
        if name == "DeleteProcThreadAttributeList":
            dispatch.attribute_buffer = None
        return result


monitor = NativeMonitor(api)
primitives = K.OwnedWin32Primitives(monitor)
monitor.primitives = primitives
pipes = W.PrivatePipeController(primitives, time.monotonic)
try:
    port = None
    started = time.perf_counter()
    outcome, error_type, code = None, None, 1
    try:
        if ROLE == "child":
            outcome = FLOW.child_flow(primitives, pipes, CONTROL, source_map["source_sha256"]["dummy_bootstrap.py"], EXPECTED_RUN, CASE)
            code = outcome["child_flow_return"]
        else:
            expectations = []
            for name, path in zip(GENERATED_NAMES, GENERATED_PATHS):
                value = monitor.call("CreateFileW", path, 0x80000000, 1, None, 3, 0x00200000, None)
                initial = primitives._retain(value, "generated-identity-probe")
                identity = primitives.identity(initial)
                primitives._close(initial)
                assert identity.size == len(GENERATED_BYTES[name]) and identity.links == 1 and not identity.directory and initial.closed
                expectations.append((path, identity))
            environment = {"SystemRoot": r"C:\Windows", "WINDIR": r"C:\Windows", "TEMP": EXPECTED_RUN, "TMP": EXPECTED_RUN,
                           "TORCH_DEVICE_BACKEND_AUTOLOAD": "0", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                           "PYANNOTE_METRICS_ENABLED": "0", "IG_FORBIDDEN_LIVE": FORBIDDEN}
            namespace_sha = ADOPTION.namespace_digest()
            manifest_sha = "0" * 64  # Replaced before bootstrap by the exact inherited-handle map.
            port = FLOW.GeneratedLifecyclePort(primitives, pipes, tuple(expectations), r"C:\Python314\python.exe",
                ("-I", "-S", "-B", __file__, "child"), EXPECTED_RUN, environment,
                os.urandom(32).hex(), manifest_sha, namespace_sha, source_map["source_sha256"]["dummy_bootstrap.py"],
                os.urandom(32), os.urandom(32), CASE, operation_mode=MODE)
            outcome = FLOW.controller_flow(port)
            code = 0
    except BaseException as error:
        error_type = type(error).__name__
        if port is not None:
            port.quarantine(port.key, port.read_set, port.permit, "dummy bootstrap failure")
    elapsed = time.perf_counter() - started
    registry_expected = dict(REGISTRY_NAMESPACE)
    for name, original in REGISTRY_TRAPS:
        registry_expected[name] = deny_registry
    adapter_state = {
        "real_approval_none": REAL_RESOLVER.REAL_APPROVAL is None,
        "real_functions_unchanged": (REAL_RESOLVER.load_manifest, REAL_RESOLVER.admit_snapshot, REAL_RESOLVER.bind_for_constructor) == ORIGINAL_REAL_FUNCTIONS,
        "private_release_restored": ADAPTER._release is ORIGINAL_ADAPTER_RELEASE,
        "services_unconfigured": all(getattr(ADAPTER, name) is None for name in ADAPTER_GLOBAL_NAMES),
        "resolver_module_restored": ADAPTER.resolver is REAL_RESOLVER,
    }
    guard = (all(adapter_state.values()) and dispatch.valid(monitor.functions) and not DENIALS and not CONTENT_OPEN and DLL_STAGE == "closed" and sys.meta_path[0] is FINDER
             and sys.modules.get("winreg") is BASELINE_WINREG
             and set(vars(BASELINE_WINREG)) == set(registry_expected)
             and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items())
             and all(getattr(owner, name) is installed for owner, name, installed in METADATA_TRAPS)
             and all(monitor.functions[name] is value for name, value in monitor.originals.items())
             and os._exit is PROCESS_ABORT
             and not HEAVY.intersection(name.split(".")[0] for name in sys.modules))
    if not guard:
        code = 1
    receipt = {"schema": "uoink.generated-actual-asr-adapter.v1", "role": ROLE, "case": CASE, "operation_mode": MODE, "result": outcome, "error_type": error_type,
               "adapter_state": adapter_state, "native_exit_planned": code, "elapsed_seconds": elapsed, "guard_valid": guard, "guard_denials": DENIALS,
               "metadata_traps": len(METADATA_TRAPS), "registry_traps": len(REGISTRY_TRAPS),
               "fixed_dispatch_valid": dispatch.valid(monitor.functions),
               "fixed_dispatch_function_count": len(dispatch.bindings),
               "fixed_dispatch_completed_calls": dispatch.completed_calls,
               "fixed_dispatch_audit_events": dispatch.call_events,
               "fixed_dispatch_invalid_contexts": dispatch.invalid_contexts,
               "fixed_attribute_cast_calls": dispatch.cast_calls,
               "native_api_calls": monitor.calls, "generated_asset_io": monitor.asset_io,
               "pending_pipe_operations": sum(len(pair.operations) for pair in pipes.pairs),
               "reserved_cleanup_calls": monitor.cleanup_calls,
               "reserved_cleanup_wait_caps": monitor.cleanup_wait_caps,
               "work_budget_closed": monitor.work_budget_closed,
               "kernel32_path_verified": True, "ctypes_bootstrap_loads": DLL_EVENTS,
               "source_sha256": source_map["source_sha256"], "model_imports": [], "model_calls": 0}
    encoded = (json.dumps(receipt, indent=2) + "\n").encode()
    assert len(encoded) <= 131072
    with open(RESULT_PATH, "xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    RESULT_WRITTEN = True
    raise SystemExit(code)
finally:
    for retained_pair in pipes.pairs:
        if retained_pair.operations:
            PROCESS_ABORT(1)
